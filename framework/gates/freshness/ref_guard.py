#!/usr/bin/env python3
"""Block ref moves that would bypass the pre-commit gate battery.

Thumbnail: Refuses unprovenanced ref updates that bypass commit gate battery.

Invariants & Expected State:
    - Fail closed: any unexpected exception prints a diagnostic and exits 1, so a
      broken guard aborts the transaction rather than waving it through.
    - Reachability, never identity: the trust set is the value each ``refs/heads``
      and ``refs/remotes`` ref holds as the transaction prepares (the ref being
      moved contributes its pre-move tip), so an ordinary rewind or fast-forward
      lands while a freshly crafted commit -- which no live tip reaches -- does
      not. Tags and remotes use the same content rule; a tag has no marker escape.
    - Armed markers bind process and tree: the marker key is the invoking git PID,
      and it is honoured only when the new commit's tree matches, the record is
      fresh (< 600 s) and ``/proc/<pid>/stat`` field 22 still pins the same
      process, so a reused PID cannot present a stale tree. The marker is consumed
      on the match and stale entries are pruned opportunistically.
    - Attribution is read from ``/proc/<ppid>/cmdline`` (via ``_invoker_cmdline``);
      only fetch/pull/push/remote/clone may move a remote-tracking ref without
      reachability, and every git subprocess runs under
      ``GIT_NO_REPLACE_OBJECTS=1``.
    - Only prepared transactions are judged; committed/aborted exit 0 before any
      read, and non-gated refs (HEAD, ORIG_HEAD, REBASE_HEAD, refs/stash,
      refs/notes, refs/bisect, ...) pass untouched.
    - Every gated decision is appended to ``<common-dir>/<gate-state-dir>/ref_audit.jsonl``
      as ``{ts, ref, old, new, verdict, rule, code, invoker}``.
    - Exit 0 allow (or a non-prepared state); 1 block or internal error.

Usage::

  framework/hooks/reference-transaction prepared   # stdin: "<old> <new> <ref>"

Exit codes: 0 allow (or a non-prepared state); 1 block or internal error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework import harness

HEADS = "refs/heads/"
TAGS = "refs/tags/"
REMOTES = "refs/remotes/"
REPLACE = "refs/replace/"
GATED_PREFIXES = (HEADS, TAGS, REMOTES, REPLACE)
TIP_PREFIXES = (HEADS, REMOTES)
MARKER_TTL = 600.0
REMOTE_OP_RE = re.compile(r"(^|/)git(-core)? (fetch|pull|push|remote|clone)\b")
HEADS_REMEDY = (
    "the target commit was not created by a gated commit. Use `git commit`; "
    "for remote commits fetch them into a remote-tracking ref first."
)


@dataclass(frozen=True)
class TransLine:
    """One ``<old> <new> <ref>`` line of a reference transaction."""

    old: str
    new: str
    ref: str


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    """Run one git command in the hook's repository with replace refs disabled."""
    env = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1")
    return subprocess.run(
        ["git", *args], check=False, capture_output=True, text=True, env=env
    )


def _out(*args: str) -> tuple[int, str]:
    """Run one git command and return ``(returncode, stdout.strip())``."""
    result = _git(*args)
    return result.returncode, result.stdout.strip()


def _is_zero(value: str) -> bool:
    """Return True for the all-zero object id a deletion carries."""
    return not value.strip("0")


def _common_dir() -> Path:
    """Return the repository's common git directory as an absolute path."""
    code, out = _out("rev-parse", "--git-common-dir")
    if code != 0 or not out:
        raise RuntimeError("git rev-parse --git-common-dir failed")
    path = Path(out)
    return path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()


def _invoker_cmdline() -> list[str]:
    """Return the argv of the invoking git command from ``/proc/<ppid>/cmdline``."""
    try:
        raw = Path(f"/proc/{os.getppid()}/cmdline").read_bytes()
    except OSError:
        return []
    return [arg for arg in raw.decode("utf-8", "replace").split("\0") if arg]


