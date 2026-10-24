#!/usr/bin/env python3
"""Fail-closed reference check for agent instruction artifacts (HNS073).

Thumbnail: Fails a file path an instruction artifact names that no tracked tree provides.

Invariants & Expected State:
    - A token is a backticked span that looks like a repository file path: it
      starts alphanumeric or underscore, ends in .py .sh .sbatch .md .toml
      .json .jsonl .yaml .yml .csv, and contains only letters, digits,
      underscore, dot, slash and dash. A bare path that follows ``python``,
      ``python3``, ``bash``, ``sh`` or ``sbatch`` on a line inside a fenced
      code block is a token too; there the span may carry ``<name>``
      placeholders, which are preserved so they classify as ``placeholder``.
      Globs, URLs, command flags and directory references never match.
    - Resolution is against tracked trees. The primary root is this repository
      (``git ls-files``); ``--roots`` adds siblings resolved by the same rule
      (tracked-exact, path-boundary suffix, or an existing path under that
      root). A token that resolves in a non-primary root is counted
      ``sibling`` and never fails: one artifact corpus is consumed from
      several trees, so a sibling-valid path is not rot.
    - Each unresolved token lands in exactly one bucket. ``placeholder`` is an
      example-shaped path segment (x/y/z, foo, bar, path/to, example, sample);
      it is a finding unless ``--allow-placeholder``. ``moved`` means exactly
      one root provides the basename, and the finding names that sole match;
      ``ambiguous`` (several candidates) is counted, never failed, because a
      guessed target is worse than none. ``output`` is a path whose first
      component no root tracks (``checkpoints/``, ``tmp_*``, ``steps/``):
      a runbook may name what a run will write, so that is counted too.
      ``dead`` means no root provides it.
      With more than one root in play, a bare filename (no ``/``) is
      ``filename``: it is counted and surfaced but
      never fails, because a multi-tree corpus cannot say whether the name is a
      produced artifact, a truncated reference or another tree's file -- the
      single-root (hook and repository) mode keeps grading it. The summary line
      carries every bucket count, so one census line is the whole evidence.
    - ``--staged`` reads each named file from the Git index; ``--corpus-root
      DIR`` also grades that tree's instruction corpus (``DIR/rules/*.md``,
      ``DIR/managed-skills/*/SKILL.md``, ``DIR/AGENTS.md``) beside this
      repository's ``AGENTS.md``, so one artifact set consumed from two trees is
      judged in one census. A git failure, an unreadable staged blob or an
      unreadable file is an environment error (exit 2), never a pass.
    - Files outside the declared corpus are ignored and stay silent.
    - Optional ``--manifest`` verifies the instruction manifest; absence of a
      specified manifest is an environment error (exit 2).
    - Exit 0 clean (or findings without ``--strict``), 1 findings with
      ``--strict``, 2 usage/environment error.

Usage::

  python framework/gates/instructions/check_instruction_refs.py [--strict]
  python framework/gates/instructions/check_instruction_refs.py --strict --staged AGENTS.md
  python framework/gates/instructions/check_instruction_refs.py --strict --corpus-root ../agent-config \\
      --roots ../sibling-project --allow-placeholder
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework import harness

REPO = harness.REPO
CANONICAL_INSTRUCTION = "AGENTS.md"
GENERATED_MIRRORS = ("CLAUDE.md", ".agents/AGENTS.md")
CORPUS_PATHS = (CANONICAL_INSTRUCTION, *GENERATED_MIRRORS)
DEFAULT_FILES = (CANONICAL_INSTRUCTION,)
MANIFEST_PATH = REPO / "results" / "manifests" / f"{harness.SLUG}.manifest.json"
SCHEMA = f"{harness.SLUG}.instruction_refs.v1"
CODE = f"{harness.CODE_PREFIX}073"
CONVENTION_NAMES = frozenset({"conftest.py"})

PLACEHOLDER_SEGMENTS = frozenset(
    {
        "x",
        "y",
        "z",
        "foo",
        "bar",
        "baz",
        "path",
        "to",
        "your",
        "my",
        "example",
        "sample",
    }
)
TOKEN_RE = re.compile(
    r"`([A-Za-z0-9_][A-Za-z0-9_./-]*"
    r"\.(?:py|sh|sbatch|md|toml|json|jsonl|ya?ml|csv))"
    r"(?:#[A-Za-z0-9_.-]+|:[0-9]+(?:-[0-9]+)?)?`"
)
FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)^```", re.DOTALL | re.MULTILINE)
COMMAND_RE = re.compile(
    r"[ \t]*(?:python3?|bash|sh|sbatch)[ \t]+"
    r"([A-Za-z0-9_<][A-Za-z0-9_.<>/-]*\.(?:py|sh|sbatch|json|toml|ya?ml))"
    r"(?![A-Za-z0-9_.<>/-])"
)
BUCKETS = (
    "resolved",
    "sibling",
    "filename",
    "placeholder",
    "moved",
    "output",
    "ambiguous",
    "dead",
)
FAILING_BUCKETS = ("moved", "dead")


@dataclass(frozen=True)
class Finding:
    """One stale file reference in an instruction artifact."""

    path: str
    line: int
    code: str
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.code} {self.message}"


@dataclass(frozen=True)
class Root:
    """One tracked tree a reference may resolve in."""

    name: str
    path: Path
    tracked: tuple[str, ...]
    known: frozenset[str]
    by_basename: dict[str, tuple[str, ...]]
    first_segments: frozenset[str]


@dataclass(frozen=True)
class Census:
    """Bucket counts plus the findings for one graded artifact."""

    counts: dict[str, int]
    findings: list[Finding]


def _basenames(tracked: Sequence[str]) -> dict[str, tuple[str, ...]]:
    """Map each tracked basename to every tracked path that carries it."""
    found: dict[str, list[str]] = {}
    for rel in tracked:
        found.setdefault(Path(rel).name, []).append(rel)
    return {name: tuple(paths) for name, paths in found.items()}


def _first_segments(tracked: Sequence[str]) -> frozenset[str]:
    """Return the top-level path components a tree actually tracks."""
    return frozenset(rel.split("/", 1)[0] for rel in tracked)


def _tracked_in(path: Path) -> tuple[str, ...] | None:
    """Return the tracked paths of one tree, or None when Git cannot list them."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return None
    return tuple(line for line in result.stdout.splitlines() if line)


