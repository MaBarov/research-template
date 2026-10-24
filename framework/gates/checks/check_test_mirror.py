#!/usr/bin/env python3
"""Fail-closed test-mirror check for the production source tree.

Thumbnail: Raises MIRROR MISSING, MIR003, HNS068 (no behavioral assertions) or HNS070
(state-anchored oracles).

Invariants & Expected State:
    * Only the src -> test direction is enforced; a test file without a source
      is never a finding.
    * ``__init__.py`` and paths containing ``__pycache__``, ``third_party`` or
      ``.git`` are exempt. A malformed alias table is an environment error
      (exit 2), not a finding; alias targets must be existing files, while
      whether they import the module is measured by the coverage gate.
    * ``--staged`` restricts the check to the listed paths; otherwise the whole
      ``--src`` tree is scanned, sorted and de-duplicated.
    * ``exists`` is a caller-supplied predicate, so the gate can be exercised
      against a virtual tree: a mirror that is absent from disk (or unreadable
      UTF-8) is never judged for assertion content, which keeps in-memory
      callers working.
    * HNS068 fires when a non-exempt mirror parses to zero assertions, or to
      nothing but tautologies (``assert True``/``assert 1``/``assert 1 == 1``),
      where ``pytest.raises``/``pytest.warns`` with-blocks count as oracles.
      An unparseable mirror is treated as assertion-free, so the gate fails
      closed.
    * HNS070 fires when every assertion is state-anchored or self-referential --
      ``assert x == x``, ``assert f() == f()``, or ``assert len(x) >= 0`` --
      pinning the oracle to its own state instead of an independent
      expectation.
    * ``check_alias_ratchet`` keeps the alias table monotonic non-increasing
      and blocks any addition with MIR003: a new module earns a dedicated
      mirror, it does not reuse a neighbour's.

Every module below ``--src`` (the project slug from ``framework/harness.py``)
must be paired with a mirrored test file below ``--tests`` (the harness test
root):

    <src>/<path>/<stem>.py  ->  <tests>/<src>/<path>/tests_<stem>.py
                                <tests>/<src>/<path>/test_<stem>.py

A module may instead be listed in the alias table (``--aliases``,
default ``framework/test_mirror_aliases.json``) pointing at one or more
existing test files. Aliases are only legitimate when the target imports the
module; the coverage gate measures that per file.

Usage::

  python framework/gates/checks/check_test_mirror.py [--strict] [--json PATH]
  python framework/gates/checks/check_test_mirror.py --strict --staged -- research/a/b.py
  python framework/gates/checks/check_test_mirror.py --strict --oracle-files tests/unit/test_x.py

``--oracle-files`` grades the named files themselves; a file is graded only
when its basename is not ``__init__.py``/``conftest.py``/``*_fixtures.py`` and
it defines at least one ``test_*`` function, so support and benchmark modules
are skipped rather than failed. With ``--staged`` the text comes from the Git
index, unlike the mirror path which reads the mirror from disk.

Exit codes: 0 = clean or findings without ``--strict``; 1 = findings with
``--strict``; 2 = environment or usage error (missing alias table, unreadable
graded file).
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework import harness

DEFAULT_SRC = harness.SLUG
DEFAULT_TESTS = harness.TEST_ROOT
DEFAULT_ALIASES = "framework/test_mirror_aliases.json"
DEFAULT_TESTS_NAMES = ("tests_{stem}.py", "test_{stem}.py")
SKIP_SEGMENTS = frozenset({"__pycache__", "third_party", ".git"})
EXEMPT_NAMES = frozenset({"__init__.py"})


@dataclass(frozen=True)
class Finding:
    """One missing or broken src -> test mirror."""

    path: str
    code: str
    message: str

    def format(self) -> str:
        return f"{self.code}: {self.message}"


def mirror_paths(rel: str, tests_root: str = DEFAULT_TESTS) -> list[str]:
    """Return the accepted mirror test paths for one source file."""

    parts = rel.split("/")
    directory = parts[:-1]
    stem = Path(parts[-1]).stem
    return [
        "/".join([tests_root, *directory, template.format(stem=stem)])
        for template in DEFAULT_TESTS_NAMES
    ]


def is_checked_path(rel: str, src: str) -> bool:
    """Return whether ``rel`` is a source module the gate is responsible for."""

    return rel.endswith(".py") and rel.startswith(f"{src}/")


def is_skipped(rel: str) -> bool:
    return any(segment in SKIP_SEGMENTS for segment in rel.split("/"))


def collect_files(src: str, staged: Sequence[str] | None = None) -> list[str]:
    """Return the source files to check, sorted and de-duplicated."""

    if staged is not None:
        candidates = [rel for rel in staged if is_checked_path(rel, src)]
    else:
        root = REPO / src
        candidates = [path.relative_to(REPO).as_posix() for path in root.rglob("*.py")]
    return sorted({rel for rel in candidates if not is_skipped(rel)})


TAUTOLOGICAL_VALUES = (True, 1)
SELF_COMPARISON_OPS = (ast.Eq, ast.Is, ast.NotEq)
ORACLE_CONTEXT_ATTRS = frozenset({"raises", "warns"})
MIRROR_EXEMPT_SUFFIX = "_fixtures.py"


def is_exempt_mirror_test(mirror: str) -> bool:
    """Return whether ``mirror`` is a fixture module exempt from HNS068."""
    name = Path(mirror).name
    return name == "conftest.py" or name.endswith(MIRROR_EXEMPT_SUFFIX)


def _is_tautological_assert(test: ast.expr) -> bool:
    """Return whether ``test`` asserts a constant truth or a self-comparison."""
    if isinstance(test, ast.Constant) and test.value in TAUTOLOGICAL_VALUES:
        return True
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        left, right = test.left, test.comparators[0]
        return (
            isinstance(test.ops[0], ast.Eq)
            and isinstance(left, ast.Constant)
            and isinstance(right, ast.Constant)
            and ast.dump(left) == ast.dump(right)
        )
    return False


def _is_self_comparison(test: ast.Compare) -> bool:
    """Return whether ``test`` compares one expression against itself."""
    if len(test.ops) != 1 or not isinstance(test.ops[0], SELF_COMPARISON_OPS):
        return False
    left, right = test.left, test.comparators[0]
    return ast.unparse(left) == ast.unparse(right)


def _is_vacuous_length_bound(test: ast.Compare) -> bool:
    """Return whether ``test`` asserts ``len(...) >= 0`` (always true)."""
    bound = test.comparators[0]
    return (
        len(test.ops) == 1
        and isinstance(test.ops[0], ast.GtE)
        and isinstance(test.left, ast.Call)
        and isinstance(test.left.func, ast.Name)
        and test.left.func.id == "len"
        and isinstance(bound, ast.Constant)
        and bound.value == 0
    )


def _is_state_anchored_assert(test: ast.expr) -> bool:
    """Return whether ``test`` is self-referential or vacuously true."""
    if not isinstance(test, ast.Compare):
        return False
    return _is_self_comparison(test) or _is_vacuous_length_bound(test)


def _is_oracle_context(node: ast.With) -> bool:
    """Return whether the with-block is a ``pytest.raises``/``warns`` oracle."""
    for item in node.items:
        expr = item.context_expr
        if (
            isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Attribute)
            and expr.func.attr in ORACLE_CONTEXT_ATTRS
        ):
            return True
    return False


def _count_oracles(source: str) -> tuple[int, int, int]:
    """Parse ``source``; return (total, tautological, state-anchored) counts."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return (0, 0, 0)
    total = 0
    tautological = 0
    anchored = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            total += 1
            if _is_tautological_assert(node.test):
                tautological += 1
            elif _is_state_anchored_assert(node.test):
                anchored += 1
        elif isinstance(node, ast.With) and _is_oracle_context(node):
            total += 1
    return (total, tautological, anchored)


