"""AST visitor for the advisory abstract-cost gate.

Thumbnail: Tracks loop scopes and helper classes to report HNS095-HNS099.

Invariants & Expected State:
    A loop scope records every name and ``self`` attribute its body rebinds, so
    an invariant verdict means no enclosing loop can change the value.
    Findings are deduplicated per (line, code) and carry the cost class they
    belong to in ``evidence``.
    A comprehension's first iterable runs once; its element expression repeats,
    exactly like a loop body.
    Helpers are summarised one level deep: a loop-invariant argument handed to a
    module-local helper that factorizes or synchronizes on it is reported at the
    call site; deeper indirection is a catalogued limit.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

from framework.gates.abstract_cost.patterns import (
    HNS095,
    HNS096,
    HNS097,
    HNS098,
    HNS099,
    MSG_HNS095,
    MSG_HNS096,
    MSG_HNS097,
    MSG_HNS098,
    MSG_HNS099,
    LoopScope,
    class_retentions,
    classify_heavy,
    derivation_operands,
    function_definitions,
    has_random_operand,
    helper_heavy_params,
    host_sync_target,
    is_invariant,
    is_tensor_sync_target,
    matrix_operand,
    pipeline_call_name,
)
from framework.gates.advisory.model import Finding

Comprehension = ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp


class AbstractCostVisitor(ast.NodeVisitor):
    """AST visitor collecting abstract cost-class findings from loop scopes."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []
        self._seen: set[tuple[int, str]] = set()
        self._scopes: list[LoopScope] = []
        self._fn_stack: list[str] = []
        self._helpers: dict[str, dict[int, str]] = {}
        self._conditional_depth: int = 0

    def visit_Module(self, node: ast.Module) -> None:
        """Summarise module-local helpers before walking the bodies."""
        self._helpers = {
            function.name: helper_heavy_params(function)
            for function in function_definitions(node.body)
        }
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Report a retained bank that another method materializes."""
        for retention in class_retentions(node):
            self._report(
                HNS097,
                f"{MSG_HNS097} [{retention.subject} materialized by "
                f"{retention.consumer}()]",
                retention.line,
                "banked capture",
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Enter one function frame for the duration of its body."""
        self._visit_fn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Enter one async function frame for the duration of its body."""
        self._visit_fn(node)

    def _visit_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Push one function frame for the duration of its body."""
        self._fn_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self._fn_stack.pop()

    def _in_loop(self) -> bool:
        """True while an enclosing loop or comprehension repeats this node."""
        return bool(self._scopes)

    def _report(self, code: str, message: str, line: int, evidence: str) -> None:
        """Record one finding, once per line and code."""
        key = (line, code)
        if key in self._seen:
            return
        self._seen.add(key)
        self.findings.append(Finding(self.path, line, code, message, evidence))

    def visit_For(self, node: ast.For) -> None:
        """The iterable runs once; the body repeats under its bound names."""
        self.visit(node.iter)
        self._visit_body(node.body, [node.target, *node.body])
        for statement in node.orelse:
            self.visit(statement)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        """An async for-loop repeats its body exactly like a for-loop."""
        self.visit(node.iter)
        self._visit_body(node.body, [node.target, *node.body])
        for statement in node.orelse:
            self.visit(statement)

    def visit_While(self, node: ast.While) -> None:
        """A while test and body both repeat; nothing in them is invariant."""
        self._visit_body([node.test, *node.body], node.body)

    def _visit_body(
        self, body: Sequence[ast.AST], assigned_from: Sequence[ast.AST]
    ) -> None:
        """Visit a repeated body with one scope of rebound names pushed."""
        scope = LoopScope(
            names=_stored_names(assigned_from), attrs=_stored_attrs(assigned_from)
        )
        self._scopes.append(scope)
        try:
            for statement in body:
                self.visit(statement)
        finally:
            self._scopes.pop()

    def _visit_element_comprehension(self, node: Comprehension) -> None:
        """A comprehension repeats its element expression (a dict: key and value)."""
        bodies: tuple[ast.AST, ...] = (
            (node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,)
        )
        self._visit_comprehension(node, bodies)

    visit_ListComp = _visit_element_comprehension
    visit_SetComp = _visit_element_comprehension
    visit_GeneratorExp = _visit_element_comprehension
    visit_DictComp = _visit_element_comprehension

    def _visit_comprehension(
        self, node: Comprehension, bodies: Sequence[ast.AST]
    ) -> None:
        """The first iterable runs once; the element expressions repeat."""
        first = node.generators[0]
        self.visit(first.iter)
        repeated = [first, *node.generators[1:], *bodies]
        self._visit_body([*first.ifs, *repeated], repeated)

    def visit_Call(self, node: ast.Call) -> None:
        """Classify one call against the abstract cost classes."""
        if self._in_loop() and not self._check_call(node):
            self._check_helper(node)
        self.generic_visit(node)

    def _check_call(self, node: ast.Call) -> bool:
        """Report the first matching direct class for this call."""
        classified = classify_heavy(node)
        if classified is not None:
            return self._report_heavy(node, classified)
        name = pipeline_call_name(node)
        if name is not None:
            self._report(
                HNS098,
                f"{MSG_HNS098} [{name}() per item]",
                node.lineno,
                "per-item pipeline pass",
            )
            return True
        return self._check_sync(node)

    def _report_heavy(self, node: ast.Call, classified: tuple[str, str]) -> bool:
        """Report an invariant factorization or derivation."""
        kind, operation = classified
        if kind == "factorization":
            matrix = matrix_operand(node)
            if matrix is not None and self._invariant(matrix):
                self._report(
                    HNS095,
                    f"{MSG_HNS095} [{operation}() on an invariant matrix]",
                    node.lineno,
                    "loop-invariant factorization",
                )
                return True
            return False
        operands = derivation_operands(node)
        invariant = all(self._invariant(operand) for operand in operands)
        if operands and invariant and not has_random_operand(node):
            self._report(
                HNS096,
                f"{MSG_HNS096} [{operation}() of invariant inputs]",
                node.lineno,
                "loop-invariant derivation",
            )
            return True
        return False

    def _check_sync(self, node: ast.Call) -> bool:
        """Report a host synchronization of a value that cannot change.

        A read inside a conditional is skipped: a branch may run once (a
        first-iteration guard), so the read is not proven to repeat.
        """
        if self._conditional_depth:
            return False
        target = host_sync_target(node)
        if target is None or not is_tensor_sync_target(target):
            return False
        if not self._invariant(target):
            return False
        self._report(
            HNS099,
            f"{MSG_HNS099} [sync read of a stable tensor]",
            node.lineno,
            "invariant host synchronization",
        )
        return True

    def visit_If(self, node: ast.If) -> None:
        """Conditional bodies may run once; track the depth for sync findings."""
        self.visit(node.test)
        self._conditional_depth += 1
        try:
            self.generic_visit(node)
        finally:
            self._conditional_depth -= 1

    def visit_IfExp(self, node: ast.IfExp) -> None:
        """A conditional expression is a conditional context too."""
        self._conditional_depth += 1
        try:
            self.generic_visit(node)
        finally:
            self._conditional_depth -= 1

    def _check_helper(self, node: ast.Call) -> None:
        """Report an invariant argument handed to a heavy module-local helper."""
        if not isinstance(node.func, ast.Name):
            return
        heavy = self._helpers.get(node.func.id)
        if not heavy:
            return
        for index, kind in sorted(heavy.items()):
            if index >= len(node.args):
                continue
            if not self._invariant(node.args[index]):
                continue
            code = HNS095 if kind == "factorization" else HNS099
            message = MSG_HNS095 if kind == "factorization" else MSG_HNS099
            self._report(
                code,
                f"{message} [invariant {kind} inside {node.func.id}()]",
                node.lineno,
                f"loop-invariant {kind} via helper",
            )
            return

    def _invariant(self, node: ast.AST) -> bool:
        """True when no enclosing loop can change anything the node reads."""
        return is_invariant(node, self._scopes)


def _stored_names(nodes: Sequence[ast.AST]) -> frozenset[str]:
    """Return every name one repeated body binds."""
    return frozenset(
        child.id
        for node in nodes
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
    )


def _stored_attrs(nodes: Sequence[ast.AST]) -> frozenset[str]:
    """Return every ``self`` attribute one repeated body rebinds."""
    return frozenset(
        child.attr
        for node in nodes
        for child in ast.walk(node)
        if isinstance(child, ast.Attribute)
        and isinstance(child.ctx, ast.Store)
        and isinstance(child.value, ast.Name)
        and child.value.id == "self"
    )


def analyze_abstract_cost(source: str, path: str) -> list[Finding]:
    """Parse Python source and collect abstract cost-class findings."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as err:
        message = f"unparseable production Python ({err.msg})"
        return [Finding(path, err.lineno or 1, "HNS000", message)]
    visitor = AbstractCostVisitor(path)
    visitor.visit(tree)
    return visitor.findings