def _load_root(name: str, path: Path) -> Root | None:
    """Build one resolution root, or None when the tree cannot be read."""
    tracked = _tracked_in(path)
    if tracked is None:
        return None
    return Root(
        name,
        path,
        tracked,
        frozenset(tracked),
        _basenames(tracked),
        _first_segments(tracked),
    )


def _load_roots(extra: Sequence[str]) -> list[Root] | None:
    """Return the primary root plus every extra tree, or None on failure."""
    primary = _load_root("repo", REPO)
    if primary is None:
        return None
    roots = [primary]
    for raw in extra:
        path = Path(raw)
        root = _load_root(path.name, path)
        if root is None:
            return None
        roots.append(root)
    return roots


def _in_root(token: str, root: Root) -> bool:
    """True when ``token`` resolves inside ``root``."""
    if token in CONVENTION_NAMES:
        return True
    if token in root.known or any(rel.endswith("/" + token) for rel in root.tracked):
        return True
    return (root.path / token).exists()


def _is_placeholder(token: str) -> bool:
    """True for example-shaped paths that name no real artifact."""
    if "<" in token or ">" in token:
        return True
    return bool(PLACEHOLDER_SEGMENTS.intersection(Path(token).parts[:-1]))


def _basename_match(token: str, roots: Sequence[Root]) -> tuple[str | None, str]:
    """Return the union-wide unique basename match and an ambiguity detail."""
    total = 0
    target = ""
    for root in roots:
        candidates = root.by_basename.get(Path(token).name, ())
        total += len(candidates)
        if len(candidates) == 1 and not target:
            target = f"{root.name}:{candidates[0]}"
    if total == 1 and target:
        return target, ""
    return None, f"{total} candidates" if total else ""


