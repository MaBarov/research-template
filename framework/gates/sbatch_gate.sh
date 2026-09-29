#!/usr/bin/env bash
# Pre-submit gate wrapper for cluster jobs (strict by default).
# Usage:
#   bash framework/gates/sbatch_gate.sh slurm/<name>.sbatch [--strict] [--dry-run] [PAYLOAD-ARG ...]
#   The project interpreter is discovered through framework/harness.py
#   (honouring the RESEARCH_PYTHON / RESEARCH_VENV overrides).
#
# Everything after the script path that is not a gate flag is forwarded to the
# job script as its positional arguments (sbatch passes them through) and to the
# canary's derived copy. A script with a `<dose> <retain> <rounds> <label>`
# contract can only be gated this way; without it the submitter hand-rolls
# `sbatch`, loses the exporting recipe's `RESEARCH_ROOT`, and the job silently runs a
# different deploy root than the one it was written for.
#
# Behavior (default = strict: any failure aborts the submit):
#   1. dirty-tree refusal (same logic as slurm/template.sbatch)   -> block
#   2. provenance stamp present (status=...commit=$(git rev-parse)  -> block
#   3. resolved project interpreter is executable                     -> block
#   4. python framework/gates/checks/local_gate.py on associated .py files          -> block
#   5. sbatch --test-only validation when on a SLURM login node      -> block
#   6. actual submit (unless --dry-run), or - with RESEARCH_SBATCH_QUEUE=1 - publish
#      the payload into its resource lane and ensure one worker allocation
#      (scripts/slurm_queue/; cluster tag RESEARCH_QUEUE_CLUSTER, default from
#      framework/harness.py)
# SBATCH_GATE_STRICT=0 downgrades every blocking check to a warning; that is
# the only way past a failure and exists for emergencies and for hosts that are
# not the job target. --strict is accepted for compatibility (already default).
# DRY_RUN=1 or --dry-run skips the final submit.
# SBATCH_GATE_PREFLIGHT=1 runs steps 1-4d only and exits: that is the queue
# worker's claim-time re-gate of the exact version an item is about to execute,
# inside its allocation. The submit-moment steps (GPU canary, --test-only, run
# manifest, publish/submit) are skipped because the payload is not submitted from
# there and the worker already owns the allocation.
# All events append one JSON line to results/gate_log.jsonl.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$1"
# Strict by default: every check below aborts the submit unless the operator
# explicitly downgrades with SBATCH_GATE_STRICT=0 (emergency / non-target host).
# The value is binary: anything other than 0 or 1 aborts before any check runs.
STRICT="${SBATCH_GATE_STRICT:-1}"
# Strictness is a binary contract: anything other than 0 or 1 would fall through
# to the advisory branch and silently weaken every check below, so it aborts here.
case "$STRICT" in
  0 | 1) ;;
  *)
    echo "[sbatch_gate] FAIL(strict): SBATCH_GATE_STRICT must be 0 or 1, got '$STRICT'" >&2
    exit 2
    ;;
esac
DRY_RUN="${DRY_RUN:-0}"
PREFLIGHT="${SBATCH_GATE_PREFLIGHT:-0}"
GATE_LOG="$REPO/results/gate_log.jsonl"
# A freshly staged deploy root has no results/ yet (it is gitignored), and the
# event log is the gate's own record, so create its directory before the first
# append instead of losing every event to a failed redirect.
mkdir -p "$(dirname "$GATE_LOG")" 2>/dev/null || true
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
AGENT_ID="${OMP_SESSION_ID:-unknown}"
FAILURES=0

# A script already in HEAD is "legacy": missing smoke drivers are metered, not
# blocking (backlog). A NEW script must ship its driver before it can submit.
NEW_SCRIPT=0
if ! git -C "$REPO" cat-file -e "HEAD:$SCRIPT" 2>/dev/null; then
  NEW_SCRIPT=1
fi


log_event() {  # tool target gate result reason
  printf '{"ts":"%s","agent":"%s","tool":"sbatch_gate","target":"%s","gate":"%s","result":"%s","reason":"%s","commit":"%s"}\n' \
    "$TS" "$AGENT_ID" "$1" "$2" "$3" "$4" "$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)" >> "$GATE_LOG" 2>/dev/null || true
}

note() {  # gate name message  (metered, never blocks: legacy driver debt)
  echo "[sbatch_gate] NOTE($1): $2" >&2
  log_event "$SCRIPT" "$1" "note" "$2"
}

