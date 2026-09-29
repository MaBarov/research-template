"""Local runtime helpers for the Slurm draining queue.

Atomic writes and file digests the queue needs, kept beside the package so the
queue can run against a bare checkout without importing the project package.

Invariants & Expected State:
    - Self-Contained: this module imports only the standard library, so a
      staged queue keeps working when no project package is importable.
    - Atomic Publishes: :func:`atomic_json_dump` publishes through an exclusive
      temporary file and fsyncs the parent directory, so a reader never sees a
      half-written record and a crash cannot leave a torn file.
    - Bounded Probes: :data:`GIT_TIMEOUT_SECONDS` is the ceiling every
      read-only git call in this package must honour.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

GIT_TIMEOUT_SECONDS: float = 60.0


def file_sha256(path: Path) -> str:
    """Return the SHA256 digest of a file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _temporary(path: Path) -> tuple[int, Path]:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    return fd, Path(name)


def _fsync_parent(path: Path) -> None:
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json_dump(path: Path, state: dict[str, Any]) -> None:
    """Atomically serialize JSON through an exclusive temporary file."""
    fd, tmp_path = _temporary(path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        _fsync_parent(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
