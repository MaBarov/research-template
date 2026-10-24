"""Benchmark regression suite for the mixed-device (HNS088) rule.

Thumbnail: Runs the labeled mixed-device set and pins its measured precision and recall.

Invariants & Expected State:
    Supported cases yield exactly their expected code set, so HNS088 never
    displaces a transfer finding and never fires on a same-placement negative.
    Known misses stay undetected; they catalogue the provenance the local rule
    cannot prove (a class attribute, and tensors that arrive through parameters
    from another module).
    Precision, recall and the trigger state are pinned to the measured values.
"""

from __future__ import annotations

import pytest

from framework.gates.transfers.visitor import analyze_transfers
from framework.tests.advisory_scoring_fixture import (
    case_matches,
    confusion,
    precision_recall,
)
from framework.tests.transfers.dataset_fixture import TransferBenchmarkCase
from framework.tests.transfers.provenance.mixing_cases_fixture import CASES

CODE = "HNS088"
SUPPORTED = tuple(case for case in CASES if not case.known_miss)
MISSES = tuple(case for case in CASES if case.known_miss)


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_case_matches_expected_codes(case: TransferBenchmarkCase) -> None:
    """Detected codes equal ground truth; a catalogued miss stays undetected."""
    assert case_matches(analyze_transfers, case)


def test_supported_set_precision_and_recall() -> None:
    """Over the supported set the rule is exact: every case lands on its side."""
    tp, fp, fn, tn = confusion(analyze_transfers, SUPPORTED, CODE)
    assert precision_recall(tp, fp, fn) == (1.0, 1.0)
    assert (tp, fp, fn, tn) == (20, 0, 0, 14)


def test_all_cases_precision_and_recall_with_open_gaps() -> None:
    """Counting known misses, recall drops to the measured 20/23 = 0.8696."""
    tp, fp, fn, tn = confusion(analyze_transfers, CASES, CODE)
    precision, recall = precision_recall(tp, fp, fn)
    assert (tp, fp, fn, tn) == (20, 0, 3, 14)
    assert precision == 1.0
    assert round(recall, 4) == 0.8696


def test_known_misses_are_the_documented_gap() -> None:
    """Every open gap is catalogued and named, so no 1.0 recall claim survives."""
    assert {case.name for case in MISSES} == {
        "hns088_historical_pursuit_expression",
        "hns088_callee_local_host_result",
        "hns088_class_attribute_host_tensor",
    }


def test_mixed_device_findings_carry_the_static_trigger() -> None:
    """A mixture fails on every run, so its evidence state is static, not loop."""
    for case in SUPPORTED:
        for finding in analyze_transfers(case.code, f"{case.name}.py"):
            if finding.code == CODE:
                assert finding.trigger == "static"
