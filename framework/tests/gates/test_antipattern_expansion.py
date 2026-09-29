"""Acceptance and evidence tests for the anti-pattern gate expansion (HNS027+).

Thumbnail: Proves the expanded rules fire on the shapes they are defined over.

Invariants & Expected State:
    Detection cases feed synthetic sources to the gate's own analyzer, so a case
    for a missing rule fails before the rule exists - this file is the work list
    for the expansion.  Guard cases pin the near-misses the survey reviewed: a
    rule that starts firing on them is a regression, not a win.  The census case
    asserts the scan covers this repository's production tree, so no count can
    drift with whatever the tree happens to contain.
"""

from __future__ import annotations

import ast

import pytest

from framework.gates.antipattern import python_checks, targets
from framework.gates.antipattern.python_visitor import analyze_python

EXPANSION_CODES = frozenset(
    {
        "HNS021",
        "HNS027",
        "HNS030",
        "HNS031",
        "HNS032",
        "HNS033",
        "HNS034",
        "HNS037",
    }
)


def codes(source: str, path: str = "research/probe.py") -> set[str]:
    """Return the gate's codes for one source string."""
    return {finding.code for finding in analyze_python(source, path)}


def function_node(source: str, name: str) -> ast.FunctionDef:
    """Return the named function of ``source``, or raise when it is absent."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name!r} is gone; the case citation drifted")


def test_stderr_rejects_the_collapsed_error_bar() -> None:
    """``_stderr`` returns NaN under two samples instead of a zero-width bar (HNS031).

    The rule targets a small-sample guard that returns ``0.0``; returning ``NaN``
    is the documented repair, so the rule must stay quiet on it.
    """
    source = (
        "def _stderr(values):\n"
        "    if len(values) < 2:\n"
        '        return float("nan")\n'
        "    return 1.0\n"
    )
    assert python_checks._degenerate_error_bar(function_node(source, "_stderr")) is None
    assert "HNS031" not in codes(source)


def test_checkpoint_hash_reports_none_without_a_basis() -> None:
    """A provenance helper falling back to the literal ``"none"`` (HNS032)."""
    source = (
        "def compute_u_safe_hash(u_safe):\n"
        "    if u_safe is None:\n"
        '        return "none"\n'
        "    return digest(u_safe)\n"
    )
    assert "HNS032" in codes(source)


ACCEPTANCE_CASES = (
    (
        "HNS021",
        "from pathlib import Path\n\ndef read(p):\n    return Path(p).read_text()\n",
    ),
    (
        "HNS021",
        "from pathlib import Path\n\ndef write(p):\n    (p / 'x.json').write_text('{}')\n",
    ),
    (
        "HNS021",
        "from pathlib import Path\n\ndef open_it(p):\n    return Path(p).open('r')\n",
    ),
    (
        "HNS027",
        "import subprocess\n\ndef run():\n    subprocess.run(['git', 'status'])\n",
    ),
    (
        "HNS027",
        "import subprocess\n\ndef out():\n    return subprocess.check_output(['ls'])\n",
    ),
    (
        "HNS030",
        "def ratio(rows, total):\n    return 1 - len(rows) / max(len(total), 1)\n",
    ),
    (
        "HNS031",
        "def _stderr(values):\n    if len(values) < 2:\n        return 0.0\n    return 1.0\n",
    ),
    (
        "HNS032",
        "def _git_head():\n    try:\n        return read()\n    except OSError:\n        return 'unknown'\n",
    ),
    (
        "HNS033",
        (
            "def _load(device):\n    model = None\n    try:\n        model = build(device)\n"
            "    except (ImportError, OSError) as error:\n        print(f'not loaded: {error}')\n"
            "    return model\n"
        ),
    ),
    (
        "HNS033",
        (
            "def _rows(path):\n    rows = []\n    try:\n        rows = read(path)\n"
            "    except OSError as error:\n        logger.error('no rows: %s', error)\n"
            "    return rows\n"
        ),
    ),
)


@pytest.mark.parametrize("code, source", ACCEPTANCE_CASES)
def test_expansion_detects_the_cited_shape(code: str, source: str) -> None:
    """Each expansion code fires on the minimal shape it is defined over."""
    assert code in codes(source)


GUARD_CASES = (
    "from pathlib import Path\n\ndef read(p):\n    return Path(p).read_text(encoding='utf-8')\n",
    "from pathlib import Path\n\ndef open_it(p):\n    return Path(p).open('rb')\n",
    "import subprocess\n\ndef run():\n    subprocess.run(['git', 'status'], timeout=30)\n",
    "import subprocess\n\ndef spawn():\n    subprocess.Popen(['sleep', '1'])\n",
    "def mean(values):\n    return sum(values) / max(len(values), 1)\n",
    (
        "def ratio(rows, total):\n    if not total:\n        raise ValueError('empty')\n"
        "    return 1 - len(rows) / max(len(total), 1)\n"
    ),
    (
        "def stream(prompts):\n    share = 1.0 / max(len(prompts), 1)\n"
        "    for prompt in prompts:\n        use(share, prompt)\n"
    ),
    (
        "def _git_head():\n    try:\n        return read()\n"
        "    except OSError as error:\n        raise RuntimeError('no git') from error\n"
    ),
    ("from PIL import Image\n\ndef load(path):\n    return Image.open(path)\n"),
    (
        "from PIL import ImageFile\n\ndef probe(path):\n"
        "    return ImageFile.open(path).size\n"
    ),
    (
        "def _load(device):\n    model = None\n    try:\n        model = build(device)\n"
        "    except OSError as error:\n        failures.append(str(error))\n"
        "    return model\n"
    ),
    (
        "def _load(device):\n    model = None\n    try:\n        model = build(device)\n"
        "    except OSError as error:\n        raise RuntimeError('required') from error\n"
        "    return model\n"
    ),
    (
        "def _load(path):\n    payload = None\n    try:\n        payload = read(path)\n"
        "    except FileNotFoundError as error:\n        logger.info('miss: %s', error)\n"
        "    return payload\n"
    ),
    "model = None\ntry:\n    model = build()\nexcept OSError as error:\n    print(error)\n",
    (
        "def _load(device):\n    model = None\n    try:\n        model = build(device)\n"
        "    except OSError as error:\n        print(error)\n"
        "    model = rebuild(device)\n    return model\n"
    ),
)


@pytest.mark.parametrize("source", GUARD_CASES)
def test_expansion_keeps_the_reviewed_near_misses_silent(source: str) -> None:
    """A reviewed near-miss that starts firing is a regression, not a win."""
    assert not codes(source) & EXPANSION_CODES


def test_existing_rules_still_fire_on_their_canonical_shapes() -> None:
    """The expansion must not have disturbed the rules that were already there."""
    assert "HNS002" in codes("import torch\n\ndef load(p):\n    return torch.load(p)\n")
    assert "HNS021" in codes("def read(p):\n    return open(p).read()\n")
    assert "HNS021" in codes(
        "class Wrapper:\n    def open(self, mode):\n        return mode\n\n\n"
        "def read(w):\n    return w.open('r')\n"
    )


@pytest.fixture(scope="module")
def production_hits() -> dict[str, set[str]]:
    """Every expansion finding in the gate's own production scope, by code."""
    hits: dict[str, set[str]] = {}
    for path in targets._files_to_check(["research", "scripts"]):
        source, finding = targets._load_source(path, staged=False)
        if finding is not None:
            continue
        for result in analyze_python(source, path):
            if result.code in EXPANSION_CODES:
                hits.setdefault(result.code, set()).add(result.path)
    return hits


