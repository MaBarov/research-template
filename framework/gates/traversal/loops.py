"""Shared loop traversal for the AST gate visitors.

Thumbnail: Visit a for/async-for iterable once and delegate its repeated body.

Invariants & Expected State:
    The loop node is not re-entered by generic_visit; only the iterable is visited
    outside the loop and the body through the subclass's repeated-body hook.
    The for-loop target is offered to the iteration hooks, so a subclass can
    bind names without overriding the loop.
    Subclasses own the loop state and the orelse visit.
"""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod


class RepeatedLoopVisitor(ast.NodeVisitor, ABC):
    """Visit iterables once and hand repeated bodies to the subclass hook."""

    def visit_For(self, node: ast.For) -> None:
        """A for-loop iterable is evaluated once; only the body repeats."""
        self.visit(node.iter)
        names = self._iteration_names(node.target, node.iter)
        self._iteration_begin(names)
        try:
            self._visit_repeated(node, node.body)
        finally:
            self._iteration_end(names)

    def _iteration_names(self, target: ast.AST, iterator: ast.AST) -> list[str]:
        """Return names the loop target binds for the repeated body."""
        return []

    def _iteration_begin(self, names: list[str]) -> None:
        """Hook run before the repeated body with the bound names."""
        return

    def _iteration_end(self, names: list[str]) -> None:
        """Hook run after the repeated body releases the bound names."""
        return

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        """An async for-loop evaluates its iterable once as well."""
        self.visit(node.iter)
        self._visit_repeated(node, node.body)

    @abstractmethod
    def _visit_repeated(
        self, node: ast.For | ast.AsyncFor, body: list[ast.stmt]
    ) -> None:
        """Visit a repeated body in loop context and its orelse outside it."""
        raise NotImplementedError
