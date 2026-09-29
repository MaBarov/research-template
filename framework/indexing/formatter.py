"""Format scanned module symbols into a dynamic Table-of-Contents index.

Role & Architecture:
    Transforms scanned ModuleEntry AST records into structured Markdown indexes,
    sub-indices, clickable file links, and Table-of-Contents hierarchies.

Invariants & Expected State:
    - Pure Formatting: Accepts immutable dataclass sequences, returns Markdown text.
    - Partitioning: Automatically splits indexes when exceeding max_lines threshold.
    - PEP 257 Compliance: Formats Tier-1 docstring thumbnails as module purpose summaries.

Failure Modes & Prohibited Patterns:
    - Missing package __init__.py returns empty docstrings without raising.
    - Prohibited: Never execute inspected code or mutate input dataclasses.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framework import harness
from framework.indexing.scanner import ClassEntry, FunctionEntry, ModuleEntry


@dataclass(frozen=True)
class SectionMeta:
    """Metadata and line numbers for an indexed package section."""

    pkg_rel: str
    doc: str
    start_line: int
    end_line: int
    module_count: int
    symbol_count: int


def _slugify(text: str) -> str:
    """Convert header text to a markdown anchor slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s_-]", "", text.lower())
    return re.sub(r"[\s_]+", "-", cleaned.strip("-"))


def _link(rel: str, line: int, end: int, label: str) -> str:
    """Construct a clickable markdown link targeting exact source lines."""
    return f"[`{label}`]({rel}#L{line}-L{end})"


def _format_function(f: FunctionEntry, rel: str) -> list[str]:
    """Format a single function entry with its signature and contract."""
    async_prefix = "async " if f.is_async else ""
    ret_annot = f" -> {f.return_type}" if f.return_type else ""
    sig = f"{async_prefix}{f.name}({f.args_repr}){ret_annot}"
    link = _link(rel, f.line_no, f.end_line_no, sig)
    lines = [f"  * {link}"]
    if f.doc_summary:
        lines.append(f"    * *Contract*: {f.doc_summary}")
    return lines


def _format_class(c: ClassEntry, rel: str) -> list[str]:
    """Format a class entry, its inheritance bases, and public methods."""
    bases_repr = f"({', '.join(c.bases)})" if c.bases else ""
    label = f"class {c.name}{bases_repr}"
    link = f"[`{label}`]({rel}#L{c.line_no}-L{c.end_line_no})"
    lines = [f"  * {link}"]
    if c.doc_summary:
        lines.append(f"    * *Contract*: {c.doc_summary}")
    for method in c.methods:
        m_sig = f"{c.name}.{method.name}({method.args_repr})"
        if method.return_type:
            m_sig += f" -> {method.return_type}"
        m_link = _link(rel, method.line_no, method.end_line_no, m_sig)
        lines.append(f"    * {m_link}")
        if method.doc_summary:
            lines.append(f"      * *Contract*: {method.doc_summary}")
    return lines


def _format_module(m: ModuleEntry) -> list[str]:
    """Format an entire module section with its exports."""
    lines = [f"- [`{m.rel_path}`]({m.rel_path}) ({m.line_count} lines)"]
    if m.doc_summary:
        lines.append(f"  * *Module Purpose*: {m.doc_summary}")
    for cls_entry in m.classes:
        lines.extend(_format_class(cls_entry, m.rel_path))
    for fn_entry in m.functions:
        lines.extend(_format_function(fn_entry, m.rel_path))
    return lines


def _resolve_package_docstring(pkg_dir: Path) -> str:
    """Extract docstring from package __init__.py dynamically from filesystem."""
    init_path = pkg_dir / "__init__.py"
    if not init_path.is_file():
        return ""
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"))
        doc = ast.get_docstring(tree)
        if doc:
            first_para = doc.strip().split("\n\n")[0].replace("\n", " ").strip()
            return first_para[:160]
    except (SyntaxError, OSError, ValueError):
        return ""
    return ""


def _format_header(
    title: str, subtitle: str, n_mods: int, n_cls: int, n_fns: int
) -> list[str]:
    """Render standard Markdown header and statistics banner."""
    return [
        f"# {title}",
        "",
        "> [!NOTE]",
        f"> {subtitle}",
        "",
        (
            f"**Repository Statistics**: {n_mods} modules | "
            f"{n_cls} classes | {n_fns} public functions."
        ),
        "",
    ]


def _render_package_section(
    pkg_rel: str, modules: list[ModuleEntry], repo_root: Path | None
) -> list[str]:
    """Render a dynamic section for a package directory and its modules."""
    pkg_doc = ""
    if repo_root is not None:
        pkg_doc = _resolve_package_docstring(repo_root / pkg_rel)
    lines: list[str] = []
    header = f"## Package `{pkg_rel}`"
    if pkg_doc:
        header += f" — *{pkg_doc}*"
    lines.append(header)
    lines.append("")
    for m in sorted(modules, key=lambda x: x.rel_path):
        lines.extend(_format_module(m))
        lines.append("")
    return lines


