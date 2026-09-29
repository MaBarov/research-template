"""AST visitor for the Python anti-pattern rules and its entry point.

Thumbnail: Raises the ``HNS0NN`` Python codes for one production source string.

Invariants & Expected State:
    Every rule is dispatched from a visitor method with the dotted call name
    resolved through :func:`~framework.gates.antipattern.python_checks._dotted_name`,
    and through its ``_chained_receiver_name`` when the receiver is a call or a
    binop, so ``Path(p).read_text()`` is judged like ``p.read_text()``.
    ``function_nodes`` mirrors ``function_stack`` for the rules that must inspect
    the enclosing body, both pushed by the same method that handles ``async
    def``, and the module-level ``dispatch_fallthrough`` pass runs once over the
    parsed tree in :func:`analyze_python`.  A finding is keyed by
    ``(id(node), code)`` so one node never reports the same code twice, and a
    rule that cannot see its shape stays silent rather than guessing.
"""

from __future__ import annotations

import ast

import framework.gates.antipattern.fallthrough_checks
import framework.gates.antipattern.python_checks
import framework.gates.antipattern.targets

_CACHE_CONTEXT_TOKENS = (
    "cache",
    "checkpoint",
    "ckpt",
    "basis",
    "artifact",
    "load",
    "restore",
    "resume",
    "read",
    "fetch",
    "snapshot",
    "manifest",
    "prediction",
    "payload",
)

_FORMAT_ERROR_NAMES = {
    "RuntimeError",
    "OSError",
    "EOFError",
    "UnpicklingError",
    "KeyError",
    "IndexError",
    "ValueError",
    "TypeError",
    "AttributeError",
    "JSONDecodeError",
}

_UNSAFE_DESERIALIZERS = {
    "pickle.load",
    "pickle.loads",
    "dill.load",
    "dill.loads",
    "marshal.load",
    "marshal.loads",
}

_SHELL_SINKS = {
    "os.system",
    "os.popen",
    "commands.getoutput",
    "commands.getstatusoutput",
}

