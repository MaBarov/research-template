"""Tests for the ratchet gates that block waiver, alias and baseline additions.

Thumbnail: Pins that the waiver, alias and duplication-baseline tables only shrink.

Invariants & Expected State:
    Every gate here compares the working-tree candidate table against the
    table committed at HEAD and refuses to let it grow, so a scratch Git
    repository is created per test and ``git show HEAD:<rel>`` resolves against
    a real commit instead of the enclosing checkout.  The scratch repositories
    are driven through ``git_env_fixture.run_git``, which strips the
    ``GIT_*`` selectors a hook inherits: without it a fixture's ``init``/
    ``commit`` would land on the caller's repository.  Each addition test is
    paired with a removal test, because a ratchet that also refused shrinking
    would pin the defect it exists to prevent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.gates.checks.check_duplication import Finding, check_baseline_ratchet
from framework.gates.checks.check_test_mirror import check_alias_ratchet
from framework.gates.coverage.run import check_waiver_ratchet
from framework.tests.hook_hygiene.git_env_fixture import run_git

# The ratchet contracts are acceptance facts, not unit behavior: each case pins
# the exact verdict the battery must reach on a candidate table. They are cheap
# enough to run on every commit, and that is where a silent refactor of the
# comparison would otherwise survive.
pytestmark = pytest.mark.pinned

WAIVERS_REL = "framework/loop_waivers.json"
ALIASES_REL = "framework/test_mirror_aliases.json"
BASELINE = "framework/jscpd-baseline.json"


def _git(repo: Path, *args: str) -> None:
    """Run one Git command in a scratch repository with a pinned identity."""

    run_git(repo, "-c", "user.email=t@example.com", "-c", "user.name=t", *args)


def _commit_json(repo: Path, rel: str, payload: dict[str, object]) -> None:
    """Init ``repo`` and commit one JSON document at ``rel`` as the baseline."""

    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", "baseline")


def test_waiver_addition_is_blocked(tmp_path: Path) -> None:
    """A new ``(file, ordinal)`` waiver absent from HEAD yields COV005."""

    _commit_json(tmp_path, WAIVERS_REL, {"research/a.py": {"3": "boundary"}})
    current = {"research/a.py": {"3": "boundary", "9": "fresh loophole"}}

    findings = check_waiver_ratchet(tmp_path, tmp_path / WAIVERS_REL, current)

    assert [finding.code for finding in findings] == ["COV005"]
    assert "research/a.py#9" in findings[0].message


def test_unchanged_waivers_are_allowed(tmp_path: Path) -> None:
    """A candidate table identical to HEAD produces no finding."""

    payload = {"research/a.py": {"3": "boundary"}, "research/b.py": {"7": "guard"}}
    _commit_json(tmp_path, WAIVERS_REL, payload)

    findings = check_waiver_ratchet(tmp_path, tmp_path / WAIVERS_REL, payload)

    assert findings == []


def test_removed_waivers_are_allowed(tmp_path: Path) -> None:
    """Shrinking the waiver table (partially or wholly) is always permitted."""

    _commit_json(
        tmp_path, WAIVERS_REL, {"research/a.py": {"3": "boundary", "4": "old"}}
    )

    partial = check_waiver_ratchet(
        tmp_path, tmp_path / WAIVERS_REL, {"research/a.py": {"3": "boundary"}}
    )
    empty = check_waiver_ratchet(tmp_path, tmp_path / WAIVERS_REL, {})

    assert partial == []
    assert empty == []


def test_alias_addition_is_blocked(tmp_path: Path) -> None:
    """A new module key absent from HEAD yields MIR003."""

    _commit_json(tmp_path, ALIASES_REL, {"research/a.py": ["tests/a_mirror.py"]})
    current = {
        "research/a.py": ["tests/a_mirror.py"],
        "research/b.py": ["tests/b_mirror.py"],
    }

    findings = check_alias_ratchet(tmp_path, tmp_path / ALIASES_REL, current)

    assert [finding.code for finding in findings] == ["MIR003"]
    assert "research/b.py" in findings[0].message


def test_unchanged_aliases_are_allowed(tmp_path: Path) -> None:
    """An alias table identical to HEAD produces no finding."""

    payload = {"research/a.py": ["tests/a_mirror.py"]}
    _commit_json(tmp_path, ALIASES_REL, payload)

    findings = check_alias_ratchet(tmp_path, tmp_path / ALIASES_REL, payload)

    assert findings == []


def test_removed_aliases_are_allowed(tmp_path: Path) -> None:
    """Dropping an alias mapping (or all of them) is always permitted."""

    _commit_json(
        tmp_path,
        ALIASES_REL,
        {
            "research/a.py": ["tests/a_mirror.py"],
            "research/b.py": ["tests/b_mirror.py"],
        },
    )

    partial = check_alias_ratchet(
        tmp_path, tmp_path / ALIASES_REL, {"research/a.py": ["tests/a_mirror.py"]}
    )
    empty = check_alias_ratchet(tmp_path, tmp_path / ALIASES_REL, {})

    assert partial == []
    assert empty == []


def _write_baseline(repo: Path, fingerprints: dict[str, int]) -> Path:
    """Write a jscpd baseline carrying ``fingerprints`` and return its path."""

    baseline = repo / BASELINE
    baseline.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "fingerprints": fingerprints}
    baseline.write_text(json.dumps(payload), encoding="utf-8")
    return baseline


def test_baseline_ratchet_blocks_expansion(tmp_path: Path) -> None:
    """A current baseline with a fingerprint absent from HEAD is blocking."""

    baseline = _write_baseline(tmp_path, {"fp1": 1})
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", BASELINE)
    _git(tmp_path, "commit", "-qm", "baseline")
    _write_baseline(tmp_path, {"fp1": 1, "fp2": 1})

    findings = check_baseline_ratchet(tmp_path, baseline)

    assert any(finding.code == "CPD002" for finding in findings)


def test_baseline_ratchet_names_the_uncovered_clone(tmp_path: Path) -> None:
    """An expansion finding names the clone locations it blocks."""

    baseline = _write_baseline(tmp_path, {"fp1": 1})
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", BASELINE)
    _git(tmp_path, "commit", "-qm", "baseline")
    _write_baseline(tmp_path, {"fp1": 1, "fp2": 1})
    clone = Finding(
        code="CPD001",
        path="research/a.py",
        line=10,
        message="Clone with research/b.py:30-40 (11 lines, 60 tokens)",
    )

    findings = check_baseline_ratchet(tmp_path, baseline, [clone])

    assert len(findings) == 1
    assert "research/a.py:10" in findings[0].message
    assert "research/b.py:30-40" in findings[0].message
    assert "monotonic non-increasing" in findings[0].message


def test_baseline_ratchet_allows_shrink_or_identical(tmp_path: Path) -> None:
    """Shrinking the baseline or keeping it identical is allowed."""

    baseline = _write_baseline(tmp_path, {"fp1": 1, "fp2": 1})
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", BASELINE)
    _git(tmp_path, "commit", "-qm", "baseline")

    _write_baseline(tmp_path, {"fp1": 1})
    assert check_baseline_ratchet(tmp_path, baseline) == []
    _write_baseline(tmp_path, {})
    assert check_baseline_ratchet(tmp_path, baseline) == []
