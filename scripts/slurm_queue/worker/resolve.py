"""Resolve a claimed item against the tree as it stands, then re-gate it.

Invariants & Expected State:
    - Pinned Version: an item runs the payload committed at its executed commit,
      refused when the checkout's HEAD disagrees with the enqueue commit, and the
      bytes that run are exactly the ones the receipt digests.
    - Claim-Time Re-Gate: the exact version about to run clears the repository's
      own gate in preflight mode before the child starts.
    - Bounded Gate: the preflight is bounded by the claim-time budget plus a kill
      grace, so a wedged gate cannot stall the allocation.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import IO

from scripts.slurm_queue.model import (
    GATE_PREFLIGHT_ENV,
    GATE_SCRIPT,
    PREFLIGHT_BUDGET_SECONDS,
    ProvenanceError,
    QueueItem,
    committed_text,
    head_commit,
    sha256_text,
)
from scripts.slurm_queue.runtime import file_sha256

from .session import Resolved, WorkerSession, child_env

# The Python-side kill is a safety net for the external ``timeout`` wrapper: it
# fires only after the wrapper has had time to reap the gate itself.
PREFLIGHT_KILL_GRACE_SECONDS = 60


def resolve_or_refuse(
    session: WorkerSession,
    item: QueueItem,
    preflight: Callable[[WorkerSession, QueueItem, Path], str | None],
    log: Path,
) -> tuple[Resolved | None, tuple[str, int | None, str | None] | None]:
    """Return the resolved payload, or the terminal refusal that blocks it."""
    resolved, state, reason = resolve_item(session, item)
    if resolved is None:
        return None, (state, None, reason)
    failure = preflight(session, item, log)
    if failure is not None:
        return None, ("gate_failed", None, failure)
    return resolved, None


def gate_preflight(session: WorkerSession, item: QueueItem, log: Path) -> str | None:
    """Re-gate the version about to run; return why it is blocked, or ``None``."""
    gate = session.repo / GATE_SCRIPT
    if not gate.is_file():
        return (
            f"{GATE_SCRIPT} is missing under {session.repo}; cannot gate {item.script}"
        )
    env = child_env(item)
    env[GATE_PREFLIGHT_ENV] = "1"
    env["SBATCH_RUN_NAME"] = item.run_name
    with log.open("ab") as handle:
        handle.write(f"\n# claim-time gate preflight: {item.script}\n".encode())
        try:
            result = _gate_process(gate, item, session, env, handle)
        except subprocess.TimeoutExpired:
            return f"claim-time gate preflight exceeded its budget for {item.script}"
    if result.returncode == 0:
        return None
    return f"claim-time gate preflight failed for {item.script}: {last_failure(log)}"


def _gate_process(
    gate: Path,
    item: QueueItem,
    session: WorkerSession,
    env: dict[str, str],
    handle: IO[bytes],
) -> subprocess.CompletedProcess[str]:
    """Run the claim-time gate under its budget and return the finished process."""

    return subprocess.run(
        [
            "timeout",
            str(PREFLIGHT_BUDGET_SECONDS),
            "bash",
            str(gate),
            item.script,
        ],
        cwd=str(session.repo),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=PREFLIGHT_BUDGET_SECONDS + PREFLIGHT_KILL_GRACE_SECONDS,
    )


def last_failure(log: Path, limit: int = 400) -> str:
    """Return the gate output that explains a failed preflight, bounded."""
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        return f"log unreadable: {error}"
    blocked = [line for line in lines if "FAIL(" in line or "ABORT" in line]
    tail = blocked[-3:] or lines[-3:]
    return " | ".join(tail)[-limit:] or "preflight produced no output"


def resolve_item(
    session: WorkerSession, item: QueueItem
) -> tuple[Resolved | None, str, str | None]:
    """Resolve an item against the tree as it stands now.

    Returns ``(resolved, "", None)`` when the payload may run, else
    ``(None, state, reason)`` with the terminal state that refuses it. The
    resolved bytes are what the child executes, so a payload rewritten while the
    item runs cannot split the run across two versions.
    """
    if not session.git_available:
        return external_payload(session, item)
    path = session.repo / item.script
    try:
        digest = file_sha256(path)
    except OSError as error:
        return None, "payload_missing", f"payload {item.script} is unreadable: {error}"
    try:
        committed = committed_text(session.repo, item.script)
    except ProvenanceError:
        return (
            None,
            "payload_missing",
            f"payload {item.script} is not committed at HEAD",
        )
    if digest != sha256_text(committed):
        return None, "payload_dirty", f"payload {item.script} has uncommitted edits"
    body = committed.encode("utf-8")
    return Resolved(head_commit(session.repo), digest, body), "", None


def external_payload(
    session: WorkerSession, item: QueueItem
) -> tuple[Resolved | None, str, str | None]:
    """Resolve a payload in a git-less deploy root against its deployed bytes."""
    try:
        body = (session.repo / item.script).read_bytes()
    except OSError as error:
        return None, "payload_missing", f"payload {item.script} is unreadable: {error}"
    return Resolved(session.commit, hashlib.sha256(body).hexdigest(), body), "", None
