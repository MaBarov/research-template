#!/usr/bin/env python3
"""Pre-submit guard: every prompt/data bank referenced by a job must be DVC-tracked.

The prompt bank is the contamination/provenance surface (guardrail #2 + #3).
If it is not under DVC, edits go silently unversioned; if it is tracked but
modified, the run would consume drifted data. This gate makes the DVC adoption
structural instead of disciplinary.

Untracked bank = hard failure (exit 1) — it is a setup violation, not a
judgment call. Tracked-but-modified = advisory warning (mid-edit is legal),
blocking under --strict. Exit 0 only when every bank is tracked and clean.

Usage:
  python framework/gates/check_dvc_tracked.py <bank.json ...> [--strict]

Invariants & Expected State:
    * Exit 0 only when every named bank has a ``.dvc`` pointer and a clean
      ``dvc status``; a clean run prints one pass line per bank.
    * A bank without a ``.dvc`` pointer is a hard failure (exit 1); a tracked
      bank whose ``dvc status`` shows drift is advisory and blocks only under
      ``--strict``.
    * The verdict comes from ``dvc status`` output, with stderr folded in, so
      an unreachable DVC surfaces as drift rather than a clean pass.
    * The gate never edits the banks or the DVC metadata; it only reports.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework import harness

DVC = Path(harness.dvc_bin())


def dvc_status(path: Path) -> str:
    proc = subprocess.run(
        [str(DVC), "status", str(path)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return proc.stdout + proc.stderr


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("banks", nargs="+", help="prompt/data bank JSON paths")
    ap.add_argument(
        "--strict", action="store_true", help="also fail on modified tracked files"
    )
    return ap.parse_args(argv)


def _bank_report(b: str, strict: bool) -> tuple[bool, str | None]:
    """Return (hard, message) for one bank; a clean bank prints its pass line."""
    p = Path(b)
    if not p.is_absolute():
        p = REPO / p
    pointer = p.with_name(p.name + ".dvc")
    if not pointer.exists():
        return True, f"NOT DVC-TRACKED: {b} — run: {DVC} add {b}"
    status = dvc_status(p)
    if "up to date" in status or "Data and pipelines are up to date" in status:
        print(f"[dvc-tracked] pass: {b} tracked and clean", flush=True)
        return False, None
    msg = f"MODIFIED vs DVC cache: {b} — dvc status shows drift; checkout or track the new state"
    return strict, msg


def _report(warnings: list[str], hard_failures: list[str]) -> None:
    for w in warnings:
        print(
            f"[dvc-tracked] WARN: {w} (advisory; --strict blocks)",
            file=sys.stderr,
            flush=True,
        )
    for f in hard_failures:
        print(f"[dvc-tracked] FAIL: {f}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    hard_failures: list[str] = []
    warnings: list[str] = []
    for b in args.banks:
        hard, message = _bank_report(b, args.strict)
        if message is None:
            continue
        if hard:
            hard_failures.append(message)
        else:
            warnings.append(message)

    _report(warnings, hard_failures)
    if hard_failures:
        print("[dvc-tracked] FAIL-CLOSED", file=sys.stderr, flush=True)
        return 1
    print("[dvc-tracked] all banks tracked", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
