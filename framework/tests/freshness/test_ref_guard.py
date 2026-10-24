"""Tests for the reference-transaction ref-provenance guard.

Thumbnail: Verifies reference-transaction blocking of unprovenanced ref moves.

Invariants & Expected State:
    - Tests bypasses (crafted commits, --no-verify, replace refs, grafts) are refused.
    - Tests legitimate moves (rewind, reachable forward move, armed commits) land.
    - Verifies audit log creation and scratch repository execution.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from framework import harness
from framework.gates.freshness import ref_guard as gate
from framework.tests.hook_hygiene.git_env_fixture import run_git

REPO_ROOT = harness.REPO
REAL_HOOK = REPO_ROOT / "framework" / "hooks" / "reference-transaction"
ZERO = "0" * 40


def _git(
    repo: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run one git command in `repo`; assert success unless `check` is False."""
    result = run_git(repo, *args, check=False)
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def _sha(repo: Path, rev: str) -> str:
    """Return the resolved object id of `rev` in `repo`."""
    return _git(repo, "rev-parse", rev).stdout.strip()


def _commit(repo: Path, name: str, content: str) -> str:
    """Write, stage and commit one file; return the new commit id."""
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", content.strip())
    return _sha(repo, "HEAD")


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repository with one commit, as the guard's working directory."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")
    monkeypatch.chdir(root)
    _commit(root, "base.txt", "one\n")
    return root


def _craft(repo: Path, message: str = "crafted") -> str:
    """Return a commit object built by plumbing, unattached to any ref."""
    tree = _git(repo, "write-tree").stdout.strip()
    head = _sha(repo, "HEAD")
    return _git(repo, "commit-tree", tree, "-p", head, "-m", message).stdout.strip()


def _run(monkeypatch: pytest.MonkeyPatch, lines: str, state: str = "prepared") -> int:
    """Feed transaction `lines` to the guard's CLI and return its exit code."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(lines))
    return gate.main(["--state", state])


def _arm(
    monkeypatch: pytest.MonkeyPatch,
    tree: str,
    stamp: float | None = None,
    starttime: str | None = None,
) -> Path:
    """Write an armed marker for the current process and return its path."""
    pid = os.getpid()
    monkeypatch.setattr(os, "getppid", lambda: pid)
    armed = gate._armed_dir(gate._common_dir())
    armed.mkdir(parents=True, exist_ok=True)
    stamp = time.time() if stamp is None else stamp
    starttime = gate._proc_starttime(pid) if starttime is None else starttime
    marker = armed / str(pid)
    marker.write_text(f"{tree} {stamp} {starttime}", encoding="utf-8")
    return marker


def test_deletion_and_equal_updates_are_allowed(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A branch deletion (new is zero) and a no-op move are always allowed."""
    head = _sha(repo, "HEAD")
    assert _run(monkeypatch, f"{head} {ZERO} refs/heads/gone\n") == 0
    assert _run(monkeypatch, f"{head} {head} refs/heads/master\n") == 0


