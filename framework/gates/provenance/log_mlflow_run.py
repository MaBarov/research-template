#!/usr/bin/env python3
"""Log one run manifest to the local MLflow registry (documentation gate #3).

Reads a run manifest and records an MLflow run under ``MLFLOW_TRACKING_URI``
(default ``file://<repo>/results/mlflow_runs``) with the manifest's pins as
params, its schema as a tag, and the manifest text as an artifact.

Usage:
  log_mlflow_run.py --manifest results/manifests/<run>.json \\
      [--metrics K=V ...] [--tag K=V ...] [--params K=V ...]

Exit codes: 0 = logged; 1 = bad K=V argument; 2 = not a run manifest of this
checkout's schema (``harness.RUN_MANIFEST_SCHEMA``) or an unreadable manifest.
No store writes happen before the manifest validates.

Invariants & Expected State:
    - Validate Before Write: a manifest is parsed and schema-checked before any
      MLflow call, so an unreadable input writes nothing.
    - Tracking URI Honoured: the run lands under ``MLFLOW_TRACKING_URI`` when set,
      else the repo-relative default beside the results tree.
    - Pins Are Defaults: manifest pins seed params without overwriting an explicit
      ``--params`` value.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ENTRY_REPO = Path(__file__).resolve().parents[3]
if str(_ENTRY_REPO) not in sys.path:
    sys.path.insert(0, str(_ENTRY_REPO))

import mlflow

from framework import harness

REPO = _ENTRY_REPO
# A repo-relative default keeps the registry inside the checkout; an operator
# points MLFLOW_TRACKING_URI at a shared store when one exists.
DEFAULT_URI = f"file://{REPO / 'results' / 'mlflow_runs'}"
SCHEMA = harness.RUN_MANIFEST_SCHEMA


def kv(items: list[str], what: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for it in items:
        if "=" not in it:
            print(f"invalid {what}: {it!r} (expected K=V)", file=sys.stderr)
            sys.exit(1)
        k, v = it.split("=", 1)
        out[k] = v
    return out


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="path to a run manifest written by record_run_manifest.py",
    )
    ap.add_argument(
        "--metrics", action="append", default=[], help="metric K=V (repeatable)"
    )
    ap.add_argument("--tag", action="append", default=[], help="tag K=V (repeatable)")
    ap.add_argument(
        "--params", action="append", default=[], help="param K=V (repeatable)"
    )
    return ap


def _load_manifest(path: Path) -> dict | None:
    """Read a run manifest of this checkout's schema, or None when unusable."""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"manifest unreadable: {exc}", file=sys.stderr)
        return None
    if manifest.get("schema") != SCHEMA:
        print(f"not a {SCHEMA} manifest: {path}", file=sys.stderr)
        return None
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    manifest = _load_manifest(args.manifest)
    if manifest is None:
        return 2

    metrics = {k: float(v) for k, v in kv(args.metrics, "metric").items()}
    tags = kv(args.tag, "tag")
    params = kv(args.params, "params")
    for pk, pv in manifest.get("pins", {}).items():
        params.setdefault(pk, str(pv))
    params.setdefault("run", str(manifest.get("run", "")))
    tags.setdefault("schema", SCHEMA)

    tags.setdefault("run_name", str(manifest.get("run", "")))
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_URI))
    with mlflow.start_run(run_name=str(manifest.get("run", ""))):
        mlflow.log_metrics(metrics)
        mlflow.log_params(params)
        mlflow.set_tags(tags)
        mlflow.log_text(json.dumps(manifest, indent=2), "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
