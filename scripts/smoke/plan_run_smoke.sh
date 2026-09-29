#!/usr/bin/env bash
# Smoke driver for experiments/example_plan/plan_run.py.
#
# framework/gates/sbatch_gate.sh (step 4d) runs this before any submit; run it by
# hand after a change. It exercises the payload end to end on the login node with
# no accelerator, no dataset and no cluster, and exits 1 on the first deviation —
# a failing driver always blocks a submit, a missing one blocks a new job script.
#
# Invariants & Expected State:
# - Self-contained: resolves the repository from its own path and needs only a
#   Python interpreter (.venv/bin/python when present, else python3).
# - Writes a transcript to results/smoke/plan_run_smoke.log and leaves no state
#   outside results/.
# - Asserts the exact status needle and the receipt the payload claims to write.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENTRY="$REPO/experiments/example_plan/plan_run.py"
RECEIPT="$REPO/results/example_plan/smoke.json"
LOG="$REPO/results/smoke/plan_run_smoke.log"
NEEDLE="status=PLAN_READY steps=3 seed=0 total=3"

. "$REPO/scripts/smoke/lib/interpreter.sh"
PY="$(smoke_python "$REPO")" || exit 1

mkdir -p "$(dirname "$LOG")" "$(dirname "$RECEIPT")"
: > "$LOG"
rm -f "$RECEIPT"
cd "$REPO"
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"
export RESEARCH_SEED=0
export RESEARCH_STEPS=3

if ! "$PY" -u "$ENTRY" --help >>"$LOG" 2>&1; then
  echo "[smoke] FAIL: --help exited non-zero (see $LOG)" >&2
  exit 1
fi

if ! out=$("$PY" -u "$ENTRY" --run smoke 2>&1 | tee -a "$LOG"); then
  echo "[smoke] FAIL: the payload exited non-zero (see $LOG)" >&2
  exit 1
fi

case "$out" in
  *"$NEEDLE"*) ;;
  *)
    echo "[smoke] FAIL: expected '$NEEDLE' in stdout (see $LOG)" >&2
    exit 1
    ;;
esac

if [ ! -s "$RECEIPT" ]; then
  echo "[smoke] FAIL: no receipt written at $RECEIPT (see $LOG)" >&2
  exit 1
fi

echo "[smoke] PASS: plan_run_smoke"
