"""Expected behavior for the local gate's undefined-name audit.

The audit resolves a Name load against its enclosing scope chain, so a binding
introduced by a statement must be visible in that scope. ``except E as err``
binds ``err`` for the handler body at module level exactly as it does inside a
function; missing that binding reported a used, defined name as undefined.
"""

from __future__ import annotations

import ast

from framework.gates.checks.local_gate import check_undefined, module_candidates

_EXCEPT_AS = """
try:
    import package
except ImportError as err:
    raise ImportError("install the extra") from err
"""

_EXCEPT_AS_IN_FUNCTION = """
def load():
    try:
        import package
    except ImportError as err:
        return err
    return None
"""

_UNDEFINED = """
def load():
    return missing_symbol
"""


def _undefined(source: str) -> list[str]:
    tree = ast.parse(source)
    return check_undefined(tree, module_candidates(tree))


def test_a_module_level_except_binding_is_not_undefined() -> None:
    assert _undefined(_EXCEPT_AS) == []


def test_a_function_except_binding_is_not_undefined() -> None:
    assert _undefined(_EXCEPT_AS_IN_FUNCTION) == []


def test_a_truly_undefined_name_is_still_reported() -> None:
    assert _undefined(_UNDEFINED) == ["undefined name 'missing_symbol' (line 3)"]
