"""Freshness and ref-provenance gates.

Thumbnail: Packages freshness checks and reference-transaction ref guards.

Invariants & Expected State:
    - Provides ``ref_guard`` and index freshness checks.
    - Exported members adhere to repository freshness invariants.
"""

from framework.gates.freshness import ref_guard

__all__ = ["ref_guard"]
