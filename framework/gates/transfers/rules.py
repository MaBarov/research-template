"""AST predicates for detecting host-device transfer bottlenecks.

Thumbnail: Pattern checkers for the HNS056-HNS060 transfer and HNS088 mixing anti-patterns.

Invariants & Expected State:
    Every predicate is pure over the ast nodes it receives and never mutates the tree.
    Functions stay strictly under 30 lines and avoid global state.
    Rules report mechanical shapes with a clear safe replacement.
    ``trigger_for`` names the evidence behind a finding (loop, aggregate, static or
    name-carried); the code-to-trigger table lives here, beside the rules that
    produce the codes, so a new aggregate rule cannot mislabel by omission.
    Streaming names match whole underscore tokens, so ``_as_timestep`` never fires.
    A bare ``float``/``int``/``bool`` counts as a synchronization only over a tensor
    reduction, and never over a numpy, math or statistics root.
    Concatenations are checked for per-element moves or casts, which belong after the join.
    The synchronization rule takes the host-built locals of the enclosing scope, so
    a ``.tolist()`` over a tensor the same function built on the host is no stall;
    ``as_tensor``/``asarray`` are deliberately absent from the factory list because
    they alias a tensor argument, device included.
    Payload contexts (checkpoint/artifact/cache writers) materialize on the host by
    design and are exempt; a discarded call result carries no data transfer.
"""

from __future__ import annotations

import ast

HNS056 = "HNS056"
HNS057 = "HNS057"
HNS058 = "HNS058"
HNS059 = "HNS059"
HNS060 = "HNS060"
HNS088 = "HNS088"

MSG_HNS056 = (
    "GPU-to-CPU transfer inside loop or streaming method causes PCIe stalls and GPU "
    "starvation; keep tensor device-resident or accumulate in-place"
)
MSG_HNS057 = (
    "in-loop/in-hook device-to-host synchronization (.item()/.tolist()/float(tensor)) "
    "forces CUDA stream stall; defer synchronization or aggregate on device"
)
MSG_HNS058 = (
    "in-loop .to(device)/.cuda() transfer of invariant target creates redundant "
    "PCIe traffic; pin to device outside loop"
)
MSG_HNS059 = (
    "in-loop CUDA synchronize serializes the stream; the loop cannot overlap host "
    "work with GPU work, so hoist the barrier out of it"
)
MSG_HNS059_CACHE = (
    "in-loop empty_cache forces a synchronous allocation on the next request; hoist "
    "it out of the loop unless the loop is a deliberate per-iteration VRAM boundary"
)
MSG_HNS060 = (
    "a concatenation comprehension moves or re-casts every element separately, "
    "allocating a tensor per element; concatenate first and transfer/cast once"
)
MSG_HNS088 = (
    "expression provably mixes a host tensor with a device tensor; torch raises "
    "'Expected all tensors to be on the same device' here -- build the host operand "
    "on the tensor's device or pin it with .to(device=...)"
)

_STREAMING_KEYWORDS = (
    "accumulate",
    "stream",
    "hook",
    "capture",
    "forward",
    "step",
    "consume",
    "add_pair",
    "add_safe",
)

_PAYLOAD_KEYWORDS = (
    "artifact",
    "cache",
    "checkpoint",
    "cpu",
    "digest",
    "dump",
    "export",
    "hash",
    "materialize",
    "payload",
    "persist",
    "receipt",
    "save",
    "serialize",
    "sha256",
    "snapshot",
    "store",
    "write",
)

