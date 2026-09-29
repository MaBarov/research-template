"""AST rule predicates for detecting surrogate distortion patterns.

Thumbnail: Predicates for identifying HNS044, HNS045, and HNS046 surrogate anti-patterns.

Invariants & Expected State:
    Public predicates are ``check_hns044_weight_subtraction``,
    ``check_hns045_pooled_dictcomp``, ``check_hns046_ratio_of_means`` (one
    anti-pattern each), with the shared helpers ``is_low_precision_expr``,
    ``references_var`` and ``is_mean_node``.
    Each checker function accepts AST nodes and returns an optional (code, message) tuple.
    Functions stay strictly under 30 lines and avoid side effects.
    Rules stay silent rather than guessing when syntax patterns do not match.
"""

from __future__ import annotations

import ast

from framework.gates.distortion import targets

_LOW_PRECISION_DIVERGENCE = {"bfloat16", "float16", "half", "int8", "int4"}
_MEAN_SYMBOLS = {"mean", "nanmean", "average", "fmean"}


def _is_low_precision_dtype_node(node: ast.AST) -> bool:
    """Return True if node represents a low-precision dtype symbol or string."""
    if (
        isinstance(node, ast.Attribute)
        and node.attr.lower() in _LOW_PRECISION_DIVERGENCE
    ):
        return True
    if isinstance(node, ast.Name) and node.id.lower() in _LOW_PRECISION_DIVERGENCE:
        return True
    return (
        isinstance(node, ast.Constant)
        and str(node.value).lower() in _LOW_PRECISION_DIVERGENCE
    )


def is_low_precision_expr(node: ast.AST) -> bool:
    """Return True if node performs low-precision conversion or quantization."""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr.lower()
            if attr in _LOW_PRECISION_DIVERGENCE:
                return True
            if attr == "to":
                if any(_is_low_precision_dtype_node(a) for a in node.args):
                    return True
                return any(
                    kw.arg == "dtype" and _is_low_precision_dtype_node(kw.value)
                    for kw in node.keywords
                )
        if isinstance(node.func, ast.Name):
            return "quant" in node.func.id.lower()
    return False


def references_var(node: ast.AST, var_names: set[str]) -> bool:
    """Check if node or its sub-call/subscript references any given variable."""
    if not var_names:
        return False
    if isinstance(node, ast.Name):
        return node.id in var_names
    if isinstance(node, (ast.Attribute, ast.Subscript)):
        return references_var(node.value, var_names)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return references_var(node.func.value, var_names)
    return False


def check_hns044_weight_subtraction(
    node: ast.BinOp, low_precision_vars: set[str]
) -> tuple[str, str] | None:
    """Detect weight subtraction preceded by low-precision casting."""
    if not isinstance(node.op, ast.Sub):
        return None
    left_lp = references_var(node.left, low_precision_vars) or is_low_precision_expr(
        node.left
    )
    right_lp = references_var(node.right, low_precision_vars) or is_low_precision_expr(
        node.right
    )
    if left_lp or right_lp:
        msg = (
            "post-quantization delta subtraction; extract deltas before low-precision "
            "casting or preserve the analytical solver proposal"
        )
        return "HNS044", msg
    return None


def _is_pooled_estimate_name(name: str) -> bool:
    """Return True if any identifier component names a pooled estimate."""
    components = name.lower().split("_")
    return any(
        hint in component
        for component in components
        for hint in targets.POOLED_ESTIMATE_HINTS
    )


def _iter_module_name(iter_node: ast.AST) -> str:
    """Extract identifier from dict comprehension generator iterator."""
    if isinstance(iter_node, ast.Name):
        return iter_node.id.lower()
    if isinstance(iter_node, ast.Attribute):
        return iter_node.attr.lower()
    if isinstance(iter_node, ast.Call) and isinstance(iter_node.func, ast.Attribute):
        val = iter_node.func.value
        if isinstance(val, ast.Name):
            return val.id.lower()
        if isinstance(val, ast.Attribute):
            return val.attr.lower()
    return ""


def check_hns045_pooled_dictcomp(
    node: ast.DictComp, func_name: str
) -> tuple[str, str] | None:
    """Detect broadcasting one pooled estimate across members in a dict comp."""
    if func_name in targets.POOLING_EXEMPT_CALLS:
        return None
    if not (isinstance(node.value, ast.Name) and len(node.generators) == 1):
        return None
    if not _is_pooled_estimate_name(node.value.id):
        return None
    iter_name = _iter_module_name(node.generators[0].iter)
    if any(hint in iter_name for hint in targets.MEMBER_NAME_HINTS):
        msg = (
            "in-sample pooled broadcast; assigning one pooled estimate to every "
            "member makes the per-member comparison tautological"
        )
        return "HNS045", msg
    return None


def is_mean_node(node: ast.AST, mean_vars: set[str]) -> bool:
    """Return True if node evaluates a mean statistic or precomputed mean variable."""
    if isinstance(node, ast.Name):
        nid = node.id.lower()
        return (
            node.id in mean_vars
            or nid.startswith(("mean_", "m_"))
            or nid.endswith("_mean")
        )
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _MEAN_SYMBOLS:
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr in _MEAN_SYMBOLS:
            return True
    return False


def _is_mean_ratio(node: ast.AST, mean_vars: set[str]) -> bool:
    """Check if node is a division between two mean evaluations."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return is_mean_node(node.left, mean_vars) and is_mean_node(
            node.right, mean_vars
        )
    return False


def check_hns046_ratio_of_means(
    node: ast.BinOp, mean_vars: set[str]
) -> tuple[str, str] | None:
    """Detect ratio-of-means scalar reduction (1 - mean(a)/mean(b) or ratio - 1)."""
    if not isinstance(node.op, ast.Sub):
        return None
    left_is_one = isinstance(node.left, ast.Constant) and node.left.value in (1, 1.0)
    right_is_one = isinstance(node.right, ast.Constant) and node.right.value in (1, 1.0)
    msg = (
        "un-errored ratio-of-means reduction; compute paired differences "
        "and emit standard error for statistical resolvability"
    )
    if left_is_one and _is_mean_ratio(node.right, mean_vars):
        return "HNS046", msg
    if right_is_one and _is_mean_ratio(node.left, mean_vars):
        return "HNS046", msg
    return None
