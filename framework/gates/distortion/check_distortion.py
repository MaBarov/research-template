"""CLI entry point for the surrogate distortion gate.

Thumbnail: CLI checker scanning staged or tree sources for HNS044, HNS045, and HNS046 findings.

Invariants & Expected State:
    --staged reads blobs from the Git index so unstaged edits cannot affect results.
    --strict exits with code 1 if any findings are discovered.
    Unreadable staged sources emit HNS010 and fail closed under --strict.
    --report writes a machine-readable JSON finding list.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework.gates.distortion.targets import (
    Finding,
    _files_to_check,
    _load_source,
)
from framework.gates.distortion.visitor import analyze_distortion


def _scan_paths(paths: list[str], staged: bool) -> list[Finding]:
    """Analyze all candidate paths and collect findings, failing closed on read errors."""
    all_findings: list[Finding] = []
    for path in paths:
        source, err_finding = _load_source(path, staged)
        if err_finding is not None:
            all_findings.append(err_finding)
            continue
        all_findings.extend(analyze_distortion(source, path))
    return all_findings


def _write_report(report_path: Path, findings: list[Finding]) -> None:
    """Serialize findings to a structured JSON machine report."""
    data = [
        {"path": f.path, "line": f.line, "code": f.code, "message": f.message}
        for f in findings
    ]
    report_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for distortion gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="read from git index")
    parser.add_argument("--strict", action="store_true", help="fail on findings")
    parser.add_argument("--report", type=Path, help="write JSON report of findings")
    parser.add_argument("files", nargs="*", help="optional paths to inspect")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint executing distortion audit."""
    args = _build_parser().parse_args(argv)
    paths = _files_to_check(args.files)
    findings = _scan_paths(paths, args.staged)
    for finding in findings:
        print(f"[check_distortion] {finding.format()}", file=sys.stderr)
    print(
        f"[check_distortion] checked {len(paths)} file(s), {len(findings)} finding(s)",
        file=sys.stderr,
    )
    if args.report:
        _write_report(args.report, findings)
    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
