"""Historical revision pins for the accelerator memory gate.

Thumbnail: Replays historical patterns to show four false-positive sites stay silent.

Invariants & Expected State:
    The probe output capture pattern binds a helper's detached output in a loop
    yet raises nothing: a helper's output is unattributable, not a guess.
    The design-judge trainer pattern carries in-loop float loss accumulations,
    loss list appends and no-grad batch loops that all stay silent.
    The indexing gate pattern carries loop-nested findings appends and counter
    increments that stay silent because neither involves tensor operations.
    The statistics gate pattern grades paths in loops without raising findings.
    Each pinned site is asserted to contain the shapes it guards, so no pin is vacuous.
"""

from __future__ import annotations

from framework.gates.memory.visitor import analyze_memory

CAPTURE_SNIPPET = """
def _probe_output(adapter, pipe, device, bound, prompt: str) -> torch.Tensor:
    embeds = adapter.encode_prompts(pipe, [prompt], device)[prompt]
    with torch.inference_mode():
        output = forward_probe(adapter, pipe, embeds, bound)
    return output.detach().to(device="cpu", dtype=torch.float64)

def capture_targets(adapter, pipe, device, bound, pairs, safe):
    flat = tuple(pair for tier in pairs.values() for pair in tier)
    concept = tuple(
        _probe_output(adapter, pipe, device, bound, prompt) for prompt, _guide in flat
    )
    guide = tuple(
        _probe_output(adapter, pipe, device, bound, prompt) for _concept, prompt in flat
    )
    safe_targets = tuple(
        _probe_output(adapter, pipe, device, bound, prompt) for prompt in safe
    )
    return concept, guide, safe_targets
"""

FIT_SNIPPET = """
def step_chunks(chunks, model, run, opt):
    total = 0.0
    for chunk in chunks:
        loss = micro_loss(model, chunk, run)
        run.scaler.scale(loss / len(chunks)).backward()
        total += float(loss.detach())
    return total

def train_epoch(items, width, model, opt, run):
    losses: list[float] = []
    for step_idx, start in enumerate(range(0, len(items), width), 1):
        loss = step_window(model, items[start : start + width], opt, run)
        losses.append(loss)
    return losses

def eval_batches(items, model, run):
    batches: list[torch.Tensor] = []
    with torch.no_grad():
        for start in range(0, len(items), 8):
            logits, _tensors = forward_batch(model, items[start : start + 8], run)
            batches.append(logits[:, :4])
    if not batches:
        return []
    return torch.cat(batches, dim=0).cpu().tolist()
"""

INDEXING_SNIPPET = """
def check_module_contracts(modules, files):
    findings: list[str] = []
    for m in modules:
        if m.rel_path in files:
            for err in m.contract_errors:
                findings.append(f"{m.rel_path}: {err}")
    return findings

def audit_contract_coverage(modules):
    total_fns = 0
    documented_fns = 0
    for m in modules:
        for f in m.functions:
            total_fns += 1
            if f.doc_summary:
                documented_fns += 1
    return total_fns, documented_fns
"""

STATISTICS_SNIPPET = """
def _grade_paths(paths: list[str], staged: bool):
    findings = []
    for path in paths:
        source, err = load_source(path, staged)
        if err is not None:
            findings.append(err)
    return findings
"""


def test_probe_output_capture_revision_is_silent() -> None:
    """The probe loop that binds _probe_output raises nothing."""
    assert "_probe_output" in CAPTURE_SNIPPET
    assert "for " in CAPTURE_SNIPPET
    assert analyze_memory(CAPTURE_SNIPPET, "research/capture.py") == []


def test_design_judge_fit_revision_is_silent() -> None:
    """The design-judge trainer's in-loop stores and accumulations raise nothing."""
    assert ".append(" in FIT_SNIPPET or "+= " in FIT_SNIPPET
    assert analyze_memory(FIT_SNIPPET, "scripts/fit.py") == []


def test_indexing_gate_revision_is_silent() -> None:
    """The indexing gate's in-loop appends and accumulations raise nothing."""
    assert ".append(" in INDEXING_SNIPPET
    assert analyze_memory(INDEXING_SNIPPET, "framework/indexing/gate.py") == []


def test_statistics_gate_revision_is_silent() -> None:
    """The statistics gate's finite-flag loop and accumulator raise nothing."""
    assert "for " in STATISTICS_SNIPPET
    assert analyze_memory(STATISTICS_SNIPPET, "framework/gates/statistics.py") == []
