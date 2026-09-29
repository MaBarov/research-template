#!/usr/bin/env python3
"""Verify that the imported repository framework is wired into this worktree.

This is a target-workspace check, not a runtime dependency check.  The
framework remains a collection of repository gates and Git hooks rather than
an installed Python package.

Invariants & Expected State:
    - Static Only: the check compiles and parses the framework's entrypoints; it
      never imports or executes the gates it inspects.
    - Worktree Scoped: it reads the checkout this script lives in and asserts the
      framework hooks are active there; nothing outside the tree is consulted.
    - Bounded: every subprocess is bounded, so a wedged compiler or git cannot
      hang the check.
    - Fail Loud: an unreadable entrypoint or an inactive hooks path fails the run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK = ROOT / "framework"
SUBPROCESS_TIMEOUT_SECONDS = 60


def fail(message: str) -> None:
    print(f"[framework-wiring] FAIL: {message}", file=sys.stderr)


def _run(argv: list[str]) -> subprocess.CompletedProcess | None:
    """Run one bounded command; ``None`` when it exceeds the timeout."""
    try:
        return subprocess.run(
            argv,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None


def _compiles(path: Path) -> bool:
    result = _run([sys.executable, "-m", "py_compile", str(path)])
    if result is None:
        fail(f"compiling {path.relative_to(ROOT)} timed out")
        return False
    if result.returncode:
        fail(f"cannot compile {path.relative_to(ROOT)}: {result.stderr.strip()}")
        return False
    return True


def _parses(path: Path) -> bool:
    result = _run(["bash", "-n", str(path)])
    if result is None:
        fail(f"parsing {path.relative_to(ROOT)} timed out")
        return False
    if result.returncode:
        fail(f"cannot parse {path.relative_to(ROOT)}: {result.stderr.strip()}")
        return False
    return True


def check_entrypoints() -> bool:
    gate_files = sorted((FRAMEWORK / "gates").rglob("*.py"))
    hook_files = sorted((FRAMEWORK / "hooks").iterdir())
    shell_files = [path for path in hook_files if path.suffix in {"", ".sh"}]
    shell_files += sorted((FRAMEWORK / "gates").glob("*.sh"))

    ok = True
    for path in gate_files:
        if not _compiles(path):
            ok = False
    for path in shell_files:
        if not _parses(path):
            ok = False

    if ok:
        print(
            f"[framework-wiring] entrypoints: PASS ({len(gate_files)} Python gates, "
            f"{len(shell_files)} shell hooks/gates)"
        )
    return ok


def check_hooks() -> bool:
    result = _run(["git", "config", "--get", "core.hooksPath"])
    if result is None:
        fail("git config timed out while reading core.hooksPath")
        return False
    if result.stdout.strip() != "framework/hooks":
        fail("Git hooks are not active; run git config core.hooksPath framework/hooks")
        return False
    print("[framework-wiring] hooks: PASS (core.hooksPath=framework/hooks)")
    return True


def main() -> int:
    checks = (check_entrypoints(), check_hooks())
    if all(checks):
        print("[framework-wiring] PASS")
        return 0
    print("[framework-wiring] FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
