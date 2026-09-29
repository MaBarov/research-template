# Research Codebase Master Index

> [!NOTE]
> Master architectural directory. Sub-indices are maintained for major subtrees. Use the sub-index links and line ranges below to load target sections into context.

**Repository Statistics**: 83 modules | 34 classes | 574 public functions.

## Master Table of Contents

### [`experiments/INDEX.md`](experiments/INDEX.md) — 1 modules | 2 symbols

- [`experiments/example_plan`](experiments/INDEX.md#L14-L22) (lines 14–22 in `experiments/INDEX.md`)

### [`framework/INDEX.md`](framework/INDEX.md) — 65 modules | 478 symbols

- [`framework`](framework/INDEX.md#L33-L55) (lines 33–55 in `framework/INDEX.md`) — *Repository gate framework (hooks + checkers).*
- [`framework/gates`](framework/INDEX.md#L56-L83) (lines 56–83 in `framework/INDEX.md`) — *Blocking and advisory repository gates.*
- [`framework/gates/antipattern`](framework/INDEX.md#L84-L113) (lines 84–113 in `framework/INDEX.md`) — *Internals of the production anti-pattern gate.*
- [`framework/gates/checks`](framework/INDEX.md#L114-L186) (lines 114–186 in `framework/INDEX.md`) — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*
- [`framework/gates/coverage`](framework/INDEX.md#L187-L244) (lines 187–244 in `framework/INDEX.md`) — *Internals of the per-file coverage and loop-iteration gate.*
- [`framework/gates/distortion`](framework/INDEX.md#L245-L291) (lines 245–291 in `framework/INDEX.md`) — *Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.*
- [`framework/gates/freshness`](framework/INDEX.md#L292-L323) (lines 292–323 in `framework/INDEX.md`)
- [`framework/gates/limits`](framework/INDEX.md#L324-L381) (lines 324–381 in `framework/INDEX.md`)
- [`framework/gates/mutation`](framework/INDEX.md#L382-L450) (lines 382–450 in `framework/INDEX.md`) — *Mutation-evidence gate: content-addressed mutmut verdicts for staged modules.*
- [`framework/gates/params`](framework/INDEX.md#L451-L491) (lines 451–491 in `framework/INDEX.md`) — *Parameter-drift gate package: registry matchers, CLI and their fixtures.*
- [`framework/gates/params/primitives`](framework/INDEX.md#L492-L496) (lines 492–496 in `framework/INDEX.md`) — *Pure AST and text primitives of the parameter-drift matchers.*
- [`framework/gates/provenance`](framework/INDEX.md#L497-L533) (lines 497–533 in `framework/INDEX.md`) — *Run-provenance gates: GPU canary, run manifest, replay verification, MLflow log.*
- [`framework/indexing`](framework/INDEX.md#L534-L585) (lines 534–585 in `framework/INDEX.md`) — *AST-based repository mapping and Table-of-Contents indexing.*
- [`framework/tests`](framework/INDEX.md#L586-L716) (lines 586–716 in `framework/INDEX.md`)
- [`framework/tests/coverage_gate`](framework/INDEX.md#L717-L727) (lines 717–727 in `framework/INDEX.md`) — *Tests for the coverage gate and its probe plugin.*
- [`framework/tests/distortion`](framework/INDEX.md#L728-L754) (lines 728–754 in `framework/INDEX.md`) — *Test package for the framework distortion gate.*
- [`framework/tests/gates`](framework/INDEX.md#L755-L865) (lines 755–865 in `framework/INDEX.md`) — *Package.*
- [`framework/tests/gates/params`](framework/INDEX.md#L866-L924) (lines 866–924 in `framework/INDEX.md`) — *Tests for the parameter registry gates.*
- [`framework/tests/harness`](framework/INDEX.md#L925-L934) (lines 925–934 in `framework/INDEX.md`) — *Harness registry tests: project identity and the interpreter floor.*
- [`framework/tests/indexing`](framework/INDEX.md#L935-L983) (lines 935–983 in `framework/INDEX.md`) — *Tests for framework.indexing Table-of-Contents subsystem.*

### [`research/INDEX.md`](research/INDEX.md) — 3 modules | 13 symbols

- [`research/params`](research/INDEX.md#L15-L42) (lines 15–42 in `research/INDEX.md`) — *Parameter registry and its runtime accessors (the worked example of the params rule).*
- [`research/probe`](research/INDEX.md#L43-L53) (lines 43–53 in `research/INDEX.md`) — *Example production package: a dependency-free plan builder.*

### [`scripts/INDEX.md`](scripts/INDEX.md) — 14 modules | 115 symbols

- [`scripts/setup`](scripts/INDEX.md#L16-L77) (lines 16–77 in `scripts/INDEX.md`) — *Framework wiring, scaffolding, and hook installation tools.*
- [`scripts/slurm_queue`](scripts/INDEX.md#L78-L268) (lines 78–268 in `scripts/INDEX.md`) — *Durable draining queue for Research sbatch jobs (model, store, submit, CLI, worker).*
- [`scripts/slurm_queue/worker`](scripts/INDEX.md#L269-L359) (lines 269–359 in `scripts/INDEX.md`) — *Drain one Slurm lane allocation.*

