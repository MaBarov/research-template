#!/usr/bin/env python3
"""GPU canary gate — framework step 4e (pre-submit, generic).

Invariants & Expected State:
    - Derivation is pure and deterministic: ``derive_canary`` returns "" when the
      source carries no driver python invocation (canary N/A, exit 0) and
      otherwise a bounded copy of the same script text.
    - Positional arguments the job script requires are forwarded verbatim to the
      derived submission (``--arg``, repeatable) and recorded in the receipt: a
      payload-arg job canaried without them is a job that would run unarmed.
    - The verdict comes from sacct only — COMPLETED with exit 0 or 124 (killed
      alive by the bound) passes; a crash before the bound fails.
    - Skipped with exit 0 where sbatch/sacct are absent, so the gate works off
      cluster; ``--dry-run`` prints the derived text and never submits.

Predicts failure classes that static gates and CPU stubs cannot see — device
miswiring (CPU generator -> CUDA randn), OOM, capacity, missing weights — by
running the REAL sbatch script bounded on the REAL GPU class BEFORE the real
submission. A canary that survives the bounded window (alive at timeout) or
completes is PASS; any earlier crash is FAIL. This is the deterministic
"predict crashes before the run starts" mechanism, and it is NOT specific to
any experiment: it derives from any cluster/<x>.sbatch with a driver python
invocation.

Derivation is mechanical: copy the source script, override job-name/time/
output directives, optionally inject a parking hook (state JSONs must not be
poisoned by the killed canary) and a METHOD override, and wrap the driver
python invocation in `timeout`. The verdict comes from sacct (State +
ExitCode). A receipt JSON lands in results/canary/<base>.receipt.json.

CLI:
  canary_gate.py --script cluster/<x>.sbatch [--method NAME] [--hook PATH]
                 [--time SECONDS] [--wait SECONDS] [--dry-run] [--arg VALUE ...]
Exit: 0 pass/skip, 1 fail, 2 usage. SIGINT cancels a submitted canary job.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

_ENTRY_REPO = Path(__file__).resolve().parents[3]
if str(_ENTRY_REPO) not in sys.path:
    sys.path.insert(0, str(_ENTRY_REPO))

from framework import harness

REPO = _ENTRY_REPO
CANARY_DIR = REPO / "results" / "canary"
SETUP_GRACE_SECONDS = 900
DRIVER_RE = re.compile(
    r"^\s*(?:stdbuf\s+-oL\s+-eL\s+)?(?:[\"']?\$VENV/bin/python[\"']?|[\"']?\$PYTHON[\"']?)\s+-u(?:\s|$)"
)
CHILD_SBATCH_RE = re.compile(r"^\s*exec\s+(?:bash\s+)?(?P<path>.+\.sbatch[\"']?)\s*$")

_ACTIVE_JOB: dict[str, str] = {}


def _cancel_on_int(signum: int, frame: object) -> None:
    jobid = _ACTIVE_JOB.get("jobid")
    if jobid:
        subprocess.run(["scancel", jobid], capture_output=True, check=False)
        print(f"[canary] SIGINT: canary job {jobid} cancelled", flush=True)
    sys.exit(130)


def _apply_directives(line: str, directives: dict[str, str], seen: set[str]) -> str:
    """Override or mark each #SBATCH --key= directive; else return line unchanged."""
    for key, replacement in directives.items():
        if line.startswith(f"#SBATCH --{key}="):
            seen.add(key)
            return replacement
    return line


def _prelude_lines(method: str | None, hook: str | None) -> list[str]:
    """Lines injected immediately before the driver invocation."""
    pre: list[str] = []
    if method:
        pre.append(f'export METHOD="{method}"')
    if hook:
        pre.append(f'bash "{hook}" park')
        pre.append(f"trap 'bash \"{hook}\" restore' EXIT")
    return pre


def _inject_directives(
    lines: list[str], directives: dict[str, str], seen: set[str]
) -> list[str]:
    """Insert missing directives after the shebang, in canonical dict order."""
    missing = [d for k, d in directives.items() if k not in seen]
    if missing:
        lines[1:1] = missing
    return lines


def _bounded_command(command: str, time_seconds: int) -> str:
    """Keep expected timeout alive signal from becoming a Slurm failure."""
    return (
        f"timeout {time_seconds} {command} || {{ code=$?; "
        'if [ "$code" -eq 124 ]; then echo "status=CANARY_TIMEOUT_ALIVE"; exit 0; '
        'else exit "$code"; fi; }'
    )


def _continuation_end(lines: list[str], start: int) -> int:
    """Return final source line belonging to one backslash-continued command."""
    end = start
    while end + 1 < len(lines) and lines[end].rstrip().endswith("\\"):
        end += 1
    return end


def _canary_name(src: Path, method: str | None) -> str:
    """Prevent concurrent method canaries from sharing files."""
    return f"{src.stem}_{method}" if method else src.stem