warn_or_fail() {  # gate name message
  local gate="$1"; local msg="$2"
  if [ "$STRICT" = "1" ]; then
    echo "[sbatch_gate] FAIL($gate): $msg" >&2
    log_event "$SCRIPT" "$gate" "block" "$msg"
    FAILURES=$((FAILURES+1))
  else
    echo "[sbatch_gate] WARN($gate): $msg (advisory: SBATCH_GATE_STRICT=0 downgrade)" >&2
    log_event "$SCRIPT" "$gate" "warn" "$msg"
  fi
}

if [ $# -lt 1 ]; then
  echo "usage: bash framework/gates/sbatch_gate.sh slurm/<name>.sbatch [--strict] [--dry-run] [PAYLOAD-ARG ...]" >&2
  exit 2
fi
# Everything after the script path that is not a gate flag is the job script's
# own payload (its positional arguments). Collecting it here is what makes the
# sanctioned submit path usable for arm scripts; an unknown flag is refused
# rather than swallowed, because arguments are now legal and silence would
# decide between "flag" and "payload" on the operator's behalf.
PAYLOAD=()
for arg in "${@:2}"; do
  case "$arg" in
    --strict) STRICT=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --*) echo "[sbatch_gate] unknown gate flag: $arg" >&2; exit 2 ;;
    *) PAYLOAD+=("$arg") ;;
  esac
done

if [ ! -f "$REPO/$SCRIPT" ]; then
  warn_or_fail "script-exists" "missing sbatch script: $REPO/$SCRIPT"
  echo "[sbatch_gate] ABORT: script not found" >&2
  exit 1
fi

# 1. dirty-tree — always blocks; every job script also refuses at runtime.
# No override exists (user ruling 2026-09-26): a run whose inputs are not in a
# commit has no identity to record, so the submit is refused rather than
# labelled. The rule is enforced on the scripts themselves by
# framework/gates/check_sbatch_contract.sh and the anti-pattern rule HNS035.
if [ -n "$(git -C "$REPO" status --porcelain 2>/dev/null)" ]; then
  warn_or_fail "dirty-tree" "working tree dirty — commit first; a dirty run has no provenance and no override exists"
else
  log_event "$SCRIPT" "dirty-tree" "pass" "clean"
fi

# 2. provenance contract (shared checker: dirty-tree refusal + commit
# resolution + status stamp; see framework/gates/check_sbatch_contract.sh)
if ! bash "$REPO/framework/gates/check_sbatch_contract.sh" "$REPO/$SCRIPT" 2>&1; then
  warn_or_fail "provenance-stamp" "sbatch provenance contract violated — copy the guard+stamp header from slurm/template.sbatch"
else
  log_event "$SCRIPT" "provenance-stamp" "pass" "contract satisfied"
fi

# 3. interpreter: resolve it once through framework/harness.py (which honours
#    RESEARCH_PYTHON, then the per-cluster/checkout venv, then its own running
#    interpreter) and use it for every helper gate below. A missing venv is a
#    note, never a failure, as long as the resolved interpreter is executable.
HARNESS="$REPO/framework/harness.py"
BOOTSTRAP_PY="${RESEARCH_PYTHON:-python3}"
if [ ! -f "$HARNESS" ]; then
  echo "[sbatch_gate] FAIL(interpreter): missing $HARNESS; cannot resolve an interpreter" >&2
  exit 2
fi
if ! PY="$("$BOOTSTRAP_PY" "$HARNESS" --get python 2>/dev/null)"; then
  echo "[sbatch_gate] FAIL(interpreter): $BOOTSTRAP_PY could not run $HARNESS --get python" >&2
  exit 2
fi
VENV="$("$BOOTSTRAP_PY" "$HARNESS" --get venv 2>/dev/null || true)"
DEFAULT_CLUSTER="$("$BOOTSTRAP_PY" "$HARNESS" --get default-cluster 2>/dev/null || true)"
if [ ! -x "$PY" ]; then
  warn_or_fail "interpreter" "resolved interpreter is not executable: $PY"
elif ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null; then
  warn_or_fail "interpreter" "resolved interpreter $PY is older than the declared floor (>= 3.11); set RESEARCH_PYTHON to a supported interpreter"
elif [ -n "$VENV" ] && [ "$PY" = "$VENV/bin/python" ]; then
  log_event "$SCRIPT" "interpreter" "pass" "venv=$PY"
else
  log_event "$SCRIPT" "interpreter" "pass" "override=$PY"
  if [ -n "$VENV" ] && [ ! -x "$VENV/bin/python" ]; then
    note "interpreter" "venv $VENV has no python; using $PY instead"
  fi
fi

