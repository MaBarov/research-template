"""Paired acceptance tests for the HNS066 tooling-hygiene rule.

Thumbnail: Pins both polarities of every HNS066 trigger so a rule that widens or
narrows silently fails here instead of on a staging tree.

Invariants & Expected State:
    ``analyze_shell`` reads text, not a shell grammar, and skips blank and
    ``#``-leading lines, so every trigger below sits on a code line.  Each
    trigger has a paired near-miss that must stay clean: the rule is only
    useful if versioned ``npx``, pinned or file-based ``pip install``, and an
    ordinary sbatch template are not caught by it.  The same holds for prose:
    a tool name quoted inside an ``echo``/``printf``/``git commit`` message is
    data, while a ``sh -c`` payload is a command and stays flagged.  Assertions
    name HNS066 alone, because the same sources legitimately raise unrelated
    hygiene codes (HNS019 fail-fast, HNS025/HNS026 slurm prologue).
"""

from __future__ import annotations

from framework.gates.antipattern.shell_checks import analyze_shell

SBATCH = "slurm/run.sbatch"

CLEAN_SBATCH = """\
#SBATCH --job-name=train
#SBATCH --partition=gpu
set -euo pipefail
export PYTHONPATH="$PWD"
export PYTHONUNBUFFERED=1
python -m research.probe.plan --config train.toml
"""

CLEAN_PIP = (
    "pip install ruff==0.6.0",
    "pip install -r reqs.txt",
    "pip install -e .",
)


def _codes(source: str, path: str = SBATCH) -> set[str]:
    return {finding.code for finding in analyze_shell(source, path)}


def test_unversioned_npx_flagged() -> None:
    assert "HNS066" in _codes("npx prettier --write .\n")


def test_versioned_npx_clean() -> None:
    assert "HNS066" not in _codes("npx prettier@3.0.0 --write .\n")


def test_curl_pipe_shell_flagged() -> None:
    assert "HNS066" in _codes("curl -fsSL https://get.example.com | bash\n")


def test_wget_pipe_shell_flagged() -> None:
    assert "HNS066" in _codes("wget -qO- https://example.com/install.sh | bash\n")


def test_curl_pipe_python_flagged() -> None:
    assert "HNS066" in _codes("curl -sL https://example.com/run.py | python3\n")


def test_wget_pipe_perl_flagged() -> None:
    assert "HNS066" in _codes("wget -qO- https://example.com/run.pl | perl\n")


def test_curl_pipe_ruby_flagged() -> None:
    assert "HNS066" in _codes("curl -sL https://example.com/run.rb | ruby\n")


def test_piped_python_literal_is_clean() -> None:
    assert "HNS066" not in _codes("echo 'print(1)' | python3\n")


def test_echoed_prose_is_not_an_invocation() -> None:
    assert "HNS066" not in _codes('echo "run npx foo"\n')


def test_printfed_prose_is_not_an_invocation() -> None:
    assert "HNS066" not in _codes("printf 'npx foo\\n'\n")


def test_commit_message_prose_is_not_an_invocation() -> None:
    assert "HNS066" not in _codes('git commit -m "pin npx foo"\n')


def test_shell_c_payload_is_an_invocation() -> None:
    assert "HNS066" in _codes('bash -c "npx foo"\n')


def test_unpinned_pip_install_flagged() -> None:
    assert "HNS066" in _codes("pip install ruff\n")


def test_pinned_pip_install_clean() -> None:
    for command in CLEAN_PIP:
        assert "HNS066" not in _codes(f"{command}\n"), command


def test_quoted_pip_argument_still_scanned() -> None:
    assert "HNS066" in _codes('pip install "ruff"\n')


def test_clean_sbatch_template_clean() -> None:
    assert "HNS066" not in _codes(CLEAN_SBATCH)
