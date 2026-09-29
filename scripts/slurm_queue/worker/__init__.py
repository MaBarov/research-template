"""Drain one Slurm lane allocation.

The worker owns one lane FIFO: it claims one item at a time, executes it as a
bounded child process group under the environment snapshot it was enqueued with,
and writes a terminal receipt per item.

Each item is *resolved against the tree as it stands when the item starts*: the
payload must be present at the checkout's HEAD (or, on a root with no git
checkout, at the operator-supplied ``RESEARCH_COMMIT``) and free of uncommitted edits,
and the exact version about to run is re-gated with the repository's own gate
(``framework/gates/sbatch_gate.sh``, preflight mode) before the child starts. An
item therefore never dies because the checkout moved on while it waited, and
nothing runs whose gates did not clear at claim time.

Item records are the only source of truth: a failure is recorded rather than
retried, a dirty checkout stops the worker with the pending items untouched (no
override exists), and an empty lane exits after a bounded grace
(``RESEARCH_QUEUE_EMPTY_GRACE_SECONDS``) instead of idling.

The modules are by role: :mod:`session` holds the allocation's state, commit and
environment; :mod:`resolve` resolves a claimed item against the tree and re-gates
it; :mod:`execute` runs one resolved payload and receipts it; :mod:`lane` owns the
fit/handoff/idle decisions and the drain loop; :mod:`smoke` is the CPU smoke.

Run with the repository root on ``PYTHONPATH``::

    PYTHONPATH=<repo> python -u scripts/slurm_queue/cli.py worker --lane <lane_id>
    PYTHONPATH=<repo> python -u scripts/slurm_queue/cli.py worker --smoke
"""

from __future__ import annotations

from scripts.slurm_queue.worker.execute import (
    TERMINATE_GRACE_SECONDS,
    execute_item,
    run_item,
)
from scripts.slurm_queue.worker.lane import (
    HANDOFF_FAILURE,
    IDLE_POLL_SECONDS,
    IdleWindow,
    drain_loop,
    fail_unfittable,
    finish_allocation,
    hand_off,
    head_item,
    next_action,
    refresh_remaining,
    report_reconcile,
    run_lane,
)
from scripts.slurm_queue.worker.resolve import (
    gate_preflight,
    last_failure,
    resolve_item,
    resolve_or_refuse,
)
from scripts.slurm_queue.worker.session import (
    Resolved,
    WorkerInterrupted,
    WorkerSession,
    checkout_provenance,
    checkout_refusal,
    child_env,
    item_log_path,
    now_or_never,
    session_from_environment,
)
from scripts.slurm_queue.worker.smoke import (
    SMOKE_PAYLOAD,
    smoke,
    smoke_problems,
    smoke_session,
    write_smoke_payload,
)

__all__ = [
    "HANDOFF_FAILURE",
    "IDLE_POLL_SECONDS",
    "SMOKE_PAYLOAD",
    "TERMINATE_GRACE_SECONDS",
    "IdleWindow",
    "Resolved",
    "WorkerInterrupted",
    "WorkerSession",
    "checkout_provenance",
    "checkout_refusal",
    "child_env",
    "drain_loop",
    "execute_item",
    "fail_unfittable",
    "finish_allocation",
    "gate_preflight",
    "hand_off",
    "head_item",
    "item_log_path",
    "last_failure",
    "next_action",
    "now_or_never",
    "refresh_remaining",
    "report_reconcile",
    "resolve_item",
    "resolve_or_refuse",
    "run_item",
    "run_lane",
    "session_from_environment",
    "smoke",
    "smoke_problems",
    "smoke_session",
    "write_smoke_payload",
]
