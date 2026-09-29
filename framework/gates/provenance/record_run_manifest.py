#!/usr/bin/env python3
"""Run manifest recorder — binds a run to frozen inputs (guardrail #3).

Records code commit, producer script(s) hash, prompt-bank hash, env pins,
seeds, the resolved run settings, and the authorization receipt under
results/manifests/<run>.json.  Reuse: verify_replay.py re-derives the hashes
and holds the manifest accountable. This makes "did the run replicate?" a
one-command answer instead of a forensic arc (cf. 2026-08-21 bit-exact
restoration).

Usage:
  python scripts/record_run_manifest.py --run NAME --script cluster/x.sbatch \
      [--bank experiments/<name>/prompts.json ...] \
      [--authorization results/xxx.json] [--seed 20260816 ...] \
      [--setting max_steps=2000 ...]

Exits 0 on success; manifest is written only when every requested pin
resolved (fail-closed).

Invariants & Expected State:
    - Resolved Pins Only: the manifest is written only when every requested pin
      (commit, script hash, banks, seeds) resolved; a missing input exits non-zero
      and writes nothing.
    - Settings Are Recorded Verbatim: ``--setting K=V`` pairs are stored as given,
      so a retry under the same manifest re-uses the values that actually ran.
    - Replayable: ``verify_replay.py`` re-derives the pinned hashes from the
      manifest, so a recorded run is reproducible from it alone.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

_ENTRY_REPO = Path(__file__).resolve().parents[3]
if str(_ENTRY_REPO) not in sys.path:
    sys.path.insert(0, str(_ENTRY_REPO))

import framework.gates.provenance.git_facts
from framework import harness

REPO = _ENTRY_REPO
MANIFEST_DIR = REPO / "results" / "manifests"
METRICS_DIR = REPO / "results" / "metrics"


def parse_metrics(items: list[str]) -> tuple[dict[str, float | str], list[str]]:
    """Parse repeatable K=V metric flags; unparseable values stay strings."""
    metrics: dict[str, float | str] = {}
    problems: list[str] = []
    for m in items:
        key, sep, val = m.partition("=")
        if not key or not sep:
            problems.append(f"invalid metric (want K=V): {m}")
            continue
        try:
            metrics[key] = float(val)
        except ValueError:
            metrics[key] = val
    return metrics, problems


def parse_settings(items: list[str]) -> tuple[dict[str, str], list[str]]:
    """Parse repeatable K=V setting flags: the resolved values a run executed."""
    settings: dict[str, str] = {}
    problems: list[str] = []
    for item in items:
        key, sep, value = item.partition("=")
        if not key or not sep or not value:
            problems.append(f"invalid setting (want K=V): {item}")
            continue
        settings[key] = value
    return settings, problems


def pin_file(
    pins: dict[str, str], problems: list[str], key: str, path: str | Path
) -> None:
    p = Path(path)
    if not p.is_absolute():
        p = REPO / p
    if not p.exists():
        problems.append(f"{key} missing: {p}")
        return
    pins[f"{key}_sha256"] = framework.gates.provenance.git_facts.sha256_file(p)


def build_pins(args: argparse.Namespace, problems: list[str]) -> dict[str, str]:
    pins: dict[str, str] = {}
    script = Path(args.script)
    if not script.is_absolute():
        script = REPO / script
    if not script.exists():
        problems.append(f"script missing: {script}")
    else:
        pins["producer_script_sha256"] = (
            framework.gates.provenance.git_facts.sha256_file(script)
        )
    for b in args.bank:
        pin_file(pins, problems, f"bank:{Path(b).name}", b)
    for a in args.authorization:
        pin_file(pins, problems, f"auth:{Path(a).name}", a)
    try:
        commit = framework.gates.provenance.git_facts.git_commit(REPO)
    except subprocess.CalledProcessError as exc:
        problems.append(f"git unavailable: {exc}")
        commit = "unknown"
    pins["git_commit"] = commit
    pins["dirty_tree"] = str(
        framework.gates.provenance.git_facts.git_dirty(REPO)
    ).lower()
    pins["seeds"] = json.dumps(args.seed, sort_keys=True)
    pins["python"] = sys.executable
    return pins


def apply_from_manifest(args: argparse.Namespace) -> str | None:
    """Reuse an existing manifest's pins/paths (adjudication path)."""
    src = Path(args.from_manifest)
    if not src.is_absolute():
        src = REPO / src
    try:
        old = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"cannot read --from-manifest {src}: {exc}"
    paths = old.get("paths", {})
    pins = old.get("pins", {})
    script_p = paths.get("producer_script")
    if not script_p:
        return "--from-manifest has no paths.producer_script"
    args.script = script_p
    args.bank = [p for k, p in paths.items() if k.startswith("bank:")]
    args.authorization = [p for k, p in paths.items() if k.startswith("auth:")]
    if not args.settings:
        args.settings = [f"{k}={v}" for k, v in (old.get("settings") or {}).items()]
    try:
        args.seed = json.loads(pins.get("seeds", "[]"))
    except json.JSONDecodeError:
        args.seed = []
    return None


