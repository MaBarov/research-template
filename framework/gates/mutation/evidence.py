"""Mutation evidence: content-addressed mutmut verdicts for staged modules.

Invariants & Expected State:
 * Evidence is keyed by repository-relative module path and stamped with the
   sha256 of the staged blob it was scored from, so any content change
   invalidates its own evidence and no baseline, allowlist or skip flag can
   outlive the code it describes.
 * The commit path is read-only: deciding costs one JSON read plus one
   ``git show`` per staged file and never forks a test run.
 * The mutated population comes from ``[tool.mutmut]`` in ``pyproject.toml``;
   an unreadable config and a ledger recorded against a different population
   are findings, never a silent pass.
 * Evidence is also stamped with the digest of the test surface it was scored
   against (every module under ``harness.TEST_ROOT``, the repository-root
   ``conftest.py`` when present, and the mutmut and pytest configuration that
   bounds the run), because mutmut reuses cached verdicts across test edits: an
   entry whose digest moved is refused, never believed. The scored surface must
   also be the committed one: a refresh refuses while any file of that surface
   differs from the index or is untracked, so verdicts never describe tests the
   commit would not carry.
 * A ``# pragma: no mutate`` line is not mutated at all by mutmut, so the
   ledger records nothing about the suppression; ``pragma_notes`` NOTEs the
   lines a staged blob newly adds over HEAD, keeping the equivalence claim
   visible at commit time (NOTEs never change the verdict).
 * No function here reads an environment variable: the gate has no downgrade.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import subprocess
import tokenize
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import framework.harness

REPO = Path(__file__).resolve().parents[3]
LEDGER_PATH = REPO / "framework" / "mutation_evidence.json"
PYPROJECT = REPO / "pyproject.toml"
LEDGER_NAME = "framework/mutation_evidence.json"

SCHEMA = "research.mutation-evidence.v2"
FINDING_PREFIX = "[check_mutation]"

#: The digest surface is the whole test tree, not just
#: ``pytest_add_cli_args_test_selection``: the selected tests import helpers from
#: elsewhere under the test root, and any of those bytes can flip a verdict. The
#: two sections below are folded in because they bound how the run executes.
TEST_SURFACE_DIR = framework.harness.TEST_ROOT
TEST_SELECTION_KEY = "pytest_add_cli_args_test_selection"
MUTMUT_SECTION = "tool.mutmut"
PYTEST_SECTION = "tool.pytest.ini_options"

#: Statuses that forbid a cleared verdict. ``killed`` and mutmut's own
#: ``skipped`` (its exit-code-34 status) are the only statuses evidence may
#: show; a ``# pragma: no mutate`` line is stronger than either — mutmut
#: generates no mutant on it, so nothing about the suppression reaches the
#: ledger (``pragma_notes`` NOTEs the lines a staged blob newly suppresses).
BLOCKING_STATUSES = (
    "survived",
    "no_tests",
    "timeout",
    "suspicious",
    "segfault",
    "caught_by_type_check",
    "check_was_interrupted_by_user",
    "not_checked",
)

#: Keys of ``[tool.mutmut]`` that define the population; both are recorded in
#: the ledger, so editing either one makes the recorded evidence stale.
POPULATION_KEYS = ("only_mutate", "do_not_mutate")

#: The unreached-mutant statuses whose remedy must be spelled out on failure.
UNKILLED_STATUSES = ("survived", "no_tests", "not_checked")

REFRESH_HINT = (
    "python framework/gates/mutation/check_mutation.py --mode staged --staged"
)


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    """Run git in the repository root; ``check=False`` leaves verdicts to callers."""
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, check=False)


def staged_bytes(rel: str) -> bytes | None:
    """The exact bytes the index would commit for ``rel`` (None when unstaged)."""
    if not rel.endswith(".py"):
        return None
    proc = _git("show", f":{rel}")
    return proc.stdout if proc.returncode == 0 else None


def staged_sha256(rel: str) -> str | None:
    """sha256 of the staged blob, the address ``rel``'s evidence is keyed by."""
    data = staged_bytes(rel)
    return None if data is None else hashlib.sha256(data).hexdigest()


