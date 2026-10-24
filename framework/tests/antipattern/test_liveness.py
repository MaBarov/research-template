"""Paired acceptance tests for the HNS072 unbounded-loop rule.

Thumbnail: Pins HNS072's fired and clean polarities on constant-true loops.

Invariants & Expected State:
    HNS072 fires when a ``while True``/``while 1`` body reaches no ``break``,
    ``return``, ``raise`` or exit call, and stays silent on every loop whose
    termination is carried by its condition or by an exit the walk can see.
    The paired near-misses are the load-bearing half: a ``break`` inside a
    nested loop or a ``return`` inside a nested function does *not* terminate
    the candidate, while a ``break`` inside a ``try`` or an ``except`` block of
    the candidate does. Each sample is minimal so its code set is exactly
    ``{"HNS072"}`` or empty; the probe path keeps the Python analyzer in play.
"""

from __future__ import annotations

from framework.gates.check_antipatterns import analyze_source


def _codes(source: str) -> set[str]:
    """Return the finding codes for one Python probe."""
    return {finding.code for finding in analyze_source(source, "probe.py")}


def test_constant_true_loop_without_exit_fires() -> None:
    """A constant-true body with no exit is an unbounded loop."""
    assert _codes("while True:\n    count += 1\n") == {"HNS072"}


def test_integer_one_loop_without_exit_fires() -> None:
    """``while 1`` is the same shape as ``while True``."""
    assert _codes("while 1:\n    count += 1\n") == {"HNS072"}


def test_nested_loop_break_does_not_excuse() -> None:
    """A break inside a nested for leaves the outer candidate running."""
    assert _codes("while True:\n    for item in items:\n        break\n") == {"HNS072"}


def test_nested_function_return_does_not_excuse() -> None:
    """A return inside a nested function runs in a different frame."""
    source = "while True:\n    def inner() -> int:\n        return 1\n"
    assert _codes(source) == {"HNS072"}


def test_break_inside_try_is_clean() -> None:
    """A break inside the candidate's own try/except terminates it."""
    source = (
        "while True:\n    try:\n        step()\n    except OSError:\n        break\n"
    )
    assert _codes(source) == set()


def test_break_terminates() -> None:
    """A direct break is an exit."""
    assert _codes("while True:\n    break\n") == set()


def test_return_terminates() -> None:
    """A return in the candidate's own frame is an exit."""
    assert _codes("def run() -> int:\n    while True:\n        return 1\n") == set()


def test_raise_terminates() -> None:
    """A raise in the candidate body is an exit."""
    assert _codes("while True:\n    raise RuntimeError('stop')\n") == set()


def test_sys_exit_terminates() -> None:
    """An explicit sys.exit call is an exit."""
    assert _codes("import sys\nwhile True:\n    sys.exit(1)\n") == set()


def test_condition_bound_loop_stays_silent() -> None:
    """A comparison test is never a candidate."""
    assert _codes("while running:\n    pass\n") == set()
