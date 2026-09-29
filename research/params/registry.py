"""Canonical parameter registry: one env var, one default, one name per parameter.

Invariants & Expected State:
- Stdlib-only import surface: the parameter gate loads this module by file path,
  so nothing here may pull a heavy dependency onto the import path.
- One row per logical parameter and one canonical env var per row. Superseded
  spellings live in ``aliases`` and the gate rejects them on sight (HNS038).
- ``default`` is the value the project already runs with. A deliberate
  non-default value is an explicit statement at the call site (a literal in a
  recipe tuple, or ``: "${VAR:=value}"`` in shell), never a second default here
  (HNS039).
- ``MODEL_SNAPSHOTS`` holds every pinned model revision, keyed by model id; it is
  empty when the project pins none. ``BANNED_LITERALS`` maps a copied literal to
  the parameter that owns it (HNS040).
- ``accessors`` names the ``resolve`` functions that serve a row; an empty tuple
  means the row is read through a generic accessor keyed by its ``name`` or
  through one of its ``constants``. The usage gate (HNS042) reports a row that no
  production module reads at all.
- ``implementations`` lists the modules that dispatch on this row's ``default``;
  each of them must compare that default text explicitly (HNS043).
- Values resolve at call time through ``research.params.resolve``; nothing in this
  table may be read from the environment anywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Parameter:
    """One registered parameter: canonical name, default and drift surface.

    ``env`` is the only spelling of the variable; ``aliases`` records the
    spellings that must never come back. ``flags``/``attrs``/``constants`` are the
    textual surfaces the gate scans for restated defaults, and ``owners`` lists
    repository paths whose presence the registry asserts.
    """

    name: str
    env: str | None
    default: str
    kind: str
    aliases: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    attrs: tuple[str, ...] = ()
    constants: tuple[str, ...] = ()
    literals: tuple[str, ...] = ()
    owners: tuple[str, ...] | None = None
    accessors: tuple[str, ...] = ()
    implementations: tuple[str, ...] = ()


PARAMETERS: tuple[Parameter, ...] = (
    Parameter(
        name="seed",
        env="RESEARCH_SEED",
        default="0",
        kind="int",
        aliases=("RESEARCH_RANDOM_SEED",),
        flags=("--seed",),
        attrs=("seed",),
        accessors=("seed",),
    ),
    Parameter(
        name="steps",
        env="RESEARCH_STEPS",
        default="3",
        kind="int",
        flags=("--steps",),
    ),
)

#: Superseded env spellings, mapped to the canonical variable. Empty when a
#: project has never renamed a parameter; an entry here is a permanent ban.
ALIAS_TO_ENV: dict[str, str] = {"RESEARCH_RANDOM_SEED": "RESEARCH_SEED"}

#: Pinned model revisions, keyed by model id (``/snapshots/<revision>`` path or
#: ``repo@revision``): empty when the project pins none.
MODEL_SNAPSHOTS: dict[str, str] = {}

#: Literals that must be read from the registry instead of copied, mapped to the
#: parameter that owns them (for example a dataset path or a frozen threshold).
BANNED_LITERALS: dict[str, str] = {}

_BY_NAME: dict[str, Parameter] = {p.name: p for p in PARAMETERS}
_BY_ENV: dict[str, Parameter] = {p.env: p for p in PARAMETERS if p.env}


def by_name(name: str) -> Parameter:
    """Return the row registered under ``name``; an unknown name raises."""

    return _BY_NAME[name]


def by_env(env: str) -> Parameter | None:
    """Return the row that owns ``env``, or ``None`` when nothing registers it."""

    return _BY_ENV.get(env)
