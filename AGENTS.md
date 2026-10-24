# Research harness — agent governance

This repository is a **research harness**: the scaffolding a research project is
built on, not the research itself. It carries one worked example you replace, and
a set of commit gates that keep provenance, parameters, code size, coverage and
evaluation integrity honest once the real code arrives.

Layout:

| Path | Role |
| --- | --- |
| `research/` | the project's package (worked example: `params/`, `probe/`) |
| `tests/research/` | mirror tests, one per source module (gate-enforced) |
| `framework/` | the harness itself: `harness.py`, gates, hooks, indexing |
| `scripts/` | entry points, setup, the Slurm queue, smoke drivers |
| `slurm/` | job scripts; `template.sbatch` is the one to copy |
| `experiments/` | run entry points grouped by experiment |
| `third_party/` | pinned vendored trees, never edited in place |

Every project-specific token — package slug, env-var prefix, gate-code prefix,
source and test roots, cluster names, interpreter — resolves through
`framework/harness.py`. Nothing else restates them. See `ADOPTING.md` for the
rename recipe and `README.md` for the quickstart.

## Gates

Repository gates are active through `core.hooksPath = framework/hooks`:

* `framework/hooks/pre-commit` — blocking. Ruff, production anti-patterns,
  the sbatch provenance contract, test mirrors, coverage clearance, code-size
  limits, docstring contracts, duplication, the parameter registry, mutation
  evidence, surrogate-distortion anti-patterns, static types, device transfers,
  memory bottlenecks, instruction references, the pinned acceptance battery, and
  index freshness. Its last act is to arm the ref-provenance marker the
  `reference-transaction` hook verifies.
* `framework/hooks/pre-push` — advisory, never blocks: whole-tree findings a
  staged check cannot see (dead code, secrets, ledger freshness, index drift,
  the pyright census, the full suite).
* Advisory families that never block: `gates/hotpath/` (HNS089-HNS094) and
  `gates/abstract_cost/` (HNS095-HNS099). They print a census and a `WARN`, and
  their recorded recall is pinned in `framework/tests/{hotpath,abstract_cost}`.
* `INDEX.md` and its sub-indices — architectural Table of Contents mapping
  modules, signatures and contracts
  (`python -m framework.indexing.cli --output INDEX.md`). Consult them for
  macro-navigation before exploratory searches.

Whole-tree audits, run before claiming a clean tree:

```bash
python framework/gates/limits/check_limits.py --mode all
python framework/gates/check_coverage.py --mode all --strict
python framework/gates/typecheck/check_types.py --mode all --engine mypy
python framework/gates/transfers/check_device_transfers.py --mode all --strict
python framework/gates/memory/check_memory_bottlenecks.py --mode all --strict
python framework/gates/instructions/check_instruction_refs.py --strict
python -m framework.indexing.cli --output INDEX.md --check
python scripts/setup/check_framework_wiring.py
```

## Governance Sync

### Code-size rules (hard)

* A Python file holds at most **600 lines**. A module that outgrows it becomes a
  directory of the same name, and its members are moved out with the vendored
  Rope runner `third_party/refactor/rope_refactor.py` — decomposition is never
  handwritten.
* A function or method spans at most **30 lines**: the `def` line through its
  last body line, decorators excluded, methods and `async def` included.
* A directory holds at most **5** first-party `.py` modules (counted
  non-recursively, `__init__.py` excluded).
* `__init__.py` carries no code: module docstring, imports and dunder-only
  assignments (`__all__`, `__version__`, ...) only.

Enforcement is *touch it, fix it*: the pre-commit hook runs
`framework/gates/limits/check_limits.py --mode staged --strict --staged FILE...`,
which reads module text and directory counts from the Git index and requires
every staged module — and the directory it lives in — to comply as staged. There
is no grandfathering, allowlist, or baseline: a legacy file is split in the same
commit that touches it, and touching a module inside an over-cap directory means
decomposing that directory first. There is no bypass: no environment variable,
no skip flag and no override.

### Working inside those rules

* New code goes into a new subpackage (for example `framework/gates/limits/`,
  `research/<area>/`), never as an extra module in a directory that is already at
  the limit.
* Moving members out with `git mv` records the removal as a deletion, so the
  directory count drops in the same commit; a decomposition therefore lands as
  additions in the new subpackage plus deletions of the old paths.
