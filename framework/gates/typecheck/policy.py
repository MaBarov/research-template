"""Typed population, engine and interpreter resolution of the static-type gate.

Thumbnail: scope roots, staged selection, and checker/interpreter resolution.

Invariants & Expected State:
    * ``TYPED_ROOTS`` owns exactly the first-party trees from ``harness.STATIC_ROOTS``;
      ``tests``, ``third_party`` and cache trees are never selected.
    * An in-tree path is subject to the population rule even when listed
      explicitly; only an absolute path outside the repository is honored as a
      one-off audit probe.
    * ``select_paths_detailed`` returns every declined path with its reason, so
      the CLI can report scope decisions and fail closed instead of skipping silently.
    * Engine resolution returns ``None`` instead of inventing a checker, so the
      CLI can fail closed (mypy) or fall back to a NOTE (pyright census).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework import harness

REPO = harness.REPO
CONFIG = REPO / "pyproject.toml"
CACHE_DIR = REPO / harness.CACHE_DIR / "typecheck" / "mypy"
TYPED_ROOTS = tuple(harness.STATIC_ROOTS)
EXCLUDED_PARTS = harness.EXCLUDED_PARTS


def relative(path: str | Path) -> str:
    """Return ``path`` as a repository-relative posix string when it is inside."""
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(REPO).as_posix()
        except ValueError:
            return candidate.as_posix()
    return Path(os.path.normpath(candidate)).as_posix()


def decline_reason(rel: str) -> str | None:
    """Return why ``rel`` is outside the typed population, or ``None``."""
    path = Path(rel)
    if path.is_absolute():
        return "absolute path outside the repository that is not a file"
    if path.suffix != ".py":
        return "not a Python module"
    parts = path.parts
    if not parts or parts[0] not in TYPED_ROOTS:
        return f"outside the typed population (roots: {', '.join(TYPED_ROOTS)})"
    excluded = [part for part in parts if part in EXCLUDED_PARTS]
    if excluded:
        return f"excluded tree '{excluded[0]}'"
    return None


def is_typed_path(rel: str) -> bool:
    """Return whether a repository-relative path is inside the typed population."""
    return decline_reason(rel) is None


def outside_repo(raw: str) -> bool:
    """Return whether ``raw`` is an absolute path that lives outside the repo."""
    candidate = Path(raw)
    if not candidate.is_absolute():
        return False
    try:
        candidate.resolve().relative_to(REPO)
    except ValueError:
        return True
    return False


def select_paths_detailed(
    paths: Iterable[str],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Return the typed selection and every declined path with its reason."""
    selected: dict[str, None] = {}
    declined: dict[str, str] = {}
    for raw in paths:
        rel = relative(raw)
        reason = decline_reason(rel)
        if reason is None:
            selected[rel] = None
        elif outside_repo(raw) and Path(raw).is_file():
            selected[raw] = None
        else:
            declined[rel] = reason
    return sorted(selected), sorted(declined.items())


def select_paths(paths: Iterable[str]) -> list[str]:
    """Return the unique typed paths of an explicit file list, sorted."""
    return select_paths_detailed(paths)[0]


def typed_sources() -> list[str]:
    """Return every typed module of the working tree, repository-relative."""
    found: list[str] = []
    for root in TYPED_ROOTS:
        directory = REPO / root
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            if is_typed_path(rel):
                found.append(rel)
    return found


def index_selection() -> list[str]:
    """Return the typed modules staged in the Git index, repository-relative."""
    completed = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return select_paths(completed.stdout.split())


def index_drift(paths: Iterable[str]) -> list[str]:
    """Return the paths whose working-tree content differs from the Git index."""
    candidates = sorted(dict.fromkeys(paths))
    if not candidates:
        return []
    completed = subprocess.run(
        ["git", "diff", "--name-only", "--", *candidates],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    changed = set(completed.stdout.split())
    return [path for path in candidates if path in changed]


def staged_blob(rel: str) -> str | None:
    """Return the staged text of a repository-relative path, or ``None``."""
    completed = subprocess.run(
        ["git", "show", f":{rel}"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout


def write_shadow(rel: str, text: str) -> Path:
    """Write one staged blob to the shadow tree and return its path."""
    shadow_root = CACHE_DIR.parent / "shadow"
    shadow_root.mkdir(parents=True, exist_ok=True)
    shadow = shadow_root / Path(rel).name
    shadow.write_text(text, encoding="utf-8")
    return shadow


def shadow_pairs(modules: Iterable[str]) -> tuple[list[str], list[str]]:
    """Return ``(mypy --shadow-file argv, drifted paths)`` for staged modules.

    A module whose working tree moved on after staging is checked as the staged
    blob (`git show :path`) rather than as the working-tree file, so the gate
    decides on exactly what the commit will write while partial staging stays
    legal. A drifted module whose blob cannot be read is left unshadowed and the
    caller never reports it clean (the checker then sees the working tree).
    """
    drift = index_drift(modules)
    argv: list[str] = []
    shadowed: list[str] = []
    for rel in drift:
        blob = staged_blob(rel)
        if blob is None:
            continue
        argv += ["--shadow-file", rel, str(write_shadow(rel, blob))]
        shadowed.append(rel)
    return argv, shadowed


_DEFAULT_INTERPRETER = Path(harness.python())


def interpreter() -> Path:
    """Return the project interpreter from harness."""
    override = os.environ.get(harness.env("PYTHON"))
    if override and Path(override).is_file():
        return Path(override)
    return _DEFAULT_INTERPRETER


def engine_command(engine: str) -> list[str] | None:
    """Return the resolved checker argv prefix, or ``None`` when it is absent."""
    candidate = harness.engine_bin(engine)
    if not candidate:
        return None
    if Path(candidate).is_file():
        return [candidate]
    found = shutil.which(candidate)
    if found:
        return [found]
    return None


def ensure_cache_dir() -> Path:
    """Return the mypy cache directory, created under the ignored ``cache`` tree."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR
