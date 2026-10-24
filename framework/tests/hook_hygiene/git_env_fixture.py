"""Shared environment sanitation for scratch-git test fixtures.

A test that runs ``git`` with ``cwd=<scratch repo>`` does not choose the
repository while ``GIT_DIR`` is set: ``GIT_DIR``/``GIT_INDEX_FILE`` inherited
from a hook make the fixture's ``init``/``add``/``commit`` land on the caller's
repository instead. Every scratch-git helper in the suite runs through
``run_git`` so the selectors are removed from the child environment, even when
the helper is invoked outside pytest (where the root ``conftest.py`` pop does
not apply).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def clean_env() -> dict[str, str]:
    """Return the environment with every git repository selector removed."""
    return {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }


def run_git(
    repo: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run one git command in `repo` with repository selectors removed."""
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        env=clean_env(),
        check=check,
        capture_output=True,
        text=True,
    )
