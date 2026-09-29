"""Python-AST analysis helpers and their pattern constants.

Thumbnail: Pattern predicates for the production anti-pattern gate's Python rules.

Invariants & Expected State:
    Every predicate is pure over the ``ast`` nodes it receives and never mutates
    the tree; it returns ``True`` only for the shape its rule documents, leaving
    the visitor as the single place that decides which code is raised.  Name
    predicates accept both the receiver-resolved dotted name and the
    method-qualified name recovered by :func:`_chained_receiver_name`, and a
    recovered name must never bypass the rule's own mode, keyword or vocabulary
    guard.
    Subprocess predicates cover only the blocking entry points
    (``run``/``call``/``check_*``) and never ``Popen``, whose lifecycle the
    caller owns.  Population predicates treat ``max(len(x), 1)`` and
    ``len(x) or 1`` as the same vacuous guard: a rate over a population that can
    be empty must name the rejection of the empty case in its enclosing
    function, and an aggregate of that very population is a mean, not a rate.  A
    quotient consumed only inside a loop over that same population is inert when
    the population is empty and therefore stays silent.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable


def _constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _dotted_name(node: ast.AST) -> str | None:
    """Return ``a.b.c`` for a name/attribute chain, otherwise ``None``."""

    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _keyword(node: ast.Call, name: str) -> ast.AST | None:
    return next(
        (keyword.value for keyword in node.keywords if keyword.arg == name), None
    )


def _keyword_is(node: ast.Call, name: str, value: object) -> bool:
    keyword = _keyword(node, name)
    return isinstance(keyword, ast.Constant) and keyword.value is value


def _is_cuda_available(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "is_available"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "cuda"
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "torch"
    )


def _guards_on_cuda_availability(test: ast.AST) -> bool:
    return any(_is_cuda_available(child) for child in ast.walk(test))


def _device_kind(node: ast.AST) -> str | None:
    """Classify a device literal used as an execution target."""

    value = _constant_string(node)
    if value is None:
        return None
    text = value.strip().lower()
    if text == "cuda" or text.startswith("cuda:"):
        return "cuda"
    if text == "cpu" or text.startswith("cpu:"):
        return "cpu"
    return None


def _device_kinds(nodes: Iterable[ast.AST]) -> set[str]:
    """Collect device literals in one branch, without descending into branches."""

    kinds: set[str] = set()
    stack = list(nodes)
    while stack:
        node = stack.pop()
        kind = _device_kind(node)
        if kind is not None:
            kinds.add(kind)
        for child in ast.iter_child_nodes(node):
            if isinstance(
                child,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.Lambda,
                    ast.If,
                    ast.IfExp,
                    ast.While,
                    ast.For,
                    ast.Try,
                ),
            ):
                continue
            stack.append(child)
    return kinds


def _cuda_cpu_fallback(node: ast.If | ast.IfExp) -> bool:
    """Return whether a CUDA-availability guard silently selects CPU."""

    if not _guards_on_cuda_availability(node.test):
        return False
    if isinstance(node, ast.IfExp):
        selections = [
            ({_device_kind(node.body)} - {None}, False),
            ({_device_kind(node.orelse)} - {None}, False),
        ]
    else:
        selections = [
            (_device_kinds(node.body), _reraises(node.body)),
            (_device_kinds(node.orelse), _reraises(node.orelse)),
        ]
    if not any("cpu" in kinds for kinds, _refuses in selections):
        return False
    return any("cpu" in kinds and not refuses for kinds, refuses in selections)


def _contains_name(node: ast.AST | None, names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in names
    if isinstance(node, ast.Attribute):
        return node.attr in names or _contains_name(node.value, names)
    if isinstance(node, ast.Tuple):
        return any(_contains_name(item, names) for item in node.elts)
    return False


def _returns_none(body: Iterable[ast.stmt]) -> bool:
    return any(
        isinstance(node, ast.Return)
        and (
            node.value is None
            or isinstance(node.value, ast.Constant)
            and node.value.value is None
        )
        for statement in body
        for node in ast.walk(statement)
    )


def _reraises(body: Iterable[ast.stmt]) -> bool:
    return any(
        isinstance(node, ast.Raise)
        for statement in body
        for node in ast.walk(statement)
    )


def _contains_pass(body: Iterable[ast.stmt]) -> bool:
    return any(
        isinstance(node, ast.Pass) for statement in body for node in ast.walk(statement)
    )


def _contains_continue(body: Iterable[ast.stmt]) -> bool:
    return any(
        isinstance(node, ast.Continue)
        for statement in body
        for node in ast.walk(statement)
    )


def _candidate_scan_handler(
    handler: ast.ExceptHandler,
    try_stack: list[ast.Try],
    loop_stack: list[ast.AST],
) -> bool:
    """Return whether a handler skips one candidate of a scan loop.

    ``for candidate in candidates: try: return use(candidate) except OSError:
    pass`` is a deliberate search over alternatives, not a swallowed failure:
    the loop keeps trying and the caller still has to produce a result.
    """

    if not loop_stack or not try_stack:
        return False
    if not (_contains_pass(handler.body) or _contains_continue(handler.body)):
        return False
    return any(isinstance(node, ast.Return) for node in try_stack[-1].body)


def _validates_state_dict_result(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Return whether a function checks both sides of a non-strict load."""

    attributes = {
        node.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Attribute)
        and node.attr in {"missing_keys", "unexpected_keys"}
    }
    return attributes == {"missing_keys", "unexpected_keys"}


