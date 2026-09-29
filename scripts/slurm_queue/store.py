"""Durable FIFO state for the Slurm draining queue.

One lane owns ``<root>/<cluster>/<lane_id>/``: its profile, its sequence
counter, its worker record, the ``pending``/``running``/``succeeded``/``failed``
FIFO directories, and its child logs.  File location is authoritative state, so
``os.replace`` alone claims an item and every state change is one atomic write.

Lifecycle decisions (publish, submit, empty-exit) take one short per-lane
``control.lock`` acquired with ``mkdir``.  A lock whose owner process died on
this host, or that outlived its stale window, is renamed out of the way rather
than unlinked, and releasing verifies the owner token, so a quarantined lock can
never be deleted underneath a live holder.

Atomic writes and file digests come from the queue's own :mod:`scripts.slurm_queue.runtime`
helpers; this module adds no second atomic-write implementation.

Invariants & Expected State:
    - One Writer per Lane: lifecycle changes run under the lane's
      ``control.lock``, and run-name allocation additionally takes the store
      root's lock.
    - File Location Is State: an item is claimed by one ``os.replace`` — a lost
      race is retried — and every other state change is one atomic JSON write.
    - Receipts Are Written Once: a terminal receipt must name the running record
      and is refused when a receipt for that item already exists.
    - Interrupt Only The Dead: reconcile turns a running record into an
      ``interrupted`` receipt only when its recorded worker is absent from the
      caller's ``live_worker_ids``; a live worker keeps its claim.
    - Abandoned Locks Only: a lock whose owner died on this host, or that
      outlived the stale window, is renamed aside, never unlinked.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import time
from collections.abc import Collection, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from scripts.slurm_queue.model import (
    ITEM_SCHEMA,
    PROFILE_SCHEMA,
    QUEUE_ROOT_ENV,
    RECEIPT_STATES,
    SEQUENCE_SCHEMA,
    WORKER_SCHEMA,
    QueueItem,
    ResourceProfile,
    now_iso,
    receipt_record,
    renumber,
)
from scripts.slurm_queue.runtime import atomic_json_dump

LOCK_WAIT_SECONDS = 10.0
LOCK_STALE_SECONDS = 120.0
LOCK_POLL_SECONDS = 0.05
LOCK_NAME = "control.lock"
STATE_DIRECTORIES = ("pending", "running", "succeeded", "failed")


class QueueStateError(RuntimeError):
    """Raised when queue state cannot be trusted."""


class QueueLockError(RuntimeError):
    """Raised when the lane lock cannot be taken."""


class LaneProfileMismatch(RuntimeError):
    """Raised when a lane id is reused for a different resource profile."""


def _now_epoch() -> float:
    return datetime.now(UTC).timestamp()


def _load_json(path: Path) -> object:
    """Read one JSON document, refusing anything unreadable as queue state."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QueueStateError(f"{path} is not readable queue state: {error}") from error


def _load_record(path: Path, schema: str) -> dict[str, object]:
    """Read one queue record, failing closed on any unreadable or foreign file."""
    record = _load_json(path)
    if not isinstance(record, dict) or record.get("schema") != schema:
        raise QueueStateError(f"{path} is not a {schema} record")
    return record


def _logical_name(name: str) -> str:
    """Accept the ``.stale.<pid>.<token>`` suffix of a quarantined directory."""
    return name.split(f"{LOCK_NAME}.stale.", 1)[0] if LOCK_NAME in name else name


def _fifo_key(path: Path) -> int:
    """Order item files by their numeric sequence, whatever the id width."""
    prefix = path.name.split("-", 1)[0]
    try:
        return int(prefix)
    except ValueError:
        raise QueueStateError(f"{path.name} is not a queue item id") from None


def _rename_if_present(source: Path, target: Path) -> bool:
    """Rename ``source`` onto ``target``; report False when a rival got there first."""
    try:
        os.replace(source, target)
    except FileNotFoundError:
        return False
    return True


