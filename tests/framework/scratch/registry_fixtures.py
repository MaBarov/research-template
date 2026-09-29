"""Scratch-checkout substrate for hook tests: a registry and its live reader.

The pre-commit hook runs the parameter gate against the *checkout it is invoked
in*, so a scratch repository used to exercise some other gate still has to carry
a loadable registry — and a reader for every row, or the usage gate (HNS042)
blocks the commit under test for the wrong reason.

Invariants & Expected State:
    - ``install_registry`` is idempotent and copies the real registry module, so
      a scratch checkout can never drift from the parameters it is testing.
    - The reader is committed by the caller as part of its baseline, so the gate
      sees it as a tracked production module.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

REGISTRY_REL = "research/params"
# The usage gate refuses a reader that lives inside the parameter package, so
# the reader sits beside the probe package instead.
READER_REL = "research/probe/read_params.py"

READER_SOURCE = (
    '"""Read every registered parameter so the usage gate sees a live reader."""\n'
    "\n"
    "from research.params import int_param, seed\n"
    "\n"
    "\n"
    "def read_all() -> tuple[int, int]:\n"
    '    return seed(), int_param("steps")\n'
)


def install_registry(root: Path) -> Path:
    """Copy the parameter package into ``root`` and add a reader for its rows."""
    source = Path(__file__).resolve().parents[3] / REGISTRY_REL
    target = root / REGISTRY_REL
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        dirs_exist_ok=True,
    )
    reader = root / READER_REL
    reader.parent.mkdir(parents=True, exist_ok=True)
    reader.write_text(READER_SOURCE, encoding="utf-8")
    _materialize_owners(root, target / "registry.py")
    return target


def _materialize_owners(root: Path, registry_path: Path) -> None:
    """Create every path the registry declares as an owner module (unmodified)."""
    spec = importlib.util.spec_from_file_location("_scratch_registry", registry_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_scratch_registry"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_scratch_registry", None)
    for parameter in module.PARAMETERS:
        for owner in parameter.owners or ():
            path = root / owner
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
