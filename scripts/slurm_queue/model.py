"""Resource-lane model for the Slurm draining queue.

A queue payload is a committed ``slurm/*.sbatch`` script.  Enqueueing parses
its ``#SBATCH`` directives into a :class:`ResourceProfile` — the lane identity
— plus the wall-clock seconds the script requests, which becomes its hard
timeout inside the worker allocation.

Parsing is closed by construction: only the directive set the current job
scripts use is accepted, short forms are normalized, and multinode, array,
dependency, requeue, or otherwise unmodelled requests are rejected instead of
approximated.  Child ``#SBATCH`` lines are comments to `bash`, so silently
dropping one would change execution semantics.

The same module owns the item/provenance record shapes and the small git
helpers that bind an item to the commit and blob it was enqueued from.

Invariants & Expected State:
    - Pure Parsing: a payload is read from text only; nothing here submits,
      executes, or touches Slurm.
    - Lane Identity: the canonical profile field set plus the cluster digest to
      the lane id, and queueing requires nodes = ntasks = 1 with an explicit
      ``--partition``.
    - Horizon Headroom: enqueue refuses a payload whose ``--time`` plus the item
      overhead and the handoff slack exceeds the worker horizon.
    - Bounded Probes: the git helpers read only, under ``GIT_TIMEOUT_SECONDS``,
      and refuse with ``ProvenanceError`` when a probe hangs or fails, so an
      unanswerable checkout cannot stall an allocation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from framework import harness
from scripts.slurm_queue.runtime import GIT_TIMEOUT_SECONDS

_QUEUE_SCHEMA = f"{harness.SLUG}.slurm-queue"
ITEM_SCHEMA = f"{_QUEUE_SCHEMA}.item.v1"
RECEIPT_SCHEMA = f"{_QUEUE_SCHEMA}.receipt.v1"
WORKER_SCHEMA = f"{_QUEUE_SCHEMA}.worker.v1"
SEQUENCE_SCHEMA = f"{_QUEUE_SCHEMA}.sequence.v1"
PROFILE_SCHEMA = f"{_QUEUE_SCHEMA}.profile.v1"
HANDOFF_FAILURE_SCHEMA = f"{_QUEUE_SCHEMA}.handoff-failure.v1"
WORKER_JOB_PREFIX = f"{harness.SLUG}_q_"
WORKER_SCRIPT_NAME = "run_slurm_queue_worker.sbatch"
# The worker launcher resolves the checkout it drains from this variable; the
# enqueue refuses when an explicit value disagrees with the checkout the item
# was built from, so a stale export cannot point the fresh worker at another tree.
WORKER_ROOT_ENV = harness.env("ROOT")
SCRIPT_ROOT = harness.SLURM_DIR
GATE_SCRIPT = "framework/gates/sbatch_gate.sh"
GATE_PREFLIGHT_ENV = "SBATCH_GATE_PREFLIGHT"
DRAIN_MARGIN_SECONDS = 300
# Provenance git probes are read-only and local: a wedged NFS mount or a hung
# credential helper must surface as a refusal, never as a stalled allocation.
# A worker's observed ``remaining`` is always a few seconds below the allocation
# limit (the job only starts after dispatch), so enqueue reserves this much extra
# horizon: without it an item whose ``--time`` plus the margin equals the horizon
# exactly is handed off by every successor forever.
HANDOFF_SLACK_SECONDS = 300
# Claim-time gate re-run bound: reserved in the fit test and enforced on the run,
# so an accepted item always has allocation time for its own ``--time`` after it.
PREFLIGHT_BUDGET_SECONDS = 1200
ITEM_OVERHEAD_SECONDS = DRAIN_MARGIN_SECONDS + PREFLIGHT_BUDGET_SECONDS
# An empty lane exits after this grace so a late enqueue lands in the live worker
# instead of paying a fresh allocation; 0 exits as soon as the lane drains.
EMPTY_GRACE_ENV = harness.env("QUEUE_EMPTY_GRACE_SECONDS")
EMPTY_GRACE_SECONDS = 600
DEFAULT_WORKER_TIME = "6-23:00:00"
WORKER_TIME_ENV = harness.env("QUEUE_WORKER_TIME")
QUEUE_ROOT_ENV = harness.env("QUEUE_ROOT")
QUEUE_CLUSTER_ENV = harness.env("QUEUE_CLUSTER")
# The child runs the resolved payload staged beside its log; this points at the
# payload's absolute path (repo joined with the script) so a payload can locate
# the checkout copy it came from.
PAYLOAD_ENV = harness.env("QUEUE_PAYLOAD")
RECORDED_ENV = re.compile(harness.env_regex())
UNRECORDED_ENV_PREFIX = harness.env("QUEUE") + "_"
DIRECTIVE = re.compile(r"^#SBATCH\s+(?P<body>--?\S.*)$")
SHORT_FLAGS = {
    "-c": "cpus-per-task",
    "-n": "ntasks",
    "-N": "nodes",
    "-p": "partition",
    "-t": "time",
}
DIRECTIVE_KEYS = frozenset(
    {
        "account",
        "constraint",
        "cpus-per-task",
        "exclude",
        "gres",
        "gpus",
        "job-name",
        "licenses",
        "mem",
        "nodelist",
        "nodes",
        "ntasks",
        "output",
        "partition",
        "qos",
        "reservation",
        "time",
    }
)
MEMORY_SUFFIXES = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
MIB = 1024 * 1024
REJECT_HINTS = {
    "array": "job arrays cannot share one draining worker",
    "dependency": "queue membership orders work; a job-level dependency hides it",
    "requeue": "a paused/requeued worker would strand pending items",
    "exclusive": "exclusive nodes cannot host the shared worker",
    "export": "the queue restores its own environment snapshot",
    "chdir": "items always execute from the repository root",
    "input": "items run without stdin",
    "wrap": "queue payloads are committed slurm/*.sbatch scripts",
    "signal": "the worker owns signal handling for its items",
}
RECEIPT_STATES = (
    "succeeded",
    "failed",
    "timed_out",
    "unfittable",
    "gate_failed",
    "payload_missing",
    "payload_dirty",
    "interrupted",
)


class SbatchRejection(ValueError):
    """Raised when a payload cannot be modelled as a queue item."""


class ProvenanceError(RuntimeError):
    """Raised when git cannot supply the commit or blob an item needs."""


def worker_job_name(lane_id: str) -> str:
    """Return the deterministic job name of a lane's worker."""
    return f"{WORKER_JOB_PREFIX}{lane_id}"


