"""End-to-end tests for the sbatch gate's queue mode.

Each test builds a *committed* scratch repository holding the trees the gate
reads, puts fake ``sbatch``/``squeue`` clients first on ``PATH`` (so no test can
reach the host's Slurm), and runs the real gate.  That exercises the strict
path, the manifest writer, the queue CLI and the queue store together, without
touching this repository's ``results/`` ledger.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from framework import harness
from scripts.slurm_queue import model
from scripts.slurm_queue.store import QueueStore

REPO = Path(__file__).resolve().parents[2]
TREES = ("research", "framework", "scripts", "slurm", "experiments")
GATE = "framework/gates/sbatch_gate.sh"
PAYLOAD = "slurm/template.sbatch"
WORKER = "slurm/run_slurm_queue_worker.sbatch"
# The gate enqueues into the harness default cluster; read it from the same
# source instead of restating a cluster name here.
CLUSTER = harness.QUEUE_CLUSTERS[0]


def scratch_repo(tmp_path: Path) -> Path:
    """Copy the trees the gate reads into a scratch repository committed at HEAD."""
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in TREES:
        shutil.copytree(
            REPO / name,
            repo / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    (repo / ".gitignore").write_text(
        "results/\n__pycache__/\n*.pyc\n", encoding="utf-8"
    )
    (repo / "results").mkdir()
    for args in (
        ["init", "-q"],
        ["add", "-A"],
        [
            "-c",
            "user.email=queue@test",
            "-c",
            "user.name=queue",
            "commit",
            "-qm",
            "base",
        ],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return repo


def commit_repo(repo: Path, message: str = "scratch") -> None:
    """Commit everything in the scratch repository so the gate sees a clean tree."""
    for args in (
        ["add", "-A"],
        [
            "-c",
            "user.email=queue@test",
            "-c",
            "user.name=queue",
            "commit",
            "-qm",
            message,
        ],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def fake_slurm(
    tmp_path: Path, repo: Path, *, job_id: str = "777001"
) -> tuple[Path, Path]:
    """Write fake sbatch/squeue clients; sbatch snapshots the repo when it submits."""
    binary = tmp_path / "bin"
    binary.mkdir()
    snapshot = tmp_path / "submit_snapshot.txt"
    sbatch = binary / "sbatch"
    sbatch.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'for arg in "$@"; do\n'
        '  if [ "$arg" = "--test-only" ]; then echo "test-only ok"; exit 0; fi\n'
        "done\n"
        f'find "{repo}/results" -name "*.json" -printf "%P\\n" 2>/dev/null'
        f" | sort > {snapshot}\n"
        f'echo "{job_id};{CLUSTER}"\n',
        encoding="utf-8",
    )
    sbatch.chmod(0o755)
    squeue = binary / "squeue"
    squeue.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    squeue.chmod(0o755)
    return binary, snapshot


def gate_env(binary: Path, **extra: str) -> dict[str, str]:
    """Return a strict gate environment that cannot reach the host's Slurm."""
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{binary}:{env['PATH']}",
            # The gates and the smoke drivers must run under the interpreter that
            # runs this suite: the host's bare python3 can be older than the
            # project floor, which the gate now refuses.
            "RESEARCH_PYTHON": sys.executable,
            "SMOKE_PYTHON": sys.executable,
            "SBATCH_GATE_STRICT": "1",
            "CANARY": "0",
            "OMP_SESSION_ID": "queue-gate-test",
        }
    )
    for name in (
        "RESEARCH_SBATCH_QUEUE",
        "RESEARCH_QUEUE_ROOT",
        "RESEARCH_QUEUE_WORKER_TIME",
    ):
        env.pop(name, None)
    env.update(extra)
    return env


def run_gate(
    repo: Path, script: str, env: dict[str, str], *flags: str
) -> subprocess.CompletedProcess:
    """Run the real gate inside the scratch repository."""
    return subprocess.run(
        ["bash", str(repo / GATE), script, *flags],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )


