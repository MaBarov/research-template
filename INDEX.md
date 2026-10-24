# Research Codebase Master Index

> [!NOTE]
> Master architectural directory. Sub-indices are maintained for major subtrees. Use the sub-index links and line ranges below to load target sections into context.

**Repository Statistics**: 98 modules | 41 classes | 725 public functions.

## Master Table of Contents

### [`experiments/INDEX.md`](experiments/INDEX.md) — 1 modules | 2 symbols

- [`experiments/example_plan`](experiments/INDEX.md#L14-L22) (lines 14–22 in `experiments/INDEX.md`)

### [`framework/INDEX.md`](framework/INDEX.md) — 79 modules | 631 symbols

- [`framework`](framework/INDEX.md#L40-L64) (lines 40–64 in `framework/INDEX.md`) — *Repository gate framework (hooks + checkers).*
- [`framework/gates`](framework/INDEX.md#L65-L92) (lines 65–92 in `framework/INDEX.md`) — *Blocking and advisory repository gates.*
- [`framework/gates/antipattern`](framework/INDEX.md#L93-L126) (lines 93–126 in `framework/INDEX.md`) — *Internals of the production anti-pattern gate.*
- [`framework/gates/antipattern/execution`](framework/INDEX.md#L127-L135) (lines 127–135 in `framework/INDEX.md`) — *Execution-sink anti-patterns for the production gate (HNS081, HNS082).*
- [`framework/gates/antipattern/liveness`](framework/INDEX.md#L136-L142) (lines 136–142 in `framework/INDEX.md`) — *Liveness checks for the production anti-pattern gate (HNS072).*
- [`framework/gates/checks`](framework/INDEX.md#L143-L227) (lines 143–227 in `framework/INDEX.md`) — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*
- [`framework/gates/coverage`](framework/INDEX.md#L228-L287) (lines 228–287 in `framework/INDEX.md`) — *Internals of the per-file coverage and loop-iteration gate.*
- [`framework/gates/distortion`](framework/INDEX.md#L288-L334) (lines 288–334 in `framework/INDEX.md`) — *Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.*
- [`framework/gates/freshness`](framework/INDEX.md#L335-L366) (lines 335–366 in `framework/INDEX.md`) — *Freshness and ref-provenance gates.*
- [`framework/gates/instructions`](framework/INDEX.md#L367-L384) (lines 367–384 in `framework/INDEX.md`) — *Fail-closed reference check for agent instruction artifacts.*
- [`framework/gates/limits`](framework/INDEX.md#L385-L442) (lines 385–442 in `framework/INDEX.md`)
- [`framework/gates/mutation`](framework/INDEX.md#L443-L548) (lines 443–548 in `framework/INDEX.md`) — *Mutation-evidence gate: content-addressed mutmut verdicts for staged modules.*
- [`framework/gates/params`](framework/INDEX.md#L549-L589) (lines 549–589 in `framework/INDEX.md`) — *Parameter-drift gate package: registry matchers, CLI and their fixtures.*
- [`framework/gates/params/primitives`](framework/INDEX.md#L590-L594) (lines 590–594 in `framework/INDEX.md`) — *Pure AST and text primitives of the parameter-drift matchers.*
- [`framework/gates/provenance`](framework/INDEX.md#L595-L631) (lines 595–631 in `framework/INDEX.md`) — *Run-provenance gates: GPU canary, run manifest, replay verification, MLflow log.*
- [`framework/gates/typecheck`](framework/INDEX.md#L632-L699) (lines 632–699 in `framework/INDEX.md`) — *Static-type gate: staged mypy enforcement with an advisory pyright census.*
- [`framework/indexing`](framework/INDEX.md#L700-L751) (lines 700–751 in `framework/INDEX.md`) — *AST-based repository mapping and Table-of-Contents indexing.*
- [`framework/tests`](framework/INDEX.md#L752-L910) (lines 752–910 in `framework/INDEX.md`)
- [`framework/tests/antipattern`](framework/INDEX.md#L911-L998) (lines 911–998 in `framework/INDEX.md`) — *Anti-pattern extension tests (HNS066/067/069/072/081/082).*
- [`framework/tests/coverage_gate`](framework/INDEX.md#L999-L1009) (lines 999–1009 in `framework/INDEX.md`) — *Tests for the coverage gate and its probe plugin.*
- [`framework/tests/distortion`](framework/INDEX.md#L1010-L1036) (lines 1010–1036 in `framework/INDEX.md`) — *Test package for the framework distortion gate.*
- [`framework/tests/gates`](framework/INDEX.md#L1037-L1147) (lines 1037–1147 in `framework/INDEX.md`) — *Package.*
- [`framework/tests/gates/params`](framework/INDEX.md#L1148-L1206) (lines 1148–1206 in `framework/INDEX.md`) — *Tests for the parameter registry gates.*
- [`framework/tests/gates/ratchet`](framework/INDEX.md#L1207-L1229) (lines 1207–1229 in `framework/INDEX.md`) — *Ratchet gates: tables that may only shrink.*
- [`framework/tests/harness`](framework/INDEX.md#L1230-L1246) (lines 1230–1246 in `framework/INDEX.md`) — *Harness registry tests: project identity and the interpreter floor.*
- [`framework/tests/hook_hygiene`](framework/INDEX.md#L1247-L1255) (lines 1247–1255 in `framework/INDEX.md`) — *Tests for the hook/test-process boundary.*
- [`framework/tests/indexing`](framework/INDEX.md#L1256-L1304) (lines 1256–1304 in `framework/INDEX.md`) — *Tests for framework.indexing Table-of-Contents subsystem.*

### [`research/INDEX.md`](research/INDEX.md) — 3 modules | 13 symbols

- [`research/params`](research/INDEX.md#L15-L42) (lines 15–42 in `research/INDEX.md`) — *Parameter registry and its runtime accessors (the worked example of the params rule).*
- [`research/probe`](research/INDEX.md#L43-L53) (lines 43–53 in `research/INDEX.md`) — *Example production package: a dependency-free plan builder.*

### [`scripts/INDEX.md`](scripts/INDEX.md) — 15 modules | 120 symbols

- [`scripts/setup`](scripts/INDEX.md#L16-L90) (lines 16–90 in `scripts/INDEX.md`) — *Framework wiring, scaffolding, and hook installation tools.*
- [`scripts/slurm_queue`](scripts/INDEX.md#L91-L281) (lines 91–281 in `scripts/INDEX.md`) — *Durable draining queue for Research sbatch jobs (model, store, submit, CLI, worker).*
- [`scripts/slurm_queue/worker`](scripts/INDEX.md#L282-L372) (lines 282–372 in `scripts/INDEX.md`) — *Drain one Slurm lane allocation.*

