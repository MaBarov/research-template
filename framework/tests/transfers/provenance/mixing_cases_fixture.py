"""Benchmark evaluation dataset for the mixed-device (HNS088) rule.

Thumbnail: 37 labeled positive, negative, and known-miss snippets for HNS088.

Invariants & Expected State:
    Every positive builds its host tensor locally (factory, .cpu(), module
    constant, local callee return or a name provably bound to one) and meets a
    device tensor in one expression, which torch refuses at run time.
    Every negative either keeps both operands on one placement, stays scalar, or
    leaves one operand UNKNOWN so the rule must stay silent.
    Known misses record the provenance the local rule cannot prove: a class
    attribute, a callee return built through a local name, and the historical
    pursuit.py expression whose tensors arrive through parameters.
"""

from __future__ import annotations

from framework.tests.transfers.dataset_fixture import TransferBenchmarkCase

CASES: tuple[TransferBenchmarkCase, ...] = (
    TransferBenchmarkCase(
        "hns088_factory_plus_to_device",
        "def f(x, device):\n    return torch.zeros(3) + x.to(device)",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_factory_times_device_constant",
        'def f(x):\n    return torch.ones(3) * x.to("cuda")',
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_cpu_result_minus_cuda",
        "def f(x, y):\n    return x.cpu() - y.cuda()",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_to_cpu_result_plus_device",
        "def f(x, y, device):\n    return x.to(device='cpu') + y.to(device)",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_module_host_constant_times_device",
        "_ONE = torch.ones(1, dtype=torch.int8)\n"
        "def f(x, device):\n    return x.to(device) * _ONE",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_module_device_constant_plus_host",
        '_SCALE = torch.ones(1, device="cuda")\n'
        "def f():\n    return torch.zeros(1) + _SCALE",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_labelled_names_mix",
        "def f(x, device):\n"
        "    host = torch.zeros(3)\n"
        "    moved = x.to(device)\n"
        "    return host + moved",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_rebound_name_withdraws_host",
        "def f(x, device):\n"
        "    pool = torch.zeros(3)\n"
        "    pool = x.to(device)\n"
        "    return torch.ones(3) + pool",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_where_mixed_branches",
        "def f(x, device):\n"
        "    return torch.where(x.to(device) > 0, torch.zeros(3), x.to(device))",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_cat_mixed_elements",
        "def f(x, device):\n    return torch.cat([torch.zeros(3), x.to(device)])",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_stack_mixed_elements",
        "def f(x, device):\n    return torch.stack([x.to(device), torch.ones(3)])",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_augassign_mixed",
        "def f(x, device):\n"
        "    host = torch.zeros(3)\n"
        "    host += x.to(device)\n"
        "    return host",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_masked_fill_host_mask",
        "def f(x, device):\n"
        "    return x.to(device).masked_fill_(torch.zeros(3).bool(), 0.0)",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_comparison_host_vs_device",
        "def f(x, device):\n    return torch.zeros(3) < x.to(device)",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_from_numpy_plus_device",
        "def f(array, device):\n"
        "    return torch.from_numpy(array) + torch.ones(1, device=device)",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_zeros_like_host_plus_device",
        "def f(device):\n"
        "    seed = torch.zeros(2)\n"
        "    return torch.zeros_like(seed) + torch.ones(2, device=device)",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_subscript_host_plus_device",
        "def f(index, device):\n"
        "    host = torch.zeros(4)\n"
        "    return host[index] - torch.ones(1, device=device)",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_sub_method_device_receiver_host_arg",
        "def f(x, device):\n    return x.to(device).sub(torch.zeros(3))",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_view_of_host_plus_device",
        "def f(x, device):\n"
        "    host = torch.zeros(3).reshape(3)\n"
        "    return host + x.to(device)",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_both_device_to",
        "def f(x, y, device):\n    return x.to(device) + y.to(device)",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_both_host_factories",
        "def f():\n    return torch.zeros(3) + torch.ones(3)",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_dtype_only_cast_on_device",
        "def f(x, y, device):\n"
        "    return x.to(device).to(torch.float32) + y.to(device)",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_dtype_keyword_on_device",
        "def f(x, y, device):\n"
        "    return x.to(device).to(dtype=torch.float32) + y.to(device)",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_dtype_only_cast_on_host",
        "def f():\n    return torch.zeros(3).to(dtype=torch.float32) + torch.ones(3)",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_scalar_multiply",
        "def f():\n    return torch.zeros(3) * 2.0",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_bare_parameters",
        "def f(left, right):\n    return left + right",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_host_with_unknown_parameter",
        "def f(other):\n    return torch.zeros(3) + other",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_both_device_cat",
        "def f(x, y, device):\n    return torch.cat([x.to(device), y.to(device)])",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_both_cpu_results",
        "def f(x, y):\n    return x.cpu() + y.cpu()",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_numpy_arithmetic",
        "def f(a, b):\n    return np.zeros(3) + np.ones(3)",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_copy_across_devices",
        "def f(host, device):\n"
        "    target = torch.ones(2, device=device)\n"
        "    target.copy_(host)\n"
        "    return target",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_host_constant_host_math",
        "_BASE = torch.ones(2)\ndef f():\n    return _BASE + torch.zeros(2)",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_mixed_returns_stay_unproven",
        "def _mixed(flag):\n"
        "    if flag:\n        return torch.zeros(2)\n"
        '    return torch.ones(2, device="cuda")\n'
        "def f(flag, x, device):\n    return _mixed(flag) + x.to(device)",
        (),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_callee_host_factory_result",
        "def _host_zero():\n    return torch.zeros(2)\n"
        "def f(x, device):\n    return _host_zero() + x.to(device)",
        ("HNS088",),
        "hns088",
    ),
    TransferBenchmarkCase(
        "hns088_historical_pursuit_expression",
        "def _align_phase(delta, value, base):\n"
        "    return delta.reshape(-1) - (value.reshape(-1) - base.reshape(-1))",
        ("HNS088",),
        "hns088",
        known_miss=True,
    ),
    TransferBenchmarkCase(
        "hns088_callee_local_host_result",
        "def _host_zero():\n"
        "    built = torch.zeros(2)\n"
        "    return built\n"
        "def f(x, device):\n    return _host_zero() + x.to(device)",
        ("HNS088",),
        "hns088",
        known_miss=True,
    ),
    TransferBenchmarkCase(
        "hns088_class_attribute_host_tensor",
        "class Holder:\n    host = torch.zeros(2)\n"
        "def f(x, device):\n    return Holder.host + x.to(device)",
        ("HNS088",),
        "hns088",
        known_miss=True,
    ),
)