def _known_segments(roots: Sequence[Root]) -> frozenset[str]:
    """Return every top-level component the roots track."""
    known: set[str] = set()
    for root in roots:
        known |= root.first_segments
    return frozenset(known)


def _classify(token: str, roots: Sequence[Root]) -> tuple[str, str]:
    """Return ``(bucket, detail)`` for one token against the root list."""
    primary, siblings = roots[0], roots[1:]
    if _in_root(token, primary):
        return "resolved", ""
    for root in siblings:
        if _in_root(token, root):
            return "sibling", root.name
    if _is_placeholder(token):
        return "placeholder", ""
    if len(roots) > 1 and "/" not in token:
        return "filename", ""
    moved, ambiguous = _basename_match(token, roots)
    if moved is not None:
        return "moved", moved
    if "/" in token and token.split("/", 1)[0] not in _known_segments(roots):
        return "output", ""
    if ambiguous:
        return "ambiguous", ambiguous
    return "dead", ""


def _message(token: str, bucket: str, detail: str) -> str:
    """Return the HNS073 message for one unresolved token."""
    if bucket == "moved":
        return (
            f"stale instruction reference: {token} moved; sole basename match "
            f"at {detail} (context rot; arXiv:2606.09090)"
        )
    return (
        f"stale instruction reference: {token} matches no tracked file "
        "(context rot; arXiv:2606.09090)"
    )


def _fenced_command_tokens(text: str) -> list[tuple[str, int]]:
    """Return ``(path, offset)`` for command lines inside fenced blocks."""
    found: list[tuple[str, int]] = []
    for fence in FENCE_RE.finditer(text):
        base = fence.start(1)
        offset = 0
        for line in fence.group(1).splitlines(keepends=True):
            match = COMMAND_RE.match(line)
            if match is not None:
                found.append((match.group(1), base + offset + match.start(1)))
            offset += len(line)
    return found


def _extract_tokens(text: str) -> list[tuple[str, int]]:
    """Return ``(token, offset)`` for every candidate path in ``text``."""
    found = [(match.group(1), match.start(1)) for match in TOKEN_RE.finditer(text)]
    found.extend(_fenced_command_tokens(text))
    return sorted(found, key=lambda item: item[1])


def census(
    path: str,
    text: str,
    roots: Sequence[Root],
    allow_placeholder: bool = False,
) -> Census:
    """Classify every token of ``text``; counts are per occurrence."""
    counts = dict.fromkeys(BUCKETS, 0)
    findings: list[Finding] = []
    seen: dict[str, int] = {}
    for token, offset in _extract_tokens(text):
        bucket, detail = _classify(token, roots)
        counts[bucket] += 1
        placeholder_fails = bucket == "placeholder" and not allow_placeholder
        if token in seen or not (bucket in FAILING_BUCKETS or placeholder_fails):
            continue
        seen[token] = text.count("\n", 0, offset) + 1
        findings.append(
            Finding(path, seen[token], CODE, _message(token, bucket, detail))
        )
    return Census(counts, findings)


def grade(path: str, text: str, tracked: list[str]) -> list[Finding]:
    """Return HNS073 findings for ``text`` against one flat tracked list."""
    root = Root(
        "repo",
        REPO,
        tuple(tracked),
        frozenset(tracked),
        _basenames(tracked),
        _first_segments(tracked),
    )
    return census(path, text, [root]).findings


