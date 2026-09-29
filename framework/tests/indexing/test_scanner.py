"""Unit tests for framework.indexing.scanner."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from framework.indexing.scanner import scan_file, scan_module_text


def test_scan_module_text_functions_and_classes() -> None:
    """Verify function signatures, class bases, and doc summaries are extracted."""
    code = (
        '"""Module docstring describing component."""\n\n'
        "class CarrierBank(BaseBank):\n"
        '    """Manages carrier matrices."""\n'
        "    def project(self, x: torch.Tensor, r: int = 12) -> torch.Tensor:\n"
        '        """Project tensor into carrier subspace."""\n'
        "        return x\n\n"
        "def compute_angles(a: torch.Tensor, b: torch.Tensor) -> float:\n"
        '    """Compute principal Grassmann angles between subspaces."""\n'
        "    return 0.5\n"
    )
    entry = scan_module_text("research/core/sample.py", code)
    assert entry is not None
    assert entry.rel_path == "research/core/sample.py"
    assert entry.doc_summary == "Module docstring describing component."
    assert len(entry.classes) == 1
    cls_entry = entry.classes[0]
    assert cls_entry.name == "CarrierBank"
    assert cls_entry.bases == ("BaseBank",)
    assert len(cls_entry.methods) == 1
    assert cls_entry.methods[0].name == "project"
    assert "x: torch.Tensor" in cls_entry.methods[0].args_repr
    assert cls_entry.methods[0].return_type == "torch.Tensor"
    assert len(entry.functions) == 1
    fn_entry = entry.functions[0]
    assert fn_entry.name == "compute_angles"
    assert "b: torch.Tensor" in fn_entry.args_repr
    assert "Grassmann angles" in fn_entry.doc_summary


def test_scan_module_text_async_and_kwonly() -> None:
    """Verify async functions, varargs, and kwonlyargs are formatted."""
    code = (
        "async def async_fetch(*args: str, timeout: float = 5.0, **kwargs) -> bool:\n"
        '    """Fetch data asynchronously.\n\nExtra details paragraph."""\n'
        "    return True\n"
    )
    entry = scan_module_text("research/runtime/net.py", code)
    assert entry is not None
    assert len(entry.functions) == 1
    fn = entry.functions[0]
    assert fn.is_async is True
    assert fn.name == "async_fetch"
    assert "*args" in fn.args_repr
    assert "timeout: float" in fn.args_repr
    assert "**kwargs" in fn.args_repr
    assert fn.return_type == "bool"
    assert fn.doc_summary == "Fetch data asynchronously."


def test_scan_module_syntax_error() -> None:
    """Verify unparseable syntax returns None instead of failing."""
    entry = scan_module_text("broken.py", "def broken(:::")
    assert entry is None


def test_scan_file_reads_source(tmp_path: Path) -> None:
    """Verify scan_file reads on-disk files relative to repo root."""
    fpath = tmp_path / "sub" / "algo.py"
    fpath.parent.mkdir(parents=True)
    fpath.write_text("def solve() -> int:\n    return 42\n")
    entry = scan_file(fpath, tmp_path)
    assert entry is not None
    assert entry.rel_path == "sub/algo.py"
    assert len(entry.functions) == 1
    assert entry.functions[0].name == "solve"


def test_two_tier_docstring_extraction() -> None:
    """Verify two-tier docstring parsing extracts thumbnail and structured sections."""
    code = (
        '"""Thumbnail for the optimization runner.\n\n'
        "Role & Architecture:\n"
        "    Orchestrates gradient descent.\n\n"
        "Invariants & Expected State:\n"
        "    - Tensors must be on CUDA device.\n"
        "    - Weights must not be None.\n\n"
        "Failure Modes & Prohibited Patterns:\n"
        "    - Raises ValueError on shape mismatch.\n"
        '"""\n\n'
        "def run() -> None:\n"
        "    pass\n"
    )
    entry = scan_module_text("research/runner.py", code)
    assert entry is not None
    assert entry.doc_summary == "Thumbnail for the optimization runner."
    assert entry.has_invariants is True
    assert len(entry.contract_errors) == 0
    sec_dict = dict(entry.doc_sections)
    assert "Invariants & Expected State" in sec_dict
    assert "Role & Architecture" in sec_dict


def test_two_tier_docstring_validation_errors() -> None:
    """Verify validation errors are recorded for missing or invalid docstrings."""
    no_doc = scan_module_text("research/empty.py", "x = 1\n")
    assert no_doc is not None
    assert any("missing" in err.lower() for err in no_doc.contract_errors)

    missing_inv = scan_module_text(
        "research/no_inv.py", '"""Only a summary line."""\nx = 1\n'
    )
    assert missing_inv is not None
    assert missing_inv.has_invariants is False
    assert any("invariant" in err.lower() for err in missing_inv.contract_errors)

    long_thumb = '"""' + ("a" * 150) + '\n\nInvariants:\n    - test\n"""\n'
    long_entry = scan_module_text("research/long.py", long_thumb)
    assert long_entry is not None
    assert any("140" in err for err in long_entry.contract_errors)
