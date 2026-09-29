"""Exercise the parameter-unification gate through a real Git commit and hook."""

from __future__ import annotations

from pathlib import Path

from research.params import by_name
from tests.framework.scratch import hook_fixtures

# The violation sample comes from the registry's own alias list: writing the
# superseded name here would itself be a HNS038 restatement of it.
_ALIAS = by_name("seed").aliases[0]
ALIAS_VIOLATION = f"""import os

MODEL = os.environ.get("{_ALIAS}", "native")
"""

CLEAN_SOURCE = """from research.params import str_param


def pick() -> str:
    return str_param("steps")
"""


def hook_checkout(root: Path) -> dict[str, str]:
    """Build a scratch checkout whose pre-commit hook is the parameter gate."""
    # The gate reads the canonical registry from disk, never through research's
    # package import path; the copied registry stays untracked so the coverage
    # gate has nothing to clear.
    return hook_fixtures.hook_checkout(root, registry=True)


def stage_source(root: Path, env: dict[str, str], body: str) -> None:
    """Stage one root-level probe module carrying ``body``."""

    (root / "probe_param.py").write_text(body, encoding="utf-8")
    result = hook_fixtures.run_git(root, env, "add", "probe_param.py")
    assert result.returncode == 0, result.stderr


def test_real_commit_refuses_a_superseded_env_alias(tmp_path: Path) -> None:
    env = hook_checkout(tmp_path)
    stage_source(tmp_path, env, ALIAS_VIOLATION)
    rejected = hook_fixtures.run_git(tmp_path, env, "commit", "-qm", "alias")
    output = rejected.stdout + rejected.stderr
    assert rejected.returncode != 0
    assert "HNS038" in output, output
    assert "parameter unification gate" in output, output


def test_real_commit_refuses_a_restated_default(tmp_path: Path) -> None:
    env = hook_checkout(tmp_path)
    stage_source(
        tmp_path, env, 'import os\n\nSEED = os.environ.get("RESEARCH_SEED", "2026")\n'
    )
    rejected = hook_fixtures.run_git(tmp_path, env, "commit", "-qm", "restated default")
    output = rejected.stdout + rejected.stderr
    assert rejected.returncode != 0
    assert "HNS039" in output, output


def test_no_environment_variable_downgrades_the_gate(tmp_path: Path) -> None:
    env = hook_checkout(tmp_path)
    stage_source(tmp_path, env, ALIAS_VIOLATION)
    env.update(
        SKIP_PARAM_GATE="1",
        RESEARCH_PARAM_GATE="0",
        PARAM_GATE_STRICT="0",
        RESEARCH_PARAM_ALLOWLIST="",
    )
    rejected = hook_fixtures.run_git(
        tmp_path, env, "commit", "-qm", "alias under bypass vars"
    )
    output = rejected.stdout + rejected.stderr
    assert rejected.returncode != 0
    assert "HNS038" in output, output


def test_real_commit_accepts_a_registry_reading_module(tmp_path: Path) -> None:
    env = hook_checkout(tmp_path)
    stage_source(tmp_path, env, CLEAN_SOURCE)
    accepted = hook_fixtures.run_git(
        tmp_path, env, "commit", "-qm", "registry reading module"
    )
    output = accepted.stdout + accepted.stderr
    assert accepted.returncode == 0, output
