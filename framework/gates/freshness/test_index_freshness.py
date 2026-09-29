"""Tests for the index-freshness gate.

The gate exists because a commit whose index was seeded from an older revision
silently deletes or reverts every path that index never learned about. Each
test below pins one side of that contract against a real, throwaway repository.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from framework.gates.freshness import check_index_freshness as gate


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    """Run one git command in `repo`, failing the test on error."""
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )


def _init_repo(root: Path) -> Path:
    """Create a repository with one committed file and return its path."""
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "keep.txt").write_text("one\n")
    _git(repo, "add", "keep.txt")
    _git(repo, "commit", "-qm", "base")
    return repo


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repository the gate is pointed at."""
    root = _init_repo(tmp_path)
    monkeypatch.setattr(gate, "REPO", root)
    return root


def test_staged_edit_with_worktree_change_is_clean(repo: Path) -> None:
    """An ordinary edit corroborated by the working tree passes."""
    (repo / "keep.txt").write_text("two\n")
    _git(repo, "add", "keep.txt")
    assert gate.collect_findings() == []
    assert gate.main(["--strict"]) == 0


def test_added_and_removed_files_are_clean(repo: Path) -> None:
    """A staged addition and a staged `git rm` are both corroborated on disk."""
    (repo / "added.txt").write_text("payload\n")
    _git(repo, "add", "added.txt")
    _git(repo, "rm", "-q", "keep.txt")
    assert gate.collect_findings() == []
    assert gate.main(["--strict"]) == 0


def test_reverted_but_still_staged_path_is_blocked(repo: Path) -> None:
    """Staged content that survives in neither HEAD nor the worktree is stale."""
    (repo / "keep.txt").write_text("two\n")
    _git(repo, "add", "keep.txt")
    (repo / "keep.txt").write_text("one\n")
    findings = gate.collect_findings()
    assert [f.path for f in findings] == ["keep.txt"]
    assert findings[0].code == gate.STAGED_CODE
    assert gate.main(["--strict"]) == 1


def test_private_index_from_an_older_revision_is_blocked(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 2026-09-25 incident: a private index seeded before a later commit.

    The peer's `newfile.txt` is in HEAD and on disk, but the private index was
    built from the previous revision, so committing it would delete the file.
    """
    (repo / "newfile.txt").write_text("payload\n")
    _git(repo, "add", "newfile.txt")
    _git(repo, "commit", "-qm", "peer lands a file")

    stale = tmp_path / "stale_index"
    env = {**os.environ, "GIT_INDEX_FILE": str(stale)}
    _git(repo, "read-tree", "HEAD~1", env=env)
    monkeypatch.setenv("GIT_INDEX_FILE", str(stale))

    findings = gate.collect_findings()
    assert [f.path for f in findings] == ["newfile.txt"]
    assert "deleted" in findings[0].message
    assert gate.main(["--strict"]) == 1


def test_deliberate_untrack_has_no_bypass(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`git rm --cached` keeps the file on disk; no environment variable allows it."""
    _git(repo, "rm", "--cached", "-q", "keep.txt")
    assert [f.path for f in gate.collect_findings()] == ["keep.txt"]
    assert gate.main(["--strict"]) == 1
    monkeypatch.setenv("RESEARCH_ALLOW_STALE_INDEX", "1")
    assert gate.main(["--strict"]) == 1


def test_unborn_head_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository with no commit has no revision to drift from."""
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    _git(fresh, "init", "-q")
    _git(fresh, "config", "user.email", "test@example.com")
    _git(fresh, "config", "user.name", "test")
    monkeypatch.setattr(gate, "REPO", fresh)
    assert gate.main(["--strict"]) == 0


def test_json_report_lists_every_finding(repo: Path, tmp_path: Path) -> None:
    """The JSON report carries the same findings the text output prints."""
    import json

    (repo / "keep.txt").write_text("two\n")
    _git(repo, "add", "keep.txt")
    (repo / "keep.txt").write_text("one\n")
    out = tmp_path / "report.json"
    assert gate.main(["--strict", "--json", str(out)]) == 1
    payload = json.loads(out.read_text())
    assert [row["path"] for row in payload] == ["keep.txt"]
    assert payload[0]["code"] == gate.STAGED_CODE
