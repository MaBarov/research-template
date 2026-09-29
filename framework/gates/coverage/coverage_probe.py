"""Pytest plugin: statement coverage with per-test contexts and exact loop counts.

Load with ``-p framework.gates.coverage.coverage_probe`` and pass ``--cov-json PATH``
(required); the statement/loop probe writes its report there.
``--cov-src PREFIX`` (default ``research``) selects the import prefix whose modules
are instrumented and measured.

Loop instrumentation records, for every ``for``/``while``/``async for``
statement, how many iterations each entry performed, keyed by
``"<module>:<ordinal>"`` where the ordinal is the loop's index in
``sorted((lineno, col_offset))`` order over the module — stable under line
shifts. Comprehensions and generator expressions are **not** instrumented:
they have no loop statement boundary of their own.

Report schema ``research.loop-coverage-report.v1``::

    {"schema": ..., "src_prefix": "research",
     "pytest": {"collected": 459, "failed": 0, "exitstatus": 0},
     "files": {"research/execution/validation.py": {
        "statements": 22,
        "lines_by_context": {"tests/...::test_x": [12, 13, 15]},
        "loops": {"0": {"lineno": 15, "by_context": {"tests/...::test_x": [0, 1, 3]}}},
        "transform_error": null}}}

A module whose AST transform fails is compiled uninstrumented and reports its
error string, never a silent skip. The policy that consumes this report lives
in ``framework/gates/check_coverage.py``.

Invariants & Expected State:
    * Loop ids are ``"<module>:<ordinal>"`` where the ordinal is the loop's
      index in ``sorted((lineno, col_offset))`` order over the module, so they
      stay stable under line shifts.
    * Only ``for``, ``while`` and ``async for`` statements are instrumented;
      comprehensions and generator expressions are not.
    * ``--cov-json`` is required: with no report path the probe has nothing to
      write, so no run is silently clean.
    * A module whose AST transform fails is compiled uninstrumented and reports
      its ``transform_error`` string, never a silent skip.
"""

from __future__ import annotations

import ast
import importlib.abc
import importlib.machinery
import importlib.util
import itertools
import json
import os
import sys
import threading
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import coverage
import pytest
from coverage.parser import PythonParser

_PROBE_NAME = "_research_probe"


