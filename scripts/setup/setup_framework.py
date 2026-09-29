#!/usr/bin/env python3
"""Install the repository framework's Git hooks in this worktree.

Invariants & Expected State:
    - Idempotent: pointing ``core.hooksPath`` at the framework hooks twice is the
      same as doing it once; the checks run before any write.
    - Worktree Scoped: it refuses outside a Git worktree and when the hooks
      directory is absent, so a stray checkout is never misconfigured.
    - Bounded: the ``git config`` call is bounded so a wedged git cannot hang the
      installer.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "framework" / "hooks"
CONFIG_TIMEOUT_SECONDS = 60


def main() -> int:
    if not (ROOT / ".git").exists():
        print(f"not a Git worktree: {ROOT}", file=sys.stderr)
        return 2
    if not HOOKS.is_dir():
        print(f"missing framework hooks directory: {HOOKS}", file=sys.stderr)
        return 2

    try:
        result = subprocess.run(
            ["git", "config", "core.hooksPath", "framework/hooks"],
            cwd=ROOT,
            check=False,
            timeout=CONFIG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print("git config timed out", file=sys.stderr)
        return 1
    if result.returncode:
        return result.returncode
    print("Installed framework hooks: core.hooksPath=framework/hooks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
