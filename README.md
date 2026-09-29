# research-template

A **gated research harness**: the scaffolding around a research project, with the
project removed. It exists to make the expensive mistakes — an uncommitted
result, a submission nobody can map back to code, a metric that a surrogate
computation quietly manufactured — fail at commit or submit time instead of in a
paper.

[![template](https://img.shields.io/badge/GitHub-template_repository-2ea44f)](https://github.com/MaBarov/research-template)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![status](https://img.shields.io/badge/gates-green%20%C2%B7%20334%20tests-success)

Marked as a GitHub template repository: **Use this template** (or the `git clone`
below) starts a project with the harness already wired.

What you get:

* **Commit gates** (`framework/hooks/pre-commit`, blocking): code-size limits,
  test mirrors, per-file coverage clearance, docstring contracts, duplication,
  a single parameter registry, mutation evidence, surrogate-distortion
  anti-patterns, an sbatch provenance contract, and index freshness.
* **Submit gates** (`framework/gates/sbatch_gate.sh`, strict by default): dirty
  tree, contract, execution paths, `local_gate`, stub smoke, GPU canary,
  `sbatch --test-only`.
* **One place for every project token** (`framework/harness.py`): slug, env-var
  prefix, gate-code prefix, source/test roots, interpreter, cluster names.
* **A worked example** (`research/params/`, `research/probe/`,
  `experiments/example_plan/`, `scripts/smoke/plan_run_smoke.sh`) that clears
  every gate, including mutation evidence.

## Requirements

| | |
| --- | --- |
| Required | Python **≥ 3.11**, `git`. The floor is declared once (`PYTHON_FLOOR`, `requires-python`) and every hook, smoke driver and submit gate refuses below it. |
| Hook tooling | `pytest`, `coverage`, `mutmut`, `ruff`, `rope` (`pip install -e . pytest coverage mutmut ruff rope`). |
| Optional | `dvc` and `mlflow` for the documentation-chain gate; without them the gate refuses with the install hint instead of passing vacuously. |
| Not needed | A GPU, a scheduler, or any network service to run the harness itself. |

## Quickstart

```bash
git clone https://github.com/MaBarov/research-template my-project && cd my-project

python3 -m venv .venv                      # 3.11+; use python3.11/3.12 if your python3 is older
.venv/bin/python -m pip install -e . pytest coverage mutmut ruff rope

python scripts/setup/setup_framework.py    # core.hooksPath = framework/hooks
python scripts/setup/check_framework_wiring.py

.venv/bin/python -m pytest tests -q                 # the example suite
.venv/bin/python -m framework.indexing.cli --output INDEX.md
```

## Adopt it for your project

Every project token lives in `framework/harness.py`. The rename is one command,
which refuses a dirty worktree or an occupied target, moves the source tree and
its mirror, rewrites the tokens in every tracked text file, then fails unless no
old token survived:

```bash
python scripts/setup/init_project.py --slug myproj --prefix MYPROJ --code MYX [--dry-run]
python framework/harness.py --get slug      # verify the new identity
```

`ADOPTING.md` documents the identity keys, the manual steps (`pyproject.toml`
tables, `[tool.<slug>.contracts]`) and the ledgers the gates refresh themselves.

## Verifying the harness

```bash
python -m pytest framework/tests tests -q          # 334 tests: gate contracts + example suite
bash framework/hooks/pre-commit                    # the commit battery, on the staged tree
bash framework/gates/sbatch_gate.sh slurm/template.sbatch --dry-run
```

On a checkout without `.venv` the hook needs the floor interpreter explicitly:

```bash
RESEARCH_PYTHON=/path/to/python3.11 bash framework/hooks/pre-commit
```

## The gates

| Gate | Blocks | Command |
| --- | --- | --- |
| Antipatterns | commit | `python framework/gates/check_antipatterns.py --strict FILE...` |
| Sbatch contract | commit, submit | `bash framework/gates/check_sbatch_contract.sh slurm/job.sbatch` |
| Test mirrors | commit | `python framework/gates/checks/check_test_mirror.py --strict --staged FILE...` |
| Coverage | commit | `python framework/gates/check_coverage.py --mode staged --staged FILE...` |
| Code size | commit | `python framework/gates/limits/check_limits.py --mode all` |
| Docstring contracts | commit | `python -m framework.indexing.cli --strict-contracts --staged-files FILE...` |
| Duplication | commit | `python framework/gates/checks/check_duplication.py --strict --staged FILE...` |
| Parameters | commit | `python framework/gates/params/check_param_duplicates.py --strict FILE...` |
| Mutation evidence | commit | `python framework/gates/mutation/check_mutation.py --mode staged --staged FILE...` |
| Distortion | commit | `python framework/gates/distortion/check_distortion.py --strict --staged FILE...` |
| Index freshness | commit | `python -m framework.indexing.cli --output INDEX.md --check` |
| Submit gate | submit | `bash framework/gates/sbatch_gate.sh slurm/job.sbatch` |

Every gate is fail-closed and none of them takes an override flag. Ledgers under
`framework/` (`coverage_evidence.json`, `mutation_evidence.json`,
`loop_waivers.json`, `jscpd-baseline.json`) record evidence, not exemptions:
they are refreshed by re-running the gate, never edited by hand.

## Submitting a job

```bash
cp slurm/template.sbatch slurm/my_job.sbatch     # keep the provenance guard
$EDITOR experiments/my_run/run.py                # the payload
$EDITOR scripts/smoke/run_smoke.sh               # its smoke driver
bash framework/gates/sbatch_gate.sh slurm/my_job.sbatch --dry-run
bash framework/gates/sbatch_gate.sh slurm/my_job.sbatch ARG...
```

The gate refuses a dirty tree at submit time and the job refuses again at
runtime; a run always carries the commit it executed.

Smoke drivers resolve their interpreter through
`scripts/smoke/lib/interpreter.sh`: `SMOKE_PYTHON`, then the checkout's
`.venv`, then `framework/harness.py`, then `python3.13`…`python3`. An
interpreter below the declared floor (3.11) is refused — a smoke that passes on
an unsupported Python is a false signal — so on a bare host run
`SMOKE_PYTHON=/path/to/python3.11 bash scripts/smoke/<name>_smoke.sh`.

## Layout

```text
framework/     harness.py, gates/{antipattern,checks,coverage,distortion,
               freshness,limits,mutation,params,provenance}, hooks/, indexing/
research/      your package (worked example: params/, probe/)
tests/research/ mirror tests, one per source module
scripts/       entry points, setup/, slurm_queue/, smoke/
slurm/         job scripts; template.sbatch is the one to copy
experiments/   run entry points grouped by experiment
third_party/   pinned vendored trees (never edited in place)
```

## What this is not

Not a framework, not a pipeline runner, and not a dataset or model registry: it
is the *policy* layer — what must be true before a result is allowed to count —
plus the small amount of machinery that enforces it. Research code goes in
`research/`; the harness only asks it to be sized, tested, mirrored, contracted
and submitted honestly.
