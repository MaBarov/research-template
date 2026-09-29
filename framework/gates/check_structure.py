#!/usr/bin/env python3
"""Experimental layout contract checker (advisory by default, exit 1 with --strict).

Enforces the repo's de-facto layout without renaming anything:
- .py sources belong in experiments/e{1,2,3}/, scripts/, tests/, or experiment tests/
- test files must match test_*.py
- modules with public functions should have a sibling test (informational)
- results/ only accepts whitelisted artifact extensions

Invariants & Expected State:
- Classification is by path shape: a flat `.py` file under `framework/` is
  accepted only when `FRAMEWORK_TOP_OK` names it, so new framework code belongs
  in a `framework/<area>/` subpackage alongside its peers.
- `README.md` and `.gitkeep` are accepted anywhere; test-file naming is judged
  only for paths containing a `tests` segment.
- The gate never renames, moves or stages anything: it reports a violation and
  its remedy and leaves the tree untouched.
- Findings are advisory without `--strict`; the pre-commit hook invokes it
  advisory, so a `FRAMEWORK LOCK` line alone never blocks a commit.

Usage:
  python scripts/check_structure.py [--staged FILE...] [--strict]
Exit 0 = layout clean; 1 = violations (with --strict) or warnings-only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework import harness

# framework/ holds the harness itself: one flat module plus subpackages. A new
# flat .py file at framework/ top level is a violation; new gates and tooling
# live in a framework/<area>/ subpackage next to their peers.
FRAMEWORK_TOP_OK = {"__init__.py", "harness.py"}
RESULTS_OK = {
    ".json",
    ".jsonl",
    ".log",
    ".sbatch",
    ".png",
    ".jpg",
    ".jpeg",
    ".csv",
    ".safetensors",
    ".npy",
    ".npz",
    ".txt",
    ".md",
    ".gz",
    ".webp",
    ".gif",
    ".pt",
    ".bin",
    ".html",
    ".tex",
}
TEST_RE = re.compile(r"tests?_.*\.py$")
FIXTURE_RE = re.compile(r"(?:__init__|.*fixtures?|.*_fixtures)\.py$")
README_RE = re.compile(r"(?:readme|00_README)\.md$", re.IGNORECASE)
GITKEEP_RE = re.compile(r"^\.gitkeep$")


def classify(path: Path, rel: str) -> str | None:
    parts = rel.split("/")
    if path.name and (README_RE.match(path.name) or GITKEEP_RE.match(path.name)):
        return None  # README/.gitkeep allowed anywhere
    if (
        parts[0] == "framework"
        and len(parts) == 2
        and path.suffix == ".py"
        and path.name not in FRAMEWORK_TOP_OK
    ):
        return (
            f"FRAMEWORK LAYOUT: {rel} → framework/ top level holds only "
            f"{sorted(FRAMEWORK_TOP_OK)}; new code goes in a subpackage"
        )
    if parts[0] == "experiments" and path.name == "__init__.py" and len(parts) == 2:
        return None  # experiments/__init__.py makes experiments a package (namespaced imports)
    if (
        path.suffix == ".py"
        and "tests" in parts
        and not TEST_RE.match(path.name)
        and not FIXTURE_RE.match(path.name)
    ):
        return f"BAD TEST NAME: {rel} → must match test_*.py or tests_*.py (or be a fixture)"
    if parts[0] == "results" and path.suffix not in RESULTS_OK:
        return f"FORBIDDEN RESULTS EXT: {rel} → whitelist {sorted(RESULTS_OK)}"


def module_needs_test(rel: str, text: str) -> bool:
    if not rel.startswith("experiments/") or not rel.endswith(".py"):
        return False
    if "tests" in rel.split("/"):
        return False
    has_public = bool(re.search(r"^def [a-z]", text, re.MULTILINE))
    return has_public


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staged", nargs="*", help="files to check (staged set)")
    ap.add_argument("--strict", action="store_true", help="exit non-zero on violations")
    ap.add_argument(
        "--informal-tests",
        action="store_true",
        help="report untested modules (non-blocking)",
    )
    return ap.parse_args()


def _collect_files(staged: list[str] | None) -> list[Path]:
    if staged:
        return [
            REPO / f
            for f in staged
            if f.endswith((".py", ".sbatch")) or "/results/" in f
        ]
    files: list[Path] = []
    for sub in (*harness.INDEX_ROOTS, harness.TEST_ROOT, "results"):
        d = REPO / sub
        if d.exists():
            files.extend(p for p in d.rglob("*") if p.is_file())
    return files


def _is_untested_module(p: Path, rel: str) -> bool:
    if p.suffix != ".py" or not module_needs_test(rel, p.read_text(errors="ignore")):
        return False
    test_dir = p.parent / "tests"
    if not test_dir.exists():
        return True
    return not (
        (test_dir / f"test_{p.stem}.py").exists()
        or any(
            t.name.startswith("test_") and p.stem in t.read_text(errors="ignore")
            for t in test_dir.glob("test_*.py")
        )
    )


def _audit_files(
    files: list[Path], informal_tests: bool
) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    untested: list[str] = []
    for p in files:
        rel = p.relative_to(REPO).as_posix()
        if any(seg in rel for seg in ("__pycache__", ".git/", "third_party/")):
            continue
        v = classify(p, rel)
        if v:
            violations.append(v)
        if informal_tests and _is_untested_module(p, rel):
            untested.append(f"UNTESTED MODULE: {rel}")
    return violations, untested


def main() -> int:
    args = _parse_args()
    files = _collect_files(args.staged)
    violations, untested = _audit_files(files, args.informal_tests)

    for v in violations:
        print(f"[check_structure] {v}", file=sys.stderr)
    for u in untested:
        print(f"[check_structure] {u}", file=sys.stderr)

    if args.strict and violations:
        print(
            f"[check_structure] STRICT FAIL: {len(violations)} violation(s)",
            file=sys.stderr,
        )
        return 1
    print(
        f"[check_structure] ok: {len(files)} files checked, {len(violations)} violations, {len(untested)} untested (informational)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
