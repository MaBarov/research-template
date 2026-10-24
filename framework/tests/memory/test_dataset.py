"""Benchmark regression suite for the accelerator memory gate.

Thumbnail: Runs the labeled memory dataset and asserts exact code matches and known-miss gaps.

Invariants & Expected State:
    Every supported labeled case yields exactly its expected codes: no misses, no extras.
    Known misses fail closed to ensure open gaps in helper-called retention are tracked.
    The in-sample floor reports precision and recall of 1.0 over supported cases.
    The dataset exercises all four rule codes and at least twenty negative controls.
"""

from __future__ import annotations

import pytest

from framework.gates.memory.visitor import analyze_memory
from framework.tests.memory.dataset_fixture import BENCHMARK_CASES, MemoryBenchmarkCase

pytestmark = pytest.mark.pinned

CASES = BENCHMARK_CASES
CODES = ("HNS083", "HNS084", "HNS085", "HNS086")


def _detected(case: MemoryBenchmarkCase) -> set[str]:
    """Return the set of codes the gate reports for one benchmark case."""
    return {f.code for f in analyze_memory(case.code, f"{case.name}.py")}


def _truth(case: MemoryBenchmarkCase, code: str | None) -> tuple[set[str], set[str]]:
    """Return the detected and expected code sets, narrowed to one code if asked."""
    detected = _detected(case)
    expected = set(case.expected_codes)
    if code is None:
        return detected, expected
    return detected & {code}, expected & {code}


def _confusion(
    cases: list[MemoryBenchmarkCase], code: str | None = None
) -> tuple[int, int, int, int]:
    """Pool true/false positives and negatives over one case list, per code or whole."""
    tp = fp = fn = tn = 0
    for case in cases:
        detected, expected = _truth(case, code)
        tp += len(detected & expected)
        fp += len(detected - expected)
        fn += len(expected - detected)
        if not detected and not expected:
            tn += 1
    return tp, fp, fn, tn


def _ratio(hit: int, total: int) -> float:
    """Return hit over total, or 1.0 for a vacuous slice that holds no positives."""
    return hit / total if total else 1.0


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_dataset_case_matches_expected_codes(case: MemoryBenchmarkCase) -> None:
    """Detected codes equal ground truth; known misses fail closed instead."""
    if case.known_miss:
        assert not _detected(case)
    else:
        assert sorted(_detected(case)) == sorted(case.expected_codes)


def test_dataset_covers_every_rule_and_negative_controls() -> None:
    """The frozen dataset exercises all four codes and enough negative controls."""
    exercised = {code for case in CASES for code in case.expected_codes}
    negatives = [case for case in CASES if not case.expected_codes]
    assert exercised == set(CODES)
    assert len(negatives) >= 20


def test_dataset_precision_and_recall_are_perfect() -> None:
    """Pooled confusion counts over supported cases assert the floor of 1.0."""
    supported = [case for case in CASES if not case.known_miss]
    tp, fp, fn, tn = _confusion(supported)
    assert (tp, fp, fn) == (sum(len(c.expected_codes) for c in supported), 0, 0)
    assert tn == sum(1 for case in supported if not case.expected_codes)


def test_dataset_per_code_metrics_are_perfect() -> None:
    """Per-code precision and recall over each of the four memory anti-patterns."""
    supported = [case for case in CASES if not case.known_miss]
    for code in CODES:
        tp, fp, fn, _tn = _confusion(supported, code)
        scores = (_ratio(tp, tp + fp), _ratio(tp, tp + fn))
        assert scores == (1.0, 1.0), f"Code {code} imperfect: {scores}"


def test_dataset_tracks_known_misses_and_open_gap() -> None:
    """Known misses are catalogued, so a 1.0 recall claim stays impossible."""
    misses = [case for case in CASES if case.known_miss]
    assert len(misses) == 3
    tp, _fp, fn, _tn = _confusion(list(CASES))
    total = tp + fn
    assert round(tp / total, 4) == 0.8636
