"""In-loop memory bottleneck checks and their literal-shape helpers.

Thumbnail: The five HNS083-HNS086 checks over one store, call or accumulation site.

Invariants & Expected State:
    Loop context is the gate: every rule needs an enclosing loop or comprehension, so a
    hoisted allocation or one single post-loop concatenation stays silent.
    HNS083 (collection store of an un-detached tensor), HNS085 (augmented accumulation)
    and HNS086 (invariant-shape allocation) all read the same passed-in evidence scope
    and never mutate it; each honours its documented safe replacement - ``.detach()``/
    ``.item()``/``.tolist()``/``.numpy()``/``.cpu()``/``float()``/``int()``/``bool()`` for
    retention and accumulation, a preallocated buffer for the growth and allocation
    shapes.
    HNS084 and HNS086 are shape-mechanical: a concatenation that reads its own target is
    provably growing it, and a literal shape cannot change across iterations. A literal
    shape whose element count is zero is exempt, because a placeholder that requests no
    storage churns nothing, and a buffer the loop returns or yields is the deliverable
    rather than churn.
    Messages follow the ``<problem>; <safe replacement>`` shape.
"""

from __future__ import annotations

import ast

from .evidence import (
    _ALLOCATION_ATTRS,
    _EMPTY_SCOPE,
    _FUNCTION_MODULES,
    _GROWTH_ATTRS,
    _RETENTION_INDEX,
    _SHAPE_KEYWORDS,
    HNS083,
    HNS084,
    HNS085,
    HNS086,
    MSG_HNS083,
    MSG_HNS084,
    MSG_HNS085,
    MSG_HNS086,
    Scope,
    _call_name,
    _container_key,
    _root_name,
    has_tensor_evidence,
    is_released,
    is_scalarized,
)


def check_collection_retention(
    node: ast.Call, in_loop: bool, scope: Scope = _EMPTY_SCOPE
) -> tuple[str, str] | None:
    """Return HNS083 for an in-loop collection method storing an un-detached tensor.

    Only ``list.append``/``list.insert``/``set.add`` shapes count, on a receiver
    that is not a function module; a value already wrapped in a release call
    (``.detach()``/``.item()``/``.tolist()``/``.numpy()``/``.cpu()``/``float()``/
    ``int()``/``bool()``) is the documented safe form. What stays out of reach is a
    tensor handed to a helper that stores it internally: the store happens in
    another frame and no single-pass walk can attribute it here.
    """
    if not in_loop or scope.nograd or not isinstance(node.func, ast.Attribute):
        return None
    index = _RETENTION_INDEX.get(node.func.attr)
    if index is None or len(node.args) <= index:
        return None
    receiver = node.func.value
    if _root_name(receiver) in _FUNCTION_MODULES:
        return None
    key = _container_key(receiver)
    if key and key in scope.scalar_names:
        return None
    stored = node.args[index]
    if is_released(stored):
        return None
    if not has_tensor_evidence(stored, scope):
        return None
    return HNS083, MSG_HNS083


def check_subscript_store(
    value: ast.AST, container: ast.AST, in_loop: bool, scope: Scope = _EMPTY_SCOPE
) -> tuple[str, str] | None:
    """Return HNS083 for an in-loop ``mapping[key] = <un-detached tensor>``.

    A store into a mapping outlives the iteration exactly like an append, so it
    needs the same graph-carrying evidence and honours the same release-wrapper and
    non-tensor annotation exemptions. A container this function built with a call,
    attribute or subscript is exempt: the machine cannot tell a growing mapping
    from a preallocated tensor buffer, and writing into a buffer is the documented
    fix for HNS086 rather than a retention.
    """
    if not in_loop or scope.nograd or is_released(value):
        return None
    key = _container_key(container)
    if key and (key in scope.scalar_names or key in scope.opaque_names):
        return None
    if not has_tensor_evidence(value, scope):
        return None
    return HNS083, MSG_HNS083


def check_accumulation(
    node: ast.AugAssign, in_loop: bool, scope: Scope = _EMPTY_SCOPE
) -> tuple[str, str] | None:
    """Return HNS085 for an in-loop augmented accumulation of an un-detached tensor.

    Only ``+=`` counts and only with graph-carrying evidence on the right-hand
    side, so ``count += 1``, ``n += len(items)``, ``total += torch.randn(1)`` (a
    fresh leaf replaces the old value instead of chaining to it) and an annotated
    ``running: float`` are counters rather than graphs. Any ``.detach()``/
    ``.item()``/``.float()``/``.int()`` wrapper on the right-hand side is the
    documented safe form. A helper that returns a fresh un-detached tensor per step
    stays out of reach and silent.
    """
    if not in_loop or scope.nograd or not isinstance(node.op, ast.Add):
        return None
    if isinstance(node.target, ast.Name) and node.target.id in scope.scalar_names:
        return None
    if is_scalarized(node.value):
        return None
    if not has_tensor_evidence(node.value, scope):
        return None
    return HNS085, MSG_HNS085


