"""Clearance ledger: baseline, evidence fingerprints and evaluation.

The ledger records, per source file, the evidence that its tests cleared it —
coverage percentage, executed line count, the fingerprint of its executable
structure and of the tests that own it — so the commit battery can decide a
staged file's clearance without running the suite again.

Invariants & Expected State:
    - Clearance is content-addressed: an entry matches only while the file's
      executable structure and its owning tests still fingerprint the same;
      comments, formatting, docstrings and line moves are free.
    - Staleness is a finding: a recorded clearance that no longer matches the
      working tree is reported and must be refreshed, never trusted.
    - ``check_evidence`` decides from the ledger alone — no test run and no
      interpreter in the decision path.
    - A waiver is recorded evidence for one loop and mode; a waiver that no
      longer matches a reported loop is itself reported.
    - An incomplete instrumentation run is refused outright rather than read as
      full coverage.
    - Baseline moves in one direction: regressions are reported and block, the
      baseline is only advanced when the evidence justifies it, and the
      refreshed baseline is written together with the ledger it came from.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from framework.gates.checks import check_test_mirror as mirror
from framework.gates.coverage import config
from framework.gates.coverage.metrics import (
    FileMetrics,
    Finding,
    _EvidenceContext,
    _ProbeRun,
    file_metrics,
    test_files_for,
)


def _baseline_entry(
    metrics: FileMetrics,
) -> dict[str, Any]:
    """Return the recorded baseline fields of one file's metrics."""

    return {
        "measured": metrics.measured,
        "statements": metrics.statements,
        "self": round(metrics.self_pct, 1),
        "suite": round(metrics.suite_pct, 1),
        "loops_uncovered": list(metrics.loops_uncovered),
    }


def _baseline_files(
    report_files: Mapping[str, Any],
    *,
    src_files: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    exists: Callable[[str], bool],
    waivers: Mapping[str, Mapping[str, str]],
    mirrors: str,
) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for rel in src_files:
        if Path(rel).name in mirror.EXEMPT_NAMES:
            continue
        waived = waivers.get(rel, {})
        metrics = file_metrics(
            rel,
            report_files.get(rel),
            test_files_for(rel, aliases, exists, mirrors),
            waived,
        )
        files[rel] = _baseline_entry(metrics)
    return files


def _generated_provenance(tests_root: str) -> dict[str, str]:
    return {
        "python": ".".join(str(part) for part in sys.version_info[:3]),
        "coverage": _coverage_version(),
        "tests": tests_root,
    }


def build_baseline(
    report: Mapping[str, Any],
    *,
    src_files: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    exists: Callable[[str], bool],
    waivers: Mapping[str, Mapping[str, str]],
    mirrors: str,
    tests_root: str,
    min_coverage: float,
) -> dict[str, Any]:
    """Return the whole-tree baseline document for one probe report."""

    files = _baseline_files(
        report.get("files", {}),
        src_files=src_files,
        aliases=aliases,
        exists=exists,
        waivers=waivers,
        mirrors=mirrors,
    )
    return {
        "schema": config.BASELINE_SCHEMA,
        "min_coverage": min_coverage,
        "loop_criterion": config.LOOP_CRITERION,
        "generated": _generated_provenance(tests_root),
        "files": files,
    }


def _coverage_version() -> str:
    try:
        from importlib.metadata import version

        return version("coverage")
    except Exception:  # noqa: BLE001 - provenance only
        return "unknown"


