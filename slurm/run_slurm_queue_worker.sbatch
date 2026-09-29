#!/usr/bin/env bash
# Lane worker for the draining queue: one allocation drains the shared queue.
#
# Submitted by `python -m scripts.slurm_queue.cli enqueue` — the queue passes the
# lane id as the single positional argument and owns every other directive
# (--job-name, --output, --time, --signal, --partition/--gres), so this file must
# not restate them. It is not a payload: model.py refuses to enqueue it.
#
# Smoke the channel without Slurm:
#   python -m scripts.slurm_queue.cli worker --smoke
#SBATCH --job-name=research_queue_worker
#SBATCH --partition=all
#SBATCH --gres=gpu:0
#SBATCH -c 2
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --output=slurm/slurm_%x_%j.log

set -euo pipefail
ROOT=${RESEARCH_ROOT:?export RESEARCH_ROOT to the deployment checkout}
if [[ -z ${RESEARCH_PYTHON:-} && -f "$ROOT/framework/harness.py" ]]; then
  RESEARCH_PYTHON=$(python3 "$ROOT/framework/harness.py" --get python 2>/dev/null || true)
fi
PYTHON=${RESEARCH_PYTHON:-python3}
export PYTHONUNBUFFERED=1
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$ROOT"

# --- provenance guard (keep verbatim) --------------------------------------
# A caller-supplied RESEARCH_COMMIT is a claim about which tree this run imports, so
# it may not disagree with the tree it is actually running in. CLAIMED keeps that
# claim apart from the value the .research_commit fallback supplies: a stale stamp
# file must not be able to mask a pin, and a pin must not be able to vouch for a
# tree it does not describe (RESEARCH_ROOT is required and is exported by the submit
# gate, so this guard always evaluates the tree the job will import).
CLAIMED=${RESEARCH_COMMIT:-}
if [[ -z $CLAIMED && -r "$ROOT/.research_commit" ]]; then
  RESEARCH_COMMIT=$(cat "$ROOT/.research_commit")
fi
export RESEARCH_COMMIT
if COMMIT=$(git rev-parse HEAD 2>/dev/null); then
  if ! DIRTY_STATUS=$(git status --porcelain 2>/dev/null); then
    echo "REFUSING RUN: unable to record git tree state" >&2
    exit 90
  fi
  DIRTY_SHA256=$(printf '%s\n' "$DIRTY_STATUS" | sha256sum | awk '{print $1}')
  if [[ -n "$DIRTY_STATUS" ]]; then
    echo "REFUSING RUN: dirty tree; commit the work before submitting" >&2
    printf '%s\n' "$DIRTY_STATUS" >&2
    exit 90
  else
    TREE_STATE=clean
  fi
  if [[ -n $CLAIMED && $CLAIMED != "$COMMIT" ]]; then
    echo "REFUSING RUN: RESEARCH_COMMIT=$CLAIMED disagrees with the checkout at $COMMIT" >&2
    exit 90
  fi
else
  if [[ -z ${RESEARCH_COMMIT:-} ]]; then
    echo "REFUSING RUN: git commit unavailable and RESEARCH_COMMIT was not provided" >&2
    exit 90
  fi
  if [[ -n $CLAIMED && -r "$ROOT/.research_commit" && $CLAIMED != "$(cat "$ROOT/.research_commit")" ]]; then
    echo "REFUSING RUN: RESEARCH_COMMIT=$CLAIMED disagrees with $ROOT/.research_commit=$(cat "$ROOT/.research_commit")" >&2
    exit 90
  fi
  COMMIT=$RESEARCH_COMMIT
  DIRTY_SHA256=untracked-worktree
  TREE_STATE=external-commit
fi
echo "status=RESEARCH_QUEUE_WORKER_START job=${SLURM_JOB_ID:-local} lane=${1:-none} start=$(date -Is) commit=$COMMIT tree_state=$TREE_STATE dirty_status_sha256=$DIRTY_SHA256"
# ---------------------------------------------------------------------------

LANE=${1:?usage: run_slurm_queue_worker.sbatch <lane-id>}
WORKER="$ROOT/scripts/slurm_queue/cli.py"
if [ ! -f "$ROOT/scripts/slurm_queue/worker/__init__.py" ]; then
  echo "REFUSING RUN: $ROOT/scripts/slurm_queue/worker/__init__.py is missing (wrong root or a moved package)" >&2
  exit 90
fi
exec "$PYTHON" -u "$WORKER" worker --lane "$LANE" --repo "$ROOT"
