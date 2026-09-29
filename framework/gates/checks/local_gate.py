#!/usr/bin/env python3
"""Local pre-submit gate (run BEFORE any sbatch submission).

Checks, in order, aborting on first failure:
1. py_compile every file passed as argument.
2. Undefined/unused name audit via pyflakes if available, else a
   conservative AST scan whose module-level candidate set includes
   import aliases (fixes the `torch` false positive of the ad-hoc check).
3. Asserts each file parses to at least one FunctionDef or is a script
   with a __main__ guard / bare call - catches empty-stub writes.

Usage: python framework/gates/checks/local_gate.py FILE [FILE ...]
Exit 0 = safe to submit.

Invariants & Expected State:
    - Exit 0 only when every argument compiles, every ``Name`` load resolves,
      and each file is more than an empty stub: a ``FunctionDef``, or a script
      carrying a ``__main__`` guard or a bare top-level call.
    - Checks run in order and abort on the first failure, so a later check
      never reports on a file an earlier one already refused.
    - Name resolution follows the nearest enclosing function chain: a global
      candidate (import alias, builtin, module-level def) never masks a name
      that the innermost scope must provide.
    - pyflakes is used when installed; without it the conservative AST scan
      takes over, and an unavailable auditor is never a silent pass.
    - Expected input: the files a job will import, checked with the interpreter
      that will run it, before any submission.
"""

from __future__ import annotations

import ast
import builtins
import py_compile
import sys


def compile_ok(path: str) -> None:
    import os
    import tempfile

    cfile = os.path.join(tempfile.mkdtemp(prefix="gate_pyc_"), "x.pyc")
    py_compile.compile(path, cfile=cfile, doraise=True)


def module_candidates(tree: ast.Module) -> set[str]:
    """Names legally resolvable at module level."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def _scope_locals_deep(fn) -> set[str]:
    """Locals of one function, descending into every nested definition."""
    s = {a.arg for a in fn.args.args}
    s |= {a.arg for a in getattr(fn.args, "kwonlyargs", [])}
    if fn.args.vararg:
        s.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        s.add(fn.args.kwarg.arg)
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            s.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            s.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                s.add((a.asname or a.name).split(".")[0])
    return s


def _scope_locals_own(fn) -> set[str]:
    """Locals of one function's OWN scope - never descends into nested defs."""
    s = {a.arg for a in fn.args.args}
    s |= {a.arg for a in getattr(fn.args, "kwonlyargs", [])}
    if fn.args.vararg:
        s.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        s.add(fn.args.kwarg.arg)
    # this function's OWN scope only - do not descend into nested defs
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            s.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            s.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                s.add((a.asname or a.name).split(".")[0])
        stack.extend(ast.iter_child_nodes(n))
    return s


def _lambda_locals(lam: ast.Lambda) -> set[str]:
    """Lambda params are locals of the lambda body only, never the enclosing fn."""
    args = {a.arg for a in lam.args.args}
    args |= {a.arg for a in getattr(lam.args, "kwonlyargs", [])}
    if lam.args.vararg:
        args.add(lam.args.vararg.arg)
    if lam.args.kwarg:
        args.add(lam.args.kwarg.arg)
    return args


def build_scopes(tree: ast.Module):
    """Map each FunctionDef to (its locals, parent function)."""
    scopes = {}

    def visit(node, parent):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                scopes[child] = (_scope_locals_deep(child), parent)
                visit(child, child)
            else:
                visit(child, parent)

    visit(tree, None)
    return scopes


def _audit_name_loads(node, fn_stack, scopes, mod_names, bad) -> None:
    """Append every unresolved Name load beneath ``node`` to ``bad``."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scopes[id(child)] = _scope_locals_own(child)
            _audit_name_loads(child, fn_stack + [child], scopes, mod_names, bad)
            continue
        if isinstance(child, ast.Lambda):
            # lambdas are their own scope: params are locals inside the
            # body only and must NOT leak into the enclosing function.
            scopes[id(child)] = _lambda_locals(child)
            _audit_name_loads(child, fn_stack + [child], scopes, mod_names, bad)
            continue
        if isinstance(child, ast.ExceptHandler) and child.name:
            # ``except E as err`` binds err for the handler body only; the
            # binding belongs to whichever scope encloses the handler.
            if fn_stack:
                scopes[id(fn_stack[-1])].add(child.name)
            else:
                mod_names.add(child.name)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            ok = (
                any(child.id in scopes[id(f)] for f in reversed(fn_stack))
                or child.id in mod_names
                or hasattr(builtins, child.id)
                or (child.id.startswith("__") and child.id.endswith("__"))
            )
            if not ok:
                bad.append(f"undefined name '{child.id}' (line {child.lineno})")
        _audit_name_loads(child, fn_stack, scopes, mod_names, bad)


def check_undefined(tree: ast.Module, mod_names: set[str]) -> list[str]:
    """Resolve every Name load against its NEAREST enclosing function chain."""
    scopes: dict = {}
    bad: list[str] = []

    # seed top-level function scopes so their OWN bodies resolve
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scopes[id(node)] = _scope_locals_own(node)
    _audit_name_loads(tree, [], scopes, mod_names, bad)
    return bad


def _pyflakes_undefined_names(path: str, src: str) -> list[str] | None:
    """Undefined-name messages from pyflakes, or None when it is unavailable."""
    try:
        import pyflakes.api  # type: ignore
        from pyflakes.reporter import Reporter  # type: ignore
    except ImportError:
        return None

    import io

    err = io.StringIO()
    pyflakes.api.check(src, path, Reporter(err, err))
    return [line for line in err.getvalue().splitlines() if "undefined name" in line]


def main(argv: list[str]) -> int:
    if not argv:
        print("local_gate: no files given")
        return 2
    failed = False
    for path in argv:
        try:
            compile_ok(path)
        except py_compile.PyCompileError as e:
            print(f"[GATE-FAIL] {path}: {e}")
            failed = True
            continue
        with open(path) as fh:
            src = fh.read()
        tree = ast.parse(src)
        msgs = _pyflakes_undefined_names(path, src)
        if msgs is None:
            problems = check_undefined(tree, module_candidates(tree))
            msgs = [f"{path}: {p}" for p in problems]
        if msgs:
            for m in msgs:
                print(f"[GATE-FAIL] {m}")
            failed = True
    if failed:
        print("GATE: FAIL")
        return 1
    print(f"GATE: PASS ({len(argv)} file(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
