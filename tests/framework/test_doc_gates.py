"""Behavioral documentation-gate tests with isolated repositories and evidence."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from framework import harness

REPO = Path(__file__).resolve().parents[2]


def run(script: Path, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=script.parents[2],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
        check=False,
    )


@pytest.fixture
def gate_repo(tmp_path: Path) -> Path:
    gates = tmp_path / "framework" / "gates"
    gates.mkdir(parents=True)
    # The gates resolve this checkout through framework/harness.py, so the
    # scratch tree needs the same import surface, not just the gate script.
    for relative in (
        "framework/__init__.py",
        "framework/harness.py",
        "framework/gates/__init__.py",
    ):
        shutil.copyfile(REPO / relative, tmp_path / relative)
    for name in ("check_dvc_tracked.py", "check_documentation.py"):
        shutil.copyfile(REPO / "framework" / "gates" / name, gates / name)
    return tmp_path


def test_tracked_bank_passes_dvc_gate(gate_repo: Path) -> None:
    bank = gate_repo / "bank.json"
    bank.write_text("{}\n", encoding="utf-8")
    commands = (
        ["git", "init", "-q"],
        [sys.executable, "-m", "dvc", "init", "-q"],
        [sys.executable, "-m", "dvc", "add", "bank.json", "-q"],
    )
    for command in commands:
        subprocess.run(command, cwd=gate_repo, check=True, capture_output=True)
    env = dict(os.environ, RESEARCH_DVC_BIN=str(Path(sys.executable).parent / "dvc"))
    gate = gate_repo / "framework/gates/check_dvc_tracked.py"
    assert run(gate, "bank.json", "--strict", env=env).returncode == 0
    bank.write_text('{"changed": true}\n', encoding="utf-8")
    assert run(gate, "bank.json", "--strict", env=env).returncode == 1


def test_untracked_file_fails_dvc_gate(gate_repo: Path) -> None:
    (gate_repo / "bank.json").write_text("{}\n", encoding="utf-8")
    gate = gate_repo / "framework/gates/check_dvc_tracked.py"
    assert run(gate, "bank.json").returncode == 1


def documented_run(repo: Path) -> dict[str, str]:
    for kind, record in (
        ("manifests", {"schema": harness.RUN_MANIFEST_SCHEMA}),
        ("metrics", {"schema": harness.RUN_METRICS_SCHEMA, "psnr": 30}),
    ):
        directory = repo / "results" / kind
        directory.mkdir(parents=True)
        (directory / "drill.json").write_text(json.dumps(record), encoding="utf-8")
    dvc = repo / "dvc-stub"
    dvc.write_text(
        '#!/bin/sh\n[ "$*" = "exp list -A --names-only" ] || exit 2\n'
        'printf "drill\\n"\n',
        encoding="utf-8",
    )
    dvc.chmod(0o755)
    return dict(
        os.environ,
        RESEARCH_DVC_BIN=str(dvc),
        MLFLOW_TRACKING_URI=(repo / "mlruns").as_uri(),
    )


def test_doc_gate_missing_run_fails(gate_repo: Path) -> None:
    env = documented_run(gate_repo)
    gate = gate_repo / "framework/gates/check_documentation.py"
    assert run(gate, "--run", "missing", env=env).returncode == 1


@pytest.mark.parametrize("missing", [None, "manifests", "metrics", "experiment"])
def test_doc_gate_requires_the_whole_chain(
    gate_repo: Path, missing: str | None
) -> None:
    env = documented_run(gate_repo)
    if missing == "experiment":
        Path(env["RESEARCH_DVC_BIN"]).write_text(
            "#!/bin/sh\nexit 0\n", encoding="utf-8"
        )
    elif missing:
        (gate_repo / "results" / missing / "drill.json").unlink()
    gate = gate_repo / "framework/gates/check_documentation.py"
    result = run(gate, "--run", "drill", env=env)
    assert result.returncode == (0 if missing is None else 1), result.stderr
