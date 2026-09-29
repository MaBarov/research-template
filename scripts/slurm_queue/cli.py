"""Command-line entry point for the Slurm draining queue.

Two subcommands, both run with the repository root importable::

    PYTHONPATH=<repo> python -u scripts/slurm_queue/cli.py enqueue \
        --script slurm/<name>.sbatch --run-name <unique-name> [--cluster <name>] \
        [--bank experiments/...json] [--seed 0]
    PYTHONPATH=<repo> python -u scripts/slurm_queue/cli.py worker \
        --lane <lane-id> --repo <root>

``enqueue`` prints one JSON object on success (``status``, ``item_id``,
``lane_id``, ``worker_job_id``, ``worker_submitted``); every refusal exits 1
without submitting anything. ``worker`` is what
``slurm/run_slurm_queue_worker.sbatch`` runs inside the lane's allocation: it
drains the lane and exits 90 when the session cannot be established.

Invariants & Expected State:
    - Refusal Before Mutation: the payload, its worker root, and its run name are
      checked before anything is published, and a refused worker start withdraws
      the published item.
    - Single Publish: the run name is allocated and the item published under the
      lane lock plus the store root lock, so two lanes never share a run name.
    - Exit Contract: ``enqueue`` prints one JSON record and exits 0; every
      refusal exits 1 with its reason on stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from framework import harness
from scripts.slurm_queue.model import (
    DEFAULT_WORKER_TIME,
    EMPTY_GRACE_ENV,
    WORKER_ROOT_ENV,
    WORKER_TIME_ENV,
    ProvenanceError,
    QueueItem,
    ResourceProfile,
    SbatchRejection,
    empty_grace_seconds,
    environment_snapshot,
    head_commit,
    now_iso,
    parse_sbatch,
    resolve_script,
    run_git,
    sha256_text,
)
from scripts.slurm_queue.store import (
    LaneProfileMismatch,
    QueueLockError,
    QueueStateError,
    QueueStore,
)
from scripts.slurm_queue.submit import SlurmError, WorkerRef, ensure_worker
from scripts.slurm_queue.worker import (
    now_or_never,
    run_lane,
    session_from_environment,
    smoke,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
QUEUE_ERRORS = (
    SbatchRejection,
    ProvenanceError,
    QueueStateError,
    QueueLockError,
    LaneProfileMismatch,
    SlurmError,
)


def committed_text(repo: Path, script: str) -> str:
    """Return the payload exactly as committed; unstaged edits never reach Slurm."""
    return run_git(repo, ["show", f"HEAD:{script}"])


def check_run_name(run_name: str) -> str:
    """Refuse a run name that would not be extractable from Slurm state."""
    if not RUN_NAME_RE.fullmatch(run_name):
        raise SbatchRejection(f"run name {run_name!r} must match {RUN_NAME_RE.pattern}")
    return run_name


def build_item(
    repo: Path,
    script: str,
    source: str,
    args: argparse.Namespace,
    environ: Mapping[str, str],
) -> QueueItem:
    """Build the item record exactly as the payload and environment describe it."""
    profile, requested = parse_sbatch(
        source, args.cluster, environ.get(WORKER_TIME_ENV, DEFAULT_WORKER_TIME)
    )
    return QueueItem(
        item_id="",
        sequence=0,
        lane_id=profile.lane_id(),
        enqueued_at=now_iso(),
        script=script,
        script_sha256=sha256_text(source),
        commit=head_commit(repo),
        run_name=check_run_name(args.run_name),
        requested_seconds=requested,
        profile=profile,
        banks=tuple(args.bank),
        seeds=tuple(int(seed) for seed in args.seed),
        env=environment_snapshot(environ),
    )


def start_worker(
    store: QueueStore, profile: ResourceProfile, published: QueueItem, repo: Path
) -> WorkerRef:
    """Start the lane's worker; withdraw the published item when that fails.

    The item must exist before the worker is ensured, otherwise a worker that
    drains immediately could exit on an empty lane before it sees the item. The
    cost is this rollback: a refused submission leaves nothing behind and frees
    the run name, so the retry is a plain retry.
    """
    try:
        return ensure_worker(store, profile, repo)
    except SlurmError as error:
        store.unpublish(profile, published.item_id)
        raise SlurmError(
            f"the lane worker could not be started ({error}); the item was "
            "withdrawn and its run name is free again"
        ) from error


def _require_worker_root(repo: Path, environ: Mapping[str, str]) -> None:
    """Refuse an explicit worker root that names a different checkout.

    The worker launcher resolves the tree it drains from ``RESEARCH_ROOT``; a stale
    value would start the fresh worker against another checkout, where the
    payload is not present at HEAD and the item could only fail its claim-time
    gate. An unset value stays the launcher's own default.
    """
    root = environ.get(WORKER_ROOT_ENV, "").strip()
    if root and Path(root).expanduser().resolve() != repo:
        raise SbatchRejection(
            f"{WORKER_ROOT_ENV}={root} does not name the enqueue checkout {repo}; "
            "the worker would drain a different tree"
        )


def enqueue(args: argparse.Namespace, environ: Mapping[str, str]) -> int:
    """Validate, persist, and start one queue item, then print its record."""
    repo = Path(args.repo).resolve()
    store = QueueStore.default(repo, environ)
    script = resolve_script(repo, args.script)
    item = build_item(repo, script, committed_text(repo, script), args, environ)
    _require_worker_root(repo, environ)
    with store.lane_lock(item.profile):
        published = _publish_item(store, item)
        ref = start_worker(store, item.profile, published, repo)
    print(
        json.dumps(
            {
                "cluster": item.profile.cluster,
                "item_id": published.item_id,
                "lane_id": published.lane_id,
                "run_name": published.run_name,
                "script": published.script,
                "status": "enqueued",
                "worker_job_id": ref.job_id,
                "worker_submitted": ref.submitted,
            },
            sort_keys=True,
        )
    )
    return 0


def _publish_item(store: QueueStore, item: QueueItem) -> QueueItem:
    """Allocate the run name and publish one item under the store-wide lock."""
    with store.root_lock():
        clash = store.run_name_in_use(item.run_name)
        if clash is not None:
            raise SbatchRejection(
                f"run name {item.run_name} is already used by {clash}"
            )
        return store.publish(item, item.profile)


def run_worker(args: argparse.Namespace, environ: Mapping[str, str]) -> int:
    """Drain one lane allocation: the queue worker's process entry point."""
    repo = Path(args.repo).resolve()
    if args.smoke:
        return smoke(repo)
    try:
        grace = empty_grace_seconds(environ)
        session = session_from_environment(repo, args.lane, environ)
    except (SbatchRejection, ProvenanceError, QueueStateError) as error:
        print(f"status=RESEARCH_SLURM_QUEUE_WORKER_ABORT reason={error}", flush=True)
        return 90
    print(
        f"status=RESEARCH_SLURM_QUEUE_WORKER_START job={session.job_id} "
        f"lane={session.profile.lane_id()} commit={session.commit} "
        f"tree_state={session.tree_state()} "
        f"remaining={now_or_never(session.remaining_seconds)} "
        f"grace={grace:.0f}s ({EMPTY_GRACE_ENV})",
        flush=True,
    )
    return run_lane(session, grace_seconds=grace)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the queue CLI's ``enqueue`` and ``worker`` subcommands."""
    parser = argparse.ArgumentParser(
        prog="slurm_queue",
        description="Submit one committed sbatch script into a draining lane.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    _add_enqueue_args(sub)
    _add_worker_args(sub)
    return parser.parse_args(argv)


def _add_enqueue_args(sub: argparse._SubParsersAction) -> None:
    """Add the ``enqueue`` subcommand: payload, run name, cluster, banks, seeds."""
    enqueue_parser = sub.add_parser(
        "enqueue", help="queue one committed slurm/*.sbatch payload"
    )
    enqueue_parser.add_argument(
        "--script", required=True, help="committed payload path"
    )
    enqueue_parser.add_argument("--run-name", required=True, help="unique run name")
    enqueue_parser.add_argument(
        "--cluster",
        choices=harness.QUEUE_CLUSTERS,
        default=harness.QUEUE_CLUSTERS[0],
        help="target cluster",
    )
    enqueue_parser.add_argument(
        "--bank", action="append", default=[], help="concept bank the payload reads"
    )
    enqueue_parser.add_argument(
        "--seed", action="append", default=[], help="seed the payload will run with"
    )
    enqueue_parser.add_argument(
        "--repo", default=str(REPO_ROOT), help="repository root"
    )


def _add_worker_args(sub: argparse._SubParsersAction) -> None:
    """Add the ``worker`` subcommand: lane id, repository root, smoke switch."""
    worker_parser = sub.add_parser(
        "worker", help="drain one lane allocation (runs inside the allocation)"
    )
    worker_parser.add_argument("--lane", default=None, help="lane id to drain")
    worker_parser.add_argument("--repo", default=str(REPO_ROOT), help="repository root")
    worker_parser.add_argument(
        "--smoke", action="store_true", help="run the CPU smoke and exit"
    )


def main(
    argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None
) -> int:
    """Dispatch one subcommand; every refusal exits non-zero without submitting."""
    source = os.environ if environ is None else environ
    args = parse_args(argv)
    if args.command == "worker":
        if not args.lane and not args.smoke:
            print("[slurm_queue] worker refused: --lane is required", file=sys.stderr)
            return 1
        try:
            return run_worker(args, source)
        except QUEUE_ERRORS as error:
            print(f"[slurm_queue] worker refused: {error}", file=sys.stderr)
            return 1
    try:
        return enqueue(args, source)
    except QUEUE_ERRORS as error:
        print(f"[slurm_queue] enqueue refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
