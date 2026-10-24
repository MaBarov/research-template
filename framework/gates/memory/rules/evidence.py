"""Tensor evidence, scope state and AST predicates for the memory bottleneck rules.

Thumbnail: Namespace probes, scope records and tensor-evidence predicates the in-loop memory rules read.

Invariants & Expected State:
    Every predicate is pure over the ast nodes it receives and never mutates the tree.
    Tensor evidence is mechanical and graph-aware, never nominal: HNS083 and HNS085 fire
    only when an expression carries a call that can attach an autograd graph - an inline
    ``torch.*``/``torch.linalg.*``/``F.*`` transform, a local this function bound from
    one, or a call of a local that already holds a torch-built callable. A bare name and
    a tensor-ish name are never evidence.
    Creation ops are deliberately not evidence: ``torch.zeros/ones/empty/full/randn/rand/
    arange/eye/`` ``*_like``/``tensor``/``from_numpy`` build leaves whose ``grad_fn`` is
    None, so a collection of them can never retain a backward graph, and the same holds
    for the boolean, index and shape queries (``isfinite``/``argmin``/``all``/``numel``)
    that keep the per-seam buffer-setup loops and finite-flag lists of this tree silent.
    ``as_tensor`` stays evidence for the opposite reason: it aliases a tensor argument
    and keeps that argument's graph.
    Non-tensor proof also exempts an enclosing ``torch.no_grad()``/``inference_mode()``
    block, an annotation naming only scalar types (``list[float]``, ``total: int``), and
    a container built by a call or attribute - the state each is read from lives in the
    passed-in ``Scope``, which no predicate ever mutates.
    Deliberately out of reach, and silent rather than guessed: a helper that detaches,
    moves to the CPU or returns a float, tensor state carried through containers or
    module globals, a container only a callee can see, and any aliasing across frames.
    No single-pass walk can attribute those, so the gate trades that recall for precision.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

HNS083 = "HNS083"
HNS084 = "HNS084"
HNS085 = "HNS085"
HNS086 = "HNS086"

MSG_HNS083 = (
    "in-loop collection store of an un-detached tensor that can carry an autograd graph "
    "retains that graph for every iteration; store tensor.detach()/.item()/.tolist()"
)
MSG_HNS084 = (
    "in-loop torch.cat/torch.stack that folds the growing tensor back into itself "
    "reallocates and copies on every iteration and fragments the allocator; "
    "pre-allocate the buffer or collect chunks in a list and concatenate once"
)
MSG_HNS085 = (
    "in-loop augmented accumulation of an un-detached tensor compounds the autograd "
    "graph across steps; accumulate loss.detach() or float(loss.detach())"
)
MSG_HNS086 = (
    "in-loop torch.zeros/ones/empty/full of an invariant literal shape churns the "
    "allocator every iteration; allocate the buffer once outside the loop"
)

_RETENTION_INDEX = {"append": 0, "insert": 1, "add": 0}
_RELEASE_METHODS = frozenset({"detach", "item", "tolist", "numpy", "cpu"})
_RELEASE_FUNCTIONS = frozenset({"float", "int", "bool"})
_SCALAR_METHODS = frozenset({"detach", "item", "float", "int"})
_SCALAR_FUNCTIONS = frozenset({"float", "int"})
_TENSOR_ROOTS = frozenset({"torch", "nn", "F", "functional"})
_FUNCTION_MODULES = frozenset(
    {"torch", "nn", "F", "functional", "np", "numpy", "operator"}
)
_FACTORY_ROOTS = frozenset(
    {
        "nn",
        "optim",
        "utils",
        "distributions",
        "autograd",
        "amp",
        "compile",
        "jit",
        "onnx",
        "torchvision",
        "datasets",
    }
)
_NON_TENSOR_CALLS = frozenset(
    {
        "device",
        "dtype",
        "Size",
        "manual_seed",
        "initial_seed",
        "is_available",
        "save",
        "load",
        "backends",
        "version",
        "compile",
        "set_grad_enabled",
        "no_grad",
        "inference_mode",
        "enable_grad",
        "autocast",
        "cuda",
        "mps",
        "memory_allocated",
        "memory_reserved",
        "max_memory_allocated",
    }
)
_GRAPH_FREE_CALLS = frozenset(
    (
        # Creation ops build leaves whose grad_fn is None.
        "zeros",
        "ones",
        "empty",
        "full",
        "zeros_like",
        "ones_like",
        "empty_like",
        "full_like",
        "new_zeros",
        "new_ones",
        "new_empty",
        "new_full",
        "rand",
        "randn",
        "randint",
        "randperm",
        "arange",
        "linspace",
        "logspace",
        "eye",
        "tensor",
        "scalar_tensor",
        "from_numpy",
        "frombuffer",
        "detach",
        # Boolean, index and shape queries return flags rather than activations.
        "isfinite",
        "isnan",
        "isinf",
        "isposinf",
        "isneginf",
        "all",
        "any",
        "argmin",
        "argmax",
        "argsort",
        "nonzero",
        "count_nonzero",
        "numel",
        "size",
        "dim",
        "ndim",
        "eq",
        "ne",
        "lt",
        "gt",
        "le",
        "ge",
        "equal",
        "is_nonzero",
        "logical_and",
        "logical_or",
        "logical_not",
        "logical_xor",
        "bincount",
        "histc",
        "unique",
    )
)
_GROWTH_ATTRS = frozenset({"cat", "stack"})
_ALLOCATION_ATTRS = frozenset({"zeros", "ones", "empty", "full"})
_SHAPE_KEYWORDS = frozenset({"size", "shape"})
_NOGRAD_ATTRS = frozenset({"no_grad", "inference_mode"})
_SCALAR_ANNOTATIONS = frozenset(
    {
        "list",
        "List",
        "dict",
        "Dict",
        "set",
        "Set",
        "tuple",
        "Tuple",
        "frozenset",
        "FrozenSet",
        "deque",
        "Deque",
        "Sequence",
        "Iterable",
        "Iterator",
        "Mapping",
        "MutableMapping",
        "Optional",
        "Union",
        "Any",
        "float",
        "int",
        "str",
        "bool",
        "bytes",
        "complex",
        "object",
        "None",
    }
)


@dataclass(frozen=True)
class Scope:
    """The per-function evidence the retention rules are allowed to use.

    ``tensor_names`` holds locals whose value can carry an autograd graph,
    ``callable_names`` the torch-built callables whose calls return one,
    ``scalar_names`` the names an annotation proves are not tensors,
    ``opaque_names`` the names this function bound from a call, attribute or
    subscript, and ``nograd`` the state of an enclosing no-grad block. Rules read
    this instead of guessing, which is what keeps them silent on a helper's
    detached output, on an annotated float list and on a preallocated buffer.
    """

    tensor_names: frozenset[str] = frozenset()
    callable_names: frozenset[str] = frozenset()
    scalar_names: frozenset[str] = frozenset()
    opaque_names: frozenset[str] = frozenset()
    nograd: bool = False


_EMPTY_SCOPE = Scope()


def _root_name(node: ast.AST) -> str:
    """Return the leftmost plain name of an expression, or the empty string."""
    current = node
    while True:
        if isinstance(current, ast.Call):
            current = current.func
        elif isinstance(current, (ast.Attribute, ast.Subscript)):
            current = current.value
        elif isinstance(current, ast.Name):
            return current.id
        else:
            return ""


def _namespace_name(func: ast.AST) -> str:
    """Return the name a callee path is rooted at, stopping at any call in it.

    Stopping matters: in ``torch.bincount(ids).tolist()`` the outer call is a
    method on a *result*, not an entry point into the torch namespace, and only
    the inner ``torch.bincount`` may speak for the expression.
    """
    current = func
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else ""


def _call_name(func: ast.AST) -> str:
    """Return the attribute or function name a call is invoked through."""
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def _attribute_chain(func: ast.AST) -> list[str]:
    """Return the attribute names leading to a call, outermost first."""
    names: list[str] = []
    current = func
    while isinstance(current, ast.Attribute):
        names.append(current.attr)
        current = current.value
    return names


def _container_key(node: ast.AST) -> str:
    """Return the variable name a container expression is known by."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _container_key(node.value)
    return ""


