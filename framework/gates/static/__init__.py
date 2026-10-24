"""Shared plumbing for the static-analysis gates.

Thumbnail: Target selection and staged-blob reading shared by every static gate.

Invariants & Expected State:
    - The package holds no policy: each gate keeps its own findings and codes, and
      imports only the population predicate and the readers here.
    - ``sources`` is the single definition of "the static population", so two
      gates cannot disagree about which file they are willing to read.
"""

from __future__ import annotations

from framework.gates.static.sources import (
    CHECKED_SUFFIXES,
    EXCLUDED_PARTS,
    PRODUCTION_ROOTS,
    REPO,
    is_production_path,
    is_target_python,
    read_staged,
    relative_path,
)

__all__ = [
    "CHECKED_SUFFIXES",
    "EXCLUDED_PARTS",
    "PRODUCTION_ROOTS",
    "REPO",
    "is_production_path",
    "is_target_python",
    "read_staged",
    "relative_path",
]
