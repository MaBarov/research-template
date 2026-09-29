"""Submit exactly one Slurm worker per lane.

Every submission is an argv array (never a shell string), is preceded by the
worker's provenance-contract check and an ``sbatch --test-only`` probe of the
exact argv, and is recorded in ``worker.json`` under the lane lock.  Liveness is
read back from ``squeue`` by the lane's deterministic job name, which is what
recovers the crash window where Slurm accepted a submission before the record
was written.

Invariants & Expected State:
    - One Live Worker per Lane: a submission proceeds only when the lane's live
      jobs are the recorded leader plus at most one ``COMPLETING`` predecessor.
    - Suspension Is Not Exit: a ``SUSPENDED`` worker keeps its allotment and
      resumes, so it counts as an unexplained worker and refuses a second one.
    - Recorded After Slurm: the worker record is written only after ``sbatch``
      returned an id, so a missing record means "adopt the live job by name".
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime

from scripts.slurm_queue.model import (
    SCRIPT_ROOT,
    WORKER_SCRIPT_NAME,
    ResourceProfile,
    format_duration,
    worker_job_name,
)
from scripts.slurm_queue.store import QueueStore

WORKER_SCRIPT = f"{SCRIPT_ROOT}/{WORKER_SCRIPT_NAME}"
WORKER_LOG_DIRECTIVE = "slurm/slurm_%x_%j.log"
WORKER_SIGNAL = "B:TERM@300"
LIVE_STATES = frozenset(
    {"PENDING", "CONFIGURING", "RUNNING", "COMPLETING", "SUSPENDED"}
)
# Only a job that has already left its script may sit beside the lane's live
# worker. SUSPENDED is deliberately absent: a suspended worker is still allotted
# and resumes, so tolerating one would put two draining workers on one lane.
DRAINING_STATES = frozenset({"COMPLETING"})
# Slurm reports COMPLETING once the batch process is gone: that script has already
# exited, so it can never claim another item. A lane whose only "live" worker is
# COMPLETING therefore has no worker at all, even though `squeue` still lists it,
# and publishing into it would strand the item until the next enqueue.
FINISHED_STATES = frozenset({"COMPLETING"})
JOB_ID_RE = re.compile(r"(?P<id>[0-9]+)(?:;.*)?")
END_TIME = re.compile(r"EndTime=(?P<time>[0-9T:+-]{10,})")


class SlurmError(RuntimeError):
    """Raised when Slurm cannot be asked, or refuses a submission."""


class SplitBrainError(SlurmError):
    """Raised when a lane has workers it cannot explain."""


def _run(
    argv: list[str], *, cwd: str | None = None, runner=subprocess.run
) -> subprocess.CompletedProcess:
    """Run one Slurm command, turning a missing binary into a clean refusal."""
    try:
        return runner(argv, cwd=cwd, capture_output=True, text=True, check=False)
    except OSError as error:
        raise SlurmError(f"cannot run {argv[0]}: {error}") from error


@dataclass(frozen=True)
class WorkerRef:
    """The lane's worker, whether it was just submitted or already running."""

    cluster: str
    lane_id: str
    job_id: str
    submitted: bool
    stragglers: tuple[str, ...] = ()


def squeue_states(name: str, *, runner=subprocess.run) -> dict[str, str]:
    """Return ``job_id -> state`` for live jobs carrying this exact job name."""
    result = _run(["squeue", "-h", "-n", name, "-o", "%A|%T"], runner=runner)
    if result.returncode:
        raise SlurmError(f"squeue -n {name} failed: {result.stderr.strip()}")
    states: dict[str, str] = {}
    for line in result.stdout.splitlines():
        job_id, _, state = line.strip().partition("|")
        if job_id.isdigit() and state.strip():
            states[job_id] = state.strip()
    return states


def live_workers(lane_id: str, *, runner=subprocess.run) -> dict[str, str]:
    """Return the lane's live workers as ``job_id -> state``."""
    return squeue_states(worker_job_name(lane_id), runner=runner)


def worker_argv(
    profile: ResourceProfile,
    repo,
    *,
    script: str = WORKER_SCRIPT,
    dependency: str | None = None,
    parsable: bool = True,
) -> list[str]:
    """Return the exact ``sbatch`` argv that reproduces the lane's worker."""
    argv = ["sbatch"]
    if parsable:
        argv.append("--parsable")
    argv.extend(
        [
            f"--job-name={worker_job_name(profile.lane_id())}",
            f"--output={WORKER_LOG_DIRECTIVE}",
            f"--time={format_duration(profile.worker_time_seconds)}",
            f"--signal={WORKER_SIGNAL}",
        ]
    )
    if dependency is not None:
        argv.append(f"--dependency={dependency}")
    argv.extend(profile.sbatch_args())
    argv.extend([f"{repo}/{script}", profile.lane_id()])
    return argv


def _assert_worker_contract(repo, script: str, *, runner=subprocess.run) -> None:
    """Refuse a worker script that violates the repository's job contract."""
    result = _run(
        [
            "bash",
            f"{repo}/framework/gates/check_sbatch_contract.sh",
            f"{repo}/{script}",
        ],
        cwd=str(repo),
        runner=runner,
    )
    if result.returncode:
        raise SlurmError(
            f"worker script {script} violates the sbatch contract: {result.stderr.strip()}"
        )


def _assert_worker_argv(
    repo, profile: ResourceProfile, script: str, *, runner=subprocess.run
) -> None:
    """Let Slurm itself validate the exact argv the submission will use."""
    argv = worker_argv(profile, repo, script=script, parsable=False)[1:]
    result = _run(["sbatch", "--test-only", *argv], cwd=str(repo), runner=runner)
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip()
        raise SlurmError(
            f"sbatch --test-only rejected the lane {profile.lane_id()} worker: {message}"
        )


