"""Unit tests for the device transfer bottleneck static analysis gate.

Thumbnail: Verifies detection of HNS056, HNS057, HNS058, and HNS059 transfer rules and CLI mechanics.

Invariants & Expected State:
    Flags transfer bottleneck patterns with exact line numbers and codes.
    Motivating historical defects from joint_statistics and hooks are caught.
    Documented clean patterns (device residency, deferred sync) pass cleanly.
    CLI runs fail closed on unreadable files and obey --strict and --report flags.
    Every test function spans at most 30 lines and runs on CPU.
"""

from __future__ import annotations

import json
from pathlib import Path

from framework.gates.transfers.check_device_transfers import main as cli_main
from framework.gates.transfers.visitor import analyze_transfers


def test_trigger_state_distinguishes_evidence_source() -> None:
    """Loop, aggregate and name-triggered evidence are three separate states."""
    aggregate = analyze_transfers(
        "def f(batch, device):\n    return torch.cat([x.to(device) for x in batch])\n",
        "probe.py",
    )
    name_only = analyze_transfers(
        "def _capture_probe(t):\n    return t.item()\n", "probe.py"
    )
    repeated = analyze_transfers(
        "def f(items):\n    for item in items:\n        x = item.item()\n", "probe.py"
    )
    repeated_join = analyze_transfers(
        "def f(batches, device):\n    for b in batches:\n        y = torch.cat([x.to(device) for x in b])\n",
        "probe.py",
    )
    assert [f.trigger for f in aggregate] == ["aggregate"]
    assert [f.trigger for f in name_only] == ["streaming"]
    assert [f.trigger for f in repeated] == ["loop"]
    assert [f.trigger for f in repeated_join] == ["loop"]


def test_hns056_flags_in_loop_cpu_transfer() -> None:
    """Flag GPU-to-CPU tensor transfer inside a for-loop body."""
    snippet = """
def process_batches(loader, model):
    results = []
    for batch in loader:
        out = model(batch)
        results.append(out.cpu().numpy())
    return results
"""
    findings = analyze_transfers(snippet, "research/eval.py")
    assert any(f.code == "HNS056" for f in findings)


def test_hns056_flags_streaming_accumulator_cpu_transfer() -> None:
    """Flag CPU transfer inside streaming accumulation method."""
    snippet = """
def _accumulate_pair_moment(error, c_design, moments, name):
    err_cpu = error.transpose(1, 2).detach().to(device="cpu", dtype=torch.float64)
    c_cpu = c_design.detach().to(device="cpu", dtype=torch.float64)
    moments[name] = torch.bmm(err_cpu, c_cpu)
"""
    findings = analyze_transfers(snippet, "research/joint_statistics.py")
    assert any(f.code == "HNS056" for f in findings)


def test_hns056_passes_on_outside_loop_transfer() -> None:
    """Pass on CPU transfer occurring outside of loops for checkpoint export."""
    snippet = """
def export_checkpoint(weights):
    cpu_state = weights.detach().cpu()
    torch.save(cpu_state, "checkpoint.pt")
"""
    findings = analyze_transfers(snippet, "research/checkpoint.py")
    assert not any(f.code == "HNS056" for f in findings)


def test_hns057_flags_in_loop_item_sync() -> None:
    """Flag .item() synchronization inside a loop."""
    snippet = """
def check_norms(modules):
    for m in modules:
        norm = torch.linalg.norm(m.weight).item()
        if norm > 1.0:
            print(norm)
"""
    findings = analyze_transfers(snippet, "research/norm.py")
    assert any(f.code == "HNS057" for f in findings)


def test_hns057_passes_on_deferred_reduction() -> None:
    """Pass on deferred device-side boolean reduction without .item() in hook."""
    snippet = """
def record_finite_check(self, design):
    flag = torch.isfinite(design).all()
    self._finite_flag = flag if self._finite_flag is None else self._finite_flag & flag
"""
    findings = analyze_transfers(snippet, "research/hooks.py")
    assert not any(f.code == "HNS057" for f in findings)


def test_hns058_flags_in_loop_device_transfer() -> None:
    """Flag redundant .to(device) transfer inside an inner loop."""
    snippet = """
def apply_steps(steps, base, delta, device):
    for step in steps:
        curr = base.to(device) + delta
"""
    findings = analyze_transfers(snippet, "research/steps.py")
    assert any(f.code == "HNS058" for f in findings)


def test_hns058_passes_on_pre_pinned_table() -> None:
    """Pass on device pinning done once outside the iteration loop."""
    snippet = """
def setup_and_run(steps, base, delta, device):
    base_dev = base.to(device)
    for step in steps:
        curr = base_dev + delta
"""
    findings = analyze_transfers(snippet, "research/steps.py")
    assert not any(f.code == "HNS058" for f in findings)


def test_hns059_flags_in_loop_cuda_sync() -> None:
    """Flag torch.cuda.synchronize() or empty_cache() inside an inner loop."""
    snippet = """
def run_eval(batches, model):
    for b in batches:
        model(b)
        torch.cuda.synchronize()
"""
    findings = analyze_transfers(snippet, "research/eval.py")
    assert any(f.code == "HNS059" for f in findings)