def _canary_directives(
    name: str, time_seconds: int, canary_dir: Path
) -> dict[str, str]:
    """Derive the bounded-time #SBATCH directive overrides for one canary."""
    script_limit = time_seconds + SETUP_GRACE_SECONDS
    time_line = (
        f"{script_limit // 3600:02d}:"
        f"{script_limit % 3600 // 60:02d}:"
        f"{script_limit % 60:02d}"
    )
    return {
        "job-name": f"#SBATCH --job-name=canary_{name}",
        "time": f"#SBATCH --time={time_line}",
        "output": f"#SBATCH --output={canary_dir / (name + '_%A.log')}",
    }


def _driver_positions(source_lines: list[str]) -> tuple[list[int], list[int]]:
    """Return the direct-driver and child-sbatch source line indices."""
    direct = [i for i, raw in enumerate(source_lines) if DRIVER_RE.search(raw)]
    child = [i for i, raw in enumerate(source_lines) if CHILD_SBATCH_RE.search(raw)]
    return direct, child


def _bounded_driver_line(
    line: str, tail: list[str], direct: list[int], time_seconds: int
) -> str:
    """Bound one driver invocation: a direct python call or a child sbatch."""
    child_match = CHILD_SBATCH_RE.search(line)
    command = "\n".join([line, *tail])
    return (
        _bounded_command(f"bash {child_match.group('path')}", time_seconds)
        if child_match and not direct
        else _bounded_command(command, time_seconds)
    )


def _rewrite_canary_lines(
    source_lines: list[str],
    directives: dict[str, str],
    seen: set[str],
    prelude: list[str],
    time_seconds: int,
) -> list[str] | None:
    """Rewrite source lines into the bounded canary body (None when N/A)."""
    direct, child = _driver_positions(source_lines)
    candidates = direct or child
    if not candidates or not source_lines or not source_lines[0].startswith("#!"):
        return None
    driver_index = candidates[-1]
    driver_end = _continuation_end(source_lines, driver_index)
    lines: list[str] = []
    for index, raw in enumerate(source_lines):
        if driver_index < index <= driver_end:
            continue
        line = _apply_directives(raw, directives, seen)
        if index == driver_index:
            lines.extend(prelude)
            tail = source_lines[index + 1 : driver_end + 1]
            line = _bounded_driver_line(line, tail, direct, time_seconds)
        lines.append(line)
    return lines


def derive_canary(
    source: str,
    *,
    name: str,
    time_seconds: int,
    method: str | None = None,
    hook: str | None = None,
    canary_dir: Path = CANARY_DIR,
) -> str:
    """Deterministically derive a bounded canary sbatch from the source text.

    Returns "" when no driver python invocation exists (canary N/A), else the
    derived script text. Pure function — unit-testable without a cluster.
    """
    directives = _canary_directives(name, time_seconds, canary_dir)
    seen: set[str] = set()
    lines = _rewrite_canary_lines(
        source.splitlines(),
        directives,
        seen,
        _prelude_lines(method, hook),
        time_seconds,
    )
    if lines is None:
        return ""
    return "\n".join(_inject_directives(lines, directives, seen)) + "\n"


def verdict_for(state: str, exitcode: str) -> tuple[bool, str]:
    """PASS when the job finished (0) or was killed alive by the bound (124)."""
    code = exitcode.partition(":")[0]
    if state == "COMPLETED" and code in ("0", "124"):
        note = "alive at bounded window" if code == "124" else "finished"
        return True, f"{state} exit {exitcode} ({note})"
    return False, f"state={state} exit={exitcode} — crashed before the bound"


def _tail(path: Path, n: int = 12) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return f"(no log at {path})"
    return "\n".join(lines[-n:]) if lines else "(empty log)"


def _write_receipt(receipt: dict, name: str) -> None:
    try:
        CANARY_DIR.mkdir(parents=True, exist_ok=True)
        (CANARY_DIR / f"{name}.receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8"
        )
    except OSError as exc:
        print(
            f"[canary] WARN: receipt write failed: {exc}", file=sys.stderr, flush=True
        )


