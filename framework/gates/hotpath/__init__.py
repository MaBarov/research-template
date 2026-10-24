"""Advisory GPU/CPU hot-path detection package.

Thumbnail: Static HNS089-HNS094 detectors for avoidable device churn and step stalls.

Invariants & Expected State:
    Package holds at most 5 modules and __init__.py carries no executable code.
    The gate is advisory: the hook reports findings and never blocks a commit.
"""

from __future__ import annotations

from framework.gates.advisory.model import Finding
from framework.gates.hotpath.visitor import analyze_hotpath

__all__ = ["Finding", "analyze_hotpath"]
