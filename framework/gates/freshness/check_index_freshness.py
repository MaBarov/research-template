#!/usr/bin/env python3
"""Block a commit whose index disagrees with HEAD and the working tree.

A staged path is only trusted when the working tree corroborates it: an ``A``
must exist on disk, a ``D`` must be gone from disk, and an ``M``/``T``/``R``/
``C`` must also differ from ``HEAD`` in the working tree. A staged change with
no working-tree counterpart means the index was built from a different
revision than ``HEAD`` -- typically a private ``GIT_INDEX_FILE`` seeded by an
older ``read-tree``, or a leftover temporary index -- and committing it writes
a tree that silently deletes or reverts every path that index never learned
about. That is the 2026-09-25 incident: a feature commit whose tree reverted 12
of a peer's files and rewound 7 more, because the index came from a stale
temp directory.

Invariants & Expected State:
- The gate inspects the index actually being committed: it honours
  ``GIT_INDEX_FILE``, so a private-index commit is guarded exactly like an
  ordinary one, and the hook that calls it inherits the same view.
- A path is reported only when the working tree contradicts the index. Edits,
  regenerated ledgers and ``git rm`` all leave a working-tree counterpart, so
  an ordinary commit is always clean; a stale index never is.
- The rule cannot distinguish one legitimate shape -- ``git rm --cached``,
  which untracks a path while deliberately keeping it on disk -- and there is
  no bypass: such a commit is refused, so untracking deliberately means
  deleting the file as well.
- An unborn ``HEAD`` is skipped: no revision exists to drift from.

Usage::

  python framework/gates/freshness/check_index_freshness.py --strict
  python framework/gates/freshness/check_index_freshness.py --json PATH

Exit codes: 0 clean (or findings without ``--strict``); 1 findings with
``--strict``; 2 usage or environment error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
STAGED_CODE = "IDX001"
CORROBORATED_STATUSES = frozenset({"M", "T", "R", "C"})
REMEDY = (
    "re-stage the path from the working tree, or delete the file to untrack "
    "deliberately"
)


@dataclass(frozen=True)
class Finding:
    """One staged path the working tree does not corroborate."""

    path: str
    code: str
    message: str

    def format(self) -> str:
        return f"{self.code}: {self.path}: {self.message}"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def _git(*args: str) -> tuple[int, str]:
    """Run one git command in the repository root; return (returncode, stdout)."""
    proc = subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stdout


def _head_exists() -> bool:
    """Return True when HEAD resolves to a commit, so drift is even possible."""
    return _git("rev-parse", "--verify", "--quiet", "HEAD^{commit}")[0] == 0


def _staged_statuses() -> dict[str, str]:
    """Map each staged path to its one-letter status against HEAD."""
    code, out = _git("diff", "--cached", "--name-status", "-M", "HEAD")
    if code != 0:
        return {}
    staged: dict[str, str] = {}
    for line in out.splitlines():
        fields = line.split("\t")
        if len(fields) >= 2 and fields[-1]:
            staged[fields[-1]] = fields[0][:1]
    return staged


def _worktree_statuses() -> set[str]:
    """Return the paths that differ from HEAD in the working tree."""
    code, out = _git("diff", "--name-only", "HEAD")
    return set(out.splitlines()) if code == 0 else set()


def _contradiction(path: str, status: str, worktree: set[str]) -> str | None:
    """Return why the working tree contradicts `path`, or None when it agrees."""
    if status == "A":
        if not (REPO / path).exists():
            return "staged as added but absent from the working tree"
        return None
    if status == "D":
        if (REPO / path).exists():
            return "staged as deleted but still present in the working tree"
        return None
    if status in CORROBORATED_STATUSES and path not in worktree:
        return "staged as changed but identical to HEAD in the working tree"
    return None


def collect_findings() -> list[Finding]:
    """Return one finding per staged path the working tree does not corroborate."""
    worktree = _worktree_statuses()
    findings: list[Finding] = []
    for path, status in sorted(_staged_statuses().items()):
        reason = _contradiction(path, status, worktree)
        if reason is not None:
            findings.append(Finding(path=path, code=STAGED_CODE, message=reason))
    return findings


def _emit(findings: list[Finding], as_json: str | None) -> None:
    """Print findings, either as a JSON report or as human-readable lines."""
    if as_json:
        Path(as_json).write_text(
            json.dumps([f.as_dict() for f in findings], indent=2) + "\n",
            encoding="utf-8",
        )
    for finding in findings:
        print(f"[index-freshness] {finding.format()}", file=sys.stderr)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description="Index freshness gate.")
    parser.add_argument("--strict", action="store_true", help="exit 1 on findings")
    parser.add_argument("--json", default=None, help="write a JSON report here")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the gate; return the process exit code."""
    args = _parse_args(argv)
    if not _head_exists():
        print("[index-freshness] no HEAD yet; nothing to drift from")
        return 0
    findings = collect_findings()
    _emit(findings, args.json)
    if not findings:
        print("[index-freshness] checked, 0 finding(s)")
        return 0
    print(
        f"[index-freshness] BLOCKED: {len(findings)} staged path(s) contradict the "
        f"working tree; {REMEDY}",
        file=sys.stderr,
    )
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
