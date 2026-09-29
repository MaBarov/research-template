#!/usr/bin/env python3
"""Run manifest verifier — re-derives hashes from live files (guardrail #3).

Replay-accountability: given a recorded manifest (results/manifests/<run>.json),
verifies that the live tree still matches every pin. Any drift (script edited,
bank swapped, commit moved, dirty tree when the run expected clean) is
reported and exits 1 with --strict. This converts "audit freshness"
(AGENTS.md rule 23) from discipline into mechanism.

Usage:
  python scripts/verify_replay.py results/manifests/<run>.json [--strict]

Exit 0 = manifest fully reconstructible from live files; 1 = drift/missing.

Invariants & Expected State:
    - Re-Derive, Never Trust: every pinned hash is recomputed from the live tree;
      a stored hash alone is never accepted.
    - Vendored Drift Excluded: the dirty-tree probe ignores ``third_party`` by
      pathspec, matching the sbatch guard's provenance scope.
    - Fail Closed: an unreadable manifest or an unanswered git probe reports drift
      and exits non-zero under ``--strict``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_ENTRY_REPO = Path(__file__).resolve().parents[3]
if str(_ENTRY_REPO) not in sys.path:
    sys.path.insert(0, str(_ENTRY_REPO))

from framework.gates.provenance.git_facts import git_commit, git_dirty, sha256_file

REPO = _ENTRY_REPO


def _git_pins_drift(pins: dict, drift: list[str]) -> None:
    try:
        live_commit = git_commit(REPO)
        if pins.get("git_commit") != live_commit:
            drift.append(
                f"git_commit: recorded {pins.get('git_commit')} != live {live_commit}"
            )
    except subprocess.CalledProcessError as exc:
        drift.append(f"git unavailable: {exc}")
    try:
        live_dirty = str(git_dirty(REPO)).lower()
        if pins.get("dirty_tree") != live_dirty:
            drift.append(
                f"dirty_tree: recorded {pins.get('dirty_tree')} != live {live_dirty}"
            )
    except subprocess.CalledProcessError as exc:
        drift.append(f"git status unavailable: {exc}")


def _resolve_pin_path(key: str, paths_map: dict[str, str]) -> str | None:
    base = key.removesuffix("_sha256")
    prefix = base.split(":", 1)[0]
    if prefix == "authorization":
        prefix = "auth"
    if base in paths_map:
        return paths_map[base]
    if prefix in ("bank", "auth"):
        matches = [v for k, v in paths_map.items() if k.startswith(prefix + ":")]
        if matches:
            return matches[0]
    if base == "producer_script":
        return paths_map.get("producer_script")
    for value in paths_map.values():
        if Path(value).name in key:
            return value
    return None


def _hash_pins_drift(pins: dict, paths_map: dict[str, str]) -> list[str]:
    drift: list[str] = []
    for key, recorded in pins.items():
        if not key.endswith("_sha256"):
            continue
        rel = _resolve_pin_path(key, paths_map)
        if rel is None:
            drift.append(f"{key}: recorded path not found in manifest")
            continue
        candidate = Path(rel) if Path(rel).is_absolute() else REPO / rel
        if not candidate.exists():
            drift.append(f"{key}: path gone ({rel})")
        else:
            live = sha256_file(candidate)
            if live != recorded:
                drift.append(f"{key}: hash drift ({rel})")
    return drift


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", help="recorded run manifest path")
    ap.add_argument("--strict", action="store_true", help="exit 1 on any drift")
    args = ap.parse_args(argv)

    mp = Path(args.manifest)
    if not mp.is_absolute():
        mp = REPO / mp
    if not mp.exists():
        print(f"[verify] MISSING manifest: {mp}", file=sys.stderr)
        return 1
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    pins = manifest["pins"]
    paths_map: dict[str, str] = manifest.get("paths", {})

    drift: list[str] = []
    _git_pins_drift(pins, drift)
    drift.extend(_hash_pins_drift(pins, paths_map))

    for d in drift:
        print(f"[verify] DRIFT: {d}", file=sys.stderr)
    if drift:
        print(
            f"[verify] FAIL: {len(drift)} drift(s); manifest not reconstructible",
            file=sys.stderr,
        )
        return 1
    print(f"[verify] PASS: manifest {manifest['run']} fully reconstructible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
