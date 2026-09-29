"""Integration test for the example package: the CLI path and the registry wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from research.params import ambient, int_param, path_param, str_param
from research.probe.plan import main

RUN_MODULE = (
    Path(__file__).resolve().parents[3] / "experiments" / "example_plan" / "plan_run.py"
)


def test_registered_values_resolve_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESEARCH_STEPS", raising=False)
    assert int_param("steps") == 3
    assert str_param("steps") == "3"


def test_ambient_reports_the_width_of_the_idea_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESEARCH_STEPS", raising=False)
    assert ambient("steps") is None
    monkeypatch.setenv("RESEARCH_STEPS", "9")
    assert ambient("steps") == "9"
    assert int_param("steps") == 9


def test_path_param_expands_and_keeps_absolute_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEARCH_STEPS", str(RUN_MODULE))
    assert path_param("steps") == RUN_MODULE


def test_registry_rows_are_not_aliased_twice() -> None:
    from research.params import ALIAS_TO_ENV, BANNED_LITERALS

    assert set(ALIAS_TO_ENV.values()).issubset({"RESEARCH_STEPS", "RESEARCH_SEED"})
    assert not (set(ALIAS_TO_ENV) & set(BANNED_LITERALS))


def test_main_writes_no_receipt_without_a_run_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 0
    assert capsys.readouterr().out.startswith("status=PLAN_READY")
