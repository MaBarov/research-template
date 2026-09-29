# Test layout

Two suites, both collected from the repository root:

```
tests/           mirror tests and integration tests
framework/tests/ tests that pin the gates themselves
```

`tests/research/` mirrors the production `research/` directory names and Python
files, each mirrored file prefixed with `tests_` — the mirror-coverage gate maps
a production module to its test by that name:

```text
research/params/registry.py  ->  tests/research/params/tests_registry.py
```

Mirror files are real tests, not empty scaffolds: they are what the coverage
gate measures a production module's own body against, so a mirror that only
imports its module fails the self-coverage requirement. Regenerate missing
mirror files with:

```bash
python scripts/setup/create_test_scaffold.py
```

Integration suites live directly under `tests/framework/`: they build a
committed scratch repository, install the real hook (`core.hooksPath`), and drive
a real `git commit`, so a gate's decision is proved end to end rather than
against a stub. Anything a scratch checkout needs to look like this repository is
built by `tests/framework/scratch_registry.py`.

Run everything:

```bash
.venv/bin/python -m pytest tests framework -q
```
