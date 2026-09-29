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
 * No function here reads an environment variable: the gate has no downgrade.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
LEDGER_PATH = REPO / "framework" / "mutation_evidence.json"
PYPROJECT = REPO / "pyproject.toml"
LEDGER_NAME = "framework/mutation_evidence.json"

SCHEMA = "research.mutation-evidence.v1"
FINDING_PREFIX = "[check_mutation]"

#: Statuses that forbid a cleared verdict. ``killed`` and ``skipped`` (a line
#: carrying ``# pragma: no mutate``) are the only statuses evidence may show.
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
    section = _section_text(text, "tool.mutmut")
    if not section.strip():
        return None, f"{FINDING_PREFIX} pyproject.toml carries no [tool.mutmut] table"
    population: dict[str, list[str]] = {}
    for key in POPULATION_KEYS:
        values = _literal_list(section, key)
        if values is None and key == "only_mutate":
            return None, f"{FINDING_PREFIX} [tool.mutmut] {key} is absent or unparsable"
        population[key] = values or []
    return population, None


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


def entry_findings(rel: str, entry: Any, sha: str) -> list[str]:
    """Every reason ``rel``'s recorded evidence does not clear content ``sha``."""
    if not isinstance(entry, Mapping):
        return [
            (
                f"{FINDING_PREFIX} {rel}: no cleared mutation evidence — refresh with "
                f"`{REFRESH_HINT} {rel}`"
            )
        ]
    findings: list[str] = []
    if entry.get("content_sha256") != sha:
        findings.append(
            f"{FINDING_PREFIX} {rel}: evidence is stamped for content "
            f"{entry.get('content_sha256')}, not the staged {sha} — refresh it"
        )
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
        scoped, ledger.get("modules") or {}, population
    )


def _module_findings(
    paths: Sequence[str],
    modules: Mapping[str, Any],
    population: Mapping[str, list[str]],
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
        findings.extend(entry_findings(rel, modules.get(rel), sha))
    return findings


def scoped_paths(paths: Sequence[str]) -> tuple[list[str], str | None]:
    """The staged paths the gate owns, or the reason the population is unreadable."""
    population, error = config_population()
    if population is None:
        return [], error
    scoped = [rel for rel in sorted(set(paths)) if match_population(rel, population)]
    return scoped, None
