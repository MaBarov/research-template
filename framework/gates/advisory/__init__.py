"""Advisory static gates shared model and runner package.

Thumbnail: Finding model, path scoping, staged loading, report emission and CLI runner.

Invariants & Expected State:
    Package holds at most 5 modules and __init__.py carries no executable code.
"""

from __future__ import annotations

from framework.gates.advisory.model import (
    Finding,
    build_parser,
    emit,
    files_to_check,
    load_source,
    run,
    scan,
    write_report,
)

__all__ = [
    "Finding",
    "build_parser",
    "emit",
    "files_to_check",
    "load_source",
    "run",
    "scan",
    "write_report",
]
