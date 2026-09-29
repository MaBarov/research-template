"""Mirror tests for the example plan builder: purity, bounds and status line."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from research.probe import plan as plan_module
from research.probe.plan import build_plan, main

PLAN_FILE = Path(__file__).resolve().parents[3] / "research" / "probe" / "plan.py"


@pytest.fixture()
def seeded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_SEED", "5")


def test_build_plan_is_deterministic(seeded: None) -> None:
    first = build_plan(4)
    second = build_plan(4)
    assert first == second
    assert [step.index for step in first] == [0, 1, 2, 3]


def test_build_plan_covers_empty_single_and_many(seeded: None) -> None:
    assert build_plan(0) == ()
    assert build_plan(1) == (plan_module.Step(0, 5),)
    assert len(build_plan(3)) == 3


def test_build_plan_uses_the_registered_step_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESEARCH_STEPS", raising=False)
    assert len(build_plan()) == 3
    monkeypatch.setenv("RESEARCH_STEPS", "1")
    assert len(build_plan()) == 1


def test_weights_stay_inside_the_modulus(seeded: None) -> None:
    assert all(0 <= step.weight < 7 for step in build_plan(10))


def test_main_prints_one_status_line(
    seeded: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["status=PLAN_READY steps=3 seed=5 total=11"]


def test_main_honours_the_flag_override(
    seeded: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--steps", "1"]) == 0
    assert "steps=1" in capsys.readouterr().out


def test_plan_module_body_loads_standalone_by_file_path() -> None:
    """A run entry point imports the plan by path; the module body must stand alone."""

    spec = importlib.util.spec_from_file_location("_plan_standalone", PLAN_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_plan_standalone"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_plan_standalone", None)
    assert (
        plan_module.Step.__dataclass_fields__.keys()
        == module.Step.__dataclass_fields__.keys()
    )
    fresh = [(step.index, step.weight) for step in module.build_plan(2)]
    assert fresh == [(step.index, step.weight) for step in plan_module.build_plan(2)]
