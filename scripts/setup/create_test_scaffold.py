#!/usr/bin/env python3
"""Create a mirrored, tests_-prefixed scaffold for the project Python package.

Invariants & Expected State:
    - Harness Defaults: the source package and mirror root default to the
      harness's ``SLUG`` and ``MIRROR_ROOT``, so the scaffold tracks the project
      identity without restating it.
    - No Production Copies: every scaffold is an empty tests_-prefixed stub; the
      tool never copies implementation text.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework import harness


def _scaffold_text(module_name: str) -> str:
    return (
        f'"""Test scaffold for ``{module_name}``."""\n\n'
        "from __future__ import annotations\n\n"
        "# Add focused tests for this module here. This scaffold intentionally\n"
        "# contains no copied production implementation.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=Path(harness.SLUG))
    parser.add_argument("--destination", type=Path, default=Path(harness.MIRROR_ROOT))
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    if not source.is_dir():
        raise SystemExit(f"source package does not exist: {source}")

    created = 0
    for source_file in sorted(source.rglob("*.py")):
        relative = source_file.relative_to(source)
        target = destination / relative.parent / f"tests_{relative.name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            _scaffold_text(".".join(relative.with_suffix("").parts)),
            encoding="utf-8",
        )
        created += 1

    print(f"Created {created} test scaffolds under {destination}")


if __name__ == "__main__":
    main()
