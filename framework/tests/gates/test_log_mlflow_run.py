"""Behavioral tests for framework/gates/provenance/log_mlflow_run.py (doc layer)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import mlflow

from framework import harness

REPO = Path(__file__).resolve().parents[3]
PY = sys.executable
SCRIPT = REPO / "framework" / "gates" / "provenance" / "log_mlflow_run.py"


def make_manifest(tmp: Path) -> Path:
    p = tmp / "run_test.json"
    p.write_text(
        json.dumps(
            {
                "schema": harness.RUN_MANIFEST_SCHEMA,
                "run": "unit_run",
                "pins": {
                    "git_commit": "a1b2c3d4e5f67890",
                    "seeds": '["1"]',
                    "python": "x",
                },
            }
        )
    )
    return p


def log(tmp: Path, *extra: str) -> subprocess.CompletedProcess:
    manifest = make_manifest(tmp)
    return subprocess.run(
        [PY, str(SCRIPT), "--manifest", str(manifest), *extra],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
        check=False,
        env={"PATH": "/usr/bin:/bin", "MLFLOW_TRACKING_URI": f"file://{tmp / 'store'}"},
    )


def test_empty_metrics_logs_run_with_pin_params(tmp_path: Path) -> None:
    proc = log(tmp_path)
    assert proc.returncode == 0, proc.stderr
    mlflow.set_tracking_uri(f"file://{tmp_path / 'store'}")
    runs = mlflow.search_runs()
    assert len(runs) == 1
    row = runs.iloc[0]
    assert row["params.git_commit"] == "a1b2c3d4e5f67890"
    assert row["tags.schema"] == harness.RUN_MANIFEST_SCHEMA


def test_metrics_tags_params_land(tmp_path: Path) -> None:
    proc = log(
        tmp_path,
        "--metrics",
        "score=25.1",
        "--metrics",
        "auc=0.05",
        "--tag",
        "verdict=probe",
        "--params",
        "lr=1e-4",
    )
    assert proc.returncode == 0, proc.stderr
    mlflow.set_tracking_uri(f"file://{tmp_path / 'store'}")
    row = mlflow.search_runs().iloc[0]
    assert row["metrics.score"] == 25.1
    assert row["metrics.auc"] == 0.05
    assert row["tags.verdict"] == "probe"
    assert row["params.lr"] == "1e-4"


def test_bad_manifest_fails_clean(tmp_path: Path) -> None:
    bad = tmp_path / "not_a_manifest.json"
    bad.write_text('{"schema": "other"}')
    proc = subprocess.run(
        [PY, str(SCRIPT), "--manifest", str(bad)],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "MLFLOW_TRACKING_URI": f"file://{tmp_path / 'store'}",
        },
    )
    assert proc.returncode == 2
    assert f"not a {harness.RUN_MANIFEST_SCHEMA} manifest" in proc.stderr
    assert not (tmp_path / "store").exists() or not list((tmp_path / "store").glob("*"))


def test_invalid_metric_kv_fails(tmp_path: Path) -> None:
    proc = log(tmp_path, "--metrics", "bogus")
    assert proc.returncode == 1
    assert "invalid metric" in proc.stderr
