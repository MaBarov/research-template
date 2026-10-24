"""Unit tests for the static-type gate: scope, parsing, CLI contract, index reads.

Thumbnail: unit tests covering typecheck policy, runner, report, and CLI entry.

Invariants & Expected State:
    * Tests exercise staged selection, path normalization, drift detection, and shadow files.
    * Mypy and pyright diagnostic parsing is verified against real and synthetic outputs.
    * CLI exit codes strictly adhere to fail-closed on error and benign skip on empty index.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from framework.gates.typecheck import check_types, policy, report, runner

_CLEAN = "Success: no issues found in 1 source file\n"


def _clean_env() -> dict[str, str]:
    """Return the environment without git's repository-selecting variables."""
    return {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }


def _completed(stdout: str, returncode: int) -> subprocess.CompletedProcess[str]:
    """Build a CompletedProcess double carrying one checker's stdout."""
    return subprocess.CompletedProcess(
        args=["checker"], returncode=returncode, stdout=stdout, stderr=None
    )


def _fake_mypy(
    monkeypatch: pytest.MonkeyPatch, stdout: str, returncode: int = 1
) -> None:
    """Make the runner use a fake mypy binary and a scripted stdout."""
    monkeypatch.setattr(policy, "engine_command", lambda engine: ["fake-mypy"])
    monkeypatch.setattr(
        runner.subprocess, "run", lambda *args, **kwargs: _completed(stdout, returncode)
    )


_MYPY_REPORT = """\
research/fake.py:12: error: Incompatible return value type (got "None", expected "int")  [return-value]
research/fake.py:12: note: Consider using "Optional[int]"
research/other.py:3: error: Foreign finding outside the scope set  [arg-type]
research/fake.py:20: error: Unexpected keyword argument "strict"  [call-arg]
Found 3 errors in 2 files (checked 2 source files)
"""


def test_scope_covers_four_roots_and_excludes_tests() -> None:
    """Keep the typed population to the four roots and drop test/vendor paths."""
    assert policy.is_typed_path("research/probe/plan.py")
    assert policy.is_typed_path("framework/gates/limits/check_limits.py")
    assert policy.is_typed_path("scripts/analysis/replay.py")
    assert policy.is_typed_path("experiments/pillar1_runner.py")
    assert not policy.is_typed_path("framework/tests/typecheck/test_check_types.py")
    assert not policy.is_typed_path("tests/research/params/tests_registry.py")
    assert not policy.is_typed_path("third_party/refactor/rope_refactor.py")
    assert not policy.is_typed_path("framework/hooks/pre-commit")
    assert not policy.is_typed_path("cache/scratch/probe.py")


def test_select_paths_keeps_explicit_outside_file_and_normalizes(
    tmp_path: Path,
) -> None:
    """Normalize in-tree paths and honor an explicit file outside the roots."""
    probe = tmp_path / "probe.py"
    probe.write_text("x = 1\n", encoding="utf-8")
    selected = policy.select_paths(
        ["./research/probe/plan.py", "research/probe/plan.py", str(probe)]
    )
    assert selected == sorted(["research/probe/plan.py", str(probe)])


def test_mypy_argv_pins_config_interpreter_and_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin the committed config, the resolved interpreter and the cache tree."""
    monkeypatch.setattr(policy, "engine_command", lambda engine: ["mypy"])
    argv = runner.mypy_argv(["research/fake.py"])
    assert argv[0] == "mypy"
    assert argv[argv.index("--config-file") + 1] == str(policy.CONFIG)
    assert argv[argv.index("--python-executable") + 1] == str(policy.interpreter())
    assert argv[argv.index("--cache-dir") + 1] == str(policy.ensure_cache_dir())
    assert argv[-1] == "research/fake.py"


def test_mypy_argv_fails_closed_without_a_checker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise CheckerMissing (with an install hint) when no mypy resolves."""
    monkeypatch.setattr(policy, "engine_command", lambda engine: None)
    with pytest.raises(runner.CheckerMissing) as error:
        runner.mypy_argv(["research/fake.py"])
    assert "uv pip install" in error.value.hint


def test_run_mypy_keeps_scoped_errors_and_drops_foreign_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attribute errors to the scope set, drop notes and foreign files."""
    _fake_mypy(monkeypatch, _MYPY_REPORT)
    result = runner.run_mypy(["research/fake.py"], {"research/fake.py"})
    assert [finding.code for finding in result.findings] == ["return-value", "call-arg"]
    assert [finding.line for finding in result.findings] == [12, 20]
    assert 'got "None"' in result.findings[0].message
    assert result.returncode == 1
    assert result.unparsed == []


def test_run_mypy_surfaces_unparsable_error_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Surface a location-less mypy error instead of reporting a clean run."""
    _fake_mypy(
        monkeypatch, "mypy: error: Cannot read file 'research/gone.py'\n", returncode=2
    )
    result = runner.run_mypy(["research/gone.py"], {"research/gone.py"})
    assert result.unparsed == ["mypy: error: Cannot read file 'research/gone.py'"]
    assert result.returncode == 2


