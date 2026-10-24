# Research Codebase Master Index

> [!NOTE]
> Master architectural directory. Sub-indices are maintained for major subtrees. Use the sub-index links and line ranges below to load target sections into context.

**Repository Statistics**: 137 modules | 55 classes | 969 public functions.

## Master Table of Contents

### [`experiments/INDEX.md`](experiments/INDEX.md) — 1 modules | 2 symbols

- [`experiments/example_plan`](experiments/INDEX.md#L14-L22) (lines 14–22 in `experiments/INDEX.md`)

### [`framework/INDEX.md`](framework/INDEX.md) — 118 modules | 889 symbols

- [`framework`](framework/INDEX.md#L57-L81) (lines 57–81 in `framework/INDEX.md`) — *Repository gate framework (hooks + checkers).*
- [`framework/gates`](framework/INDEX.md#L82-L109) (lines 82–109 in `framework/INDEX.md`) — *Blocking and advisory repository gates.*
- [`framework/gates/abstract_cost`](framework/INDEX.md#L110-L179) (lines 110–179 in `framework/INDEX.md`) — *Advisory abstract-cost gate package.*
- [`framework/gates/advisory`](framework/INDEX.md#L180-L204) (lines 180–204 in `framework/INDEX.md`) — *Advisory static gates shared model and runner package.*
- [`framework/gates/antipattern`](framework/INDEX.md#L205-L238) (lines 205–238 in `framework/INDEX.md`) — *Internals of the production anti-pattern gate.*
- [`framework/gates/antipattern/execution`](framework/INDEX.md#L239-L247) (lines 239–247 in `framework/INDEX.md`) — *Execution-sink anti-patterns for the production gate (HNS081, HNS082).*
- [`framework/gates/antipattern/liveness`](framework/INDEX.md#L248-L254) (lines 248–254 in `framework/INDEX.md`) — *Liveness checks for the production anti-pattern gate (HNS072).*
- [`framework/gates/checks`](framework/INDEX.md#L255-L339) (lines 255–339 in `framework/INDEX.md`) — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*
- [`framework/gates/coverage`](framework/INDEX.md#L340-L399) (lines 340–399 in `framework/INDEX.md`) — *Internals of the per-file coverage and loop-iteration gate.*
- [`framework/gates/distortion`](framework/INDEX.md#L400-L444) (lines 400–444 in `framework/INDEX.md`) — *Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.*
- [`framework/gates/freshness`](framework/INDEX.md#L445-L483) (lines 445–483 in `framework/INDEX.md`) — *Freshness and ref-provenance gates.*
- [`framework/gates/hotpath`](framework/INDEX.md#L484-L551) (lines 484–551 in `framework/INDEX.md`) — *Advisory GPU/CPU hot-path detection package.*
- [`framework/gates/instructions`](framework/INDEX.md#L552-L569) (lines 552–569 in `framework/INDEX.md`) — *Fail-closed reference check for agent instruction artifacts.*
- [`framework/gates/limits`](framework/INDEX.md#L570-L627) (lines 570–627 in `framework/INDEX.md`)
- [`framework/gates/memory`](framework/INDEX.md#L628-L673) (lines 628–673 in `framework/INDEX.md`) — *Accelerator memory bottleneck detection package.*
- [`framework/gates/memory/rules`](framework/INDEX.md#L674-L713) (lines 674–713 in `framework/INDEX.md`) — *Memory bottleneck rule surface: scope predicates and the HNS083-HNS086 checks.*
- [`framework/gates/mutation`](framework/INDEX.md#L714-L819) (lines 714–819 in `framework/INDEX.md`) — *Mutation-evidence gate: content-addressed mutmut verdicts for staged modules.*
- [`framework/gates/params`](framework/INDEX.md#L820-L860) (lines 820–860 in `framework/INDEX.md`) — *Parameter-drift gate package: registry matchers, CLI and their fixtures.*
- [`framework/gates/params/primitives`](framework/INDEX.md#L861-L865) (lines 861–865 in `framework/INDEX.md`) — *Pure AST and text primitives of the parameter-drift matchers.*
- [`framework/gates/provenance`](framework/INDEX.md#L866-L902) (lines 866–902 in `framework/INDEX.md`) — *Run-provenance gates: GPU canary, run manifest, replay verification, MLflow log.*
- [`framework/gates/static`](framework/INDEX.md#L903-L915) (lines 903–915 in `framework/INDEX.md`) — *Shared plumbing for the static-analysis gates.*
- [`framework/gates/transfers`](framework/INDEX.md#L916-L1002) (lines 916–1002 in `framework/INDEX.md`) — *Device transfer bottleneck detection package.*
- [`framework/gates/transfers/provenance`](framework/INDEX.md#L1003-L1018) (lines 1003–1018 in `framework/INDEX.md`) — *Device provenance inference for the host-device transfer gate.*
- [`framework/gates/traversal`](framework/INDEX.md#L1019-L1029) (lines 1019–1029 in `framework/INDEX.md`) — *Shared AST traversal helpers for the gate visitors.*
- [`framework/gates/typecheck`](framework/INDEX.md#L1030-L1108) (lines 1030–1108 in `framework/INDEX.md`) — *Static-type gate: staged mypy enforcement with an advisory pyright census.*
- [`framework/indexing`](framework/INDEX.md#L1109-L1160) (lines 1109–1160 in `framework/INDEX.md`) — *AST-based repository mapping and Table-of-Contents indexing.*
- [`framework/tests`](framework/INDEX.md#L1161-L1332) (lines 1161–1332 in `framework/INDEX.md`)
- [`framework/tests/abstract_cost`](framework/INDEX.md#L1333-L1354) (lines 1333–1354 in `framework/INDEX.md`) — *Tests for the advisory abstract-cost gate package.*
- [`framework/tests/antipattern`](framework/INDEX.md#L1355-L1442) (lines 1355–1442 in `framework/INDEX.md`) — *Anti-pattern extension tests (HNS066/067/069/072/081/082).*
- [`framework/tests/coverage_gate`](framework/INDEX.md#L1443-L1453) (lines 1443–1453 in `framework/INDEX.md`) — *Tests for the coverage gate and its probe plugin.*
- [`framework/tests/distortion`](framework/INDEX.md#L1454-L1480) (lines 1454–1480 in `framework/INDEX.md`) — *Test package for the framework distortion gate.*
- [`framework/tests/freshness`](framework/INDEX.md#L1481-L1533) (lines 1481–1533 in `framework/INDEX.md`) — *Tests for freshness and ref guard gates.*
- [`framework/tests/gates`](framework/INDEX.md#L1534-L1646) (lines 1534–1646 in `framework/INDEX.md`) — *Package.*
- [`framework/tests/gates/instructions`](framework/INDEX.md#L1647-L1686) (lines 1647–1686 in `framework/INDEX.md`) — *Tests for instruction reference validation.*
- [`framework/tests/gates/params`](framework/INDEX.md#L1687-L1745) (lines 1687–1745 in `framework/INDEX.md`) — *Tests for the parameter registry gates.*
- [`framework/tests/gates/ratchet`](framework/INDEX.md#L1746-L1768) (lines 1746–1768 in `framework/INDEX.md`) — *Ratchet gates: tables that may only shrink.*
- [`framework/tests/harness`](framework/INDEX.md#L1769-L1785) (lines 1769–1785 in `framework/INDEX.md`) — *Harness registry tests: project identity and the interpreter floor.*
- [`framework/tests/hook_hygiene`](framework/INDEX.md#L1786-L1794) (lines 1786–1794 in `framework/INDEX.md`) — *Tests for the hook/test-process boundary.*
- [`framework/tests/hotpath`](framework/INDEX.md#L1795-L1812) (lines 1795–1812 in `framework/INDEX.md`) — *Tests for the advisory hot-path gate package.*
- [`framework/tests/indexing`](framework/INDEX.md#L1813-L1861) (lines 1813–1861 in `framework/INDEX.md`) — *Tests for framework.indexing Table-of-Contents subsystem.*
- [`framework/tests/memory`](framework/INDEX.md#L1862-L1949) (lines 1862–1949 in `framework/INDEX.md`) — *Tests for the accelerator memory bottleneck static analysis gate.*
- [`framework/tests/transfers`](framework/INDEX.md#L1950-L2039) (lines 1950–2039 in `framework/INDEX.md`) — *Test package for device transfer bottleneck gate.*
- [`framework/tests/transfers/provenance`](framework/INDEX.md#L2040-L2057) (lines 2040–2057 in `framework/INDEX.md`) — *Test package for device provenance inference and mixing detection.*
- [`framework/tests/typecheck`](framework/INDEX.md#L2058-L2108) (lines 2058–2108 in `framework/INDEX.md`) — *Tests for the static-type gate.*

### [`research/INDEX.md`](research/INDEX.md) — 3 modules | 13 symbols

- [`research/params`](research/INDEX.md#L15-L42) (lines 15–42 in `research/INDEX.md`) — *Parameter registry and its runtime accessors (the worked example of the params rule).*
- [`research/probe`](research/INDEX.md#L43-L53) (lines 43–53 in `research/INDEX.md`) — *Example production package: a dependency-free plan builder.*

### [`scripts/INDEX.md`](scripts/INDEX.md) — 15 modules | 120 symbols

- [`scripts/setup`](scripts/INDEX.md#L16-L90) (lines 16–90 in `scripts/INDEX.md`) — *Framework wiring, scaffolding, and hook installation tools.*
- [`scripts/slurm_queue`](scripts/INDEX.md#L91-L281) (lines 91–281 in `scripts/INDEX.md`) — *Durable draining queue for Research sbatch jobs (model, store, submit, CLI, worker).*
- [`scripts/slurm_queue/worker`](scripts/INDEX.md#L282-L372) (lines 282–372 in `scripts/INDEX.md`) — *Drain one Slurm lane allocation.*

