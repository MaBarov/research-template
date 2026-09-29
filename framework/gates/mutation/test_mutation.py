"""Behavioral tests for the mutation-evidence gate (no mutmut run is forked here).

Invariants & Expected State:
 * Every case drives the gate through a real throwaway Git repository, so the
   decision under test is the one the pre-commit hook makes: staged bytes,
   staged index, ledger file.
 * The refresh path is exercised only up to the point where it would fork
   mutmut; the tool-scoring run itself is verified by running the gate once
   against the repository population.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from framework.gates.mutation import check_mutation, evidence, scoring

MODULE = "research/runtime/device.py"
OUTSIDE = "research/analysis/rgb.py"
POPULATION = {"only_mutate": ["research/runtime/*.py"], "do_not_mutate": []}
STAGED_SOURCE = "def require_device(device):\n    return device\n"


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repository whose staged blob and ledger the gate reads."""
    for args in (
        ("init", "-q"),
        ("config", "user.email", "gate@test"),
        ("config", "user.name", "gate"),
    ):
        subprocess.run(["git", *args], cwd=tmp_path, check=True)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.mutmut]\nonly_mutate = ["research/runtime/*.py"]\n\n[tool.ruff]\n',
        encoding="utf-8",
    )
    module = tmp_path / MODULE
    module.parent.mkdir(parents=True)
    module.write_text(STAGED_SOURCE, encoding="utf-8")
    outside = tmp_path / OUTSIDE
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text(STAGED_SOURCE, encoding="utf-8")
    ledger = tmp_path / "framework" / "mutation_evidence.json"
    ledger.parent.mkdir(parents=True)
    monkeypatch.setattr(evidence, "REPO", tmp_path)
    monkeypatch.setattr(evidence, "PYPROJECT", tmp_path / "pyproject.toml")
    monkeypatch.setattr(evidence, "LEDGER_PATH", ledger)
    monkeypatch.setattr(scoring, "REPO", tmp_path)
    monkeypatch.setattr(scoring, "MUTANTS_DIR", tmp_path / "mutants")
    subprocess.run(
        ["git", "add", "pyproject.toml", "research"], cwd=tmp_path, check=True
    )
    return tmp_path


def _stage(repo: Path, rel: str, text: str) -> None:
    (repo / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=repo, check=True)


def _record(repo: Path, **overrides: object) -> None:
    """Write a ledger entry cleared for the *staged* content of MODULE."""
    entry: dict[str, object] = {"content_sha256": evidence.staged_sha256(MODULE)}
    entry.update(
        {
            "mutmut_version": "mutmut, version 3.8.0",
            "mutants": 11,
            "killed": 11,
            "skipped": 0,
            "survived": 0,
            "no_tests": 0,
            "timeout": 0,
            "suspicious": 0,
            "segfault": 0,
            "caught_by_type_check": 0,
            "check_was_interrupted_by_user": 0,
            "not_checked": 0,
        }
    )
    entry.update(overrides)
    evidence.save_ledger(
        {
            "schema": evidence.SCHEMA,
            "population": POPULATION,
            "mutmut_version": entry["mutmut_version"],
            "modules": {MODULE: entry},
        }
    )


def test_absent_evidence_blocks_with_the_refresh_command(repo: Path) -> None:
    findings = evidence.staged_findings([MODULE])
    assert any(MODULE in finding for finding in findings)
    assert any("check_mutation.py --mode staged" in finding for finding in findings)


def test_cleared_evidence_for_the_staged_content_passes(repo: Path) -> None:
    _record(repo)
    assert evidence.staged_findings([MODULE]) == []


def test_staging_new_content_invalidates_the_recorded_evidence(repo: Path) -> None:
    _record(repo)
    _stage(repo, MODULE, "def require_device(device):\n    return device or 0\n")
    findings = evidence.staged_findings([MODULE])
    assert any("not the staged" in finding for finding in findings)


def test_unstaged_edits_do_not_change_the_decision(repo: Path) -> None:
    _record(repo)
    (repo / MODULE).write_text("def require_device(device):\n    return None\n")
    assert evidence.staged_findings([MODULE]) == []


def test_a_survivor_blocks_and_is_named(repo: Path) -> None:
    _record(
        repo,
        survived=1,
        killed=10,
        survived_names=["research.runtime.device.x_require_device__mutmut_2"],
    )
    findings = evidence.staged_findings([MODULE])
    assert any("1 survived" in finding for finding in findings)
    assert any("__mutmut_2" in finding for finding in findings)
    assert any("no allowlist" in finding for finding in findings)


