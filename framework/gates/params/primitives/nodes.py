"""AST and text primitives with no registry state.

Invariants & Expected State:
    - Every helper here is pure: it reads only its arguments, never a module
      global, so a matcher can move between modules without changing behaviour.
    - Lexical helpers never import the ``research`` package or torch.
"""
