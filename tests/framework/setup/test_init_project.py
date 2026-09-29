"""End-to-end tests for the template adoption script, run on a copied checkout."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = ("scripts", "setup", "init_project.py")
OLD_SLUG, NEW_SLUG = "research", "myproj"
OLD_PREFIX, NEW_PREFIX = "RESEARCH", "MYPROJ"
OLD_CODE, NEW_CODE = "HNS", "XYZ"
TIMEOUT_SECONDS = 600
IGNORED_DIRS = frozenset(
    {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "cache",
        "checkpoints",
        "logs",
        "mlruns",
        "models",
        "mutants",
        "results",
        "third_party",
    }
)
TOKEN = re.compile(rf"{OLD_PREFIX}(?![A-Za-z])|{OLD_CODE}(?![A-Za-z])|tests/{OLD_SLUG}")


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one git command in ``root`` under a throwaway committer identity."""

    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A committed copy of this repository, so the script may rename it freely."""

    root = tmp_path / "demo"
    shutil.copytree(
        REPO, root, ignore=shutil.ignore_patterns(*IGNORED_DIRS), symlinks=True
    )
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "seed")
    return root


def init_project(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """Run the adoption script inside ``root`` with the new identity and ``extra`` flags."""

    argv = [
        sys.executable,
        str(root.joinpath(*SCRIPT)),
        "--slug",
        NEW_SLUG,
        "--prefix",
        NEW_PREFIX,
        "--code",
        NEW_CODE,
        *extra,
    ]
    return subprocess.run(
        argv,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )


def harness_value(root: Path, key: str) -> str:
    """Return one harness key as the renamed tree's own harness prints it."""

    done = subprocess.run(
        [sys.executable, "framework/harness.py", "--get", key],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    return done.stdout.strip()


def token_findings(root: Path) -> list[str]:
    """Every line outside the ignored trees that still carries an old-identity token."""

    findings: list[str] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS]
        for name in names:
            path = Path(current) / name
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if TOKEN.search(line):
                    findings.append(
                        f"{path.relative_to(root).as_posix()}:{number}: {line}"
                    )
    return findings


def test_refuses_a_dirty_worktree_and_an_occupied_target(checkout: Path) -> None:
    """Both preconditions are checked, and nothing is moved when either fails."""

    occupied = checkout / NEW_SLUG
    occupied.mkdir()
    refused = init_project(checkout)
    assert refused.returncode != 0
    assert "refusing to overwrite existing path" in refused.stderr
    assert (checkout / OLD_SLUG).is_dir()
    occupied.rmdir()

    (checkout / "scratch.txt").write_text("dirty\n", encoding="utf-8")
    dirty = init_project(checkout)
    assert dirty.returncode != 0
    assert "worktree is dirty" in dirty.stderr
    assert (checkout / OLD_SLUG).is_dir()
    assert not (checkout / NEW_SLUG).exists()


def test_dry_run_plans_without_touching_the_tree(checkout: Path) -> None:
    """A dry run prints the plan, including the files it would rewrite, and writes nothing."""

    harness_path = checkout / "framework" / "harness.py"
    before = harness_path.read_bytes()
    planned = init_project(checkout, "--dry-run")
    assert planned.returncode == 0, planned.stderr
    assert f"would git mv {OLD_SLUG} -> {NEW_SLUG}" in planned.stdout
    assert f"would git mv tests/{OLD_SLUG} -> tests/{NEW_SLUG}" in planned.stdout
    assert f"{OLD_SLUG}/params/registry.py" in planned.stdout
    assert "would rewrite pyproject.toml" in planned.stdout
    assert (checkout / OLD_SLUG).is_dir()
    assert not (checkout / NEW_SLUG).exists()
    assert (checkout / "tests" / OLD_SLUG).is_dir()
    assert harness_path.read_bytes() == before
    assert git(checkout, "status", "--porcelain").stdout == ""


def assert_identity_replaced(root: Path) -> None:
    """The renamed tree answers to the new identity and keeps no token of the old one."""

    assert harness_value(root, "slug") == NEW_SLUG
    assert harness_value(root, "env-prefix") == NEW_PREFIX
    assert harness_value(root, "code-prefix") == NEW_CODE
    registry = root / NEW_SLUG / "params" / "registry.py"
    assert NEW_PREFIX in registry.read_text(encoding="utf-8")
    assert NEW_SLUG in (root / "INDEX.md").read_text(encoding="utf-8")
    assert NEW_PREFIX in (root / ".agents" / "AGENTS.md").read_text(encoding="utf-8")
    assert token_findings(root) == []


def assert_example_suite_green(root: Path) -> None:
    """The renamed mirror tree's own suite still passes under its new name."""

    suite = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            f"tests/{NEW_SLUG}",
            "-q",
            "-p",
            "no:randomly",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert suite.returncode == 0, suite.stdout + suite.stderr


def test_adoption_renames_the_identity_and_keeps_the_example_suite_green(
    checkout: Path,
) -> None:
    """The real run moves both trees, rewrites every token, and the example suite passes."""

    adopted = init_project(checkout)
    assert adopted.returncode == 0, adopted.stderr
    assert "leftover scan: clean" in adopted.stdout
    assert (checkout / NEW_SLUG).is_dir()
    assert not (checkout / OLD_SLUG).exists()
    assert (checkout / "tests" / NEW_SLUG).is_dir()
    assert not (checkout / "tests" / OLD_SLUG).exists()
    assert_identity_replaced(checkout)
    assert_example_suite_green(checkout)