def test_the_census_covers_the_production_tree() -> None:
    """The census must span this repo's production tree, not a fixed site count."""
    scanned = targets._files_to_check(sorted(targets.PRODUCTION_ROOTS))
    assert scanned
    assert "scripts/slurm_queue/submit.py" in scanned


def test_expansion_leaves_the_remediated_error_bar_alone(
    production_hits: dict[str, set[str]],
) -> None:
    """HNS031 names no production site: ``_stderr`` now returns ``NaN``, not 0.0."""
    assert not production_hits.get("HNS031")


def test_expansion_leaves_the_reviewed_inert_quotient_alone(
    production_hits: dict[str, set[str]],
) -> None:
    """HNS030 names no production site: the one candidate quotient is inert."""
    assert len(production_hits.get("HNS030", set())) <= 1


def test_expansion_holds_the_dispatch_census(
    production_hits: dict[str, set[str]],
) -> None:
    """HNS037 has at most one live site in production; the repair empties it."""
    assert len(production_hits.get("HNS037", set())) <= 1


def test_optional_input_neutralized_to_a_placeholder_is_reported() -> None:
    """The solver took ``Sigma_safe`` and silently dropped the basis constraint."""
    source = (
        "import numpy as np\n"
        "\n"
        "\n"
        "def solve(C, Sigma_safe, U_safe=None, rank=2):\n"
        "    if U_safe is None:\n"
        "        return np.empty((C.shape[0], 0))\n"
        "    return U_safe\n"
    )
    assert "HNS034" in codes(source)


def test_requiring_the_input_instead_of_substituting_is_silent() -> None:
    """Failing closed is the documented repair and must not re-trip the rule."""
    source = (
        "def solve(C, Sigma_safe, U_safe=None, rank=2):\n"
        "    if U_safe is None:\n"
        '        raise ValueError("requires U_safe")\n'
        "    return U_safe\n"
    )
    assert "HNS034" not in codes(source)


