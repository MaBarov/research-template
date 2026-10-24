"""Rendering, machine reports and census aggregation of the static-type gate.

Thumbnail: finding rendering, JSON reports, and per-tree census aggregation.

Invariants & Expected State:
    * Printed findings are capped at ``MAX_PRINTED`` and the cap is always disclosed,
      so a hundred-finding file cannot hide behind a truncated log.
    * The JSON report rows carry exactly ``path``, ``line``, ``code`` and ``message``
      and are written in the order the checker reported them.
    * Census rows count findings per typed root and name the five worst files.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework.gates.typecheck.runner import Finding

MAX_PRINTED = 40


def print_findings(
    findings: Sequence[Finding],
    stream: TextIO = sys.stderr,
    limit: int = MAX_PRINTED,
) -> None:
    """Print findings (capped) and disclose how many were left out."""
    for finding in findings[:limit]:
        print(f"[check_types] {finding.format()}", file=stream)
    hidden = len(findings) - limit
    if hidden > 0:
        print(f"[check_types] ... {hidden} more finding(s)", file=stream)


def write_report(path: Path, findings: Sequence[Finding]) -> None:
    """Write the machine-readable JSON report of one run."""
    payload = [
        {
            "path": finding.path,
            "line": finding.line,
            "code": finding.code,
            "message": finding.message,
        }
        for finding in findings
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def per_tree(findings: Sequence[Finding]) -> list[tuple[str, int]]:
    """Return ``(tree, count)`` rows for the typed roots, heaviest first."""
    counts = Counter(finding.path.split("/", 1)[0] for finding in findings)
    return sorted(counts.items(), key=lambda row: (-row[1], row[0]))


def census_lines(findings: Sequence[Finding], checked: int) -> list[str]:
    """Return the census summary: totals, per-tree rows and the worst files."""
    lines = [f"[check_types] census: {checked} module(s), {len(findings)} finding(s)"]
    lines.extend(
        f"[check_types]   {tree}: {count}" for tree, count in per_tree(findings)
    )
    worst = Counter(finding.path for finding in findings).most_common(5)
    lines.extend(f"[check_types]   top {path}: {count}" for path, count in worst)
    return lines
