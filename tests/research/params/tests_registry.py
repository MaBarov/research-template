"""Mirror tests for the parameter registry: uniqueness, lookup and pin shape."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from research.params import registry
from research.params.registry import Parameter, by_env, by_name

REGISTRY_FILE = (
    Path(__file__).resolve().parents[3] / "research" / "params" / "registry.py"
)


def test_registry_rows_are_unique() -> None:
    names = [row.name for row in registry.PARAMETERS]
    envs = [row.env for row in registry.PARAMETERS if row.env]
    assert len(names) == len(set(names))
    assert len(envs) == len(set(envs))
    assert registry.PARAMETERS, "the registry must not be empty"


def test_registry_row_shape() -> None:
    row = by_name("seed")
    assert isinstance(row, Parameter)
    assert row.kind == "int"
    assert row.env is not None and row.env.startswith("RESEARCH_")
    assert row.default == "0"
    assert row.accessors == ("seed",)


def test_by_env_round_trips_and_rejects_unknown() -> None:
    assert by_env("RESEARCH_STEPS") is by_name("steps")
    assert by_env("RESEARCH_NOT_REGISTERED") is None


def test_by_name_rejects_unknown() -> None:
    with pytest.raises(KeyError):
        by_name("not_a_registered_parameter")


def test_aliases_map_to_canonical_envs_not_defaults() -> None:
    assert registry.ALIAS_TO_ENV == {"RESEARCH_RANDOM_SEED": "RESEARCH_SEED"}
    assert all(by_env(env) is not None for env in registry.ALIAS_TO_ENV.values())
    assert registry.BANNED_LITERALS == {}
    assert registry.MODEL_SNAPSHOTS == {}


def test_registry_defaults_parse_under_their_kind() -> None:
    parsers = {"int": int, "float": float, "str": str, "path": str}
    for row in registry.PARAMETERS:
        parser = parsers[row.kind]
        assert parser(row.default) == parser(row.default)


def test_registry_body_loads_standalone_by_file_path() -> None:
    """The gate loads the registry by path, not through the package: it must work."""

    spec = importlib.util.spec_from_file_location("_registry_standalone", REGISTRY_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_registry_standalone"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_registry_standalone", None)
    assert module.PARAMETERS is not registry.PARAMETERS
    assert [row.name for row in module.PARAMETERS] == [
        row.name for row in registry.PARAMETERS
    ]
    assert module.by_name("steps").default == registry.by_name("steps").default
