# Research Sub-Index: `experiments`

> [!NOTE]
> Sub-index for the `experiments` package hierarchy. Use the line ranges below to load specific sections directly into context.

**Repository Statistics**: 1 modules | 0 classes | 2 public functions.

## Table of Contents

- [`experiments/example_plan`](#package-experimentsexample-plan) (lines 14–22)

---

## Package `experiments/example_plan`

- [`experiments/example_plan/plan_run.py`](experiments/example_plan/plan_run.py) (68 lines)
  * *Module Purpose*: Cluster entry point for the worked example: build a plan, stamp a receipt.
  * [`receipt(plan: tuple[Step, ...], run: str) -> dict[str, object]`](experiments/example_plan/plan_run.py#L38-L47)
    * *Contract*: Return the receipt payload of one finished plan.
  * [`main(argv: Sequence[str] | None) -> int`](experiments/example_plan/plan_run.py#L50-L64)
    * *Contract*: Write the run receipt, print the status line, return the exit code.

