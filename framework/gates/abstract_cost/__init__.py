"""Advisory abstract-cost gate package.

Thumbnail: Static HNS095-HNS099 detectors for cost classes that no correctness gate owns.

Invariants & Expected State:
    Package holds at most 5 modules and __init__.py carries no executable code.
    The gate is advisory: findings are reported, never blocking a commit.
"""

from __future__ import annotations

from framework.gates.abstract_cost.visitor import analyze_abstract_cost
from framework.gates.advisory.model import Finding

__all__ = ["Finding", "analyze_abstract_cost"]
