"""Checker invocation and diagnostic parsing of the static-type gate.

Thumbnail: mypy/pyright argv construction, subprocess runs and diagnostic parsing.

Invariants & Expected State:
    * ``--follow-imports=silent`` plus the caller's scope set keep every returned
      finding attributable to a file the caller asked for.
    * A line carrying an ``error`` marker but no parsable location is surfaced as an
      unparsed line, so the CLI fails closed instead of reporting a clean run.
    * pyright ranges are zero-based: the parsed line is ``start.line + 1``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework import harness
from framework.gates.typecheck import policy

_DIAGNOSTIC = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+): (?P<kind>error|note): (?P<message>.*)$"
)
_CODE = re.compile(r"\s*\[(?P<code>[a-z0-9-]+)\]\s*$")


class CheckerMissing(RuntimeError):
    """Raised when the configured checker executable cannot be resolved."""

    def __init__(self, engine: str, hint: str) -> None:
        super().__init__(f"{engine} is not installed or not on PATH")
        self.engine = engine
        self.hint = hint


@dataclass(frozen=True)
class Finding:
    """One checker diagnostic with its file, line, error code and message."""

    path: str
    line: int
    code: str
    message: str

    def format(self) -> str:
        """Return the finding as one ``path:line: code message`` line."""
        return f"{self.path}:{self.line}: {self.code} {self.message}"


@dataclass(frozen=True)
class RunResult:
    """Outcome of one checker invocation."""

    findings: list[Finding]
    unparsed: list[str]
    returncode: int
    engine: str
    shadowed: list[str] = field(default_factory=list)


def _parse_mypy(text: str, scoped: set[str]) -> tuple[list[Finding], list[str]]:
    """Return ``(findings, unparsed error lines)`` for one mypy report text."""
    findings: list[Finding] = []
    unparsed: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        match = _DIAGNOSTIC.match(line)
        if match is None:
            if ": error:" in line or line.startswith("mypy: error"):
                unparsed.append(line)
            continue
        if match["kind"] != "error":
            continue
        path = policy.relative(match["path"])
        if scoped and path not in scoped:
            continue
        message = match["message"]
        code = _CODE.search(message)
        findings.append(
            Finding(
                path,
                int(match["line"]),
                code["code"] if code else "mypy",
                _CODE.sub("", message).strip(),
            )
        )
    return findings, unparsed


def mypy_argv(paths: Sequence[str], staged: bool = False) -> list[str]:
    """Return the mypy command line for ``paths`` under the committed config."""
    command = policy.engine_command("mypy")
    if command is None:
        raise CheckerMissing(
            "mypy",
            f"uv pip install --python {harness.python()} mypy",
        )
    shadow: list[str] = []
    if staged:
        shadow, _ = policy.shadow_pairs(paths)
    return [
        *command,
        "--config-file",
        str(policy.CONFIG),
        "--python-executable",
        str(policy.interpreter()),
        "--cache-dir",
        str(policy.ensure_cache_dir()),
        "--no-pretty",
        *shadow,
        *paths,
    ]


def run_mypy(paths: Sequence[str], scoped: set[str], staged: bool = False) -> RunResult:
    """Run mypy on ``paths`` and return the findings they own."""
    argv = mypy_argv(paths, staged=staged)
    shadowed = [
        argv[index + 1] for index, item in enumerate(argv) if item == "--shadow-file"
    ]
    completed = subprocess.run(
        argv,
        cwd=policy.REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    findings, unparsed = _parse_mypy(completed.stdout, scoped)
    return RunResult(findings, unparsed, completed.returncode, "mypy", shadowed)


def _pyright_run(completed: subprocess.CompletedProcess[str]) -> RunResult:
    """Parse one pyright JSON run into a result, failing closed on garbage output."""
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        tail = [line for line in completed.stdout.splitlines() if line.strip()][-3:]
        return RunResult(
            [],
            tail or ["pyright produced no JSON output"],
            completed.returncode,
            "pyright",
        )
    findings = [
        Finding(
            policy.relative(str(diagnostic.get("file", ""))),
            int(diagnostic.get("range", {}).get("start", {}).get("line", 0)) + 1,
            str(diagnostic.get("rule") or "pyright"),
            " ".join(str(diagnostic.get("message", "")).split()),
        )
        for diagnostic in payload.get("generalDiagnostics", [])
        if diagnostic.get("severity") == "error"
    ]
    return RunResult(findings, [], completed.returncode, "pyright")


def run_pyright(paths: Sequence[str]) -> RunResult:
    """Run the pyright census engine on ``paths`` and return its findings."""
    command = policy.engine_command("pyright")
    if command is None:
        raise CheckerMissing(
            "pyright",
            f"uv pip install --python {harness.python()} pyright",
        )
    completed = subprocess.run(
        [*command, "--outputjson", "--pythonpath", str(policy.interpreter()), *paths],
        cwd=policy.REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    return _pyright_run(completed)


def run(
    engine: str,
    paths: Sequence[str],
    scoped: set[str] | None = None,
    staged: bool = False,
) -> RunResult:
    """Dispatch one run to ``engine`` with the caller's scope filter."""
    if engine == "pyright":
        return run_pyright(paths)
    scope = scoped if scoped is not None else {policy.relative(path) for path in paths}
    return run_mypy(paths, scope, staged=staged)
