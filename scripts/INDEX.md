# Research Sub-Index: `scripts`

> [!NOTE]
> Sub-index for the `scripts` package hierarchy. Use the line ranges below to load specific sections directly into context.

**Repository Statistics**: 15 modules | 18 classes | 102 public functions.

## Table of Contents

- [`scripts/setup`](#package-scriptssetup) (lines 16–90) — *Framework wiring, scaffolding, and hook installation tools.*
- [`scripts/slurm_queue`](#package-scriptsslurm-queue) (lines 91–281) — *Durable draining queue for Research sbatch jobs (model, store, submit, CLI, worker).*
- [`scripts/slurm_queue/worker`](#package-scriptsslurm-queueworker) (lines 282–372) — *Drain one Slurm lane allocation.*

---

## Package `scripts/setup` — *Framework wiring, scaffolding, and hook installation tools.*

- [`scripts/setup/bootstrap.py`](scripts/setup/bootstrap.py) (138 lines)
  * *Module Purpose*: One-command bootstrap: floor interpreter, venv, toolchain, hooks, example suite.
  * [`at_floor(interpreter: str) -> bool`](scripts/setup/bootstrap.py#L53-L59)
    * *Contract*: Return whether ``interpreter`` runs and meets the harness floor.
  * [`pick_interpreter(explicit: str | None) -> str`](scripts/setup/bootstrap.py#L62-L76)
    * *Contract*: Return the interpreter to build the venv with, or fail with the floor message.
  * [`build_steps(interpreter: str, skip_install: bool, skip_suite: bool) -> list[list[str]]`](scripts/setup/bootstrap.py#L79-L95)
    * *Contract*: Return the commands to run, in order, for the resolved interpreter.
  * [`run_step(step: list[str], dry_run: bool) -> None`](scripts/setup/bootstrap.py#L98-L111)
    * *Contract*: Print and run one step, stopping the bootstrap when it fails or overruns.
  * [`main(argv: list[str] | None) -> int`](scripts/setup/bootstrap.py#L114-L134)
    * *Contract*: Resolve the interpreter, run every step in order, report the next action.

- [`scripts/setup/check_framework_wiring.py`](scripts/setup/check_framework_wiring.py) (114 lines)
  * *Module Purpose*: Verify that the imported repository framework is wired into this worktree.
  * [`fail(message: str) -> None`](scripts/setup/check_framework_wiring.py#L29-L30)
  * [`check_entrypoints() -> bool`](scripts/setup/check_framework_wiring.py#L70-L89)
  * [`check_hooks() -> bool`](scripts/setup/check_framework_wiring.py#L92-L101)
  * [`main() -> int`](scripts/setup/check_framework_wiring.py#L104-L110)

- [`scripts/setup/create_test_scaffold.py`](scripts/setup/create_test_scaffold.py) (60 lines)
  * *Module Purpose*: Create a mirrored, tests_-prefixed scaffold for the project Python package.
  * [`main() -> None`](scripts/setup/create_test_scaffold.py#L34-L56)

- [`scripts/setup/init_project.py`](scripts/setup/init_project.py) (333 lines)
  * *Module Purpose*: Adopt the research template for a new project by rewriting its identity.
  * [`class AdoptionError(RuntimeError)`](scripts/setup/init_project.py#L62-L63)
    * *Contract*: Raised when this checkout cannot be adopted: dirty, occupied or unwritable.
  * [`parse_args(argv: list[str] | None) -> argparse.Namespace`](scripts/setup/init_project.py#L66-L78)
    * *Contract*: Parse the new identity (slug, env prefix, gate code) and the dry-run flag.
  * [`validate(slug: str, prefix: str, code: str) -> None`](scripts/setup/init_project.py#L81-L94)
    * *Contract*: Reject an identity the harness, the interpreter or the gate codes cannot carry.
  * [`run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]`](scripts/setup/init_project.py#L97-L107)
    * *Contract*: Run one bounded command, capturing its text output for the caller to judge.
  * [`tracked_paths(repo: Path) -> list[str]`](scripts/setup/init_project.py#L110-L116)
    * *Contract*: Return every Git-tracked path in POSIX form, refusing when git cannot list them.
  * [`readable_text(path: Path) -> str | None`](scripts/setup/init_project.py#L119-L124)
    * *Contract*: Return the file's text; ``None`` only for a known-binary or missing path.
  * [`scan_files(repo: Path) -> list[tuple[str, str]]`](scripts/setup/init_project.py#L127-L137)
    * *Contract*: Return ``(relative path, text)`` for every tracked text file outside the skip list.
  * [`build_rules(slug: str, prefix: str, code: str) -> tuple[Rule, ...]`](scripts/setup/init_project.py#L140-L155)
    * *Contract*: Return the ordered substitutions that move the current identity to the new one.
  * [`apply_rules(text: str, rules: tuple[Rule, ...]) -> tuple[str, int]`](scripts/setup/init_project.py#L158-L165)
    * *Contract*: Apply every rule in order; return the rewritten text and how often rules fired.
  * [`rewrite_tracked(repo: Path, rules: tuple[Rule, ...], dry_run: bool) -> list[tuple[str, int]]`](scripts/setup/init_project.py#L168-L181)
    * *Contract*: Rewrite the identity tokens in every tracked text file; return the per-file counts.
  * [`rewrite_identity(path: Path, slug: str, prefix: str, code: str, dry_run: bool) -> list[str]`](scripts/setup/init_project.py#L184-L201)
    * *Contract*: Rewrite the three harness identity literals; return the keys that changed.
  * [`rewrite_project_name(path: Path, slug: str, dry_run: bool) -> None`](scripts/setup/init_project.py#L204-L212)
    * *Contract*: Set ``[project] name`` in the pyproject to the new slug.
  * [`git_move(repo: Path, source: Path, target: Path, dry_run: bool) -> None`](scripts/setup/init_project.py#L215-L227)
    * *Contract*: ``git mv`` one tracked tree, refusing a target that already exists.
  * [`regenerate_index(repo: Path, dry_run: bool) -> None`](scripts/setup/init_project.py#L230-L237)
    * *Contract*: Regenerate INDEX.md and the per-root sub-indices through the real indexer.
  * [`refresh_mirrors(repo: Path, dry_run: bool) -> None`](scripts/setup/init_project.py#L240-L248)
    * *Contract*: Rewrite the CLAUDE.md and .agents/AGENTS.md mirrors from the canonical AGENTS.md.
  * [`leftover_findings(repo: Path, rules: tuple[Rule, ...]) -> list[str]`](scripts/setup/init_project.py#L251-L261)
    * *Contract*: Return ``path:line: token`` for every old-identity token still in a tracked text file.
  * [`say(label: str, dry_run: bool) -> None`](scripts/setup/init_project.py#L264-L267)
    * *Contract*: Print one plan line: ``would ...`` while dry-running, plain otherwise.
  * [`report_hits(hits: list[tuple[str, int]], dry_run: bool) -> None`](scripts/setup/init_project.py#L270-L277)
    * *Contract*: Report the token pass: one line per file while dry-running, a summary otherwise.
  * [`report_leftovers(findings: list[str]) -> int`](scripts/setup/init_project.py#L280-L291)
    * *Contract*: Print the leftover scan and return a non-zero code while anything survived.
  * [`adopt(args: argparse.Namespace, rules: tuple[Rule, ...]) -> int`](scripts/setup/init_project.py#L294-L312)
    * *Contract*: Apply the plan (or print it) and verify that no token of the old identity survives.
  * [`main(argv: list[str] | None) -> int`](scripts/setup/init_project.py#L315-L329)
    * *Contract*: Plan, apply and verify the adoption; return the process exit code.

- [`scripts/setup/setup_framework.py`](scripts/setup/setup_framework.py) (49 lines)
  * *Module Purpose*: Install the repository framework's Git hooks in this worktree.
  * [`main() -> int`](scripts/setup/setup_framework.py#L24-L45)

## Package `scripts/slurm_queue` — *Durable draining queue for Research sbatch jobs (model, store, submit, CLI, worker).*

- [`scripts/slurm_queue/cli.py`](scripts/slurm_queue/cli.py) (292 lines)
  * *Module Purpose*: Command-line entry point for the Slurm draining queue.
  * [`committed_text(repo: Path, script: str) -> str`](scripts/slurm_queue/cli.py#L82-L84)
    * *Contract*: Return the payload exactly as committed; unstaged edits never reach Slurm.
  * [`check_run_name(run_name: str) -> str`](scripts/slurm_queue/cli.py#L87-L91)
    * *Contract*: Refuse a run name that would not be extractable from Slurm state.
  * [`build_item(repo: Path, script: str, source: str, args: argparse.Namespace, environ: Mapping[str, str]) -> QueueItem`](scripts/slurm_queue/cli.py#L94-L119)
    * *Contract*: Build the item record exactly as the payload and environment describe it.
  * [`start_worker(store: QueueStore, profile: ResourceProfile, published: QueueItem, repo: Path) -> WorkerRef`](scripts/slurm_queue/cli.py#L122-L139)
    * *Contract*: Start the lane's worker; withdraw the published item when that fails.
  * [`enqueue(args: argparse.Namespace, environ: Mapping[str, str]) -> int`](scripts/slurm_queue/cli.py#L158-L183)
    * *Contract*: Validate, persist, and start one queue item, then print its record.
  * [`run_worker(args: argparse.Namespace, environ: Mapping[str, str]) -> int`](scripts/slurm_queue/cli.py#L197-L216)
    * *Contract*: Drain one lane allocation: the queue worker's process entry point.
  * [`parse_args(argv: Sequence[str] | None) -> argparse.Namespace`](scripts/slurm_queue/cli.py#L219-L228)
    * *Contract*: Parse the queue CLI's ``enqueue`` and ``worker`` subcommands.
  * [`main(argv: Sequence[str] | None, environ: Mapping[str, str] | None) -> int`](scripts/slurm_queue/cli.py#L269-L288)
    * *Contract*: Dispatch one subcommand; every refusal exits non-zero without submitting.

- [`scripts/slurm_queue/model.py`](scripts/slurm_queue/model.py) (600 lines)
  * *Module Purpose*: Resource-lane model for the Slurm draining queue.
  * [`class SbatchRejection(ValueError)`](scripts/slurm_queue/model.py#L141-L142)
    * *Contract*: Raised when a payload cannot be modelled as a queue item.
  * [`class ProvenanceError(RuntimeError)`](scripts/slurm_queue/model.py#L145-L146)
    * *Contract*: Raised when git cannot supply the commit or blob an item needs.
  * [`class ResourceProfile`](scripts/slurm_queue/model.py#L302-L397)
    * *Contract*: The allocation shape of one lane; its digest is the lane identity.
    * [`ResourceProfile.build(cls, values: Mapping[str, str], cluster: str, worker_seconds: int) -> ResourceProfile`](scripts/slurm_queue/model.py#L323-L343)
      * *Contract*: Build a profile from parsed directives, rejecting unusable shapes.
    * [`ResourceProfile.from_record(cls, record: Mapping[str, object]) -> ResourceProfile`](scripts/slurm_queue/model.py#L346-L353)
      * *Contract*: Rebuild a profile from its stored record, ignoring unknown keys.
    * [`ResourceProfile.canonical(self) -> dict[str, object]`](scripts/slurm_queue/model.py#L355-L357)
      * *Contract*: Return the exact fields that make two profiles different lanes.
    * [`ResourceProfile.lane_id(self) -> str`](scripts/slurm_queue/model.py#L359-L362)
      * *Contract*: Return the 16-hex lane identity hashed over the canonical profile.
    * [`ResourceProfile.sbatch_args(self) -> list[str]`](scripts/slurm_queue/model.py#L364-L393)
      * *Contract*: Return the ``sbatch`` resource overrides that reproduce this lane.
    * [`ResourceProfile.record(self) -> dict[str, object]`](scripts/slurm_queue/model.py#L395-L397)
      * *Contract*: Return the lane's ``profile.json`` payload.
  * [`class QueueItem`](scripts/slurm_queue/model.py#L401-L458)
    * *Contract*: One enqueued payload and everything needed to replay its provenance.
    * [`QueueItem.from_record(cls, record: Mapping[str, object]) -> QueueItem`](scripts/slurm_queue/model.py#L420-L434)
      * *Contract*: Rebuild an item from its stored record, ignoring unknown keys.
    * [`QueueItem.record(self) -> dict[str, object]`](scripts/slurm_queue/model.py#L436-L454)
      * *Contract*: Return the item's persisted payload.
    * [`QueueItem.env_map(self) -> dict[str, str]`](scripts/slurm_queue/model.py#L456-L458)
      * *Contract*: Return the recorded environment snapshot as a mapping.
  * [`worker_job_name(lane_id: str) -> str`](scripts/slurm_queue/model.py#L149-L151)
    * *Contract*: Return the deterministic job name of a lane's worker.
  * [`now_iso() -> str`](scripts/slurm_queue/model.py#L154-L156)
    * *Contract*: Return the current UTC time in ISO-8601 form.
  * [`worker_time_seconds(environ: Mapping[str, str]) -> int`](scripts/slurm_queue/model.py#L159-L161)
    * *Contract*: Return the worker horizon from ``RESEARCH_QUEUE_WORKER_TIME`` (or default).
  * [`empty_grace_seconds(environ: Mapping[str, str]) -> float`](scripts/slurm_queue/model.py#L164-L177)
    * *Contract*: Return the empty-lane grace from ``RESEARCH_QUEUE_EMPTY_GRACE_SECONDS``.
  * [`parse_duration(text: str) -> int`](scripts/slurm_queue/model.py#L186-L212)
    * *Contract*: Parse a Slurm duration (``MM``, ``HH:MM:SS``, ``D-HH:MM:SS``) to seconds.
  * [`format_duration(seconds: int) -> str`](scripts/slurm_queue/model.py#L215-L219)
    * *Contract*: Render seconds as the ``D-HH:MM:SS``/``HH:MM:SS`` form Slurm accepts.
  * [`parse_memory_mib(text: str) -> int`](scripts/slurm_queue/model.py#L222-L229)
    * *Contract*: Parse a Slurm memory request (``16G``, ``1024M``, bytes) into MiB.
  * [`split_directive(body: str, number: int) -> tuple[str, str]`](scripts/slurm_queue/model.py#L232-L246)
    * *Contract*: Split one ``#SBATCH`` body into its normalized ``(key, value)`` pair.
  * [`directive_values(source: str) -> dict[str, str]`](scripts/slurm_queue/model.py#L249-L262)
    * *Contract*: Return the raw ``key -> value`` map of a script's ``#SBATCH`` lines.
  * [`parse_sbatch(source: str, cluster: str, worker_time: str) -> tuple[ResourceProfile, int]`](scripts/slurm_queue/model.py#L461-L482)
    * *Contract*: Parse one sbatch script into its lane profile and requested seconds.
  * [`resolve_script(repo: Path, script: str) -> str`](scripts/slurm_queue/model.py#L485-L507)
    * *Contract*: Validate a payload path as a repository-relative ``slurm/*.sbatch`` file.
  * [`run_git(repo: Path, args: Sequence[str]) -> str`](scripts/slurm_queue/model.py#L510-L526)
    * *Contract*: Run a read-only git command, failing closed when it cannot answer.
  * [`head_commit(repo: Path) -> str`](scripts/slurm_queue/model.py#L529-L534)
    * *Contract*: Return the commit the repository currently has checked out.
  * [`is_dirty(repo: Path) -> bool`](scripts/slurm_queue/model.py#L537-L539)
    * *Contract*: Return whether the working tree differs from HEAD.
  * [`committed_text(repo: Path, script: str) -> str`](scripts/slurm_queue/model.py#L542-L544)
    * *Contract*: Return the committed text of a payload script (it must be in HEAD).
  * [`sha256_text(text: str) -> str`](scripts/slurm_queue/model.py#L547-L549)
    * *Contract*: Return the SHA-256 digest of a text payload.
  * [`environment_snapshot(environ: Mapping[str, str]) -> tuple[tuple[str, str], ...]`](scripts/slurm_queue/model.py#L552-L559)
    * *Contract*: Record the ``RESEARCH_*`` override set, minus the queue's own variables.
  * [`receipt_record(**fields) -> dict[str, object]`](scripts/slurm_queue/model.py#L585-L595)
    * *Contract*: Build a terminal receipt payload in the queue's receipt schema.
  * [`renumber(item: QueueItem, item_id: str, sequence: int, lane_id: str) -> QueueItem`](scripts/slurm_queue/model.py#L598-L600)
    * *Contract*: Return the item stamped with its lane and sequence-allocated id.

- [`scripts/slurm_queue/runtime.py`](scripts/slurm_queue/runtime.py) (62 lines)
  * *Module Purpose*: Local runtime helpers for the Slurm draining queue.
  * [`file_sha256(path: Path) -> str`](scripts/slurm_queue/runtime.py#L28-L34)
    * *Contract*: Return the SHA256 digest of a file without loading it into memory.
  * [`atomic_json_dump(path: Path, state: dict[str, Any]) -> None`](scripts/slurm_queue/runtime.py#L50-L62)
    * *Contract*: Atomically serialize JSON through an exclusive temporary file.

- [`scripts/slurm_queue/store.py`](scripts/slurm_queue/store.py) (579 lines)
  * *Module Purpose*: Durable FIFO state for the Slurm draining queue.
  * [`class QueueStateError(RuntimeError)`](scripts/slurm_queue/store.py#L68-L69)
    * *Contract*: Raised when queue state cannot be trusted.
  * [`class QueueLockError(RuntimeError)`](scripts/slurm_queue/store.py#L72-L73)
    * *Contract*: Raised when the lane lock cannot be taken.
  * [`class LaneProfileMismatch(RuntimeError)`](scripts/slurm_queue/store.py#L76-L77)
    * *Contract*: Raised when a lane id is reused for a different resource profile.
  * [`class Lane`](scripts/slurm_queue/store.py#L161-L201)
    * *Contract*: Filesystem layout of one resource lane.
    * [`Lane.create(self) -> Lane`](scripts/slurm_queue/store.py#L166-L171)
      * *Contract*: Create every lane directory and return the lane.
    * [`Lane.profile(self) -> Path`](scripts/slurm_queue/store.py#L173-L174)
    * [`Lane.sequence(self) -> Path`](scripts/slurm_queue/store.py#L176-L177)
    * [`Lane.worker(self) -> Path`](scripts/slurm_queue/store.py#L179-L180)
    * [`Lane.lock(self) -> Path`](scripts/slurm_queue/store.py#L182-L183)
    * [`Lane.pending(self) -> Path`](scripts/slurm_queue/store.py#L185-L186)
    * [`Lane.running(self) -> Path`](scripts/slurm_queue/store.py#L188-L189)
    * [`Lane.succeeded(self) -> Path`](scripts/slurm_queue/store.py#L191-L192)
    * [`Lane.failed(self) -> Path`](scripts/slurm_queue/store.py#L194-L195)
    * [`Lane.logs(self) -> Path`](scripts/slurm_queue/store.py#L197-L198)
    * [`Lane.state_directories(self) -> tuple[Path, ...]`](scripts/slurm_queue/store.py#L200-L201)
  * [`class QueueStore`](scripts/slurm_queue/store.py#L205-L477)
    * *Contract*: Durable FIFO state for every lane, rooted outside the git tree.
    * [`QueueStore.default(cls, repo: Path, environ: Mapping[str, str] | None) -> QueueStore`](scripts/slurm_queue/store.py#L211-L219)
      * *Contract*: Return the store rooted at ``RESEARCH_QUEUE_ROOT`` or ``results/slurm_queue``.
    * [`QueueStore.lane(self, cluster: str, lane_id: str) -> Lane`](scripts/slurm_queue/store.py#L221-L223)
      * *Contract*: Return the layout of one lane without touching the filesystem.
    * [`QueueStore.ensure_lane(self, profile: ResourceProfile) -> Lane`](scripts/slurm_queue/store.py#L225-L239)
      * *Contract*: Create the lane and verify any pre-existing profile before reuse.
    * [`QueueStore.publish(self, item: QueueItem, profile: ResourceProfile) -> QueueItem`](scripts/slurm_queue/store.py#L259-L266)
      * *Contract*: Allocate a sequence and append one item. Call with the lane lock held.
    * [`QueueStore.pending_items(self, profile: ResourceProfile) -> list[QueueItem]`](scripts/slurm_queue/store.py#L268-L275)
      * *Contract*: Return the lane's FIFO order without claiming anything.
    * [`QueueStore.claim(self, profile: ResourceProfile, job_id: str) -> QueueItem | None`](scripts/slurm_queue/store.py#L277-L297)
      * *Contract*: Atomically move the oldest pending item into ``running``.
    * [`QueueStore.unpublish(self, profile: ResourceProfile, item_id: str) -> bool`](scripts/slurm_queue/store.py#L299-L305)
      * *Contract*: Withdraw a pending item that no worker accepted. Call under the lane lock.
    * [`QueueStore.bump_handoffs(self, profile: ResourceProfile, item_id: str) -> int`](scripts/slurm_queue/store.py#L307-L314)
      * *Contract*: Count one fit handoff on a pending item. Call under the lane lock.
    * [`QueueStore.existing_receipt(self, profile: ResourceProfile, item_id: str) -> Path | None`](scripts/slurm_queue/store.py#L316-L323)
      * *Contract*: Return the terminal receipt of an item, when it already finished.
    * [`QueueStore.finish(self, profile: ResourceProfile, item_id: str, receipt: Mapping[str, object]) -> Path`](scripts/slurm_queue/store.py#L325-L350)
      * *Contract*: Write a terminal receipt first, then drop the running record.
    * [`QueueStore.read_profile(self, cluster: str, lane_id: str) -> ResourceProfile`](scripts/slurm_queue/store.py#L352-L357)
      * *Contract*: Return the lane's stored profile, failing closed when it is absent.
    * [`QueueStore.read_worker(self, profile: ResourceProfile) -> dict[str, object] | None`](scripts/slurm_queue/store.py#L359-L364)
      * *Contract*: Return the lane's recorded worker, or ``None`` when it has none.
    * [`QueueStore.write_worker(self, profile: ResourceProfile, job_id: str) -> dict[str, object]`](scripts/slurm_queue/store.py#L366-L377)
      * *Contract*: Record which Slurm job owns the lane's drain.
    * [`QueueStore.clear_worker(self, profile: ResourceProfile, job_id: str) -> bool`](scripts/slurm_queue/store.py#L379-L385)
      * *Contract*: Retire the lane's worker record when it names ``job_id``.
    * [`QueueStore.reconcile(self, profile: ResourceProfile, job_id: str, live_worker_ids: Collection[str]) -> list[str]`](scripts/slurm_queue/store.py#L387-L410)
      * *Contract*: Trust receipts, retire running records of workers that are gone.
    * [`QueueStore.run_name_in_use(self, run_name: str) -> Path | None`](scripts/slurm_queue/store.py#L440-L455)
      * *Contract*: Return the queue record that already uses ``run_name``, if any.
    * [`QueueStore.lane_lock(self, profile: ResourceProfile, wait_seconds: float) -> Iterator[Lane]`](scripts/slurm_queue/store.py#L458-L467)
      * *Contract*: Hold the lane's lifecycle lock for one short critical section.
    * [`QueueStore.root_lock(self, wait_seconds: float) -> Iterator[None]`](scripts/slurm_queue/store.py#L470-L477)
      * *Contract*: Hold the store-wide lock that serializes run-name allocation.
  * [`acquire_lock(lock: Path, wait_seconds: float) -> str`](scripts/slurm_queue/store.py#L544-L558)
    * *Contract*: Take a lock directory (or break a provably abandoned one); return its token.
  * [`release_lock(lock: Path, token: str) -> None`](scripts/slurm_queue/store.py#L561-L569)
    * *Contract*: Release a lock only when this process's token still owns it.
  * [`acquire_lane_lock(lane: Lane, wait_seconds: float) -> str`](scripts/slurm_queue/store.py#L572-L574)
    * *Contract*: Take the lane lock (or break a provably abandoned one) and return its token.
  * [`release_lane_lock(lane: Lane, token: str) -> None`](scripts/slurm_queue/store.py#L577-L579)
    * *Contract*: Release the lane lock only when this process's token still owns it.

- [`scripts/slurm_queue/submit.py`](scripts/slurm_queue/submit.py) (327 lines)
  * *Module Purpose*: Submit exactly one Slurm worker per lane.
  * [`class SlurmError(RuntimeError)`](scripts/slurm_queue/submit.py#L54-L55)
    * *Contract*: Raised when Slurm cannot be asked, or refuses a submission.
  * [`class SplitBrainError(SlurmError)`](scripts/slurm_queue/submit.py#L58-L59)
    * *Contract*: Raised when a lane has workers it cannot explain.
  * [`class WorkerRef`](scripts/slurm_queue/submit.py#L73-L80)
    * *Contract*: The lane's worker, whether it was just submitted or already running.
  * [`squeue_states(name: str, runner) -> dict[str, str]`](scripts/slurm_queue/submit.py#L83-L93)
    * *Contract*: Return ``job_id -> state`` for live jobs carrying this exact job name.
  * [`live_workers(lane_id: str, runner) -> dict[str, str]`](scripts/slurm_queue/submit.py#L96-L98)
    * *Contract*: Return the lane's live workers as ``job_id -> state``.
  * [`worker_argv(profile: ResourceProfile, repo, script: str, dependency: str | None, parsable: bool) -> list[str]`](scripts/slurm_queue/submit.py#L101-L125)
    * *Contract*: Return the exact ``sbatch`` argv that reproduces the lane's worker.
  * [`validate_worker(repo, profile: ResourceProfile, script: str, runner) -> None`](scripts/slurm_queue/submit.py#L158-L167)
    * *Contract*: Run the worker's contract check and Slurm's own argv validation.
  * [`parse_job_id(stdout: str, name: str, runner) -> str`](scripts/slurm_queue/submit.py#L170-L181)
    * *Contract*: Read a strict job id, recovering an ambiguous submission by job name.
  * [`submit_worker(repo, profile: ResourceProfile, script: str, dependency: str | None, runner) -> str`](scripts/slurm_queue/submit.py#L184-L202)
    * *Contract*: Validate and submit the lane's worker, returning its Slurm job id.
  * [`ensure_worker(store: QueueStore, profile: ResourceProfile, repo, runner) -> WorkerRef`](scripts/slurm_queue/submit.py#L247-L271)
    * *Contract*: Submit or adopt the lane's single worker. Call with the lane lock held.
  * [`handoff_worker(store: QueueStore, profile: ResourceProfile, repo, predecessor_job_id: str, runner) -> WorkerRef`](scripts/slurm_queue/submit.py#L274-L293)
    * *Contract*: Submit the successor that inherits the lane. Call with the lane lock held.
  * [`allocation_remaining_seconds(job_id: str, runner) -> float | None`](scripts/slurm_queue/submit.py#L312-L327)
    * *Contract*: Return seconds left in the allocation, or None when it cannot be read.

## Package `scripts/slurm_queue/worker` — *Drain one Slurm lane allocation.*

- [`scripts/slurm_queue/worker/execute.py`](scripts/slurm_queue/worker/execute.py) (177 lines)
  * *Module Purpose*: Run one resolved payload as a bounded child process group.
  * [`run_item(session: WorkerSession, item: QueueItem, preflight: Callable[[WorkerSession, QueueItem, Path], str | None]) -> str`](scripts/slurm_queue/worker/execute.py#L78-L106)
    * *Contract*: Resolve, re-gate, execute, and receipt one claimed item.
  * [`execute_item(session: WorkerSession, item: QueueItem, resolved: Resolved) -> tuple[str, int | None, str | None]`](scripts/slurm_queue/worker/execute.py#L109-L119)
    * *Contract*: Run one payload as a bounded child process group.
  * [`staged_payload_path(log: Path) -> Path`](scripts/slurm_queue/worker/execute.py#L122-L129)
    * *Contract*: Return where the resolved payload bytes are staged for the child.
  * [`terminate_group(process: subprocess.Popen, grace_seconds: float) -> None`](scripts/slurm_queue/worker/execute.py#L164-L174)
    * *Contract*: Terminate the item's process group, escalating only after the grace.

- [`scripts/slurm_queue/worker/lane.py`](scripts/slurm_queue/worker/lane.py) (310 lines)
  * *Module Purpose*: Drain the lane: fit, handoff, idle grace and the drain loop.
  * [`class StepOutcome`](scripts/slurm_queue/worker/lane.py#L88-L92)
    * *Contract*: What one non-empty drain step did: a failure delta, or the exit code.
  * [`class IdleWindow`](scripts/slurm_queue/worker/lane.py#L250-L274)
    * *Contract*: Bounded wait on an empty lane: exit once the grace elapses without items.
    * [`IdleWindow.elapsed(self) -> bool`](scripts/slurm_queue/worker/lane.py#L258-L269)
      * *Contract*: Announce the wait once and report whether the grace has run out.
    * [`IdleWindow.reset(self) -> None`](scripts/slurm_queue/worker/lane.py#L271-L274)
      * *Contract*: Forget the wait, so the next empty moment starts a fresh grace.
  * [`run_lane(session: WorkerSession, preflight: Callable[[WorkerSession, QueueItem, Path], str | None], remaining_probe: Callable[[str], float | None], live_probe: Callable[[str], dict[str, str]], grace_seconds: float, clock: Callable[[], float]) -> int`](scripts/slurm_queue/worker/lane.py#L43-L58)
    * *Contract*: Drain the lane until it empties after its grace, the allocation is short, or it fails.
  * [`drain_loop(session: WorkerSession, preflight: Callable[[WorkerSession, QueueItem, Path], str | None], remaining_probe: Callable[[str], float | None], grace_seconds: float, clock: Callable[[], float]) -> int`](scripts/slurm_queue/worker/lane.py#L61-L84)
    * *Contract*: Drain the lane FIFO until it empties, the allocation is short, or it fails.
  * [`report_reconcile(session: WorkerSession, live_probe: Callable[[str], dict[str, str]]) -> None`](scripts/slurm_queue/worker/lane.py#L127-L148)
    * *Contract*: Print the receipts and retirements this allocation's start reconciled.
  * [`finish_allocation(session: WorkerSession, failures: int) -> int | None`](scripts/slurm_queue/worker/lane.py#L172-L183)
    * *Contract*: Exit when the lane is still empty under the lock, else return ``None``.
  * [`hand_off(session: WorkerSession, reason: str, fit_item: QueueItem | None) -> int`](scripts/slurm_queue/worker/lane.py#L186-L213)
    * *Contract*: Submit the successor worker that inherits the pending items.
  * [`fail_unfittable(session: WorkerSession) -> bool`](scripts/slurm_queue/worker/lane.py#L227-L246)
    * *Contract*: Fail an item a second worker in a row cannot fit; never chain allocations forever.
  * [`refresh_remaining(session: WorkerSession, probe: Callable[[str], float | None]) -> WorkerSession`](scripts/slurm_queue/worker/lane.py#L277-L285)
    * *Contract*: Re-read the allocation's remaining time; a failed read is retried next loop.
  * [`head_item(session: WorkerSession) -> QueueItem | None`](scripts/slurm_queue/worker/lane.py#L288-L291)
    * *Contract*: Return the lane's FIFO head without claiming it.
  * [`next_action(session: WorkerSession, executed: frozenset[str]) -> str`](scripts/slurm_queue/worker/lane.py#L294-L306)
    * *Contract*: Decide what this allocation does next: ``run``, ``handoff``, ``unfit``, ``empty``.

- [`scripts/slurm_queue/worker/resolve.py`](scripts/slurm_queue/worker/resolve.py) (153 lines)
  * *Module Purpose*: Resolve a claimed item against the tree as it stands, then re-gate it.
  * [`resolve_or_refuse(session: WorkerSession, item: QueueItem, preflight: Callable[[WorkerSession, QueueItem, Path], str | None], log: Path) -> tuple[Resolved | None, tuple[str, int | None, str | None] | None]`](scripts/slurm_queue/worker/resolve.py#L40-L53)
    * *Contract*: Return the resolved payload, or the terminal refusal that blocks it.
  * [`gate_preflight(session: WorkerSession, item: QueueItem, log: Path) -> str | None`](scripts/slurm_queue/worker/resolve.py#L56-L74)
    * *Contract*: Re-gate the version about to run; return why it is blocked, or ``None``.
  * [`last_failure(log: Path, limit: int) -> str`](scripts/slurm_queue/worker/resolve.py#L103-L111)
    * *Contract*: Return the gate output that explains a failed preflight, bounded.
  * [`resolve_item(session: WorkerSession, item: QueueItem) -> tuple[Resolved | None, str, str | None]`](scripts/slurm_queue/worker/resolve.py#L114-L142)
    * *Contract*: Resolve an item against the tree as it stands now.
  * [`external_payload(session: WorkerSession, item: QueueItem) -> tuple[Resolved | None, str, str | None]`](scripts/slurm_queue/worker/resolve.py#L145-L153)
    * *Contract*: Resolve a payload in a git-less deploy root against its deployed bytes.

- [`scripts/slurm_queue/worker/session.py`](scripts/slurm_queue/worker/session.py) (160 lines)
  * *Module Purpose*: Worker session state: the allocation's checkout, commit and environment.
  * [`class WorkerSession`](scripts/slurm_queue/worker/session.py#L127-L143)
    * *Contract*: Everything one worker invocation needs, so tests need no git or Slurm.
    * [`WorkerSession.tree_state(self) -> str`](scripts/slurm_queue/worker/session.py#L139-L143)
      * *Contract*: Return the provenance label this allocation's receipts carry.
  * [`class Resolved`](scripts/slurm_queue/worker/session.py#L147-L152)
    * *Contract*: The payload version an item actually runs.
  * [`class WorkerInterrupted(Exception)`](scripts/slurm_queue/worker/session.py#L155-L156)
    * *Contract*: Raised in the worker when Slurm asks the allocation to stop.
  * [`item_log_path(session: WorkerSession, item: QueueItem) -> Path`](scripts/slurm_queue/worker/session.py#L36-L39)
    * *Contract*: Return the item's child-log path inside its lane.
  * [`child_env(item: QueueItem) -> dict[str, str]`](scripts/slurm_queue/worker/session.py#L42-L48)
    * *Contract*: Return the worker environment with inherited ``RESEARCH_*`` replaced by the snapshot.
  * [`checkout_refusal(session: WorkerSession) -> str | None`](scripts/slurm_queue/worker/session.py#L51-L58)
    * *Contract*: Return why the worker must not start, or ``None`` when the checkout is usable.
  * [`session_from_environment(repo: Path, lane_id: str, environ: Mapping[str, str] | None) -> WorkerSession`](scripts/slurm_queue/worker/session.py#L61-L80)
    * *Contract*: Build the session an allocation actually runs with (git + Slurm + store).
  * [`checkout_provenance(repo: Path, environ: Mapping[str, str] | None) -> tuple[str, bool, bool]`](scripts/slurm_queue/worker/session.py#L99-L118)
    * *Contract*: Return the root's commit, whether git answered, and whether it is clean.
  * [`now_or_never(seconds: float | None) -> str`](scripts/slurm_queue/worker/session.py#L121-L123)
    * *Contract*: Render a remaining-seconds value for a status line.

- [`scripts/slurm_queue/worker/smoke.py`](scripts/slurm_queue/worker/smoke.py) (155 lines)
  * *Module Purpose*: CPU smoke: exercise publish, claim, execute and receipt without Slurm.
  * [`smoke(repo: Path) -> int`](scripts/slurm_queue/worker/smoke.py#L53-L75)
    * *Contract*: Exercise parse, enqueue, claim, execute, and receipt without Slurm.
  * [`smoke_problems(code: int, session: WorkerSession, receipt: Path | None, item_id: str) -> list[str]`](scripts/slurm_queue/worker/smoke.py#L78-L97)
    * *Contract*: Return every way the smoke run failed to behave like a real drain.
  * [`smoke_preflight(session: WorkerSession, item: QueueItem, log: Path) -> None`](scripts/slurm_queue/worker/smoke.py#L100-L102)
    * *Contract*: The smoke exercises the drain path; the gate preflight has its own suite.
  * [`smoke_session(root: Path, template: str) -> tuple[WorkerSession, QueueStore, str]`](scripts/slurm_queue/worker/smoke.py#L105-L125)
    * *Contract*: Build a temporary lane holding one harmless item, and run it.
  * [`write_smoke_payload(root: Path) -> None`](scripts/slurm_queue/worker/smoke.py#L145-L149)
    * *Contract*: Create the harmless payload repository the smoke executes in.

