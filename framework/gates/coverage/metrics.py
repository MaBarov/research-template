"""Report dataclasses and per-file coverage/loop metrics.

Turns one coverage probe report into the findings of every source file in
scope: the lines its own probe executed, the lines its mirror suite reached,
and the loops in it that no test ever entered.

Invariants & Expected State:
    - A file with no probe entry is a finding, never a pass: unmeasured is not
      cleared.
    - Self-coverage is required of every file in scope; the suite-coverage
      reading is additional and is enforced in whole-tree mode.
    - Every loop in a source file is expected to have its zero-iteration case
      exercised, and the loops are matched in ordinal order.
    - A loop may be grandfathered only while the recorded evidence names it;
      a waiver that no longer matches a reported loop is stale and reported.
    - Missing loop instrumentation is reported rather than read as a covered
      loop.
    - Findings are value objects: one per file, carrying the path, a gate code
      and a message, so a caller can print or aggregate them without state.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framework.gates.checks import check_test_mirror as mirror


@dataclass(frozen=True)
class Finding:
    """One coverage or loop-iteration violation."""

    path: str
    code: str
    message: str

    def format(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(frozen=True)
class FileMetrics:
    """Coverage and loop status of one source file in one probe run."""

    rel: str
    measured: bool
    statements: int
    self_pct: float
    suite_pct: float
    loops_uncovered: tuple[int, ...]
    loops: dict[str, Mapping[str, Any]]


@dataclass(frozen=True)
class _EvalContext:
    """Per-run knobs shared by the per-file evaluation helpers."""

    aliases: Mapping[str, Sequence[str]]
    exists: Callable[[str], bool]
    loop_lines: Mapping[str, Sequence[int]]
    mirrors: str
    mode: str
    min_coverage: float


@dataclass(frozen=True)
class _EvidenceContext:
    """Per-run knobs shared by the evidence-ledger helpers."""

    aliases: Mapping[str, Sequence[str]]
    exists: Callable[[str], bool]
    mirrors: str
    waivers: Mapping[str, Mapping[str, str]]
    min_coverage: float
    require_cleared: bool
    refresh_hint: str


@dataclass(frozen=True)
class _ProbeRun:
    """Probe-derived inputs, raw report and reference baseline of one run."""

    loop_lines: Mapping[str, Sequence[int]]
    baseline: Any
    report: Any


def test_files_for(
    rel: str,
    aliases: Mapping[str, Sequence[str]],
    exists: Callable[[str], bool],
    tests_root: str = mirror.DEFAULT_TESTS,
) -> list[str]:
    """Return the test files that own ``rel`` (mirror paths plus aliases)."""

    candidates = [path for path in mirror.mirror_paths(rel, tests_root) if exists(path)]
    candidates.extend(target for target in aliases.get(rel, ()) if exists(target))
    return sorted(set(candidates))


def contexts_for(test_files: Sequence[str], contexts: Iterable[str]) -> set[str]:
    """Return the pytest nodeid contexts that belong to ``test_files``."""

    wanted = set(test_files)
    found: set[str] = set()
    for context in contexts:
        for test_file in wanted:
            if context == test_file or context.startswith(f"{test_file}::"):
                found.add(context)
                break
    return found


def source_loop_lines(path: Path) -> list[int]:
    """Return the loop line numbers of one source file, in ordinal order."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While))
    ]
    nodes.sort(key=lambda node: (node.lineno, node.col_offset))
    return [node.lineno for node in nodes]


def loop_missing(loop: Mapping[str, Any], waived: bool) -> list[str]:
    """Return the missing iteration cases of one loop (empty when compliant)."""

    counts = [
        count for values in loop.get("by_context", {}).values() for count in values
    ]
    missing: list[str] = []
    if counts and 0 not in counts and not waived:
        missing.append("0")
    if 1 not in counts:
        missing.append("1")
    if not any(count >= 2 for count in counts):
        missing.append("many")
    return missing


def _pct(executed: Iterable[int], statements: int) -> float:
    if statements <= 0:
        return 100.0
    return 100.0 * len(set(executed)) / statements


def _self_lines(
    lines_by_context: Mapping[str, Any], test_files: Sequence[str]
) -> set[int]:
    return {
        line
        for context in contexts_for(test_files, lines_by_context)
        for line in lines_by_context[context]
    }


def _suite_lines(lines_by_context: Mapping[str, Any]) -> set[int]:
    return {line for lines in lines_by_context.values() for line in lines}


