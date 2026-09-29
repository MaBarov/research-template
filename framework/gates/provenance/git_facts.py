"""Repository facts shared by the provenance gates.

Invariants & Expected State:
    - ``git_dirty`` is diff-based over the working tree with ``third_party``
      excluded, matching the sbatch guard's semantics.
    - Every helper only reads Git state and returns it; nothing here stages,
      writes or mutates the repository.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def git_dirty(repo: Path) -> bool:
    # diff-based (vendored third_party excluded): `git status --porcelain`
    # hard-fails on the repo's broken submodule gitdirs; vendored dirs are
    # intentionally outside provenance (same semantics as the sbatch guard).
    out = subprocess.run(
        ["git", "-C", str(repo), "diff", "--quiet", "HEAD", "--", ".", ":!third_party"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.returncode != 0


def git_commit(repo: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return out


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
