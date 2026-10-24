"""Paired acceptance tests for the HNS067 and HNS069 fallthrough rules.

Thumbnail: Pins both polarities of the positional-response and dead-guard rules.

Invariants & Expected State:
    ``analyze_source`` picks an analyzer from the path suffix, so every sample
    below is judged as a ``.py`` module.  HNS067 names a subscript whose *value*
    is a response-shaped accessor -- an attribute named ``choices``/``content``/
    ``parts`` or a mapping lookup keyed by those names -- and whose index is the
    constant ``0``; that shape breaks when a thinking block precedes the output
    or a choice list comes back empty, because position no longer identifies the
    block.  HNS069 names an ``if``/``while`` whose test is a never-true constant
    (``False``/``None``/``0``), the guard-and-go shape that keeps removed code
    alive instead of deleting it.  Each trigger has a paired near-miss that must
    stay clean: ordinary list indexing, iteration over the same collections and
    ordinary branching are legitimate.  Assertions name the targeted code alone,
    because a sample may legitimately raise unrelated hygiene codes.
"""

from __future__ import annotations

from framework.gates.check_antipatterns import analyze_source

_MODULE = "probe.py"


def _codes(source: str) -> set[str]:
    return {finding.code for finding in analyze_source(source, _MODULE)}


def test_choices_index_zero_flagged() -> None:
    source = "def get_text(resp):\n    return resp.choices[0].message.content\n"
    assert "HNS067" in _codes(source)


def test_content_index_zero_flagged() -> None:
    source = "def get_content(msg):\n    return msg.content[0].text\n"
    assert "HNS067" in _codes(source)


def test_dict_choices_index_zero_flagged() -> None:
    source = 'def get_reply(data):\n    return data["choices"][0]["message"]\n'
    assert "HNS067" in _codes(source)


def test_generic_index_zero_clean() -> None:
    source = "def first_item(items):\n    return items[0]\n"
    assert "HNS067" not in _codes(source)


def test_iteration_over_choices_clean() -> None:
    source = (
        "def get_text(resp):\n    return [c.message.content for c in resp.choices]\n"
    )
    assert "HNS067" not in _codes(source)


def test_blocks_parts_index_zero_flagged() -> None:
    source = "def get_block(blocks):\n    return blocks.parts[0].text\n"
    assert "HNS067" in _codes(source)


def test_dict_get_choices_index_zero_flagged() -> None:
    source = 'def get_reply(resp):\n    return resp.get("choices", [])[0]\n'
    assert "HNS067" in _codes(source)


def test_self_path_parts_clean() -> None:
    source = "class Record:\n    def part(self):\n        return self.path.parts[0]\n"
    assert "HNS067" not in _codes(source)


def test_path_constructor_parts_clean() -> None:
    source = (
        "from pathlib import Path\n\n"
        "def first_part():\n"
        '    return Path("a/b").parts[0]\n'
    )
    assert "HNS067" not in _codes(source)


def test_getattr_choices_index_zero_flagged() -> None:
    source = 'def get_text(resp):\n    return getattr(resp, "choices")[0]\n'
    assert "HNS067" in _codes(source)


def test_getattr_content_index_zero_flagged() -> None:
    source = 'def get_content(msg):\n    return getattr(msg, "content")[0]\n'
    assert "HNS067" in _codes(source)


def test_getattr_other_index_zero_clean() -> None:
    source = 'def first_other(obj):\n    return getattr(obj, "other")[0]\n'
    assert "HNS067" not in _codes(source)


def test_hns069_flags_if_false() -> None:
    source = "def f():\n    if False:\n        old_code()\n"
    assert "HNS069" in _codes(source)


def test_hns069_flags_if_zero() -> None:
    source = "def f():\n    if 0:\n        old_code()\n"
    assert "HNS069" in _codes(source)


def test_hns069_flags_while_false() -> None:
    source = "def f():\n    while False:\n        old_code()\n"
    assert "HNS069" in _codes(source)


def test_hns069_accepts_normal_branching() -> None:
    source = "def f(x):\n    if not x:\n        return None\n"
    assert "HNS069" not in _codes(source)
