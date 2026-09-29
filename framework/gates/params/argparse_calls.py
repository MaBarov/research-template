"""Locally aliased ``add_argument`` calls, so an alias cannot hide a default.

Invariants & Expected State:
    - ``argument_aliases`` collects the plain names one module binds to an
      ``<expr>.add_argument`` method; ``is_flag_call`` accepts both the method
      call and a call through such a name, so the ``add = parser.add_argument``
      idiom is matched exactly like ``parser.add_argument``.
    - Reading is pure: a parsed tree in, a name set out - no file, environment
      or registry access, and no import of the matcher module.
"""

from __future__ import annotations

import ast


def argument_aliases(tree: ast.AST) -> frozenset[str]:
    """Return the local names one module binds to an ``add_argument`` method."""

    names: set[str] = set()
    for node in ast.walk(tree):
        value = getattr(node, "value", None)
        if not (isinstance(value, ast.Attribute) and value.attr == "add_argument"):
            continue
        targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
        names.update(target.id for target in targets if isinstance(target, ast.Name))
    return frozenset(names)


def is_flag_call(node: ast.AST, aliases: frozenset[str]) -> bool:
    """Return whether ``node`` calls ``add_argument``, directly or by alias."""

    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "add_argument"
    return isinstance(func, ast.Name) and func.id in aliases