def check_dynamic_growth(
    value: ast.AST, in_loop: bool, target_names: frozenset[str] = frozenset()
) -> tuple[str, str] | None:
    """Return HNS084 for an in-loop ``torch.cat``/``torch.stack`` that grows its target.

    Requiring the assigned name to appear among the call arguments separates real
    growth (``history = torch.cat([history, chunk])``) from a fixed-shape join. A
    helper that grows a buffer internally is out of reach and stays silent.
    """
    if not in_loop or not target_names or not isinstance(value, ast.Call):
        return None
    if (
        not isinstance(value.func, ast.Attribute)
        or value.func.attr not in _GROWTH_ATTRS
    ):
        return None
    if _root_name(value.func.value) != "torch":
        return None
    argument_names = {
        child.id for child in ast.walk(value) if isinstance(child, ast.Name)
    }
    if not target_names & argument_names:
        return None
    return HNS084, MSG_HNS084


def _is_literal_shape(node: ast.AST) -> bool:
    """Return True when a shape argument is a constant or a constant container."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _is_literal_shape(node.operand)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_literal_shape(element) for element in node.elts)
    return False


def _literal_ints(node: ast.AST) -> list[int] | None:
    """Return the integer components of a literal shape, None when not literal ints."""
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, int) else None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _literal_ints(node.operand)
        if inner is None or len(inner) != 1:
            return None
        return [-inner[0] if isinstance(node.op, ast.USub) else inner[0]]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        collected: list[int] = []
        for element in node.elts:
            inner = _literal_ints(element)
            if inner is None:
                return None
            collected.extend(inner)
        return collected
    return None


def _shape_arguments(node: ast.Call) -> list[ast.expr]:
    """Return the arguments that describe an allocation's element count.

    ``torch.full`` takes its fill value as a second positional argument and that
    value says nothing about the shape, so only its first argument counts.
    """
    keywords = [
        keyword.value for keyword in node.keywords if keyword.arg in _SHAPE_KEYWORDS
    ]
    if keywords:
        return keywords
    return list(node.args[:1]) if _call_name(node.func) == "full" else list(node.args)


def _is_empty_shape(node: ast.Call) -> bool:
    """Return True when a literal shape provably asks for zero elements."""
    counts = [_literal_ints(part) for part in _shape_arguments(node)]
    if not counts:
        return False
    product = 1
    for count in counts:
        if count is None:
            return False
        for value in count:
            product *= value
    return product == 0


def _has_literal_shape(node: ast.Call) -> bool:
    """Return True when every shape argument is a literal demanding real storage.

    A zero-element literal shape is exempt: it requests no storage, so repeating it
    cannot fragment the allocator. That keeps the placeholder rows of a ``finish()``
    comprehension - ``torch.empty(0, device=...)`` for the timesteps a run never
    reached - silent, while every positive literal product still fires.
    """
    shape_nodes = list(node.args) + [
        keyword.value for keyword in node.keywords if keyword.arg in _SHAPE_KEYWORDS
    ]
    if not shape_nodes or not all(_is_literal_shape(part) for part in shape_nodes):
        return False
    return not _is_empty_shape(node)


def check_buffer_allocation(
    node: ast.Call,
    in_loop: bool,
    escaping_ids: frozenset[int] = frozenset(),
    exempt_ids: frozenset[int] = frozenset(),
) -> tuple[str, str] | None:
    """Return HNS086 for an in-loop invariant-shape ``torch.zeros/ones/empty/full``.

    Every shape argument must be a literal, so a buffer sized from the iteration is
    silent: only a shape that cannot change is churn. A literal shape of zero
    elements is exempt as well, because a placeholder that requests no storage churns
    nothing. A buffer the loop returns or yields is the deliverable rather than churn,
    and the ``*_like`` variants are out of scope because they already carry a source
    tensor's shape.
    """
    if not in_loop or id(node) in exempt_ids or id(node) in escaping_ids:
        return None
    if (
        not isinstance(node.func, ast.Attribute)
        or node.func.attr not in _ALLOCATION_ATTRS
    ):
        return None
    if _root_name(node.func.value) != "torch":
        return None
    if not _has_literal_shape(node):
        return None
    return HNS086, MSG_HNS086