def _read_mirror_source(mirror: str) -> str | None:
    """Return the on-disk text of ``mirror``, or None when absent or unreadable."""

    target = REPO / mirror
    if not target.is_file():
        return None
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _assertion_findings(rel: str, mirrors: Sequence[str]) -> list[Finding]:
    """Return HNS068/HNS070 findings for non-exempt mirrors lacking oracles."""
    findings: list[Finding] = []
    for mirror in mirrors:
        if is_exempt_mirror_test(mirror):
            continue
        source = _read_mirror_source(mirror)
        if source is not None:
            findings.extend(_oracle_findings(rel, mirror, source))
    return findings


def _oracle_findings(rel: str, mirror: str, source: str) -> list[Finding]:
    """Return HNS068/HNS070 findings for one readable mirror file."""
    total, tautological, anchored = _count_oracles(source)
    if total == 0 or total == tautological:
        return [
            Finding(
                rel,
                "HNS068",
                f"{mirror} has no behavioral assertions "
                "(assertion-free test theater; arXiv:2606.18168)",
            )
        ]
    if anchored and tautological + anchored == total:
        return [
            Finding(
                rel,
                "HNS070",
                f"{mirror} contains state-anchored or self-referential "
                "assertions (arXiv:2608.17214)",
            )
        ]
    return []


