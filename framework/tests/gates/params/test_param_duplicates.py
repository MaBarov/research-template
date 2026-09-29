"""Fixtures for the parameter-drift matchers and the gate CLI.

Invariants & Expected State:
    - Exempt from the gate's own scan (``param_checks.EXEMPT_PATHS``): this module
      names the superseded alias and synthetic banned literals on purpose.
    - The shipped registry has two rows (``seed``/``steps``); every surface the
      registry cannot trigger (constant names, banned literals, owner scoping) is
      built here on a synthetic ``Parameter`` and patched onto the derived tables
      of ``param_checks`` (``_FLAG_ROWS``, ``_ATTR_ROWS``, ``_CONSTANT_ROWS``,
      ``_LITERAL_ROWS``, ``REGISTRY``) under the real attribute names.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from types import SimpleNamespace

from framework.gates.params import check_param_duplicates as cli
from framework.gates.params import param_checks, param_matchers
from research.params.registry import Parameter

_PROBE_PATH = "research/probe/plan.py"


def _codes(findings: list[param_checks.Finding]) -> list[str]:
    return [finding.code for finding in findings]


def _row(**overrides: object) -> Parameter:
    """Return one synthetic row with every field defaulted."""

    fields: dict[str, object] = {
        "name": "probe",
        "env": "RESEARCH_PROBE",
        "default": "7",
        "kind": "int",
    }
    fields.update(overrides)
    return Parameter(**fields)  # type: ignore[arg-type]


def _patch_shell_artifact(monkeypatch) -> None:
    """Patch a path parameter that is only ever written through a deviation."""
    artifact = _row(
        name="artifact",
        env="RESEARCH_ARTIFACT",
        default="/shared/artifacts",
        kind="path",
        literals=("/shared/artifacts/v1",),
    )
    monkeypatch.setattr(param_checks, "REGISTRY", _registry((artifact,)))
    monkeypatch.setattr(
        param_checks, "_LITERAL_ROWS", (("/shared/artifacts/v1", "artifact"),)
    )


def _registry(rows: tuple[Parameter, ...]) -> SimpleNamespace:
    """Return a registry stand-in exposing ``by_name`` over ``rows``."""

    index = {row.name: row for row in rows}
    return SimpleNamespace(by_name=index.__getitem__, PARAMETERS=rows)


def test_python_and_shell_alias_are_hns038() -> None:
    python = "import os\nprior = os.environ.get('RESEARCH_RANDOM_SEED')\n"
    shell = "unset RESEARCH_RANDOM_SEED\n"

    python_findings = param_matchers.python_findings(python, "research/x.py")
    shell_findings = param_matchers.shell_findings(shell, "slurm/x.sbatch")

    assert _codes(python_findings) == ["HNS038"]
    assert python_findings[0].line == 2
    assert "superseded by RESEARCH_SEED" in python_findings[0].message
    assert _codes(shell_findings) == ["HNS038"]
    assert shell_findings[0].line == 1


def test_alias_matching_respects_token_boundaries() -> None:
    source = "RESEARCH_RANDOM_SEED_EXTRA = 1\nOTHER_RESEARCH_RANDOM_SEED = 2\n"

    assert param_matchers.python_findings(source, "research/x.py") == []


def test_registered_env_reads_are_hns039() -> None:
    source = (
        "import os\n"
        "a = os.environ.get('RESEARCH_SEED')\n"
        "b = os.environ['RESEARCH_STEPS']\n"
        "c = os.getenv('RESEARCH_SEED')\n"
        "d = os.environ.get('UNRELATED_VAR', 'x')\n"
    )

    findings = param_matchers.python_findings(source, "research/x.py")

    assert _codes(findings) == ["HNS039"] * 3
    assert {finding.message.split(":")[0] for finding in findings} == {"seed", "steps"}


def test_env_helper_reads_are_hns039() -> None:
    source = "value = _env_int('RESEARCH_SEED', 0)\n"

    findings = param_matchers.python_findings(source, "research/x.py")

    assert _codes(findings) == ["HNS039"]
    assert "read via _env_int" in findings[0].message


def test_argparse_default_is_scoped_to_owner_modules(monkeypatch) -> None:
    row = _row(owners=(_PROBE_PATH,))
    monkeypatch.setattr(param_checks, "_FLAG_ROWS", (("--seed", row),))
    source = "parser.add_argument('--seed', type=int, default=2026)\n"

    owned = param_matchers.python_findings(source, _PROBE_PATH)
    unowned = param_matchers.python_findings(source, "research/other.py")

    assert _codes(owned) == ["HNS039"]
    assert owned[0].message.startswith("probe: ")
    assert unowned == []


def test_argparse_default_through_a_local_alias_is_flagged(monkeypatch) -> None:
    row = _row(owners=(_PROBE_PATH,))
    monkeypatch.setattr(param_checks, "_FLAG_ROWS", (("--seed", row),))
    source = (
        "parser = argparse.ArgumentParser()\n"
        "add = parser.add_argument\n"
        "add('--seed', type=int, default=2026)\n"
    )

    findings = param_matchers.python_findings(source, _PROBE_PATH)
    clean = param_matchers.python_findings(
        source.replace("default=2026", "default=int_param('seed')"), _PROBE_PATH
    )

    assert _codes(findings) == ["HNS039"]
    assert findings[0].message.startswith("probe: ")
    assert clean == []


def test_argparse_default_none_is_not_a_second_default() -> None:
    source = "parser.add_argument('--steps', type=int, default=None)\n"

    assert param_matchers.python_findings(source, _PROBE_PATH) == []


def test_integer_flag_pair_restating_the_default_is_flagged() -> None:
    source = "ARGS = ['--steps', 3]\n"

    findings = param_matchers.python_findings(source, _PROBE_PATH)

    assert _codes(findings) == ["HNS039"]
    assert findings[0].message.startswith("steps: ")


def test_flag_pair_with_an_explicit_value_is_allowed() -> None:
    source = "GROUPS = (('--steps', '2'), ('--seed', str(seed)))\n"

    assert param_matchers.python_findings(source, _PROBE_PATH) == []


def test_tuple_recipe_restating_the_default_is_flagged() -> None:
    source = "TAIL = (('--seed', '0'), ('--strict',))\n"

    findings = param_matchers.python_findings(source, _PROBE_PATH)

    assert _codes(findings) == ["HNS039"]
    assert findings[0].message.startswith("seed: ")


def test_registered_constant_assignment_is_scoped_by_owner(monkeypatch) -> None:
    row = _row(constants=("PLAN_WEIGHTS",), owners=(_PROBE_PATH,))
    monkeypatch.setattr(param_checks, "_CONSTANT_ROWS", (("PLAN_WEIGHTS", row),))

    owned = param_matchers.python_findings("PLAN_WEIGHTS = 7\n", _PROBE_PATH)
    unowned = param_matchers.python_findings("PLAN_WEIGHTS = 7\n", "research/other.py")

    assert _codes(owned) == ["HNS039"]
    assert owned[0].message.startswith("probe: ")
    assert unowned == []


def test_registry_reads_are_not_constant_findings(monkeypatch) -> None:
    row = _row(constants=("PLAN_WEIGHTS",), owners=(_PROBE_PATH,))
    monkeypatch.setattr(param_checks, "_CONSTANT_ROWS", (("PLAN_WEIGHTS", row),))
    source = (
        "from research.params import int_param\nPLAN_WEIGHTS = int_param('steps')\n"
    )

    assert param_matchers.python_findings(source, _PROBE_PATH) == []


def test_getattr_default_is_hns039() -> None:
    source = "value = getattr(args, 'seed', 0)\n"

    findings = param_matchers.python_findings(source, _PROBE_PATH)

    assert _codes(findings) == ["HNS039"]
    assert findings[0].message.startswith("seed: ")


def test_shell_fallback_drift_requires_the_deviation_form() -> None:
    equal = "export RESEARCH_STEPS=${RESEARCH_STEPS:-3}\n"
    drift = "RESEARCH_STEPS=${RESEARCH_STEPS:-4}\n"
    empty = "SEED=${RESEARCH_SEED:-}\n"

    assert param_matchers.shell_findings(equal, "slurm/x.sbatch") == []
    assert param_matchers.shell_findings(empty, "slurm/x.sbatch") == []
    findings = param_matchers.shell_findings(drift, "slurm/x.sbatch")
    assert _codes(findings) == ["HNS039"]
    assert 'write : "${RESEARCH_STEPS:=4}"' in findings[0].message


def test_shell_quoted_fallbacks_compare_unquoted() -> None:
    quoted_empty = 'SEED=${RESEARCH_SEED:-""}\n'
    quoted_equal = 'STEPS=${RESEARCH_STEPS:-"3"}\n'
    quoted_drift = 'STEPS=${RESEARCH_STEPS:-"4"}\n'

    assert param_matchers.shell_findings(quoted_empty, "slurm/x.sbatch") == []
    assert param_matchers.shell_findings(quoted_equal, "slurm/x.sbatch") == []
    findings = param_matchers.shell_findings(quoted_drift, "slurm/x.sbatch")
    assert _codes(findings) == ["HNS039"]
    assert "fallback 4" in findings[0].message


def test_python_literals_ignore_docstrings_but_flag_values(monkeypatch) -> None:
    monkeypatch.setattr(
        param_checks, "_LITERAL_ROWS", (("/shared/artifacts/v1", "artifact"),)
    )
    docstring = '"""Pinned at /shared/artifacts/v1."""\n'
    value = 'SNAPSHOT = "/shared/artifacts/v1"\n'

    assert param_matchers.python_findings(docstring, "research/x.py") == []
    findings = param_matchers.python_findings(value, "research/x.py")
    assert _codes(findings) == ["HNS040"]
    assert findings[0].message.startswith("artifact: ")


def test_one_line_reports_each_parameter_once(monkeypatch) -> None:
    monkeypatch.setattr(
        param_checks,
        "_LITERAL_ROWS",
        (("/shared/artifacts", "artifact"), ("/shared/artifacts/v1", "artifact")),
    )
    line = 'P = "/shared/artifacts/v1/model"\n'

    findings = param_matchers.python_findings(line, "research/x.py")

    assert _codes(findings) == ["HNS040"]
    assert findings[0].message.startswith("artifact: ")
    assert any(
        literal in findings[0].message for literal in ("/shared/artifacts", "/v1")
    )


def test_shell_deviation_statement_is_allowed(monkeypatch) -> None:
    _patch_shell_artifact(monkeypatch)
    deviation = (
        ': "${RESEARCH_ARTIFACT:=/shared/artifacts/v1}"; export RESEARCH_ARTIFACT\n'
    )
    copied = 'echo "/shared/artifacts/v1"\n'

    assert param_matchers.shell_findings(deviation, "scripts/x.sh") == []
    findings = param_matchers.shell_findings(copied, "scripts/x.sh")
    assert _codes(findings) == ["HNS040"]
    assert findings[0].message.startswith("artifact: ")


def test_shell_inline_deviation_prefix_is_allowed(monkeypatch) -> None:
    _patch_shell_artifact(monkeypatch)
    line = "RESEARCH_ARTIFACT=/shared/artifacts/v1 python build.py\n"

    assert param_matchers.shell_findings(line, "scripts/x.sh") == []


def test_unparseable_python_is_hns041() -> None:
    findings = param_matchers.python_findings("def broken(:\n", "research/x.py")

    assert _codes(findings) == ["HNS041"]


def test_shipped_registry_is_wellformed() -> None:
    assert param_checks.registry_findings() == []


def test_registry_self_check_detects_a_duplicate_name(monkeypatch) -> None:
    first = _row(name="dup")
    second = replace(first, env="RESEARCH_DUP_TWO")
    monkeypatch.setattr(param_checks.REGISTRY, "PARAMETERS", (first, second))

    messages = [finding.message for finding in param_checks.registry_findings()]

    assert any("duplicate parameter name" in message for message in messages)


def test_registry_self_check_detects_a_duplicate_env(monkeypatch) -> None:
    first = _row(name="alpha")
    second = replace(first, name="beta")
    monkeypatch.setattr(param_checks.REGISTRY, "PARAMETERS", (first, second))

    messages = [finding.message for finding in param_checks.registry_findings()]

    assert any("duplicate env var" in message for message in messages)


def test_registry_self_check_detects_a_duplicate_alias(monkeypatch) -> None:
    first = _row(name="alpha", aliases=("RESEARCH_OLD",))
    second = _row(name="beta", env="RESEARCH_BETA", aliases=("RESEARCH_OLD",))
    monkeypatch.setattr(param_checks.REGISTRY, "PARAMETERS", (first, second))

    messages = [finding.message for finding in param_checks.registry_findings()]

    assert any("duplicate alias" in message for message in messages)


def test_registry_self_check_detects_a_duplicate_literal(monkeypatch) -> None:
    first = _row(name="alpha", literals=("/shared/x",))
    second = _row(name="beta", env="RESEARCH_BETA", literals=("/shared/x",))
    monkeypatch.setattr(param_checks.REGISTRY, "PARAMETERS", (first, second))

    messages = [finding.message for finding in param_checks.registry_findings()]

    assert any("duplicate banned literal" in message for message in messages)


def test_registry_self_check_detects_an_alias_env_collision(monkeypatch) -> None:
    first = _row(name="alpha", env="RESEARCH_ALPHA", aliases=("RESEARCH_BETA",))
    second = _row(name="beta", env="RESEARCH_BETA")
    monkeypatch.setattr(param_checks.REGISTRY, "PARAMETERS", (first, second))

    messages = [finding.message for finding in param_checks.registry_findings()]

    assert any("alias collides with a canonical env" in message for message in messages)


def test_registry_self_check_detects_a_malformed_row(monkeypatch) -> None:
    wrong_kind = _row(name="alpha", kind="banana")
    bad_default = _row(name="beta", env="RESEARCH_BETA", kind="int", default="lots")
    gone_owner = _row(
        name="gamma", env="RESEARCH_GAMMA", owners=("research/absent.py",)
    )
    monkeypatch.setattr(
        param_checks.REGISTRY, "PARAMETERS", (wrong_kind, bad_default, gone_owner)
    )

    messages = [finding.message for finding in param_checks.registry_findings()]

    assert any("unknown kind banana" in message for message in messages)
    assert any("bad int default lots" in message for message in messages)
    assert any(
        "owner research/absent.py does not exist" in message for message in messages
    )


def test_registry_self_check_detects_an_unpinned_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(param_checks.REGISTRY, "MODEL_SNAPSHOTS", {"demo": "repo@main"})

    messages = [finding.message for finding in param_checks.registry_findings()]

    assert any("missing a pinned revision" in message for message in messages)


def test_scope_filters_exempt_and_skipped_paths() -> None:
    assert cli._in_scope("research/params/registry.py") is False
    assert cli._in_scope("third_party/foo/bar.py") is False
    assert cli._in_scope("cache/worktrees/ap_head/x.py") is False
    assert cli._in_scope("research/probe/plan.py") is True
    assert cli.files_to_check(["/tmp/outside.py"]) == ["/tmp/outside.py"]


def test_every_exempt_path_exists() -> None:
    """A moved file must not leave a stale exemption behind."""

    assert [
        p for p in param_checks.EXEMPT_PATHS if not (param_checks.REPO / p).is_file()
    ] == []


def test_main_reports_findings_and_writes_the_tally(tmp_path) -> None:
    violating = tmp_path / "violating.py"
    violating.write_text(
        "import os\nprior = os.environ.get('RESEARCH_RANDOM_SEED')\n", encoding="utf-8"
    )
    report = tmp_path / "report.txt"

    code = cli.main(["--strict", "--report", str(report), str(violating)])

    assert code == 1
    text = report.read_text(encoding="utf-8")
    assert f"{violating}:2: HNS038" in text
    assert "# per-parameter tally" in text
    assert "1  RESEARCH_SEED" in text


def test_main_passes_on_a_clean_file(tmp_path, capsys) -> None:
    clean = tmp_path / "clean.py"
    clean.write_text("from research.params import seed\n\nSEED = seed()\n", "utf-8")

    assert cli.main(["--strict", str(clean)]) == 0
    assert "0 finding(s)" in capsys.readouterr().out


def test_module_body_reexecutes_without_side_effects() -> None:
    import importlib.util
    from pathlib import Path

    for name in ("param_checks", "check_param_duplicates"):
        source = Path(sys.modules[f"framework.gates.params.{name}"].__file__)
        spec = importlib.util.spec_from_file_location(f"_cover_{name}", source)
        assert spec is not None and spec.loader is not None
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = loaded
        try:
            spec.loader.exec_module(loaded)
        finally:
            del sys.modules[spec.name]
        assert loaded.__name__ == spec.name
    assert param_checks.REPO == cli.param_checks.REPO
    assert cli.TOOL == "check_param_duplicates"
