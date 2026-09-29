"""AST visitor for detecting surrogate distortion anti-patterns.

Thumbnail: AST visitor collecting HNS044, HNS045, and HNS046 findings across module trees.

Invariants & Expected State:
    analyze_distortion returns findings for one source string and path.
    Syntax errors fail closed by emitting a syntax error finding.
    Visitor functions span at most 30 lines and module total stays under 600 lines.
"""

from __future__ import annotations

import ast

from framework.gates.distortion.rules import (
    check_hns044_weight_subtraction,
    check_hns045_pooled_dictcomp,
    check_hns046_ratio_of_means,
    is_low_precision_expr,
    is_mean_node,
)
from framework.gates.distortion.targets import Finding


def _collect_scope_vars(
    fn_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[set[str], set[str]]:
    """Scan function body for low-precision casts and mean assignments."""
    lp_vars: set[str] = set()
    mean_vars: set[str] = set()
    for child in ast.walk(fn_node):
        if not isinstance(child, ast.Assign) or child.value is None:
            continue
        for target in child.targets:
            if not isinstance(target, ast.Name):
                continue
            for val_child in ast.walk(child.value):
                if is_low_precision_expr(val_child):
                    lp_vars.add(target.id)
            if is_mean_node(child.value, mean_vars):
                mean_vars.add(target.id)
    return lp_vars, mean_vars


class DistortionVisitor(ast.NodeVisitor):
    """AST visitor traversing nodes to record distortion findings."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []
        self._current_func: str = ""
        self._lp_vars: set[str] = set()
        self._mean_vars: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Inspect function body tracking local precision and statistics context."""
        prev = (self._current_func, self._lp_vars, self._mean_vars)
        lp, means = _collect_scope_vars(node)
        self._current_func = node.name
        self._lp_vars = lp
        self._mean_vars = means
        self.generic_visit(node)
        self._current_func, self._lp_vars, self._mean_vars = prev

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Inspect async function body tracking local precision context."""
        prev = (self._current_func, self._lp_vars, self._mean_vars)
        lp, means = _collect_scope_vars(node)
        self._current_func = node.name
        self._lp_vars = lp
        self._mean_vars = means
        self.generic_visit(node)
        self._current_func, self._lp_vars, self._mean_vars = prev

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """Inspect binary operations for weight subtractions and ratio-of-means."""
        res44 = check_hns044_weight_subtraction(node, self._lp_vars)
        if res44:
            self.findings.append(Finding(self.path, node.lineno, res44[0], res44[1]))
        res46 = check_hns046_ratio_of_means(node, self._mean_vars)
        if res46:
            self.findings.append(Finding(self.path, node.lineno, res46[0], res46[1]))
        self.generic_visit(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        """Inspect dictionary comprehensions for pooled estimate broadcasts."""
        res45 = check_hns045_pooled_dictcomp(node, self._current_func)
        if res45:
            self.findings.append(Finding(self.path, node.lineno, res45[0], res45[1]))
        self.generic_visit(node)


def analyze_distortion(source: str, path: str) -> list[Finding]:
    """Parse source and return all identified surrogate distortion findings."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as error:
        return [Finding(path, error.lineno or 1, "HNS000", f"syntax error: {error}")]
    visitor = DistortionVisitor(path)
    visitor.visit(tree)
    return visitor.findings
