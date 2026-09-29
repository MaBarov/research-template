#!/usr/bin/env python3
"""Single registry for the project identity, path roots and interpreter the harness uses.

Invariants & Expected State:
    - This module is the only place a project-specific literal lives: the package
      slug, the env-var prefix, the gate code prefix, the source/test roots and the
      interpreter discovery. Every other harness module imports from here, so
      adopting the template for a new project is one edit
      (``scripts/setup/init_project.py`` performs it mechanically).
    - Stdlib-only and import-side-effect free, so the gates can import it under a
      bare interpreter; tool paths may be overridden by the caller through env
      vars, but no policy decision here changes with the environment.
    - ``python framework/harness.py --get KEY`` prints one value for shell hooks and
      ``--shell`` prints the hook assignments; unknown keys exit 2.

Keys: slug, env-prefix, code-prefix, python, python-floor, dvc-bin, venv,
deploy-root, source-roots, test-root, mirror-root, params-module, registry-path,
resolve-path, smoke-dir, slurm-dir, queue-clusters, default-cluster,
mirror-scope, coverage-scope, distortion-scope, index-scope, production-scope,
run-manifest-schema, run-metrics-schema, canary-receipt-schema, env-regex.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# --- project identity (rewritten by scripts/setup/init_project.py) ----------
SLUG = "research"
ENV_PREFIX = "RESEARCH"
CODE_PREFIX = "HNS"

# Minimum interpreter the harness itself runs on; every gate may use the whole
# standard library of this version. Keep it equal to ``requires-python`` in
# ``pyproject.toml``.
PYTHON_FLOOR = "3.11"

# Schema ids of the provenance artifacts (run manifest, its metrics sidecar and
# the canary receipt). The writer and every validator read them from here, so a
# renamed project cannot end up with a writer and a validator that disagree.
RUN_MANIFEST_SCHEMA = f"{SLUG}.run-manifest.v1"
RUN_METRICS_SCHEMA = f"{SLUG}.run-metrics.v1"
CANARY_RECEIPT_SCHEMA = f"{SLUG}.canary-receipt.v1"

# --- roots ------------------------------------------------------------------
SOURCE_ROOTS = (SLUG,)
TEST_ROOT = "tests"
MIRROR_ROOT = f"{TEST_ROOT}/{SLUG}"
PRODUCTION_ROOTS = (SLUG, "scripts", "slurm")
CONSUMING_ROOTS = (SLUG, "experiments", "framework", "scripts", "slurm")
INDEX_ROOTS = (SLUG, "framework", "experiments", "scripts")
LIMITS_ROOTS = (SLUG, "experiments", "framework", "scripts", "tests")
DISTORTION_ROOTS = (SLUG, "framework", "scripts", "experiments")

# --- canonical paths inside the checkout ------------------------------------
PARAMS_MODULE = f"{SLUG}.params"
REGISTRY_PATH = f"{SLUG}/params/registry.py"
REGISTRY_TEST_PATH = f"{TEST_ROOT}/{SLUG}/params/tests_registry.py"
RESOLVE_PATH = f"{SLUG}/params/resolve.py"
ENFORCE_PATHS = (*SOURCE_ROOTS, "framework", "scripts")
SMOKE_DIR = "scripts/smoke"
SLURM_DIR = "slurm"

# --- Slurm ------------------------------------------------------------------
# Names of the Slurm controllers this checkout can drain; the first is the
# default. Extend the tuple for a second controller and give it a venv below.
QUEUE_CLUSTERS = ("local",)
CLUSTER_VENVS: dict[str, str] = {}
VENV_DIR = ".venv"
MLRUNS_DIR = "mlruns"
RESULTS_DIR = "results"


def env(name: str) -> str:
    """Return the canonical env-var spelling of a harness parameter."""

    return f"{ENV_PREFIX}_{name}"


def env_regex() -> str:
    """Return the ERE that matches every canonical env var of this project."""

    return rf"^{ENV_PREFIX}_[A-Z0-9_]+$"


def venv() -> str:
    """Return the interpreter directory: override, per-cluster, or the checkout venv."""

    override = os.environ.get(env("VENV"))
    if override:
        return override
    cluster = os.environ.get(env("QUEUE_CLUSTER"))
    if cluster and CLUSTER_VENVS.get(cluster):
        return CLUSTER_VENVS[cluster]
    return str(REPO / VENV_DIR)


def _interpreter_version(exe: str) -> str:
    """Return ``MAJOR.MINOR`` of ``exe``, or an empty string when it will not run."""

    try:
        out = subprocess.run(
            [
                exe,
                "-c",
                "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    return out


def _floor_tuple(version: str) -> tuple[int, int]:
    major, _, minor = version.partition(".")
    return int(major), int(minor)


def python() -> str:
    """Return the project interpreter: env override, venv binary, else this one.

    Refuses an interpreter below ``PYTHON_FLOOR``: a gate that runs on an older
    Python fails where it looks like a gate bug, not an environment mismatch.
    """

    override = os.environ.get(env("PYTHON"))
    candidate = override or str(Path(venv()) / "bin" / "python")
    if not Path(candidate).is_file():
        candidate = sys.executable
    version = _interpreter_version(candidate)
    if not version or _floor_tuple(version) < _floor_tuple(PYTHON_FLOOR):
        raise SystemExit(
            f"FAIL: {candidate} is Python {version or 'unavailable'}, below the "
            f"{PYTHON_FLOOR} floor: create {VENV_DIR} with a {PYTHON_FLOOR}+ "
            f"interpreter or set {env('PYTHON')}."
        )
    return candidate


def deploy_root() -> str:
    """Return the checkout the jobs import: env override, else this repository."""

    return os.environ.get(env("ROOT")) or str(REPO)


def mlflow_uri() -> str:
    """Return the MLflow tracking URI: env override, else this checkout's mlruns dir."""

    return os.environ.get("MLFLOW_TRACKING_URI") or (REPO / MLRUNS_DIR).as_uri()


