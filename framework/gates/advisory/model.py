"""Shared plumbing for the advisory static gates.

Thumbnail: Finding model, path scoping, staged loading, report emission and CLI runner.

Invariants & Expected State:
    One finding model and one population resolver, so every advisory gate scans
    the same production roots as the blocking transfer gate and reports the same
    shape (path, line, code, message, evidence).
    A staged read comes from the Git index, so an unstaged working-tree edit can
    never change a staged verdict; an unreadable source is a fail-closed HNS010.
    Emission prints one line per finding and returns the exit code: advisory
    unless the caller passes strict, with --report always writing the full list.
    The CLI options live here once, so a new advisory gate supplies an analyzer
    and a label and nothing else.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framework.gates.transfers.targets import _files_to_check, _load_source


@dataclass(frozen=True)
class Finding:
    """One static finding: file, line, code, message and its evidence class."""

    path: str
    line: int
    code: str
    message: str
    evidence: str = ""

    def format(self) -> str:
        """Format the finding as a compiler-style diagnostic line."""
        suffix = f" [{self.evidence}]" if self.evidence else ""
        return f"{self.path}:{self.line}: {self.code} {self.message}{suffix}"

    def as_dict(self) -> dict[str, object]:
        """Return the JSON-serializable form used by --report."""
        return {
            "path": self.path,
            "line": self.line,
            "code": self.code,
            "message": self.message,
            "evidence": self.evidence,
        }


def files_to_check(paths: Sequence[str]) -> list[str]:
    """Resolve CLI paths into the production-root Python modules to scan."""
    return _files_to_check(list(paths))


def load_source(path: str, staged: bool) -> tuple[str | None, Finding | None]:
    """Load one source from the Git index or disk, converting the error finding."""
    source, error = _load_source(path, staged)
    if error is None:
        return source, None
    return None, Finding(error.path, error.line, error.code, error.message)


def scan(
    paths: Iterable[str], staged: bool, analyze: Callable[[str, str], list[Finding]]
) -> list[Finding]:
    """Analyze every path with the gate's own analyzer, collecting findings."""
    findings: list[Finding] = []
    for path in paths:
        source, error = load_source(path, staged)
        if error is not None:
            findings.append(error)
        elif source is not None:
            findings.extend(analyze(source, path))
    return findings


def write_report(report_path: Path, findings: Sequence[Finding]) -> None:
    """Serialize findings to a JSON report."""
    data = [finding.as_dict() for finding in findings]
    report_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def emit(findings: Sequence[Finding], strict: bool, label: str) -> int:
    """Print every finding plus a summary line and return the exit code."""
    if findings:
        print("\n".join(f"[{label}] {finding.format()}" for finding in findings))
        counts = sorted({finding.code for finding in findings})
        print(f"[{label}] {len(findings)} finding(s) across {len(counts)} code(s)")
    if findings and strict:
        print(f"[{label}] STRICT FAIL: {len(findings)} finding(s)")
        return 1
    return 0


_OPTIONS: tuple[tuple[tuple[str, ...], dict[str, Any]], ...] = (
    (("--staged",), {"action": "store_true", "help": "read staged blobs"}),
    (("--strict",), {"action": "store_true", "help": "exit 1 on findings"}),
    (
        ("--mode",),
        {"choices": ["staged", "all"], "default": "staged", "help": "population"},
    ),
    (("--report",), {"type": Path, "help": "JSON finding list"}),
)


def build_parser(description: str) -> argparse.ArgumentParser:
    """Build the argument parser every advisory gate shares."""
    parser = argparse.ArgumentParser(description=description)
    for flags, options in _OPTIONS:
        parser.add_argument(*flags, **options)
    parser.add_argument("files", nargs="*", help="paths to inspect")
    return parser


def run(
    argv: list[str] | None,
    analyze: Callable[[str, str], list[Finding]],
    label: str,
    description: str,
) -> int:
    """Parse arguments, scan the requested population, report, and return the code."""
    args = build_parser(description).parse_args(argv)
    staged = args.staged or (args.mode == "staged" and not args.files)
    findings = scan(files_to_check(args.files), staged, analyze)
    if args.report:
        write_report(args.report, findings)
    return emit(findings, args.strict, label)