def _assert_receipt_identity(
    record: Mapping[str, object], receipt: Mapping[str, object], item_id: str
) -> None:
    """Refuse a receipt that does not close the named running record."""
    if str(record.get("item_id")) != str(item_id):
        raise QueueStateError(f"{item_id} does not name the running record")
    for field in ("item_id", "sequence", "lane_id"):
        if str(receipt.get(field)) != str(record.get(field)):
            raise QueueStateError(
                f"receipt {field}={receipt.get(field)!r} does not match the running "
                f"record ({field}={record.get(field)!r})"
            )


def _interrupted_receipt(
    record: Mapping[str, object], profile: ResourceProfile, item_id: str
) -> dict[str, object]:
    """Build the terminal receipt of an item whose worker disappeared."""
    worker = record.get("worker_job_id")
    return receipt_record(
        item_id=item_id,
        sequence=int(record["sequence"]),
        lane_id=profile.lane_id(),
        worker_job_id=str(worker),
        script=str(record["script"]),
        run_name=str(record["run_name"]),
        banks=[str(bank) for bank in record.get("banks") or ()],
        seeds=[str(seed) for seed in record.get("seeds") or ()],
        state="interrupted",
        started_at=None,
        finished_at=now_iso(),
        log=None,
        reason=f"worker {worker} left this item running",
        payload_env=dict(record.get("env") or ()),
    )


@dataclass(frozen=True)
class Lane:
    """Filesystem layout of one resource lane."""

    directory: Path

    def create(self) -> Lane:
        """Create every lane directory and return the lane."""
        self.directory.mkdir(parents=True, exist_ok=True)
        for child in (*STATE_DIRECTORIES, "logs"):
            (self.directory / child).mkdir(exist_ok=True)
        return self

    def profile(self) -> Path:
        return self.directory / "profile.json"

    def sequence(self) -> Path:
        return self.directory / "sequence.json"

    def worker(self) -> Path:
        return self.directory / "worker.json"

    def lock(self) -> Path:
        return self.directory / LOCK_NAME

    def pending(self) -> Path:
        return self.directory / "pending"

    def running(self) -> Path:
        return self.directory / "running"

    def succeeded(self) -> Path:
        return self.directory / "succeeded"

    def failed(self) -> Path:
        return self.directory / "failed"

    def logs(self) -> Path:
        return self.directory / "logs"

    def state_directories(self) -> tuple[Path, ...]:
        return tuple(self.directory / name for name in STATE_DIRECTORIES)


