"""CLI options, paths and schema constants of the coverage gate.

Invariants & Expected State:
    * Owns the gate's defaults: ``DEFAULT_SRC``, ``DEFAULT_TESTS``,
      ``DEFAULT_BASELINE``, ``DEFAULT_EVIDENCE``, ``DEFAULT_WAIVERS``,
      ``DEFAULT_ALIASES`` and the schema names ``BASELINE_SCHEMA``,
      ``EVIDENCE_SCHEMA``, ``REPORT_SCHEMA``, plus ``LOOP_CRITERION`` and
      ``PROBE_PLUGIN``. Each default is declared here and nowhere else.
    * ``REPO`` is derived from ``__file__``, so the gate is cwd-independent.
    * ``DEFAULT_ALIASES`` re-exports the alias table path owned by
      ``framework.gates.checks.check_test_mirror`` so both gates read one file.
    * Importing this module performs no I/O and no environment lookup.
"""

from __future__ import annotations

from pathlib import Path

from framework.gates.checks import check_test_mirror as mirror

REPO = Path(__file__).resolve().parents[3]

DEFAULT_SRC = "research"

DEFAULT_TESTS = "tests/research"

DEFAULT_BASELINE = "framework/coverage_baseline.json"

DEFAULT_ALIASES = mirror.DEFAULT_ALIASES

DEFAULT_WAIVERS = "framework/loop_waivers.json"

DEFAULT_EVIDENCE = "framework/coverage_evidence.json"

BASELINE_SCHEMA = "research.coverage-baseline.v1"

EVIDENCE_SCHEMA = "research.coverage-evidence.v1"

REPORT_SCHEMA = "research.loop-coverage-report.v1"

LOOP_CRITERION = "0-1-many"

PROBE_PLUGIN = "framework.gates.coverage.coverage_probe"
