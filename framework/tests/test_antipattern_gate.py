"""Tests for the production anti-pattern gate."""

from __future__ import annotations

import subprocess
from pathlib import Path

import framework.gates.antipattern.python_checks
import framework.gates.antipattern.shell_checks
import framework.gates.antipattern.targets
from framework.gates import check_antipatterns as gate
from framework.gates.check_antipatterns import analyze_source

REPO = Path(__file__).resolve().parents[2]
PROLOGUE = "set -euo pipefail\n"


def codes(source: str, path: str = "research/example.py") -> set[str]:
    return {finding.code for finding in analyze_source(source, path)}


def shell_codes(source: str, path: str = "slurm/run.sbatch") -> set[str]:
    return {
        finding.code
        for finding in framework.gates.antipattern.shell_checks.analyze_shell(
            source, path
        )
    }


def test_safe_production_patterns_are_clean() -> None:
    source = """
import torch

payload = torch.load(path, weights_only=True)
for left, right in zip(lefts, rights, strict=True):
    pass
"""
    assert codes(source) == set()


def test_checked_exceptions_and_validated_non_strict_loads_are_clean() -> None:
    source = """
def install(module, state):
    result = module.load_state_dict(state, strict=False)
    if result.missing_keys or result.unexpected_keys:
        raise ValueError("state mismatch")

try:
    install(module, state)
except BaseException:
    cleanup()
    raise
"""
    assert codes(source) == set()


def test_runtime_and_deserialization_patterns_are_blocked() -> None:
    source = """
def load_cache(path):
    try:
        return torch.load(path)
    except RuntimeError:
        return None

assert ready
for left, right in zip(lefts, rights):
    pass
module.load_state_dict(state, strict=False)
"""
    assert codes(source) == {"HNS001", "HNS002", "HNS003", "HNS004", "HNS006"}


def test_explicit_unsafe_arguments_are_blocked() -> None:
    assert "HNS002" in codes("torch.load(path, weights_only=False)")
    assert "HNS002" in codes("torch.load(path, weights_only=flag)")
    assert "HNS003" in codes("zip(left, right, strict=False)")


def test_silent_exception_and_error_sentinel_fallbacks_are_blocked() -> None:
    source = """
def run():
    try:
        work()
    except OSError:
        pass
    return {"error": "work failed"}
"""
    assert codes(source) == {"HNS011", "HNS012"}


def test_recorded_optional_metric_failure_is_not_silent() -> None:
    source = """
try:
    metric = calculate_metric()
except RuntimeError as error:
    metric = None
    metric_errors.append(str(error))
"""
    assert codes(source) == set()


def test_broad_exception_and_cuda_fallback_are_blocked() -> None:
    source = """
try:
    run()
except BaseException:
    return_value = None

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
"""
    assert codes(source) == {"HNS005", "HNS007"}


def test_bare_except_is_broad_but_reraising_handler_is_clean() -> None:
    assert codes("try:\n    run()\nexcept:\n    recover()\n") == {"HNS005"}
    assert codes("try:\n    run()\nexcept:\n    recover()\n    raise\n") == set()


def test_cache_format_errors_treated_as_misses_are_blocked() -> None:
    format_mismatch = """
def load_basis_artifact(path):
    try:
        return read_payload(path)
    except (KeyError, ValueError, json.JSONDecodeError):
        return None
"""
    assert codes(format_mismatch) == {"HNS006"}

    missing_file = """
def load_basis_artifact(path):
    try:
        read_payload(path)
    except FileNotFoundError:
        return None
"""
    assert codes(missing_file) == set()

    unrelated = """
def summarize(rows):
    try:
        return rows["value"]
    except KeyError:
        return None
"""
    assert codes(unrelated) == set()


def test_candidate_scan_loop_does_not_count_as_silent_discard() -> None:
    scan = """
def _font():
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, 18)
        except OSError:
            pass
    return ImageFont.load_default()
"""
    assert codes(scan) == set()

    silent = """
def load_gradient_cache(path):
    try:
        return torch.load(path, weights_only=True)
    except OSError:
        pass
"""
    assert codes(silent) == {"HNS011"}


def test_discarded_non_strict_load_is_blocked() -> None:
    assert codes("pipe.unet.load_state_dict(state, strict=False)\n") == {"HNS004"}

    validated = """
def install(module, state):
    result = module.load_state_dict(state, strict=False)
    if result.missing_keys or result.unexpected_keys:
        raise ValueError("state mismatch")
"""
    assert codes(validated) == set()

    # Validation elsewhere in the function does not excuse discarding this result.
    discarded_after_validation = """
def install(module, state, other):
    checked = module.load_state_dict(state, strict=False)
    if checked.missing_keys or checked.unexpected_keys:
        raise ValueError("state mismatch")
    other.load_state_dict(state, strict=False)
"""
    assert codes(discarded_after_validation) == {"HNS004"}


