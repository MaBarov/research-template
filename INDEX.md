# Research Codebase Master Index

> [!NOTE]
> Master architectural directory. Sub-indices are maintained for major subtrees. Use the sub-index links and line ranges below to load target sections into context.

**Repository Statistics**: 102 modules | 42 classes | 801 public functions.

## Master Table of Contents

### [`experiments/INDEX.md`](experiments/INDEX.md) — 1 modules | 2 symbols

- [`experiments/example_plan`](experiments/INDEX.md#L14-L22) (lines 14–22 in `experiments/INDEX.md`)

### [`framework/INDEX.md`](framework/INDEX.md) — 83 modules | 708 symbols

- [`framework`](framework/INDEX.md#L43-L67) (lines 43–67 in `framework/INDEX.md`) — *Repository gate framework (hooks + checkers).*
- [`framework/gates`](framework/INDEX.md#L68-L95) (lines 68–95 in `framework/INDEX.md`) — *Blocking and advisory repository gates.*
- [`framework/gates/antipattern`](framework/INDEX.md#L96-L129) (lines 96–129 in `framework/INDEX.md`) — *Internals of the production anti-pattern gate.*
- [`framework/gates/antipattern/execution`](framework/INDEX.md#L130-L138) (lines 130–138 in `framework/INDEX.md`) — *Execution-sink anti-patterns for the production gate (HNS081, HNS082).*
- [`framework/gates/antipattern/liveness`](framework/INDEX.md#L139-L145) (lines 139–145 in `framework/INDEX.md`) — *Liveness checks for the production anti-pattern gate (HNS072).*
- [`framework/gates/checks`](framework/INDEX.md#L146-L230) (lines 146–230 in `framework/INDEX.md`) — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*
- [`framework/gates/coverage`](framework/INDEX.md#L231-L290) (lines 231–290 in `framework/INDEX.md`) — *Internals of the per-file coverage and loop-iteration gate.*
- [`framework/gates/distortion`](framework/INDEX.md#L291-L337) (lines 291–337 in `framework/INDEX.md`) — *Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.*
- [`framework/gates/freshness`](framework/INDEX.md#L338-L376) (lines 338–376 in `framework/INDEX.md`) — *Freshness and ref-provenance gates.*
- [`framework/gates/instructions`](framework/INDEX.md#L377-L394) (lines 377–394 in `framework/INDEX.md`) — *Fail-closed reference check for agent instruction artifacts.*
- [`framework/gates/limits`](framework/INDEX.md#L395-L452) (lines 395–452 in `framework/INDEX.md`)
- [`framework/gates/mutation`](framework/INDEX.md#L453-L558) (lines 453–558 in `framework/INDEX.md`) — *Mutation-evidence gate: content-addressed mutmut verdicts for staged modules.*
- [`framework/gates/params`](framework/INDEX.md#L559-L599) (lines 559–599 in `framework/INDEX.md`) — *Parameter-drift gate package: registry matchers, CLI and their fixtures.*
- [`framework/gates/params/primitives`](framework/INDEX.md#L600-L604) (lines 600–604 in `framework/INDEX.md`) — *Pure AST and text primitives of the parameter-drift matchers.*
- [`framework/gates/provenance`](framework/INDEX.md#L605-L641) (lines 605–641 in `framework/INDEX.md`) — *Run-provenance gates: GPU canary, run manifest, replay verification, MLflow log.*
- [`framework/gates/typecheck`](framework/INDEX.md#L642-L720) (lines 642–720 in `framework/INDEX.md`) — *Static-type gate: staged mypy enforcement with an advisory pyright census.*
- [`framework/indexing`](framework/INDEX.md#L721-L772) (lines 721–772 in `framework/INDEX.md`) — *AST-based repository mapping and Table-of-Contents indexing.*
- [`framework/tests`](framework/INDEX.md#L773-L931) (lines 773–931 in `framework/INDEX.md`)
- [`framework/tests/antipattern`](framework/INDEX.md#L932-L1019) (lines 932–1019 in `framework/INDEX.md`) — *Anti-pattern extension tests (HNS066/067/069/072/081/082).*
- [`framework/tests/coverage_gate`](framework/INDEX.md#L1020-L1030) (lines 1020–1030 in `framework/INDEX.md`) — *Tests for the coverage gate and its probe plugin.*
- [`framework/tests/distortion`](framework/INDEX.md#L1031-L1057) (lines 1031–1057 in `framework/INDEX.md`) — *Test package for the framework distortion gate.*
- [`framework/tests/freshness`](framework/INDEX.md#L1058-L1110) (lines 1058–1110 in `framework/INDEX.md`) — *Tests for freshness and ref guard gates.*
- [`framework/tests/gates`](framework/INDEX.md#L1111-L1223) (lines 1111–1223 in `framework/INDEX.md`) — *Package.*
- [`framework/tests/gates/instructions`](framework/INDEX.md#L1224-L1263) (lines 1224–1263 in `framework/INDEX.md`) — *Tests for instruction reference validation.*
- [`framework/tests/gates/params`](framework/INDEX.md#L1264-L1322) (lines 1264–1322 in `framework/INDEX.md`) — *Tests for the parameter registry gates.*
- [`framework/tests/gates/ratchet`](framework/INDEX.md#L1323-L1345) (lines 1323–1345 in `framework/INDEX.md`) — *Ratchet gates: tables that may only shrink.*
- [`framework/tests/harness`](framework/INDEX.md#L1346-L1362) (lines 1346–1362 in `framework/INDEX.md`) — *Harness registry tests: project identity and the interpreter floor.*
- [`framework/tests/hook_hygiene`](framework/INDEX.md#L1363-L1371) (lines 1363–1371 in `framework/INDEX.md`) — *Tests for the hook/test-process boundary.*
- [`framework/tests/indexing`](framework/INDEX.md#L1372-L1420) (lines 1372–1420 in `framework/INDEX.md`) — *Tests for framework.indexing Table-of-Contents subsystem.*
- [`framework/tests/typecheck`](framework/INDEX.md#L1421-L1471) (lines 1421–1471 in `framework/INDEX.md`) — *Tests for the static-type gate.*

### [`research/INDEX.md`](research/INDEX.md) — 3 modules | 13 symbols

- [`research/params`](research/INDEX.md#L15-L42) (lines 15–42 in `research/INDEX.md`) — *Parameter registry and its runtime accessors (the worked example of the params rule).*
- [`research/probe`](research/INDEX.md#L43-L53) (lines 43–53 in `research/INDEX.md`) — *Example production package: a dependency-free plan builder.*

### [`scripts/INDEX.md`](scripts/INDEX.md) — 15 modules | 120 symbols

- [`scripts/setup`](scripts/INDEX.md#L16-L90) (lines 16–90 in `scripts/INDEX.md`) — *Framework wiring, scaffolding, and hook installation tools.*
- [`scripts/slurm_queue`](scripts/INDEX.md#L91-L281) (lines 91–281 in `scripts/INDEX.md`) — *Durable draining queue for Research sbatch jobs (model, store, submit, CLI, worker).*
- [`scripts/slurm_queue/worker`](scripts/INDEX.md#L282-L372) (lines 282–372 in `scripts/INDEX.md`) — *Drain one Slurm lane allocation.*

