"""Paired acceptance tests for the HNS081/HNS082 execution-sink rules.

Thumbnail: Pins the fired and clean polarities of shell injection and silent swallowing.

Invariants & Expected State:
    HNS081 fires only when a shell sink -- ``os.system`` or a ``subprocess``
    call with a literal ``shell=True`` -- receives a command string that
    interpolates unquoted data: an f-string whose formatted value is not a
    direct ``shlex.quote`` call, a ``%``-formatting, or a ``+`` concatenation
    mixing text with a non-constant.  A constant command, an argv list, and an
    f-string whose formatted value is ``shlex.quote``-wrapped stay silent.
    HNS082 fires on a bare ``except:`` or an ``except Exception``/
    ``except BaseException`` whose body is exactly one ``pass`` or one
    ``return`` of ``None``/``False``/``""`` with no logging call; a narrow
    exception family, a handler that records the failure, and any test or
    ``__init__`` path stay silent.  Each probe asserts membership of the
    targeted code, because the visitor rules legitimately fire nearby.
"""

from __future__ import annotations

from framework.gates.check_antipatterns import analyze_source

PROBE = "research/probe.py"


def _codes(source: str, path: str = PROBE) -> set[str]:
    """Return the finding codes for one Python probe."""
    return {finding.code for finding in analyze_source(source, path)}


def test_fstring_interpolation_into_shell_fires() -> None:
    """An unquoted f-string command handed to ``shell=True`` is injection."""
    source = 'import subprocess\nsubprocess.run(f"ls {target}", shell=True)\n'
    assert "HNS081" in _codes(source)


def test_concatenated_command_into_os_system_fires() -> None:
    """A ``+``-concatenated variable command into ``os.system`` is injection."""
    source = 'import os\nos.system("cat " + filename)\n'
    assert "HNS081" in _codes(source)


def test_mod_formatted_command_fires() -> None:
    """A ``%``-formatted command into ``os.system`` is injection."""
    source = 'import os\nos.system("cat %s" % filename)\n'
    assert "HNS081" in _codes(source)


def test_shlex_quoted_fstring_is_clean() -> None:
    """Quoting the formatted value removes the injection surface."""
    source = (
        "import shlex\nimport subprocess\n"
        'subprocess.run(f"ls {shlex.quote(target)}", shell=True)\n'
    )
    assert "HNS081" not in _codes(source)


def test_argv_list_is_clean() -> None:
    """An argv list never reaches a shell."""
    source = 'import subprocess\nsubprocess.run(["ls", target])\n'
    assert "HNS081" not in _codes(source)


def test_constant_command_is_clean() -> None:
    """A constant command string carries no interpolated data."""
    source = 'import subprocess\nsubprocess.run("ls -la", shell=True)\n'
    assert "HNS081" not in _codes(source)


def test_broad_except_pass_fires() -> None:
    """A broad handler whose only body is ``pass`` swallows the failure."""
    source = (
        "def run() -> None:\n    try:\n        step()\n    except Exception:\n"
        "        pass\n"
    )
    assert "HNS082" in _codes(source)


def test_bare_except_return_none_fires() -> None:
    """A bare handler returning ``None`` masks the crash."""
    source = "def run():\n    try:\n        step()\n    except:\n        return None\n"
    assert "HNS082" in _codes(source)


def test_narrow_exception_is_clean() -> None:
    """Catching the absence family is a deliberate choice, not a swallow."""
    source = (
        "def run() -> None:\n    try:\n        step()\n"
        "    except FileNotFoundError:\n        pass\n"
    )
    assert "HNS082" not in _codes(source)


def test_logged_handler_is_clean() -> None:
    """A handler that records the failure and returns is never silent."""
    source = (
        "def run():\n    try:\n        step()\n"
        "    except Exception as error:\n        logger.error(error)\n"
        "        return None\n"
    )
    assert "HNS082" not in _codes(source)


def test_test_file_is_clean() -> None:
    """The rule is scoped out of test modules."""
    source = (
        "def run():\n    try:\n        step()\n    except Exception:\n        pass\n"
    )
    assert "HNS082" not in _codes(source, "framework/tests/gates/test_foo.py")
