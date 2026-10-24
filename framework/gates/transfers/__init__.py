"""Device transfer bottleneck detection package.

Thumbnail: Static AST rules and entry points detecting CPU<->GPU transfer bottlenecks.

Invariants & Expected State:
    Package holds at most 5 modules and __init__.py carries no executable code.
"""

from __future__ import annotations

from framework.gates.transfers.targets import Finding
from framework.gates.transfers.visitor import analyze_transfers

__all__ = ["Finding", "analyze_transfers"]
