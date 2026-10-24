# Research Sub-Index: `framework`

> [!NOTE]
> Sub-index for the `framework` package hierarchy. Use the line ranges below to load specific sections directly into context.

**Repository Statistics**: 83 modules | 22 classes | 686 public functions.

## Table of Contents

- [`framework`](#package-framework) (lines 43–67) — *Repository gate framework (hooks + checkers).*
- [`framework/gates`](#package-frameworkgates) (lines 68–95) — *Blocking and advisory repository gates.*
- [`framework/gates/antipattern`](#package-frameworkgatesantipattern) (lines 96–129) — *Internals of the production anti-pattern gate.*
- [`framework/gates/antipattern/execution`](#package-frameworkgatesantipatternexecution) (lines 130–138) — *Execution-sink anti-patterns for the production gate (HNS081, HNS082).*
- [`framework/gates/antipattern/liveness`](#package-frameworkgatesantipatternliveness) (lines 139–145) — *Liveness checks for the production anti-pattern gate (HNS072).*
- [`framework/gates/checks`](#package-frameworkgateschecks) (lines 146–230) — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*
- [`framework/gates/coverage`](#package-frameworkgatescoverage) (lines 231–290) — *Internals of the per-file coverage and loop-iteration gate.*
- [`framework/gates/distortion`](#package-frameworkgatesdistortion) (lines 291–337) — *Surrogate distortion gate package for detecting HNS044, HNS045, and HNS046.*
- [`framework/gates/freshness`](#package-frameworkgatesfreshness) (lines 338–376) — *Freshness and ref-provenance gates.*
- [`framework/gates/instructions`](#package-frameworkgatesinstructions) (lines 377–394) — *Fail-closed reference check for agent instruction artifacts.*
- [`framework/gates/limits`](#package-frameworkgateslimits) (lines 395–452)
- [`framework/gates/mutation`](#package-frameworkgatesmutation) (lines 453–558) — *Mutation-evidence gate: content-addressed mutmut verdicts for staged modules.*
- [`framework/gates/params`](#package-frameworkgatesparams) (lines 559–599) — *Parameter-drift gate package: registry matchers, CLI and their fixtures.*
- [`framework/gates/params/primitives`](#package-frameworkgatesparamsprimitives) (lines 600–604) — *Pure AST and text primitives of the parameter-drift matchers.*
- [`framework/gates/provenance`](#package-frameworkgatesprovenance) (lines 605–641) — *Run-provenance gates: GPU canary, run manifest, replay verification, MLflow log.*
- [`framework/gates/typecheck`](#package-frameworkgatestypecheck) (lines 642–720) — *Static-type gate: staged mypy enforcement with an advisory pyright census.*
- [`framework/indexing`](#package-frameworkindexing) (lines 721–772) — *AST-based repository mapping and Table-of-Contents indexing.*
- [`framework/tests`](#package-frameworktests) (lines 773–931)
- [`framework/tests/antipattern`](#package-frameworktestsantipattern) (lines 932–1019) — *Anti-pattern extension tests (HNS066/067/069/072/081/082).*
- [`framework/tests/coverage_gate`](#package-frameworktestscoverage-gate) (lines 1020–1030) — *Tests for the coverage gate and its probe plugin.*
- [`framework/tests/distortion`](#package-frameworktestsdistortion) (lines 1031–1057) — *Test package for the framework distortion gate.*
- [`framework/tests/freshness`](#package-frameworktestsfreshness) (lines 1058–1110) — *Tests for freshness and ref guard gates.*
- [`framework/tests/gates`](#package-frameworktestsgates) (lines 1111–1223) — *Package.*
- [`framework/tests/gates/instructions`](#package-frameworktestsgatesinstructions) (lines 1224–1263) — *Tests for instruction reference validation.*
- [`framework/tests/gates/params`](#package-frameworktestsgatesparams) (lines 1264–1322) — *Tests for the parameter registry gates.*
- [`framework/tests/gates/ratchet`](#package-frameworktestsgatesratchet) (lines 1323–1345) — *Ratchet gates: tables that may only shrink.*
- [`framework/tests/harness`](#package-frameworktestsharness) (lines 1346–1362) — *Harness registry tests: project identity and the interpreter floor.*
- [`framework/tests/hook_hygiene`](#package-frameworktestshook-hygiene) (lines 1363–1371) — *Tests for the hook/test-process boundary.*
- [`framework/tests/indexing`](#package-frameworktestsindexing) (lines 1372–1420) — *Tests for framework.indexing Table-of-Contents subsystem.*
- [`framework/tests/typecheck`](#package-frameworkteststypecheck) (lines 1421–1471) — *Tests for the static-type gate.*

---

## Package `framework` — *Repository gate framework (hooks + checkers).*

- [`framework/harness.py`](framework/harness.py) (303 lines)
  * *Module Purpose*: Single registry for the project identity, path roots and interpreter the harness uses.
  * [`env(name: str) -> str`](framework/harness.py#L118-L121)
    * *Contract*: Return the canonical env-var spelling of a harness parameter.
  * [`env_regex() -> str`](framework/harness.py#L124-L127)
    * *Contract*: Return the ERE that matches every canonical env var of this project.
  * [`venv() -> str`](framework/harness.py#L130-L139)
    * *Contract*: Return the interpreter directory: override, per-cluster, or the checkout venv.
  * [`python() -> str`](framework/harness.py#L166-L184)
    * *Contract*: Return the project interpreter: env override, venv binary, else this one.
  * [`deploy_root() -> str`](framework/harness.py#L187-L190)
    * *Contract*: Return the checkout the jobs import: env override, else this repository.
  * [`mlflow_uri() -> str`](framework/harness.py#L193-L196)
    * *Contract*: Return the MLflow tracking URI: env override, else this checkout's mlruns dir.
  * [`dvc_bin() -> str`](framework/harness.py#L199-L206)
    * *Contract*: Return the DVC executable: env override, the venv binary, else ``dvc`` on PATH.
  * [`engine_bin(name: str) -> str`](framework/harness.py#L209-L218)
    * *Contract*: Return an external checker: env override, the venv binary, else ``name`` on PATH.
  * [`scope_regex(roots: tuple[str, ...], suffix: str) -> str`](framework/harness.py#L221-L225)
    * *Contract*: Return an ERE anchoring ``roots`` (plus optional per-root suffix) at the start.
  * [`main(argv: list[str]) -> int`](framework/harness.py#L279-L299)
    * *Contract*: Print every key, one key (``--get``), or the hook assignments (``--shell``).

## Package `framework/gates` — *Blocking and advisory repository gates.*

- [`framework/gates/check_antipatterns.py`](framework/gates/check_antipatterns.py) (180 lines)
  * *Module Purpose*: Fail-closed static checks for high-risk production anti-patterns.
  * [`analyze_source(source: str, path: str) -> list[framework.gates.antipattern.targets.Finding]`](framework/gates/check_antipatterns.py#L119-L127)
  * [`main(argv: list[str] | None) -> int`](framework/gates/check_antipatterns.py#L163-L176)

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

- [`framework/gates/antipattern/fallthrough_checks.py`](framework/gates/antipattern/fallthrough_checks.py) (591 lines)
  * *Module Purpose*: Predicates for handler, dispatcher, response and dead-guard shapes.
  * [`placeholder_fallthrough(handler: ast.ExceptHandler, function: ast.AST) -> str | None`](framework/gates/antipattern/fallthrough_checks.py#L216-L229)
    * *Contract*: Return the placeholder a log-only handler lets reach the caller.
  * [`optional_input_neutralized(function: ast.AST) -> tuple[ast.If, str] | None`](framework/gates/antipattern/fallthrough_checks.py#L321-L336)
    * *Contract*: Return the branch and input whose absence becomes a valid-but-empty value.
  * [`dispatch_fallthrough(tree: ast.Module) -> list[tuple[ast.AST, str]]`](framework/gates/antipattern/fallthrough_checks.py#L443-L459)
    * *Contract*: Return mode defaults the module's own enumerated dispatch never matches.
  * [`check_positional_parsing(tree: ast.AST, path: str) -> list[framework.gates.antipattern.targets.Finding]`](framework/gates/antipattern/fallthrough_checks.py#L549-L562)
    * *Contract*: Return findings for naive ``[0]`` indexing into an LLM response object.
  * [`check_deletion_avoidance(tree: ast.AST, path: str) -> list[framework.gates.antipattern.targets.Finding]`](framework/gates/antipattern/fallthrough_checks.py#L578-L591)
    * *Contract*: Return findings for dead ``if``/``while`` guards left around removed code.

- [`framework/gates/antipattern/python_checks.py`](framework/gates/antipattern/python_checks.py) (592 lines)
  * *Module Purpose*: Python-AST analysis helpers and their pattern constants.

- [`framework/gates/antipattern/python_visitor.py`](framework/gates/antipattern/python_visitor.py) (600 lines)
  * *Module Purpose*: AST visitor for the Python anti-pattern rules and its entry point.
  * [`analyze_python(source: str, path: str) -> list[framework.gates.antipattern.targets.Finding]`](framework/gates/antipattern/python_visitor.py#L579-L600)
    * *Contract*: Return findings for one Python source string.

- [`framework/gates/antipattern/shell_checks.py`](framework/gates/antipattern/shell_checks.py) (446 lines)
  * *Module Purpose*: Shell/slurm anti-pattern analysis and its pattern constants.
  * [`analyze_shell(source: str, path: str) -> list[framework.gates.antipattern.targets.Finding]`](framework/gates/antipattern/shell_checks.py#L418-L446)
    * *Contract*: Return findings for shell/slurm provenance and hygiene problems.

- [`framework/gates/antipattern/targets.py`](framework/gates/antipattern/targets.py) (116 lines)
  * *Module Purpose*: Scope constants, findings and target-file resolution.
  * [`class Finding`](framework/gates/antipattern/targets.py#L32-L41)
    * *Contract*: One source-level anti-pattern finding.
    * [`Finding.format(self) -> str`](framework/gates/antipattern/targets.py#L40-L41)

## Package `framework/gates/antipattern/execution` — *Execution-sink anti-patterns for the production gate (HNS081, HNS082).*

- [`framework/gates/antipattern/execution/checks.py`](framework/gates/antipattern/execution/checks.py) (201 lines)
  * *Module Purpose*: Execution-sink anti-patterns for the production gate (HNS081, HNS082).
  * [`check_shell_injection(tree: ast.AST, path: str) -> list[Finding]`](framework/gates/antipattern/execution/checks.py#L120-L129)
    * *Contract*: Return findings for a shell sink fed an unquoted interpolated command.
  * [`check_silent_exception_swallowing(tree: ast.AST, path: str) -> list[Finding]`](framework/gates/antipattern/execution/checks.py#L191-L201)
    * *Contract*: Return findings for a broad handler that silently suppresses failure.

## Package `framework/gates/antipattern/liveness` — *Liveness checks for the production anti-pattern gate (HNS072).*

- [`framework/gates/antipattern/liveness/checks.py`](framework/gates/antipattern/liveness/checks.py) (77 lines)
  * *Module Purpose*: HNS072: a constant-true loop whose body cannot reach an exit.
  * [`check_loop_termination(tree: ast.AST, path: str) -> list[Finding]`](framework/gates/antipattern/liveness/checks.py#L69-L77)
    * *Contract*: Return one HNS072 finding per constant-true loop with no exit.

## Package `framework/gates/checks` — *Standalone checker gates: contamination, mirrors, local lint, agent mirrors, probe.*

- [`framework/gates/checks/check_contamination.py`](framework/gates/checks/check_contamination.py) (290 lines)
  * *Module Purpose*: Contamination gate — automated overlap & quality check for curated bank pairs.
  * [`log_event(target: str, gate: str, result: str, reason: str) -> None`](framework/gates/checks/check_contamination.py#L51-L73)
  * [`load_bank(path: Path) -> dict`](framework/gates/checks/check_contamination.py#L76-L105)
  * [`normalized(s: str) -> str`](framework/gates/checks/check_contamination.py#L137-L138)
  * [`token_overlap(a: str, b: str) -> float`](framework/gates/checks/check_contamination.py#L141-L146)
  * [`check_bank(path: Path, strict: bool, markers: Sequence[str]) -> list[str]`](framework/gates/checks/check_contamination.py#L208-L227)
  * [`main(argv: list[str] | None) -> int`](framework/gates/checks/check_contamination.py#L257-L286)

- [`framework/gates/checks/check_duplication.py`](framework/gates/checks/check_duplication.py) (503 lines)
  * *Module Purpose*: Fail-closed copy-paste detection gate for staged or whole-tree code.
  * [`class Finding`](framework/gates/checks/check_duplication.py#L53-L63)
    * *Contract*: One duplicate code finding reported by the gate.
    * [`Finding.format(self) -> str`](framework/gates/checks/check_duplication.py#L61-L63)
      * *Contract*: Format finding for terminal or log output.
  * [`resolve_jscpd_bin(custom_path: str | None) -> str | None`](framework/gates/checks/check_duplication.py#L66-L78)
    * *Contract*: Resolve the path to the jscpd executable.
  * [`collect_staged_files(repo_root: Path) -> list[str]`](framework/gates/checks/check_duplication.py#L81-L107)
    * *Contract*: Retrieve list of staged files suitable for duplication check.
  * [`build_jscpd_args(jscpd_bin: str, target_paths: Sequence[str], config_path: Path | None, baseline_path: Path | None, update_baseline: bool, output_dir: Path | None) -> list[str]`](framework/gates/checks/check_duplication.py#L110-L131)
    * *Contract*: Assemble argument list for the jscpd subprocess invocation.
  * [`parse_jscpd_json(report_file: Path, baseline_active: bool) -> list[Finding]`](framework/gates/checks/check_duplication.py#L134-L154)
    * *Contract*: Parse findings from jscpd JSON report output.
  * [`parse_stdout_clones(stdout: str, baseline_active: bool) -> list[Finding]`](framework/gates/checks/check_duplication.py#L157-L180)
    * *Contract*: Parse clone occurrences directly from jscpd stdout lines.
  * [`run_jscpd(jscpd_bin: str, target_paths: Sequence[str], config_path: Path | None, baseline_path: Path | None, update_baseline: bool, repo_root: Path) -> tuple[int, list[Finding], str]`](framework/gates/checks/check_duplication.py#L200-L229)
    * *Contract*: Execute jscpd subprocess and parse clone findings.
  * [`uncovered_clone_findings(jscpd_bin: str, target_paths: Sequence[str], config_path: Path | None, baseline_path: Path, repo_root: Path) -> list[Finding]`](framework/gates/checks/check_duplication.py#L232-L259)
    * *Contract*: Locate the clones the committed (HEAD) baseline does not cover.
  * [`check_baseline_ratchet(repo_root: Path, baseline_path: Path, uncovered: Sequence[Finding]) -> list[Finding]`](framework/gates/checks/check_duplication.py#L314-L330)
    * *Contract*: Block expansion of the committed jscpd baseline (ratchet-only).
  * [`evaluate_duplication(target_files: Sequence[str], staged: bool, baseline_path: Path | None, update_baseline: bool, config_path: Path | None, custom_jscpd: str | None, repo_root: Path) -> tuple[list[Finding], str]`](framework/gates/checks/check_duplication.py#L349-L376)
    * *Contract*: Evaluate codebase or target files for duplication violations.
  * [`parse_args(argv: Sequence[str] | None) -> argparse.Namespace`](framework/gates/checks/check_duplication.py#L458-L464)
    * *Contract*: Parse command line options for duplication checker.
  * [`output_json_report(findings: Sequence[Finding], dest: Path) -> None`](framework/gates/checks/check_duplication.py#L467-L473)
    * *Contract*: Save findings array to JSON file destination.
  * [`main(argv: Sequence[str] | None) -> int`](framework/gates/checks/check_duplication.py#L476-L499)
    * *Contract*: Run duplication evaluation and exit with status code.

- [`framework/gates/checks/check_test_mirror.py`](framework/gates/checks/check_test_mirror.py) (533 lines)
  * *Module Purpose*: Fail-closed test-mirror check for the production source tree.
  * [`class Finding`](framework/gates/checks/check_test_mirror.py#L88-L96)
    * *Contract*: One missing or broken src -> test mirror.
    * [`Finding.format(self) -> str`](framework/gates/checks/check_test_mirror.py#L95-L96)
  * [`mirror_paths(rel: str, tests_root: str) -> list[str]`](framework/gates/checks/check_test_mirror.py#L99-L108)
    * *Contract*: Return the accepted mirror test paths for one source file.
  * [`is_checked_path(rel: str, src: str) -> bool`](framework/gates/checks/check_test_mirror.py#L111-L114)
    * *Contract*: Return whether ``rel`` is a source module the gate is responsible for.
  * [`is_skipped(rel: str) -> bool`](framework/gates/checks/check_test_mirror.py#L117-L118)
  * [`collect_files(src: str, staged: Sequence[str] | None) -> list[str]`](framework/gates/checks/check_test_mirror.py#L121-L129)
    * *Contract*: Return the source files to check, sorted and de-duplicated.
  * [`is_exempt_mirror_test(mirror: str) -> bool`](framework/gates/checks/check_test_mirror.py#L138-L141)
    * *Contract*: Return whether ``mirror`` is a fixture module exempt from HNS068.
  * [`defines_test_function(source: str) -> bool`](framework/gates/checks/check_test_mirror.py#L270-L280)
    * *Contract*: True when ``source`` defines at least one ``test_*`` function.
  * [`grade_oracle_file(rel: str, source: str) -> list[Finding]`](framework/gates/checks/check_test_mirror.py#L283-L289)
    * *Contract*: Return HNS068/HNS070 findings for one test file's own text.
  * [`evaluate(files: Sequence[str], aliases: Mapping[str, Sequence[str]], exists: Callable[[str], bool], tests_root: str) -> list[Finding]`](framework/gates/checks/check_test_mirror.py#L321-L335)
    * *Contract*: Return one finding per source module without a valid test mirror.
  * [`load_aliases(path: Path) -> dict[str, list[str]]`](framework/gates/checks/check_test_mirror.py#L338-L354)
  * [`check_alias_ratchet(repo_root: Path, alias_path: Path, current_aliases: Mapping[str, Sequence[str]]) -> list[Finding]`](framework/gates/checks/check_test_mirror.py#L372-L400)
    * *Contract*: Block newly added alias mappings (MIR003); the table may only shrink.
  * [`main(argv: Sequence[str] | None) -> int`](framework/gates/checks/check_test_mirror.py#L501-L529)

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

- [`framework/gates/coverage/run.py`](framework/gates/coverage/run.py) (515 lines)
  * *Module Purpose*: Probe invocation: pytest selection, execution and report validation.
  * [`check_waiver_ratchet(repo: Path, waivers_path: Path, current_waivers: Mapping[str, Mapping[str, str]]) -> list[Finding]`](framework/gates/coverage/run.py#L408-L436)
    * *Contract*: Block loop-waiver additions absent from HEAD; waivers only shrink.

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

## Package `framework/gates/freshness` — *Freshness and ref-provenance gates.*

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

- [`framework/gates/freshness/ref_guard.py`](framework/gates/freshness/ref_guard.py) (361 lines)
  * *Module Purpose*: Block ref moves that would bypass the pre-commit gate battery.
  * [`class TransLine`](framework/gates/freshness/ref_guard.py#L69-L74)
    * *Contract*: One ``<old> <new> <ref>`` line of a reference transaction.
  * [`main(argv: Sequence[str] | None) -> int`](framework/gates/freshness/ref_guard.py#L345-L357)
    * *Contract*: Judge a prepared transaction; allow non-prepared states and fail closed.

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

## Package `framework/gates/instructions` — *Fail-closed reference check for agent instruction artifacts.*

- [`framework/gates/instructions/check_instruction_refs.py`](framework/gates/instructions/check_instruction_refs.py) (499 lines)
  * *Module Purpose*: Fail-closed reference check for agent instruction artifacts (HNS073).
  * [`class Finding`](framework/gates/instructions/check_instruction_refs.py#L122-L131)
    * *Contract*: One stale file reference in an instruction artifact.
    * [`Finding.format(self) -> str`](framework/gates/instructions/check_instruction_refs.py#L130-L131)
  * [`class Root`](framework/gates/instructions/check_instruction_refs.py#L135-L143)
    * *Contract*: One tracked tree a reference may resolve in.
  * [`class Census`](framework/gates/instructions/check_instruction_refs.py#L147-L151)
    * *Contract*: Bucket counts plus the findings for one graded artifact.
  * [`census(path: str, text: str, roots: Sequence[Root], allow_placeholder: bool) -> Census`](framework/gates/instructions/check_instruction_refs.py#L306-L326)
    * *Contract*: Classify every token of ``text``; counts are per occurrence.
  * [`grade(path: str, text: str, tracked: list[str]) -> list[Finding]`](framework/gates/instructions/check_instruction_refs.py#L329-L339)
    * *Contract*: Return HNS073 findings for ``text`` against one flat tracked list.
  * [`main(argv: Sequence[str] | None) -> int`](framework/gates/instructions/check_instruction_refs.py#L466-L495)
    * *Contract*: Grade the named instruction artifacts; 0 clean, 1 findings, 2 error.

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

- [`framework/gates/mutation/check_mutation.py`](framework/gates/mutation/check_mutation.py) (233 lines)
  * *Module Purpose*: Mutation gate CLI: refresh and verify cleared mutmut evidence for staged files.
  * [`parse_args(argv: Sequence[str] | None) -> argparse.Namespace`](framework/gates/mutation/check_mutation.py#L40-L48)
    * *Contract*: Command line for the mutation gate.
  * [`main(argv: Sequence[str] | None) -> int`](framework/gates/mutation/check_mutation.py#L215-L229)
    * *Contract*: Decide from the ledger, or refresh it, for the staged population.

- [`framework/gates/mutation/evidence.py`](framework/gates/mutation/evidence.py) (465 lines)
  * *Module Purpose*: Mutation evidence: content-addressed mutmut verdicts for staged modules.
  * [`staged_bytes(rel: str) -> bytes | None`](framework/gates/mutation/evidence.py#L93-L98)
    * *Contract*: The exact bytes the index would commit for ``rel`` (None when unstaged).
  * [`staged_sha256(rel: str) -> str | None`](framework/gates/mutation/evidence.py#L101-L104)
    * *Contract*: sha256 of the staged blob, the address ``rel``'s evidence is keyed by.
  * [`head_bytes(rel: str) -> bytes | None`](framework/gates/mutation/evidence.py#L107-L111)
    * *Contract*: The bytes HEAD carries for ``rel`` (None when HEAD has no such blob).
  * [`pragma_lines(text: str) -> dict[str, int]`](framework/gates/mutation/evidence.py#L114-L130)
    * *Contract*: Map the code text of each ``# pragma: no mutate`` comment to its line.
  * [`pragma_notes(paths: Sequence[str]) -> list[str]`](framework/gates/mutation/evidence.py#L133-L156)
    * *Contract*: NOTE the ``# pragma: no mutate`` lines a staged blob adds over HEAD.
  * [`tests_drift_reason() -> str | None`](framework/gates/mutation/evidence.py#L159-L183)
    * *Contract*: Why the test surface is not committed as staged, or None when it is.
  * [`load_ledger(path: Path | None) -> dict[str, Any]`](framework/gates/mutation/evidence.py#L186-L195)
    * *Contract*: Read the evidence ledger; a missing or malformed file reads as empty.
  * [`save_ledger(data: Mapping[str, Any], path: Path | None) -> None`](framework/gates/mutation/evidence.py#L198-L203)
    * *Contract*: Write the ledger deterministically, so its diff stays reviewable.
  * [`config_population() -> tuple[dict[str, list[str]] | None, str | None]`](framework/gates/mutation/evidence.py#L235-L250)
    * *Contract*: The mutated-file population from ``[tool.mutmut]``, or why it is unreadable.
  * [`test_selection() -> list[str] | None`](framework/gates/mutation/evidence.py#L253-L260)
    * *Contract*: The configured ``pytest_add_cli_args_test_selection`` list, or None.
  * [`tests_sha256() -> str`](framework/gates/mutation/evidence.py#L283-L297)
    * *Contract*: Digest of the test surface plus the configuration that bounds the run.
  * [`match_population(rel: str, population: Mapping[str, list[str]]) -> bool`](framework/gates/mutation/evidence.py#L321-L329)
    * *Contract*: True when ``rel`` is mutated: it matches only_mutate, not do_not_mutate.
  * [`entry_findings(rel: str, entry: Any, sha: str, tests_sha: str) -> list[str]`](framework/gates/mutation/evidence.py#L380-L397)
    * *Contract*: Every reason ``rel``'s recorded evidence does not clear content ``sha``.
  * [`staged_findings(paths: Sequence[str], ledger_path: Path | None) -> list[str]`](framework/gates/mutation/evidence.py#L423-L434)
    * *Contract*: Every reason the staged files lack cleared evidence for their content.
  * [`scoped_paths(paths: Sequence[str]) -> tuple[list[str], str | None]`](framework/gates/mutation/evidence.py#L459-L465)
    * *Contract*: The staged paths the gate owns, or the reason the population is unreadable.

- [`framework/gates/mutation/scoring.py`](framework/gates/mutation/scoring.py) (209 lines)
  * *Module Purpose*: mutmut driver for the mutation gate: score the population, read the verdicts.
  * [`class RefreshBusy(RuntimeError)`](framework/gates/mutation/scoring.py#L75-L76)
    * *Contract*: Another process holds the refresh lock and is already scoring.
  * [`cache_stamp() -> Path`](framework/gates/mutation/scoring.py#L51-L54)
    * *Contract*: Where the test-surface digest of the cached verdicts is recorded.
  * [`cached_tests_sha256() -> str | None`](framework/gates/mutation/scoring.py#L57-L63)
    * *Contract*: The test-surface digest the cached mutmut verdicts were scored against.
  * [`refresh_lock() -> Iterator[None]`](framework/gates/mutation/scoring.py#L98-L118)
    * *Contract*: Serialize scorers: one mutmut run per repository, a peer's is refused.
  * [`prepare_cache(tests_sha256: str) -> str | None`](framework/gates/mutation/scoring.py#L121-L131)
    * *Contract*: Drop mutmut's verdict cache when it predates ``tests_sha256``.
  * [`status_table() -> tuple[dict[int | None, str] | None, str | None, str | None]`](framework/gates/mutation/scoring.py#L134-L140)
    * *Contract*: mutmut's status map, its unknown-code fallback status, or why it is absent.
  * [`mutmut_version(python: str | None) -> tuple[str | None, str | None]`](framework/gates/mutation/scoring.py#L143-L155)
    * *Contract*: The installed mutmut version reported by ``-m mutmut --version``.
  * [`run_mutmut(jobs: int, python: str | None) -> int`](framework/gates/mutation/scoring.py#L158-L170)
    * *Contract*: Score every uncached or invalidated mutant; mutmut's output streams through.
  * [`meta_path(rel: str) -> Path`](framework/gates/mutation/scoring.py#L173-L175)
    * *Contract*: Where mutmut stores one module's verdicts.
  * [`collect_statuses(rel: str) -> tuple[dict[str, str], str | None]`](framework/gates/mutation/scoring.py#L178-L191)
    * *Contract*: Map every recorded mutant of ``rel`` to a status, or say why it cannot.
  * [`aggregate(statuses: Mapping[str, str]) -> dict[str, int]`](framework/gates/mutation/scoring.py#L194-L201)
    * *Contract*: Count statuses, emitting every blocking key so a silent slip is impossible.
  * [`names_by_status(statuses: Mapping[str, str]) -> dict[str, list[str]]`](framework/gates/mutation/scoring.py#L204-L209)
    * *Contract*: The mutant names behind each status, so findings can print the offender.

- [`framework/gates/mutation/test_evidence_stamp.py`](framework/gates/mutation/test_evidence_stamp.py) (176 lines)
  * *Module Purpose*: Behavioral tests for the v2 evidence stamp, cache invalidation and lock.
  * [`repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path`](framework/gates/mutation/test_evidence_stamp.py#L51-L72)
    * *Contract*: A committed scratch repository with one staged module and no tests yet.
  * [`test_stale_test_surface_stamp_blocks(repo: Path) -> None`](framework/gates/mutation/test_evidence_stamp.py#L105-L114)
    * *Contract*: An entry scored against other test bytes is refused, not believed.
  * [`test_tests_sha256_moves_with_the_test_tree(repo: Path) -> None`](framework/gates/mutation/test_evidence_stamp.py#L117-L133)
    * *Contract*: A new test byte and a moved run-bounding section both change the digest.
  * [`test_prepare_cache_drops_only_when_the_digest_moves(repo: Path) -> None`](framework/gates/mutation/test_evidence_stamp.py#L136-L146)
    * *Contract*: The cached verdicts survive an identical stamp and are dropped on a move.
  * [`test_refresh_lock_refuses_a_second_holder(repo: Path) -> None`](framework/gates/mutation/test_evidence_stamp.py#L149-L159)
    * *Contract*: Two scorers never share ``mutants/``: the peer is refused, not queued.
  * [`test_pragma_notes_report_only_new_suppressions(repo: Path) -> None`](framework/gates/mutation/test_evidence_stamp.py#L162-L176)
    * *Contract*: A suppression HEAD already carried is silent; a new one is NOTEd.

- [`framework/gates/mutation/test_mutation.py`](framework/gates/mutation/test_mutation.py) (246 lines)
  * *Module Purpose*: Behavioral tests for the mutation-evidence gate (no mutmut run is forked here).
  * [`repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path`](framework/gates/mutation/test_mutation.py#L28-L56)
    * *Contract*: A throwaway repository whose staged blob and ledger the gate reads.
  * [`test_absent_evidence_blocks_with_the_refresh_command(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L103-L106)
  * [`test_cleared_evidence_for_the_staged_content_passes(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L109-L111)
  * [`test_staging_new_content_invalidates_the_recorded_evidence(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L114-L118)
  * [`test_unstaged_edits_do_not_change_the_decision(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L121-L124)
  * [`test_a_survivor_blocks_and_is_named(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L127-L137)
  * [`test_unreached_mutants_block_as_a_coverage_hole(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L140-L143)
  * [`test_a_timeout_blocks_as_an_unscored_mutant(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L146-L148)
  * [`test_files_outside_the_population_are_not_the_gates_business(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L151-L153)
  * [`test_population_drift_blocks_until_the_ledger_is_refreshed(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L156-L165)
  * [`test_population_drift_blocks_without_a_staged_population_file(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L168-L177)
  * [`test_emptying_the_population_blocks_against_recorded_evidence(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L180-L186)
  * [`test_config_only_staging_passes_when_the_ledger_matches(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L189-L191)
  * [`test_glob_matching_respects_segments_and_double_star(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L194-L199)
  * [`test_no_environment_variable_downgrades_the_gate(repo: Path, monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None`](framework/gates/mutation/test_mutation.py#L207-L213)
  * [`test_cli_evidence_only_exits_nonzero_on_findings(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L216-L220)
  * [`test_refresh_refuses_a_worktree_that_differs_from_the_index(repo: Path) -> None`](framework/gates/mutation/test_mutation.py#L223-L225)
  * [`test_aggregate_maps_mutmut_statuses_and_unknown_codes_block() -> None`](framework/gates/mutation/test_mutation.py#L228-L246)

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

## Package `framework/gates/typecheck` — *Static-type gate: staged mypy enforcement with an advisory pyright census.*

- [`framework/gates/typecheck/check_types.py`](framework/gates/typecheck/check_types.py) (123 lines)
  * *Module Purpose*: CLI entry point of the static-type gate (mypy blocking, pyright census).
  * [`build_parser() -> argparse.ArgumentParser`](framework/gates/typecheck/check_types.py#L36-L49)
    * *Contract*: Return the CLI parser of the type gate.
  * [`selection(args: argparse.Namespace) -> tuple[list[str], list[str]]`](framework/gates/typecheck/check_types.py#L52-L59)
    * *Contract*: Return the modules to check and a decline note per named out-of-scope path.
  * [`invoke(args: argparse.Namespace, modules: list[str]) -> runner.RunResult | None`](framework/gates/typecheck/check_types.py#L62-L69)
    * *Contract*: Run the engine; on a missing checker print the hint and return ``None``.
  * [`emit(args: argparse.Namespace, result: runner.RunResult, checked: int) -> int`](framework/gates/typecheck/check_types.py#L72-L94)
    * *Contract*: Print one run's findings and census, then return its exit code.
  * [`main(argv: list[str] | None) -> int`](framework/gates/typecheck/check_types.py#L97-L119)
    * *Contract*: Execute the type gate and return its exit code.

- [`framework/gates/typecheck/policy.py`](framework/gates/typecheck/policy.py) (223 lines)
  * *Module Purpose*: Typed population, engine and interpreter resolution of the static-type gate.
  * [`relative(path: str | Path) -> str`](framework/gates/typecheck/policy.py#L39-L47)
    * *Contract*: Return ``path`` as a repository-relative posix string when it is inside.
  * [`decline_reason(rel: str) -> str | None`](framework/gates/typecheck/policy.py#L50-L63)
    * *Contract*: Return why ``rel`` is outside the typed population, or ``None``.
  * [`is_typed_path(rel: str) -> bool`](framework/gates/typecheck/policy.py#L66-L68)
    * *Contract*: Return whether a repository-relative path is inside the typed population.
  * [`outside_repo(raw: str) -> bool`](framework/gates/typecheck/policy.py#L71-L80)
    * *Contract*: Return whether ``raw`` is an absolute path that lives outside the repo.
  * [`select_paths_detailed(paths: Iterable[str]) -> tuple[list[str], list[tuple[str, str]]]`](framework/gates/typecheck/policy.py#L83-L98)
    * *Contract*: Return the typed selection and every declined path with its reason.
  * [`select_paths(paths: Iterable[str]) -> list[str]`](framework/gates/typecheck/policy.py#L101-L103)
    * *Contract*: Return the unique typed paths of an explicit file list, sorted.
  * [`typed_sources() -> list[str]`](framework/gates/typecheck/policy.py#L106-L117)
    * *Contract*: Return every typed module of the working tree, repository-relative.
  * [`index_selection() -> list[str]`](framework/gates/typecheck/policy.py#L120-L131)
    * *Contract*: Return the typed modules staged in the Git index, repository-relative.
  * [`index_drift(paths: Iterable[str]) -> list[str]`](framework/gates/typecheck/policy.py#L134-L149)
    * *Contract*: Return the paths whose working-tree content differs from the Git index.
  * [`staged_blob(rel: str) -> str | None`](framework/gates/typecheck/policy.py#L152-L163)
    * *Contract*: Return the staged text of a repository-relative path, or ``None``.
  * [`write_shadow(rel: str, text: str) -> Path`](framework/gates/typecheck/policy.py#L166-L172)
    * *Contract*: Write one staged blob to the shadow tree and return its path.
  * [`shadow_pairs(modules: Iterable[str]) -> tuple[list[str], list[str]]`](framework/gates/typecheck/policy.py#L175-L193)
    * *Contract*: Return ``(mypy --shadow-file argv, drifted paths)`` for staged modules.
  * [`interpreter() -> Path`](framework/gates/typecheck/policy.py#L199-L204)
    * *Contract*: Return the project interpreter from harness.
  * [`engine_command(engine: str) -> list[str] | None`](framework/gates/typecheck/policy.py#L207-L217)
    * *Contract*: Return the resolved checker argv prefix, or ``None`` when it is absent.
  * [`ensure_cache_dir() -> Path`](framework/gates/typecheck/policy.py#L220-L223)
    * *Contract*: Return the mypy cache directory, created under the ignored ``cache`` tree.

- [`framework/gates/typecheck/report.py`](framework/gates/typecheck/report.py) (72 lines)
  * *Module Purpose*: Rendering, machine reports and census aggregation of the static-type gate.
  * [`print_findings(findings: Sequence[Finding], stream: TextIO, limit: int) -> None`](framework/gates/typecheck/report.py#L31-L41)
    * *Contract*: Print findings (capped) and disclose how many were left out.
  * [`write_report(path: Path, findings: Sequence[Finding]) -> None`](framework/gates/typecheck/report.py#L44-L55)
    * *Contract*: Write the machine-readable JSON report of one run.
  * [`per_tree(findings: Sequence[Finding]) -> list[tuple[str, int]]`](framework/gates/typecheck/report.py#L58-L61)
    * *Contract*: Return ``(tree, count)`` rows for the typed roots, heaviest first.
  * [`census_lines(findings: Sequence[Finding], checked: int) -> list[str]`](framework/gates/typecheck/report.py#L64-L72)
    * *Contract*: Return the census summary: totals, per-tree rows and the worst files.

- [`framework/gates/typecheck/runner.py`](framework/gates/typecheck/runner.py) (195 lines)
  * *Module Purpose*: Checker invocation and diagnostic parsing of the static-type gate.
  * [`class CheckerMissing(RuntimeError)`](framework/gates/typecheck/runner.py#L36-L42)
    * *Contract*: Raised when the configured checker executable cannot be resolved.
    * [`CheckerMissing.__init__(self, engine: str, hint: str) -> None`](framework/gates/typecheck/runner.py#L39-L42)
  * [`class Finding`](framework/gates/typecheck/runner.py#L46-L56)
    * *Contract*: One checker diagnostic with its file, line, error code and message.
    * [`Finding.format(self) -> str`](framework/gates/typecheck/runner.py#L54-L56)
      * *Contract*: Return the finding as one ``path:line: code message`` line.
  * [`class RunResult`](framework/gates/typecheck/runner.py#L60-L67)
    * *Contract*: Outcome of one checker invocation.
  * [`mypy_argv(paths: Sequence[str], staged: bool) -> list[str]`](framework/gates/typecheck/runner.py#L99-L121)
    * *Contract*: Return the mypy command line for ``paths`` under the committed config.
  * [`run_mypy(paths: Sequence[str], scoped: set[str], staged: bool) -> RunResult`](framework/gates/typecheck/runner.py#L124-L139)
    * *Contract*: Run mypy on ``paths`` and return the findings they own.
  * [`run_pyright(paths: Sequence[str]) -> RunResult`](framework/gates/typecheck/runner.py#L167-L182)
    * *Contract*: Run the pyright census engine on ``paths`` and return its findings.
  * [`run(engine: str, paths: Sequence[str], scoped: set[str] | None, staged: bool) -> RunResult`](framework/gates/typecheck/runner.py#L185-L195)
    * *Contract*: Dispatch one run to ``engine`` with the caller's scope filter.

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

- [`framework/tests/test_test_mirror_gate.py`](framework/tests/test_test_mirror_gate.py) (385 lines)
  * *Module Purpose*: Tests for the src -> test mirror gate.
  * [`test_mirror_paths_accepts_both_spellings() -> None`](framework/tests/test_test_mirror_gate.py#L36-L40)
  * [`test_evaluate_accepts_both_spellings_and_exempts_packages() -> None`](framework/tests/test_test_mirror_gate.py#L43-L61)
  * [`test_alias_satisfies_a_missing_mirror() -> None`](framework/tests/test_test_mirror_gate.py#L64-L71)
  * [`test_dangling_alias_is_a_finding() -> None`](framework/tests/test_test_mirror_gate.py#L74-L82)
  * [`test_stale_alias_beside_a_real_mirror_is_a_finding() -> None`](framework/tests/test_test_mirror_gate.py#L85-L92)
  * [`test_collect_files_skips_caches_and_third_party(tmp_path, monkeypatch) -> None`](framework/tests/test_test_mirror_gate.py#L95-L103)
  * [`test_collect_files_staged_filter_ignores_other_roots(tmp_path, monkeypatch) -> None`](framework/tests/test_test_mirror_gate.py#L106-L110)
  * [`test_load_aliases_reads_targets(tmp_path) -> None`](framework/tests/test_test_mirror_gate.py#L113-L118)
  * [`test_load_aliases_rejects_a_non_object(tmp_path) -> None`](framework/tests/test_test_mirror_gate.py#L121-L125)
  * [`test_cli_blocks_a_missing_mirror(tmp_path, monkeypatch, capsys) -> None`](framework/tests/test_test_mirror_gate.py#L128-L135)
  * [`test_cli_passes_with_a_real_mirror(tmp_path, monkeypatch, capsys) -> None`](framework/tests/test_test_mirror_gate.py#L138-L143)
  * [`test_cli_missing_alias_table_is_an_environment_error(tmp_path, monkeypatch, capsys) -> None`](framework/tests/test_test_mirror_gate.py#L146-L151)
  * [`test_cli_staged_ignores_non_source_paths(tmp_path, monkeypatch, capsys) -> None`](framework/tests/test_test_mirror_gate.py#L154-L157)
  * [`test_cli_json_report_lists_findings(tmp_path, monkeypatch) -> None`](framework/tests/test_test_mirror_gate.py#L160-L167)
  * [`test_count_oracles_counts_tautologies() -> None`](framework/tests/test_test_mirror_gate.py#L175-L183)
  * [`test_count_oracles_counts_state_anchored_assertions() -> None`](framework/tests/test_test_mirror_gate.py#L186-L194)
  * [`test_count_oracles_treats_unparseable_as_empty() -> None`](framework/tests/test_test_mirror_gate.py#L197-L198)
  * [`test_count_oracles_counts_context_managers(source: str) -> None`](framework/tests/test_test_mirror_gate.py#L216-L217)
  * [`test_is_exempt_mirror_test() -> None`](framework/tests/test_test_mirror_gate.py#L220-L223)
  * [`test_evaluate_flags_an_assertion_free_mirror(tmp_path, monkeypatch) -> None`](framework/tests/test_test_mirror_gate.py#L226-L235)
  * [`test_evaluate_flags_a_tautological_mirror(tmp_path, monkeypatch) -> None`](framework/tests/test_test_mirror_gate.py#L238-L243)
  * [`test_evaluate_flags_state_anchored_mirrors(tmp_path, monkeypatch, assertion) -> None`](framework/tests/test_test_mirror_gate.py#L256-L265)
  * [`test_evaluate_accepts_genuine_value_comparisons(tmp_path, monkeypatch) -> None`](framework/tests/test_test_mirror_gate.py#L268-L276)
  * [`test_evaluate_accepts_a_behavioral_mirror(tmp_path, monkeypatch) -> None`](framework/tests/test_test_mirror_gate.py#L279-L283)
  * [`test_evaluate_exempts_fixture_mirrors(tmp_path, monkeypatch) -> None`](framework/tests/test_test_mirror_gate.py#L286-L290)
  * [`test_unreadable_mirror_is_not_graded(tmp_path, monkeypatch) -> None`](framework/tests/test_test_mirror_gate.py#L293-L302)
    * *Contract*: A mirror that is not valid UTF-8 is treated as unreadable, not crashed on.
  * [`test_cli_blocks_an_assertion_free_mirror(tmp_path, monkeypatch, capsys) -> None`](framework/tests/test_test_mirror_gate.py#L305-L310)
  * [`test_grade_oracle_file_flags_zero_oracle_tests() -> None`](framework/tests/test_test_mirror_gate.py#L328-L332)
    * *Contract*: An assertion-free test function is HNS068.
  * [`test_grade_oracle_file_accepts_a_real_assertion() -> None`](framework/tests/test_test_mirror_gate.py#L335-L338)
    * *Contract*: An assertion against an independent expectation passes.
  * [`test_grade_oracle_file_flags_tautologies() -> None`](framework/tests/test_test_mirror_gate.py#L341-L345)
    * *Contract*: An all-tautological body is HNS070 (state-anchored).
  * [`test_grade_oracle_file_skips_support_modules() -> None`](framework/tests/test_test_mirror_gate.py#L348-L351)
    * *Contract*: A module without a test_* function is support code, not a test.
  * [`test_grade_oracle_file_skips_exempt_names() -> None`](framework/tests/test_test_mirror_gate.py#L354-L360)
    * *Contract*: conftest and *_fixtures modules are fixtures, not oracle targets.
  * [`test_grade_oracle_file_treats_unparseable_source_as_no_test() -> None`](framework/tests/test_test_mirror_gate.py#L363-L365)
    * *Contract*: A file that does not parse defines no test function.
  * [`test_oracle_cli_reads_the_staged_blob(tmp_path, monkeypatch, capsys) -> None`](framework/tests/test_test_mirror_gate.py#L368-L385)
    * *Contract*: --staged decides from the Git index, not the working tree.

## Package `framework/tests/antipattern` — *Anti-pattern extension tests (HNS066/067/069/072/081/082).*

- [`framework/tests/antipattern/test_execution.py`](framework/tests/antipattern/test_execution.py) (110 lines)
  * *Module Purpose*: Paired acceptance tests for the HNS081/HNS082 execution-sink rules.
  * [`test_fstring_interpolation_into_shell_fires() -> None`](framework/tests/antipattern/test_execution.py#L32-L35)
    * *Contract*: An unquoted f-string command handed to ``shell=True`` is injection.
  * [`test_concatenated_command_into_os_system_fires() -> None`](framework/tests/antipattern/test_execution.py#L38-L41)
    * *Contract*: A ``+``-concatenated variable command into ``os.system`` is injection.
  * [`test_mod_formatted_command_fires() -> None`](framework/tests/antipattern/test_execution.py#L44-L47)
    * *Contract*: A ``%``-formatted command into ``os.system`` is injection.
  * [`test_shlex_quoted_fstring_is_clean() -> None`](framework/tests/antipattern/test_execution.py#L50-L56)
    * *Contract*: Quoting the formatted value removes the injection surface.
  * [`test_argv_list_is_clean() -> None`](framework/tests/antipattern/test_execution.py#L59-L62)
    * *Contract*: An argv list never reaches a shell.
  * [`test_constant_command_is_clean() -> None`](framework/tests/antipattern/test_execution.py#L65-L68)
    * *Contract*: A constant command string carries no interpolated data.
  * [`test_broad_except_pass_fires() -> None`](framework/tests/antipattern/test_execution.py#L71-L77)
    * *Contract*: A broad handler whose only body is ``pass`` swallows the failure.
  * [`test_bare_except_return_none_fires() -> None`](framework/tests/antipattern/test_execution.py#L80-L83)
    * *Contract*: A bare handler returning ``None`` masks the crash.
  * [`test_narrow_exception_is_clean() -> None`](framework/tests/antipattern/test_execution.py#L86-L92)
    * *Contract*: Catching the absence family is a deliberate choice, not a swallow.
  * [`test_logged_handler_is_clean() -> None`](framework/tests/antipattern/test_execution.py#L95-L102)
    * *Contract*: A handler that records the failure and returns is never silent.
  * [`test_test_file_is_clean() -> None`](framework/tests/antipattern/test_execution.py#L105-L110)
    * *Contract*: The rule is scoped out of test modules.

- [`framework/tests/antipattern/test_fallthrough.py`](framework/tests/antipattern/test_fallthrough.py) (114 lines)
  * *Module Purpose*: Paired acceptance tests for the HNS067 and HNS069 fallthrough rules.
  * [`test_choices_index_zero_flagged() -> None`](framework/tests/antipattern/test_fallthrough.py#L31-L33)
  * [`test_content_index_zero_flagged() -> None`](framework/tests/antipattern/test_fallthrough.py#L36-L38)
  * [`test_dict_choices_index_zero_flagged() -> None`](framework/tests/antipattern/test_fallthrough.py#L41-L43)
  * [`test_generic_index_zero_clean() -> None`](framework/tests/antipattern/test_fallthrough.py#L46-L48)
  * [`test_iteration_over_choices_clean() -> None`](framework/tests/antipattern/test_fallthrough.py#L51-L55)
  * [`test_blocks_parts_index_zero_flagged() -> None`](framework/tests/antipattern/test_fallthrough.py#L58-L60)
  * [`test_dict_get_choices_index_zero_flagged() -> None`](framework/tests/antipattern/test_fallthrough.py#L63-L65)
  * [`test_self_path_parts_clean() -> None`](framework/tests/antipattern/test_fallthrough.py#L68-L70)
  * [`test_path_constructor_parts_clean() -> None`](framework/tests/antipattern/test_fallthrough.py#L73-L79)
  * [`test_getattr_choices_index_zero_flagged() -> None`](framework/tests/antipattern/test_fallthrough.py#L82-L84)
  * [`test_getattr_content_index_zero_flagged() -> None`](framework/tests/antipattern/test_fallthrough.py#L87-L89)
  * [`test_getattr_other_index_zero_clean() -> None`](framework/tests/antipattern/test_fallthrough.py#L92-L94)
  * [`test_hns069_flags_if_false() -> None`](framework/tests/antipattern/test_fallthrough.py#L97-L99)
  * [`test_hns069_flags_if_zero() -> None`](framework/tests/antipattern/test_fallthrough.py#L102-L104)
  * [`test_hns069_flags_while_false() -> None`](framework/tests/antipattern/test_fallthrough.py#L107-L109)
  * [`test_hns069_accepts_normal_branching() -> None`](framework/tests/antipattern/test_fallthrough.py#L112-L114)

- [`framework/tests/antipattern/test_liveness.py`](framework/tests/antipattern/test_liveness.py) (77 lines)
  * *Module Purpose*: Paired acceptance tests for the HNS072 unbounded-loop rule.
  * [`test_constant_true_loop_without_exit_fires() -> None`](framework/tests/antipattern/test_liveness.py#L26-L28)
    * *Contract*: A constant-true body with no exit is an unbounded loop.
  * [`test_integer_one_loop_without_exit_fires() -> None`](framework/tests/antipattern/test_liveness.py#L31-L33)
    * *Contract*: ``while 1`` is the same shape as ``while True``.
  * [`test_nested_loop_break_does_not_excuse() -> None`](framework/tests/antipattern/test_liveness.py#L36-L38)
    * *Contract*: A break inside a nested for leaves the outer candidate running.
  * [`test_nested_function_return_does_not_excuse() -> None`](framework/tests/antipattern/test_liveness.py#L41-L44)
    * *Contract*: A return inside a nested function runs in a different frame.
  * [`test_break_inside_try_is_clean() -> None`](framework/tests/antipattern/test_liveness.py#L47-L52)
    * *Contract*: A break inside the candidate's own try/except terminates it.
  * [`test_break_terminates() -> None`](framework/tests/antipattern/test_liveness.py#L55-L57)
    * *Contract*: A direct break is an exit.
  * [`test_return_terminates() -> None`](framework/tests/antipattern/test_liveness.py#L60-L62)
    * *Contract*: A return in the candidate's own frame is an exit.
  * [`test_raise_terminates() -> None`](framework/tests/antipattern/test_liveness.py#L65-L67)
    * *Contract*: A raise in the candidate body is an exit.
  * [`test_sys_exit_terminates() -> None`](framework/tests/antipattern/test_liveness.py#L70-L72)
    * *Contract*: An explicit sys.exit call is an exit.
  * [`test_condition_bound_loop_stays_silent() -> None`](framework/tests/antipattern/test_liveness.py#L75-L77)
    * *Contract*: A comparison test is never a candidate.

- [`framework/tests/antipattern/test_shell.py`](framework/tests/antipattern/test_shell.py) (106 lines)
  * *Module Purpose*: Paired acceptance tests for the HNS066 tooling-hygiene rule.
  * [`test_unversioned_npx_flagged() -> None`](framework/tests/antipattern/test_shell.py#L44-L45)
  * [`test_versioned_npx_clean() -> None`](framework/tests/antipattern/test_shell.py#L48-L49)
  * [`test_curl_pipe_shell_flagged() -> None`](framework/tests/antipattern/test_shell.py#L52-L53)
  * [`test_wget_pipe_shell_flagged() -> None`](framework/tests/antipattern/test_shell.py#L56-L57)
  * [`test_curl_pipe_python_flagged() -> None`](framework/tests/antipattern/test_shell.py#L60-L61)
  * [`test_wget_pipe_perl_flagged() -> None`](framework/tests/antipattern/test_shell.py#L64-L65)
  * [`test_curl_pipe_ruby_flagged() -> None`](framework/tests/antipattern/test_shell.py#L68-L69)
  * [`test_piped_python_literal_is_clean() -> None`](framework/tests/antipattern/test_shell.py#L72-L73)
  * [`test_echoed_prose_is_not_an_invocation() -> None`](framework/tests/antipattern/test_shell.py#L76-L77)
  * [`test_printfed_prose_is_not_an_invocation() -> None`](framework/tests/antipattern/test_shell.py#L80-L81)
  * [`test_commit_message_prose_is_not_an_invocation() -> None`](framework/tests/antipattern/test_shell.py#L84-L85)
  * [`test_shell_c_payload_is_an_invocation() -> None`](framework/tests/antipattern/test_shell.py#L88-L89)
  * [`test_unpinned_pip_install_flagged() -> None`](framework/tests/antipattern/test_shell.py#L92-L93)
  * [`test_pinned_pip_install_clean() -> None`](framework/tests/antipattern/test_shell.py#L96-L98)
  * [`test_quoted_pip_argument_still_scanned() -> None`](framework/tests/antipattern/test_shell.py#L101-L102)
  * [`test_clean_sbatch_template_clean() -> None`](framework/tests/antipattern/test_shell.py#L105-L106)

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
  * [`test_hns044_passes_on_full_precision_distance() -> None`](framework/tests/distortion/test_distortion_gate.py#L38-L45)
    * *Contract*: Pass on a float64 distance computed without a low-precision cast.
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

## Package `framework/tests/freshness` — *Tests for freshness and ref guard gates.*

- [`framework/tests/freshness/test_ref_guard.py`](framework/tests/freshness/test_ref_guard.py) (378 lines)
  * *Module Purpose*: Tests for the reference-transaction ref-provenance guard.
  * [`repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path`](framework/tests/freshness/test_ref_guard.py#L56-L65)
    * *Contract*: A throwaway repository with one commit, as the guard's working directory.
  * [`test_deletion_and_equal_updates_are_allowed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L99-L105)
    * *Contract*: A branch deletion (new is zero) and a no-op move are always allowed.
  * [`test_rewind_to_an_ancestor_is_allowed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L108-L114)
    * *Contract*: `reset --hard HEAD~1` moves a branch back onto its own history.
  * [`test_crafted_commit_into_a_new_branch_is_blocked(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L117-L122)
    * *Contract*: `commit-tree` + `update-ref refs/heads/x` never reaches a live tip.
  * [`test_force_branch_and_reset_to_crafted_are_blocked(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L125-L131)
    * *Contract*: `branch -f` and `reset --hard` onto a crafted commit are refused.
  * [`test_forward_move_to_a_reachable_tip_is_allowed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L134-L142)
    * *Contract*: A fast-forward onto another branch's tip is already in history.
  * [`test_a_nested_branch_tip_is_trusted(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L145-L154)
    * *Contract*: A tip under `fix/...` is a live tip; a fast-forward onto it lands.
  * [`test_a_crafted_object_stays_refused_among_nested_tips(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L157-L168)
    * *Contract*: Enumerating every ref keeps the reachability rule for a crafted object.
  * [`test_unresolvable_new_value_is_blocked(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L171-L177)
    * *Contract*: A branch pointed at a non-commit object is refused.
  * [`test_non_gated_refs_pass(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L188-L192)
    * *Contract*: HEAD, stash and notes carry no provenance guarantee and are untouched.
  * [`test_marker_allows_and_is_consumed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L195-L202)
    * *Contract*: An armed marker matching pid, tree and starttime lets a gated commit land.
  * [`test_marker_rejected_after_pid_reuse(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L205-L211)
    * *Contract*: A stale starttime (the pid was reused) never vouches for a move.
  * [`test_marker_rejected_when_stale(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L214-L221)
    * *Contract*: A marker older than the freshness window is pruned and ignored.
  * [`test_marker_rejected_for_a_different_tree(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L224-L230)
    * *Contract*: A marker armed for another tree does not vouch for this commit.
  * [`test_remote_tracking_ref_by_fetch_is_allowed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L233-L239)
    * *Contract*: A remote-tracking ref may move to an unreachable value under `git fetch`.
  * [`test_remote_tracking_ref_by_update_ref_is_blocked(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L242-L248)
    * *Contract*: A remote-tracking ref moved outside fetch/pull/push is refused.
  * [`test_tag_rules(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L251-L256)
    * *Contract*: A crafted tag is refused; a tag at a live branch tip is not.
  * [`test_replace_ref_is_blocked(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L259-L263)
    * *Contract*: A replace ref may only be deleted or reset to itself.
  * [`test_grafts_file_fails_closed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L266-L272)
    * *Contract*: An info/grafts file blocks even an ordinary rewind.
  * [`test_non_prepared_states_exit_zero_before_reading(monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L275-L281)
    * *Contract*: committed/aborted never read stdin and never block.
  * [`test_malformed_line_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/freshness/test_ref_guard.py#L284-L286)
    * *Contract*: A malformed transaction record aborts the transaction.
  * [`test_scratch_e2e_gated_commit_lands_and_no_verify_fails(tmp_path: Path) -> None`](framework/tests/freshness/test_ref_guard.py#L346-L352)
    * *Contract*: The shipped guard arms a gated commit and refuses `--no-verify`.
  * [`test_scratch_e2e_plumbing_moves_are_blocked(tmp_path: Path) -> None`](framework/tests/freshness/test_ref_guard.py#L355-L366)
    * *Contract*: `commit-tree`+`update-ref`, `branch -f` and `reset --hard` are refused.
  * [`test_scratch_e2e_rewind_is_allowed(tmp_path: Path) -> None`](framework/tests/freshness/test_ref_guard.py#L369-L378)
    * *Contract*: A rewind onto an ancestor is not a bypass and lands.

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
    * *Contract*: ``matrix = None -> eye`` selects everything; nothing was emptied.
  * [`test_a_zeroed_substitute_is_still_reported() -> None`](framework/tests/gates/test_antipattern_expansion.py#L321-L332)
    * *Contract*: ``zeros`` voids a direction, which is the family the rule targets.
  * [`test_a_mode_default_outside_its_dispatch_is_reported() -> None`](framework/tests/gates/test_antipattern_expansion.py#L335-L345)
    * *Contract*: A default mode string that no branch of its own dispatch matches is reported.
  * [`test_a_default_inside_its_own_dispatch_is_silent() -> None`](framework/tests/gates/test_antipattern_expansion.py#L348-L358)
    * *Contract*: Enumerating the default is the documented repair and must stay silent.
  * [`test_a_single_special_case_is_not_a_dispatch_table() -> None`](framework/tests/gates/test_antipattern_expansion.py#L361-L369)
    * *Contract*: One ``==`` beside a general branch is not an enumeration of the modes.
  * [`test_a_literal_beside_an_enumeration_counts_as_handled() -> None`](framework/tests/gates/test_antipattern_expansion.py#L372-L386)
    * *Contract*: ``mode == "sdp"`` in its own helper claims the default.
  * [`test_a_mode_forwarded_without_a_local_dispatch_is_out_of_scope() -> None`](framework/tests/gates/test_antipattern_expansion.py#L389-L395)
    * *Contract*: A module that only relays the setting cannot discharge the branch itself.
  * [`test_a_non_mode_string_default_is_not_a_dispatch_key() -> None`](framework/tests/gates/test_antipattern_expansion.py#L398-L406)
    * *Contract*: A path or message default is not a mode, even beside a mode table.

- [`framework/tests/gates/test_check_contamination.py`](framework/tests/gates/test_check_contamination.py) (186 lines)
  * *Module Purpose*: Behavioral tests for framework/gates/checks/check_contamination.py (guardrail #2).
  * [`run_gate(bank: dict, strict: bool, markers: str) -> subprocess.CompletedProcess`](framework/tests/gates/test_check_contamination.py#L16-L34)
  * [`clean_bank() -> dict`](framework/tests/gates/test_check_contamination.py#L37-L41)
  * [`test_clean_bank_passes() -> None`](framework/tests/gates/test_check_contamination.py#L44-L47)
  * [`test_exact_overlap_detected() -> None`](framework/tests/gates/test_check_contamination.py#L50-L55)
  * [`test_lookalike_detected() -> None`](framework/tests/gates/test_check_contamination.py#L58-L64)
  * [`test_single_token_share_not_lookalike() -> None`](framework/tests/gates/test_check_contamination.py#L67-L73)
    * *Contract*: Regression for the min-normalization bug: one shared token must not flag.
  * [`test_marker_in_safe_bank_detected() -> None`](framework/tests/gates/test_check_contamination.py#L76-L81)
  * [`test_marker_without_the_flag_is_not_contamination() -> None`](framework/tests/gates/test_check_contamination.py#L84-L90)
    * *Contract*: The marker vocabulary is the caller's: none supplied means none applied.
  * [`test_low_n_flagged() -> None`](framework/tests/gates/test_check_contamination.py#L93-L100)
  * [`test_missing_bank_errors() -> None`](framework/tests/gates/test_check_contamination.py#L103-L113)
  * [`pair_bank() -> dict`](framework/tests/gates/test_check_contamination.py#L116-L126)
    * *Contract*: A certified concept/guide pair bank: pairs plus the criterion it was selected under.
  * [`test_pair_bank_certified_passes() -> None`](framework/tests/gates/test_check_contamination.py#L129-L137)
    * *Contract*: C1-C4 read concept/safe lists a pair bank does not have.
  * [`test_pair_bank_with_an_honest_false_flag_passes() -> None`](framework/tests/gates/test_check_contamination.py#L140-L153)
    * *Contract*: An honest diagnostic reading, not a claim, is not refused.
  * [`test_pair_bank_over_its_threshold_flagged() -> None`](framework/tests/gates/test_check_contamination.py#L156-L162)
  * [`test_pair_bank_claiming_certification_without_its_numbers_flagged() -> None`](framework/tests/gates/test_check_contamination.py#L165-L172)
  * [`test_bank_with_both_layouts_is_graded_by_concept_checks() -> None`](framework/tests/gates/test_check_contamination.py#L175-L186)
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

## Package `framework/tests/gates/instructions` — *Tests for instruction reference validation.*

- [`framework/tests/gates/instructions/test_instruction_refs.py`](framework/tests/gates/instructions/test_instruction_refs.py) (275 lines)
  * *Module Purpose*: Tests for the instruction-reference gate (HNS073).
  * [`test_an_exact_tracked_path_resolves() -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L30-L33)
  * [`test_a_path_with_anchor_resolves() -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L36-L39)
  * [`test_a_path_boundary_suffix_resolves() -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L42-L44)
  * [`test_a_non_boundary_suffix_does_not_resolve() -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L47-L50)
  * [`test_non_path_shapes_stay_silent() -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L53-L62)
  * [`test_a_fenced_command_path_resolves() -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L77-L81)
    * *Contract*: A bare script path on a fenced command line is a graded token.
  * [`test_a_fenced_command_path_reports_its_line() -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L84-L88)
    * *Contract*: A missing fenced command path is a finding on the command's line.
  * [`test_paths_outside_fenced_commands_stay_silent() -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L91-L97)
    * *Contract*: A bare path is graded only when a fence holds a command line.
  * [`test_a_fenced_command_placeholder_is_preserved() -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L100-L104)
    * *Contract*: Angle brackets in a command path survive and classify as placeholder.
  * [`test_a_stale_token_reports_its_line() -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L107-L111)
  * [`test_a_token_repeated_names_its_first_line_only() -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L114-L117)
  * [`test_cli_staged_reads_the_index(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L120-L135)
  * [`test_cli_unreadable_file_is_an_environment_error(tmp_path, monkeypatch) -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L138-L144)
  * [`test_cli_passes_on_the_real_instruction_file() -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L147-L149)
    * *Contract*: The canonical AGENTS.md resolves every path it names.
  * [`test_roots_count_a_sibling_tree(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L152-L166)
    * *Contract*: A token only a sibling tree provides is counted, never failed.
  * [`test_moved_bucket_names_the_target(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L169-L182)
    * *Contract*: A basename that lives at another path fails and names the target.
  * [`test_placeholder_fails_unless_allowed(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L185-L196)
    * *Contract*: Example-shaped paths fail by default and are counted under the flag.
  * [`test_corpus_root_enumerates_rules_and_skills(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L199-L219)
    * *Contract*: --corpus-root grades that tree's rules, skills and AGENTS.md.
  * [`test_bare_filename_is_counted_under_roots(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L222-L236)
    * *Contract*: A bare filename is ambiguous across roots: counted, never failed.
  * [`test_output_path_is_counted_not_failed(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L239-L253)
    * *Contract*: A path under a directory no root tracks (a produced artifact) passes.
  * [`test_files_outside_corpus_stay_silent(tmp_path: Path, monkeypatch, capsys) -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L256-L265)
    * *Contract*: A file outside the declared corpus is skipped without findings.
  * [`test_missing_manifest_is_environment_error(tmp_path: Path, monkeypatch) -> None`](framework/tests/gates/instructions/test_instruction_refs.py#L268-L275)
    * *Contract*: --manifest with a nonexistent file exits 2 with an error message.

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

## Package `framework/tests/gates/ratchet` — *Ratchet gates: tables that may only shrink.*

- [`framework/tests/gates/ratchet/test_ratchet_gates.py`](framework/tests/gates/ratchet/test_ratchet_gates.py) (201 lines)
  * *Module Purpose*: Tests for the ratchet gates that block waiver, alias and baseline additions.
  * [`test_waiver_addition_is_blocked(tmp_path: Path) -> None`](framework/tests/gates/ratchet/test_ratchet_gates.py#L57-L66)
    * *Contract*: A new ``(file, ordinal)`` waiver absent from HEAD yields COV005.
  * [`test_unchanged_waivers_are_allowed(tmp_path: Path) -> None`](framework/tests/gates/ratchet/test_ratchet_gates.py#L69-L77)
    * *Contract*: A candidate table identical to HEAD produces no finding.
  * [`test_removed_waivers_are_allowed(tmp_path: Path) -> None`](framework/tests/gates/ratchet/test_ratchet_gates.py#L80-L93)
    * *Contract*: Shrinking the waiver table (partially or wholly) is always permitted.
  * [`test_alias_addition_is_blocked(tmp_path: Path) -> None`](framework/tests/gates/ratchet/test_ratchet_gates.py#L96-L108)
    * *Contract*: A new module key absent from HEAD yields MIR003.
  * [`test_unchanged_aliases_are_allowed(tmp_path: Path) -> None`](framework/tests/gates/ratchet/test_ratchet_gates.py#L111-L119)
    * *Contract*: An alias table identical to HEAD produces no finding.
  * [`test_removed_aliases_are_allowed(tmp_path: Path) -> None`](framework/tests/gates/ratchet/test_ratchet_gates.py#L122-L140)
    * *Contract*: Dropping an alias mapping (or all of them) is always permitted.
  * [`test_baseline_ratchet_blocks_expansion(tmp_path: Path) -> None`](framework/tests/gates/ratchet/test_ratchet_gates.py#L153-L164)
    * *Contract*: A current baseline with a fingerprint absent from HEAD is blocking.
  * [`test_baseline_ratchet_names_the_uncovered_clone(tmp_path: Path) -> None`](framework/tests/gates/ratchet/test_ratchet_gates.py#L167-L187)
    * *Contract*: An expansion finding names the clone locations it blocks.
  * [`test_baseline_ratchet_allows_shrink_or_identical(tmp_path: Path) -> None`](framework/tests/gates/ratchet/test_ratchet_gates.py#L190-L201)
    * *Contract*: Shrinking the baseline or keeping it identical is allowed.

## Package `framework/tests/harness` — *Harness registry tests: project identity and the interpreter floor.*

- [`framework/tests/harness/test_harness.py`](framework/tests/harness/test_harness.py) (128 lines)
  * *Module Purpose*: Tests for the harness registry: project identity and the interpreter floor.
  * [`test_python_refuses_an_interpreter_below_the_floor(tmp_path, monkeypatch) -> None`](framework/tests/harness/test_harness.py#L30-L39)
  * [`test_python_accepts_an_interpreter_at_the_floor(tmp_path, monkeypatch) -> None`](framework/tests/harness/test_harness.py#L42-L46)
  * [`test_floor_matches_the_packaging_floor() -> None`](framework/tests/harness/test_harness.py#L49-L52)
  * [`test_floor_is_exposed_as_a_key() -> None`](framework/tests/harness/test_harness.py#L55-L56)
  * [`test_dvc_bin_prefers_the_venv_binary(tmp_path, monkeypatch) -> None`](framework/tests/harness/test_harness.py#L59-L70)
  * [`test_engine_bin_prefers_env_then_venv_then_path(tmp_path, monkeypatch) -> None`](framework/tests/harness/test_harness.py#L73-L85)
  * [`test_static_scope_covers_the_static_roots() -> None`](framework/tests/harness/test_harness.py#L88-L92)
  * [`test_test_scope_covers_the_test_root() -> None`](framework/tests/harness/test_harness.py#L95-L100)
  * [`test_gate_state_and_cache_dirs_are_slug_scoped(monkeypatch) -> None`](framework/tests/harness/test_harness.py#L103-L106)
  * [`test_keys_key_lists_every_key() -> None`](framework/tests/harness/test_harness.py#L109-L114)
  * [`test_bare_invocation_prints_every_key(capsys) -> None`](framework/tests/harness/test_harness.py#L117-L122)
  * [`test_superseded_distortion_scope_key_is_unknown(capsys) -> None`](framework/tests/harness/test_harness.py#L125-L128)

## Package `framework/tests/hook_hygiene` — *Tests for the hook/test-process boundary.*

- [`framework/tests/hook_hygiene/git_env_fixture.py`](framework/tests/hook_hygiene/git_env_fixture.py) (37 lines)
  * *Module Purpose*: Shared environment sanitation for scratch-git test fixtures.
  * [`clean_env() -> dict[str, str]`](framework/tests/hook_hygiene/git_env_fixture.py#L19-L23)
    * *Contract*: Return the environment with every git repository selector removed.
  * [`run_git(repo: Path, *args, check: bool) -> subprocess.CompletedProcess[str]`](framework/tests/hook_hygiene/git_env_fixture.py#L26-L37)
    * *Contract*: Run one git command in `repo` with repository selectors removed.

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

## Package `framework/tests/typecheck` — *Tests for the static-type gate.*

- [`framework/tests/typecheck/test_check_types.py`](framework/tests/typecheck/test_check_types.py) (411 lines)
  * *Module Purpose*: Unit tests for the static-type gate: scope, parsing, CLI contract, index reads.
  * [`test_scope_covers_four_roots_and_excludes_tests() -> None`](framework/tests/typecheck/test_check_types.py#L59-L69)
    * *Contract*: Keep the typed population to the four roots and drop test/vendor paths.
  * [`test_select_paths_keeps_explicit_outside_file_and_normalizes(tmp_path: Path) -> None`](framework/tests/typecheck/test_check_types.py#L72-L81)
    * *Contract*: Normalize in-tree paths and honor an explicit file outside the roots.
  * [`test_mypy_argv_pins_config_interpreter_and_cache(monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/typecheck/test_check_types.py#L84-L94)
    * *Contract*: Pin the committed config, the resolved interpreter and the cache tree.
  * [`test_mypy_argv_fails_closed_without_a_checker(monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/typecheck/test_check_types.py#L97-L104)
    * *Contract*: Raise CheckerMissing (with an install hint) when no mypy resolves.
  * [`test_run_mypy_keeps_scoped_errors_and_drops_foreign_ones(monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/typecheck/test_check_types.py#L107-L117)
    * *Contract*: Attribute errors to the scope set, drop notes and foreign files.
  * [`test_run_mypy_surfaces_unparsable_error_lines(monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/typecheck/test_check_types.py#L120-L129)
    * *Contract*: Surface a location-less mypy error instead of reporting a clean run.
  * [`test_run_pyright_reads_json_ranges(monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/typecheck/test_check_types.py#L132-L161)
    * *Contract*: Parse pyright JSON and convert its zero-based range to a 1-based line.
  * [`test_cli_strict_blocks_on_a_scoped_finding(monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/typecheck/test_check_types.py#L164-L174)
    * *Contract*: Exit 1 under --strict when the staged module owns a finding.
  * [`test_cli_clean_run_exits_zero_and_writes_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None`](framework/tests/typecheck/test_check_types.py#L177-L191)
    * *Contract*: Exit 0 on a clean module and write the machine report on request.
  * [`test_cli_missing_checker_blocks_only_under_strict(monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/typecheck/test_check_types.py#L194-L206)
    * *Contract*: Fail closed under --strict when the checker is absent, NOTE otherwise.
  * [`test_index_selection_reads_staged_typed_modules(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None`](framework/tests/typecheck/test_check_types.py#L209-L226)
    * *Contract*: Select only staged typed modules from a real Git index.
  * [`test_typed_sources_walks_roots_and_honors_exclusions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None`](framework/tests/typecheck/test_check_types.py#L229-L248)
    * *Contract*: Walk the four roots and never yield test or vendor modules.
  * [`test_index_drift_flags_module_modified_after_staging(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None`](framework/tests/typecheck/test_check_types.py#L251-L266)
    * *Contract*: Report a staged module whose working tree moved on after staging.
  * [`test_mypy_argv_shadows_a_drifted_staged_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None`](framework/tests/typecheck/test_check_types.py#L269-L288)
    * *Contract*: Check the staged blob when the working tree moved on after staging.
  * [`test_cli_notes_shadowed_modules_without_blocking(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None`](framework/tests/typecheck/test_check_types.py#L291-L300)
    * *Contract*: Report a shadowed staged module as a NOTE, never as a failure.
  * [`test_run_mypy_executes_the_resolved_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None`](framework/tests/typecheck/test_check_types.py#L303-L320)
    * *Contract*: Execute a real checker process and parse its report end to end.
  * [`test_select_paths_drops_explicit_in_tree_test_module() -> None`](framework/tests/typecheck/test_check_types.py#L323-L326)
    * *Contract*: Never smuggle an in-tree excluded module into the typed population.
  * [`test_select_paths_detailed_reports_every_decline_reason() -> None`](framework/tests/typecheck/test_check_types.py#L329-L349)
    * *Contract*: A declined path carries the population rule's own reason.
  * [`test_cli_fails_closed_when_every_named_path_is_out_of_scope(capsys: pytest.CaptureFixture[str]) -> None`](framework/tests/typecheck/test_check_types.py#L352-L362)
    * *Contract*: Naming only out-of-population paths is an error, never a silent pass.
  * [`test_cli_unnamed_empty_index_is_a_benign_skip(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None`](framework/tests/typecheck/test_check_types.py#L365-L371)
    * *Contract*: Nothing staged and nothing named is a skip, not a failure.
  * [`test_pyright_engine_is_advisory_without_strict(monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/typecheck/test_check_types.py#L374-L382)
    * *Contract*: Pyright census never blocks unless --strict is given.
  * [`test_engine_command_returns_none_when_checker_absent(monkeypatch: pytest.MonkeyPatch) -> None`](framework/tests/typecheck/test_check_types.py#L385-L393)
    * *Contract*: Return None when the checker binary is absent from path and venv.
  * [`test_report_write_report_and_census_lines(tmp_path: Path) -> None`](framework/tests/typecheck/test_check_types.py#L396-L411)
    * *Contract*: Verify JSON report structure and census summary lines.