def validate_worker(
    repo,
    profile: ResourceProfile,
    *,
    script: str = WORKER_SCRIPT,
    runner=subprocess.run,
) -> None:
    """Run the worker's contract check and Slurm's own argv validation."""
    _assert_worker_contract(repo, script, runner=runner)
    _assert_worker_argv(repo, profile, script, runner=runner)


def parse_job_id(stdout: str, name: str, *, runner=subprocess.run) -> str:
    """Read a strict job id, recovering an ambiguous submission by job name."""
    token = stdout.strip().splitlines()[0].strip() if stdout.strip() else ""
    match = JOB_ID_RE.fullmatch(token)
    if match:
        return match.group("id")
    recovered = squeue_states(name, runner=runner)
    if len(recovered) == 1:
        return next(iter(recovered))
    raise SlurmError(
        f"cannot determine the submitted job id from {stdout!r} (name {name})"
    )


def submit_worker(
    repo,
    profile: ResourceProfile,
    *,
    script: str = WORKER_SCRIPT,
    dependency: str | None = None,
    runner=subprocess.run,
) -> str:
    """Validate and submit the lane's worker, returning its Slurm job id."""
    validate_worker(repo, profile, script=script, runner=runner)
    argv = worker_argv(profile, repo, script=script, dependency=dependency)
    result = _run(argv, cwd=str(repo), runner=runner)
    if result.returncode:
        raise SlurmError(
            f"sbatch rejected the lane {profile.lane_id()} worker: {result.stderr.strip()}"
        )
    return parse_job_id(
        result.stdout, worker_job_name(profile.lane_id()), runner=runner
    )


def _leader(states: dict[str, str]) -> str:
    """Return the highest live job id: the worker that owns the lane's drain."""
    return max(states, key=int)


def _stragglers(states: dict[str, str], leader: str) -> tuple[str, ...]:
    """Return every live job of the lane other than its leader, oldest first."""
    return tuple(sorted((job_id for job_id in states if job_id != leader), key=int))


def _reject_split_brain(states: dict[str, str], stragglers: tuple[str, ...]) -> None:
    """Tolerate exactly one draining predecessor; refuse anything else."""
    if not stragglers:
        return
    if len(stragglers) == 1 and states[stragglers[0]] in DRAINING_STATES:
        return
    described = ", ".join(
        f"{job_id}={states[job_id]}" for job_id in sorted(states, key=int)
    )
    raise SplitBrainError(
        f"lane has unexplained workers ({described}); refusing to add another"
    )


def _submit(
    store: QueueStore,
    profile: ResourceProfile,
    repo,
    *,
    dependency: str | None,
    runner,
) -> WorkerRef:
    job_id = submit_worker(repo, profile, dependency=dependency, runner=runner)
    store.write_worker(profile, job_id)
    return WorkerRef(
        cluster=profile.cluster,
        lane_id=profile.lane_id(),
        job_id=job_id,
        submitted=True,
    )


def ensure_worker(
    store: QueueStore, profile: ResourceProfile, repo, *, runner=subprocess.run
) -> WorkerRef:
    """Submit or adopt the lane's single worker. Call with the lane lock held."""
    live = live_workers(profile.lane_id(), runner=runner)
    recorded = store.read_worker(profile)
    active = {
        job_id: state for job_id, state in live.items() if state not in FINISHED_STATES
    }
    if not active:
        if recorded is not None:
            store.clear_worker(profile, str(recorded.get("job_id")))
        return _submit(store, profile, repo, dependency=None, runner=runner)
    leader = _leader(active)
    stragglers = _stragglers(live, leader)
    _reject_split_brain(live, stragglers)
    if recorded is None or str(recorded.get("job_id")) != leader:
        store.write_worker(profile, leader)
    return WorkerRef(
        cluster=profile.cluster,
        lane_id=profile.lane_id(),
        job_id=leader,
        submitted=False,
        stragglers=stragglers,
    )


def handoff_worker(
    store: QueueStore,
    profile: ResourceProfile,
    repo,
    predecessor_job_id: str,
    *,
    runner=subprocess.run,
) -> WorkerRef:
    """Submit the successor that inherits the lane. Call with the lane lock held."""
    _reject_foreign_workers(profile, runner, predecessor_job_id)
    job_id = submit_worker(
        repo, profile, dependency=f"afterany:{predecessor_job_id}", runner=runner
    )
    store.write_worker(profile, job_id)
    return WorkerRef(
        cluster=profile.cluster,
        lane_id=profile.lane_id(),
        job_id=job_id,
        submitted=True,
    )


def _reject_foreign_workers(profile, runner, predecessor_job_id):
    live = live_workers(profile.lane_id(), runner=runner)
    strangers = sorted(
        (
            job_id
            for job_id, state in live.items()
            if str(job_id) != str(predecessor_job_id) and state not in FINISHED_STATES
        ),
        key=int,
    )
    if strangers:
        raise SplitBrainError(
            f"lane {profile.lane_id()} already has workers {strangers}; refusing to hand off"
        )


def allocation_remaining_seconds(job_id: str, *, runner=subprocess.run) -> float | None:
    """Return seconds left in the allocation, or None when it cannot be read."""
    try:
        result = _run(["scontrol", "show", "job", str(job_id), "-o"], runner=runner)
    except SlurmError:
        return None
    if result.returncode:
        return None
    match = END_TIME.search(result.stdout)
    if match is None:
        return None
    try:
        end = datetime.strptime(match.group("time"), "%Y-%m-%dT%H:%M:%S").astimezone()
    except ValueError:
        return None
    return end.timestamp() - datetime.now(UTC).timestamp()
