# Research Sub-Index: `framework`

> [!NOTE]
> Sub-index for the `framework` package hierarchy. Use the line ranges below to load specific sections directly into context.

**Repository Statistics**: 65 modules | 14 classes | 464 public functions.

## Table of Contents

- [`framework`](#package-framework) (lines 33–55) — *Repository gate framework (hooks + checkers).*
- [`framework/gates`](#package-frameworkgates) (lines 56–83) — *Blocking and advisory repository gates.*
- [`framework/gates/antipattern`](#package-frameworkgatesantipattern) (lines 84–113) — *Internals of the production anti-pattern gate.*
- [`framework/gates/checks`](#package-frameworkgateschecks) (lines 114–186) — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*
- [`framework/gates/coverage`](#package-frameworkgatescoverage) (lines 187–244) — *Internals of the per-file coverage and loop-iteration gate.*
- [`framework/gates/distortion`](#package-frameworkgatesdistortion) (lines 245–291) — *Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.*
- [`framework/gates/freshness`](#package-frameworkgatesfreshness) (lines 292–323)
- [`framework/gates/limits`](#package-frameworkgateslimits) (lines 324–381)
- [`framework/gates/mutation`](#package-frameworkgatesmutation) (lines 382–450) — *Mutation-evidence gate: content-addressed mutmut verdicts for staged modules.*
- [`framework/gates/params`](#package-frameworkgatesparams) (lines 451–491) — *Parameter-drift gate package: registry matchers, CLI and their fixtures.*
- [`framework/gates/params/primitives`](#package-frameworkgatesparamsprimitives) (lines 492–496) — *Pure AST and text primitives of the parameter-drift matchers.*
- [`framework/gates/provenance`](#package-frameworkgatesprovenance) (lines 497–533) — *Run-provenance gates: GPU canary, run manifest, replay verification, MLflow log.*
- [`framework/indexing`](#package-frameworkindexing) (lines 534–585) — *AST-based repository mapping and Table-of-Contents indexing.*
- [`framework/tests`](#package-frameworktests) (lines 586–716)
- [`framework/tests/coverage_gate`](#package-frameworktestscoverage-gate) (lines 717–727) — *Tests for the coverage gate and its probe plugin.*
- [`framework/tests/distortion`](#package-frameworktestsdistortion) (lines 728–754) — *Test package for the framework distortion gate.*
- [`framework/tests/gates`](#package-frameworktestsgates) (lines 755–865) — *Package.*
- [`framework/tests/gates/params`](#package-frameworktestsgatesparams) (lines 866–924) — *Tests for the parameter registry gates.*
- [`framework/tests/harness`](#package-frameworktestsharness) (lines 925–934) — *Harness registry tests: project identity and the interpreter floor.*
- [`framework/tests/indexing`](#package-frameworktestsindexing) (lines 935–983) — *Tests for framework.indexing Table-of-Contents subsystem.*

---

## Package `framework` — *Repository gate framework (hooks + checkers).*

- [`framework/harness.py`](framework/harness.py) (237 lines)
  * *Module Purpose*: Single registry for the project identity, path roots and interpreter the harness uses.
  * [`env(name: str) -> str`](framework/harness.py#L78-L81)
    * *Contract*: Return the canonical env-var spelling of a harness parameter.
  * [`env_regex() -> str`](framework/harness.py#L84-L87)
    * *Contract*: Return the ERE that matches every canonical env var of this project.
  * [`venv() -> str`](framework/harness.py#L90-L99)
    * *Contract*: Return the interpreter directory: override, per-cluster, or the checkout venv.
  * [`python() -> str`](framework/harness.py#L126-L144)
    * *Contract*: Return the project interpreter: env override, venv binary, else this one.
  * [`deploy_root() -> str`](framework/harness.py#L147-L150)
    * *Contract*: Return the checkout the jobs import: env override, else this repository.
  * [`mlflow_uri() -> str`](framework/harness.py#L153-L156)
    * *Contract*: Return the MLflow tracking URI: env override, else this checkout's mlruns dir.
  * [`dvc_bin() -> str`](framework/harness.py#L159-L166)
    * *Contract*: Return the DVC executable: env override, the venv binary, else ``dvc`` on PATH.
  * [`scope_regex(roots: tuple[str, ...], suffix: str) -> str`](framework/harness.py#L169-L173)
    * *Contract*: Return an ERE anchoring ``roots`` (plus optional per-root suffix) at the start.
  * [`main(argv: list[str]) -> int`](framework/harness.py#L217-L233)
    * *Contract*: Print one key (``--get``) or the hook assignments (``--shell``).

## Package `framework/gates` — *Blocking and advisory repository gates.*

- [`framework/gates/check_antipatterns.py`](framework/gates/check_antipatterns.py) (148 lines)
  * *Module Purpose*: Fail-closed static checks for high-risk production anti-patterns.
  * [`analyze_source(source: str, path: str) -> list[framework.gates.antipattern.targets.Finding]`](framework/gates/check_antipatterns.py#L87-L95)
  * [`main(argv: list[str] | None) -> int`](framework/gates/check_antipatterns.py#L131-L144)

- [`framework/gates/check_coverage.py`](framework/gates/check_coverage.py) (222 lines)
  * *Module Purpose*: Per-file statement and loop-iteration coverage gate for the production tree.
  * [`main(argv: Sequence[str] | None) -> int`](framework/gates/check_coverage.py#L191-L218)

- [`framework/gates/check_documentation.py`](framework/gates/check_documentation.py) (141 lines)
  * *Module Purpose*: Adjudication guard: a run verdict requires the full documentation chain.
  * [`dvc_experiments() -> list[str]`](framework/gates/check_documentation.py#L50-L59)
  * [`mlflow_has_run(run: str) -> bool`](framework/gates/check_documentation.py#L62-L64)
  * [`main(argv: list[str] | None) -> int`](framework/gates/check_documentation.py#L116-L137)

- [`framework/gates/check_dvc_tracked.py`](framework/gates/check_dvc_tracked.py) (114 lines)
  * *Module Purpose*: Pre-submit guard: every prompt/data bank referenced by a job must be DVC-tracked.
  * [`dvc_status(path: Path) -> str`](framework/gates/check_dvc_tracked.py#L43-L52)
  * [`main(argv: list[str] | None) -> int`](framework/gates/check_dvc_tracked.py#L91-L110)

- [`framework/gates/check_structure.py`](framework/gates/check_structure.py) (189 lines)
  * *Module Purpose*: Experimental layout contract checker (advisory by default, exit 1 with --strict).
  * [`classify(path: Path, rel: str) -> str | None`](framework/gates/check_structure.py#L71-L95)
  * [`module_needs_test(rel: str, text: str) -> bool`](framework/gates/check_structure.py#L98-L104)
  * [`main() -> int`](framework/gates/check_structure.py#L166-L185)

## Package `framework/gates/antipattern` — *Internals of the production anti-pattern gate.*

- [`framework/gates/antipattern/fallthrough_checks.py`](framework/gates/antipattern/fallthrough_checks.py) (443 lines)
  * *Module Purpose*: Predicates for a log-only handler that lets a placeholder reach the caller.
  * [`placeholder_fallthrough(handler: ast.ExceptHandler, function: ast.AST) -> str | None`](framework/gates/antipattern/fallthrough_checks.py#L200-L213)
    * *Contract*: Return the placeholder a log-only handler lets reach the caller.
  * [`optional_input_neutralized(function: ast.AST) -> tuple[ast.If, str] | None`](framework/gates/antipattern/fallthrough_checks.py#L305-L320)
    * *Contract*: Return the branch and input whose absence becomes a valid-but-empty value.
  * [`dispatch_fallthrough(tree: ast.Module) -> list[tuple[ast.AST, str]]`](framework/gates/antipattern/fallthrough_checks.py#L427-L443)
    * *Contract*: Return mode defaults the module's own enumerated dispatch never matches.

- [`framework/gates/antipattern/python_checks.py`](framework/gates/antipattern/python_checks.py) (592 lines)
  * *Module Purpose*: Python-AST analysis helpers and their pattern constants.

- [`framework/gates/antipattern/python_visitor.py`](framework/gates/antipattern/python_visitor.py) (600 lines)
  * *Module Purpose*: AST visitor for the Python anti-pattern rules and its entry point.
  * [`analyze_python(source: str, path: str) -> list[framework.gates.antipattern.targets.Finding]`](framework/gates/antipattern/python_visitor.py#L579-L600)
    * *Contract*: Return findings for one Python source string.

- [`framework/gates/antipattern/shell_checks.py`](framework/gates/antipattern/shell_checks.py) (325 lines)
  * *Module Purpose*: Shell/slurm anti-pattern analysis and its pattern constants.
  * [`analyze_shell(source: str, path: str) -> list[framework.gates.antipattern.targets.Finding]`](framework/gates/antipattern/shell_checks.py#L297-L325)
    * *Contract*: Return findings for shell/slurm provenance and hygiene problems.

- [`framework/gates/antipattern/targets.py`](framework/gates/antipattern/targets.py) (111 lines)
  * *Module Purpose*: Scope constants, findings and target-file resolution.
  * [`class Finding`](framework/gates/antipattern/targets.py#L32-L41)
    * *Contract*: One source-level anti-pattern finding.
    * [`Finding.format(self) -> str`](framework/gates/antipattern/targets.py#L40-L41)

## Package `framework/gates/checks` — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*

- [`framework/gates/checks/check_contamination.py`](framework/gates/checks/check_contamination.py) (288 lines)
  * *Module Purpose*: Contamination gate — automated overlap & quality check for curated bank pairs.
  * [`log_event(target: str, gate: str, result: str, reason: str) -> None`](framework/gates/checks/check_contamination.py#L55-L77)
  * [`load_bank(path: Path) -> dict`](framework/gates/checks/check_contamination.py#L80-L109)
  * [`normalized(s: str) -> str`](framework/gates/checks/check_contamination.py#L141-L142)
  * [`token_overlap(a: str, b: str) -> float`](framework/gates/checks/check_contamination.py#L145-L150)
  * [`check_bank(path: Path, strict: bool) -> list[str]`](framework/gates/checks/check_contamination.py#L216-L235)
  * [`main(argv: list[str] | None) -> int`](framework/gates/checks/check_contamination.py#L263-L284)

- [`framework/gates/checks/check_duplication.py`](framework/gates/checks/check_duplication.py) (361 lines)
  * *Module Purpose*: Fail-closed copy-paste detection gate for staged or whole-tree code.
  * [`class Finding`](framework/gates/checks/check_duplication.py#L47-L57)
    * *Contract*: One duplicate code finding reported by the gate.
    * [`Finding.format(self) -> str`](framework/gates/checks/check_duplication.py#L55-L57)
      * *Contract*: Format finding for terminal or log output.
  * [`resolve_jscpd_bin(custom_path: str | None) -> str | None`](framework/gates/checks/check_duplication.py#L60-L72)
    * *Contract*: Resolve the path to the jscpd executable.
  * [`collect_staged_files(repo_root: Path) -> list[str]`](framework/gates/checks/check_duplication.py#L75-L101)
    * *Contract*: Retrieve list of staged files suitable for duplication check.
  * [`build_jscpd_args(jscpd_bin: str, target_paths: Sequence[str], config_path: Path | None, baseline_path: Path | None, update_baseline: bool, output_dir: Path | None) -> list[str]`](framework/gates/checks/check_duplication.py#L104-L125)
    * *Contract*: Assemble argument list for the jscpd subprocess invocation.
  * [`parse_jscpd_json(report_file: Path, baseline_active: bool) -> list[Finding]`](framework/gates/checks/check_duplication.py#L128-L148)
    * *Contract*: Parse findings from jscpd JSON report output.
  * [`parse_stdout_clones(stdout: str, baseline_active: bool) -> list[Finding]`](framework/gates/checks/check_duplication.py#L151-L174)
    * *Contract*: Parse clone occurrences directly from jscpd stdout lines.
  * [`run_jscpd(jscpd_bin: str, target_paths: Sequence[str], config_path: Path | None, baseline_path: Path | None, update_baseline: bool, repo_root: Path) -> tuple[int, list[Finding], str]`](framework/gates/checks/check_duplication.py#L194-L223)
    * *Contract*: Execute jscpd subprocess and parse clone findings.
  * [`evaluate_duplication(target_files: Sequence[str], staged: bool, baseline_path: Path | None, update_baseline: bool, config_path: Path | None, custom_jscpd: str | None, repo_root: Path) -> tuple[list[Finding], str]`](framework/gates/checks/check_duplication.py#L255-L284)
    * *Contract*: Evaluate codebase or target files for duplication violations.
  * [`parse_args(argv: Sequence[str] | None) -> argparse.Namespace`](framework/gates/checks/check_duplication.py#L316-L322)
    * *Contract*: Parse command line options for duplication checker.
  * [`output_json_report(findings: Sequence[Finding], dest: Path) -> None`](framework/gates/checks/check_duplication.py#L325-L331)
    * *Contract*: Save findings array to JSON file destination.
  * [`main(argv: Sequence[str] | None) -> int`](framework/gates/checks/check_duplication.py#L334-L357)
    * *Contract*: Run duplication evaluation and exit with status code.

- [`framework/gates/checks/check_test_mirror.py`](framework/gates/checks/check_test_mirror.py) (257 lines)
  * *Module Purpose*: Fail-closed test-mirror check for the production source tree.
  * [`class Finding`](framework/gates/checks/check_test_mirror.py#L62-L70)
    * *Contract*: One missing or broken src -> test mirror.
    * [`Finding.format(self) -> str`](framework/gates/checks/check_test_mirror.py#L69-L70)
  * [`mirror_paths(rel: str, tests_root: str) -> list[str]`](framework/gates/checks/check_test_mirror.py#L73-L82)
    * *Contract*: Return the accepted mirror test paths for one source file.
  * [`is_checked_path(rel: str, src: str) -> bool`](framework/gates/checks/check_test_mirror.py#L85-L88)
    * *Contract*: Return whether ``rel`` is a source module the gate is responsible for.
  * [`is_skipped(rel: str) -> bool`](framework/gates/checks/check_test_mirror.py#L91-L92)
  * [`collect_files(src: str, staged: Sequence[str] | None) -> list[str]`](framework/gates/checks/check_test_mirror.py#L95-L103)
    * *Contract*: Return the source files to check, sorted and de-duplicated.
  * [`evaluate(files: Sequence[str], aliases: Mapping[str, Sequence[str]], exists: Callable[[str], bool], tests_root: str) -> list[Finding]`](framework/gates/checks/check_test_mirror.py#L135-L149)
    * *Contract*: Return one finding per source module without a valid test mirror.
  * [`load_aliases(path: Path) -> dict[str, list[str]]`](framework/gates/checks/check_test_mirror.py#L152-L168)
  * [`main(argv: Sequence[str] | None) -> int`](framework/gates/checks/check_test_mirror.py#L228-L253)

- [`framework/gates/checks/local_gate.py`](framework/gates/checks/local_gate.py) (225 lines)
  * *Module Purpose*: Local pre-submit gate (run BEFORE any sbatch submission).
  * [`compile_ok(path: str) -> None`](framework/gates/checks/local_gate.py#L38-L43)
  * [`module_candidates(tree: ast.Module) -> set[str]`](framework/gates/checks/local_gate.py#L46-L60)
    * *Contract*: Names legally resolvable at module level.
  * [`build_scopes(tree: ast.Module)`](framework/gates/checks/local_gate.py#L118-L131)
    * *Contract*: Map each FunctionDef to (its locals, parent function).
  * [`check_undefined(tree: ast.Module, mod_names: set[str]) -> list[str]`](framework/gates/checks/local_gate.py#L166-L176)
    * *Contract*: Resolve every Name load against its NEAREST enclosing function chain.
  * [`main(argv: list[str]) -> int`](framework/gates/checks/local_gate.py#L194-L221)

- [`framework/gates/checks/sync_agents_mirrors.py`](framework/gates/checks/sync_agents_mirrors.py) (123 lines)
  * *Module Purpose*: Governance mirror sync + check (non-breaking, additive).
  * [`canonical_block(path: Path) -> str`](framework/gates/checks/sync_agents_mirrors.py#L43-L48)
  * [`mirror_block(text: str) -> str`](framework/gates/checks/sync_agents_mirrors.py#L51-L55)
  * [`write_mirror(path: Path, block: str) -> None`](framework/gates/checks/sync_agents_mirrors.py#L58-L65)
  * [`main() -> int`](framework/gates/checks/sync_agents_mirrors.py#L102-L119)

## Package `framework/gates/coverage` — *Internals of the per-file coverage and loop-iteration gate.*

- [`framework/gates/coverage/config.py`](framework/gates/coverage/config.py) (43 lines)
  * *Module Purpose*: CLI options, paths and schema constants of the coverage gate.

- [`framework/gates/coverage/coverage_probe.py`](framework/gates/coverage/coverage_probe.py) (453 lines)
  * *Module Purpose*: Pytest plugin: statement coverage with per-test contexts and exact loop counts.
  * [`instrument_tree(tree: ast.Module, module: str, plugin_module: str) -> dict[int, int]`](framework/gates/coverage/coverage_probe.py#L195-L206)
    * *Contract*: Instrument one parsed module in place; return ``{ordinal: lineno}``.
  * [`pytest_addoption(parser) -> None`](framework/gates/coverage/coverage_probe.py#L265-L278)
  * [`pytest_configure(config) -> None`](framework/gates/coverage/coverage_probe.py#L281-L301)
  * [`pytest_runtest_setup(item) -> None`](framework/gates/coverage/coverage_probe.py#L304-L309)
  * [`pytest_runtest_teardown(item) -> None`](framework/gates/coverage/coverage_probe.py#L312-L313)
  * [`statement_lines(path: Path) -> tuple[set[int], set[int]]`](framework/gates/coverage/coverage_probe.py#L324-L331)
    * *Contract*: Return coverage's executable-statement and excluded line sets.
  * [`build_report(state: _ProbeState, session, exitstatus: int) -> dict[str, Any]`](framework/gates/coverage/coverage_probe.py#L417-L443)
  * [`pytest_sessionfinish(session, exitstatus) -> None`](framework/gates/coverage/coverage_probe.py#L446-L453)

- [`framework/gates/coverage/ledger.py`](framework/gates/coverage/ledger.py) (540 lines)
  * *Module Purpose*: Clearance ledger: baseline, evidence fingerprints and evaluation.
  * [`build_baseline(report: Mapping[str, Any], src_files: Sequence[str], aliases: Mapping[str, Sequence[str]], exists: Callable[[str], bool], waivers: Mapping[str, Mapping[str, str]], mirrors: str, tests_root: str, min_coverage: float) -> dict[str, Any]`](framework/gates/coverage/ledger.py#L94-L121)
    * *Contract*: Return the whole-tree baseline document for one probe report.
  * [`baseline_regressions(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]`](framework/gates/coverage/ledger.py#L133-L151)
    * *Contract*: Return human-readable coverage regressions between two baselines.
  * [`cleared_by(entry: Mapping[str, Any], min_coverage: float) -> bool`](framework/gates/coverage/ledger.py#L179-L186)
    * *Contract*: Return whether a recorded entry satisfies the staged clearance criterion.
  * [`structure_hash(path: Path) -> str`](framework/gates/coverage/ledger.py#L204-L209)
    * *Contract*: Fingerprint executable structure: comments, formatting and line moves are free.
  * [`build_entry(rel: str, measured: bool, statements: int, self_pct: float, suite_pct: float, loops_uncovered: Sequence[int], aliases: Mapping[str, Sequence[str]], exists: Callable[[str], bool], mirrors: str, waivers: Mapping[str, str], min_coverage: float) -> dict[str, Any]`](framework/gates/coverage/ledger.py#L228-L255)
    * *Contract*: Build one content-addressed clearance record for a source file.
  * [`load_evidence(path: Path) -> dict[str, Any]`](framework/gates/coverage/ledger.py#L258-L262)
  * [`write_evidence(path: Path, entries: Mapping[str, Any]) -> None`](framework/gates/coverage/ledger.py#L265-L276)
  * [`check_evidence(evidence: Mapping[str, Any], src_files: Sequence[str], aliases: Mapping[str, Sequence[str]], exists: Callable[[str], bool], mirrors: str, waivers: Mapping[str, Mapping[str, str]], min_coverage: float, require_cleared: bool, refresh_hint: str) -> list[Finding]`](framework/gates/coverage/ledger.py#L373-L400)
    * *Contract*: Decide clearance from recorded evidence alone; no test run, no interpreter.

- [`framework/gates/coverage/metrics.py`](framework/gates/coverage/metrics.py) (462 lines)
  * *Module Purpose*: Report dataclasses and per-file coverage/loop metrics.
  * [`class Finding`](framework/gates/coverage/metrics.py#L34-L42)
    * *Contract*: One coverage or loop-iteration violation.
    * [`Finding.format(self) -> str`](framework/gates/coverage/metrics.py#L41-L42)
  * [`class FileMetrics`](framework/gates/coverage/metrics.py#L46-L55)
    * *Contract*: Coverage and loop status of one source file in one probe run.
  * [`test_files_for(rel: str, aliases: Mapping[str, Sequence[str]], exists: Callable[[str], bool], tests_root: str) -> list[str]`](framework/gates/coverage/metrics.py#L92-L102)
    * *Contract*: Return the test files that own ``rel`` (mirror paths plus aliases).
  * [`contexts_for(test_files: Sequence[str], contexts: Iterable[str]) -> set[str]`](framework/gates/coverage/metrics.py#L105-L115)
    * *Contract*: Return the pytest nodeid contexts that belong to ``test_files``.
  * [`source_loop_lines(path: Path) -> list[int]`](framework/gates/coverage/metrics.py#L118-L128)
    * *Contract*: Return the loop line numbers of one source file, in ordinal order.
  * [`loop_missing(loop: Mapping[str, Any], waived: bool) -> list[str]`](framework/gates/coverage/metrics.py#L131-L144)
    * *Contract*: Return the missing iteration cases of one loop (empty when compliant).
  * [`file_metrics(rel: str, entry: Mapping[str, Any] | None, test_files: Sequence[str], waivers: Mapping[str, str]) -> FileMetrics`](framework/gates/coverage/metrics.py#L179-L203)
    * *Contract*: Compute the metrics of one source file from one probe report entry.
  * [`evaluate(report: Mapping[str, Any], baseline: Mapping[str, Any] | None, waivers: Mapping[str, Mapping[str, str]], src_files: Sequence[str], aliases: Mapping[str, Sequence[str]], exists: Callable[[str], bool], loop_lines: Mapping[str, Sequence[int]], mirrors: str, mode: str, min_coverage: float) -> list[Finding]`](framework/gates/coverage/metrics.py#L438-L462)
    * *Contract*: Return the per-file findings of one probe report.

- [`framework/gates/coverage/run.py`](framework/gates/coverage/run.py) (423 lines)
  * *Module Purpose*: Probe invocation: pytest selection, execution and report validation.

## Package `framework/gates/distortion` — *Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.*

- [`framework/gates/distortion/check_distortion.py`](framework/gates/distortion/check_distortion.py) (81 lines)
  * *Module Purpose*: CLI entry point for the surrogate distortion gate.
  * [`main(argv: list[str] | None) -> int`](framework/gates/distortion/check_distortion.py#L62-L77)
    * *Contract*: CLI entrypoint executing distortion audit.

- [`framework/gates/distortion/rules.py`](framework/gates/distortion/rules.py) (180 lines)
  * *Module Purpose*: AST rule predicates for detecting surrogate distortion patterns.
  * [`is_low_precision_expr(node: ast.AST) -> bool`](framework/gates/distortion/rules.py#L40-L56)
    * *Contract*: Return True if node performs low-precision conversion or quantization.
  * [`references_var(node: ast.AST, var_names: set[str]) -> bool`](framework/gates/distortion/rules.py#L59-L69)
    * *Contract*: Check if node or its sub-call/subscript references any given variable.
  * [`check_hns044_weight_subtraction(node: ast.BinOp, low_precision_vars: set[str]) -> tuple[str, str] | None`](framework/gates/distortion/rules.py#L72-L90)
    * *Contract*: Detect weight subtraction preceded by low-precision casting.
  * [`check_hns045_pooled_dictcomp(node: ast.DictComp, func_name: str) -> tuple[str, str] | None`](framework/gates/distortion/rules.py#L118-L135)
    * *Contract*: Detect broadcasting one pooled estimate across members in a dict comp.
  * [`is_mean_node(node: ast.AST, mean_vars: set[str]) -> bool`](framework/gates/distortion/rules.py#L138-L152)
    * *Contract*: Return True if node evaluates a mean statistic or precomputed mean variable.
  * [`check_hns046_ratio_of_means(node: ast.BinOp, mean_vars: set[str]) -> tuple[str, str] | None`](framework/gates/distortion/rules.py#L164-L180)
    * *Contract*: Detect ratio-of-means scalar reduction (1 - mean(a)/mean(b) or ratio - 1).

- [`framework/gates/distortion/targets.py`](framework/gates/distortion/targets.py) (124 lines)
  * *Module Purpose*: Target definitions and source loaders for the surrogate distortion gate.
  * [`class Finding`](framework/gates/distortion/targets.py#L35-L45)
    * *Contract*: One anti-pattern finding with file path, line number, code, and message.
    * [`Finding.format(self) -> str`](framework/gates/distortion/targets.py#L43-L45)
      * *Contract*: Format finding for standard compiler-style CLI diagnostic output.
  * [`is_target_python(path: str) -> bool`](framework/gates/distortion/targets.py#L54-L62)
    * *Contract*: Return True if path points to a scoped production Python module.

- [`framework/gates/distortion/visitor.py`](framework/gates/distortion/visitor.py) (101 lines)
  * *Module Purpose*: AST visitor for detecting surrogate distortion anti-patterns.
  * [`class DistortionVisitor(ast.NodeVisitor)`](framework/gates/distortion/visitor.py#L45-L90)
    * *Contract*: AST visitor traversing nodes to record distortion findings.
    * [`DistortionVisitor.__init__(self, path: str) -> None`](framework/gates/distortion/visitor.py#L48-L53)
    * [`DistortionVisitor.visit_FunctionDef(self, node: ast.FunctionDef) -> None`](framework/gates/distortion/visitor.py#L55-L63)
      * *Contract*: Inspect function body tracking local precision and statistics context.
    * [`DistortionVisitor.visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None`](framework/gates/distortion/visitor.py#L65-L73)
      * *Contract*: Inspect async function body tracking local precision context.
    * [`DistortionVisitor.visit_BinOp(self, node: ast.BinOp) -> None`](framework/gates/distortion/visitor.py#L75-L83)
      * *Contract*: Inspect binary operations for weight subtractions and ratio-of-means.
    * [`DistortionVisitor.visit_DictComp(self, node: ast.DictComp) -> None`](framework/gates/distortion/visitor.py#L85-L90)
      * *Contract*: Inspect dictionary comprehensions for pooled estimate broadcasts.
  * [`analyze_distortion(source: str, path: str) -> list[Finding]`](framework/gates/distortion/visitor.py#L93-L101)
    * *Contract*: Parse source and return all identified surrogate distortion findings.

## Package `framework/gates/freshness`

- [`framework/gates/freshness/check_index_freshness.py`](framework/gates/freshness/check_index_freshness.py) (167 lines)
  * *Module Purpose*: Block a commit whose index disagrees with HEAD and the working tree.
  * [`class Finding`](framework/gates/freshness/check_index_freshness.py#L56-L67)
    * *Contract*: One staged path the working tree does not corroborate.
    * [`Finding.format(self) -> str`](framework/gates/freshness/check_index_freshness.py#L63-L64)
    * [`Finding.as_dict(self) -> dict[str, str]`](framework/gates/freshness/check_index_freshness.py#L66-L67)
  * [`collect_findings() -> list[Finding]`](framework/gates/freshness/check_index_freshness.py#L117-L125)
    * *Contract*: Return one finding per staged path the working tree does not corroborate.
  * [`main(argv: list[str] | None) -> int`](framework/gates/freshness/check_index_freshness.py#L147-L163)
    * *Contract*: Run the gate; return the process exit code.

- [`framework/gates/freshness/test_index_freshness.py`](framework/gates/freshness/test_index_freshness.py) (137 lines)
  * *Module Purpose*: Tests for the index-freshness gate.
  * [`repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path`](framework/gates/freshness/test_index_freshness.py#L44-L48)
    * *Contract*: A throwaway repository the gate is pointed at.
  * [`test_staged_edit_with_worktree_change_is_clean(repo: Path) -> None`](framework/gates/freshness/test_index_freshness.py#L51-L56)
    * *Contract*: An ordinary edit corroborated by the working tree passes.
  * [`test_added_and_removed_files_are_clean(repo: Path) -> None`](framework/gates/freshness/test_index_freshness.py#L59-L65)
    * *Contract*: A staged addition and a staged `git rm` are both corroborated on disk.
  * [`test_reverted_but_still_staged_path_is_blocked(repo: Path) -> None`](framework/gates/freshness/test_index_freshness.py#L68-L76)
    * *Contract*: Staged content that survives in neither HEAD nor the worktree is stale.
  * [`test_private_index_from_an_older_revision_is_blocked(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/gates/freshness/test_index_freshness.py#L79-L99)
    * *Contract*: The 2026-09-25 incident: a private index seeded before a later commit.
  * [`test_deliberate_untrack_has_no_bypass(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/gates/freshness/test_index_freshness.py#L102-L110)
    * *Contract*: `git rm --cached` keeps the file on disk; no environment variable allows it.
  * [`test_unborn_head_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/gates/freshness/test_index_freshness.py#L113-L123)
    * *Contract*: A repository with no commit has no revision to drift from.
  * [`test_json_report_lists_every_finding(repo: Path, tmp_path: Path) -> None`](framework/gates/freshness/test_index_freshness.py#L126-L137)
    * *Contract*: The JSON report carries the same findings the text output prints.

## Package `framework/gates/limits`

- [`framework/gates/limits/check_limits.py`](framework/gates/limits/check_limits.py) (413 lines)
  * *Module Purpose*: Code-size limits for agent-authored Python (blocking on staged files).
  * [`class Finding`](framework/gates/limits/check_limits.py#L72-L81)
    * *Contract*: One code-size limit violation.
    * [`Finding.format(self) -> str`](framework/gates/limits/check_limits.py#L80-L81)
  * [`is_first_party(rel: str) -> bool`](framework/gates/limits/check_limits.py#L84-L94)
    * *Contract*: Return whether a repository-relative path is in this gate's scope.
  * [`walk_functions(node: ast.AST, prefix: str) -> Iterator[tuple[str, ast.AST]]`](framework/gates/limits/check_limits.py#L150-L161)
    * *Contract*: Yield ``(qualname, node)`` for every function/method, outermost first.
  * [`function_findings(rel: str, tree: ast.Module) -> list[Finding]`](framework/gates/limits/check_limits.py#L164-L180)
    * *Contract*: Return ``LMT002`` findings for every over-long function or method.
  * [`init_findings(rel: str, tree: ast.Module) -> list[Finding]`](framework/gates/limits/check_limits.py#L183-L201)
    * *Contract*: Return the ``LMT004`` finding when ``__init__.py`` carries code.
  * [`file_findings(rel: str, text: str) -> list[Finding]`](framework/gates/limits/check_limits.py#L204-L231)
    * *Contract*: Return every per-file limit finding for one module's source text.
  * [`directory_findings(counts: Mapping[str, int]) -> list[Finding]`](framework/gates/limits/check_limits.py#L234-L247)
    * *Contract*: Return ``LMT003`` findings for every directory above the module limit.
  * [`read_staged(rel: str) -> str | None`](framework/gates/limits/check_limits.py#L250-L264)
    * *Contract*: Return the staged text of ``rel`` from the Git index, or ``None``.
  * [`index_directory_counts(directories: Sequence[str]) -> dict[str, int]`](framework/gates/limits/check_limits.py#L267-L286)
    * *Contract*: Count indexed ``.py`` modules per directory, as the commit will see them.
  * [`collect_sources() -> list[str]`](framework/gates/limits/check_limits.py#L289-L305)
    * *Contract*: Return every first-party module of the working tree, repository-relative.
  * [`report(findings: Sequence[Finding], checked: int, max_findings: int) -> None`](framework/gates/limits/check_limits.py#L308-L323)
    * *Contract*: Print findings (capped) plus per-code totals and the checked count.
  * [`parse_args(argv: Sequence[str] | None) -> argparse.Namespace`](framework/gates/limits/check_limits.py#L326-L344)
  * [`run_staged(args: argparse.Namespace) -> int`](framework/gates/limits/check_limits.py#L347-L375)
    * *Contract*: Verify every staged first-party module without grandfathering.
  * [`run_all(args: argparse.Namespace) -> int`](framework/gates/limits/check_limits.py#L378-L402)
    * *Contract*: Audit the working tree; the debt meter, not a commit gate.
  * [`main(argv: Sequence[str] | None) -> int`](framework/gates/limits/check_limits.py#L405-L409)

- [`framework/gates/limits/test_limits.py`](framework/gates/limits/test_limits.py) (207 lines)
  * *Module Purpose*: Tests for the code-size limits gate.
  * [`codes(source: str, path: str) -> set[str]`](framework/gates/limits/test_limits.py#L24-L25)
  * [`git_env() -> dict[str, str]`](framework/gates/limits/test_limits.py#L28-L31)
  * [`stage(root: Path, rel: str, text: str) -> None`](framework/gates/limits/test_limits.py#L34-L38)
  * [`unstage(root: Path, rel: str) -> None`](framework/gates/limits/test_limits.py#L41-L44)
  * [`repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]`](framework/gates/limits/test_limits.py#L48-L51)
  * [`test_file_length_boundary() -> None`](framework/gates/limits/test_limits.py#L54-L56)
  * [`test_function_length_boundary_uses_the_qualname() -> None`](framework/gates/limits/test_limits.py#L59-L65)
  * [`test_decorators_do_not_count_towards_the_span() -> None`](framework/gates/limits/test_limits.py#L68-L70)
  * [`test_init_py_allows_docstring_imports_and_dunder_metadata() -> None`](framework/gates/limits/test_limits.py#L73-L84)
  * [`test_init_py_code_is_blocked() -> None`](framework/gates/limits/test_limits.py#L87-L97)
  * [`test_init_py_silent_optional_import_guards_are_blocked() -> None`](framework/gates/limits/test_limits.py#L100-L102)
  * [`test_syntax_errors_fail_closed() -> None`](framework/gates/limits/test_limits.py#L105-L107)
  * [`test_directory_limit_ignores_init_files() -> None`](framework/gates/limits/test_limits.py#L110-L114)
  * [`test_scope_covers_first_party_trees_only() -> None`](framework/gates/limits/test_limits.py#L117-L128)
  * [`test_staged_mode_reads_the_index_not_the_worktree(repo: Path) -> None`](framework/gates/limits/test_limits.py#L131-L136)
  * [`test_staged_mode_blocks_a_new_module_in_a_crowded_directory(repo: Path) -> None`](framework/gates/limits/test_limits.py#L139-L148)
  * [`test_staged_deletion_frees_the_directory_slot(repo: Path) -> None`](framework/gates/limits/test_limits.py#L151-L160)
  * [`test_staged_mode_requires_files_and_ignores_vendored_paths(repo: Path) -> None`](framework/gates/limits/test_limits.py#L163-L178)
  * [`test_mode_all_reports_and_strict_decides(repo: Path, capsys: pytest.CaptureFixture) -> None`](framework/gates/limits/test_limits.py#L181-L190)
  * [`test_hook_wiring_is_blocking_before_the_advisory_section() -> None`](framework/gates/limits/test_limits.py#L193-L201)
  * [`test_gate_obeys_its_own_limits() -> None`](framework/gates/limits/test_limits.py#L204-L207)

## Package `framework/gates/mutation` — *Mutation-evidence gate: content-addressed mutmut verdicts for staged modules.*

- [`framework/gates/mutation/check_mutation.py`](framework/gates/mutation/check_mutation.py) (172 lines)
  * *Module Purpose*: Mutation gate CLI: refresh and verify cleared mutmut evidence for staged files.
  * [`parse_args(argv: Sequence[str] | None) -> argparse.Namespace`](framework/gates/mutation/check_mutation.py#L33-L41)
    * *Contract*: Command line for the mutation gate.
  * [`main(argv: Sequence[str] | None) -> int`](framework/gates/mutation/check_mutation.py#L154-L168)
    * *Contract*: Decide from the ledger, or refresh it, for the staged population.

- [`framework/gates/mutation/evidence.py`](framework/gates/mutation/evidence.py) (293 lines)
  * *Module Purpose*: Mutation evidence: content-addressed mutmut verdicts for staged modules.
  * [`staged_bytes(rel: str) -> bytes | None`](framework/gates/mutation/evidence.py#L65-L70)
    * *Contract*: The exact bytes the index would commit for ``rel`` (None when unstaged).
  * [`staged_sha256(rel: str) -> str | None`](framework/gates/mutation/evidence.py#L73-L76)
    * *Contract*: sha256 of the staged blob, the address ``rel``'s evidence is keyed by.
  * [`load_ledger(path: Path | None) -> dict[str, Any]`](framework/gates/mutation/evidence.py#L79-L88)
    * *Contract*: Read the evidence ledger; a missing or malformed file reads as empty.
  * [`save_ledger(data: Mapping[str, Any], path: Path | None) -> None`](framework/gates/mutation/evidence.py#L91-L96)
    * *Contract*: Write the ledger deterministically, so its diff stays reviewable.
  * [`config_population() -> tuple[dict[str, list[str]] | None, str | None]`](framework/gates/mutation/evidence.py#L128-L143)
    * *Contract*: The mutated-file population from ``[tool.mutmut]``, or why it is unreadable.
  * [`match_population(rel: str, population: Mapping[str, list[str]]) -> bool`](framework/gates/mutation/evidence.py#L167-L175)
    * *Contract*: True when ``rel`` is mutated: it matches only_mutate, not do_not_mutate.
  * [`entry_findings(rel: str, entry: Any, sha: str) -> list[str]`](framework/gates/mutation/evidence.py#L206-L227)
    * *Contract*: Every reason ``rel``'s recorded evidence does not clear content ``sha``.
  * [`staged_findings(paths: Sequence[str], ledger_path: Path | None) -> list[str]`](framework/gates/mutation/evidence.py#L253-L264)
    * *Contract*: Every reason the staged files lack cleared evidence for their content.
  * [`scoped_paths(paths: Sequence[str]) -> tuple[list[str], str | None]`](framework/gates/mutation/evidence.py#L287-L293)
    * *Contract*: The staged paths the gate owns, or the reason the population is unreadable.

- [`framework/gates/mutation/scoring.py`](framework/gates/mutation/scoring.py) (111 lines)
  * *Module Purpose*: mutmut driver for the mutation gate: score the population, read the verdicts.
  * [`status_table() -> tuple[dict[int | None, str] | None, str | None, str | None]`](framework/gates/mutation/scoring.py#L36-L42)
    * *Contract*: mutmut's status map, its unknown-code fallback status, or why it is absent.
  * [`mutmut_version(python: str | None) -> tuple[str | None, str | None]`](framework/gates/mutation/scoring.py#L45-L57)
    * *Contract*: The installed mutmut version reported by ``-m mutmut --version``.
  * [`run_mutmut(jobs: int, python: str | None) -> int`](framework/gates/mutation/scoring.py#L60-L72)
    * *Contract*: Score every uncached or invalidated mutant; mutmut's output streams through.
  * [`meta_path(rel: str) -> Path`](framework/gates/mutation/scoring.py#L75-L77)
    * *Contract*: Where mutmut stores one module's verdicts.
  * [`collect_statuses(rel: str) -> tuple[dict[str, str], str | None]`](framework/gates/mutation/scoring.py#L80-L93)
    * *Contract*: Map every recorded mutant of ``rel`` to a status, or say why it cannot.
  * [`aggregate(statuses: Mapping[str, str]) -> dict[str, int]`](framework/gates/mutation/scoring.py#L96-L103)
    * *Contract*: Count statuses, emitting every blocking key so a silent slip is impossible.
  * [`names_by_status(statuses: Mapping[str, str]) -> dict[str, list[str]]`](framework/gates/mutation/scoring.py#L106-L111)
    * *Contract*: The mutant names behind each status, so findings can print the offender.

- [`framework/gates/mutation/test_mutation.py`](framework/gates/mutation/test_mutation.py) (237 lines)
  * *Module Purpose*: Behavioral tests for the mutation-evidence gate (no mutmut run is forked here).
  * [`repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path`](framework/gates/mutation/test_mutation.py#L28-L56)
    * *Contract*: A throwaway repository whose staged blob and ledger the gate reads.
  * [`test_absent_evidence_blocks_with_the_refresh_command(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L94-L97)
  * [`test_cleared_evidence_for_the_staged_content_passes(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L100-L102)
  * [`test_staging_new_content_invalidates_the_recorded_evidence(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L105-L109)
  * [`test_unstaged_edits_do_not_change_the_decision(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L112-L115)
  * [`test_a_survivor_blocks_and_is_named(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L118-L128)
  * [`test_unreached_mutants_block_as_a_coverage_hole(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L131-L134)
  * [`test_a_timeout_blocks_as_an_unscored_mutant(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L137-L139)
  * [`test_files_outside_the_population_are_not_the_gates_business(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L142-L144)
  * [`test_population_drift_blocks_until_the_ledger_is_refreshed(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L147-L156)
  * [`test_population_drift_blocks_without_a_staged_population_file(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L159-L168)
  * [`test_emptying_the_population_blocks_against_recorded_evidence(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L171-L177)
  * [`test_config_only_staging_passes_when_the_ledger_matches(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L180-L182)
  * [`test_glob_matching_respects_segments_and_double_star(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L185-L190)
  * [`test_no_environment_variable_downgrades_the_gate(repo: Path, monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None`](framework/gates/mutation/test_mutation.py#L198-L204)
  * [`test_cli_evidence_only_exits_nonzero_on_findings(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L207-L211)
  * [`test_refresh_refuses_a_worktree_that_differs_from_the_index(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L214-L216)
  * [`test_aggregate_maps_mutmut_statuses_and_unknown_codes_block() -> None`](framework/gates/mutation/test_mutation.py#L219-L237)

## Package `framework/gates/params` — *Parameter-drift gate package: registry matchers, CLI and their fixtures.*

- [`framework/gates/params/argparse_calls.py`](framework/gates/params/argparse_calls.py) (38 lines)
  * *Module Purpose*: Locally aliased ``add_argument`` calls, so an alias cannot hide a default.
  * [`argument_aliases(tree: ast.AST) -> frozenset[str]`](framework/gates/params/argparse_calls.py#L17-L27)
    * *Contract*: Return the local names one module binds to an ``add_argument`` method.
  * [`is_flag_call(node: ast.AST, aliases: frozenset[str]) -> bool`](framework/gates/params/argparse_calls.py#L30-L38)
    * *Contract*: Return whether ``node`` calls ``add_argument``, directly or by alias.

- [`framework/gates/params/check_param_duplicates.py`](framework/gates/params/check_param_duplicates.py) (162 lines)
  * *Module Purpose*: Blocking parameter-duplication gate: one env var, one default, one name.
  * [`files_to_check(paths: Sequence[str]) -> list[str]`](framework/gates/params/check_param_duplicates.py#L78-L82)
    * *Contract*: Return the in-scope files of this invocation, in stable order.
  * [`check_paths(paths: Sequence[str], staged: bool) -> list[Finding]`](framework/gates/params/check_param_duplicates.py#L101-L111)
    * *Contract*: Return every finding of the given paths, registry and usage sweeps included.
  * [`main(argv: Sequence[str] | None) -> int`](framework/gates/params/check_param_duplicates.py#L140-L158)
    * *Contract*: Run the gate and return its process exit code.

- [`framework/gates/params/param_checks.py`](framework/gates/params/param_checks.py) (164 lines)
  * *Module Purpose*: Drift matchers for the canonical parameter registry (codes HNS038-HNS041).
  * [`registry_findings() -> list[Finding]`](framework/gates/params/param_checks.py#L152-L164)
    * *Contract*: Return HNS041 findings for a malformed registry table.

- [`framework/gates/params/param_matchers.py`](framework/gates/params/param_matchers.py) (460 lines)
  * *Module Purpose*: Source-text matchers for the canonical parameter registry (HNS038-HNS041).
  * [`source_findings(source: str, path: str) -> list[Finding]`](framework/gates/params/param_matchers.py#L26-L30)
    * *Contract*: Dispatch one source text to its language matcher.
  * [`shell_findings(source: str, path: str) -> list[Finding]`](framework/gates/params/param_matchers.py#L33-L39)
    * *Contract*: Return every HNS038-HNS041 finding of one shell source text.
  * [`python_findings(source: str, path: str) -> list[Finding]`](framework/gates/params/param_matchers.py#L98-L117)
    * *Contract*: Return every HNS038-HNS041 finding of one Python source text.
  * [`alias_findings(source: str, path: str) -> list[Finding]`](framework/gates/params/param_matchers.py#L398-L413)
    * *Contract*: Return one HNS038 finding per superseded alias occurrence.

- [`framework/gates/params/param_usage.py`](framework/gates/params/param_usage.py) (338 lines)
  * *Module Purpose*: Usage gate for the canonical parameter registry (codes HNS042, HNS043).
  * [`class Reads`](framework/gates/params/param_usage.py#L41-L48)
    * *Contract*: The accessor surface of one parsed module.
  * [`usage_findings(texts: Mapping[str, str] | None, rows: Sequence[Any] | None) -> list[Finding]`](framework/gates/params/param_usage.py#L321-L338)
    * *Contract*: Return every usage finding of the registry rows against ``texts``.

## Package `framework/gates/params/primitives` — *Pure AST and text primitives of the parameter-drift matchers.*

- [`framework/gates/params/primitives/nodes.py`](framework/gates/params/primitives/nodes.py) (7 lines)
  * *Module Purpose*: AST and text primitives with no registry state.

## Package `framework/gates/provenance` — *Run-provenance gates: GPU canary, run manifest, replay verification, MLflow log.*

- [`framework/gates/provenance/canary_gate.py`](framework/gates/provenance/canary_gate.py) (421 lines)
  * *Module Purpose*: GPU canary gate — framework step 4e (pre-submit, generic).
  * [`derive_canary(source: str, name: str, time_seconds: int, method: str | None, hook: str | None, canary_dir: Path) -> str`](framework/gates/provenance/canary_gate.py#L191-L216)
    * *Contract*: Deterministically derive a bounded canary sbatch from the source text.
  * [`verdict_for(state: str, exitcode: str) -> tuple[bool, str]`](framework/gates/provenance/canary_gate.py#L219-L225)
    * *Contract*: PASS when the job finished (0) or was killed alive by the bound (124).
  * [`main(argv: list[str] | None) -> int`](framework/gates/provenance/canary_gate.py#L365-L366)

- [`framework/gates/provenance/git_facts.py`](framework/gates/provenance/git_facts.py) (45 lines)
  * *Module Purpose*: Repository facts shared by the provenance gates.
  * [`git_dirty(repo: Path) -> bool`](framework/gates/provenance/git_facts.py#L17-L27)
  * [`git_commit(repo: Path) -> str`](framework/gates/provenance/git_facts.py#L30-L37)
  * [`sha256_file(path: Path) -> str`](framework/gates/provenance/git_facts.py#L40-L45)

- [`framework/gates/provenance/log_mlflow_run.py`](framework/gates/provenance/log_mlflow_run.py) (115 lines)
  * *Module Purpose*: Log one run manifest to the local MLflow registry (documentation gate #3).
  * [`kv(items: list[str], what: str) -> dict[str, str]`](framework/gates/provenance/log_mlflow_run.py#L48-L56)
  * [`main(argv: list[str] | None) -> int`](framework/gates/provenance/log_mlflow_run.py#L90-L111)

- [`framework/gates/provenance/record_run_manifest.py`](framework/gates/provenance/record_run_manifest.py) (292 lines)
  * *Module Purpose*: Run manifest recorder — binds a run to frozen inputs (guardrail #3).
  * [`parse_metrics(items: list[str]) -> tuple[dict[str, float | str], list[str]]`](framework/gates/provenance/record_run_manifest.py#L51-L64)
    * *Contract*: Parse repeatable K=V metric flags; unparseable values stay strings.
  * [`parse_settings(items: list[str]) -> tuple[dict[str, str], list[str]]`](framework/gates/provenance/record_run_manifest.py#L67-L77)
    * *Contract*: Parse repeatable K=V setting flags: the resolved values a run executed.
  * [`pin_file(pins: dict[str, str], problems: list[str], key: str, path: str | Path) -> None`](framework/gates/provenance/record_run_manifest.py#L80-L89)
  * [`build_pins(args: argparse.Namespace, problems: list[str]) -> dict[str, str]`](framework/gates/provenance/record_run_manifest.py#L92-L118)
  * [`apply_from_manifest(args: argparse.Namespace) -> str | None`](framework/gates/provenance/record_run_manifest.py#L121-L144)
    * *Contract*: Reuse an existing manifest's pins/paths (adjudication path).
  * [`main(argv: list[str] | None) -> int`](framework/gates/provenance/record_run_manifest.py#L264-L288)

- [`framework/gates/provenance/verify_replay.py`](framework/gates/provenance/verify_replay.py) (131 lines)
  * *Module Purpose*: Run manifest verifier — re-derives hashes from live files (guardrail #3).
  * [`main(argv: list[str] | None) -> int`](framework/gates/provenance/verify_replay.py#L98-L127)

## Package `framework/indexing` — *AST-based repository mapping and Table-of-Contents indexing.*

- [`framework/indexing/cli.py`](framework/indexing/cli.py) (115 lines)
  * *Module Purpose*: Command-line interface for the framework Table-of-Contents indexer.
  * [`main(argv: list[str] | None) -> int`](framework/indexing/cli.py#L95-L111)
    * *Contract*: Entry point for python -m framework.indexing.

- [`framework/indexing/formatter.py`](framework/indexing/formatter.py) (266 lines)
  * *Module Purpose*: Format scanned module symbols into a dynamic Table-of-Contents index.
  * [`class SectionMeta`](framework/indexing/formatter.py#L32-L40)
    * *Contract*: Metadata and line numbers for an indexed package section.
  * [`format_sub_index(pkg_root: str, modules: Sequence[ModuleEntry], repo_root: Path | None) -> tuple[str, list[SectionMeta]]`](framework/indexing/formatter.py#L178-L201)
    * *Contract*: Render a self-contained sub-index with its own local TOC and line ranges.
  * [`format_master_index(sub_indices: list[dict[str, Any]], stats: dict[str, Any]) -> str`](framework/indexing/formatter.py#L221-L241)
    * *Contract*: Render the master index linking to sub-indices with section line ranges.
  * [`format_markdown_index(modules: Sequence[ModuleEntry], repo_root: Path | None) -> str`](framework/indexing/formatter.py#L244-L266)
    * *Contract*: Render a structured Table of Contents grouped dynamically by package directory.

- [`framework/indexing/gate.py`](framework/indexing/gate.py) (418 lines)
  * *Module Purpose*: Verification gate and freshness check for the repository Table of Contents.
  * [`load_contract_config(repo_root: Path | None) -> dict[str, Any]`](framework/indexing/gate.py#L138-L160)
    * *Contract*: Load contract enforcement settings from pyproject.toml with safe fallback.
  * [`check_interface_drift(repo_root: Path, modules: Sequence[ModuleEntry], files: Sequence[str], config: dict[str, Any] | None) -> list[str]`](framework/indexing/gate.py#L191-L210)
    * *Contract*: Check whether any staged file altered public signatures without doc updates.
  * [`check_module_contracts(modules: Sequence[ModuleEntry], files: Sequence[str] | None, repo_root: Path | None, config: dict[str, Any] | None) -> list[str]`](framework/indexing/gate.py#L213-L232)
    * *Contract*: Audit staged or specified modules for Two-Tier docstring schema errors.
  * [`audit_contract_coverage(modules: Sequence[ModuleEntry]) -> dict[str, Any]`](framework/indexing/gate.py#L235-L261)
    * *Contract*: Audit the percentage of public functions and modules carrying contracts.
  * [`verify_index_freshness(file_map: dict[Path, str]) -> tuple[bool, str]`](framework/indexing/gate.py#L276-L285)
    * *Contract*: Check if all planned index files match their on-disk counterparts.
  * [`plan_index_files(repo_root: Path, index_path: Path, modules: Sequence[ModuleEntry], roots: Sequence[str], max_lines: int) -> dict[Path, str]`](framework/indexing/gate.py#L316-L345)
    * *Contract*: Plan index files: unified if under max_lines, otherwise tree of sub-indices.
  * [`run_index_gate(repo_root: Path, index_path: Path, roots: Sequence[str], max_lines: int, check_only: bool, strict_contracts: bool, staged_files: Sequence[str] | None) -> int`](framework/indexing/gate.py#L394-L418)
    * *Contract*: Run the repository index gate: verify synchronization or write updates.

- [`framework/indexing/scanner.py`](framework/indexing/scanner.py) (262 lines)
  * *Module Purpose*: Static AST-based scanner for codebase modules, classes, and contracts.
  * [`class FunctionEntry`](framework/indexing/scanner.py#L32-L41)
    * *Contract*: Represents a public function or method extracted from the AST.
  * [`class ClassEntry`](framework/indexing/scanner.py#L45-L53)
    * *Contract*: Represents a class definition and its public methods.
  * [`class ModuleEntry`](framework/indexing/scanner.py#L57-L71)
    * *Contract*: Represents a scanned Python module with its docstring and exports.
    * [`ModuleEntry.has_invariants(self) -> bool`](framework/indexing/scanner.py#L69-L71)
      * *Contract*: Return True if an Invariants section is present in docstring.
  * [`scan_module_text(rel_path: str, text: str) -> ModuleEntry | None`](framework/indexing/scanner.py#L196-L221)
    * *Contract*: Parse module text statically into a ModuleEntry without executing code.
  * [`scan_file(file_path: Path, repo_root: Path) -> ModuleEntry | None`](framework/indexing/scanner.py#L224-L234)
    * *Contract*: Read and scan a single Python file relative to repo_root.
  * [`scan_repository(repo_root: Path, roots: Sequence[str]) -> list[ModuleEntry]`](framework/indexing/scanner.py#L249-L262)
    * *Contract*: Scan all specified subtrees of a repository and return sorted ModuleEntries.

## Package `framework/tests`

- [`framework/tests/test_antipattern_gate.py`](framework/tests/test_antipattern_gate.py) (599 lines)
  * *Module Purpose*: Tests for the production anti-pattern gate.
  * [`codes(source: str, path: str) -> set[str]`](framework/tests/test_antipattern_gate.py#L18-L19)
  * [`shell_codes(source: str, path: str) -> set[str]`](framework/tests/test_antipattern_gate.py#L22-L28)
  * [`test_safe_production_patterns_are_clean() -> None`](framework/tests/test_antipattern_gate.py#L31-L39)
  * [`test_checked_exceptions_and_validated_non_strict_loads_are_clean() -> None`](framework/tests/test_antipattern_gate.py#L42-L55)
  * [`test_runtime_and_deserialization_patterns_are_blocked() -> None`](framework/tests/test_antipattern_gate.py#L58-L71)
  * [`test_explicit_unsafe_arguments_are_blocked() -> None`](framework/tests/test_antipattern_gate.py#L74-L77)
  * [`test_silent_exception_and_error_sentinel_fallbacks_are_blocked() -> None`](framework/tests/test_antipattern_gate.py#L80-L89)
  * [`test_recorded_optional_metric_failure_is_not_silent() -> None`](framework/tests/test_antipattern_gate.py#L92-L100)
  * [`test_broad_exception_and_cuda_fallback_are_blocked() -> None`](framework/tests/test_antipattern_gate.py#L103-L112)
  * [`test_bare_except_is_broad_but_reraising_handler_is_clean() -> None`](framework/tests/test_antipattern_gate.py#L115-L117)
  * [`test_cache_format_errors_treated_as_misses_are_blocked() -> None`](framework/tests/test_antipattern_gate.py#L120-L146)
  * [`test_candidate_scan_loop_does_not_count_as_silent_discard() -> None`](framework/tests/test_antipattern_gate.py#L149-L168)
  * [`test_discarded_non_strict_load_is_blocked() -> None`](framework/tests/test_antipattern_gate.py#L171-L190)
  * [`test_cuda_device_variants_and_statement_fallbacks_are_blocked() -> None`](framework/tests/test_antipattern_gate.py#L193-L207)
  * [`test_explicit_cuda_refusal_and_guarded_maintenance_are_clean() -> None`](framework/tests/test_antipattern_gate.py#L210-L224)
  * [`test_wall_clock_timers_are_blocked() -> None`](framework/tests/test_antipattern_gate.py#L227-L231)
  * [`test_unsafe_deserialization_and_dynamic_execution_are_blocked() -> None`](framework/tests/test_antipattern_gate.py#L234-L243)
  * [`test_shell_execution_sinks_and_discarded_subprocess_are_blocked() -> None`](framework/tests/test_antipattern_gate.py#L246-L259)
    * *Contract*: HNS017/HNS018 as named; a missing timeout (HNS027) is another rule's subject.
  * [`test_python_provenance_fallbacks_are_blocked() -> None`](framework/tests/test_antipattern_gate.py#L262-L272)
  * [`test_provenance_name_detection_is_precise() -> None`](framework/tests/test_antipattern_gate.py#L275-L285)
  * [`test_provenance_fallbacks_are_blocked_in_shell() -> None`](framework/tests/test_antipattern_gate.py#L288-L296)
  * [`test_provenance_assignment_fallbacks_are_blocked_in_shell() -> None`](framework/tests/test_antipattern_gate.py#L299-L323)
  * [`test_swallowed_failures_are_blocked_except_cleanup() -> None`](framework/tests/test_antipattern_gate.py#L326-L330)
  * [`test_shell_fail_fast_is_required() -> None`](framework/tests/test_antipattern_gate.py#L333-L337)
  * [`test_buffered_python_script_invocation_is_blocked() -> None`](framework/tests/test_antipattern_gate.py#L340-L358)
  * [`test_non_production_paths_are_not_part_of_gate_scope() -> None`](framework/tests/test_antipattern_gate.py#L377-L386)
  * [`test_precommit_wires_the_gate_as_blocking_and_staged() -> None`](framework/tests/test_antipattern_gate.py#L389-L393)
  * [`test_cli_blocks_a_bad_worktree_file(tmp_path: Path, monkeypatch) -> None`](framework/tests/test_antipattern_gate.py#L396-L402)
  * [`test_cli_reads_staged_blob_not_unstaged_worktree(tmp_path: Path, monkeypatch) -> None`](framework/tests/test_antipattern_gate.py#L405-L420)
  * [`test_cli_ignores_non_production_paths(tmp_path: Path, monkeypatch) -> None`](framework/tests/test_antipattern_gate.py#L423-L429)
  * [`test_cli_reports_syntax_errors_as_gate_findings(tmp_path: Path, monkeypatch) -> None`](framework/tests/test_antipattern_gate.py#L432-L440)
  * [`test_directory_arguments_expand_to_checked_files(tmp_path: Path, monkeypatch) -> None`](framework/tests/test_antipattern_gate.py#L443-L467)
  * [`test_paths_outside_the_repo_are_out_of_scope(tmp_path: Path, monkeypatch) -> None`](framework/tests/test_antipattern_gate.py#L470-L479)
  * [`test_committed_production_tree_is_parseable() -> None`](framework/tests/test_antipattern_gate.py#L516-L535)
    * *Contract*: Every committed production file must be parseable by the gate.
  * [`test_extended_python_antipattern_rules() -> None`](framework/tests/test_antipattern_gate.py#L538-L560)
  * [`test_dirty_refusal_rules() -> None`](framework/tests/test_antipattern_gate.py#L563-L584)
    * *Contract*: HNS035 bans the override knob and HNS036 bans a conditional refusal.
  * [`test_extended_shell_antipattern_rules() -> None`](framework/tests/test_antipattern_gate.py#L587-L599)

- [`framework/tests/test_canary_gate.py`](framework/tests/test_canary_gate.py) (143 lines)
  * *Module Purpose*: Unit tests for the GPU canary gate (framework step 4e).
  * [`test_driver_wrapped_in_timeout()`](framework/tests/test_canary_gate.py#L40-L43)
  * [`test_python_variable_driver_is_wrapped()`](framework/tests/test_canary_gate.py#L46-L49)
  * [`test_multiline_driver_arguments_stay_inside_timeout_command()`](framework/tests/test_canary_gate.py#L52-L60)
  * [`test_directives_overridden()`](framework/tests/test_canary_gate.py#L63-L69)
  * [`test_method_and_hook_injected_before_driver()`](framework/tests/test_canary_gate.py#L72-L83)
  * [`test_no_driver_returns_empty()`](framework/tests/test_canary_gate.py#L86-L90)
  * [`test_only_final_driver_is_wrapped()`](framework/tests/test_canary_gate.py#L93-L100)
  * [`test_child_sbatch_is_bounded_when_no_direct_driver()`](framework/tests/test_canary_gate.py#L103-L109)
  * [`test_child_bash_wrapper_is_bounded_once()`](framework/tests/test_canary_gate.py#L112-L119)
  * [`test_timeout_is_a_clean_alive_signal()`](framework/tests/test_canary_gate.py#L122-L125)
  * [`test_method_scopes_canary_name()`](framework/tests/test_canary_gate.py#L128-L129)
  * [`test_verdict_finished_and_alive_pass()`](framework/tests/test_canary_gate.py#L132-L136)
  * [`test_verdict_crash_fails()`](framework/tests/test_canary_gate.py#L139-L143)

- [`framework/tests/test_coverage_gate.py`](framework/tests/test_coverage_gate.py) (543 lines)
  * *Module Purpose*: Tests for the per-file coverage and loop-iteration gate.
  * [`entry_of(statements: int, contexts: dict[str, list[int]], loops: dict[str, dict] | None) -> dict`](framework/tests/test_coverage_gate.py#L18-L30)
    * *Contract*: Return one probe report entry.
  * [`loop_of(*counts) -> dict`](framework/tests/test_coverage_gate.py#L33-L39)
    * *Contract*: Return one loop entry observing ``counts`` iterations.
  * [`run_evaluate(report: dict, baseline: dict | None, mode: str, loop_lines: dict[str, list[int]] | None, waivers: dict[str, dict[str, str]] | None, src_files: tuple[str, ...]) -> list[cov.Finding]`](framework/tests/test_coverage_gate.py#L42-L63)
    * *Contract*: Evaluate one synthetic report through the public gate API.
  * [`baseline_entry(self_pct: float, suite_pct: float, loops_uncovered: list[int] | None, measured: bool) -> dict`](framework/tests/test_coverage_gate.py#L66-L80)
    * *Contract*: Return one baseline file entry.
  * [`test_test_files_for_uses_the_mirror_base_once() -> None`](framework/tests/test_coverage_gate.py#L83-L96)
    * *Contract*: The mirror base is joined with the full source path exactly once.
  * [`test_contexts_for_matches_only_own_nodeids() -> None`](framework/tests/test_coverage_gate.py#L99-L105)
  * [`test_file_metrics_separates_own_and_suite_coverage() -> None`](framework/tests/test_coverage_gate.py#L108-L115)
  * [`test_unmeasured_entry_reports_zero_metrics() -> None`](framework/tests/test_coverage_gate.py#L118-L121)
  * [`test_clean_file_has_no_findings() -> None`](framework/tests/test_coverage_gate.py#L124-L134)
  * [`test_low_coverage_reports_self_and_suite() -> None`](framework/tests/test_coverage_gate.py#L137-L148)
  * [`test_all_mode_requires_the_baseline_suite_floor_too() -> None`](framework/tests/test_coverage_gate.py#L151-L158)
  * [`test_all_mode_grandfathers_recorded_legacy_coverage() -> None`](framework/tests/test_coverage_gate.py#L161-L166)
  * [`test_staged_mode_ignores_grandfathering() -> None`](framework/tests/test_coverage_gate.py#L169-L176)
  * [`test_staged_mode_flags_unmeasured_file() -> None`](framework/tests/test_coverage_gate.py#L179-L182)
  * [`test_staged_mode_flags_a_file_without_tests() -> None`](framework/tests/test_coverage_gate.py#L185-L197)
  * [`test_all_mode_reports_never_imported_files() -> None`](framework/tests/test_coverage_gate.py#L200-L203)
  * [`test_all_mode_skips_recorded_unmeasured_files() -> None`](framework/tests/test_coverage_gate.py#L206-L208)
  * [`test_loop_criterion_requires_zero_one_and_many() -> None`](framework/tests/test_coverage_gate.py#L211-L220)
  * [`test_loop_findings_name_ordinal_and_observed_counts() -> None`](framework/tests/test_coverage_gate.py#L223-L235)
  * [`test_baseline_grandfathers_non_compliant_loops_only_in_all_mode() -> None`](framework/tests/test_coverage_gate.py#L238-L253)
  * [`test_instrumentation_gap_is_detected() -> None`](framework/tests/test_coverage_gate.py#L256-L268)
  * [`test_stale_waiver_is_reported() -> None`](framework/tests/test_coverage_gate.py#L271-L280)
  * [`test_waiver_for_file_outside_the_run_is_not_stale() -> None`](framework/tests/test_coverage_gate.py#L283-L292)
  * [`test_waivers_file_rejects_missing_reasons(tmp_path: Path) -> None`](framework/tests/test_coverage_gate.py#L295-L303)
  * [`test_baseline_regressions_cover_percent_and_loop_drops() -> None`](framework/tests/test_coverage_gate.py#L306-L323)
  * [`make_tmp_repo(tmp_path: Path, monkeypatch) -> Path`](framework/tests/test_coverage_gate.py#L326-L337)
    * *Contract*: Create a minimal repo layout the gate can run against.
  * [`test_cli_requires_the_baseline(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/test_coverage_gate.py#L340-L343)
  * [`test_cli_staged_requires_mirror_tests(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/test_coverage_gate.py#L346-L349)
  * [`test_cli_update_baseline_requires_all_mode(tmp_path: Path, monkeypatch) -> None`](framework/tests/test_coverage_gate.py#L352-L354)
  * [`test_cli_ignores_files_outside_the_source_root(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/test_coverage_gate.py#L357-L362)
  * [`test_cli_ignores_exempt_files(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/test_coverage_gate.py#L365-L368)
  * [`make_evidence_repo(tmp_path: Path, monkeypatch) -> Path`](framework/tests/test_coverage_gate.py#L389-L407)
    * *Contract*: Create a repo layout with a source/mirror-test pair and a pytest config.
  * [`record_clearance(root: Path, cleared: bool) -> None`](framework/tests/test_coverage_gate.py#L410-L428)
    * *Contract*: Write one ledger entry for ``research/a/b.py`` reflecting the current files.
  * [`evidence_codes(root: Path, require_cleared: bool, waivers: dict[str, dict[str, str]] | None) -> list[str]`](framework/tests/test_coverage_gate.py#L431-L452)
    * *Contract*: Return the finding codes of the static clearance decision.
  * [`test_structure_hash_ignores_comments_and_docstrings(tmp_path: Path) -> None`](framework/tests/test_coverage_gate.py#L455-L467)
    * *Contract*: Clearance survives comments, docstrings and line moves, not code edits.
  * [`test_evidence_gate_replays_a_cleared_record(tmp_path: Path, monkeypatch) -> None`](framework/tests/test_coverage_gate.py#L470-L475)
  * [`test_evidence_gate_flags_stale_records(tmp_path: Path, monkeypatch) -> None`](framework/tests/test_coverage_gate.py#L478-L493)
  * [`test_evidence_gate_flags_missing_and_uncleared_records(tmp_path: Path, monkeypatch) -> None`](framework/tests/test_coverage_gate.py#L496-L503)
  * [`test_cli_records_then_replays_clearance(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/test_coverage_gate.py#L506-L520)
    * *Contract*: One staged run records clearance; replays are instant and void after edits.

- [`framework/tests/test_test_mirror_gate.py`](framework/tests/test_test_mirror_gate.py) (158 lines)
  * *Module Purpose*: Tests for the src -> test mirror gate.
  * [`test_mirror_paths_accepts_both_spellings() -> None`](framework/tests/test_test_mirror_gate.py#L27-L31)
  * [`test_evaluate_accepts_both_spellings_and_exempts_packages() -> None`](framework/tests/test_test_mirror_gate.py#L34-L52)
  * [`test_alias_satisfies_a_missing_mirror() -> None`](framework/tests/test_test_mirror_gate.py#L55-L62)
  * [`test_dangling_alias_is_a_finding() -> None`](framework/tests/test_test_mirror_gate.py#L65-L73)
  * [`test_stale_alias_beside_a_real_mirror_is_a_finding() -> None`](framework/tests/test_test_mirror_gate.py#L76-L83)
  * [`test_collect_files_skips_caches_and_third_party(tmp_path, monkeypatch) -> None`](framework/tests/test_test_mirror_gate.py#L86-L94)
  * [`test_collect_files_staged_filter_ignores_other_roots(tmp_path, monkeypatch) -> None`](framework/tests/test_test_mirror_gate.py#L97-L101)
  * [`test_load_aliases_reads_targets(tmp_path) -> None`](framework/tests/test_test_mirror_gate.py#L104-L109)
  * [`test_load_aliases_rejects_a_non_object(tmp_path) -> None`](framework/tests/test_test_mirror_gate.py#L112-L116)
  * [`test_cli_blocks_a_missing_mirror(tmp_path, monkeypatch, capsys) -> None`](framework/tests/test_test_mirror_gate.py#L119-L126)
  * [`test_cli_passes_with_a_real_mirror(tmp_path, monkeypatch, capsys) -> None`](framework/tests/test_test_mirror_gate.py#L129-L134)
  * [`test_cli_missing_alias_table_is_an_environment_error(tmp_path, monkeypatch, capsys) -> None`](framework/tests/test_test_mirror_gate.py#L137-L142)
  * [`test_cli_staged_ignores_non_source_paths(tmp_path, monkeypatch, capsys) -> None`](framework/tests/test_test_mirror_gate.py#L145-L148)
  * [`test_cli_json_report_lists_findings(tmp_path, monkeypatch) -> None`](framework/tests/test_test_mirror_gate.py#L151-L158)

## Package `framework/tests/coverage_gate` — *Tests for the coverage gate and its probe plugin.*

- [`framework/tests/coverage_gate/test_coverage_probe.py`](framework/tests/coverage_gate/test_coverage_probe.py) (90 lines)
  * *Module Purpose*: Integration tests for the coverage probe pytest plugin.
  * [`test_probe_records_statements_loops_and_contexts(tmp_path: Path) -> None`](framework/tests/coverage_gate/test_coverage_probe.py#L30-L45)
    * *Contract*: The probe plugin reports real statement and loop-iteration data.
  * [`run_probe(tmp_path: Path, report_path: Path) -> subprocess.CompletedProcess[str]`](framework/tests/coverage_gate/test_coverage_probe.py#L48-L77)
    * *Contract*: Run the coverage probe over the fixture; return the pytest result.
  * [`write_probe_fixture(tmp_path: Path) -> Path`](framework/tests/coverage_gate/test_coverage_probe.py#L80-L90)
    * *Contract*: Write a tiny package plus its tests; return the probe report path.

## Package `framework/tests/distortion` — *Test package for the framework distortion gate.*

- [`framework/tests/distortion/test_distortion_gate.py`](framework/tests/distortion/test_distortion_gate.py) (159 lines)
  * *Module Purpose*: Unit tests for the surrogate distortion static analysis gate.
  * [`test_hns044_flags_quantized_subtraction() -> None`](framework/tests/distortion/test_distortion_gate.py#L25-L35)
    * *Contract*: Flag weight subtraction preceded by low-precision bfloat16 casting.
  * [`test_hns044_passes_on_full_precision_weight_dose() -> None`](framework/tests/distortion/test_distortion_gate.py#L38-L45)
    * *Contract*: Pass on float64/float32 distance calculation from dose.py.
  * [`test_hns045_flags_pooled_broadcast() -> None`](framework/tests/distortion/test_distortion_gate.py#L48-L57)
    * *Contract*: Flag broadcasting one pooled estimate value across members.
  * [`test_hns045_exemption_is_configured_by_the_project(monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/distortion/test_distortion_gate.py#L60-L78)
    * *Contract*: Exempt the fallback API a project opts in; the same shape stays flagged.
  * [`test_hns045_passes_on_non_estimate_values_and_non_member_iterables() -> None`](framework/tests/distortion/test_distortion_gate.py#L81-L92)
    * *Contract*: Pass when the value or the iterable carries no pooled/member name hint.
  * [`test_hns046_flags_grand_scalar_reduction() -> None`](framework/tests/distortion/test_distortion_gate.py#L95-L104)
    * *Contract*: Flag ratio-of-means scalar reduction over two reductions.
  * [`test_hns046_flags_precomputed_means_and_reversed_ratio() -> None`](framework/tests/distortion/test_distortion_gate.py#L107-L117)
    * *Contract*: Flag ratio using precomputed mean variables and reversed 1.0 subtraction.
  * [`test_hns046_passes_on_meandiff_and_paired_reductions() -> None`](framework/tests/distortion/test_distortion_gate.py#L120-L131)
    * *Contract*: Pass on meandiff function calls and elementwise paired reductions.
  * [`test_cli_clean_file_exits_zero(tmp_path: Path) -> None`](framework/tests/distortion/test_distortion_gate.py#L134-L138)
    * *Contract*: CLI exits with 0 on clean scoped sources under --strict.
  * [`test_cli_dirty_file_exits_one_and_writes_report(tmp_path: Path) -> None`](framework/tests/distortion/test_distortion_gate.py#L141-L153)
    * *Contract*: CLI exits with 1 on dirty sources under --strict and outputs json report.
  * [`test_cli_unreadable_staged_blob_fails_closed() -> None`](framework/tests/distortion/test_distortion_gate.py#L156-L159)
    * *Contract*: CLI emits HNS010 and exits with 1 when staged file cannot be read.

## Package `framework/tests/gates` — *Package.*

- [`framework/tests/gates/test_antipattern_expansion.py`](framework/tests/gates/test_antipattern_expansion.py) (406 lines)
  * *Module Purpose*: Acceptance and evidence tests for the anti-pattern gate expansion (HNS027+).
  * [`codes(source: str, path: str) -> set[str]`](framework/tests/gates/test_antipattern_expansion.py#L37-L39)
    * *Contract*: Return the gate's codes for one source string.
  * [`function_node(source: str, name: str) -> ast.FunctionDef`](framework/tests/gates/test_antipattern_expansion.py#L42-L47)
    * *Contract*: Return the named function of ``source``, or raise when it is absent.
  * [`test_stderr_rejects_the_collapsed_error_bar() -> None`](framework/tests/gates/test_antipattern_expansion.py#L50-L63)
    * *Contract*: ``_stderr`` returns NaN under two samples instead of a zero-width bar (HNS031).
  * [`test_checkpoint_hash_reports_none_without_a_basis() -> None`](framework/tests/gates/test_antipattern_expansion.py#L66-L74)
    * *Contract*: A provenance helper falling back to the literal ``"none"`` (HNS032).
  * [`test_expansion_detects_the_cited_shape(code: str, source: str) -> None`](framework/tests/gates/test_antipattern_expansion.py#L130-L132)
    * *Contract*: Each expansion code fires on the minimal shape it is defined over.
  * [`test_expansion_keeps_the_reviewed_near_misses_silent(source: str) -> None`](framework/tests/gates/test_antipattern_expansion.py#L183-L185)
    * *Contract*: A reviewed near-miss that starts firing is a regression, not a win.
  * [`test_existing_rules_still_fire_on_their_canonical_shapes() -> None`](framework/tests/gates/test_antipattern_expansion.py#L188-L195)
    * *Contract*: The expansion must not have disturbed the rules that were already there.
  * [`production_hits() -> dict[str, set[str]]`](framework/tests/gates/test_antipattern_expansion.py#L199-L209)
    * *Contract*: Every expansion finding in the gate's own production scope, by code.
  * [`test_the_census_covers_the_production_tree() -> None`](framework/tests/gates/test_antipattern_expansion.py#L212-L216)
    * *Contract*: The census must span this repo's production tree, not a fixed site count.
  * [`test_expansion_leaves_the_remediated_error_bar_alone(production_hits: dict[str, set[str]]) -> None`](framework/tests/gates/test_antipattern_expansion.py#L219-L223)
    * *Contract*: HNS031 names no production site: ``_stderr`` now returns ``NaN``, not 0.0.
  * [`test_expansion_leaves_the_reviewed_inert_quotient_alone(production_hits: dict[str, set[str]]) -> None`](framework/tests/gates/test_antipattern_expansion.py#L226-L230)
    * *Contract*: HNS030 names no production site: the one candidate quotient is inert.
  * [`test_expansion_holds_the_dispatch_census(production_hits: dict[str, set[str]]) -> None`](framework/tests/gates/test_antipattern_expansion.py#L233-L237)
    * *Contract*: HNS037 has at most one live site in production; the repair empties it.
  * [`test_optional_input_neutralized_to_a_placeholder_is_reported() -> None`](framework/tests/gates/test_antipattern_expansion.py#L240-L251)
    * *Contract*: The solver took ``Sigma_safe`` and silently dropped the basis constraint.
  * [`test_requiring_the_input_instead_of_substituting_is_silent() -> None`](framework/tests/gates/test_antipattern_expansion.py#L254-L262)
    * *Contract*: Failing closed is the documented repair and must not re-trip the rule.
  * [`test_a_legitimate_default_substitute_stays_silent() -> None`](framework/tests/gates/test_antipattern_expansion.py#L265-L276)
    * *Contract*: ``device = cpu`` is a default, not a dropped constraint.
  * [`test_a_required_input_is_never_a_finding() -> None`](framework/tests/gates/test_antipattern_expansion.py#L279-L290)
    * *Contract*: A parameter that was never optional cannot be silently neutralized.
  * [`test_a_neutral_value_that_escapes_nothing_is_silent() -> None`](framework/tests/gates/test_antipattern_expansion.py#L293-L304)
    * *Contract*: The substitute must be returned or assigned to count as degradation.
  * [`test_a_full_rank_default_selection_stays_silent() -> None`](framework/tests/gates/test_antipattern_expansion.py#L307-L318)
    * *Contract*: ``carrier = None -> eye`` selects everything; nothing was emptied.
  * [`test_a_zeroed_substitute_is_still_reported() -> None`](framework/tests/gates/test_antipattern_expansion.py#L321-L332)
    * *Contract*: ``zeros`` voids a direction, which is the family the rule targets.
  * [`test_a_mode_default_outside_its_dispatch_is_reported() -> None`](framework/tests/gates/test_antipattern_expansion.py#L335-L345)
    * *Contract*: A default mode string that no branch of its own dispatch matches is reported.
  * [`test_a_default_inside_its_own_dispatch_is_silent() -> None`](framework/tests/gates/test_antipattern_expansion.py#L348-L358)
    * *Contract*: Enumerating the default is the documented repair and must stay silent.
  * [`test_a_single_special_case_is_not_a_dispatch_table() -> None`](framework/tests/gates/test_antipattern_expansion.py#L361-L369)
    * *Contract*: One ``==`` beside a general branch is not an enumeration of the modes.
  * [`test_a_literal_beside_an_enumeration_counts_as_handled() -> None`](framework/tests/gates/test_antipattern_expansion.py#L372-L386)
    * *Contract*: ``carrier_mode == "sdp"`` in its own helper claims the default.
  * [`test_a_mode_forwarded_without_a_local_dispatch_is_out_of_scope() -> None`](framework/tests/gates/test_antipattern_expansion.py#L389-L395)
    * *Contract*: A module that only relays the setting cannot discharge the branch itself.
  * [`test_a_non_mode_string_default_is_not_a_dispatch_key() -> None`](framework/tests/gates/test_antipattern_expansion.py#L398-L406)
    * *Contract*: A path or message default is not a mode, even beside a mode table.

- [`framework/tests/gates/test_check_contamination.py`](framework/tests/gates/test_check_contamination.py) (172 lines)
  * *Module Purpose*: Behavioral tests for framework/gates/checks/check_contamination.py (guardrail #2).
  * [`run_gate(bank: dict, strict: bool) -> subprocess.CompletedProcess`](framework/tests/gates/test_check_contamination.py#L16-L29)
  * [`clean_bank() -> dict`](framework/tests/gates/test_check_contamination.py#L32-L36)
  * [`test_clean_bank_passes() -> None`](framework/tests/gates/test_check_contamination.py#L39-L42)
  * [`test_exact_overlap_detected() -> None`](framework/tests/gates/test_check_contamination.py#L45-L50)
  * [`test_lookalike_detected() -> None`](framework/tests/gates/test_check_contamination.py#L53-L59)
  * [`test_single_token_share_not_lookalike() -> None`](framework/tests/gates/test_check_contamination.py#L62-L68)
    * *Contract*: Regression for the min-normalization bug: one shared token must not flag.
  * [`test_nsfw_marker_in_safe_bank_detected() -> None`](framework/tests/gates/test_check_contamination.py#L71-L76)
  * [`test_low_n_flagged() -> None`](framework/tests/gates/test_check_contamination.py#L79-L86)
  * [`test_missing_bank_errors() -> None`](framework/tests/gates/test_check_contamination.py#L89-L99)
  * [`pair_bank() -> dict`](framework/tests/gates/test_check_contamination.py#L102-L112)
    * *Contract*: A certified concept/guide pair bank: pairs plus the criterion it was selected under.
  * [`test_pair_bank_certified_passes() -> None`](framework/tests/gates/test_check_contamination.py#L115-L123)
    * *Contract*: C1-C4 read concept/safe lists a pair bank does not have.
  * [`test_pair_bank_with_an_honest_false_flag_passes() -> None`](framework/tests/gates/test_check_contamination.py#L126-L139)
    * *Contract*: An honest diagnostic reading, not a claim, is not refused.
  * [`test_pair_bank_over_its_threshold_flagged() -> None`](framework/tests/gates/test_check_contamination.py#L142-L148)
  * [`test_pair_bank_claiming_certification_without_its_numbers_flagged() -> None`](framework/tests/gates/test_check_contamination.py#L151-L158)
  * [`test_bank_with_both_layouts_is_graded_by_concept_checks() -> None`](framework/tests/gates/test_check_contamination.py#L161-L172)
    * *Contract*: The pair branch must not become a way past C1-C4.

- [`framework/tests/gates/test_check_duplication.py`](framework/tests/gates/test_check_duplication.py) (283 lines)
  * *Module Purpose*: Tests for the jscpd code duplication precommit gate.
  * [`test_finding_formatting() -> None`](framework/tests/gates/test_check_duplication.py#L39-L49)
  * [`test_resolve_jscpd_bin_custom(tmp_path: Path) -> None`](framework/tests/gates/test_check_duplication.py#L52-L59)
  * [`test_build_jscpd_args(tmp_path: Path) -> None`](framework/tests/gates/test_check_duplication.py#L62-L78)
  * [`test_build_jscpd_args_update_baseline(tmp_path: Path) -> None`](framework/tests/gates/test_check_duplication.py#L81-L92)
  * [`test_parse_jscpd_json(tmp_path: Path) -> None`](framework/tests/gates/test_check_duplication.py#L95-L120)
  * [`test_parse_jscpd_json_empty_or_missing(tmp_path: Path) -> None`](framework/tests/gates/test_check_duplication.py#L123-L127)
  * [`test_parse_stdout_clones() -> None`](framework/tests/gates/test_check_duplication.py#L130-L143)
  * [`test_run_jscpd_on_clean_files(tmp_path: Path) -> None`](framework/tests/gates/test_check_duplication.py#L146-L160)
  * [`test_run_jscpd_on_duplicate_files(tmp_path: Path) -> None`](framework/tests/gates/test_check_duplication.py#L163-L175)
  * [`test_main_cli_clean(tmp_path: Path) -> None`](framework/tests/gates/test_check_duplication.py#L178-L184)
  * [`test_main_cli_duplicates(tmp_path: Path) -> None`](framework/tests/gates/test_check_duplication.py#L187-L202)
  * [`test_parse_args_defaults() -> None`](framework/tests/gates/test_check_duplication.py#L205-L210)
  * [`test_matches_staged() -> None`](framework/tests/gates/test_check_duplication.py#L213-L235)
  * [`test_missing_jscpd_binary(tmp_path: Path) -> None`](framework/tests/gates/test_check_duplication.py#L238-L254)
  * [`test_evaluate_duplication_staged_filtering(tmp_path: Path) -> None`](framework/tests/gates/test_check_duplication.py#L257-L283)

- [`framework/tests/gates/test_local_gate.py`](framework/tests/gates/test_local_gate.py) (51 lines)
  * *Module Purpose*: Expected behavior for the local gate's undefined-name audit.
  * [`test_a_module_level_except_binding_is_not_undefined() -> None`](framework/tests/gates/test_local_gate.py#L42-L43)
  * [`test_a_function_except_binding_is_not_undefined() -> None`](framework/tests/gates/test_local_gate.py#L46-L47)
  * [`test_a_truly_undefined_name_is_still_reported() -> None`](framework/tests/gates/test_local_gate.py#L50-L51)

- [`framework/tests/gates/test_log_mlflow_run.py`](framework/tests/gates/test_log_mlflow_run.py) (105 lines)
  * *Module Purpose*: Behavioral tests for framework/gates/provenance/log_mlflow_run.py (doc layer).
  * [`make_manifest(tmp: Path) -> Path`](framework/tests/gates/test_log_mlflow_run.py#L19-L34)
  * [`log(tmp: Path, *extra) -> subprocess.CompletedProcess`](framework/tests/gates/test_log_mlflow_run.py#L37-L47)
  * [`test_empty_metrics_logs_run_with_pin_params(tmp_path: Path) -> None`](framework/tests/gates/test_log_mlflow_run.py#L50-L58)
  * [`test_metrics_tags_params_land(tmp_path: Path) -> None`](framework/tests/gates/test_log_mlflow_run.py#L61-L79)
  * [`test_bad_manifest_fails_clean(tmp_path: Path) -> None`](framework/tests/gates/test_log_mlflow_run.py#L82-L99)
  * [`test_invalid_metric_kv_fails(tmp_path: Path) -> None`](framework/tests/gates/test_log_mlflow_run.py#L102-L105)

## Package `framework/tests/gates/params` — *Tests for the parameter registry gates.*

- [`framework/tests/gates/params/test_param_duplicates.py`](framework/tests/gates/params/test_param_duplicates.py) (419 lines)
  * *Module Purpose*: Fixtures for the parameter-drift matchers and the gate CLI.
  * [`test_python_and_shell_alias_are_hns038() -> None`](framework/tests/gates/params/test_param_duplicates.py#L65-L76)
  * [`test_alias_matching_respects_token_boundaries() -> None`](framework/tests/gates/params/test_param_duplicates.py#L79-L82)
  * [`test_registered_env_reads_are_hns039() -> None`](framework/tests/gates/params/test_param_duplicates.py#L85-L97)
  * [`test_env_helper_reads_are_hns039() -> None`](framework/tests/gates/params/test_param_duplicates.py#L100-L106)
  * [`test_argparse_default_is_scoped_to_owner_modules(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L109-L119)
  * [`test_argparse_default_through_a_local_alias_is_flagged(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L122-L138)
  * [`test_argparse_default_none_is_not_a_second_default() -> None`](framework/tests/gates/params/test_param_duplicates.py#L141-L144)
  * [`test_integer_flag_pair_restating_the_default_is_flagged() -> None`](framework/tests/gates/params/test_param_duplicates.py#L147-L153)
  * [`test_flag_pair_with_an_explicit_value_is_allowed() -> None`](framework/tests/gates/params/test_param_duplicates.py#L156-L159)
  * [`test_tuple_recipe_restating_the_default_is_flagged() -> None`](framework/tests/gates/params/test_param_duplicates.py#L162-L168)
  * [`test_registered_constant_assignment_is_scoped_by_owner(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L171-L180)
  * [`test_registry_reads_are_not_constant_findings(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L183-L190)
  * [`test_getattr_default_is_hns039() -> None`](framework/tests/gates/params/test_param_duplicates.py#L193-L199)
  * [`test_shell_fallback_drift_requires_the_deviation_form() -> None`](framework/tests/gates/params/test_param_duplicates.py#L202-L211)
  * [`test_shell_quoted_fallbacks_compare_unquoted() -> None`](framework/tests/gates/params/test_param_duplicates.py#L214-L223)
  * [`test_python_literals_ignore_docstrings_but_flag_values(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L226-L236)
  * [`test_one_line_reports_each_parameter_once(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L239-L253)
  * [`test_shell_deviation_statement_is_allowed(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L256-L266)
  * [`test_shell_inline_deviation_prefix_is_allowed(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L269-L273)
  * [`test_unparseable_python_is_hns041() -> None`](framework/tests/gates/params/test_param_duplicates.py#L276-L279)
  * [`test_shipped_registry_is_wellformed() -> None`](framework/tests/gates/params/test_param_duplicates.py#L282-L283)
  * [`test_registry_self_check_detects_a_duplicate_name(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L286-L293)
  * [`test_registry_self_check_detects_a_duplicate_env(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L296-L303)
  * [`test_registry_self_check_detects_a_duplicate_alias(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L306-L313)
  * [`test_registry_self_check_detects_a_duplicate_literal(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L316-L323)
  * [`test_registry_self_check_detects_an_alias_env_collision(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L326-L333)
  * [`test_registry_self_check_detects_a_malformed_row(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L336-L352)
  * [`test_registry_self_check_detects_an_unpinned_snapshot(monkeypatch) -> None`](framework/tests/gates/params/test_param_duplicates.py#L355-L360)
  * [`test_scope_filters_exempt_and_skipped_paths() -> None`](framework/tests/gates/params/test_param_duplicates.py#L363-L368)
  * [`test_every_exempt_path_exists() -> None`](framework/tests/gates/params/test_param_duplicates.py#L371-L376)
    * *Contract*: A moved file must not leave a stale exemption behind.
  * [`test_main_reports_findings_and_writes_the_tally(tmp_path) -> None`](framework/tests/gates/params/test_param_duplicates.py#L379-L392)
  * [`test_main_passes_on_a_clean_file(tmp_path, capsys) -> None`](framework/tests/gates/params/test_param_duplicates.py#L395-L400)
  * [`test_module_body_reexecutes_without_side_effects() -> None`](framework/tests/gates/params/test_param_duplicates.py#L403-L419)

- [`framework/tests/gates/params/test_param_usage.py`](framework/tests/gates/params/test_param_usage.py) (161 lines)
  * *Module Purpose*: Tests for the parameter usage sweep (codes HNS042, HNS043).
  * [`test_a_named_accessor_call_reads_the_row() -> None`](framework/tests/gates/params/test_param_usage.py#L31-L34)
  * [`test_an_aliased_accessor_call_reads_the_row() -> None`](framework/tests/gates/params/test_param_usage.py#L37-L43)
  * [`test_a_dotted_call_through_the_package_module_reads_the_row() -> None`](framework/tests/gates/params/test_param_usage.py#L46-L49)
  * [`test_a_generic_accessor_with_the_name_reads_the_row() -> None`](framework/tests/gates/params/test_param_usage.py#L52-L56)
  * [`test_a_generic_accessor_of_another_name_is_not_a_reader() -> None`](framework/tests/gates/params/test_param_usage.py#L59-L63)
  * [`test_an_imported_constant_reads_the_row() -> None`](framework/tests/gates/params/test_param_usage.py#L66-L69)
  * [`test_an_ambient_read_of_the_env_var_is_not_a_reader() -> None`](framework/tests/gates/params/test_param_usage.py#L72-L76)
  * [`test_a_test_file_is_not_a_reader() -> None`](framework/tests/gates/params/test_param_usage.py#L79-L84)
  * [`test_the_parameter_package_is_not_a_reader() -> None`](framework/tests/gates/params/test_param_usage.py#L87-L92)
  * [`test_a_root_outside_the_consuming_set_is_not_a_reader() -> None`](framework/tests/gates/params/test_param_usage.py#L95-L98)
  * [`test_a_docstring_mention_is_not_a_reader() -> None`](framework/tests/gates/params/test_param_usage.py#L101-L104)
  * [`test_an_undeclared_accessor_is_a_finding() -> None`](framework/tests/gates/params/test_param_usage.py#L107-L111)
  * [`test_a_declared_implementation_must_compare_the_default() -> None`](framework/tests/gates/params/test_param_usage.py#L114-L123)
  * [`test_a_comparing_implementation_is_clean() -> None`](framework/tests/gates/params/test_param_usage.py#L126-L135)
  * [`test_a_missing_implementation_module_is_a_finding() -> None`](framework/tests/gates/params/test_param_usage.py#L138-L141)
  * [`test_the_live_rows_name_their_accessors_and_defaults() -> None`](framework/tests/gates/params/test_param_usage.py#L144-L152)
  * [`test_the_live_tree_compares_every_declared_default() -> None`](framework/tests/gates/params/test_param_usage.py#L155-L161)

## Package `framework/tests/harness` — *Harness registry tests: project identity and the interpreter floor.*

- [`framework/tests/harness/test_harness.py`](framework/tests/harness/test_harness.py) (70 lines)
  * *Module Purpose*: Tests for the harness registry: project identity and the interpreter floor.
  * [`test_python_refuses_an_interpreter_below_the_floor(tmp_path, monkeypatch) -> None`](framework/tests/harness/test_harness.py#L30-L39)
  * [`test_python_accepts_an_interpreter_at_the_floor(tmp_path, monkeypatch) -> None`](framework/tests/harness/test_harness.py#L42-L46)
  * [`test_floor_matches_the_packaging_floor() -> None`](framework/tests/harness/test_harness.py#L49-L52)
  * [`test_floor_is_exposed_as_a_key() -> None`](framework/tests/harness/test_harness.py#L55-L56)
  * [`test_dvc_bin_prefers_the_venv_binary(tmp_path, monkeypatch) -> None`](framework/tests/harness/test_harness.py#L59-L70)

## Package `framework/tests/indexing` — *Tests for framework.indexing Table-of-Contents subsystem.*

- [`framework/tests/indexing/test_formatter.py`](framework/tests/indexing/test_formatter.py) (85 lines)
  * *Module Purpose*: Unit tests for framework.indexing.formatter.
  * [`test_format_markdown_index_line_ranges(tmp_path: Path) -> None`](framework/tests/indexing/test_formatter.py#L48-L63)
    * *Contract*: Verify TOC specifies line ranges and slicing matches section content.
  * [`test_format_sub_and_master_index(tmp_path: Path) -> None`](framework/tests/indexing/test_formatter.py#L66-L85)
    * *Contract*: Verify sub-index local TOC and master index sub-index pointers.

- [`framework/tests/indexing/test_gate.py`](framework/tests/indexing/test_gate.py) (192 lines)
  * *Module Purpose*: Unit tests for framework.indexing.gate.
  * [`test_verify_index_freshness(tmp_path: Path) -> None`](framework/tests/indexing/test_gate.py#L24-L38)
    * *Contract*: Verify freshness check distinguishes between synced, drifted, and missing index.
  * [`test_audit_contract_coverage() -> None`](framework/tests/indexing/test_gate.py#L41-L49)
    * *Contract*: Verify contract coverage stats accurately meter documented functions.
  * [`test_plan_index_files_splitting(tmp_path: Path) -> None`](framework/tests/indexing/test_gate.py#L52-L80)
    * *Contract*: Verify plan_index_files splits into tree when exceeding max_lines.
  * [`test_run_index_gate_integration(tmp_path: Path) -> None`](framework/tests/indexing/test_gate.py#L83-L96)
    * *Contract*: Verify run_index_gate creates index on update and validates on check.
  * [`test_check_module_contracts() -> None`](framework/tests/indexing/test_gate.py#L99-L107)
    * *Contract*: Verify check_module_contracts filters to production scope and reports errors.
  * [`test_check_interface_drift_detects_drift(tmp_path: Path, monkeypatch) -> None`](framework/tests/indexing/test_gate.py#L110-L131)
    * *Contract*: Verify drift detection flags signature changes without doc updates.
  * [`test_strict_contracts_mode(tmp_path: Path) -> None`](framework/tests/indexing/test_gate.py#L134-L141)
    * *Contract*: Verify run_index_gate with strict_contracts=True fails on contract errors.
  * [`test_load_contract_config_defaults(tmp_path: Path) -> None`](framework/tests/indexing/test_gate.py#L144-L150)
    * *Contract*: Verify default contract config when pyproject.toml is absent.
  * [`test_load_contract_config_custom(tmp_path: Path) -> None`](framework/tests/indexing/test_gate.py#L153-L163)
    * *Contract*: Verify custom contract config loaded from pyproject.toml.
  * [`test_parse_contracts_fallback() -> None`](framework/tests/indexing/test_gate.py#L166-L175)
    * *Contract*: Verify fallback parser extracts lists without toml library.
  * [`test_check_module_contracts_custom_config() -> None`](framework/tests/indexing/test_gate.py#L178-L192)
    * *Contract*: Verify check_module_contracts respects custom enforce and exclude rules.

- [`framework/tests/indexing/test_scanner.py`](framework/tests/indexing/test_scanner.py) (126 lines)
  * *Module Purpose*: Unit tests for framework.indexing.scanner.
  * [`test_scan_module_text_functions_and_classes() -> None`](framework/tests/indexing/test_scanner.py#L15-L44)
    * *Contract*: Verify function signatures, class bases, and doc summaries are extracted.
  * [`test_scan_module_text_async_and_kwonly() -> None`](framework/tests/indexing/test_scanner.py#L47-L64)
    * *Contract*: Verify async functions, varargs, and kwonlyargs are formatted.
  * [`test_scan_module_syntax_error() -> None`](framework/tests/indexing/test_scanner.py#L67-L70)
    * *Contract*: Verify unparseable syntax returns None instead of failing.
  * [`test_scan_file_reads_source(tmp_path: Path) -> None`](framework/tests/indexing/test_scanner.py#L73-L82)
    * *Contract*: Verify scan_file reads on-disk files relative to repo root.
  * [`test_two_tier_docstring_extraction() -> None`](framework/tests/indexing/test_scanner.py#L85-L107)
    * *Contract*: Verify two-tier docstring parsing extracts thumbnail and structured sections.
  * [`test_two_tier_docstring_validation_errors() -> None`](framework/tests/indexing/test_scanner.py#L110-L126)
    * *Contract*: Verify validation errors are recorded for missing or invalid docstrings.