def now_iso() -> str:
    """Return the current UTC time in ISO-8601 form."""
    return datetime.now(UTC).isoformat()


def worker_time_seconds(environ: Mapping[str, str]) -> int:
    """Return the worker horizon from ``RESEARCH_QUEUE_WORKER_TIME`` (or default)."""
    return parse_duration(environ.get(WORKER_TIME_ENV, DEFAULT_WORKER_TIME))


def empty_grace_seconds(environ: Mapping[str, str]) -> float:
    """Return the empty-lane grace from ``RESEARCH_QUEUE_EMPTY_GRACE_SECONDS``."""
    raw = environ.get(EMPTY_GRACE_ENV)
    if raw is None or not raw.strip():
        return float(EMPTY_GRACE_SECONDS)
    try:
        grace = float(raw)
    except ValueError as error:
        raise SbatchRejection(f"{EMPTY_GRACE_ENV}={raw!r} is not a number") from error
    if not math.isfinite(grace) or grace < 0:
        raise SbatchRejection(
            f"{EMPTY_GRACE_ENV}={raw!r} is not a finite non-negative number"
        )
    return grace


def _int_field(text: str, label: str, raw: str) -> int:
    if not text.isdigit():
        raise SbatchRejection(f"{label} is not a number in {raw!r}")
    return int(text)


def parse_duration(text: str) -> int:
    """Parse a Slurm duration (``MM``, ``HH:MM:SS``, ``D-HH:MM:SS``) to seconds."""
    raw = text.strip()
    lowered = raw.lower()
    if not raw or lowered in {"infinite", "unlimited"}:
        raise SbatchRejection(f"unsupported time limit {text!r}")
    days_text, dash, clock = lowered.partition("-")
    if not dash:
        days_text, clock = "", days_text
    days = _int_field(days_text, "days", raw) if dash else 0
    fields = clock.split(":")
    if not fields or len(fields) > 3 or any(not item.isdigit() for item in fields):
        raise SbatchRejection(f"unsupported Slurm duration {text!r}")
    if dash:
        hours = _int_field(fields[0], "hours", raw)
        minutes = _int_field(fields[1], "minutes", raw) if len(fields) > 1 else 0
        seconds = _int_field(fields[2], "seconds", raw) if len(fields) > 2 else 0
    elif len(fields) == 3:
        hours, minutes, seconds = (int(item) for item in fields)
    elif len(fields) == 2:
        hours, minutes, seconds = 0, int(fields[0]), int(fields[1])
    else:
        hours, minutes, seconds = 0, int(fields[0]), 0
    total = ((days * 24 + hours) * 60 + minutes) * 60 + seconds
    if total <= 0:
        raise SbatchRejection(f"unsupported time limit {text!r}")
    return total