_DISCARDED_SUBPROCESS = {"subprocess.run", "subprocess.call"}


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[framework.gates.antipattern.targets.Finding] = []
        self.function_stack: list[str] = []
        self.function_nodes: list[ast.AST] = []
        self.state_dict_validation_stack: list[bool] = []
        self.try_stack: list[ast.Try] = []
        self.loop_stack: list[ast.AST] = []
        self.discarded_call: ast.AST | None = None
        self._seen: set[tuple[int, str]] = set()

    def add(self, node: ast.AST, code: str, message: str) -> None:
        key = (id(node), code)
        if key in self._seen:
            return
        self._seen.add(key)
        self.findings.append(
            framework.gates.antipattern.targets.Finding(
                self.path, getattr(node, "lineno", 1), code, message
            )
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.function_nodes.append(node)
        self.state_dict_validation_stack.append(
            framework.gates.antipattern.python_checks._validates_state_dict_result(node)
        )
        self._check_degenerate_error_bar(node)
        self._check_optional_input_neutralized(node)
        self.generic_visit(node)
        self.state_dict_validation_stack.pop()
        self.function_nodes.pop()
        self.function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Try(self, node: ast.Try) -> None:
        self.try_stack.append(node)
        self.generic_visit(node)
        self.try_stack.pop()

    def _visit_loop(self, node: ast.AST) -> None:
        self.loop_stack.append(node)
        self.generic_visit(node)
        self.loop_stack.pop()

    visit_For = _visit_loop
    visit_AsyncFor = _visit_loop
    visit_While = _visit_loop

    def visit_Expr(self, node: ast.Expr) -> None:
        previous = self.discarded_call
        self.discarded_call = node.value if isinstance(node.value, ast.Call) else None
        self.generic_visit(node)
        self.discarded_call = previous

    def visit_Assert(self, node: ast.Assert) -> None:
        self.add(
            node,
            "HNS001",
            "runtime assert is removable under python -O; raise an explicit exception",
        )
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self._check_broad_handler(node)
        self._check_silent_handler(node)
        self._check_cache_handler(node)
        self._check_placeholder_fallthrough(node)
        self.generic_visit(node)

    def _check_placeholder_fallthrough(self, node: ast.ExceptHandler) -> None:
        function = self._enclosing_function()
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        placeholder = (
            framework.gates.antipattern.fallthrough_checks.placeholder_fallthrough(
                node, function
            )
        )
        if placeholder is None:
            return
        self.add(
            node,
            "HNS033",
            f"handler only logs and continues, so {placeholder!r} reaches the caller as "
            "if it were a real result; fail closed or record the failure",
        )

    def _check_broad_handler(self, node: ast.ExceptHandler) -> None:
        broad = (
            node.type is None
            or framework.gates.antipattern.python_checks._contains_name(
                node.type, {"Exception", "BaseException"}
            )
        )
        if broad and not framework.gates.antipattern.python_checks._reraises(node.body):
            self.add(
                node,
                "HNS005",
                "broad exception handler can hide a real failure; catch the expected exception",
            )

    def _check_silent_handler(self, node: ast.ExceptHandler) -> None:
        silent = framework.gates.antipattern.python_checks._contains_pass(
            node.body
        ) or framework.gates.antipattern.python_checks._contains_continue(node.body)
        if (
            not framework.gates.antipattern.python_checks._reraises(node.body)
            and silent
            and not framework.gates.antipattern.python_checks._candidate_scan_handler(
                node, self.try_stack, self.loop_stack
            )
        ):
            self.add(
                node,
                "HNS011",
                "exception handler contains pass and silently discards a failure",
            )

    def _check_cache_handler(self, node: ast.ExceptHandler) -> None:
        cache_context = any(
            token in name.lower()
            for name in self.function_stack
            for token in _CACHE_CONTEXT_TOKENS
        )
        deserialization_errors = (
            framework.gates.antipattern.python_checks._contains_name(
                node.type, _FORMAT_ERROR_NAMES
            )
        )
        if (
            cache_context
            and deserialization_errors
            and framework.gates.antipattern.python_checks._returns_none(node.body)
        ):
            self.add(
                node,
                "HNS006",
                "cache/deserialization failure is being treated as a cache miss; only a missing path may return None",
            )

    def visit_Return(self, node: ast.Return) -> None:
        if isinstance(node.value, ast.Dict):
            keys = {
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if "error" in keys:
                self.add(
                    node,
                    "HNS012",
                    "returning an error sentinel can make a failed run look successful; raise or mark the report incomplete",
                )
        self._check_provenance_return(node)
        self.generic_visit(node)

    def _check_provenance_literal(
        self, node: ast.AST, key: str, value: ast.AST
    ) -> None:
        literal = framework.gates.antipattern.python_checks._constant_string(value)
        if (
            literal is None
            or not framework.gates.antipattern.python_checks._is_sentinel_value(literal)
        ):
            return
        if not framework.gates.antipattern.python_checks._is_provenance_name(key):
            return
        self.add(
            node,
            "HNS013",
            f"provenance field {key!r} falls back to {literal!r}; fail closed instead of recording an unverifiable value",
        )

    def visit_Assign(self, node: ast.Assign) -> None:
        if (
            isinstance(node.value, ast.Call)
            and framework.gates.antipattern.python_checks._dotted_name(node.value.func)
            == "time.time"
        ):
            for target in node.targets:
                if isinstance(
                    target, ast.Name
                ) and framework.gates.antipattern.python_checks._is_timer_name(
                    target.id
                ):
                    self.add(
                        target,
                        "HNS014",
                        "wall-clock time.time() is not monotonic; use time.monotonic() for durations and deadlines",
                    )
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._check_provenance_literal(target, target.id, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            self._check_provenance_literal(node.target, node.target.id, node.value)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values, strict=True):
            key_name = (
                framework.gates.antipattern.python_checks._constant_string(key)
                if key is not None
                else None
            )
            if key_name is not None:
                self._check_provenance_literal(node, key_name, value)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if framework.gates.antipattern.python_checks._calls_wall_clock(node):
            self.add(
                node,
                "HNS014",
                "wall-clock time.time() is not monotonic; use time.monotonic() for durations and deadlines",
            )
        self._check_vacuous_population_rate(node)
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        if framework.gates.antipattern.python_checks._cuda_cpu_fallback(node):
            self.add(
                node,
                "HNS007",
                "CUDA-unavailable fallback to CPU hides a requested device failure; reject it explicitly",
            )
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        if framework.gates.antipattern.python_checks._cuda_cpu_fallback(node):
            self.add(
                node,
                "HNS007",
                "CUDA-unavailable fallback to CPU hides a requested device failure; reject it explicitly",
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = framework.gates.antipattern.python_checks._dotted_name(node.func)
        if name is None:
            name = framework.gates.antipattern.python_checks._chained_receiver_name(
                node.func
            )
        self._check_torch_load(node, name)
        self._check_zip(node, name)
        self._check_state_dict(node, name)
        self._check_deserializers(node, name)
        self._check_shell_sinks(node, name)
        self._check_subprocess_discard(node, name)
        self._check_subprocess_timeout(node, name)
        self._check_provenance_get(node, name)
        self._check_text_encoding(node, name)
        self._check_empty_cache_in_loop(node, name)
        self._check_naive_datetime(node, name)
        self._check_yaml_load(node, name)
        self.generic_visit(node)

    def _check_torch_load(self, node: ast.Call, name: str | None) -> None:
        if (
            name == "torch.load"
            and not framework.gates.antipattern.python_checks._keyword_is(
                node, "weights_only", True
            )
        ):
            self.add(
                node,
                "HNS002",
                "torch.load must pass weights_only=True; do not deserialize arbitrary objects",
            )

    def _check_zip(self, node: ast.Call, name: str | None) -> None:
        if name == "zip":
            strict = framework.gates.antipattern.python_checks._keyword(node, "strict")
            if len(node.args) >= 2 and not (
                isinstance(strict, ast.Constant) and strict.value is True
            ):
                self.add(
                    node,
                    "HNS003",
                    "zip with multiple inputs must use strict=True to reject truncation",
                )

    def _check_state_dict(self, node: ast.Call, name: str | None) -> None:
        if name is not None and name.endswith(".load_state_dict"):
            strict_false = framework.gates.antipattern.python_checks._keyword_is(
                node, "strict", False
            )
            state_dict_is_validated = bool(
                self.state_dict_validation_stack
                and self.state_dict_validation_stack[-1]
            )
            if strict_false and (
                not state_dict_is_validated or self.discarded_call is node
            ):
                self.add(
                    node,
                    "HNS004",
                    "load_state_dict(strict=False) can silently drop weights; validate missing and unexpected keys",
                )

    def _check_deserializers(self, node: ast.Call, name: str | None) -> None:
        if name in _UNSAFE_DESERIALIZERS:
            self.add(
                node,
                "HNS015",
                "pickle/marshal deserialization executes arbitrary objects; use torch.load(weights_only=True) or np.load",
            )
        if name in {"np.load", "numpy.load"}:
            allow_pickle = framework.gates.antipattern.python_checks._keyword(
                node, "allow_pickle"
            )
            if (
                allow_pickle is not None
                and not framework.gates.antipattern.python_checks._keyword_is(
                    node, "allow_pickle", False
                )
            ):
                self.add(
                    node,
                    "HNS015",
                    "np.load(allow_pickle=True) executes arbitrary objects; store plain arrays instead",
                )
        if name in {"eval", "exec"}:
            self.add(
                node,
                "HNS016",
                "dynamic code execution on production input; use ast.literal_eval for data",
            )

    def _check_shell_sinks(self, node: ast.Call, name: str | None) -> None:
        shell = framework.gates.antipattern.python_checks._keyword(node, "shell")
        if (
            shell is not None
            and name is not None
            and name.startswith("subprocess.")
            and not framework.gates.antipattern.python_checks._keyword_is(
                node, "shell", False
            )
        ):
            self.add(
                node,
                "HNS017",
                "subprocess(shell=True) hands the command to a shell; pass an argv list",
            )
        if name in _SHELL_SINKS:
            self.add(
                node,
                "HNS017",
                "shell execution sink builds a command string; pass an argv list",
            )

    def _check_subprocess_discard(self, node: ast.Call, name: str | None) -> None:
        if (
            name in _DISCARDED_SUBPROCESS
            and self.discarded_call is node
            and not framework.gates.antipattern.python_checks._keyword_is(
                node, "check", True
            )
        ):
            self.add(
                node,
                "HNS018",
                "subprocess failure is discarded; pass check=True or inspect the return code",
            )

    def _check_provenance_get(self, node: ast.Call, name: str | None) -> None:
        if name is not None and name.endswith(".get") and len(node.args) >= 2:
            key_name = framework.gates.antipattern.python_checks._constant_string(
                node.args[0]
            )
            if key_name is not None:
                self._check_provenance_literal(node, key_name, node.args[1])

    def _check_text_encoding(self, node: ast.Call, name: str | None) -> None:
        if framework.gates.antipattern.python_checks._is_text_open(node, name):
            self.add(
                node,
                "HNS021",
                "text I/O without explicit encoding uses system locale; pass encoding='utf-8'",
            )

    def _check_empty_cache_in_loop(self, node: ast.Call, name: str | None) -> None:
        if bool(
            self.loop_stack
        ) and framework.gates.antipattern.python_checks._is_empty_cache(name):
            self.add(
                node,
                "HNS022",
                "torch.cuda.empty_cache() inside loop destroys GPU allocator throughput; remove it",
            )

    def _check_naive_datetime(self, node: ast.Call, name: str | None) -> None:
        if framework.gates.antipattern.python_checks._is_naive_datetime(node, name):
            self.add(
                node,
                "HNS023",
                "naive datetime without timezone diverges across cluster nodes; use datetime.now(timezone.utc)",
            )

    def _check_yaml_load(self, node: ast.Call, name: str | None) -> None:
        if framework.gates.antipattern.python_checks._is_insecure_yaml_load(node, name):
            self.add(
                node,
                "HNS024",
                "yaml.load without safe Loader executes arbitrary code; use yaml.safe_load",
            )

    def _check_subprocess_timeout(self, node: ast.Call, name: str | None) -> None:
        if not framework.gates.antipattern.python_checks._is_blocking_subprocess(name):
            return
        if (
            framework.gates.antipattern.python_checks._keyword(node, "timeout")
            is not None
        ):
            return
        self.add(
            node,
            "HNS027",
            "blocking subprocess call without timeout= can hang a job forever on a wedged "
            "host or filesystem; pass timeout= and handle TimeoutExpired",
        )

    def _check_vacuous_population_rate(self, node: ast.BinOp) -> None:
        if not isinstance(node.op, ast.Div):
            return
        population = (
            framework.gates.antipattern.python_checks._vacuous_population_divisor(
                node.right
            )
        )
        if population is None:
            return
        if framework.gates.antipattern.python_checks._names_collection(
            node.left, population
        ):
            return
        if framework.gates.antipattern.python_checks._rejects_empty_population(
            self._enclosing_function(), population
        ):
            return
        if framework.gates.antipattern.python_checks._consumed_only_in_population_loop(
            self._enclosing_function(), node, population
        ):
            return
        self.add(
            node,
            "HNS030",
            f"rate divides by max(len({population}), 1): an empty population reports a "
            "number instead of failing; reject the empty case explicitly",
        )

    def _check_degenerate_error_bar(self, node: ast.FunctionDef) -> None:
        guard = framework.gates.antipattern.python_checks._degenerate_error_bar(node)
        if guard is None:
            return
        self.add(
            guard,
            "HNS031",
            f"error bar {node.name!r} collapses to zero under two samples; omit the bar or "
            "refuse the verdict instead of reporting perfect certainty",
        )

    def _check_optional_input_neutralized(self, node: ast.FunctionDef) -> None:
        hit = framework.gates.antipattern.fallthrough_checks.optional_input_neutralized(
            node
        )
        if hit is None:
            return
        branch, name = hit
        self.add(
            branch,
            "HNS034",
            f"optional input {name!r} is neutralized to a valid-but-empty value when "
            "absent; require it so the constraint cannot silently vanish",
        )

    def _check_provenance_return(self, node: ast.Return) -> None:
        literal = framework.gates.antipattern.python_checks._provenance_sentinel(
            node.value
        )
        if literal is None:
            return
        name = self.function_stack[-1] if self.function_stack else ""
        if not framework.gates.antipattern.python_checks._is_provenance_helper_name(
            name
        ):
            return
        self.add(
            node,
            "HNS032",
            f"provenance helper {name!r} falls back to {literal!r}; fail closed instead of "
            "labelling the run with an unverifiable value",
        )

    def _enclosing_function(self) -> ast.AST | None:
        return self.function_nodes[-1] if self.function_nodes else None


def analyze_python(
    source: str, path: str
) -> list[framework.gates.antipattern.targets.Finding]:
    """Return findings for one Python source string."""

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as error:
        return [
            framework.gates.antipattern.targets.Finding(
                path,
                error.lineno or 1,
                "HNS000",
                f"cannot parse production Python: {error.msg}",
            )
        ]
    visitor = _PythonVisitor(path)
    visitor.visit(tree)
    hits = framework.gates.antipattern.fallthrough_checks.dispatch_fallthrough(tree)
    for node, message in hits:
        visitor.add(node, "HNS037", message)
    return visitor.findings
