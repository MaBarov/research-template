"""AST-based repository mapping and Table-of-Contents indexing."""

from __future__ import annotations

from framework.indexing.formatter import (
    format_markdown_index,
    format_master_index,
    format_sub_index,
)
from framework.indexing.gate import (
    plan_index_files,
    run_index_gate,
    verify_index_freshness,
)
from framework.indexing.scanner import scan_repository

__all__ = [
    "format_markdown_index",
    "format_master_index",
    "format_sub_index",
    "plan_index_files",
    "run_index_gate",
    "scan_repository",
    "verify_index_freshness",
]
