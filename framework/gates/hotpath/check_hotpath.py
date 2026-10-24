"""Advisory hot-path checker: HNS089-HNS094 over staged or tree sources.

Thumbnail: Advisory CLI scanning staged or tree sources for device-churn rules.

Invariants & Expected State:
    --staged reads blobs from the Git index so unstaged edits cannot affect the
    verdict, and an unreadable blob is a fail-closed HNS010 finding.
    Exit is 0 unless --strict is given and findings exist; the hook runs it
    advisory, printing the same lines as a WARN.
    --report always writes the full finding list, one object per finding.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework import harness
from framework.gates.advisory.model import run
from framework.gates.hotpath.visitor import analyze_hotpath

SCHEMA = f"{harness.SLUG}.hotpath.v1"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point executing the hot-path audit."""
    return run(argv, analyze_hotpath, "check_hotpath", __doc__ or "")


if __name__ == "__main__":
    sys.exit(main())