def _uncovered_loops(
    loops: Mapping[str, Any], waivers: Mapping[str, str]
) -> tuple[int, ...]:
    return tuple(
        sorted(
            int(ordinal)
            for ordinal, loop in loops.items()
            if loop_missing(loop, ordinal in waivers)
        )
    )


def file_metrics(
    rel: str,
    entry: Mapping[str, Any] | None,
    test_files: Sequence[str],
    waivers: Mapping[str, str],
) -> FileMetrics:
    """Compute the metrics of one source file from one probe report entry."""

    if entry is None:
        return FileMetrics(rel, False, 0, 0.0, 0.0, (), {})
    statements = int(entry.get("statements", 0))
    lines_by_context = entry.get("lines_by_context", {})
    self_lines = _self_lines(lines_by_context, test_files)
    suite_lines = _suite_lines(lines_by_context)
    loops = dict(entry.get("loops", {}))
    uncovered = _uncovered_loops(loops, waivers)
    return FileMetrics(
        rel,
        True,
        statements,
        round(_pct(self_lines, statements), 1),
        round(_pct(suite_lines, statements), 1),
        uncovered,
        loops,
    )


def _staged_exit_findings(
    rel: str, metrics: FileMetrics, test_files: Sequence[str]
) -> list[Finding] | None:
    """Return the staged-mode early exit of one file, or ``None`` to continue."""

    if not test_files:
        return [Finding(rel, "NO TESTS", f"nothing selected for {rel}")]
    if metrics.measured:
        return None
    return [
        Finding(
            rel,
            "COVERAGE",
            f"{rel} not measured (never imported by its tests)",
        )
    ]


def _all_exit_findings(
    rel: str, metrics: FileMetrics, recorded: Mapping[str, Any] | None
) -> list[Finding] | None:
    """Return the whole-tree early exit of one file, or ``None`` to continue."""

    if not metrics.measured:
        if recorded is None:
            return [
                Finding(
                    rel,
                    "COVERAGE",
                    f"{rel} not measured (never imported by the selected tests)",
                )
            ]
        return []
    if recorded is not None and not recorded.get("measured", True):
        return []
    return None


def _unmeasured_findings(
    rel: str,
    metrics: FileMetrics,
    recorded: Mapping[str, Any] | None,
    test_files: Sequence[str],
    mode: str,
) -> list[Finding] | None:
    """Return the early-exit findings of one file, or ``None`` to keep checking."""

    if mode == "staged":
        return _staged_exit_findings(rel, metrics, test_files)
    if mode == "all":
        return _all_exit_findings(rel, metrics, recorded)
    return None


def _required_self(
    recorded: Mapping[str, Any] | None, mode: str, min_coverage: float
) -> float:
    if mode == "staged" or recorded is None:
        return min_coverage
    return float(recorded["self"])


def _self_coverage_findings(
    rel: str,
    metrics: FileMetrics,
    recorded: Mapping[str, Any] | None,
    context: _EvalContext,
) -> list[Finding]:
    """Return the self-coverage finding of one file (empty when it passes)."""

    required = _required_self(recorded, context.mode, context.min_coverage)
    if metrics.self_pct >= required - 1e-9:
        return []
    return [
        Finding(
            rel,
            "COVERAGE",
            f"{rel} self {metrics.self_pct:.1f}% < required "
            f"{required:.1f}% (suite {metrics.suite_pct:.1f}%)",
        )
    ]


def _suite_coverage_findings(
    rel: str,
    metrics: FileMetrics,
    recorded: Mapping[str, Any] | None,
    context: _EvalContext,
) -> list[Finding]:
    """Return the suite-coverage finding of one file (empty when it passes)."""

    required = context.min_coverage if recorded is None else float(recorded["suite"])
    if metrics.suite_pct >= required - 1e-9:
        return []
    return [
        Finding(
            rel,
            "COVERAGE",
            f"{rel} suite {metrics.suite_pct:.1f}% < required "
            f"{required:.1f}% (self {metrics.self_pct:.1f}%)",
        )
    ]


def _coverage_findings(
    rel: str,
    metrics: FileMetrics,
    recorded: Mapping[str, Any] | None,
    context: _EvalContext,
) -> list[Finding]:
    """Return the self and (whole-tree only) suite coverage findings."""

    findings = _self_coverage_findings(rel, metrics, recorded, context)
    if context.mode == "all":
        findings.extend(_suite_coverage_findings(rel, metrics, recorded, context))
    return findings


