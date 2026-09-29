#!/usr/bin/env python3
"""Per-file statement and loop-iteration coverage gate for the production tree.

Runs the mirror tests of the files under ``--src`` with
``framework.gates.coverage.coverage_probe`` (statement coverage with per-test contexts
plus exact loop-iteration counts) and enforces:

* ``--mode staged`` (the pre-commit hook): every staged source file must be
  **cleared on its own** — its mirror/alias tests must exist, must be the ones
  selected, must reach ``--min-coverage`` (default 80%) and must exercise every
  loop the file contains with 0, 1 and >=2 iterations. No baseline
  grandfathering: touching a file means clearing it.
* ``--mode all`` (the whole-tree audit): each file must stay at or above its
  recorded baseline (``self`` and ``suite``) and may not lose loop cases;
  files without a baseline entry need ``--min-coverage``.

Loop criterion: per loop ordinal, the observed entry multiset must contain a
0-iteration entry (or no entry at all), a 1-iteration entry and a >=2-iteration
entry. ``--waivers`` may exempt the 0-case of a specific loop with a reason
(a loop whose empty-iterable path is guarded away cannot satisfy it).

Fast path: ``--evidence-only`` decides clearance from the content-addressed
ledger (``framework/coverage_evidence.json``) without running tests or needing
coverage/pytest installed. A staged file passes when the recorded fingerprints
of the file, its test files and its waivers still match the working tree and
the recorded run met the criterion — comments, formatting and line moves do not
invalidate a record. The pre-commit hook uses this (sub-second). Refreshing is
explicit: any ``--mode staged`` run executes the mirror tests and rewrites the
ledger entries for the files it checked, so a changed file is committed only
after its mirror tests have cleared it. ``--update-baseline`` records the
whole-tree baseline and ledger in one run.

The pre-commit hook runs this against the working tree: tests cannot execute
against the Git index, so stage the mirror tests together with the source.

Exit codes: 0 clean; 1 findings (with ``--strict``) or refused baseline update;
2 environment or usage error.

Usage::

  <test interpreter> framework/gates/check_coverage.py --mode all --strict
  <test interpreter> framework/gates/check_coverage.py --mode staged --strict \\
      --staged research/a/b.py            # run + record clearance for these files
  python framework/gates/check_coverage.py --mode staged --evidence-only \\
      --strict --staged research/a/b.py   # decide from the ledger only (fast)

Invariants & Expected State:
    * Exit 0 clean, 1 findings under ``--strict``, 2 environment or usage
      error; a missing baseline or no selected tests exit 2, never clean.
    * ``--mode staged`` requires every staged source file to clear on its own
      (mirror tests, ``--min-coverage`` and 0/1/>=2 loop cases) with no
      baseline grandfathering; ``--mode all`` compares against the baseline.
    * ``--evidence-only`` decides from the content-addressed ledger
      ``framework/coverage_evidence.json`` and runs no tests.
    * ``--update-baseline`` is refused (exit 2) unless ``--mode all``.
    * Paths and schema names come from ``framework.gates.coverage.config``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_ENTRY_REPO = Path(__file__).resolve().parents[2]
if str(_ENTRY_REPO) not in sys.path:
    sys.path.insert(0, str(_ENTRY_REPO))

from framework.gates.checks import check_test_mirror as mirror
from framework.gates.coverage import config, ledger, metrics
from framework.gates.coverage import run as covrun


def _select_staged(staged: Sequence[str]) -> list[str]:
    return [
        rel
        for rel in staged
        if mirror.is_checked_path(rel, config.DEFAULT_SRC)
        and not mirror.is_skipped(rel)
        and Path(rel).name not in mirror.EXEMPT_NAMES
    ]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    return _build_parser().parse_args(argv)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    _add_scope_arguments(parser)
    _add_ledger_arguments(parser)
    _add_execution_arguments(parser)
    return parser


def _add_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--src",
        default=config.DEFAULT_SRC,
        help="source directory",
    )
    parser.add_argument(
        "--tests",
        default=config.DEFAULT_TESTS,
        help="pytest target",
    )
    parser.add_argument(
        "--mirrors",
        default=mirror.DEFAULT_TESTS,
        help="mirror test base for path construction",
    )
    parser.add_argument(
        "--mode", choices=("all", "staged"), default="all", help="check scope"
    )
    parser.add_argument(
        "--staged", nargs="*", help="source files to check (pre-commit hook)"
    )
    parser.add_argument("--min-coverage", type=float, default=80.0)


def _add_ledger_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--baseline", default=config.DEFAULT_BASELINE)
    parser.add_argument("--aliases", default=config.DEFAULT_ALIASES)
    parser.add_argument("--waivers", default=config.DEFAULT_WAIVERS)
    parser.add_argument(
        "--evidence",
        default=config.DEFAULT_EVIDENCE,
        help="content-addressed clearance ledger",
    )
    parser.add_argument(
        "--evidence-only",
        action="store_true",
        help="decide from the recorded ledger alone (no test run; sub-second)",
    )


def _add_execution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--accept-regression", action="store_true")
    parser.add_argument("--allow-test-failures", action="store_true")
    parser.add_argument("--json", help="write the raw probe report here")
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--strict", action="store_true", help="exit 1 on findings")


def _report_findings(
    findings: Sequence[metrics.Finding],
    checked: Sequence[str],
    measured: int,
    strict: bool,
) -> int:
    """Print the findings and the summary line; return the process exit code."""

    for finding in findings:
        print(f"[check_coverage] {finding.format()}", file=sys.stderr)
    print(
        f"[check_coverage] checked {len(checked)} file(s), {measured} measured, "
        f"{len(findings)} finding(s)"
    )
    if findings and strict:
        print(
            f"[check_coverage] STRICT FAIL: {len(findings)} finding(s)",
            file=sys.stderr,
        )
        return 1
    return 0


def _finish(
    args: argparse.Namespace,
    run: metrics._ProbeRun,
    src_files: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    waivers: Mapping[str, Mapping[str, str]],
) -> int:
    """Evaluate the report, refresh the ledger when asked, print the verdict."""

    findings = covrun._collect_findings(args, run, src_files, aliases, waivers)
    checked = [rel for rel in src_files if Path(rel).name not in mirror.EXEMPT_NAMES]
    measured = sum(
        1 for rel in checked if run.report.get("files", {}).get(rel) is not None
    )
    if args.mode == "staged" and not covrun._staged_run_failed(args, run.report):
        covrun._record_staged_evidence(args, run.report, src_files, aliases, waivers)
    if args.update_baseline:
        return ledger._update_baseline(args, run, findings, src_files, aliases, waivers)
    return _report_findings(findings, checked, measured, args.strict)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        aliases, waivers = covrun._load_config(args)
    except (OSError, ValueError, TypeError) as error:
        print(f"[check_coverage] ERROR: {error}", file=sys.stderr)
        return 2
    code = covrun._mode_error(args)
    if code is not None:
        return code

    staged = _select_staged(args.staged or [])
    src_files = mirror.collect_files(
        args.src, staged if args.mode == "staged" else None
    )
    if args.mode == "staged" and not src_files:
        print("[check_coverage] checked 0 file(s), 0 finding(s)")
        return 0
    if args.evidence_only:
        return covrun._run_evidence_only(args, src_files, aliases, waivers)
    selection, code = covrun._select_tests(args, src_files, aliases)
    if code is not None:
        return code
    run = covrun._prepare(args, selection, src_files)
    if isinstance(run, int):
        return run
    return _finish(args, run, src_files, aliases, waivers)


if __name__ == "__main__":
    raise SystemExit(main())