def test_cuda_device_variants_and_statement_fallbacks_are_blocked() -> None:
    variant = (
        'device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")\n'
    )
    assert codes(variant) == {"HNS007"}

    statement = """
def pick():
    if not torch.cuda.is_available():
        device = torch.device("cpu")
    else:
        device = torch.device("cuda")
    return device
"""
    assert codes(statement) == {"HNS007"}


def test_explicit_cuda_refusal_and_guarded_maintenance_are_clean() -> None:
    refusal = """
def pick():
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for this run")
    return torch.device("cuda")
"""
    assert codes(refusal) == set()

    maintenance = """
def release():
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
"""
    assert codes(maintenance) == set()


def test_wall_clock_timers_are_blocked() -> None:
    assert codes("t_start = time.time()\n") == {"HNS014"}
    assert codes("elapsed = time.time() - t0\n") == {"HNS014"}
    assert codes("timestamp = time.time()\n") == set()
    assert codes("t0 = time.monotonic()\n") == set()


def test_unsafe_deserialization_and_dynamic_execution_are_blocked() -> None:
    assert codes("payload = pickle.load(handle)\n") == {"HNS015"}
    assert codes("payload = marshal.loads(blob)\n") == {"HNS015"}
    assert codes("weights = np.load(path, allow_pickle=True)\n") == {"HNS015"}
    assert codes("weights = np.load(path)\n") == set()
    assert codes("weights = np.load(path, allow_pickle=False)\n") == set()
    assert codes("payload = torch.load(path, weights_only=True)\n") == set()
    assert codes("value = eval(text)\n") == {"HNS016"}
    assert codes("value = exec(program)\n") == {"HNS016"}
    assert codes("value = ast.literal_eval(text)\n") == set()


def test_shell_execution_sinks_and_discarded_subprocess_are_blocked() -> None:
    """HNS017/HNS018 as named; a missing timeout (HNS027) is another rule's subject."""
    assert "HNS017" in codes("out = subprocess.run(cmd, shell=True)\n")
    assert "HNS017" in codes("os.system(cmd)\n")
    assert "HNS017" not in codes("out = subprocess.run(cmd, shell=False)\n")
    assert "HNS018" in codes("subprocess.run(cmd)\n")
    assert "HNS018" not in codes("subprocess.call(cmd, check=True)\n")

    inspected = """
result = subprocess.run(cmd)
if result.returncode:
    raise SystemExit(result.returncode)
"""
    assert "HNS018" not in codes(inspected)


def test_python_provenance_fallbacks_are_blocked() -> None:
    assert codes('commit = "unknown"\n') == {"HNS013"}
    assert codes('record = {"commit": "unknown"}\n') == {"HNS013"}
    assert codes('revision = record.get("git_revision", "unavailable")\n') == {"HNS013"}
    assert codes('DIRTY_SHA256 = "n/a"\n') == {"HNS013"}

    assert codes('carrier_stability_verdict = "unknown"\n') == set()
    assert (
        codes('token_geometry = basis_dict.get("token_geometry", "unknown")\n') == set()
    )
    assert codes("commit = git_commit()\n") == set()


def test_provenance_name_detection_is_precise() -> None:
    assert framework.gates.antipattern.python_checks._is_provenance_name("DIRTY_SHA256")
    assert framework.gates.antipattern.python_checks._is_provenance_name("tree_state")
    assert framework.gates.antipattern.python_checks._is_provenance_name("git_commit")
    assert framework.gates.antipattern.python_checks._is_provenance_name("commitHash")
    assert not framework.gates.antipattern.python_checks._is_provenance_name(
        "reverse_order"
    )
    assert not framework.gates.antipattern.python_checks._is_provenance_name(
        "stability_verdict"
    )


def test_provenance_fallbacks_are_blocked_in_shell() -> None:
    source = (
        PROLOGUE
        + """
commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)
git status --porcelain || true
"""
    )
    assert shell_codes(source) == {"HNS008", "HNS009"}


def test_provenance_assignment_fallbacks_are_blocked_in_shell() -> None:
    fallback = (
        PROLOGUE
        + """
if DIRTY_STATUS=$(git status --porcelain); then
  TREE_STATE=clean
else
  TREE_STATE=unknown
  DIRTY_SHA256=unavailable
fi
"""
    )
    assert shell_codes(fallback) == {"HNS008"}

    clean = (
        PROLOGUE
        + """
if DIRTY_STATUS=$(git status --porcelain); then
  TREE_STATE=clean
else
  TREE_STATE=dirty
fi
"""
    )
    assert shell_codes(clean) == set()