# 4. run local gate on associated python files referenced in the script,
# PLUS the vendored/other python those files may execute (subprocess/import
# targets under third_party/) — "all code that might be run", not just the
# driver. Static reach is intentionally conservative (whole referenced
# vendored dirs); these block by default, so keep the reach conservative.
ASSOC_PY=$(grep -oE '(experiments|scripts)/[A-Za-z0-9_./-]+\.py' "$REPO/$SCRIPT" 2>/dev/null | sort -u || true)
ASSOC_ALL_PY="$ASSOC_PY"
for py in $ASSOC_PY; do
  vendored=$(grep -hoE 'third_party/[A-Za-z0-9_./-]+' "$REPO/$py" 2>/dev/null | sort -u || true)
  for v in $vendored; do
    if [ -d "$REPO/$v" ]; then
      ASSOC_ALL_PY="$ASSOC_ALL_PY $(find "$REPO/$v" -name '*.py' -type f 2>/dev/null | sed "s|$REPO/||")"
    elif [ -f "$REPO/$v" ]; then
      ASSOC_ALL_PY="$ASSOC_ALL_PY $v"
    fi
  done
done
ASSOC_ALL_PY=$(printf '%s\n' $ASSOC_ALL_PY | sort -u)
if [ -n "$ASSOC_ALL_PY" ]; then
  if ! "$PY" "$REPO/framework/gates/checks/local_gate.py" $ASSOC_ALL_PY 2>/dev/null; then
    warn_or_fail "local-gate" "local_gate failed on: $ASSOC_ALL_PY"
  else
    log_event "$SCRIPT" "local-gate" "pass" "ok"
  fi
fi
# 4b. contamination gate on prompt banks referenced by the script (guardrail #2)
ASSOC_BANKS=$(grep -oE 'experiments/[A-Za-z0-9_./-]+\.json' "$REPO/$SCRIPT" 2>/dev/null | sort -u || true)
if [ -n "$ASSOC_BANKS" ]; then
  if ! "$PY" "$REPO/framework/gates/checks/check_contamination.py" $ASSOC_BANKS --strict >/dev/null 2>&1; then
    warn_or_fail "contamination" "check_contamination failed on: $ASSOC_BANKS"
  else
    log_event "$SCRIPT" "contamination" "pass" "banks clean"
  fi
fi
# 4d. stub-smoke gate: run the suite's smoke driver BEFORE submit — catches
# runtime-class errors (attr/type/shape) the static gates cannot see. A FAILING
# driver always blocks. A MISSING driver blocks for NEW scripts (not in HEAD);
# for legacy scripts the backlog is metered with a NOTE instead. --dry-run skips.
if [ "$DRY_RUN" != "1" ]; then
  for sm in $ASSOC_PY; do
    base=$(basename "$sm" .py)
    if [ "$base" = "__init__" ]; then
      # A package entry point is its package: resolve the driver by directory.
      base=$(basename "$(dirname "$sm")")
    fi
    driver="$REPO/scripts/smoke/${base}_smoke.sh"
    if [ -f "$driver" ]; then
      if timeout 950 bash "$driver" >/dev/null 2>&1; then
        log_event "$SCRIPT" "stub-smoke" "pass" "$driver"
        echo "[sbatch_gate] stub-smoke PASS: $driver"
      else
        warn_or_fail "stub-smoke" "smoke driver FAILED: $driver (see results/smoke_*.log) — do not submit"
      fi
    elif [ "$NEW_SCRIPT" = "1" ]; then
      warn_or_fail "stub-smoke" "no smoke driver for $sm (new script) — write scripts/smoke/${base}_smoke.sh (one smoke driver per submit-ready payload)"
    else
      note "stub-smoke" "legacy script, no smoke driver for $sm — write scripts/smoke/${base}_smoke.sh"
    fi
  done
fi
# 4f. claim-time preflight mode (SBATCH_GATE_PREFLIGHT=1): the queue worker runs
# steps 1-4d against the exact version an item is about to execute, inside its
# allocation. Everything from here on belongs to the submit moment (GPU canary,
# --test-only, run manifest, publish/submit), which the worker does not do.
if [ "$PREFLIGHT" = "1" ]; then
  if [ "$STRICT" = "1" ] && [ "$FAILURES" -gt 0 ]; then
    echo "[sbatch_gate] PREFLIGHT BLOCK: $FAILURES failure(s) for $SCRIPT" >&2
    log_event "$SCRIPT" "preflight" "block" "$FAILURES failure(s)"
    exit 1
  fi
  echo "[sbatch_gate] PREFLIGHT PASS: $SCRIPT"
  log_event "$SCRIPT" "preflight" "pass" "claim-time re-gate"
  exit 0
