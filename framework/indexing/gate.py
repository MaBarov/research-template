"""Verification gate and freshness check for the repository Table of Contents.

Role & Architecture:
    Validates that planned index files match on-disk indices, checks for public
    interface drift without corresponding docstring updates, and audits docstring
    contract completeness across repository modules using pyproject.toml configuration.

Invariants & Expected State:
    - Fail-Closed: Out-of-sync indices, missing contracts, or unreviewed interface
      drift cause verification to exit non-zero (code 1).
    - Configurable Scope: Reads enforce-paths and exclude-patterns from pyproject.toml
      with resilient zero-dependency fallback under Python 3.10.
    - Scope Enforcement: Scopes checks to specified staged files when run from pre-commit.
    - Line Limits: Master index and sub-indices are partitioned to satisfy the 600-line limit.

Failure Modes & Prohibited Patterns:
    - Unhandled git command errors return None/safe fallbacks.
    - Prohibited: Never write index files when check_only=True.
"""

from __future__ import annotations

import contextlib
import difflib
import fnmatch
import re
import subprocess
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore[assignment]


from framework import harness
from framework.indexing.formatter import (
    format_markdown_index,
    format_master_index,
    format_sub_index,
)
from framework.indexing.scanner import (
    FunctionEntry,
    ModuleEntry,
    scan_module_text,
    scan_repository,
)


def _signatures_map(
    functions: Sequence[FunctionEntry],
) -> dict[str, tuple[str, str]]:
    """Map function names to their arguments and return type signature."""
    return {f.name: (f.args_repr, f.return_type) for f in functions}


