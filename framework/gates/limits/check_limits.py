#!/usr/bin/env python3
"""Code-size limits for agent-authored Python (blocking on staged files).

Rulings of 2026-09-17 (they supersede the earlier 15-line function rule):

* ``LMT001`` a Python file holds at most 600 lines;
* ``LMT002`` a function or method spans at most 30 source lines — the ``def``
  line through its last body line, decorators excluded, methods and
  ``async def`` included;
* ``LMT003`` a directory holds at most 5 first-party ``.py`` modules
  (``__init__.py`` never counts, directories are counted non-recursively);
* ``LMT004`` ``__init__.py`` carries no code: module docstring, imports and
  dunder-only assignments (``__all__``, ``__version__``, ...) only;
* ``LMT000`` an unreadable or unparseable module fails closed.

A module that outgrows a limit becomes a package with the same name, and its
members are moved out with the vendored Rope runner
(``third_party/refactor/rope_refactor.py``); decomposition is never handwritten.

Enforcement is "touch it, fix it": ``--mode staged`` (the pre-commit hook)
requires every staged first-party module to satisfy all four limits as staged,
with no grandfathering, and reads module text from the Git index so unrelated
unstaged edits cannot change the decision. Directory counts also come from the
index, so a staged rename or deletion is seen as it will be committed.
``--mode all`` audits the working tree and is the debt meter, not a commit
gate. There is no escape hatch: no environment variable and no skip flag.

Usage::

  python framework/gates/limits/check_limits.py --mode staged --strict --staged FILE...
  python framework/gates/limits/check_limits.py --mode all [--strict] [--max-findings N]

Exit codes: 0 clean (or findings without ``--strict``); 1 findings with
``--strict``; 2 usage or environment error.

Invariants & Expected State:
    * Exit 0 means "no finding", 1 means "at least one finding", 2 means fail
      closed: unreadable, unparseable or unindexable input is never reported
      clean.
    * ``--mode staged`` reads module text and directory counts from the Git
      index, so unstaged edits cannot change a staged decision, and a staged
      rename or deletion is judged as it will be committed.
    * The limits are the only tunables and they are constants: the module never
      reads a threshold, an allowlist or a baseline from the environment.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework import harness

SOURCE_ROOTS = tuple(harness.LIMITS_ROOTS)
EXCLUDED_PARTS = {"third_party", "results", "notes", "models", "cache", "datasets"}
MAX_FILE_LINES = 600
MAX_FUNCTION_LINES = 30
MAX_DIR_MODULES = 5
REMEDY = "third_party/refactor/rope_refactor.py"


@dataclass(frozen=True)
class Finding:
    """One code-size limit violation."""

    path: str
    line: int
    code: str
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.code} {self.message}"


def is_first_party(rel: str) -> bool:
    """Return whether a repository-relative path is in this gate's scope."""

    parts = Path(rel).parts
    if not rel.endswith(".py") or not parts:
        return False
    if any(part in EXCLUDED_PARTS or part.startswith(".") for part in parts[:-1]):
        return False
    if len(parts) == 1:
        return not rel.startswith(".")
    return parts[0] in SOURCE_ROOTS


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _dunder_name(target: ast.expr) -> bool:
    if isinstance(target, ast.Tuple):
        return all(_dunder_name(element) for element in target.elts)
    if isinstance(target, (ast.List, ast.Set)):
        return all(_dunder_name(element) for element in target.elts)
    name = target.id if isinstance(target, ast.Name) else None
    return bool(name) and name.startswith("__") and name.endswith("__")


def _dunder_assignment(node: ast.stmt) -> bool:
    if isinstance(node, ast.Assign):
        return all(_dunder_name(target) for target in node.targets)
    if isinstance(node, ast.AnnAssign):
        return _dunder_name(node.target)
    return False


def _importish_block(stmts: Sequence[ast.stmt], allow_docstring: bool = False) -> bool:
    return all(
        _importish(stmt, first=allow_docstring and index == 0)
        for index, stmt in enumerate(stmts)
    )