fi
# 4e. GPU canary gate (GENERIC, applies to every script with a driver python
# invocation): derive a bounded copy of the real sbatch (timeout + canary
# directives) and run it on the real GPU class for CANARY_TIME seconds.
# Predicts device/OOM/capacity/missing-weight crashes BEFORE the real run —
# the class static gates and CPU stubs cannot see. N/A (no driver python /
# no sbatch on this host) is a pass; a crash is a block. CANARY=0 opts out;
# CANARY_TIME bounds driver work (default 600s). CANARY_SETUP_GRACE covers
# model/basis initialization before driver timeout; CANARY_METHOD injects a METHOD.
# Skipped in --dry-run.
if [ "$DRY_RUN" != "1" ] && [ "${CANARY:-1}" = "1" ]; then
  CANARY_T="${CANARY_TIME:-600}"
  CANARY_GRACE="${CANARY_SETUP_GRACE:-900}"
  CANARY_WAIT="$((CANARY_T + CANARY_GRACE + 60))"
  # A controller with accounting disabled answers `sacct` with nothing, which
  # leaves the verdict poll blind and aborts every submission; the shim answers
  # the same query from the controller's own record (framework/tools/slurm_state).
  CANARY_ARGS=()
  for p in ${PAYLOAD[@]+"${PAYLOAD[@]}"}; do
    CANARY_ARGS+=(--arg "$p")
  done
  if ! timeout "$CANARY_WAIT" env "PATH=$REPO/framework/tools/slurm_state:$PATH" \
      "$PY" "$REPO/framework/gates/provenance/canary_gate.py" \
      --script "$SCRIPT" --time "$CANARY_T" ${CANARY_METHOD:+--method "$CANARY_METHOD"} \
      ${CANARY_ARGS[@]+"${CANARY_ARGS[@]}"} >/dev/null 2>&1; then
    warn_or_fail "canary" "GPU canary gate FAILED for $SCRIPT — predicted crash; do not submit (log: results/canary/)"
  else
    log_event "$SCRIPT" "canary" "pass" "bounded canary ok"
    echo "[sbatch_gate] canary PASS: $SCRIPT bounded ${CANARY_T}s"
  fi
fi

# 5. test-only validation when on SLURM submit node (skip in dry-run if no sbatch)
if [ "$DRY_RUN" = "1" ]; then
  echo "[sbatch_gate] DRY_RUN=1 — skipping --test-only and final submit"
  log_event "$SCRIPT" "dry-run" "pass" "skipped submit"
  if [ "$STRICT" = "1" ] && [ "$FAILURES" -gt 0 ]; then
    echo "[sbatch_gate] STRICT ABORT: $FAILURES failure(s)" >&2
    exit 1
  fi
  exit 0
fi

if command -v sbatch >/dev/null 2>&1; then
  if ! (cd "$REPO" && sbatch --test-only "$SCRIPT" >/dev/null 2>&1); then
    warn_or_fail "sbatch-test-only" "sbatch --test-only rejected script (syntax/scheduling)"
  else
    log_event "$SCRIPT" "sbatch-test-only" "pass" "accepted"
  fi
fi

if [ "$STRICT" = "1" ] && [ "$FAILURES" -gt 0 ]; then
  echo "[sbatch_gate] STRICT ABORT: $FAILURES failure(s)" >&2
  exit 1
