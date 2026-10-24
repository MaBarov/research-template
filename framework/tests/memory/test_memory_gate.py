"""Unit tests for the accelerator memory bottleneck static analysis gate.

Thumbnail: Unit tests for HNS083-HNS086 memory bottleneck rules and CLI entry points.

Invariants & Expected State:
    Every rule fires only in loop context: an out-of-loop store, concatenation or
    allocation stays silent.
    HNS083 and HNS085 require graph-carrying tensor evidence; creation-op leaves,
    boolean queries, scalar annotations and release wrappers are exempt.
    HNS084 fires only on self-referential growth; a post-loop single cat is exempt.
    HNS086 requires an invariant literal shape; zero-element and escaping buffers exempt.
    --strict exits 1 on findings; without it the exit status is clean.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from framework.gates.memory.check_memory_bottlenecks import main as cli_main
from framework.gates.memory.targets import REPO
from framework.gates.memory.visitor import analyze_memory

INDEXED = "framework/gates/static/sources.py"


def _codes(source: str) -> list[str]:
    """Return the sorted distinct codes the gate reports for one snippet."""
    return sorted({finding.code for finding in analyze_memory(source, "probe.py")})


def test_hns083_flags_inline_transform_append() -> None:
    """An in-loop append of an inline torch transform retains its graph."""
    snippet = (
        "def f(rows):\n"
        "    outs = []\n"
        "    for row in rows:\n"
        "        outs.append(torch.linalg.norm(row))\n"
        "    return outs\n"
    )
    assert _codes(snippet) == ["HNS083"]


def test_hns083_flags_callable_output_append() -> None:
    """A tensor produced by a locally built module call is un-detached evidence."""
    snippet = (
        "def f(batches):\n"
        "    model = torch.nn.Linear(4, 4)\n"
        "    losses = []\n"
        "    for batch in batches:\n"
        "        loss = model(batch)\n"
        "        losses.append(loss)\n"
        "    return losses\n"
    )
    assert _codes(snippet) == ["HNS083"]


def test_hns083_flags_subscript_store() -> None:
    """An in-loop mapping store of a graph-carrying tensor outlives the iteration."""
    snippet = "def f(n):\n    for i in range(n):\n        buffer[i] = torch.bmm(a, b)\n"
    assert _codes(snippet) == ["HNS083"]


def test_hns083_flags_insert_and_set_add() -> None:
    """``insert`` and ``add`` are retention methods like ``append``."""
    inserted = (
        "def f(pending, ms):\n"
        "    for m in ms:\n"
        "        pending.insert(0, torch.diagonal(m))\n"
    )
    added = (
        "def f(seen, n):\n    for i in range(n):\n        seen.add(torch.mm(a, b))\n"
    )
    assert _codes(inserted) == ["HNS083"]
    assert _codes(added) == ["HNS083"]


def test_hns084_flags_self_referential_cat() -> None:
    """A concatenation that folds its own target back in is provably growing."""
    snippet = (
        "def f(chunks):\n"
        "    history = None\n"
        "    for chunk in chunks:\n"
        "        history = torch.cat([history, chunk], dim=0)\n"
        "    return history\n"
    )
    assert _codes(snippet) == ["HNS084"]


def test_hns084_flags_self_referential_stack() -> None:
    """A stack that reads its own target grows on every iteration too."""
    snippet = "def f(parts):\n    for part in parts:\n        stacked = torch.stack([stacked, part])\n"
    assert _codes(snippet) == ["HNS084"]


def test_hns085_flags_inline_tensor_accumulation() -> None:
    """An augmented accumulation of an inline graph call compounds the graph."""
    snippet = "def f(n):\n    total = 0\n    for i in range(n):\n        total += torch.mm(a, b)\n"
    assert _codes(snippet) == ["HNS085"]


def test_hns085_flags_callable_local_accumulation() -> None:
    """Accumulating a local bound from a torch-built callable compounds the graph."""
    snippet = (
        "def f(batches):\n"
        "    model = torch.nn.Linear(4, 4)\n"
        "    running = 0\n"
        "    for batch in batches:\n"
        "        loss = model(batch)\n"
        "        running += loss\n"
    )
    assert _codes(snippet) == ["HNS085"]


def test_hns086_flags_literal_allocation_in_loop() -> None:
    """An invariant literal shape churns the allocator on every iteration."""
    snippet = (
        "def f(device, n):\n"
        "    for i in range(n):\n"
        "        buf = torch.zeros((4, 4), device=device)\n"
    )
    assert _codes(snippet) == ["HNS086"]


def test_hns086_flags_literal_allocation_in_comprehension() -> None:
    """A comprehension body repeats, so its invariant allocation is in-loop."""
    snippet = "xs = [torch.empty((2, 3)) for _ in range(3)]\n"
    assert _codes(snippet) == ["HNS086"]


def test_hns083_exempts_scalar_annotation_and_string_store() -> None:
    """A scalar annotation and a plain string store prove no tensor is retained."""
    annotated = (
        "def f(losses, loss):\n"
        "    losses: list[float] = []\n"
        "    for i in range(3):\n"
        "        losses.append(loss)\n"
    )
    stringy = "def f(items):\n    for x in items:\n        append(err)\n"
    assert analyze_memory(annotated, "probe.py") == []
    assert analyze_memory(stringy, "probe.py") == []


def test_hns083_exempts_helper_output() -> None:
    """A helper's output carries no local proof; the interprocedural gap stays silent."""
    snippet = (
        "def f(concepts, items):\n"
        "    for x in items:\n"
        "        output = helper(x)\n"
        "        concepts.append(output)\n"
    )
    assert analyze_memory(snippet, "probe.py") == []