def _add_pin_arguments(ap: argparse.ArgumentParser) -> None:
    """Add the repeatable --bank/--authorization/--seed pin flags."""
    ap.add_argument(
        "--bank", action="append", default=[], help="prompt/data bank JSON path"
    )
    ap.add_argument(
        "--authorization",
        action="append",
        default=[],
        help="authorization receipt path",
    )
    ap.add_argument(
        "--seed", action="append", default=[], help="seed value (repeatable)"
    )


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="unique run/arm name")
    ap.add_argument(
        "--script",
        default=None,
        help="producer sbatch/script path (required unless --from-manifest)",
    )
    _add_pin_arguments(ap)
    ap.add_argument(
        "--metrics",
        action="append",
        default=[],
        help="metric K=V (repeatable; written to results/metrics/<run>.json)",
    )
    ap.add_argument(
        "--setting",
        action="append",
        dest="settings",
        default=[],
        help="resolved run setting K=V (repeatable; written to the manifest)",
    )
    ap.add_argument(
        "--from-manifest",
        default=None,
        help="reuse an existing manifest: re-read its pinned script/banks/auth/seeds, re-derive hashes, add --metrics (adjudication path)",
    )
    return ap


def _resolve_source(args: argparse.Namespace) -> str | None:
    """Apply --from-manifest, then require a producer script; None on failure."""
    if args.from_manifest:
        err = apply_from_manifest(args)
        if err:
            print(f"[manifest] {err}", file=sys.stderr)
            return None
    if not args.script:
        print("[manifest] --script required (or use --from-manifest)", file=sys.stderr)
        return None
    return args.script


def _resolve_paths(args: argparse.Namespace) -> dict[str, str]:
    """Pin key -> repo-relative path map so verify_replay can re-derive hashes."""
    script = Path(args.script)
    if not script.is_absolute():
        script = REPO / script
    paths: dict[str, str] = {}
    for b in args.bank:
        p = Path(b)
        paths[f"bank:{p.name}"] = str(p)
    for a in args.authorization:
        p = Path(a)
        paths[f"auth:{p.name}"] = str(p)
    paths["producer_script"] = str(
        script.relative_to(REPO) if script.is_relative_to(REPO) else script
    )
    return paths


def _write_manifest(
    args: argparse.Namespace,
    pins: dict[str, str],
    paths: dict[str, str],
    settings: dict[str, str],
) -> Path:
    """Write the run manifest and return its path."""
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": harness.RUN_MANIFEST_SCHEMA,
        "run": args.run,
        "recorded_at": datetime.now(UTC).isoformat(),
        "pins": pins,
        "paths": paths,
        "settings": settings,
    }
    out = MANIFEST_DIR / f"{args.run}.json"
    out.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[manifest] wrote {out}")
    return out


def _write_metrics(run: str, metrics: dict[str, float | str]) -> None:
    """Write the optional run-metrics sidecar."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    mout = METRICS_DIR / f"{run}.json"
    mout.write_text(
        json.dumps(
            {"schema": harness.RUN_METRICS_SCHEMA, "run": run, "metrics": metrics},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[manifest] wrote {mout}", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if _resolve_source(args) is None:
        return 1

    metrics, metric_problems = parse_metrics(args.metrics)
    settings, setting_problems = parse_settings(args.settings)

    problems: list[str] = []
    problems.extend(metric_problems)
    problems.extend(setting_problems)
    pins = build_pins(args, problems)

    if problems:
        for p in problems:
            print(f"[manifest] {p}", file=sys.stderr)
        print("[manifest] FAIL-CLOSED: manifest not written", file=sys.stderr)
        return 1

    _write_manifest(args, pins, _resolve_paths(args), settings)

    if metrics:
        _write_metrics(args.run, metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
