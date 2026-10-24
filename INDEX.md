# Research Codebase Master Index

> [!NOTE]
> Master architectural directory. Sub-indices are maintained for major subtrees. Use the sub-index links and line ranges below to load target sections into context.

**Repository Statistics**: 101 modules | 42 classes | 748 public functions.

## Master Table of Contents

### [`experiments/INDEX.md`](experiments/INDEX.md) — 1 modules | 2 symbols

- [`experiments/example_plan`](experiments/INDEX.md#L14-L22) (lines 14–22 in `experiments/INDEX.md`)

### [`framework/INDEX.md`](framework/INDEX.md) — 82 modules | 655 symbols

- [`framework`](framework/INDEX.md#L42-L66) (lines 42–66 in `framework/INDEX.md`) — *Repository gate framework (hooks + checkers).*
- [`framework/gates`](framework/INDEX.md#L67-L94) (lines 67–94 in `framework/INDEX.md`) — *Blocking and advisory repository gates.*
- [`framework/gates/antipattern`](framework/INDEX.md#L95-L128) (lines 95–128 in `framework/INDEX.md`) — *Internals of the production anti-pattern gate.*
- [`framework/gates/antipattern/execution`](framework/INDEX.md#L129-L137) (lines 129–137 in `framework/INDEX.md`) — *Execution-sink anti-patterns for the production gate (HNS081, HNS082).*
- [`framework/gates/antipattern/liveness`](framework/INDEX.md#L138-L144) (lines 138–144 in `framework/INDEX.md`) — *Liveness checks for the production anti-pattern gate (HNS072).*
- [`framework/gates/checks`](framework/INDEX.md#L145-L229) (lines 145–229 in `framework/INDEX.md`) — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*
- [`framework/gates/coverage`](framework/INDEX.md#L230-L289) (lines 230–289 in `framework/INDEX.md`) — *Internals of the per-file coverage and loop-iteration gate.*
- [`framework/gates/distortion`](framework/INDEX.md#L290-L336) (lines 290–336 in `framework/INDEX.md`) — *Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.*
- [`framework/gates/freshness`](framework/INDEX.md#L337-L375) (lines 337–375 in `framework/INDEX.md`) — *Freshness and ref-provenance gates.*
- [`framework/gates/instructions`](framework/INDEX.md#L376-L393) (lines 376–393 in `framework/INDEX.md`) — *Fail-closed reference check for agent instruction artifacts.*
- [`framework/gates/limits`](framework/INDEX.md#L394-L451) (lines 394–451 in `framework/INDEX.md`)
- [`framework/gates/mutation`](framework/INDEX.md#L452-L557) (lines 452–557 in `framework/INDEX.md`) — *Mutation-evidence gate: content-addressed mutmut verdicts for staged modules.*
- [`framework/gates/params`](framework/INDEX.md#L558-L598) (lines 558–598 in `framework/INDEX.md`) — *Parameter-drift gate package: registry matchers, CLI and their fixtures.*
- [`framework/gates/params/primitives`](framework/INDEX.md#L599-L603) (lines 599–603 in `framework/INDEX.md`) — *Pure AST and text primitives of the parameter-drift matchers.*
- [`framework/gates/provenance`](framework/INDEX.md#L604-L640) (lines 604–640 in `framework/INDEX.md`) — *Run-provenance gates: GPU canary, run manifest, replay verification, MLflow log.*
- [`framework/gates/typecheck`](framework/INDEX.md#L641-L708) (lines 641–708 in `framework/INDEX.md`) — *Static-type gate: staged mypy enforcement with an advisory pyright census.*
- [`framework/indexing`](framework/INDEX.md#L709-L760) (lines 709–760 in `framework/INDEX.md`) — *AST-based repository mapping and Table-of-Contents indexing.*
- [`framework/tests`](framework/INDEX.md#L761-L919) (lines 761–919 in `framework/INDEX.md`)
- [`framework/tests/antipattern`](framework/INDEX.md#L920-L1007) (lines 920–1007 in `framework/INDEX.md`) — *Anti-pattern extension tests (HNS066/067/069/072/081/082).*
- [`framework/tests/coverage_gate`](framework/INDEX.md#L1008-L1018) (lines 1008–1018 in `framework/INDEX.md`) — *Tests for the coverage gate and its probe plugin.*
- [`framework/tests/distortion`](framework/INDEX.md#L1019-L1045) (lines 1019–1045 in `framework/INDEX.md`) — *Test package for the framework distortion gate.*
- [`framework/tests/freshness`](framework/INDEX.md#L1046-L1049) (lines 1046–1049 in `framework/INDEX.md`) — *Tests for freshness and ref guard gates.*
- [`framework/tests/gates`](framework/INDEX.md#L1050-L1160) (lines 1050–1160 in `framework/INDEX.md`) — *Package.*
- [`framework/tests/gates/instructions`](framework/INDEX.md#L1161-L1200) (lines 1161–1200 in `framework/INDEX.md`) — *Tests for instruction reference validation.*
- [`framework/tests/gates/params`](framework/INDEX.md#L1201-L1259) (lines 1201–1259 in `framework/INDEX.md`) — *Tests for the parameter registry gates.*
- [`framework/tests/gates/ratchet`](framework/INDEX.md#L1260-L1282) (lines 1260–1282 in `framework/INDEX.md`) — *Ratchet gates: tables that may only shrink.*
- [`framework/tests/harness`](framework/INDEX.md#L1283-L1299) (lines 1283–1299 in `framework/INDEX.md`) — *Harness registry tests: project identity and the interpreter floor.*
- [`framework/tests/hook_hygiene`](framework/INDEX.md#L1300-L1308) (lines 1300–1308 in `framework/INDEX.md`) — *Tests for the hook/test-process boundary.*
- [`framework/tests/indexing`](framework/INDEX.md#L1309-L1357) (lines 1309–1357 in `framework/INDEX.md`) — *Tests for framework.indexing Table-of-Contents subsystem.*

### [`research/INDEX.md`](research/INDEX.md) — 3 modules | 13 symbols

- [`research/params`](research/INDEX.md#L15-L42) (lines 15–42 in `research/INDEX.md`) — *Parameter registry and its runtime accessors (the worked example of the params rule).*
- [`research/probe`](research/INDEX.md#L43-L53) (lines 43–53 in `research/INDEX.md`) — *Example production package: a dependency-free plan builder.*

### [`scripts/INDEX.md`](scripts/INDEX.md) — 15 modules | 120 symbols

- [`scripts/setup`](scripts/INDEX.md#L16-L90) (lines 16–90 in `scripts/INDEX.md`) — *Framework wiring, scaffolding, and hook installation tools.*
- [`scripts/slurm_queue`](scripts/INDEX.md#L91-L281) (lines 91–281 in `scripts/INDEX.md`) — *Durable draining queue for Research sbatch jobs (model, store, submit, CLI, worker).*
- [`scripts/slurm_queue/worker`](scripts/INDEX.md#L282-L372) (lines 282–372 in `scripts/INDEX.md`) — *Drain one Slurm lane allocation.*

