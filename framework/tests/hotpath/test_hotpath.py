"""Benchmark regression suite for the advisory hot-path gate.

Thumbnail: Runs the labeled HNS089-HNS094 set and pins its measured precision and recall.

Invariants & Expected State:
    Supported cases yield exactly their expected code set, so no rule fires on
    another rule's negative and no rule silently disappears.
    Known misses stay undetected; they catalogue the two interprocedural gaps
    (a helper called from a step, a tensor built by a helper).
    Each rule keeps at least two supported positives.
"""

from __future__ import annotations

import pytest

from framework.gates.advisory.model import emit
from framework.gates.hotpath.visitor import analyze_hotpath
from framework.tests.advisory_scoring_fixture import (
    case_matches,
    confusion,
    precision_recall,
)
from framework.tests.hotpath.hotpath_cases_fixture import CASES
from framework.tests.transfers.dataset_fixture import TransferBenchmarkCase

pytestmark = pytest.mark.pinned

CODES = ("HNS089", "HNS090", "HNS091", "HNS092", "HNS093", "HNS094")
SUPPORTED = tuple(case for case in CASES if not case.known_miss)
MISSES = tuple(case for case in CASES if case.known_miss)


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_case_matches_expected_codes(case: TransferBenchmarkCase) -> None:
    """Detected codes equal ground truth; a catalogued miss stays undetected."""
    assert case_matches(analyze_hotpath, case)


def test_supported_set_precision_and_recall() -> None:
    """Over the supported set every rule is exact on its labeled cases."""
    tp, fp, fn, _ = confusion(analyze_hotpath, SUPPORTED)
    assert precision_recall(tp, fp, fn) == (1.0, 1.0)


def test_all_cases_recall_exposes_the_open_gaps() -> None:
    """Counting the catalogued misses, recall drops to the measured floor."""
    tp, fp, fn, _ = confusion(analyze_hotpath, CASES)
    precision, recall = precision_recall(tp, fp, fn)
    assert precision == 1.0
    assert round(recall, 4) == 0.8889


def test_every_rule_has_supported_positive_cases() -> None:
    """All six codes are exercised, so no rule can rot into dead code."""
    for code in CODES:
        positives = [case for case in SUPPORTED if code in case.expected_codes]
        assert len(positives) >= 2, f"{code} has too few supported positives"


def test_known_misses_are_the_documented_gap() -> None:
    """Every open gap is catalogued, so no 1.0 end-to-end recall claim survives."""
    assert {case.name for case in MISSES} == {
        "hns091_helper_sync",
        "hns093_helper_tensor",
    }


def test_clean_run_still_prints_a_census(capsys: pytest.CaptureFixture[str]) -> None:
    """The shared advisory runner names its population even with no finding."""
    assert emit([], strict=False, label="check_hotpath", checked=3) == 0
    assert capsys.readouterr().out.strip() == (
        "[check_hotpath] checked 3 module(s), 0 finding(s)"
    )
