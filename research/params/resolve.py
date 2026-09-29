"""Runtime accessors for the canonical registry: the only way code reads a value.

Invariants & Expected State:
- Every accessor resolves at call time: the registry env var when it is set, else
  the registry default. Nothing here caches, so a test may set and unset the
  environment around a call.
- The module is stdlib-only: the parameter gate parses it to prove that every
  accessor a registry row declares exists here.
- ``ambient`` is the single escape hatch that reports the raw environment value
  (or ``None``); callers that need to know whether a value was overridden use it
  instead of reading the environment themselves.
"""

from __future__ import annotations

import os
from pathlib import Path

from research.params.registry import by_name


def default(name: str) -> str:
    """Return the registry default of ``name``, ignoring the environment."""

    return by_name(name).default


def ambient(name: str) -> str | None:
    """Return the raw environment value of ``name``, or ``None`` when unset."""

    parameter = by_name(name)
    if parameter.env is None:
        return None
    return os.environ.get(parameter.env)


def str_param(name: str) -> str:
    """Return the string value of ``name``: environment first, default second."""

    return ambient(name) or default(name)


def int_param(name: str) -> int:
    """Return the integer value of ``name``."""

    return int(str_param(name))


def float_param(name: str) -> float:
    """Return the float value of ``name``."""

    return float(str_param(name))


def path_param(name: str) -> Path:
    """Return the filesystem path value of ``name``, expanded."""

    return Path(str_param(name)).expanduser()


def seed() -> int:
    """Return the registered run seed."""

    return int_param("seed")
