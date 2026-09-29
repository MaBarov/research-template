"""Acceptance tests for the sbatch provenance contract (the unchangeable gate).

Thumbnail: Pins the contract checker's five rules, including the two that ban a dirty-run override.

Invariants & Expected State:
    The checker is the single source of truth shared by the pre-commit hook and
    ``framework/gates/sbatch_gate.sh``, so its own behaviour is pinned here: a
    script that satisfies the contract exits 0, and each violation exits 1 with
    the offending line named.  The corpus case runs the checker over every
    committed job script, so a script edited in this worktree cannot weaken the
    evidence; a new job script joins that case automatically.  The override and
    refusal-shape rules (user ruling 2026-09-26) are pinned from both sides: the
    knob is rejected, and a refusal nested behind a condition is rejected even
    when the literal is present.  The guard's *claim reconciliation* is pinned
    behaviourally against ``slurm/template.sbatch`` itself, because a stamp is a
    claim and text assertions cannot see whether it was compared: a pin that
    contradicts the root's ``.research_commit`` — or a checkout's HEAD — refuses with
    90 and names both values, while a pin that matches the tree runs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHECKER = "framework/gates/check_sbatch_contract.sh"

PROLOGUE = """#!/usr/bin/env bash
#SBATCH --job-name=research_contract_test
#SBATCH --time=00:20:00
set -euo pipefail
export HF_HOME=$ROOT/hf-cache
export PYTHONUNBUFFERED=1
"""

GUARD = """if COMMIT=$(git rev-parse HEAD 2>/dev/null); then
  if [[ -n "$DIRTY_STATUS" ]]; then
    echo "REFUSING RUN: dirty tree; commit the work before submitting" >&2
    exit 90
  fi
else
  COMMIT=${RESEARCH_COMMIT:?}
