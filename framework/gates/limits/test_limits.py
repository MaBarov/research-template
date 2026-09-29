"""Tests for the code-size limits gate."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from framework.gates.limits import check_limits as gate

REPO = Path(__file__).resolve().parents[3]
GIT_ENV_POISON = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_CONFIG",
    "GIT_PREFIX",
)


def codes(source: str, path: str = "research/example.py") -> set[str]:
    return {finding.code for finding in gate.file_findings(path, source)}


def git_env() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items() if key not in GIT_ENV_POISON
    }


def stage(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=root, check=True, env=git_env())


def unstage(root: Path, rel: str) -> None:
    subprocess.run(
        ["git", "rm", "--cached", "-q", rel], cwd=root, check=True, env=git_env()
    )


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, env=git_env())
    monkeypatch.setattr(gate, "REPO", tmp_path)
    yield tmp_path


def test_file_length_boundary() -> None:
    assert codes("\n".join(["x = 1"] * 600) + "\n") == set()
    assert codes("\n".join(["x = 1"] * 601) + "\n") == {"LMT001"}


def test_function_length_boundary_uses_the_qualname() -> None:
    short = "class Klass:\n    def m(self):\n" + "        pass\n" * 29
    assert codes(short) == set()
    long = "class Klass:\n    def m(self):\n" + "        pass\n" * 30
    findings = gate.file_findings("research/example.py", long)
    assert [finding.code for finding in findings] == ["LMT002"]
    assert "Klass.m spans 31 lines" in findings[0].message


def test_decorators_do_not_count_towards_the_span() -> None:
    source = "@staticmethod\n" * 40 + "def f():\n" + "    pass\n" * 29
    assert codes(source) == set()


def test_init_py_allows_docstring_imports_and_dunder_metadata() -> None:
    source = (
        '"""Facade."""\n'
        "from __future__ import annotations\n"
        "from .core import Thing\n"
        "import os.path\n"
        "__all__ = ['Thing']\n"
        "__version__ = '1.0'\n"
        "if False:\n"
        "    from .typing_only import Alias\n"
    )
    assert codes(source, "research/example/__init__.py") == set()


def test_init_py_code_is_blocked() -> None:
    assert codes("def helper():\n    return 1\n", "research/example/__init__.py") == {
        "LMT004"
    }
    assert codes("ROOT = compute()\n", "research/example/__init__.py") == {"LMT004"}
    assert codes(
        "x = 1\n" + "\n".join("x += 1" for _ in range(700)), "research/e/__init__.py"
    ) == {
        "LMT001",
        "LMT004",
    }


def test_init_py_silent_optional_import_guards_are_blocked() -> None:
    source = "try:\n    import fast\nexcept ImportError:\n    pass\n"
    assert codes(source, "research/example/__init__.py") == {"LMT004"}


def test_syntax_errors_fail_closed() -> None:
    findings = gate.file_findings("research/broken.py", "def broken(:\n")
    assert [finding.code for finding in findings] == ["LMT000"]


def test_directory_limit_ignores_init_files() -> None:
    assert gate.directory_findings({"research/pkg": 5}) == []
    findings = gate.directory_findings({"research/pkg": 6})
    assert [finding.code for finding in findings] == ["LMT003"]
    assert "research/pkg/" in findings[0].path


def test_scope_covers_first_party_trees_only() -> None:
    assert gate.is_first_party("research/a/b.py")
    assert gate.is_first_party("scripts/a.py")
    assert gate.is_first_party("framework/gates/limits/check_limits.py")
    assert gate.is_first_party("experiments/e3/a.py")
    assert gate.is_first_party("tests/research/a.py")
    assert gate.is_first_party("conftest.py")
    assert not gate.is_first_party("third_party/refactor/rope_refactor.py")
    assert not gate.is_first_party("results/run/a.py")
    assert not gate.is_first_party("research/analysis/cache/x.py")
    assert not gate.is_first_party("slurm/run.sbatch")
    assert not gate.is_first_party("README.md")


def test_staged_mode_reads_the_index_not_the_worktree(repo: Path) -> None:
    stage(repo, "scripts/big.py", "\n".join(["x = 1"] * 601) + "\n")
    (repo / "scripts" / "big.py").write_text("x = 1\n", encoding="utf-8")
    assert (
        gate.main(["--mode", "staged", "--strict", "--staged", "scripts/big.py"]) == 1
    )


def test_staged_mode_blocks_a_new_module_in_a_crowded_directory(repo: Path) -> None:
    for index in range(5):
        stage(repo, f"scripts/mod{index}.py", "x = 1\n")
    assert (
        gate.main(["--mode", "staged", "--strict", "--staged", "scripts/mod0.py"]) == 0
    )
    stage(repo, "scripts/sixth.py", "x = 1\n")
    assert (
        gate.main(["--mode", "staged", "--strict", "--staged", "scripts/sixth.py"]) == 1
    )


def test_staged_deletion_frees_the_directory_slot(repo: Path) -> None:
    for index in range(6):
        stage(repo, f"scripts/mod{index}.py", "x = 1\n")
    assert (
        gate.main(["--mode", "staged", "--strict", "--staged", "scripts/mod0.py"]) == 1
    )
    unstage(repo, "scripts/mod5.py")
    assert (
        gate.main(["--mode", "staged", "--strict", "--staged", "scripts/mod0.py"]) == 0
    )


def test_staged_mode_requires_files_and_ignores_vendored_paths(repo: Path) -> None:
    assert gate.main(["--mode", "staged", "--strict"]) == 2
    stage(repo, "third_party/refactor/rope_refactor.py", "\n".join(["x = 1"] * 900))
    assert (
        gate.main(
            [
                "--mode",
                "staged",
                "--strict",
                "--staged",
                "third_party/refactor/rope_refactor.py",
            ]
        )
        == 0
    )
    assert gate.main(["--mode", "staged", "--strict", "--staged", "notes/plan.py"]) == 0


def test_mode_all_reports_and_strict_decides(
    repo: Path, capsys: pytest.CaptureFixture
) -> None:
    (repo / "scripts").mkdir()
    (repo / "scripts" / "big.py").write_text(
        "\n".join(["x = 1"] * 601), encoding="utf-8"
    )
    assert gate.main(["--mode", "all"]) == 0
    assert gate.main(["--mode", "all", "--strict"]) == 1
    assert "LMT001: 1" in capsys.readouterr().err


def test_hook_wiring_is_blocking_before_the_advisory_section() -> None:
    hook = (REPO / "framework" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    gate_at = hook.index("check_limits.py")
    assert "--mode staged" in hook[gate_at - 200 : gate_at + 200]
    assert gate_at < hook.index("5. CHECKS")
    assert "exit 1" in hook[gate_at : gate_at + 400]
    prepush = (REPO / "framework" / "hooks" / "pre-push").read_text(encoding="utf-8")
    prepush_at = prepush.index("check_limits.py")
    assert "--mode all" in prepush[prepush_at : prepush_at + 200]


def test_gate_obeys_its_own_limits() -> None:
    source = Path(gate.__file__).read_text(encoding="utf-8")
    assert gate.file_findings("framework/gates/limits/check_limits.py", source) == []
    assert len(source.splitlines()) <= gate.MAX_FILE_LINES
