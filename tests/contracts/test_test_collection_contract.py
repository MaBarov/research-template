"""Safety contracts for the mirrored test tree."""

from __future__ import annotations

from pathlib import Path


def test_mirrored_tests_use_path_safe_import_mode() -> None:
    """Duplicate tests_ basenames must not collide during collection."""
    root = Path(__file__).resolve().parents[2]
    config = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'addopts = ["--import-mode=importlib"]' in config
