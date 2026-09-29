"""Static AST-based scanner for codebase modules, classes, and contracts.

Role & Architecture:
    Extracts module metadata, class definitions, function signatures, and docstring
    contracts without importing or executing candidate code. Used by the framework
    indexing gate and contract enforcement pipelines.

Invariants & Expected State:
    - Pure Static Analysis: Never imports or executes scanned modules.
    - Determinism: Scans return sorted, immutable ModuleEntry tuples.
    - Robust Parsing: Gracefully handles SyntaxError or UnicodeDecodeError by
      returning None without raising or terminating execution.

Failure Modes & Prohibited Patterns:
    - Never import torch or heavy dependencies in this scanner.
    - Prohibited: Never use eval(), exec(), or __import__() to inspect objects.
"""

from __future__ import annotations

import ast
import contextlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from framework import harness


@dataclass(frozen=True)
class FunctionEntry:
    """Represents a public function or method extracted from the AST."""

    name: str
    args_repr: str
    return_type: str
    doc_summary: str
    line_no: int
    end_line_no: int
    is_async: bool = False


@dataclass(frozen=True)
class ClassEntry:
    """Represents a class definition and its public methods."""

    name: str
    bases: tuple[str, ...]
    doc_summary: str
    methods: tuple[FunctionEntry, ...]
    line_no: int
    end_line_no: int


@dataclass(frozen=True)
class ModuleEntry:
    """Represents a scanned Python module with its docstring and exports."""

    rel_path: str
    doc_summary: str
    classes: tuple[ClassEntry, ...]
    functions: tuple[FunctionEntry, ...]
    line_count: int
    doc_sections: tuple[tuple[str, str], ...] = ()
    contract_errors: tuple[str, ...] = ()

    @property
    def has_invariants(self) -> bool:
        """Return True if an Invariants section is present in docstring."""
        return any("invariant" in k.lower() for k, _ in self.doc_sections)


_SECTION_HEADER_RE = re.compile(r"^([A-Za-z0-9_ &/-]+):\s*$", re.MULTILINE)


def _extract_doc_thumbnail(raw: str) -> str:
    """Extract first sentence/paragraph as the Tier-1 thumbnail."""
    paras = raw.strip().split("\n\n")
    return paras[0].replace("\n", " ").strip()


def _parse_doc_sections(raw: str) -> list[tuple[str, str]]:
    """Parse structured sections like 'Invariants:', 'Role:', etc."""
    matches = list(_SECTION_HEADER_RE.finditer(raw))
    if not matches:
        return []
    sections: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        header = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        sections.append((header, raw[start:end].strip()))
    return sections


def _validate_module_docstring(
    raw: str | None,
) -> tuple[str, tuple[tuple[str, str], ...], tuple[str, ...]]:
    """Validate and extract thumbnail, sections, and structural contract errors."""
    if not raw or not raw.strip():
        return "", (), ("Missing module docstring",)
    thumb = _extract_doc_thumbnail(raw)
    errors: list[str] = []
    if len(thumb) > 140:
        errors.append(f"Docstring thumbnail exceeds 140 chars ({len(thumb)})")
    sections = _parse_doc_sections(raw)
    if not any("invariant" in k.lower() for k, _ in sections):
        errors.append("Missing required 'Invariants & Expected State' section")
    return thumb[:140], tuple(sections), tuple(errors)


def _extract_doc_summary(node: ast.AST) -> str:
    """Extract the first paragraph of a docstring as the behavioral contract."""
    raw = ast.get_docstring(node)
    if not raw:
        return ""
    paras = raw.strip().split("\n\n")
    first = paras[0].replace("\n", " ").strip()
    return first[:200] if len(first) > 200 else first


def _format_arg(arg: ast.arg) -> str:
    """Format an individual function parameter with its annotation if present."""
    if arg.annotation is not None:
        try:
            ann_str = ast.unparse(arg.annotation)
            return f"{arg.arg}: {ann_str}"
        except (AttributeError, ValueError):
            return arg.arg
    return arg.arg


