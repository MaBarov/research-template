"""Unit tests for the GPU canary gate (framework step 4e)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SRC = importlib.util.spec_from_file_location(
    "canary_gate",
    "framework/gates/provenance/canary_gate.py",
) and importlib.util.module_from_spec(
    importlib.util.spec_from_file_location(
        "canary_gate", "framework/gates/provenance/canary_gate.py"
    )
)
if SRC:
    importlib.util.spec_from_file_location(
        "canary_gate", "framework/gates/provenance/canary_gate.py"
    ).loader.exec_module(SRC)


SBATCH = """#!/bin/bash
#SBATCH --job-name=demo
#SBATCH --partition=all
#SBATCH --gres=gpu:1
#SBATCH --time=02:00:00
#SBATCH --output=/results/demo_%A.log
set -euo pipefail
VENV=.venv
echo start
$VENV/bin/python -u experiments/e1/demo.py --flag 1
echo done
"""


def _tc(name: str):
    return getattr(SRC, name)


def test_driver_wrapped_in_timeout():
    out = _tc("derive_canary")(SBATCH, name="demo", time_seconds=600)
    assert "timeout 600 $VENV/bin/python -u experiments/e1/demo.py --flag 1" in out
    assert "timeout 600" in out


def test_python_variable_driver_is_wrapped():
    source = SBATCH.replace("$VENV/bin/python", '"$PYTHON"')
    out = _tc("derive_canary")(source, name="demo", time_seconds=600)
    assert 'timeout 600 "$PYTHON" -u experiments/e1/demo.py --flag 1' in out


def test_multiline_driver_arguments_stay_inside_timeout_command():
    source = SBATCH.replace(
        "$VENV/bin/python -u experiments/e1/demo.py --flag 1",
        '$VENV/bin/python -u experiments/e1/demo.py \\\n+  --flag 1 --output "$OUT"',
    )
    out = _tc("derive_canary")(source, name="demo", time_seconds=600)
    assert "timeout 600 $VENV/bin/python -u experiments/e1/demo.py \\" in out
    assert '--flag 1 --output "$OUT" || { code=$?' in out
    assert out.count('--flag 1 --output "$OUT"') == 1


def test_directives_overridden():
    out = _tc("derive_canary")(SBATCH, name="demo", time_seconds=600)
    assert "#SBATCH --job-name=canary_demo" in out
    assert "#SBATCH --time=00:25:00" in out
    assert "demo_%A.log" in out
    assert "#SBATCH --time=02:00:00" not in out
    assert "#SBATCH --job-name=demo" not in out


def test_method_and_hook_injected_before_driver():
    out = _tc("derive_canary")(
        SBATCH,
        name="demo",
        time_seconds=600,
        method="uce",
        hook="scripts/smoke/demo_canary.sh",
    )
    assert 'export METHOD="uce"' in out
    assert 'bash "scripts/smoke/demo_canary.sh" park' in out
    assert "trap 'bash \"scripts/smoke/demo_canary.sh\" restore' EXIT" in out
    assert out.index("export METHOD") < out.index("timeout 600")


def test_no_driver_returns_empty():
    out = _tc("derive_canary")(
        "#!/bin/bash\necho no python here\n", name="demo", time_seconds=600
    )
    assert out == ""


def test_only_final_driver_is_wrapped():
    source = SBATCH.replace(
        "echo start",
        'if ! "$VENV/bin/python" -c "import bitsandbytes"; then\n  true\nfi',
    )
    out = _tc("derive_canary")(source, name="demo", time_seconds=600)
    assert 'timeout 600 if ! "$VENV/bin/python"' not in out
    assert "timeout 600 $VENV/bin/python -u experiments/e1/demo.py --flag 1" in out


def test_child_sbatch_is_bounded_when_no_direct_driver():
    source = SBATCH.replace(
        "$VENV/bin/python -u experiments/e1/demo.py --flag 1",
        'exec "$ROOT/cluster/child.sbatch"',
    )
    out = _tc("derive_canary")(source, name="demo", time_seconds=600)
    assert 'timeout 600 bash "$ROOT/cluster/child.sbatch"' in out


def test_child_bash_wrapper_is_bounded_once():
    source = SBATCH.replace(
        "$VENV/bin/python -u experiments/e1/demo.py --flag 1",
        'exec bash "$ROOT/cluster/child.sbatch"',
    )
    out = _tc("derive_canary")(source, name="demo", time_seconds=600)
    assert 'timeout 600 bash "$ROOT/cluster/child.sbatch"' in out
    assert "bash bash" not in out


def test_timeout_is_a_clean_alive_signal():
    out = _tc("derive_canary")(SBATCH, name="demo", time_seconds=600)
    assert 'if [ "$code" -eq 124 ]; then echo "status=CANARY_TIMEOUT_ALIVE"' in out
    assert 'else exit "$code"; fi; }' in out


def test_method_scopes_canary_name():
    assert _tc("_canary_name")(Path("cluster/demo.sbatch"), "esd") == "demo_esd"


def test_verdict_finished_and_alive_pass():
    ok, why = _tc("verdict_for")("COMPLETED", "0:0")
    assert ok and "finished" in why
    ok, why = _tc("verdict_for")("COMPLETED", "124:0")
    assert ok and "alive at bounded window" in why


def test_verdict_crash_fails():
    ok, why = _tc("verdict_for")("FAILED", "1:0")
    assert not ok and "crashed before the bound" in why
    ok, why = _tc("verdict_for")("OOM", "137:0")
    assert not ok
