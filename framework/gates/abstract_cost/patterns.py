"""Abstract cost-class rules for the advisory gate.

Thumbnail: HNS095-HNS099 rules for invariant repeated work, retained banks and per-item passes.

Invariants & Expected State:
    The rules name a cost class, not a library call: work repeated although its
    inputs do not change (HNS095/HNS096/HNS099), a bank retained only to be
    reduced later (HNS097), and a heavy call made once per item (HNS098).
    Invariance is syntactic and conservative: any name or ``self`` attribute
    bound inside the loop makes an expression varying, so an invariant verdict is
    never guessed. Unproven shapes are skipped rather than reported.
    A bare ``@`` product is not reported: an operand mutated in place through a
    helper is invisible to local analysis, so only the call forms
    (``torch.mm``/``bmm``/``matmul``/``einsum``) are judged. A sync read inside a
    conditional is skipped for the same reason (a first-iteration guard runs
    once). Every rule is pure over the AST it receives; the visitor owns state.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass

from framework.gates.transfers.rules import _is_torch_root, is_payload_method_name

HNS095 = "HNS095"
HNS096 = "HNS096"
HNS097 = "HNS097"
HNS098 = "HNS098"
HNS099 = "HNS099"

MSG_HNS095 = (
    "the matrix is loop-invariant but is factorized again on every iteration; "
    "factorize (or invert/solve) once before the loop and reuse the factorization"
)
MSG_HNS096 = (
    "this derivation depends only on loop-invariant inputs, so repeating it inside "
    "the loop recomputes the same value; hoist it (cache the derived tensor) once"
)
MSG_HNS097 = (
    "every iteration's tensor is retained in a bank and later concatenated, but the "
    "consumer only aggregates it; accumulate the statistic (gram, sum, norm) per "
    "capture instead of keeping the elements"
)
MSG_HNS098 = (
    "a model/pipeline call runs once per item inside the loop; batch the items into "
    "one pass (or cache the result) instead of paying a full forward per item"
)
MSG_HNS099 = (
    "this host synchronization reads a value that cannot change between iterations, "
    "so the device round trip repeats identically; read it once before the loop"
)

FACTORIZATION_OPS = frozenset(
    {
        "cholesky",
        "det",
        "eig",
        "eigh",
        "eigvals",
        "eigvalsh",
        "inv",
        "inverse",
        "lstsq",
        "lu",
        "lu_factor",
        "matrix_rank",
        "pinv",
        "qr",
        "slogdet",
        "solve",
        "svd",
        "svdvals",
    }
)
DERIVATION_OPS = FACTORIZATION_OPS | frozenset(
    {
        "bmm",
        "cdist",
        "dot",
        "einsum",
        "float64",
        "double",
        "matmul",
        "matrix_norm",
        "mm",
        "mv",
        "norm",
        "outer",
        "tensordot",
        "tobytes",
        "tostring",
    }
)
PIPELINE_NAMES = frozenset({"model", "net", "pipe", "pipeline", "unet", "vae"})
SYNC_ATTRS = frozenset({"item", "synchronize", "tolist"})
SYNC_FUNCTIONS = frozenset({"bool", "float", "int"})
RANDOM_ATTRS = frozenset(
    {
        "bernoulli",
        "choice",
        "default_rng",
        "empty",
        "empty_like",
        "integers",
        "multinomial",
        "normal",
        "permutation",
        "rand",
        "rand_like",
        "randint",
        "randn",
        "randn_like",
        "randperm",
        "sample",
        "shuffle",
        "uniform",
    }
)
_METADATA_ATTRS = frozenset({"dim", "ndim", "numel", "size"})
_LINEAR_ALGEBRA_ROOTS = frozenset({"linalg"})
_TORCH_ROOTS = frozenset({"torch", "np", "numpy"})


@dataclass(frozen=True)
class LoopScope:
    """Names a loop body rebinds; an expression touching them is varying."""

    names: frozenset[str]
    attrs: frozenset[str]


@dataclass(frozen=True)
class Retention:
    """One retained-bank finding site: append line, subject, materializing consumer."""

    line: int
    subject: str
    consumer: str


def names_in(node: ast.AST) -> frozenset[str]:
    """Return every simple name read or written by one expression."""
    return frozenset(
        child.id for child in ast.walk(node) if isinstance(child, ast.Name)
    )


def self_attrs_in(node: ast.AST) -> frozenset[str]:
    """Return every ``self.<attr>`` touched by one expression."""
    return frozenset(
        child.attr
        for child in ast.walk(node)
        if isinstance(child, ast.Attribute)
        and isinstance(child.value, ast.Name)
        and child.value.id == "self"
    )


def is_invariant(node: ast.AST, scopes: Sequence[LoopScope]) -> bool:
    """True when no enclosing loop rebinds anything the expression reads."""
    names = names_in(node)
    attrs = self_attrs_in(node)
    return not any(names & scope.names or attrs & scope.attrs for scope in scopes)


def has_random_operand(node: ast.AST) -> bool:
    """True when the expression draws from an RNG, so hoisting changes semantics."""
    return any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr in RANDOM_ATTRS
        for child in ast.walk(node)
    )


def classify_heavy(call: ast.Call) -> tuple[str, str] | None:
    """Classify one call as a factorization or derivation, with its operation."""
    if not isinstance(call.func, ast.Attribute):
        return None
    return _kind(call.func.attr)


def _kind(attr: str) -> tuple[str, str] | None:
    """Map an operation name to its class within the torch/numpy namespaces."""
    if attr in FACTORIZATION_OPS:
        return "factorization", attr
    if attr in DERIVATION_OPS - FACTORIZATION_OPS:
        return "derivation", attr
    return None


def matrix_operand(call: ast.Call) -> ast.AST | None:
    """Return the matrix a factorization consumes: first argument, else receiver."""
    if not isinstance(call.func, ast.Attribute):
        return None
    if call.args:
        return call.args[0]
    return call.func.value


def derivation_operands(call: ast.Call) -> list[ast.expr]:
    """Return every input of a derivation: arguments plus the receiver."""
    if not isinstance(call.func, ast.Attribute):
        return []
    root = call.func.value
    namespaced = isinstance(root, ast.Name) and root.id in _TORCH_ROOTS
    linalg = isinstance(root, ast.Attribute) and root.attr in _LINEAR_ALGEBRA_ROOTS
    operands = [*call.args, *(keyword.value for keyword in call.keywords)]
    if namespaced or linalg:
        return operands
    return [root, *operands]


def host_sync_target(call: ast.Call) -> ast.AST | None:
    """Return the expression a blocking host read consumes, if this is one."""
    function = call.func
    if isinstance(function, ast.Name) and function.id in SYNC_FUNCTIONS:
        return call.args[0] if call.args else None
    if isinstance(function, ast.Attribute) and function.attr in SYNC_ATTRS:
        return function.value
    return None


def is_tensor_sync_target(node: ast.AST) -> bool:
    """A call target is a tensor read; metadata and RNG calls are not."""
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Attribute) and node.func.attr in _METADATA_ATTRS:
        return False
    return not has_random_operand(node)


def pipeline_call_name(call: ast.Call) -> str | None:
    """Return the model/pipeline name a call invokes, if it invokes one."""
    function = call.func
    if isinstance(function, ast.Name):
        return function.id if function.id in PIPELINE_NAMES else None
    if isinstance(function, ast.Attribute) and (
        function.attr in PIPELINE_NAMES or function.attr == "forward"
    ):
        return function.attr
    return None


def own_calls(body: Sequence[ast.stmt]) -> list[ast.Call]:
    """Return calls in one function body without descending into nested scopes."""
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
    calls: list[ast.Call] = []
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        if isinstance(node, nested):
            continue
        if isinstance(node, ast.Call):
            calls.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return calls


def function_definitions(
    body: Sequence[ast.stmt],
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Return functions defined in a body, descending into class bodies only."""
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for statement in body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append(statement)
        elif isinstance(statement, ast.ClassDef):
            found.extend(function_definitions(statement.body))
    return found


