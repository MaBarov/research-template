"""Unit tests for the surrogate distortion static analysis gate.

Thumbnail: Verifies detection of HNS044, HNS045, and HNS046 anti-patterns and CLI mechanics.

Invariants & Expected State:
    Flags offending patterns with exact line numbers and codes.
    Synthetic anti-pattern snippets are detected with the configured vocabulary.
    Exempt-call, non-matching, and full-precision snippets pass cleanly.
    CLI runs fail closed on unreadable files and obey --strict and --report flags.
    Functions span at most 30 lines, and test runs completely on CPU.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.gates.distortion import targets
from framework.gates.distortion.check_distortion import main as cli_main
from framework.gates.distortion.visitor import analyze_distortion


def test_hns044_flags_quantized_subtraction() -> None:
    """Flag weight subtraction preceded by low-precision bfloat16 casting."""
    snippet = """
def _simulate_agent_weight_extraction(weight, delta):
    live = (weight.double() + delta.double()).to(dtype=torch.bfloat16)
    return (live.float() - weight.float()).double()
"""
    findings = analyze_distortion(snippet, "research/model.py")
    assert len(findings) == 1
    assert findings[0].code == "HNS044"
    assert "post-quantization" in findings[0].message


def test_hns044_passes_on_full_precision_weight_dose() -> None:
    """Pass on float64/float32 distance calculation from dose.py."""
    snippet = """
def _cumulative_weight_dose(weights, ctx):
    return sum((weights[n].double() - ctx.W0[n].double()).square() for n in weights)
"""
    findings = analyze_distortion(snippet, "research/peeling/dose.py")
    assert len(findings) == 0


def test_hns045_flags_pooled_broadcast() -> None:
    """Flag broadcasting one pooled estimate value across members."""
    snippet = """
def evaluate_groups(pooled_basis, modules):
    return {name: pooled_basis for name in modules}
"""
    findings = analyze_distortion(snippet, "research/eval.py")
    assert len(findings) == 1
    assert findings[0].code == "HNS045"
    assert "in-sample pooled broadcast" in findings[0].message


def test_hns045_exemption_is_configured_by_the_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exempt the fallback API a project opts in; the same shape stays flagged."""
    # A project extends the empty default with its own per-member fallback API.
    monkeypatch.setattr(
        targets, "POOLING_EXEMPT_CALLS", frozenset({"_member_defaults"})
    )
    exempt = """
def _member_defaults(pooled_basis, modules):
    return {name: pooled_basis for name in modules}
"""
    assert analyze_distortion(exempt, "research/optimizer.py") == []
    flagged = """
def publish_defaults(pooled_basis, modules):
    return {name: pooled_basis for name in modules}
"""
    findings = analyze_distortion(flagged, "research/optimizer.py")
    assert findings[0].code == "HNS045"


def test_hns045_passes_on_non_estimate_values_and_non_member_iterables() -> None:
    """Pass when the value or the iterable carries no pooled/member name hint."""
    device_snippet = """
def init_devices(dev, modules):
    return {name: dev for name in modules}
"""
    assert analyze_distortion(device_snippet, "research/device.py") == []
    rows_snippet = """
def score_rows(pooled_basis, rows):
    return {name: pooled_basis for name in rows}
"""
    assert analyze_distortion(rows_snippet, "research/metrics.py") == []


def test_hns046_flags_grand_scalar_reduction() -> None:
    """Flag ratio-of-means scalar reduction over two reductions."""
    snippet = """
def _agent_scalar_reduction(curr, base):
    return float((1.0 - curr.mean() / base.mean()).item())
"""
    findings = analyze_distortion(snippet, "research/metrics.py")
    assert len(findings) == 1
    assert findings[0].code == "HNS046"
    assert "ratio-of-means" in findings[0].message


def test_hns046_flags_precomputed_means_and_reversed_ratio() -> None:
    """Flag ratio using precomputed mean variables and reversed 1.0 subtraction."""
    snippet = """
def compute_reduction(curr, base):
    m_after = curr.mean()
    m_before = base.mean()
    return m_after / m_before - 1.0
"""
    findings = analyze_distortion(snippet, "research/metrics.py")
    assert len(findings) == 1
    assert findings[0].code == "HNS046"


def test_hns046_passes_on_meandiff_and_paired_reductions() -> None:
    """Pass on meandiff function calls and elementwise paired reductions."""
    meandiff_snippet = """
def compute(a, b):
    return 1.0 - meandiff(a) / meandiff_ratio(b)
"""
    assert len(analyze_distortion(meandiff_snippet, "research/metrics.py")) == 0
    paired_snippet = """
def paired(after, before):
    return [1.0 - a / b for a, b in zip(after, before, strict=True)]
"""
    assert len(analyze_distortion(paired_snippet, "research/metrics.py")) == 0


def test_cli_clean_file_exits_zero(tmp_path: Path) -> None:
    """CLI exits with 0 on clean scoped sources under --strict."""
    clean_file = tmp_path / "clean.py"
    clean_file.write_text("def solve(): return 42\n", encoding="utf-8")
    assert cli_main(["--strict", str(clean_file)]) == 0


def test_cli_dirty_file_exits_one_and_writes_report(tmp_path: Path) -> None:
    """CLI exits with 1 on dirty sources under --strict and outputs json report."""
    dirty_file = tmp_path / "dirty.py"
    dirty_file.write_text(
        "def bad(a, b): return 1.0 - a.mean() / b.mean()\n", encoding="utf-8"
    )
    report_file = tmp_path / "report.json"
    rc = cli_main(["--strict", "--report", str(report_file), str(dirty_file)])
    assert rc == 1
    assert report_file.exists()
    payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["code"] == "HNS046"


def test_cli_unreadable_staged_blob_fails_closed() -> None:
    """CLI emits HNS010 and exits with 1 when staged file cannot be read."""
    rc = cli_main(["--strict", "--staged", "research/non_existent_module_staged.py"])
    assert rc == 1