def _build_sections_and_toc(
    groups: dict[str, list[ModuleEntry]],
    repo_root: Path | None,
    header_len: int,
) -> tuple[list[str], list[str], list[SectionMeta]]:
    """Compute line ranges and assemble Table of Contents and package bodies."""
    pkg_keys = sorted(groups.keys())
    scaffold_len = 5 + len(pkg_keys)
    curr_line = header_len + scaffold_len + 1
    toc_entries: list[str] = []
    body_lines: list[str] = []
    metas: list[SectionMeta] = []
    for pkg in pkg_keys:
        doc = _resolve_package_docstring(repo_root / pkg) if repo_root else ""
        sec = _render_package_section(pkg, groups[pkg], repo_root)
        start, end = curr_line, curr_line + len(sec) - 1
        curr_line = end + 1
        n_mods = len(groups[pkg])
        n_syms = sum(len(m.functions) + len(m.classes) for m in groups[pkg])
        metas.append(SectionMeta(pkg, doc, start, end, n_mods, n_syms))
        slug = _slugify(f"package-{pkg}")
        doc_str = f" — *{doc}*" if doc else ""
        toc_entries.append(f"- [`{pkg}`](#{slug}) (lines {start}–{end}){doc_str}")
        body_lines.extend(sec)
    toc = ["## Table of Contents", ""] + toc_entries + ["", "---", ""]
    return toc, body_lines, metas


def format_sub_index(
    pkg_root: str,
    modules: Sequence[ModuleEntry],
    repo_root: Path | None = None,
) -> tuple[str, list[SectionMeta]]:
    """Render a self-contained sub-index with its own local TOC and line ranges."""
    groups: dict[str, list[ModuleEntry]] = defaultdict(list)
    total_fns = sum(len(m.functions) for m in modules)
    total_cls = sum(len(m.classes) for m in modules)
    for m in modules:
        groups[Path(m.rel_path).parent.as_posix()].append(m)
    note = (
        f"Sub-index for the `{pkg_root}` package hierarchy. "
        "Use the line ranges below to load specific sections directly into context."
    )
    hdr = _format_header(
        f"{harness.SLUG.title()} Sub-Index: `{pkg_root}`",
        note,
        len(modules),
        total_cls,
        total_fns,
    )
    toc, body, metas = _build_sections_and_toc(groups, repo_root, len(hdr))
    return "\n".join(hdr + toc + body), metas


def _format_sub_index_block(sub: dict[str, Any]) -> list[str]:
    """Format one sub-index section and its packages for the master index."""
    path_str = sub["path_str"]
    m_cnt, s_cnt = sub["module_count"], sub["symbol_count"]
    lines = [f"### [`{path_str}`]({path_str}) — {m_cnt} modules | {s_cnt} symbols", ""]
    for sec in sub["sections"]:
        doc_str = f" — *{sec.doc}*" if sec.doc else ""
        target = f"{path_str}#L{sec.start_line}-L{sec.end_line}"
        entry = (
            f"- [`{sec.pkg_rel}`]({target}) "
            f"(lines {sec.start_line}–{sec.end_line} in `{path_str}`){doc_str}"
        )
        lines.append(entry)
    lines.append("")
    return lines


def format_master_index(
    sub_indices: list[dict[str, Any]],
    stats: dict[str, Any],
) -> str:
    """Render the master index linking to sub-indices with section line ranges."""
    note = (
        "Master architectural directory. Sub-indices are maintained for "
        "major subtrees. Use the sub-index links and line ranges below to "
        "load target sections into context."
    )
    lines = _format_header(
        f"{harness.SLUG.title()} Codebase Master Index",
        note,
        stats["total_modules"],
        stats["total_classes"],
        stats["total_functions"],
    )
    lines.extend(["## Master Table of Contents", ""])
    for sub in sub_indices:
        lines.extend(_format_sub_index_block(sub))
    return "\n".join(lines)


def format_markdown_index(
    modules: Sequence[ModuleEntry], repo_root: Path | None = None
) -> str:
    """Render a structured Table of Contents grouped dynamically by package directory."""
    groups: dict[str, list[ModuleEntry]] = defaultdict(list)
    total_fns = sum(len(m.functions) for m in modules)
    total_cls = sum(len(m.classes) for m in modules)
    for m in modules:
        groups[Path(m.rel_path).parent.as_posix()].append(m)
    note = (
        "This index is generated dynamically from the filesystem AST by "
        "`framework.indexing`. It maps package hierarchies, exported "
        "classes/functions, and behavioral contracts without hardcoded lists."
    )
    hdr = _format_header(
        f"{harness.SLUG.title()} Codebase Index & Table of Contents",
        note,
        len(modules),
        total_cls,
        total_fns,
    )
    toc, body, _ = _build_sections_and_toc(groups, repo_root, len(hdr))
    return "\n".join(hdr + toc + body)