_PROVENANCE_TOKENS = {
    "commit",
    "sha",
    "sha1",
    "sha256",
    "sha512",
    "hash",
    "revision",
    "rev",
    "dirty",
    "provenance",
    "identity",
}

_SENTINEL_VALUES = {"unknown", "unavailable", "n/a"}

_TIMER_NAMES = {
    "t",
    "t0",
    "t1",
    "start",
    "started",
    "begin",
    "elapsed",
    "duration",
    "timer",
    "lap",
    "t_start",
    "t_end",
    "t_elapsed",
}

_TIMER_NAME_RE = re.compile(r"^_?t(_\d+|_[a-z0-9_]+)?$")


def _name_tokens(name: str) -> set[str]:
    tokens: set[str] = set()
    for part in name.split("_"):
        tokens.update(
            match.lower()
            for match in re.findall(r"[A-Z]+(?![a-z])|[A-Za-z][a-z0-9]*", part)
        )
    return tokens


def _is_provenance_name(name: str) -> bool:
    tokens = _name_tokens(name)
    if tokens & _PROVENANCE_TOKENS:
        return True
    return {"tree", "state"} <= tokens


def _is_sentinel_value(value: str) -> bool:
    return value.strip().lower() in _SENTINEL_VALUES


def _is_timer_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in _TIMER_NAMES or bool(_TIMER_NAME_RE.match(lowered))


def _calls_wall_clock(node: ast.AST) -> bool:
    return any(
        _dotted_name(child.func) == "time.time"
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
    )


def _extract_open_mode(node: ast.Call, is_standalone: bool, is_method: bool) -> str:
    mode = "r"
    if is_standalone and len(node.args) >= 2:
        val = _constant_string(node.args[1])
        mode = val if val is not None else mode
    elif is_method and len(node.args) >= 1:
        val = _constant_string(node.args[0])
        mode = val if val is not None else mode
    mode_kw = _keyword(node, "mode")
    if mode_kw is not None:
        val = _constant_string(mode_kw)
        mode = val if val is not None else mode
    return mode


def _is_text_open(node: ast.Call, name: str | None) -> bool:
    """Return whether a file-open call operates in text mode without encoding."""
    if name == "os.open" or (name is not None and name.endswith(".os.open")):
        return False
    if name in _IMAGE_OPENERS:
        return False  # Pillow/image decoders read bytes; they have no text mode
    if name in {"read_text", "write_text"} or (
        name is not None and name.endswith((".read_text", ".write_text"))
    ):
        return not any(kw.arg == "encoding" for kw in node.keywords)
    is_standalone = name in {"open", "io.open"}
    is_method = name is not None and name.endswith(".open")
    if not (is_standalone or is_method):
        return False
    if "b" in _extract_open_mode(node, is_standalone, is_method):
        return False
    has_encoding = any(kw.arg == "encoding" for kw in node.keywords)
    if not has_encoding and is_standalone and len(node.args) >= 4:
        has_encoding = True
    return not has_encoding


def _is_empty_cache(name: str | None) -> bool:
    return name in {"torch.cuda.empty_cache", "cuda.empty_cache"}