def _read_git_head_text(repo_root: Path, rel_path: str) -> str | None:
    """Read a file's content at HEAD via git cat-file."""
    try:
        proc = subprocess.run(
            ["git", "cat-file", "-p", f"HEAD:{rel_path}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout if proc.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _detect_drift_for_file(
    repo_root: Path, rel_path: str, staged_entry: ModuleEntry
) -> str | None:
    """Detect if public signatures changed without updating module docstring."""
    head_text = _read_git_head_text(repo_root, rel_path)
    if head_text is None:
        return None
    head_entry = scan_module_text(rel_path, head_text)
    if head_entry is None:
        return None
    head_sigs = _signatures_map(head_entry.functions)
    staged_sigs = _signatures_map(staged_entry.functions)
    if head_sigs != staged_sigs:
        doc_same = (
            head_entry.doc_summary == staged_entry.doc_summary
            and head_entry.doc_sections == staged_entry.doc_sections
        )
        if doc_same:
            return (
                f"{rel_path}: public interface changed, but module "
                "docstring was not updated (docstring drift detected)"
            )
    return None


DEFAULT_ENFORCE_PATHS = tuple(harness.ENFORCE_PATHS)
DEFAULT_EXCLUDE_PATTERNS = (
    "*/tests/*",
    "tests/*",
    "test_*.py",
    "tests_*.py",
    "__init__.py",
)


def _parse_toml_string_list(section_text: str, key: str) -> list[str]:
    """Extract a list of strings for a key from a TOML section text."""
    pattern = rf"{re.escape(key)}\s*=\s*\[(.*?)\]"
    match = re.search(pattern, section_text, re.DOTALL)
    if not match:
        return []
    items = re.findall(r'["\']([^"\']+)["\']', match.group(1))
    return [item.strip() for item in items if item.strip()]


def _parse_contracts_fallback(text: str) -> dict[str, Any]:
    """Fallback TOML parser for [tool.research.contracts] without external dependencies."""
    match = re.search(
        rf"\[tool\.{harness.SLUG}\.contracts\](.*?)(?=\n\[|\Z)", text, re.DOTALL
    )
    if not match:
        return {}
    sec = match.group(1)
    res: dict[str, Any] = {}
    paths = _parse_toml_string_list(sec, "enforce-paths")
    if paths:
        res["enforce-paths"] = paths
    ex = _parse_toml_string_list(sec, "exclude-patterns")
    if ex:
        res["exclude-patterns"] = ex
    return res


def load_contract_config(repo_root: Path | None = None) -> dict[str, Any]:
    """Load contract enforcement settings from pyproject.toml with safe fallback."""
    cfg: dict[str, Any] = {
        "enforce_paths": list(DEFAULT_ENFORCE_PATHS),
        "exclude_patterns": list(DEFAULT_EXCLUDE_PATTERNS),
    }
    if repo_root is None:
        return cfg
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return cfg
    with contextlib.suppress(OSError, KeyError, ValueError, TypeError):
        content = pyproject.read_text(encoding="utf-8")
        if tomllib is not None:
            data = tomllib.loads(content)
            raw = data.get("tool", {}).get(harness.SLUG, {}).get("contracts", {})
        else:
            raw = _parse_contracts_fallback(content)
        if "enforce-paths" in raw:
            cfg["enforce_paths"] = list(raw["enforce-paths"])
        if "exclude-patterns" in raw:
            cfg["exclude_patterns"] = list(raw["exclude-patterns"])
    return cfg


def _is_path_excluded(rel_path: str, exclude_patterns: Sequence[str]) -> bool:
    """Check if rel_path matches any exclusion glob pattern."""
    path_obj = Path(rel_path)
    posix = path_obj.as_posix()
    name = path_obj.name
    for pat in exclude_patterns:
        if fnmatch.fnmatch(posix, pat) or fnmatch.fnmatch(name, pat):
            return True
        if pat.endswith("/*") and posix.startswith(pat[:-2]):
            return True
    return False


def _is_path_enforced(
    rel_path: str,
    enforce_paths: Sequence[str],
    exclude_patterns: Sequence[str],
) -> bool:
    """Return True if rel_path is within enforced roots and not excluded."""
    norm = Path(rel_path).as_posix()
    if _is_path_excluded(norm, exclude_patterns):
        return False
    return any(
        norm == root or norm.startswith(f"{root.rstrip('/')}/")
        for root in enforce_paths
    )


def check_interface_drift(
    repo_root: Path,
    modules: Sequence[ModuleEntry],
    files: Sequence[str],
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Check whether any staged file altered public signatures without doc updates."""
    cfg = config or load_contract_config(repo_root)
    enforce_paths = cfg.get("enforce_paths", list(DEFAULT_ENFORCE_PATHS))
    exclude_patterns = cfg.get("exclude_patterns", list(DEFAULT_EXCLUDE_PATTERNS))
    file_set = {Path(f).as_posix() for f in files}
    findings: list[str] = []
    for m in modules:
        if m.rel_path in file_set:
            if not _is_path_enforced(m.rel_path, enforce_paths, exclude_patterns):
                continue
            err = _detect_drift_for_file(repo_root, m.rel_path, m)
            if err is not None:
                findings.append(err)
    return findings


def check_module_contracts(
    modules: Sequence[ModuleEntry],
    files: Sequence[str] | None = None,
    repo_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Audit staged or specified modules for Two-Tier docstring schema errors."""
    cfg = config or load_contract_config(repo_root)
    enforce_paths = cfg.get("enforce_paths", list(DEFAULT_ENFORCE_PATHS))
    exclude_patterns = cfg.get("exclude_patterns", list(DEFAULT_EXCLUDE_PATTERNS))
    file_set = {Path(f).as_posix() for f in files} if files else None
    findings: list[str] = []
    for m in modules:
        if file_set is not None and m.rel_path not in file_set:
            continue
        if not _is_path_enforced(m.rel_path, enforce_paths, exclude_patterns):
            continue
        for err in m.contract_errors:
            findings.append(f"{m.rel_path}: {err}")
    return findings


def audit_contract_coverage(
    modules: Sequence[ModuleEntry],
) -> dict[str, Any]:
    """Audit the percentage of public functions and modules carrying contracts."""
    total_fns = 0
    documented_fns = 0
    for m in modules:
        for f in m.functions:
            total_fns += 1
            if f.doc_summary:
                documented_fns += 1
        for c in m.classes:
            for meth in c.methods:
                total_fns += 1
                if meth.doc_summary:
                    documented_fns += 1
    inv_mods = sum(1 for m in modules if m.has_invariants)
    fn_pct = (documented_fns / total_fns * 100.0) if total_fns > 0 else 100.0
    mod_pct = (inv_mods / len(modules) * 100.0) if modules else 100.0
    return {
        "total_functions": total_fns,
        "documented_functions": documented_fns,
        "coverage_percentage": round(fn_pct, 1),
        "total_modules": len(modules),
        "invariant_modules": inv_mods,
        "invariant_percentage": round(mod_pct, 1),
    }


def _diff_files(path: Path, existing: str, planned: str) -> str:
    """Format unified diff between existing file and planned index content."""
    diff = difflib.unified_diff(
        existing.splitlines(keepends=True),
        planned.splitlines(keepends=True),
        fromfile=f"existing_{path.name}",
        tofile="planned_AST_index",
        n=2,
    )
    return "".join(list(diff)[:20])


def verify_index_freshness(file_map: dict[Path, str]) -> tuple[bool, str]:
    """Check if all planned index files match their on-disk counterparts."""
    for path, content in file_map.items():
        if not path.is_file():
            return False, f"Missing index file at {path}"
        existing = path.read_text(encoding="utf-8")
        if existing.strip() != content.strip():
            diff_text = _diff_files(path, existing, content)
            return False, f"Index out of sync at {path}:\n{diff_text}"
    return True, "All indices are in sync"


def _build_sub_index(
    root: str,
    mods: list[ModuleEntry],
    repo_root: Path,
    base_dir: Path,
) -> tuple[Path, str, dict[str, Any]]:
    """Render a sub-index file and return its path, content, and metadata."""
    sub_text, sections = format_sub_index(root, mods, repo_root=repo_root)
    sub_path = base_dir / root / "INDEX.md"
    sym_cnt = sum(len(m.functions) + len(m.classes) for m in mods)
    meta = {
        "path_str": f"{root}/INDEX.md",
        "module_count": len(mods),
        "symbol_count": sym_cnt,
        "sections": sections,
    }
    return sub_path, sub_text + "\n", meta


def _group_by_root(modules: Sequence[ModuleEntry]) -> dict[str, list[ModuleEntry]]:
    """Group scanned modules by their top-level root directory."""
    root_mods: dict[str, list[ModuleEntry]] = defaultdict(list)
    for m in modules:
        top = m.rel_path.split("/")[0]
        root_mods[top].append(m)
    return root_mods


def plan_index_files(
    repo_root: Path,
    index_path: Path,
    modules: Sequence[ModuleEntry],
    roots: Sequence[str],
    max_lines: int = 600,
) -> dict[Path, str]:
    """Plan index files: unified if under max_lines, otherwise tree of sub-indices."""
    unified = format_markdown_index(modules, repo_root=repo_root) + "\n"
    if len(unified.splitlines()) <= max_lines:
        return {index_path: unified}

    root_mods = _group_by_root(modules)
    file_map: dict[Path, str] = {}
    sub_metas: list[dict[str, Any]] = []
    base_dir = index_path.parent
    for r in sorted(root_mods.keys()):
        sub_path, sub_text, meta = _build_sub_index(
            r, root_mods[r], repo_root, base_dir
        )
        file_map[sub_path] = sub_text
        sub_metas.append(meta)

    stats = {
        "total_modules": len(modules),
        "total_classes": sum(len(m.classes) for m in modules),
        "total_functions": sum(len(m.functions) for m in modules),
    }
    file_map[index_path] = format_master_index(sub_metas, stats) + "\n"
    return file_map


def _write_index_files(file_map: dict[Path, str]) -> None:
    """Write all planned index files to disk creating parent directories."""
    for path, content in file_map.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _report_freshness_verdict(file_map: dict[Path, str], stats: dict[str, Any]) -> int:
    """Check freshness of index files and print gate verdict."""
    ok, msg = verify_index_freshness(file_map)
    if not ok:
        print(f"[index_gate] FAILED: {msg}")
        return 1
    pct = stats["coverage_percentage"]
    print(
        f"[index_gate] PASS: {stats['documented_functions']}/"
        f"{stats['total_functions']} ({pct}%) contracts documented "
        f"across {len(file_map)} index file(s)."
    )
    return 0


def _check_strict_contracts(
    repo_root: Path,
    modules: Sequence[ModuleEntry],
    files: Sequence[str] | None,
) -> int:
    """Validate docstring contracts and interface drift for scoped modules."""
    cfg = load_contract_config(repo_root)
    c_findings = check_module_contracts(
        modules, files=files, repo_root=repo_root, config=cfg
    )
    d_findings = (
        check_interface_drift(repo_root, modules, files, config=cfg) if files else []
    )
    findings = c_findings + d_findings
    if findings:
        for f in findings:
            print(f"[index_gate] CONTRACT FAIL: {f}")
        return 1

    cnt = len(files) if files else len(modules)
    print(f"[index_gate] PASS: {cnt} module(s) verified for Two-Tier contracts.")
    return 0


def run_index_gate(
    repo_root: Path,
    index_path: Path,
    roots: Sequence[str] = tuple(harness.INDEX_ROOTS),
    max_lines: int = 600,
    check_only: bool = False,
    strict_contracts: bool = False,
    staged_files: Sequence[str] | None = None,
) -> int:
    """Run the repository index gate: verify synchronization or write updates."""
    modules = scan_repository(repo_root, roots=roots)
    if strict_contracts:
        return _check_strict_contracts(repo_root, modules, staged_files)
    file_map = plan_index_files(
        repo_root, index_path, modules, roots=roots, max_lines=max_lines
    )
    stats = audit_contract_coverage(modules)
    if check_only:
        return _report_freshness_verdict(file_map, stats)
    _write_index_files(file_map)
    print(
        f"[index_gate] Updated {len(file_map)} index file(s) "
        f"({len(modules)} modules, {stats['total_functions']} symbols)."
    )
    return 0
