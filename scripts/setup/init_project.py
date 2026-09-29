#!/usr/bin/env python3
"""Adopt the research template for a new project by rewriting its identity.

Invariants & Expected State:
    - Refuses a dirty worktree and an occupied target package or mirror test
      directory, so adoption starts from a clean checkout and never overwrites an
      existing tree.
    - ``--dry-run`` prints the exact plan (moves, rewritten files, regenerated
      ledgers) and writes nothing; the real run applies that plan and then scans
      every tracked text file, exiting non-zero while a token of the old identity
      survives anywhere in the tree.
    - Only tracked files outside ``third_party/``, ``.git/``, ``results/``,
      ``cache/`` and ``mutants/`` are read or rewritten, and the rewrite pass and
      the leftover scan share that one file list so the two cannot disagree.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework import harness

GIT_TIMEOUT_SECONDS = 300
HARNESS_PATH = REPO / "framework" / "harness.py"
PYPROJECT_PATH = REPO / "pyproject.toml"
INDEX_ARGS = ("-m", "framework.indexing.cli", "--output", "INDEX.md")
MIRRORS_SCRIPT = ("framework", "gates", "checks", "sync_agents_mirrors.py")
SKIP_PREFIXES = ("third_party/", ".git/", "results/", "cache/", "mutants/")
BINARY_SUFFIXES = frozenset(
    {
        ".bin",
        ".gif",
        ".gz",
        ".ico",
        ".jpeg",
        ".jpg",
        ".npy",
        ".npz",
        ".pdf",
        ".png",
        ".pt",
        ".pth",
        ".safetensors",
        ".tar",
        ".woff",
        ".woff2",
        ".zip",
    }
)
NAME_LINE = re.compile(r'^(name = )"[^"]*"', re.MULTILINE)
Rule = tuple[re.Pattern[str], str]


class AdoptionError(RuntimeError):
    """Raised when this checkout cannot be adopted: dirty, occupied or unwritable."""


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the new identity (slug, env prefix, gate code) and the dry-run flag."""

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--slug", required=True, help="new package and mirror-tree slug"
    )
    parser.add_argument("--prefix", required=True, help="new upper-case env-var prefix")
    parser.add_argument(
        "--code", required=True, help="new 2-4 letter gate finding code"
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan only")
    return parser.parse_args(argv)


def validate(slug: str, prefix: str, code: str) -> None:
    """Reject an identity the harness, the interpreter or the gate codes cannot carry."""

    checks = (
        (slug, r"[a-z][a-z0-9_]*", "slug must match [a-z][a-z0-9_]*"),
        (prefix, r"[A-Z][A-Z0-9_]*", "prefix must match [A-Z][A-Z0-9_]*"),
        (code, r"[A-Z]{2,4}", "code must be 2-4 upper-case letters"),
    )
    for value, pattern, message in checks:
        if not re.fullmatch(pattern, value):
            raise AdoptionError(f"{message}: {value!r}")
    current = (harness.SLUG, harness.ENV_PREFIX, harness.CODE_PREFIX)
    if (slug, prefix, code) == current:
        raise AdoptionError(f"the new identity is the current one: {current}")


def run(argv: list[str], cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    """Run one bounded command, capturing its text output for the caller to judge."""

    return subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )


def tracked_paths(repo: Path) -> list[str]:
    """Return every Git-tracked path in POSIX form, refusing when git cannot list them."""

    result = run(["git", "ls-files", "-z"], repo)
    if result.returncode:
        raise AdoptionError(f"git ls-files failed: {result.stderr.strip()}")
    return [path for path in result.stdout.split("\0") if path]


def readable_text(path: Path) -> str | None:
    """Return the file's text; ``None`` only for a known-binary or missing path."""

    if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def scan_files(repo: Path) -> list[tuple[str, str]]:
    """Return ``(relative path, text)`` for every tracked text file outside the skip list."""

    files: list[tuple[str, str]] = []
    for rel in tracked_paths(repo):
        if rel.startswith(SKIP_PREFIXES):
            continue
        text = readable_text(repo / rel)
        if text is not None:
            files.append((rel, text))
    return files


def build_rules(slug: str, prefix: str, code: str) -> tuple[Rule, ...]:
    """Return the ordered substitutions that move the current identity to the new one.

    The old tokens are matched anywhere but at the start of a longer word of the same
    case, so an embedded leftover (``OTHER_<PREFIX>_X``, ``_<slug>_probe``) is renamed
    too: the leftover scan below reuses these very rules, so a pattern the rewrite
    misses would otherwise be reported as a surviving token.
    """

    old_slug = re.escape(harness.SLUG)
    return (
        (re.compile(rf"tests/{old_slug}\b"), f"tests/{slug}"),
        (re.compile(rf"{old_slug}(?![A-Za-z0-9\s])"), slug),
        (re.compile(rf"{re.escape(harness.ENV_PREFIX)}(?![A-Za-z])"), prefix),
        (re.compile(rf"{re.escape(harness.CODE_PREFIX)}(?![A-Za-z])"), code),
    )


def apply_rules(text: str, rules: tuple[Rule, ...]) -> tuple[str, int]:
    """Apply every rule in order; return the rewritten text and how often rules fired."""

    total = 0
    for pattern, replacement in rules:
        text, hits = pattern.subn(replacement, text)
        total += hits
    return text, total


def rewrite_tracked(
    repo: Path, rules: tuple[Rule, ...], dry_run: bool
) -> list[tuple[str, int]]:
    """Rewrite the identity tokens in every tracked text file; return the per-file counts."""

    hits: list[tuple[str, int]] = []
    for rel, text in scan_files(repo):
        new_text, count = apply_rules(text, rules)
        if not count:
            continue
        hits.append((rel, count))
        if not dry_run:
            (repo / rel).write_text(new_text, encoding="utf-8")
    return hits


def rewrite_identity(
    path: Path, slug: str, prefix: str, code: str, dry_run: bool
) -> list[str]:
    """Rewrite the three harness identity literals; return the keys that changed."""

    text = path.read_text(encoding="utf-8")
    changed: list[str] = []
    for key, value in (("SLUG", slug), ("ENV_PREFIX", prefix), ("CODE_PREFIX", code)):
        pattern = re.compile(rf'^{key} = "[^"]*"$', re.MULTILINE)
        if not pattern.search(text):
            raise AdoptionError(f"{path.name}: no top-level {key} literal to rewrite")
        updated = pattern.sub(f'{key} = "{value}"', text, count=1)
        if updated != text:
            changed.append(key)
        text = updated
    if changed and not dry_run:
        path.write_text(text, encoding="utf-8")
    return changed


def rewrite_project_name(path: Path, slug: str, dry_run: bool) -> None:
    """Set ``[project] name`` in the pyproject to the new slug."""

    text = path.read_text(encoding="utf-8")
    updated, count = NAME_LINE.subn(f'name = "{slug}"', text, count=1)
    if not count:
        raise AdoptionError(f"{path.name}: no [project] name literal to rewrite")
    if updated != text and not dry_run:
        path.write_text(updated, encoding="utf-8")


def git_move(repo: Path, source: Path, target: Path, dry_run: bool) -> None:
    """``git mv`` one tracked tree, refusing a target that already exists."""

    if target.exists():
        raise AdoptionError(f"refusing to overwrite existing path: {target}")
    if dry_run:
        return
    moved = run(
        ["git", "mv", str(source.relative_to(repo)), str(target.relative_to(repo))],
        repo,
    )
    if moved.returncode:
        raise AdoptionError(f"git mv {source} {target} failed: {moved.stderr.strip()}")


def regenerate_index(repo: Path, dry_run: bool) -> None:
    """Regenerate INDEX.md and the per-root sub-indices through the real indexer."""

    if dry_run:
        return
    result = run([sys.executable, *INDEX_ARGS], repo)
    if result.returncode:
        raise AdoptionError(f"index regeneration failed: {result.stderr.strip()}")


def refresh_mirrors(repo: Path, dry_run: bool) -> None:
    """Rewrite the CLAUDE.md and .agents/AGENTS.md mirrors from the canonical AGENTS.md."""

    if dry_run:
        return
    script = repo.joinpath(*MIRRORS_SCRIPT)
    result = run([sys.executable, str(script)], repo)
    if result.returncode:
        raise AdoptionError(f"mirror refresh failed: {result.stderr.strip()}")


def leftover_findings(repo: Path, rules: tuple[Rule, ...]) -> list[str]:
    """Return ``path:line: token`` for every old-identity token still in a tracked text file."""

    findings: list[str] = []
    for rel, text in scan_files(repo):
        for number, line in enumerate(text.splitlines(), start=1):
            for pattern, _ in rules:
                match = pattern.search(line)
                if match:
                    findings.append(f"{rel}:{number}: {match.group(0)}")
    return findings


def say(label: str, dry_run: bool) -> None:
    """Print one plan line: ``would ...`` while dry-running, plain otherwise."""

    print(f"[init-project] {'would ' if dry_run else ''}{label}")


def report_hits(hits: list[tuple[str, int]], dry_run: bool) -> None:
    """Report the token pass: one line per file while dry-running, a summary otherwise."""

    total = sum(count for _, count in hits)
    if dry_run:
        for rel, count in hits:
            print(f"[init-project]   {rel}: {count} substitution(s)")
    say(f"rewrite {len(hits)} tracked text file(s), {total} substitution(s)", dry_run)


def report_leftovers(findings: list[str]) -> int:
    """Print the leftover scan and return a non-zero code while anything survived."""

    if findings:
        print(
            f"[init-project] leftover scan: {len(findings)} finding(s)", file=sys.stderr
        )
        for finding in findings:
            print(f"[init-project]   {finding}", file=sys.stderr)
        return 1
    print("[init-project] leftover scan: clean, no old-identity token survived")
    return 0


def adopt(args: argparse.Namespace, rules: tuple[Rule, ...]) -> int:
    """Apply the plan (or print it) and verify that no token of the old identity survives."""

    dry = args.dry_run
    tests = harness.TEST_ROOT
    say(f"git mv {harness.SLUG} -> {args.slug}", dry)
    git_move(REPO, REPO / harness.SLUG, REPO / args.slug, dry)
    say(f"git mv {tests}/{harness.SLUG} -> {tests}/{args.slug}", dry)
    git_move(REPO, REPO / tests / harness.SLUG, REPO / tests / args.slug, dry)
    changed = rewrite_identity(HARNESS_PATH, args.slug, args.prefix, args.code, dry)
    say(f"rewrite framework/harness.py ({', '.join(changed) or 'no change'})", dry)
    rewrite_project_name(PYPROJECT_PATH, args.slug, dry)
    say(f"rewrite pyproject.toml: [project] name -> {args.slug}", dry)
    report_hits(rewrite_tracked(REPO, rules, dry), dry)
    say("regenerate INDEX.md and the sub-indices", dry)
    regenerate_index(REPO, dry)
    say("refresh the AGENTS.md mirrors", dry)
    refresh_mirrors(REPO, dry)
    return 0 if dry else report_leftovers(leftover_findings(REPO, rules))


def main(argv: list[str] | None = None) -> int:
    """Plan, apply and verify the adoption; return the process exit code."""

    args = parse_args(argv)
    try:
        validate(args.slug, args.prefix, args.code)
        status = run(["git", "status", "--porcelain"])
        if status.returncode:
            raise AdoptionError(f"not a Git worktree: {REPO}")
        if status.stdout.strip():
            raise AdoptionError("worktree is dirty; commit or stash before adopting")
        return adopt(args, build_rules(args.slug, args.prefix, args.code))
    except AdoptionError as error:
        print(f"[init-project] FAIL: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
