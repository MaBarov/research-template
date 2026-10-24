"""HNS072: a constant-true loop whose body cannot reach an exit.

Thumbnail: Fails a `while True` body that reaches no break, return, raise or exit call.

Invariants & Expected State:
    - The candidate is an ``ast.While`` whose test is the literal ``True`` or
      ``1``. A comparison test (``while running:``) is never a candidate, even
      when its body carries no exit.
    - A ``break`` counts as an exit only when its nearest enclosing loop is the
      candidate; a ``break`` inside a nested ``for``/``while`` leaves the
      candidate running and does not excuse it.
    - ``return``, ``raise``, ``sys.exit(...)``, ``os._exit(...)``, ``exit()``
      and ``quit()`` count anywhere in the body except inside a nested
      function, lambda or class, which runs in a different frame.
    - The candidate's ``else`` clause is not walked (it runs after the loop).
    - Everything else stays silent: the check answers one shape and never
      guesses at bounded-by-condition loops.
"""

from __future__ import annotations

import ast

from framework.gates.antipattern.targets import Finding

MESSAGE = (
    "unbounded loop: constant-true while body reaches no "
    "break/return/raise/exit (arXiv:2607.01641)"
)
_EXIT_NAMES = frozenset({"exit", "quit"})
_EXIT_ATTRS = frozenset({("sys", "exit"), ("os", "_exit")})
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
_NESTED_LOOPS = (ast.For, ast.AsyncFor, ast.While)


def _is_constant_true(test: ast.expr) -> bool:
    """True for the literal constants ``True`` and ``1``."""
    return isinstance(test, ast.Constant) and (test.value is True or test.value == 1)


def _is_exit_call(node: ast.Call) -> bool:
    """True for ``exit()``/``quit()``/``sys.exit()``/``os._exit()``."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in _EXIT_NAMES
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return (func.value.id, func.attr) in _EXIT_ATTRS
    return False


def _exits(body: list[ast.stmt]) -> bool:
    """True when the statement list reaches a break/return/raise/exit call."""
    stack: list[tuple[ast.AST, int]] = [(stmt, 0) for stmt in body]
    while stack:
        node, nested = stack.pop()
        if isinstance(node, _NESTED_SCOPES):
            continue
        if isinstance(node, (ast.Return, ast.Raise)):
            return True
        if isinstance(node, ast.Break) and nested == 0:
            return True
        if isinstance(node, ast.Call) and _is_exit_call(node):
            return True
        next_depth = nested + 1 if isinstance(node, _NESTED_LOOPS) else nested
        stack.extend((child, next_depth) for child in ast.iter_child_nodes(node))
    return False


def check_loop_termination(tree: ast.AST, path: str) -> list[Finding]:
    """Return one HNS072 finding per constant-true loop with no exit."""
    return [
        Finding(path, node.lineno, "HNS072", MESSAGE)
        for node in ast.walk(tree)
        if isinstance(node, ast.While)
        and _is_constant_true(node.test)
        and not _exits(node.body)
    ]
