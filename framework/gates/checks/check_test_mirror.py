#!/usr/bin/env python3
"""Fail-closed test-mirror check for the production source tree.

Every module below ``--src`` (default ``research``) must be paired with a mirrored
test file below ``--tests`` (default ``tests``):

    research/<path>/<stem>.py  ->  tests/research/<path>/tests_<stem>.py
                              tests/research/<path>/test_<stem>.py

A module may instead be listed in the alias table (``--aliases``,
default ``framework/test_mirror_aliases.json``) pointing at one or more
existing test files. Aliases are only legitimate when the target imports the
module; the coverage gate measures that per file.

Package markers (``__init__.py``) are exempt. Tests, third-party code, and
caches are never checked. Only the src -> test direction is enforced.

Usage::

  python framework/gates/checks/check_test_mirror.py [--strict] [--json PATH]
  python framework/gates/checks/check_test_mirror.py --strict --staged -- research/a/b.py

Exit codes: 0 = clean or findings without ``--strict``; 1 = findings with
``--strict``; 2 = environment or usage error (missing alias table).

Invariants & Expected State:
    * Only the src -> test direction is enforced; a test file without a source
      is never a finding.
    * ``__init__.py`` and paths containing ``__pycache__``, ``third_party`` or
      ``.git`` are exempt.
    * A missing or malformed alias table is an environment error (exit 2), not
      a finding; alias targets must be existing files, while whether they
      import the module is measured by the coverage gate.
    * ``--staged`` restricts the check to the listed paths; otherwise the whole
      ``--src`` tree is scanned, sorted and de-duplicated.
"""

from __future__ import annotations

import argparse
import json
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
    return []


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

    for finding in findings:
        print(f"[check_test_mirror] {finding.format()}", file=sys.stderr)
    if args.json:
        _write_json_report(args.json, files, findings)
    return _report(findings, files, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
