"""AST visitor for traversing module trees and detecting memory bottlenecks.

Thumbnail: Traverses AST tracking loop depth and per-function tensor evidence scopes.

Invariants & Expected State:
    Syntax errors fail closed by emitting a HNS000 finding.
    Visitor functions span at most 30 lines and module total stays under 600 lines.
    analyze_memory returns findings for one source string and path.
    Loop context gates every rule: a shape outside an enclosing loop or comprehension
    is a hoisted buffer or a single post-loop join and stays silent.
    Evidence is rebuilt per function frame and never leaks across frames. The tensor
    bindings, the torch-built callables, the scalar annotations, the opaque containers
    and the no-grad state of a callee are unknown, so a helper's locals can never
    justify a finding in its caller: a detached probe output, a float loss and a
    CPU-moved row set returned by helpers all stay silent. That interprocedural limit
    is documented rather than guessed at.
    A no-grad or inference-mode block raises a depth counter over its body and a
    no-grad decorator seeds it for the whole function, because no graph can be
    retained where no graph is built.
    Escape frames exempt an allocation the loop hands back: a returned or yielded
    buffer, directly or through a name the loop returns.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from framework.gates.memory.rules import (
    Scope,
    check_accumulation,
    check_buffer_allocation,
    check_collection_retention,
    check_dynamic_growth,
    check_subscript_store,
    classify_binding,
    is_nograd_context,
    is_scalar_annotation,
    starts_nograd,
)
from framework.gates.memory.targets import Finding
from framework.gates.traversal.loops import RepeatedLoopVisitor

Comprehension = ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp


@dataclass
class _Frame:
    """Mutable per-function evidence; every rule sees a frozen Scope snapshot."""

    tensor_names: set[str] = field(default_factory=set)
    callable_names: set[str] = field(default_factory=set)
    scalar_names: set[str] = field(default_factory=set)
    opaque_names: set[str] = field(default_factory=set)
    nograd: int = 0


class MemoryBottleneckVisitor(RepeatedLoopVisitor):
    """AST visitor collecting in-loop tensor retention and allocation findings."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []
        self._frame = _Frame()
        self._loop_stack: list[ast.AST] = []
        self._escape_stack: list[tuple[frozenset[int], frozenset[str]]] = []
        self._exempt_ids: set[int] = set()

    @property
    def in_loop(self) -> bool:
        """Return True when the current node sits inside a loop or comprehension."""
        return bool(self._loop_stack)

    @property
    def escaping_ids(self) -> frozenset[int]:
        """Return the call nodes whose results leave the enclosing loop."""
        return frozenset().union(*(frame[0] for frame in self._escape_stack))

    @property
    def escaping_names(self) -> frozenset[str]:
        """Return the names whose values leave the enclosing loop."""
        return frozenset().union(*(frame[1] for frame in self._escape_stack))

    def _scope(self) -> Scope:
        """Snapshot the evidence of the innermost function frame."""
        frame = self._frame
        return Scope(
            tensor_names=frozenset(frame.tensor_names),
            callable_names=frozenset(frame.callable_names),
            scalar_names=frozenset(frame.scalar_names),
            opaque_names=frozenset(frame.opaque_names),
            nograd=bool(frame.nograd),
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Rebuild the evidence frame for each function body."""
        self._visit_fn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Rebuild the evidence frame for each async function body."""
        self._visit_fn(node)

    def _visit_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Push one evidence frame: tensor bindings, scalar proofs, no-grad state."""
        previous = self._frame
        self._frame = _Frame(nograd=int(starts_nograd(node)))
        self.generic_visit(node)
        self._frame = previous

    @staticmethod
    def _escape_frame(node: ast.AST) -> tuple[frozenset[int], frozenset[str]]:
        """Return the call ids and names a repeated body hands back to its caller."""
        ids: set[int] = set()
        names: set[str] = set()
        for child in ast.walk(node):
            if not isinstance(child, (ast.Return, ast.Yield, ast.YieldFrom)):
                continue
            if child.value is None:
                continue
            ids.update(id(inner) for inner in ast.walk(child.value))
            names.update(
                part.id for part in ast.walk(child.value) if isinstance(part, ast.Name)
            )
        return frozenset(ids), frozenset(names)

    def _enter_loop(self, node: ast.AST) -> None:
        """Push the loop and escape frames that gate every rule."""
        self._loop_stack.append(node)
        self._escape_stack.append(self._escape_frame(node))

    def _exit_loop(self) -> None:
        """Pop the frames pushed by ``_enter_loop``."""
        self._escape_stack.pop()
        self._loop_stack.pop()

    def visit_While(self, node: ast.While) -> None:
        """A while-loop test re-evaluates every iteration, so it stays in-loop."""
        self._enter_loop(node)
        self.visit(node.test)
        for stmt in node.body:
            self.visit(stmt)
        self._exit_loop()
        for stmt in node.orelse:
            self.visit(stmt)

    def _visit_repeated(
        self, node: ast.For | ast.AsyncFor, body: list[ast.stmt]
    ) -> None:
        """Visit a repeated body in loop context, its orelse outside it."""
        self._enter_loop(node)
        for stmt in body:
            self.visit(stmt)
        self._exit_loop()
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node, node.elt)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node, node.elt)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node, node.elt)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node, node.key, node.value)

    def _visit_comprehension(self, node: Comprehension, *bodies: ast.AST) -> None:
        """The first iterable runs once; guards, later iterables and bodies repeat."""
        first = node.generators[0]
        self.visit(first.iter)
        self.visit(first.target)
        self._enter_loop(node)
        for index, generator in enumerate(node.generators):
            if index:
                self.visit(generator.iter)
                self.visit(generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        for body in bodies:
            self.visit(body)
        self._exit_loop()

    def visit_With(self, node: ast.With) -> None:
        """A no-grad or inference-mode block cannot retain an autograd graph."""
        self._visit_context(node.items, node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        """An async context manager enters the same no-grad state."""
        self._visit_context(node.items, node)

    def _visit_context(self, items: list[ast.withitem], node: ast.AST) -> None:
        """Visit one context block with its no-grad depth raised over the body."""
        depth = sum(1 for item in items if is_nograd_context(item.context_expr))
        self._frame.nograd += depth
        self.generic_visit(node)
        self._frame.nograd -= depth

    def visit_Assign(self, node: ast.Assign) -> None:
        """Evaluate an assignment for retention, growth, escape and binding."""
        self._record_assignment(list(node.targets), node.value, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """An annotated assignment binds values and can prove a non-tensor type."""
        if node.value is not None:
            self._record_assignment([node.target], node.value, node.lineno)
        self._record_annotation(node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Evaluate an augmented assignment for compounded graph accumulation."""
        result = check_accumulation(node, self.in_loop, self._scope())
        if result is not None:
            self._append(result, node.lineno)
        self.generic_visit(node)

    def _record_annotation(self, node: ast.AnnAssign) -> None:
        """Record or withdraw the non-tensor proof carried by an annotation."""
        if not isinstance(node.target, ast.Name):
            return
        if is_scalar_annotation(node.annotation):
            self._frame.scalar_names.add(node.target.id)
        else:
            self._frame.scalar_names.discard(node.target.id)

    def _record_assignment(
        self, targets: list[ast.AST], value: ast.AST, lineno: int
    ) -> None:
        """Collect the findings one assignment can raise, then track its bindings."""
        names = [target.id for target in targets if isinstance(target, ast.Name)]
        self._record_growth(names, value, lineno)
        self._record_store(targets, value, lineno)
        self._record_escaping(names, value)
        self._record_binding(targets, value)

    def _record_growth(self, names: list[str], value: ast.AST, lineno: int) -> None:
        """Flag an in-loop self-referential ``torch.cat``/``torch.stack`` rebind."""
        result = check_dynamic_growth(value, self.in_loop, frozenset(names))
        if result is not None:
            self._append(result, lineno)

    def _record_store(
        self, targets: list[ast.AST], value: ast.AST, lineno: int
    ) -> None:
        """Flag an in-loop subscript store of a provably un-detached tensor."""
        for target in targets:
            if not isinstance(target, ast.Subscript):
                continue
            result = check_subscript_store(
                value, target.value, self.in_loop, self._scope()
            )
            if result is not None:
                self._append(result, lineno)

    def _record_escaping(self, names: list[str], value: ast.AST) -> None:
        """Exempt a buffer bound to a name the enclosing loop returns or yields."""
        if not names or not isinstance(value, ast.Call):
            return
        if any(name in self.escaping_names for name in names):
            self._exempt_ids.add(id(value))

    def _record_binding(self, targets: list[ast.AST], value: ast.AST) -> None:
        """Track what each assigned name holds: a tensor, a callable, or nothing."""
        frame = self._frame
        kind = classify_binding(value, self._scope())
        opaque = isinstance(value, (ast.Call, ast.Attribute, ast.Subscript))
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            frame.tensor_names.discard(target.id)
            frame.callable_names.discard(target.id)
            frame.opaque_names.discard(target.id)
            if opaque:
                frame.opaque_names.add(target.id)
            if kind == "tensor":
                frame.tensor_names.add(target.id)
                frame.scalar_names.discard(target.id)
            elif kind == "callable":
                frame.callable_names.add(target.id)

    def visit_Call(self, node: ast.Call) -> None:
        """Evaluate call expression against the retention and allocation rules."""
        self._record_call_findings(node)
        self.generic_visit(node)

    def _record_call_findings(self, node: ast.Call) -> None:
        """Evaluate one call expression against HNS083 and HNS086."""
        retention = check_collection_retention(node, self.in_loop, self._scope())
        if retention is not None:
            self._append(retention, node.lineno)
        allocation = check_buffer_allocation(
            node, self.in_loop, self.escaping_ids, frozenset(self._exempt_ids)
        )
        if allocation is not None:
            self._append(allocation, node.lineno)

    def _append(self, result: tuple[str, str], lineno: int) -> None:
        """Record one finding from a ``(code, message)`` rule result."""
        code, message = result
        self.findings.append(Finding(self.path, lineno, code, message))


def analyze_memory(source: str, path: str) -> list[Finding]:
    """Parse Python source and collect all memory bottleneck findings."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as err:
        msg = f"unparseable production Python ({err.msg})"
        return [Finding(path, err.lineno or 1, "HNS000", msg)]
    visitor = MemoryBottleneckVisitor(path)
    visitor.visit(tree)
    return visitor.findings
