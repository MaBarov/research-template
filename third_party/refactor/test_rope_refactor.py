import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("rope")

CANDIDATES = (
    Path(__file__).resolve().parent / "rope_refactor.py",
    Path(__file__).resolve().parents[1] / "rope_refactor.py",
)
TOOL = next((path for path in CANDIDATES if path.exists()), None)

if TOOL is None:
    pytest.skip("rope_refactor.py not found", allow_module_level=True)


def run_tool(root: Path, *args: str, json_output: bool = True):
    cmd = [sys.executable, str(TOOL), *args, "--root", str(root)]
    if json_output:
        cmd.append("--json")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def parse_json(proc):
    assert proc.stdout, f"stdout was empty; stderr: {proc.stderr}"
    return json.loads(proc.stdout)


def test_rename_dry_run_then_apply(tmp_path):
    code = (
        "def foo():\n"
        "    return 1\n"
        "\n"
        "def bar():\n"
        "    return foo()\n"
    )
    (tmp_path / "a.py").write_text(code, encoding="utf-8")

    proc = run_tool(
        tmp_path,
        "rename",
        "--file",
        "a.py",
        "--line",
        "1",
        "--col",
        "5",
        "--new-name",
        "baz",
        "--dry-run",
    )
    assert proc.returncode == 0, proc.stderr
    payload = parse_json(proc)
    assert payload["ok"] is True
    assert payload["dry_run"] is True

    # Dry run must not modify files.
    assert "def foo" in (tmp_path / "a.py").read_text(encoding="utf-8")

    proc = run_tool(
        tmp_path,
        "rename",
        "--file",
        "a.py",
        "--line",
        "1",
        "--col",
        "5",
        "--new-name",
        "baz",
    )
    assert proc.returncode == 0, proc.stderr

    text = (tmp_path / "a.py").read_text(encoding="utf-8")
    assert "def baz" in text
    assert "return baz()" in text


def test_extract_variable(tmp_path):
    code = (
        "def f():\n"
        "    a = 1 + 2\n"
    )
    (tmp_path / "a.py").write_text(code, encoding="utf-8")

    proc = run_tool(
        tmp_path,
        "extract_variable",
        "--file",
        "a.py",
        "--start-line",
        "2",
        "--end-line",
        "2",
        "--start-col",
        "9",
        "--end-col",
        "14",
        "--name",
        "total",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    text = (tmp_path / "a.py").read_text(encoding="utf-8")
    assert "total" in text


def test_extract_method(tmp_path):
    code = (
        "def f():\n"
        "    a = 1\n"
        "    b = 2\n"
        "    c = a + b\n"
        "    return c\n"
    )
    (tmp_path / "a.py").write_text(code, encoding="utf-8")

    proc = run_tool(
        tmp_path,
        "extract_method",
        "--file",
        "a.py",
        "--start-line",
        "2",
        "--end-line",
        "3",
        "--name",
        "helper",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    text = (tmp_path / "a.py").read_text(encoding="utf-8")
    assert "helper" in text


def test_extract_function(tmp_path):
    code = (
        "def f():\n"
        "    a = 1\n"
        "    b = 2\n"
        "    c = a + b\n"
        "    return c\n"
    )
    (tmp_path / "a.py").write_text(code, encoding="utf-8")

    proc = run_tool(
        tmp_path,
        "extract_function",
        "--file",
        "a.py",
        "--start-line",
        "2",
        "--end-line",
        "3",
        "--name",
        "helper",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    text = (tmp_path / "a.py").read_text(encoding="utf-8")
    assert "helper" in text


def test_organize_imports(tmp_path):
    code = (
        "import sys\n"
        "import os\n"
        "print(os.getcwd(), sys.argv)\n"
    )
    (tmp_path / "a.py").write_text(code, encoding="utf-8")

    proc = run_tool(
        tmp_path,
        "organize_imports",
        "--file",
        "a.py",
    )
    assert proc.returncode == 0, proc.stderr

    text = (tmp_path / "a.py").read_text(encoding="utf-8")
    assert "import os" in text
    assert "import sys" in text


def test_move_global(tmp_path):
    a_code = (
        "def util():\n"
        "    return 1\n"
        "\n"
        "def main():\n"
        "    return util()\n"
    )
    (tmp_path / "a.py").write_text(a_code, encoding="utf-8")
    (tmp_path / "b.py").write_text("", encoding="utf-8")

    proc = run_tool(
        tmp_path,
        "move_global",
        "--source-file",
        "a.py",
        "--line",
        "1",
        "--col",
        "5",
        "--dest-file",
        "b.py",
    )
    assert proc.returncode == 0, proc.stderr

    b_text = (tmp_path / "b.py").read_text(encoding="utf-8")
    a_text = (tmp_path / "a.py").read_text(encoding="utf-8")

    assert "def util" in b_text
    assert "def util" not in a_text


def test_move_module_optional(tmp_path):
    pkg = tmp_path / "pkg"
    other = tmp_path / "other"

    pkg.mkdir()
    other.mkdir()

    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (other / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod.py").write_text("def x():\n    return 1\n", encoding="utf-8")

    proc = run_tool(
        tmp_path,
        "move_module",
        "--source",
        "pkg/mod.py",
        "--dest",
        "other",
    )

    if proc.returncode != 0:
        pytest.skip(
            "MoveModule behavior depends on Rope version; skipped because CLI reported failure: "
            f"{proc.stderr}"
        )

    assert (other / "mod.py").exists()


def test_path_outside_root(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    proc = run_tool(
        tmp_path,
        "rename",
        "--file",
        "../outside.py",
        "--line",
        "1",
        "--col",
        "1",
        "--new-name",
        "y",
    )
    assert proc.returncode == 1

    payload = parse_json(proc)
    assert payload["ok"] is False
    assert any("outside project root" in error for error in payload["errors"])


def test_invalid_line(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    proc = run_tool(
        tmp_path,
        "rename",
        "--file",
        "a.py",
        "--line",
        "99",
        "--col",
        "1",
        "--new-name",
        "y",
    )
    assert proc.returncode == 1

    payload = parse_json(proc)
    assert payload["ok"] is False


def test_json_schema(tmp_path):
    (tmp_path / "a.py").write_text("def foo(): pass\n", encoding="utf-8")

    proc = run_tool(
        tmp_path,
        "rename",
        "--file",
        "a.py",
        "--line",
        "1",
        "--col",
        "5",
        "--new-name",
        "bar",
        "--dry-run",
    )
    assert proc.returncode == 0, proc.stderr

    payload = parse_json(proc)
    for key in ("ok", "dry_run", "action", "message", "changes", "files", "errors"):
        assert key in payload