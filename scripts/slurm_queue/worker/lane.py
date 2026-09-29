"""Drain the lane: fit, handoff, idle grace and the drain loop.

Invariants & Expected State:
    - One Draining Allocation: the loop either runs the FIFO head, hands the
      lane to a successor, fails an unfittable item, or waits out the grace.
    - Horizon Refreshed Every Loop: the remaining-time probe runs each iteration,
      so one failed read costs a single loop and never freezes the session.
    - Reconciled Only With Evidence: this allocation's start retires the running
      records of workers that ``squeue`` no longer lists, and skips the pass
      entirely when that liveness read fails.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from scripts.slurm_queue.model import (
    HANDOFF_FAILURE_SCHEMA,
    ITEM_OVERHEAD_SECONDS,
    WORKER_TIME_ENV,
    QueueItem,
    now_iso,
)
from scripts.slurm_queue.runtime import atomic_json_dump
from scripts.slurm_queue.store import QueueLockError
from scripts.slurm_queue.submit import (
    FINISHED_STATES,
    SlurmError,
    WorkerRef,
    allocation_remaining_seconds,
    handoff_worker,
    live_workers,
)

from .execute import _receipt, run_item
from .resolve import gate_preflight
from .session import WorkerSession, checkout_refusal, now_or_never


def run_lane(
    session: WorkerSession,
    *,
    preflight: Callable[[WorkerSession, QueueItem, Path], str | None] = gate_preflight,
    remaining_probe: Callable[[str], float | None] = allocation_remaining_seconds,
    live_probe: Callable[[str], dict[str, str]] = live_workers,
    grace_seconds: float = 0.0,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Drain the lane until it empties after its grace, the allocation is short, or it fails."""
    refusal = checkout_refusal(session)
    if refusal is not None:
        print(f"status=RESEARCH_SLURM_QUEUE_WORKER_ABORT reason={refusal}", flush=True)
        return 90
    report_reconcile(session, live_probe)
    return drain_loop(session, preflight, remaining_probe, grace_seconds, clock)


