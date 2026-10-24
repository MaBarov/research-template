"""Exercise the staged-oracle enforcement through a real Git commit and hook.

Thumbnail: Pins that a staged test file with no independent oracle blocks the commit.

Invariants & Expected State:
    - The hook under test is the copied repository hook, run in a scratch
      checkout by ``hook_fixtures``, so the assertion is about the real commit
      path and not about a helper called directly.
    - A staged test file whose only assertion is a tautology (``assert True``)
      is removal theater: the commit is refused with HNS068/HNS070 named.
    - A staged test file asserting an independent expectation commits cleanly,
      so the gate is not a blanket refusal of staged test changes.
"""

from __future__ import annotations

from pathlib import Path

from tests.framework.scratch import hook_fixtures

MIRROR = "tests/research/probe/tests_plan.py"
SELF_TEST = "framework/tests/probe/test_demo.py"


def hook_checkout(root: Path) -> dict[str, str]:
    """Build a scratch checkout whose pre-commit hook is the repository hook."""

    return hook_fixtures.hook_checkout(root, registry=True)


def stage_mirror(
    root: Path, env: dict[str, str], source: str, rel: str = MIRROR
) -> None:
    """Write ``source`` to ``rel`` and stage it."""

    mirror = root / rel
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(source, encoding="utf-8")
    assert hook_fixtures.run_git(root, env, "add", rel).returncode == 0


def test_tautological_staged_test_file_blocks_the_commit(tmp_path: Path) -> None:
    """A staged test file with no behavioral assertion is refused."""

    env = hook_checkout(tmp_path)
    stage_mirror(tmp_path, env, "def test_plan() -> None:\n    assert True\n")
    refused = hook_fixtures.run_git(
        tmp_path, env, "commit", "-qm", "assertion-free mirror"
    )
    output = refused.stdout + refused.stderr
    assert refused.returncode != 0, output
    assert "HNS068" in output, output


def test_tautological_harness_test_blocks_too(tmp_path: Path) -> None:
    """The harness's own suite is held to the same oracle rule as a mirror."""

    env = hook_checkout(tmp_path)
    stage_mirror(
        tmp_path,
        env,
        "def test_demo(items) -> None:\n    assert len(items) >= 0\n",
        SELF_TEST,
    )
    refused = hook_fixtures.run_git(
        tmp_path, env, "commit", "-qm", "tautological harness test"
    )
    output = refused.stdout + refused.stderr
    assert refused.returncode != 0, output
    assert "HNS070" in output, output


def test_behavioral_staged_test_file_commits(tmp_path: Path) -> None:
    """A staged test file with an independent expectation commits cleanly."""

    env = hook_checkout(tmp_path)
    stage_mirror(
        tmp_path, env, "def test_plan() -> None:\n    assert len([1, 2]) == 2\n"
    )
    accepted = hook_fixtures.run_git(
        tmp_path, env, "commit", "-qm", "behavioral mirror"
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