def test_unreached_mutants_block_as_a_coverage_hole(repo: Path) -> None:
    _record(repo, not_checked=3, mutants=14)
    findings = evidence.staged_findings([MODULE])
    assert any("3 not checked" in finding for finding in findings)


def test_a_timeout_blocks_as_an_unscored_mutant(repo: Path) -> None:
    _record(repo, timeout=1, killed=10)
    assert any("1 timeout" in finding for finding in evidence.staged_findings([MODULE]))


def test_files_outside_the_population_are_not_the_gates_business(repo: Path) -> None:
    assert evidence.staged_findings([OUTSIDE]) == []
    assert evidence.scoped_paths([OUTSIDE]) == ([], None)


def test_population_drift_blocks_until_the_ledger_is_refreshed(repo: Path) -> None:
    _record(repo)
    ledger = evidence.load_ledger()
    ledger["population"] = {
        "only_mutate": ["research/analysis/*.py"],
        "do_not_mutate": [],
    }
    evidence.save_ledger(ledger)
    findings = evidence.staged_findings([MODULE])
    assert any("configured is" in finding for finding in findings)


def test_population_drift_blocks_without_a_staged_population_file(repo: Path) -> None:
    _record(repo)
    ledger = evidence.load_ledger()
    ledger["population"] = {
        "only_mutate": ["research/analysis/*.py"],
        "do_not_mutate": [],
    }
    evidence.save_ledger(ledger)
    findings = evidence.staged_findings([OUTSIDE])
    assert any("configured is" in finding for finding in findings)


def test_emptying_the_population_blocks_against_recorded_evidence(repo: Path) -> None:
    _record(repo)
    (repo / "pyproject.toml").write_text(
        "[tool.mutmut]\nonly_mutate = []\n\n[tool.ruff]\n", encoding="utf-8"
    )
    findings = evidence.staged_findings([MODULE])
    assert any("configured is" in finding for finding in findings)


def test_config_only_staging_passes_when_the_ledger_matches(repo: Path) -> None:
    _record(repo)
    assert evidence.staged_findings(["pyproject.toml"]) == []


def test_glob_matching_respects_segments_and_double_star(repo: Path) -> None:
    assert evidence.match_population(MODULE, POPULATION)
    assert not evidence.match_population("research/runtime/sub/deep.py", POPULATION)
    spanning = {"only_mutate": ["research/**/*.py"], "do_not_mutate": []}
    assert evidence.match_population("research/runtime/sub/deep.py", spanning)
    assert not evidence.match_population("tests/research/x.py", spanning)


@pytest.mark.parametrize(
    "name",
    ["MUTATION_GATE", "SKIP_MUTATION", "RESEARCH_ALLOW_MUTANTS", "MUTATION_EVIDENCE"],
)
@pytest.mark.parametrize("value", ["0", "1", "skip", "off"])
def test_no_environment_variable_downgrades_the_gate(
    repo: Path, monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    baseline = len(evidence.staged_findings([MODULE]))
    assert baseline > 0
    assert len(evidence.staged_findings([MODULE])) == baseline


def test_cli_evidence_only_exits_nonzero_on_findings(repo: Path) -> None:
    args = ["--mode", "staged", "--evidence-only", "--strict", "--staged", MODULE]
    assert check_mutation.main(args) == 1
    _record(repo)
    assert check_mutation.main(args) == 0


def test_refresh_refuses_a_worktree_that_differs_from_the_index(repo: Path) -> None:
    (repo / MODULE).write_text("def require_device(device):\n    return 1\n")
    assert check_mutation.main(["--mode", "staged", "--staged", MODULE]) == 1


def test_aggregate_maps_mutmut_statuses_and_unknown_codes_block() -> None:
    pytest.importorskip("mutmut.stats")
    table, fallback, error = scoring.status_table()
    assert error is None and table is not None and fallback is not None
    unknown = max(code for code in table if isinstance(code, int)) + 7
    statuses = {
        "a": table[1],
        "b": table[0],
        "c": table[5],
        "d": fallback,
    }
    counts = scoring.aggregate(statuses)
    assert counts["killed"] == 1
    assert counts["survived"] == 1
    assert counts["no_tests"] == 1
    assert counts["suspicious"] == 1
    assert counts["mutants"] == 4
    assert table.get(unknown, fallback) == fallback
    assert scoring.names_by_status(statuses)["survived"] == ["b"]
