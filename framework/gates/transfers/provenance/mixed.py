"""Mixed-device operand detection for tensor expressions.

Thumbnail: Flags expressions that provably combine a host tensor with a device tensor.

Invariants & Expected State:
    A finding needs both placements proved inside one expression: one UNKNOWN
    operand suppresses it, so the rule never guesses a device.
    Only operators with a same-device contract are inspected - arithmetic,
    comparisons, torch joins and ``where``, and the arithmetic methods.
    ``copy_`` is excluded because torch documents it as a cross-device copy, and
    ``.to`` moves operands itself; neither raises the mismatch error.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from framework.gates.transfers.provenance.infer import (
    DEVICE,
    HOST,
    provenance_of,
)
from framework.gates.transfers.rules import (
    _AGGREGATE_ATTRS,
    HNS088,
    MSG_HNS088,
    _is_torch_root,
)

_NO_RETURNS: Mapping[str, str] = MappingProxyType({})
_MIXING_METHODS = frozenset(
    {
        "add",
        "add_",
        "addcmul",
        "addcmul_",
        "div",
        "div_",
        "lerp",
        "lerp_",
        "masked_fill",
        "masked_fill_",
        "mul",
        "mul_",
        "pow",
        "pow_",
        "sub",
        "sub_",
    }
)


def mixing_finding(
    node: ast.AST,
    names: Mapping[str, str],
    returns: Mapping[str, str] = _NO_RETURNS,
) -> tuple[str, str] | None:
    """Return the HNS088 finding for one expression, None when it is safe."""
    operands = _operands(node)
    if not operands:
        return None
    placements = {provenance_of(operand, names, returns) for operand in operands}
    if HOST in placements and DEVICE in placements:
        return HNS088, MSG_HNS088
    return None


def _operands(node: ast.AST) -> Sequence[ast.AST]:
    """Return the operand expressions of a same-device contract, if any."""
    if isinstance(node, ast.BinOp):
        return [node.left, node.right]
    if isinstance(node, ast.Compare):
        return [node.left, *node.comparators]
    if isinstance(node, ast.AugAssign):
        return [node.target, node.value]
    if isinstance(node, ast.Call):
        return _call_operands(node)
    return []


def _call_operands(node: ast.Call) -> Sequence[ast.AST]:
    """Operands of a torch join/where or an arithmetic tensor method call."""
    if not isinstance(node.func, ast.Attribute):
        return []
    attribute = node.func.attr
    if _is_torch_root(node.func.value) and attribute in _AGGREGATE_ATTRS:
        return _joined(node.args)
    if _is_torch_root(node.func.value) and attribute == "where":
        return node.args
    if attribute in _MIXING_METHODS:
        return [node.func.value, *node.args]
    return []


def _joined(arguments: Sequence[ast.AST]) -> Sequence[ast.AST]:
    """Elements of a literal sequence argument; a bare name cannot be resolved."""
    if not arguments:
        return []
    sequence = arguments[0]
    if isinstance(sequence, (ast.List, ast.Tuple)):
        return sequence.elts
    return []