def _submit(derived_path: Path, payload: list[str]) -> str:
    sub = subprocess.run(
        ["sbatch", str(derived_path), *payload],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if sub.returncode != 0:
        raise RuntimeError(f"sbatch failed: {sub.stderr.strip() or sub.stdout.strip()}")
    m = re.search(r"Submitted batch job (\d+)", sub.stdout)
    if not m:
        raise RuntimeError(f"unrecognized sbatch output: {sub.stdout.strip()}")
    return m.group(1)


def _poll(jobid: str, wait_s: int) -> tuple[str, str]:
    """Bound the canary run; return (state, exitcode). Cancels on timeout."""
    started = time.monotonic()
    last = None
    while time.monotonic() - started < wait_s:
        try:
            raw = subprocess.run(
                ["sacct", "-j", jobid, "-X", "-n", "-o", "State,ExitCode"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            ).stdout.strip()
        except subprocess.TimeoutExpired:
            time.sleep(15)
            continue
        parts = raw.split()
        if len(parts) >= 2 and parts[0] != last:
            state, exitcode = parts[0], parts[1]
            print(f"[canary] job {jobid} state={state} exit={exitcode}", flush=True)
            last = parts[0]
            if state not in ("PENDING", "RUNNING", "CONFIGURING", "COMPLETING"):
                return state, exitcode
        time.sleep(15)
    subprocess.run(["scancel", jobid], capture_output=True, check=False)
    return "CANCELLED_BY_GATE", "124"


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--script", required=True, help="cluster/<x>.sbatch to canary")
    ap.add_argument("--method", default=None, help="override METHOD env in the canary")
    ap.add_argument(
        "--hook", default=None, help="scripts/smoke/<name>_canary.sh (park|restore)"
    )
    ap.add_argument(
        "--arg",
        action="append",
        default=[],
        metavar="VALUE",
        help="positional argument the job script requires; repeat per argument",
    )
    ap.add_argument(
        "--time", type=int, default=600, help="bounded run seconds (default 600)"
    )
    ap.add_argument(
        "--wait", type=int, default=0, help="max wait seconds (default time+180)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="print derived script, do not submit"
    )
    return ap


def _stage_derived_script(
    name: str, derived: str, source: str, src: Path, args: argparse.Namespace
) -> tuple[Path, dict]:
    """Write the derived canary script and build its receipt skeleton."""
    CANARY_DIR.mkdir(parents=True, exist_ok=True)
    derived_path = CANARY_DIR / f"{name}.canary.sbatch"
    derived_path.write_text(derived, encoding="utf-8")
    receipt: dict = {
        "schema": harness.CANARY_RECEIPT_SCHEMA,
        "source_script": str(src),
        "source_sha256_16": hashlib.sha256(source.encode()).hexdigest()[:16],
        "derived_path": str(derived_path),
        "time_seconds": args.time,
        "method": args.method,
        "hook": args.hook,
        "payload_args": list(args.arg),
    }
    return derived_path, receipt


def _run(args: argparse.Namespace) -> int:
    src = REPO / args.script
    if not src.is_file():
        print(f"[canary] FAIL: no script {src}", file=sys.stderr, flush=True)
        return 1
    source = src.read_text(encoding="utf-8")
    name = _canary_name(src, args.method)
    derived = derive_canary(
        source,
        name=name,
        time_seconds=args.time,
        method=args.method,
        hook=args.hook,
    )
    if not derived:
        print(
            f"[canary] SKIP: no driver python invocation in {src} — canary N/A",
            flush=True,
        )
        return 0
    derived_path, receipt = _stage_derived_script(name, derived, source, src, args)
    if args.dry_run:
        print(derived, end="", flush=True)
        return 0
    return _execute(args, derived_path, receipt, name)


def main(argv: list[str] | None = None) -> int:
    return _run(_build_parser().parse_args(argv))


def _submit_and_record(
    args: argparse.Namespace, derived_path: Path, receipt: dict, name: str
) -> str | None:
    """Submit the bounded canary and record the submission in its receipt."""
    try:
        jobid = _submit(derived_path, list(args.arg))
    except RuntimeError as exc:
        print(f"[canary] FAIL: {exc}", file=sys.stderr, flush=True)
        return None
    _ACTIVE_JOB["jobid"] = jobid
    signal.signal(signal.SIGINT, _cancel_on_int)
    receipt.update(
        sbatch_jobid=jobid,
        submitted_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        log_path=str(CANARY_DIR / f"{name}_{jobid}.log"),
    )
    print(f"[canary] submitted bounded canary {jobid} for {args.script}", flush=True)
    return jobid


def _execute(
    args: argparse.Namespace, derived_path: Path, receipt: dict, name: str
) -> int:
    if shutil.which("sbatch") is None or shutil.which("sacct") is None:
        print(
            "[canary] SKIP: not a SLURM host (no sbatch/sacct) — canary N/A", flush=True
        )
        return 0
    jobid = _submit_and_record(args, derived_path, receipt, name)
    if jobid is None:
        return 1
    wait_s = args.wait or args.time + SETUP_GRACE_SECONDS + 60
    t0 = time.monotonic()
    state, exitcode = _poll(jobid, wait_s)
    ok, why = verdict_for(state, exitcode)
    receipt.update(
        state=state,
        exitcode=exitcode,
        verdict="pass" if ok else "fail",
        duration_s=round(time.monotonic() - t0, 1),
    )
    _write_receipt(receipt, name)
    if ok:
        print(f"[canary] PASS {args.script}: {why}", flush=True)
        return 0
    log_path = CANARY_DIR / f"{name}_{jobid}.log"
    print(f"[canary] FAIL {args.script}: {why}", file=sys.stderr, flush=True)
    print(f"[canary] log tail:\n{_tail(log_path)}", file=sys.stderr, flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