def head_bytes(rel: str) -> bytes | None:
    """The bytes HEAD carries for ``rel`` (None when HEAD has no such blob)."""

    proc = _git("show", f"HEAD:{rel}")
    return proc.stdout if proc.returncode == 0 else None


def pragma_lines(text: str) -> dict[str, int]:
    """Map the code text of each ``# pragma: no mutate`` comment to its line."""

    found: dict[str, int] = {}
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError):
        return found
    lines = text.splitlines()
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        if "# pragma:" not in token.string or "no mutate" not in token.string:
            continue
        code = lines[token.start[0] - 1][: token.start[1]].strip()
        found.setdefault(code or lines[token.start[0] - 1].strip(), token.start[0])
    return found


def pragma_notes(paths: Sequence[str]) -> list[str]:
    """NOTE the ``# pragma: no mutate`` lines a staged blob adds over HEAD."""

    notes: list[str] = []
    for rel in sorted(set(paths)):
        staged = staged_bytes(rel)
        if staged is None:
            continue
        head = head_bytes(rel)
        known = pragma_lines(head.decode("utf-8", "replace")) if head else {}
        added = sorted(
            number
            for code, number in pragma_lines(staged.decode("utf-8", "replace")).items()
            if code not in known
        )
        if not added:
            continue
        listed = ", ".join(str(number) for number in added)
        notes.append(
            f"{FINDING_PREFIX} {rel}: NOTE new `# pragma: no mutate` line(s) "
            f"{listed} — mutmut generates no mutant there, so the ledger records "
            "nothing; the equivalence claim lives on the line, state the reason there"
        )
    return notes


def tests_drift_reason() -> str | None:
    """Why the test surface is not committed as staged, or None when it is."""

    proc = _git(
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        TEST_SURFACE_DIR,
        "conftest.py",
        "pyproject.toml",
    )
    if proc.returncode != 0:
        return f"{FINDING_PREFIX} git status failed for the test surface"
    lines = [
        line for line in proc.stdout.decode("utf-8", "replace").splitlines() if line
    ]
    drift = [line for line in lines if line.startswith("??") or line[1] != " "]
    if not drift:
        return None
    return (
        f"{FINDING_PREFIX} the test surface differs from the index "
        f"({len(drift)} path(s), first: {drift[0].strip()}) — scored verdicts must "
        "describe the committed tests; stage the test edits (git add) and refresh"
    )


