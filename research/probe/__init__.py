"""Example production package: a dependency-free plan builder.

Invariants & Expected State:
- Tunables are read only through ``research.params``, so the parameter gate sees
  every registry row as read and no default is restated in this package.
- ``build_plan`` is pure and deterministic: the same settings yield the same
  plan, ordered by step index.
"""

__all__: list[str] = []
