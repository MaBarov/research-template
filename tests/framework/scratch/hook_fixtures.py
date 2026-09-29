"""Scratch-checkout fixtures shared by the framework hook tests.

The pre-commit hook is only exercised honestly against a real Git commit in a
real checkout, so each hook test builds one: a copy of ``framework/`` committed
with ``core.hooksPath`` pointing at the copied hook.

Invariants & Expected State:
    - ``hook_checkout`` drops this repository's gate evidence before the
      baseline commit, so a scratch tree never inherits a clearance record.
    - The hook under test is always the copied repository hook, never a stub,
      and it is marked executable only after the baseline commit.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from tests.framework.scratch import registry_fixtures

REPO = Path(__file__).resolve().parents[3]
DEFAULT_DROP = ("framework/coverage_evidence.json",)
HOOK = "framework/hooks/pre-commit"


def run_git(
    root: Path, env: dict[str, str], *args: str
) -> subprocess.CompletedProcess[str]:
    """Run one Git command inside the scratch repository."""

    return subprocess.run(
        ["git", *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def hook_env(root: Path) -> dict[str, str]:
    """Return the environment the hook runs under in the scratch checkout."""

    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        PATH=f"{Path(sys.executable).parent}:{env['PATH']}", PYTHONPATH=str(root)
    )
    return env


def commit_baseline(root: Path, env: dict[str, str]) -> None:
    """Commit the scratch tree and point ``core.hooksPath`` at the framework hooks."""

    for args in (
        ("init", "-q"),
        ("config", "user.email", "hook@test.invalid"),
        ("config", "user.name", "Hook test"),
        ("add", "."),
        ("commit", "-qm", "baseline"),
        ("config", "core.hooksPath", "framework/hooks"),
    ):
        result = run_git(root, env, *args)
        assert result.returncode == 0, result.stdout + result.stderr


def hook_checkout(
    root: Path,
    *,
    drop: Iterable[str] = DEFAULT_DROP,
    chmod: Iterable[str] = (),
    copy: Iterable[str] = (),
    registry: bool = False,
) -> dict[str, str]:
    """Build a committed scratch checkout whose ``pre-commit`` hook is the repo's."""

    shutil.copytree(
        REPO / "framework",
        root / "framework",
        ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"),
    )
    for relative in drop:
        (root / relative).unlink(missing_ok=True)
    (root / "framework/test_mirror_aliases.json").write_text("{}\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    for relative in copy:
        shutil.copy2(REPO / relative, root / relative)
    if registry:
        registry_fixtures.install_registry(root)
    env = hook_env(root)
    commit_baseline(root, env)
    for relative in (*chmod, HOOK):
        (root / relative).chmod(0o755)
    return env
