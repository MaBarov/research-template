"""Shared scoring helpers for the advisory gate benchmark suites.

Thumbnail: Case-level confusion counting and precision/recall for labeled gate datasets.

Invariants & Expected State:
    One analyzer signature ``(source, path) -> sequence of coded findings`` is
    assumed, so every advisory gate's dataset is scored the same way.
    A known-miss case passes only when it stays undetected, so a gap is pinned
    rather than silently closed by a lenient expectation.
    Counting is case-level: a case is a positive when it names expected codes, and
    a per-code count is available for rule coverage.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from framework.tests.transfers.dataset_fixture import TransferBenchmarkCase


class Coded(Protocol):
    """The one attribute scoring needs from a finding."""

    code: str


Analyzer = Callable[[str, str], Sequence[Coded]]


def detected(analyze: Analyzer, case: TransferBenchmarkCase) -> set[str]:
    """Return the set of codes one analyzer reports for a benchmark case."""
    return {finding.code for finding in analyze(case.code, f"{case.name}.py")}


def confusion(
    analyze: Analyzer,
    cases: Sequence[TransferBenchmarkCase],
    code: str | None = None,
) -> tuple[int, int, int, int]:
    """Return tp, fp, fn, tn over one case set, for a code or for any finding."""
    tp = fp = fn = tn = 0
    for case in cases:
        found = detected(analyze, case)
        if code is None:
            flagged, expected = bool(found), bool(case.expected_codes)
        else:
            flagged, expected = code in found, code in case.expected_codes
        tp += int(flagged and expected)
        fp += int(flagged and not expected)
        fn += int(expected and not flagged)
        tn += int(not flagged and not expected)
    return tp, fp, fn, tn


def precision_recall(tp: int, fp: int, fn: int) -> tuple[float, float]:
    """Precision and recall; an empty denominator counts as perfect."""
    return (
        tp / (tp + fp) if tp + fp else 1.0,
        tp / (tp + fn) if tp + fn else 1.0,
    )


def case_matches(analyze: Analyzer, case: TransferBenchmarkCase) -> bool:
    """A supported case must match exactly; a known miss must stay undetected."""
    found = sorted(detected(analyze, case))
    expected = sorted(case.expected_codes)
    return found != expected if case.known_miss else found == expected
