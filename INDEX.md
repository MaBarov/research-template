# Research Codebase Master Index

> [!NOTE]
> Master architectural directory. Sub-indices are maintained for major subtrees. Use the sub-index links and line ranges below to load target sections into context.

**Repository Statistics**: 93 modules | 35 classes | 698 public functions.

## Master Table of Contents

### [`experiments/INDEX.md`](experiments/INDEX.md) — 1 modules | 2 symbols

- [`experiments/example_plan`](experiments/INDEX.md#L14-L22) (lines 14–22 in `experiments/INDEX.md`)

### [`framework/INDEX.md`](framework/INDEX.md) — 74 modules | 598 symbols

- [`framework`](framework/INDEX.md#L38-L62) (lines 38–62 in `framework/INDEX.md`) — *Repository gate framework (hooks + checkers).*
- [`framework/gates`](framework/INDEX.md#L63-L90) (lines 63–90 in `framework/INDEX.md`) — *Blocking and advisory repository gates.*
- [`framework/gates/antipattern`](framework/INDEX.md#L91-L124) (lines 91–124 in `framework/INDEX.md`) — *Internals of the production anti-pattern gate.*
- [`framework/gates/antipattern/execution`](framework/INDEX.md#L125-L133) (lines 125–133 in `framework/INDEX.md`) — *Execution-sink anti-patterns for the production gate (HNS081, HNS082).*
- [`framework/gates/antipattern/liveness`](framework/INDEX.md#L134-L140) (lines 134–140 in `framework/INDEX.md`) — *Liveness checks for the production anti-pattern gate (HNS072).*
- [`framework/gates/checks`](framework/INDEX.md#L141-L225) (lines 141–225 in `framework/INDEX.md`) — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*
- [`framework/gates/coverage`](framework/INDEX.md#L226-L285) (lines 226–285 in `framework/INDEX.md`) — *Internals of the per-file coverage and loop-iteration gate.*
- [`framework/gates/distortion`](framework/INDEX.md#L286-L332) (lines 286–332 in `framework/INDEX.md`) — *Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.*
- [`framework/gates/freshness`](framework/INDEX.md#L333-L364) (lines 333–364 in `framework/INDEX.md`)
- [`framework/gates/limits`](framework/INDEX.md#L365-L422) (lines 365–422 in `framework/INDEX.md`)
- [`framework/gates/mutation`](framework/INDEX.md#L423-L528) (lines 423–528 in `framework/INDEX.md`) — *Mutation-evidence gate: content-addressed mutmut verdicts for staged modules.*
- [`framework/gates/params`](framework/INDEX.md#L529-L569) (lines 529–569 in `framework/INDEX.md`) — *Parameter-drift gate package: registry matchers, CLI and their fixtures.*
- [`framework/gates/params/primitives`](framework/INDEX.md#L570-L574) (lines 570–574 in `framework/INDEX.md`) — *Pure AST and text primitives of the parameter-drift matchers.*
- [`framework/gates/provenance`](framework/INDEX.md#L575-L611) (lines 575–611 in `framework/INDEX.md`) — *Run-provenance gates: GPU canary, run manifest, replay verification, MLflow log.*
- [`framework/indexing`](framework/INDEX.md#L612-L663) (lines 612–663 in `framework/INDEX.md`) — *AST-based repository mapping and Table-of-Contents indexing.*
- [`framework/tests`](framework/INDEX.md#L664-L820) (lines 664–820 in `framework/INDEX.md`)
- [`framework/tests/antipattern`](framework/INDEX.md#L821-L908) (lines 821–908 in `framework/INDEX.md`) — *Anti-pattern extension tests (HNS066/067/069/072/081/082).*
- [`framework/tests/coverage_gate`](framework/INDEX.md#L909-L919) (lines 909–919 in `framework/INDEX.md`) — *Tests for the coverage gate and its probe plugin.*
- [`framework/tests/distortion`](framework/INDEX.md#L920-L946) (lines 920–946 in `framework/INDEX.md`) — *Test package for the framework distortion gate.*
- [`framework/tests/gates`](framework/INDEX.md#L947-L1057) (lines 947–1057 in `framework/INDEX.md`) — *Package.*
- [`framework/tests/gates/params`](framework/INDEX.md#L1058-L1116) (lines 1058–1116 in `framework/INDEX.md`) — *Tests for the parameter registry gates.*
- [`framework/tests/gates/ratchet`](framework/INDEX.md#L1117-L1139) (lines 1117–1139 in `framework/INDEX.md`) — *Ratchet gates: tables that may only shrink.*
- [`framework/tests/harness`](framework/INDEX.md#L1140-L1156) (lines 1140–1156 in `framework/INDEX.md`) — *Harness registry tests: project identity and the interpreter floor.*
- [`framework/tests/hook_hygiene`](framework/INDEX.md#L1157-L1165) (lines 1157–1165 in `framework/INDEX.md`) — *Tests for the hook/test-process boundary.*
- [`framework/tests/indexing`](framework/INDEX.md#L1166-L1214) (lines 1166–1214 in `framework/INDEX.md`) — *Tests for framework.indexing Table-of-Contents subsystem.*

### [`research/INDEX.md`](research/INDEX.md) — 3 modules | 13 symbols

- [`research/params`](research/INDEX.md#L15-L42) (lines 15–42 in `research/INDEX.md`) — *Parameter registry and its runtime accessors (the worked example of the params rule).*
- [`research/probe`](research/INDEX.md#L43-L53) (lines 43–53 in `research/INDEX.md`) — *Example production package: a dependency-free plan builder.*

### [`scripts/INDEX.md`](scripts/INDEX.md) — 15 modules | 120 symbols

- [`scripts/setup`](scripts/INDEX.md#L16-L90) (lines 16–90 in `scripts/INDEX.md`) — *Framework wiring, scaffolding, and hook installation tools.*
- [`scripts/slurm_queue`](scripts/INDEX.md#L91-L281) (lines 91–281 in `scripts/INDEX.md`) — *Durable draining queue for Research sbatch jobs (model, store, submit, CLI, worker).*
- [`scripts/slurm_queue/worker`](scripts/INDEX.md#L282-L372) (lines 282–372 in `scripts/INDEX.md`) — *Drain one Slurm lane allocation.*

