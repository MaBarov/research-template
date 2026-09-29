# Adopting the template

The harness is written so that **one file** holds the project's identity and
every gate, hook and script reads it. Rename the project by editing that file and
running the mechanical rename below; nothing else should need project names.

## 1. The identity file

`framework/harness.py`:

| Key | Meaning | Template value |
| --- | --- | --- |
| `SLUG` | package/name slug, used for titles and prefixes | `research` |
| `ENV_PREFIX` | every environment variable the project owns | `RESEARCH` |
| `CODE_PREFIX` | gate finding codes | `HNS` |
| `SOURCE_ROOTS` | first-party Python roots | `research/` |
| `TEST_ROOT` | root of the mirror test tree | `tests/research` |
| `PRODUCTION_ROOTS` | trees the antipattern gate reads | `research`, `scripts`, `slurm` |
| `CONSUMING_ROOTS` | trees the parameter gate reads | `research`, `experiments`, `framework`, `scripts`, `slurm` |
| `PARAMS_MODULE` / `REGISTRY_PATH` | the parameter registry | `research.params` / `research/params/registry.py` |
| `REGISTRY_TEST_PATH` | the registry's mirror test | `tests/research/params/tests_registry.py` |
| `RESOLVE_PATH` | the parameter accessors | `research/params/resolve.py` |
| `SMOKE_DIR` / `SLURM_DIR` | submit-gate directories | `scripts/smoke` / `slurm` |
| `QUEUE_CLUSTERS` / `CLUSTER_VENVS` | the Slurm queue's clusters | `("local",)` / `{}` |
| `VENV_DIR` | the project virtualenv | `.venv` |
| `PYTHON_FLOOR` | minimum interpreter, equal to `requires-python` | `3.11` |

Print any of them, or the derived scopes the hooks use, with:

```bash
python framework/harness.py            # every key: value pair
python framework/harness.py --get KEY  # one key; e.g. python, venv, env-regex
```

## 2. Rename recipe

The mechanical part of this recipe runs as one command. It refuses a dirty worktree
or a target that already exists, applies steps 1-4 below, regenerates `INDEX.md` and
the `AGENTS.md` mirrors, and only then succeeds while no old token survived:

```bash
python scripts/setup/init_project.py --slug <slug> --prefix <PREFIX> --code <CODE> [--dry-run]
```

The coverage, duplication and mutation ledgers of step 5 are still refreshed by the
gates themselves, exactly as that step describes; step 6 stays a judgement call.

Pick `<slug>`, `<PREFIX>` (upper-case) and `<CODE>` (2-4 upper-case letters), then:

1. `git mv research <slug>`; rename `tests/research` to `tests/<slug>`.
2. Update `framework/harness.py` (`SLUG`, `ENV_PREFIX`, `CODE_PREFIX`, roots).
3. Update `pyproject.toml`: `[project] name`, `[project.scripts]`,
   `[tool.setuptools.packages.find] include`, `[tool.mutmut]` `source_paths` /
   `only_mutate` / `pytest_add_cli_args*`, `[tool.ruff.lint.isort]`
   `known-first-party`, and `[tool.<slug>.contracts]`.
4. Replace the token names mechanically, then verify nothing is left:

   ```bash
   grep -rn '<PREFIX>_\|<CODE>[0-9]' --include='*.py' --include='*.sh' \
       --include='*.md' --include='*.sbatch' . | grep -v '^./.git/'
   ```

5. `python framework/harness.py --get keys` and every gate must still run; then
   regenerate the ledgers in this order:

   ```bash
   python -m framework.indexing.cli --output INDEX.md          # index + sub-indices
   python framework/gates/check_coverage.py --update-baseline  # coverage ledgers
   python framework/gates/checks/check_duplication.py --update-baseline
   python framework/gates/mutation/check_mutation.py --mode staged --staged FILE...
   python framework/gates/checks/sync_agents_mirrors.py        # AGENTS.md mirrors
   ```

6. Drop the worked example when the real modules exist: delete `research/params`,
   `research/probe`, `experiments/example_plan`, its mirror tests, the smoke
   driver and the `slurm/` example job — in the same commit that adds the
   replacement, so no gate is left pointing at a deleted module. Keep the
   *structure*: a registry module, mirror tests, a smoke driver.

## 3. What is deliberately not in the template

* No project dependencies: the harness and the example are stdlib-only. Add yours
  to `[project] dependencies` (or a `uv.lock`) when you have them.
* No cluster identity: `QUEUE_CLUSTERS` and `CLUSTER_VENVS` are the two places a
  cluster name, its sbatch flags or its interpreter path belong. `slurm/template.sbatch`
  keeps only `#SBATCH` directives and the provenance guard.
* No model or dataset pins: `MODEL_SNAPSHOTS` and `BANNED_LITERALS` in the
  registry start empty; fill them so the parameter gate can defend them.
* No domain vocabulary: the contamination gate's `NSFW_MARKERS` ships with one
  domain's words as an illustration, and its bank keys (`concept`, `safe`) are
  the vocabulary it assumes. It is not wired into the hook: call it against your
  own bank files
  (`python framework/gates/checks/check_contamination.py --strict BANK.json`).
* No default science: the distortion and contamination gates encode *classes* of
  surrogate artifact (post-quantization differencing, pooled-basis broadcast,
  un-errored ratios) rather than one paper's method. Extend them with your own
  class of artifact, in the same gate, when you find one.

## 4. Rules that are not negotiable

* A dirty tree never submits, and there is no override knob: no environment
  variable, no skip flag, no allowlist. If a gate is wrong, fix the gate in the
  same commit as the finding it produced.
* `dvc`/`mlflow` provenance (`framework/gates/provenance/`) is optional: the
  gates degrade to a clear refusal when the tool or the run is missing, and they
  never invent a run.
* Every ledger under `framework/` is content-addressed evidence: refreshing it
  means running the gate, and a stale entry is a finding, not a warning.
