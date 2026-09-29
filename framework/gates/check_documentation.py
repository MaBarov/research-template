#!/usr/bin/env python3
"""Adjudication guard: a run verdict requires the full documentation chain.

Before a run's numbers may be treated as evidence, this gate verifies the
documentation layer captured it: manifest (guardrail #3), metrics file
(``harness.RUN_METRICS_SCHEMA``), DVC experiment snapshot, and (optionally) the
MLflow run. No chain = no verdict.

Usage:
  python framework/gates/check_documentation.py --run <name> [--mlflow] [--strict]
    --mlflow  also require the run to exist in the MLflow file store
    --strict  equivalent to always; failures exit 1 either way (adjudication
              is hard — a verdict without a doc chain is not reproducible)

Invariants & Expected State:
    * Exit 0 only when all links exist for ``--run``: the
      ``results/manifests/<run>.json`` manifest with the checkout's manifest
      schema (``harness.RUN_MANIFEST_SCHEMA``), the
      ``results/metrics/<run>.json`` metrics file
      and the DVC experiment of the same name.
    * The MLflow run is checked only under ``--mlflow``; it is otherwise not
      required.
    * Failures are hard by default; ``--strict`` is accepted but changes
      nothing because a verdict without a chain never passes.
    * The gate only reads recorded artefacts: it never creates a manifest,
      metrics file or DVC snapshot itself.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import mlflow

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework import harness

DVC = Path(harness.dvc_bin())
SCHEMA = harness.RUN_MANIFEST_SCHEMA
MLFLOW_URI = harness.mlflow_uri()


def dvc_experiments() -> list[str]:
    proc = subprocess.run(
        [str(DVC), "exp", "list", "-A", "--names-only"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return [ln.strip() for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]


def mlflow_has_run(run: str) -> bool:
    mlflow.set_tracking_uri(MLFLOW_URI)
    return len(mlflow.search_runs(filter_string=f"tags.run_name = '{run}'")) > 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--run", required=True, help="run name (== results/manifests/<run>.json)"
    )
    ap.add_argument("--mlflow", action="store_true", help="also require the MLflow run")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="accepted for symmetry; failures are hard by default",
    )
    return ap.parse_args(argv)


def _manifest_failures(run: str) -> list[str]:
    manifest = REPO / "results" / "manifests" / f"{run}.json"
    if not manifest.exists():
        return [
            f"manifest missing: results/manifests/{run}.json — run record_run_manifest.py --run {run}"
        ]
    try:
        m = json.loads(manifest.read_text(encoding="utf-8"))
        if m.get("schema") != SCHEMA:
            return [f"manifest has schema {m.get('schema')!r}, expected {SCHEMA}"]
    except (OSError, json.JSONDecodeError) as exc:
        return [f"manifest unreadable: {exc}"]
    return []


def _metrics_failures(run: str) -> list[str]:
    metrics = REPO / "results" / "metrics" / f"{run}.json"
    if not metrics.exists():
        return [
            f"metrics missing: results/metrics/{run}.json — re-record with --metrics K=V"
        ]
    return []


def _provenance_failures(run: str, require_mlflow: bool) -> list[str]:
    failures: list[str] = []
    if run not in dvc_experiments():
        failures.append(f"no DVC experiment '{run}' — run: {DVC} exp save -n {run}")
    if require_mlflow and not mlflow_has_run(run):
        failures.append(
            f"no MLflow run '{run}' — run: log_mlflow_run.py --manifest results/manifests/{run}.json"
        )
    return failures


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    failures: list[str] = []
    failures += _manifest_failures(args.run)
    failures += _metrics_failures(args.run)
    failures += _provenance_failures(args.run, args.mlflow)

    if failures:
        for f in failures:
            print(f"[documentation] FAIL: {f}", file=sys.stderr, flush=True)
        print(
            "[documentation] FAIL — verdict not documented; no adjudication",
            file=sys.stderr,
            flush=True,
        )
        return 1
    print(
        f"[documentation] PASS: run {args.run} fully documented (manifest + metrics + DVC exp)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