def is_torch_call(node: ast.Call) -> bool:
    """Return True when a call is invoked through a tensor namespace."""
    if _namespace_name(node.func) not in _TENSOR_ROOTS:
        return False
    return _call_name(node.func) not in _NON_TENSOR_CALLS


def is_factory_call(node: ast.Call) -> bool:
    """Return True for a call that builds a module, optimizer or loader.

    ``torch.nn.Linear(...)`` and ``nn.Parameter(...)`` return something that
    produces or holds tensors rather than a tensor, so the binding is tracked as a
    callable: its call sites are tensor evidence while the object itself is not.
    ``torch.nn.functional`` is excluded because those entries return tensors.
    """
    if not is_torch_call(node):
        return False
    chain = _attribute_chain(node.func)
    if "functional" in chain:
        return False
    if _namespace_name(node.func) in _FACTORY_ROOTS:
        return True
    return any(name in _FACTORY_ROOTS for name in chain)


def is_graph_call(node: ast.Call) -> bool:
    """Return True for a tensor-producing call that can attach an autograd graph."""
    if not is_torch_call(node) or is_factory_call(node):
        return False
    return _call_name(node.func) not in _GRAPH_FREE_CALLS


def classify_binding(node: ast.AST, scope: Scope = _EMPTY_SCOPE) -> str:
    """Classify an assignment value as ``tensor``, ``callable`` or ``none``.

    ``tensor`` marks a local whose value can carry a graph, ``callable`` the
    torch-built callables whose calls do, and ``none`` everything a single-pass
    walk cannot attribute: a helper's return, a literal, or a creation-op leaf.
    """
    if not isinstance(node, ast.Call):
        return "none"
    if is_factory_call(node):
        return "callable"
    if is_graph_call(node):
        return "tensor"
    root = _namespace_name(node.func)
    if root and (root in scope.tensor_names or root in scope.callable_names):
        return "tensor"
    return "none"


