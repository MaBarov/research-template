"""Predicates for a log-only handler that lets a placeholder reach the caller.

Thumbnail: Detects a handler that only logs, leaving a pre-set placeholder as the result.

Invariants & Expected State:
    ``placeholder_fallthrough`` names the placeholder only when the handler body
    is nothing but logging calls (no ``raise``, ``return``, assignment or
    failure record), the enclosing function assigned that name a placeholder
    constant before the handler, and the function returns that name after it.
    A handler that re-raises, records the failure in a collection, returns an
    explicit failure value, or catches only the absence family
    (``FileNotFoundError`` and its NotFound-shaped siblings) stays silent,
    because the caller can still tell the failure from a real result.  Only the
    enclosing function's own scope is inspected, so a placeholder assigned or
    returned inside a nested function or lambda never produces a finding, and a
    handler outside any function is never a finding.  The dataflow is a
    line-order may-analysis, not a CFG: a name the function assigns a
    placeholder before the handler, returns after it, and never assigns again in
    between is reported even when an earlier ``try`` body may already have
    replaced the value, so a retry chain that re-runs its own attempt stays a
    finding until the last attempt fails closed too.

    ``optional_input_neutralized`` names the input only when the signature
    advertises it as optional (a PEP 604 ``| None`` or ``Optional[...]``
    annotation) *and* a branch guarding that name returns or assigns a
    structurally valid but empty value -- a ``zeros``/``empty``/``eye`` family
    constructor.  That pairing is what lets a solver report a mode it did not
    run: the substitute is a perfectly valid basis or projection, so every
    shape and orthogonality assertion downstream still passes while the term
    that made the computation constrained is gone.  The constructor is what
    keeps the rule silent on ordinary defaults -- ``if device is None: device =
    torch.device("cpu")`` substitutes a real device, not a neutral one -- and a
    branch that raises stays silent by construction.  A neutral value merely
    present in a branch but neither returned nor assigned is not a finding.

    ``dispatch_fallthrough`` names a mode default only when the same module
    enumerates the literals it dispatches on for that parameter name and the
    default is not among them.  A default is the value a caller gets by saying
    nothing, so a signature that advertises one while the dispatcher matches
    only the other values runs the fall-through branch instead -- or, where a
    pin upstream forces another mode, never reaches the advertised value at all.
    One enumerated set is required before a name is judged, so a single ``==``
    special case beside a general branch stays silent, and a module that merely
    forwards the value, without a comparison of its own, is out of scope.
"""

from __future__ import annotations

import ast
import re
from itertools import pairwise

import framework.gates.antipattern.python_checks

_LOG_METHODS = {
    "warn",
    "warning",
    "info",
    "debug",
    "error",
    "exception",
    "critical",
}

_ABSENCE_EXCEPTIONS = {
    "FileNotFoundError",
    "FileExistsError",
    "IsADirectoryError",
    "NotADirectoryError",
    "ProcessLookupError",
}

_SCOPE_BARRIERS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _is_log_call(node: ast.AST) -> bool:
    """Return whether ``node`` is a printing/logging call."""

    if not isinstance(node, ast.Call):
        return False
    name = framework.gates.antipattern.python_checks._dotted_name(node.func)
    if name is None:
        return False
    if name == "print":
        return True
    return name.rsplit(".", 1)[-1] in _LOG_METHODS


def _log_only(body: list[ast.stmt]) -> bool:
    """Return whether every statement of the handler just logs."""

    return bool(body) and all(
        isinstance(statement, ast.Expr) and _is_log_call(statement.value)
        for statement in body
    )


def _scope_walk(function: ast.AST) -> list[ast.stmt]:
    """Return the function's own statements, never a nested scope's."""

    found: list[ast.stmt] = []
    stack = list(getattr(function, "body", []))
    while stack:
        node = stack.pop()
        if isinstance(node, ast.stmt):
            found.append(node)
        if isinstance(node, _SCOPE_BARRIERS):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return found


def _is_placeholder(node: ast.AST | None) -> bool:
    """Return whether ``node`` is an absence-shaped constant or empty literal."""

    if isinstance(node, ast.Constant):
        value = node.value
        return (
            value is None
            or value is False
            or value is True
            or value == 0
            or value == ""
        )
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return not node.elts
    if isinstance(node, ast.Dict):
        return not node.keys
    return False


def _assignments(function: ast.AST) -> list[tuple[int, set[str], ast.AST | None]]:
    """Return ``(line, names, value)`` for every assignment in the scope."""

    found: list[tuple[int, set[str], ast.AST | None]] = []
    for node in _scope_walk(function):
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = {node.target.id}
        else:
            continue
        found.append((node.lineno, names, node.value))
    return found


