#!/usr/bin/env python3
"""Fail-closed copy-paste detection gate for staged or whole-tree code.

Scans source files using jscpd to detect duplicate code blocks across
the codebase. Supports staged-mode verification and baseline tracking.

Invariants & Expected State:
    - Binary Resolution: jscpd is located via custom path, PATH, or
      user-local bin directory; failure in strict mode reports CPD000.
    - Baseline Invariance: Existing clones registered in baseline JSON
      are ignored; only newly introduced clones are reported as CPD001.
    - Verdict-Path Unity: Every finding names the offending file and
      exact lines where duplication begins and ends.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEFAULT_BASELINE = REPO / "framework" / "jscpd-baseline.json"
DEFAULT_CONFIG = REPO / ".jscpd.json"
DEFAULT_ROOTS = ("research", "framework", "scripts", "slurm", "tests")
CLONE_HEADER_RE = re.compile(
    r"Clone found \((?P<format>[^)]+)\)(?:\s+\[(?P<tag>[^\]]+)\])?"
)
CLONE_LOC_RE = re.compile(
    r"^\s*-\s*(?P<f1>[^\s]+)\s+\[(?P<s1>\d+):(?P<c1>\d+)\s*-\s*(?P<e1>\d+):(?P<c2>\d+)\]"
    r"(?:\s+\((?P<lines>\d+)\s+lines,\s+(?P<tokens>\d+)\s+tokens\))?"
)
CLONE_PEER_RE = re.compile(
    r"^\s+(?P<f2>[^\s]+)\s+\[(?P<s2>\d+):(?P<c1>\d+)\s*-\s*(?P<e2>\d+):(?P<c2>\d+)\]"
)


@dataclass(frozen=True)
class Finding:
    """One duplicate code finding reported by the gate."""

    code: str
    path: str
    line: int
    message: str

    def format(self) -> str:
        """Format finding for terminal or log output."""
        return f"{self.path}:{self.line}: {self.code} {self.message}"


def resolve_jscpd_bin(custom_path: str | None = None) -> str | None:
    """Resolve the path to the jscpd executable."""
    if custom_path is not None:
        if os.path.isfile(custom_path) and os.access(custom_path, os.X_OK):
            return custom_path
        return None
    resolved = shutil.which("jscpd")
    if resolved:
        return resolved
    user_local = Path.home() / ".local" / "bin" / "jscpd"
    if user_local.is_file() and os.access(user_local, os.X_OK):
        return str(user_local)
    return None


def collect_staged_files(repo_root: Path) -> list[str]:
    """Retrieve list of staged files suitable for duplication check."""
    cmd = [
        "git",
        "-C",
        str(repo_root),
        "diff",
        "--cached",
        "--name-only",
        "--diff-filter=ACM",
    ]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    if res.returncode != 0:
        return []
    valid_exts = {".py", ".sh", ".sbatch", ".js", ".ts"}
    return [
        line.strip()
        for line in res.stdout.splitlines()
        if line.strip() and Path(line.strip()).suffix in valid_exts
    ]


def build_jscpd_args(
    jscpd_bin: str,
    target_paths: Sequence[str],
    config_path: Path | None,
    baseline_path: Path | None,
    update_baseline: bool,
    output_dir: Path | None,
) -> list[str]:
    """Assemble argument list for the jscpd subprocess invocation."""
    args = [jscpd_bin]
    if config_path and config_path.is_file():
        args.extend(["--config", str(config_path)])
    if baseline_path:
        args.extend(["--baseline", str(baseline_path)])
        if update_baseline:
            args.append("--update-baseline")
        else:
            args.append("--fail-on-new-clones=0")
    if output_dir:
        args.extend(["--reporters", "console,json", "--output", str(output_dir)])
    args.extend(target_paths)
    return args


def parse_jscpd_json(report_file: Path, baseline_active: bool = False) -> list[Finding]:
    """Parse findings from jscpd JSON report output."""
    if not report_file.is_file():
        return []
    try:
        data = json.loads(report_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    findings: list[Finding] = []
    for dup in data.get("duplicates", []):
        if baseline_active and not dup.get("isNew"):
            continue
        f1 = dup.get("firstFile", {})
        f2 = dup.get("secondFile", {})
        p1, s1, e1 = f1.get("name", "unknown"), f1.get("start", 1), f1.get("end", 1)
        p2, s2, e2 = f2.get("name", "unknown"), f2.get("start", 1), f2.get("end", 1)
        lines = dup.get("lines", e1 - s1 + 1)
        tokens = dup.get("tokens", 0)
        msg = f"Clone with {p2}:{s2}-{e2} ({lines} lines, {tokens} tokens)"
        findings.append(Finding(code="CPD001", path=p1, line=s1, message=msg))
    return findings


def parse_stdout_clones(stdout: str, baseline_active: bool = False) -> list[Finding]:
    """Parse clone occurrences directly from jscpd stdout lines."""
    findings: list[Finding] = []
    lines = stdout.splitlines()
    idx = 0
    current_is_new = False
    while idx < len(lines):
        line = lines[idx]
        if "Clone found" in line:
            current_is_new = "[NEW]" in line
        m1 = CLONE_LOC_RE.match(line)
        if m1 and idx + 1 < len(lines):
            m2 = CLONE_PEER_RE.match(lines[idx + 1])
            if m2 and (not baseline_active or current_is_new):
                p1, s1 = m1.group("f1"), int(m1.group("s1"))
                p2, s2, e2 = m2.group("f2"), m2.group("s2"), m2.group("e2")
                lns = m1.group("lines") or str(int(m1.group("e1")) - s1 + 1)
                tok = m1.group("tokens") or "0"
                msg = f"Clone with {p2}:{s2}-{e2} ({lns} lines, {tok} tokens)"
                findings.append(Finding(code="CPD001", path=p1, line=s1, message=msg))
                idx += 2
                continue
        idx += 1
    return findings


def _execute_jscpd(args: list[str], repo_root: Path) -> tuple[int, str, str, bool]:
    """Execute jscpd subprocess returning exitcode, stdout, stderr, and timeout."""
    try:
        res = subprocess.run(
            args,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
        return res.returncode, res.stdout, res.stderr, False
    except subprocess.TimeoutExpired:
        return 1, "", "Process timed out after 120s", True


def run_jscpd(
    jscpd_bin: str,
    target_paths: Sequence[str],
    config_path: Path | None,
    baseline_path: Path | None,
    update_baseline: bool,
    repo_root: Path,
) -> tuple[int, list[Finding], str]:
    """Execute jscpd subprocess and parse clone findings."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        args = build_jscpd_args(
            jscpd_bin,
            target_paths,
            config_path,
            baseline_path,
            update_baseline,
            tmp_path,
        )
        ret, out, err, timed_out = _execute_jscpd(args, repo_root)
        if timed_out:
            return 1, [Finding("CPD002", "jscpd", 1, err)], err
        json_file = tmp_path / "jscpd-report.json"
        base_act = bool(
            baseline_path and baseline_path.is_file() and not update_baseline
        )
        findings = parse_jscpd_json(json_file, base_act) if json_file.is_file() else []
        if not findings and out:
            findings = parse_stdout_clones(out, base_act)
        return ret, findings, f"{out}\n{err}".strip()


