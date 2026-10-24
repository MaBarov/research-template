"""Memory bottleneck rule surface: scope predicates and the HNS083-HNS086 checks.

Thumbnail: Re-exports every rule name the AST visitor and the CLI consume from one place.

Invariants & Expected State:
    Import and dunder statements only; no executable behaviour lives here (LMT004).
    ``evidence`` is the leaf member holding the constants, ``Scope`` and the namespace,
    annotation and nograd predicates; ``checks`` holds the five in-loop rules and their
    literal-shape helpers, and imports the evidence it reads through a relative import,
    so the package stays acyclic. Importers may use either this surface or the members.
"""

from __future__ import annotations

from .checks import (
    check_accumulation,
    check_buffer_allocation,
    check_collection_retention,
    check_dynamic_growth,
    check_subscript_store,
)
from .evidence import (
    HNS083,
    HNS084,
    HNS085,
    HNS086,
    MSG_HNS083,
    MSG_HNS084,
    MSG_HNS085,
    MSG_HNS086,
    Scope,
    classify_binding,
    is_nograd_context,
    is_scalar_annotation,
    starts_nograd,
)

__all__ = [
    "HNS083",
    "HNS084",
    "HNS085",
    "HNS086",
    "MSG_HNS083",
    "MSG_HNS084",
    "MSG_HNS085",
    "MSG_HNS086",
    "Scope",
    "check_accumulation",
    "check_buffer_allocation",
    "check_collection_retention",
    "check_dynamic_growth",
    "check_subscript_store",
    "classify_binding",
    "is_nograd_context",
    "is_scalar_annotation",
    "starts_nograd",
]
