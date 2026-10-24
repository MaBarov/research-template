"""Behavioral tests for the v2 evidence stamp, cache invalidation and lock.

Thumbnail: Pins that a moved test surface invalidates evidence and that one refresh scores at a time.

Invariants & Expected State:
 * Every case drives a real throwaway Git repository whose ``REPO`` the gate
   modules were pointed at, so digests, staged bytes and the lock path are the
   ones the commit path uses.
 * ``tests_sha256`` must move when a test byte or a run-bounding pyproject
   section moves, and an entry stamped against the old digest must be refused:
   mutmut reuses cached verdicts across test edits, so a stale stamp is a
   silent pass otherwise.
 * ``prepare_cache`` drops the verdict cache exactly when the stamp moves and
   leaves it alone when it does not; ``refresh_lock`` refuses a second holder.
 * ``pragma_notes`` reports only suppressions the staged blob adds over HEAD,
   never one HEAD already carried.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from framework.gates.mutation import evidence, scoring

MODULE = "research/runtime/device.py"
POPULATION = {"only_mutate": ["research/runtime/*.py"], "do_not_mutate": []}
SOURCE = "def require_device(device):\n    return device\n"


def _git(repo: Path, *args: str) -> None:
    """Run one Git command in the scratch repository, failing on error."""

    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        },
    )


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A committed scratch repository with one staged module and no tests yet."""

    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "gate@test")
    _git(tmp_path, "config", "user.name", "gate")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.mutmut]\nonly_mutate = ["research/runtime/*.py"]\n\n[tool.ruff]\n',
        encoding="utf-8",
    )
    module = tmp_path / MODULE
    module.parent.mkdir(parents=True)
    module.write_text(SOURCE, encoding="utf-8")
    ledger = tmp_path / "framework" / "mutation_evidence.json"
    ledger.parent.mkdir(parents=True)
    monkeypatch.setattr(evidence, "REPO", tmp_path)
    monkeypatch.setattr(evidence, "PYPROJECT", tmp_path / "pyproject.toml")
    monkeypatch.setattr(evidence, "LEDGER_PATH", ledger)
    monkeypatch.setattr(scoring, "REPO", tmp_path)
    monkeypatch.setattr(scoring, "MUTANTS_DIR", tmp_path / "mutants")
    _git(tmp_path, "add", "pyproject.toml", "research")
    return tmp_path


def _record_stale_tests_stamp(repo: Path) -> None:
    """Save an entry whose content matches but whose test-surface stamp is old."""

    evidence.save_ledger(
        {
            "schema": evidence.SCHEMA,
            "population": POPULATION,
            "mutmut_version": "mutmut, version 3.8.0",
            "modules": {
                MODULE: {
                    "content_sha256": evidence.staged_sha256(MODULE),
                    "tests_sha256": "0" * 64,
                    "mutmut_version": "mutmut, version 3.8.0",
                    "mutants": 1,
                    "killed": 1,
                    "skipped": 0,
                    "survived": 0,
                    "no_tests": 0,
                    "timeout": 0,
                    "suspicious": 0,
                    "segfault": 0,
                    "caught_by_type_check": 0,
                    "check_was_interrupted_by_user": 0,
                    "not_checked": 0,
                }
            },
        }
    )


def test_stale_test_surface_stamp_blocks(repo: Path) -> None:
    """An entry scored against other test bytes is refused, not believed."""

    _record_stale_tests_stamp(repo)

    findings = evidence.staged_findings([MODULE])

    assert len(findings) == 1
    assert "test surface" in findings[0]
    assert evidence.tests_sha256() in findings[0]


def test_tests_sha256_moves_with_the_test_tree(repo: Path) -> None:
    """A new test byte and a moved run-bounding section both change the digest."""

    before = evidence.tests_sha256()

    tests = repo / evidence.TEST_SURFACE_DIR / "research" / "test_device.py"
    tests.parent.mkdir(parents=True)
    tests.write_text("def test_device() -> None:\n    assert True\n", encoding="utf-8")

    assert evidence.tests_sha256() != before
    with_tests = evidence.tests_sha256()
    (repo / "pyproject.toml").write_text(
        '[tool.mutmut]\nonly_mutate = ["research/runtime/*.py"]\n'
        'pytest_add_cli_args_test_selection = ["tests"]\n\n[tool.ruff]\n',
        encoding="utf-8",
    )
    assert evidence.tests_sha256() != with_tests


def test_prepare_cache_drops_only_when_the_digest_moves(repo: Path) -> None:
    """The cached verdicts survive an identical stamp and are dropped on a move."""

    assert scoring.prepare_cache("a" * 64) is not None
    assert scoring.cached_tests_sha256() == "a" * 64
    assert scoring.prepare_cache("a" * 64) is None

    dropped = scoring.prepare_cache("b" * 64)

    assert dropped is not None and "cache dropped" in dropped
    assert scoring.cached_tests_sha256() == "b" * 64


def test_refresh_lock_refuses_a_second_holder(repo: Path) -> None:
    """Two scorers never share ``mutants/``: the peer is refused, not queued."""

    with scoring.refresh_lock():
        peer = scoring.refresh_lock()
        with pytest.raises(scoring.RefreshBusy) as refused:
            peer.__enter__()
        assert "another mutation refresh is scoring" in str(refused.value)

    with scoring.refresh_lock():
        assert scoring._lock_path().is_file()


def test_pragma_notes_report_only_new_suppressions(repo: Path) -> None:
    """A suppression HEAD already carried is silent; a new one is NOTEd."""

    suppressed = "def require_device(device):\n    return device  # pragma: no mutate\n"
    _git(repo, "commit", "-qm", "baseline")
    assert evidence.pragma_notes([MODULE]) == []

    (repo / MODULE).write_text(suppressed, encoding="utf-8")
    _git(repo, "add", MODULE)

    notes = evidence.pragma_notes([MODULE])

    assert len(notes) == 1
    assert "line(s) 2" in notes[0]
    assert "no mutant" in notes[0]
