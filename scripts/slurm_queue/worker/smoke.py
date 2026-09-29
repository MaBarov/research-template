"""CPU smoke: exercise publish, claim, execute and receipt without Slurm.

Invariants & Expected State:
    - Runs entirely on a temporary root; it never touches the live queue or the
      real receipt directory.
    - Hermetic Horizon: the drain's `remaining`/`live` probes are answered from
      constants, never from the host's `scontrol`/`squeue`. A smoke that read the
      login node's job table would pass or fail on whatever else is running on
      it — job id ``0`` resolves to some unrelated job on a busy cluster.
    - Exercises the published contract surface in order (publish, claim,
      execute, receipt) and fails loudly on the first broken step.
    - Exits 0 only when the whole cycle completes; any exception propagates.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from framework import harness
from scripts.slurm_queue.model import (
    DEFAULT_WORKER_TIME,
    SCRIPT_ROOT,
    QueueItem,
    ResourceProfile,
    now_iso,
    parse_sbatch,
    sha256_text,
)
from scripts.slurm_queue.store import QueueStore

from .lane import run_lane
from .session import WorkerSession

# The smoke has no Slurm allocation: an hour of headroom comfortably fits the
# template's 20-minute payload plus the item overhead, and every horizon read
# answers the same value, so the drain's fit decision cannot drift mid-run.
SMOKE_HORIZON_SECONDS = 3600.0


def _smoke_remaining(job_id: str) -> float:
    """Report the smoke's synthetic horizon, never the host's job table."""
    return SMOKE_HORIZON_SECONDS


def _smoke_live(lane_id: str) -> dict[str, str]:
    """Report no live jobs: the smoke's lane exists only inside its temp root."""
    return {}


def smoke(repo: Path) -> int:
    """Exercise parse, enqueue, claim, execute, and receipt without Slurm."""
    template = (repo / SCRIPT_ROOT / "template.sbatch").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix=f"{harness.SLUG}_queue_smoke_") as tmp:
        session, store, item_id = smoke_session(Path(tmp), template)
        print(
            f"status=RESEARCH_SLURM_QUEUE_SMOKE_START lane={session.profile.lane_id()}",
            flush=True,
        )
        code = run_lane(
            session,
            preflight=smoke_preflight,
            remaining_probe=_smoke_remaining,
            live_probe=_smoke_live,
        )
        receipt = store.existing_receipt(session.profile, item_id)
        problems = smoke_problems(code, session, receipt, item_id)
    if problems:
        for problem in problems:
            print(f"[slurm_queue] SMOKE FAIL: {problem}", file=sys.stderr)
        return 1
    print("status=RESEARCH_SLURM_QUEUE_SMOKE_OK", flush=True)
    return 0


def smoke_problems(
    code: int, session: WorkerSession, receipt: Path | None, item_id: str
) -> list[str]:
    """Return every way the smoke run failed to behave like a real drain."""
    problems: list[str] = []
    if code != 0:
        problems.append(f"drain exited {code}")
    if receipt is None:
        problems.append(f"no terminal receipt for {item_id}")
    elif json.loads(receipt.read_text(encoding="utf-8")).get("state") != "succeeded":
        problems.append(f"receipt {receipt} is not a success")
    if session.store.pending_items(session.profile):
        problems.append("pending items remain after the drain")
    lane = session.store.lane(session.profile.cluster, session.profile.lane_id())
    leftovers = sorted(path.name for path in lane.running().glob("*.json"))
    if leftovers:
        problems.append(f"running records remain: {leftovers}")
    if lane.worker().exists():
        problems.append("worker record remains after an empty drain")
    return problems


def smoke_preflight(session: WorkerSession, item: QueueItem, log: Path) -> None:
    """The smoke exercises the drain path; the gate preflight has its own suite."""
    return


def smoke_session(root: Path, template: str) -> tuple[WorkerSession, QueueStore, str]:
    """Build a temporary lane holding one harmless item, and run it."""
    profile, requested = parse_sbatch(
        template, cluster=harness.QUEUE_CLUSTERS[0], worker_time=DEFAULT_WORKER_TIME
    )
    store = QueueStore(root=root / "queue")
    exec_repo = root / "repo"
    write_smoke_payload(exec_repo)
    with store.lane_lock(profile):
        published = store.publish(_smoke_item(profile, requested), profile)
    session = WorkerSession(
        repo=exec_repo,
        store=store,
        profile=profile,
        job_id="0",
        commit="smoke",
        tree_clean=True,
        remaining_seconds=SMOKE_HORIZON_SECONDS,
        git_available=False,
    )
    return session, store, published.item_id


def _smoke_item(profile: ResourceProfile, requested: int) -> QueueItem:
    """Build the harmless item the smoke publishes into a temporary lane."""
    return QueueItem(
        item_id="",
        sequence=0,
        lane_id=profile.lane_id(),
        enqueued_at=now_iso(),
        script=f"{SCRIPT_ROOT}/template.sbatch",
        script_sha256=sha256_text(SMOKE_PAYLOAD),
        commit="smoke",
        run_name="queue_smoke",
        requested_seconds=requested,
        profile=profile,
        env=((harness.env("SMOKE_MARKER"), "1"),),
    )


def write_smoke_payload(root: Path) -> None:
    """Create the harmless payload repository the smoke executes in."""
    directory = root / SCRIPT_ROOT
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "template.sbatch").write_text(SMOKE_PAYLOAD, encoding="utf-8")


SMOKE_PAYLOAD = """#!/usr/bin/env bash
set -euo pipefail
echo "status=RESEARCH_SLURM_QUEUE_SMOKE_PAYLOAD_DONE"
"""
