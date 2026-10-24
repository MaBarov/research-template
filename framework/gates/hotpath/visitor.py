"""AST visitor for the advisory hot-path gate.

Thumbnail: Tracks loops, functions and proven tensor names to collect HNS089-HNS094.

Invariants & Expected State:
    Loop and function contexts are stack-based, and a comprehension repeats its
    element expression exactly like a loop body.
    Tensor names are per function scope and only from local proofs; a rebind or
    a loop target withdraws the name.
    A finding is emitted once per (line, code), so nested expressions cannot
    multiply the same defect.
    A function nested inside a step function inherits its hot context.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

from framework.gates.advisory.model import Finding
from framework.gates.hotpath.evidence import (
    HNS089,
    HNS090,
    HNS091,
    HNS092,
    HNS093,
    HNS094,
    MSG_HNS089,
    MSG_HNS090,
    MSG_HNS091,
    MSG_HNS092,
    MSG_HNS093,
    MSG_HNS094,
    has_device_keyword,
    hot_function_names,
    is_anomaly_enabled,
    is_device_move,
    is_factory_call,
    is_loader_call,
    is_tensor_annotation,
    is_tensor_expression,
    loader_gaps,
    synchronizes,
    synchronizes_on_tensor,
)
from framework.gates.transfers.rules import is_payload_method_name

Comprehension = ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp


class HotpathVisitor(ast.NodeVisitor):
    """AST visitor collecting GPU/CPU hot-path findings from local proofs."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []
        self._seen: set[tuple[int, str]] = set()
        self._loop_names: list[frozenset[str]] = []
        self._tensor_scopes: list[set[str]] = []
        self._hot_scopes: list[bool] = []
        self._fn_stack: list[str] = []
        self._hot_names: frozenset[str] = frozenset()

    def visit_Module(self, node: ast.Module) -> None:
        """Pre-scan the module's training-step functions before walking bodies."""
        self._hot_names = hot_function_names(node.body)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Enter one function with its hot context and tensor-annotated arguments."""
        self._visit_fn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Enter one async function with its hot context and annotations."""
        self._visit_fn(node)

    def _visit_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Push one function frame for the duration of its body."""
        inherited = bool(self._hot_scopes) and self._hot_scopes[-1]
        hot = inherited or node.name in self._hot_names
        annotated = [
            argument.arg
            for argument in [*node.args.args, *node.args.kwonlyargs]
            if is_tensor_annotation(argument.annotation)
        ]
        self._hot_scopes.append(hot)
        self._tensor_scopes.append(set(annotated))
        self._fn_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self._fn_stack.pop()
            self._tensor_scopes.pop()
            self._hot_scopes.pop()

    def _current_function(self) -> str:
        """Return the innermost enclosing function or method name."""
        return self._fn_stack[-1] if self._fn_stack else ""

    def _in_loop(self) -> bool:
        """Return True while a loop or comprehension repeats the current node."""
        return bool(self._loop_names)

    def _in_hot_function(self) -> bool:
        """Return True inside a training-step function."""
        return bool(self._hot_scopes) and self._hot_scopes[-1]

    def _tensor_names(self) -> frozenset[str]:
        """Return the tensor names proved in the active function scopes."""
        return frozenset().union(*self._tensor_scopes)

    def _loop_names_union(self) -> frozenset[str]:
        """Return every name bound by an enclosing loop or comprehension."""
        return frozenset().union(*self._loop_names)

    def _report(self, code: str, message: str, node: ast.expr | ast.stmt) -> None:
        """Record one finding, once per line and code."""
        key = (node.lineno, code)
        if key in self._seen:
            return
        self._seen.add(key)
        self.findings.append(Finding(self.path, node.lineno, code, message))

    def _forget(self, names: frozenset[str]) -> None:
        """Withdraw tensor-ness from names a loop rebinds each iteration."""
        if not self._tensor_scopes:
            return
        self._tensor_scopes[-1].difference_update(names)

    def visit_For(self, node: ast.For) -> None:
        """The iterable runs once; the body repeats with the target names bound."""
        self.visit(node.iter)
        self._visit_body(node.body, self._target_names(node.target))
        for statement in node.orelse:
            self.visit(statement)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        """An async for-loop repeats its body exactly like a for-loop."""
        self.visit(node.iter)
        self._visit_body(node.body, self._target_names(node.target))
        for statement in node.orelse:
            self.visit(statement)

    def visit_While(self, node: ast.While) -> None:
        """A while body repeats; its names cannot be proven from the test alone."""
        self._visit_body([node.test, *node.body], frozenset())
        for statement in node.orelse:
            self.visit(statement)

    def _visit_body(self, body: Sequence[ast.AST], names: frozenset[str]) -> None:
        """Visit a repeated body with the loop's bound names in scope."""
        self._loop_names.append(names)
        self._forget(names)
        try:
            for statement in body:
                self.visit(statement)
        finally:
            self._loop_names.pop()

    @staticmethod
    def _target_names(target: ast.AST) -> frozenset[str]:
        """Return the names one loop target binds, tuple unpacking included."""
        return frozenset(
            child.id for child in ast.walk(target) if isinstance(child, ast.Name)
        )

    def visit_ListComp(self, node: ast.ListComp) -> None:
        """A list comprehension repeats its element expression."""
        self._visit_comprehension(node, (node.elt,))

    def visit_SetComp(self, node: ast.SetComp) -> None:
        """A set comprehension repeats its element expression."""
        self._visit_comprehension(node, (node.elt,))

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        """A generator expression repeats its element expression."""
        self._visit_comprehension(node, (node.elt,))

    def visit_DictComp(self, node: ast.DictComp) -> None:
        """A dict comprehension repeats its key and value expressions."""
        self._visit_comprehension(node, (node.key, node.value))

    def _visit_comprehension(
        self, node: Comprehension, bodies: tuple[ast.AST, ...]
    ) -> None:
        """The first iterable runs once; every element expression repeats."""
        first = node.generators[0]
        self.visit(first.iter)
        names = frozenset().union(
            *(self._target_names(generator.target) for generator in node.generators)
        )
        self._visit_body([*first.ifs, *node.generators[1:], *bodies], names)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Track names bound to a provably tensor-valued expression."""
        tensor = is_tensor_expression(node.value) or (
            isinstance(node.value, ast.Name) and node.value.id in self._tensor_names()
        )
        for target in node.targets:
            if isinstance(target, ast.Name) and self._tensor_scopes:
                if tensor:
                    self._tensor_scopes[-1].add(target.id)
                else:
                    self._tensor_scopes[-1].discard(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """An annotated assignment binds a tensor exactly like a plain one."""
        if (
            node.value is None
            or not isinstance(node.target, ast.Name)
            or not self._tensor_scopes
        ):
            self.generic_visit(node)
            return
        if is_tensor_expression(node.value):
            self._tensor_scopes[-1].add(node.target.id)
        else:
            self._tensor_scopes[-1].discard(node.target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Evaluate one call against the hot-path rules, then descend."""
        self._check_factory_move(node)
        self._check_conversion(node)
        self._check_step_sync(node)
        if is_anomaly_enabled(node):
            self._report(HNS092, MSG_HNS092, node)
        if is_loader_call(node):
            gaps = loader_gaps(node)
            if gaps:
                self._report(HNS094, f"{MSG_HNS094} [missing: {', '.join(gaps)}]", node)
        self.generic_visit(node)

    def _check_factory_move(self, node: ast.Call) -> None:
        """A factory allocated on the host and then moved is two allocations."""
        if not isinstance(node.func, ast.Attribute) or not is_device_move(node):
            return
        source = node.func.value
        if (
            isinstance(source, ast.Call)
            and is_factory_call(source)
            and not has_device_keyword(source)
        ):
            self._report(HNS089, MSG_HNS089, node)

    def _check_conversion(self, node: ast.Call) -> None:
        """A host conversion inside a loop pays the round trip every pass."""
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "numpy":
            return
        if not self._in_loop():
            return
        if is_payload_method_name(self._current_function()):
            return
        self._report(HNS090, MSG_HNS090, node)

    def _check_step_sync(self, node: ast.Call) -> None:
        """A synchronization inside a step function stalls the pipeline."""
        if not self._in_hot_function() or self._in_loop():
            return
        if synchronizes(node) or synchronizes_on_tensor(node, self._tensor_names()):
            self._report(HNS091, MSG_HNS091, node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Per-element indexing of a proven tensor inside a loop."""
        if isinstance(node.value, ast.Name) and node.value.id in self._tensor_names():
            index_names = {
                child.id
                for child in ast.walk(node.slice)
                if isinstance(child, ast.Name)
            }
            if (
                self._is_scalar_index(node.slice)
                and index_names & self._loop_names_union()
            ):
                self._report(HNS093, MSG_HNS093, node)
        self.generic_visit(node)

    @classmethod
    def _is_scalar_index(cls, index: ast.AST) -> bool:
        """A scalar index selects one element; a slice selects a block and a
        tensor index is advanced indexing, which is one vectorized op."""
        if isinstance(index, (ast.Name, ast.Constant)):
            return not (isinstance(index, ast.Constant) and index.value is Ellipsis)
        if isinstance(index, ast.UnaryOp):
            return cls._is_scalar_index(index.operand)
        if isinstance(index, ast.BinOp):
            return cls._is_scalar_index(index.left) and cls._is_scalar_index(
                index.right
            )
        if isinstance(index, ast.Tuple):
            return all(cls._is_scalar_index(element) for element in index.elts)
        return False


def analyze_hotpath(source: str, path: str) -> list[Finding]:
    """Parse Python source and collect all hot-path findings."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as err:
        message = f"unparseable production Python ({err.msg})"
        return [Finding(path, err.lineno or 1, "HNS000", message)]
    visitor = HotpathVisitor(path)
    visitor.visit(tree)
    return visitor.findings
