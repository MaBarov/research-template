"""Behavioral tests for framework/gates/provenance/record_run_manifest.py.

The recorder writes into the repository's own ``results/`` ledger, so each test
runs the real CLI inside a scratch repository that holds a copy of the recorder
and of the payload it pins.  Nothing here touches this repository's ledger.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from framework import harness

REPO = Path(__file__).resolve().parents[2]
RECORDER = "framework/gates/provenance/record_run_manifest.py"
SCRIPT = "slurm/template.sbatch"


def scratch_repo(tmp_path: Path) -> Path:
    """Build a committed scratch repository holding the recorder and one payload."""
    repo = tmp_path / "repo"
    (repo / "slurm").mkdir(parents=True)
    copy_import_surface(repo)
    for args in (
        ["init", "-q"],
        ["add", "-A"],
        [
            "-c",
            "user.email=manifest@test",
            "-c",
            "user.name=manifest",
            "commit",
            "-qm",
            "base",
        ],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return repo


def copy_import_surface(repo: Path) -> None:
    """Copy the recorder's import surface and one payload into the scratch tree."""

    # The recorder resolves its checkout through framework/harness.py and its
    # git facts through the provenance package, so the scratch tree needs the
    # same import surface, not just the recorder script.
    for relative in (
        "framework/__init__.py",
        "framework/harness.py",
        "framework/gates/__init__.py",
        "framework/gates/provenance/__init__.py",
        "framework/gates/provenance/git_facts.py",
        RECORDER,
    ):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    shutil.copy2(REPO / SCRIPT, repo / SCRIPT)


def record(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the real recorder inside the scratch repository."""
    return subprocess.run(
        [sys.executable, str(repo / RECORDER), *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def manifest_of(repo: Path, run: str) -> dict:
    return json.loads(
        (repo / "results" / "manifests" / f"{run}.json").read_text(encoding="utf-8")
    )


def test_settings_are_recorded_with_the_pins(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    result = record(
        repo,
        "--run",
        "unit_settings",
        "--script",
        SCRIPT,
        "--setting",
        "model_id=demo-model",
        "--setting",
        "carrier_rank=19",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = manifest_of(repo, "unit_settings")
    assert manifest["settings"] == {
        "model_id": "demo-model",
        "carrier_rank": "19",
    }
    assert manifest["schema"] == harness.RUN_MANIFEST_SCHEMA
    assert manifest["paths"]["producer_script"] == SCRIPT
    assert manifest["pins"]["producer_script_sha256"]


def test_no_settings_flag_records_an_empty_block(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    assert record(repo, "--run", "unit_bare", "--script", SCRIPT).returncode == 0
    assert manifest_of(repo, "unit_bare")["settings"] == {}


def test_a_malformed_setting_fails_closed(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    result = record(
        repo, "--run", "unit_bad", "--script", SCRIPT, "--setting", "banana"
    )
    assert result.returncode == 1
    assert "FAIL-CLOSED" in result.stderr
    assert not (repo / "results" / "manifests" / "unit_bad.json").exists()


def test_from_manifest_reuses_the_recorded_settings(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    assert (
        record(
            repo,
            "--run",
            "unit_first",
            "--script",
            SCRIPT,
            "--setting",
            "rounds=5",
            "--setting",
            "max_round_dose=0.4",
        ).returncode
        == 0
    )
    replay = record(
        repo,
        "--run",
        "unit_replay",
        "--from-manifest",
        "results/manifests/unit_first.json",
    )
    assert replay.returncode == 0, replay.stdout + replay.stderr
    assert manifest_of(repo, "unit_replay")["settings"] == {
        "rounds": "5",
        "max_round_dose": "0.4",
    }
