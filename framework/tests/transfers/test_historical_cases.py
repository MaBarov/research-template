"""Historical revision pins for the device transfer gate.

Thumbnail: Replays historical patterns to show which past defects the gate can see.

Invariants & Expected State:
    The host-bound joint accumulator pattern raises HNS056 on both transfer lines.
    The pre-fix arm writer pattern raises HNS056 on its CPU round trip.
    Device-mismatch fixes (bands, ridge) are pinned as out of static reach: those
    defects carried no transfer call, so a transfer gate cannot see them.
"""

from __future__ import annotations

from framework.gates.transfers.visitor import analyze_transfers

ACCUMULATOR_SNIPPET = """
def _accumulate_pair_moment(self, error, c_design):
    err_cpu = error.transpose(1, 2).detach().to(device="cpu", dtype=torch.float64)
    c_cpu = c_design.detach().to(device="cpu", dtype=torch.float64)
    return err_cpu, c_cpu
"""

ARM_WRITER_SNIPPET = """
def solve_arms(arms, batch):
    for arm in arms:
        delta = arm.solve(batch)
        delta_cpu = delta.cpu()
        record(delta_cpu)
"""

BANDS_SNIPPET = """
def _blend_bands(bands, weights, device):
    weights = weights.to(device)
    for band in bands:
        out = band * weights
"""

RIDGE_SNIPPET = """
def _accumulate_ridge(cov, target):
    for chunk in cov:
        reg = chunk + target
"""


def _flagged_lines(source: str, path: str) -> list[tuple[str, str]]:
    """Return (code, source line) for every finding in one source text."""
    lines = source.splitlines()
    return [
        (finding.code, lines[finding.line - 1].strip())
        for finding in analyze_transfers(source, path)
    ]


def test_host_bound_accumulator_revision_is_flagged() -> None:
    """The host-bound fp64 accumulator pattern raises HNS056 twice."""
    flagged = _flagged_lines(ACCUMULATOR_SNIPPET, "research/joint_statistics.py")
    cpu_transfers = [line for code, line in flagged if code == "HNS056"]
    assert len(cpu_transfers) == 2
    assert all('to(device="cpu"' in line for line in cpu_transfers)


def test_pre_fix_arm_writer_revision_is_flagged() -> None:
    """The pre-fix arm writer raises HNS056 on its per-run CPU round trip."""
    flagged = _flagged_lines(ARM_WRITER_SNIPPET, "experiments/solve_arms.py")
    assert any(code == "HNS056" and ".cpu()" in line for code, line in flagged)


def test_sanctioned_band_pinning_revision_is_clean() -> None:
    """The band-table fix pins once per blend and raises nothing."""
    assert _flagged_lines(BANDS_SNIPPET, "research/runtime.py") == []


def test_device_mismatch_fixes_stay_out_of_static_reach() -> None:
    """Device mismatches without transfers stay invisible to transfer gate."""
    assert _flagged_lines(BANDS_SNIPPET, "research/runtime.py") == []
    assert _flagged_lines(RIDGE_SNIPPET, "research/ridge.py") == []