def dvc_bin() -> str:
    """Return the DVC executable: env override, the venv binary, else ``dvc`` on PATH."""

    override = os.environ.get(env("DVC_BIN"))
    if override:
        return override
    candidate = Path(venv()) / "bin" / "dvc"
    return str(candidate) if candidate.is_file() else "dvc"


def scope_regex(roots: tuple[str, ...], suffix: str = "") -> str:
    """Return an ERE anchoring ``roots`` (plus optional per-root suffix) at the start."""

    parts = "|".join(roots)
    return rf"^({parts})/{suffix}" if suffix else rf"^({parts})/"


KEYS: dict[str, object] = {
    "slug": SLUG,
    "env-prefix": ENV_PREFIX,
    "code-prefix": CODE_PREFIX,
    "python": python,
    "python-floor": PYTHON_FLOOR,
    "dvc-bin": dvc_bin,
    "run-manifest-schema": RUN_MANIFEST_SCHEMA,
    "run-metrics-schema": RUN_METRICS_SCHEMA,
    "canary-receipt-schema": CANARY_RECEIPT_SCHEMA,
    "venv": venv,
    "deploy-root": deploy_root,
    "source-roots": SOURCE_ROOTS,
    "test-root": TEST_ROOT,
    "mirror-root": MIRROR_ROOT,
    "params-module": PARAMS_MODULE,
    "registry-path": REGISTRY_PATH,
    "resolve-path": RESOLVE_PATH,
    "smoke-dir": SMOKE_DIR,
    "slurm-dir": SLURM_DIR,
    "queue-clusters": QUEUE_CLUSTERS,
    "default-cluster": QUEUE_CLUSTERS[0],
    "mirror-scope": lambda: scope_regex((*SOURCE_ROOTS, MIRROR_ROOT)),
    "coverage-scope": lambda: scope_regex(SOURCE_ROOTS, r".*\.py$"),
    "distortion-scope": lambda: scope_regex(DISTORTION_ROOTS, r".*\.py$"),
    "index-scope": lambda: scope_regex(INDEX_ROOTS),
    "production-scope": lambda: scope_regex(PRODUCTION_ROOTS),
    "env-regex": env_regex,
}


def _values(key: str) -> list[str]:
    raw = KEYS.get(key)
    if raw is None:
        raise KeyError(key)
    value = raw() if callable(raw) else raw
    if isinstance(value, tuple):
        return list(value)
    return [str(value)]


def main(argv: list[str]) -> int:
    """Print one key (``--get``) or the hook assignments (``--shell``)."""

    if len(argv) == 2 and argv[0] == "--get":
        try:
            print(" ".join(_values(argv[1])))
        except KeyError:
            print(f"unknown harness key: {argv[1]}", file=sys.stderr)
            return 2
        return 0
    if argv == ["--shell"]:
        print(f'PY="{python()}"')
        print(f'DEPLOY_ROOT="{deploy_root()}"')
        print(f'ENV_PREFIX="{ENV_PREFIX}"')
        return 0
    print(__doc__.split("Usage", 1)[0].strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
