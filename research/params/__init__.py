"""Parameter registry and its runtime accessors (the worked example of the params rule).

Invariants & Expected State:
- This package is the single source of parameter names, defaults and accessor
  implementations; production code imports from here and never reads the
  environment directly.
- The re-exports below are imports only, so the gate that loads
  ``registry.py`` by file path sees an unchanged module surface.
"""

from research.params.registry import (
    ALIAS_TO_ENV,
    BANNED_LITERALS,
    MODEL_SNAPSHOTS,
    PARAMETERS,
    Parameter,
    by_env,
    by_name,
)
from research.params.resolve import (
    ambient,
    default,
    float_param,
    int_param,
    path_param,
    seed,
    str_param,
)

__all__ = [
    "ALIAS_TO_ENV",
    "BANNED_LITERALS",
    "MODEL_SNAPSHOTS",
    "PARAMETERS",
    "Parameter",
    "ambient",
    "by_env",
    "by_name",
    "default",
    "float_param",
    "int_param",
    "path_param",
    "seed",
    "str_param",
]