def test_run_pyright_reads_json_ranges(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parse pyright JSON and convert its zero-based range to a 1-based line."""
    payload: dict[str, Any] = {
        "generalDiagnostics": [
            {
                "file": str(policy.REPO / "research/fake.py"),
                "severity": "error",
                "rule": "reportReturnType",
                "message": 'Type "None" is not assignable\n  to return type "int"',
                "range": {"start": {"line": 41}},
            },
            {
                "file": str(policy.REPO / "research/fake.py"),
                "severity": "warning",
                "message": "ignored",
                "range": {"start": {"line": 1}},
            },
        ]
    }
    monkeypatch.setattr(policy, "engine_command", lambda engine: ["pyright"])
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *a, **k: _completed(json.dumps(payload), 1),
    )
    result = runner.run_pyright(["research/fake.py"])
    assert len(result.findings) == 1
    assert result.findings[0].line == 42
    assert result.findings[0].code == "reportReturnType"
    assert "\n" not in result.findings[0].message


def test_cli_strict_blocks_on_a_scoped_finding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exit 1 under --strict when the staged module owns a finding."""
    finding = runner.Finding("research/fake.py", 3, "return-value", "bad return")
    monkeypatch.setattr(
        runner,
        "run",
        lambda engine, paths, scoped, staged=False: runner.RunResult(
            [finding], [], 1, "mypy"
        ),
    )
    assert check_types.main(["--strict", "research/fake.py"]) == 1


def test_cli_clean_run_exits_zero_and_writes_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exit 0 on a clean module and write the machine report on request."""
    monkeypatch.setattr(
        runner,
        "run",
        lambda engine, paths, scoped, staged=False: runner.RunResult([], [], 0, "mypy"),
    )
    report_file = tmp_path / "report.json"
    assert (
        check_types.main(["--strict", "--report", str(report_file), "research/fake.py"])
        == 0
    )
    assert json.loads(report_file.read_text(encoding="utf-8")) == []


def test_cli_missing_checker_blocks_only_under_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed under --strict when the checker is absent, NOTE otherwise."""

    def _missing(
        engine: str, paths: list[str], scoped: set[str], staged: bool = False
    ) -> runner.RunResult:
        raise runner.CheckerMissing("mypy", "install mypy")

    monkeypatch.setattr(runner, "run", _missing)
    assert check_types.main(["--strict", "research/fake.py"]) == 1
    assert check_types.main(["research/fake.py"]) == 0


def test_index_selection_reads_staged_typed_modules(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Select only staged typed modules from a real Git index."""
    repo = tmp_path / "repo"
    (repo / "research").mkdir(parents=True)
    (repo / "tests" / "research").mkdir(parents=True)
    (repo / "research" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "tests" / "research" / "tests_mod.py").write_text(
        "y = 1\n", encoding="utf-8"
    )
    (repo / "notes.txt").write_text("n\n", encoding="utf-8")
    for command in (["git", "init", "-q"], ["git", "add", "-A"]):
        subprocess.run(
            command, cwd=repo, env=_clean_env(), check=True, capture_output=True
        )
    monkeypatch.setattr(policy, "REPO", repo)
    assert policy.index_selection() == ["research/mod.py"]


def test_typed_sources_walks_roots_and_honors_exclusions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Walk the four roots and never yield test or vendor modules."""
    for rel in (
        "research/pkg/mod.py",
        "framework/tests/typecheck/test_x.py",
        "scripts/run.py",
        "experiments/e1/probe.py",
        "third_party/vendor/lib.py",
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(policy, "REPO", tmp_path)
    assert policy.typed_sources() == [
        "research/pkg/mod.py",
        "scripts/run.py",
        "experiments/e1/probe.py",
    ]


def test_index_drift_flags_module_modified_after_staging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Report a staged module whose working tree moved on after staging."""
    repo = tmp_path / "repo"
    (repo / "research").mkdir(parents=True)
    module = repo / "research" / "mod.py"
    module.write_text("x = 1\n", encoding="utf-8")
    for command in (["git", "init", "-q"], ["git", "add", "-A"]):
        subprocess.run(
            command, cwd=repo, env=_clean_env(), check=True, capture_output=True
        )
    monkeypatch.setattr(policy, "REPO", repo)
    assert policy.index_drift(["research/mod.py"]) == []
    module.write_text("x = 2\n", encoding="utf-8")
    assert policy.index_drift(["research/mod.py"]) == ["research/mod.py"]


def test_mypy_argv_shadows_a_drifted_staged_module(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Check the staged blob when the working tree moved on after staging."""
    repo = tmp_path / "repo"
    (repo / "research").mkdir(parents=True)
    module = repo / "research" / "mod.py"
    module.write_text("value: int = 1\n", encoding="utf-8")
    for command in (["git", "init", "-q"], ["git", "add", "-A"]):
        subprocess.run(
            command, cwd=repo, env=_clean_env(), check=True, capture_output=True
        )
    module.write_text("value: int = 'drifted'\n", encoding="utf-8")
    monkeypatch.setattr(policy, "REPO", repo)
    monkeypatch.setattr(policy, "CACHE_DIR", tmp_path / "cache" / "mypy")
    monkeypatch.setattr(policy, "engine_command", lambda engine: ["mypy"])
    argv = runner.mypy_argv(["research/mod.py"], staged=True)
    shadow = Path(argv[argv.index("--shadow-file") + 2])
    assert shadow.read_text(encoding="utf-8") == "value: int = 1\n"
    assert "--shadow-file" not in runner.mypy_argv(["research/mod.py"])


def test_cli_notes_shadowed_modules_without_blocking(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report a shadowed staged module as a NOTE, never as a failure."""
    result = runner.RunResult([], [], 0, "mypy", ["research/fake.py"])
    monkeypatch.setattr(
        runner, "run", lambda engine, paths, scoped, staged=False: result
    )
    assert check_types.main(["--strict", "--staged", "research/fake.py"]) == 0
    assert "checking the staged blob" in capsys.readouterr().err


def test_run_mypy_executes_the_resolved_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Execute a real checker process and parse its report end to end."""
    stub = tmp_path / "mypy"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'research/fake.py:7: error: boom  [arg-type]'\n"
        "echo 'Found 1 error in 1 file (checked 1 source file)'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    monkeypatch.setattr(policy, "engine_command", lambda engine: [str(stub)])
    result = runner.run_mypy(["research/fake.py"], {"research/fake.py"})
    assert [finding.code for finding in result.findings] == ["arg-type"]
    assert result.returncode == 1
    assert result.unparsed == []


def test_select_paths_drops_explicit_in_tree_test_module() -> None:
    """Never smuggle an in-tree excluded module into the typed population."""
    assert policy.select_paths(["framework/tests/typecheck/test_check_types.py"]) == []
    assert policy.select_paths(["third_party/refactor/rope_refactor.py"]) == []


def test_select_paths_detailed_reports_every_decline_reason() -> None:
    """A declined path carries the population rule's own reason."""
    selected, declined = policy.select_paths_detailed(
        [
            "framework/tests/typecheck/test_check_types.py",
            "README.md",
            "docs/notes.py",
            "cache/scratch/probe.py",
            "research/runtime/tests/probe.py",
        ]
    )
    assert selected == []
    reasons = dict(declined)
    assert (
        "excluded tree 'tests'"
        in reasons["framework/tests/typecheck/test_check_types.py"]
    )
    assert reasons["README.md"] == "not a Python module"
    assert "outside the typed population" in reasons["docs/notes.py"]
    assert reasons["cache/scratch/probe.py"].startswith("outside the typed population")
    assert reasons["research/runtime/tests/probe.py"] == "excluded tree 'tests'"


def test_cli_fails_closed_when_every_named_path_is_out_of_scope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Naming only out-of-population paths is an error, never a silent pass."""
    code = check_types.main(
        ["--strict", "framework/tests/typecheck/test_check_types.py"]
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "out of scope: framework/tests/typecheck/test_check_types.py" in err
    assert "belongs to the typed population" in err


def test_cli_unnamed_empty_index_is_a_benign_skip(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nothing staged and nothing named is a skip, not a failure."""
    monkeypatch.setattr(policy, "index_selection", list)
    assert check_types.main(["--strict"]) == 0
    assert "nothing staged and no paths named" in capsys.readouterr().err


def test_pyright_engine_is_advisory_without_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pyright census never blocks unless --strict is given."""
    finding = runner.Finding("research/fake.py", 10, "reportGeneralTypeIssues", "issue")
    result = runner.RunResult([finding], [], 1, "pyright")
    monkeypatch.setattr(runner, "run", lambda *a, **k: result)
    assert check_types.main(["--engine", "pyright", "--mode", "all"]) == 0
    assert check_types.main(["--engine", "pyright", "--mode", "all", "--strict"]) == 1


def test_engine_command_returns_none_when_checker_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return None when the checker binary is absent from path and venv."""
    monkeypatch.setattr(
        policy.harness, "engine_bin", lambda name: "nonexistent-checker"
    )
    monkeypatch.setattr(policy.shutil, "which", lambda name: None)
    assert policy.engine_command("mypy") is None


def test_report_write_report_and_census_lines(tmp_path: Path) -> None:
    """Verify JSON report structure and census summary lines."""
    findings = [
        runner.Finding("research/a.py", 1, "code1", "msg1"),
        runner.Finding("framework/b.py", 2, "code2", "msg2"),
        runner.Finding("research/a.py", 3, "code3", "msg3"),
    ]
    report_file = tmp_path / "census_report.json"
    report.write_report(report_file, findings)
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert len(data) == 3
    assert data[0]["path"] == "research/a.py"
    lines = report.census_lines(findings, checked=5)
    assert any("census: 5 module(s), 3 finding(s)" in line for line in lines)
    assert any("research: 2" in line for line in lines)
    assert any("top research/a.py: 2" in line for line in lines)
