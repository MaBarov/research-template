"""Device provenance inference for tensor expressions.

Thumbnail: Infers host, device or unknown placement for an expression from local syntax.

Invariants & Expected State:
    Only provable placement is reported: an attribute or an unmodelled call is
    UNKNOWN and never guessed.
    Device-preserving views, dtype-only casts and ``.detach`` keep the receiver's
    placement; a torch factory without a device keyword is HOST, because that is
    where torch builds it.
    A locally defined function's return placement counts as provable when every
    return agrees: ``def _host():\n    return torch.zeros(2)`` returns HOST, so
    calling it into device arithmetic is caught. One UNKNOWN return removes the
    entry rather than guessing.
    Inference is pure: it reads the node and the two maps it is given and mutates
    neither.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType

from framework.gates.transfers.rules import (
    _HOST_PASS_METHODS,
    _TORCH_HOST_FACTORIES,
    _is_cpu_device_node,
    _is_dtype_node,
    _is_torch_root,
)

HOST = "host"
DEVICE = "device"
UNKNOWN = "unknown"

_NO_RETURNS: Mapping[str, str] = MappingProxyType({})
_PRESERVING_METHODS = frozenset(_HOST_PASS_METHODS - {"cpu"}) | {"abs", "bool"}
_LIKE_FACTORIES = frozenset(
    {
        "zeros_like",
        "ones_like",
        "empty_like",
        "full_like",
        "rand_like",
        "randn_like",
    }
)
_ALIAS_FACTORIES = frozenset({"as_tensor", "asarray"})
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def module_bindings(body: Sequence[ast.stmt]) -> dict[str, str]:
    """Return placement of the module-scope names assigned by simple literals."""
    bindings: dict[str, str] = {}
    for statement in body:
        targets, value = _simple_assignment(statement)
        if value is None:
            continue
        placement = provenance_of(value, bindings)
        bindings.update({target: placement for target in targets})
    return bindings


def function_returns(
    body: Sequence[ast.stmt], names: Mapping[str, str]
) -> dict[str, str]:
    """Return placement of each top-level function whose returns all agree."""
    returns: dict[str, str] = {}
    for statement in body:
        if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        placement = _return_placement(statement, names)
        if placement != UNKNOWN:
            returns[statement.name] = placement
    return returns


def provenance_of(
    node: ast.AST,
    names: Mapping[str, str],
    returns: Mapping[str, str] = _NO_RETURNS,
) -> str:
    """Return the provable placement of one expression, UNKNOWN when not provable."""
    node = _unwrap_subscripts(node)
    if isinstance(node, ast.Name):
        return names.get(node.id, UNKNOWN)
    if isinstance(node, ast.Call):
        return _call_provenance(node, names, returns)
    if isinstance(node, ast.BinOp):
        return _combined(node.left, node.right, names, returns)
    if isinstance(node, ast.UnaryOp):
        return provenance_of(node.operand, names, returns)
    return UNKNOWN


def _simple_assignment(statement: ast.stmt) -> tuple[list[str], ast.AST | None]:
    """Return simple-name targets and the value of one assignment statement."""
    value: ast.AST | None
    if isinstance(statement, ast.Assign):
        targets, value = statement.targets, statement.value
    elif isinstance(statement, ast.AnnAssign):
        targets, value = [statement.target], statement.value
    else:
        return [], None
    names = [target.id for target in targets if isinstance(target, ast.Name)]
    return names, value


def _return_placement(
    function: ast.FunctionDef | ast.AsyncFunctionDef, names: Mapping[str, str]
) -> str:
    """Return the one placement every return agrees on, UNKNOWN otherwise."""
    placements = {
        provenance_of(value, names) for value in _return_values(function.body)
    }
    if len(placements) != 1:
        return UNKNOWN
    return placements.pop()


def _return_values(body: list[ast.stmt]) -> Iterable[ast.AST]:
    """Yield return values of one function body, never descending into scopes."""
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        if isinstance(node, _NESTED_SCOPES):
            continue
        if isinstance(node, ast.Return) and node.value is not None:
            yield node.value
        stack.extend(ast.iter_child_nodes(node))


def _unwrap_subscripts(node: ast.AST) -> ast.AST:
    """An index of a tensor is a tensor on the same device as its base."""
    while isinstance(node, ast.Subscript):
        node = node.value
    return node


def _combined(
    left: ast.AST,
    right: ast.AST,
    names: Mapping[str, str],
    returns: Mapping[str, str],
) -> str:
    """One placement survives a binary op only when both operands share it."""
    placements = {
        provenance_of(left, names, returns),
        provenance_of(right, names, returns),
    }
    if len(placements) == 1:
        return placements.pop()
    return UNKNOWN


def _call_provenance(
    node: ast.Call, names: Mapping[str, str], returns: Mapping[str, str]
) -> str:
    """Placement of a call: local function, transfer, cast, factory or view."""
    function = node.func
    if isinstance(function, ast.Name):
        return returns.get(function.id, UNKNOWN)
    if not isinstance(function, ast.Attribute):
        return UNKNOWN
    attribute = function.attr
    if attribute == "cpu":
        return HOST
    if attribute == "cuda":
        return DEVICE
    if attribute == "to":
        return _to_provenance(node, function, names, returns)
    if _is_torch_root(function.value):
        return _torch_provenance(node, attribute, names, returns)
    if attribute in _PRESERVING_METHODS:
        return provenance_of(function.value, names, returns)
    return UNKNOWN


def _torch_provenance(
    node: ast.Call,
    attribute: str,
    names: Mapping[str, str],
    returns: Mapping[str, str],
) -> str:
    """Placement of a ``torch.*`` factory, join helper or alias constructor."""
    placement = _device_keyword(node)
    if attribute in _TORCH_HOST_FACTORIES:
        return placement or HOST
    if attribute in _LIKE_FACTORIES or attribute in _ALIAS_FACTORIES:
        return placement or _first_argument(node, names, returns)
    return UNKNOWN


def _device_keyword(node: ast.Call) -> str | None:
    """Placement declared by a ``device=`` keyword, None when the call has none."""
    for keyword in node.keywords:
        if keyword.arg != "device":
            continue
        return HOST if _is_cpu_device_node(keyword.value) else DEVICE
    return None


def _first_argument(
    node: ast.Call, names: Mapping[str, str], returns: Mapping[str, str]
) -> str:
    """Placement of a call's first argument; the empty call is UNKNOWN."""
    if not node.args:
        return UNKNOWN
    return provenance_of(node.args[0], names, returns)


def _to_provenance(
    node: ast.Call,
    function: ast.Attribute,
    names: Mapping[str, str],
    returns: Mapping[str, str],
) -> str:
    """Placement of ``.to(...)``: a device argument moves, a dtype keeps."""
    receiver = provenance_of(function.value, names, returns)
    declared = _device_keyword(node)
    if declared is not None:
        return declared
    moves = [argument for argument in node.args if not _is_dtype_node(argument)]
    if not moves:
        return receiver
    return HOST if _is_cpu_device_node(moves[0]) else DEVICE