def _placeholder_names(function: ast.AST, before_line: int) -> set[str]:
    """Return names assigned a placeholder before ``before_line``."""

    return {
        name
        for line, names, value in _assignments(function)
        if line < before_line and _is_placeholder(value)
        for name in names
    }


def _bare_names(value: ast.AST | None) -> set[str]:
    """Return the bare names a returned expression carries."""

    if isinstance(value, ast.Name):
        return {value.id}
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return {element.id for element in value.elts if isinstance(element, ast.Name)}
    return set()


def _returned_names(function: ast.AST, after_line: int) -> set[str]:
    """Return names the function returns after ``after_line``."""

    names: set[str] = set()
    for node in _scope_walk(function):
        if isinstance(node, ast.Return) and node.lineno > after_line:
            names |= _bare_names(node.value)
    return names


def _assigned_names(function: ast.AST, after_line: int) -> set[str]:
    """Return names the function assigns again after ``after_line``."""

    return {
        name
        for line, names, _value in _assignments(function)
        if line > after_line
        for name in names
    }


def _catches_only_absence(handler: ast.ExceptHandler) -> bool:
    """Return whether the handler catches only documented absence errors."""

    if handler.type is None:
        return False
    caught = {
        child.id for child in ast.walk(handler.type) if isinstance(child, ast.Name)
    }
    return bool(caught) and caught <= _ABSENCE_EXCEPTIONS


def placeholder_fallthrough(
    handler: ast.ExceptHandler, function: ast.AST
) -> str | None:
    """Return the placeholder a log-only handler lets reach the caller."""

    if _catches_only_absence(handler) or not _log_only(handler.body):
        return None
    after_line = handler.body[-1].end_lineno or handler.lineno
    repaired = _assigned_names(function, after_line)
    carried = (
        _placeholder_names(function, handler.lineno)
        & _returned_names(function, after_line)
    ) - repaired
    return min(carried) if carried else None


# Constructors that build a structurally void or zeroed object. Identity and
# all-ones objects are deliberately *excluded*: they have full content and
# select everything, so substituting one is a default selection rather than a
# vanished constraint. `matrix = None -> torch.eye(width)` in a projection
# helper is that shape - a documented whole-space default, not a dropped bound.
_NEUTRAL_CTORS = {
    "empty",
    "empty_like",
    "zeros",
    "zeros_like",
}


def _admits_none(annotation: ast.AST) -> bool:
    """Return whether the annotation makes ``None`` an admissible value."""

    for node in ast.walk(annotation):
        if (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.BitOr)
            and any(
                isinstance(part, ast.Constant) and part.value is None
                for part in ast.walk(node)
            )
        ):
            return True
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "Optional"
        ):
            return True
    return False


def _optional_inputs(function: ast.AST) -> set[str]:
    """Return parameter names the signature advertises as optional.

    An annotation admitting ``None`` is the explicit form and a bare ``= None``
    default is the implicit one; they carry the same risk, so both count.
    """

    def _is_none_default(node: ast.AST | None) -> bool:
        return isinstance(node, ast.Constant) and node.value is None

    args = getattr(function, "args", None)
    if args is None:
        return set()
    positional = [*args.posonlyargs, *args.args]
    names = {
        p.arg
        for p in [*positional, *args.kwonlyargs]
        if p.annotation is not None and _admits_none(p.annotation)
    }
    offset = max(len(positional) - len(args.defaults), 0)
    for p, d in zip(positional[offset:], args.defaults, strict=True):
        if _is_none_default(d):
            names.add(p.arg)
    for p, d in zip(args.kwonlyargs, args.kw_defaults or [], strict=False):
        if _is_none_default(d):
            names.add(p.arg)
    return names


def _neutral_value(node: ast.AST | None) -> bool:
    """Return whether the node builds a structurally valid but empty value."""

    if node is None:
        return False
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        name = getattr(func, "attr", None) or getattr(func, "id", "")
        if name in _NEUTRAL_CTORS:
            return True
    return False


def _branches_to_neutral(body: list[ast.stmt]) -> bool:
    """Return whether the branch returns or assigns such a value."""

    return any(
        (isinstance(s, ast.Return) and _neutral_value(s.value))
        or (isinstance(s, (ast.Assign, ast.AnnAssign)) and _neutral_value(s.value))
        for s in body
    )


def optional_input_neutralized(function: ast.AST) -> tuple[ast.If, str] | None:
    """Return the branch and input whose absence becomes a valid-but-empty value."""

    optional = _optional_inputs(function)
    if not optional:
        return None
    for node in _scope_walk(function):
        if not isinstance(node, ast.If):
            continue
        guarded = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
        hit = guarded & optional
        if hit and (
            _branches_to_neutral(node.body) or _branches_to_neutral(node.orelse)
        ):
            return node, min(hit)
    return None


