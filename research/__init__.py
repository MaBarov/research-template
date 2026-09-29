"""Example first-party package: the module tree a new project replaces.

Invariants & Expected State:
- Importing this package is side-effect free and dependency free.
- Every module here mirrors into ``tests/research/<same path>/tests_<stem>.py``;
  the mirror gate blocks an unmirrored addition at commit time.
"""

__all__: list[str] = []
