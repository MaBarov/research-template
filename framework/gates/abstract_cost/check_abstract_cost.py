"""Advisory abstract-cost checker: HNS095-HNS099 over staged or tree sources.

Thumbnail: CLI wrapper that runs the abstract-cost analyzer over a chosen population.

Invariants & Expected State:
    Staged mode reads Git-index blobs, so an unstaged working-tree edit cannot
    change the verdict of a staged path; an unreadable blob becomes HNS010.
    Advisory is the default: findings print, exit stays 0. --strict is the audit
    switch and exits 1, which is what a promotion to blocking would call.
    --report writes the complete finding list as JSON, evidence included.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework import harness
from framework.gates.abstract_cost.visitor import analyze_abstract_cost
from framework.gates.advisory.model import run

SCHEMA = f"{harness.SLUG}.abstract-cost.v1"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point executing the abstract-cost audit."""
    return run(argv, analyze_abstract_cost, "check_abstract_cost", __doc__ or "")


if __name__ == "__main__":
    sys.exit(main())
