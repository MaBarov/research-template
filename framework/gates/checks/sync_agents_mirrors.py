#!/usr/bin/env python3
"""Governance mirror sync + check (non-breaking, additive).

Canonical governance lives in repo-root AGENTS.md (lines between the
`## Governance Sync` marker and end-of-file). CLAUDE.md and
.agents/AGENTS.md are generated mirrors. Without arguments this script
overwrites the mirror blocks; `--check` only verifies equality and exits
1 on divergence.

Non-breaking: never rewrites other content of either mirror; marker lines
are required in each mirror file before sync/check is attempted. If a
mirror lacks markers, --check reports and exits 1, sync inserts the block
at end of file.

Usage:
  python framework/gates/checks/sync_agents_mirrors.py [--check]

Invariants & Expected State:
    * Canonical text is the ``## Governance Sync`` block of repo-root
      ``AGENTS.md`` (marker line through end of file); ``CLAUDE.md`` and
      ``.agents/AGENTS.md`` are generated mirrors.
    * With no flag the mirrors are rewritten in place; ``--check`` writes
      nothing and exits 1 when any mirror diverges.
    * Only the marker block is rewritten: content before the marker in either
      mirror is never touched.
    * A missing canonical file exits 1; a canonical file without the marker
      exits 1 under ``--check`` and 0 for a plain (no-op) sync.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CANONICAL = REPO / "AGENTS.md"
MIRRORS = [REPO / "CLAUDE.md", REPO / ".agents" / "AGENTS.md"]
START_MARKER = "## Governance Sync"
HEADER = "<!-- MIRROR: generated from AGENTS.md by framework/gates/checks/sync_agents_mirrors.py -- do not edit; see AGENTS.md -->"


def canonical_block(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if START_MARKER not in text:
        return ""
    idx = text.index(START_MARKER)
    return text[idx:]


def mirror_block(text: str) -> str:
    if START_MARKER not in text:
        return ""
    idx = text.index(START_MARKER)
    return text[idx:]


def write_mirror(path: Path, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    existing = mirror_block(text)
    if existing:
        text = text.replace(existing, block)
    else:
        text = text.rstrip("\n") + "\n\n" + HEADER + "\n" + block
    path.write_text(text, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--check", action="store_true", help="verify mirrors match canonical; no writes"
    )
    return ap


def _sync_one_mirror(m: Path, block: str, check: bool) -> bool:
    """Sync or verify one mirror; True when it diverged from canonical."""
    if not m.exists():
        print(f"sync_agents_mirrors: missing mirror {m} (skipped)", file=sys.stderr)
        return False
    if mirror_block(m.read_text(encoding="utf-8")) == block:
        return False
    print(f"sync_agents_mirrors: MIRROR DIVERGENCE: {m}", file=sys.stderr)
    if not check:
        write_mirror(m, block)
        print(f"sync_agents_mirrors: synced {m}", file=sys.stderr)
    return True


def _report(check: bool, problems: int) -> int:
    """Print the run summary and return the process exit code."""
    if check:
        print(
            "sync_agents_mirrors: check %s"
            % ("PASS" if problems == 0 else f"FAIL ({problems} divergent)")
        )
        return 0 if problems == 0 else 1
    print("sync_agents_mirrors: synced mirrors (no-op unless diverged)")
    return 0


def main() -> int:
    args = _build_parser().parse_args()

    if not CANONICAL.exists():
        print(f"sync_agents_mirrors: canonical missing: {CANONICAL}", file=sys.stderr)
        return 1
    block = canonical_block(CANONICAL)
    if not block:
        print(
            "sync_agents_mirrors: AGENTS.md lacks '## Governance Sync' section; nothing to sync",
            file=sys.stderr,
        )
        return 1 if args.check else 0

    problems = 0
    for m in MIRRORS:
        problems += _sync_one_mirror(m, block, args.check)
    return _report(args.check, problems)


if __name__ == "__main__":
    raise SystemExit(main())
