# third_party — vendored tooling

Trees here are **copied, not imported**: they are excluded from the lint and
duplication gates (`pyproject.toml`, `.jscpd.json`) and are never reformatted as
a side effect of other work. Nothing in `research/`, `framework/` or `scripts/`
imports them at runtime; they are tools a human runs in a deliberate session.

## `refactor/` — the decomposition runner

`rope_refactor.py` (+ `rope_batch.py`, `rope_batch_driver.py`) is the hardened,
deterministic Rope runner the code-size rules call for. It is vendored rather
than installed because every decomposition in this repository is reproducible
only if the tool that performed it is pinned here: a module over 600 lines, or a
function over 30, is split with this runner, never by hand.

```
python third_party/refactor/rope_refactor.py --help
python third_party/refactor/rope_refactor.py move_global \
    --source-file research/a/b.py --dest-file research/a/c.py --names f g
python third_party/refactor/rope_refactor.py extract_function \
    --file research/a/b.py --name slow_part --scope function:fast_part
```

Properties that matter when a gate demands a decomposition:

* dry-run pre-simulation with AST validation of every generated file, so a
  refused move leaves the tree untouched;
* strict path containment — it refuses to write outside the project root;
* revert on failure (Rope's own history) and machine-readable `--json` output.

Requires the `rope` package in the interpreter that runs it:

```bash
.venv/bin/python -m pip install rope
.venv/bin/python -m pytest third_party/refactor -q    # the runner's own tests
```

Changing a file under `third_party/` is a change to the tool, not a refactor of
the project: make it in its own commit, with its tests, and say so in the message.
