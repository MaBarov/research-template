"""Unit tests for framework.indexing.gate."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework.indexing.gate import (
    _parse_contracts_fallback,
    audit_contract_coverage,
    check_module_contracts,
    load_contract_config,
    plan_index_files,
    run_index_gate,
    verify_index_freshness,
)
from framework.indexing.scanner import FunctionEntry, ModuleEntry, scan_module_text


def test_verify_index_freshness(tmp_path: Path) -> None:
    """Verify freshness check distinguishes between synced, drifted, and missing index."""
    idx = tmp_path / "INDEX.md"
    ok, msg = verify_index_freshness({idx: "# Fresh Content\n"})
    assert ok is False
    assert "missing" in msg.lower()

    idx.write_text("# Fresh Content\n", encoding="utf-8")
    ok, msg = verify_index_freshness({idx: "# Fresh Content\n"})
    assert ok is True
    assert "in sync" in msg.lower()

    ok, msg = verify_index_freshness({idx: "# Changed Content\n"})
    assert ok is False
    assert "out of sync" in msg.lower()


def test_audit_contract_coverage() -> None:
    """Verify contract coverage stats accurately meter documented functions."""
    f1 = FunctionEntry("fn1", "", "", "Does work.", 1, 5)
    f2 = FunctionEntry("fn2", "", "", "", 6, 10)
    m = ModuleEntry("mod.py", "", (), (f1, f2), 15)
    stats = audit_contract_coverage([m])
    assert stats["total_functions"] == 2
    assert stats["documented_functions"] == 1
    assert stats["coverage_percentage"] == 50.0


def test_plan_index_files_splitting(tmp_path: Path) -> None:
    """Verify plan_index_files splits into tree when exceeding max_lines."""
    f = FunctionEntry("solve", "", "", "Doc.", 1, 5)
    m1 = ModuleEntry("research/solve.py", "Solvers", (), (f,), 10)
    m2 = ModuleEntry("framework/check.py", "Checks", (), (f,), 10)

    # Large threshold: unified
    flat_map = plan_index_files(
        tmp_path,
        tmp_path / "INDEX.md",
        [m1, m2],
        ("research", "framework"),
        max_lines=5000,
    )
    assert len(flat_map) == 1
    assert tmp_path / "INDEX.md" in flat_map

    # Small threshold: tree of sub-indices
    tree_map = plan_index_files(
        tmp_path,
        tmp_path / "INDEX.md",
        [m1, m2],
        ("research", "framework"),
        max_lines=5,
    )
    assert len(tree_map) == 3
    assert tmp_path / "INDEX.md" in tree_map
    assert tmp_path / "research" / "INDEX.md" in tree_map
    assert tmp_path / "framework" / "INDEX.md" in tree_map


def test_run_index_gate_integration(tmp_path: Path) -> None:
    """Verify run_index_gate creates index on update and validates on check."""
    src = tmp_path / "research" / "test_mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("def ping() -> str:\n    '''Health check.'''\n    return 'pong'\n")

    idx = tmp_path / "INDEX.md"
    code = run_index_gate(tmp_path, idx, roots=("research",), check_only=False)
    assert code == 0
    assert idx.is_file()
    assert "Health check." in idx.read_text()

    check_code = run_index_gate(tmp_path, idx, roots=("research",), check_only=True)
    assert check_code == 0


def test_check_module_contracts() -> None:
    """Verify check_module_contracts filters to production scope and reports errors."""
    code_valid = '"""Thumbnail.\n\nInvariants:\n    - inv\n"""\n'
    m_valid = scan_module_text("research/valid.py", code_valid)
    m_invalid = scan_module_text("research/invalid.py", "x = 1\n")
    assert m_valid is not None and m_invalid is not None
    findings = check_module_contracts([m_valid, m_invalid])
    assert len(findings) == 1
    assert "research/invalid.py" in findings[0]


def test_check_interface_drift_detects_drift(tmp_path: Path, monkeypatch) -> None:
    """Verify drift detection flags signature changes without doc updates."""
    from framework.indexing import gate

    head_code = '"""Thumbnail.\n\nInvariants:\n    - test\n"""\ndef f(a: int) -> int:\n    return a\n'
    monkeypatch.setattr(gate, "_read_git_head_text", lambda root, rel: head_code)

    staged_code = '"""Thumbnail.\n\nInvariants:\n    - test\n"""\ndef f(a: int, b: int = 0) -> int:\n    return a + b\n'
    staged_entry = scan_module_text("research/mod.py", staged_code)
    assert staged_entry is not None

    findings = gate.check_interface_drift(tmp_path, [staged_entry], ["research/mod.py"])
    assert len(findings) == 1
    assert "drift detected" in findings[0]

    updated_doc = '"""Updated.\n\nInvariants:\n    - test\n"""\ndef f(a: int, b: int = 0) -> int:\n    return a + b\n'
    clean_entry = scan_module_text("research/mod.py", updated_doc)
    assert clean_entry is not None
    assert (
        len(gate.check_interface_drift(tmp_path, [clean_entry], ["research/mod.py"]))
        == 0
    )


def test_strict_contracts_mode(tmp_path: Path) -> None:
    """Verify run_index_gate with strict_contracts=True fails on contract errors."""
    src = tmp_path / "research" / "bad.py"
    src.parent.mkdir(parents=True)
    src.write_text("x = 1\n")
    idx = tmp_path / "INDEX.md"
    code = run_index_gate(tmp_path, idx, roots=("research",), strict_contracts=True)
    assert code == 1


def test_load_contract_config_defaults(tmp_path: Path) -> None:
    """Verify default contract config when pyproject.toml is absent."""
    cfg = load_contract_config(tmp_path)
    assert "research" in cfg["enforce_paths"]
    assert "framework" in cfg["enforce_paths"]
    assert "scripts" in cfg["enforce_paths"]
    assert "*/tests/*" in cfg["exclude_patterns"]


def test_load_contract_config_custom(tmp_path: Path) -> None:
    """Verify custom contract config loaded from pyproject.toml."""
    toml = (
        "[tool.research.contracts]\n"
        'enforce-paths = ["experiments"]\n'
        'exclude-patterns = ["legacy/*"]\n'
    )
    (tmp_path / "pyproject.toml").write_text(toml, encoding="utf-8")
    cfg = load_contract_config(tmp_path)
    assert cfg["enforce_paths"] == ["experiments"]
    assert cfg["exclude_patterns"] == ["legacy/*"]


def test_parse_contracts_fallback() -> None:
    """Verify fallback parser extracts lists without toml library."""
    toml = (
        "[tool.research.contracts]\n"
        'enforce-paths = [\n    "alpha",\n    "beta",\n]\n'
        'exclude-patterns = ["gamma/*"]\n'
    )
    parsed = _parse_contracts_fallback(toml)
    assert parsed["enforce-paths"] == ["alpha", "beta"]
    assert parsed["exclude-patterns"] == ["gamma/*"]


def test_check_module_contracts_custom_config() -> None:
    """Verify check_module_contracts respects custom enforce and exclude rules."""
    m_exp = scan_module_text("experiments/bad.py", "x = 1\n")
    m_bad = scan_module_text("research/bad.py", "x = 1\n")
    assert m_exp is not None and m_bad is not None

    cfg_bad_only = {"enforce_paths": ["research"], "exclude_patterns": []}
    findings = check_module_contracts([m_exp, m_bad], config=cfg_bad_only)
    assert len(findings) == 1
    assert "research/bad.py" in findings[0]

    cfg_exp_only = {"enforce_paths": ["experiments"], "exclude_patterns": []}
    findings_exp = check_module_contracts([m_exp, m_bad], config=cfg_exp_only)
    assert len(findings_exp) == 1
    assert "experiments/bad.py" in findings_exp[0]
