"""Usage gate for the canonical parameter registry (codes HNS042, HNS043).

Invariants & Expected State:
    - A row must have a reader: a production ``.py`` file calls a ``resolve`` accessor
      for it, imports one of its ``constants``, or accepts a generic accessor keyed by
      its ``name`` (HNS042).
    - ``tests/`` never justifies a row and the parameter package is not its own reader;
      an unreadable file or declaration is a finding, never silence.
    - A declared ``implementations`` module must carry the row's ``default`` text as an
      ``ast.Compare`` operand, so a policy name is a named branch and not a silent
      fallback (HNS043).
    - Reading is pure: ``usage_findings`` takes the rows and the source texts, so a
      caller can replay it on a fixture without touching the tree.
"""

from __future__ import annotations

import ast
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from framework import harness
from framework.gates.antipattern.targets import Finding, _read_staged
from framework.gates.params import param_checks

CONSUMING_ROOTS = tuple(harness.CONSUMING_ROOTS)
GENERIC_ACCESSORS = frozenset(
    {"default", "ambient", "str_param", "int_param", "float_param", "path_param"}
)
PARAMS_MODULE = harness.PARAMS_MODULE
PARAMS_DIR = PARAMS_MODULE.replace(".", "/")
SKIP_SEGMENTS = frozenset({"__pycache__", "third_party", "cache", "mutants"})
USAGE_CODE = "HNS042"
COMPARISON_CODE = "HNS043"
RESOLVE_PATH = harness.RESOLVE_PATH


@dataclass(frozen=True)
class Reads:
    """The accessor surface of one parsed module."""

    generic: frozenset[str]
    pairs: frozenset[tuple[str, str]]
    leaves: frozenset[str]
    names: frozenset[str]
    module_import: bool


def _dotted(node: ast.AST) -> str | None:
    """Return the dotted callee name of ``node``, or ``None`` for a dynamic call."""

    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _leaf(node: ast.Call) -> str | None:
    """Return the leaf name of ``node``'s callee, or ``None`` when it is dynamic."""

    name = _dotted(node.func)
    return None if name is None else name.rsplit(".", 1)[-1]


def _string_argument(node: ast.Call) -> str | None:
    """Return the string literal first argument of ``node``, if it has one."""

    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _imports_of(tree: ast.AST) -> tuple[set[tuple[str, str]], bool]:
    """Return the ``(local, original)`` imports from the package and whether its module is bound."""

    pairs: set[tuple[str, str]] = set()
    module_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if not (node.module or "").startswith(PARAMS_MODULE):
                continue
            pairs.update(
                (alias.asname or alias.name, alias.name) for alias in node.names
            )
            module_import = module_import or any(
                alias.name in {"registry", "resolve"} for alias in node.names
            )
        elif isinstance(node, ast.Import) and any(
            alias.name.startswith(PARAMS_MODULE) for alias in node.names
        ):
            module_import = True
    return pairs, module_import


def _call_reads(tree: ast.AST) -> tuple[set[str], set[str], set[str]]:
    """Return the generic-accessor row names, the called leaves and the used names."""

    generic: set[str] = set()
    leaves: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        if not isinstance(node, ast.Call):
            continue
        name = _leaf(node)
        if name is None:
            continue
        leaves.add(name)
        if name in GENERIC_ACCESSORS:
            value = _string_argument(node)
            if value is not None:
                generic.add(value)
    return generic, leaves, names


def _reads_of(tree: ast.AST) -> Reads:
    """Return the accessor surface of one parsed module."""

    pairs, module_import = _imports_of(tree)
    generic, leaves, names = _call_reads(tree)
    return Reads(
        frozenset(generic),
        frozenset(pairs),
        frozenset(leaves),
        frozenset(names),
        module_import,
    )


def _is_consuming(rel: str) -> bool:
    """Return whether one repository-relative path may consume a parameter."""

    if not rel.endswith(".py") or rel in param_checks.EXEMPT_PATHS:
        return False
    parts = rel.split("/")
    stem = parts[-1]
    if parts[0] not in CONSUMING_ROOTS or set(parts) & SKIP_SEGMENTS:
        return False
    if "tests" in parts or stem.startswith(("test_", "tests_")):
        return False
    return not rel.startswith(f"{PARAMS_DIR}/")


def _tracked_python() -> list[str]:
    """Return every tracked Python path of the repository."""

    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=param_checks.REPO,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return result.stdout.decode("utf-8").split()


def _source_text(rel: str) -> str | None:
    """Return one path's text from the worktree, else from the Git index."""

    try:
        return (param_checks.REPO / rel).read_text("utf-8")
    except (OSError, UnicodeError):
        pass
    try:
        return _read_staged(rel)
    except (OSError, RuntimeError, UnicodeError):
        return None