def test_hns059_passes_on_outside_loop_sync() -> None:
    """Pass on synchronization surrounding an entire timed phase."""
    snippet = """
def measure_phase(device):
    torch.cuda.synchronize(device)
    yield
    torch.cuda.synchronize(device)
"""
    findings = analyze_transfers(snippet, "research/timing.py")
    assert not any(f.code == "HNS059" for f in findings)


def test_hns056_flags_comprehension_cpu_transfer() -> None:
    """Flag GPU-to-CPU transfer inside list comprehension."""
    snippet = "outputs = [x.cpu() for x in batch]"
    findings = analyze_transfers(snippet, "research/eval.py")
    assert any(f.code == "HNS056" for f in findings)


def test_hns056_flags_torch_device_cpu() -> None:
    """Flag to(torch.device('cpu')) transfer inside loop."""
    snippet = """
for x in items:
    out = x.to(torch.device("cpu"))
"""
    findings = analyze_transfers(snippet, "research/eval.py")
    assert any(f.code == "HNS056" for f in findings)


def test_hns057_flags_generator_item_sync() -> None:
    """Flag .item() synchronization inside generator expression."""
    snippet = "total = sum(x.item() for x in losses)"
    findings = analyze_transfers(snippet, "research/loss.py")
    assert any(f.code == "HNS057" for f in findings)


def test_hns057_flags_forward_hook_sync() -> None:
    """Flag .item() synchronization inside a forward hook."""
    snippet = """
def seam_forward_hook(module, args, output):
    mean = output.mean().item()
"""
    findings = analyze_transfers(snippet, "research/hook.py")
    assert any(f.code == "HNS057" for f in findings)


def test_hns058_passes_on_pure_dtype_cast() -> None:
    """Pass on in-loop pure dtype downcast without device movement."""
    snippet = """
for delta in deltas:
    casted = delta.to(torch.float32)
    half_cast = delta.to(dtype=torch.bfloat16)
"""
    findings = analyze_transfers(snippet, "research/cast.py")
    assert not any(f.code == "HNS058" for f in findings)


def test_cli_clean_file_exits_zero(tmp_path: Path) -> None:
    """CLI exits with 0 on clean scoped sources under --strict."""
    clean = tmp_path / "clean.py"
    clean.write_text("x = 1 + 2\n", encoding="utf-8")
    rc = cli_main(["--strict", str(clean)])
    assert rc == 0


def test_cli_dirty_file_exits_one_and_writes_report(tmp_path: Path) -> None:
    """CLI exits with 1 on dirty sources under --strict and outputs json report."""
    dirty = tmp_path / "dirty.py"
    dirty.write_text("for i in range(10):\n    x = i.item()\n", encoding="utf-8")
    report = tmp_path / "report.json"
    rc = cli_main(["--strict", "--report", str(report), str(dirty)])
    assert rc == 1
    assert report.is_file()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert len(payload) >= 1
    assert payload[0]["code"] == "HNS057"


def test_cli_unreadable_staged_blob_fails_closed() -> None:
    """CLI emits HNS010 and exits with 1 when staged file cannot be read."""
    rc = cli_main(["--strict", "--staged", "research/nonexistent_blob_xyz.py"])
    assert rc == 1


def test_cli_skips_paths_outside_the_gate_population() -> None:
    """A named repository test module is outside the population, a temp path is not.

    The hook hands the gate explicit staged paths, so the population filter has
    to run on explicit names too - otherwise the fixture modules that embed the
    dataset's snippets would be scanned as if they were production sources.
    """
    assert (
        cli_main(
            ["--strict", "--staged", "framework/tests/transfers/dataset_fixture.py"]
        )
        == 0
    )


def test_hns057_exempts_host_constructed_tensor_factories() -> None:
    """A .tolist() on a tensor the same function built on the host moves nothing."""
    snippets = (
        "def f(n):\n    for i in range(3):\n        x = torch.randperm(n).tolist()\n",
        "def f(indices):\n    for i in range(3):\n        x = torch.tensor(indices, dtype=torch.long).tolist()\n",
        "def f(a, b):\n    for i in range(3):\n        x = torch.linspace(a, b, 8).long().tolist()\n",
        (
            "def resample(indices):\n    out = []\n    for _ in range(10):\n"
            "        pool = torch.tensor(indices, dtype=torch.long)\n"
            "        drawn = pool[torch.randint(len(indices), (len(indices),))]\n"
            "        out.append(drawn[torch.randperm(len(indices))].tolist())\n"
            "    return out\n"
        ),
    )
    for snippet in snippets:
        assert analyze_transfers(snippet, "probe.py") == [], snippet