class _Registry:
    """Thread-safe loop-entry counter keyed by (context, loop id)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.counts: dict[tuple[str, str], Counter] = {}
        self.open: dict[int, tuple[tuple[str, str], int]] = {}
        self.tokens = itertools.count()
        self.state = threading.local()

    def context(self) -> str:
        return getattr(self.state, "context", "<background>")

    def set_context(self, context: str) -> None:
        self.state.context = context

    def begin(self, loop_id: str) -> int:
        token = next(self.tokens)
        with self.lock:
            self.open[token] = ((self.context(), loop_id), 0)
        return token

    def step(self, token: int) -> None:
        with self.lock:
            key, count = self.open[token]
            self.open[token] = (key, count + 1)

    def end(self, token: int) -> None:
        with self.lock:
            (context, loop_id), count = self.open.pop(token)
            self.counts.setdefault((context, loop_id), Counter())[count] += 1

    def snapshot(self) -> dict[tuple[str, str], dict[int, int]]:
        with self.lock:
            return {
                key: {count: entries for count, entries in counter.items()}
                for key, counter in self.counts.items()
            }


_REGISTRY = _Registry()

begin = _REGISTRY.begin
step = _REGISTRY.step
end = _REGISTRY.end


def _probe_call(name: str, args: list[ast.expr]) -> ast.Call:
    return ast.Call(
        func=ast.Attribute(
            value=ast.Name(_PROBE_NAME, ast.Load()), attr=name, ctx=ast.Load()
        ),
        args=args,
        keywords=[],
    )


def _loop_nodes(tree: ast.AST) -> list[ast.For | ast.AsyncFor | ast.While]:
    nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While))
    ]
    nodes.sort(key=lambda node: (node.lineno, node.col_offset))
    return nodes


def _inject_probe_handle(tree: ast.Module, plugin_module: str) -> None:
    """Bind ``_research_probe`` to the live plugin module without sys.path games."""

    statement = f"{_PROBE_NAME} = __import__('sys').modules[{plugin_module!r}]"
    node = ast.parse(statement).body[0]
    insert_at = 0
    body = tree.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        insert_at = 1
    while (
        insert_at < len(body)
        and isinstance(body[insert_at], ast.ImportFrom)
        and body[insert_at].module == "__future__"
    ):
        insert_at += 1
    body.insert(insert_at, node)


class _LoopInstrumenter(ast.NodeTransformer):
    """Wrap every loop statement in begin/step/end probes."""

    def __init__(self, module: str, ordinals: dict[int, int]) -> None:
        self.module = module
        self.ordinals = ordinals

    def _wrap(self, node: ast.For | ast.AsyncFor | ast.While) -> list[ast.stmt]:
        ordinal = self.ordinals[id(node)]
        token = f"_probe_loop_token_{ordinal}"
        loop_id = f"{self.module}:{ordinal}"
        node.body.insert(
            0,
            ast.Expr(value=_probe_call("step", [ast.Name(token, ast.Load())])),
        )
        assign = ast.Assign(
            targets=[ast.Name(token, ast.Store())],
            value=_probe_call("begin", [ast.Constant(loop_id)]),
        )
        guard = ast.Try(
            body=[node],
            handlers=[],
            orelse=[],
            finalbody=[
                ast.Expr(value=_probe_call("end", [ast.Name(token, ast.Load())]))
            ],
        )
        return [assign, guard]

    def visit_For(self, node: ast.For) -> list[ast.stmt]:
        self.generic_visit(node)
        return self._wrap(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> list[ast.stmt]:
        self.generic_visit(node)
        return self._wrap(node)

    def visit_While(self, node: ast.While) -> list[ast.stmt]:
        self.generic_visit(node)
        return self._wrap(node)


def instrument_tree(
    tree: ast.Module, module: str, plugin_module: str
) -> dict[int, int]:
    """Instrument one parsed module in place; return ``{ordinal: lineno}``."""

    nodes = _loop_nodes(tree)
    linenos = {index: node.lineno for index, node in enumerate(nodes)}
    ordinals = {id(node): index for index, node in enumerate(nodes)}
    _inject_probe_handle(tree, plugin_module)
    _LoopInstrumenter(module, ordinals).visit(tree)
    ast.fix_missing_locations(tree)
    return linenos


class _InstrumentedLoader(importlib.machinery.SourceFileLoader):
    def __init__(self, fullname: str, path: str, state: _ProbeState) -> None:
        super().__init__(fullname, path)
        self._state = state

    def get_code(self, fullname):
        """Compile from source every time; cached bytecode would drop the probes."""

        source_path = self.get_filename(fullname)
        return self.source_to_code(self.get_data(source_path), source_path)

    def source_to_code(self, data, path, *, _optimize=-1):
        source = (
            importlib.util.decode_source(bytes(data))
            if isinstance(data, (bytes, bytearray))
            else data
        )
        try:
            tree = ast.parse(source, filename=str(path))
            linenos = instrument_tree(tree, self.name, self._state.plugin_module)
        except Exception as error:  # noqa: BLE001 - recorded, never silent
            self._state.transform_errors[self.name] = f"{type(error).__name__}: {error}"
            return super().source_to_code(data, path, _optimize=_optimize)
        self._state.loop_linenos[self.name] = linenos
        self._state.module_files[self.name] = str(path)
        return compile(tree, str(path), "exec", dont_inherit=True, optimize=_optimize)


class _ProbeFinder(importlib.abc.MetaPathFinder):
    """Instrument every import under the configured prefix."""

    def __init__(self, state: _ProbeState) -> None:
        self._state = state

    def find_spec(self, fullname, path=None, target=None):
        prefix = self._state.prefix
        if not (fullname == prefix or fullname.startswith(f"{prefix}.")):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or not spec.origin or not spec.origin.endswith(".py"):
            return None
        spec.loader = _InstrumentedLoader(fullname, spec.origin, self._state)
        return spec


class _ProbeState:
    def __init__(self, prefix: str, json_path: str, plugin_module: str) -> None:
        self.prefix = prefix
        self.json_path = Path(json_path)
        self.plugin_module = plugin_module
        self.transform_errors: dict[str, str] = {}
        self.loop_linenos: dict[str, dict[int, int]] = {}
        self.module_files: dict[str, str] = {}
        self.cov: coverage.Coverage | None = None


def pytest_addoption(parser) -> None:
    group = parser.getgroup("coverage-probe", "statement/loop coverage probe")
    group.addoption(
        "--cov-src",
        action="store",
        default="research",
        help="import prefix to instrument and measure (default: research)",
    )
    group.addoption(
        "--cov-json",
        action="store",
        default=None,
        help="path of the JSON report (required)",
    )


def pytest_configure(config) -> None:
    json_path = config.getoption("--cov-json")
    if not json_path:
        raise pytest.UsageError(
            "framework.gates.coverage.coverage_probe requires --cov-json PATH"
        )
    state = _ProbeState(
        prefix=config.getoption("--cov-src"),
        json_path=json_path,
        plugin_module=__name__,
    )
    cov = coverage.Coverage(
        branch=True,
        source=[state.prefix],
        data_file=str(Path(os.path.abspath(json_path)).with_name(".coverage_probe")),
        config_file=False,
    )
    cov.start()
    state.cov = cov
    sys.meta_path.insert(0, _ProbeFinder(state))
    config._coverage_probe_state = state


def pytest_runtest_setup(item) -> None:
    state = getattr(item.config, "_coverage_probe_state", None)
    if state is None or state.cov is None:
        return
    state.cov.switch_context(item.nodeid)
    _REGISTRY.set_context(item.nodeid)


def pytest_runtest_teardown(item) -> None:
    _REGISTRY.set_context("<background>")


def _relative(filename: str) -> str:
    path = Path(filename).resolve()
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def statement_lines(path: Path) -> tuple[set[int], set[int]]:
    """Return coverage's executable-statement and excluded line sets."""

    parser = PythonParser(
        text=path.read_text(encoding="utf-8", errors="replace"), filename=str(path)
    )
    parser.parse_source()
    return set(parser.statements), set(parser.excluded)