def _tree_sources() -> dict[str, str]:
    """Return the repository-relative text of every tracked Python module."""

    sources: dict[str, str] = {}
    for rel in _tracked_python():
        text = _source_text(rel)
        if text is None:
            raise RuntimeError(f"cannot read {rel} from worktree or index")
        sources[rel] = text
    return sources


def _parsed(texts: Mapping[str, str]) -> list[tuple[str, Reads]]:
    """Return one ``(path, Reads)`` pair per parseable source."""

    pairs: list[tuple[str, Reads]] = []
    for rel in sorted(texts):
        try:
            tree = ast.parse(texts[rel], filename=rel)
        except (SyntaxError, ValueError):
            continue
        pairs.append((rel, _reads_of(tree)))
    return pairs


def _is_read(row: Any, reads: Reads) -> bool:
    """Return whether one module's accessor surface reads ``row``."""

    accessors = frozenset(row.accessors)
    constants = frozenset(row.constants)
    if row.name in reads.generic:
        return True
    if reads.module_import and accessors & reads.leaves:
        return True
    for local, original in reads.pairs:
        if original in accessors and local in reads.leaves:
            return True
        if original in constants and local in reads.names:
            return True
    return False


def _resolve_callables(text: str | None) -> frozenset[str]:
    """Return the plain function names one ``resolve`` source defines."""

    if text is None:
        return frozenset()
    try:
        tree = ast.parse(text, filename=RESOLVE_PATH)
    except (SyntaxError, ValueError):
        return frozenset()
    return frozenset(
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    )


def _declaration_findings(
    rows: Sequence[Any], callables: frozenset[str]
) -> list[Finding]:
    """Return one finding per declared accessor that ``resolve`` does not define."""

    return [
        Finding(
            RESOLVE_PATH,
            1,
            USAGE_CODE,
            f"{row.name}: declared accessor {name} is not defined; fix {harness.REGISTRY_PATH}",
        )
        for row in rows
        for name in row.accessors
        if name not in callables
    ]


def _unread_findings(
    rows: Sequence[Any], pairs: Sequence[tuple[str, Reads]]
) -> list[Finding]:
    """Return one finding per row no module of ``pairs`` reads."""

    return [
        Finding(
            harness.REGISTRY_PATH,
            1,
            USAGE_CODE,
            f"{row.name}: registered parameter has no reader; read it through "
            "research/params or drop the row",
        )
        for row in rows
        if not any(_is_read(row, reads) for _, reads in pairs)
    ]


def _compares(tree: ast.AST, literal: str) -> bool:
    """Return whether ``tree`` compares the string ``literal`` anywhere."""

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for operand in (node.left, *node.comparators):
            if isinstance(operand, ast.Constant) and operand.value == literal:
                return True
    return False


def _comparison_findings(
    rows: Sequence[Any], texts: Mapping[str, str]
) -> list[Finding]:
    """Return one finding per declared implementation that ignores its default."""

    findings: list[Finding] = []
    for row in rows:
        for rel in row.implementations:
            text = texts.get(rel)
            if text is None:
                findings.append(_uncompared(row, rel, "is missing or unreadable"))
                continue
            try:
                tree = ast.parse(text, filename=rel)
            except (SyntaxError, ValueError):
                findings.append(_uncompared(row, rel, "does not parse"))
                continue
            if not _compares(tree, row.default):
                findings.append(_uncompared(row, rel, "never compares it"))
    return findings


def _uncompared(row: Any, rel: str, reason: str) -> Finding:
    """Return the HNS043 finding for one declared implementation of ``row``."""

    return Finding(
        rel,
        1,
        COMPARISON_CODE,
        f"{row.name}: declared implementation {reason} against the default "
        f"{row.default!r}; a policy default must be a named branch",
    )


def usage_findings(
    texts: Mapping[str, str] | None = None, rows: Sequence[Any] | None = None
) -> list[Finding]:
    """Return every usage finding of the registry rows against ``texts``."""

    registry_rows = list(param_checks.REGISTRY.PARAMETERS if rows is None else rows)
    gathered = _tree_sources() if texts is None else dict(texts)
    sources = {rel: text for rel, text in gathered.items() if _is_consuming(rel)}
    resolve_text = gathered.get(RESOLVE_PATH)
    if resolve_text is None:
        try:
            resolve_text = (param_checks.REPO / RESOLVE_PATH).read_text("utf-8")
        except (OSError, UnicodeError):
            resolve_text = None
    findings = _declaration_findings(registry_rows, _resolve_callables(resolve_text))
    findings.extend(_unread_findings(registry_rows, _parsed(sources)))
    findings.extend(_comparison_findings(registry_rows, sources))
    return findings
