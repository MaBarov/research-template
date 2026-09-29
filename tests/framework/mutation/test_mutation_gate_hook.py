"""Exercise mutation-evidence enforcement through a real Git commit and hook."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.framework.scratch import hook_fixtures

PROBE = "research/params/__init__.py"
PROBE_SOURCE = '"""Runtime probe marker for the mutation gate hook test."""\n'
LEDGER = "framework/mutation_evidence.json"
EVIDENCE_KNOBS = {
    "MUTATION_GATE": "0",
    "SKIP_MUTATION": "1",
    "RESEARCH_ALLOW_MUTANTS": "off",
    "MUTATION_EVIDENCE": "/dev/null",
}
_RECORD_TEMPLATE = """
import sys

sys.path.insert(0, ".")
from framework.gates.mutation import evidence

sha = evidence.staged_sha256(%r)
population, error = evidence.config_population()
assert error is None, error
stamp = "2026-09-28T00:00:00+00:00"
entry = {
    "content_sha256": sha,
    "mutmut_version": "mutmut, version 3.8.0",
    "recorded_at": stamp,
    "mutants": 1,
    "killed": 1,
    "skipped": 0,
}
evidence.save_ledger({
    "schema": evidence.SCHEMA,
    "population": population,
    "mutmut_version": "mutmut, version 3.8.0",
    "recorded_at": stamp,
    "modules": {%r: entry},
})"""
RECORD_SNIPPET = _RECORD_TEMPLATE % (PROBE, PROBE)


def hook_checkout(root: Path) -> dict[str, str]:
    """Build a scratch checkout whose pre-commit hook is the mutation gate."""
    return hook_fixtures.hook_checkout(
        root,
        drop=("framework/coverage_evidence.json", LEDGER),
        copy=("pyproject.toml",),
        registry=True,
    )


def stage_probe(root: Path, env: dict[str, str]) -> None:
    """Stage a runtime package marker that is inside the mutated population."""
    probe = root / PROBE
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(PROBE_SOURCE, encoding="utf-8")
    assert hook_fixtures.run_git(root, env, "add", PROBE).returncode == 0


def record_cleared_evidence(root: Path, env: dict[str, str]) -> None:
    """Record a killed-mutant ledger entry for the staged probe content."""
    result = subprocess.run(
        [sys.executable, "-c", RECORD_SNIPPET],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_real_commit_refuses_a_population_module_without_cleared_evidence(
    tmp_path: Path,
) -> None:
    env = hook_checkout(tmp_path)
    stage_probe(tmp_path, env)
    before = hook_fixtures.run_git(tmp_path, env, "rev-parse", "HEAD").stdout
    refused = hook_fixtures.run_git(tmp_path, env, "commit", "-qm", "uncleared probe")
    output = refused.stdout + refused.stderr
    assert refused.returncode != 0
    assert "mutation gate blocked this commit" in output, output
    assert PROBE in output, output
    assert hook_fixtures.run_git(tmp_path, env, "rev-parse", "HEAD").stdout == before


def test_no_environment_variable_downgrades_the_gate(tmp_path: Path) -> None:
    env = hook_checkout(tmp_path)
    env.update(EVIDENCE_KNOBS)
    stage_probe(tmp_path, env)
    refused = hook_fixtures.run_git(
        tmp_path, env, "commit", "-qm", "uncleared probe with knobs"
    )
    output = refused.stdout + refused.stderr
    assert refused.returncode != 0
    assert "mutation gate blocked this commit" in output, output


def test_missing_gate_script_fails_closed(tmp_path: Path) -> None:
    env = hook_checkout(tmp_path)
    (tmp_path / "framework/gates/mutation/check_mutation.py").unlink()
    stage_probe(tmp_path, env)
    refused = hook_fixtures.run_git(tmp_path, env, "commit", "-qm", "gate deleted")
    output = refused.stdout + refused.stderr
    assert refused.returncode != 0
    assert "mutation gate missing" in output, output


def test_real_commit_accepts_the_probe_once_evidence_is_recorded(
    tmp_path: Path,
) -> None:
    env = hook_checkout(tmp_path)
    stage_probe(tmp_path, env)
    record_cleared_evidence(tmp_path, env)
    assert hook_fixtures.run_git(tmp_path, env, "add", LEDGER).returncode == 0
    accepted = hook_fixtures.run_git(tmp_path, env, "commit", "-qm", "cleared probe")
    output = accepted.stdout + accepted.stderr
    assert accepted.returncode == 0, output
    assert "PASS: staged modules carry cleared evidence" in output, output


def test_commit_of_a_file_outside_the_population_passes(tmp_path: Path) -> None:
    env = hook_checkout(tmp_path)
    note = tmp_path / "tests/framework/test_mutation_gate_note.py"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("def test_note():\n    assert True\n", encoding="utf-8")
    assert hook_fixtures.run_git(tmp_path, env, "add", "tests").returncode == 0
    accepted = hook_fixtures.run_git(
        tmp_path, env, "commit", "-qm", "outside the population"
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
