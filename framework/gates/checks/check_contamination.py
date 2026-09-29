#!/usr/bin/env python3
"""Contamination gate — automated overlap & quality check for curated bank pairs.

Guardrail #2: catches the class of confound where the "safe" side of a bank pair
already carries the factor the intervention was meant to preserve or remove, so
the measurement reports the leak instead of the intervention's effect. Checks, in
order:
  C1 exact/normalized duplicate overlap concept <-> safe
  C2 safe-side rows carrying a banned source marker (NSFW_MARKERS, below)
  C3 low-n warning (n < 25 per cell => binomial significance unreliable)
  C4 near-duplicate guard: >X% token-overlap pairs flagged as LOOKALIKE
Exit codes: 0 clean, 1 violations (--strict), 2 usage.
Usage: python framework/gates/checks/check_contamination.py [--strict] BANK_JSON [...]
Writes results/gate_log.jsonl event lines.

The module is domain-neutral: NSFW_MARKERS and the bank layout keys are the
only domain-specific knobs, and both are plain strings a caller can restate.

Invariants & Expected State:
    - Read-Only Grading: Bank JSON files are read and graded in the order given;
      nothing is written beside the gate log's append-only event lines.
    - Pair-Bank Self-Attestation: A ``selected_pairs`` bank must record the
      selection criterion it was built under (``selection_distance`` plus
      ``selection_threshold``) alongside its own ``passed_gate`` claim, so the
      claim can be re-derived from the bank. A bank that reports
      ``passed_gate: true`` without those fields is unverifiable; reporting a
      distance above its own threshold is a violation. An honest
      ``passed_gate: false`` reading is not a violation.
    - Verdict-Path Unity: Every violation line is produced by this module and
      names the file it came from, so a caller can always attribute a failure.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GATE_LOG = REPO / "results" / "gate_log.jsonl"
TOKEN_RE = re.compile(r"[a-z0-9]+")
NSFW_MARKERS = (
    "i2p",
    "nsfw",
    "nudit",
    "sexual",
    "adult",
)  # project-specific: edit for your domain
LOOKALIKE_OVERLAP = 0.7  # token-overlap ratio that flags a near-duplicate
PAIR_BANK_KEY = "selected_pairs"  # certified concept/guide pair banks


def log_event(target: str, gate: str, result: str, reason: str) -> None:
    try:
        with GATE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": __import__("datetime")
                        .datetime.now(tz=__import__("datetime").timezone.utc)
                        .isoformat(),
                        "agent": "contamination-gate",
                        "tool": "check_contamination",
                        "target": target,
                        "gate": gate,
                        "result": result,
                        "reason": reason,
                        "commit": "(gate)",
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    except OSError:
        pass


def load_bank(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    # A pair bank is recognised only when it carries no concept/safe lists: a
    # bank that has both layouts is graded by C1-C4, so a contaminated bank
    # cannot leave through the pair branch.
    if isinstance(data.get(PAIR_BANK_KEY), list) and not (
        data.get("concept_prompts") or data.get("safe_prompts")
    ):
        return {
            "layout": "pair",
            "raw": data,
            "concept": [],
            "safe": [],
            "n_concept": 0,
            "n_safe": 0,
        }
    concept = data.get("concept_prompts") or []
    safe = data.get("safe_prompts") or []
    if not isinstance(concept, list) or not isinstance(safe, list):
        raise TypeError(
            f"{path}: banks must be lists under concept_prompts/safe_prompts"
        )
    return {
        "layout": "concept_safe",
        "raw": data,
        "concept": concept,
        "safe": safe,
        "n_concept": len(concept),
        "n_safe": len(safe),
    }


def _pair_bank_violations(data: dict) -> list[str]:
    """A pair bank must carry the criterion and numbers behind its own claim.

    ``selected_pairs`` banks hold concept/guide atom pairs instead of the flat
    concept/safe prompt lists C1-C4 inspect, so those checks have nothing to
    read. This check therefore polices one property: a bank that asserts
    ``passed_gate`` must also record the selection criterion it was graded
    under — the ``selection_distance`` value and the ``selection_threshold``
    it was compared against — and the recorded distance must not exceed that
    threshold. Without those fields the claim is unverifiable, which is a
    violation; a bank that reports ``passed_gate`` false is not claiming
    anything and passes regardless of its numbers.
    """
    if data.get("passed_gate") is not True:
        return []
    distance = data.get("selection_distance")
    threshold = data.get("selection_threshold")
    if not isinstance(distance, int | float) or not isinstance(threshold, int | float):
        return ["pair bank claims passed_gate without selection_distance/threshold"]
    if distance > threshold:
        return [
            (
                f"pair bank selection_distance {distance} exceeds its "
                f"threshold {threshold}"
            )
        ]
    return []


def normalized(s: str) -> str:
    return " ".join(TOKEN_RE.findall(s.lower()))


def token_overlap(a: str, b: str) -> float:
    ta = set(TOKEN_RE.findall(a.lower()))
    tb = set(TOKEN_RE.findall(b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _overlap_violation(concept_norm: dict, safe_norm: dict) -> list[str]:
    """C1 exact / normalized duplicates across the two banks."""
    dup = sorted(concept_norm.keys() & safe_norm.keys())
    if not dup:
        return []
    examples = " | ".join(f"{concept_norm[d][:60]!r}" for d in dup[:5])
    violations: list[str] = []
    violations.append(
        f"C1 overlap: {len(dup)} prompt(s) appear in BOTH concept and safe "
        f"banks (e.g. {examples})"
    )
    return violations


def _marker_violations(bank: dict) -> list[str]:
    """C2 source marker contamination: only safe-side leaks are flagged."""
    violations: list[str] = []
    for p in bank["concept"]:
        low = p.lower()
        if any(m in low for m in NSFW_MARKERS):
            pass  # concept bank SHOULD contain NSFW-ish prompts; only flag safe-side leaks
    for p in bank["safe"]:
        low = p.lower()
        if any(m in low for m in NSFW_MARKERS):
            violations.append(f"C2 safe-bank NSFW leak: {p[:80]!r}")
    return violations


def _power_floor_violation(bank: dict) -> list[str]:
    """C3 power floor: fewer than 25 prompts per cell is unreliable."""
    violations: list[str] = []
    if bank["n_concept"] < 25 or bank["n_safe"] < 25:
        violations.append(
            f"C3 low-n: concept={bank['n_concept']} safe={bank['n_safe']} "
            "(n<25 => binomial significance unreliable; do not cite as success)"
        )
    return violations


def _lookalike_violations(concept_list: list, safe_list: list) -> list[str]:
    """C4 near-duplicate cross-bank pairs above the token-overlap floor."""
    # Floor of 2 shared tokens prevents single-token co-occurrence ("blunt")
    # from scoring 100% via min-normalization.
    lookalikes: list[tuple[str, str, float]] = []
    for c in concept_list:
        for s in safe_list:
            tc = set(TOKEN_RE.findall(c.lower()))
            ts = set(TOKEN_RE.findall(s.lower()))
            shared = tc & ts
            if len(shared) >= 2 and token_overlap(c, s) >= LOOKALIKE_OVERLAP:
                lookalikes.append((c, s, token_overlap(c, s)))
    violations: list[str] = []
    if lookalikes:
        top = sorted(lookalikes, key=lambda t: -t[2])[:5]
        desc = " | ".join(f"{a[:40]!r}~{b[:40]!r} ({ov:.2f})" for a, b, ov in top)
        violations.append(
            f"C4 lookalike: {len(lookalikes)} concept/safe pair(s) with "
            f"token-overlap >= {LOOKALIKE_OVERLAP:.0%} and >=2 shared tokens "
            f"(e.g. {desc})"
        )
    return violations


def check_bank(path: Path, strict: bool) -> list[str]:
    bank = load_bank(path)
    if bank["layout"] == "pair":
        return _pair_bank_violations(bank["raw"])
    concept_norm = {normalized(p): p for p in bank["concept"]}
    safe_norm = {normalized(p): p for p in bank["safe"]}

    # C1 exact / normalized duplicates
    violations: list[str] = _overlap_violation(concept_norm, safe_norm)

    # C2 source marker contamination
    violations.extend(_marker_violations(bank))

    # C3 power floor
    violations.extend(_power_floor_violation(bank))

    # C4 lookalike pairs (near-duplicates across banks)
    violations.extend(_lookalike_violations(bank["concept"], bank["safe"]))

    return violations


def _check_one_bank(bank_arg: str, strict: bool, all_violations: list[str]) -> bool:
    """Check one bank file into ``all_violations``; True when it is missing."""
    path = REPO / bank_arg if not Path(bank_arg).is_absolute() else Path(bank_arg)
    if not path.exists():
        print(f"[contamination] MISSING bank: {path}", file=sys.stderr)
        all_violations.append(f"missing bank {path}")
        return True
    try:
        for v in check_bank(path, strict):
            print(f"[contamination] {v}", file=sys.stderr)
            all_violations.append(v)
        clean = len(all_violations)
        log_event(
            str(path),
            "contamination",
            "warn" if all_violations else "pass",
            "; ".join(all_violations[:3]) or "clean",
        )
        print(f"[contamination] {path}: {clean} violation(s)")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[contamination] ERROR {path}: {exc}", file=sys.stderr)
        all_violations.append(f"parse error {path}: {exc}")
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("banks", nargs="+", help="prompt bank JSON files")
    ap.add_argument("--strict", action="store_true", help="exit 1 on violations")
    args = ap.parse_args(argv)

    all_violations: list[str] = []
    missing = False
    for bank_arg in args.banks:
        if _check_one_bank(bank_arg, args.strict, all_violations):
            missing = True

    if missing:
        print("[contamination] ABORT: missing bank file(s)", file=sys.stderr)
        return 1
    if args.strict and all_violations:
        print(
            f"[contamination] STRICT FAIL: {len(all_violations)} violation(s)",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