def test_hns083_exempts_creation_ops_and_boolean_queries() -> None:
    """Creation-op leaves and boolean queries cannot retain a backward graph."""
    snippets = [
        "def f(rows, n):\n    for i in range(n):\n        rows.append(torch.zeros(n))\n",
        "def f(xs, k):\n    for i in range(3):\n        xs.append(torch.arange(k))\n",
        "def f(flags, x):\n    for i in range(3):\n        flags.append(torch.isfinite(x).all())\n",
    ]
    for snippet in snippets:
        assert analyze_memory(snippet, "probe.py") == [], snippet


def test_hns083_and_hns085_exempt_release_wrappers() -> None:
    """detach/cpu/float wrappers are the documented safe forms."""
    snippets = [
        "def f(records, it):\n    for i in it:\n        records.append(out.detach().cpu())\n",
        "def f(it, loss):\n    total = 0\n    for i in it:\n        total += loss.detach()\n",
        "def f(it, loss):\n    for i in it:\n        x = float(loss.detach())\n",
    ]
    for snippet in snippets:
        assert analyze_memory(snippet, "probe.py") == [], snippet


def test_rules_exempt_nograd_contexts() -> None:
    """No graph is built inside a no-grad block or under a no-grad decorator."""
    with_block = (
        "def f(items):\n"
        "    with torch.no_grad():\n"
        "        for x in items:\n"
        "            outs.append(torch.linalg.norm(x))\n"
    )
    inference = (
        "def f(items):\n"
        "    with torch.inference_mode():\n"
        "        for x in items:\n"
        "            outs.append(torch.linalg.norm(x))\n"
    )
    decorator = (
        "def f(items):\n"
        "    @torch.no_grad()\n"
        "    def inner():\n"
        "        for x in items:\n"
        "            outs.append(torch.linalg.norm(x))\n"
    )
    assert analyze_memory(with_block, "probe.py") == []
    assert analyze_memory(inference, "probe.py") == []
    assert analyze_memory(decorator, "probe.py") == []


def test_rules_exempt_out_of_loop_statements() -> None:
    """A store or allocation with no enclosing loop repeats nothing."""
    appended = "def f(x, values):\n    values.append(torch.linalg.norm(x))\n"
    allocated = "def f(n):\n    buf = torch.zeros((4, 4))\n    use(buf)\n"
    assert analyze_memory(appended, "probe.py") == []
    assert analyze_memory(allocated, "probe.py") == []


def test_hns084_exempts_post_loop_and_fresh_concatenation() -> None:
    """A single post-loop join and a fixed-shape join are the documented fixes."""
    post_loop = (
        "def f(chunks):\n"
        "    parts = []\n"
        "    for c in chunks:\n"
        "        parts.append(c)\n"
        "    merged = torch.cat(parts)\n"
        "    return merged\n"
    )
    fresh = "def f(items):\n    for x in items:\n        merged = torch.cat([a, b])\n"
    assert analyze_memory(post_loop, "probe.py") == []
    assert analyze_memory(fresh, "probe.py") == []


def test_hns086_exempts_hoisted_nonliteral_escaping_and_like() -> None:
    """Only an invariant literal allocation that stays inside the loop is churn."""
    snippets = [
        "def f(device, n):\n    buf = torch.zeros((4, 4), device=device)\n    for i in range(n):\n        use(buf)\n",
        "def f(rows, cols):\n    for i in range(3):\n        buf = torch.zeros(rows, cols)\n",
        "def f(n):\n    for i in range(n):\n        buf = torch.zeros(4)\n        return buf\n",
        "def f(x, n):\n    for i in range(n):\n        buf = torch.zeros_like(x)\n",
    ]
    for snippet in snippets:
        assert analyze_memory(snippet, "probe.py") == [], snippet


