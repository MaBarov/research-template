"""Fail-closed reference check for agent instruction artifacts.

Thumbnail: Packages the instruction-reference gate and its resolution model.

Invariants & Expected State:
    - Provides ``check_instruction_refs`` for reference resolution against tracked trees.
    - Exported members adhere to the HNS073 contract.
"""

from framework.gates.instructions import check_instruction_refs

__all__ = ["check_instruction_refs"]
