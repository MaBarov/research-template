"""CLI entry point for the accelerator memory bottleneck gate.

Thumbnail: CLI scanner reporting in-loop tensor retention and allocation findings.

Invariants & Expected State:
    --staged loads blobs from the Git index, so a dirty worktree cannot shift a verdict.
    --strict turns any finding into exit code 1; without it a run stays informational.
    A staged blob that will not load still emits HNS010 and fails closed under --strict.
    --report writes a JSON array of path, line, code, message and trigger rows.
    Findings stream to stderr as ``[check_memory] path:line: CODE message``, followed by
    the per-code split and, under --strict, the failing total.
    A clean run prints a summary (checked N module(s), M finding(s)).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework import harness
from framework.gates.memory.targets import Finding, _files_to_check, _load_source
from framework.gates.memory.visitor import analyze_memory

PREFIX = "[check_memory]"
SCHEMA = f"{harness.SLUG}.memory-bottlenecks.v1"


def _path_findings(path: str, staged: bool) -> list[Finding]:
    """Return what one path contributes: its load failure, or its rule findings."""
    source, failure = _load_source(path, staged)
    if failure is not None:
        return [failure]
    return [] if source is None else analyze_memory(source, path)


def _scan(paths: list[str], staged: bool) -> list[Finding]:
    """Collect the findings of every candidate path, one path at a time."""
    return [finding for path in paths for finding in _path_findings(path, staged)]


def _code_split(findings: list[Finding]) -> str:
    """Return the sorted ``CODE count`` summary of one finding list."""
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.code] = counts.get(finding.code, 0) + 1
    return ", ".join(f"{code} {total}" for code, total in sorted(counts.items()))


def _write_report(dest: Path, findings: list[Finding]) -> None:
    """Serialize findings as the path, line, code, message and trigger rows."""
    rows = [vars(finding) for finding in findings]
    dest.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _emit(findings: list[Finding], strict: bool, checked: int) -> int:
    """Stream one diagnostic per finding plus the split, then vote on exit status."""
    for finding in findings:
        print(f"{PREFIX} {finding.format()}", file=sys.stderr)
    if findings:
        print(f"{PREFIX} code split: {_code_split(findings)}", file=sys.stderr)
    if findings and strict:
        print(f"{PREFIX} STRICT FAIL: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    print(
        f"{PREFIX} checked {checked} module(s), {len(findings)} finding(s)",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, audit the selected sources, and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="read from git index")
    parser.add_argument("--strict", action="store_true", help="fail on findings")
    parser.add_argument("--mode", choices=("staged", "all"), default="staged")
    parser.add_argument("--report", type=Path, help="write JSON report of findings")
    parser.add_argument("files", nargs="*", help="optional paths to inspect")
    options = parser.parse_args(argv)
    staged = options.staged or (options.mode == "staged" and not options.files)
    target_files = _files_to_check(options.files)
    findings = _scan(target_files, staged)
    if options.report:
        _write_report(options.report, findings)
    return _emit(findings, options.strict, len(target_files))


if __name__ == "__main__":
    sys.exit(main())
