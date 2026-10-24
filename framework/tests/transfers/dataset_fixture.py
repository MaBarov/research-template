"""Benchmark evaluation dataset for host-device transfer bottleneck detection.

Thumbnail: 89 curated positive, negative, and known-miss snippets for HNS056-HNS060 transfer rules.

Invariants & Expected State:
    Covers positive cases for HNS056, HNS057, HNS058, HNS059, HNS060 across loops and hooks.
    Covers negative controls (pure dtype casts, outside-loop pinning, device accumulation).
    Every snippet is self-contained valid Python AST.
    Includes explicit known_miss cases (e.g. source-taking constructors without device kwarg)
    to prevent false claims of 1.0 recall and ensure open gaps remain visible.
    File stays strictly under 600 lines.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransferBenchmarkCase:
    """Single benchmark snippet with ground-truth expected gate codes."""

    name: str
    code: str
    expected_codes: tuple[str, ...]
    category: str
    known_miss: bool = False


BENCHMARK_CASES: tuple[TransferBenchmarkCase, ...] = (
    TransferBenchmarkCase(
        "hns056_in_loop_cpu_method",
        "for x in loader:\n    arr.append(x.cpu().numpy())",
        ("HNS056",),
        "hns056",
    ),
    TransferBenchmarkCase(
        "hns056_list_comprehension_cpu",
        "res = [item.cpu() for item in batch]",
        ("HNS056",),
        "hns056",
    ),
    TransferBenchmarkCase(
        "hns056_to_cpu_positional_string",
        'for step in range(10):\n    val = tensor.to("cpu")',
        ("HNS056",),
        "hns056",
    ),
    TransferBenchmarkCase(
        "hns056_to_cpu_keyword_string",
        'while condition:\n    val = tensor.to(device="cpu")',
        ("HNS056",),
        "hns056",
    ),
    TransferBenchmarkCase(
        "hns056_to_torch_device_cpu",
        'for i in range(5):\n    val = tensor.to(torch.device("cpu"))',
        ("HNS056",),
        "hns056",
    ),
    TransferBenchmarkCase(
        "hns056_streaming_accumulator_cpu",
        'def _accumulate_pair_moment(self, err, design):\n    err_cpu = err.detach().to(device="cpu", dtype=torch.float64)\n    return err_cpu',
        ("HNS056",),
        "hns056",
    ),
    TransferBenchmarkCase(
        "hns056_streaming_consume_cpu",
        "def _consume_design(self, design):\n    d_cpu = design.cpu()\n    self.buffer.append(d_cpu)",
        ("HNS056",),
        "hns056",
    ),
    TransferBenchmarkCase(
        "hns056_generator_exp_cpu",
        "gen = (x.cpu() for x in tensors)",
        ("HNS056",),
        "hns056",
    ),
    TransferBenchmarkCase(
        "hns057_in_loop_item_call",
        "for m in modules:\n    val = m.weight.norm().item()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_comprehension_item_call",
        "norms = [m.weight.norm().item() for m in modules]",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_generator_sum_item",
        "total = sum(x.item() for x in losses)",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_in_loop_tolist_call",
        "for pred in predictions:\n    rows.extend(pred.tolist())",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_forward_hook_item",
        "def seam_forward_hook(module, args, output):\n    scalar = output.mean().item()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_streaming_capture_item",
        "def capture_event(self, design):\n    flag = torch.isfinite(design).all().item()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_step_backward_item",
        "def _step_backward(self, loss):\n    l_val = loss.item()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_in_loop_detach_item",
        "for loss in loss_history:\n    tracked.append(loss.detach().item())",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_float_cast_of_tensor_reduction",
        "def _run_rounds(probe):\n    for round_index in range(probe.rounds):\n        converged = bool(torch.isfinite(probe.delta).all())",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns058_in_loop_cuda_method",
        "for x in batches:\n    w = static_weight.cuda()",
        ("HNS058",),
        "hns058",
    ),
    TransferBenchmarkCase(
        "hns058_in_loop_to_device_var",
        "for step in range(steps):\n    t = host_table.to(device)",
        ("HNS058",),
        "hns058",
    ),
    TransferBenchmarkCase(
        "hns058_in_loop_to_device_keyword",
        "for i in range(10):\n    p = payload.to(device=target_device)",
        ("HNS058",),
        "hns058",
    ),
    TransferBenchmarkCase(
        "hns058_in_loop_to_torch_device_cuda",
        'for i in range(10):\n    res = basis.to(torch.device("cuda:0"))',
        ("HNS058",),
        "hns058",
    ),
    TransferBenchmarkCase(
        "hns058_in_loop_module_device_attr",
        "for m in modules:\n    w = basis.to(m.weight.device)",
        ("HNS058",),
        "hns058",
    ),
    TransferBenchmarkCase(
        "hns058_constant_call_receiver",
        "def f(device):\n    for _ in range(5):\n        y = torch.tensor([1]).to(device)",
        ("HNS058",),
        "hns058",
    ),
    TransferBenchmarkCase(
        "hns058_comprehension_invariant_receiver",
        "def pin_all(basis, device):\n    return [basis.to(device) for _ in range(4)]",
        ("HNS058",),
        "hns058",
    ),
    TransferBenchmarkCase(
        "hns060_concat_transfers_per_element",
        "def _paired_batch(batch, device):\n    return torch.cat([item[0].to(device) for item in batch], dim=0)",
        ("HNS060",),
        "hns060",
    ),
    TransferBenchmarkCase(
        "hns056_cpu_concat_is_not_aggregate_waste",
        "def _harvest(batches):\n    for batch in batches:\n        rows = torch.cat([item[0].cpu() for item in batch], dim=0)",
        ("HNS056",),
        "hns056",
    ),
    TransferBenchmarkCase(
        "hns059_in_loop_cuda_synchronize",
        "for batch in dataloader:\n    model(batch)\n    torch.cuda.synchronize()",
        ("HNS059",),
        "hns059",
    ),
    TransferBenchmarkCase(
        "hns059_in_loop_empty_cache",
        "for step in range(50):\n    denoise_step(step)\n    torch.cuda.empty_cache()",
        ("HNS059",),
        "hns059",
    ),
    TransferBenchmarkCase(
        "hns059_comprehension_cuda_sync",
        "[torch.cuda.synchronize() for _ in range(3)]",
        ("HNS059",),
        "hns059",
    ),
    TransferBenchmarkCase(
        "clean_pure_dtype_cast_positional",
        "for delta in deltas:\n    cast = delta.to(torch.float32)",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_pure_dtype_cast_keyword",
        "for delta in deltas:\n    cast = delta.to(dtype=torch.bfloat16)",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_device_resident_inplace_accumulation",
        "def _accumulate_pair_moment(self, err, design):\n    rows = design.double().reshape(-1, self.width)\n    self.gram.add_(rows.T @ rows)\n    self.total.add_(rows.sum(0))",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_outside_loop_device_pinning",
        "def serve_bands(w0, band_table, device):\n    pinned = band_table.to(device=device)\n    for step in range(50):\n        w = w0 + pinned[step]",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_outside_loop_phase_synchronize",
        "def timed_phase(model, batch):\n    torch.cuda.synchronize()\n    out = model(batch)\n    torch.cuda.synchronize()\n    return out",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_vectorized_reduction_outside_loop",
        "def compute_summary_loss(losses):\n    all_losses = torch.stack(losses)\n    return all_losses.mean().item()",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_deferred_boolean_hook_check",
        "def record_finite_check(self, design):\n    flag = torch.isfinite(design).all()\n    self._finite_flag = flag if self._finite_flag is None else (self._finite_flag & flag)",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_scalar_scheduler_readout",
        "def _as_timestep(value):\n    if isinstance(value, torch.Tensor):\n        return int(value.reshape(-1)[0].item())\n    return int(value)",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_serialization_export_cpu",
        'def export_state_dict(weights):\n    cpu_state = {k: v.detach().cpu() for k, v in weights.items()}\n    torch.save(cpu_state, "checkpoint.pt")',
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_loop_header_tolist",
        "def _top_aligned_tokens(top_vals, top_indices):\n    for val, idx in zip(top_vals.tolist(), top_indices.tolist()):\n        yield val, idx",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_first_iterable_evaluated_once",
        'def _row_match_fields(best, best_cosine):\n    record = {}\n    record["best_match_index"] = [int(index) for index in best.tolist()]\n    record["best_match_cosine"] = [float(value) for value in best_cosine.tolist()]\n    return record',
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_module_offload_statement",
        'def _offload_text_encoders(pipe):\n    pipe.text_encoder.to(device="cpu")\n    pipe.text_encoder_2.to(device="cpu")',
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_host_store_materialization",
        "def _lift_host_map(host_map, device):\n    return {k: v.to(device) for k, v in host_map.items()}",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_concat_without_element_transfer",
        "def _stack_batch(batch):\n    return torch.cat([item[0] for item in batch], dim=0)",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_transfer_after_concatenation",
        "def _paired_batch(batch, device):\n    return torch.cat([item[0] for item in batch], dim=0).to(device)",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_trailing_tensor_readout",
        "def _final_scale(loss):\n    return float(loss.detach().sum())",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_float_cast_of_scalar_config",
        "def _schedule(tunables, steps):\n    for step in range(steps):\n        ratio = float(tunables.clip)\n        yield step, ratio",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_payload_cache_writer",
        'def _save_round_gradient_cache(probe):\n    return {\n        "tier_C_grads": [c.detach().cpu() for c in probe.tier_C_grads],\n    }',
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "hns057_while_test_item",
        "def run_until(tensor, threshold):\n    while tensor.item() < threshold:\n        tensor = step(tensor)\n    return tensor",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns056_capture_outputs_cpu",
        "def _capture_outputs(adapter, pipe, embeds, bound):\n    outputs = {}\n    for key in bound:\n        outputs[key] = forward_probe(adapter, pipe, embeds, bound).detach().cpu()\n    return outputs",
        ("HNS056",),
        "hns056",
    ),
    TransferBenchmarkCase(
        "clean_hns057_randperm_tolist",
        "def f(n):\n    for _ in range(5):\n        x = torch.randperm(n).tolist()",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_hns057_linspace_long_tolist",
        "def f(a, b):\n    for _ in range(5):\n        x = torch.linspace(a, b, 8).long().tolist()",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_hns057_zeros_tolist",
        "def f():\n    for _ in range(5):\n        x = torch.zeros(10).tolist()",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_hns057_arange_item",
        "def f():\n    for _ in range(5):\n        x = torch.arange(1).item()",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_hns057_multistep_host_assignment",
        "def resample(indices):\n    out = []\n    for _ in range(10):\n        pool = torch.tensor(indices, dtype=torch.long)\n        drawn = pool[torch.randint(len(indices), (len(indices),))]\n        out.append(drawn[torch.randperm(len(indices))].tolist())\n    return out",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_hns057_subscript_long_chain",
        "def f():\n    for _ in range(5):\n        x = torch.linspace(0, 10, 5)[1:3].long().tolist()",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_hns057_explicit_cpu_device_kwarg",
        "def f(idx):\n    for _ in range(5):\n        x = torch.tensor(idx, device='cpu').tolist()",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_hns057_ones_view_tolist",
        "def f():\n    for _ in range(5):\n        x = torch.ones(2, 2).view(-1).tolist()",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "hns057_explicit_cuda_device_kwarg",
        "def f(idx):\n    for _ in range(5):\n        x = torch.tensor(idx, device='cuda').tolist()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_dynamic_device_kwarg",
        "def f(idx, device):\n    for _ in range(5):\n        x = torch.tensor(idx, device=device).tolist()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_host_rebound_to_device",
        "def f(idx, device):\n    for _ in range(5):\n        pool = torch.tensor(idx)\n        pool = pool.to(device)\n        x = pool.tolist()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_host_rebound_to_model",
        "def f(idx, model):\n    for _ in range(5):\n        pool = torch.tensor(idx)\n        pool = model(pool)\n        x = pool.tolist()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_host_chain_to_device",
        "def f(batches, device):\n    for idx in batches:\n        x = torch.tensor(idx).to(device).tolist()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_host_chain_cuda",
        "def f(batches):\n    for idx in batches:\n        x = torch.tensor(idx).cuda().tolist()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_alias_as_tensor",
        "def f(w):\n    for _ in range(5):\n        x = torch.as_tensor(w).tolist()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_alias_asarray",
        "def f(w):\n    for _ in range(5):\n        x = torch.asarray(w).tolist()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_and_hns058_invariant_chain",
        "def f(idx, device):\n    for _ in range(5):\n        x = torch.tensor(idx).to(device).tolist()",
        ("HNS057", "HNS058"),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns057_nested_loop_item",
        "def f(matrix):\n    for row in matrix:\n        for cell in row:\n            val = cell.item()",
        ("HNS057",),
        "hns057",
    ),
    TransferBenchmarkCase(
        "hns060_concat_cuda_per_element",
        "def f(batch):\n    return torch.cat([x.cuda() for x in batch], dim=0)",
        ("HNS060",),
        "hns060",
    ),
    TransferBenchmarkCase(
        "hns060_concat_generator_expression",
        "def f(batch, dev):\n    return torch.cat(x.to(dev) for x in batch)",
        ("HNS060",),
        "hns060",
    ),
    TransferBenchmarkCase(
        "hns060_concat_dtype_cast_per_element",
        "def f(batch):\n    return torch.cat([x.to(torch.float32) for x in batch], dim=0)",
        ("HNS060",),
        "hns060",
    ),
    TransferBenchmarkCase(
        "hns060_concat_string_device_per_element",
        'def f(batch):\n    return torch.cat([x.to("cuda") for x in batch], dim=0)',
        ("HNS060",),
        "hns060",
    ),
    TransferBenchmarkCase(
        "clean_hns060_concat_plain",
        "def f(batch):\n    return torch.cat([x for x in batch], dim=0)",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_hns060_concat_then_transfer",
        "def f(batch, dev):\n    return torch.cat([x for x in batch], dim=0).to(dev)",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_hns060_concat_then_dtype_cast",
        "def f(batch):\n    return torch.cat([x for x in batch], dim=0).to(torch.float32)",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "hns058_invariant_weight_transfer_in_loop",
        "def f(loader, model, dev):\n    for batch in loader:\n        w = model.weight.to(dev)",
        ("HNS058",),
        "hns058",
    ),
    TransferBenchmarkCase(
        "hns058_while_loop_invariant_transfer",
        "def f(cond, weight, dev):\n    while cond:\n        w = weight.to(dev)",
        ("HNS058",),
        "hns058",
    ),
    TransferBenchmarkCase(
        "clean_hns058_loop_target_streaming_transfer",
        "def f(loader, dev):\n    for i, x in enumerate(loader):\n        x = x.to(dev)",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_hns058_with_context_target_transfer",
        "def f(paths, dev):\n    for p in paths:\n        with open(p) as handle:\n            t = load(handle).to(dev)",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "hns056_in_loop_model_forward_cpu",
        "def f(data, model):\n    for x in data:\n        out = model(x).cpu()",
        ("HNS056",),
        "hns056",
    ),
    TransferBenchmarkCase(
        "clean_hns056_discarded_cpu_transfer",
        "def f(data):\n    for x in data:\n        x.to('cpu')",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_hns056_save_checkpoint_helper",
        "def _save_weights(model):\n    return {k: v.cpu() for k, v in model.state_dict().items()}",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_metadata_shape_query",
        "def f(tensors):\n    for t in tensors:\n        n = t.shape[0]",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_metadata_numel_query",
        "def f(tensors):\n    for t in tensors:\n        n = t.numel()",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_metadata_size_query",
        "def f(tensors):\n    for t in tensors:\n        s = t.size()",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_python_native_math",
        "def f():\n    for i in range(10):\n        y = float(math.sin(i))",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_numpy_scalar_cast",
        "def f(arrays):\n    for a in arrays:\n        m = float(np.mean(a))",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_list_item_cast",
        "def f(matrix):\n    for row in matrix:\n        val = float(row[0])",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "clean_hns058_rebind_in_body",
        "def f(device):\n    for _ in range(5):\n        x = torch.tensor([1])\n        x = x.to(device)",
        (),
        "negative_control",
    ),
    TransferBenchmarkCase(
        "hns057_known_miss_device_inheriting_constructor",
        "def f(cuda_t):\n    for _ in range(5):\n        t = torch.tensor(cuda_t)\n        x = t.tolist()",
        ("HNS057",),
        "hns057",
        known_miss=True,
    ),
)
