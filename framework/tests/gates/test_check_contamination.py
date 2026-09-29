"""Behavioral tests for framework/gates/checks/check_contamination.py (guardrail #2)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY = sys.executable

SCRIPT = REPO / "framework" / "gates" / "checks" / "check_contamination.py"


def run_gate(bank: dict, strict: bool = False) -> subprocess.CompletedProcess:
    p = Path(REPO) / "tmp_contamination_bank.json"
    p.write_text(json.dumps(bank))
    try:
        return subprocess.run(
            [PY, str(SCRIPT), str(p)] + (["--strict"] if strict else []),
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=120,
            check=False,
        )
    finally:
        p.unlink(missing_ok=True)


def clean_bank() -> dict:
    return {
        "concept_prompts": [f"nude woman portrait style {i}" for i in range(30)],
        "safe_prompts": [f"mountain landscape painting {i}" for i in range(30)],
    }


def test_clean_bank_passes() -> None:
    r = run_gate(clean_bank())
    assert r.returncode == 0
    assert "violation" not in r.stderr.lower() or "0 violation" in r.stderr


def test_exact_overlap_detected() -> None:
    bank = clean_bank()
    bank["safe_prompts"].append(bank["concept_prompts"][0])
    r = run_gate(bank, strict=True)
    assert r.returncode == 1
    assert "C1 overlap: 1" in r.stderr


def test_lookalike_detected() -> None:
    bank = clean_bank()
    bank["concept_prompts"][0] = "disney concept artists style portrait"
    bank["safe_prompts"][0] = "disney concept artists style landscape"
    r = run_gate(bank, strict=True)
    assert r.returncode == 1
    assert "C4 lookalike" in r.stderr


def test_single_token_share_not_lookalike() -> None:
    """Regression for the min-normalization bug: one shared token must not flag."""
    bank = clean_bank()
    bank["concept_prompts"][0] = "blunt smoke"
    bank["safe_prompts"][0] = "epic scale cinematic full body marijuana blunt"
    r = run_gate(bank, strict=True)
    assert "C4 lookalike" not in r.stderr


def test_nsfw_marker_in_safe_bank_detected() -> None:
    bank = clean_bank()
    bank["safe_prompts"][0] = "adult dark-skinned man and woman kissing"
    r = run_gate(bank, strict=True)
    assert r.returncode == 1
    assert "C2 safe-bank NSFW leak" in r.stderr


def test_low_n_flagged() -> None:
    bank = {
        "concept_prompts": [f"c {i}" for i in range(5)],
        "safe_prompts": [f"s {i}" for i in range(5)],
    }
    r = run_gate(bank, strict=True)
    assert r.returncode == 1
    assert "C3 low-n" in r.stderr


def test_missing_bank_errors() -> None:
    r = subprocess.run(
        [PY, str(SCRIPT), "nope/not/a/file.json"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=60,
        check=False,
    )
    assert r.returncode == 1
    assert "MISSING bank" in r.stderr


def pair_bank() -> dict:
    """A certified concept/guide pair bank: pairs plus the criterion it was selected under."""
    return {
        "contract": "research_concept_guide_atoms_v6_certified",
        "n_selected": 4,
        "rank": 15,
        "selection_distance": 0.59,
        "selection_threshold": 0.8,
        "passed_gate": True,
        "selected_pairs": [["nude person", "person in cotton apparel"]] * 4,
    }


def test_pair_bank_certified_passes() -> None:
    """C1-C4 read concept/safe lists a pair bank does not have.

    Grading it with them produced C3's low-n abort (n=0 in both cells), which
    reported a violation for a bank it never actually read.
    """
    r = run_gate(pair_bank(), strict=True)
    assert r.returncode == 0
    assert "C3 low-n" not in r.stderr


def test_pair_bank_with_an_honest_false_flag_passes() -> None:
    """An honest diagnostic reading, not a claim, is not refused.

    A bank that reports ``passed_gate`` false with its criterion recorded must
    pass: it asserts nothing, so there is no unverifiable claim to police, even
    when its recorded distance sits above its own threshold.
    """
    bank = pair_bank()
    bank["passed_gate"] = False
    bank["selection_distance"] = 0.6098487600125845
    bank["selection_threshold"] = 0.2
    r = run_gate(bank, strict=True)
    assert r.returncode == 0
    assert "pair bank" not in r.stderr


def test_pair_bank_over_its_threshold_flagged() -> None:
    bank = pair_bank()
    bank["selection_distance"] = 0.9
    r = run_gate(bank, strict=True)
    assert r.returncode == 1
    assert "exceeds its threshold" in r.stderr
    assert "selection_distance 0.9" in r.stderr


def test_pair_bank_claiming_certification_without_its_numbers_flagged() -> None:
    bank = pair_bank()
    del bank["selection_distance"]
    del bank["selection_threshold"]
    r = run_gate(bank, strict=True)
    assert r.returncode == 1
    assert "claims passed_gate without" in r.stderr
    assert "selection_distance/threshold" in r.stderr


def test_bank_with_both_layouts_is_graded_by_concept_checks() -> None:
    """The pair branch must not become a way past C1-C4.

    A bank that carries concept/safe lists as well is graded by the overlap
    checks, so an overlapping pair bank cannot pass as a different contract.
    """
    bank = pair_bank()
    bank["concept_prompts"] = [f"nude woman portrait style {i}" for i in range(30)]
    bank["safe_prompts"] = [f"nude woman portrait style {i}" for i in range(30)]
    r = run_gate(bank, strict=True)
    assert r.returncode == 1
    assert "C1 overlap" in r.stderr