fi
echo "status=RESEARCH_CONTRACT_TEST_START job=${SLURM_JOB_ID:-local} commit=$COMMIT"
"""


def check(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    """Run the contract checker on one script written from ``body``."""
    script = tmp_path / "job.sbatch"
    script.write_text(body, encoding="utf-8")
    return subprocess.run(
        ["bash", CHECKER, str(script)],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_a_script_that_satisfies_the_contract_passes(tmp_path: Path) -> None:
    result = check(tmp_path, PROLOGUE + GUARD)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_the_template_satisfies_the_contract() -> None:
    """The canonical template is what new scripts copy, so it is the reference."""
    result = subprocess.run(
        ["bash", CHECKER, "slurm/template.sbatch"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr


def test_every_committed_job_script_satisfies_the_contract() -> None:
    """The committed corpus is clean: the gate cannot be satisfied by exceptions."""
    listed = subprocess.run(
        ["git", "ls-files", "slurm/*.sbatch"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    scripts = [line for line in listed.stdout.splitlines() if line]
    assert scripts, "the job-script corpus vanished; check the pathspec"
    assert "slurm/template.sbatch" in scripts, scripts

    result = subprocess.run(
        ["bash", CHECKER, *scripts],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr


def test_a_dirty_run_override_is_rejected(tmp_path: Path) -> None:
    body = PROLOGUE + GUARD.replace(
        '    echo "REFUSING RUN: dirty tree; commit the work before submitting" >&2\n',
        "    if [[ ${RESEARCH_ALLOW_DIRTY_RUN:-0} != 1 ]]; then\n"
        '      echo "REFUSING RUN: dirty tree" >&2\n'
        "      exit 90\n"
        "    fi\n",
    )

    result = check(tmp_path, body)

    assert result.returncode == 1
    assert "a dirty-run override is banned" in result.stderr


def test_a_conditional_refusal_is_rejected(tmp_path: Path) -> None:
    """The literal alone is not enough: it must lead the dirty branch."""
    body = PROLOGUE + GUARD.replace(
        '    echo "REFUSING RUN: dirty tree; commit the work before submitting" >&2\n',
        '    if [[ -z "${RESEARCH_FORCE_IT:-}" ]]; then\n'
        '      echo "REFUSING RUN: dirty tree" >&2\n'
        "      exit 90\n"
        "    fi\n",
    )

    result = check(tmp_path, body)

    assert result.returncode == 1
    assert "does not lead the dirty branch" in result.stderr


def test_a_refusal_without_its_exit_is_rejected(tmp_path: Path) -> None:
    """A refusal that falls through to the run is worse than none at all."""
    body = PROLOGUE + GUARD.replace("    exit 90\n", "    :\n")

    result = check(tmp_path, body)

    assert result.returncode == 1
    assert "not followed by 'exit 90'" in result.stderr


def test_a_script_without_the_refusal_is_rejected(tmp_path: Path) -> None:
    result = check(tmp_path, PROLOGUE + 'echo "status=x commit=$COMMIT"\n')

    assert result.returncode == 1
    assert "missing the 'REFUSING RUN: dirty tree' runtime refusal" in result.stderr


def test_a_script_without_a_commit_or_stamp_is_rejected(tmp_path: Path) -> None:
    result = check(tmp_path, PROLOGUE + "echo running\n")

    assert result.returncode == 1
    assert "missing commit resolution" in result.stderr
    assert "missing 'status=... commit=<commit>' stamp" in result.stderr


def test_the_checker_reports_a_missing_file(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", CHECKER, str(tmp_path / "gone.sbatch")],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 1
    assert "missing file" in result.stderr


# --- the guard's claim reconciliation (behaviour, not text) -----------------
#
# The incident these pin: four cluster jobs were submitted as
# ``cd $root && sbatch script``, which does not set ``RESEARCH_ROOT``, so they ran the
# arm's default deploy root while a pinned ``RESEARCH_COMMIT`` made their start lines
# read the commit the submitter intended.  The canonical guard body is run here
# against throwaway roots with stub interpreters, so what is asserted is what the
# guard does, never what it says.

TEMPLATE = REPO / "slurm" / "template.sbatch"
FOREIGN = "0" * 40


def run_template(root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run the canonical guard body against ``root`` with the given overrides."""
    base = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(root),
        "RESEARCH_ROOT": str(root),
        "RESEARCH_TEST_PYTHON": "/bin/true",
    }
    base.update(env)
    return subprocess.run(
        ["bash", str(TEMPLATE)],
        cwd=str(root),
        env=base,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def rsync_root(tmp_path: Path, stamped: str) -> Path:
    """A deploy root with no checkout, carrying the stamp the sync wrote."""
    root = tmp_path / "rsync-root"
    root.mkdir()
    (root / ".research_commit").write_text(stamped, encoding="utf-8")
    return root


def checkout(tmp_path: Path) -> tuple[Path, str]:
    """A clean single-commit checkout, with the commit it sits at."""
    root = tmp_path / "checkout"
    root.mkdir()
    git = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], cwd=root, check=True, timeout=120)
    subprocess.run(
        [*git, "commit", "--allow-empty", "-q", "-m", "x"],
        cwd=root,
        check=True,
        timeout=120,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    ).stdout.strip()
    return root, head


def test_a_pin_that_contradicts_an_rsync_root_is_refused(tmp_path: Path) -> None:
    """The observed failure: the root's stamp and the caller's pin disagree."""
    root = rsync_root(tmp_path, stamped=FOREIGN)

    result = run_template(root, {"RESEARCH_COMMIT": "1" * 40})

    assert result.returncode == 90
    assert f"RESEARCH_COMMIT={'1' * 40} disagrees with" in result.stderr


def test_a_stamp_file_is_the_only_claim_when_no_pin_is_given(tmp_path: Path) -> None:
    """Without a pin the root's own stamp is the claim, and it is honest."""
    root = rsync_root(tmp_path, stamped=FOREIGN)

    result = run_template(root, {})

    assert result.returncode == 0
    assert f"commit={FOREIGN}" in result.stdout
    assert "tree_state=external-commit" in result.stdout


def test_a_pin_without_a_stamp_or_checkout_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "bare"
    root.mkdir()

    result = run_template(root, {})

    assert result.returncode == 90
    assert "RESEARCH_COMMIT was not provided" in result.stderr


def test_a_pin_matching_the_checkout_runs(tmp_path: Path) -> None:
    root, head = checkout(tmp_path)

    result = run_template(root, {"RESEARCH_COMMIT": head})

    assert result.returncode == 0
    assert f"commit={head}" in result.stdout
    assert "tree_state=clean" in result.stdout


def test_a_pin_that_contradicts_the_checkout_is_refused(tmp_path: Path) -> None:
    """A pin must not be able to vouch for a tree it does not describe."""
    root, _head = checkout(tmp_path)

    result = run_template(root, {"RESEARCH_COMMIT": FOREIGN})

    assert result.returncode == 90
    assert "disagrees with the checkout at" in result.stderr