_TENSOR_REDUCTIONS = {"sum", "mean", "norm", "all", "any", "max", "min", "pow", "abs"}
_CPU_ROOTS = {"np", "numpy", "math", "random", "statistics", "px", "pixel", "pixels"}
_AGGREGATE_ATTRS = {"cat", "stack", "concatenate", "hstack", "vstack"}
_TORCH_HOST_FACTORIES = {
    "tensor",
    "from_numpy",
    "zeros",
    "ones",
    "empty",
    "full",
    "arange",
    "linspace",
    "logspace",
    "rand",
    "randn",
    "randint",
    "randperm",
    "eye",
}
_HOST_PASS_METHODS = {
    "long",
    "int",
    "float",
    "double",
    "cpu",
    "detach",
    "clone",
    "contiguous",
    "view",
    "reshape",
    "flatten",
}

_TORCH_DTYPES = {
    "float32",
    "float64",
    "bfloat16",
    "float16",
    "half",
    "double",
    "float",
    "int32",
    "int64",
    "long",
    "int",
    "bool",
    "uint8",
    "int8",
    "int16",
    "short",
    "complex64",
    "complex128",
    "dtype",
}


def is_streaming_method_name(fn_name: str) -> bool:
    """Return True if the name marks a streaming or capture pass.

    Matching is token-bounded on underscores, so ``_step_backward`` counts as
    a streaming step while ``_as_timestep`` and ``timestamp`` do not.
    """
    padded = f"_{fn_name.lower()}_"
    return any(f"_{kw}_" in padded for kw in _STREAMING_KEYWORDS)


def _is_dtype_node(node: ast.AST) -> bool:
    """Return True if AST node represents a torch dtype specification."""
    if isinstance(node, ast.Attribute) and node.attr.lower() in _TORCH_DTYPES:
        return True
    if isinstance(node, ast.Name) and node.id.lower() in _TORCH_DTYPES:
        return True
    return isinstance(node, ast.Constant) and str(node.value).lower() in _TORCH_DTYPES


def _is_cpu_device_node(node: ast.AST) -> bool:
    """Return True if AST node represents a CPU device specification."""
    if isinstance(node, ast.Constant) and str(node.value).lower() == "cpu":
        return True
    if isinstance(node, ast.Call):
        return any(
            isinstance(arg, ast.Constant) and str(arg.value).lower() == "cpu"
            for arg in node.args
        )
    return False


def is_cpu_transfer_call(node: ast.Call) -> bool:
    """Return True if node represents a .cpu() or .to('cpu') call."""
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr == "cpu":
        return True
    if node.func.attr == "to":
        if any(_is_cpu_device_node(arg) for arg in node.args):
            return True
        for kw in node.keywords:
            if kw.arg == "device" and _is_cpu_device_node(kw.value):
                return True
    return False


def _tensor_sync_root(node: ast.AST) -> str:
    """Return the root name of a reduction receiver, empty when it is not one."""
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            node = node.value
        else:
            node = node.value
    return node.id if isinstance(node, ast.Name) else ""


def is_tensor_cast_sync_call(
    node: ast.Call, host_names: frozenset[str] = frozenset()
) -> bool:
    """Return True for ``float(...)``/``int(...)``/``bool(...)`` over a tensor reduction.

    Only a reduction is accepted as the argument, because ``float(config["dose"])``
    and ``int(index)`` are plain Python arithmetic: 258 of the tree's 268 cast sites
    take a name, attribute or subscript, and flagging those would be pure noise.
    Receivers that already end in ``.item()``/``.tolist()`` are skipped as duplicates
    of HNS057, and numpy/math roots never touch the CUDA stream.
    """
    if not isinstance(node.func, ast.Name) or node.func.id not in {
        "float",
        "int",
        "bool",
    }:
        return False
    if not node.args:
        return False
    receiver = node.args[0]
    if not isinstance(receiver, ast.Call) or not isinstance(
        receiver.func, ast.Attribute
    ):
        return False
    if receiver.func.attr not in _TENSOR_REDUCTIONS and receiver.func.attr != "detach":
        return False
    root = _tensor_sync_root(receiver)
    if root in _CPU_ROOTS or root in host_names:
        return False
    return not _is_host_tensor_node(receiver.func.value, host_names)


