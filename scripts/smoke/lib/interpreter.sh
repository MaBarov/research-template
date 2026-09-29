#!/usr/bin/env bash
# Interpreter resolution shared by the smoke drivers (sourced, not executed).
#
# The drivers set the same options before sourcing this file, so the prologue is
# idempotent there and gives any other consumer the same fail-fast contract the
# gate (HNS019) requires of every shell module in this tree.
set -euo pipefail
#
# A smoke that runs under an interpreter the project does not support is a false
# signal: it can fail on syntax the real job would accept, or pass on a path the
# real job never takes. The floor lives once, in framework/harness.py
# (PYTHON_FLOOR, kept equal to requires-python), and this helper enforces it.
#
# Usage, from a driver:
#   . "$REPO/scripts/smoke/lib/interpreter.sh"
#   PY="$(smoke_python "$REPO")" || exit 1
#
# Resolution order: SMOKE_PYTHON, the checkout's .venv, then python3.NN on PATH
# from newest to oldest. Prints the chosen interpreter; prints nothing but an
# explanation on stderr when none satisfies the floor.

_smoke_floor() {
  local repo="$1" floor
  floor="$(python3 -u "$repo/framework/harness.py" --get python-floor 2>/dev/null || true)"
  printf '%s\n' "${floor:-0.0}"
}

_smoke_version_ok() {
  "$1" -c 'import sys
floor = sys.argv[1].split(".")
raise SystemExit(0 if sys.version_info[:2] >= (int(floor[0]), int(floor[1])) else 1)' \
    "$2" >/dev/null 2>&1
}

smoke_python() {
  local repo="$1" floor candidate
  floor="$(_smoke_floor "$repo")"
  for candidate in \
    "${SMOKE_PYTHON:-}" \
    "$repo/.venv/bin/python" \
    "$(python3 -u "$repo/framework/harness.py" --get python 2>/dev/null || true)" \
    "$(command -v python3.13 || true)" \
    "$(command -v python3.12 || true)" \
    "$(command -v python3.11 || true)" \
    "$(command -v python3 || true)"; do
    [ -n "$candidate" ] || continue
    [ -x "$candidate" ] || continue
    if _smoke_version_ok "$candidate" "$floor"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  echo "[smoke] FAIL: no interpreter >= $floor found (create .venv or set SMOKE_PYTHON)" >&2
  return 1
}
