"""Shell/slurm anti-pattern analysis and its pattern constants.

Thumbnail: Detects shell and Slurm defects, including any dirty-run override, in staged scripts.

Invariants & Expected State:
    ``analyze_shell`` reports one finding per defect and never raises on
    unparseable input: it reads text, not a shell grammar.  Every finding names
    the line it was seen on, so a caller can print a diff.  Rules are additive:
    a defect already reported by an earlier rule is not re-reported on the same
    line, and a clean ``set -euo pipefail`` script reports nothing.  The
    dirty-tree refusal is a gate with no override (HNS035 bans the knob,
    HNS036 bans a conditional refusal), so a script that can be talked into
    running from a dirty tree is a finding, not a configuration.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator

import framework.gates.antipattern.targets

_UNKNOWN_PROVENANCE = re.compile(
    r"git\s+rev-parse\b[^\n]*(?:\|\||;)\s*(?:echo|printf)\s+['\"]?unknown",
    re.IGNORECASE,
)

_PROVENANCE_NAME = (
    r"(?:[A-Za-z_][A-Za-z0-9_]*_)?"
    r"(?:COMMIT|SHA|SHA1|SHA256|SHA512|HASH|REVISION|REV|TREE_STATE|DIRTY[A-Z0-9_]*|"
    r"PROVENANCE|IDENTITY)"
    r"(?:_[A-Za-z0-9]+)*"
)

_PROVENANCE_ASSIGNMENT = re.compile(
    rf"(?<![A-Za-z0-9_]){_PROVENANCE_NAME}\s*=\s*['\"]?"
    r"(?:unknown|unavailable|n/?a)['\"]?",
    re.IGNORECASE,
)

_STATUS_FALLBACK = re.compile(r"git\s+status\b[^\n]*\|\|\s*true", re.IGNORECASE)

# A dirty-run override -- any variable that would let a job start from a tree
# whose contents no receipt can reproduce. The ban is absolute (user ruling
# 2026-09-26): the refusal is a gate, not a default. The check reads whole
# identifiers so that a *stated negation* (``DISALLOW_DIRTY``, ``NO_ALLOW_DIRTY``)
# is not mistaken for the knob itself.
_OVERRIDE_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_OVERRIDE_VERB = re.compile(
    r"(?:ALLOW|SKIP|PERMIT|IGNORE|FORCE|BYPASS)_?DIRTY|DIRTY_(?:RUN|OK|ALLOWED)",
    re.IGNORECASE,
)
_OVERRIDE_NEGATIONS = ("DIS", "NO", "NOT", "NEVER")


def _dirty_override(line: str) -> str | None:
    """Return the override identifier on ``line``, ignoring a stated negation."""
    for token in _OVERRIDE_TOKEN.findall(line):
        match = _OVERRIDE_VERB.search(token)
        if not match:
            continue
        if token[: match.start()].rstrip("_").upper().endswith(_OVERRIDE_NEGATIONS):
            continue
        return token
    return None


# The dirty branch and the refusal it must lead with, as written by the guard.
_DIRTY_BRANCH = re.compile(r"if\s+\[\[\s+-n\s+\"?\$?\{?DIRTY_STATUS\}?\"?\s*\]\]")
_DIRTY_REFUSAL = "REFUSING RUN: dirty tree"

_SWALLOWED_FAILURE = re.compile(r"\|\|\s*(?:true|:)(?=\s|$)")

_CLEANUP_COMMANDS = {
    "rm",
    "kill",
    "pkill",
    "wait",
    "chmod",
    "chown",
    "sync",
    "true",
    ":",
}

_PYTHON_INTERPRETER = re.compile(r"python[0-9.]*")

_QUOTED_LITERAL = re.compile(r"'[^']*'|\"[^\"$]*\"")

_FAIL_FAST_FLAGS = {"e": "errexit (-e)", "u": "nounset (-u)"}


def _shell_code_lines(source: str) -> Iterator[tuple[int, str]]:
    for line_number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            yield line_number, line


def _fail_fast_gaps(source: str) -> list[str]:
    """Return missing capabilities of a ``set -euo pipefail`` prologue."""

    flags: set[str] = set()
    pipefail = False
    for _line_number, line in _shell_code_lines(source):
        match = re.match(r"\s*set\s+([-+][A-Za-z]+)", line)
        if match and match.group(1).startswith("-"):
            flags.update(match.group(1)[1:])
        if re.search(r"\bset\b[^\n]*\bpipefail\b", line):
            pipefail = True
    missing = [label for flag, label in _FAIL_FAST_FLAGS.items() if flag not in flags]
    if not pipefail:
        missing.append("pipefail")
    return missing


def _python_script_invocations(line: str) -> list[tuple[str, bool]]:
    """Return ``(script, unbuffered)`` for direct Python script invocations."""

    code = _QUOTED_LITERAL.sub("", line.split("#", 1)[0])
    invocations: list[tuple[str, bool]] = []
    for command in re.split(r"&&|\|\||[;|]", code):
        tokens = command.split()
        if not tokens or any(token in {"-m", "-c"} for token in tokens):
            continue
        unbuffered = tokens[0] == "stdbuf" or "-u" in tokens
        interpreter = None
        for index, token in enumerate(tokens):
            bare = token.strip("\"'")
            if bare.endswith(".py"):
                if interpreter is not None:
                    invocations.append((bare, unbuffered))
                break
            if "python" in bare.lower() and not bare.startswith("-"):
                interpreter = bare
    return invocations


def _swallowed_command(line: str, match: re.Match[str]) -> str | None:
    segments = re.split(r"[;&|]+", line[: match.start()])
    last = segments[-1].strip() if segments else ""
    if not last:
        return None
    return last.split()[0].lstrip("(\"'$")


def _report_fail_fast(
    source: str,
    code_lines: list[tuple[int, str]],
    report: Callable[[int, str, str], None],
) -> None:
    missing = _fail_fast_gaps(source)
    if missing:
        report(
            code_lines[0][0],
            "HNS019",
            f"shell is not fail-fast (missing {', '.join(missing)}); add `set -euo pipefail`",
        )


def _report_dirty_override(
    code_lines: list[tuple[int, str]],
    report: Callable[[int, str, str], None],
) -> None:
    """Refuse any dirty-run override: the refusal is unchangeable."""
    for line_number, line in code_lines:
        token = _dirty_override(line)
        if token:
            report(
                line_number,
                "HNS035",
                f"dirty-run override {token!r} is banned; a run must "
                "refuse a dirty tree instead of labelling it",
            )


def _refusal_is_unconditional(code_lines: list[tuple[int, str]], index: int) -> bool:
    """Return whether the refusal at ``index`` leads its dirty branch."""
    if index == 0 or not _DIRTY_BRANCH.search(code_lines[index - 1][1]):
        return False
    following = [line for _number, line in code_lines[index + 1 : index + 3]]
    return any("exit 90" in line for line in following)


def _report_dirty_refusal(
    code_lines: list[tuple[int, str]],
    report: Callable[[int, str, str], None],
) -> None:
    """The dirty-tree refusal must lead its branch, with no condition in front."""
    for index, (line_number, line) in enumerate(code_lines):
        if _DIRTY_REFUSAL in line and not _refusal_is_unconditional(code_lines, index):
            report(
                line_number,
                "HNS036",
                "the dirty-tree refusal is conditional; make it the dirty branch's "
                "first statement, followed by `exit 90`",
            )


def _report_buffered_python(
    source: str,
    code_lines: list[tuple[int, str]],
    report: Callable[[int, str, str], None],
) -> None:
    if "PYTHONUNBUFFERED" not in source:
        for line_number, line in code_lines:
            for script, unbuffered in _python_script_invocations(line):
                if not unbuffered:
                    report(
                        line_number,
                        "HNS020",
                        f"python script {script} runs buffered; pass `-u` or export PYTHONUNBUFFERED=1",
                    )


def _provenance_line_findings(line: str) -> list[tuple[str, str]]:
    """Return the provenance findings of one shell line, in report order."""

    found: list[tuple[str, str]] = []
    if _UNKNOWN_PROVENANCE.search(line):
        found.append(
            (
                "HNS008",
                "Git provenance must fail closed; do not substitute commit=unknown",
            )
        )
    if _PROVENANCE_ASSIGNMENT.search(line):
        found.append(
            (
                "HNS008",
                "Git provenance must fail closed; do not record unknown/unavailable values",
            )
        )
    if _STATUS_FALLBACK.search(line):
        found.append(
            (
                "HNS009",
                "Git status failure must stop the run; do not ignore it with || true",
            )
        )
    return found


def _swallowed_line_findings(line: str) -> list[tuple[str, str]]:
    """Return the swallowed-failure finding of one shell line, when present."""

    match = _SWALLOWED_FAILURE.search(line)
    if match and _swallowed_command(line, match) not in _CLEANUP_COMMANDS:
        return [
            (
                "HNS009",
                "a command failure is swallowed here; handle it or drop `|| true`",
            )
        ]
    return []


def _shell_line_findings(line: str) -> list[tuple[str, str]]:
    """Return the ``(code, message)`` findings of one shell line, in order."""

    return [*_provenance_line_findings(line), *_swallowed_line_findings(line)]


def _report_line_hygiene(
    code_lines: list[tuple[int, str]],
    report: Callable[[int, str, str], None],
) -> None:
    for line_number, line in code_lines:
        for code, message in _shell_line_findings(line):
            report(line_number, code, message)


def _report_slurm_hygiene(
    source: str,
    path: str,
    code_lines: list[tuple[int, str]],
    report: Callable[[int, str, str], None],
) -> None:
    if not (path.endswith(".sbatch") and "#SBATCH" in source):
        return
    first_line = code_lines[0][0]

    if "PYTHONPATH" not in source:
        report(
            first_line,
            "HNS025",
            "SLURM script does not export PYTHONPATH; the job would not import its checkout",
        )
    if "PYTHONUNBUFFERED" not in source:
        report(
            first_line,
            "HNS026",
            "SLURM script does not export PYTHONUNBUFFERED=1; add export PYTHONUNBUFFERED=1",
        )


def analyze_shell(
    source: str, path: str
) -> list[framework.gates.antipattern.targets.Finding]:
    """Return findings for shell/slurm provenance and hygiene problems."""

    findings: list[framework.gates.antipattern.targets.Finding] = []
    seen: set[tuple[int, str]] = set()

    def report(line_number: int, code: str, message: str) -> None:
        if (line_number, code) in seen:
            return
        seen.add((line_number, code))
        findings.append(
            framework.gates.antipattern.targets.Finding(
                path, line_number, code, message
            )
        )

    code_lines = list(_shell_code_lines(source))
    if not code_lines:
        return findings

    _report_fail_fast(source, code_lines, report)
    _report_buffered_python(source, code_lines, report)
    _report_dirty_override(code_lines, report)
    _report_dirty_refusal(code_lines, report)
    _report_slurm_hygiene(source, path, code_lines, report)
    _report_line_hygiene(code_lines, report)
    return findings
