"""Rule evidence for the advisory hot-path gate: codes, messages and predicates.

Thumbnail: HNS089-HNS094 with the tensor, hot-function and loader predicates they read.

Invariants & Expected State:
    Every predicate is pure over the AST it receives and reuses the transfer
    gate's proven placement helpers instead of restating them.
    Tensor-ness is claimed only from a local proof: a torch factory, a tensor
    returning method, a ``.to``/``.cuda``/``.detach`` chain, or a ``Tensor``
    annotation. A name arriving as a bare parameter stays unproven.
    A hot function is one whose own body calls ``backward``/``step``/
    ``zero_grad``; calls made through a helper are not followed, and that gap is
    catalogued in the test dataset.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Sequence

from framework.gates.transfers.rules import (
    _TORCH_HOST_FACTORIES,
    _is_torch_root,
    is_device_to_transfer_call,
)

HNS089 = "HNS089"
HNS090 = "HNS090"
HNS091 = "HNS091"
HNS092 = "HNS092"
HNS093 = "HNS093"
HNS094 = "HNS094"

MSG_HNS089 = (
    "a CPU-allocating torch factory is followed by .to(device)/.cuda(), so every call "
    "allocates on the host and copies; pass device= to the factory (or use a *_like of "
    "a device tensor) to allocate once on the target device"
)
MSG_HNS090 = (
    ".numpy() inside a loop converts a tensor to host memory on every iteration; "
    "convert once outside the loop and reuse the array"
)
MSG_HNS091 = (
    "device-to-host synchronization inside a training-step function stalls the step "
    "pipeline; accumulate the value on the device and read it once after the step"
)
MSG_HNS092 = (
    "torch.autograd anomaly detection is left enabled; every backward then runs the "
    "NaNs/gradient checks, which dominates step time -- enable it only while debugging"
)
MSG_HNS093 = (
    "per-element tensor indexing inside a Python loop launches one GPU op per element "
    "and never saturates the device; vectorize, slice, or gather with a tensor index"
)
MSG_HNS094 = (
    "DataLoader without worker prefetch or pinned memory lets the CPU feed the GPU "
    "synchronously and can starve it; set num_workers>0 and pin_memory=True"
)

_FACTORY_ATTRS = frozenset(_TORCH_HOST_FACTORIES) | {"as_tensor"}
_MOVE_ATTRS = frozenset({"to", "cuda"})
_SYNC_ATTRS = frozenset({"cpu", "item", "numpy", "tolist"})
_TENSOR_CASTS = frozenset({"bool", "float", "int"})
_TENSOR_ARG_METHODS = frozenset(
    {
        "abs",
        "clamp",
        "clamp_max",
        "clamp_min",
        "detach",
        "exp",
        "log",
        "max",
        "mean",
        "min",
        "norm",
        "pow",
        "softmax",
        "sqrt",
        "sum",
    }
)
_TENSOR_ARG_FUNCTIONS = frozenset({"clip_grad_norm_", "norm"})
_TENSOR_METHODS = frozenset(
    {
        "abs",
        "cat",
        "clamp",
        "clone",
        "contiguous",
        "cpu",
        "cuda",
        "detach",
        "double",
        "exp",
        "flatten",
        "float",
        "log",
        "long",
        "masked_fill",
        "masked_select",
        "mean",
        "norm",
        "pow",
        "reshape",
        "softmax",
        "sqrt",
        "stack",
        "sum",
        "to",
        "view",
        "where",
    }
)
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def is_factory_call(node: ast.AST) -> bool:
    """Return True for a ``torch.<factory>`` call, a tensor source with no device."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _FACTORY_ATTRS
        and _is_torch_root(node.func.value)
    )


def has_device_keyword(node: ast.Call) -> bool:
    """Return True when a factory call already names its device."""
    return any(keyword.arg == "device" for keyword in node.keywords)


def is_tensor_expression(node: ast.AST) -> bool:
    """Return True when the expression provably produces a tensor."""
    while isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Attribute):
            return False
        return node.func.attr in _FACTORY_ATTRS | _TENSOR_METHODS
    return False


