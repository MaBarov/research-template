"""Benchmark evaluation dataset for the advisory abstract-cost gate.

Thumbnail: 33 labeled positive, negative and known-miss snippets for HNS095-HNS099.

Invariants & Expected State:
    A positive repeats work whose inputs an enclosing loop provably cannot change,
    banks per-capture tensors that another method materializes, or pays a pipeline
    pass per item.
    A negative differs in exactly the premise: a varying operand, an RNG draw, a
    payload-named consumer, an unproven name, or no enclosing loop.
    Known misses catalogue three gaps: a local list materialized inside one
    function (usually payload assembly, not a capture bank), a local alias inside a
    helper, and a pipeline reached through a variable.
"""

from __future__ import annotations

from framework.tests.transfers.dataset_fixture import TransferBenchmarkCase

CASES: tuple[TransferBenchmarkCase, ...] = (
    TransferBenchmarkCase(
        "hns095_invariant_solve_matrix",
        "def f(gram, rhs, n):\n"
        "    out = []\n"
        "    for i in range(n):\n"
        "        out.append(torch.linalg.solve(gram, rhs[i]))\n"
        "    return out",
        ("HNS095",),
        "hns095",
    ),
    TransferBenchmarkCase(
        "hns095_invariant_cholesky_method",
        "def f(gram, n):\n"
        "    for _ in range(n):\n"
        "        factor = gram.cholesky()\n"
        "    return factor",
        ("HNS095",),
        "hns095",
    ),
    TransferBenchmarkCase(
        "hns095_invariant_eigh",
        "def f(gram, n):\n"
        "    for _ in range(n):\n"
        "        values, vectors = torch.linalg.eigh(gram)\n"
        "    return values",
        ("HNS095",),
        "hns095",
    ),
    TransferBenchmarkCase(
        "hns095_helper_factorizes_invariant_argument",
        "def _solve(rhs, gram):\n"
        "    return torch.linalg.solve(gram, rhs)\n"
        "def f(gram, rhs, n):\n"
        "    for i in range(n):\n"
        "        result = _solve(rhs[i], gram)\n"
        "    return result",
        ("HNS095",),
        "hns095",
    ),
    TransferBenchmarkCase(
        "clean_factorization_of_varying_matrix",
        "def f(mats, rhs):\n"
        "    for matrix in mats:\n"
        "        result = torch.linalg.solve(matrix, rhs)\n"
        "    return result",
        (),
        "hns095",
    ),
    TransferBenchmarkCase(
        "clean_factorization_outside_loop",
        "def f(gram, rhs):\n    return torch.linalg.solve(gram, rhs)",
        (),
        "hns095",
    ),
    TransferBenchmarkCase(
        "hns096_invariant_matmul",
        "def f(weight, other, n):\n"
        "    total = 0.0\n"
        "    for _ in range(n):\n"
        "        total += torch.mm(weight, other)\n"
        "    return total",
        ("HNS096",),
        "hns096",
    ),
    TransferBenchmarkCase(
        "hns096_invariant_double_cast",
        "def f(weight, n):\n"
        "    for _ in range(n):\n"
        "        widened = weight.double()\n"
        "    return widened",
        ("HNS096",),
        "hns096",
    ),
    TransferBenchmarkCase(
        "hns096_invariant_digest_bytes",
        "def f(weight, n):\n"
        "    for _ in range(n):\n"
        "        payload = weight.contiguous().tobytes()\n"
        "    return payload",
        ("HNS096",),
        "hns096",
    ),
    TransferBenchmarkCase(
        "hns096_invariant_norm",
        "def f(gram, n):\n"
        "    for _ in range(n):\n"
        "        scale = torch.linalg.norm(gram)\n"
        "    return scale",
        ("HNS096",),
        "hns096",
    ),
    TransferBenchmarkCase(
        "clean_derivation_with_varying_operand",
        "def f(weight, other, rows):\n"
        "    for i in rows:\n"
        "        result = weight @ other[i]\n"
        "    return result",
        (),
        "hns096",
    ),
    TransferBenchmarkCase(
        "clean_derivation_draws_from_rng",
        "def f(weight, n):\n"
        "    for _ in range(n):\n"
        "        result = torch.randn(3) @ weight\n"
        "    return result",
        (),
        "hns096",
    ),
    TransferBenchmarkCase(
        "clean_derivation_outside_loop",
        "def f(weight, other):\n    return weight @ other",
        (),
        "hns096",
    ),
    TransferBenchmarkCase(
        "hns097_class_bank_materialized",
        "class Hook:\n"
        "    def __init__(self):\n"
        "        self.rows = []\n"
        "    def record(self, design):\n"
        "        self.rows.append(design)\n"
        "    def matrix(self):\n"
        "        return torch.cat(self.rows, dim=0)",
        ("HNS097",),
        "hns097",
    ),
    TransferBenchmarkCase(
        "hns097_local_bank_materialized",
        "def f(rows, n):\n"
        "    out = []\n"
        "    for i in range(n):\n"
        "        out.append(rows[i])\n"
        "    return torch.cat(out, dim=0)",
        ("HNS097",),
        "hns097",
        known_miss=True,
    ),
    TransferBenchmarkCase(
        "hns097_class_bank_stacked",
        "class Bank:\n"
        "    def __init__(self):\n"
        "        self.items = []\n"
        "    def hook(self, value):\n"
        "        self.items.append(value)\n"
        "    def stacked(self):\n"
        "        return torch.stack(self.items)",
        ("HNS097",),
        "hns097",
    ),
    TransferBenchmarkCase(
        "clean_payload_named_consumer",
        "class Bank:\n"
        "    def __init__(self):\n"
        "        self.items = []\n"
        "    def hook(self, value):\n"
        "        self.items.append(value)\n"
        "    def _dump(self):\n"
        "        return torch.cat(self.items)",
        (),
        "hns097",
    ),
    TransferBenchmarkCase(
        "clean_bank_returned_without_concatenation",
        "def f(rows, n):\n"
        "    out = []\n"
        "    for i in range(n):\n"
        "        out.append(rows[i])\n"
        "    return out",
        (),
        "hns097",
    ),
    TransferBenchmarkCase(
        "clean_append_outside_loop",
        "def f(row):\n"
        "    out = []\n"
        "    out.append(row)\n"
        "    return torch.cat(out, dim=0)",
        (),
        "hns097",
    ),
    TransferBenchmarkCase(
        "hns098_pipeline_per_prompt",
        "def f(pipe, prompts):\n"
        "    images = []\n"
        "    for prompt in prompts:\n"
        "        images.append(pipe(prompt))\n"
        "    return images",
        ("HNS098",),
        "hns098",
    ),
    TransferBenchmarkCase(
        "hns098_pipeline_in_comprehension",
        "def f(pipe, prompts):\n    return [pipe(prompt) for prompt in prompts]",
        ("HNS098",),
        "hns098",
    ),
    TransferBenchmarkCase(
        "hns098_forward_per_item",
        "def f(model, rows):\n    for row in rows:\n        model.forward(row)\n",
        ("HNS098",),
        "hns098",
    ),
    TransferBenchmarkCase(
        "clean_pipeline_outside_loop",
        "def f(pipe, prompts):\n    return pipe(prompts)",
        (),
        "hns098",
    ),
    TransferBenchmarkCase(
        "clean_non_pipeline_call_in_loop",
        "def f(rows):\n    for row in rows:\n        encode(row)\n",
        (),
        "hns098",
    ),
    TransferBenchmarkCase(
        "hns099_invariant_count_nonzero",
        "def f(gram, n):\n"
        "    for _ in range(n):\n"
        "        if not bool(torch.count_nonzero(gram)):\n"
        "            return None\n"
        "    return gram",
        ("HNS099",),
        "hns099",
    ),
    TransferBenchmarkCase(
        "hns099_invariant_maximum",
        "def f(info, n):\n"
        "    for _ in range(n):\n"
        "        code = int(info.max())\n"
        "    return code",
        ("HNS099",),
        "hns099",
    ),
    TransferBenchmarkCase(
        "hns099_helper_syncs_invariant_argument",
        "def _check(gram):\n"
        "    return bool(torch.count_nonzero(gram))\n"
        "def f(gram, n):\n"
        "    for _ in range(n):\n"
        "        ready = _check(gram)\n"
        "    return ready",
        ("HNS099",),
        "hns099",
    ),
    TransferBenchmarkCase(
        "clean_cast_of_config_attribute",
        "def f(cfg, n):\n"
        "    for _ in range(n):\n"
        "        clip = float(cfg.clip)\n"
        "    return clip",
        (),
        "hns099",
    ),
    TransferBenchmarkCase(
        "clean_cast_of_plain_name",
        "def f(index, n):\n"
        "    for _ in range(n):\n"
        "        value = int(index)\n"
        "    return value",
        (),
        "hns099",
    ),
    TransferBenchmarkCase(
        "clean_sync_of_varying_tensor",
        "def f(grams, n):\n"
        "    for i in range(n):\n"
        "        if bool(torch.count_nonzero(grams[i])):\n"
        "            return i\n"
        "    return n",
        (),
        "hns099",
    ),
    TransferBenchmarkCase(
        "clean_sync_outside_loop",
        "def f(gram):\n    return bool(torch.count_nonzero(gram))",
        (),
        "hns099",
    ),
    TransferBenchmarkCase(
        "hns095_alias_local_matrix_in_helper",
        "def _shift(factors, gram, shift):\n"
        "    matrix = gram + shift * torch.eye(4)\n"
        "    return torch.linalg.solve(matrix, factors)\n"
        "def f(factors, gram, n):\n"
        "    for _ in range(n):\n"
        "        result = _shift(factors, gram, n)\n"
        "    return result",
        ("HNS095",),
        "hns095",
        known_miss=True,
    ),
    TransferBenchmarkCase(
        "hns098_pipeline_behind_variable",
        "def f(pipe, prompts):\n"
        "    call = pipe\n"
        "    return [call(prompt) for prompt in prompts]",
        ("HNS098",),
        "hns098",
        known_miss=True,
    ),
)