* Every touched source file also needs its mirror test and coverage evidence
  refreshed in the same commit:

  ```bash
  python framework/gates/check_coverage.py --mode staged --staged FILE...
  git add framework/coverage_evidence.json FILE...
  ```

  A mirror is `tests/<root>/<path>/tests_<stem>.py` (or `test_<stem>.py`), and it
  must clear the gate **on its own**: the mirror test file has to reach the
  module's statements itself, because a line executed during another test file's
  import is credited to that file, not to this one. Assert the module's
  behavior; do not rely on a neighbour's import.
* Keep the index fresh and the docstrings contractual:

  ```bash
  python -m framework.indexing.cli --output INDEX.md
  python -m framework.indexing.cli --strict-contracts --staged-files FILE...
  ```

  Two-Tier docstrings are enforced on touch for the paths in `pyproject.toml`
  (`[tool.research.contracts]` `enforce-paths`): a PEP 257 Tier-1 thumbnail
  (<= 140 chars) followed by an explicit `Invariants & Expected State:` section.
  Tests and `__init__.py` are excluded via `exclude-patterns`. If a public
  signature changes, the docstring contract changes with it (interface drift
  gate).

### Test oracles and ratchet tables (blocking pre-commit)

A test file that exists but asserts nothing is worse than a missing one: it
satisfies an existence check and cannot catch a regression.

* `framework/gates/checks/check_test_mirror.py` grades the mirror's own text.
  `HNS068` fires when a non-exempt mirror parses to no behavioral assertion or
  to nothing but tautologies (`assert True`, `assert 1 == 1`); `HNS070` fires
  when every assertion is state-anchored or self-referential (`assert x == x`,
  `assert f() == f()`, `assert len(x) >= 0`). `pytest.raises`/`pytest.warns`
  blocks count as oracles; `conftest.py` and `*_fixtures.py` are exempt; an
  unparseable mirror fails closed.
* The same module grades every staged test file through `--oracle-files`, so
  weakening a test blocks the commit that weakens it, whether or not the module
  it mirrors is staged too.
* `MIR003` (alias table), `COV005` (loop waivers) and `CPD002` (duplication
  baseline) are ratchets: each compares the working table with the table
  committed at `HEAD` and refuses an addition. Removals and identical tables
  pass. A new module earns a dedicated mirror instead of borrowing a
  neighbour's; a loop that cannot reach its 0-case is fixed in a test instead of
  waived afresh; a new clone is deleted instead of baselined.
* Mutation evidence is schema v2. Every ledger entry carries
  `content_sha256` (the staged blob), `tests_sha256` (the digest of
  `harness.TEST_ROOT`, the root `conftest.py` and the `[tool.mutmut]` /
  `[tool.pytest.ini_options]` sections) and the mutmut verdict counts. A
  refresh refuses while the test surface differs from the index, refuses to
  record when the surface or the staged bytes moved during the run, and drops
  mutmut's own verdict cache when the digest moved, because mutmut reuses cached
  verdicts across test edits. A refresh serializes on an exclusive lock under
  `harness.GATE_STATE_DIR`; a peer refresh is refused, never queued.
* A `# pragma: no mutate` line generates no mutant at all, so it is reported as
  a `NOTE` (never a verdict) when a staged blob adds one over `HEAD`.

### Submission provenance (strict by default)

Every cluster job is identified by the commit it ran from, and nothing submits
without that identity.

* `framework/gates/check_sbatch_contract.sh` is the single source of truth for
  the job-script contract: a dirty-tree refusal (`REFUSING RUN: dirty tree`), a
  commit resolution (`COMMIT=$(git rev-parse ...)`), a status stamp carrying it
  (`status=... commit=$COMMIT`), no dirty-run override, and a refusal that leads
  its dirty branch and is followed by `exit 90`. New jobs copy
  `slurm/template.sbatch`.
* `framework/hooks/pre-commit` **blocks** any staged `slurm/*.sbatch` that
  violates the contract.
* `framework/gates/sbatch_gate.sh` is **strict by default**: dirty tree, missing
  contract, missing execution-node paths, `local_gate`, stub-smoke, GPU canary
  and `sbatch --test-only` all abort the submit. `SBATCH_GATE_STRICT=0` is the
  only downgrade (human emergency, or a host that is not the job target);
  `--dry-run` skips the submit.
