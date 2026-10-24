"""Tests for the instruction-reference gate (HNS073).

Thumbnail: Verifies path resolution, anchor handling, and reference rot detection.

Invariants & Expected State:
    - Tests exact paths, boundary suffixes, fenced commands and placeholders.
    - Verifies exit codes under strict, staged, sibling and corpus modes.
    - Verifies that files outside the declared corpus stay silent.
"""

from __future__ import annotations

from pathlib import Path

from framework import harness
from framework.gates.instructions import check_instruction_refs as gate
from framework.tests.hook_hygiene.git_env_fixture import run_git


def _git(repo: Path, *args: str) -> None:
    """Run one Git command in a scratch repository."""
    run_git(repo, *args, check=True)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_an_exact_tracked_path_resolves() -> None:
    tracked = ["framework/gates/checks/check_test_mirror.py"]
    text = "See `framework/gates/checks/check_test_mirror.py`.\n"
    assert gate.grade("AGENTS.md", text, tracked) == []


def test_a_path_with_anchor_resolves() -> None:
    tracked = ["framework/gates/sbatch_gate.sh"]
    text = "See `framework/gates/sbatch_gate.sh#L12` and `sbatch_gate.sh#anchor`.\n"
    assert gate.grade("AGENTS.md", text, tracked) == []


def test_a_path_boundary_suffix_resolves() -> None:
    tracked = ["framework/gates/sbatch_gate.sh"]
    assert gate.grade("AGENTS.md", "See `sbatch_gate.sh`.\n", tracked) == []


def test_a_non_boundary_suffix_does_not_resolve() -> None:
    tracked = ["framework/gates/sbatch_gate.sh"]
    findings = gate.grade("AGENTS.md", "See `gate.sh`.\n", tracked)
    assert [finding.code for finding in findings] == ["HNS073"]


def test_non_path_shapes_stay_silent() -> None:
    shapes = (
        "`<name>_smoke.sh`",
        "`results/**`",
        "`https://example.com/a.md`",
        "`float/int/bool`",
        "`framework/gates/`",
    )
    text = " ".join(shapes) + "\n"
    assert gate.grade("AGENTS.md", text, ["framework/gates/sbatch_gate.sh"]) == []


def _root(tracked: list[str]) -> gate.Root:
    """Build one flat repository root over ``tracked``."""
    return gate.Root(
        "repo",
        Path("/nonexistent"),
        tuple(tracked),
        frozenset(tracked),
        {},
        frozenset(),
    )


def test_a_fenced_command_path_resolves() -> None:
    """A bare script path on a fenced command line is a graded token."""
    tracked = ["scripts/smoke/test_smoke.sh"]
    text = "```bash\npython scripts/smoke/test_smoke.sh\n```\n"
    assert gate.grade("AGENTS.md", text, tracked) == []


def test_a_fenced_command_path_reports_its_line() -> None:
    """A missing fenced command path is a finding on the command's line."""
    text = "intro\n```sh\nbash scripts/smoke/test_smoke.sh\n```\n"
    findings = gate.grade("AGENTS.md", text, ["scripts/other/keep.sh"])
    assert [(finding.code, finding.line) for finding in findings] == [("HNS073", 3)]


def test_paths_outside_fenced_commands_stay_silent() -> None:
    """A bare path is graded only when a fence holds a command line."""
    tracked = ["scripts/other/keep.sh"]
    prose = "python scripts/smoke/test_smoke.sh\n"
    fenced = "```bash\necho scripts/smoke/test_smoke.sh\n```\n"
    assert gate.grade("AGENTS.md", prose, tracked) == []
    assert gate.grade("AGENTS.md", fenced, tracked) == []


def test_a_fenced_command_placeholder_is_preserved() -> None:
    """Angle brackets in a command path survive and classify as placeholder."""
    text = "```bash\nsbatch slurm/<name>_smoke.sh\n```\n"
    counts = gate.census("AGENTS.md", text, [_root([])], allow_placeholder=True).counts
    assert counts["placeholder"] == 1


def test_a_stale_token_reports_its_line() -> None:
    text = "line one\nline two\nSee `framework/gates/instructions/absent_probe.py`.\n"
    findings = gate.grade("AGENTS.md", text, ["framework/gates/sbatch_gate.sh"])
    assert [(finding.code, finding.line) for finding in findings] == [("HNS073", 3)]
    assert "absent_probe.py" in findings[0].message


def test_a_token_repeated_names_its_first_line_only() -> None:
    text = "`absent_probe.py`\n`absent_probe.py`\n"
    findings = gate.grade("AGENTS.md", text, [])
    assert [finding.line for finding in findings] == [1]


