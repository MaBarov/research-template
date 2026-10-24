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
| `STATIC_ROOTS` | trees the static gates audit | `research`, `framework`, `scripts`, `experiments` |
| `EXCLUDED_PARTS` | path components no static gate reads (tests, vendored trees, caches) | `tests`, `third_party`, `cache`, `mutants`, `__pycache__`, `.venv`, `venv`, `results`, `models`, `.git` |
| `TEST_ROOT` | root of the whole test tree (mirrors, harness tests, fixtures) | `tests` |
| `MIRROR_ROOT` | mirror test tree the mirror gate resolves against | `tests/research` |
| `CACHE_DIR` / `GATE_STATE_DIR` | build cache / per-repository gate state (locks, canaries) | `cache` / `research-gate` |
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
* No domain vocabulary: the contamination gate ships **no** marker words — the
  vocabulary a safe-side prompt may not carry is the project's, supplied as
  `--markers a,b,c` (or a registry row you wire it to), and its bank keys
  (`concept`, `safe`) are the layout it assumes. It is not wired into the hook:
  call it against your own bank files
  (`python framework/gates/checks/check_contamination.py --strict --markers X,Y BANK.json`).
* No default science: the distortion and contamination gates encode *classes* of
  surrogate artifact (post-quantization differencing, pooled-basis broadcast,
  un-errored ratios) rather than one paper's method. Extend them with your own
  class of artifact, in the same gate, when you find one.
* No project judgment where it would bind you. The source project this harness
  was extracted from also carries policy gates calibrated against *its* labelled
  case corpus. Two families ship here because they are mechanical and their taste
  is quarantined: the hot-path detector (`hotpath/`, HNS089-HNS094) and the
  abstract-cost/PROXY-quality detector (`abstract_cost/`, HNS095-HNS099) run as
  **advisories** — their recorded recall is pinned (16/18 and 16/19), and they
  print findings while the commit proceeds. Adopt them tightly by adding
  `--strict` in the hook step, or ignore their census entirely. Still absent: a
  statistics-policy gate over one project's metric families and a design judge for
  SOLID/DRY shapes, both of which need that project's module graph and receipt
  schemas. If you want equivalents, build them the same way: an AST visitor with
  one code per shape, a labelled case table with its expected code set, and a
  printed precision/recall so a rule that stops firing is visible.

## 3a. What each blocking gate answers

Every code below is printed by the gate named beside it; the code prefix is
`harness.CODE_PREFIX` (`HNS` in the template).

| Gate | Codes | Question it refuses to answer "probably" |
| --- | --- | --- |
| `check_antipatterns.py` | HNS005-HNS037, HNS066, HNS067, HNS069, HNS072, HNS081, HNS082 | Is this code shape a known failure mode (swallowed failure, unbounded loop, unquoted shell interpolation, dead guard, positional response read, unpinned tooling)? |
| `checks/check_test_mirror.py` | MIRROR MISSING, ALIAS DANGLING/STALE, MIR003, HNS068, HNS070 | Does the mirror exist, does its table only shrink, and does it assert the module's behavior with an independent oracle? |
| `check_coverage.py` | COV005 + coverage findings | Do the mirror tests alone clear the file's statements and every loop's 0/1/>=2 cases, and does the waiver table only shrink? |
| `limits/check_limits.py` | LMT001-LMT003 | Is the file, function and directory under the size caps, as staged? |
| `indexing/gate.py` | contract findings | Does the module docstring keep its thumbnail and its `Invariants & Expected State:` contract? |
| `checks/check_duplication.py` | CPD000-CPD002 | Is this clone new, and does the baseline only shrink? |
| `params/check_param_duplicates.py` | HNS038-HNS043 | Is every parameter declared once in the registry, with no second default or alias? |
| `distortion/check_distortion.py` | HNS044-HNS046 | Was this metric manufactured by a surrogate computation artifact? |
| `typecheck/check_types.py` | mypy/pyright findings | Does the module I am touching type-check, judged on the staged blob? |
| `transfers/check_device_transfers.py` | HNS056-HNS060, HNS088 | Does this loop move data to the host, mix devices in one expression, or synchronize redundantly? |
| `memory/check_memory_bottlenecks.py` | HNS083-HNS086 | Does this step allocate per iteration, retain an autograd graph, or keep a tensor alive for the whole run? |
| `hotpath/check_hotpath.py` (advisory) | HNS089-HNS094 | Does this shape match a measured hot-path defect in the labelled corpus (census only, never blocking)? |
| `abstract_cost/check_abstract_cost.py` (advisory) | HNS095-HNS099 | Is this a proxy-quality computation (census only, never blocking)? |
| `mutation/check_mutation.py` | mutation findings | Do the tests kill the mutants of this exact content, scored against this exact test surface? |
| `check_documentation.py` | doc-chain findings | Is there a manifest, metrics file and DVC/MLflow run behind the number? |
| `check_sbatch_contract.sh` + `sbatch_gate.sh` | contract findings | Can this job be mapped back to a commit, and does it refuse a dirty tree? |
| `instructions/check_instruction_refs.py` | HNS073 | Does every file path the instruction artifacts name exist in a tracked tree? |
| `freshness/ref_guard.py` (+ hook `reference-transaction`) | GUARD001 | Did this ref move carry a tree this battery armed, or is it a ref bypass of the gates? |

## 4. Rules that are not negotiable

* A dirty tree never submits, and there is no override knob: no environment
  variable, no skip flag, no allowlist. If a gate is wrong, fix the gate in the
  same commit as the finding it produced.
* `dvc`/`mlflow` provenance (`framework/gates/provenance/`) is optional: the
  gates degrade to a clear refusal when the tool or the run is missing, and they
  never invent a run.
* Every ledger under `framework/` is content-addressed evidence: refreshing it
  means running the gate, and a stale entry is a finding, not a warning.
* A test is an oracle or it is not a test. The mirror gate grades the mirror's
  own text (HNS068 for no behavioral assertion, HNS070 for assertions pinned to
  their own state), the hook grades every staged test file the same way, and the
  mutation ledger stamps the digest of the whole test surface: a verdict scored
  against older tests is refused, because mutmut reuses its cache across test
  edits (`harness.TEST_ROOT`, the root `conftest.py` and the `[tool.mutmut]`/
  `[tool.pytest.ini_options]` sections are inside that digest).
* The alias, waiver and duplication-baseline tables are ratchets (MIR003,
  COV005, CPD002): they may shrink, never grow. A new module earns a mirror; a
  loop that cannot reach its 0-case is fixed in a test, not waived afresh.