* There is **no dirty-run override**: a dirty tree always refuses, at submit time
  (`sbatch_gate.sh` step 1) and at runtime in the job script itself (`exit 90`).
  The ban is mechanical, not conventional: contract rules above, the anti-pattern
  codes `HNS035` (override knob) and `HNS036` (conditional refusal), and
  `checkout_refusal` in the queue worker all refuse, and
  `tests/framework/test_sbatch_contract.py` pins the contract from both sides.
  Re-opening it needs a change in each layer, never a flag at the call site.
  Without a git checkout at all, `RESEARCH_COMMIT` must be supplied or the run
  refuses.
* Stub-smoke: a failing driver always blocks the submit; a **missing** driver
  blocks new scripts (write `scripts/smoke/<name>_smoke.sh`) and is metered with
  a `NOTE` for legacy scripts. A job script's payload is discovered under
  `experiments/`/`scripts/` by path, and the driver must **fail** (never
  skip-as-pass) when the payload is gone, so a moved module cannot slip past the
  smoke gate unnoticed.
* A supplied `RESEARCH_COMMIT` is a **claim about which tree the job imports**,
  and the guard reconciles it: on a checkout it must equal `git rev-parse HEAD`,
  and where there is no checkout it must equal the deploy root's
  `.research_commit`; a disagreement refuses with `exit 90`. The hole this closes
  is real: `cd $ROOT && sbatch script` does **not** set `RESEARCH_ROOT`, so the
  arm's default root is what executes, and without reconciliation a pinned
  `RESEARCH_COMMIT` makes the stamped commit differ from the code that ran.
  `slurm/template.sbatch` carries the reconciliation, and `sbatch_gate.sh`
  forwards a script's positional arguments
  (`sbatch_gate.sh <script> [--dry-run] ARG ...`), so the sanctioned submit path
  is usable for parameterized arms instead of a hand-rolled `sbatch` that loses
  the recipe's `RESEARCH_ROOT`.

### Parameters (one registry, one env var, one default)

Every important parameter — env var name, default value, superseded aliases and
banned literals — lives once, in `research/params/registry.py`. Nothing else may
name a second env var for the same parameter, restate its default, or copy one of
its pinned literals (dataset paths, thresholds, frozen values).

* Production code reads a value through `research.params` only:
  `int_param`/`float_param`/`str_param`/`path_param("name")` for plain values, a
  named accessor (`seed()`) where the row declares one, or `ambient(name)` when
  the caller must know whether the value was overridden. The package is
  stdlib-only and resolves at call time; nothing caches.
* `framework/gates/params/check_param_duplicates.py` is the single source of
  truth for the rule, and `framework/hooks/pre-commit` step **5d4 blocks** every
  commit that violates it: `HNS038` a superseded env alias, `HNS039` a restated
  default (module constant, argparse `default=`, `getattr(..., default)`,
  flag/value recipe pair), `HNS040` a copied registered literal, `HNS041` a
  malformed registry. The gate reads no environment variable, has no baseline, no
  allowlist and no override; an unreadable staged file is a finding. Its usage
  companion (`HNS042`, `HNS043`) reports a row no production module reads and an
  implementation that does not compare its registered default.
* A run that must deviate keeps its exact behaviour at the call site as an
  **explicit** value: Python literals in recipe tuples, or a shell
  `: "${VAR:=<value>}"` assignment followed by `"$VAR"`. A *differing* default
  inside a `:-` expansion is banned; a flag/value pair whose value differs from
  the registry default is a deliberate choice and stays.
* `python framework/gates/params/check_param_duplicates.py --strict FILE...`
  checks files, `--staged` checks the Git index; `--report PATH` writes the
  machine-readable finding list used by the migration census.

### Surrogate distortion anti-patterns (blocking pre-commit)

Empirical guarantees and benchmark metrics must not be distorted by surrogate
computation artifacts:

* `framework/gates/distortion/check_distortion.py` is the single source of truth
  for the rule, and `framework/hooks/pre-commit` step **5d6 blocks** every commit
  that violates it: `HNS044` post-quantization delta subtraction (extracting a
  change after low-precision casting erases sub-ULP adjustments), `HNS045`
  in-sample pooled broadcast (assigning one estimate computed over a pooled
  population to each member of it, so the per-member comparison is tautological),
  `HNS046` un-errored ratio-of-means reduction (a point estimate collapses
  variance without paired error bars).
* The gate reads staged blobs from the Git index (`--staged`), enforces
  `--strict` exit 1 on any finding, and fails closed with `HNS010` on unreadable
  or missing staged sources. There is no bypass, allowlist, or skip flag.

### Static types, instruction references and ref provenance (blocking)

