# Research Codebase Master Index

> [!NOTE]
> Master architectural directory. Sub-indices are maintained for major subtrees. Use the sub-index links and line ranges below to load target sections into context.

**Repository Statistics**: 84 modules | 34 classes | 586 public functions.

## Master Table of Contents

### [`experiments/INDEX.md`](experiments/INDEX.md) — 1 modules | 2 symbols

- [`experiments/example_plan`](experiments/INDEX.md#L14-L22) (lines 14–22 in `experiments/INDEX.md`)

### [`framework/INDEX.md`](framework/INDEX.md) — 65 modules | 485 symbols

- [`framework`](framework/INDEX.md#L33-L57) (lines 33–57 in `framework/INDEX.md`) — *Repository gate framework (hooks + checkers).*
- [`framework/gates`](framework/INDEX.md#L58-L85) (lines 58–85 in `framework/INDEX.md`) — *Blocking and advisory repository gates.*
- [`framework/gates/antipattern`](framework/INDEX.md#L86-L115) (lines 86–115 in `framework/INDEX.md`) — *Internals of the production anti-pattern gate.*
- [`framework/gates/checks`](framework/INDEX.md#L116-L188) (lines 116–188 in `framework/INDEX.md`) — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*
- [`framework/gates/coverage`](framework/INDEX.md#L189-L246) (lines 189–246 in `framework/INDEX.md`) — *Internals of the per-file coverage and loop-iteration gate.*
- [`framework/gates/distortion`](framework/INDEX.md#L247-L293) (lines 247–293 in `framework/INDEX.md`) — *Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.*
- [`framework/gates/freshness`](framework/INDEX.md#L294-L325) (lines 294–325 in `framework/INDEX.md`)
- [`framework/gates/limits`](framework/INDEX.md#L326-L383) (lines 326–383 in `framework/INDEX.md`)
- [`framework/gates/mutation`](framework/INDEX.md#L384-L452) (lines 384–452 in `framework/INDEX.md`) — *Mutation-evidence gate: content-addressed mutmut verdicts for staged modules.*
- [`framework/gates/params`](framework/INDEX.md#L453-L493) (lines 453–493 in `framework/INDEX.md`) — *Parameter-drift gate package: registry matchers, CLI and their fixtures.*
- [`framework/gates/params/primitives`](framework/INDEX.md#L494-L498) (lines 494–498 in `framework/INDEX.md`) — *Pure AST and text primitives of the parameter-drift matchers.*
- [`framework/gates/provenance`](framework/INDEX.md#L499-L535) (lines 499–535 in `framework/INDEX.md`) — *Run-provenance gates: GPU canary, run manifest, replay verification, MLflow log.*
- [`framework/indexing`](framework/INDEX.md#L536-L587) (lines 536–587 in `framework/INDEX.md`) — *AST-based repository mapping and Table-of-Contents indexing.*
- [`framework/tests`](framework/INDEX.md#L588-L718) (lines 588–718 in `framework/INDEX.md`)
- [`framework/tests/coverage_gate`](framework/INDEX.md#L719-L729) (lines 719–729 in `framework/INDEX.md`) — *Tests for the coverage gate and its probe plugin.*
- [`framework/tests/distortion`](framework/INDEX.md#L730-L756) (lines 730–756 in `framework/INDEX.md`) — *Test package for the framework distortion gate.*
- [`framework/tests/gates`](framework/INDEX.md#L757-L867) (lines 757–867 in `framework/INDEX.md`) — *Package.*
- [`framework/tests/gates/params`](framework/INDEX.md#L868-L926) (lines 868–926 in `framework/INDEX.md`) — *Tests for the parameter registry gates.*
- [`framework/tests/harness`](framework/INDEX.md#L927-L942) (lines 927–942 in `framework/INDEX.md`) — *Harness registry tests: project identity and the interpreter floor.*
- [`framework/tests/indexing`](framework/INDEX.md#L943-L991) (lines 943–991 in `framework/INDEX.md`) — *Tests for framework.indexing Table-of-Contents subsystem.*

### [`research/INDEX.md`](research/INDEX.md) — 3 modules | 13 symbols

- [`research/params`](research/INDEX.md#L15-L42) (lines 15–42 in `research/INDEX.md`) — *Parameter registry and its runtime accessors (the worked example of the params rule).*
- [`research/probe`](research/INDEX.md#L43-L53) (lines 43–53 in `research/INDEX.md`) — *Example production package: a dependency-free plan builder.*

### [`scripts/INDEX.md`](scripts/INDEX.md) — 15 modules | 120 symbols

- [`scripts/setup`](scripts/INDEX.md#L16-L90) (lines 16–90 in `scripts/INDEX.md`) — *Framework wiring, scaffolding, and hook installation tools.*
- [`scripts/slurm_queue`](scripts/INDEX.md#L91-L281) (lines 91–281 in `scripts/INDEX.md`) — *Durable draining queue for Research sbatch jobs (model, store, submit, CLI, worker).*
- [`scripts/slurm_queue/worker`](scripts/INDEX.md#L282-L372) (lines 282–372 in `scripts/INDEX.md`) — *Drain one Slurm lane allocation.*

