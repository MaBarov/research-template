"""Tests for the parameter usage sweep (codes HNS042, HNS043)."""

from __future__ import annotations

from framework.gates.params import param_checks, param_usage
from research.params.registry import Parameter

PROBE = "probe_param"


def _probe(**overrides: object) -> Parameter:
    """Return one probe row with every field defaulted."""

    fields: dict[str, object] = {
        "name": PROBE,
        "env": "RESEARCH_PROBE_PARAM",
        "default": "1",
        "kind": "int",
    }
    fields.update(overrides)
    return Parameter(**fields)  # type: ignore[arg-type]


def _codes(rows: list[Parameter], sources: dict[str, str]) -> list[str]:
    """Return the usage codes of ``rows`` against ``sources``."""

    findings = param_usage.usage_findings(texts=sources, rows=rows)
    return [finding.code for finding in findings]


def test_a_named_accessor_call_reads_the_row() -> None:
    row = _probe(accessors=("seed",))
    source = "from research.params import seed\n\nvalue = seed()\n"
    assert _codes([row], {"research/consumer.py": source}) == []


def test_an_aliased_accessor_call_reads_the_row() -> None:
    row = _probe(accessors=("seed",))
    source = (
        "from research.params import seed as registered_seed\n\n"
        "value = registered_seed()\n"
    )
    assert _codes([row], {"research/consumer.py": source}) == []


def test_a_dotted_call_through_the_package_module_reads_the_row() -> None:
    row = _probe(accessors=("seed",))
    source = "import research.params as params\n\nvalue = params.seed()\n"
    assert _codes([row], {"research/consumer.py": source}) == []


def test_a_generic_accessor_with_the_name_reads_the_row() -> None:
    source = (
        "from research.params import int_param\n\nvalue = int_param('probe_param')\n"
    )
    assert _codes([_probe()], {"research/consumer.py": source}) == []


def test_a_generic_accessor_of_another_name_is_not_a_reader() -> None:
    source = "from research.params import str_param\n\nvalue = str_param('other')\n"
    assert _codes([_probe()], {"research/consumer.py": source}) == [
        param_usage.USAGE_CODE
    ]


def test_an_imported_constant_reads_the_row() -> None:
    row = _probe(constants=("PLAN_WEIGHTS",))
    source = "from research.params import PLAN_WEIGHTS\n\nvalue = PLAN_WEIGHTS\n"
    assert _codes([row], {"research/consumer.py": source}) == []


def test_an_ambient_read_of_the_env_var_is_not_a_reader() -> None:
    source = "import os\n\nvalue = os.environ['RESEARCH_PROBE_PARAM']\n"
    assert _codes([_probe()], {"research/consumer.py": source}) == [
        param_usage.USAGE_CODE
    ]


def test_a_test_file_is_not_a_reader() -> None:
    row = _probe(accessors=("seed",))
    source = "from research.params import seed\n\nvalue = seed()\n"
    assert _codes([row], {"tests/research/consumer.py": source}) == [
        param_usage.USAGE_CODE
    ]


def test_the_parameter_package_is_not_a_reader() -> None:
    row = _probe(accessors=("seed",))
    source = "from research.params import seed\n\nvalue = seed()\n"
    assert _codes([row], {"research/params/consumer.py": source}) == [
        param_usage.USAGE_CODE
    ]


def test_a_root_outside_the_consuming_set_is_not_a_reader() -> None:
    row = _probe(accessors=("seed",))
    source = "from research.params import seed\n\nvalue = seed()\n"
    assert _codes([row], {"docs/snippet.py": source}) == [param_usage.USAGE_CODE]


def test_a_docstring_mention_is_not_a_reader() -> None:
    row = _probe(accessors=("seed",))
    source = '"""Call seed() for the repository seed."""\n'
    assert _codes([row], {"research/consumer.py": source}) == [param_usage.USAGE_CODE]


def test_an_undeclared_accessor_is_a_finding() -> None:
    row = _probe(accessors=("not_a_function",))
    findings = param_usage.usage_findings(texts={}, rows=[row])
    assert [finding.code for finding in findings] == [param_usage.USAGE_CODE] * 2
    assert any("declared accessor" in finding.message for finding in findings)


def test_a_declared_implementation_must_compare_the_default() -> None:
    row = _probe(default="fast", kind="str", implementations=("research/impl.py",))
    source = 'value = "slow" if mode == "slow" else "fast_v1"\n'
    findings = param_usage.usage_findings(
        texts={"research/impl.py": source}, rows=[row]
    )
    assert [finding.code for finding in findings] == [
        param_usage.USAGE_CODE,
        param_usage.COMPARISON_CODE,
    ]


def test_a_comparing_implementation_is_clean() -> None:
    row = _probe(default="fast", kind="str", implementations=("research/impl.py",))
    source = (
        "from research.params import str_param\n"
        "\nmode = str_param('probe_param')\n"
        "crit = 'fast' if mode == 'fast' else 'slow'\n"
    )
    assert (
        param_usage.usage_findings(texts={"research/impl.py": source}, rows=[row]) == []
    )


def test_a_missing_implementation_module_is_a_finding() -> None:
    row = _probe(default="fast", kind="str", implementations=("research/absent.py",))
    findings = param_usage.usage_findings(texts={}, rows=[row])
    assert param_usage.COMPARISON_CODE in [finding.code for finding in findings]


def test_the_live_rows_name_their_accessors_and_defaults() -> None:
    seed_row = param_checks.REGISTRY.by_name("seed")
    steps_row = param_checks.REGISTRY.by_name("steps")

    assert seed_row.env == "RESEARCH_SEED"
    assert seed_row.default == "0"
    assert seed_row.accessors == ("seed",)
    assert steps_row.env == "RESEARCH_STEPS"
    assert steps_row.default == "3"


def test_the_live_tree_compares_every_declared_default() -> None:
    live = [
        finding
        for finding in param_usage.usage_findings()
        if finding.code == param_usage.COMPARISON_CODE
    ]
    assert live == []