def _instrumentation_gap_findings(
    rel: str, metrics: FileMetrics, expected: Sequence[int]
) -> list[Finding]:
    """Return the loop-instrumentation-gap finding of one file, when present."""

    if len(metrics.loops) == len(expected) and sorted(
        int(ordinal) for ordinal in metrics.loops
    ) == list(range(len(expected))):
        return []
    return [
        Finding(
            rel,
            "LOOP INSTRUMENTATION GAP",
            f"{rel} source has {len(expected)} loop(s), probe recorded "
            f"{len(metrics.loops)}",
        )
    ]


def _grandfathered_loops(recorded: Mapping[str, Any] | None, mode: str) -> set[int]:
    if recorded is None or mode == "staged":
        return set()
    return set(recorded.get("loops_uncovered", ()))


def _loop_iteration_finding(
    rel: str, ordinal: int, loop: Mapping[str, Any], missing: Sequence[str]
) -> Finding:
    observed = sorted(
        count for values in loop.get("by_context", {}).values() for count in values
    )
    return Finding(
        rel,
        "LOOP ITERATIONS",
        f"{rel}:{loop.get('lineno', 0)} loop #{ordinal} observed "
        f"{observed}; missing {'/'.join(missing)} case",
    )


def _loop_findings(
    rel: str,
    metrics: FileMetrics,
    recorded: Mapping[str, Any] | None,
    waived: Mapping[str, str],
    context: _EvalContext,
) -> list[Finding]:
    """Return the missing loop-iteration-case findings of one file."""

    findings: list[Finding] = []
    grandfathered = _grandfathered_loops(recorded, context.mode)
    for ordinal in sorted(int(value) for value in metrics.loops):
        if ordinal in grandfathered:
            continue
        loop = metrics.loops[str(ordinal)]
        missing = loop_missing(loop, str(ordinal) in waived)
        if not missing:
            continue
        findings.append(_loop_iteration_finding(rel, ordinal, loop, missing))
    return findings


def _rel_findings(
    rel: str,
    report_files: Mapping[str, Any],
    baseline_files: Mapping[str, Any],
    waivers: Mapping[str, Mapping[str, str]],
    context: _EvalContext,
) -> list[Finding]:
    """Return the findings of one source file (empty when it is exempt)."""

    if Path(rel).name in mirror.EXEMPT_NAMES:
        return []
    waived = waivers.get(rel, {})
    test_files = test_files_for(rel, context.aliases, context.exists, context.mirrors)
    entry = report_files.get(rel)
    metrics = file_metrics(rel, entry, test_files, waived)
    recorded = baseline_files.get(rel)
    findings = _unmeasured_findings(rel, metrics, recorded, test_files, context.mode)
    if findings is not None:
        return findings
    findings = _coverage_findings(rel, metrics, recorded, context)
    expected = list(context.loop_lines.get(rel, ()))
    findings.extend(_instrumentation_gap_findings(rel, metrics, expected))
    findings.extend(_loop_findings(rel, metrics, recorded, waived, context))
    return findings


def _stale_waiver_findings(
    waivers: Mapping[str, Mapping[str, str]],
    report_files: Mapping[str, Any],
    src_files: Sequence[str],
) -> list[Finding]:
    """Return the findings of waivers that no longer match a reported loop."""

    findings: list[Finding] = []
    for rel, entries in sorted(waivers.items()):
        if rel not in src_files:
            continue
        entry = report_files.get(rel)
        if entry is None:
            continue
        reported = set(entry.get("loops", {}))
        for ordinal in sorted(entries, key=int):
            if ordinal not in reported:
                findings.append(
                    Finding(
                        rel,
                        "STALE WAIVER",
                        f"{rel} loop #{ordinal} no longer exists; drop the waiver",
                    )
                )
    return findings


def evaluate(
    report: Mapping[str, Any],
    baseline: Mapping[str, Any] | None,
    waivers: Mapping[str, Mapping[str, str]],
    *,
    src_files: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    exists: Callable[[str], bool],
    loop_lines: Mapping[str, Sequence[int]],
    mirrors: str = mirror.DEFAULT_TESTS,
    mode: str = "all",
    min_coverage: float = 80.0,
) -> list[Finding]:
    """Return the per-file findings of one probe report."""

    findings: list[Finding] = []
    baseline_files = (baseline or {}).get("files", {})
    report_files = report.get("files", {})
    context = _EvalContext(aliases, exists, loop_lines, mirrors, mode, min_coverage)
    for rel in src_files:
        findings.extend(
            _rel_findings(rel, report_files, baseline_files, waivers, context)
        )
    findings.extend(_stale_waiver_findings(waivers, report_files, src_files))
    return findings
