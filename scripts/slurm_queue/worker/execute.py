"""Run one resolved payload as a bounded child process group.

The child executes the resolved bytes staged beside its own log, so the run is
bit-identical to the version the receipt stamps and immune to the checkout being
rewritten while the payload runs.

Invariants & Expected State:
    - Staged Bytes: the child runs the claim-time resolved file, never the
      checkout's current copy, so a mid-run edit cannot split one item.
    - One Terminal Receipt: every path ends in exactly one receipt naming the
      executed commit, the script hash and the enqueue identity it ran for.
    - Bounded Child: the payload runs in its own process group under the item's
      requested seconds, then the grace; a timeout kills the group.
"""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Callable
from pathlib import Path

from scripts.slurm_queue.model import PAYLOAD_ENV, QueueItem, now_iso, receipt_record

from .resolve import resolve_or_refuse
from .session import (
    Resolved,
    WorkerInterrupted,
    WorkerSession,
    _raise_interrupt,
    child_env,
    item_log_path,
)


def _receipt(
    session: WorkerSession,
    item: QueueItem,
    state: str,
    code: int | None,
    reason: str | None,
    started: str,
    log: Path | None,
    resolved: Resolved | None,
) -> dict[str, object]:
    """Build the terminal receipt of one item, bound to the commit that ran."""
    return receipt_record(
        **_enqueue_fields(item),
        worker_job_id=session.job_id,
        state=state,
        exit_code=code,
        started_at=started,
        finished_at=now_iso(),
        log=None if log is None else str(log),
        reason=reason,
        executed_commit=None if resolved is None else resolved.commit,
        executed_script_sha256=None if resolved is None else resolved.script_sha256,
        tree_state=session.tree_state(),
        payload_env=item.env_map(),
    )


def _enqueue_fields(item: QueueItem) -> dict[str, object]:
    """The receipt's enqueue half: what was asked for, and from which commit."""
    return {
        "item_id": item.item_id,
        "sequence": item.sequence,
        "lane_id": item.lane_id,
        "script": item.script,
        "run_name": item.run_name,
        "banks": list(item.banks),
        "seeds": list(item.seeds),
        "enqueued_commit": item.commit,
    }


def run_item(
    session: WorkerSession,
    item: QueueItem,
    preflight: Callable[[WorkerSession, QueueItem, Path], str | None],
) -> str:
    """Resolve, re-gate, execute, and receipt one claimed item."""
    started = now_iso()
    log = item_log_path(session, item)
    log.parent.mkdir(parents=True, exist_ok=True)
    resolved, refusal = resolve_or_refuse(session, item, preflight, log)
    if resolved is not None:
        print(
            f"status=RESEARCH_SLURM_QUEUE_ITEM_START item={item.item_id} run={item.run_name} "
            f"script={item.script} commit={resolved.commit} log={log}",
            flush=True,
        )
        state, code, reason = execute_item(session, item, resolved)
    else:
        state, code, reason = refusal
    session.store.finish(
        session.profile,
        item.item_id,
        _receipt(session, item, state, code, reason, started, log, resolved),
    )
    print(
        f"status=RESEARCH_SLURM_QUEUE_ITEM_DONE item={item.item_id} state={state} exit={code}",
        flush=True,
    )
    return state


def execute_item(
    session: WorkerSession, item: QueueItem, resolved: Resolved
) -> tuple[str, int | None, str | None]:
    """Run one payload as a bounded child process group."""
    log = item_log_path(session, item)
    log.parent.mkdir(parents=True, exist_ok=True)
    previous = signal.signal(signal.SIGTERM, _raise_interrupt)
    try:
        return _bounded_run(session, item, log, resolved)
    finally:
        signal.signal(signal.SIGTERM, previous)


def staged_payload_path(log: Path) -> Path:
    """Return where the resolved payload bytes are staged for the child.

    The child runs this copy rather than the checkout's file, so the bytes that
    run are exactly the ones the receipt stamps and a rewrite of the checkout
    during the run cannot split an item across two payload versions.
    """
    return log.with_suffix(".payload.sbatch")


def _bounded_run(
    session: WorkerSession, item: QueueItem, log: Path, resolved: Resolved
) -> tuple[str, int | None, str | None]:
    """Wait for the payload under its own ``--time`` budget, then classify it."""
    staged = staged_payload_path(log)
    staged.write_bytes(resolved.payload)
    env = child_env(item)
    env[PAYLOAD_ENV] = str(session.repo / item.script)
    with log.open("ab") as handle:
        process = subprocess.Popen(
            ["bash", str(staged)],
            cwd=str(session.repo),
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=item.requested_seconds)
        except subprocess.TimeoutExpired:
            terminate_group(process, TERMINATE_GRACE_SECONDS)
            return (
                "timed_out",
                124,
                f"exceeded its {item.requested_seconds}s #SBATCH --time",
            )
        except WorkerInterrupted as interrupt:
            terminate_group(process, TERMINATE_GRACE_SECONDS)
            return "interrupted", None, str(interrupt)
    return ("succeeded" if code == 0 else "failed"), code, None


def terminate_group(process: subprocess.Popen, grace_seconds: float) -> None:
    """Terminate the item's process group, escalating only after the grace."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


TERMINATE_GRACE_SECONDS = 60.0