fi
# 5b. record the run manifest (guardrail #3) — advisory; DRY_RUN skips it
if [ "$DRY_RUN" != "1" ]; then
  RUN_NAME="${SBATCH_RUN_NAME:-$(basename "$SCRIPT" .sbatch)}"
  if [[ ! "$RUN_NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
    warn_or_fail "manifest-name" "unsafe SBATCH_RUN_NAME: $RUN_NAME"
    RUN_NAME="$(basename "$SCRIPT" .sbatch)"
  fi
  BANK_ARGS=()
  for bank in $ASSOC_BANKS; do
    BANK_ARGS+=(--bank "$bank")
  done
  SEED_ARGS=()
  for seed in ${SBATCH_RUN_SEEDS:-}; do
    SEED_ARGS+=(--seed "$seed")
  done
  SETTING_ARGS=()
  if [ -n "${SBATCH_RUN_SETTINGS:-}" ]; then
    # Comma-separated K=V pairs, so a value may contain spaces but not a comma.
    IFS=',' read -r -a SETTING_PAIRS <<< "$SBATCH_RUN_SETTINGS"
    for setting in "${SETTING_PAIRS[@]}"; do
      if [ -n "$setting" ]; then
        SETTING_ARGS+=(--setting "$setting")
      fi
    done
  fi
  "$PY" "$REPO/framework/gates/provenance/record_run_manifest.py" --run "$RUN_NAME" \
    --script "$REPO/$SCRIPT" "${BANK_ARGS[@]}" "${SEED_ARGS[@]}" "${SETTING_ARGS[@]}" >/dev/null 2>&1 || \
    warn_or_fail "manifest" "record_run_manifest failed for $SCRIPT"
fi

if [ "$STRICT" = "1" ] && [ "$FAILURES" -gt 0 ]; then
  echo "[sbatch_gate] STRICT ABORT: $FAILURES failure(s)" >&2
  exit 1
fi

# 6. queue mode (RESEARCH_SBATCH_QUEUE=1): publish the payload into its resource lane
# and make sure the lane owns exactly one worker allocation instead of submitting
# the payload here. scripts/slurm_queue/ re-applies this gate's provenance
# discipline at runtime: the worker refuses a dirty checkout, refuses items whose
# commit or payload digest drifted since enqueue, and records a terminal receipt
# per item. Queue-root and worker-horizon overrides: RESEARCH_QUEUE_ROOT,
# RESEARCH_QUEUE_WORKER_TIME, RESEARCH_QUEUE_CLUSTER.
if [ "${RESEARCH_SBATCH_QUEUE:-0}" = "1" ]; then
  # A queue item is a payload, not a command line: positional arguments have no
  # representation in it, so a payload-arg submit refuses instead of enqueueing a
  # job that would run unarmed (or refuse at claim time for a missing argument).
  if [ "${#PAYLOAD[@]}" -gt 0 ]; then
    warn_or_fail "queue-args" "queue mode cannot carry script arguments (${PAYLOAD[*]}) — submit this script directly"
    echo "[sbatch_gate] QUEUE ENQUEUE REFUSED - arguments cannot be queued" >&2
    exit 1
  fi
  QUEUE_CLUSTER="${RESEARCH_QUEUE_CLUSTER:-$DEFAULT_CLUSTER}"
  ENQ_ARGS=(--script "$SCRIPT" --run-name "$RUN_NAME" --cluster "$QUEUE_CLUSTER" --repo "$REPO")
  for bank in $ASSOC_BANKS; do ENQ_ARGS+=(--bank "$bank"); done
  for seed in ${SBATCH_RUN_SEEDS:-}; do ENQ_ARGS+=(--seed "$seed"); done
  if ! ENQ_JSON=$(PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" "$PY" -u \
      "$REPO/scripts/slurm_queue/cli.py" enqueue "${ENQ_ARGS[@]}"); then
    warn_or_fail "queue" "enqueue refused for $SCRIPT (reason on the slurm_queue line above)"
    echo "[sbatch_gate] QUEUE ENQUEUE FAILED - nothing was submitted" >&2
    exit 1
  fi
  ENQ_ITEM_ID=$(printf '%s\n' "$ENQ_JSON" | sed -n 's/.*"item_id": "\([^"]*\)".*/\1/p')
  ENQ_WORKER=$(printf '%s\n' "$ENQ_JSON" | sed -n 's/.*"worker_job_id": "\([^"]*\)".*/\1/p')
  if [ -z "$ENQ_ITEM_ID" ] || [ -z "$ENQ_WORKER" ]; then
    warn_or_fail "queue" "enqueue returned an unreadable record: $ENQ_JSON"
    echo "[sbatch_gate] QUEUE ENQUEUE FAILED - item record unreadable" >&2
    exit 1
  fi
  echo "[sbatch_gate] queued: item=$ENQ_ITEM_ID worker=$ENQ_WORKER run=$RUN_NAME cluster=$QUEUE_CLUSTER"
  log_event "$SCRIPT" "enqueue" "pass" "item=$ENQ_ITEM_ID worker=$ENQ_WORKER cluster=$QUEUE_CLUSTER"
  exit 0
fi

echo "[sbatch_gate] submitting: sbatch $REPO/$SCRIPT ${SBATCH_EXTRA_ARGS:-} ${PAYLOAD[*]:-}"
log_event "$SCRIPT" "submit" "pass" "submitted"
# shellcheck disable=SC2086  # intentional word-splitting for extra sbatch flags
exec sbatch ${SBATCH_EXTRA_ARGS:-} "$REPO/$SCRIPT" ${PAYLOAD[@]+"${PAYLOAD[@]}"}