Three holes that surface only after the fact, closed at commit and at ref move:

* `framework/gates/typecheck/check_types.py`, pre-commit step **5d7**: touching a
  typed module means leaving it type-clean, so mypy runs over the staged blob
  (`--shadow-file`) for every staged module under the static roots. A foreign
  finding never blocks (`--follow-imports=silent`, filtered to the caller's
  scope), an unreadable blob is never reported clean, and a missing mypy fails
  closed under `--strict`. `--mode all` is the census; pyright is the advisory
  second opinion on pre-push. The census is a debt meter, not a block: it prints
  per-tree counts and the worst files, and exits 0 without `--strict`. The
  blocking decision is staged-only, so the debt falls as files are touched —
  exactly the posture the code-size rule already takes. Policy lives in
  `[tool.mypy]`/`[tool.pyright]` in `pyproject.toml`, and both engines are dev
  extras.
* `framework/gates/instructions/check_instruction_refs.py`, pre-commit step
  **5d9**: every backticked file path an instruction artifact names must resolve
  against `git ls-files`. `HNS073` buckets each unresolved token (`placeholder`,
  `moved` with the sole match named, `output`, `dead`) and blocks on a dead or
  placeholder reference. `--corpus-root DIR` extends one census over a second
  tree's corpus (`DIR/rules/*.md`, `DIR/managed-skills/*/SKILL.md`,
  `DIR/AGENTS.md`) beside this repository's `AGENTS.md`; the root is a parameter,
  never a product path.
* `framework/gates/freshness/ref_guard.py` is invoked by the
  `framework/hooks/reference-transaction` hook for every ref move, and
  `framework/hooks/pre-merge-commit` forwards to the battery because git creates
  no pre-commit hook for a merge commit. A move is allowed only when the new
  value is already reachable from a live tip, or when pre-commit step **6**
  armed a marker binding the invoking git PID to the tree it wrote (tree, start
  time, 600 s window, consumed on the match). Anything else is `GUARD001` and the
  transaction aborts; every decision is appended to
  `<common-dir>/research-gate/ref_audit.jsonl`.

### Device transfers and memory bottlenecks (blocking), hot path and abstract cost (advisory)

Four gates read the same static population and share one loader
(`framework/gates/static/sources.py`), so they cannot disagree about which file
they are willing to read:

* `framework/gates/transfers/check_device_transfers.py`, pre-commit step
  **5d8**: `HNS056`-`HNS060` grade host↔device transfer shapes (a copy inside a
  loop or comprehension, `to("cpu")` in either spelling, a concatenation built
  from moved pieces) and `HNS088` an expression that mixes two devices. Every
  finding carries its `trigger` (`loop`, `aggregate`, `streaming`, `static`), so
  a name-triggered hit is never read as a measured per-iteration cost.
* `framework/gates/memory/check_memory_bottlenecks.py`, step **5d11**:
  `HNS083`-`HNS086` grade per-iteration allocation and retention — an
  un-detached tensor appended to a list keeps its graph alive for the whole run.
* `framework/gates/hotpath/check_hotpath.py` (**5d12**) and
  `framework/gates/abstract_cost/check_abstract_cost.py` (**5d13**) are
  **advisory**: they print a census and a `WARN`, and never fail a commit. Their
  calibration is the source project's labelled corpus, so shipping them as vetoes
  would ship its taste; their recorded recall (16/18 and 16/19) is pinned, which
  means a rule that stops firing fails the pinned battery instead of decaying
  silently. `--strict` is how a project that adopts the notion flips the posture.

### Pinned acceptance battery (blocking pre-commit)

A `pinned` test carries a number a human recorded — a census floor, a recall
figure, a wiring fact — rather than a behavior. Those are the tests a silent
refactor breaks first while every behavioral test keeps passing, so pre-commit
step **5d10** runs `pytest -m pinned` over `framework/tests` and the project's
test root on every commit:

* Mark a case `pytestmark = pytest.mark.pinned` when its expectation is a
  recorded number or an acceptance fact that a refactor could move without
  failing anything else. Do not mark ordinary behavior: the battery is meant to
  stay a few seconds.
* The step fails closed twice: a failing pinned case (re-census the number, or
  fix the regression it caught), and a selection that collects nothing (pytest
  exit 5) — a marker whose last carrier was deleted cannot pin anything.
* The marker is registered in `[tool.pytest.ini_options]`, so an unregistered
  warning is never the reason a battery silently runs nothing.