def test_hns057_still_flags_device_and_untyped_tensors() -> None:
    """An explicit device placement or an opaque receiver keeps the sync."""
    snippets = (
        "def f(indices):\n    for i in range(3):\n        x = torch.tensor(indices, device='cuda').tolist()\n",
        "def f(indices, device):\n    for i in range(3):\n        x = torch.tensor(indices, device=device).tolist()\n",
        "def f(t):\n    for i in range(3):\n        x = t.tolist()\n",
        "def f(loss):\n    for i in range(3):\n        x = loss.item()\n",
        "def f(w):\n    for i in range(3):\n        x = torch.linalg.matrix_norm(w).item()\n",
    )
    for snippet in snippets:
        codes = [f.code for f in analyze_transfers(snippet, "probe.py")]
        assert "HNS057" in codes, snippet


_REBIND_SNIPPETS = (
    (
        "def f(indices, model):\n    for _ in range(3):\n"
        "        pool = torch.tensor(indices, dtype=torch.long)\n"
        "        pool = model(pool)\n"
        "        x = pool.tolist()\n"
    ),
    (
        "def f(indices, device):\n    for _ in range(3):\n"
        "        pool = torch.tensor(indices)\n"
        "        pool = pool.to(device)\n"
        "        x = pool.tolist()\n"
    ),
    (
        "def f(indices, device):\n    for _ in range(3):\n"
        "        x = torch.tensor(indices).to(device).tolist()\n"
    ),
    (
        "def f(indices):\n    for _ in range(3):\n"
        "        x = torch.tensor(indices).cuda().tolist()\n"
    ),
)


def test_hns057_survives_device_rebinding_and_to_chains() -> None:
    """A moved host local, or a chain that moves, stays flagged."""
    for snippet in _REBIND_SNIPPETS:
        codes = [f.code for f in analyze_transfers(snippet, "probe.py")]
        assert "HNS057" in codes, snippet


def test_hns057_flags_alias_constructors_that_keep_the_input_device() -> None:
    """``as_tensor``/``asarray`` hand back a tensor argument, device included."""
    snippets = (
        "def f(w):\n    for step in range(3):\n        x = torch.as_tensor(w).tolist()\n",
        "def f(w):\n    for step in range(3):\n        x = torch.asarray(w).tolist()\n",
    )
    for snippet in snippets:
        codes = [f.code for f in analyze_transfers(snippet, "probe.py")]
        assert "HNS057" in codes, snippet


def test_hns057_exempts_numpy_pixel_reduction_methods() -> None:
    """Numpy pixel reductions do not touch the stream and are exempt."""
    snippet = (
        "def _pixel_stats(pixels):\n"
        "    return {\n"
        "        name: {\n"
        "            'min': float(px.min()),\n"
        "            'max': float(px.max()),\n"
        "            'mean': float(px.mean()),\n"
        "        }\n"
        "        for name, px in pixels.items()\n"
        "    }\n"
    )
    findings = analyze_transfers(snippet, "probe.py")
    assert not [f for f in findings if f.code == "HNS057"], snippet


def test_hns057_tracks_host_torch_load_placement() -> None:
    """torch.load with map_location='cpu' binds host tensors and stays clean."""
    clean = (
        "def delta_norms(path):\n"
        "    deltas = torch.load(path, map_location='cpu')\n"
        "    return {name: float(delta.float().norm()) for name, delta in deltas.items()}\n"
    )
    flagged = (
        "def delta_norms(path):\n"
        "    deltas = torch.load(path)\n"
        "    return {name: float(delta.float().norm()) for name, delta in deltas.items()}\n"
    )
    assert not analyze_transfers(clean, "probe.py")
    assert any(f.code == "HNS057" for f in analyze_transfers(flagged, "probe.py"))


def test_hns057_flags_detached_loss_synchronization() -> None:
    """In-loop float(loss.detach()) stalls the CUDA stream and is flagged."""
    snippet = (
        "def step(chunks):\n"
        "    total = 0.0\n"
        "    for chunk in chunks:\n"
        "        total += float(loss.detach())\n"
        "    return total\n"
    )
    findings = analyze_transfers(snippet, "probe.py")
    assert any(f.code == "HNS057" for f in findings), snippet


def test_hns058_flags_in_loop_as_tensor_device_conversion() -> None:
    """In-loop torch.as_tensor with device argument causes redundant PCIe transfers."""
    snippet = (
        "def convert(covs, device):\n"
        "    for c in covs:\n"
        "        x = torch.as_tensor(c, device=device)\n"
    )
    findings = analyze_transfers(snippet, "probe.py")
    assert any(f.code == "HNS058" for f in findings), snippet


def test_hns057_exempts_test_assertions() -> None:
    """Test assertions verifying values via .item()/.tolist() do not flag stalls."""
    exempt = (
        "def test_fn(self, pairs):\n"
        "    for pred, target in pairs:\n"
        "        assert pred.item() == 1\n"
        "        self.assertEqual(pred.tolist(), [1])\n"
    )
    unasserted = (
        "def test_fn(pairs):\n"
        "    for pred, target in pairs:\n"
        "        x = pred.item()\n"
        "        assert x == 1\n"
    )
    assert not analyze_transfers(exempt, "probe.py")
    assert any(f.code == "HNS057" for f in analyze_transfers(unasserted, "probe.py"))
