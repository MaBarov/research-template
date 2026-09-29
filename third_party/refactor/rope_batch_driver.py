#!/usr/bin/env python3
"""Apply many name-based Rope batches in ONE Rope process.

Why this exists: every ``rope_refactor.py`` CLI invocation pays Rope's
source-module import re-resolution once (measured ~110s on a 2205-line source
module with ~60 imports) in addition to the per-move project scan.  Sixteen
invocations therefore cost ~30 minutes; the same work in one process pays that
cost once and then roughly a second per move.

Usage::

    python rope_batch_driver.py --root ROOT --jobs jobs.json [--dry-run] [--json]

``jobs.json``::

    [{"source_file": "experiments/.../probe.py",
      "dest_file": "experiments/.../tier_pairs/measure/readout.py",
      "names": ["_median", "_ratio"]}, ...]

Each job is validated and applied exactly like the ``move_globals`` action of
the CLI.  ``--dry-run`` computes and validates without applying the merged
change set (like the CLI, the per-name merge preview writes and restores files
while it composes the batch).  A validation failure undoes that job and stops
the run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import rope_refactor as R  # noqa: E402  (sibling tool import)


def load_jobs(path: Path) -> list[dict]:
    jobs = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(jobs, list) or not jobs:
        raise SystemExit("jobs file must be a non-empty JSON list")
    for job in jobs:
        missing = {"source_file", "dest_file", "names"} - set(job)
        if missing:
            raise SystemExit(f"job missing keys {sorted(missing)}: {job!r}")
    return jobs


def build_job_args(root: Path, job: dict) -> argparse.Namespace:
    argv = [
        "move_globals",
        "--root",
        str(root),
        "--source-file",
        job["source_file"],
        "--dest-file",
        job["dest_file"],
        "--names",
        *job["names"],
    ]
    return R.build_parser().parse_args(argv)


def apply_job(project, root: Path, job: dict, dry_run: bool) -> dict:
    started = time.perf_counter()
    args = build_job_args(root, job)
    changes, message = R.rope_batch.action_move_globals(project, root, args, R)
    report = {
        "names": job["names"],
        "dest": job["dest_file"],
        "message": message,
        "seconds": 0.0,
    }
    if changes is None:
        report["files"] = []
        report["seconds"] = round(time.perf_counter() - started, 2)
        return report

    paths = R.collect_change_paths(changes, root)
    report["files"] = [R.display_path(path, root) for path in paths]
    if not dry_run:
        project.do(changes)
        errors = R.validate_python_files(paths)
        if errors:
            R.undo_last_change(project)
            report.update({"ok": False, "errors": errors})
            report["seconds"] = round(time.perf_counter() - started, 2)
            return report
    report["seconds"] = round(time.perf_counter() - started, 2)
    return report


def report_human(reports: list[dict]) -> None:
    for report in reports:
        state = "ok" if report.get("ok", True) else "FAILED"
        print(
            f"[{report['job']}] {state} {report['seconds']:7.2f}s "
            f"{report['dest']} <- {', '.join(report['names'])}"
        )
        for error in report.get("errors", []):
            print(f"    {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rope_batch_driver.py",
        description="Apply many move_globals batches in one Rope process.",
    )
    parser.add_argument("--root", default=".", help="Project root (Rope root).")
    parser.add_argument(
        "--jobs", required=True, help="JSON list of {source_file, dest_file, names}."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Compute and validate, apply nothing."
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable report.")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Project root is not a directory: {args.root}")
    jobs = load_jobs(Path(args.jobs))

    project = R.open_project(root, argparse.Namespace(rope_folder=None))
    reports: list[dict] = []
    try:
        for index, job in enumerate(jobs, start=1):
            report = apply_job(project, root, job, args.dry_run)
            report["job"] = index
            reports.append(report)
            if not report.get("ok", True):
                break
    finally:
        project.close()

    ok = all(report.get("ok", True) for report in reports) and len(reports) == len(jobs)
    if args.json:
        print(json.dumps({"ok": ok, "dry_run": args.dry_run, "jobs": reports}, indent=2))
    else:
        report_human(reports)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
