"""Mutation gate CLI: refresh and verify cleared mutmut evidence for staged files.

Invariants & Expected State:
 * ``--mode staged`` scopes to the staged modules inside ``[tool.mutmut]``
   ``only_mutate``; files outside that population are not the gate's business.
 * ``--evidence-only`` never runs mutmut: it decides from
   ``framework/mutation_evidence.json`` and the Git index, so the pre-commit
   hook stays sub-second.
 * A refresh re-scores through mutmut itself under an exclusive per-repository
   lock, and refuses to record anything unless the staged sources, the staged
   test surface and the working test bytes all stayed put across the run, so
   evidence always describes the bytes a commit would carry.
 * A refresh records the digest of the test surface it scored against and drops
   mutmut's own verdict cache when that digest moved, so a verdict cached
   against older tests can neither be recorded nor believed.
 * A ``# pragma: no mutate`` line added by the staged blob is reported as a
   NOTE, never as a verdict: mutmut generates no mutant there, so the ledger
   records nothing and the equivalence claim lives only on that line.
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
    rel: str, version: str, statuses: Mapping[str, str], tests_sha256: str
) -> dict[str, Any]:
    """One ledger entry: content address, test surface, version and counts."""
    entry: dict[str, Any] = {
        "content_sha256": evidence.staged_sha256(rel),
        "tests_sha256": tests_sha256,
        "mutmut_version": version,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    entry.update(scoring.aggregate(statuses))
    for status, names in scoring.names_by_status(statuses).items():
        entry[f"{status}_names"] = names
    return entry


def _score(jobs: int, tests_sha256: str) -> tuple[str | None, int]:
    """Run mutmut over the population; returns its version and process exit code."""
    version, error = scoring.mutmut_version()
    if version is None:
        print(f"{FINDING_PREFIX} {error}", file=sys.stderr)
        return None, 1
    dropped = scoring.prepare_cache(tests_sha256)
    if dropped is not None:
        print(f"{FINDING_PREFIX} {dropped}", flush=True)
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
    try:
        with scoring.refresh_lock():
            return _scored_refresh(args, scoped)
    except scoring.RefreshBusy as busy:
        print(f"{FINDING_PREFIX} {busy}", file=sys.stderr)
        return 1


def _moved_reason(
    before_tests: str, before_shas: Mapping[str, str | None], scoped: Sequence[str]
) -> str | None:
    """Why the tree moved during the run, or None when the scored bytes survived."""
    if evidence.tests_sha256() != before_tests:
        return (
            f"{FINDING_PREFIX} the test surface moved during the refresh — the "
            "verdicts describe tests the commit would not carry; re-run the refresh"
        )
    moved = [rel for rel in scoped if evidence.staged_sha256(rel) != before_shas[rel]]
    if moved:
        return (
            f"{FINDING_PREFIX} staged content moved during the refresh "
            f"({moved[0]}); re-run the refresh so evidence matches the commit"
        )
    return None


def _collect_entries(
    version: str, scoped: Sequence[str], tests_sha256: str
) -> dict[str, Any] | None:
    """One ledger entry per scoped module, or None after printing the failure."""
    entries: dict[str, Any] = {}
    for rel in scoped:
        statuses, error = scoring.collect_statuses(rel)
        if error is not None:
            print(f"{FINDING_PREFIX} {rel}: {error}", file=sys.stderr)
            return None
        entries[rel] = _module_entry(rel, version, statuses, tests_sha256)
    return entries


def _scored_refresh(args: argparse.Namespace, scoped: Sequence[str]) -> int:
    """Score under the lock; record only when nothing moved in the meantime."""
    drift = evidence.tests_drift_reason()
    if drift is not None:
        print(drift, file=sys.stderr)
        return 1
    before_tests = evidence.tests_sha256()
    before_shas = {rel: evidence.staged_sha256(rel) for rel in scoped}
    version, returncode = _score(args.jobs, before_tests)
    if version is None or returncode != 0:
        print(
            f"{FINDING_PREFIX} mutmut scoring failed (exit {returncode})",
            file=sys.stderr,
        )
        return 1
    moved = _moved_reason(before_tests, before_shas, scoped)
    if moved is not None:
        print(moved, file=sys.stderr)
        return 1
    entries = _collect_entries(version, scoped, before_tests)
    if entries is None:
        return 1
    written = _write_ledger(version, entries)
    if written is not None:
        print(written, file=sys.stderr)
        return 1
    print(f"{FINDING_PREFIX} recorded evidence for {len(entries)} module(s)")
    return _report(evidence.staged_findings(scoped), evidence.pragma_notes(scoped))


def _report(findings: Sequence[str], notes: Sequence[str] = ()) -> int:
    """Print findings with the exact remedy, or the pass line plus any NOTE."""
    for note in notes:
        print(note, file=sys.stderr)
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
