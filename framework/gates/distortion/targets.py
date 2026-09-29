"""Target definitions and source loaders for the surrogate distortion gate.

Thumbnail: Finding dataclass and fail-closed target loaders for distortion analysis.

Invariants & Expected State:
    Finding objects are immutable dataclasses with compiler-style formatting.
    Target predicates identify production Python sources and skip test trees.
    HNS045 vocabulary constants default to empty or generic, project-neutral hints.
    _load_source fails closed with HNS010 on missing or unreadable staged files.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from framework import harness
from framework.gates.antipattern.targets import _relative_path

REPO = Path(__file__).resolve().parents[3]
PRODUCTION_ROOTS = set(harness.DISTORTION_ROOTS)
CHECKED_SUFFIXES = {".py"}
_EXCLUDED_PARTS = {"tests", "third_party", ".git", ".venv", "venv", "__pycache__"}

# HNS045 vocabulary: empty exemption set plus generic member/estimate name hints.
# A project opts its own per-member API in by assigning POOLING_EXEMPT_CALLS and
# narrows the hints to its own naming scheme.
POOLING_EXEMPT_CALLS: frozenset[str] = frozenset()
MEMBER_NAME_HINTS: tuple[str, ...] = ("module", "group", "layer", "shard")
POOLED_ESTIMATE_HINTS: tuple[str, ...] = ("basis", "pooled", "estimate", "mean")


@dataclass(frozen=True)
class Finding:
    """One anti-pattern finding with file path, line number, code, and message."""

    path: str
    line: int
    code: str
    message: str

    def format(self) -> str:
        """Format finding for standard compiler-style CLI diagnostic output."""
        return f"{self.path}:{self.line}: {self.code} {self.message}"


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


def _read_staged(path: str) -> str:
    """Read blob content from Git index for path, raising RuntimeError on error."""
    rel = _relative_path(path)
    result = subprocess.run(
        ["git", "show", f":{rel}"],
        cwd=REPO,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        err = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"cannot read staged file {path}: {err}")
    return result.stdout.decode("utf-8")


def _checked_directory(directory: Path) -> list[str]:
    """Return relative paths for all scoped Python files in directory."""
    return [
        p.relative_to(REPO).as_posix()
        for p in sorted(directory.rglob("*.py"))
        if is_target_python(str(p))
    ]


def _files_to_check(paths: list[str]) -> list[str]:
    """Collect unique scoped Python target paths from explicit arguments or tree."""
    if paths:
        result: list[str] = []
        for path in paths:
            p = Path(path)
            if p.is_file() and p.suffix.lower() == ".py":
                result.append(path)
                continue
            rel = _relative_path(path)
            candidate = REPO / rel
            if candidate.is_dir():
                result.extend(_checked_directory(candidate))
            elif is_target_python(rel):
                result.append(rel)
        return sorted(dict.fromkeys(result))
    result = []
    for root in sorted(PRODUCTION_ROOTS):
        d = REPO / root
        if d.is_dir():
            result.extend(_checked_directory(d))
    return sorted(dict.fromkeys(result))


def _load_source(path: str, staged: bool) -> tuple[str, Finding | None]:
    """Return (source, finding); the finding explains an unreadable file."""
    try:
        if staged:
            source = _read_staged(path)
        else:
            p = Path(path)
            full = p if p.is_file() else (REPO / path)
            source = full.read_text(encoding="utf-8")
    except (OSError, RuntimeError, UnicodeError) as error:
        return "", Finding(path, 1, "HNS010", f"cannot inspect source: {error}")
    return source, None
