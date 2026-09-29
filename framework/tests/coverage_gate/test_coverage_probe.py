"""Integration tests for the coverage probe pytest plugin."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from framework.tests.test_coverage_gate import REPO, SOURCE

PROBE_TEST_SOURCE = (
    "from pkg import mod\n"
    "\n"
    "\n"
    "def test_empty() -> None:\n"
    "    assert mod.total([]) == 0\n"
    "\n"
    "\n"
    "def test_single() -> None:\n"
    "    assert mod.total([2]) == 2\n"
    "\n"
    "\n"
    "def test_many() -> None:\n"
    "    assert mod.total([1, 2, 3]) == 6\n"
)


def test_probe_records_statements_loops_and_contexts(tmp_path: Path) -> None:
    """The probe plugin reports real statement and loop-iteration data."""

    report_path = write_probe_fixture(tmp_path)
    completed = run_probe(tmp_path, report_path)
    assert report_path.is_file(), completed.stdout + completed.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema"] == "research.loop-coverage-report.v1"
    assert report["pytest"]["failed"] == 0
    entry = report["files"]["pkg/mod.py"]
    assert entry["statements"] == 5
    assert entry["transform_error"] is None
    counts = entry["loops"]["0"]["by_context"]
    assert counts["tests/test_mod.py::test_empty"] == [0]
    assert counts["tests/test_mod.py::test_single"] == [1]
    assert counts["tests/test_mod.py::test_many"] == [3]


def run_probe(tmp_path: Path, report_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the coverage probe over the fixture; return the pytest result."""

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "framework.gates.coverage.coverage_probe",
            "--cov-src",
            "pkg",
            "--cov-json",
            str(report_path),
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": str(REPO),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def write_probe_fixture(tmp_path: Path) -> Path:
    """Write a tiny package plus its tests; return the probe report path."""

    package = tmp_path / "pkg"
    tests = tmp_path / "tests"
    package.mkdir()
    tests.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "mod.py").write_text(SOURCE, encoding="utf-8")
    (tests / "test_mod.py").write_text(PROBE_TEST_SOURCE, encoding="utf-8")
    return tmp_path / "report.json"