def baseline_regressions(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    """Return human-readable coverage regressions between two baselines."""

    regressions: list[str] = []
    old_files = old.get("files", {})
    for rel, entry in sorted(new.get("files", {}).items()):
        previous = old_files.get(rel)
        if previous is None:
            continue
        if entry["self"] < previous["self"]:
            regressions.append(f"{rel} self {previous['self']}% -> {entry['self']}%")
        if entry["suite"] < previous["suite"]:
            regressions.append(f"{rel} suite {previous['suite']}% -> {entry['suite']}%")
        lost = sorted(
            set(entry["loops_uncovered"]) - set(previous.get("loops_uncovered", ()))
        )
        for ordinal in lost:
            regressions.append(f"{rel} loop #{ordinal} lost a satisfied case")
    return regressions


def _json_or_none(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_waivers(path: Path) -> dict[str, dict[str, str]]:
    payload = _json_or_none(path)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise TypeError(f"{path}: waivers must be a JSON object")
    waivers: dict[str, dict[str, str]] = {}
    for rel, entries in payload.items():
        if not isinstance(entries, dict):
            raise TypeError(f"{path}: {rel}: waivers must map ordinal -> reason")
        for ordinal, reason in entries.items():
            if not isinstance(reason, str) or not reason.strip():
                raise TypeError(f"{path}: {rel}:{ordinal}: a reason is required")
        waivers[rel] = {
            str(ordinal): str(reason) for ordinal, reason in entries.items()
        }
    return waivers


def cleared_by(entry: Mapping[str, Any], min_coverage: float) -> bool:
    """Return whether a recorded entry satisfies the staged clearance criterion."""

    return (
        bool(entry.get("measured"))
        and float(entry.get("self", 0.0)) >= min_coverage - 1e-9
        and not entry.get("loops_uncovered")
    )


def _strip_docstrings(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:]


def structure_hash(path: Path) -> str:
    """Fingerprint executable structure: comments, formatting and line moves are free."""

    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    _strip_docstrings(tree)
    return hashlib.sha256(ast.dump(tree).encode("utf-8")).hexdigest()


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _test_structure_hashes(tests: Sequence[str]) -> dict[str, str]:
    """Return the executable-structure fingerprints of the given test files."""

    hashes: dict[str, str] = {}
    for test in tests:
        try:
            hashes[test] = structure_hash(config.REPO / test)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
    return hashes


def build_entry(
    rel: str,
    *,
    measured: bool,
    statements: int,
    self_pct: float,
    suite_pct: float,
    loops_uncovered: Sequence[int],
    aliases: Mapping[str, Sequence[str]],
    exists: Callable[[str], bool],
    mirrors: str,
    waivers: Mapping[str, str],
    min_coverage: float,
) -> dict[str, Any]:
    """Build one content-addressed clearance record for a source file."""

    entry: dict[str, Any] = {
        "structure": structure_hash(config.REPO / rel),
        "tests": _test_structure_hashes(test_files_for(rel, aliases, exists, mirrors)),
        "waivers": {str(k): _digest(v) for k, v in sorted(waivers.items())},
        "measured": measured,
        "statements": statements,
        "self": self_pct,
        "suite": suite_pct,
        "loops_uncovered": sorted(int(value) for value in loops_uncovered),
    }
    entry["cleared"] = cleared_by(entry, min_coverage)
    return entry


def load_evidence(path: Path) -> dict[str, Any]:
    payload = _json_or_none(path)
    if not isinstance(payload, dict) or payload.get("schema") != config.EVIDENCE_SCHEMA:
        return {}
    return payload.get("files", {})


def write_evidence(path: Path, entries: Mapping[str, Any]) -> None:
    files = dict(load_evidence(path))
    files.update(entries)
    files = {rel: files[rel] for rel in sorted(files) if (config.REPO / rel).is_file()}
    payload = {
        "schema": config.EVIDENCE_SCHEMA,
        "generated_by": "framework/gates/check_coverage.py",
        "files": files,
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _recorded_waivers(waivers: Mapping[str, str]) -> dict[str, str]:
    return {str(k): _digest(v) for k, v in sorted(waivers.items())}


def _evidence_stale(
    rel: str,
    entry: Mapping[str, Any],
    tests: Sequence[str],
    current_waivers: Mapping[str, str],
    recorded: Mapping[str, Any],
) -> bool:
    """Return whether a recorded clearance no longer matches the working tree."""

    if (
        set(tests) != set(recorded)
        or entry.get("waivers", {}) != current_waivers
        or not isinstance(entry.get("structure"), str)
    ):
        return True
    try:
        if structure_hash(config.REPO / rel) != entry["structure"]:
            return True
        for test in tests:
            if structure_hash(config.REPO / test) != recorded.get(test):
                return True
    except (OSError, SyntaxError, UnicodeDecodeError):
        return True
    return False


def _stale_findings(
    rel: str,
    entry: Mapping[str, Any],
    context: _EvidenceContext,
) -> list[Finding] | None:
    """Return the staleness finding of one file, or ``None`` when it matches."""

    tests = test_files_for(rel, context.aliases, context.exists, context.mirrors)
    recorded = entry.get("tests", {})
    current = _recorded_waivers(context.waivers.get(rel) or {})
    if not _evidence_stale(rel, entry, tests, current, recorded):
        return None
    return [
        Finding(
            rel,
            "EVIDENCE STALE",
            f"recorded clearance no longer matches {rel} or its tests; "
            f"refresh: {context.refresh_hint}",
        )
    ]


def _not_cleared_findings(
    rel: str,
    entry: Mapping[str, Any],
    context: _EvidenceContext,
) -> list[Finding]:
    """Return the not-cleared finding of one file (empty when clearance holds)."""

    if not context.require_cleared or cleared_by(entry, context.min_coverage):
        return []
    return [
        Finding(
            rel,
            "NOT CLEARED",
            f"{rel} is not cleared (self {entry.get('self')}%, "
            f"statements {entry.get('statements')}, "
            f"loops uncovered {entry.get('loops_uncovered')}); "
            f"refresh: {context.refresh_hint}",
        )
    ]


def _evidence_findings(
    rel: str,
    entry: Mapping[str, Any] | None,
    context: _EvidenceContext,
) -> list[Finding]:
    """Return the evidence findings of one file (missing, stale or not cleared)."""

    if not isinstance(entry, dict):
        return [
            Finding(
                rel,
                "EVIDENCE MISSING",
                f"no recorded clearance for {rel}; refresh: {context.refresh_hint}",
            )
        ]
    findings = _stale_findings(rel, entry, context)
    if findings is not None:
        return findings
    return _not_cleared_findings(rel, entry, context)


def check_evidence(
    evidence: Mapping[str, Any],
    src_files: Sequence[str],
    *,
    aliases: Mapping[str, Sequence[str]],
    exists: Callable[[str], bool],
    mirrors: str,
    waivers: Mapping[str, Mapping[str, str]],
    min_coverage: float,
    require_cleared: bool,
    refresh_hint: str,
) -> list[Finding]:
    """Decide clearance from recorded evidence alone; no test run, no interpreter."""

    context = _EvidenceContext(
        aliases=aliases,
        exists=exists,
        mirrors=mirrors,
        waivers=waivers,
        min_coverage=min_coverage,
        require_cleared=require_cleared,
        refresh_hint=refresh_hint,
    )
    return [
        finding
        for rel in src_files
        for finding in _evidence_findings(rel, evidence.get(rel), context)
    ]


def _refuse_instrumentation_gap(
    findings: Sequence[Finding],
) -> int | None:
    gap = [
        finding for finding in findings if finding.code == "LOOP INSTRUMENTATION GAP"
    ]
    if not gap:
        return None
    for finding in gap:
        print(f"[check_coverage] {finding.format()}", file=sys.stderr)
    print(
        "[check_coverage] ERROR: refusing to record an instrumentation gap",
        file=sys.stderr,
    )
    return 1


def _new_baseline(
    args: argparse.Namespace,
    run: _ProbeRun,
    src_files: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    waivers: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    return build_baseline(
        run.report,
        src_files=src_files,
        aliases=aliases,
        exists=lambda path: (config.REPO / path).is_file(),
        waivers=waivers,
        mirrors=args.mirrors,
        tests_root=args.tests,
        min_coverage=args.min_coverage,
    )


def _report_regressions(
    baseline: Mapping[str, Any],
    new_baseline: Mapping[str, Any],
    accept_regression: bool,
) -> int | None:
    regressions = baseline_regressions(baseline, new_baseline)
    for line in regressions:
        print(f"[check_coverage] REGRESSION: {line}", file=sys.stderr)
    if regressions and not accept_regression:
        print(
            "[check_coverage] ERROR: refusing to lower the baseline; pass "
            "--accept-regression to record it deliberately",
            file=sys.stderr,
        )
        return 1
    return None


def _report_improvements(
    baseline: Mapping[str, Any], new_baseline: Mapping[str, Any]
) -> None:
    improved = [
        (rel, old["self"], entry["self"])
        for rel, entry in sorted(new_baseline["files"].items())
        if (old := baseline.get("files", {}).get(rel)) is not None
        and entry["self"] > old["self"]
    ]
    for rel, old_pct, new_pct in sorted(
        improved, key=lambda row: row[2] - row[1], reverse=True
    )[:10]:
        print(f"[check_coverage] improved: {rel} {old_pct}% -> {new_pct}%")


def _baseline_ledger_entry(
    args: argparse.Namespace,
    rel: str,
    fields: Mapping[str, Any],
    aliases: Mapping[str, Sequence[str]],
    waivers: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    return build_entry(
        rel,
        measured=bool(fields.get("measured", False)),
        statements=int(fields.get("statements", 0)),
        self_pct=float(fields.get("self", 0.0)),
        suite_pct=float(fields.get("suite", 0.0)),
        loops_uncovered=fields.get("loops_uncovered", ()),
        aliases=aliases,
        exists=lambda path: (config.REPO / path).is_file(),
        mirrors=args.mirrors,
        waivers=waivers.get(rel, {}),
        min_coverage=args.min_coverage,
    )


def _write_baseline(
    args: argparse.Namespace,
    new_baseline: Mapping[str, Any],
    aliases: Mapping[str, Sequence[str]],
    waivers: Mapping[str, Mapping[str, str]],
) -> None:
    """Write the new baseline document and refresh the ledger from it."""

    path = config.REPO / args.baseline
    path.write_text(
        json.dumps(new_baseline, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_evidence(
        config.REPO / args.evidence,
        {
            rel: _baseline_ledger_entry(args, rel, fields, aliases, waivers)
            for rel, fields in new_baseline["files"].items()
        },
    )


def _update_baseline(
    args: argparse.Namespace,
    run: _ProbeRun,
    findings: Sequence[Finding],
    src_files: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    waivers: Mapping[str, Mapping[str, str]],
) -> int:
    """Write the whole-tree baseline plus ledger; return the process exit code."""

    code = _refuse_instrumentation_gap(findings)
    if code is not None:
        return code
    new_baseline = _new_baseline(args, run, src_files, aliases, waivers)
    if run.baseline is not None:
        code = _report_regressions(run.baseline, new_baseline, args.accept_regression)
        if code is not None:
            return code
        _report_improvements(run.baseline, new_baseline)
    _write_baseline(args, new_baseline, aliases, waivers)
    print(
        f"[check_coverage] baseline written: {args.baseline} "
        f"({len(new_baseline['files'])} file(s))"
    )
    return 0