# A mode token is an identifier-shaped lowercase word: the kind of string a
# signature advertises as a dispatch key, not a path, a message or a sentence.
_MODE_TOKEN = re.compile(r"[a-z][a-z0-9_]*\Z")

# ``frozenset({"a", "b"})`` enumerates the same values as the bare set literal.
_ENUMERATING_CTORS = {"frozenset", "set", "tuple", "list"}


def _string_constant(node: ast.AST) -> str | None:
    """Return the node's string value, or ``None`` when it is not one."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _enumerated_strings(node: ast.AST) -> set[str]:
    """Return the string constants a set/tuple/list literal enumerates."""

    if isinstance(node, ast.Call):
        if not node.args or getattr(node.func, "id", "") not in _ENUMERATING_CTORS:
            return set()
        node = node.args[0]
    if not isinstance(node, (ast.Set, ast.Tuple, ast.List)):
        return set()
    values = [_string_constant(element) for element in node.elts]
    if not all(values):
        return set()
    return {value for value in values if value is not None}


def _comparison_sides(node: ast.Compare) -> list[tuple[str, ast.AST]]:
    """Return ``(name, matched operand)`` for both comparison orientations."""

    sides: list[tuple[str, ast.AST]] = []
    for left, right in pairwise([node.left, *node.comparators]):
        for named, other in ((left, right), (right, left)):
            if isinstance(named, ast.Name):
                sides.append((named.id, other))
    return sides


def _compared_literals(tree: ast.Module) -> dict[str, set[str]]:
    """Return the string literals each name is matched against, with set evidence.

    A name counts as dispatched only when at least one comparison enumerates two
    or more string constants; its single-literal comparisons are folded into the
    same handled set, because ``mode == "sdp"`` in a helper is a branch that
    claims that value just as a set membership does.
    """

    handled: dict[str, set[str]] = {}
    enumerated: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for name, operand in _comparison_sides(node):
            literals = _enumerated_strings(operand)
            if len(literals) > 1:
                handled.setdefault(name, set()).update(literals)
                enumerated.add(name)
                continue
            literal = _string_constant(operand)
            if literal is not None:
                handled.setdefault(name, set()).add(literal)
    return {name: handled[name] for name in enumerated}


def _signature_defaults(node: ast.AST) -> list[tuple[ast.AST, ast.AST]]:
    """Return the ``(argument, default)`` pairs a signature declares explicitly."""

    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    positional = [*node.args.posonlyargs, *node.args.args]
    offset = max(len(positional) - len(node.args.defaults), 0)
    paired = list(zip(positional[offset:], node.args.defaults, strict=True))
    keyword = zip(node.args.kwonlyargs, node.args.kw_defaults or [], strict=False)
    return [*paired, *((a, d) for a, d in keyword if d is not None)]


def _mode_defaults(tree: ast.Module) -> list[tuple[ast.AST, str, str]]:
    """Return ``(argument, name, default)`` for every mode default in the module."""

    found: list[tuple[ast.AST, str, str]] = []
    for node in ast.walk(tree):
        for argument, default in _signature_defaults(node):
            value = _string_constant(default)
            if value is None or _MODE_TOKEN.fullmatch(value) is None:
                continue
            found.append((argument, argument.arg, value))
    return found


def _dispatch_message(name: str, default: str, handled: set[str]) -> str:
    """Return the finding text for one mode default that no branch matches."""

    matched = ", ".join(sorted(handled))
    return (
        f"mode parameter {name!r} defaults to {default!r} but no branch in this "
        f"module matches it (matched: {matched}); the value a caller gets by "
        "saying nothing falls through to the branch that handles everything else"
    )


def dispatch_fallthrough(tree: ast.Module) -> list[tuple[ast.AST, str]]:
    """Return mode defaults the module's own enumerated dispatch never matches.

    A signature that advertises a mode default promises the behaviour of the
    branch that runs when the caller says nothing, so a module that enumerates
    the values it handles must enumerate that default too.  When it does not, the
    default silently takes the fall-through branch -- or, where a pin upstream
    forces a mode, the advertised branch is unreachable and the setting is inert.
    """

    handled = _compared_literals(tree)
    findings: list[tuple[ast.AST, str]] = []
    for node, name, default in _mode_defaults(tree):
        if name not in handled or default in handled[name]:
            continue
        findings.append((node, _dispatch_message(name, default, handled[name])))
    return findings