def defines_test_function(source: str) -> bool:
    """True when ``source`` defines at least one ``test_*`` function."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(tree)
    )


def grade_oracle_file(rel: str, source: str) -> list[Finding]:
    """Return HNS068/HNS070 findings for one test file's own text."""
    if Path(rel).name in EXEMPT_NAMES or is_exempt_mirror_test(rel):
        return []
    if not defines_test_function(source):
        return []
    return _oracle_findings(rel, rel, source)


def _evaluate_one(
    rel: str,
    aliases: Mapping[str, Sequence[str]],
    exists: Callable[[str], bool],
    tests_root: str,
) -> list[Finding]:
    """Return the mirror findings for one source module ([] when mirrored)."""
    mirrors = [path for path in mirror_paths(rel, tests_root) if exists(path)]
    targets = list(aliases.get(rel, ()))
    dangling = [target for target in targets if not exists(target)]
    if mirrors and targets:
        return [
            Finding(
                rel,
                "ALIAS STALE",
                f"{rel} has a mirror test file; drop the alias entry",
            )
        ]
    if dangling:
        return [
            Finding(rel, "ALIAS DANGLING", f"{rel} -> {target} (missing)")
            for target in dangling
        ]
    if not mirrors and not targets:
        expected = mirror_paths(rel, tests_root)[0]
        return [Finding(rel, "MIRROR MISSING", f"{rel} -> expected {expected}")]
    return _assertion_findings(rel, mirrors)


def evaluate(
    files: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    exists: Callable[[str], bool],
    *,
    tests_root: str = DEFAULT_TESTS,
) -> list[Finding]:
    """Return one finding per source module without a valid test mirror."""

    findings: list[Finding] = []
    for rel in files:
        if Path(rel).name in EXEMPT_NAMES:
            continue
        findings.extend(_evaluate_one(rel, aliases, exists, tests_root))
    return findings


def load_aliases(path: Path) -> dict[str, list[str]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"missing alias table: {path} "
            "(create it or pass --aliases; empty JSON object is valid)"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path}: alias table must be a JSON object")
    aliases: dict[str, list[str]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, list):
            raise TypeError(f"{path}: entries must map string -> list of strings")
        if not all(isinstance(target, str) for target in value):
            raise TypeError(f"{path}: {key}: targets must be strings")
        aliases[key] = value
    return aliases


def _parse_alias_payload(payload: str) -> dict[str, list[str]]:
    """Parse a committed alias table; return {} when it is malformed."""
    try:
        data = json.loads(payload)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: list(value)
        for key, value in data.items()
        if isinstance(key, str) and isinstance(value, list)
    }