def _known_modules(state: _ProbeState) -> dict[str, str]:
    """Map repo-relative filename -> module name for every probe module."""
    known: dict[str, str] = {}
    for module, filename in state.module_files.items():
        known.setdefault(_relative(filename), module)
    return known


def _loop_table(state: _ProbeState, known: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Per-module loop ordinal -> {lineno, by_context} with observed counts."""
    loops: dict[str, dict[str, Any]] = {}
    for rel, module in known.items():
        loops[rel] = {
            str(ordinal): {"lineno": lineno, "by_context": defaultdict(list)}
            for ordinal, lineno in sorted(state.loop_linenos.get(module, {}).items())
        }
    for (context, loop_id), counts in _REGISTRY.snapshot().items():
        module, _, ordinal = loop_id.rpartition(":")
        filename = state.module_files.get(module)
        if filename is None:
            continue
        entry = loops.get(_relative(filename), {}).get(ordinal)
        if entry is None:
            continue
        entry["by_context"][context].extend(
            count for count, entries in sorted(counts.items()) for _ in range(entries)
        )
    return loops


def _loop_entry(rel: str, loops: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Per-loop ordinal entry for one file, counts sorted per context."""
    return {
        ordinal: {
            "lineno": entry["lineno"],
            "by_context": {
                context: sorted(counts)
                for context, counts in sorted(entry["by_context"].items())
            },
        }
        for ordinal, entry in sorted(loops.get(rel, {}).items())
    }


def _lines_by_context(data: Any, filename: str, kept: set[int]) -> dict[str, list[int]]:
    """Executable statement lines grouped by coverage context."""
    per_context: dict[str, set[int]] = defaultdict(set)
    for lineno, contexts in data.contexts_by_lineno(filename).items():
        if lineno not in kept:
            continue
        for context in contexts:
            per_context[context].add(lineno)
    return {context: sorted(lines) for context, lines in sorted(per_context.items())}


def _file_entry(
    state: _ProbeState,
    data: Any,
    known: dict[str, str],
    loops: dict[str, dict[str, Any]],
    rel: str,
    filename: str,
) -> dict[str, Any] | None:
    """Build one measured file's entry, or None when it is not a probe module."""
    if rel not in known:
        return None
    module = known[rel]
    transform_error = state.transform_errors.get(module)
    statements: set[int] = set()
    excluded: set[int] = set()
    try:
        statements, excluded = statement_lines(Path(filename))
    except Exception as error:  # noqa: BLE001 - surfaced in the report
        transform_error = f"cannot parse statements: {error}"
    kept = statements - excluded
    return {
        "statements": len(kept),
        "lines_by_context": _lines_by_context(data, filename, kept),
        "loops": _loop_entry(rel, loops),
        "transform_error": transform_error,
    }


def build_report(state: _ProbeState, session, exitstatus: int) -> dict[str, Any]:
    cov = state.cov
    if cov is None:
        raise RuntimeError("coverage probe was never configured")
    cov.stop()
    data = cov.get_data()
    known = _known_modules(state)
    loops = _loop_table(state, known)

    files: dict[str, Any] = {}
    for filename in data.measured_files():
        rel = _relative(filename)
        entry = _file_entry(state, data, known, loops, rel, filename)
        if entry is not None:
            files[rel] = entry

    reported = session.testscollected if hasattr(session, "testscollected") else 0
    return {
        "schema": "research.loop-coverage-report.v1",
        "src_prefix": state.prefix,
        "pytest": {
            "collected": reported,
            "failed": int(getattr(session, "testsfailed", 0)),
            "exitstatus": int(exitstatus),
        },
        "files": files,
    }


def pytest_sessionfinish(session, exitstatus) -> None:
    state = getattr(session.config, "_coverage_probe_state", None)
    if state is None:
        return
    report = build_report(state, session, exitstatus)
    state.json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
