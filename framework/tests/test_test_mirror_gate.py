"""Tests for the src -> test mirror gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.gates.checks import check_test_mirror as gate


def _touch(root: Path, rel: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _fake_repo(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(gate, "REPO", tmp_path)
    aliases = tmp_path / "framework" / "test_mirror_aliases.json"
    aliases.parent.mkdir(parents=True, exist_ok=True)
    aliases.write_text("{}", encoding="utf-8")
    return tmp_path


def test_mirror_paths_accepts_both_spellings() -> None:
    assert gate.mirror_paths("research/a/b/c.py") == [
        "tests/research/a/b/tests_c.py",
        "tests/research/a/b/test_c.py",
    ]


def test_evaluate_accepts_both_spellings_and_exempts_packages() -> None:
    existing = {"tests/research/tests_x.py", "tests/research/a/test_y.py"}
    findings = gate.evaluate(
        [
            "research/x.py",
            "research/a/y.py",
            "research/__init__.py",
            "research/missing.py",
        ],
        {},
        existing.__contains__,
    )
    assert [(finding.code, finding.path) for finding in findings] == [
        ("MIRROR MISSING", "research/missing.py")
    ]
    assert (
        findings[0].message
        == "research/missing.py -> expected tests/research/tests_missing.py"
    )


def test_alias_satisfies_a_missing_mirror() -> None:
    existing = {"tests/research/tests_ab.py"}
    findings = gate.evaluate(
        ["research/a/b.py"],
        {"research/a/b.py": ["tests/research/tests_ab.py"]},
        existing.__contains__,
    )
    assert findings == []


def test_dangling_alias_is_a_finding() -> None:
    findings = gate.evaluate(
        ["research/a/b.py"],
        {"research/a/b.py": ["tests/research/tests_gone.py"]},
        set().__contains__,
    )
    assert [(finding.code, finding.message) for finding in findings] == [
        ("ALIAS DANGLING", "research/a/b.py -> tests/research/tests_gone.py (missing)")
    ]


def test_stale_alias_beside_a_real_mirror_is_a_finding() -> None:
    existing = {"tests/research/a/tests_b.py", "tests/research/tests_ab.py"}
    findings = gate.evaluate(
        ["research/a/b.py"],
        {"research/a/b.py": ["tests/research/tests_ab.py"]},
        existing.__contains__,
    )
    assert [finding.code for finding in findings] == ["ALIAS STALE"]


def test_collect_files_skips_caches_and_third_party(tmp_path, monkeypatch) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    for rel in (
        "research/a.py",
        "research/__pycache__/a.py",
        "research/third_party/x.py",
    ):
        _touch(root, rel)
    assert gate.collect_files("research") == ["research/a.py"]


def test_collect_files_staged_filter_ignores_other_roots(tmp_path, monkeypatch) -> None:
    _fake_repo(tmp_path, monkeypatch)
    assert gate.collect_files("research", ["scripts/x.py", "research/b.py"]) == [
        "research/b.py"
    ]


def test_load_aliases_reads_targets(tmp_path) -> None:
    path = tmp_path / "aliases.json"
    path.write_text(
        '{"research/a.py": ["tests/research/tests_a.py"]}', encoding="utf-8"
    )
    assert gate.load_aliases(path) == {"research/a.py": ["tests/research/tests_a.py"]}


def test_load_aliases_rejects_a_non_object(tmp_path) -> None:
    path = tmp_path / "aliases.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(TypeError, match="JSON object"):
        gate.load_aliases(path)


def test_cli_blocks_a_missing_mirror(tmp_path, monkeypatch, capsys) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a.py")
    assert gate.main(["--strict"]) == 1
    assert (
        "MIRROR MISSING: research/a.py -> expected tests/research/tests_a.py"
        in capsys.readouterr().err
    )


def test_cli_passes_with_a_real_mirror(tmp_path, monkeypatch, capsys) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a/b.py")
    _touch(root, "tests/research/a/tests_b.py")
    assert gate.main(["--strict"]) == 0
    assert "checked 1 file(s), 0 finding(s)" in capsys.readouterr().out


def test_cli_missing_alias_table_is_an_environment_error(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(gate, "REPO", tmp_path)
    assert gate.main(["--strict"]) == 2
    assert "missing alias table" in capsys.readouterr().err


def test_cli_staged_ignores_non_source_paths(tmp_path, monkeypatch, capsys) -> None:
    _fake_repo(tmp_path, monkeypatch)
    assert gate.main(["--strict", "--staged", "README.md", "scripts/x.py"]) == 0
    assert "checked 0 file(s)" in capsys.readouterr().out


def test_cli_json_report_lists_findings(tmp_path, monkeypatch) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a.py")
    assert gate.main(["--json", "report.json"]) == 0
    payload = json.loads((root / "report.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "research.test-mirror.v1"
    assert payload["checked"] == ["research/a.py"]
    assert payload["findings"][0]["code"] == "MIRROR MISSING"
