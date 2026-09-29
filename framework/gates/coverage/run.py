"""Probe invocation: pytest selection, execution and report validation.

Invariants & Expected State:
    * Exit 2 marks environment or usage errors: unreadable alias/waiver table,
      a missing baseline in ``--mode all``, no tests selected for the staged
      files, an interpreter without ``coverage``/``pytest``, a probe that wrote
      no report, a wrong report schema, or a pytest collection/internal error.
    * The report is validated before any finding is computed: its schema must be
      ``research.loop-coverage-report.v1`` and pytest ``exitstatus`` must be 0
      or 1.
    * ``--mode all`` selects the whole ``--tests`` target; ``--mode staged``
      selects exactly the mirror/alias tests of the staged files.
    * Baseline, waiver and alias data are read from the paths declared in
      ``framework.gates.coverage.config``; the module never invents them.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from framework.gates.checks import check_test_mirror as mirror
from framework.gates.coverage import config, ledger
from framework.gates.coverage.metrics import (
    Finding,
    _ProbeRun,
    evaluate,
    file_metrics,
    source_loop_lines,
    test_files_for,
)


def _load_config(
    args: argparse.Namespace,
) -> tuple[Mapping[str, Sequence[str]], dict[str, dict[str, str]]]:
    aliases = mirror.load_aliases(config.REPO / args.aliases)
    waivers = ledger._load_waivers(config.REPO / args.waivers)
    return aliases, waivers


def _mode_error(args: argparse.Namespace) -> int | None:
    if args.update_baseline and args.mode != "all":
        print(
            "[check_coverage] ERROR: --update-baseline requires --mode all",
            file=sys.stderr,
        )
        return 2
    return None


def _evidence_refresh_hint(files: Sequence[str]) -> str:
    return (
        "python framework/gates/check_coverage.py --mode staged --staged "
        + " ".join(files[:8])
        + (" …" if len(files) > 8 else "")
    )


def _report_evidence(
    files: Sequence[str],
    findings: Sequence[Finding],
    strict: bool,
) -> int:
    for finding in findings:
        print(f"[check_coverage] {finding.format()}", file=sys.stderr)
    print(
        f"[check_coverage] evidence: {len(files)} file(s), {len(findings)} finding(s)"
    )
    if findings and strict:
        print(
            f"[check_coverage] STRICT FAIL: {len(findings)} finding(s)",
            file=sys.stderr,
        )
        return 1
    return 0


def _run_evidence_only(
    args: argparse.Namespace,
    src_files: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    waivers: Mapping[str, Mapping[str, str]],
) -> int:
    """Decide from the recorded clearance ledger alone; return the exit code."""

    files = [rel for rel in src_files if Path(rel).name not in mirror.EXEMPT_NAMES]
    findings = ledger.check_evidence(
        ledger.load_evidence(config.REPO / args.evidence),
        files,
        aliases=aliases,
        exists=lambda path: (config.REPO / path).is_file(),
        mirrors=args.mirrors,
        waivers=waivers,
        min_coverage=args.min_coverage,
        require_cleared=args.mode == "staged",
        refresh_hint=_evidence_refresh_hint(files),
    )
    return _report_evidence(files, findings, args.strict)


def _no_tests_error(src_files: Sequence[str]) -> None:
    for rel in src_files:
        print(
            f"[check_coverage] NO TESTS: nothing selected for {rel}",
            file=sys.stderr,
        )
    print(
        "[check_coverage] ERROR: no mirror tests selected for the staged files",
        file=sys.stderr,
    )


def _select_tests(
    args: argparse.Namespace,
    src_files: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
) -> tuple[list[str], int | None]:
    """Return the pytest selection, or an exit code when nothing was selected."""

    if args.mode != "staged":
        return [args.tests], None
    selection = sorted(
        {
            test
            for rel in src_files
            for test in test_files_for(
                rel,
                aliases,
                lambda path: (config.REPO / path).is_file(),
                args.mirrors,
            )
        }
    )
    if selection:
        return selection, None
    _no_tests_error(src_files)
    return selection, 2


def _collect_loop_lines(
    src_files: Sequence[str],
) -> tuple[dict[str, list[int]] | None, int | None]:
    loop_lines: dict[str, list[int]] = {}
    for rel in src_files:
        try:
            loop_lines[rel] = source_loop_lines(config.REPO / rel)
        except SyntaxError as error:
            print(
                f"[check_coverage] ERROR: {rel}: cannot parse: {error}", file=sys.stderr
            )
            return None, 2
    return loop_lines, None


def _require_probe_interpreter() -> int | None:
    probe = subprocess.run(
        [sys.executable, "-c", "import coverage, pytest"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0:
        return None
    print(
        "[check_coverage] ERROR: the test interpreter lacks coverage/pytest; "
        f"install with: uv pip install --python {sys.executable} 'coverage>=7.4'",
        file=sys.stderr,
    )
    return 2


def _load_baseline(args: argparse.Namespace) -> tuple[Any, int | None]:
    baseline = ledger._json_or_none(config.REPO / args.baseline)
    if baseline is None and args.mode == "all" and not args.update_baseline:
        print(
            f"[check_coverage] ERROR: missing baseline {args.baseline}; "
            "generate it with --update-baseline",
            file=sys.stderr,
        )
        return None, 2
    return baseline, None


def _probe_command(
    args: argparse.Namespace,
    selection: Sequence[str],
    tmp: Path,
    report_path: Path,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        *selection,
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        config.PROBE_PLUGIN,
        "--cov-src",
        args.src,
        "--cov-json",
        str(report_path),
        f"--basetemp={tmp / 'bt'}",
    ]


def _no_report_error(run: subprocess.CompletedProcess[str]) -> int:
    tail = "\n".join((run.stdout + run.stderr).splitlines()[-15:])
    print(
        f"[check_coverage] ERROR: the probe produced no report; pytest said:\n{tail}",
        file=sys.stderr,
    )
    return 2


def _pytest_run(
    args: argparse.Namespace,
    selection: Sequence[str],
    tmp: Path,
    report_path: Path,
) -> int | None:
    command = _probe_command(args, selection, tmp, report_path)
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        run = subprocess.run(
            command,
            cwd=config.REPO,
            env=environment,
            capture_output=True,
            text=True,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(
            f"[check_coverage] ERROR: pytest exceeded --timeout {args.timeout:g}s",
            file=sys.stderr,
        )
        return 2
    if report_path.is_file():
        return None
    return _no_report_error(run)


def _run_probe(
    args: argparse.Namespace, selection: Sequence[str]
) -> tuple[Any, int | None]:
    """Run the pytest coverage probe; return ``(report, exit code)``."""

    with tempfile.TemporaryDirectory(prefix="research-coverage-gate-") as tmp:
        report_path = Path(tmp) / "report.json"
        code = _pytest_run(args, selection, Path(tmp), report_path)
        if code is not None:
            return None, code
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if args.json:
            (config.REPO / args.json).write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    return report, None


def _validate_report(report: Mapping[str, Any]) -> int | None:
    if report.get("schema") != config.REPORT_SCHEMA:
        print(
            f"[check_coverage] ERROR: unexpected report schema {report.get('schema')!r}",
            file=sys.stderr,
        )
        return 2
    pytest_info = report.get("pytest", {})
    if int(pytest_info.get("exitstatus", 0)) not in (0, 1):
        print(
            "[check_coverage] ERROR: pytest exit status "
            f"{pytest_info.get('exitstatus')} (collection or internal error)",
            file=sys.stderr,
        )
        return 2
    return None


def _probe_inputs(
    args: argparse.Namespace, src_files: Sequence[str]
) -> tuple[Any, Any, int | None]:
    """Return the loop lines and baseline of one run, or the failing exit code."""

    loop_lines, code = _collect_loop_lines(src_files)
    if code is not None:
        return None, None, code
    code = _require_probe_interpreter()
    if code is not None:
        return None, None, code
    baseline, code = _load_baseline(args)
    if code is not None:
        return None, None, code
    return loop_lines, baseline, None


def _prepare(
    args: argparse.Namespace, selection: Sequence[str], src_files: Sequence[str]
) -> _ProbeRun | int:
    """Return the probe run, or the exit code of the first failing step."""

    loop_lines, baseline, code = _probe_inputs(args, src_files)
    if code is not None:
        return code
    report, code = _run_probe(args, selection)
    if code is not None:
        return code
    code = _validate_report(report)
    if code is not None:
        return code
    return _ProbeRun(loop_lines, baseline, report)


def _failed_count(report: Mapping[str, Any]) -> int:
    return int(report.get("pytest", {}).get("failed", 0))


def _test_failure_finding(
    args: argparse.Namespace, report: Mapping[str, Any]
) -> list[Finding]:
    failed = _failed_count(report)
    if not failed or args.allow_test_failures:
        return []
    return [
        Finding(
            "",
            "TEST FAILURES",
            f"{failed} failed; fix the suite before reading coverage",
        )
    ]


def _staged_run_failed(args: argparse.Namespace, report: Mapping[str, Any]) -> bool:
    failed = _failed_count(report)
    return bool(failed and not args.allow_test_failures)


def _staged_entry(
    args: argparse.Namespace,
    rel: str,
    report: Mapping[str, Any],
    aliases: Mapping[str, Sequence[str]],
    waivers: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    metrics = _staged_metrics(rel, report, aliases, args, waivers)
    return ledger.build_entry(
        rel,
        measured=metrics.measured,
        statements=metrics.statements,
        self_pct=metrics.self_pct,
        suite_pct=metrics.suite_pct,
        loops_uncovered=metrics.loops_uncovered,
        aliases=aliases,
        exists=lambda path: (config.REPO / path).is_file(),
        mirrors=args.mirrors,
        waivers=waivers.get(rel, {}),
        min_coverage=args.min_coverage,
    )


def _staged_metrics(rel, report, aliases, args, waivers):
    metrics = file_metrics(
        rel,
        report.get("files", {}).get(rel),
        test_files_for(
            rel,
            aliases,
            lambda path: (config.REPO / path).is_file(),
            args.mirrors,
        ),
        waivers.get(rel, {}),
    )
    return metrics


def _record_staged_evidence(
    args: argparse.Namespace,
    report: Mapping[str, Any],
    src_files: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    waivers: Mapping[str, Mapping[str, str]],
) -> None:
    """Record the content-addressed clearance entries of the staged files."""

    entries = {
        rel: _staged_entry(args, rel, report, aliases, waivers) for rel in src_files
    }
    ledger.write_evidence(config.REPO / args.evidence, entries)


def _collect_findings(
    args: argparse.Namespace,
    run: _ProbeRun,
    src_files: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    waivers: Mapping[str, Mapping[str, str]],
) -> list[Finding]:
    """Return the evaluation findings plus the test-failure finding."""

    findings = evaluate(
        run.report,
        run.baseline,
        waivers,
        src_files=src_files,
        aliases=aliases,
        exists=lambda path: (config.REPO / path).is_file(),
        loop_lines=run.loop_lines,
        mirrors=args.mirrors,
        mode=args.mode,
        min_coverage=args.min_coverage,
    )
    findings.extend(_test_failure_finding(args, run.report))
    return findings
