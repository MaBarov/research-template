"""Blocking parameter-duplication gate: one env var, one default, one name.

Invariants & Expected State:
    - Exit codes: 0 clean, 1 findings under ``--strict``, 2 usage or registry failure.
    - No bypass surface: the gate reads no environment variable, offers no baseline and
      no update flag; ``--staged`` reads each file from the Git index and an unreadable
      file is a finding, never silence.
    - Scope: tracked ``.py``/``.sh``/``.sbatch`` files, minus the registry/gate fixtures
      and minus ``cache/``, ``mutants/`` and ``third_party/``.
    - The usage sweep is tree-wide and runs on every invocation: a registered row with
      no production reader (HNS042) and a declared implementation that does not compare
      its default (HNS043) block like drift does.

Usage::

  python framework/gates/params/check_param_duplicates.py \\
      [--strict] [--staged] [--report PATH] [files...]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

_ENTRY_REPO = Path(__file__).resolve().parents[3]
if str(_ENTRY_REPO) not in sys.path:
    sys.path.insert(0, str(_ENTRY_REPO))

from framework.gates.antipattern.targets import Finding, _read_staged
from framework.gates.params import param_checks, param_matchers, param_usage

_ENTRY_REPO = Path(__file__).resolve().parents[3]
if str(_ENTRY_REPO) not in sys.path:
    sys.path.insert(0, str(_ENTRY_REPO))

TOOL = "check_param_duplicates"


def _relative(path: str) -> str:
    """Return ``path`` relative to the repository root when it lives inside it."""

    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(param_checks.REPO).as_posix()
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


def _in_scope(rel: str) -> bool:
    """Return whether one repository-relative path is checked by this gate."""

    if rel in param_checks.EXEMPT_PATHS:
        return False
    return not (set(Path(rel).parts) & param_checks.SKIP_PARTS)


def _tracked_files() -> list[str]:
    """Return every tracked file with a checked suffix."""

    result = subprocess.run(
        ["git", "ls-files"], cwd=param_checks.REPO, capture_output=True, check=False
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return [
        line
        for line in result.stdout.decode("utf-8").splitlines()
        if Path(line).suffix in param_checks.CHECKED_SUFFIXES
    ]


def files_to_check(paths: Sequence[str]) -> list[str]:
    """Return the in-scope files of this invocation, in stable order."""

    candidates = [_relative(path) for path in paths] if paths else _tracked_files()
    return sorted({rel for rel in candidates if _in_scope(rel)})


def _load(path: str, staged: bool) -> tuple[str, list[Finding]]:
    """Return ``(source, findings)``; an unreadable file becomes a HNS041 finding."""

    try:
        source = (
            _read_staged(path)
            if staged
            else (param_checks.REPO / path).read_text("utf-8")
        )
    except (OSError, RuntimeError, UnicodeError) as error:
        return "", [
            Finding(path, 1, "HNS041", f"registry: cannot inspect source: {error}")
        ]
    return source, []


def check_paths(paths: Sequence[str], staged: bool = False) -> list[Finding]:
    """Return every finding of the given paths, registry and usage sweeps included."""

    findings = list(param_checks.registry_findings())
    findings.extend(param_usage.usage_findings())
    for rel in files_to_check(paths):
        source, problems = _load(rel, staged)
        findings.extend(problems)
        if source:
            findings.extend(param_matchers.source_findings(source, rel))
    return findings


def _write_report(path: str, findings: Sequence[Finding]) -> None:
    """Write every finding plus a per-parameter tally to ``path``."""

    tally = Counter(finding.message.split(":", 1)[0] for finding in findings)
    lines = [finding.format() for finding in findings]
    lines.extend(["", "# per-parameter tally"])
    lines.extend(
        f"{count:4d}  {name}"
        for name, count in sorted(tally.items(), key=lambda item: (-item[1], item[0]))
    )
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files", nargs="*", help="files to check (default: tracked files)"
    )
    parser.add_argument("--strict", action="store_true", help="exit 1 on findings")
    parser.add_argument(
        "--staged", action="store_true", help="read files from the index"
    )
    parser.add_argument("--report", help="write findings and the tally here")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate and return its process exit code."""

    args = _parse_args(argv)
    try:
        selected = files_to_check(args.files)
        findings = check_paths(args.files, staged=args.staged)
    except RuntimeError as error:
        print(f"[{TOOL}] ERROR: {error}", file=sys.stderr)
        return 2
    if args.report:
        _write_report(args.report, findings)
    for finding in findings:
        print(f"[{TOOL}] {finding.format()}", file=sys.stderr)
    print(f"[{TOOL}] checked {len(selected)} file(s), {len(findings)} finding(s)")
    if findings and args.strict:
        print(f"[{TOOL}] STRICT FAIL: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
