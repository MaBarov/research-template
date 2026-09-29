#!/usr/bin/env bash
# Adjudication gate — the documentation chain is MECHANICALLY enforced here.
# A verdict for <run> is only accepted when ALL of these pass (hard, exit 1):
#   1. verify_replay --strict      manifest re-derives at the live HEAD
#   2. record_run_manifest         re-record with --from-manifest + --metrics
#   3. dvc exp save -n <run>       registry snapshot
#   4. log_mlflow_run              queryable MLflow run (only with --mlflow)
#   5. check_documentation         manifest + metrics + DVC exp exist
# Usage:
#   bash framework/gates/adjudication_gate.sh <run> [--metrics K=V ...] [--mlflow]
# No doc chain = no adjudication. Never hand-edit results after this passes.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# The interpreter and dvc come from the harness, which honours RESEARCH_VENV /
# RESEARCH_PYTHON and the per-cluster venv map.
HARNESS="$REPO/framework/harness.py"
BOOTSTRAP_PY="${RESEARCH_PYTHON:-python3}"
PY="$("$BOOTSTRAP_PY" "$HARNESS" --get python)"
DVC="$("$BOOTSTRAP_PY" "$HARNESS" --get dvc-bin)"
RUN="${1:-}"
[ -n "$RUN" ] || { echo "usage: adjudication_gate.sh <run> [--metrics K=V ...] [--mlflow]" >&2; exit 2; }
shift
METRICS=()
MLFLOW=0
for a in "$@"; do
  case "$a" in
    --mlflow) MLFLOW=1 ;;
    --metrics) ;;
    *) METRICS+=("$a") ;;
  esac
done

MANIFEST="$REPO/results/manifests/$RUN.json"
[ -f "$MANIFEST" ] || { echo "[adjudication] FAIL: no manifest $MANIFEST — submit via sbatch_gate.sh first" >&2; exit 1; }

step() { echo "[adjudication] $*" >&2; }
METRICS_ARGS=()
for m in "${METRICS[@]}"; do METRICS_ARGS+=(--metrics "$m"); done

# 1. replay verification (hashes must match the live tree)
step "verify_replay --strict"
"$PY" "$REPO/framework/gates/provenance/verify_replay.py" "$MANIFEST" --strict || {
  echo "[adjudication] FAIL: manifest drift — fix or discard before adjudicating" >&2; exit 1; }

# 2. re-record with metrics (keeps the original pins; adds --metrics)
if [ "${#METRICS[@]}" -gt 0 ]; then
  step "record_run_manifest --from-manifest --metrics"
  "$PY" "$REPO/framework/gates/provenance/record_run_manifest.py" --run "$RUN" \
    --from-manifest "$MANIFEST" "${METRICS_ARGS[@]}" >/dev/null || {
    echo "[adjudication] FAIL: record --metrics" >&2; exit 1; }
fi

# 3. DVC experiment snapshot (clean index required — see decision note)
step "dvc exp save -n $RUN"
if ! command -v "$DVC" >/dev/null 2>&1 && [ ! -x "$DVC" ]; then
  echo "[adjudication] FAIL: dvc not found (resolved to '$DVC') — install it in the project" >&2
  echo "[adjudication]       venv or set the harness override (\`python framework/harness.py --get dvc-bin\`)." >&2
  exit 1
fi
if ! "$DVC" exp save -n "$RUN" -f >/dev/null 2>&1; then
  echo "[adjudication] FAIL: dvc exp save -n $RUN (needs a dvc-initialised repo and a clean index)" >&2
  exit 1
fi

# 4. MLflow run (only when requested)
if [ "$MLFLOW" = "1" ]; then
  step "log_mlflow_run"
  "$PY" "$REPO/framework/gates/provenance/log_mlflow_run.py" --manifest "$MANIFEST" \
    "${METRICS_ARGS[@]}" >/dev/null || {
    echo "[adjudication] FAIL: log_mlflow_run" >&2; exit 1; }
fi

# 5. documentation gate (hard)
step "check_documentation${MLFLOW:+ --mlflow}"
"$PY" "$REPO/framework/gates/check_documentation.py" --run "$RUN" \
  $([ "$MLFLOW" = "1" ] && echo --mlflow) >/dev/null || {
  echo "[adjudication] FAIL: documentation gate" >&2; exit 1; }

echo "[adjudication] PASS: $RUN fully documented — verdict may be accepted"
echo "[adjudication] evidence: $REPO/results/manifests/$RUN.json + dvc exp $RUN"