def has_tensor_evidence(node: ast.AST, scope: Scope = _EMPTY_SCOPE) -> bool:
    """Return True when an expression carries a graph-carrying tensor proof.

    An inline graph-capable ``torch.*`` call is un-detached by construction, and a
    local this function bound from one carries the same proof; nothing else does.
    """
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in scope.tensor_names:
            return True
        if isinstance(child, ast.Call) and is_graph_call(child):
            return True
    return False


def _has_wrapper(
    node: ast.AST, methods: frozenset[str], functions: frozenset[str]
) -> bool:
    """Return True when any call inside an expression wraps the value it receives."""
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Attribute) and child.func.attr in methods:
            return True
        if isinstance(child.func, ast.Name) and child.func.id in functions:
            return True
    return False


def is_released(node: ast.AST) -> bool:
    """Return True when an expression is wrapped in a graph-releasing call."""
    return _has_wrapper(node, _RELEASE_METHODS, _RELEASE_FUNCTIONS)


def is_scalarized(node: ast.AST) -> bool:
    """Return True when an expression is wrapped in a scalarizing call."""
    return _has_wrapper(node, _SCALAR_METHODS, _SCALAR_FUNCTIONS)


def is_scalar_annotation(node: ast.AST) -> bool:
    """Return True when a type annotation proves the value is not a tensor.

    ``losses: list[float]`` and ``total: int`` are local proofs of non-tensor
    storage. ``list[torch.Tensor]`` and ``list[Finding]`` are not: the first names
    a tensor, the second a type this gate cannot see through, so both keep their
    evidence requirement instead of an exemption.
    """
    identifiers = [
        child.id if isinstance(child, ast.Name) else child.attr
        for child in ast.walk(node)
        if isinstance(child, (ast.Name, ast.Attribute))
    ]
    if not identifiers:
        return False
    return all(name in _SCALAR_ANNOTATIONS for name in identifiers)


def is_nograd_context(node: ast.AST) -> bool:
    """Return True for a ``torch.no_grad()`` or ``torch.inference_mode()`` context."""
    if not isinstance(node, ast.Call):
        return False
    return _root_name(node.func) == "torch" and _call_name(node.func) in _NOGRAD_ATTRS


def starts_nograd(node: ast.AST) -> bool:
    """Return True when a function definition runs under a no-grad decorator."""
    return any(is_nograd_context(item) for item in getattr(node, "decorator_list", []))