def _invoker_is_remote_op() -> bool:
    """Return True when the invoking command is a fetch/pull/push/remote/clone."""
    return bool(REMOTE_OP_RE.search(" ".join(_invoker_cmdline())))


def _parse_lines(text: str) -> list[TransLine]:
    """Parse stdin into transaction lines, raising on a malformed record."""
    lines: list[TransLine] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        parts = raw.split(" ", 2)
        if len(parts) != 3:
            raise ValueError(f"malformed transaction line: {raw!r}")
        lines.append(TransLine(old=parts[0], new=parts[1], ref=parts[2]))
    return lines


def _resolves_to_commit(rev: str) -> bool:
    """Return True when ``rev`` peels to a commit object."""
    if _is_zero(rev):
        return False
    code, _ = _out("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    return code == 0


def _is_ancestor(commit: str, tip: str) -> bool:
    """Return True when ``commit`` is an ancestor of ``tip`` (unresolvable -> False)."""
    return _git("merge-base", "--is-ancestor", commit, tip).returncode == 0


def _tree_of(rev: str) -> str | None:
    """Return the tree id of ``rev``, or None when it does not resolve."""
    code, out = _out("rev-parse", "--verify", "--quiet", f"{rev}^{{tree}}")
    return out if code == 0 else None


def _trust_tips() -> list[str]:
    """Return the live branch and remote-tracking tips the transaction prepares over.

    Every ref is enumerated and filtered by prefix. A glob such as
    ``refs/heads/*`` does not match nested names (``fix/x``, ``fix/deep/x``),
    which would hide a live tip and refuse a legitimate fast-forward from it.
    """
    code, out = _out("for-each-ref", "--format=%(objectname)%00%(refname)")
    if code != 0:
        return []
    tips: list[str] = []
    for record in out.splitlines():
        objectname, _, refname = record.partition("\x00")
        if objectname and refname.startswith(TIP_PREFIXES):
            tips.append(objectname)
    return tips


def _content_verdict(new: str, old: str, tips: Sequence[str]) -> str | None:
    """Return the rule that lets ``new`` stand without a marker, or None."""
    if _is_zero(new):
        return "deletion"
    if new == old:
        return "equal"
    if not _resolves_to_commit(new):
        return "unresolvable"
    for tip in tips:
        if _is_ancestor(new, tip):
            return "reachable"
    return None


def _proc_starttime(pid: int) -> str | None:
    """Return ``/proc/<pid>/stat`` field 22 (starttime), or None when unreadable."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    close = stat.rfind(")")
    fields = stat[close + 2 :].split()
    return fields[19] if len(fields) > 19 else None


def _armed_dir(common: Path) -> Path:
    """Return the directory holding this repository's armed tree markers."""
    return common / harness.GATE_STATE_DIR / "armed"


def _prune_stale_markers(armed: Path, now: float) -> None:
    """Unlink armed markers older than the freshness window."""
    if not armed.is_dir():
        return
    for entry in armed.iterdir():
        try:
            _, stamp, _ = entry.read_text(encoding="utf-8").split()
            if now - float(stamp) > MARKER_TTL:
                entry.unlink()
        except (OSError, ValueError):
            continue


def _marker_verdict(common: Path, new: str, now: float) -> str | None:
    """Return ``"marker"`` when an armed marker vouches for this move, else None."""
    pid = os.getppid()
    marker = _armed_dir(common) / str(pid)
    if not marker.is_file():
        return None
    try:
        tree, stamp, starttime = marker.read_text(encoding="utf-8").split()
    except (OSError, ValueError):
        return None
    if now - float(stamp) >= MARKER_TTL:
        return None
    if _proc_starttime(pid) != starttime:
        return None
    if _tree_of(new) != tree:
        return None
    marker.unlink()
    return "marker"


def _is_gated(ref: str) -> bool:
    """Return True for a ref in a guarded namespace."""
    return ref.startswith(GATED_PREFIXES)


def _verdict_remote(line: TransLine, tips: Sequence[str]) -> tuple[str, str]:
    """Decide one remote-tracking ref move."""
    if _content_verdict(line.new, line.old, tips) == "reachable":
        return "allow", "reachable"
    if _invoker_is_remote_op():
        return "allow", "remote-op"
    return "block", "remote-plumbing"


def _gated_verdict(
    line: TransLine, tips: Sequence[str], common: Path, grafts: bool, now: float
) -> tuple[str, str]:
    """Return ``(verdict, rule)`` for one guarded ref line."""
    if _is_zero(line.new):
        return "allow", "deletion"
    if line.new == line.old:
        return "allow", "equal"
    if grafts:
        return "block", "grafts"
    if line.ref.startswith(REPLACE):
        return "block", "replace"
    if line.ref.startswith(REMOTES):
        return _verdict_remote(line, tips)
    verdict = _content_verdict(line.new, line.old, tips)
    if verdict == "reachable":
        return "allow", verdict
    if verdict == "unresolvable":
        return "block", "unresolvable"
    if line.ref.startswith(HEADS) and _marker_verdict(common, line.new, now):
        return "allow", "marker"
    return "block", "plumbing"


def _block_message(ref: str, rule: str) -> str:
    """Return the actionable stderr message for one blocked decision."""
    if rule == "grafts":
        return "the repository carries an info/grafts file, which can fake ancestry"
    if rule == "replace":
        return "replace refs can fake ancestry"
    if rule == "remote-plumbing":
        return "a remote-tracking ref moved without a fetch/pull/push"
    if rule == "unresolvable":
        return "the new value does not resolve to a commit"
    if ref.startswith(TAGS):
        return "the tag did not come from a gated commit"
    return HEADS_REMEDY


def _log(common: Path, line: TransLine, verdict: str, rule: str) -> None:
    """Append one JSONL audit record for a guarded decision."""
    path = common / harness.GATE_STATE_DIR / "ref_audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.time(),
        "ref": line.ref,
        "old": line.old,
        "new": line.new,
        "verdict": verdict,
        "rule": rule,
        "code": "GUARD001",
        "invoker": " ".join(_invoker_cmdline()),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _judge(
    line: TransLine, tips: Sequence[str], common: Path, grafts: bool, now: float
) -> int:
    """Judge one guarded line: log it, report a block, and return 1 when blocked."""
    verdict, rule = _gated_verdict(line, tips, common, grafts, now)
    _log(common, line, verdict, rule)
    if verdict != "block":
        return 0
    print(
        f"[ref-guard] GUARD001 BLOCKED {line.ref}: {_block_message(line.ref, rule)}",
        file=sys.stderr,
    )
    return 1


def _run_prepared() -> int:
    """Judge every guarded line of a prepared transaction; 1 when any is blocked."""
    lines = _parse_lines(sys.stdin.read())
    common = _common_dir()
    now = time.time()
    _prune_stale_markers(_armed_dir(common), now)
    grafts = (common / "info" / "grafts").exists()
    tips = _trust_tips()
    blocked = 0
    for line in lines:
        if _is_gated(line.ref):
            blocked += _judge(line, tips, common, grafts, now)
    return 1 if blocked else 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the reference-transaction hook argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state",
        default="prepared",
        choices=("prepared", "committed", "aborted"),
        help="the reference-transaction state git reports (only prepared is judged)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Judge a prepared transaction; allow non-prepared states and fail closed."""
    args = _build_parser().parse_args(argv)
    if args.state != "prepared":
        return 0
    try:
        return _run_prepared()
    except Exception as exc:  # noqa: BLE001 - fail closed on any internal error
        print(
            f"[ref-guard] internal error: {exc!r}; blocking (fail-closed)",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