def _importish(node: ast.stmt, first: bool = False) -> bool:
    """Return whether a statement is import machinery rather than code."""

    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return True
    if first and _is_docstring(node):
        return True
    if _dunder_assignment(node):
        return True
    if isinstance(node, ast.If):
        return _importish_block(node.body) and _importish_block(node.orelse)
    if isinstance(node, ast.Try):
        return (
            _importish_block(node.body)
            and _importish_block(node.orelse)
            and _importish_block(node.finalbody)
            and all(_importish_block(handler.body) for handler in node.handlers)
        )
    return False


def walk_functions(node: ast.AST, prefix: str = "") -> Iterator[tuple[str, ast.AST]]:
    """Yield ``(qualname, node)`` for every function/method, outermost first."""

    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = f"{prefix}{child.name}"
            yield qualname, child
            yield from walk_functions(child, f"{qualname}.")
        elif isinstance(child, ast.ClassDef):
            yield from walk_functions(child, f"{prefix}{child.name}.")
        else:
            yield from walk_functions(child, prefix)


def function_findings(rel: str, tree: ast.Module) -> list[Finding]:
    """Return ``LMT002`` findings for every over-long function or method."""

    findings: list[Finding] = []
    for qualname, node in walk_functions(tree):
        span = (node.end_lineno or node.lineno) - node.lineno + 1
        if span > MAX_FUNCTION_LINES:
            findings.append(
                Finding(
                    rel,
                    node.lineno,
                    "LMT002",
                    f"{qualname} spans {span} lines (limit {MAX_FUNCTION_LINES}); "
                    f"extract helpers with {REMEDY} extract_method",
                )
            )
    return findings


def init_findings(rel: str, tree: ast.Module) -> list[Finding]:
    """Return the ``LMT004`` finding when ``__init__.py`` carries code."""

    offenders = [
        stmt
        for index, stmt in enumerate(tree.body)
        if not _importish(stmt, first=index == 0)
    ]
    if not offenders:
        return []
    return [
        Finding(
            rel,
            offenders[0].lineno,
            "LMT004",
            f"__init__.py holds {len(offenders)} code statement(s) (limit 0); keep "
            "docstring/imports/__all__ and move logic into a module",
        )
    ]


def file_findings(rel: str, text: str) -> list[Finding]:
    """Return every per-file limit finding for one module's source text."""

    findings: list[Finding] = []
    lines = len(text.splitlines())
    if lines > MAX_FILE_LINES:
        findings.append(
            Finding(
                rel,
                1,
                "LMT001",
                f"file holds {lines} lines (limit {MAX_FILE_LINES}); make it a "
                f"package and move members with {REMEDY}",
            )
        )
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError as error:
        findings.append(
            Finding(
                rel, error.lineno or 1, "LMT000", f"cannot parse module: {error.msg}"
            )
        )
        return findings
    findings.extend(function_findings(rel, tree))
    if Path(rel).name == "__init__.py":
        findings.extend(init_findings(rel, tree))
    return findings


def directory_findings(counts: Mapping[str, int]) -> list[Finding]:
    """Return ``LMT003`` findings for every directory above the module limit."""

    return [
        Finding(
            f"{directory}/",
            1,
            "LMT003",
            f"directory holds {count} modules (limit {MAX_DIR_MODULES}); group "
            "members into subpackages",
        )
        for directory, count in sorted(counts.items())
        if count > MAX_DIR_MODULES
    ]


