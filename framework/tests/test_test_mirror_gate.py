"""Tests for the src -> test mirror gate."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from framework.gates.checks import check_test_mirror as gate


def _touch(root: Path, rel: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fake_repo(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(gate, "REPO", tmp_path)
    aliases = tmp_path / "framework" / "test_mirror_aliases.json"
    aliases.parent.mkdir(parents=True, exist_ok=True)
    aliases.write_text("{}", encoding="utf-8")
    return tmp_path


def test_mirror_paths_accepts_both_spellings() -> None:
    assert gate.mirror_paths("research/a/b/c.py") == [
        "tests/research/a/b/tests_c.py",
        "tests/research/a/b/test_c.py",
    ]


def test_evaluate_accepts_both_spellings_and_exempts_packages() -> None:
    existing = {"tests/research/tests_x.py", "tests/research/a/test_y.py"}
    findings = gate.evaluate(
        [
            "research/x.py",
            "research/a/y.py",
            "research/__init__.py",
            "research/missing.py",
        ],
        {},
        existing.__contains__,
    )
    assert [(finding.code, finding.path) for finding in findings] == [
        ("MIRROR MISSING", "research/missing.py")
    ]
    assert (
        findings[0].message
        == "research/missing.py -> expected tests/research/tests_missing.py"
    )


def test_alias_satisfies_a_missing_mirror() -> None:
    existing = {"tests/research/tests_ab.py"}
    findings = gate.evaluate(
        ["research/a/b.py"],
        {"research/a/b.py": ["tests/research/tests_ab.py"]},
        existing.__contains__,
    )
    assert findings == []


def test_dangling_alias_is_a_finding() -> None:
    findings = gate.evaluate(
        ["research/a/b.py"],
        {"research/a/b.py": ["tests/research/tests_gone.py"]},
        set().__contains__,
    )
    assert [(finding.code, finding.message) for finding in findings] == [
        ("ALIAS DANGLING", "research/a/b.py -> tests/research/tests_gone.py (missing)")
    ]


def test_stale_alias_beside_a_real_mirror_is_a_finding() -> None:
    existing = {"tests/research/a/tests_b.py", "tests/research/tests_ab.py"}
    findings = gate.evaluate(
        ["research/a/b.py"],
        {"research/a/b.py": ["tests/research/tests_ab.py"]},
        existing.__contains__,
    )
    assert [finding.code for finding in findings] == ["ALIAS STALE"]


def test_collect_files_skips_caches_and_third_party(tmp_path, monkeypatch) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    for rel in (
        "research/a.py",
        "research/__pycache__/a.py",
        "research/third_party/x.py",
    ):
        _touch(root, rel)
    assert gate.collect_files("research") == ["research/a.py"]


def test_collect_files_staged_filter_ignores_other_roots(tmp_path, monkeypatch) -> None:
    _fake_repo(tmp_path, monkeypatch)
    assert gate.collect_files("research", ["scripts/x.py", "research/b.py"]) == [
        "research/b.py"
    ]


def test_load_aliases_reads_targets(tmp_path) -> None:
    path = tmp_path / "aliases.json"
    path.write_text(
        '{"research/a.py": ["tests/research/tests_a.py"]}', encoding="utf-8"
    )
    assert gate.load_aliases(path) == {"research/a.py": ["tests/research/tests_a.py"]}


def test_load_aliases_rejects_a_non_object(tmp_path) -> None:
    path = tmp_path / "aliases.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(TypeError, match="JSON object"):
        gate.load_aliases(path)


def test_cli_blocks_a_missing_mirror(tmp_path, monkeypatch, capsys) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a.py")
    assert gate.main(["--strict"]) == 1
    assert (
        "MIRROR MISSING: research/a.py -> expected tests/research/tests_a.py"
        in capsys.readouterr().err
    )


def test_cli_passes_with_a_real_mirror(tmp_path, monkeypatch, capsys) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a/b.py")
    _write(root, "tests/research/a/tests_b.py", "def test_b():\n    assert compute()\n")
    assert gate.main(["--strict"]) == 0
    assert "checked 1 file(s), 0 finding(s)" in capsys.readouterr().out


def test_cli_missing_alias_table_is_an_environment_error(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(gate, "REPO", tmp_path)
    assert gate.main(["--strict"]) == 2
    assert "missing alias table" in capsys.readouterr().err


def test_cli_staged_ignores_non_source_paths(tmp_path, monkeypatch, capsys) -> None:
    _fake_repo(tmp_path, monkeypatch)
    assert gate.main(["--strict", "--staged", "README.md", "scripts/x.py"]) == 0
    assert "checked 0 file(s)" in capsys.readouterr().out


def test_cli_json_report_lists_findings(tmp_path, monkeypatch) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a.py")
    assert gate.main(["--json", "report.json"]) == 0
    payload = json.loads((root / "report.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "research.test-mirror.v1"
    assert payload["checked"] == ["research/a.py"]
    assert payload["findings"][0]["code"] == "MIRROR MISSING"


def _disk_exists(root: Path) -> Callable[[str], bool]:
    """Return an ``exists`` predicate backed by the fake repo on disk."""
    return lambda rel: (root / rel).is_file()


def test_count_oracles_counts_tautologies() -> None:
    source = (
        "def test_a():\n"
        "    assert True\n"
        "    assert 1\n"
        "    assert 1 == 1\n"
        "    assert compute()\n"
    )
    assert gate._count_oracles(source) == (4, 3, 0)


def test_count_oracles_counts_state_anchored_assertions() -> None:
    source = (
        "def test_a():\n"
        "    assert value == value\n"
        "    assert compute() == compute()\n"
        "    assert len(items) >= 0\n"
        "    assert result == 2\n"
    )
    assert gate._count_oracles(source) == (4, 0, 3)


def test_count_oracles_treats_unparseable_as_empty() -> None:
    assert gate._count_oracles("def (:\n") == (0, 0, 0)


@pytest.mark.parametrize(
    "source",
    [
        (
            "import pytest\n\n\ndef test_a():\n"
            "    with pytest.raises(ValueError):\n"
            "        raise ValueError\n"
        ),
        (
            "import pytest\n\n\ndef test_a():\n"
            "    with pytest.warns(UserWarning):\n"
            "        warnings.warn('x', UserWarning)\n"
        ),
    ],
)
def test_count_oracles_counts_context_managers(source: str) -> None:
    assert gate._count_oracles(source) == (1, 0, 0)


def test_is_exempt_mirror_test() -> None:
    assert gate.is_exempt_mirror_test("tests/research/conftest.py")
    assert gate.is_exempt_mirror_test("tests/research/a/tests_x_fixtures.py")
    assert not gate.is_exempt_mirror_test("tests/research/tests_a.py")


def test_evaluate_flags_an_assertion_free_mirror(tmp_path, monkeypatch) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a.py")
    _touch(root, "tests/research/tests_a.py")
    findings = gate.evaluate(["research/a.py"], {}, _disk_exists(root))
    assert [(finding.code, finding.path) for finding in findings] == [
        ("HNS068", "research/a.py")
    ]
    assert "no behavioral assertions" in findings[0].message
    assert "arXiv:2606.18168" in findings[0].message


def test_evaluate_flags_a_tautological_mirror(tmp_path, monkeypatch) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a.py")
    _write(root, "tests/research/tests_a.py", "def test_a():\n    assert True\n")
    findings = gate.evaluate(["research/a.py"], {}, _disk_exists(root))
    assert [finding.code for finding in findings] == ["HNS068"]


@pytest.mark.parametrize(
    "assertion",
    [
        "assert x == x",
        "assert compute() == compute()",
        "assert x is x",
        "assert x != x",
        "assert len(items) >= 0",
    ],
)
def test_evaluate_flags_state_anchored_mirrors(
    tmp_path, monkeypatch, assertion
) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a.py")
    _write(root, "tests/research/tests_a.py", f"def test_a():\n    {assertion}\n")
    findings = gate.evaluate(["research/a.py"], {}, _disk_exists(root))
    assert [finding.code for finding in findings] == ["HNS070"]
    assert "state-anchored or self-referential" in findings[0].message
    assert "arXiv:2608.17214" in findings[0].message


def test_evaluate_accepts_genuine_value_comparisons(tmp_path, monkeypatch) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a.py")
    _write(
        root,
        "tests/research/tests_a.py",
        "def test_a():\n    assert x == y\n    assert len(items) > 0\n",
    )
    assert gate.evaluate(["research/a.py"], {}, _disk_exists(root)) == []


def test_evaluate_accepts_a_behavioral_mirror(tmp_path, monkeypatch) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a.py")
    _write(root, "tests/research/tests_a.py", "def test_a():\n    assert result == 2\n")
    assert gate.evaluate(["research/a.py"], {}, _disk_exists(root)) == []


def test_evaluate_exempts_fixture_mirrors(tmp_path, monkeypatch) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a/x_fixtures.py")
    _touch(root, "tests/research/a/tests_x_fixtures.py")
    assert gate.evaluate(["research/a/x_fixtures.py"], {}, _disk_exists(root)) == []


def test_cli_blocks_an_assertion_free_mirror(tmp_path, monkeypatch, capsys) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    _touch(root, "research/a.py")
    _touch(root, "tests/research/tests_a.py")
    assert gate.main(["--strict"]) == 1
    assert "HNS068" in capsys.readouterr().err


def _git(repo: Path, *args: str) -> None:
    """Run one Git command in a scratch repository.

    The hook environment inherits ``GIT_DIR``/``GIT_INDEX_FILE`` (and friends)
    from the commit that invoked it; leaving them set would point the scratch
    ``git init``/``git add`` at the caller's repository instead of ``repo``.
    """
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, env=environment
    )


def test_grade_oracle_file_flags_zero_oracle_tests() -> None:
    """An assertion-free test function is HNS068."""
    source = "def test_x() -> None:\n    pass\n"
    findings = gate.grade_oracle_file("tests/unit/test_x.py", source)
    assert [finding.code for finding in findings] == ["HNS068"]


def test_grade_oracle_file_accepts_a_real_assertion() -> None:
    """An assertion against an independent expectation passes."""
    source = "def test_x() -> None:\n    assert value == 3\n"
    assert gate.grade_oracle_file("tests/unit/test_x.py", source) == []


def test_grade_oracle_file_flags_tautologies() -> None:
    """An all-tautological body is HNS070 (state-anchored)."""
    source = "def test_x() -> None:\n    assert item == item\n"
    findings = gate.grade_oracle_file("tests/unit/test_x.py", source)
    assert [finding.code for finding in findings] == ["HNS070"]


def test_grade_oracle_file_skips_support_modules() -> None:
    """A module without a test_* function is support code, not a test."""
    source = "def helper() -> int:\n    return 1\n"
    assert gate.grade_oracle_file("tests/unit/tests_recording.py", source) == []


def test_grade_oracle_file_skips_exempt_names() -> None:
    """conftest and *_fixtures modules are fixtures, not oracle targets."""
    source = "def test_x() -> None:\n    pass\n"
    assert gate.grade_oracle_file("tests/research/x/conftest.py", source) == []
    assert (
        gate.grade_oracle_file("tests/research/x/tests_data_fixtures.py", source) == []
    )


def test_grade_oracle_file_treats_unparseable_source_as_no_test() -> None:
    """A file that does not parse defines no test function."""
    assert gate.grade_oracle_file("tests/unit/test_x.py", "def test_x(:\n") == []


def test_oracle_cli_reads_the_staged_blob(tmp_path, monkeypatch, capsys) -> None:
    """--staged decides from the Git index, not the working tree."""
    repo = _fake_repo(tmp_path, monkeypatch)
    rel = "tests/unit/test_x.py"
    _write(repo, rel, "def test_x() -> None:\n    pass\n")
    _git(repo, "init", "-q")
    _git(repo, "add", rel)

    assert gate.main(["--strict", "--staged", "--oracle-files", rel]) == 1
    assert "HNS068" in capsys.readouterr().err

    _write(repo, rel, "def test_x() -> None:\n    assert value == 3\n")
    _git(repo, "add", rel)
    assert gate.main(["--strict", "--staged", "--oracle-files", rel]) == 0

    # The index decides: a weaker disk copy does not change the staged verdict.
    _write(repo, rel, "def test_x() -> None:\n    pass\n")
    assert gate.main(["--strict", "--staged", "--oracle-files", rel]) == 0
