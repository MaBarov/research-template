"""Benchmark regression suite for the device transfer gate.

Thumbnail: Runs the labeled transfer dataset and asserts exact code matches and known-miss gaps.

Invariants & Expected State:
    Every supported labeled case yields exactly its expected codes: no misses, no extras.
    Known misses fail closed to ensure open gaps in source-taking constructors are tracked.
    The in-sample floor reports precision and recall of 1.0 over supported cases.
    The dataset exercises all five rule codes and at least twenty negative controls.
"""

from __future__ import annotations

import pytest

from framework.gates.transfers.visitor import analyze_transfers
from framework.tests.transfers.dataset_fixture import (
    BENCHMARK_CASES,
    TransferBenchmarkCase,
)

CASES = BENCHMARK_CASES


def _detected(case: TransferBenchmarkCase) -> set[str]:
    """Return the set of codes the gate reports for one benchmark case."""
    return {f.code for f in analyze_transfers(case.code, f"{case.name}.py")}


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_dataset_case_matches_expected_codes(case: TransferBenchmarkCase) -> None:
    """Detected codes equal ground truth for supported cases; known misses fail closed."""
    if case.known_miss:
        assert sorted(_detected(case)) != sorted(case.expected_codes)
    else:
        assert sorted(_detected(case)) == sorted(case.expected_codes)


def test_dataset_covers_every_rule_and_negative_controls() -> None:
    """The frozen dataset exercises all five codes and enough negative controls."""
    covered = {code for case in CASES for code in case.expected_codes}
    negatives = [case for case in CASES if not case.expected_codes]
    assert covered == {"HNS056", "HNS057", "HNS058", "HNS059", "HNS060"}
    assert len(negatives) >= 20


def test_dataset_precision_and_recall_are_perfect() -> None:
    """In-sample confusion matrix over supported cases asserts 1.0 floor."""
    supported = [c for c in CASES if not c.known_miss]
    true_positive = false_positive = false_negative = true_negative = 0
    for case in supported:
        detected = _detected(case)
        expected = set(case.expected_codes)
        true_positive += len(detected & expected)
        false_positive += len(detected - expected)
        false_negative += len(expected - detected)
        true_negative += int(not expected and not detected)
    precision = true_positive / (true_positive + false_positive)
    recall = true_positive / (true_positive + false_negative)
    assert (precision, recall) == (1.0, 1.0)
    assert true_negative == sum(1 for case in supported if not case.expected_codes)


def test_dataset_per_code_metrics_are_perfect() -> None:
    """Per-code precision and recall over each of the five transfer anti-patterns."""
    supported = [c for c in CASES if not c.known_miss]
    codes = ("HNS056", "HNS057", "HNS058", "HNS059", "HNS060")
    for code in codes:
        cases_with_code = [c for c in supported if code in c.expected_codes]
        assert len(cases_with_code) >= 3, f"Code {code} has too few positive cases"
        tp = fp = fn = 0
        for case in supported:
            detected = _detected(case)
            expected = set(case.expected_codes)
            tp += int(code in detected and code in expected)
            fp += int(code in detected and code not in expected)
            fn += int(code not in detected and code in expected)
        prec = tp / (tp + fp) if (tp + fp) else 1.0
        rec = tp / (tp + fn) if (tp + fn) else 1.0
        assert (prec, rec) == (1.0, 1.0), f"{code} imperfect: prec={prec}, rec={rec}"


def test_dataset_tracks_known_misses_and_open_gap() -> None:
    """Known misses are catalogued, so a 1.0 recall claim stays impossible."""
    misses = [case for case in BENCHMARK_CASES if case.known_miss]
    assert misses, "no known-miss row is catalogued: the open gap is untracked"
    for miss in misses:
        assert sorted(_detected(miss)) != sorted(miss.expected_codes)
    tp = sum(len(_detected(c) & set(c.expected_codes)) for c in BENCHMARK_CASES)
    total = sum(len(c.expected_codes) for c in BENCHMARK_CASES)
    assert round(tp / total, 4) == 0.98
