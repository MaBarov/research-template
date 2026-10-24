"""Benchmark evaluation dataset for accelerator memory bottleneck detection.

Thumbnail: 45 curated positive, negative, and known-miss snippets for HNS083-HNS086 retention rules.

Invariants & Expected State:
    Covers positive cases for HNS083, HNS084, HNS085 and HNS086 across loops and comprehensions.
    Covers negative controls (creation-op leaves, boolean queries, release wrappers,
    no-grad blocks, hoisted or non-literal allocations, escaping buffers).
    Every snippet is self-contained valid Python carrying its own function scope.
    Includes explicit known_miss cases (a helper's detached output, a helper-grown
    buffer, a helper-returned loss) so the interprocedural recall gap stays visible
    and a perfect-recall claim remains impossible.
    File stays strictly under 600 lines.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryBenchmarkCase:
    """Single benchmark snippet with ground-truth expected gate codes."""

    name: str
    code: str
    expected_codes: tuple[str, ...]
    category: str
    known_miss: bool = False


BENCHMARK_CASES: tuple[MemoryBenchmarkCase, ...] = (
    MemoryBenchmarkCase(
        "hns083_inline_transform_append",
        "def f(rows):\n    outs = []\n    for row in rows:\n        outs.append(torch.linalg.norm(row))\n    return outs\n",
        ("HNS083",),
        "hns083",
    ),
    MemoryBenchmarkCase(
        "hns083_callable_output_append",
        "def f(batches):\n    model = torch.nn.Linear(4, 4)\n    losses = []\n    for batch in batches:\n        loss = model(batch)\n        losses.append(loss)\n    return losses\n",
        ("HNS083",),
        "hns083",
    ),
    MemoryBenchmarkCase(
        "hns083_subscript_store_bmm",
        "def f(n):\n    for i in range(n):\n        buffer[i] = torch.bmm(a, b)\n",
        ("HNS083",),
        "hns083",
    ),
    MemoryBenchmarkCase(
        "hns083_insert_diagonal",
        "def f(pending, ms):\n    for m in ms:\n        pending.insert(0, torch.diagonal(m))\n",
        ("HNS083",),
        "hns083",
    ),
    MemoryBenchmarkCase(
        "hns083_set_add_mm",
        "def f(seen, n):\n    for i in range(n):\n        seen.add(torch.mm(a, b))\n",
        ("HNS083",),
        "hns083",
    ),
    MemoryBenchmarkCase(
        "hns084_cat_self_referential",
        "def f(chunks):\n    history = None\n    for chunk in chunks:\n        history = torch.cat([history, chunk], dim=0)\n    return history\n",
        ("HNS084",),
        "hns084",
    ),
    MemoryBenchmarkCase(
        "hns084_stack_self_referential",
        "def f(parts):\n    for part in parts:\n        stacked = torch.stack([stacked, part])\n",
        ("HNS084",),
        "hns084",
    ),
    MemoryBenchmarkCase(
        "hns084_cat_tuple_slice",
        "def f(chunks):\n    for chunk in chunks:\n        buf = torch.cat((buf, chunk), dim=1)\n",
        ("HNS084",),
        "hns084",
    ),
    MemoryBenchmarkCase(
        "hns084_stack_dim_keyword",
        "def f(items):\n    for item in items:\n        acc = torch.stack([acc, item], dim=0)\n",
        ("HNS084",),
        "hns084",
    ),
    MemoryBenchmarkCase(
        "hns085_mm_accumulate",
        "def f(n):\n    total = 0\n    for i in range(n):\n        total += torch.mm(a, b)\n",
        ("HNS085",),
        "hns085",
    ),
    MemoryBenchmarkCase(
        "hns085_callable_local_accumulate",
        "def f(batches):\n    model = torch.nn.Linear(4, 4)\n    running = 0\n    for batch in batches:\n        loss = model(batch)\n        running += loss\n",
        ("HNS085",),
        "hns085",
    ),
    MemoryBenchmarkCase(
        "hns085_norm_accumulate",
        "def f(rows):\n    total = 0\n    for row in rows:\n        total += torch.linalg.norm(row)\n",
        ("HNS085",),
        "hns085",
    ),
    MemoryBenchmarkCase(
        "hns085_matmul_accumulate",
        "def f(n):\n    acc = 0\n    for i in range(n):\n        acc += torch.matmul(a, b)\n",
        ("HNS085",),
        "hns085",
    ),
    MemoryBenchmarkCase(
        "hns085_bmm_accumulate",
        "def f(n):\n    res = 0\n    for i in range(n):\n        res += torch.bmm(a, b)\n",
        ("HNS085",),
        "hns085",
    ),
    MemoryBenchmarkCase(
        "hns086_literal_zeros_in_loop",
        "def f(device, n):\n    for i in range(n):\n        buf = torch.zeros((4, 4), device=device)\n",
        ("HNS086",),
        "hns086",
    ),
    MemoryBenchmarkCase(
        "hns086_comprehension_literal_empty",
        "xs = [torch.empty((2, 3)) for _ in range(3)]\n",
        ("HNS086",),
        "hns086",
    ),
    MemoryBenchmarkCase(
        "hns086_literal_ones_in_loop",
        "def f(n):\n    for i in range(n):\n        b = torch.ones(8)\n",
        ("HNS086",),
        "hns086",
    ),
    MemoryBenchmarkCase(
        "hns086_literal_full_in_loop",
        "def f(n):\n    for i in range(n):\n        b = torch.full((2, 3), 7.0)\n",
        ("HNS086",),
        "hns086",
    ),
    MemoryBenchmarkCase(
        "hns086_literal_list_shape",
        "def f(n):\n    for i in range(n):\n        b = torch.zeros([4, 4])\n",
        ("HNS086",),
        "hns086",
    ),
    MemoryBenchmarkCase(
        "neg_annotated_float_list_append",
        "def f(losses, loss):\n    losses: list[float] = []\n    for i in range(3):\n        losses.append(loss)\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_string_store_append",
        "def f(items):\n    for x in items:\n        append(err)\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_creation_op_zeros_append",
        "def f(rows, n):\n    for i in range(n):\n        rows.append(torch.zeros(n))\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_creation_op_arange_append",
        "def f(xs, k):\n    for i in range(3):\n        xs.append(torch.arange(k))\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_boolean_query_append",
        "def f(flags, x):\n    for i in range(3):\n        flags.append(torch.isfinite(x).all())\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_release_detach_cpu_append",
        "def f(records, it):\n    for i in it:\n        records.append(out.detach().cpu())\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_release_detach_accumulate",
        "def f(it, loss):\n    total = 0\n    for i in it:\n        total += loss.detach()\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_scalarize_float_detach",
        "def f(it, loss):\n    for i in it:\n        x = float(loss.detach())\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_nograd_block",
        "def f(items):\n    with torch.no_grad():\n        for x in items:\n            outs.append(torch.linalg.norm(x))\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_inference_mode_block",
        "def f(items):\n    with torch.inference_mode():\n        for x in items:\n            outs.append(torch.linalg.norm(x))\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_nograd_decorated_helper",
        "def f(items):\n    @torch.no_grad()\n    def inner():\n        for x in items:\n            outs.append(torch.linalg.norm(x))\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_out_of_loop_append",
        "def f(x, values):\n    values.append(torch.linalg.norm(x))\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_out_of_loop_zeros",
        "def f(n):\n    buf = torch.zeros((4, 4))\n    use(buf)\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_post_loop_single_cat",
        "def f(chunks):\n    parts = []\n    for c in chunks:\n        parts.append(c)\n    merged = torch.cat(parts)\n    return merged\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_fresh_cat_in_loop",
        "def f(items):\n    for x in items:\n        merged = torch.cat([a, b])\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_hoisted_zeros_before_loop",
        "def f(device, n):\n    buf = torch.zeros((4, 4), device=device)\n    for i in range(n):\n        use(buf)\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_nonliteral_shape_zeros",
        "def f(rows, cols):\n    for i in range(3):\n        buf = torch.zeros(rows, cols)\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_escaping_zeros_returned",
        "def f(n):\n    for i in range(n):\n        buf = torch.zeros(4)\n        return buf\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_zeros_like",
        "def f(x, n):\n    for i in range(n):\n        buf = torch.zeros_like(x)\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_zero_element_placeholder",
        "def f(device, n):\n    for i in range(n):\n        buf = torch.empty(0, device=device)\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_counter_increment",
        "def f(n):\n    c = 0\n    for i in range(n):\n        c += 1\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_annotated_running_float",
        "def f(batches):\n    running: float = 0.0\n    model = torch.nn.Linear(4, 4)\n    for b in batches:\n        running += model(b)\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "neg_randn_accumulate",
        "def f(n):\n    t = 0\n    for i in range(n):\n        t += torch.randn(1)\n",
        (),
        "negative",
    ),
    MemoryBenchmarkCase(
        "km_helper_detached_output",
        "def f(concepts, items):\n    for x in items:\n        output = helper(x)\n        concepts.append(output)\n",
        ("HNS083",),
        "known_miss",
        known_miss=True,
    ),
    MemoryBenchmarkCase(
        "km_helper_grown_buffer",
        "def f(chunks):\n    for chunk in chunks:\n        history = grow(history, chunk)\n",
        ("HNS084",),
        "known_miss",
        known_miss=True,
    ),
    MemoryBenchmarkCase(
        "km_helper_returned_loss",
        "def f(batches):\n    running = 0\n    for b in batches:\n        running += step_loss(b)\n",
        ("HNS085",),
        "known_miss",
        known_miss=True,
    ),
)
