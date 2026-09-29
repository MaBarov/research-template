#!/usr/bin/env bash
# Smoke driver for the queue worker (slurm/run_slurm_queue_worker.sbatch).
#
# framework/gates/sbatch_gate.sh (step 4d) runs this before any worker submit.
# It drives the queue's real code path — parse directives -> lane profile ->
# publish -> claim -> child execution -> terminal receipt -> empty drain — inside
# a temporary queue root, so runtime-class errors (attr/type/shape/state) die
# before a cluster submit. No Slurm, no GPU, no host resource flags.
#
# Invariants & Expected State:
# - Self-contained: resolves the repository from its own path and needs only a
#   Python interpreter (.venv/bin/python when present, else python3).
# - Writes a transcript to results/smoke/worker_smoke.log and touches no state
#   outside results/ and a temporary directory the queue smoke creates itself.
# - Fails on the first missing status needle or a non-succeeded receipt.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKER="$REPO/scripts/slurm_queue/cli.py"
LOG="$REPO/results/smoke/worker_smoke.log"

if [ ! -f "$WORKER" ]; then
  echo "[smoke] FAIL: scripts/slurm_queue/cli.py not found under $REPO — module moved or the sbatch reference is stale" >&2
  exit 1
fi

. "$REPO/scripts/smoke/lib/interpreter.sh"
PY="$(smoke_python "$REPO")" || exit 1

mkdir -p "$(dirname "$LOG")"
: > "$LOG"
cd "$REPO"
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

if ! "$PY" -u "$WORKER" --help >>"$LOG" 2>&1; then
  echo "[smoke] FAIL: cli.py --help exited non-zero (see $LOG)" >&2
  exit 1
fi

if ! OUT=$("$PY" -u "$WORKER" worker --smoke --repo "$REPO" 2>&1 | tee -a "$LOG"); then
  echo "[smoke] FAIL: the queue smoke exited non-zero (see $LOG)" >&2
  exit 1
fi

for needle in \
  RESEARCH_SLURM_QUEUE_SMOKE_START \
  RESEARCH_SLURM_QUEUE_ITEM_START \
  RESEARCH_SLURM_QUEUE_ITEM_DONE \
  RESEARCH_SLURM_QUEUE_WORKER_DONE \
  RESEARCH_SLURM_QUEUE_SMOKE_OK; do
  case "$OUT" in
    *"$needle"*) ;;
    *)
      echo "[smoke] FAIL: the queue smoke never reported $needle (see $LOG)" >&2
      exit 1
      ;;
  esac
done

case "$OUT" in
  *state=succeeded*) ;;
  *)
    echo "[smoke] FAIL: the queue smoke recorded no succeeded receipt (see $LOG)" >&2
    exit 1
    ;;
esac

echo "[smoke] PASS: worker_smoke (drain: publish -> claim -> execute -> receipt)"
