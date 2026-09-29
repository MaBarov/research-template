"""Mutation gate CLI: refresh and verify cleared mutmut evidence for staged files.

Invariants & Expected State:
 * ``--mode staged`` scopes to the staged modules inside ``[tool.mutmut]``
   ``only_mutate``; files outside that population are not the gate's business.
 * ``--evidence-only`` never runs mutmut: it decides from
   ``framework/mutation_evidence.json`` and the Git index, so the pre-commit
   hook stays sub-second.
 * A refresh re-scores through mutmut itself and refuses to record anything when
   the working tree differs from the index, so evidence always describes the
   bytes a commit would carry.
 * There is no skip flag, no environment variable and no warn-only path:
   findings always exit 1. ``--strict`` is accepted for hook symmetry only.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework.gates.mutation import evidence, scoring

FINDING_PREFIX = evidence.FINDING_PREFIX


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Command line for the mutation gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("staged",), default="staged")
    parser.add_argument("--staged", nargs="+", required=True, metavar="FILE")
    parser.add_argument("--evidence-only", action="store_true")
    parser.add_argument("--strict", action="store_true", help="accepted; always strict")
    parser.add_argument("--jobs", type=int, default=8)
    return parser.parse_args(argv)


def _worktree_matches_index(rel: str) -> str | None:
    """None when the working file equals the staged blob, else the reason."""
    staged = evidence.staged_bytes(rel)
    if staged is None:
        return f"{FINDING_PREFIX} {rel}: not in the index (git add it first)"
    working = evidence.REPO / rel
    if not working.is_file():
        return f"{FINDING_PREFIX} {rel}: missing from the working tree"
    if working.read_bytes() != staged:
        return (
            f"{FINDING_PREFIX} {rel}: the working tree differs from the index — stage "
            "the content you want scored (git add), then refresh"
        )
    return None


def _module_entry(
    rel: str, version: str, statuses: Mapping[str, str]
) -> dict[str, Any]:
    """One ledger entry: content address, tool version, counts and offender names."""
    entry: dict[str, Any] = {
        "content_sha256": evidence.staged_sha256(rel),
        "mutmut_version": version,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    entry.update(scoring.aggregate(statuses))
    for status, names in scoring.names_by_status(statuses).items():
        entry[f"{status}_names"] = names
    return entry


def _score(jobs: int) -> tuple[str | None, int]:
    """Run mutmut over the population; returns its version and process exit code."""
    version, error = scoring.mutmut_version()
    if version is None:
        print(f"{FINDING_PREFIX} {error}", file=sys.stderr)
        return None, 1
    print(f"{FINDING_PREFIX} scoring with {version}; mutmut output follows", flush=True)
    try:
        return version, scoring.run_mutmut(jobs)
    except subprocess.TimeoutExpired:
        print(f"{FINDING_PREFIX} mutmut exceeded its wall-clock bound", file=sys.stderr)
        return None, 1


def _write_ledger(version: str, entries: Mapping[str, Any]) -> str | None:
    """Merge fresh entries into the ledger; returns the reason on failure."""
    population, error = evidence.config_population()
    if population is None:
        return error
    ledger = evidence.load_ledger()
    modules: dict[str, Any] = dict(ledger.get("modules") or {})
    modules.update(entries)
    ledger.update(
        {
            "schema": evidence.SCHEMA,
            "population": population,
            "mutmut_version": version,
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "modules": modules,
        }
    )
    evidence.save_ledger(ledger)
    return None


def _refresh(args: argparse.Namespace, scoped: Sequence[str]) -> int:
    """Re-score the staged modules and record their entries in the ledger."""
    problems = [reason for rel in scoped if (reason := _worktree_matches_index(rel))]
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    version, returncode = _score(args.jobs)
    if version is None or returncode != 0:
        print(
            f"{FINDING_PREFIX} mutmut scoring failed (exit {returncode})",
            file=sys.stderr,
        )
        return 1
    entries: dict[str, Any] = {}
    for rel in scoped:
        statuses, error = scoring.collect_statuses(rel)
        if error is not None:
            print(f"{FINDING_PREFIX} {rel}: {error}", file=sys.stderr)
            return 1
        entries[rel] = _module_entry(rel, version, statuses)
    written = _write_ledger(version, entries)
    if written is not None:
        print(written, file=sys.stderr)
        return 1
    print(f"{FINDING_PREFIX} recorded evidence for {len(entries)} module(s)")
    return _report(evidence.staged_findings(scoped))


def _report(findings: Sequence[str]) -> int:
    """Print findings with the exact remedy, or the pass line."""
    if not findings:
        print(f"{FINDING_PREFIX} PASS: staged modules carry cleared evidence")
        return 0
    for finding in findings:
        print(finding, file=sys.stderr)
    print(
        f"{FINDING_PREFIX} refresh: {evidence.REFRESH_HINT} <files>; then "
        f"git add {evidence.LEDGER_NAME} <files>",
        file=sys.stderr,
    )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Decide from the ledger, or refresh it, for the staged population."""
    args = parse_args(argv)
    scoped, error = evidence.scoped_paths(args.staged)
    if error is not None:
        print(error, file=sys.stderr)
        return 1
    if args.evidence_only:
        findings = evidence.staged_findings(scoped)
        if not findings and not scoped:
            return 0
        return _report(findings)
    if not scoped:
        return 0
    return _refresh(args, scoped)


if __name__ == "__main__":
    raise SystemExit(main())