def helper_heavy_params(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[int, str]:
    """Map a parameter index to the heavy class the helper applies to it.

    Only an operand that depends on exactly one parameter is mapped, so a helper
    mixing two parameters (``f(cumulative, basis)``) is not read as syncing
    either one: the caller cannot tell which argument drives the heavy call.
    """
    params = [
        argument.arg for argument in [*function.args.args, *function.args.kwonlyargs]
    ]
    heavy: dict[int, str] = {}
    for call in own_calls(function.body):
        classified = classify_heavy(call)
        if classified is not None:
            kind, _operation = classified
            operands = [matrix_operand(call)] if kind == "factorization" else []
        else:
            target = host_sync_target(call)
            tensor_target = target is not None and is_tensor_sync_target(target)
            operands, kind = ([target] if tensor_target else []), "sync"
        for operand in operands:
            index = _single_param_index(operand, params)
            if index is not None:
                heavy.setdefault(index, kind)
    return heavy


_NAMESPACE_NAMES = frozenset({"F", "math", "np", "numpy", "scipy", "self", "torch"})


def _single_param_index(operand: ast.AST | None, params: Sequence[str]) -> int | None:
    """Return the index of the only parameter an operand depends on, else None."""
    if operand is None:
        return None
    touched = names_in(operand) - _NAMESPACE_NAMES
    for index, param in enumerate(params):
        if touched == {param}:
            return index
    return None


_CAPTURE_METHODS = frozenset({"call", "capture", "hook", "record"})
_BANK_SUFFIXES = ("_bank", "_banks", "_batches", "_designs", "_events", "_rows")


def class_retentions(class_node: ast.ClassDef) -> list[Retention]:
    """Retention where a capture callback banks ``self.<attr>`` and a method cats it."""
    appends: dict[str, tuple[int, str]] = {}
    for function in function_definitions(class_node.body):
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            holder = _append_holder(node)
            if holder is not None:
                appends.setdefault(holder, (node.lineno, function.name))
    materialized: dict[str, str] = {}
    for function in function_definitions(class_node.body):
        if is_payload_method_name(function.name):
            continue
        for call in ast.walk(function):
            subject = _materialized_subject(call)
            if subject is not None:
                materialized.setdefault(subject, function.name)
    return [
        Retention(appends[attr][0], f"self.{attr}", materialized[attr])
        for attr in appends
        if attr in materialized and _is_capture_bank(attr, appends[attr][1])
    ]


def _is_capture_bank(attr: str, method_name: str) -> bool:
    """A capture callback (hook, ``__call__``, record) or a bank-shaped name."""
    return method_name.strip("_") in _CAPTURE_METHODS or attr.endswith(_BANK_SUFFIXES)


def _append_holder(call: ast.AST) -> str | None:
    """Return the attribute or list name one ``append`` call pushes into."""
    if not isinstance(call, ast.Call):
        return None
    if not isinstance(call.func, ast.Attribute) or call.func.attr != "append":
        return None
    holder = call.func.value
    if isinstance(holder, ast.Attribute):
        return holder.attr
    return holder.id if isinstance(holder, ast.Name) else None


def _materialized_subject(call: ast.AST) -> str | None:
    """Return the list name a ``torch.cat``/``stack`` materializes."""
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return None
    if call.func.attr not in {"cat", "stack"} or not _is_torch_root(call.func.value):
        return None
    first = call.args[0] if call.args else None
    if isinstance(first, ast.Name):
        return first.id
    if isinstance(first, ast.Attribute):
        return first.attr
    return None