def format_duration(seconds: int) -> str:
    """Render seconds as the ``D-HH:MM:SS``/``HH:MM:SS`` form Slurm accepts."""
    days, rest = divmod(int(seconds), 86400)
    clock = f"{rest // 3600:02d}:{rest % 3600 // 60:02d}:{rest % 60:02d}"
    return f"{days}-{clock}" if days else clock


def parse_memory_mib(text: str) -> int:
    """Parse a Slurm memory request (``16G``, ``1024M``, bytes) into MiB."""
    match = re.fullmatch(r"(?P<value>\d+)(?P<unit>[KMGTkmgt]?)B?", text.strip())
    if not match:
        raise SbatchRejection(f"unsupported memory request {text!r}")
    value = int(match.group("value"))
    multiplier = MEMORY_SUFFIXES[match.group("unit").upper()]
    return max(1, -(-value * multiplier // MIB))


def split_directive(body: str, number: int) -> tuple[str, str]:
    """Split one ``#SBATCH`` body into its normalized ``(key, value)`` pair."""
    text = body.split("#", 1)[0].strip()
    flag, has_equals, tail = text.partition("=")
    if not has_equals:
        flag, has_space, tail = text.partition(" ")
        if not has_space:
            raise SbatchRejection(f"line {number}: directive {text!r} has no value")
    key = SHORT_FLAGS.get(flag, flag[2:] if flag.startswith("--") else "")
    if not key:
        raise SbatchRejection(f"line {number}: unsupported short flag {flag!r}")
    value = tail.strip().strip("'\"")
    if not value:
        raise SbatchRejection(f"line {number}: directive {flag} has an empty value")
    return key.lower(), value


def directive_values(source: str) -> dict[str, str]:
    """Return the raw ``key -> value`` map of a script's ``#SBATCH`` lines."""
    values: dict[str, str] = {}
    for number, line in enumerate(source.splitlines(), start=1):
        match = DIRECTIVE.match(line.strip())
        if match is None:
            continue
        key, value = split_directive(match.group("body"), number)
        if key in values:
            raise SbatchRejection(f"line {number}: duplicate #SBATCH {key}")
        values[key] = value
    if not values:
        raise SbatchRejection("no #SBATCH directives found")
    return values


def _rejection_message(unknown: Sequence[str]) -> str:
    details = [
        f"--{key} ({REJECT_HINTS[key]})" if key in REJECT_HINTS else f"--{key}"
        for key in unknown
    ]
    return (
        "queueing does not model "
        + ", ".join(details)
        + "; submit this script directly"
    )


def _int_directive(values: Mapping[str, str], key: str, default: int) -> int:
    if key not in values:
        return default
    return _int_field(values[key], key, values[key])


def _profile_fields(values: Mapping[str, str]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key in (
        "account",
        "constraint",
        "exclude",
        "gres",
        "gpus",
        "licenses",
        "nodelist",
        "qos",
        "reservation",
    ):
        fields[key.replace("-", "_")] = values.get(key)
    fields["mem_mib"] = parse_memory_mib(values["mem"]) if "mem" in values else None
    return fields


@dataclass(frozen=True)
class ResourceProfile:
    """The allocation shape of one lane; its digest is the lane identity."""

    cluster: str
    partition: str
    nodes: int
    ntasks: int
    cpus_per_task: int
    worker_time_seconds: int
    account: str | None = None
    constraint: str | None = None
    exclude: str | None = None
    gres: str | None = None
    gpus: str | None = None
    licenses: str | None = None
    mem_mib: int | None = None
    nodelist: str | None = None
    qos: str | None = None
    reservation: str | None = None

    @classmethod
    def build(
        cls, values: Mapping[str, str], cluster: str, worker_seconds: int
    ) -> ResourceProfile:
        """Build a profile from parsed directives, rejecting unusable shapes."""
        nodes = _int_directive(values, "nodes", 1)
        ntasks = _int_directive(values, "ntasks", 1)
        if nodes != 1 or ntasks != 1:
            raise SbatchRejection(
                f"queueing requires nodes=1 and ntasks=1, got nodes={nodes} ntasks={ntasks}"
            )
        if "partition" not in values:
            raise SbatchRejection("queueing requires an explicit #SBATCH --partition")
        return cls(
            cluster=cluster,
            partition=values["partition"],
            nodes=nodes,
            ntasks=ntasks,
            cpus_per_task=_int_directive(values, "cpus-per-task", 1),
            worker_time_seconds=worker_seconds,
            **_profile_fields(values),
        )

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> ResourceProfile:
        """Rebuild a profile from its stored record, ignoring unknown keys."""
        known = {
            name: Value
            for name, Value in record.items()
            if name in cls.__dataclass_fields__
        }
        return cls(**known)  # type: ignore[arg-type]

    def canonical(self) -> dict[str, object]:
        """Return the exact fields that make two profiles different lanes."""
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    def lane_id(self) -> str:
        """Return the 16-hex lane identity hashed over the canonical profile."""
        blob = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def sbatch_args(self) -> list[str]:
        """Return the ``sbatch`` resource overrides that reproduce this lane."""
        args = [
            f"--partition={self.partition}",
            f"--nodes={self.nodes}",
            f"--ntasks={self.ntasks}",
            f"--cpus-per-task={self.cpus_per_task}",
        ]
        pairs = (
            ("--account", self.account),
            ("--constraint", self.constraint),
            ("--exclude", self.exclude),
            ("--gres", self.gres),
            ("--gpus", self.gpus),
            ("--licenses", self.licenses),
            ("--nodelist", self.nodelist),
            ("--qos", self.qos),
            ("--reservation", self.reservation),
        )
        args.extend(f"{flag}={value}" for flag, value in pairs if value is not None)
        if self.mem_mib is not None:
            args.append(f"--mem={self.mem_mib}M")
        else:
            # The worker hosts the payload as a child process, so a lane whose
            # payload declared no --mem must not inherit the worker script's own
            # request: 0 means "all memory on the node". An explicit request is
            # also what makes the lane unschedulable where nodes report no
            # tracked memory (some clusters advertise no per-node RealMemory).
            args.append("--mem=0")
        return args

    def record(self) -> dict[str, object]:
        """Return the lane's ``profile.json`` payload."""
        return {"schema": PROFILE_SCHEMA, "lane_id": self.lane_id(), **self.canonical()}


@dataclass(frozen=True)
class QueueItem:
    """One enqueued payload and everything needed to replay its provenance."""

    item_id: str
    sequence: int
    lane_id: str
    enqueued_at: str
    script: str
    script_sha256: str
    commit: str
    run_name: str
    requested_seconds: int
    profile: ResourceProfile
    handoffs: int = 0
    banks: tuple[str, ...] = ()
    seeds: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> QueueItem:
        """Rebuild an item from its stored record, ignoring unknown keys."""
        fields = dict(record)
        fields["profile"] = ResourceProfile.from_record(record["profile"])  # type: ignore[arg-type]
        fields["banks"] = tuple(record.get("banks") or ())
        fields["seeds"] = tuple(record.get("seeds") or ())
        fields["env"] = tuple(tuple(pair) for pair in record.get("env") or ())
        fields["handoffs"] = int(record.get("handoffs") or 0)
        return cls(
            **{
                name: fields[name]
                for name in cls.__dataclass_fields__
                if name in fields
            }
        )  # type: ignore[arg-type]

    def record(self) -> dict[str, object]:
        """Return the item's persisted payload."""
        return {
            "schema": ITEM_SCHEMA,
            "item_id": self.item_id,
            "sequence": self.sequence,
            "lane_id": self.lane_id,
            "enqueued_at": self.enqueued_at,
            "script": self.script,
            "script_sha256": self.script_sha256,
            "commit": self.commit,
            "run_name": self.run_name,
            "requested_seconds": self.requested_seconds,
            "profile": self.profile.canonical(),
            "handoffs": self.handoffs,
            "banks": list(self.banks),
            "seeds": list(self.seeds),
            "env": [list(pair) for pair in self.env],
        }

    def env_map(self) -> dict[str, str]:
        """Return the recorded environment snapshot as a mapping."""
        return dict(self.env)


def parse_sbatch(
    source: str, cluster: str, worker_time: str
) -> tuple[ResourceProfile, int]:
    """Parse one sbatch script into its lane profile and requested seconds."""
    values = directive_values(source)
    unknown = sorted(set(values) - DIRECTIVE_KEYS)
    if unknown:
        raise SbatchRejection(_rejection_message(unknown))
    if "time" not in values:
        raise SbatchRejection("queueing requires an explicit #SBATCH --time")
    profile = ResourceProfile.build(values, cluster, parse_duration(worker_time))
    requested = parse_duration(values["time"])
    reserve = ITEM_OVERHEAD_SECONDS + HANDOFF_SLACK_SECONDS
    if requested + reserve > profile.worker_time_seconds:
        raise SbatchRejection(
            f"--time={values['time']} ({requested}s) plus the lane's item overhead "
            f"({PREFLIGHT_BUDGET_SECONDS}s claim-time gate budget + {DRAIN_MARGIN_SECONDS}s "
            f"drain margin) and the {HANDOFF_SLACK_SECONDS}s handoff slack exceeds the "
            f"{worker_time} worker horizon; raise {WORKER_TIME_ENV} to an accepted duration "
            "or submit this script directly"
        )
    return profile, requested


def resolve_script(repo: Path, script: str) -> str:
    """Validate a payload path as a repository-relative ``slurm/*.sbatch`` file."""
    candidate = Path(script)
    if candidate.is_absolute():
        raise SbatchRejection(f"expect a repository-relative payload, got {script!r}")
    if candidate.name == WORKER_SCRIPT_NAME:
        raise SbatchRejection("refusing to enqueue the queue worker itself")
    if len(candidate.parts) != 2 or candidate.parts[0] != SCRIPT_ROOT:
        raise SbatchRejection(
            f"queue payloads are {SCRIPT_ROOT}/*.sbatch files, got {script!r}"
        )
    if candidate.suffix != ".sbatch" or candidate.name.startswith("."):
        raise SbatchRejection(
            f"queue payloads are {SCRIPT_ROOT}/*.sbatch files, got {script!r}"
        )
    absolute = repo / candidate
    if absolute.is_symlink():
        raise SbatchRejection(f"payload {script} is a symlink")
    if not absolute.is_file():
        raise SbatchRejection(f"missing payload script {repo / candidate}")
    if not absolute.resolve().is_relative_to(repo.resolve()):
        raise SbatchRejection(f"payload {script} escapes the repository")
    return candidate.as_posix()


def run_git(repo: Path, args: Sequence[str]) -> str:
    """Run a read-only git command, failing closed when it cannot answer."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise ProvenanceError(
            f"git {' '.join(args)} timed out after {GIT_TIMEOUT_SECONDS:.0f}s"
        ) from error
    if result.returncode:
        raise ProvenanceError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def head_commit(repo: Path) -> str:
    """Return the commit the repository currently has checked out."""
    commit = run_git(repo, ["rev-parse", "HEAD"]).strip()
    if not commit:
        raise ProvenanceError("git rev-parse HEAD returned no commit")
    return commit


def is_dirty(repo: Path) -> bool:
    """Return whether the working tree differs from HEAD."""
    return bool(run_git(repo, ["status", "--porcelain"]).strip())


def committed_text(repo: Path, script: str) -> str:
    """Return the committed text of a payload script (it must be in HEAD)."""
    return run_git(repo, ["show", f"HEAD:{script}"])


def sha256_text(text: str) -> str:
    """Return the SHA-256 digest of a text payload."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def environment_snapshot(environ: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Record the ``RESEARCH_*`` override set, minus the queue's own variables."""
    recorded = [
        (key, value)
        for key, value in sorted(environ.items())
        if RECORDED_ENV.match(key) and not key.startswith(UNRECORDED_ENV_PREFIX)
    ]
    return tuple(recorded)


RECEIPT_FIELDS = (
    "item_id",
    "sequence",
    "lane_id",
    "worker_job_id",
    "script",
    "run_name",
    "banks",
    "seeds",
    "state",
    "exit_code",
    "started_at",
    "finished_at",
    "log",
    "reason",
    "enqueued_commit",
    "executed_commit",
    "executed_script_sha256",
    "tree_state",
    "payload_env",
)


def receipt_record(**fields: object) -> dict[str, object]:
    """Build a terminal receipt payload in the queue's receipt schema."""
    state = str(fields.get("state", ""))
    if state not in RECEIPT_STATES:
        raise SbatchRejection(f"unknown receipt state {state!r}")
    unknown = sorted(set(fields) - set(RECEIPT_FIELDS))
    if unknown:
        raise SbatchRejection(f"unknown receipt fields {unknown}")
    record: dict[str, object] = {"schema": RECEIPT_SCHEMA}
    record.update({name: fields.get(name) for name in RECEIPT_FIELDS})
    return record


def renumber(item: QueueItem, item_id: str, sequence: int, lane_id: str) -> QueueItem:
    """Return the item stamped with its lane and sequence-allocated id."""
    return replace(item, item_id=item_id, sequence=sequence, lane_id=lane_id)
