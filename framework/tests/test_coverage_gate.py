"""Tests for the per-file coverage and loop-iteration gate."""

from __future__ import annotations

import json
from pathlib import Path

from framework.gates import check_coverage as gate
from framework.gates.checks import check_test_mirror as mirror
from framework.gates.coverage import config, ledger
from framework.gates.coverage import metrics as cov

REPO = Path(__file__).resolve().parents[2]
MIRROR_TEST = "tests/research/a/tests_b.py"
OTHER_TEST = "tests/research/a/tests_other.py"


def entry_of(
    statements: int,
    contexts: dict[str, list[int]],
    loops: dict[str, dict] | None = None,
) -> dict:
    """Return one probe report entry."""

    return {
        "statements": statements,
        "lines_by_context": contexts,
        "loops": loops or {},
        "transform_error": None,
    }


def loop_of(*counts: int) -> dict:
    """Return one loop entry observing ``counts`` iterations."""

    return {
        "lineno": 10,
        "by_context": {"tests/research/a/tests_b.py::test_x": list(counts)},
    }


def run_evaluate(
    report: dict,
    baseline: dict | None = None,
    *,
    mode: str = "all",
    loop_lines: dict[str, list[int]] | None = None,
    waivers: dict[str, dict[str, str]] | None = None,
    src_files: tuple[str, ...] = ("research/a/b.py",),
) -> list[cov.Finding]:
    """Evaluate one synthetic report through the public gate API."""

    return cov.evaluate(
        report,
        baseline,
        waivers or {},
        src_files=list(src_files),
        aliases={},
        exists=lambda path: True,
        loop_lines=loop_lines or {},
        mode=mode,
        min_coverage=80.0,
    )


def baseline_entry(
    self_pct: float = 100.0,
    suite_pct: float = 100.0,
    loops_uncovered: list[int] | None = None,
    measured: bool = True,
) -> dict:
    """Return one baseline file entry."""

    return {
        "measured": measured,
        "statements": 4,
        "self": self_pct,
        "suite": suite_pct,
        "loops_uncovered": loops_uncovered or [],
    }


def test_test_files_for_uses_the_mirror_base_once() -> None:
    """The mirror base is joined with the full source path exactly once."""

    found = cov.test_files_for("research/a/b.py", {}, lambda path: True)
    assert found == ["tests/research/a/test_b.py", "tests/research/a/tests_b.py"]

    aliased = cov.test_files_for(
        "research/a/b.py", {"research/a/b.py": [OTHER_TEST]}, lambda path: True
    )
    assert aliased == [
        "tests/research/a/test_b.py",
        "tests/research/a/tests_b.py",
        OTHER_TEST,
    ]


def test_contexts_for_matches_only_own_nodeids() -> None:
    contexts = [
        f"{MIRROR_TEST}::test_x",
        f"{OTHER_TEST}::test_y",
        "<background>",
    ]
    assert cov.contexts_for([MIRROR_TEST], contexts) == {f"{MIRROR_TEST}::test_x"}


def test_file_metrics_separates_own_and_suite_coverage() -> None:
    entry = entry_of(
        4, {f"{MIRROR_TEST}::test_x": [1, 2], f"{OTHER_TEST}::test_y": [3, 4]}
    )
    metrics = cov.file_metrics("research/a/b.py", entry, [MIRROR_TEST], {})
    assert metrics.measured is True
    assert metrics.self_pct == 50.0
    assert metrics.suite_pct == 100.0


def test_unmeasured_entry_reports_zero_metrics() -> None:
    metrics = cov.file_metrics("research/a/b.py", None, [MIRROR_TEST], {})
    assert metrics.measured is False
    assert metrics.statements == 0


def test_clean_file_has_no_findings() -> None:
    report = {
        "files": {
            "research/a/b.py": entry_of(
                4,
                {f"{MIRROR_TEST}::test_x": [1, 2, 3, 4]},
                {"0": loop_of(0, 1, 3)},
            )
        }
    }
    assert run_evaluate(report, loop_lines={"research/a/b.py": [10]}) == []


def test_low_coverage_reports_self_and_suite() -> None:
    report = {
        "files": {
            "research/a/b.py": entry_of(
                4, {f"{MIRROR_TEST}::test_x": [1, 2], f"{OTHER_TEST}::test_y": [3]}
            )
        }
    }
    findings = run_evaluate(report, mode="staged")
    assert [finding.code for finding in findings] == ["COVERAGE"]
    assert "self 50.0% < required 80.0%" in findings[0].message
    assert "suite 75.0%" in findings[0].message


