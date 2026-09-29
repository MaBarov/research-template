"""Behavioral tests for atomic, name-based Rope batches."""

import importlib
import json
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

pytest.importorskip("rope")
TOOL = Path(__file__).with_name("rope_refactor.py")
CODE = "def first():\n    return 3\n\ndef second():\n    return first() + 4\n"


def _tool_module(name: str):
    """Import a tool module from this directory (repository-layout agnostic)."""

    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    return importlib.import_module(name)


@pytest.fixture
def project_files(tmp_path):
    (tmp_path / "source.py").write_text(CODE)
    (tmp_path / "caller.py").write_text(
        "from source import second\nassert second() == 7\n"
    )
    return tmp_path


def _run(root, names, *extra):
    command = [sys.executable, str(TOOL), "move_globals", "--root", str(root)]
    command += "--source-file source.py --dest-file dest.py --json --names".split()
    command += [*names, *extra]
    return subprocess.run(command, capture_output=True, text=True, timeout=30)


def test_batch_resolves_shifted_lines_and_rewrites_callers(project_files):
    result = _run(project_files, ["first", "second"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"]
    assert "def first" not in (project_files / "source.py").read_text()
    assert "def second" in (project_files / "dest.py").read_text()
    executed = subprocess.run(
        [sys.executable, "caller.py"],
        cwd=project_files,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert executed.returncode == 0, executed.stderr


def test_batch_dry_run_restores_source_and_absent_destination(project_files):
    before = {p.name: p.read_bytes() for p in project_files.glob("*.py")}
    result = _run(project_files, ["first", "second"], "--dry-run")
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["dry_run"]
    assert {p.name: p.read_bytes() for p in project_files.glob("*.py")} == before


@pytest.mark.parametrize(
    "names", [["first", "absent"], ["first", "first"], ["X.method"]]
)
def test_invalid_names_leave_no_partial_moves(project_files, names):
    result = _run(project_files, names)
    assert result.returncode != 0
    assert not json.loads(result.stdout)["ok"]
    assert (project_files / "source.py").read_text() == CODE
    assert not (project_files / "dest.py").exists()


def test_destination_collision_fails_without_mutation(project_files):
    (project_files / "dest.py").write_text("first = 123\n")
    result = _run(project_files, ["first", "second"])
    assert result.returncode != 0
    assert "already binds" in result.stdout
    assert (project_files / "source.py").read_text() == CODE
    assert (project_files / "dest.py").read_text() == "first = 123\n"


def _late_failure(monkeypatch, batch):
    original = batch._move_one

    def move(project, source, destination, name, api):
        if name == "second":
            raise RuntimeError("planted second-move failure")
        return original(project, source, destination, name, api)

    monkeypatch.setattr(batch, "_move_one", move)


def test_later_rope_failure_rolls_back_earlier_move(project_files, monkeypatch):
    api = _tool_module("rope_refactor")
    _late_failure(monkeypatch, api.rope_batch)
    args = ["move_globals", "--root", str(project_files)]
    args += "--source-file source.py --dest-file dest.py --names first second --json".split()
    assert api.run(args) == 1
    assert (project_files / "source.py").read_text() == CODE
    assert not (project_files / "dest.py").exists()


def test_ignored_destination_rejected_without_creating_file(project_files):
    (project_files / "third_party").mkdir()
    result = _run(project_files, ["first"], "--dest-file", "third_party/dest.py")
    assert result.returncode != 0
    assert "ignored by Rope" in result.stdout
    assert (project_files / "source.py").read_text() == CODE
    assert not (project_files / "third_party/dest.py").exists()


class FailedChange:
    def do(self):
        raise OSError("planted apply failure")


@pytest.fixture
def history_stack(project_files):
    from rope.base.change import ChangeContents
    from rope.base.project import Project

    _preview_stack = _tool_module("rope_batch")._preview_stack

    with closing(Project(str(project_files))) as project:
        resource = project.get_file("source.py")
        project.do(ChangeContents(resource, CODE + "# existing edit\n"))
        stack = _preview_stack(project, "test")
        stack.push(ChangeContents(resource, CODE + "# preview\n"))
        yield project, resource, stack


def test_preview_apply_failure_preserves_prior_history(history_stack):
    project, resource, stack = history_stack
    previous = list(project.history.undo_list)
    with pytest.raises(OSError, match="planted"):
        stack.push(FailedChange())
    stack.pop_all()
    assert resource.read() == CODE + "# existing edit\n"
    assert project.history.undo_list == previous
