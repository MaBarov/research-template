"""Accelerator memory bottleneck detection package.

Thumbnail: Static AST rules and entry points detecting in-loop memory retention bottlenecks.

Invariants & Expected State:
    Package holds at most 5 modules and __init__.py carries no executable code.
"""

from __future__ import annotations

from framework.gates.memory.targets import Finding
from framework.gates.memory.visitor import analyze_memory

__all__ = ["Finding", "analyze_memory"]
