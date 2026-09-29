"""Command-line interface for the framework Table-of-Contents indexer.

Role & Architecture:
    Provides CLI entrypoint for generating indices, verifying freshness, and
    enforcing Two-Tier docstring contracts in pre-commit and CI gates.

Invariants & Expected State:
    - Default Subtrees: Targets research, framework, experiments, and scripts.
    - Atomic Exit Codes: Returns 0 on success/pass, 1 on out-of-sync or contract failure.
    - Path Resolution: Normalizes output paths relative to repository root.

Failure Modes & Prohibited Patterns:
    - Invalid arguments raise SystemExit via standard argparse.
    - Prohibited: Never bypass repository root boundary during indexing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework import harness
from framework.indexing.gate import run_index_gate

DEFAULT_ROOTS = tuple(harness.INDEX_ROOTS)


def _add_contract_arguments(parser: argparse.ArgumentParser) -> None:
    """Register contract verification flags on the argument parser."""
    parser.add_argument(
        "--strict-contracts",
        action="store_true",
        help="Enforce Two-Tier docstring contracts and fail on missing invariants or drift.",
    )
    parser.add_argument(
        "--staged-files",
        nargs="*",
        default=None,
        help="Specific staged files to scope contract and drift validation to.",
    )


def _add_index_arguments(parser: argparse.ArgumentParser) -> None:
    """Register index generation and freshness flags on the argument parser."""
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("INDEX.md"),
        help="Path to output Markdown index file (default: INDEX.md).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the existing index is in sync rather than overwriting.",
    )
    parser.add_argument(
        "--roots",
        nargs="+",
        default=list(DEFAULT_ROOTS),
        help=f"Subtrees to index (default: {' '.join(DEFAULT_ROOTS)}).",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=600,
        help="Maximum lines before splitting into sub-indices (default: 600).",
    )
    parser.add_argument(
        "--no-split",
        action="store_true",
        help="Force a single consolidated index file regardless of size.",
    )


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register command line arguments on the argument parser."""
    _add_index_arguments(parser)
    _add_contract_arguments(parser)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments for the repository indexer."""
    parser = argparse.ArgumentParser(
        description="Generate or verify the codebase Table-of-Contents index."
    )
    _add_arguments(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for python -m framework.indexing."""
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    index_path = args.output
    if not index_path.is_absolute():
        index_path = repo_root / index_path
    max_lines = sys.maxsize if args.no_split else args.max_lines
    return run_index_gate(
        repo_root=repo_root,
        index_path=index_path,
        roots=tuple(args.roots),
        max_lines=max_lines,
        check_only=args.check,
        strict_contracts=args.strict_contracts,
        staged_files=args.staged_files,
    )


if __name__ == "__main__":
    sys.exit(main())