def test_rewind_to_an_ancestor_is_allowed(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`reset --hard HEAD~1` moves a branch back onto its own history."""
    base = _sha(repo, "HEAD")
    tip = _commit(repo, "base.txt", "two\n")
    assert _run(monkeypatch, f"{tip} {base} refs/heads/master\n") == 0


def test_crafted_commit_into_a_new_branch_is_blocked(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`commit-tree` + `update-ref refs/heads/x` never reaches a live tip."""
    crafted = _craft(repo)
    assert _run(monkeypatch, f"{ZERO} {crafted} refs/heads/x\n") == 1


def test_force_branch_and_reset_to_crafted_are_blocked(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`branch -f` and `reset --hard` onto a crafted commit are refused."""
    head = _sha(repo, "HEAD")
    crafted = _craft(repo)
    assert _run(monkeypatch, f"{head} {crafted} refs/heads/master\n") == 1


def test_forward_move_to_a_reachable_tip_is_allowed(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fast-forward onto another branch's tip is already in history."""
    base = _sha(repo, "HEAD")
    _git(repo, "checkout", "-q", "-b", "side")
    tip = _commit(repo, "side.txt", "s\n")
    _git(repo, "checkout", "-q", "master")
    assert _run(monkeypatch, f"{base} {tip} refs/heads/master\n") == 0


def test_a_nested_branch_tip_is_trusted(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tip under `fix/...` is a live tip; a fast-forward onto it lands."""
    base = _sha(repo, "HEAD")
    _git(repo, "checkout", "-q", "-b", "fix/nested-arm")
    tip = _commit(repo, "nested.txt", "n\n")
    _git(repo, "checkout", "-q", "master")
    assert tip in gate._trust_tips()
    assert _run(monkeypatch, f"{base} {tip} refs/heads/master\n") == 0


def test_a_crafted_object_stays_refused_among_nested_tips(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enumerating every ref keeps the reachability rule for a crafted object."""
    _git(repo, "checkout", "-q", "-b", "fix/deep/arm")
    nested_tip = _commit(repo, "nested.txt", "n\n")
    _git(repo, "checkout", "-q", "master")
    crafted = _craft(repo)
    tips = gate._trust_tips()
    assert set(tips) == {_sha(repo, "master"), nested_tip}
    assert crafted not in tips
    assert _run(monkeypatch, f"{ZERO} {crafted} refs/heads/fix/new\n") == 1


def test_unresolvable_new_value_is_blocked(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A branch pointed at a non-commit object is refused."""
    head = _sha(repo, "HEAD")
    tree = _sha(repo, "HEAD^{tree}")
    assert _run(monkeypatch, f"{head} {tree} refs/heads/bad\n") == 1


def _craft_with_tree(repo: Path) -> tuple[str, str]:
    """Return a crafted commit and its tree id."""
    crafted = _craft(repo)
    tree = gate._tree_of(crafted)
    assert tree is not None
    return crafted, tree


def test_non_gated_refs_pass(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """HEAD, stash and notes carry no provenance guarantee and are untouched."""
    crafted = _craft(repo)
    assert _run(monkeypatch, f"{ZERO} {crafted} HEAD\n") == 0
    assert _run(monkeypatch, f"{ZERO} {crafted} refs/stash\n") == 0


def test_marker_allows_and_is_consumed(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An armed marker matching pid, tree and starttime lets a gated commit land."""
    crafted, tree = _craft_with_tree(repo)
    marker = _arm(monkeypatch, tree)
    assert _run(monkeypatch, f"{ZERO} {crafted} refs/heads/newb\n") == 0
    assert not marker.exists()


def test_marker_rejected_after_pid_reuse(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale starttime (the pid was reused) never vouches for a move."""
    crafted, tree = _craft_with_tree(repo)
    _arm(monkeypatch, tree, starttime="1")
    assert _run(monkeypatch, f"{ZERO} {crafted} refs/heads/newb\n") == 1


def test_marker_rejected_when_stale(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A marker older than the freshness window is pruned and ignored."""
    crafted, tree = _craft_with_tree(repo)
    marker = _arm(monkeypatch, tree, stamp=time.time() - 700.0)
    assert _run(monkeypatch, f"{ZERO} {crafted} refs/heads/newb\n") == 1
    assert not marker.exists()


def test_marker_rejected_for_a_different_tree(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A marker armed for another tree does not vouch for this commit."""
    crafted = _craft(repo)
    _arm(monkeypatch, "1" * 40)
    assert _run(monkeypatch, f"{ZERO} {crafted} refs/heads/newb\n") == 1


def test_remote_tracking_ref_by_fetch_is_allowed(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A remote-tracking ref may move to an unreachable value under `git fetch`."""
    crafted = _craft(repo)
    monkeypatch.setattr(gate, "_invoker_cmdline", lambda: ["git", "fetch", "origin"])
    assert _run(monkeypatch, f"{ZERO} {crafted} refs/remotes/origin/master\n") == 0


def test_remote_tracking_ref_by_update_ref_is_blocked(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A remote-tracking ref moved outside fetch/pull/push is refused."""
    crafted = _craft(repo)
    monkeypatch.setattr(gate, "_invoker_cmdline", lambda: ["git", "update-ref", "x"])
    assert _run(monkeypatch, f"{ZERO} {crafted} refs/remotes/origin/master\n") == 1


def test_tag_rules(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A crafted tag is refused; a tag at a live branch tip is not."""
    head = _sha(repo, "HEAD")
    crafted = _craft(repo)
    assert _run(monkeypatch, f"{ZERO} {crafted} refs/tags/v1\n") == 1
    assert _run(monkeypatch, f"{ZERO} {head} refs/tags/v2\n") == 0


def test_replace_ref_is_blocked(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A replace ref may only be deleted or reset to itself."""
    head = _sha(repo, "HEAD")
    crafted = _craft(repo)
    assert _run(monkeypatch, f"{ZERO} {crafted} refs/replace/{head}\n") == 1


def test_grafts_file_fails_closed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An info/grafts file blocks even an ordinary rewind."""
    base = _sha(repo, "HEAD")
    tip = _commit(repo, "base.txt", "two\n")
    (repo / ".git" / "info").mkdir(exist_ok=True)
    (repo / ".git" / "info" / "grafts").write_text(base + "\n", encoding="utf-8")
    assert _run(monkeypatch, f"{tip} {base} refs/heads/master\n") == 1


def test_non_prepared_states_exit_zero_before_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """committed/aborted never read stdin and never block."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("garbage not three fields"))
    assert gate.main(["--state", "committed"]) == 0
    assert gate.main(["--state", "aborted"]) == 0


def test_malformed_line_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed transaction record aborts the transaction."""
    assert _run(monkeypatch, "only-two-fields\n") == 1


def _stub_pre_commit() -> str:
    return f"""#!/usr/bin/env bash
set -e
COMMON="$(git rev-parse --git-common-dir)"
TREE="$(git write-tree)"
STARTTIME="$(awk '{{print $22}}' /proc/$PPID/stat)"
mkdir -p "$COMMON/{harness.GATE_STATE_DIR}/armed"
printf '%s %s %s\\n' "$TREE" "$(date +%s)" "$STARTTIME" > "$COMMON/{harness.GATE_STATE_DIR}/armed/$PPID"
"""


def _hook_run(repo: Path) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Return a runner for one git command in `repo` that never raises."""

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return run_git(repo, *args, check=False)

    return run


def _hook_repo(tmp_path: Path) -> Path:
    """Return a scratch repository whose hooks are the shipped guard plus a stub."""
    repo = tmp_path / "scratch"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    hooks = repo / "hooks"
    hooks.mkdir()
    if REAL_HOOK.is_file():
        os.symlink(REAL_HOOK, hooks / "reference-transaction")
    else:
        hook_script = f"""#!/usr/bin/env bash
set -euo pipefail
exec "{sys.executable}" "{gate.__file__}" --state "${{1:-prepared}}"
"""
        hook_file = hooks / "reference-transaction"
        hook_file.write_text(hook_script, encoding="utf-8")
        hook_file.chmod(0o755)
    (hooks / "pre-commit").write_text(_stub_pre_commit(), encoding="utf-8")
    (hooks / "pre-commit").chmod(0o755)
    _git(repo, "config", "core.hooksPath", str(hooks))
    return repo


def _bootstrapped_hook_repo(
    tmp_path: Path,
) -> tuple[Path, Callable[..., subprocess.CompletedProcess[str]], str]:
    """Return `(repo, run, base)` after one gated root commit lands."""
    repo = _hook_repo(tmp_path)
    run = _hook_run(repo)
    (repo / "f.txt").write_text("one\n", encoding="utf-8")
    run("add", "f.txt")
    assert run("commit", "-m", "base").returncode == 0
    return repo, run, _sha(repo, "HEAD")


def test_scratch_e2e_gated_commit_lands_and_no_verify_fails(tmp_path: Path) -> None:
    """The shipped guard arms a gated commit and refuses `--no-verify`."""
    repo, run, base = _bootstrapped_hook_repo(tmp_path)
    (repo / "f.txt").write_text("two\n", encoding="utf-8")
    run("add", "f.txt")
    assert run("commit", "--no-verify", "-m", "bypass").returncode != 0
    assert _sha(repo, "HEAD") == base


def test_scratch_e2e_plumbing_moves_are_blocked(tmp_path: Path) -> None:
    """`commit-tree`+`update-ref`, `branch -f` and `reset --hard` are refused."""
    repo, run, base = _bootstrapped_hook_repo(tmp_path)
    (repo / "f.txt").write_text("two\n", encoding="utf-8")
    run("add", "f.txt")
    tree = run("write-tree").stdout.strip()
    crafted = run("commit-tree", tree, "-p", base, "-m", "crafted").stdout.strip()
    assert run("update-ref", "refs/heads/crafted", crafted).returncode != 0
    assert run("rev-parse", "--verify", "--quiet", "refs/heads/crafted").returncode != 0
    assert run("branch", "-f", "forcebranch", crafted).returncode != 0
    assert run("reset", "--hard", crafted).returncode != 0
    assert _sha(repo, "HEAD") == base


def test_scratch_e2e_rewind_is_allowed(tmp_path: Path) -> None:
    """A rewind onto an ancestor is not a bypass and lands."""
    repo, run, base = _bootstrapped_hook_repo(tmp_path)
    (repo / "f.txt").write_text("two\n", encoding="utf-8")
    run("add", "f.txt")
    assert run("commit", "-m", "two").returncode == 0
    assert run("reset", "--hard", "HEAD~1").returncode == 0
    assert _sha(repo, "HEAD") == base
    audit_log = repo / ".git" / harness.GATE_STATE_DIR / "ref_audit.jsonl"
    assert audit_log.is_file()
