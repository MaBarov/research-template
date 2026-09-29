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
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
MUTANTS_DIR = REPO / "mutants"

WORKER_ENV = {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}

#: Wall-clock bound for one refresh; a hung run fails closed instead of hanging
#: a developer session, and mutmut's own per-mutant CPU limits stay in force.
REFRESH_TIMEOUT_SECONDS = 7200

UNKNOWN_EXIT_CODE = 999_999


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
