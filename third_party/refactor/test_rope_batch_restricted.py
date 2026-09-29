"""Tests for the name-bearing resource restriction (local Research patch)."""

from __future__ import annotations

import importlib
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

pytest.importorskip("rope")


def _tool_module(name: str):
    """Import a tool module from this directory (repository-layout agnostic)."""

    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    return importlib.import_module(name)


class _File:
    def __init__(self, name: str, text: str, unreadable: bool = False) -> None:
        self.name = name
        self._text = text
        self._unreadable = unreadable

    def read(self) -> str:
        if self._unreadable:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "planted")
        return self._text


class _Project:
    def __init__(self, files) -> None:
        self._files = list(files)

    def get_python_files(self):
        return list(self._files)


def test_name_bearing_resources_keep_source_and_destination():
    batch = _tool_module("rope_batch")
    mention = _File("probe.py", "ratio_median = _median(ratios)\n")
    unrelated = _File("other.py", "value = 1\n")
    unreadable = _File("blob.py", "", unreadable=True)
    source = _File("src.py", '"""source"""\n')
    destination = _File("stages.py", '"""destination"""\n')

    picked = batch._name_bearing_resources(
        _Project([mention, unrelated, unreadable]), source, destination, "_median"
    )

    assert mention in picked
    assert source in picked
    assert destination in picked
    assert unreadable in picked
    assert unrelated not in picked


def _fixture(root: Path) -> None:
    (root / "source.py").write_text("def helper():\n    return 3\n")
    (root / "caller.py").write_text(
        "from source import helper\nassert helper() == 3\n"
    )
    (root / "dest.py").write_text('"""Destination."""\n')


def _run_tool(root: Path) -> subprocess.CompletedProcess:
    api = _tool_module("rope_refactor")
    args = ["move_globals", "--root", str(root)]
    args += "--source-file source.py --dest-file dest.py --names helper --json".split()
    return api.run(args)


def test_restricted_batch_moves_symbol_and_keeps_caller_working(tmp_path):
    _fixture(tmp_path)

    assert _run_tool(tmp_path) == 0

    assert "def helper" not in (tmp_path / "source.py").read_text()
    assert "def helper" in (tmp_path / "dest.py").read_text()
    executed = subprocess.run(
        [sys.executable, "caller.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert executed.returncode == 0, executed.stderr


def test_restricted_batch_matches_wide_scan_output(tmp_path):
    from rope.base.project import Project
    from rope.refactor.move import MoveGlobal

    restricted = tmp_path / "restricted"
    wide = tmp_path / "wide"
    for root in (restricted, wide):
        root.mkdir()
        _fixture(root)

    assert _run_tool(restricted) == 0

    with closing(Project(str(wide))) as project:
        source = project.get_file("source.py")
        destination = project.get_file("dest.py")
        offset = source.read().index("helper")
        project.do(MoveGlobal(project, source, offset).get_changes(destination))

    for name in ("source.py", "caller.py", "dest.py"):
        assert (restricted / name).read_bytes() == (wide / name).read_bytes(), name