def test_all_mode_requires_the_baseline_suite_floor_too() -> None:
    report = {
        "files": {"research/a/b.py": entry_of(4, {f"{MIRROR_TEST}::test_x": [1, 2]})}
    }
    baseline = {"files": {"research/a/b.py": baseline_entry(50.0, 80.0)}}
    findings = run_evaluate(report, baseline)
    assert [finding.code for finding in findings] == ["COVERAGE"]
    assert "suite 50.0% < required 80.0%" in findings[0].message


def test_all_mode_grandfathers_recorded_legacy_coverage() -> None:
    report = {
        "files": {"research/a/b.py": entry_of(4, {f"{MIRROR_TEST}::test_x": [1]})}
    }
    baseline = {"files": {"research/a/b.py": baseline_entry(25.0, 25.0)}}
    assert run_evaluate(report, baseline) == []


def test_staged_mode_ignores_grandfathering() -> None:
    report = {
        "files": {"research/a/b.py": entry_of(4, {f"{MIRROR_TEST}::test_x": [1]})}
    }
    baseline = {"files": {"research/a/b.py": baseline_entry(25.0, 25.0)}}
    findings = run_evaluate(report, baseline, mode="staged")
    assert [finding.code for finding in findings] == ["COVERAGE"]
    assert "self 25.0% < required 80.0%" in findings[0].message


def test_staged_mode_flags_unmeasured_file() -> None:
    findings = run_evaluate({"files": {}}, mode="staged")
    assert [finding.code for finding in findings] == ["COVERAGE"]
    assert "not measured" in findings[0].message


def test_staged_mode_flags_a_file_without_tests() -> None:
    findings = cov.evaluate(
        {"files": {}},
        None,
        {},
        src_files=["research/a/b.py"],
        aliases={},
        exists=lambda path: False,
        loop_lines={},
        mode="staged",
        min_coverage=80.0,
    )
    assert [finding.code for finding in findings] == ["NO TESTS"]


def test_all_mode_reports_never_imported_files() -> None:
    findings = run_evaluate({"files": {}})
    assert [finding.code for finding in findings] == ["COVERAGE"]
    assert "not measured" in findings[0].message


def test_all_mode_skips_recorded_unmeasured_files() -> None:
    baseline = {"files": {"research/a/b.py": baseline_entry(measured=False)}}
    assert run_evaluate({"files": {}}, baseline) == []


def test_loop_criterion_requires_zero_one_and_many() -> None:
    assert cov.loop_missing(loop_of(0, 1, 3), waived=False) == []
    assert cov.loop_missing(loop_of(0, 1), waived=False) == ["many"]
    assert cov.loop_missing(loop_of(1, 2), waived=False) == ["0"]
    assert cov.loop_missing(loop_of(), waived=False) == [
        "1",
        "many",
    ]
    assert cov.loop_missing(loop_of(1, 2), waived=True) == []
    assert cov.loop_missing(loop_of(2), waived=True) == ["1"]


def test_loop_findings_name_ordinal_and_observed_counts() -> None:
    report = {
        "files": {
            "research/a/b.py": entry_of(
                4,
                {f"{MIRROR_TEST}::test_x": [1, 2, 3, 4]},
                {"0": loop_of(1, 2)},
            )
        }
    }
    findings = run_evaluate(report, loop_lines={"research/a/b.py": [10]}, mode="staged")
    assert [finding.code for finding in findings] == ["LOOP ITERATIONS"]
    assert "loop #0 observed [1, 2]; missing 0 case" in findings[0].message


def test_baseline_grandfathers_non_compliant_loops_only_in_all_mode() -> None:
    report = {
        "files": {
            "research/a/b.py": entry_of(
                4,
                {f"{MIRROR_TEST}::test_x": [1, 2, 3, 4]},
                {"0": loop_of(1, 2)},
            )
        }
    }
    baseline = {"files": {"research/a/b.py": baseline_entry(100.0, 100.0, [0])}}
    assert run_evaluate(report, baseline, loop_lines={"research/a/b.py": [10]}) == []
    staged = run_evaluate(
        report, baseline, mode="staged", loop_lines={"research/a/b.py": [10]}
    )
    assert [finding.code for finding in staged] == ["LOOP ITERATIONS"]


def test_instrumentation_gap_is_detected() -> None:
    report = {
        "files": {
            "research/a/b.py": entry_of(
                4,
                {f"{MIRROR_TEST}::test_x": [1, 2, 3, 4]},
                {"0": loop_of(0, 1, 2)},
            )
        }
    }
    findings = run_evaluate(report, loop_lines={"research/a/b.py": [10, 20, 30]})
    assert [finding.code for finding in findings] == ["LOOP INSTRUMENTATION GAP"]
    assert "source has 3 loop(s), probe recorded 1" in findings[0].message


def test_stale_waiver_is_reported() -> None:
    report = {
        "files": {
            "research/a/b.py": entry_of(4, {f"{MIRROR_TEST}::test_x": [1, 2, 3, 4]})
        }
    }
    findings = run_evaluate(
        report, waivers={"research/a/b.py": {"3": "guarded empty iterate"}}
    )
    assert [finding.code for finding in findings] == ["STALE WAIVER"]