def is_tensor_annotation(node: ast.AST | None) -> bool:
    """Return True only for a scalar ``Tensor`` annotation, not a container of them."""
    if node is None:
        return False
    text = ast.unparse(node).replace(" ", "")
    while text.endswith("|None"):
        text = text[: -len("|None")]
    if text.startswith("Optional[") and text.endswith("]"):
        text = text[len("Optional[") : -1]
    return text in {"Tensor", "torch.Tensor"}


def is_device_move(node: ast.Call) -> bool:
    """Return True for a ``.to(device)``/``.cuda()`` that allocates elsewhere first."""
    if not isinstance(node.func, ast.Attribute):
        return False
    return node.func.attr in _MOVE_ATTRS and is_device_to_transfer_call(node)


def synchronizes(node: ast.Call) -> bool:
    """Return True for a call that reads a value back from the device."""
    if not isinstance(node.func, ast.Attribute):
        return False
    return node.func.attr in _SYNC_ATTRS or node.func.attr == "synchronize"


def synchronizes_on_tensor(node: ast.Call, tensor_names: frozenset[str]) -> bool:
    """Return True for a cast that reads a tensor value back to the host."""
    if not isinstance(node.func, ast.Name) or node.func.id not in _TENSOR_CASTS:
        return False
    if not node.args:
        return False
    argument = node.args[0]
    if isinstance(argument, ast.Name):
        return argument.id in tensor_names
    if not isinstance(argument, ast.Call):
        return False
    if isinstance(argument.func, ast.Name):
        return argument.func.id in _TENSOR_ARG_FUNCTIONS
    if not isinstance(argument.func, ast.Attribute):
        return False
    if argument.func.attr in _TENSOR_ARG_METHODS:
        return True
    return isinstance(argument.func.value, ast.Name) and (
        argument.func.value.id in {"torch", "F"}
    )


def is_anomaly_enabled(node: ast.Call) -> bool:
    """Return True for ``torch.autograd.set_detect_anomaly(True)``."""
    if (
        not isinstance(node.func, ast.Attribute)
        or node.func.attr != "set_detect_anomaly"
    ):
        return False
    if (
        not isinstance(node.func.value, ast.Attribute)
        or node.func.value.attr != "autograd"
    ):
        return False
    if not _is_torch_root(node.func.value.value):
        return False
    if not node.args:
        return False
    argument = node.args[0]
    return isinstance(argument, ast.Constant) and argument.value is True


def is_loader_call(node: ast.AST) -> bool:
    """Return True for a ``DataLoader(...)`` construction."""
    if not isinstance(node, ast.Call):
        return False
    name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
    if not name and isinstance(node.func, ast.Name):
        name = node.func.id
    return name == "DataLoader"


def loader_gaps(node: ast.Call) -> list[str]:
    """Return the loader settings that leave the CPU pipeline synchronous."""
    settings = {keyword.arg: keyword.value for keyword in node.keywords}
    gaps: list[str] = []
    workers = settings.get("num_workers")
    if workers is None or (isinstance(workers, ast.Constant) and workers.value == 0):
        gaps.append("num_workers")
    pinned = settings.get("pin_memory")
    if pinned is None or (isinstance(pinned, ast.Constant) and pinned.value is False):
        gaps.append("pin_memory")
    return gaps


def hot_function_names(body: Sequence[ast.stmt]) -> frozenset[str]:
    """Return the module-local functions and methods whose own body steps."""
    names: set[str] = set()
    for statement in _function_definitions(body):
        if any(_is_step_call(call) for call in _own_calls(statement.body)):
            names.add(statement.name)
    return frozenset(names)


def _function_definitions(
    body: Sequence[ast.stmt],
) -> Iterable[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yield functions defined in one body, descending into class bodies only."""
    for statement in body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield statement
        elif isinstance(statement, ast.ClassDef):
            yield from _function_definitions(statement.body)


def _is_step_call(node: ast.Call) -> bool:
    """Return True for ``backward``, optimizer/scheduler ``step`` or ``zero_grad``."""
    if not isinstance(node.func, ast.Attribute):
        return False
    return node.func.attr in {"backward", "step", "zero_grad"}


def _own_calls(body: Sequence[ast.stmt]) -> Iterable[ast.Call]:
    """Yield calls of one function body without descending into nested scopes."""
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        if isinstance(node, _NESTED_SCOPES):
            continue
        if isinstance(node, ast.Call):
            yield node
        stack.extend(ast.iter_child_nodes(node))
