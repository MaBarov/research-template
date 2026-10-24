"""Benchmark regression suite for the advisory abstract-cost gate.

Thumbnail: Scores the labeled HNS095-HNS099 set and pins its precision and recall.

Invariants & Expected State:
    Supported cases yield exactly their expected code set, so no rule fires on
    another rule's negative and no rule silently disappears.
    Known misses stay undetected; they catalogue the three documented gaps (a
    local bank, a local alias inside a helper, and a pipeline reached through a
    variable).
    Each rule keeps its measured positive count, so none can drift unused.
"""

from __future__ import annotations

import pytest

from framework.gates.abstract_cost.visitor import analyze_abstract_cost
from framework.tests.abstract_cost.abstract_cases_fixture import CASES
from framework.tests.advisory_scoring_fixture import (
    case_matches,
    confusion,
    precision_recall,
)
from framework.tests.transfers.dataset_fixture import TransferBenchmarkCase

pytestmark = pytest.mark.pinned

CODES = ("HNS095", "HNS096", "HNS097", "HNS098", "HNS099")
SUPPORTED = tuple(case for case in CASES if not case.known_miss)
MISSES = tuple(case for case in CASES if case.known_miss)
POSITIVES = {"HNS095": 4, "HNS096": 4, "HNS097": 2, "HNS098": 3, "HNS099": 3}


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_case_matches_expected_codes(case: TransferBenchmarkCase) -> None:
    """Detected codes equal ground truth; a catalogued miss stays undetected."""
    assert case_matches(analyze_abstract_cost, case)


def test_supported_set_precision_and_recall() -> None:
    """Over the supported set the gate is exact: every case lands on its side."""
    tp, fp, fn, tn = confusion(analyze_abstract_cost, SUPPORTED)
    assert precision_recall(tp, fp, fn) == (1.0, 1.0)
    assert (tp + tn) == len(SUPPORTED)


def test_all_cases_recall_exposes_the_open_gaps() -> None:
    """Counting the catalogued misses, recall drops to the measured floor."""
    tp, fp, fn, _ = confusion(analyze_abstract_cost, CASES)
    precision, recall = precision_recall(tp, fp, fn)
    assert precision == 1.0
    assert round(recall, 4) == 0.8421


def test_every_rule_keeps_its_supported_positives() -> None:
    """All five classes are exercised, so no rule can rot into dead code."""
    for code, expected in POSITIVES.items():
        positives = [case for case in SUPPORTED if code in case.expected_codes]
        assert len(positives) == expected, f"{code} positive count drifted"


def test_known_misses_are_the_documented_gap() -> None:
    """Every open gap is catalogued, so no 1.0 end-to-end recall claim survives."""
    assert {case.name for case in MISSES} == {
        "hns097_local_bank_materialized",
        "hns095_alias_local_matrix_in_helper",
        "hns098_pipeline_behind_variable",
    }


def test_findings_name_their_cost_class() -> None:
    """A finding's evidence names the abstract class, not just the call site."""
    for case in SUPPORTED:
        for finding in analyze_abstract_cost(case.code, f"{case.name}.py"):
            assert finding.evidence, f"{case.name}:{finding.line} has no evidence"


def test_evidence_labels_are_the_documented_vocabulary() -> None:
    """Each code reports only the class name the gate documents for it."""
    documented = {
        "HNS095": {
            "loop-invariant factorization",
            "loop-invariant factorization via helper",
        },
        "HNS096": {"loop-invariant derivation"},
        "HNS097": {"banked capture"},
        "HNS098": {"per-item pipeline pass"},
        "HNS099": {
            "invariant host synchronization",
            "loop-invariant sync via helper",
        },
    }
    for case in SUPPORTED:
        for finding in analyze_abstract_cost(case.code, f"{case.name}.py"):
            assert finding.evidence in documented[finding.code], (
                f"{case.name}:{finding.line} {finding.code} reports "
                f"undocumented evidence {finding.evidence!r}"
            )
