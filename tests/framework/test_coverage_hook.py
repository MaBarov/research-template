"""Exercise coverage enforcement through a real Git commit and pre-commit hook."""

from __future__ import annotations

from pathlib import Path

from tests.framework.scratch import hook_fixtures

# The coverage step runs these two gate scripts; both must be executable in the
# scratch checkout for the hook under test to reach the coverage decision.
CHECKED_GATES = (
    "framework/gates/checks/check_test_mirror.py",
    "framework/gates/check_coverage.py",
)


def hook_checkout(root: Path) -> dict[str, str]:
    """Build a scratch checkout whose pre-commit hook is the repository's."""
    return hook_fixtures.hook_checkout(root, chmod=CHECKED_GATES)


def stage_uncleared_source(root: Path, env: dict[str, str]) -> None:
    source = root / "research/probe/value.py"
    mirror = root / "tests/research/probe/test_value.py"
    source.parent.mkdir(parents=True)
    mirror.parent.mkdir(parents=True)
    source.write_text("def value():\n    return 7\n", encoding="utf-8")
    mirror.write_text(
        "from research.probe.value import value\n\ndef test_value():\n    assert value() == 7\n",
        encoding="utf-8",
    )
    result = hook_fixtures.run_git(root, env, "add", "research", "tests")
    assert result.returncode == 0, result.stderr


def test_real_commit_refuses_source_without_coverage_clearance(tmp_path: Path) -> None:
    env = hook_checkout(tmp_path)
    (tmp_path / "control.txt").write_text("control\n", encoding="utf-8")
    assert hook_fixtures.run_git(tmp_path, env, "add", "control.txt").returncode == 0
    control = hook_fixtures.run_git(tmp_path, env, "commit", "-qm", "ordinary change")
    assert control.returncode == 0, control.stdout + control.stderr
    before = hook_fixtures.run_git(tmp_path, env, "rev-parse", "HEAD").stdout
    stage_uncleared_source(tmp_path, env)
    rejected = hook_fixtures.run_git(tmp_path, env, "commit", "-qm", "uncleared source")
    assert rejected.returncode != 0
    assert "staged research sources lack cleared coverage evidence" in (
        rejected.stdout + rejected.stderr
    ), rejected.stdout + rejected.stderr
    assert hook_fixtures.run_git(tmp_path, env, "rev-parse", "HEAD").stdout == before


def test_skip_githooks_env_var_no_longer_bypasses_the_hook(tmp_path: Path) -> None:
    """SKIP_GITHOOKS is inert: the bypass was removed, so the gate still blocks."""
    env = hook_checkout(tmp_path)
    env["SKIP_GITHOOKS"] = "1"
    stage_uncleared_source(tmp_path, env)
    rejected = hook_fixtures.run_git(
        tmp_path, env, "commit", "-qm", "uncleared source with bypass env"
    )
    assert rejected.returncode != 0
    assert "staged research sources lack cleared coverage evidence" in (
        rejected.stdout + rejected.stderr
    ), rejected.stdout + rejected.stderr
