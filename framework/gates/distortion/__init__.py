"""Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.

Thumbnail: Package facade exporting analyzer and finding structures for surrogate distortion checks.

Invariants & Expected State:
    Carries no executable code; re-exports public API symbols only.
    Module total spans under 30 lines.
"""

from __future__ import annotations

from framework.gates.distortion.targets import Finding
from framework.gates.distortion.visitor import analyze_distortion

__all__ = ["Finding", "analyze_distortion"]