def test_swallowed_failures_are_blocked_except_cleanup() -> None:
    assert shell_codes(PROLOGUE + "python3 -m pytest tests/ -q || true\n") == {"HNS009"}
    assert shell_codes(PROLOGUE + 'sha256sum "$CERT" || :\n') == {"HNS009"}
    assert shell_codes(PROLOGUE + 'rm -f "$TMPFILE" || true\n') == set()
    assert shell_codes(PROLOGUE + 'kill "$PID" || true\n') == set()


def test_shell_fail_fast_is_required() -> None:
    assert shell_codes('cd "$ROOT"\necho start\n') == {"HNS019"}
    assert shell_codes('set -eu\ncd "$ROOT"\n') == {"HNS019"}
    assert shell_codes(PROLOGUE + 'cd "$ROOT"\n') == set()
    assert shell_codes("# comments only\n") == set()


def test_buffered_python_script_invocation_is_blocked() -> None:
    assert shell_codes(PROLOGUE + '"$PYTHON" scripts/run_example.py --flag\n') == {
        "HNS020"
    }
    assert shell_codes(PROLOGUE + "python3 scripts/run_example.py\n") == {"HNS020"}
    assert shell_codes(PROLOGUE + '"$PYTHON" -u scripts/run_example.py\n') == set()
    assert (
        shell_codes(
            PROLOGUE + '"$PYTHON" -u -m research.benchmark.architectures.joint.basis\n'
        )
        == set()
    )
    assert (
        shell_codes(
            PROLOGUE + 'export PYTHONUNBUFFERED=1\n"$PYTHON" scripts/run_example.py\n'
        )
        == set()
    )
    _unbuffered_forms_are_allowed()


def _unbuffered_forms_are_allowed() -> None:
    assert (
        shell_codes(PROLOGUE + 'PYTHONUNBUFFERED=1 "$PYTHON" scripts/run_example.py\n')
        == set()
    )
    assert (
        shell_codes(PROLOGUE + 'stdbuf -oL -eL "$PYTHON" scripts/run_example.py\n')
        == set()
    )
    assert shell_codes(PROLOGUE + '"$PYTHON" -m pytest tests/ -q\n') == set()
    assert (
        shell_codes(PROLOGUE + 'echo "run python scripts/run_example.py now"\n')
        == set()
    )


def test_non_production_paths_are_not_part_of_gate_scope() -> None:
    assert (
        framework.gates.antipattern.targets._files_to_check(["tests/example.py"]) == []
    )
    assert (
        framework.gates.antipattern.targets._files_to_check(
            ["framework/gates/check_antipatterns.py"]
        )
        == []
    )


