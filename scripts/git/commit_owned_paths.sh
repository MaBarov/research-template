#!/usr/bin/env bash
# Commit exactly the named paths through a private index, then resync the shared one.
#
# Why this exists. `git commit` commits whatever tree the index resolves to. In a
# repo whose index also carries a peer agent's staged work, committing only your
# own files means a private GIT_INDEX_FILE -- and a private index never advances
# the shared one. Two failure modes follow, both observed on 2026-09-25:
#
#   1. The private index is rebuilt from the wrong path (a glob matching a stale
#      temp dir). The commit then writes a tree from an older revision and
#      silently deletes or rewinds every path it never learned about. The
#      framework/gates/freshness gate now refuses that commit.
#   2. The private index is correct, but the shared index is left behind. It
#      drifts until the next commit from it reverts files.
#
# This script does both halves and proves each one, so neither depends on memory.
#
# Usage:
#   scripts/git/commit_owned_paths.sh -F MESSAGE_FILE -- PATH...
#   scripts/git/commit_owned_paths.sh -m "subject" -- PATH...
#
# Exit codes: 0 committed and resynced; 1 a proof failed (nothing committed, or
# committed but the resync reported paths needing review); 2 usage error.
set -euo pipefail

usage() {
  sed -n '2,17p' "$0" >&2
  exit 2
}

MSG_FILE=""
MSG_INLINE=""
while getopts ":F:m:h" opt; do
  case "$opt" in
    F) MSG_FILE="$OPTARG" ;;
    m) MSG_INLINE="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))
[ "${1:-}" = "--" ] && shift
[ "$#" -gt 0 ] || usage

REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"

if [ -n "$MSG_FILE" ]; then
  [ -f "$MSG_FILE" ] || { echo "message file not found: $MSG_FILE" >&2; exit 2; }
elif [ -n "$MSG_INLINE" ]; then
  printf '%s\n' "$MSG_INLINE" > /tmp/commit_owned_msg.$$
  MSG_FILE=/tmp/commit_owned_msg.$$
else
  usage
fi

# 1. Pin the private index in a variable used only in this process. Never
#    re-derive it later: a glob is how failure mode 1 starts.
IDX="$(mktemp -d /tmp/commit_owned_XXXXXX)/index"
export GIT_INDEX_FILE="$IDX"

git read-tree HEAD
git add -- "$@"

# 2. Prove the tree before committing: every requested path must be staged.
MISSING=""
for p in "$@"; do
  git diff --cached --name-only HEAD -- "$p" | grep -qxF "$p" || MISSING="$MISSING $p"
done
if [ -n "$MISSING" ]; then
  echo "ABORT: these paths are not staged in the private index:$MISSING" >&2
  echo "ABORT: refusing to commit a tree that does not contain them." >&2
  exit 1
fi
echo "[commit-owned] tree proof ok: $(git diff --cached --name-only HEAD | wc -l) staged path(s)"

# 3. Commit.
git commit -F "$MSG_FILE"

# 4. Prove it landed.
LOST=""
for p in "$@"; do
  git cat-file -e "HEAD:$p" 2>/dev/null || LOST="$LOST $p"
done
if [ -n "$LOST" ]; then
  echo "FAILED: committed, but these paths are absent from HEAD:$LOST" >&2
  echo "FAILED: the wrong index was committed. Restore the dropped paths and retry." >&2
  exit 1
fi
echo "[commit-owned] HEAD proof ok: all $(printf '%s\n' "$@" | wc -l) path(s) present in HEAD"

# 5. Resync the shared index for everything this commit touched. The hook stages
#    regenerated ledgers (INDEX.md and friends) into the private index as well,
#    so resyncing only the named paths would leave the shared index behind. Only
#    re-stage where the working tree equals HEAD: that is lossless and cannot
#    sweep a peer's staged work.
unset GIT_INDEX_FILE
TOUCHED="$(git diff --name-only HEAD^ HEAD 2>/dev/null || true)"
[ -n "$TOUCHED" ] || TOUCHED="$(printf '%s\n' "$@")"
RESYNCED=0
SKIPPED=""
while IFS= read -r p; do
  [ -n "$p" ] || continue
  [ -e "$p" ] || continue
  HEAD_SHA="$(git cat-file blob "HEAD:$p" 2>/dev/null | sha256sum | cut -d' ' -f1)"
  DISK_SHA="$(sha256sum "$p" | cut -d' ' -f1)"
  if [ "$HEAD_SHA" = "$DISK_SHA" ]; then
    git add -- "$p"
    RESYNCED=$((RESYNCED + 1))
  else
    SKIPPED="$SKIPPED $p"
  fi
done <<< "$TOUCHED"
echo "[commit-owned] shared index resynced for $RESYNCED path(s) touched by the commit"
if [ -n "$SKIPPED" ]; then
  echo "[commit-owned] note: working tree differs from HEAD for:$SKIPPED (left as-is)"
fi
echo "[commit-owned] $(git log --oneline -1)"
