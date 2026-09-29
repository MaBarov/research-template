"""Behavioral tests for scripts/setup/bootstrap.py: plan, refusal, reuse.

The bootstrap is exercised in scratch checkouts that copy the import surface it
needs (``framework/harness.py`` plus the script itself), so no test touches this
repository's own venv or hooks.
"""

from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BOOTSTRAP = "scripts/setup/bootstrap.py"
COPIES = ("framework/__init__.py", "framework/harness.py", BOOTSTRAP)


def fake_interpreter(tmp_path: Path, version: str) -> Path:
    """Write an executable that reports ``version`` to the interpreter probe."""

    path = tmp_path / f"python{version.replace('.', '')}"
    path.write_text(f'#!/bin/sh\necho "{version}"\n')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def scratch_repo(tmp_path: Path) -> Path:
    """Build a checkout holding the bootstrap and the harness it imports."""

    repo = tmp_path / "repo"
    for relative in COPIES:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((REPO / relative).read_text(), encoding="utf-8")
    return repo


def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the bootstrap inside ``repo`` and capture its output."""

    return subprocess.run(
        [sys.executable, BOOTSTRAP, *args],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_dry_run_plans_every_step_and_creates_nothing(tmp_path: Path) -> None:
    """The plan names venv, install, hooks, wiring and suite, and writes nothing."""

    repo = scratch_repo(tmp_path)
    done = run(
        repo, "--dry-run", "--interpreter", str(fake_interpreter(tmp_path, "3.11"))
    )
    assert done.returncode == 0, done.stderr
    assert "-m venv" in done.stdout
    assert "pip install -e .[dev]" in done.stdout
    assert "setup_framework.py" in done.stdout
    assert "check_framework_wiring.py" in done.stdout
    assert "-m pytest tests -q" in done.stdout
    assert "DRY_RUN" in done.stdout
    assert not (repo / ".venv").exists()
    sources = sorted(
        p.relative_to(repo).as_posix()
        for p in repo.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    assert sources == sorted(COPIES)


def test_below_floor_interpreter_is_refused(tmp_path: Path) -> None:
    """A candidate under the harness floor stops the run with the floor message."""

    repo = scratch_repo(tmp_path)
    done = run(
        repo, "--dry-run", "--interpreter", str(fake_interpreter(tmp_path, "3.9"))
    )
    assert done.returncode != 0
    assert "3.11" in done.stderr
    assert not (repo / ".venv").exists()


def test_existing_venv_at_the_floor_is_reused(tmp_path: Path) -> None:
    """A checkout that already has a floor venv plans no venv-creation step."""

    repo = scratch_repo(tmp_path)
    venv_bin = repo / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text('#!/bin/sh\necho "3.12"\n')
    (venv_bin / "python").chmod((venv_bin / "python").stat().st_mode | stat.S_IXUSR)
    done = run(repo, "--dry-run")
    assert done.returncode == 0, done.stderr
    assert "-m venv" not in done.stdout
    assert "[bootstrap] $ " in done.stdout
    assert ".[dev]" in done.stdout


def test_skip_flags_drop_their_steps(tmp_path: Path) -> None:
    """``--skip-install`` and ``--skip-suite`` remove exactly those steps."""

    repo = scratch_repo(tmp_path)
    venv_bin = repo / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text('#!/bin/sh\necho "3.12"\n')
    (venv_bin / "python").chmod((venv_bin / "python").stat().st_mode | stat.S_IXUSR)
    done = run(repo, "--dry-run", "--skip-install", "--skip-suite")
    assert done.returncode == 0, done.stderr
    assert "-m pip install" not in done.stdout
    assert "-m pytest" not in done.stdout
    assert "setup_framework.py" in done.stdout
    assert "check_framework_wiring.py" in done.stdout