def test_precommit_wires_the_gate_as_blocking_and_staged() -> None:
    hook = (REPO / "framework" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    assert "check_antipatterns.py" in hook
    assert "--strict --staged" in hook
    assert "exit 1" in hook


def test_cli_blocks_a_bad_worktree_file(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "research" / "bad.py"
    source.parent.mkdir()
    source.write_text("assert ready\n", encoding="utf-8")
    monkeypatch.setattr(framework.gates.antipattern.targets, "REPO", tmp_path)

    assert gate.main(["--strict", "research/bad.py"]) == 1


def test_cli_reads_staged_blob_not_unstaged_worktree(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path
    source = repo / "research" / "example.py"
    source.parent.mkdir()
    source.write_text("for a, b in zip(xs, ys, strict=True):\n    pass\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "research/example.py"], cwd=repo, check=True)

    # The index contains the safe version; the working tree is now unsafe.
    source.write_text("for a, b in zip(xs, ys):\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(framework.gates.antipattern.targets, "REPO", repo)

    assert gate.main(["--strict", "--staged", "research/example.py"]) == 0
    assert gate.main(["--strict", "research/example.py"]) == 1


def test_cli_ignores_non_production_paths(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "tests" / "example.py"
    source.parent.mkdir()
    source.write_text("assert False\n", encoding="utf-8")
    monkeypatch.setattr(framework.gates.antipattern.targets, "REPO", tmp_path)

    assert gate.main(["--strict", "tests/example.py"]) == 0


def test_cli_reports_syntax_errors_as_gate_findings(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "scripts" / "broken.py"
    source.parent.mkdir()
    source.write_text("def broken(:\n", encoding="utf-8")
    monkeypatch.setattr(framework.gates.antipattern.targets, "REPO", tmp_path)

    assert gate.main(["--strict", "scripts/broken.py"]) == 1


def test_directory_arguments_expand_to_checked_files(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "research" / "pkg").mkdir(parents=True)
    (tmp_path / "research" / "pkg" / "bad.py").write_text(
        "assert ready\n", encoding="utf-8"
    )
    (tmp_path / "research" / "pkg" / "good.py").write_text(
        "value = 1\n", encoding="utf-8"
    )
    (tmp_path / "slurm").mkdir()
    (tmp_path / "slurm" / "job.sbatch").write_text("echo hi\n", encoding="utf-8")
    monkeypatch.setattr(framework.gates.antipattern.targets, "REPO", tmp_path)

    assert framework.gates.antipattern.targets._files_to_check(["research"]) == [
        "research/pkg/bad.py",
        "research/pkg/good.py",
    ]
    assert gate.main(["--strict", "research"]) == 1
    assert gate.main(["--strict", "slurm"]) == 1

    (tmp_path / "slurm" / "job.sbatch").write_text(
        PROLOGUE + "echo hi\n", encoding="utf-8"
    )
    assert gate.main(["--strict", "slurm", "research/pkg/good.py"]) == 0


def test_paths_outside_the_repo_are_out_of_scope(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "elsewhere" / "bad.py"
    outside.parent.mkdir()
    outside.write_text("assert ready\n", encoding="utf-8")
    monkeypatch.setattr(framework.gates.antipattern.targets, "REPO", repo)

    assert framework.gates.antipattern.targets._files_to_check([str(outside)]) == []
    assert gate.main(["--strict", str(outside)]) == 0


def _committed_production_files() -> list[str]:
    result = subprocess.run(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            "HEAD",
            "--",
            *sorted(framework.gates.antipattern.targets.PRODUCTION_ROOTS),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        line
        for line in result.stdout.splitlines()
        if Path(line).suffix.lower()
        in framework.gates.antipattern.targets.CHECKED_SUFFIXES
    ]


def _committed_source(path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        cwd=REPO,
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8")


def test_committed_production_tree_is_parseable() -> None:
    """Every committed production file must be parseable by the gate.

    A ``HNS000`` here means the gate would fail closed on unreadable source:
    the file is missing from the check, not the gate.  Legacy findings in
    committed files are deliberately not asserted here — the blocking hook
    covers staged files, and concurrent work-in-progress is out of scope.
    """

    paths = _committed_production_files()
    assert paths, "production tree discovery matched no committed file"
    assert "scripts/setup/setup_framework.py" in paths, paths

    unparseable = [
        finding
        for path in paths
        for finding in analyze_source(_committed_source(path), path)
        if finding.code == "HNS000"
    ]
    assert unparseable == [], "\n".join(finding.format() for finding in unparseable)


def test_extended_python_antipattern_rules() -> None:
    bad = """
import datetime, yaml, torch
for _ in range(2):
    torch.cuda.empty_cache()
with open("foo.txt", "w") as f:
    pass
ts = datetime.datetime.now()
data = yaml.load("a: 1")
"""
    assert codes(bad) == {"HNS021", "HNS022", "HNS023", "HNS024"}
    good = """
from datetime import datetime, timezone
import yaml, torch
torch.cuda.empty_cache()
with open("foo.txt", "w", encoding="utf-8") as f:
    pass
with open("foo.bin", "wb") as f:
    pass
ts = datetime.now(timezone.utc)
data = yaml.safe_load("a: 1")
"""
    assert codes(good) == set()


def test_dirty_refusal_rules() -> None:
    """HNS035 bans the override knob and HNS036 bans a conditional refusal."""
    retired = {"HNS035", "HNS036"}
    override = (
        "#SBATCH --job-name=t\n"
        'if [[ -n "$DIRTY_STATUS" ]]; then\n'
        "  if [[ ${RESEARCH_ALLOW_DIRTY_RUN:-0} != 1 ]]; then\n"
        '    echo "REFUSING RUN: dirty tree" >&2\n'
        "    exit 90\n"
        "  fi\n"
        "fi\n"
    )
    assert {"HNS035", "HNS036"} <= shell_codes(override, "slurm/job.sbatch")
    unconditional = (
        "#SBATCH --job-name=t\n"
        'if [[ -n "$DIRTY_STATUS" ]]; then\n'
        '  echo "REFUSING RUN: dirty tree; commit the work before submitting" >&2\n'
        "  exit 90\n"
        "fi\n"
    )
    assert not shell_codes(unconditional, "slurm/job.sbatch") & retired
    assert not shell_codes("echo DISALLOW_DIRTY_NOTES=1\n", "scripts/run.sh") & retired


def test_extended_shell_antipattern_rules() -> None:
    bad = "#SBATCH --job-name=test\nset -euo pipefail\necho ok\n"
    assert "HNS025" in shell_codes(bad, "slurm/job.sbatch")
    assert "HNS026" in shell_codes(bad, "slurm/job.sbatch")
    good = (
        "#SBATCH --job-name=test\n"
        "set -euo pipefail\n"
        "export PYTHONPATH=/checkout\n"
        "export PYTHONUNBUFFERED=1\n"
        "echo ok\n"
    )
    assert shell_codes(good, "slurm/job.sbatch") == set()
    assert shell_codes(bad, "scripts/run.sh") == set()