def read_staged(rel: str) -> str | None:
    """Return the staged text of ``rel`` from the Git index, or ``None``."""

    result = subprocess.run(
        ["git", "show", f":{rel}"],
        cwd=REPO,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return None
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def index_directory_counts(directories: Sequence[str]) -> dict[str, int]:
    """Count indexed ``.py`` modules per directory, as the commit will see them."""

    counts = {directory: 0 for directory in directories}
    if not directories:
        return counts
    result = subprocess.run(
        ["git", "ls-files", "--cached", "-z", "--", *directories],
        cwd=REPO,
        capture_output=True,
        check=False,
    )
    entries = result.stdout.decode("utf-8", errors="replace").split("\0")
    for entry in entries:
        if not entry.endswith(".py") or Path(entry).name == "__init__.py":
            continue
        key = Path(entry).parent.as_posix()
        if key in counts:
            counts[key] += 1
    return counts


def collect_sources() -> list[str]:
    """Return every first-party module of the working tree, repository-relative."""

    rels: list[str] = []
    for root in SOURCE_ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        rels.extend(
            path.relative_to(REPO).as_posix()
            for path in sorted(base.rglob("*.py"))
            if is_first_party(path.relative_to(REPO).as_posix())
        )
    rels.extend(
        path.name for path in sorted(REPO.glob("*.py")) if is_first_party(path.name)
    )
    return rels


def report(findings: Sequence[Finding], checked: int, max_findings: int) -> None:
    """Print findings (capped) plus per-code totals and the checked count."""

    ordered = sorted(
        findings, key=lambda finding: (finding.code, finding.path, finding.line)
    )
    shown = ordered if max_findings <= 0 else ordered[:max_findings]
    for finding in shown:
        print(f"[check_limits] {finding.format()}", file=sys.stderr)
    if len(ordered) > len(shown):
        remaining = len(ordered) - len(shown)
        print(f"[check_limits] ... {remaining} more finding(s)", file=sys.stderr)
    for code in sorted({finding.code for finding in ordered}):
        total = sum(1 for finding in ordered if finding.code == code)
        print(f"[check_limits] {code}: {total}", file=sys.stderr)
    print(f"[check_limits] checked {checked} file(s), {len(ordered)} finding(s)")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Code-size limits gate.")
    ap.add_argument(
        "--mode",
        choices=("staged", "all"),
        default="all",
        help="staged: verify staged modules (pre-commit); all: audit the tree",
    )
    ap.add_argument("--staged", nargs="*", default=[], help="staged paths to check")
    ap.add_argument(
        "--strict", action="store_true", help="exit non-zero when findings exist"
    )
    ap.add_argument(
        "--max-findings",
        type=int,
        default=50,
        help="printed findings cap (0 prints all); totals always print",
    )
    return ap.parse_args(argv)


def run_staged(args: argparse.Namespace) -> int:
    """Verify every staged first-party module without grandfathering."""

    if not args.staged:
        print("[check_limits] --mode staged needs --staged FILE...", file=sys.stderr)
        return 2
    rels = sorted({rel for rel in args.staged if is_first_party(rel)})
    if not rels:
        print("[check_limits] no staged first-party Python modules")
        return 0
    findings: list[Finding] = []
    for rel in rels:
        text = read_staged(rel)
        if text is None:
            findings.append(
                Finding(rel, 1, "LMT000", "cannot read staged blob from the Git index")
            )
            continue
        findings.extend(file_findings(rel, text))
    directories = sorted({Path(rel).parent.as_posix() for rel in rels})
    findings.extend(directory_findings(index_directory_counts(directories)))
    report(findings, len(rels), args.max_findings)
    if findings and args.strict:
        print(
            f"[check_limits] STRICT FAIL: {len(findings)} finding(s) in staged modules",
            file=sys.stderr,
        )
        return 1
    return 0


def run_all(args: argparse.Namespace) -> int:
    """Audit the working tree; the debt meter, not a commit gate."""

    rels = collect_sources()
    findings: list[Finding] = []
    counts: dict[str, int] = {}
    for rel in rels:
        try:
            text = (REPO / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            findings.append(Finding(rel, 1, "LMT000", f"cannot read module: {error}"))
            continue
        findings.extend(file_findings(rel, text))
        if Path(rel).name != "__init__.py":
            key = Path(rel).parent.as_posix()
            counts[key] = counts.get(key, 0) + 1
    findings.extend(directory_findings(counts))
    report(findings, len(rels), args.max_findings)
    if findings and args.strict:
        print(
            f"[check_limits] STRICT FAIL: {len(findings)} finding(s) in the tree",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "staged":
        return run_staged(args)
    return run_all(args)


if __name__ == "__main__":
    raise SystemExit(main())