def drain_loop(
    session: WorkerSession,
    preflight: Callable[[WorkerSession, QueueItem, Path], str | None],
    remaining_probe: Callable[[str], float | None],
    grace_seconds: float,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Drain the lane FIFO until it empties, the allocation is short, or it fails."""
    executed: set[str] = set()
    failures = 0
    idle = IdleWindow(grace_seconds, clock=clock)
    while True:
        session = refresh_remaining(session, remaining_probe)
        action = next_action(session, frozenset(executed))
        if action == "empty":
            code = _wait_out_grace(session, idle, failures)
            if code is not None:
                return code
            continue
        idle.reset()
        outcome = _step(session, action, preflight, executed)
        if outcome.exit_code is not None:
            return outcome.exit_code
        failures += outcome.failures


@dataclass(frozen=True)
class StepOutcome:
    """What one non-empty drain step did: a failure delta, or the exit code."""

    failures: int = 0
    exit_code: int | None = None


def _wait_out_grace(
    session: WorkerSession, idle: IdleWindow, failures: int
) -> int | None:
    """Return the exit code once an empty lane's grace elapsed, else ``None``."""
    if not idle.elapsed():
        time.sleep(IDLE_POLL_SECONDS)
        return None
    code = finish_allocation(session, failures)
    if code is None:
        idle.reset()
    return code


def _step(
    session: WorkerSession,
    action: str,
    preflight: Callable[[WorkerSession, QueueItem, Path], str | None],
    executed: set[str],
) -> StepOutcome:
    """Hand the lane on, fail an unfit item, or claim and run the item at the head."""
    if action == "handoff":
        return StepOutcome(exit_code=hand_off(session, action, head_item(session)))
    if action == "unfit":
        return StepOutcome(failures=1 if fail_unfittable(session) else 0)
    item = session.store.claim(session.profile, session.job_id)
    if item is None:
        return StepOutcome()
    executed.add(item.script)
    succeeded = run_item(session, item, preflight) == "succeeded"
    return StepOutcome(failures=0 if succeeded else 1)


def report_reconcile(
    session: WorkerSession,
    live_probe: Callable[[str], dict[str, str]] = live_workers,
) -> None:
    """Print the receipts and retirements this allocation's start reconciled.

    Reconciliation needs the lane's live job set: without it the store could
    only guess whether a recorded worker is gone. An unreadable ``squeue``
    therefore skips the pass (leaving every claim intact) instead of failing
    items that a live worker still owns.
    """
    live = _claimable_jobs(live_probe, session.profile.lane_id())
    if live is None:
        return
    events = session.store.reconcile(
        session.profile, session.job_id, live_worker_ids=live
    )
    for event in events:
        print(
            f"status=RESEARCH_SLURM_QUEUE_RECONCILE lane={session.profile.lane_id()} {event}",
            flush=True,
        )


def _claimable_jobs(
    live_probe: Callable[[str], dict[str, str]], lane_id: str
) -> frozenset[str] | None:
    """Job ids that can still claim an item; ``None`` when the live set is unreadable.

    An unreadable ``squeue`` skips the pass (leaving every claim intact) instead of
    failing items that a live worker still owns.
    """
    try:
        live = live_probe(lane_id)
    except SlurmError as error:
        print(
            f"status=RESEARCH_SLURM_QUEUE_RECONCILE_SKIP lane={lane_id} reason={error}",
            flush=True,
        )
        return None
    return frozenset(
        job_id for job_id, state in live.items() if state not in FINISHED_STATES
    )


def finish_allocation(session: WorkerSession, failures: int) -> int | None:
    """Exit when the lane is still empty under the lock, else return ``None``."""
    with session.store.lane_lock(session.profile):
        if session.store.pending_items(session.profile):
            return None
        session.store.clear_worker(session.profile, session.job_id)
    print(
        f"status=RESEARCH_SLURM_QUEUE_WORKER_DONE job={session.job_id} "
        f"lane={session.profile.lane_id()} failures={failures}",
        flush=True,
    )
    return 0 if failures == 0 else 1


def hand_off(
    session: WorkerSession, reason: str, fit_item: QueueItem | None = None
) -> int:
    """Submit the successor worker that inherits the pending items."""
    print(
        f"status=RESEARCH_SLURM_QUEUE_HANDOFF job={session.job_id} "
        f"lane={session.profile.lane_id()} reason={reason} "
        f"unfit={fit_item.item_id if fit_item is not None else 'none'}",
        flush=True,
    )
    try:
        ref = _submit_successor(session, fit_item)
    except (SlurmError, QueueLockError) as error:
        lane = session.store.lane(session.profile.cluster, session.profile.lane_id())
        atomic_json_dump(
            lane.directory / HANDOFF_FAILURE,
            {"schema": HANDOFF_FAILURE_SCHEMA, "reason": str(error)},
        )
        print(
            f"status=RESEARCH_SLURM_QUEUE_HANDOFF_FAILED job={session.job_id} reason={error}",
            flush=True,
        )
        return 1
    print(
        f"status=RESEARCH_SLURM_QUEUE_HANDOFF_DONE predecessor={session.job_id} successor={ref.job_id}",
        flush=True,
    )
    return 0


def _submit_successor(session: WorkerSession, fit_item: QueueItem | None) -> WorkerRef:
    """Bump the item's handoff count and submit the successor under the lane lock."""
    with session.store.lane_lock(session.profile):
        if fit_item is not None:
            session.store.bump_handoffs(session.profile, fit_item.item_id)
        ref = handoff_worker(
            session.store, session.profile, session.repo, session.job_id
        )
    return ref


def fail_unfittable(session: WorkerSession) -> bool:
    """Fail an item a second worker in a row cannot fit; never chain allocations forever."""
    item = session.store.claim(session.profile, session.job_id)
    if item is None:
        return False
    reason = (
        f"payload needs {item.requested_seconds + ITEM_OVERHEAD_SECONDS}s including the "
        f"{ITEM_OVERHEAD_SECONDS}s item overhead, but {item.handoffs} handoff(s) left this "
        f"lane with {now_or_never(session.remaining_seconds)}s; raise {WORKER_TIME_ENV}"
    )
    session.store.finish(
        session.profile,
        item.item_id,
        _receipt(session, item, "unfittable", None, reason, now_iso(), None, None),
    )
    print(
        f"status=RESEARCH_SLURM_QUEUE_ITEM_DONE item={item.item_id} state=unfittable exit=None",
        flush=True,
    )
    return True


@dataclass
class IdleWindow:
    """Bounded wait on an empty lane: exit once the grace elapses without items."""

    grace_seconds: float
    clock: Callable[[], float] = time.monotonic
    started: float | None = None
    announced: bool = False

    def elapsed(self) -> bool:
        """Announce the wait once and report whether the grace has run out."""
        now = self.clock()
        if self.started is None:
            self.started = now
        if not self.announced:
            print(
                f"status=RESEARCH_SLURM_QUEUE_IDLE_WAIT grace={self.grace_seconds:.0f}s",
                flush=True,
            )
            self.announced = True
        return now - self.started >= self.grace_seconds

    def reset(self) -> None:
        """Forget the wait, so the next empty moment starts a fresh grace."""
        self.started = None
        self.announced = False


def refresh_remaining(
    session: WorkerSession,
    probe: Callable[[str], float | None] = allocation_remaining_seconds,
) -> WorkerSession:
    """Re-read the allocation's remaining time; a failed read is retried next loop."""
    remaining = probe(session.job_id)
    if remaining is None:
        return session
    return replace(session, remaining_seconds=remaining)


def head_item(session: WorkerSession) -> QueueItem | None:
    """Return the lane's FIFO head without claiming it."""
    pending = session.store.pending_items(session.profile)
    return pending[0] if pending else None


def next_action(session: WorkerSession, executed: frozenset[str]) -> str:
    """Decide what this allocation does next: ``run``, ``handoff``, ``unfit``, ``empty``."""
    pending = session.store.pending_items(session.profile)
    if not pending:
        return "empty"
    item = pending[0]
    if item.script in executed:
        return "handoff"
    if session.remaining_seconds is None:
        return "handoff" if executed else "run"
    if session.remaining_seconds < item.requested_seconds + ITEM_OVERHEAD_SECONDS:
        return "unfit" if item.handoffs else "handoff"
    return "run"


HANDOFF_FAILURE = "handoff_failure.json"
IDLE_POLL_SECONDS = 5.0
