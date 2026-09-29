#!/usr/bin/env python3
"""One-command bootstrap: floor interpreter, venv, toolchain, hooks, example suite.

Usage:
  python scripts/setup/bootstrap.py [--dry-run] [--interpreter PATH]
                                    [--skip-install] [--skip-suite]

Steps, in order:
  1. resolve the floor interpreter: ``--interpreter``, else an existing
     ``.venv``, else ``python3.13`` … ``python3`` on ``PATH``;
  2. create the checkout venv with it when the venv is absent;
  3. install the project and its dev extra (``pip install -e ".[dev]"``);
  4. install the git hooks (``scripts/setup/setup_framework.py``);
  5. verify the wiring (``scripts/setup/check_framework_wiring.py``);
  6. run the example suite (``python -m pytest tests -q``).

Invariants & Expected State:
    - The floor is read from ``framework/harness.py``; an interpreter below it
      is refused before anything is created.
    - An existing venv at or above the floor is reused, never recreated, so a
      second run is idempotent.
    - ``--dry-run`` prints the exact commands and creates nothing.
    - Steps run in order and the first failure stops the run: a half-built
      environment is never reported as ready.
    - Expected state after a successful run: the checkout venv holds the dev
      extra, the hooks are active, the wiring check passes and ``tests/`` is
      green.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework import harness

CANDIDATES = harness.INTERPRETER_CANDIDATES
HOOKS_SCRIPT = "scripts/setup/setup_framework.py"
WIRING_SCRIPT = "scripts/setup/check_framework_wiring.py"
DEV_EXTRA = ".[dev]"
# One bound for every step: pip resolves against the network, so the ceiling has
# to fit a cold install while still refusing to hang a bootstrap forever.
STEP_TIMEOUT_S = 1800


def at_floor(interpreter: str) -> bool:
    """Return whether ``interpreter`` runs and meets the harness floor."""

    version = harness._interpreter_version(interpreter)
    if not version:
        return False
    return harness._floor_tuple(version) >= harness._floor_tuple(harness.PYTHON_FLOOR)


def pick_interpreter(explicit: str | None) -> str:
    """Return the interpreter to build the venv with, or fail with the floor message."""

    venv_python = Path(harness.venv()) / "bin" / "python"
    for candidate in (explicit, str(venv_python)):
        if candidate and Path(candidate).is_file() and at_floor(candidate):
            return candidate
    for name in CANDIDATES:
        found = shutil.which(name)
        if found and at_floor(found):
            return found
    raise SystemExit(
        f"FAIL: no Python >= {harness.PYTHON_FLOOR} found "
        f"({'tried ' + ', '.join(CANDIDATES)}): install one or pass --interpreter."
    )


def build_steps(
    interpreter: str, skip_install: bool, skip_suite: bool
) -> list[list[str]]:
    """Return the commands to run, in order, for the resolved interpreter."""

    venv_python = str(Path(harness.venv()) / "bin" / "python")
    steps: list[list[str]] = []
    if not Path(venv_python).is_file():
        steps.append([interpreter, "-m", "venv", harness.venv()])
    if not skip_install:
        steps.append([venv_python, "-m", "pip", "install", "--upgrade", "pip"])
        steps.append([venv_python, "-m", "pip", "install", "-e", DEV_EXTRA])
    steps.append([venv_python, str(REPO / HOOKS_SCRIPT)])
    steps.append([venv_python, str(REPO / WIRING_SCRIPT)])
    if not skip_suite:
        steps.append([venv_python, "-m", "pytest", "tests", "-q"])
    return steps


def run_step(step: list[str], dry_run: bool) -> None:
    """Print and run one step, stopping the bootstrap when it fails or overruns."""

    print(f"[bootstrap] $ {' '.join(step)}", flush=True)
    if dry_run:
        return
    try:
        done = subprocess.run(step, cwd=REPO, check=False, timeout=STEP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise SystemExit(
            f"FAIL: step exceeded {STEP_TIMEOUT_S}s: {' '.join(step)}"
        ) from None
    if done.returncode:
        raise SystemExit(f"FAIL: step exited {done.returncode}: {' '.join(step)}")


def main(argv: list[str] | None = None) -> int:
    """Resolve the interpreter, run every step in order, report the next action."""

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print the plan only")
    parser.add_argument(
        "--interpreter", help="floor interpreter to build the venv with"
    )
    parser.add_argument("--skip-install", action="store_true", help="do not touch pip")
    parser.add_argument("--skip-suite", action="store_true", help="do not run pytest")
    args = parser.parse_args(argv)

    interpreter = pick_interpreter(args.interpreter)
    print(f"[bootstrap] repo {REPO} · floor {harness.PYTHON_FLOOR} · {interpreter}")
    for step in build_steps(interpreter, args.skip_install, args.skip_suite):
        run_step(step, args.dry_run)
    if args.dry_run:
        print("[bootstrap] DRY_RUN: nothing was created")
        return 0
    print("[bootstrap] READY: hooks active; next: read ADOPTING.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
