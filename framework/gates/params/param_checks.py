"""Drift matchers for the canonical parameter registry (codes HNS038-HNS041).

Invariants & Expected State:
    - The registry is loaded from its file path with ``importlib``, never through the
      ``research`` package: the gate runs under a bare interpreter and must not import torch.
    - ``owners`` scopes a check to the registry row's modules; ``None`` means
      repository-wide, and a module no row lists is out of scope.
    - Fail closed: an unreadable or unparseable file yields a finding, never silence.
    - Every finding names its parameter or alias first, so the report can tally drift.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

from framework import harness
from framework.gates.antipattern.targets import Finding

REPO = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO / harness.REGISTRY_PATH
CHECKED_SUFFIXES = frozenset({".py", ".sh", ".sbatch"})
SKIP_PARTS = frozenset({"cache", "mutants", "third_party"})
EXEMPT_PATHS = frozenset(
    {
        harness.REGISTRY_PATH,
        harness.REGISTRY_TEST_PATH,
        "framework/gates/params/param_checks.py",
        "framework/gates/params/check_param_duplicates.py",
        "framework/tests/gates/params/test_param_duplicates.py",
    }
)


def _load_registry() -> Any:
    """Load the registry module by file path, keeping torch off the import path."""

    spec = importlib.util.spec_from_file_location(
        "_harness_params_registry", REGISTRY_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover - broken checkout
        raise RuntimeError(f"cannot load parameter registry: {REGISTRY_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


REGISTRY = _load_registry()
REGISTRY_PATH_TEXT = REGISTRY_PATH.relative_to(REPO).as_posix()

_FLAG_ROWS: tuple[tuple[str, Any], ...] = tuple(
    (flag, parameter) for parameter in REGISTRY.PARAMETERS for flag in parameter.flags
)
_ATTR_ROWS: tuple[tuple[str, Any], ...] = tuple(
    (name, parameter) for parameter in REGISTRY.PARAMETERS for name in parameter.attrs
)
_CONSTANT_ROWS: tuple[tuple[str, Any], ...] = tuple(
    (name, parameter)
    for parameter in REGISTRY.PARAMETERS
    for name in parameter.constants
)
_ENV_INDEX: dict[str, Any] = {
    parameter.env: parameter for parameter in REGISTRY.PARAMETERS if parameter.env
}
_LITERAL_ROWS: tuple[tuple[str, str], ...] = tuple(
    sorted(REGISTRY.BANNED_LITERALS.items())
)
_ALIAS_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = tuple(
    (
        re.compile(rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])"),
        alias,
        env,
    )
    for alias, env in sorted(REGISTRY.ALIAS_TO_ENV.items())
)
_SHELL_EXPANSION = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):-([^}]*)\}")
_ENV_ASSIGN = re.compile(r"(^|[;&|(\s])(export\s+)?([A-Za-z_][A-Za-z0-9_]*)=")


def _rows_for(rows: tuple[tuple[str, Any], ...], key: str, path: str) -> list[Any]:
    """Return the parameters whose ``rows`` name ``key`` and own ``path``."""

    return [
        row
        for name, row in rows
        if name == key and (row.owners is None or path in row.owners)
    ]


def _duplicate_findings(path: str) -> list[Finding]:
    """Return HNS041 findings for a name, env var, alias or literal used twice."""

    parameters = list(REGISTRY.PARAMETERS)
    envs = [p.env for p in parameters if p.env]
    aliases = [a for p in parameters for a in p.aliases]
    literals = [lit for p in parameters for lit in p.literals]
    checks = (
        ([p.name for p in parameters], "registry: duplicate parameter name"),
        (envs, "registry: duplicate env var"),
        (aliases, "registry: duplicate alias"),
        (literals, "registry: duplicate banned literal"),
    )
    findings = [
        Finding(path, 1, "HNS041", message)
        for values, message in checks
        if len(values) != len(set(values))
    ]
    if set(aliases) & set(envs):
        findings.append(
            Finding(path, 1, "HNS041", "registry: alias collides with a canonical env")
        )
    return findings


def _kind_findings(parameter: Any, path: str) -> list[Finding]:
    """Return HNS041 findings for a row whose kind or default does not parse."""

    parsers = {"int": int, "float": float, "str": str, "path": str}
    parser = parsers.get(parameter.kind)
    if parser is None:
        kind = parameter.kind
        return [Finding(path, 1, "HNS041", f"{parameter.name}: unknown kind {kind}")]
    if not parameter.default:
        return []
    try:
        parser(parameter.default)
    except ValueError:
        message = f"{parameter.name}: bad {parameter.kind} default {parameter.default}"
        return [Finding(path, 1, "HNS041", message)]
    return []


def _row_findings(parameter: Any, path: str) -> list[Finding]:
    """Return the HNS041 findings of one registry row."""

    findings = _kind_findings(parameter, path)
    findings.extend(
        Finding(path, 1, "HNS041", f"{parameter.name}: owner {owner} does not exist")
        for owner in parameter.owners or ()
        if not (REPO / owner).exists()
    )
    return findings


def registry_findings() -> list[Finding]:
    """Return HNS041 findings for a malformed registry table."""

    path = REGISTRY_PATH_TEXT
    findings = _duplicate_findings(path)
    for parameter in REGISTRY.PARAMETERS:
        findings.extend(_row_findings(parameter, path))
    findings.extend(
        Finding(path, 1, "HNS041", f"registry: {model_id} is missing a pinned revision")
        for model_id, snapshot in REGISTRY.MODEL_SNAPSHOTS.items()
        if "/snapshots/" not in snapshot
    )
    return findings
