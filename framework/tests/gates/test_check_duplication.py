"""Tests for the jscpd code duplication precommit gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.gates.checks.check_duplication import (
    Finding,
    build_jscpd_args,
    main,
    parse_args,
    parse_jscpd_json,
    parse_stdout_clones,
    resolve_jscpd_bin,
    run_jscpd,
)

SAMPLE_CODE = """
def sample_computation(values: list[float], scale: float, bias: float) -> list[float]:
    out: list[float] = []
    for idx, val in enumerate(values):
        if val > 0.0:
            term = val * scale + bias
            scaled = (term - 1.0) / (term + 1.0)
            out.append(scaled)
        elif val < 0.0:
            term = val * scale - bias
            scaled = (term + 1.0) / (term - 1.0)
            out.append(scaled)
        else:
            out.append(0.0)
    return out
"""


def test_finding_formatting() -> None:
    f = Finding(
        code="CPD001",
        path="research/test.py",
        line=42,
        message="Clone with other.py:10-25",
    )
    assert f.format() == "research/test.py:42: CPD001 Clone with other.py:10-25"
    assert f.code == "CPD001"
    assert f.path == "research/test.py"
    assert f.line == 42


def test_resolve_jscpd_bin_custom(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake_jscpd"
    fake_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    resolved = resolve_jscpd_bin(str(fake_bin))
    assert resolved == str(fake_bin)
    missing = resolve_jscpd_bin(str(tmp_path / "nonexistent"))
    assert missing != str(tmp_path / "nonexistent")


def test_build_jscpd_args(tmp_path: Path) -> None:
    cfg = tmp_path / ".jscpd.json"
    cfg.write_text("{}", encoding="utf-8")
    base = tmp_path / "base.json"
    args = build_jscpd_args(
        jscpd_bin="jscpd",
        target_paths=["src1.py", "src2.py"],
        config_path=cfg,
        baseline_path=base,
        update_baseline=False,
        output_dir=tmp_path / "out",
    )
    assert args[0] == "jscpd"
    assert "--config" in args
    assert "--baseline" in args
    assert "--fail-on-new-clones=0" in args
    assert "src1.py" in args


def test_build_jscpd_args_update_baseline(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    args = build_jscpd_args(
        jscpd_bin="jscpd",
        target_paths=["src.py"],
        config_path=None,
        baseline_path=base,
        update_baseline=True,
        output_dir=None,
    )
    assert "--update-baseline" in args
    assert "--fail-on-new-clones=0" not in args


def test_parse_jscpd_json(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    payload = {
        "duplicates": [
            {
                "firstFile": {"name": "a.py", "start": 10, "end": 20},
                "secondFile": {"name": "b.py", "start": 30, "end": 40},
                "lines": 11,
                "tokens": 65,
                "isNew": True,
            },
            {
                "firstFile": {"name": "c.py", "start": 1, "end": 15},
                "secondFile": {"name": "d.py", "start": 1, "end": 15},
                "lines": 15,
                "tokens": 70,
                "isNew": False,
            },
        ]
    }
    report.write_text(json.dumps(payload), encoding="utf-8")
    all_findings = parse_jscpd_json(report, baseline_active=False)
    assert len(all_findings) == 2
    new_findings = parse_jscpd_json(report, baseline_active=True)
    assert len(new_findings) == 1
    assert new_findings[0].path == "a.py"


def test_parse_jscpd_json_empty_or_missing(tmp_path: Path) -> None:
    assert parse_jscpd_json(tmp_path / "missing.json") == []
    corrupted = tmp_path / "corrupted.json"
    corrupted.write_text("invalid json", encoding="utf-8")
    assert parse_jscpd_json(corrupted) == []


def test_parse_stdout_clones() -> None:
    sample_out = (
        "Clone found (python) [NEW]\n"
        " - src/mod_a.py [10:1 - 25:10] (16 lines, 80 tokens)\n"
        "   src/mod_b.py [30:1 - 45:10]\n"
        "Clone found (python)\n"
        " - src/old_a.py [5:1 - 15:10] (11 lines, 60 tokens)\n"
        "   src/old_b.py [50:1 - 60:10]\n"
    )
    all_f = parse_stdout_clones(sample_out, baseline_active=False)
    assert len(all_f) == 2
    new_f = parse_stdout_clones(sample_out, baseline_active=True)
    assert len(new_f) == 1
    assert new_f[0].path == "src/mod_a.py"


def test_run_jscpd_on_clean_files(tmp_path: Path) -> None:
    f1 = tmp_path / "clean1.py"
    f2 = tmp_path / "clean2.py"
    f1.write_text("def unique_func_alpha():\n    return 42 * 2\n", encoding="utf-8")
    f2.write_text(
        "def unique_func_beta():\n    return 'hello world'.upper()\n", encoding="utf-8"
    )
    jscpd = resolve_jscpd_bin()
    if not jscpd:
        pytest.skip("jscpd binary not available on test host")
    ret, findings, _out = run_jscpd(
        jscpd, [str(f1), str(f2)], None, None, False, tmp_path
    )
    assert ret == 0
    assert findings == []


def test_run_jscpd_on_duplicate_files(tmp_path: Path) -> None:
    f1 = tmp_path / "dup1.py"
    f2 = tmp_path / "dup2.py"
    f1.write_text(SAMPLE_CODE, encoding="utf-8")
    f2.write_text(SAMPLE_CODE, encoding="utf-8")
    jscpd = resolve_jscpd_bin()
    if not jscpd:
        pytest.skip("jscpd binary not available on test host")
    _ret, findings, _out = run_jscpd(
        jscpd, [str(f1), str(f2)], None, None, False, tmp_path
    )
    assert len(findings) >= 1
    assert any(f.code == "CPD001" for f in findings)


def test_main_cli_clean(tmp_path: Path) -> None:
    f1 = tmp_path / "clean1.py"
    f2 = tmp_path / "clean2.py"
    f1.write_text("def clean_a():\n    return 'apple'\n", encoding="utf-8")
    f2.write_text("def clean_b():\n    return 'banana'\n", encoding="utf-8")
    code = main(["--strict", "--no-baseline", str(f1), str(f2)])
    assert code == 0


def test_main_cli_duplicates(tmp_path: Path) -> None:
    f1 = tmp_path / "dup1.py"
    f2 = tmp_path / "dup2.py"
    f1.write_text(SAMPLE_CODE, encoding="utf-8")
    f2.write_text(SAMPLE_CODE, encoding="utf-8")
    json_out = tmp_path / "out.json"
    code = main(
        ["--strict", "--no-baseline", "--json", str(json_out), str(f1), str(f2)]
    )
    assert code == 1
    assert json_out.is_file()
    records = json.loads(json_out.read_text(encoding="utf-8"))
    assert len(records) >= 1
    assert records[0]["code"] == "CPD001"
    advisory_code = main(["--no-baseline", str(f1), str(f2)])
    assert advisory_code == 0


def test_parse_args_defaults() -> None:
    opts = parse_args([])
    assert opts.strict is False
    assert opts.staged is False
    assert opts.update_baseline is False
    assert opts.no_baseline is False


def test_matches_staged() -> None:
    from framework.gates.checks.check_duplication import _matches_staged

    staged_set = {"research/module_a.py"}
    f_direct = Finding(
        code="CPD001", path="research/module_a.py", line=10, message="Clone"
    )
    assert _matches_staged(f_direct, staged_set) is True
    f_peer = Finding(
        code="CPD001",
        path="research/module_b.py",
        line=10,
        message="Clone with research/module_a.py:5-15",
    )
    assert _matches_staged(f_peer, staged_set) is True
    f_unrelated = Finding(
        code="CPD001",
        path="research/other.py",
        line=1,
        message="Clone with research/third.py:1-10",
    )
    assert _matches_staged(f_unrelated, staged_set) is False
    assert _matches_staged(f_unrelated, set()) is True


def test_missing_jscpd_binary(tmp_path: Path) -> None:
    from framework.gates.checks.check_duplication import evaluate_duplication

    f1 = tmp_path / "a.py"
    f1.write_text("print('test')\n", encoding="utf-8")
    findings, _out = evaluate_duplication(
        target_files=[str(f1)],
        staged=False,
        baseline_path=None,
        update_baseline=False,
        config_path=None,
        custom_jscpd=str(tmp_path / "nonexistent_binary"),
        repo_root=tmp_path,
    )
    assert len(findings) == 1
    assert findings[0].code == "CPD000"
    assert "not found" in findings[0].message


def test_evaluate_duplication_staged_filtering(tmp_path: Path) -> None:
    from framework.gates.checks.check_duplication import evaluate_duplication

    jscpd = resolve_jscpd_bin()
    if not jscpd:
        pytest.skip("jscpd binary not available on test host")
    research_dir = tmp_path / "research"
    research_dir.mkdir()
    f1 = research_dir / "staged.py"
    f2 = research_dir / "unstaged.py"
    f1.write_text(SAMPLE_CODE, encoding="utf-8")
    f2.write_text(SAMPLE_CODE, encoding="utf-8")
    base = tmp_path / "base.json"
    base.write_text(json.dumps({"version": 1, "fingerprints": {}}), encoding="utf-8")
    findings, _out = evaluate_duplication(
        target_files=[str(f1)],
        staged=True,
        baseline_path=base,
        update_baseline=False,
        config_path=None,
        custom_jscpd=jscpd,
        repo_root=tmp_path,
    )
    assert len(findings) >= 1
    assert any(
        f.path.endswith("staged.py") or "staged.py" in f.message for f in findings
    )