@dataclass(frozen=True)
class QueueStore:
    """Durable FIFO state for every lane, rooted outside the git tree."""

    root: Path

    @classmethod
    def default(
        cls, repo: Path, environ: Mapping[str, str] | None = None
    ) -> QueueStore:
        """Return the store rooted at ``RESEARCH_QUEUE_ROOT`` or ``results/slurm_queue``."""
        source = os.environ if environ is None else environ
        override = source.get(QUEUE_ROOT_ENV)
        return cls(
            root=Path(override) if override else repo / "results" / "slurm_queue"
        )

    def lane(self, cluster: str, lane_id: str) -> Lane:
        """Return the layout of one lane without touching the filesystem."""
        return Lane(self.root / cluster / lane_id)

    def ensure_lane(self, profile: ResourceProfile) -> Lane:
        """Create the lane and verify any pre-existing profile before reuse."""
        lane = self.lane(profile.cluster, profile.lane_id()).create()
        if not lane.profile().exists():
            atomic_json_dump(lane.profile(), profile.record())
            return lane
        stored = ResourceProfile.from_record(
            _load_record(lane.profile(), PROFILE_SCHEMA)
        )
        if stored.canonical() != profile.canonical():
            raise LaneProfileMismatch(
                f"lane {profile.lane_id()} already holds a different resource profile; "
                f"refusing to reuse the lane id"
            )
        return lane

    def _next_sequence(self, lane: Lane) -> int:
        path = lane.sequence()
        current = 1
        if path.exists():
            record = _load_record(path, SEQUENCE_SCHEMA)
            if not isinstance(record.get("next"), int) or int(record["next"]) < 1:
                raise QueueStateError(f"{path} has no usable next sequence")
            current = int(record["next"])
        atomic_json_dump(
            path,
            {
                "schema": SEQUENCE_SCHEMA,
                "lane_id": lane.directory.name,
                "next": current + 1,
            },
        )
        return current

    def publish(self, item: QueueItem, profile: ResourceProfile) -> QueueItem:
        """Allocate a sequence and append one item. Call with the lane lock held."""
        lane = self.ensure_lane(profile)
        sequence = self._next_sequence(lane)
        item_id = f"{sequence:06d}-{secrets.token_hex(6)}"
        published = renumber(item, item_id, sequence, profile.lane_id())
        atomic_json_dump(lane.pending() / f"{item_id}.json", published.record())
        return published

    def pending_items(self, profile: ResourceProfile) -> list[QueueItem]:
        """Return the lane's FIFO order without claiming anything."""
        lane = self.lane(profile.cluster, profile.lane_id())
        items = [
            QueueItem.from_record(_load_record(path, ITEM_SCHEMA))
            for path in sorted(lane.pending().glob("*.json"), key=_fifo_key)
        ]
        return items

    def claim(self, profile: ResourceProfile, job_id: str) -> QueueItem | None:
        """Atomically move the oldest pending item into ``running``.

        A second worker can be alive long enough to race this move (see the
        split-brain guard in :mod:`scripts.slurm_queue.submit`), so a lost
        ``os.replace`` is retried against what is left instead of failing the
        drain: the winner's file is gone, and the loser takes the next one.
        """
        lane = self.lane(profile.cluster, profile.lane_id())
        while True:
            pending = sorted(lane.pending().glob("*.json"), key=_fifo_key)
            if not pending:
                return None
            target = lane.running() / pending[0].name
            if _rename_if_present(pending[0], target):
                break
        record = _load_record(target, ITEM_SCHEMA)
        record["worker_job_id"] = job_id
        record["claimed_at"] = now_iso()
        atomic_json_dump(target, record)
        return QueueItem.from_record(record)

    def unpublish(self, profile: ResourceProfile, item_id: str) -> bool:
        """Withdraw a pending item that no worker accepted. Call under the lane lock."""
        lane = self.lane(profile.cluster, profile.lane_id())
        path = lane.pending() / f"{item_id}.json"
        existed = path.is_file()
        path.unlink(missing_ok=True)
        return existed

    def bump_handoffs(self, profile: ResourceProfile, item_id: str) -> int:
        """Count one fit handoff on a pending item. Call under the lane lock."""
        lane = self.lane(profile.cluster, profile.lane_id())
        path = lane.pending() / f"{item_id}.json"
        record = _load_record(path, ITEM_SCHEMA)
        record["handoffs"] = int(record.get("handoffs") or 0) + 1
        atomic_json_dump(path, record)
        return int(record["handoffs"])

    def existing_receipt(self, profile: ResourceProfile, item_id: str) -> Path | None:
        """Return the terminal receipt of an item, when it already finished."""
        lane = self.lane(profile.cluster, profile.lane_id())
        for directory in (lane.succeeded(), lane.failed()):
            candidate = directory / f"{item_id}.json"
            if candidate.is_file():
                return candidate
        return None

    def finish(
        self, profile: ResourceProfile, item_id: str, receipt: Mapping[str, object]
    ) -> Path:
        """Write a terminal receipt first, then drop the running record.

        A receipt is written once, for the item that is actually running: the
        running record must exist, must name the same item, and must not already
        have a terminal receipt. Anything else is corrupt state, refused rather
        than overwritten so the first outcome stays the recorded one.
        """
        lane = self.lane(profile.cluster, profile.lane_id())
        state = str(receipt.get("state"))
        if state not in RECEIPT_STATES:
            raise QueueStateError(f"refusing to store receipt with state {state!r}")
        running = lane.running() / f"{item_id}.json"
        if not running.is_file():
            raise QueueStateError(f"{running} is not running; refusing a receipt")
        _assert_receipt_identity(_load_record(running, ITEM_SCHEMA), receipt, item_id)
        existing = self.existing_receipt(profile, item_id)
        if existing is not None:
            raise QueueStateError(f"{item_id} already holds a receipt at {existing}")
        directory = lane.succeeded() if state == "succeeded" else lane.failed()
        target = directory / f"{item_id}.json"
        atomic_json_dump(target, dict(receipt))
        running.unlink(missing_ok=True)
        return target

    def read_profile(self, cluster: str, lane_id: str) -> ResourceProfile:
        """Return the lane's stored profile, failing closed when it is absent."""
        path = self.lane(cluster, lane_id).profile()
        if not path.is_file():
            raise QueueStateError(f"lane {lane_id} has no profile at {path}")
        return ResourceProfile.from_record(_load_record(path, PROFILE_SCHEMA))

    def read_worker(self, profile: ResourceProfile) -> dict[str, object] | None:
        """Return the lane's recorded worker, or ``None`` when it has none."""
        path = self.lane(profile.cluster, profile.lane_id()).worker()
        if not path.exists():
            return None
        return _load_record(path, WORKER_SCHEMA)

    def write_worker(self, profile: ResourceProfile, job_id: str) -> dict[str, object]:
        """Record which Slurm job owns the lane's drain."""
        lane = self.ensure_lane(profile)
        record = {
            "schema": WORKER_SCHEMA,
            "lane_id": profile.lane_id(),
            "cluster": profile.cluster,
            "job_id": str(job_id),
            "submitted_at": now_iso(),
        }
        atomic_json_dump(lane.worker(), record)
        return record

    def clear_worker(self, profile: ResourceProfile, job_id: str) -> bool:
        """Retire the lane's worker record when it names ``job_id``."""
        record = self.read_worker(profile)
        if record is None or str(record.get("job_id")) != str(job_id):
            return False
        self.lane(profile.cluster, profile.lane_id()).worker().unlink(missing_ok=True)
        return True

    def reconcile(
        self,
        profile: ResourceProfile,
        job_id: str,
        *,
        live_worker_ids: Collection[str],
    ) -> list[str]:
        """Trust receipts, retire running records of workers that are gone.

        ``live_worker_ids`` are the jobs that can still claim an item: a
        ``COMPLETING`` worker has left its script, so it belongs outside the set
        and the record it left behind becomes an ``interrupted`` receipt.
        """
        lane = self.lane(profile.cluster, profile.lane_id())
        live = {str(entry) for entry in live_worker_ids}
        events: list[str] = []
        for path in sorted(lane.running().glob("*.json")):
            record = _load_record(path, ITEM_SCHEMA)
            event = self._retire_running_record(
                lane, path, record, profile, job_id, live
            )
            if event is not None:
                events.append(event)
        return events

    def _retire_running_record(
        self,
        lane: Lane,
        path: Path,
        record: Mapping[str, object],
        profile: ResourceProfile,
        job_id: str,
        live: set[str],
    ) -> str | None:
        """Resolve one running record: a gone worker's is retired, a live one's kept.

        Returns the event line for the receipt header, or ``None`` for the running
        record this worker itself owns (its item is still in flight).
        """
        item_id = str(record["item_id"])
        if self.existing_receipt(profile, item_id) is not None:
            path.unlink(missing_ok=True)
            return f"dropped duplicate running record for {item_id}"
        worker = str(record.get("worker_job_id"))
        if worker == str(job_id):
            return None
        if worker in live:
            return f"kept {item_id} (worker {worker} still live)"
        receipt = _interrupted_receipt(record, profile, item_id)
        atomic_json_dump(lane.failed() / path.name, receipt)
        path.unlink(missing_ok=True)
        return f"interrupted {item_id} (worker {worker} gone)"

    def run_name_in_use(self, run_name: str) -> Path | None:
        """Return the queue record that already uses ``run_name``, if any."""
        for lane in sorted(self.root.glob("*/*")):
            if not lane.is_dir():
                continue
            for directory in lane.iterdir():
                if (
                    _logical_name(directory.name) not in STATE_DIRECTORIES
                    or not directory.is_dir()
                ):
                    continue
                for path in sorted(directory.glob("*.json")):
                    record = _load_json(path)
                    if isinstance(record, dict) and record.get("run_name") == run_name:
                        return path
        return None

    @contextmanager
    def lane_lock(
        self, profile: ResourceProfile, *, wait_seconds: float = LOCK_WAIT_SECONDS
    ) -> Iterator[Lane]:
        """Hold the lane's lifecycle lock for one short critical section."""
        lane = self.lane(profile.cluster, profile.lane_id())
        token = acquire_lane_lock(lane, wait_seconds=wait_seconds)
        try:
            yield lane
        finally:
            release_lane_lock(lane, token)

    @contextmanager
    def root_lock(self, *, wait_seconds: float = LOCK_WAIT_SECONDS) -> Iterator[None]:
        """Hold the store-wide lock that serializes run-name allocation."""
        lock = self.root / LOCK_NAME
        token = acquire_lock(lock, wait_seconds=wait_seconds)
        try:
            yield None
        finally:
            release_lock(lock, token)