def _is_naive_datetime(node: ast.Call, name: str | None) -> bool:
    if name in {"datetime.utcnow", "datetime.datetime.utcnow"}:
        return True
    if name in {"datetime.now", "datetime.datetime.now"}:
        return len(node.args) == 0 and not any(
            kw.arg in {"tz", "timezone"} for kw in node.keywords
        )
    return False


def _is_insecure_yaml_load(node: ast.Call, name: str | None) -> bool:
    if name != "yaml.load" and not (name is not None and name.endswith(".yaml.load")):
        return False
    loader = _keyword(node, "Loader")
    if loader is None and len(node.args) < 2:
        return True
    loader_name = _dotted_name(loader) if loader is not None else None
    return not (loader_name is not None and "safeloader" in loader_name.lower())


_CHAINED_CALL_ATTRS = frozenset({"read_text", "write_text", "open"})
_IMAGE_OPENERS = frozenset(
    {"Image.open", "PIL.Image.open", "ImageFile.open", "PIL.ImageFile.open"}
)


def _chained_receiver_name(func: ast.AST) -> str | None:
    """Recover a method-qualified file-I/O name whose receiver is an expression.

    ``_dotted_name`` returns ``None`` for ``Path(p).read_text()`` and
    ``(root / "x").open()`` because the receiver is a call or a binop, which
    left every name-gated rule blind to chained constructors and joined paths.
    The recovered name keeps its leading dot (``".open"``) so that
    arity-sensitive predicates keep method semantics: the mode of
    ``Path(p).open("rb")`` is its first argument, not the second one
    ``open(p, "rb")`` uses.
    """
    if isinstance(func, ast.Attribute) and func.attr in _CHAINED_CALL_ATTRS:
        return f".{func.attr}"
    return None


_BLOCKING_SUBPROCESS_CALLS = frozenset(
    {
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
    }
)


def _is_blocking_subprocess(name: str | None) -> bool:
    """Return whether ``name`` is a subprocess entry point that blocks to exit."""
    if name is None:
        return False
    if name in _BLOCKING_SUBPROCESS_CALLS:
        return True
    return any(name.endswith(f".{target}") for target in _BLOCKING_SUBPROCESS_CALLS)


def _len_argument(node: ast.AST) -> str | None:
    """Return the collection named by ``len(x)``, or ``None`` for any other shape."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
        and len(node.args) == 1
    ):
        target = node.args[0]
        if isinstance(target, ast.Name):
            return target.id
        if isinstance(target, ast.Attribute):
            return target.attr
    return None


def _names_collection(node: ast.AST, collection: str) -> bool:
    """Return whether ``node`` mentions ``collection`` by name or attribute."""
    return any(
        (isinstance(child, ast.Name) and child.id == collection)
        or (isinstance(child, ast.Attribute) and child.attr == collection)
        for child in ast.walk(node)
    )


def _vacuous_population_divisor(node: ast.AST) -> str | None:
    """Return the population name of a ``max(len(x), 1)``/``len(x) or 1`` divisor."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "max"
        and len(node.args) == 2
    ):
        head, one = node.args
    elif (
        isinstance(node, ast.BoolOp)
        and isinstance(node.op, ast.Or)
        and len(node.values) == 2
    ):
        head, one = node.values
    else:
        return None
    if not (isinstance(one, ast.Constant) and one.value == 1):
        return None
    return _len_argument(head)


def _is_empty_population_test(test: ast.AST, population: str) -> bool:
    """Return whether ``test`` rejects an empty ``population`` collection."""
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return _names_collection(test.operand, population)
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if _len_argument(test.left) != population:
        return False
    if not isinstance(test.comparators[0], ast.Constant):
        return False
    bound = test.comparators[0].value
    if isinstance(test.ops[0], ast.Eq):
        return bound == 0
    if isinstance(test.ops[0], (ast.Lt, ast.LtE)):
        return bound == 1
    return False


def _rejects_empty_population(function: ast.AST | None, population: str) -> bool:
    """Return whether ``function`` raises or returns early on an empty population."""
    if function is None:
        return False
    for node in ast.walk(function):
        if not isinstance(node, ast.If):
            continue
        if not _is_empty_population_test(node.test, population):
            continue
        if any(
            isinstance(child, (ast.Raise, ast.Return))
            for statement in node.body
            for child in ast.walk(statement)
        ):
            return True
    return False


