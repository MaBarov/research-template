"""Execution-sink anti-patterns for the production gate (HNS081, HNS082).

Thumbnail: Flags unquoted shell-command interpolation and silent broad-except handlers.

Invariants & Expected State:
    ``check_shell_injection`` fires once per call that reaches a shell sink with
    a command string the shell will re-parse: ``os.system(...)``, or a
    ``subprocess`` ``Popen``/``run``/``call``/``check_call``/``check_output``
    that passes ``shell=True``.  The command argument is dangerous only when it
    composes interpolated data into the string -- an f-string whose formatted
    value is not a direct ``shlex.quote`` call, a ``"..." % value`` formatting,
    or a ``"..." + value`` concatenation with a non-constant operand.  A
    constant command string, an argv list, and an f-string whose every
    formatted value is ``shlex.quote``-wrapped all stay silent.

    ``check_silent_exception_swallowing`` fires on a handler that catches
    everything -- a bare ``except:`` or ``except Exception``/``except
    BaseException`` -- and then does nothing observable: its body is exactly one
    ``pass`` or one ``return`` of ``None``/``False``/``""``, with no logging,
    print, warn or traceback call anywhere in the body.  A narrow exception
    family, a handler that records the failure, or a handler that re-raises is
    never a finding.  The rule is scoped to production code: a path under
    ``tests/``, a ``test_``-named module, or any ``__init__.py`` is skipped, so
    fixtures and package wiring stay out of scope.
"""

from __future__ import annotations

import ast
from pathlib import Path

from framework.gates.antipattern.targets import Finding

_INJECTION_MESSAGE = (
    "command string composed with unquoted interpolation passed to shell "
    "execution; susceptible to shell injection"
)
_SWALLOW_MESSAGE = (
    "broad exception handler silently suppresses failure with bare pass/empty "
    "return; masks execution crashes"
)

_SHELL_SUBPROCESS = frozenset({"Popen", "run", "call", "check_call", "check_output"})
_BROAD_EXCEPTIONS = frozenset({"Exception", "BaseException"})
_LOG_MARKERS = ("log", "logger", "print", "warn", "traceback")


def _is_named(value: ast.AST, name: str) -> bool:
    """Return whether ``value`` is the bare name ``name`` (``os``/``subprocess``)."""
    return isinstance(value, ast.Name) and value.id == name


def _shell_true(node: ast.Call) -> bool:
    """Return whether the call passes a literal ``shell=True`` keyword."""
    for keyword in node.keywords:
        if keyword.arg == "shell":
            return (
                isinstance(keyword.value, ast.Constant) and keyword.value.value is True
            )
    return False


def _shell_sink(node: ast.Call) -> bool:
    """Return whether ``node`` reaches a shell that re-parses a command string."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr == "system" and _is_named(func.value, "os"):
        return True
    if func.attr in _SHELL_SUBPROCESS and _is_named(func.value, "subprocess"):
        return _shell_true(node)
    return False


def _is_shlex_quote(node: ast.AST) -> bool:
    """Return whether ``node`` is a direct ``shlex.quote(...)`` call."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "quote"
        and _is_named(node.func.value, "shlex")
    )


def _unquoted_value(part: ast.FormattedValue) -> bool:
    """Return whether a formatted value reaches the shell without quoting."""
    return not _is_shlex_quote(part.value)


def _concat_operands(node: ast.AST) -> list[ast.AST]:
    """Return the flattened operands of a chained ``+`` expression."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _concat_operands(node.left) + _concat_operands(node.right)
    return [node]


def _concat_with_variable(node: ast.BinOp) -> bool:
    """Return whether a ``+`` chain mixes string text with a non-constant."""
    operands = _concat_operands(node)
    has_text = any(
        isinstance(item, ast.Constant) and isinstance(item.value, str)
        for item in operands
    )
    has_variable = any(not isinstance(item, ast.Constant) for item in operands)
    return has_text and has_variable


def _has_interpolation(node: ast.AST) -> bool:
    """Return whether the command expression interpolates unquoted data."""
    if isinstance(node, ast.JoinedStr):
        parts = (p for p in node.values if isinstance(p, ast.FormattedValue))
        return any(_unquoted_value(part) for part in parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _concat_with_variable(node)
    return False


def check_shell_injection(tree: ast.AST, path: str) -> list[Finding]:
    """Return findings for a shell sink fed an unquoted interpolated command."""
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _shell_sink(node):
            continue
        command = node.args[0] if node.args else None
        if command is not None and _has_interpolation(command):
            findings.append(Finding(path, node.lineno, "HNS081", _INJECTION_MESSAGE))
    return findings


def _is_test_path(path: str) -> bool:
    """Return whether ``path`` is test, fixture or package-wiring code."""
    normalized = Path(path).as_posix()
    if normalized.endswith("__init__.py"):
        return True
    if normalized.startswith("tests/") or "/tests/" in normalized:
        return True
    return "test_" in Path(normalized).name


def _call_marker(func: ast.AST) -> str | None:
    """Return the textual name of a called function or attribute."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _has_logging(body: list[ast.stmt]) -> bool:
    """Return whether the handler body calls anything that records the failure."""
    for statement in body:
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call):
                continue
            name = _call_marker(node.func)
            if name is not None and any(marker in name for marker in _LOG_MARKERS):
                return True
    return False


def _empty_return(value: ast.AST | None) -> bool:
    """Return whether a ``return`` carries a falsy placeholder the caller can't tell apart."""
    if value is None:
        return True
    if not isinstance(value, ast.Constant):
        return False
    if value.value is None or value.value == "":
        return True
    return isinstance(value.value, bool) and value.value is False


def _silent_body(body: list[ast.stmt]) -> bool:
    """Return whether the handler body only swallows the failure."""
    if len(body) != 1 or _has_logging(body):
        return False
    statement = body[0]
    if isinstance(statement, ast.Pass):
        return True
    return isinstance(statement, ast.Return) and _empty_return(statement.value)


def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
    """Return whether the handler catches every exception."""
    if handler.type is None:
        return True
    return isinstance(handler.type, ast.Name) and handler.type.id in _BROAD_EXCEPTIONS


def check_silent_exception_swallowing(tree: ast.AST, path: str) -> list[Finding]:
    """Return findings for a broad handler that silently suppresses failure."""
    if _is_test_path(path):
        return []
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or not _is_broad_handler(node):
            continue
        if _silent_body(node.body):
            findings.append(Finding(path, node.lineno, "HNS082", _SWALLOW_MESSAGE))
    return findings