def _format_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, str]:
    """Format argument list and return annotation for a function node."""
    parts: list[str] = [_format_arg(a) for a in node.args.posonlyargs]
    parts.extend(_format_arg(a) for a in node.args.args)
    if node.args.vararg:
        parts.append(f"*{node.args.vararg.arg}")
    parts.extend(_format_arg(a) for a in node.args.kwonlyargs)
    if node.args.kwarg:
        parts.append(f"**{node.args.kwarg.arg}")
    args_str = ", ".join(parts)
    ret_str = ""
    if node.returns is not None:
        try:
            ret_str = ast.unparse(node.returns)
        except (AttributeError, ValueError):
            ret_str = ""
    return args_str, ret_str


def _parse_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> FunctionEntry:
    """Construct a FunctionEntry from a FunctionDef or AsyncFunctionDef node."""
    args_repr, ret_type = _format_signature(node)
    doc = _extract_doc_summary(node)
    end = node.end_lineno if node.end_lineno is not None else node.lineno
    return FunctionEntry(
        name=node.name,
        args_repr=args_repr,
        return_type=ret_type,
        doc_summary=doc,
        line_no=node.lineno,
        end_line_no=end,
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )


def _parse_class(node: ast.ClassDef) -> ClassEntry:
    """Construct a ClassEntry from a ClassDef node including public methods."""
    bases: list[str] = []
    for b in node.bases:
        with contextlib.suppress(AttributeError, ValueError):
            bases.append(ast.unparse(b))
    methods: list[FunctionEntry] = [
        _parse_function(item)
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and (not item.name.startswith("_") or item.name == "__init__")
    ]
    end = node.end_lineno if node.end_lineno is not None else node.lineno
    return ClassEntry(
        name=node.name,
        bases=tuple(bases),
        doc_summary=_extract_doc_summary(node),
        methods=tuple(methods),
        line_no=node.lineno,
        end_line_no=end,
    )


def scan_module_text(rel_path: str, text: str) -> ModuleEntry | None:
    """Parse module text statically into a ModuleEntry without executing code."""
    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError:
        return None
    classes: list[ClassEntry] = []
    functions: list[FunctionEntry] = []
    for item in tree.body:
        if isinstance(item, ast.ClassDef) and not item.name.startswith("_"):
            classes.append(_parse_class(item))
        elif isinstance(
            item, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and not item.name.startswith("_"):
            functions.append(_parse_function(item))
    raw_doc = ast.get_docstring(tree)
    thumb, sections, errors = _validate_module_docstring(raw_doc)
    return ModuleEntry(
        rel_path=rel_path,
        doc_summary=thumb if thumb else _extract_doc_summary(tree),
        classes=tuple(classes),
        functions=tuple(functions),
        line_count=len(text.splitlines()),
        doc_sections=sections,
        contract_errors=errors,
    )


def scan_file(file_path: Path, repo_root: Path) -> ModuleEntry | None:
    """Read and scan a single Python file relative to repo_root."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    try:
        rel = file_path.relative_to(repo_root).as_posix()
    except ValueError:
        rel = file_path.as_posix()
    return scan_module_text(rel, text)


def _walk_py_files(target_dir: Path) -> list[Path]:
    """Recursively collect valid Python source files within target_dir."""
    files: list[Path] = []
    for p in sorted(target_dir.rglob("*.py")):
        if p.name == "__init__.py" or ".pytest_cache" in p.parts:
            continue
        if any(part.startswith(".") or part == "__pycache__" for part in p.parts):
            continue
        files.append(p)
    return files


def scan_repository(
    repo_root: Path, roots: Sequence[str] = tuple(harness.INDEX_ROOTS)
) -> list[ModuleEntry]:
    """Scan all specified subtrees of a repository and return sorted ModuleEntries."""
    entries: list[ModuleEntry] = []
    for root_name in roots:
        root_path = repo_root / root_name
        if not root_path.is_dir():
            continue
        for fpath in _walk_py_files(root_path):
            entry = scan_file(fpath, repo_root)
            if entry is not None:
                entries.append(entry)
    return sorted(entries, key=lambda e: e.rel_path)
