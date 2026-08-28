"""Compatibility shim: the network solve lives in `momwire.networks` now.

The whole of this module — the closed-form TL/chain math, the MNA primitives
and `MNASystem`, and `NetworkReducer` with its branch-stamping switch — moved
down into momwire in momwire#456 workstream 2, phase B (design record: momwire
``docs/design/networks-move-into-the-engine.md``). It went because momwire is
the thing standing at the drop-in seams: two of the three emit ``TL``/``NT``
cards, and NEC-2 and NEC-5 both solve networks natively, so an engine at their
seams has to as well. The code arrived there verbatim, split across
`momwire.networks._reduce` (the type-free core) and `._reducer`.

Nothing in antennaknobs had to change its imports for that, which is the
point of this file: ~40 design modules and ~50 test modules import from
``antennaknobs.network_reduce``, and every name they ask for is re-exported
below and IS the momwire object (``network_reduce.NetworkReducer is
momwire.networks.NetworkReducer``). The PyNEC-gated oracles that guard the
moved core — ``tests/test_tl_composition.py`` and the ``nt_card`` oracle in
``tests/test_momwire_engine.py`` — stay in antennaknobs and keep exercising
it from above, since PyNEC is outside momwire's dependency envelope.

Prefer importing from ``momwire.networks`` directly in new code.
"""

from __future__ import annotations

from momwire.networks import (
    C_LIGHT,
    FEET_PER_M,
    NEPER_PER_DB,
    RCOND_SINGULAR,
    RCOND_SUSPECT,
    MNASystem,
    NetworkReducer,
    SingularNetworkError,
    Z_REF_DEFAULT,
    balanced_admittance_4x4,
    magnetizing_impedance,
    poison_singular_sample,
    tl_abcd,
    tl_admittance_2x2,
)

__all__ = [
    "C_LIGHT",
    "FEET_PER_M",
    "NEPER_PER_DB",
    "MNASystem",
    "NetworkReducer",
    "RCOND_SINGULAR",
    "RCOND_SUSPECT",
    "SingularNetworkError",
    "Z_REF_DEFAULT",
    "balanced_admittance_4x4",
    "magnetizing_impedance",
    "poison_singular_sample",
    "tl_abcd",
    "tl_admittance_2x2",
]
