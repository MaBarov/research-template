#!/usr/bin/env bash
# Worked example of a submit-ready job: the plan builder of the harness example.
#
# Copy `slurm/template.sbatch` for a new job, keep the provenance guard and the
# status stamp verbatim (framework/gates/check_sbatch_contract.sh is the contract),
# and name the payload under experiments/ so the submit gate can find its smoke
# driver: experiments/example_plan/plan_run.py -> scripts/smoke/plan_run_smoke.sh.
#
#   bash framework/gates/sbatch_gate.sh slurm/example_plan.sbatch --dry-run
#   bash framework/gates/sbatch_gate.sh slurm/example_plan.sbatch <run-name>
#SBATCH --job-name=research_example
#SBATCH --partition=all
#SBATCH --gres=gpu:0
#SBATCH -c 2
#SBATCH --mem=4G
#SBATCH --time=00:10:00
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
echo "status=RESEARCH_EXAMPLE_START job=${SLURM_JOB_ID:-local} start=$(date -Is) commit=$COMMIT tree_state=$TREE_STATE dirty_status_sha256=$DIRTY_SHA256"
# ---------------------------------------------------------------------------

# --- experiment body --------------------------------------------------------
# The run name defaults to the job id so a rerun never overwrites a receipt.
RUN_NAME=${1:-example-${SLURM_JOB_ID:-local}}
"$PYTHON" -u experiments/example_plan/plan_run.py --run "$RUN_NAME"
# ---------------------------------------------------------------------------

echo "status=RESEARCH_EXAMPLE_DONE run=$RUN_NAME"