def test_waiver_for_file_outside_the_run_is_not_stale() -> None:
    report = {
        "files": {
            "research/a/b.py": entry_of(4, {f"{MIRROR_TEST}::test_x": [1, 2, 3, 4]})
        }
    }
    findings = run_evaluate(
        report, waivers={"research/other/c.py": {"0": "guarded empty iterate"}}
    )
    assert findings == []


def test_waivers_file_rejects_missing_reasons(tmp_path: Path) -> None:
    bad = tmp_path / "waivers.json"
    bad.write_text(json.dumps({"research/a/b.py": {"0": ""}}), encoding="utf-8")
    try:
        ledger._load_waivers(bad)
    except TypeError as error:
        assert "reason" in str(error)
    else:  # pragma: no cover - the gate must reject reason-less waivers
        raise AssertionError("reason-less waiver was accepted")


def test_baseline_regressions_cover_percent_and_loop_drops() -> None:
    old = {
        "files": {
            "research/a/b.py": baseline_entry(90.0, 90.0),
            "research/a/c.py": baseline_entry(50.0, 50.0),
        }
    }
    new = {
        "files": {
            "research/a/b.py": baseline_entry(80.0, 95.0, [1]),
            "research/a/c.py": baseline_entry(50.0, 50.0),
            "research/a/d.py": baseline_entry(10.0, 10.0),
        }
    }
    assert ledger.baseline_regressions(old, new) == [
        "research/a/b.py self 90.0% -> 80.0%",
        "research/a/b.py loop #1 lost a satisfied case",
    ]


def make_tmp_repo(tmp_path: Path, monkeypatch) -> Path:
    """Create a minimal repo layout the gate can run against."""

    (tmp_path / "research").mkdir()
    (tmp_path / "framework").mkdir()
    (tmp_path / "research" / "x.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "framework" / "test_mirror_aliases.json").write_text(
        "{}\n", encoding="utf-8"
    )
    monkeypatch.setattr(config, "REPO", tmp_path)
    monkeypatch.setattr(mirror, "REPO", tmp_path)
    return tmp_path


def test_cli_requires_the_baseline(tmp_path: Path, monkeypatch, capsys) -> None:
    make_tmp_repo(tmp_path, monkeypatch)
    assert gate.main(["--mode", "all"]) == 2
    assert "missing baseline" in capsys.readouterr().err


def test_cli_staged_requires_mirror_tests(tmp_path: Path, monkeypatch, capsys) -> None:
    make_tmp_repo(tmp_path, monkeypatch)
    assert gate.main(["--mode", "staged", "--staged", "research/x.py"]) == 2
    assert "no mirror tests selected" in capsys.readouterr().err


def test_cli_update_baseline_requires_all_mode(tmp_path: Path, monkeypatch) -> None:
    make_tmp_repo(tmp_path, monkeypatch)
    assert gate.main(["--update-baseline", "--mode", "staged"]) == 2


def test_cli_ignores_files_outside_the_source_root(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    make_tmp_repo(tmp_path, monkeypatch)
    assert gate.main(["--mode", "staged", "--staged", "scripts/run.py"]) == 0
    assert "checked 0 file(s)" in capsys.readouterr().out


def test_cli_ignores_exempt_files(tmp_path: Path, monkeypatch, capsys) -> None:
    make_tmp_repo(tmp_path, monkeypatch)
    assert gate.main(["--mode", "staged", "--staged", "research/__init__.py"]) == 0
    assert "checked 0 file(s)" in capsys.readouterr().out


SOURCE = (
    "def total(values):\n"
    "    seen = 0\n"
    "    for value in values:\n"
    "        seen += value\n"
    "    return seen\n"
)
TEST_SOURCE = (
    "from research.a import b\n"
    "\n"
    "\n"
    "def test_total() -> None:\n"
    "    assert b.total([]) == 0\n"
    "    assert b.total([2]) == 2\n"
    "    assert b.total([1, 2, 3]) == 6\n"
)


def make_evidence_repo(tmp_path: Path, monkeypatch) -> Path:
    """Create a repo layout with a source/mirror-test pair and a pytest config."""

    root = make_tmp_repo(tmp_path, monkeypatch)
    (root / "research" / "a").mkdir()
    (root / "tests" / "research" / "a").mkdir(parents=True)
    for package in (root / "research", root / "research" / "a"):
        (package / "__init__.py").write_text("", encoding="utf-8")
    (root / "research" / "a" / "b.py").write_text(SOURCE, encoding="utf-8")
    (root / "tests" / "research" / "a" / "tests_b.py").write_text(
        TEST_SOURCE, encoding="utf-8"
    )
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'pythonpath = ["."]\n'
        'python_files = ["test_*.py", "tests_*.py"]\n',
        encoding="utf-8",
    )
    return root