def _declares_host_placement(node: ast.Call) -> bool:
    """Return True when a factory call carries no device or an explicit CPU one."""
    for keyword in node.keywords:
        if keyword.arg != "device":
            continue
        if not isinstance(keyword.value, ast.Constant):
            return False
        return keyword.value.value == "cpu"
    return True


def _is_host_load_call(node: ast.Call) -> bool:
    """Return True when torch.load passes an explicit map_location='cpu'."""
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "load":
        return False
    if not _is_torch_root(node.func.value):
        return False
    for keyword in node.keywords:
        if keyword.arg == "map_location" and isinstance(keyword.value, ast.Constant):
            return keyword.value.value == "cpu"
    return False


def _unwrap_host_receiver(node: ast.AST) -> ast.AST:
    """Unwrap subscripts and device-preserving method calls."""
    while True:
        if isinstance(node, ast.Subscript):
            node = node.value
            continue
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _HOST_PASS_METHODS
        ):
            node = node.func.value
            continue
        return node


def _is_host_tensor_node(node: ast.AST, host_names: frozenset[str]) -> bool:
    """Return True when an expression provably builds its tensor on the host."""
    node = _unwrap_host_receiver(node)
    if isinstance(node, ast.Name):
        return node.id in host_names
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if _is_host_load_call(node):
        return True
    if (
        not _is_torch_root(node.func.value)
        or node.func.attr not in _TORCH_HOST_FACTORIES
    ):
        return False
    return _declares_host_placement(node)


def is_device_sync_call(
    node: ast.Call, host_names: frozenset[str] = frozenset()
) -> bool:
    """Return True if node represents a device-to-host synchronization."""
    if isinstance(node.func, ast.Name):
        return is_tensor_cast_sync_call(node, host_names)
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in {"item", "tolist"}:
        return False
    return not _is_host_tensor_node(node.func.value, host_names)


def is_aggregate_transfer_call(node: ast.Call) -> bool:
    """Return True for a concatenation whose elements are transferred one by one."""
    if (
        not isinstance(node.func, ast.Attribute)
        or node.func.attr not in _AGGREGATE_ATTRS
    ):
        return False
    if not _is_torch_root(node.func.value):
        return False
    return any(_comprehension_transfers(arg) for arg in node.args)


def _is_torch_root(node: ast.AST) -> bool:
    """Return True when a callable is reached through ``torch``."""
    return isinstance(node, ast.Name) and node.id == "torch"


def _comprehension_transfers(node: ast.AST) -> bool:
    """Return True when a comprehension element moves or re-casts a tensor.

    Only the host-to-device direction is a defect here: a concatenation on the
    host *requires* every element on the host first, so ``[x.cpu() for x in xs]``
    has no cheaper form and belongs to HNS056 instead.
    """
    if not isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        return False
    return any(
        isinstance(child, ast.Call) and _is_device_move(child)
        for child in ast.walk(node.elt)
    )


def _is_device_move(node: ast.Call) -> bool:
    """Return True for a ``.cuda()`` or device/dtype ``.to(...)`` call.

    A positional argument counts unless it is a CPU device specification, so a
    constant device string (``.to("cuda")``) fires like ``.to(device)`` does.
    """
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr == "cuda":
        return True
    if node.func.attr != "to":
        return False
    return any(
        keyword.arg in {"device", "dtype", "memory_format"} for keyword in node.keywords
    ) or any(not _is_cpu_device_node(arg) for arg in node.args)


def is_cuda_sync_call(node: ast.Call) -> bool:
    """Return True if node represents an in-loop CUDA synchronize or empty_cache call."""
    if not isinstance(node.func, ast.Attribute):
        return False
    attr = node.func.attr
    return attr in {"synchronize", "empty_cache"}


