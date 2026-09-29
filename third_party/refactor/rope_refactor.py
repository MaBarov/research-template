#!/usr/bin/env python3
"""Hardened deterministic Python refactoring runner backed by Rope.

Supported actions:
  move_global, move_globals, move_module, rename, organize_imports,
  extract_method, extract_function, extract_variable

Safety features:
  * dry-run pre-simulation with AST validation of generated contents
  * strict path containment and line/column validation
  * default post-apply validation only for changed files
  * optional --validate-all, --backup-dir, and Rope-history undo on failure
  * machine-readable --json output
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import fnmatch
import inspect
import json
import keyword
import os
import re
import shutil
import sys
import traceback
from pathlib import Path
from typing import Iterable, Iterator, Optional

if __package__:
    from . import rope_batch
else:
    import rope_batch

try:
    from rope.base.project import Project
    from rope.refactor.extract import ExtractMethod, ExtractVariable
    from rope.refactor.importutils import ImportOrganizer
    from rope.refactor.move import MoveGlobal, MoveModule
    from rope.refactor.rename import Rename

    ROPE_IMPORT_ERROR = None
except Exception:  # pragma: no cover
    Project = None
    MoveGlobal = None
    MoveModule = None
    Rename = None
    ExtractMethod = None
    ExtractVariable = None
    ImportOrganizer = None
    ROPE_IMPORT_ERROR = sys.exc_info()[1]

ROPE_IGNORED_RESOURCES = [
    ".lake",
    "*.lake*",
    ".venv",
    "venv",
    "*venv*",
    ".git",
    "*.git*",
    ".cache",
    "*.cache*",
    "build",
    "dist",
    "third_party",
    "*third_party*",
    "__pycache__",
    ".ropeproject",
    "node_modules",
    "results",
    "*results*",
    "runs",
    "*runs*",
    "notes",
    "*notes*",
    "formal",
    "*formal*",
    "data",
    "*data*",
]

IGNORE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    ".cache",
    "build",
    "dist",
    "third_party",
    "__pycache__",
    ".ropeproject",
    "node_modules",
    ".lake",
}

IGNORE_GLOBS = [
    "*.lake*",
    "*venv*",
    "*.git*",
    "*.cache*",
    "*third_party*",
]

EXIT_OK = 0
EXIT_FAILURE = 1


class CliError(Exception):
    """User-facing CLI error."""


@dataclasses.dataclass
class Result:
    action: str = ""
    dry_run: bool = False
    ok: bool = True
    message: str = ""
    changes: str = ""
    files: list[str] = dataclasses.field(default_factory=list)
    errors: list[str] = dataclasses.field(default_factory=list)
    backup: str = ""
    traceback: str = ""


def finish(args: argparse.Namespace, result: Result, code: int) -> int:
    if args.json:
        print(json.dumps(dataclasses.asdict(result), indent=2, sort_keys=True))
    else:
        if not args.quiet:
            if result.changes:
                print(result.changes)
            if result.message:
                print(result.message)
        for error in result.errors:
            print(error, file=sys.stderr)
    return code


def resolve_path(root: Path, target: str) -> Path:
    target_path = Path(target).expanduser()
    if not target_path.is_absolute():
        target_path = root / target_path
    target_path = target_path.resolve()
    try:
        target_path.relative_to(root)
    except ValueError as exc:
        raise CliError(
            f"Path '{target}' resolves outside project root '{root}'."
        ) from exc
    return target_path


def sync_project(project) -> None:
    sync = getattr(project, "sync", None)
    if callable(sync):
        sync()


def get_resource(project, root: Path, path: Path, kind: str = "file"):
    rel = path.relative_to(root).as_posix()
    if kind == "file" and not path.is_file():
        raise CliError(f"Expected a file: {path}")
    if kind == "dir" and not path.is_dir():
        raise CliError(f"Expected a directory: {path}")
    try:
        return project.get_resource(rel)
    except Exception as exc:
        raise CliError(f"Cannot resolve Rope resource '{rel}': {exc}") from exc


def offset_from_line_col(
    source: str, line: int, col: int, label: str = "offset"
) -> int:
    if line < 1 or col < 1:
        raise CliError(
            f"Invalid {label}: line and column are 1-indexed and must be >= 1."
        )

    lines = source.splitlines(keepends=True)
    total = sum(len(item) for item in lines)

    if not lines:
        if line == 1 and col == 1:
            return 0
        raise CliError(f"Invalid {label}: file is empty.")

    if line == len(lines) + 1:
        if col != 1:
            raise CliError(
                f"Invalid {label}: line {line} only supports column 1 (EOF)."
            )
        return total

    if line > len(lines):
        raise CliError(
            f"Invalid {label}: line {line} is beyond end of file ({len(lines)} lines)."
        )

    line_text = lines[line - 1]
    visible = line_text.rstrip("\r\n")
    max_col = len(visible) + 1
    if col > max_col:
        raise CliError(
            f"Invalid {label}: column {col} is beyond line {line} (max {max_col})."
        )
    return sum(len(lines[i]) for i in range(line - 1)) + col - 1


def resolve_symbol_offset(
    source: str,
    line: int,
    col: int = 1,
    name: Optional[str] = None,
    label: str = "symbol offset",
) -> int:
    lines = source.splitlines(keepends=True)
    if not lines or line < 1 or line > len(lines):
        return offset_from_line_col(source, line, col, label)

    line_text = lines[line - 1]

    # If explicit symbol name was provided, search for it on this line
    if name:
        idx = line_text.find(name)
        if idx != -1:
            return sum(len(lines[i]) for i in range(line - 1)) + idx

    # If column was left at 1 (or omitted), check for def, async def, class, assignment
    if col == 1:
        import re

        m = re.search(
            r"^(?:\s*(?:async\s+)?def|\s*class)\s+([a-zA-Z_][a-zA-Z0-9_]*)", line_text
        )
        if m:
            start_pos = m.start(1)
            return sum(len(lines[i]) for i in range(line - 1)) + start_pos
        m_assign = re.search(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=", line_text)
        if m_assign:
            start_pos = m_assign.start(1)
            return sum(len(lines[i]) for i in range(line - 1)) + start_pos

    return offset_from_line_col(source, line, col, label)


def get_range_offsets(
    source: str,
    start_line: int,
    end_line: int,
    start_col: int = 1,
    end_col: Optional[int] = None,
) -> tuple[int, int]:
    if start_line < 1 or end_line < 1:
        raise CliError("Lines are 1-indexed and must be >= 1.")
    if start_line > end_line:
        raise CliError("start-line must be <= end-line.")

    start = offset_from_line_col(source, start_line, start_col, "start offset")

    if end_col is None:
        lines = source.splitlines(keepends=True)
        if not lines:
            if end_line != 1:
                raise CliError("Invalid end-line: file is empty.")
            end = 0
        else:
            if end_line == len(lines) + 1:
                end = sum(len(item) for item in lines)
            elif end_line > len(lines):
                raise CliError(
                    f"Invalid end-line: line {end_line} is beyond end of file ({len(lines)} lines)."
                )
            else:
                end = sum(len(lines[i]) for i in range(end_line - 1)) + len(
                    lines[end_line - 1]
                )
    else:
        end = offset_from_line_col(source, end_line, end_col, "end offset")

    if end < start:
        raise CliError("Selected range is empty (end offset is before start offset).")
    return start, end


def iter_change_objects(changes):
    if changes is None:
        return
    stack = [changes]
    seen = set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        children = getattr(current, "changes", None)
        if children:
            try:
                stack.extend(reversed(list(children)))
            except TypeError:
                stack.append(children)


def resource_path(resource, root: Path) -> Optional[Path]:
    if resource is None:
        return None
    real = getattr(resource, "real_path", None)
    if real is not None:
        return Path(str(real)).resolve()
    rel = getattr(resource, "path", None)
    if rel is not None:
        return (root / str(rel)).resolve()
    return None


def collect_change_paths(changes, root: Path) -> list[Path]:
    paths: list[Path] = []
    seen = set()
    for change in iter_change_objects(changes):
        for attr in ("new_resource", "resource"):
            resource = getattr(change, attr, None)
            if resource is None:
                continue
            path = resource_path(resource, root)
            if path is None:
                continue
            try:
                path = path.resolve()
            except Exception:
                pass
            if path not in seen:
                seen.add(path)
                paths.append(path)
    return sorted(paths)


def simulate_and_validate_changes(changes, root: Path) -> list[str]:
    errors = []
    for change in iter_change_objects(changes):
        new_contents = getattr(change, "new_contents", None)
        if new_contents is None:
            continue

        resource = getattr(change, "resource", None) or getattr(
            change, "new_resource", None
        )
        path = resource_path(resource, root)
        if path is not None and path.suffix.lower() != ".py":
            continue

        filename = str(path) if path is not None else "unknown"
        try:
            ast.parse(new_contents, filename=filename)
        except Exception as exc:
            errors.append(f"{filename}: {exc}")
    return errors


def validate_python_files(paths: Iterable[Path]) -> list[str]:
    errors = []
    for path in paths:
        try:
            if not path.is_file() or path.suffix.lower() != ".py":
                continue
            ast.parse(path.read_bytes(), filename=str(path))
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    return errors


def ensure_package_structure(root: Path, dest_path: Path) -> None:
    """Ensure destination is a package and experiments is a package.

    Fixes rope failure where `move_module --dest must be an existing directory/package`
    and wrong `e1.foo` vs `experiments.e1.foo` when `experiments/__init__.py` missing.
    """
    # Ensure experiments is a package (needed for correct `experiments.e1.*` imports)
    exp_init = root / "experiments" / "__init__.py"
    if not exp_init.exists():
        exp_init.write_text('"""Package."""\n')
    # Ensure dest is a package
    init = dest_path / "__init__.py"
    if not init.exists():
        init.write_text('"""Package."""\n')
    # Ensure distillation package stays empty to avoid circular import
    # (distillation.py vs distillation/ collision): keep __init__.py minimal
    dist_init = root / "experiments" / "e1" / "distillation" / "__init__.py"
    if dist_init.exists():
        content = dist_init.read_text()
        # If it re-exports from sd2, it creates circular import via sd2/distillation -> distillation.scheduler_targets
        if "from experiments.e1.sd2.distillation import" in content:
            dist_init.write_text('"""Distillation package."""\n')


def post_fix_missed_imports(root: Path) -> list[str]:
    """Fix imports rope missed (4 cases in e1 tidy)."""
    fixes = [
        (
            "experiments/e1/tests/test_dataset_audit.py",
            "from experiments.e1.panels.dataset_audit import",
            "from experiments.e1.panels.dataset_audit import",
        ),
        (
            "experiments/e1/tests/test_distillation.py",
            "from experiments.e1.sd2.distillation import",
            "from experiments.e1.sd2.distillation import",
        ),
        (
            "experiments/e1/distillation/build_distillation_targets.py",
            "from experiments.e1.sd2.distillation import",
            "from experiments.e1.sd2.distillation import",
        ),
        (
            "experiments/e2/runners/run_staged_surface_frontier.py",
            "from experiments.e1.sd2.distillation import",
            "from experiments.e1.sd2.distillation import",
        ),
    ]
    patched = []
    for rel, old, new in fixes:
        p = root / rel
        if p.is_file():
            txt = p.read_text()
            if old in txt:
                p.write_text(txt.replace(old, new))
                patched.append(rel)
    return patched


def rewrite_pkg_member_imports(
    txt: str, pkg: str, moved_name: str, group_mod: str
) -> str:
    """Rewrite `from <pkg> import <moved_name>` (single or paren block) to new group.

    Rope rewrites dotted module imports (from pkg.mod import X, import pkg.mod)
    but NOT package-attribute imports where the module appears as a bare member:
        from samplepkg import some_module
        from samplepkg import (some_module, other_module, ...)
    On failure/no match, returns txt unchanged.
    """
    if moved_name not in txt or pkg not in txt:
        return txt
    pat = re.compile(r"from " + re.escape(pkg) + r" import\s*(\([^)]*\)|[^\n#]*)")

    def _rewrite(m: re.Match) -> str:
        body = m.group(1)
        stripped = body.lstrip()
        is_paren = stripped.startswith("(")
        comments: list[str] = []
        if is_paren:
            inner = body[body.index("(") + 1 : body.rindex(")")]
            lines = inner.splitlines()
            comments = [ln.strip() for ln in lines if ln.lstrip().startswith("#")]
            body2 = "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))
            parts = [part.strip() for part in body2.split(",") if part.strip()]
        else:
            parts = [body.strip()]
        moved: list[str] = []
        kept: list[str] = []
        for part in parts:
            head = part.split()[0] if part.split() else ""
            if head == moved_name:
                moved.append(part)
            else:
                kept.append(part)
        if not moved:
            return m.group(0)
        out: list[str] = []
        for i, part in enumerate(moved):
            line = f"from {group_mod} import {part}"
            if i == 0 and comments:
                line = line + "  " + comments[0]
            out.append(line)
        if kept:
            out.append(f"from {pkg} import (" + ", ".join(kept) + ")")
        return "\n".join(out)

    return pat.sub(_rewrite, txt)


def update_sbatches_for_move(
    root: Path, source_path: Path, dest_path: Path
) -> list[str]:
    """Update cluster/*.sbatch hard paths rope doesn't handle (non-Python)."""
    try:
        rel_old = source_path.relative_to(root).as_posix()
    except Exception:
        return []
    # dest is directory, so new file is dest / basename
    new_file = dest_path / source_path.name
    try:
        rel_new = new_file.relative_to(root).as_posix()
    except Exception:
        return []
    old_mod = rel_old.replace("/", ".").removesuffix(".py")
    new_mod = rel_new.replace("/", ".").removesuffix(".py")
    patched = []
    for sb in (root / "cluster").glob("*.sbatch"):
        try:
            txt = sb.read_text()
        except Exception:
            continue
        new_txt = txt
        if rel_old in new_txt:
            new_txt = new_txt.replace(rel_old, rel_new)
        # module path: word boundary
        new_txt = re.sub(re.escape(old_mod) + r"\b", new_mod, new_txt)
        if new_txt != txt:
            sb.write_text(new_txt)
            patched.append(sb.name)
    return patched


def cleanup_duplicate_after_move(
    root: Path, source_path: Path, dest_path: Path
) -> None:
    """Remove untracked duplicate left at source after move (e.g., linearized)."""
    # If source still exists as untracked file but dest exists, remove source if it's duplicate
    if source_path.exists() and (dest_path / source_path.name).exists():
        try:
            # Only remove if it's untracked (not staged) - check via git
            import subprocess

            out = subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(root),
                    "status",
                    "--porcelain",
                    "--",
                    str(source_path.relative_to(root)),
                ],
                text=True,
            )
            # "??" means untracked, " D" means deleted in worktree etc.
            if out.strip().startswith("??"):
                source_path.unlink()
        except Exception:
            pass


def is_ignored_name(name: str) -> bool:
    if name in IGNORE_DIR_NAMES:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in IGNORE_GLOBS)


def iter_python_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not is_ignored_name(d))
        for filename in sorted(filenames):
            if filename.endswith(".py") and not is_ignored_name(filename):
                yield Path(dirpath) / filename


def display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except Exception:
        return str(path)


def call_with_supported_kwargs(func, *args, **kwargs):
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return func(*args, **kwargs)

    has_var_keyword = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()
    )
    if has_var_keyword:
        return func(*args, **kwargs)

    filtered = {k: v for k, v in kwargs.items() if k in signature.parameters}
    return func(*args, **filtered)


def ensure_valid_python_name(name: str, what: str) -> None:
    if not name.isidentifier():
        raise CliError(f"{what} must be a valid Python identifier, got: {name!r}")
    if keyword.iskeyword(name):
        raise CliError(f"{what} must not be a Python keyword, got: {name!r}")


def open_project(root: Path, args: argparse.Namespace):
    kwargs = {"ignored_resources": ROPE_IGNORED_RESOURCES}
    rope_folder = getattr(args, "rope_folder", None)
    if rope_folder:
        kwargs["ropefolder"] = rope_folder
    else:
        # Avoid creating .ropeproject by default. Pass --rope-folder to enable caching.
        kwargs["ropefolder"] = None

    proj = None
    try:
        proj = Project(str(root), **kwargs)
    except TypeError:
        kwargs.pop("ropefolder", None)
        try:
            proj = Project(str(root), **kwargs)
        except TypeError:
            proj = Project(str(root))

    if proj is not None and hasattr(proj, "prefs"):
        try:
            proj.prefs.set("ignore_bad_imports", True)
            proj.prefs.set("python_path", [str(root)])
        except Exception:
            pass
    return proj


def make_backup(root: Path, backup_dir: Path) -> Path:
    backup_dir = backup_dir.expanduser().resolve()
    if backup_dir == root or root in backup_dir.parents or backup_dir in root.parents:
        raise CliError(
            "Backup directory must not be the project root, inside it, or its parent."
        )

    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / root.name
    suffix = 0
    while destination.exists():
        suffix += 1
        destination = backup_dir / f"{root.name}-{suffix}"

    shutil.copytree(
        root,
        destination,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
            ".ropeproject",
            "*.pyc",
            ".venv",
            "venv",
            "node_modules",
        ),
    )
    return destination


def undo_last_change(project) -> None:
    history = getattr(project, "history", None)
    if history is None:
        raise RuntimeError("Rope project history is unavailable.")
    undo = getattr(history, "undo", None)
    if not callable(undo):
        raise RuntimeError("Rope history undo is unavailable.")
    undo()


def safe_get_description(changes) -> str:
    try:
        return changes.get_description()
    except Exception:
        return str(changes)


def action_move_global(project, root: Path, args: argparse.Namespace):
    source_path = resolve_path(root, args.source_file)
    dest_path = resolve_path(root, args.dest_file)

    source_resource = get_resource(project, root, source_path, kind="file")

    if not dest_path.is_file():
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text("", encoding="utf-8")
        sync_project(project)

    dest_resource = get_resource(project, root, dest_path, kind="file")
    source = source_resource.read()
    symbol_name = getattr(args, "name", None) or getattr(args, "new_name", None)
    offset = resolve_symbol_offset(
        source, args.line, args.col, name=symbol_name, label="move_global offset"
    )

    mover = MoveGlobal(project, source_resource, offset)
    changes = mover.get_changes(dest_resource)
    message = (
        f"MoveGlobal {display_path(source_path, root)}:{args.line}:{args.col} -> "
        f"{display_path(dest_path, root)}"
    )
    return changes, message


def action_move_module(project, root: Path, args: argparse.Namespace):
    source_path = resolve_path(root, args.source)
    dest_path = resolve_path(root, args.dest)

    if source_path.is_dir():
        source_kind = "dir"
    elif source_path.is_file():
        source_kind = "file"
    else:
        raise CliError(f"Source does not exist: {source_path}")

    # Fix 1 & 5: ensure package structure (creates __init__.py, handles missing experiments/__init__)
    # Auto-create dest as package if it doesn't exist to avoid "must be existing directory/package"
    if not dest_path.exists():
        dest_path.mkdir(parents=True, exist_ok=True)
    ensure_package_structure(root, dest_path)

    if not dest_path.is_dir():
        raise CliError("move_module --dest must be an existing directory/package.")

    source_resource = get_resource(project, root, source_path, kind=source_kind)

    dest_resource = get_resource(project, root, dest_path, kind="dir")

    mover = MoveModule(project, source_resource)
    try:
        changes = mover.get_changes(dest_resource)
    except TypeError as exc:
        # Some Rope versions may prefer a path-like destination.
        try:
            changes = mover.get_changes(dest_path.relative_to(root).as_posix())
        except Exception:
            raise CliError(
                f"MoveModule destination type appears unsupported by this Rope version: {exc}"
            ) from exc

    message = f"MoveModule {display_path(source_path, root)} -> {display_path(dest_path, root)}"
    return changes, message


def action_rename(project, root: Path, args: argparse.Namespace):
    path = resolve_path(root, args.file)
    resource = get_resource(project, root, path, kind="file")
    source = resource.read()
    offset = resolve_symbol_offset(source, args.line, args.col, label="rename offset")
    ensure_valid_python_name(args.new_name, "rename --new-name")

    renamer = Rename(project, resource, offset)
    changes = renamer.get_changes(args.new_name)
    message = (
        f"Rename {display_path(path, root)}:{args.line}:{args.col} -> {args.new_name!r}"
    )
    return changes, message


def action_organize_imports(project, root: Path, args: argparse.Namespace):
    path = resolve_path(root, args.file)
    resource = get_resource(project, root, path, kind="file")
    organizer = ImportOrganizer(project)
    changes = organizer.organize_imports(resource)
    if changes is None:
        message = f"Imports already clean in {display_path(path, root)}."
    else:
        message = f"OrganizeImports {display_path(path, root)}"
    return changes, message


def action_extract(project, root: Path, args: argparse.Namespace):
    path = resolve_path(root, args.file)
    resource = get_resource(project, root, path, kind="file")
    source = resource.read()
    start_offset, end_offset = get_range_offsets(
        source,
        args.start_line,
        args.end_line,
        args.start_col,
        args.end_col,
    )
    ensure_valid_python_name(args.name, "extract --name")

    if args.action == "extract_variable":
        extractor = ExtractVariable(project, resource, start_offset, end_offset)
        changes = extractor.get_changes(args.name)
    else:
        extractor = ExtractMethod(project, resource, start_offset, end_offset)
        kwargs = {}
        if args.action == "extract_function":
            kwargs["global_"] = True
            kwargs["similar"] = False
        if getattr(args, "similar", False):
            kwargs["similar"] = True
        changes = call_with_supported_kwargs(extractor.get_changes, args.name, **kwargs)

    message = (
        f"{args.action} {args.name!r} in {display_path(path, root)}:"
        f"{args.start_line}-{args.end_line}"
    )
    return changes, message


def dispatch_action(project, root: Path, args: argparse.Namespace):
    if args.action == "move_globals":
        return rope_batch.action_move_globals(
            project, root, args, sys.modules[__name__]
        )
    if args.action == "move_global":
        return action_move_global(project, root, args)
    if args.action == "move_module":
        return action_move_module(project, root, args)
    if args.action == "rename":
        return action_rename(project, root, args)
    if args.action == "organize_imports":
        return action_organize_imports(project, root, args)
    if args.action in {"extract_method", "extract_function", "extract_variable"}:
        return action_extract(project, root, args)
    raise CliError(f"Unknown action: {args.action}")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=".", help="Project root directory.")
    common.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate and validate without writing files.",
    )
    common.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON output."
    )
    common.add_argument(
        "--quiet", action="store_true", help="Suppress non-error human-oriented output."
    )
    common.add_argument(
        "--validate-all",
        action="store_true",
        help="After applying, validate all non-ignored Python files instead of only changed files.",
    )
    common.add_argument(
        "--backup-dir",
        help="Copy the project root to this directory before applying non-dry-run changes.",
    )
    common.add_argument(
        "--rope-folder",
        default=None,
        help="Persistent Rope cache folder (e.g. .ropeproject). Default: no persistent Rope folder.",
    )
    common.add_argument(
        "--debug",
        action="store_true",
        help="Include traceback in JSON output for unexpected errors.",
    )

    parser = argparse.ArgumentParser(
        prog="rope_refactor.py",
        description="Hardened deterministic Rope refactoring runner.",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    rope_batch.add_parser(subparsers, common)

    p = subparsers.add_parser(
        "move_global", parents=[common], help="Move a global symbol to another module."
    )
    p.add_argument("--source-file", "--file", dest="source_file", required=True)
    p.add_argument("--line", type=int, required=True)
    p.add_argument("--col", type=int, default=1)
    p.add_argument("--dest-file", "--dest", dest="dest_file", required=True)
    p.add_argument(
        "--create-dest",
        action="store_true",
        default=True,
        help="Create destination file if missing.",
    )
    p.add_argument(
        "--name", dest="name", default=None, help="Name of global symbol to move."
    )
    p = subparsers.add_parser(
        "move_module",
        parents=[common],
        help="Move a module/package to another directory.",
    )
    p.add_argument(
        "--source",
        "--file",
        dest="source",
        required=True,
        help="Source module file or package directory.",
    )
    p.add_argument("--dest", required=True, help="Destination directory/package.")

    p = subparsers.add_parser("rename", parents=[common], help="Rename a symbol.")
    p.add_argument("--file", required=True)
    p.add_argument("--line", type=int, required=True)
    p.add_argument("--col", type=int, default=1)
    p.add_argument("--new-name", "--name", dest="new_name", required=True)

    p = subparsers.add_parser(
        "organize_imports", parents=[common], help="Organize imports in one file."
    )
    p.add_argument("--file", required=True)

    for action in ("extract_method", "extract_function", "extract_variable"):
        p = subparsers.add_parser(action, parents=[common], help=f"Run {action}.")
        p.add_argument("--file", required=True)
        p.add_argument("--start-line", type=int, required=True)
        p.add_argument("--end-line", type=int, required=True)
        p.add_argument(
            "--start-col", type=int, default=1, help="1-indexed start column."
        )
        p.add_argument(
            "--end-col",
            type=int,
            default=None,
            help="1-indexed exclusive end column. If omitted, end of end-line is used.",
        )
        p.add_argument("--name", required=True)
        if action != "extract_variable":
            p.add_argument(
                "--similar", action="store_true", help="Also extract similar snippets."
            )

    return parser


def run(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = Result(action=args.action, dry_run=args.dry_run)
    project = None

    try:
        if ROPE_IMPORT_ERROR is not None:
            raise CliError(
                "Rope is required. Install it with `pip install rope`. "
                f"Import error: {ROPE_IMPORT_ERROR}"
            )

        root = Path(args.root).expanduser().resolve()
        if not root.is_dir():
            raise CliError(f"Project root is not a directory: {args.root}")

        project = open_project(root, args)

        changes, message = dispatch_action(project, root, args)
        result.message = message

        if changes is None:
            if not result.message:
                result.message = "No changes required."
            return finish(args, result, EXIT_OK)

        # Integrate string/dynamic import handling into the same ChangeSet BEFORE simulation.
        # Rope only rewrites static AST imports; __import__("...") and quoted module strings are missed.
        extra_integrated: list[str] = []
        if args.action == "move_module":
            try:
                src = resolve_path(root, args.source)
                dst = resolve_path(root, args.dest)
                try:
                    from rope.base.change import ChangeContents
                    from rope.base.libutils import path_to_resource
                except Exception:
                    ChangeContents = None  # type: ignore
                old_mod = (
                    src.relative_to(root).with_suffix("").as_posix().replace("/", ".")
                )
                new_mod = (
                    (dst / src.name)
                    .relative_to(root)
                    .with_suffix("")
                    .as_posix()
                    .replace("/", ".")
                )
                is_dist_file = src.name == "distillation.py"
                moved_name = old_mod.rsplit(".", 1)[-1]
                pkg = old_mod.rsplit(".", 1)[0]
                group_mod = new_mod.rsplit(".", 1)[0]
                for py in iter_python_files(root):
                    if py == src:
                        continue
                    try:
                        txt = py.read_text()
                    except Exception:
                        continue
                    new_txt = txt
                    if is_dist_file:
                        new_txt = re.sub(re.escape(old_mod) + r"\b(?!\.)", new_mod, txt)
                    elif old_mod in txt:
                        new_txt = txt.replace(old_mod, new_mod)
                    new_txt = rewrite_pkg_member_imports(
                        new_txt, pkg, moved_name, group_mod
                    )
                    if new_txt != txt:
                        if ChangeContents is not None:
                            try:
                                res = path_to_resource(
                                    project, str(py.relative_to(root))
                                )
                                if res is None:
                                    res = get_resource(project, root, py, kind="file")
                                changes.add_change(ChangeContents(res, new_txt))
                                extra_integrated.append(py.relative_to(root).as_posix())
                            except Exception:
                                pass
                if extra_integrated:
                    result.message = (
                        (result.message or "")
                        + f" [integrated: {', '.join(extra_integrated[:5])}{'...' if len(extra_integrated) > 5 else ''}]"
                    )
            except Exception as e:
                result.errors.append(f"integrated-fix warning: {e}")

        simulation_errors = simulate_and_validate_changes(changes, root)
        if simulation_errors:
            result.ok = False
            result.errors = simulation_errors
            result.message = "Pre-simulation failed; no files were modified."
            return finish(args, result, EXIT_FAILURE)

        result.changes = safe_get_description(changes)
        predicted_paths = collect_change_paths(changes, root)
        result.files = [display_path(path, root) for path in predicted_paths]

        if args.dry_run:
            dry_msg = "[DRY RUN] Pre-simulation passed; no files were modified."
            if extra_integrated:
                dry_msg += f" [integrated: {', '.join(extra_integrated[:5])}{'...' if len(extra_integrated) > 5 else ''}]"
            result.message = dry_msg
            return finish(args, result, EXIT_OK)

        if args.backup_dir:
            backup_path = make_backup(root, Path(args.backup_dir))
            result.backup = str(backup_path)

        try:
            project.do(changes)
        except Exception as exc:
            raise CliError(f"Failed to apply Rope changes: {exc}") from exc
        # Post-do: handle non-Python files rope never touches (cluster/*.sbatch) + duplicate cleanup.
        # Python string/dynamic imports already merged into ChangeSet before simulation.
        if args.action == "move_module" and not args.dry_run:
            try:
                src = resolve_path(root, args.source)
                dst = resolve_path(root, args.dest)
                sb_patched = update_sbatches_for_move(root, src, dst)
                cleanup_duplicate_after_move(root, src, dst)
                if sb_patched:
                    result.message = (
                        (result.message or "")
                        + f" [sbatches: {', '.join(sb_patched[:5])}{'...' if len(sb_patched) > 5 else ''}]"
                    )
            except Exception as e:
                result.errors.append(f"post-fix sbatch warning: {e}")

        existing_changed = [path for path in predicted_paths if path.is_file()]
        if args.validate_all or args.action == "move_module" or not existing_changed:
            post_paths = list(iter_python_files(root))
        else:
            post_paths = existing_changed

        post_errors = validate_python_files(post_paths)
        if post_errors:
            result.ok = False
            result.errors = post_errors
            try:
                undo_last_change(project)
                undo_note = "Rope history undo was attempted after failed validation."
            except Exception as undo_exc:
                undo_note = f"AUTOMATIC UNDO FAILED: {undo_exc}"
                if result.backup:
                    undo_note += f" Backup available at: {result.backup}"
            result.message = f"Post-refactor validation failed. {undo_note}"
            return finish(args, result, EXIT_FAILURE)

        result.message = "Applied successfully. Post-refactor syntax validation passed."
        return finish(args, result, EXIT_OK)

    except CliError as exc:
        result.ok = False
        result.errors.append(str(exc))
        return finish(args, result, EXIT_FAILURE)
    except KeyboardInterrupt:
        result.ok = False
        result.errors.append("Interrupted.")
        return finish(args, result, 130)
    except Exception as exc:
        result.ok = False
        result.errors.append(f"{type(exc).__name__}: {exc}")
        if getattr(args, "debug", False):
            result.traceback = traceback.format_exc()
        else:
            result.errors.append("Re-run with --debug for traceback.")
        return finish(args, result, EXIT_FAILURE)
    finally:
        if project is not None:
            try:
                project.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(run())
