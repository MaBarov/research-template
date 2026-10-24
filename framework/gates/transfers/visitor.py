"""AST visitor for traversing module trees and detecting transfer bottlenecks.

Thumbnail: Traverses AST tracking loop, method and provenance contexts to collect findings.

Invariants & Expected State:
    Syntax errors fail closed by emitting a HNS000 finding.
    Visitor functions span at most 30 lines and module total stays under 600 lines.
    analyze_transfers returns findings for one source string and path.
    Device provenance is tracked per scope and only from local proofs: module
    bindings, simple-name assignments, loop-target withdrawal, and the returns
    of module-local functions whose returns all agree. A name never inherits a
    placement from an attribute, a container element or a parameter.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from types import MappingProxyType

from framework.gates.transfers.provenance import (
    UNKNOWN,
    mixing_finding,
    provenance_of,
)
from framework.gates.transfers.provenance.infer import function_returns, module_bindings
from framework.gates.transfers.rules import (
    _is_host_tensor_node,
    check_transfer_node,
    trigger_for,
)
from framework.gates.transfers.targets import Finding
from framework.gates.traversal.loops import RepeatedLoopVisitor

Comprehension = ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp


class TransferBottleneckVisitor(RepeatedLoopVisitor):
    """AST visitor collecting host-device transfer and synchronization findings."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []
        self._loop_stack: list[ast.AST] = []
        self._varying_stack: list[frozenset[str]] = []
        self._fn_stack: list[str] = []
        self._discarded_node: ast.Call | None = None
        self._host_names: set[str] = set()
        self._in_assert: bool = False
        self._module_scope: dict[str, str] = {}
        self._local_scopes: list[dict[str, str]] = []
        self._returns: Mapping[str, str] = MappingProxyType({})

    def visit_Module(self, node: ast.Module) -> None:
        """Pre-scan module bindings and function returns before walking bodies."""
        self._module_scope.update(module_bindings(node.body))
        self._returns = function_returns(node.body, self._module_scope)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """A class body binds its own names; they must not leak to module scope."""
        self._local_scopes.append({})
        try:
            self.generic_visit(node)
        finally:
            self._local_scopes.pop()

    @property
    def current_function(self) -> str:
        """Return the innermost enclosing function or method name."""
        return self._fn_stack[-1] if self._fn_stack else ""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track the innermost enclosing function name."""
        self._visit_fn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track the innermost enclosing async function name."""
        self._visit_fn(node)

    def _visit_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Push one function frame for the duration of its body."""
        self._fn_stack.append(node.name)
        previous_hosts = self._host_names
        self._host_names = set()
        self._local_scopes.append({})
        try:
            self.generic_visit(node)
        finally:
            self._local_scopes.pop()
            self._host_names = previous_hosts
            self._fn_stack.pop()

    def visit_Assert(self, node: ast.Assert) -> None:
        """Assertions in tests verify values and are exempt from transfer stalls."""
        previous = self._in_assert
        self._in_assert = True
        self.generic_visit(node)
        self._in_assert = previous

    def visit_While(self, node: ast.While) -> None:
        """A while-loop test re-evaluates every iteration, so it stays in-loop."""
        names = self._assigned_names(node.body)
        self._forget(names)
        self._loop_stack.append(node)
        self._varying_stack.append(names)
        self.visit(node.test)
        for stmt in node.body:
            self.visit(stmt)
        self._varying_stack.pop()
        self._loop_stack.pop()
        for stmt in node.orelse:
            self.visit(stmt)

    def _visit_repeated(
        self, node: ast.For | ast.AsyncFor, body: list[ast.stmt]
    ) -> None:
        """Visit a repeated body in loop context, its orelse outside it."""
        names = self._bound_names(node.target) | self._assigned_names(body)
        self._forget(names)
        self._loop_stack.append(node)
        self._varying_stack.append(names)
        for stmt in body:
            self.visit(stmt)
        self._varying_stack.pop()
        self._loop_stack.pop()
        for stmt in node.orelse:
            self.visit(stmt)

    @staticmethod
    def _bound_names(target: ast.AST | None) -> frozenset[str]:
        """Return the names one loop target binds, tuple unpacking included."""
        if target is None:
            return frozenset()
        return frozenset(
            child.id for child in ast.walk(target) if isinstance(child, ast.Name)
        )

    @classmethod
    def _assigned_names(cls, body: list[ast.stmt]) -> frozenset[str]:
        """Return the names the body rebinds, so they vary across iterations."""
        names: set[str] = set()
        for stmt in body:
            for node in ast.walk(stmt):
                names |= cls._rebound_names(node)
        return frozenset(names)

    @staticmethod
    def _rebound_names(node: ast.AST) -> set[str]:
        """Names one statement node rebinds; subscript and attribute bases mutate."""
        if isinstance(node, ast.Assign):
            targets: list[ast.AST | None] = list(node.targets)
        elif isinstance(
            node, (ast.AugAssign, ast.AnnAssign, ast.NamedExpr, ast.For, ast.AsyncFor)
        ):
            targets = [node.target]
        elif isinstance(node, ast.withitem):
            targets = [node.optional_vars]
        else:
            return set()
        bound: set[str] = set()
        for target in targets:
            if target is None or isinstance(target, (ast.Subscript, ast.Attribute)):
                continue
            bound |= {
                child.id for child in ast.walk(target) if isinstance(child, ast.Name)
            }
        return bound

    @property
    def enclosing_loop_names(self) -> frozenset[str]:
        """Return every name bound by an enclosing loop or comprehension."""
        if not self._varying_stack:
            return frozenset()
        return frozenset().union(*self._varying_stack)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        """Visit a list comprehension with its element expression repeating."""
        self._visit_comprehension(node, (node.elt,))

    def visit_SetComp(self, node: ast.SetComp) -> None:
        """Visit a set comprehension with its element expression repeating."""
        self._visit_comprehension(node, (node.elt,))

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        """Visit a generator expression with its element expression repeating."""
        self._visit_comprehension(node, (node.elt,))

    def visit_DictComp(self, node: ast.DictComp) -> None:
        """Visit a dict comprehension with key and value expressions repeating."""
        self._visit_comprehension(node, (node.key, node.value))

    def _host_iteration_targets(self, target: ast.AST, iterator: ast.AST) -> list[str]:
        """Return names bound to elements of a host collection in iteration."""
        if (
            isinstance(iterator, ast.Call)
            and isinstance(iterator.func, ast.Attribute)
            and iterator.func.attr in {"items", "values"}
        ):
            iterator = iterator.func.value
        if not isinstance(iterator, ast.Name) or iterator.id not in self._host_names:
            return []
        if isinstance(target, ast.Tuple) and len(target.elts) >= 2:
            val = target.elts[1]
            return [val.id] if isinstance(val, ast.Name) else []
        return [target.id] if isinstance(target, ast.Name) else []

    def _iteration_names(self, target: ast.AST, iterator: ast.AST) -> list[str]:
        """Return host names the loop target binds for the repeated body."""
        return self._host_iteration_targets(target, iterator)

    def _iteration_begin(self, names: list[str]) -> None:
        """Bind the host names for the repeated body."""
        self._host_names.update(names)

    def _iteration_end(self, names: list[str]) -> None:
        """Release the host names after the repeated body."""
        self._host_names.difference_update(names)

    def _visit_comprehension(
        self, node: Comprehension, bodies: tuple[ast.AST, ...]
    ) -> None:
        """The first iterable runs once; every element expression repeats."""
        first = node.generators[0]
        self.visit(first.iter)
        self.visit(first.target)
        names = self._comprehension_names(node.generators)
        self._forget(names)
        self._loop_stack.append(node)
        self._varying_stack.append(names)
        bound_hosts = self._host_iteration_targets(first.target, first.iter)
        for name in bound_hosts:
            self._host_names.add(name)
        self._visit_comprehension_tail(node, first, bodies)
        for name in bound_hosts:
            self._host_names.discard(name)
        self._varying_stack.pop()
        self._loop_stack.pop()

    def _comprehension_names(
        self, generators: list[ast.comprehension]
    ) -> frozenset[str]:
        """Return every name the comprehension's generators bind."""
        return frozenset().union(
            *(self._bound_names(generator.target) for generator in generators)
        )

    def _visit_comprehension_tail(
        self, node: Comprehension, first: ast.comprehension, bodies: tuple[ast.AST, ...]
    ) -> None:
        """Conditions, further iterables and element expressions repeat."""
        for condition in first.ifs:
            self.visit(condition)
        for generator in node.generators[1:]:
            self.visit(generator.iter)
            self.visit(generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        for body in bodies:
            self.visit(body)

    def visit_Expr(self, node: ast.Expr) -> None:
        """A bare call discards its result: it moves state, not data rows."""
        previous = self._discarded_node
        self._discarded_node = node.value if isinstance(node.value, ast.Call) else None
        self.visit(node.value)
        self._discarded_node = previous

    def visit_Assign(self, node: ast.Assign) -> None:
        """Track locals that provably hold a host-built tensor, and only those."""
        self._track_host_targets(list(node.targets), node.value)
        self._track_binding(list(node.targets), node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """An annotated assignment binds a host tensor exactly like a plain one."""
        if node.value is not None:
            self._track_host_targets([node.target], node.value)
            self._track_binding([node.target], node.value)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """Flag arithmetic that provably mixes a host with a device tensor."""
        self._record_mixing(node)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        """Flag a comparison that provably mixes a host with a device tensor."""
        self._record_mixing(node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Flag in-place arithmetic over mixed devices, then forget the target."""
        self._record_mixing(node)
        if isinstance(node.target, ast.Name):
            self._write_name(node.target.id, UNKNOWN)
        self.generic_visit(node)

    def _track_host_targets(self, targets: list[ast.AST], value: ast.AST) -> None:
        """Record simple names bound to a host tensor; withdraw the others.

        Withdrawal matters: ``pool = pool.to(device)`` rebinds the name to a
        device tensor, and the exemption must not outlive that.
        """
        host = _is_host_tensor_node(value, frozenset(self._host_names))
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if host:
                self._host_names.add(target.id)
            else:
                self._host_names.discard(target.id)

    def _name_map(self) -> dict[str, str]:
        """Flatten the active provenance scopes, local scopes shadowing module ones."""
        names = dict(self._module_scope)
        for scope in self._local_scopes:
            names.update(scope)
        return names

    def _write_name(self, name: str, placement: str) -> None:
        """Record one binding in the innermost scope; module scope at top level."""
        scope = self._local_scopes[-1] if self._local_scopes else self._module_scope
        scope[name] = placement

    def _forget(self, names: frozenset[str]) -> None:
        """Invalidate names a loop target or body rebinds on each iteration."""
        for name in names:
            self._write_name(name, UNKNOWN)

    def _track_binding(self, targets: list[ast.AST], value: ast.AST) -> None:
        """Record the placement of simple names; every rebind overwrites it."""
        placement = provenance_of(value, self._name_map(), self._returns)
        for target in targets:
            if isinstance(target, ast.Name):
                self._write_name(target.id, placement)

    def _record_mixing(self, node: ast.expr | ast.stmt) -> None:
        """Record a HNS088 finding when one expression provably mixes devices."""
        result = mixing_finding(node, self._name_map(), self._returns)
        if result is None:
            return
        code, message = result
        in_loop = bool(self._loop_stack)
        self.findings.append(
            Finding(self.path, node.lineno, code, message, trigger_for(code, in_loop))
        )

    def _is_assert_call(self, node: ast.Call) -> bool:
        """Return True for self.assert* test assertions."""
        return (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
            and node.func.attr.startswith("assert")
        )

    def _record_call_findings(self, node: ast.Call) -> None:
        """Evaluate call node and record findings if any transfer rules fire."""
        in_loop = bool(self._loop_stack)
        result = check_transfer_node(
            node,
            in_loop=in_loop,
            fn_name=self.current_function,
            discarded=self._discarded_node is not None and node is self._discarded_node,
            loop_names=self.enclosing_loop_names,
            host_names=frozenset(self._host_names),
        )
        if result is not None:
            code, msg = result
            self.findings.append(
                Finding(self.path, node.lineno, code, msg, trigger_for(code, in_loop))
            )

    def visit_Call(self, node: ast.Call) -> None:
        """Evaluate call expression against transfer bottleneck predicates."""
        if self._is_assert_call(node):
            previous = self._in_assert
            self._in_assert = True
            self.generic_visit(node)
            self._in_assert = previous
            return
        if not self._in_assert:
            self._record_mixing(node)
            self._record_call_findings(node)
        self.generic_visit(node)


def analyze_transfers(source: str, path: str) -> list[Finding]:
    """Parse Python source and collect all transfer bottleneck findings."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as err:
        msg = f"unparseable production Python ({err.msg})"
        return [Finding(path, err.lineno or 1, "HNS000", msg)]
    visitor = TransferBottleneckVisitor(path)
    visitor.visit(tree)
    return visitor.findings
