"""Device provenance inference for the host-device transfer gate.

Thumbnail: Infers host, device or unknown placement for expressions and flags mixtures.

Invariants & Expected State:
    Package holds at most 5 modules and __init__.py carries no executable code.
    Only provable placement leaves this package; anything unmodelled is UNKNOWN.
"""

from __future__ import annotations

from framework.gates.transfers.provenance.infer import (
    DEVICE,
    HOST,
    UNKNOWN,
    provenance_of,
)
from framework.gates.transfers.provenance.mixed import mixing_finding

__all__ = ["DEVICE", "HOST", "UNKNOWN", "mixing_finding", "provenance_of"]