def check_alias_ratchet(
    repo_root: Path,
    alias_path: Path,
    current_aliases: Mapping[str, Sequence[str]],
) -> list[Finding]:
    """Block newly added alias mappings (MIR003); the table may only shrink."""
    try:
        rel = alias_path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return []
    result = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"HEAD:{rel.as_posix()}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return []
    head_aliases = _parse_alias_payload(result.stdout)
    added = set(current_aliases) - set(head_aliases)
    if not added:
        return []
    message = (
        f"test mirror alias addition blocked ({len(added)} new mapping(s)); "
        "new production modules must provide dedicated mirror tests "
        "(tests/.../tests_<stem>.py), not aliases: " + ", ".join(sorted(added)[:5])
    )
    return [Finding(path=str(rel), code="MIR003", message=message)]


def _read_oracle_source(rel: str, staged: bool) -> str | None:
    """Return one test file's text from the Git index or the working tree."""
    if staged:
        result = subprocess.run(
            ["git", "cat-file", "-p", f":{rel}"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.stdout if result.returncode == 0 else None
    target = Path(rel) if Path(rel).is_absolute() else REPO / rel
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _run_oracle_files(args: argparse.Namespace) -> int:
    """Grade the named test files directly, from the index or disk."""
    findings: list[Finding] = []
    for rel in args.oracle_files:
        source = _read_oracle_source(rel, args.staged is not None)
        if source is None:
            print(f"[check_test_mirror] ERROR: cannot read {rel}", file=sys.stderr)
            return 2
        findings.extend(grade_oracle_file(rel, source))
    for finding in findings:
        print(f"[check_test_mirror] {finding.format()}", file=sys.stderr)
    return _report(findings, list(args.oracle_files), args.strict)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default=DEFAULT_SRC, help="source directory")
    parser.add_argument("--tests", default=DEFAULT_TESTS, help="test directory")
    parser.add_argument(
        "--aliases",
        default=DEFAULT_ALIASES,
        help="alias table (src path -> existing test paths)",
    )
    parser.add_argument(
        "--staged",
        nargs="*",
        help="check only these paths (as passed by the pre-commit hook)",
    )
    parser.add_argument(
        "--oracle-files",
        nargs="+",
        help=(
            "grade these test files directly (HNS068/HNS070) instead of "
            "resolving mirrors; with --staged read each from the Git index"
        ),
    )
    parser.add_argument("--strict", action="store_true", help="exit 1 on findings")
    parser.add_argument("--json", help="write a machine-readable report here")
    return parser


def _write_json_report(
    path: str, files: Sequence[str], findings: Sequence[Finding]
) -> None:
    (REPO / path).write_text(
        json.dumps(
            {
                "schema": "research.test-mirror.v1",
                "checked": files,
                "findings": [
                    {
                        "path": finding.path,
                        "code": finding.code,
                        "message": finding.message,
                    }
                    for finding in findings
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _report(findings: Sequence[Finding], files: Sequence[str], strict: bool) -> int:
    """Print the run summary and return the process exit code."""
    print(
        f"[check_test_mirror] checked {len(files)} file(s), {len(findings)} finding(s)"
    )
    if findings and strict:
        print(
            f"[check_test_mirror] STRICT FAIL: {len(findings)} mirror finding(s)",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.oracle_files:
        return _run_oracle_files(args)

    try:
        aliases = load_aliases(REPO / args.aliases)
    except (OSError, ValueError, TypeError) as error:
        print(f"[check_test_mirror] ERROR: {error}", file=sys.stderr)
        return 2

    files = [
        rel
        for rel in collect_files(args.src, args.staged)
        if Path(rel).name not in EXEMPT_NAMES
    ]
    findings = evaluate(
        files,
        aliases,
        lambda rel: (REPO / rel).is_file(),
        tests_root=args.tests,
    )
    findings += check_alias_ratchet(REPO, REPO / args.aliases, aliases)

    for finding in findings:
        print(f"[check_test_mirror] {finding.format()}", file=sys.stderr)
    if args.json:
        _write_json_report(args.json, files, findings)
    return _report(findings, files, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
