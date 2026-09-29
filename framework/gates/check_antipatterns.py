#!/usr/bin/env python3
"""Fail-closed static checks for high-risk production anti-patterns.

Thumbnail: Gate entry point that raises the HNS0NN codes for production sources.

Invariants & Expected State:
    ``--staged`` reads every source from the Git index, so an unstaged edit in
    the same path cannot change the verdict; with no paths, the production roots
    (``research``, ``scripts``, ``slurm``) are walked.  Each check is mechanical and
    carries a safe replacement, and a rule that cannot see its shape stays
    silent rather than guessing.  Findings print one per line as
    ``path:line: CODE message``; ``--strict`` turns any finding into a non-zero
    exit, and an unreadable or unparseable production module fails closed
    (HNS010/HNS000) instead of being skipped.  Tests, third-party code and test
    fixtures are never in scope.

This gate intentionally checks only mechanical patterns with a clear, safe
replacement.  It is run on staged production files by ``framework/hooks``.
Tests, third-party code, and framework test fixtures are not in its scope.

Usage::

    python framework/gates/check_antipatterns.py --strict --staged -- FILE...

With no files, all files below ``research/``, ``scripts/``, and ``slurm/`` are
checked.  Directory arguments are expanded to the production files they hold.
When ``--staged`` is supplied, source is read from the Git index so unstaged
edits cannot affect the result.

Codes and their safe replacements::

    HNS000 unparseable production Python          fix the syntax error
    HNS001 runtime ``assert``                     raise an explicit exception
    HNS002 ``torch.load`` without ``weights_only=True``
                                                  pass weights_only=True
    HNS003 ``zip`` without ``strict=True``        pass strict=True
    HNS004 unchecked ``load_state_dict(strict=False)``
                                                  validate both key lists
    HNS005 broad ``except``                       catch the expected exception
    HNS006 artifact read failure treated as miss  only a missing path may be None
    HNS007 CUDA-unavailable CPU fallback          reject the missing GPU explicitly
    HNS008 Git provenance fallback                let the run fail closed
    HNS009 swallowed command failure              handle or drop ``|| true``
    HNS010 unreadable source                      make the file readable UTF-8
    HNS011 ``except`` body is ``pass``            record or re-raise the failure
    HNS012 ``{"error": ...}`` sentinel return     raise / flag the report incomplete
    HNS013 provenance fallback in Python          let the run fail closed
    HNS014 wall-clock ``time.time()`` timing      use ``time.monotonic()``
    HNS015 unsafe deserialization                 ``torch.load(weights_only=True)``
    HNS016 dynamic code execution                 ``ast.literal_eval`` for data
    HNS017 shell execution sink                   pass an argv list
    HNS018 discarded ``subprocess`` failure       ``check=True``/read ``returncode``
    HNS019 shell without ``set -euo pipefail``    add it
    HNS020 buffered Python script invocation      run with ``-u``/``PYTHONUNBUFFERED=1``
    HNS021 text I/O without explicit encoding     pass encoding="utf-8"
    HNS022 in-loop torch.cuda.empty_cache()       remove empty_cache from loop
    HNS023 naive datetime.now() without timezone  use datetime.now(timezone.utc)
    HNS024 insecure yaml.load deserialization     use yaml.safe_load
    HNS025 SLURM script missing PYTHONPATH      export PYTHONPATH="$ROOT"
    HNS026 SLURM script missing PYTHONUNBUFFERED  export PYTHONUNBUFFERED=1
    HNS027 subprocess without ``timeout=``        pass ``timeout=`` and handle the expiry
    HNS030 rate over a vacuous population         reject the empty population
    HNS031 error bar collapsed under 2 samples    omit the bar or refuse the verdict
    HNS032 provenance helper sentinel fallback    let the run fail closed
    HNS033 log-only handler keeps placeholder    fail closed or record the failure
    HNS034 optional input neutralized to empty    require it, or fail closed
    HNS035 dirty-run override in a shell script   delete the knob; refuse instead
    HNS036 conditional dirty-tree refusal         make the refusal unconditional
    HNS037 mode default outside its dispatch      match the default explicitly
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ENTRY_REPO = Path(__file__).resolve().parents[2]
if str(_ENTRY_REPO) not in sys.path:
    sys.path.insert(0, str(_ENTRY_REPO))

import framework.gates.antipattern.python_visitor
import framework.gates.antipattern.shell_checks
import framework.gates.antipattern.targets


def analyze_source(
    source: str, path: str
) -> list[framework.gates.antipattern.targets.Finding]:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return framework.gates.antipattern.python_visitor.analyze_python(source, path)
    if suffix in framework.gates.antipattern.targets.SHELL_SUFFIXES:
        return framework.gates.antipattern.shell_checks.analyze_shell(source, path)
    return []


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict", action="store_true", help="exit 1 when findings exist"
    )
    parser.add_argument(
        "--staged", action="store_true", help="read each file from the Git index"
    )
    parser.add_argument("files", nargs="*", help="production files to inspect")
    return parser


def _report_findings(
    files: list[str],
    findings: list[framework.gates.antipattern.targets.Finding],
    strict: bool,
) -> int:
    """Print the findings and the summary line; return the process exit code."""

    for finding in findings:
        print(f"[check_antipatterns] {finding.format()}", file=sys.stderr)
    if findings and strict:
        print(
            f"[check_antipatterns] STRICT FAIL: {len(findings)} finding(s)",
            file=sys.stderr,
        )
        return 1
    print(
        f"[check_antipatterns] checked {len(framework.gates.antipattern.targets._files_to_check(files))} file(s), {len(findings)} finding(s)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    findings: list[framework.gates.antipattern.targets.Finding] = []
    for path in framework.gates.antipattern.targets._files_to_check(args.files):
        source, finding = framework.gates.antipattern.targets._load_source(
            path, args.staged
        )
        if finding is not None:
            findings.append(finding)
            continue
        findings.extend(analyze_source(source, path))

    return _report_findings(args.files, findings, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