def test_a_legitimate_default_substitute_stays_silent() -> None:
    """``device = cpu`` is a default, not a dropped constraint."""
    source = (
        "import torch\n"
        "\n"
        "\n"
        "def move(t, device: torch.device | None = None):\n"
        "    if device is None:\n"
        '        device = torch.device("cpu")\n'
        "    return t.to(device)\n"
    )
    assert "HNS034" not in codes(source)


def test_a_required_input_is_never_a_finding() -> None:
    """A parameter that was never optional cannot be silently neutralized."""
    source = (
        "import numpy as np\n"
        "\n"
        "\n"
        "def solve(C, U_safe, rank=2):\n"
        "    if U_safe is None:\n"
        "        return np.empty((C.shape[0], 0))\n"
        "    return U_safe\n"
    )
    assert "HNS034" not in codes(source)


def test_a_neutral_value_that_escapes_nothing_is_silent() -> None:
    """The substitute must be returned or assigned to count as degradation."""
    source = (
        "import numpy as np\n"
        "\n"
        "\n"
        "def solve(C, U_safe=None, rank=2):\n"
        "    if U_safe is None:\n"
        "        np.empty((C.shape[0], 0))\n"
        "    return C\n"
    )
    assert "HNS034" not in codes(source)


def test_a_full_rank_default_selection_stays_silent() -> None:
    """``carrier = None -> eye`` selects everything; nothing was emptied."""
    source = (
        "import torch\n"
        "\n"
        "\n"
        "def normalize(carrier: torch.Tensor | None, width: int):\n"
        "    if carrier is None:\n"
        "        return torch.eye(width)\n"
        "    return carrier\n"
    )
    assert "HNS034" not in codes(source)


def test_a_zeroed_substitute_is_still_reported() -> None:
    """``zeros`` voids a direction, which is the family the rule targets."""
    source = (
        "import numpy as np\n"
        "\n"
        "\n"
        "def solve(C, rho=None):\n"
        "    if rho is None:\n"
        "        return np.zeros(C.shape[0])\n"
        "    return rho\n"
    )
    assert "HNS034" in codes(source)


def test_a_mode_default_outside_its_dispatch_is_reported() -> None:
    """A default mode string that no branch of its own dispatch matches is reported."""
    source = (
        "def extract(G, U_safe, rank_mode: str = 'adaptive', rank: int | None = None):\n"
        "    if rank_mode in {'spectral', 'energy'}:\n"
        "        return spectral(rank_mode)\n"
        "    if rank_mode in {'gavish_donoho', 'oht', 'donoho'}:\n"
        "        return gavish(rank_mode)\n"
        "    return pinned(rank)\n"
    )
    assert "HNS037" in codes(source)


def test_a_default_inside_its_own_dispatch_is_silent() -> None:
    """Enumerating the default is the documented repair and must stay silent."""
    source = (
        "def extract(G, U_safe, rank_mode: str = 'adaptive'):\n"
        "    if rank_mode in {'spectral', 'energy'}:\n"
        "        return spectral(rank_mode)\n"
        "    if rank_mode in {'adaptive', 'oht', 'donoho'}:\n"
        "        return resolve_default(rank_mode)\n"
        "    return None\n"
    )
    assert "HNS037" not in codes(source)


def test_a_single_special_case_is_not_a_dispatch_table() -> None:
    """One ``==`` beside a general branch is not an enumeration of the modes."""
    source = (
        "def rank_for(mode: str = 'oht', rank: int | None = None):\n"
        "    if mode == 'energy':\n"
        "        return energy()\n"
        "    return rank or 0\n"
    )
    assert "HNS037" not in codes(source)


def test_a_literal_beside_an_enumeration_counts_as_handled() -> None:
    """``carrier_mode == "sdp"`` in its own helper claims the default."""
    source = (
        "def wants_sdp(mode):\n"
        "    return mode == 'sdp'\n"
        "\n"
        "\n"
        "def extract(mode: str = 'sdp'):\n"
        "    if wants_sdp(mode):\n"
        "        return sdp(mode)\n"
        "    if mode in {'adaptive', 'protected_adaptive'}:\n"
        "        return resolve_default(mode)\n"
        "    return svd(mode)\n"
    )
    assert "HNS037" not in codes(source)


def test_a_mode_forwarded_without_a_local_dispatch_is_out_of_scope() -> None:
    """A module that only relays the setting cannot discharge the branch itself."""
    source = (
        "def settings(rank_mode: str = 'adaptive'):\n"
        "    return {'rank_mode': rank_mode}\n"
    )
    assert "HNS037" not in codes(source)


def test_a_non_mode_string_default_is_not_a_dispatch_key() -> None:
    """A path or message default is not a mode, even beside a mode table."""
    source = (
        "def load(path: str = '/tmp/x.pt', mode: str = 'ridge'):\n"
        "    if mode in {'ridge', 'gradient'}:\n"
        "        return read(path, mode)\n"
        "    return None\n"
    )
    assert "HNS037" not in codes(source)