def _lock_owner(lock: Path) -> dict[str, object] | None:
    """Return the lock's owner record; ``None`` when it is gone or unreadable."""
    try:
        record = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return record if isinstance(record, dict) else None


def _owner_is_dead_here(owner: Mapping[str, object] | None) -> bool:
    """Return whether the owner pid recorded on this host is gone."""
    if owner is None or owner.get("host") != socket.gethostname():
        return False
    pid = owner.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _create_lock(lock: Path, token: str) -> bool:
    """Create the lock directory, returning False when it already exists."""
    try:
        os.mkdir(lock)
    except FileExistsError:
        return False
    atomic_json_dump(
        lock / "owner.json",
        {
            "token": token,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "created_at": now_iso(),
        },
    )
    return True


def _quarantine_stale_lock(lock: Path) -> bool:
    """Rename a provably abandoned lock aside; never unlink a possibly live lock.

    Abandonment is proven either by the owner pid being gone on this host (the
    fast path: no waiting needed) or by the lock outliving its stale window (the
    cross-host fallback, where a pid recorded on another node proves nothing).
    """
    try:
        age = _now_epoch() - lock.stat().st_mtime
    except FileNotFoundError:
        return True
    if age < LOCK_STALE_SECONDS and not _owner_is_dead_here(_lock_owner(lock)):
        return False
    stale = lock.with_name(f"{lock.name}.stale.{os.getpid()}.{secrets.token_hex(4)}")
    try:
        os.rename(lock, stale)
    except OSError:
        return False
    return True


