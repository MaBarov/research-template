"""Target definitions and source loaders for the device transfer gate.

Thumbnail: Target finding dataclass and fail-closed file loaders for transfer audits.

Invariants & Expected State:
    Finding objects are immutable dataclasses with compiler-style formatting.
    Target predicates identify production Python sources under the static roots.
    _load_source fails closed with HNS010 on missing or unreadable staged files.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework import harness

REPO = harness.REPO
PRODUCTION_ROOTS = set(harness.STATIC_ROOTS)
CHECKED_SUFFIXES = {".py"}
_EXCLUDED_PARTS = set(harness.EXCLUDED_PARTS)


@dataclass(frozen=True)
class Finding:
    """One anti-pattern finding with file path, line number, code, and message.

    ``trigger`` records why the rule fired, in one of four states: ``static``
    when the defect is a context-free shape that fails wherever it appears (a
    host tensor meeting a device tensor in one expression, which torch refuses
    on every run), ``loop`` when an enclosing loop or comprehension repeats the
    call, ``aggregate`` when the evidence is a context-free shape (a
    concatenation whose elements are moved one by one, which costs the same
    wherever it appears), and ``streaming`` when only the enclosing function's
    name marks a per-forward pass. The split is reported so a name-triggered
    finding is never read as a measured per-iteration cost.
    """

    path: str
    line: int
    code: str
    message: str
    trigger: str = "loop"

    def format(self) -> str:
        """Format finding for standard compiler-style CLI diagnostic output."""
        return f"{self.path}:{self.line}: {self.code} {self.message}"


def _relative_path(path: str | Path) -> str:
    """Normalize absolute or relative path to a repository-relative string."""
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(REPO)
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


def _is_production_path(path: str) -> bool:
    """Return True if path starts with one of the configured production roots."""
    parts = Path(path).parts
    return bool(parts) and parts[0] in PRODUCTION_ROOTS


def is_target_python(path: str) -> bool:
    """Return True if path points to a scoped production Python module."""
    rel = _relative_path(path)
    p = Path(rel)
    if p.suffix.lower() not in CHECKED_SUFFIXES or p.name == "__init__.py":
        return False
    if not _is_production_path(rel):
        return False
    return not any(part in _EXCLUDED_PARTS for part in p.parts)


def _load_git_blob(rel_path: str) -> str:
    """Read blob content from Git index for the relative path."""
    return subprocess.check_output(
        ["git", "cat-file", "-p", f":{rel_path}"],
        cwd=REPO,
        text=True,
        encoding="utf-8",
    )


def _load_source(path: str, staged: bool) -> tuple[str | None, Finding | None]:
    """Load source text from git index or disk, returning finding on failure."""
    rel = _relative_path(path)
    try:
        if staged:
            return _load_git_blob(rel), None
        p = Path(path)
        full = p if p.is_file() else (REPO / rel)
        return full.read_text(encoding="utf-8"), None
    except (subprocess.SubprocessError, OSError, UnicodeDecodeError) as exc:
        msg = f"unreadable source ({exc})"
        return None, Finding(rel, 1, "HNS010", msg)


def _scan_production_roots() -> list[str]:
    """Return every target module under the production roots."""
    collected: list[str] = []
    for root in sorted(PRODUCTION_ROOTS):
        target_dir = REPO / root
        if target_dir.is_dir():
            for candidate in target_dir.rglob("*.py"):
                rel = _relative_path(candidate)
                if is_target_python(rel):
                    collected.append(rel)
    return sorted(collected)


def _resolve_argument(raw: str) -> list[str]:
    """Return the target modules named by one CLI argument."""
    rel = _relative_path(raw)
    if not Path(rel).is_absolute() and not is_target_python(rel):
        return []
    candidate = Path(raw)
    if candidate.is_file() and candidate.suffix.lower() == ".py":
        return [raw]
    if not candidate.is_dir():
        return [rel]
    resolved: list[str] = []
    for child in candidate.rglob("*.py"):
        child_rel = _relative_path(child)
        if is_target_python(child_rel):
            resolved.append(child_rel)
    return resolved


def _files_to_check(paths: list[str]) -> list[str]:
    """Resolve CLI file or directory arguments into target Python files."""
    if not paths:
        return _scan_production_roots()
    return sorted({rel for raw in paths for rel in _resolve_argument(raw)})
