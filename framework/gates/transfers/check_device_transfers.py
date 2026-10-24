"""CLI entry point for the device-transfer bottleneck gate.

Thumbnail: CLI checker grading HNS056-HNS060 host-device transfer shapes.

Invariants & Expected State:
    - The population is the static roots minus the excluded trees; a named path
      outside it is reported ``out of scope`` rather than silently graded.
    - ``--staged`` reads each named module from the Git index, so the decision is
      what the commit writes and not what the working copy happens to hold.
    - Every finding carries a ``trigger`` (loop, aggregate, streaming, static) so
      a name-triggered hit is never presented as a measured per-iteration cost,
      and the run prints that split beside its code counts.
    - An unreadable staged blob is an ``HNS010`` finding: unreadable source is
      never treated as clean source, and ``--strict`` exits 1 on any finding.
    - A clean run states how many modules it read; a gate that prints nothing
      cannot be told apart from a gate that scanned nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework import harness
from framework.gates.transfers.targets import (
    Finding,
    _files_to_check,
    _load_source,
)
from framework.gates.transfers.visitor import analyze_transfers

SCHEMA = f"{harness.SLUG}.device-transfers.v1"


def _scan_paths(paths: list[str], staged: bool) -> list[Finding]:
    """Analyze all candidate paths and collect findings, failing closed on read errors."""
    all_findings: list[Finding] = []
    for path in paths:
        source, err_finding = _load_source(path, staged)
        if err_finding is not None:
            all_findings.append(err_finding)
            continue
        if source is not None:
            all_findings.extend(analyze_transfers(source, path))
    return all_findings


def _write_report(report_path: Path, findings: list[Finding]) -> None:
    """Serialize findings and their trigger split to a structured JSON report."""
    data = [
        {
            "path": f.path,
            "line": f.line,
            "code": f.code,
            "message": f.message,
            "trigger": f.trigger,
        }
        for f in findings
    ]
    report_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _report_findings(findings: list[Finding], strict: bool, checked: int) -> int:
    """Print findings to stderr and return exit code."""
    for finding in findings:
        print(f"[check_device_transfers] {finding.format()}", file=sys.stderr)
    if findings:
        counts = Counter(f.code for f in findings)
        triggers = Counter(f.trigger for f in findings)
        print(
            f"[check_device_transfers] code split: "
            f"{', '.join(f'{code} {count}' for code, count in sorted(counts.items()))}; "
            f"loop-triggered {triggers['loop']}, aggregate {triggers['aggregate']}, "
            f"streaming-name {triggers['streaming']}, static {triggers['static']}",
            file=sys.stderr,
        )
    if findings and strict:
        print(
            f"[check_device_transfers] STRICT FAIL: {len(findings)} finding(s)",
            file=sys.stderr,
        )
        return 1
    # A clean run must say what it read: a gate that prints nothing cannot be
    # distinguished from a gate that scanned nothing.
    print(
        f"[check_device_transfers] checked {checked} module(s), {len(findings)} finding(s)",
        file=sys.stderr,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for device transfer gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="read from git index")
    parser.add_argument("--strict", action="store_true", help="fail on findings")
    parser.add_argument(
        "--mode", choices=["staged", "all"], default="staged", help="audit mode"
    )
    parser.add_argument("--report", type=Path, help="write JSON report of findings")
    parser.add_argument("files", nargs="*", help="optional paths to inspect")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point executing host-device transfer audit."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    staged = args.staged or (args.mode == "staged" and not args.files)
    target_files = _files_to_check(args.files)
    findings = _scan_paths(target_files, staged=staged)
    if args.report:
        _write_report(args.report, findings)
    return _report_findings(findings, strict=args.strict, checked=len(target_files))


if __name__ == "__main__":
    sys.exit(main())