def acquire_lock(lock: Path, *, wait_seconds: float = LOCK_WAIT_SECONDS) -> str:
    """Take a lock directory (or break a provably abandoned one); return its token."""
    lock.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(8)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if _create_lock(lock, token):
            return token
        if _quarantine_stale_lock(lock):
            continue
        time.sleep(LOCK_POLL_SECONDS)
    if _quarantine_stale_lock(lock) and _create_lock(lock, token):
        return token
    owner = _lock_owner(lock)
    raise QueueLockError(f"lock {lock} is held by {owner or 'an unknown process'}")


def release_lock(lock: Path, token: str) -> None:
    """Release a lock only when this process's token still owns it."""
    owner = _lock_owner(lock)
    if owner is None or owner.get("token") != token:
        return
    try:
        shutil.rmtree(lock)
    except FileNotFoundError:
        return


def acquire_lane_lock(lane: Lane, *, wait_seconds: float = LOCK_WAIT_SECONDS) -> str:
    """Take the lane lock (or break a provably abandoned one) and return its token."""
    return acquire_lock(lane.create().lock(), wait_seconds=wait_seconds)


def release_lane_lock(lane: Lane, token: str) -> None:
    """Release the lane lock only when this process's token still owns it."""
    release_lock(lane.lock(), token)
