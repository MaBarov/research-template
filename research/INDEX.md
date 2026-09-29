# Research Sub-Index: `research`

> [!NOTE]
> Sub-index for the `research` package hierarchy. Use the line ranges below to load specific sections directly into context.

**Repository Statistics**: 3 modules | 2 classes | 11 public functions.

## Table of Contents

- [`research/params`](#package-researchparams) (lines 15–42) — *Parameter registry and its runtime accessors (the worked example of the params rule).*
- [`research/probe`](#package-researchprobe) (lines 43–53) — *Example production package: a dependency-free plan builder.*

---

## Package `research/params` — *Parameter registry and its runtime accessors (the worked example of the params rule).*

- [`research/params/registry.py`](research/params/registry.py) (99 lines)
  * *Module Purpose*: Canonical parameter registry: one env var, one default, one name per parameter.
  * [`class Parameter`](research/params/registry.py#L31-L51)
    * *Contract*: One registered parameter: canonical name, default and drift surface.
  * [`by_name(name: str) -> Parameter`](research/params/registry.py#L90-L93)
    * *Contract*: Return the row registered under ``name``; an unknown name raises.
  * [`by_env(env: str) -> Parameter | None`](research/params/registry.py#L96-L99)
    * *Contract*: Return the row that owns ``env``, or ``None`` when nothing registers it.

- [`research/params/resolve.py`](research/params/resolve.py) (64 lines)
  * *Module Purpose*: Runtime accessors for the canonical registry: the only way code reads a value.
  * [`default(name: str) -> str`](research/params/resolve.py#L22-L25)
    * *Contract*: Return the registry default of ``name``, ignoring the environment.
  * [`ambient(name: str) -> str | None`](research/params/resolve.py#L28-L34)
    * *Contract*: Return the raw environment value of ``name``, or ``None`` when unset.
  * [`str_param(name: str) -> str`](research/params/resolve.py#L37-L40)
    * *Contract*: Return the string value of ``name``: environment first, default second.
  * [`int_param(name: str) -> int`](research/params/resolve.py#L43-L46)
    * *Contract*: Return the integer value of ``name``.
  * [`float_param(name: str) -> float`](research/params/resolve.py#L49-L52)
    * *Contract*: Return the float value of ``name``.
  * [`path_param(name: str) -> Path`](research/params/resolve.py#L55-L58)
    * *Contract*: Return the filesystem path value of ``name``, expanded.
  * [`seed() -> int`](research/params/resolve.py#L61-L64)
    * *Contract*: Return the registered run seed.

## Package `research/probe` — *Example production package: a dependency-free plan builder.*

- [`research/probe/plan.py`](research/probe/plan.py) (66 lines)
  * *Module Purpose*: Worked example of a production module: a deterministic plan builder.
  * [`class Step`](research/probe/plan.py#L26-L30)
    * *Contract*: One planned step: its index and the seed-derived weight.
  * [`build_plan(steps: int | None) -> tuple[Step, ...]`](research/probe/plan.py#L33-L38)
    * *Contract*: Return the plan for ``steps``, defaulting to the registered step count.
  * [`main(argv: Sequence[str] | None) -> int`](research/probe/plan.py#L55-L62)
    * *Contract*: Print the plan's status line and return the process exit code.

