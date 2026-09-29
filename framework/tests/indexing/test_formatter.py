"""Unit tests for framework.indexing.formatter."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework.indexing.formatter import (
    format_markdown_index,
    format_master_index,
    format_sub_index,
)
from framework.indexing.scanner import ClassEntry, FunctionEntry, ModuleEntry


def _sample_module(rel: str) -> ModuleEntry:
    """Helper to construct a mock ModuleEntry with sample symbols."""
    fn = FunctionEntry(
        name="fit_line",
        args_repr="target: Tensor, alpha: float",
        return_type="Tensor",
        doc_summary="Solve a least-squares fit.",
        line_no=10,
        end_line_no=25,
    )
    cls_entry = ClassEntry(
        name="FitEngine",
        bases=("BaseSolver",),
        doc_summary="Main fit orchestrator.",
        methods=(fn,),
        line_no=5,
        end_line_no=30,
    )
    return ModuleEntry(
        rel_path=rel,
        doc_summary="Module implementing line fits.",
        classes=(cls_entry,),
        functions=(fn,),
        line_count=50,
    )


def test_format_markdown_index_line_ranges(tmp_path: Path) -> None:
    """Verify TOC specifies line ranges and slicing matches section content."""
    m_solver = _sample_module("research/solver/fit.py")
    init_solver = tmp_path / "research" / "solver" / "__init__.py"
    init_solver.parent.mkdir(parents=True)
    init_solver.write_text('"""Explicit solver inputs and projections."""\n')

    md = format_markdown_index([m_solver], repo_root=tmp_path)
    assert "## Table of Contents" in md
    match = re.search(r"\(lines (\d+)–(\d+)\)", md)
    assert match is not None
    start, end = int(match.group(1)), int(match.group(2))
    lines = md.splitlines()
    sliced = lines[start - 1 : end]
    assert sliced[0].startswith("## Package `research/solver`")
    assert "*Contract*: Main fit orchestrator." in "\n".join(sliced)


def test_format_sub_and_master_index(tmp_path: Path) -> None:
    """Verify sub-index local TOC and master index sub-index pointers."""
    m = _sample_module("research/solver/fit.py")
    sub_text, sections = format_sub_index("research", [m], repo_root=tmp_path)
    assert "# Research Sub-Index: `research`" in sub_text
    assert len(sections) == 1
    sec = sections[0]
    assert sec.pkg_rel == "research/solver"

    sub_meta = {
        "path_str": "research/INDEX.md",
        "module_count": 1,
        "symbol_count": 2,
        "sections": sections,
    }
    stats = {"total_modules": 1, "total_classes": 1, "total_functions": 1}
    master = format_master_index([sub_meta], stats)
    assert "# Research Codebase Master Index" in master
    assert "### [`research/INDEX.md`](research/INDEX.md)" in master
    assert f"(lines {sec.start_line}–{sec.end_line} in `research/INDEX.md`)" in master