def test_cli_staged_reads_the_index(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo / "framework" / "gates" / "sbatch_gate.sh", "#!/bin/bash\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "framework/gates/sbatch_gate.sh")
    monkeypatch.setattr(gate, "REPO", repo)

    _write(repo / "AGENTS.md", "Ref: `framework/gates/absent_probe.py`\n")
    _git(repo, "add", "AGENTS.md")
    assert gate.main(["--strict", "--staged"]) == 1
    assert "HNS073" in capsys.readouterr().err

    _write(repo / "AGENTS.md", "Ref: `framework/gates/sbatch_gate.sh`\n")
    _git(repo, "add", "AGENTS.md")
    assert gate.main(["--strict", "--staged"]) == 0


def test_cli_unreadable_file_is_an_environment_error(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    monkeypatch.setattr(gate, "REPO", repo)

    assert gate.main(["--strict", "AGENTS.md"]) == 2


def test_cli_passes_on_the_real_instruction_file() -> None:
    """The canonical AGENTS.md resolves every path it names."""
    assert gate.main(["--strict"]) == 0


def test_roots_count_a_sibling_tree(tmp_path: Path, monkeypatch, capsys) -> None:
    """A token only a sibling tree provides is counted, never failed."""
    primary = tmp_path / "primary"
    sibling = tmp_path / "sibling"
    for repo in (primary, sibling):
        repo.mkdir()
        _git(repo, "init", "-q")
    _write(primary / "AGENTS.md", "Ref: `framework/gates/sbatch_gate.sh`\n")
    _write(sibling / "framework" / "gates" / "sbatch_gate.sh", "#!/bin/bash\n")
    _git(sibling, "add", "framework/gates/sbatch_gate.sh")
    monkeypatch.setattr(gate, "REPO", primary)

    args = ["--strict", str(primary / "AGENTS.md"), "--roots", str(sibling)]
    assert gate.main(args) == 0
    assert "sibling=1" in capsys.readouterr().out


def test_moved_bucket_names_the_target(tmp_path: Path, monkeypatch, capsys) -> None:
    """A basename that lives at another path fails and names the target."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _write(repo / "framework" / "gates" / "checks" / "local_gate.py", "# moved\n")
    _git(repo, "add", "framework/gates/checks/local_gate.py")
    monkeypatch.setattr(gate, "REPO", repo)
    _write(repo / "AGENTS.md", "Ref: `framework/gates/local_gate.py`\n")

    assert gate.main(["--strict"]) == 1
    assert "sole basename match at repo:framework/gates/checks/local_gate.py" in (
        capsys.readouterr().err
    )


def test_placeholder_fails_unless_allowed(tmp_path: Path, monkeypatch, capsys) -> None:
    """Example-shaped paths fail by default and are counted under the flag."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    monkeypatch.setattr(gate, "REPO", repo)
    _write(repo / "AGENTS.md", f"Ref: `{harness.SLUG}/x/y.py`\n")

    assert gate.main(["--strict"]) == 1
    capsys.readouterr()
    assert gate.main(["--strict", "--allow-placeholder"]) == 0
    assert "placeholder=1" in capsys.readouterr().out


def test_corpus_root_enumerates_rules_and_skills(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """--corpus-root grades that tree's rules, skills and AGENTS.md."""
    repo = tmp_path / "repo"
    agent_root = tmp_path / "agent-config"
    repo.mkdir()
    _git(repo, "init", "-q")
    _write(repo / "framework" / "gates" / "sbatch_gate.sh", "#!/bin/bash\n")
    _git(repo, "add", "framework/gates/sbatch_gate.sh")
    _write(repo / "AGENTS.md", "Repo: `framework/gates/sbatch_gate.sh`\n")
    monkeypatch.setattr(gate, "REPO", repo)
    for path in (
        agent_root / "rules" / "a.md",
        agent_root / "managed-skills" / "s" / "SKILL.md",
        agent_root / "AGENTS.md",
    ):
        _write(path, "Ref: `framework/gates/sbatch_gate.sh`\n")

    assert gate.main(["--strict", "--corpus-root", str(agent_root)]) == 0
    assert "checked 4 file(s)" in capsys.readouterr().out


def test_bare_filename_is_counted_under_roots(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """A bare filename is ambiguous across roots: counted, never failed."""
    primary = tmp_path / "primary"
    sibling = tmp_path / "sibling"
    for repo in (primary, sibling):
        repo.mkdir()
        _git(repo, "init", "-q")
    _write(primary / "AGENTS.md", "Ref: `absent_probe.py`\n")
    monkeypatch.setattr(gate, "REPO", primary)

    args = ["--strict", str(primary / "AGENTS.md"), "--roots", str(sibling)]
    assert gate.main(args) == 0
    assert "filename=1" in capsys.readouterr().out


def test_output_path_is_counted_not_failed(tmp_path: Path, monkeypatch, capsys) -> None:
    """A path under a directory no root tracks (a produced artifact) passes."""
    repo = tmp_path / "repo"
    sibling = tmp_path / "sibling"
    for tree in (repo, sibling):
        tree.mkdir()
        _git(tree, "init", "-q")
    _write(
        repo / "AGENTS.md", "Artifact: `checkpoints/seam_diagnostics_round_01.json`\n"
    )
    monkeypatch.setattr(gate, "REPO", repo)

    args = ["--strict", str(repo / "AGENTS.md"), "--roots", str(sibling)]
    assert gate.main(args) == 0
    assert "output=1" in capsys.readouterr().out


def test_files_outside_corpus_stay_silent(tmp_path: Path, monkeypatch, capsys) -> None:
    """A file outside the declared corpus is skipped without findings."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _write(repo / "outside.py", "Ref: `nonexistent_file.py`\n")
    monkeypatch.setattr(gate, "REPO", repo)

    assert gate.main(["--strict", str(repo / "outside.py")]) == 0
    assert "checked 0 file(s)" in capsys.readouterr().out


def test_missing_manifest_is_environment_error(tmp_path: Path, monkeypatch) -> None:
    """--manifest with a nonexistent file exits 2 with an error message."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    monkeypatch.setattr(gate, "REPO", repo)

    assert gate.main(["--strict", "--manifest", str(repo / "nonexistent.json")]) == 2