def _read(path: str, staged: bool) -> str | None:
    """Return the text of ``path`` from the Git index or the working tree."""
    if staged:
        result = subprocess.run(
            ["git", "cat-file", "-p", f":{path}"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.stdout if result.returncode == 0 else None
    target = Path(path) if Path(path).is_absolute() else REPO / path
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _corpus_files(root: Path) -> list[str]:
    """Return ``root``'s instruction corpus (rules, skills, AGENTS.md) + this repo's.

    The tree layout is a convention, not a product name: ``rules/*.md``,
    ``managed-skills/*/SKILL.md`` and ``AGENTS.md`` under the caller's root, plus
    the repository's own ``AGENTS.md``. A root that does not exist contributes
    only the repository file.
    """

    files = [str(REPO / CANONICAL_INSTRUCTION)]
    candidates = sorted(root.glob("rules/*.md"))
    candidates += sorted(root.glob("managed-skills/*/SKILL.md"))
    agents = root / CANONICAL_INSTRUCTION
    if agents.is_file():
        candidates.append(agents)
    files.extend(str(path) for path in candidates)
    return files


def _is_in_corpus(path: str, declared_corpus: set[str]) -> bool:
    """Return True if path matches one of the declared corpus paths."""
    p = Path(path)
    if str(p) in declared_corpus or p.name in declared_corpus:
        return True
    try:
        rel = str(p.relative_to(REPO))
        if rel in declared_corpus:
            return True
    except ValueError:
        pass
    return False


def _write_report(
    path: str,
    files: Sequence[str],
    counts: dict[str, int],
    findings: Sequence[Finding],
) -> None:
    """Write the machine-readable census the sweep script consumes."""
    payload = {
        "schema": SCHEMA,
        "files": list(files),
        "buckets": counts,
        "findings": [
            {
                "path": finding.path,
                "line": finding.line,
                "code": finding.code,
                "message": finding.message,
            }
            for finding in findings
        ],
    }
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 1 on findings")
    parser.add_argument("--staged", action="store_true", help="read from git index")
    parser.add_argument(
        "--corpus-root",
        type=Path,
        help="also grade another tree's instruction corpus (rules/*.md, "
        "managed-skills/*/SKILL.md, AGENTS.md) beside this repository's AGENTS.md",
    )
    parser.add_argument("--roots", nargs="+", default=[], help="extra tracked trees")
    parser.add_argument(
        "--allow-placeholder", action="store_true", help="count placeholders"
    )
    parser.add_argument("--report", help="write census json here")
    parser.add_argument("--manifest", help="path to JSON manifest (error if missing)")
    parser.add_argument("files", nargs="*", default=[], help="files to grade")
    return parser


def _collect_all(
    files: Sequence[str], roots: Sequence[Root], args: argparse.Namespace
) -> tuple[dict[str, int], list[Finding]] | None:
    counts = dict.fromkeys(BUCKETS, 0)
    findings: list[Finding] = []
    for path in files:
        text = _read(path, args.staged)
        if text is None:
            print(
                f"[check_instruction_refs] ERROR: cannot read {path}", file=sys.stderr
            )
            return None
        result = census(path, text, roots, args.allow_placeholder)
        findings.extend(result.findings)
        for bucket, value in result.counts.items():
            counts[bucket] += value
    return counts, findings


def _resolve_files(args: argparse.Namespace) -> list[str]:
    """Return the files to grade, filtering out paths outside declared corpus."""
    if args.corpus_root is not None:
        return _corpus_files(args.corpus_root)
    declared = set(CORPUS_PATHS)
    raw_files = list(args.files) if args.files else list(DEFAULT_FILES)
    return [f for f in raw_files if _is_in_corpus(f, declared)]


def main(argv: Sequence[str] | None = None) -> int:
    """Grade the named instruction artifacts; 0 clean, 1 findings, 2 error."""
    args = _build_parser().parse_args(argv)
    if args.manifest:
        manifest_file = Path(args.manifest)
        if not manifest_file.is_file():
            print(
                f"[check_instruction_refs] ERROR: manifest not found: {args.manifest}",
                file=sys.stderr,
            )
            return 2
    roots = _load_roots(args.roots)
    if roots is None:
        print("[check_instruction_refs] ERROR: git ls-files failed", file=sys.stderr)
        return 2
    files = _resolve_files(args)
    collected = _collect_all(files, roots, args)
    if collected is None:
        return 2
    counts, findings = collected
    for finding in findings:
        print(f"[check_instruction_refs] {finding.format()}", file=sys.stderr)
    if args.report:
        _write_report(args.report, files, counts, findings)
    summary = ", ".join(f"{bucket}={counts[bucket]}" for bucket in BUCKETS)
    print(
        f"[check_instruction_refs] checked {len(files)} file(s), "
        f"{len(findings)} finding(s) | buckets: {summary}"
    )
    return 1 if findings and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