def only_lane(repo: Path) -> tuple[QueueStore, Path, model.ResourceProfile]:
    """Return the store, lane directory and profile of the single live lane."""
    store = QueueStore(root=repo / "results" / "slurm_queue")
    lanes = sorted((store.root / CLUSTER).iterdir())
    assert len(lanes) == 1
    return store, lanes[0], store.read_profile(CLUSTER, lanes[0].name)


def test_strict_queue_mode_enqueues_the_payload_in_its_lane(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    binary, _snapshot = fake_slurm(tmp_path, repo)
    env = gate_env(binary, RESEARCH_SBATCH_QUEUE="1", SBATCH_RUN_NAME="queue_gate_test")
    result = run_gate(repo, PAYLOAD, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[sbatch_gate] queued: item=" in result.stdout
    store, lane, profile = only_lane(repo)
    pending = store.pending_items(profile)
    assert len(pending) == 1
    item = pending[0]
    committed = model.run_git(repo, ["show", f"HEAD:{PAYLOAD}"])
    assert item.script == PAYLOAD
    assert item.script_sha256 == model.sha256_text(committed)
    assert item.commit == model.head_commit(repo)
    assert item.run_name == "queue_gate_test"
    assert (profile.partition, profile.cpus_per_task, item.requested_seconds) == (
        "all",
        4,
        1200,
    )
    assert str(store.read_worker(profile)["job_id"]) == "777001"
    assert not list(lane.glob("running/*.json")) and not list(
        lane.glob("succeeded/*.json")
    )
    assert json.loads(
        (repo / "results" / "gate_log.jsonl").read_text().strip().splitlines()[-1]
    )


def test_manifest_exists_before_the_item_is_published(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    binary, snapshot = fake_slurm(tmp_path, repo)
    env = gate_env(
        binary, RESEARCH_SBATCH_QUEUE="1", SBATCH_RUN_NAME="queue_gate_order"
    )
    assert run_gate(repo, PAYLOAD, env).returncode == 0
    manifest = repo / "results" / "manifests" / "queue_gate_order.json"
    store, lane, profile = only_lane(repo)
    item_path = lane / "pending" / f"{store.pending_items(profile)[0].item_id}.json"
    assert "manifests/queue_gate_order.json" in snapshot.read_text(encoding="utf-8")
    assert manifest.stat().st_mtime_ns <= item_path.stat().st_mtime_ns


def test_gate_records_the_resolved_run_settings(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    binary, _snapshot = fake_slurm(tmp_path, repo)
    env = gate_env(
        binary,
        SBATCH_RUN_NAME="gate_settings",
        SBATCH_RUN_SETTINGS=("model_id=demo-model,max_round_dose=0.4,carrier_rank=19"),
    )
    result = run_gate(repo, PAYLOAD, env)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(
        (repo / "results" / "manifests" / "gate_settings.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["settings"] == {
        "model_id": "demo-model",
        "max_round_dose": "0.4",
        "carrier_rank": "19",
    }


def test_dry_run_leaves_no_manifest_and_no_queue_state(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    binary, snapshot = fake_slurm(tmp_path, repo)
    env = gate_env(binary, RESEARCH_SBATCH_QUEUE="1", SBATCH_RUN_NAME="queue_dry")
    result = run_gate(repo, PAYLOAD, env, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not snapshot.exists()
    assert not (repo / "results" / "manifests").exists()
    assert not (repo / "results" / "slurm_queue").exists()


def test_gate_logs_into_a_deploy_root_without_results(tmp_path: Path) -> None:
    # A staged deploy root ships no results/ (it is gitignored), so the gate has
    # to create its own log directory instead of dropping every event.
    repo = scratch_repo(tmp_path)
    shutil.rmtree(repo / "results")
    binary, _snapshot = fake_slurm(tmp_path, repo)
    env = gate_env(binary, RESEARCH_SBATCH_QUEUE="1", SBATCH_RUN_NAME="queue_log_dir")
    result = run_gate(repo, PAYLOAD, env)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = (repo / "results" / "gate_log.jsonl").read_text().strip().splitlines()
    assert json.loads(lines[-1])["result"] == "pass"


def test_gate_smoke_gates_the_new_worker_script(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    binary, snapshot = fake_slurm(tmp_path, repo)
    env = gate_env(binary, SBATCH_RUN_NAME="worker_gate")
    result = run_gate(repo, WORKER, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "stub-smoke PASS" in result.stdout
    assert "scripts/smoke/worker_smoke.sh" in result.stdout
    assert "cli_smoke.sh" not in result.stdout
    assert snapshot.exists()


def test_enqueue_refusal_blocks_the_gate_in_queue_mode(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    binary, snapshot = fake_slurm(tmp_path, repo)
    env = gate_env(binary, RESEARCH_SBATCH_QUEUE="1", SBATCH_RUN_NAME="queue_refused")
    result = run_gate(repo, WORKER, env)
    assert result.returncode == 1
    assert "QUEUE ENQUEUE FAILED" in result.stderr
    assert not snapshot.exists()
    assert not (repo / "results" / "slurm_queue").exists()


def test_preflight_runs_the_local_gates_and_skips_the_submit(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    binary, snapshot = fake_slurm(tmp_path, repo)
    env = gate_env(binary, SBATCH_GATE_PREFLIGHT="1")
    result = run_gate(repo, PAYLOAD, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[sbatch_gate] PREFLIGHT PASS" in result.stdout
    assert not snapshot.exists()
    assert not (repo / "results" / "slurm_queue").exists()
    assert not (repo / "results" / "manifests").exists()
    lines = (repo / "results" / "gate_log.jsonl").read_text().strip().splitlines()
    assert json.loads(lines[-1])["gate"] == "preflight"
    assert json.loads(lines[-1])["result"] == "pass"


def test_preflight_blocks_a_payload_without_the_provenance_contract(
    tmp_path: Path,
) -> None:
    repo = scratch_repo(tmp_path)
    binary, snapshot = fake_slurm(tmp_path, repo)
    (repo / "slurm" / "broken.sbatch").write_text(
        "#!/usr/bin/env bash\n"
        "#SBATCH --job-name=research_broken\n"
        "#SBATCH --time=00:20:00\n"
        "echo no-provenance-stamp\n",
        encoding="utf-8",
    )
    commit_repo(repo)
    env = gate_env(binary, SBATCH_GATE_PREFLIGHT="1")
    result = run_gate(repo, "slurm/broken.sbatch", env)
    assert result.returncode == 1
    assert "FAIL(provenance-stamp)" in result.stderr
    assert "PREFLIGHT BLOCK" in result.stderr
    assert not snapshot.exists()


def test_preflight_refuses_a_dirty_tree_with_no_override(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    binary, snapshot = fake_slurm(tmp_path, repo)
    payload = repo / PAYLOAD
    payload.write_text(payload.read_text(encoding="utf-8") + "\n# uncommitted\n")
    env = gate_env(binary, SBATCH_GATE_PREFLIGHT="1", RESEARCH_ALLOW_DIRTY_RUN="1")

    result = run_gate(repo, PAYLOAD, env)

    assert result.returncode == 1
    assert "FAIL(dirty-tree)" in result.stderr
    assert "PREFLIGHT BLOCK" in result.stderr
    assert "NOTE(dirty-tree)" not in result.stderr
    assert not snapshot.exists()


def test_gate_refuses_a_nonbinary_strict_value(tmp_path: Path) -> None:
    repo = scratch_repo(tmp_path)
    binary, _snapshot = fake_slurm(tmp_path, repo)
    result = run_gate(repo, PAYLOAD, gate_env(binary, SBATCH_GATE_STRICT="banana"))
    assert result.returncode == 2
    assert "SBATCH_GATE_STRICT must be 0 or 1" in result.stderr
