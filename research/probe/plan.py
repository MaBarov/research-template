"""Worked example of a production module: a deterministic plan builder.

Invariants & Expected State:
- Every tunable arrives through ``research.params``: the step count through the
  generic integer accessor and the seed through its registered accessor, so the
  usage gate (HNS042) sees both registry rows as read.
- ``build_plan`` is pure: given the same ``steps`` and the same registered seed it
  returns the same ordered tuple, and ``steps=0`` yields an empty plan.
- ``main`` prints exactly one ``status=PLAN_READY`` line per run. The smoke driver
  asserts that needle, so a wording change fails the submit gate rather than a
  downstream reader.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass

from research.params import int_param, seed

_WEIGHTS = 7


@dataclass(frozen=True)
class Step:
    """One planned step: its index and the seed-derived weight."""

    index: int
    weight: int


def build_plan(steps: int | None = None) -> tuple[Step, ...]:
    """Return the plan for ``steps``, defaulting to the registered step count."""

    count = int_param("steps") if steps is None else steps
    base = seed()
    return tuple(Step(index, (base + index) % _WEIGHTS) for index in range(count))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Return the parsed arguments of one plan invocation.

    Both statements carry ``# pragma: no mutate``: the only content a mutation
    can change is CLI description/help text, and the parser's behaviour (no
    default, ``--steps`` override, ``--help``) is asserted elsewhere, so a text
    mutation is equivalent by construction.
    """

    parser = argparse.ArgumentParser(description="Build the plan.")  # pragma: no mutate
    parser.add_argument("--steps", type=int, help="override")  # pragma: no mutate
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the plan's status line and return the process exit code."""

    args = _parse_args(argv)
    plan = build_plan(args.steps)
    total = sum(step.weight for step in plan)
    print(f"status=PLAN_READY steps={len(plan)} seed={seed()} total={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