def _is_device_constructor_transfer(node: ast.Call) -> bool:
    """Return True for torch.as_tensor/tensor with an explicit non-cpu device keyword."""
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "as_tensor":
        return False
    if not _is_torch_root(node.func.value):
        return False
    for kw in node.keywords:
        if kw.arg == "device":
            return not (isinstance(kw.value, ast.Constant) and kw.value.value == "cpu")
    return False


def is_device_to_transfer_call(node: ast.Call) -> bool:
    """Return True if node represents a .cuda() or .to(device) transfer inside a loop."""
    if _is_device_constructor_transfer(node):
        return True
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr == "cuda":
        return True
    if node.func.attr == "to":
        if is_cpu_transfer_call(node):
            return False
        if any(kw.arg == "device" for kw in node.keywords):
            return True
        non_dtype_args = [arg for arg in node.args if not _is_dtype_node(arg)]
        return bool(non_dtype_args)
    return False


def is_payload_method_name(fn_name: str) -> bool:
    """Return True for host-materialization contexts (artifacts, checkpoints).

    Such a function exists to hand data to the host or to disk: the transfer is
    its deliverable, and the loop it runs is over artifacts rather than over the
    hot path, so none of the transfer rules apply inside it.
    """
    padded = f"_{fn_name.lower()}_"
    return any(f"_{kw}_" in padded for kw in _PAYLOAD_KEYWORDS)


def _references_any(node: ast.AST, names: frozenset[str]) -> bool:
    """Return True if the subtree reads any of the given variable names."""
    return any(
        isinstance(child, ast.Name) and child.id in names for child in ast.walk(node)
    )


def is_redundant_device_transfer(node: ast.Call, loop_names: frozenset[str]) -> bool:
    """Return True for an in-loop host-to-device transfer of an invariant target."""
    if not is_device_to_transfer_call(node):
        return False
    if _is_device_constructor_transfer(node):
        return True
    receiver = node.func.value if isinstance(node.func, ast.Attribute) else node.func
    return not _references_any(receiver, loop_names)


_AGGREGATE_CODES = frozenset({HNS060})
_STATIC_CODES = frozenset({HNS088})


def trigger_for(code: str, in_loop: bool) -> str:
    """Map a finding's code and repetition context to its evidence state.

    ``static`` wins for codes whose defect is a context-free shape that fails
    wherever it appears (a host tensor meeting a device tensor in one expression);
    ``loop`` then wins whenever a loop or comprehension repeats the call, because
    repetition is what turns the shape into a per-iteration cost; ``aggregate``
    marks the codes whose evidence is context-free (the concatenation shape costs
    the same wherever it appears); otherwise the finding is ``streaming`` -
    carried by the enclosing function's name alone.
    """
    if code in _STATIC_CODES:
        return "static"
    if in_loop:
        return "loop"
    return "aggregate" if code in _AGGREGATE_CODES else "streaming"


def check_transfer_node(
    node: ast.Call,
    in_loop: bool,
    fn_name: str,
    discarded: bool = False,
    loop_names: frozenset[str] = frozenset(),
    host_names: frozenset[str] = frozenset(),
) -> tuple[str, str] | None:
    """Evaluate an AST call node against the transfer rules.

    ``discarded`` marks a state-moving call; ``host_names`` the host-built locals.
    """
    if is_payload_method_name(fn_name):
        return None
    if is_cuda_sync_call(node) and in_loop:
        attribute = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        return HNS059, (MSG_HNS059_CACHE if attribute == "empty_cache" else MSG_HNS059)
    if is_aggregate_transfer_call(node):
        return HNS060, MSG_HNS060
    if discarded:
        return None
    if is_cpu_transfer_call(node) and (in_loop or is_streaming_method_name(fn_name)):
        return HNS056, MSG_HNS056
    if is_device_sync_call(node, host_names) and (
        in_loop or is_streaming_method_name(fn_name)
    ):
        return HNS057, MSG_HNS057
    if in_loop and is_redundant_device_transfer(node, loop_names):
        return HNS058, MSG_HNS058
    return None
