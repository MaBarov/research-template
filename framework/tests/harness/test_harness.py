"""Tests for the harness registry: project identity and the interpreter floor.

Invariants & Expected State:
    - ``python()`` refuses an interpreter below ``PYTHON_FLOOR`` and says which
      interpreter it saw, so a hook never fails later with a gate-bug traceback.
    - The floor is the single source of truth: ``pyproject.toml`` restates it for
      packaging only, and the two must agree.
"""

from __future__ import annotations

import stat
import tomllib
from pathlib import Path

import pytest

from framework import harness


def _fake_interpreter(directory: Path, version: str) -> Path:
    """Write a shim that answers the version probe with ``version``."""

    path = directory / "python"
    path.write_text(f'#!/bin/sh\necho "{version}"\n', encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_python_refuses_an_interpreter_below_the_floor(tmp_path, monkeypatch) -> None:
    shim = _fake_interpreter(tmp_path, "3.10")
    monkeypatch.setenv(harness.env("PYTHON"), str(shim))

    with pytest.raises(SystemExit) as excinfo:
        harness.python()

    message = str(excinfo.value)
    assert "3.10" in message
    assert harness.PYTHON_FLOOR in message


def test_python_accepts_an_interpreter_at_the_floor(tmp_path, monkeypatch) -> None:
    shim = _fake_interpreter(tmp_path, harness.PYTHON_FLOOR)
    monkeypatch.setenv(harness.env("PYTHON"), str(shim))

    assert harness.python() == str(shim)


def test_floor_matches_the_packaging_floor() -> None:
    packaging = tomllib.loads((harness.REPO / "pyproject.toml").read_text("utf-8"))

    assert packaging["project"]["requires-python"] == f">={harness.PYTHON_FLOOR}"


def test_floor_is_exposed_as_a_key() -> None:
    assert harness.KEYS["python-floor"] == harness.PYTHON_FLOOR


def test_dvc_bin_prefers_the_venv_binary(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(harness.env("DVC_BIN"), raising=False)
    monkeypatch.setenv(harness.env("VENV"), str(tmp_path))
    assert harness.dvc_bin() == "dvc"

    binary = tmp_path / "bin" / "dvc"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    assert harness.dvc_bin() == str(binary)

    monkeypatch.setenv(harness.env("DVC_BIN"), "/opt/dvc")
    assert harness.dvc_bin() == "/opt/dvc"


def test_engine_bin_prefers_env_then_venv_then_path(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(harness.env("MYPY_BIN"), raising=False)
    monkeypatch.setenv(harness.env("VENV"), str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert harness.engine_bin("mypy") == "mypy"

    binary = tmp_path / "bin" / "mypy"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    assert harness.engine_bin("mypy") == str(binary)

    monkeypatch.setenv(harness.env("MYPY_BIN"), "/opt/mypy")
    assert harness.engine_bin("mypy") == "/opt/mypy"


def test_static_scope_covers_the_static_roots() -> None:
    regex = harness.KEYS["static-scope"]()

    assert regex == r"^(research|framework|scripts|experiments)/.*\.py$"
    assert harness.STATIC_ROOTS == ("research", "framework", "scripts", "experiments")


def test_test_scope_covers_the_test_root() -> None:
    regex = harness.KEYS["test-scope"]()

    assert regex == rf"^({harness.TEST_ROOT})/.*\.py$"
    assert harness.main(["--get", "test-scope"]) == 0


def test_gate_state_and_cache_dirs_are_slug_scoped(monkeypatch) -> None:
    assert harness.KEYS["gate-state-dir"] == f"{harness.SLUG}-gate"
    assert harness.KEYS["cache-dir"] == "cache"
    assert "tests" in harness.EXCLUDED_PARTS


def test_keys_key_lists_every_key() -> None:
    names = harness.KEYS["keys"]()

    assert "static-scope" in names
    assert "mypy-bin" in names
    assert "keys" in names


def test_bare_invocation_prints_every_key(capsys) -> None:
    assert harness.main([]) == 0

    printed = capsys.readouterr().out
    for key in harness.KEYS:
        assert f"{key}: " in printed


def test_superseded_distortion_scope_key_is_unknown(capsys) -> None:
    assert harness.main(["--get", "distortion-scope"]) == 2

    assert "unknown harness key" in capsys.readouterr().err
