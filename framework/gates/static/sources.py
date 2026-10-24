"""Shared target selection and fail-closed source loading for the static gates.

Thumbnail: One target predicate and one staged-blob reader for every static gate.

Invariants & Expected State:
    - Identity comes from the harness: the population is ``harness.STATIC_ROOTS``
      and the exclusions are ``harness.EXCLUDED_PARTS``, so a new tree is adopted
      in one place and every static gate follows.
    - ``read_staged`` fails closed: a git failure or a timeout raises
      ``RuntimeError`` instead of returning empty source, because a wedged index
      that reads as clean is worse than a gate that refuses.
    - ``relative_path`` never invents a path: a target outside the repository
      keeps its absolute form rather than being silently rebased onto this tree.
    - ``is_target_python`` judges the path only (suffix, first component, excluded
      parts) and never touches the file, so a caller can filter a staged list
      without I/O.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from framework import harness

REPO = harness.REPO
PRODUCTION_ROOTS = frozenset(harness.STATIC_ROOTS)
CHECKED_SUFFIXES = frozenset({".py"})
EXCLUDED_PARTS = frozenset(harness.EXCLUDED_PARTS)


def relative_path(path: str | Path) -> str:
    """Normalize an absolute or relative path to a repository-relative string."""
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(REPO)
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


def is_production_path(path: str) -> bool:
    """Return True if the path's first component is a static root."""
    parts = Path(path).parts
    return bool(parts) and parts[0] in PRODUCTION_ROOTS


def is_target_python(path: str) -> bool:
    """Return True if the path names a scoped, non-package production module."""
    rel = relative_path(path)
    parts = Path(rel)
    if parts.suffix.lower() not in CHECKED_SUFFIXES or parts.name == "__init__.py":
        return False
    if not is_production_path(rel):
        return False
    return not any(part in EXCLUDED_PARTS for part in parts.parts)


def read_staged(path: str, repo: Path | None = None) -> str:
    """Return the staged blob of ``path``; a wedged git fails closed, never hangs."""
    try:
        result = subprocess.run(
            ["git", "show", f":{path}"],
            cwd=repo or REPO,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"timed out reading staged file {path}") from None
    if result.returncode:
        stderr = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"cannot read staged file {path}: {stderr}")
    return result.stdout.decode("utf-8")
