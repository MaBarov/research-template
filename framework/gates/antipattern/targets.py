"""Scope constants, findings and target-file resolution.

Invariants & Expected State:
    * Only first-party production roots (``harness.PRODUCTION_ROOTS``) are ever
      selected; a path outside them is dropped, not reported.
    * ``.py``, ``.sh`` and ``.sbatch`` files are checked; a directory argument
      is expanded recursively and the result is sorted and de-duplicated.
    * ``--mode staged`` reads module text from the Git index (``git show
      :<path>``), so unstaged edits cannot change the decision.
    * A file that cannot be read becomes an ``HNS010`` finding: unreadable
      source is never silently treated as empty and clean.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from framework import harness

REPO = Path(__file__).resolve().parents[3]

PRODUCTION_ROOTS = set(harness.PRODUCTION_ROOTS)

SHELL_SUFFIXES = {".sbatch", ".sh"}

CHECKED_SUFFIXES = {".py", *SHELL_SUFFIXES}


@dataclass(frozen=True)
class Finding:
    """One source-level anti-pattern finding."""

    path: str
    line: int
    code: str
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.code} {self.message}"


def _relative_path(path: str | Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(REPO)
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


def _is_production_path(path: str) -> bool:
    parts = Path(path).parts
    return bool(parts) and parts[0] in PRODUCTION_ROOTS


def _read_staged(path: str) -> str:
    result = subprocess.run(
        ["git", "show", f":{path}"],
        cwd=REPO,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"cannot read staged file {path}: {result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout.decode("utf-8")


def _checked_directory(directory: Path) -> list[str]:
    return [
        p.relative_to(REPO).as_posix()
        for p in sorted(directory.rglob("*"))
        if p.is_file() and p.suffix.lower() in CHECKED_SUFFIXES
    ]


def _files_to_check(paths: list[str]) -> list[str]:
    if paths:
        result: list[str] = []
        for path in paths:
            relative = _relative_path(path)
            if not _is_production_path(relative):
                continue
            candidate = REPO / relative
            if candidate.is_dir():
                result.extend(_checked_directory(candidate))
            else:
                result.append(relative)
        return sorted(dict.fromkeys(result))
    result = []
    for root in sorted(PRODUCTION_ROOTS):
        directory = REPO / root
        if directory.exists():
            result.extend(_checked_directory(directory))
    return sorted(result)


def _load_source(path: str, staged: bool) -> tuple[str, Finding | None]:
    """Return ``(source, finding)``; the finding explains an unreadable file."""

    try:
        source = (
            _read_staged(path) if staged else (REPO / path).read_text(encoding="utf-8")
        )
    except (OSError, RuntimeError, UnicodeError) as error:
        return "", Finding(path, 1, "HNS010", f"cannot inspect source: {error}")
    return source, None