def _bound_target(function: ast.AST, value_node: ast.AST) -> ast.Name | None:
    """Return the plain name ``value_node`` is assigned to, if any."""
    for child in ast.walk(function):
        if not isinstance(child, (ast.Assign, ast.AnnAssign)) or child.value is None:
            continue
        if not any(node is value_node for node in ast.walk(child.value)):
            continue
        names = child.targets if isinstance(child, ast.Assign) else [child.target]
        if len(names) == 1 and isinstance(names[0], ast.Name):
            return names[0]
    return None


def _iterates_collection(node: ast.AST, collection: str) -> bool:
    """Return whether a loop iterable draws its items from ``collection``."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"zip", "enumerate"}
    ):
        return any(_iterates_collection(argument, collection) for argument in node.args)
    if _len_argument(node) is not None:
        return _len_argument(node) == collection
    return _names_collection(node, collection)


def _consumed_only_in_population_loop(
    function: ast.AST | None, value_node: ast.AST, population: str
) -> bool:
    """Return whether a quotient only ever feeds a loop over its own population.

    ``share = 1 / max(len(prompts), 1)`` in a function that streams one item per
    prompt is inert for an empty bank: the loop body that consumes ``share``
    never runs, so the vacuous divisor cannot disguise an empty population.
    """
    if function is None:
        return False
    target = _bound_target(function, value_node)
    if target is None:
        return False
    loops = [
        child
        for child in ast.walk(function)
        if isinstance(child, (ast.For, ast.AsyncFor))
        and _iterates_collection(child.iter, population)
    ]
    if not loops:
        return False
    return all(
        any(any(inner is user for inner in ast.walk(loop)) for loop in loops)
        for user in ast.walk(function)
        if isinstance(user, ast.Name) and user.id == target.id and user is not target
    )


_DEGENERATE_ERROR_BAR_RE = re.compile(
    r"(stderr|std_err|_se$|^se_|_se_|sem|ci95|_ci$|margin)"
)


def _is_small_sample_test(test: ast.AST) -> bool:
    """Return whether ``test`` is a ``len(x) < 2``/``len(x) <= 1`` small-sample guard."""
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if _len_argument(test.left) is None:
        return False
    bound = test.comparators[0]
    if not (isinstance(bound, ast.Constant) and bound.value in {1, 2}):
        return False
    if isinstance(test.ops[0], ast.Lt):
        return bound.value == 2
    return isinstance(test.ops[0], ast.LtE) and bound.value == 1


def _returns_zero(body: Iterable[ast.stmt]) -> bool:
    """Return whether a branch returns the literal ``0``/``0.0``."""
    return any(
        isinstance(child, ast.Return)
        and isinstance(child.value, ast.Constant)
        and child.value.value == 0
        for statement in body
        for child in ast.walk(statement)
    )


def _degenerate_error_bar(node: ast.FunctionDef) -> ast.If | None:
    """Return the small-sample branch of a function whose name claims an error bar.

    A zero-width error bar is not "no error": it is a claim of perfect certainty
    built from a single draw, which is what lets one sample read as a resolved
    win.  Returning the branch makes the finding point at the collapse.
    """
    if not _DEGENERATE_ERROR_BAR_RE.search(node.name.lower()):
        return None
    for child in ast.walk(node):
        if (
            isinstance(child, ast.If)
            and _is_small_sample_test(child.test)
            and _returns_zero(child.body)
        ):
            return child
    return None


_PROVENANCE_HELPER_RE = re.compile(
    r"(git|commit|sha|hash|rev|version|provenance|identity|tree|status|branch|digest)"
)
_PROVENANCE_SENTINELS = _SENTINEL_VALUES | {"none", "missing", "unset"}


def _is_provenance_helper_name(name: str) -> bool:
    """Return whether a function name claims to compute run provenance."""
    return bool(_PROVENANCE_HELPER_RE.search(name.lower()))


def _provenance_sentinel(value: ast.AST | None) -> str | None:
    """Return the sentinel literal a provenance helper falls back to, if any."""
    literal = _constant_string(value)
    if literal is None or literal.strip().lower() not in _PROVENANCE_SENTINELS:
        return None
    return literal