def test_hns086_exempts_zero_element_placeholder() -> None:
    """A literal shape requesting no storage allocates nothing to churn."""
    snippet = (
        "def f(device, n):\n"
        "    for i in range(n):\n"
        "        buf = torch.empty(0, device=device)\n"
    )
    assert analyze_memory(snippet, "probe.py") == []


def test_hns085_exempts_counters_and_scalar_proofs() -> None:
    """Integer counters, annotated floats and fresh leaves are not accumulations."""
    snippets = [
        "def f(n):\n    c = 0\n    for i in range(n):\n        c += 1\n",
        "def f(batches):\n    running: float = 0.0\n    model = torch.nn.Linear(4, 4)\n    for b in batches:\n        running += model(b)\n",
        "def f(n):\n    t = 0\n    for i in range(n):\n        t += torch.randn(1)\n",
    ]
    for snippet in snippets:
        assert analyze_memory(snippet, "probe.py") == [], snippet


def test_cli_returns_zero_on_findings_without_strict(tmp_path: Path) -> None:
    """Without --strict the CLI reports findings but exits clean."""
    dirty = tmp_path / "dirty.py"
    dirty.write_text(
        "def f(rows):\n    for row in rows:\n        outs.append(torch.linalg.norm(row))\n",
        encoding="utf-8",
    )
    assert cli_main([str(dirty)]) == 0


def test_cli_strict_returns_one_on_findings(tmp_path: Path) -> None:
    """--strict turns any finding into a failing exit code."""
    dirty = tmp_path / "dirty.py"
    dirty.write_text(
        "def f(rows):\n    for row in rows:\n        outs.append(torch.linalg.norm(row))\n",
        encoding="utf-8",
    )
    assert cli_main(["--strict", str(dirty)]) == 1


def test_cli_report_json_carries_expected_fields(tmp_path: Path) -> None:
    """The JSON report lists path, line, code, message and trigger per finding."""
    dirty = tmp_path / "dirty.py"
    dirty.write_text(
        "def f(rows):\n    for row in rows:\n        outs.append(torch.linalg.norm(row))\n",
        encoding="utf-8",
    )
    report = tmp_path / "report.json"
    rc = cli_main(["--report", str(report), str(dirty)])
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert rc == 0
    assert payload[0]["code"] == "HNS083"
    assert payload[0]["line"] == 3
    assert payload[0]["trigger"] == "loop"
    assert set(payload[0]) == {"path", "line", "code", "message", "trigger"}


def test_cli_unreadable_staged_path_fails_closed(tmp_path: Path) -> None:
    """An untracked staged path emits HNS010 and fails closed under --strict."""
    report = tmp_path / "report.json"
    rc = cli_main(
        [
            "--strict",
            "--staged",
            "--report",
            str(report),
            "research/nonexistent_blob_xyz.py",
        ]
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert rc == 1
    assert [row["code"] for row in payload] == ["HNS010"]


def test_cli_skips_paths_outside_the_gate_population() -> None:
    """A repository test module is outside the population and is never scanned."""
    assert (
        cli_main(["--strict", "--staged", "framework/tests/memory/dataset_fixture.py"])
        == 0
    )


def test_cli_staged_reads_the_git_index(tmp_path: Path, monkeypatch) -> None:
    """--staged reads the index blob, so a worktree edit cannot shift the verdict."""
    objects = tmp_path / "objects"
    objects.mkdir()
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "index"))
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(objects))
    dirty = "def f(rows):\n    for row in rows:\n        outs.append(torch.linalg.norm(row))\n"
    sha = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        input=dirty,
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-index", "--add", "--cacheinfo", f"100644,{sha},{INDEXED}"],
        cwd=REPO,
        check=True,
    )
    clean_on_disk = (REPO / INDEXED).read_text(encoding="utf-8")
    assert "outs.append" not in clean_on_disk
    report = tmp_path / "report.json"
    rc = cli_main(["--strict", "--staged", "--report", str(report), INDEXED])
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert rc == 1
    assert payload[0]["code"] == "HNS083"
    assert payload[0]["path"] == INDEXED


@pytest.mark.pinned
def test_hook_wiring_is_blocking() -> None:
    """Pre-commit step 5d11 runs the gate strict, on the index, fail-closed."""
    hook = (REPO / "framework" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    start = hook.index("BLOCKING MEMORY-BOTTLENECK GATE")
    section = hook[start : hook.index("# 5d12.", start)]
    assert "check_memory_bottlenecks.py" in section
    assert "--strict" in section
    assert "STAGED_MEMORY_FILES" in section
    assert "the memory-bottleneck gate blocked this commit" in section
    assert "exit 1" in section
