"""Worker session state: the allocation's checkout, commit and environment.

Invariants & Expected State:
    - Allocation Identity: a session exists only inside a Slurm allocation whose
      job name names its lane, and a root without a git checkout must carry
      ``RESEARCH_COMMIT`` as its commit identity.
    - Labelled Dirt: a dirty checkout refuses the drain, unconditionally and
      with no override (user ruling 2026-09-26), and
      :meth:`WorkerSession.tree_state` labels the state it refused.
    - Snapshot Environment: the child sees the enqueue-time ``RESEARCH_*`` set from
      the item record, never the worker's inherited values.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from framework import harness
from scripts.slurm_queue.model import (
    QUEUE_CLUSTER_ENV,
    RECORDED_ENV,
    ProvenanceError,
    QueueItem,
    ResourceProfile,
    head_commit,
    is_dirty,
    worker_job_name,
)
from scripts.slurm_queue.store import QueueStateError, QueueStore
from scripts.slurm_queue.submit import allocation_remaining_seconds


def item_log_path(session: WorkerSession, item: QueueItem) -> Path:
    """Return the item's child-log path inside its lane."""
    lane = session.store.lane(session.profile.cluster, session.profile.lane_id())
    return lane.logs() / f"{item.sequence:06d}_{item.item_id}.log"


def child_env(item: QueueItem) -> dict[str, str]:
    """Return the worker environment with inherited ``RESEARCH_*`` replaced by the snapshot."""
    env = {
        key: value for key, value in os.environ.items() if not RECORDED_ENV.match(key)
    }
    env.update(item.env_map())
    return env


def checkout_refusal(session: WorkerSession) -> str | None:
    """Return why the worker must not start, or ``None`` when the checkout is usable."""
    if session.tree_clean:
        return None
    return (
        "dirty working tree; commit the work before draining the lane "
        "(a dirty run has no commit identity, and no override exists)"
    )


def session_from_environment(
    repo: Path, lane_id: str, environ: Mapping[str, str] | None = None
) -> WorkerSession:
    """Build the session an allocation actually runs with (git + Slurm + store)."""
    source = os.environ if environ is None else environ
    job_id = _allocation_job_id(source, lane_id)
    store = QueueStore.default(repo, source)
    cluster = source.get(QUEUE_CLUSTER_ENV) or harness.QUEUE_CLUSTERS[0]
    profile = store.read_profile(cluster, lane_id)
    commit, git_available, tree_clean = checkout_provenance(repo, source)
    return WorkerSession(
        repo=repo,
        store=store,
        profile=profile,
        job_id=job_id,
        commit=commit,
        tree_clean=tree_clean,
        remaining_seconds=allocation_remaining_seconds(job_id),
        git_available=git_available,
    )


def _allocation_job_id(source: Mapping[str, str], lane_id: str) -> str:
    """Return the allocation's job id, refusing one that names another lane."""
    job_id = source.get("SLURM_JOB_ID", "").strip()
    if not job_id:
        raise QueueStateError(
            "SLURM_JOB_ID is unset; refusing to drain outside an allocation"
        )
    job_name = source.get("SLURM_JOB_NAME", "").strip()
    if job_name and job_name != worker_job_name(lane_id):
        raise QueueStateError(
            f"SLURM_JOB_NAME={job_name!r} does not name lane {lane_id!r}; refusing "
            "to drain a lane this allocation was not submitted for"
        )
    return job_id


def checkout_provenance(
    repo: Path, environ: Mapping[str, str] | None = None
) -> tuple[str, bool, bool]:
    """Return the root's commit, whether git answered, and whether it is clean.

    A root with no git checkout (a content-addressed deploy root) must carry the
    commit it was staged at in ``RESEARCH_COMMIT``; that commit is then the identity
    its receipts record.
    """
    source = os.environ if environ is None else environ
    try:
        return head_commit(repo), True, not is_dirty(repo)
    except ProvenanceError:
        commit = source.get("RESEARCH_COMMIT", "").strip()
        if not commit:
            raise ProvenanceError(
                "no git checkout under the root and RESEARCH_COMMIT is unset; "
                "refusing to drain without a commit identity"
            ) from None
        return commit, False, True


def now_or_never(seconds: float | None) -> str:
    """Render a remaining-seconds value for a status line."""
    return "unknown" if seconds is None else f"{seconds:.0f}"


@dataclass(frozen=True)
class WorkerSession:
    """Everything one worker invocation needs, so tests need no git or Slurm."""

    repo: Path
    store: QueueStore
    profile: ResourceProfile
    job_id: str
    commit: str
    tree_clean: bool
    remaining_seconds: float | None
    git_available: bool = True

    def tree_state(self) -> str:
        """Return the provenance label this allocation's receipts carry."""
        if not self.tree_clean:
            return "dirty"
        return "clean" if self.git_available else "external-commit"


@dataclass(frozen=True)
class Resolved:
    """The payload version an item actually runs."""

    commit: str
    script_sha256: str
    payload: bytes


class WorkerInterrupted(Exception):
    """Raised in the worker when Slurm asks the allocation to stop."""


def _raise_interrupt(signum: int, frame: object) -> None:
    raise WorkerInterrupted(f"worker received signal {signum}")
