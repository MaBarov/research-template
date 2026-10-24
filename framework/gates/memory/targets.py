"""Shared loader facade for the accelerator memory bottleneck gate.

Thumbnail: Re-export facade over the transfer gate's finding and source loaders.

Invariants & Expected State:
    Finding, REPO and target path resolution are imported from the transfer
    gate: both gates walk the same static roots through the same accessors.
    _load_source binds read_staged from framework.gates.static.sources, failing
    closed with HNS010 on missing or unreadable staged files.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework import harness
from framework.gates.static.sources import read_staged, relative_path
from framework.gates.transfers.targets import (
    Finding,
    _files_to_check,
)

REPO = harness.REPO


def _read_staged(path: str) -> str:
    """Read staged blob from repository (allows test redirection of REPO)."""
    return read_staged(path, repo=REPO)


def _load_source(path: str, staged: bool) -> tuple[str | None, Finding | None]:
    """Load source text from git index or disk, returning finding on failure."""
    rel = relative_path(path)
    try:
        if staged:
            return _read_staged(rel), None
        p = Path(path)
        full = p if p.is_file() else (REPO / rel)
        return full.read_text(encoding="utf-8"), None
    except Exception as exc:  # noqa: BLE001
        msg = f"unreadable source ({exc})"
        return None, Finding(rel, 1, "HNS010", msg)


__all__ = ["REPO", "Finding", "_files_to_check", "_load_source"]
