#!/usr/bin/env bash
# Single-source sbatch provenance contract (shared by framework/hooks/pre-commit
# and framework/gates/sbatch_gate.sh so the two cannot drift).
#
# A job script satisfies the contract when it:
#   1. refuses to run on a dirty tree      -> literal "REFUSING RUN: dirty tree"
#   2. resolves the commit it runs from    -> "COMMIT=$(git rev-parse ...)"
#      (case-insensitive commIT; the canonical guard in slurm/template.sbatch
#       does this, and so does every script that copies its header)
#   3. stamps a status line with it        -> "status=... commit=$COMMIT" or
#      "status=... commit=$(git rev-parse ...)"
#   4. offers no dirty-run override        -> no ALLOW_DIRTY-style knob anywhere
#      (user ruling 2026-09-26: the refusal is a gate, not a default)
#   5. refuses unconditionally             -> the refusal leads the dirty branch
#      ("if [[ -n "$DIRTY_STATUS" ]]") and is followed by "exit 90"
#
# Rules 4 and 5 exist so the refusal cannot be re-opened by editing a script:
# the anti-pattern rule HNS035/HNS036 checks the same two properties from the
# Python gate, and every job script refuses at runtime under bash.
#
# Usage: bash framework/gates/check_sbatch_contract.sh FILE...
# Exit 0 when every file satisfies the contract, 1 otherwise (reasons on stderr).
set -uo pipefail

OVERRIDE_PATTERN='(ALLOW|SKIP|PERMIT|IGNORE|FORCE|BYPASS)_?DIRTY|DIRTY_(RUN|OK|ALLOWED)'

# Report the line that breaks rule 4 or rule 5, if any.
refusal_shape_problem() {
  local file="$1" line_number="$2"
  local previous
  previous=$(sed -n "$((line_number - 1))p" "$file")
  if ! printf '%s' "$previous" | grep -qE '\[\[[[:space:]]+-n[[:space:]]+"?[$]?\{?DIRTY_STATUS'; then
    printf '%s' "the dirty-tree refusal does not lead the dirty branch"
    return 0
  fi
  if ! sed -n "$((line_number + 1)),$((line_number + 2))p" "$file" | grep -q "exit 90"; then
    printf '%s' "the dirty-tree refusal is not followed by 'exit 90'"
    return 0
  fi
  return 1
}

status=0
for f in "$@"; do
  [ -f "$f" ] || { echo "[sbatch-contract] $f: missing file" >&2; status=1; continue; }
  if ! grep -q "REFUSING RUN: dirty tree" "$f" 2>/dev/null; then
    echo "[sbatch-contract] $f: missing the 'REFUSING RUN: dirty tree' runtime refusal" >&2
    status=1
  fi
  if ! grep -qE '[Cc][Oo][Mm][Mm][Ii][Tt]=\$\(git rev-parse' "$f" 2>/dev/null; then
    echo "[sbatch-contract] $f: missing commit resolution 'COMMIT=\$(git rev-parse ...)'" >&2
    status=1
  fi
  stamp_ok=0
  if grep -qE 'status=.*commit=\$\(git rev-parse' "$f" 2>/dev/null; then
    stamp_ok=1
  elif grep -qE 'status=.*commit=\$\{?COMMIT\}?' "$f" 2>/dev/null; then
    stamp_ok=1
  fi
  if [ "$stamp_ok" != "1" ]; then
    echo "[sbatch-contract] $f: missing 'status=... commit=<commit>' stamp (copy the repo's sbatch template)" >&2
    status=1
  fi
  override_hit=$(grep -nE "$OVERRIDE_PATTERN" "$f" 2>/dev/null | head -1)
  if [ -n "$override_hit" ]; then
    echo "[sbatch-contract] $f: a dirty-run override is banned (line ${override_hit%%:*}); commit the work before submitting" >&2
    status=1
  fi
  refusal_line=$(grep -n "REFUSING RUN: dirty tree" "$f" 2>/dev/null | head -1 | cut -d: -f1)
  if [ -n "$refusal_line" ]; then
    problem=$(refusal_shape_problem "$f" "$refusal_line")
    if [ -n "$problem" ]; then
      echo "[sbatch-contract] $f: $problem (line $refusal_line)" >&2
      status=1
    fi
  fi
done
exit "$status"
