# Research Codebase Master Index

> [!NOTE]
> Master architectural directory. Sub-indices are maintained for major subtrees. Use the sub-index links and line ranges below to load target sections into context.

**Repository Statistics**: 90 modules | 34 classes | 668 public functions.

## Master Table of Contents

### [`experiments/INDEX.md`](experiments/INDEX.md) — 1 modules | 2 symbols

- [`experiments/example_plan`](experiments/INDEX.md#L14-L22) (lines 14–22 in `experiments/INDEX.md`)

### [`framework/INDEX.md`](framework/INDEX.md) — 71 modules | 567 symbols

- [`framework`](framework/INDEX.md#L36-L60) (lines 36–60 in `framework/INDEX.md`) — *Repository gate framework (hooks + checkers).*
- [`framework/gates`](framework/INDEX.md#L61-L88) (lines 61–88 in `framework/INDEX.md`) — *Blocking and advisory repository gates.*
- [`framework/gates/antipattern`](framework/INDEX.md#L89-L122) (lines 89–122 in `framework/INDEX.md`) — *Internals of the production anti-pattern gate.*
- [`framework/gates/antipattern/execution`](framework/INDEX.md#L123-L131) (lines 123–131 in `framework/INDEX.md`) — *Execution-sink anti-patterns for the production gate (HNS081, HNS082).*
- [`framework/gates/antipattern/liveness`](framework/INDEX.md#L132-L138) (lines 132–138 in `framework/INDEX.md`) — *Liveness checks for the production anti-pattern gate (HNS072).*
- [`framework/gates/checks`](framework/INDEX.md#L139-L219) (lines 139–219 in `framework/INDEX.md`) — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*
- [`framework/gates/coverage`](framework/INDEX.md#L220-L277) (lines 220–277 in `framework/INDEX.md`) — *Internals of the per-file coverage and loop-iteration gate.*
- [`framework/gates/distortion`](framework/INDEX.md#L278-L324) (lines 278–324 in `framework/INDEX.md`) — *Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.*
- [`framework/gates/freshness`](framework/INDEX.md#L325-L356) (lines 325–356 in `framework/INDEX.md`)
- [`framework/gates/limits`](framework/INDEX.md#L357-L414) (lines 357–414 in `framework/INDEX.md`)
- [`framework/gates/mutation`](framework/INDEX.md#L415-L483) (lines 415–483 in `framework/INDEX.md`) — *Mutation-evidence gate: content-addressed mutmut verdicts for staged modules.*
- [`framework/gates/params`](framework/INDEX.md#L484-L524) (lines 484–524 in `framework/INDEX.md`) — *Parameter-drift gate package: registry matchers, CLI and their fixtures.*
- [`framework/gates/params/primitives`](framework/INDEX.md#L525-L529) (lines 525–529 in `framework/INDEX.md`) — *Pure AST and text primitives of the parameter-drift matchers.*
- [`framework/gates/provenance`](framework/INDEX.md#L530-L566) (lines 530–566 in `framework/INDEX.md`) — *Run-provenance gates: GPU canary, run manifest, replay verification, MLflow log.*
- [`framework/indexing`](framework/INDEX.md#L567-L618) (lines 567–618 in `framework/INDEX.md`) — *AST-based repository mapping and Table-of-Contents indexing.*
- [`framework/tests`](framework/INDEX.md#L619-L775) (lines 619–775 in `framework/INDEX.md`)
- [`framework/tests/antipattern`](framework/INDEX.md#L776-L863) (lines 776–863 in `framework/INDEX.md`) — *Anti-pattern extension tests (HNS066/067/069/072/081/082).*
- [`framework/tests/coverage_gate`](framework/INDEX.md#L864-L874) (lines 864–874 in `framework/INDEX.md`) — *Tests for the coverage gate and its probe plugin.*
- [`framework/tests/distortion`](framework/INDEX.md#L875-L901) (lines 875–901 in `framework/INDEX.md`) — *Test package for the framework distortion gate.*
- [`framework/tests/gates`](framework/INDEX.md#L902-L1012) (lines 902–1012 in `framework/INDEX.md`) — *Package.*
- [`framework/tests/gates/params`](framework/INDEX.md#L1013-L1071) (lines 1013–1071 in `framework/INDEX.md`) — *Tests for the parameter registry gates.*
- [`framework/tests/harness`](framework/INDEX.md#L1072-L1088) (lines 1072–1088 in `framework/INDEX.md`) — *Harness registry tests: project identity and the interpreter floor.*
- [`framework/tests/indexing`](framework/INDEX.md#L1089-L1137) (lines 1089–1137 in `framework/INDEX.md`) — *Tests for framework.indexing Table-of-Contents subsystem.*

### [`research/INDEX.md`](research/INDEX.md) — 3 modules | 13 symbols

- [`research/params`](research/INDEX.md#L15-L42) (lines 15–42 in `research/INDEX.md`) — *Parameter registry and its runtime accessors (the worked example of the params rule).*
- [`research/probe`](research/INDEX.md#L43-L53) (lines 43–53 in `research/INDEX.md`) — *Example production package: a dependency-free plan builder.*

### [`scripts/INDEX.md`](scripts/INDEX.md) — 15 modules | 120 symbols

- [`scripts/setup`](scripts/INDEX.md#L16-L90) (lines 16–90 in `scripts/INDEX.md`) — *Framework wiring, scaffolding, and hook installation tools.*
- [`scripts/slurm_queue`](scripts/INDEX.md#L91-L281) (lines 91–281 in `scripts/INDEX.md`) — *Durable draining queue for Research sbatch jobs (model, store, submit, CLI, worker).*
- [`scripts/slurm_queue/worker`](scripts/INDEX.md#L282-L372) (lines 282–372 in `scripts/INDEX.md`) — *Drain one Slurm lane allocation.*

