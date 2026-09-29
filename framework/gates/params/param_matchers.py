"""Source-text matchers for the canonical parameter registry (HNS038-HNS041).

Invariants & Expected State:
    - Every matcher takes source text plus its repository-relative path and returns
      ``Finding`` objects; no matcher touches the filesystem.
    - An assignment whose value equals the registry default is silent; a drifted
      default, a superseded alias or a copied banned literal is a finding.
    - Fail closed: unparseable input yields a finding, never silence.
    - The derived registry tables are read through ``param_checks`` at call time, so
      a test that patches a table is honoured.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from framework.gates.antipattern.targets import Finding
from framework.gates.params import param_checks
from framework.gates.params.argparse_calls import argument_aliases, is_flag_call
from framework.gates.params.param_checks import _rows_for


def source_findings(source: str, path: str) -> list[Finding]:
    """Dispatch one source text to its language matcher."""

    finder = python_findings if Path(path).suffix == ".py" else shell_findings
    return finder(source, path)


def shell_findings(source: str, path: str) -> list[Finding]:
    """Return every HNS038-HNS041 finding of one shell source text."""

    findings = alias_findings(source, path)
    findings.extend(_shell_expansion_findings(source, path))
    findings.extend(_shell_literal_findings(source, path))
    return _dedupe(findings)


def _shell_literal_findings(source: str, path: str) -> list[Finding]:
    """Return HNS040 findings for banned literals outside deviation statements."""

    findings: list[Finding] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        for literal, name in param_checks._LITERAL_ROWS:
            if literal not in line:
                continue
            parameter = param_checks.REGISTRY.by_name(name)
            if _shell_deviation(line, parameter):
                continue
            findings.append(
                Finding(
                    path, line_number, "HNS040", f"{name}: copied literal {literal}"
                )
            )
    return findings


def _shell_expansion_findings(source: str, path: str) -> list[Finding]:
    """Return HNS039 findings for shell fallback defaults of a registered param."""

    findings: list[Finding] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        for match in param_checks._SHELL_EXPANSION.finditer(line):
            env, literal = match.group(1), _unquote(match.group(2).strip())
            parameter = param_checks._ENV_INDEX.get(env)
            if parameter is None or not literal:
                continue
            if _same_value(literal, parameter.default):
                continue
            findings.append(
                Finding(
                    path,
                    line_number,
                    "HNS039",
                    f"{parameter.name}: {env} fallback {literal} differs from the "
                    f'registry default {parameter.default}; write : "${{{env}:={literal}}}"',
                )
            )
    return findings


def _shell_deviation(line: str, parameter: Any) -> bool:
    """Return whether ``line`` is the sanctioned deviation point of ``parameter``."""

    env = parameter.env
    if not env:
        return False
    if re.search(r"\$\{" + re.escape(env) + ":=", line):
        return True
    return any(
        match.group(3) == env for match in param_checks._ENV_ASSIGN.finditer(line)
    )


def python_findings(source: str, path: str) -> list[Finding]:
    """Return every HNS038-HNS041 finding of one Python source text."""

    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError) as error:
        line = getattr(error, "lineno", None) or 1
        return [
            Finding(path, line, "HNS041", f"registry: cannot parse source: {error}")
        ]
    findings = alias_findings(source, path) + _python_literal_findings(tree, path)
    aliases = argument_aliases(tree)
    for node in ast.walk(tree):
        findings.extend(_env_read_findings(node, path))
        findings.extend(_env_helper_findings(node, path))
        findings.extend(_add_argument_findings(node, path, aliases))
        findings.extend(_attr_default_findings(node, path))
        findings.extend(_constant_findings(node, path))
        findings.extend(_pair_findings(node, path))
    return _dedupe(findings)


def _pair_findings(node: ast.AST, path: str) -> list[Finding]:
    """Return HNS039 findings for flag/value pairs that copy a registered default."""

    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    elements = node.elts
    findings: list[Finding] = []
    for index in range(len(elements) - 1):
        flag = elements[index]
        if not (
            isinstance(flag, ast.Constant)
            and isinstance(flag.value, str)
            and flag.value.startswith("-")
        ):
            continue
        text = _literal_text(elements[index + 1])
        if text is None:
            continue
        for parameter in _rows_for(param_checks._FLAG_ROWS, flag.value, path):
            if _same_value(text, parameter.default):
                findings.append(
                    Finding(
                        path,
                        flag.lineno,
                        "HNS039",
                        f"{parameter.name}: {flag.value} restates the default ({text}); "
                        "read research/params",
                    )
                )
    return findings


def _constant_findings(node: ast.AST, path: str) -> list[Finding]:
    """Return HNS039 findings for assignments to a registered constant name."""

    value = getattr(node, "value", None)
    if value is None or not isinstance(value, ast.expr):
        return []
    if not _is_literal_expression(value):
        return []
    findings: list[Finding] = []
    for name in _assigned_names(node):
        for parameter in _rows_for(param_checks._CONSTANT_ROWS, name, path):
            findings.append(
                Finding(
                    path,
                    node.lineno,
                    "HNS039",
                    f"{parameter.name}: {name} restates the default; read "
                    "research/params",
                )
            )
    return findings


def _is_literal_expression(node: ast.expr) -> bool:
    """Return whether ``node`` restates a value instead of reading the registry."""

    if _literal_text(node) is not None:
        return True
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in {"Path", "PosixPath"} and all(
            _literal_text(argument) is not None for argument in node.args
        )
    if isinstance(node, ast.BinOp):
        return _is_literal_expression(node.left) and _is_literal_expression(node.right)
    return False


def _assigned_names(node: ast.AST) -> list[str]:
    """Return the plain names assigned by one assignment statement."""

    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            names.extend(
                element.id for element in target.elts if isinstance(element, ast.Name)
            )
    return names


def _attr_default_findings(node: ast.AST, path: str) -> list[Finding]:
    """Return HNS039 findings for ``getattr``/``dict.get`` defaults of a param."""

    if not isinstance(node, ast.Call):
        return []
    func, args = node.func, node.args
    if isinstance(func, ast.Name) and func.id == "getattr" and len(args) >= 2:
        operands = (args[1], args[2] if len(args) > 2 else None)
    elif isinstance(func, ast.Attribute) and func.attr == "get" and len(args) >= 1:
        operands = (args[0], args[1] if len(args) > 1 else None)
    else:
        return []
    attribute, default = operands
    if not (isinstance(attribute, ast.Constant) and isinstance(attribute.value, str)):
        return []
    text = _literal_text(default) if default is not None else None
    if text is None:
        return []
    return [
        Finding(
            path,
            node.lineno,
            "HNS039",
            f"{parameter.name}: {attribute.value} restates default {text}; read "
            "research/params",
        )
        for parameter in _rows_for(param_checks._ATTR_ROWS, attribute.value, path)
    ]


def _add_argument_findings(
    node: ast.AST, path: str, aliases: frozenset[str]
) -> list[Finding]:
    """Return HNS039 findings for argparse defaults of a registered flag."""

    if not is_flag_call(node, aliases):
        return []
    word = _keyword(node, "default")
    if word is None:
        return []
    text = _literal_text(word.value)
    if text is None:
        return []
    findings: list[Finding] = []
    for argument in node.args:
        if not (isinstance(argument, ast.Constant) and isinstance(argument.value, str)):
            continue
        for parameter in _rows_for(param_checks._FLAG_ROWS, argument.value, path):
            findings.append(
                Finding(
                    path,
                    node.lineno,
                    "HNS039",
                    f"{parameter.name}: {argument.value} restates default {text} as an "
                    "argparse default; read research/params",
                )
            )
    return findings


def _keyword(node: ast.Call, name: str) -> ast.keyword | None:
    """Return the keyword argument ``name`` of ``call``, if present."""

    return next((word for word in node.keywords if word.arg == name), None)


def _env_helper_findings(node: ast.AST, path: str) -> list[Finding]:
    """Return HNS039 findings for ``_env_*(ENV, ...)`` helper reads."""

    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
        return []
    if not node.func.id.startswith("_env_") or not node.args:
        return []
    first = node.args[0]
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return []
    parameter = param_checks._ENV_INDEX.get(first.value)
    if parameter is None:
        return []
    return [
        Finding(
            path,
            node.lineno,
            "HNS039",
            f"{parameter.name}: {first.value} read via {node.func.id}; use "
            "research/params",
        )
    ]


def _env_read_findings(node: ast.AST, path: str) -> list[Finding]:
    """Return HNS039 findings for direct reads of a registered env var."""

    found = _environ_env(node)
    if found is None:
        return []
    env, _default = found
    parameter = param_checks._ENV_INDEX.get(env)
    if parameter is None:
        return []
    return [
        Finding(
            path,
            node.lineno,
            "HNS039",
            f"{parameter.name}: {env} read directly; use research/params",
        )
    ]


def _environ_env(node: ast.AST) -> tuple[str, ast.expr | None] | None:
    """Return ``(env, default)`` for an ``os.environ``/``os.getenv`` read."""

    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        target = node.value
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "environ"
            and isinstance(node.slice.value, str)
        ):
            return node.slice.value, None
        return None
    if isinstance(node, ast.Call) and node.args:
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            return None
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "get":
            holder = func.value
            if isinstance(holder, ast.Attribute) and holder.attr == "environ":
                default = node.args[1] if len(node.args) > 1 else None
                return first.value, default
        is_getenv = (isinstance(func, ast.Name) and func.id == "getenv") or (
            isinstance(func, ast.Attribute) and func.attr == "getenv"
        )
        if is_getenv:
            default = node.args[1] if len(node.args) > 1 else None
            return first.value, default
    return None


def _python_literal_findings(tree: ast.AST, path: str) -> list[Finding]:
    """Return HNS040 findings for string literals outside docstrings."""

    docstrings = _docstring_values(tree)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            findings.extend(_literal_matches(node.value, node.lineno, path))
    return findings


def _literal_matches(text: str, line: int, path: str) -> list[Finding]:
    """Return HNS040 findings for every banned literal inside ``text``."""

    return [
        Finding(
            path,
            line,
            "HNS040",
            f"{name}: copied literal {literal}; read research/params",
        )
        for literal, name in param_checks._LITERAL_ROWS
        if literal in text
    ]


def _docstring_values(tree: ast.AST) -> set[int]:
    """Return the ``id`` of every docstring constant in ``tree``."""

    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, holders) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                found.add(id(first.value))
    return found


def alias_findings(source: str, path: str) -> list[Finding]:
    """Return one HNS038 finding per superseded alias occurrence."""

    findings: list[Finding] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        for pattern, alias, env in param_checks._ALIAS_PATTERNS:
            if pattern.search(line):
                findings.append(
                    Finding(
                        path,
                        line_number,
                        "HNS038",
                        f"{env}: alias {alias} is superseded by {env}",
                    )
                )
    return findings


def _dedupe(findings: list[Finding]) -> list[Finding]:
    """Collapse repeated findings of one line, code and parameter."""

    unique: dict[tuple[str, int, str, str], Finding] = {}
    for finding in findings:
        key = (
            finding.path,
            finding.line,
            finding.code,
            finding.message.split(":", 1)[0],
        )
        unique.setdefault(key, finding)
    return [unique[key] for key in sorted(unique)]


def _literal_text(node: ast.expr) -> str | None:
    """Return the text of a comparable literal node, or ``None``."""

    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
        return str(node.value)
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        return f"-{node.operand.value}"
    return None


def _same_value(literal: str, default: str) -> bool:
    """Compare two literal texts numerically when both parse, else textually."""

    try:
        return float(literal) == float(default)
    except ValueError:
        return literal == default


def _unquote(text: str) -> str:
    """Return ``text`` without one layer of matching shell quotes."""

    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text
