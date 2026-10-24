"""CLI entry point of the static-type gate (mypy blocking, pyright census).

Thumbnail: staged mypy enforcement over the static roots.

Invariants & Expected State:
    * ``--mode staged`` checks exactly the staged or explicitly listed modules; a
      missing checker fails closed under ``--strict`` and only NOTEs otherwise.
    * ``--staged`` checks a drifted module as its staged blob (mypy
      ``--shadow-file``), so the decision is what the commit writes while partial
      staging stays legal; an unreadable blob is never reported clean.
    * ``--mode all`` is the census: per-tree counts and the worst files, blocking
      only when ``--strict`` is also given (the debt meter).
    * A named file list is answered per path: every path outside the population is
      reported as ``out of scope`` with its reason, and a list whose every entry is
      out of scope fails closed (exit 1) rather than skipping silently; an unnamed
      run over an empty Git index is a benign skip (exit 0) that says nothing was
      staged.
    * Foreign findings never block: mypy runs with ``--follow-imports=silent`` and
      every finding is filtered to the caller's scope set.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework.gates.typecheck import policy, report, runner
from framework.gates.typecheck.runner import CheckerMissing


def build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser of the type gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("staged", "all"), default="staged")
    parser.add_argument("--engine", choices=("mypy", "pyright"), default="mypy")
    parser.add_argument(
        "--staged",
        action="store_true",
        help="the file list came from the Git index; check staged blobs",
    )
    parser.add_argument("--strict", action="store_true", help="fail on findings")
    parser.add_argument("--report", type=Path, help="write JSON findings report")
    parser.add_argument("files", nargs="*", help="paths, defaulting to the Git index")
    return parser


def selection(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    """Return the modules to check and a decline note per named out-of-scope path."""
    if args.mode == "all":
        return policy.typed_sources(), []
    if args.files:
        modules, declined = policy.select_paths_detailed(args.files)
        return modules, [f"{path}: {reason}" for path, reason in declined]
    return policy.index_selection(), []


def invoke(args: argparse.Namespace, modules: list[str]) -> runner.RunResult | None:
    """Run the engine; on a missing checker print the hint and return ``None``."""
    scoped = {policy.relative(path) for path in modules}
    try:
        return runner.run(args.engine, modules, scoped, staged=args.staged)
    except CheckerMissing as missing:
        print(f"[check_types] NOTE: {missing}; {missing.hint}", file=sys.stderr)
        return None


def emit(args: argparse.Namespace, result: runner.RunResult, checked: int) -> int:
    """Print one run's findings and census, then return its exit code."""
    if args.mode == "all":
        for line in report.census_lines(result.findings, checked):
            print(line, file=sys.stderr)
    for path in result.shadowed:
        print(
            f"[check_types] {path}: checking the staged blob (the working tree "
            "moved on after staging)",
            file=sys.stderr,
        )
    report.print_findings(result.findings)
    for line in result.unparsed:
        print(f"[check_types] unparsed: {line}", file=sys.stderr)
    if args.report:
        report.write_report(args.report, result.findings)
    print(
        f"[check_types] {result.engine} checked {checked} module(s), "
        f"{len(result.findings)} finding(s), rc={result.returncode}",
        file=sys.stderr,
    )
    blocking = bool(result.findings) or bool(result.unparsed) or result.returncode == 2
    return 1 if (args.strict and blocking) else 0


def main(argv: list[str] | None = None) -> int:
    """Execute the type gate and return its exit code."""
    args = build_parser().parse_args(argv)
    modules, declined = selection(args)
    for note in declined:
        print(f"[check_types] out of scope: {note}", file=sys.stderr)
    if not modules:
        if declined:
            print(
                f"[check_types] FAILED: none of the {len(declined)} named path(s) "
                "belongs to the typed population (see 'out of scope' above).",
                file=sys.stderr,
            )
            return 1
        print(
            "[check_types] no module in scope: nothing staged and no paths named",
            file=sys.stderr,
        )
        return 0
    result = invoke(args, modules)
    if result is None:
        return 1 if args.strict else 0
    return emit(args, result, len(modules))


if __name__ == "__main__":
    sys.exit(main())
