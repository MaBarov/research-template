"""Mirror tests for the parameter accessors: env-first resolution and fallbacks."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from research.params import resolve

RESOLVE_FILE = (
    Path(__file__).resolve().parents[3] / "research" / "params" / "resolve.py"
)


def _load_standalone():
    """Load the accessors by file path, the way the parameter gate loads them."""

    spec = importlib.util.spec_from_file_location("_resolve_standalone", RESOLVE_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_resolve_standalone"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_resolve_standalone", None)
    return module


def test_accessors_are_importable_by_file_path() -> None:
    module = _load_standalone()
    assert module.seed.__name__ == "seed"
    assert module.default("steps") == resolve.default("steps")


def test_str_param_prefers_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESEARCH_STEPS", raising=False)
    assert resolve.str_param("steps") == "3"
    monkeypatch.setenv("RESEARCH_STEPS", "8")
    assert resolve.str_param("steps") == "8"


def test_int_and_float_accessors_parse_the_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEARCH_STEPS", "12")
    assert resolve.int_param("steps") == 12
    assert resolve.float_param("steps") == 12.0


def test_path_param_expands_the_user_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEARCH_STEPS", "~/data")
    assert resolve.path_param("steps") == Path("~/data").expanduser()


def test_ambient_reports_none_for_an_unset_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESEARCH_SEED", raising=False)
    assert resolve.ambient("seed") is None
    monkeypatch.setenv("RESEARCH_SEED", "4")
    assert resolve.ambient("seed") == "4"


def test_seed_reads_its_registered_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_SEED", "11")
    assert resolve.seed() == 11
    monkeypatch.delenv("RESEARCH_SEED", raising=False)
    assert resolve.seed() == 0
