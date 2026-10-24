"""mutmut driver for the mutation gate: score the population, read the verdicts.

Invariants & Expected State:
 * Statuses come from mutmut's own ``status_by_exit_code`` table, so the gate
   never re-implements the tool's verdict vocabulary; an unknown exit code maps
   to that table's fallback (``suspicious``) and therefore blocks.
 * A module mutmut never scored cannot produce a cleared verdict: a missing
   ``mutants/<module>.meta`` is an error, while a present-but-empty one is a
   module with zero mutable lines and clears at ``mutants = 0``.
 * The child run pins ``OMP_NUM_THREADS``/``MKL_NUM_THREADS`` to one thread:
   unpinned BLAS on a many-core host turns fast tests into false timeouts.
 * mutmut caches each mutant's verdict and does not notice a test edit, so a
   refresh drops that cache whenever the test surface moved: the stamp beside it
   records which digest the cached verdicts were scored against.
 * Refreshes serialize on an exclusive lock under the repository's git dir: a
   second refresh fails fast instead of sharing ``mutants/`` with the first,
   because two concurrent scorers interleave verdicts and each can reuse the
   other's half-written mutation cache.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO

import framework.harness

REPO = Path(__file__).resolve().parents[3]
MUTANTS_DIR = REPO / "mutants"
CACHE_STAMP_NAME = ".tests-digest"

WORKER_ENV = {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}

#: Wall-clock bound for one refresh; a hung run fails closed instead of hanging
#: a developer session, and mutmut's own per-mutant CPU limits stay in force.
REFRESH_TIMEOUT_SECONDS = 7200

UNKNOWN_EXIT_CODE = 999_999


def cache_stamp() -> Path:
    """Where the test-surface digest of the cached verdicts is recorded."""

    return MUTANTS_DIR / CACHE_STAMP_NAME


def cached_tests_sha256() -> str | None:
    """The test-surface digest the cached mutmut verdicts were scored against."""

    try:
        return cache_stamp().read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _discard(path: Path) -> None:
    """Remove one cache path whether it is a directory or a file."""

    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


class RefreshBusy(RuntimeError):
    """Another process holds the refresh lock and is already scoring."""


def _lock_path() -> Path:
    """Where refreshes serialize: the repo's git dir, or the temp dir off-checkout."""

    git_dir = REPO / ".git"
    if git_dir.is_dir():
        return git_dir / framework.harness.GATE_STATE_DIR / "mutation-refresh.lock"
    digest = hashlib.sha256(str(REPO).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"mutation-refresh-{digest}.lock"


def _busy_message(handle: TextIO) -> str:
    """The refusal naming whoever holds the refresh lock."""

    handle.seek(0)
    holder = handle.read().strip() or "an unidentified process"
    return f"another mutation refresh is scoring ({holder}); wait for it to finish"


@contextmanager
def refresh_lock() -> Iterator[None]:
    """Serialize scorers: one mutmut run per repository, a peer's is refused."""

    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle: TextIO = path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RefreshBusy(_busy_message(handle)) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid {os.getpid()}")
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def prepare_cache(tests_sha256: str) -> str | None:
    """Drop mutmut's verdict cache when it predates ``tests_sha256``."""

    if cached_tests_sha256() == tests_sha256:
        return None
    for path in (MUTANTS_DIR, REPO / ".mutmut-cache"):
        _discard(path)
    stamp = cache_stamp()
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(tests_sha256 + "\n", encoding="utf-8")
    return "mutmut cache dropped: the test surface moved since the last score"


def status_table() -> tuple[dict[int | None, str] | None, str | None, str | None]:
    """mutmut's status map, its unknown-code fallback status, or why it is absent."""
    try:
        from mutmut.stats import status_by_exit_code as table
    except ImportError as exc:
        return None, None, f"mutmut is not importable by {sys.executable}: {exc}"
    return dict(table), table[UNKNOWN_EXIT_CODE], None


def mutmut_version(python: str | None = None) -> tuple[str | None, str | None]:
    """The installed mutmut version reported by ``-m mutmut --version``."""
    interpreter = sys.executable if python is None else python
    proc = subprocess.run(
        [interpreter, "-m", "mutmut", "--version"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None, f"{interpreter} -m mutmut --version failed: {proc.stderr.strip()}"
    return proc.stdout.strip(), None


def run_mutmut(jobs: int, python: str | None = None) -> int:
    """Score every uncached or invalidated mutant; mutmut's output streams through."""
    interpreter = sys.executable if python is None else python
    environment = dict(os.environ)
    environment.update(WORKER_ENV)
    proc = subprocess.run(
        [interpreter, "-m", "mutmut", "run", "--max-children", str(jobs)],
        cwd=REPO,
        env=environment,
        check=False,
        timeout=REFRESH_TIMEOUT_SECONDS,
    )
    return proc.returncode


def meta_path(rel: str) -> Path:
    """Where mutmut stores one module's verdicts."""
    return MUTANTS_DIR / f"{rel}.meta"


def collect_statuses(rel: str) -> tuple[dict[str, str], str | None]:
    """Map every recorded mutant of ``rel`` to a status, or say why it cannot."""
    path = meta_path(rel)
    if not path.is_file():
        return {}, f"mutmut recorded nothing for {rel} (missing {path.name})"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"unreadable mutation meta for {rel}: {exc}"
    table, fallback, error = status_table()
    if error is not None or table is None or fallback is None:
        return {}, error or "mutmut exposes no fallback status; refusing to guess"
    codes: Mapping[str, Any] = data.get("exit_code_by_key") or {}
    return {name: table.get(code, fallback) for name, code in codes.items()}, None


def aggregate(statuses: Mapping[str, str]) -> dict[str, int]:
    """Count statuses, emitting every blocking key so a silent slip is impossible."""
    counts: dict[str, int] = {"killed": 0, "skipped": 0}
    for status in statuses.values():
        key = status.replace(" ", "_")
        counts[key] = counts.get(key, 0) + 1
    counts["mutants"] = len(statuses)
    return counts


def names_by_status(statuses: Mapping[str, str]) -> dict[str, list[str]]:
    """The mutant names behind each status, so findings can print the offender."""
    grouped: dict[str, list[str]] = {}
    for name, status in sorted(statuses.items()):
        grouped.setdefault(status.replace(" ", "_"), []).append(name)
    return grouped
