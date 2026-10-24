# Research Codebase Master Index

> [!NOTE]
> Master architectural directory. Sub-indices are maintained for major subtrees. Use the sub-index links and line ranges below to load target sections into context.

**Repository Statistics**: 118 modules | 48 classes | 875 public functions.

## Master Table of Contents

### [`experiments/INDEX.md`](experiments/INDEX.md) — 1 modules | 2 symbols

- [`experiments/example_plan`](experiments/INDEX.md#L14-L22) (lines 14–22 in `experiments/INDEX.md`)

### [`framework/INDEX.md`](framework/INDEX.md) — 99 modules | 788 symbols

- [`framework`](framework/INDEX.md#L50-L74) (lines 50–74 in `framework/INDEX.md`) — *Repository gate framework (hooks + checkers).*
- [`framework/gates`](framework/INDEX.md#L75-L102) (lines 75–102 in `framework/INDEX.md`) — *Blocking and advisory repository gates.*
- [`framework/gates/advisory`](framework/INDEX.md#L103-L127) (lines 103–127 in `framework/INDEX.md`) — *Advisory static gates shared model and runner package.*
- [`framework/gates/antipattern`](framework/INDEX.md#L128-L161) (lines 128–161 in `framework/INDEX.md`) — *Internals of the production anti-pattern gate.*
- [`framework/gates/antipattern/execution`](framework/INDEX.md#L162-L170) (lines 162–170 in `framework/INDEX.md`) — *Execution-sink anti-patterns for the production gate (HNS081, HNS082).*
- [`framework/gates/antipattern/liveness`](framework/INDEX.md#L171-L177) (lines 171–177 in `framework/INDEX.md`) — *Liveness checks for the production anti-pattern gate (HNS072).*
- [`framework/gates/checks`](framework/INDEX.md#L178-L262) (lines 178–262 in `framework/INDEX.md`) — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*
- [`framework/gates/coverage`](framework/INDEX.md#L263-L322) (lines 263–322 in `framework/INDEX.md`) — *Internals of the per-file coverage and loop-iteration gate.*
- [`framework/gates/distortion`](framework/INDEX.md#L323-L367) (lines 323–367 in `framework/INDEX.md`) — *Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.*
- [`framework/gates/freshness`](framework/INDEX.md#L368-L406) (lines 368–406 in `framework/INDEX.md`) — *Freshness and ref-provenance gates.*
- [`framework/gates/instructions`](framework/INDEX.md#L407-L424) (lines 407–424 in `framework/INDEX.md`) — *Fail-closed reference check for agent instruction artifacts.*
- [`framework/gates/limits`](framework/INDEX.md#L425-L482) (lines 425–482 in `framework/INDEX.md`)
- [`framework/gates/mutation`](framework/INDEX.md#L483-L588) (lines 483–588 in `framework/INDEX.md`) — *Mutation-evidence gate: content-addressed mutmut verdicts for staged modules.*
- [`framework/gates/params`](framework/INDEX.md#L589-L629) (lines 589–629 in `framework/INDEX.md`) — *Parameter-drift gate package: registry matchers, CLI and their fixtures.*
- [`framework/gates/params/primitives`](framework/INDEX.md#L630-L634) (lines 630–634 in `framework/INDEX.md`) — *Pure AST and text primitives of the parameter-drift matchers.*
- [`framework/gates/provenance`](framework/INDEX.md#L635-L671) (lines 635–671 in `framework/INDEX.md`) — *Run-provenance gates: GPU canary, run manifest, replay verification, MLflow log.*
- [`framework/gates/static`](framework/INDEX.md#L672-L684) (lines 672–684 in `framework/INDEX.md`) — *Shared plumbing for the static-analysis gates.*
- [`framework/gates/transfers`](framework/INDEX.md#L685-L771) (lines 685–771 in `framework/INDEX.md`) — *Device transfer bottleneck detection package.*
- [`framework/gates/transfers/provenance`](framework/INDEX.md#L772-L787) (lines 772–787 in `framework/INDEX.md`) — *Device provenance inference for the host-device transfer gate.*
- [`framework/gates/traversal`](framework/INDEX.md#L788-L798) (lines 788–798 in `framework/INDEX.md`) — *Shared AST traversal helpers for the gate visitors.*
- [`framework/gates/typecheck`](framework/INDEX.md#L799-L877) (lines 799–877 in `framework/INDEX.md`) — *Static-type gate: staged mypy enforcement with an advisory pyright census.*
- [`framework/indexing`](framework/INDEX.md#L878-L929) (lines 878–929 in `framework/INDEX.md`) — *AST-based repository mapping and Table-of-Contents indexing.*
- [`framework/tests`](framework/INDEX.md#L930-L1101) (lines 930–1101 in `framework/INDEX.md`)
- [`framework/tests/antipattern`](framework/INDEX.md#L1102-L1189) (lines 1102–1189 in `framework/INDEX.md`) — *Anti-pattern extension tests (HNS066/067/069/072/081/082).*
- [`framework/tests/coverage_gate`](framework/INDEX.md#L1190-L1200) (lines 1190–1200 in `framework/INDEX.md`) — *Tests for the coverage gate and its probe plugin.*
- [`framework/tests/distortion`](framework/INDEX.md#L1201-L1227) (lines 1201–1227 in `framework/INDEX.md`) — *Test package for the framework distortion gate.*
- [`framework/tests/freshness`](framework/INDEX.md#L1228-L1280) (lines 1228–1280 in `framework/INDEX.md`) — *Tests for freshness and ref guard gates.*
- [`framework/tests/gates`](framework/INDEX.md#L1281-L1393) (lines 1281–1393 in `framework/INDEX.md`) — *Package.*
- [`framework/tests/gates/instructions`](framework/INDEX.md#L1394-L1433) (lines 1394–1433 in `framework/INDEX.md`) — *Tests for instruction reference validation.*
- [`framework/tests/gates/params`](framework/INDEX.md#L1434-L1492) (lines 1434–1492 in `framework/INDEX.md`) — *Tests for the parameter registry gates.*
- [`framework/tests/gates/ratchet`](framework/INDEX.md#L1493-L1515) (lines 1493–1515 in `framework/INDEX.md`) — *Ratchet gates: tables that may only shrink.*
- [`framework/tests/harness`](framework/INDEX.md#L1516-L1532) (lines 1516–1532 in `framework/INDEX.md`) — *Harness registry tests: project identity and the interpreter floor.*
- [`framework/tests/hook_hygiene`](framework/INDEX.md#L1533-L1541) (lines 1533–1541 in `framework/INDEX.md`) — *Tests for the hook/test-process boundary.*
- [`framework/tests/indexing`](framework/INDEX.md#L1542-L1590) (lines 1542–1590 in `framework/INDEX.md`) — *Tests for framework.indexing Table-of-Contents subsystem.*
- [`framework/tests/transfers`](framework/INDEX.md#L1591-L1680) (lines 1591–1680 in `framework/INDEX.md`) — *Test package for device transfer bottleneck gate.*
- [`framework/tests/transfers/provenance`](framework/INDEX.md#L1681-L1698) (lines 1681–1698 in `framework/INDEX.md`) — *Test package for device provenance inference and mixing detection.*
- [`framework/tests/typecheck`](framework/INDEX.md#L1699-L1749) (lines 1699–1749 in `framework/INDEX.md`) — *Tests for the static-type gate.*

### [`research/INDEX.md`](research/INDEX.md) — 3 modules | 13 symbols

- [`research/params`](research/INDEX.md#L15-L42) (lines 15–42 in `research/INDEX.md`) — *Parameter registry and its runtime accessors (the worked example of the params rule).*
- [`research/probe`](research/INDEX.md#L43-L53) (lines 43–53 in `research/INDEX.md`) — *Example production package: a dependency-free plan builder.*

### [`scripts/INDEX.md`](scripts/INDEX.md) — 15 modules | 120 symbols

- [`scripts/setup`](scripts/INDEX.md#L16-L90) (lines 16–90 in `scripts/INDEX.md`) — *Framework wiring, scaffolding, and hook installation tools.*
- [`scripts/slurm_queue`](scripts/INDEX.md#L91-L281) (lines 91–281 in `scripts/INDEX.md`) — *Durable draining queue for Research sbatch jobs (model, store, submit, CLI, worker).*
- [`scripts/slurm_queue/worker`](scripts/INDEX.md#L282-L372) (lines 282–372 in `scripts/INDEX.md`) — *Drain one Slurm lane allocation.*

