"""Benchmark evaluation dataset for the advisory hot-path gate.

Thumbnail: 35 labeled positive, negative, and known-miss snippets for HNS089-HNS094.

Invariants & Expected State:
    Every positive is a locally provable hot-path shape: a host factory followed
    by a device move, a loop conversion, a step-function synchronization, an
    always-on anomaly check, per-element tensor indexing, or an untuned loader.
    Every negative keeps the shape outside the rule's premise (device keyword,
    payload-named function, config cast, slice/advanced index, tuned loader).
    Known misses catalogue the two interprocedural gaps: a sync inside a helper
    called from a step, and a tensor built by a helper.
"""

from __future__ import annotations

from framework.tests.transfers.dataset_fixture import TransferBenchmarkCase

CASES: tuple[TransferBenchmarkCase, ...] = (
    TransferBenchmarkCase(
        "hns089_factory_to_device",
        "def f(device):\n    return torch.zeros(3).to(device)",
        ("HNS089",),
        "hns089",
    ),
    TransferBenchmarkCase(
        "hns089_factory_cuda",
        "def f():\n    return torch.ones(3).cuda()",
        ("HNS089",),
        "hns089",
    ),
    TransferBenchmarkCase(
        "hns089_as_tensor_to_device",
        "def f(device):\n    return torch.as_tensor([1.0]).to(device)",
        ("HNS089",),
        "hns089",
    ),
    TransferBenchmarkCase(
        "clean_factory_device_kwarg",
        "def f(device):\n    return torch.zeros(3, device=device)",
        (),
        "hns089",
    ),
    TransferBenchmarkCase(
        "clean_factory_dtype_only_move",
        "def f():\n    return torch.zeros(3).to(torch.float32)",
        (),
        "hns089",
    ),
    TransferBenchmarkCase(
        "clean_receiver_move",
        "def f(x, device):\n    return x.to(device)",
        (),
        "hns089",
    ),
    TransferBenchmarkCase(
        "hns090_numpy_in_for",
        "def f(t):\n"
        "    out = []\n"
        "    for _ in range(2):\n"
        "        out.append(t.numpy())\n"
        "    return out",
        ("HNS090",),
        "hns090",
    ),
    TransferBenchmarkCase(
        "hns090_numpy_in_comprehension",
        "def f(t):\n    return [t.numpy() for _ in range(2)]",
        ("HNS090",),
        "hns090",
    ),
    TransferBenchmarkCase(
        "clean_numpy_outside_loop",
        "def f(t):\n    return t.numpy()",
        (),
        "hns090",
    ),
    TransferBenchmarkCase(
        "clean_numpy_in_payload",
        "def _save_bytes(t):\n"
        "    out = []\n"
        "    for _ in range(2):\n"
        "        out.append(t.numpy().tobytes())\n"
        "    return out",
        (),
        "hns090",
    ),
    TransferBenchmarkCase(
        "hns091_float_detach_after_backward",
        "def step(loss, opt):\n"
        "    loss.backward()\n"
        "    opt.step()\n"
        "    return float(loss.detach())",
        ("HNS091",),
        "hns091",
    ),
    TransferBenchmarkCase(
        "hns091_clip_grad_norm_cast",
        "def step(params, opt):\n"
        "    opt.step()\n"
        "    return float(clip_grad_norm_(params, 1.0))",
        ("HNS091",),
        "hns091",
    ),
    TransferBenchmarkCase(
        "hns091_item_after_step",
        "def step(loss, opt):\n"
        "    loss.backward()\n"
        "    opt.step()\n"
        "    return loss.item()",
        ("HNS091",),
        "hns091",
    ),
    TransferBenchmarkCase(
        "clean_cast_config_in_step",
        "def step(loss, opt, cfg):\n"
        "    loss.backward()\n"
        "    opt.step()\n"
        "    return float(cfg.clip)",
        (),
        "hns091",
    ),
    TransferBenchmarkCase(
        "clean_cast_outside_step",
        "def f(loss):\n    return float(loss.detach())",
        (),
        "hns091",
    ),
    TransferBenchmarkCase(
        "clean_item_in_loop_in_step",
        "def step(loss, opt):\n"
        "    loss.backward()\n"
        "    opt.step()\n"
        "    for _ in range(2):\n"
        "        print(loss.item())",
        (),
        "hns091",
    ),
    TransferBenchmarkCase(
        "hns091_helper_sync",
        "def _report(loss):\n"
        "    return loss.item()\n"
        "def step(loss, opt):\n"
        "    loss.backward()\n"
        "    opt.step()\n"
        "    return _report(loss)",
        ("HNS091",),
        "hns091",
        known_miss=True,
    ),
    TransferBenchmarkCase(
        "hns092_anomaly_true",
        "def f():\n    torch.autograd.set_detect_anomaly(True)",
        ("HNS092",),
        "hns092",
    ),
    TransferBenchmarkCase(
        "hns092_anomaly_check_nan",
        "def f():\n    torch.autograd.set_detect_anomaly(True, check_nan=False)",
        ("HNS092",),
        "hns092",
    ),
    TransferBenchmarkCase(
        "clean_anomaly_false",
        "def f():\n    torch.autograd.set_detect_anomaly(False)",
        (),
        "hns092",
    ),
    TransferBenchmarkCase(
        "clean_anomaly_variable",
        "def f(flag):\n    torch.autograd.set_detect_anomaly(flag)",
        (),
        "hns092",
    ),
    TransferBenchmarkCase(
        "hns093_store_in_loop",
        "def f(device, n):\n"
        "    x = torch.zeros(4, device=device)\n"
        "    for i in range(n):\n"
        "        x[i] = 1.0\n"
        "    return x",
        ("HNS093",),
        "hns093",
    ),
    TransferBenchmarkCase(
        "hns093_annotated_param_load",
        "def f(x: torch.Tensor, n):\n"
        "    total = torch.zeros(1)\n"
        "    for i in range(n):\n"
        "        total += x[i]\n"
        "    return total",
        ("HNS093",),
        "hns093",
    ),
    TransferBenchmarkCase(
        "hns093_comprehension",
        "def f(x: torch.Tensor, n):\n    return [x[i] for i in range(n)]",
        ("HNS093",),
        "hns093",
    ),
    TransferBenchmarkCase(
        "hns093_factory_alias",
        "def f(device, n):\n"
        "    alphas = torch.zeros(4, device=device)\n"
        "    for i in range(n):\n"
        "        alphas[i] = alphas[i] + 1.0\n"
        "    return alphas",
        ("HNS093",),
        "hns093",
    ),
    TransferBenchmarkCase(
        "clean_slice_in_loop",
        "def f(device, n):\n"
        "    x = torch.zeros(4, device=device)\n"
        "    for i in range(n):\n"
        "        x[i, :] = 1.0\n"
        "    return x",
        (),
        "hns093",
    ),
    TransferBenchmarkCase(
        "clean_advanced_index",
        "def f(device, n):\n"
        "    x = torch.zeros(4, device=device)\n"
        "    for _ in range(n):\n"
        "        x[torch.randperm(4)] = 1.0\n"
        "    return x",
        (),
        "hns093",
    ),
    TransferBenchmarkCase(
        "clean_unknown_parameter",
        "def f(x, n):\n    for i in range(n):\n        x[i] = 1.0",
        (),
        "hns093",
    ),
    TransferBenchmarkCase(
        "clean_constant_index",
        "def f(device, n):\n"
        "    x = torch.zeros(4, device=device)\n"
        "    for _ in range(n):\n"
        "        x[0] = 1.0\n"
        "    return x",
        (),
        "hns093",
    ),
    TransferBenchmarkCase(
        "hns093_helper_tensor",
        "def make_tensor():\n"
        "    return torch.zeros(4)\n"
        "def f(n):\n"
        "    x = make_tensor()\n"
        "    for i in range(n):\n"
        "        x[i] = 1.0\n"
        "    return x",
        ("HNS093",),
        "hns093",
        known_miss=True,
    ),
    TransferBenchmarkCase(
        "hns094_loader_defaults",
        "def f(ds):\n    return DataLoader(ds, batch_size=4)",
        ("HNS094",),
        "hns094",
    ),
    TransferBenchmarkCase(
        "hns094_loader_zero_workers",
        "def f(ds):\n    return DataLoader(ds, num_workers=0, pin_memory=True)",
        ("HNS094",),
        "hns094",
    ),
    TransferBenchmarkCase(
        "clean_loader_tuned",
        "def f(ds):\n    return DataLoader(ds, num_workers=4, pin_memory=True)",
        (),
        "hns094",
    ),
    TransferBenchmarkCase(
        "clean_loader_unknown_settings",
        "def f(ds, workers, pinned):\n"
        "    return DataLoader(ds, num_workers=workers, pin_memory=pinned)",
        (),
        "hns094",
    ),
    TransferBenchmarkCase(
        "clean_pinned_tensor_math",
        "def f(x, y, device):\n    return x.to(device) + y.to(device)",
        (),
        "hns089",
    ),
)