def record_clearance(root: Path, *, cleared: bool = True) -> None:
    """Write one ledger entry for ``research/a/b.py`` reflecting the current files."""

    entry = ledger.build_entry(
        "research/a/b.py",
        measured=True,
        statements=4,
        self_pct=100.0,
        suite_pct=100.0,
        loops_uncovered=[] if cleared else [0],
        aliases={},
        exists=lambda path: (root / path).is_file(),
        mirrors="tests",
        waivers={},
        min_coverage=80.0,
    )
    ledger.write_evidence(
        root / "framework" / "evidence.json", {"research/a/b.py": entry}
    )


def evidence_codes(
    root: Path,
    *,
    require_cleared: bool = True,
    waivers: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    """Return the finding codes of the static clearance decision."""

    return [
        finding.code
        for finding in ledger.check_evidence(
            ledger.load_evidence(root / "framework" / "evidence.json"),
            ["research/a/b.py"],
            aliases={},
            exists=lambda path: (root / path).is_file(),
            mirrors="tests",
            waivers=waivers or {},
            min_coverage=80.0,
            require_cleared=require_cleared,
            refresh_hint="refresh",
        )
    ]


def test_structure_hash_ignores_comments_and_docstrings(tmp_path: Path) -> None:
    """Clearance survives comments, docstrings and line moves, not code edits."""

    target = tmp_path / "a.py"
    target.write_text('"""Doc."""\n\n\ndef f(x):\n    return x + 1\n', encoding="utf-8")
    original = ledger.structure_hash(target)
    target.write_text(
        "# comment\n\n\ndef f(x):\n    '''Other doc.'''\n    return x + 1\n",
        encoding="utf-8",
    )
    assert ledger.structure_hash(target) == original
    target.write_text("def f(x):\n    return x + 2\n", encoding="utf-8")
    assert ledger.structure_hash(target) != original


def test_evidence_gate_replays_a_cleared_record(tmp_path: Path, monkeypatch) -> None:
    root = make_evidence_repo(tmp_path, monkeypatch)
    record_clearance(root)
    assert evidence_codes(root) == []
    (root / "research" / "a" / "b.py").write_text(SOURCE + "# note\n", encoding="utf-8")
    assert evidence_codes(root) == []


def test_evidence_gate_flags_stale_records(tmp_path: Path, monkeypatch) -> None:
    root = make_evidence_repo(tmp_path, monkeypatch)
    record_clearance(root)
    (root / "research" / "a" / "b.py").write_text(
        SOURCE + "def extra() -> int:\n    return 1\n", encoding="utf-8"
    )
    assert evidence_codes(root) == ["EVIDENCE STALE"]
    record_clearance(root)
    (root / "tests" / "research" / "a" / "tests_b.py").write_text(
        TEST_SOURCE + "def test_extra() -> None:\n    assert True\n", encoding="utf-8"
    )
    assert evidence_codes(root) == ["EVIDENCE STALE"]
    record_clearance(root)
    assert evidence_codes(root, waivers={"research/a/b.py": {"0": "guarded"}}) == [
        "EVIDENCE STALE"
    ]


def test_evidence_gate_flags_missing_and_uncleared_records(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_evidence_repo(tmp_path, monkeypatch)
    assert evidence_codes(root) == ["EVIDENCE MISSING"]
    record_clearance(root, cleared=False)
    assert evidence_codes(root) == ["NOT CLEARED"]
    assert evidence_codes(root, require_cleared=False) == []


def test_cli_records_then_replays_clearance(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """One staged run records clearance; replays are instant and void after edits."""

    root = make_evidence_repo(tmp_path, monkeypatch)
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    staged, replay = _clearance_cli_args()
    assert gate.main([*staged, "--strict"]) == 0, capsys.readouterr().err
    assert (root / "framework" / "evidence.json").is_file()
    assert gate.main([*replay, "--strict"]) == 0
    (root / "research" / "a" / "b.py").write_text(
        SOURCE + "def extra() -> int:\n    return 1\n", encoding="utf-8"
    )
    assert gate.main([*replay, "--strict"]) == 1


def _clearance_cli_args() -> tuple[list[str], list[str]]:
    """Return the staged and replay CLI argument lists for the clearance probe."""

    common = [
        "--src",
        "research",
        "--tests",
        "tests/research",
        "--evidence",
        "framework/evidence.json",
    ]
    staged = ["--mode", "staged", "--staged", "research/a/b.py", *common]
    replay = [
        "--mode",
        "staged",
        "--evidence-only",
        "--staged",
        "research/a/b.py",
        *common,
    ]
    return staged, replay
