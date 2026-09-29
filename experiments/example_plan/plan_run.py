"""Cluster entry point for the worked example: build a plan, stamp a receipt.

Invariants & Expected State:
- CPU-only and dependency-free: the smoke driver runs it on a login node with no
  accelerator and no dataset, and the submit gate runs that driver before it
  releases the job.
- Tunables arrive through ``research.params`` only, so replaying a run needs its
  command line and its environment, never a second default in this file.
- Exactly one ``status=`` line per run and one receipt per run name; the smoke
  driver asserts the exact needle, so a wording change fails the gate.
- Exit codes: 0 = receipt written, 2 = unusable invocation (no run name).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from research.params import ambient, seed
from research.probe.plan import Step, build_plan

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "example_plan"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Return the parsed arguments of one run invocation."""

    parser = argparse.ArgumentParser(description="Build a plan and stamp a receipt.")
    parser.add_argument("--run", help="run name; the receipt is written to <run>.json")
    parser.add_argument(
        "--steps", type=int, default=None, help="override the step count"
    )
    return parser.parse_args(argv)


def receipt(plan: tuple[Step, ...], run: str) -> dict[str, object]:
    """Return the receipt payload of one finished plan."""

    return {
        "run": run,
        "seed": seed(),
        "steps_env": ambient("steps"),
        "steps": len(plan),
        "total": sum(step.weight for step in plan),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Write the run receipt, print the status line, return the exit code."""

    args = _parse_args(argv)
    if not args.run:
        print("status=FAIL reason=missing_run_name")
        return 2
    plan = build_plan(args.steps)
    payload = receipt(plan, args.run)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"{args.run}.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"status=PLAN_READY steps={len(plan)} seed={payload['seed']} total={payload['total']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