def _matches_staged(finding: Finding, staged_set: set[str]) -> bool:
    """Check if finding or its cloned peer involves a staged file."""
    if not staged_set:
        return True
    f_path = Path(finding.path).as_posix()
    if any(f_path.endswith(s) or s.endswith(f_path) for s in staged_set):
        return True
    return any(s in finding.message for s in staged_set)


def _resolve_targets(
    target_files: Sequence[str], staged: bool, has_base: bool, repo: Path
) -> tuple[list[str], set[str]]:
    """Determine jscpd targets and staged filter set."""
    staged_set: set[str] = set()
    if staged:
        staged_list = list(target_files) if target_files else collect_staged_files(repo)
        staged_set = {Path(p).as_posix() for p in staged_list}
    if staged and has_base:
        roots = [str(repo / r) for r in DEFAULT_ROOTS if (repo / r).exists()]
        extras = [
            f for f in target_files if not any(f.startswith(r) for r in DEFAULT_ROOTS)
        ]
        return roots + extras, staged_set
    if target_files:
        return list(target_files), staged_set
    return [str(repo / r) for r in DEFAULT_ROOTS if (repo / r).exists()], staged_set


def evaluate_duplication(
    target_files: Sequence[str],
    staged: bool,
    baseline_path: Path | None,
    update_baseline: bool,
    config_path: Path | None,
    custom_jscpd: str | None,
    repo_root: Path,
) -> tuple[list[Finding], str]:
    """Evaluate codebase or target files for duplication violations."""
    bin_path = resolve_jscpd_bin(custom_jscpd)
    if not bin_path:
        err = Finding(
            code="CPD000", path="jscpd", line=1, message="jscpd binary not found"
        )
        return [err], "Executable jscpd not found in PATH or ~/.local/bin/jscpd"
    has_base = bool(baseline_path and baseline_path.is_file() and not update_baseline)
    targets, staged_set = _resolve_targets(target_files, staged, has_base, repo_root)
    if not targets:
        return [], "No targets to scan."
    retcode, findings, output = run_jscpd(
        bin_path, targets, config_path, baseline_path, update_baseline, repo_root
    )
    if staged_set and findings:
        findings = [f for f in findings if _matches_staged(f, staged_set)]
    if retcode != 0 and not findings and not staged_set:
        findings.append(
            Finding(code="CPD002", path="jscpd", line=1, message=output[:200])
        )
    return findings, output


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register CLI arguments on parser."""
    parser.add_argument("files", nargs="*", help="Files or directories to scan.")
    flags: list[tuple[str, dict[str, object]]] = [
        ("--strict", {"action": "store_true", "help": "Fail closed on findings."}),
        (
            "--staged",
            {"action": "store_true", "help": "Scan staged files from Git index."},
        ),
        (
            "--baseline",
            {"type": Path, "default": DEFAULT_BASELINE, "help": "Baseline JSON."},
        ),
        (
            "--no-baseline",
            {"action": "store_true", "help": "Disable baseline verification."},
        ),
        (
            "--update-baseline",
            {"action": "store_true", "help": "Rewrite baseline file."},
        ),
        ("--config", {"type": Path, "default": DEFAULT_CONFIG, "help": "Config file."}),
        ("--jscpd-bin", {"type": str, "default": None, "help": "Explicit jscpd path."}),
        ("--json", {"type": Path, "default": None, "help": "Output findings to JSON."}),
    ]
    for flag, kwargs in flags:
        parser.add_argument(flag, **kwargs)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line options for duplication checker."""
    parser = argparse.ArgumentParser(
        description="Check for code duplication using jscpd."
    )
    _add_arguments(parser)
    return parser.parse_args(argv)


def output_json_report(findings: Sequence[Finding], dest: Path) -> None:
    """Save findings array to JSON file destination."""
    records = [
        {"code": f.code, "path": f.path, "line": f.line, "message": f.message}
        for f in findings
    ]
    dest.write_text(json.dumps(records, indent=2), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run duplication evaluation and exit with status code."""
    opts = parse_args(argv)
    baseline = None if opts.no_baseline else opts.baseline
    findings, _output = evaluate_duplication(
        target_files=opts.files,
        staged=opts.staged,
        baseline_path=baseline,
        update_baseline=opts.update_baseline,
        config_path=opts.config,
        custom_jscpd=opts.jscpd_bin,
        repo_root=REPO,
    )
    if opts.json:
        output_json_report(findings, opts.json)
    for f in findings:
        print(f"[check_duplication] {f.format()}", file=sys.stderr)
    if not findings:
        print("[check_duplication] checked targets, 0 finding(s)")
        return 0
    print(
        f"[check_duplication] {len(findings)} duplication finding(s)", file=sys.stderr
    )
    return 1 if opts.strict else 0


if __name__ == "__main__":
    sys.exit(main())