def load_ledger(path: Path | None = None) -> dict[str, Any]:
    """Read the evidence ledger; a missing or malformed file reads as empty."""
    ledger_path = LEDGER_PATH if path is None else path
    if not ledger_path.is_file():
        return {}
    try:
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_ledger(data: Mapping[str, Any], path: Path | None = None) -> None:
    """Write the ledger deterministically, so its diff stays reviewable."""
    ledger_path = LEDGER_PATH if path is None else path
    ledger_path.write_text(
        json.dumps(dict(data), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _section_text(text: str, section: str) -> str:
    """The body of one ``[section]`` block, up to the next table header."""
    header = re.compile(rf"^\[{re.escape(section)}\][ \t]*$", re.MULTILINE)
    match = header.search(text)
    if match is None:
        return ""
    rest = text[match.end() :]
    following = re.search(r"^\[", rest, re.MULTILINE)
    return rest if following is None else rest[: following.start()]


def _literal_list(section_text: str, key: str) -> list[str] | None:
    """Parse ``key = ["..."]`` with AST literals; None when absent or unparsable."""
    match = re.search(
        rf"^[ \t]*{re.escape(key)}[ \t]*=[ \t]*(?P<value>\[[^\]]*\])",
        section_text,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        return None
    try:
        value = ast.literal_eval(match.group("value"))
    except (SyntaxError, ValueError):
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return value


def config_population() -> tuple[dict[str, list[str]] | None, str | None]:
    """The mutated-file population from ``[tool.mutmut]``, or why it is unreadable."""
    try:
        text = PYPROJECT.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{FINDING_PREFIX} cannot read {PYPROJECT.name}: {exc}"
    section = _section_text(text, MUTMUT_SECTION)
    if not section.strip():
        return None, f"{FINDING_PREFIX} pyproject.toml carries no [tool.mutmut] table"
    population: dict[str, list[str]] = {}
    for key in POPULATION_KEYS:
        values = _literal_list(section, key)
        if values is None and key == "only_mutate":
            return None, f"{FINDING_PREFIX} [tool.mutmut] {key} is absent or unparsable"
        population[key] = values or []
    return population, None


def test_selection() -> list[str] | None:
    """The configured ``pytest_add_cli_args_test_selection`` list, or None."""

    try:
        text = PYPROJECT.read_text(encoding="utf-8")
    except OSError:
        return None
    return _literal_list(_section_text(text, MUTMUT_SECTION), TEST_SELECTION_KEY)


def _fold_file(digest: Any, path: Path) -> None:
    """Fold one file's repository path and bytes into ``digest``."""

    digest.update(path.relative_to(REPO).as_posix().encode("utf-8"))
    digest.update(b"\0")
    digest.update(hashlib.sha256(path.read_bytes()).digest())


def _fold_section(digest: Any, section: str) -> None:
    """Fold one pyproject section's text into ``digest``: the run's own bounds."""

    try:
        text = PYPROJECT.read_text(encoding="utf-8")
    except OSError:
        text = ""
    digest.update(section.encode("utf-8"))
    digest.update(b"\0")
    digest.update(_section_text(text, section).encode("utf-8"))


def tests_sha256() -> str:
    """Digest of the test surface plus the configuration that bounds the run."""

    digest = hashlib.sha256()
    surface = REPO / TEST_SURFACE_DIR
    if surface.is_dir():
        for path in sorted(surface.rglob("*.py")):
            if path.is_file():
                _fold_file(digest, path)
    conftest = REPO / "conftest.py"
    if conftest.is_file():
        _fold_file(digest, conftest)
    for section in (MUTMUT_SECTION, PYTEST_SECTION):
        _fold_section(digest, section)
    return digest.hexdigest()


def _glob_regex(pattern: str) -> str:
    """Translate a mutated-file glob: ``*`` stays inside a segment, ``**/`` spans."""
    parts: list[str] = ["^"]
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
            continue
        char = pattern[index]
        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(char))
        index += 1
    parts.append("$")
    return "".join(parts)


def match_population(rel: str, population: Mapping[str, list[str]]) -> bool:
    """True when ``rel`` is mutated: it matches only_mutate, not do_not_mutate."""

    def matches(patterns: Sequence[str]) -> bool:
        return any(re.match(_glob_regex(pattern), rel) for pattern in patterns)

    if not matches(population.get("only_mutate", [])):
        return False
    return not matches(population.get("do_not_mutate", []))


def _status_findings(rel: str, entry: Mapping[str, Any]) -> list[str]:
    """One finding per blocking status that carries a non-zero count."""
    findings: list[str] = []
    for status in BLOCKING_STATUSES:
        count = entry.get(status)
        if not isinstance(count, int) or count <= 0:
            continue
        names = entry.get(f"{status}_names") or []
        findings.append(
            f"{FINDING_PREFIX} {rel}: {count} {status.replace('_', ' ')} — "
            f"{', '.join(names[:6])}"
        )
    return findings


def _remedy_findings(rel: str, entry: Mapping[str, Any]) -> list[str]:
    """The explicit remedy when mutants were not killed or not reached at all."""
    if not any(entry.get(status) for status in UNKILLED_STATUSES):
        return []
    return [
        (
            f"{FINDING_PREFIX} {rel}: kill each mutant with a real assertion, or mark the "
            "mutated line `# pragma: no mutate` in this same commit; there is no allowlist, "
            "no environment variable and no skip flag"
        )
    ]


def _stamp_findings(
    rel: str, entry: Mapping[str, Any], sha: str, tests_sha: str
) -> list[str]:
    """Findings for an entry whose content or test-surface stamp has moved."""

    findings: list[str] = []
    if entry.get("content_sha256") != sha:
        findings.append(
            f"{FINDING_PREFIX} {rel}: evidence is stamped for content "
            f"{entry.get('content_sha256')}, not the staged {sha} — refresh it"
        )
    if entry.get("tests_sha256") != tests_sha:
        findings.append(
            f"{FINDING_PREFIX} {rel}: evidence was scored against test surface "
            f"{entry.get('tests_sha256') or 'no digest'}, the tree now digests to "
            f"{tests_sha} — mutmut reuses cached verdicts across test edits; refresh it"
        )
    return findings


def entry_findings(rel: str, entry: Any, sha: str, tests_sha: str) -> list[str]:
    """Every reason ``rel``'s recorded evidence does not clear content ``sha``."""

    if not isinstance(entry, Mapping):
        return [
            (
                f"{FINDING_PREFIX} {rel}: no cleared mutation evidence — refresh with "
                f"`{REFRESH_HINT} {rel}`"
            )
        ]
    findings = _stamp_findings(rel, entry, sha, tests_sha)
    if not entry.get("mutmut_version"):
        findings.append(f"{FINDING_PREFIX} {rel}: evidence records no mutmut version")
    if not isinstance(entry.get("mutants"), int):
        findings.append(f"{FINDING_PREFIX} {rel}: evidence records no mutant count")
    findings.extend(_status_findings(rel, entry))
    findings.extend(_remedy_findings(rel, entry))
    return findings


def _population_findings(ledger: Mapping[str, Any]) -> list[str]:
    """Fail closed when the ledger is absent or describes another population."""
    if not ledger:
        return [
            (
                f"{FINDING_PREFIX} {LEDGER_NAME} is missing or unreadable — refresh with "
                f"`{REFRESH_HINT} <files>`"
            )
        ]
    population, error = config_population()
    if population is None:
        return [error or f"{FINDING_PREFIX} unreadable mutation population"]
    if ledger.get("population") != population:
        return [
            (
                f"{FINDING_PREFIX} ledger records the population "
                f"{ledger.get('population')!r}, configured is {population!r} — refresh the "
                "evidence for the staged modules"
            )
        ]
    return []


def staged_findings(paths: Sequence[str], ledger_path: Path | None = None) -> list[str]:
    """Every reason the staged files lack cleared evidence for their content."""
    population, error = config_population()
    if population is None:
        return [error or f"{FINDING_PREFIX} unreadable mutation population"]
    scoped = [rel for rel in sorted(set(paths)) if match_population(rel, population)]
    ledger = load_ledger(ledger_path)
    if not scoped and (not ledger or ledger.get("population") == population):
        return []
    return _population_findings(ledger) + _module_findings(
        scoped, ledger.get("modules") or {}, population, tests_sha256()
    )


def _module_findings(
    paths: Sequence[str],
    modules: Mapping[str, Any],
    population: Mapping[str, list[str]],
    tests_sha: str,
) -> list[str]:
    """Cleared-evidence findings for the staged paths inside the population."""

    findings: list[str] = []
    for rel in sorted(set(paths)):
        if not rel.endswith(".py") or not match_population(rel, population):
            continue
        sha = staged_sha256(rel)
        if sha is None:
            findings.append(
                f"{FINDING_PREFIX} {rel}: not readable from the index (stage it first)"
            )
            continue
        findings.extend(entry_findings(rel, modules.get(rel), sha, tests_sha))
    return findings


def scoped_paths(paths: Sequence[str]) -> tuple[list[str], str | None]:
    """The staged paths the gate owns, or the reason the population is unreadable."""
    population, error = config_population()
    if population is None:
        return [], error
    scoped = [rel for rel in sorted(set(paths)) if match_population(rel, population)]
    return scoped, None
