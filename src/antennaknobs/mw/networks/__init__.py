"""antennaknobs' general network reducer (AK#2219 phase 3, stage 1).

A COPY of momwire's ``momwire.networks`` taken at momwire commit 03a2357e
(momwire 0.89.0), with the same four module names. From that commit on it is
antennaknobs' code: bug fixes and new branch models land here, on
antennaknobs' release cycle, and are not ported back. momwire keeps its own
``momwire.networks`` for its deck path and drop-ins and, after a deprecation
window, trims it to the NEC-card subset (``PortOnWire``, ``TL``,
``Admittance`` as ``NT``, ``Driven`` and lumped port loads; stage 3 of the
plan in AK#2219). ``tests/test_mw_networks_ab_2219.py`` holds this copy equal
to momwire's, bit for bit, on every branch type; a change here that is meant
to move a number updates that test on purpose.

What changed in the copy, and nothing else (diff against the momwire commit
to check):

* ``C_LIGHT`` is defined in `._reduce` rather than imported from
  ``momwire._constants``: it is the exact SI value, so the two cannot differ.
* The power budget's two Group-1 products are written ``a @ b`` where momwire
  calls ``momwire._lapack.matmul``. That seam routes products to a host's BLAS
  only when a host process publishes one (``sys._mw_host_lapack``, momwire's
  standalone executables); otherwise it returns ``a @ b`` itself. No process
  antennaknobs runs in publishes one, so this is the same call, and the copy
  imports nothing from momwire at all.
* antennaknobs' lint, which momwire's config does not select: the seven
  ``zip`` calls in `._reducer` say ``strict=True`` (B905; every one zips
  lists built in step or validated to equal length, so the only change is
  that a misaligned network now raises instead of truncating), and the two
  tuple subclasses carrying ``.key`` are marked as not slottable (SLOT001).
* This docstring.

The three modules, as upstream described them:

* `._reduce` — the TYPE-FREE core: the closed-form TL/chain math and the MNA
  primitives, which never see a port name, a branch dataclass or a `Network`.
* `._spec` — ports, branches, sources and the flat `Network` container. It
  reuses `._reduce`'s series-RLC helper rather than carrying a second copy,
  which is why the dependency runs spec -> reduce and not the reverse.
* `._reducer` — `NetworkReducer`, which needs both and so is its own module.

`tl_abcd` is what the reducer stamps; `tl_admittance_2x2` and
`balanced_admittance_4x4` are the closed forms the composition oracles are
written against.

The `Network` here is FLAT: the authoring hierarchy (`Composite`/`Instance`)
is `antennaknobs.network`, which flattens before reducing and passes the
resulting ``branch_paths``. `Cable` is the formal line spec `TL.from_cable`
takes; the cable CATALOG is `antennaknobs.wire_catalog`, and the Touchstone
parser behind the `AdmittanceData` protocol is `antennaknobs.touchstone`.
Docstrings below keep momwire's vocabulary ("arrived from antennaknobs",
"momwire#NNN") where they record history.
"""

from __future__ import annotations

from ._reduce import (
    C_LIGHT,
    FEET_PER_M,
    NEPER_PER_DB,
    RCOND_SINGULAR,
    RCOND_SUSPECT,
    Z_REF_DEFAULT,
    MNASystem,
    SingularNetworkError,
    balanced_admittance_4x4,
    magnetizing_impedance,
    poison_singular_sample,
    tl_abcd,
    tl_admittance_2x2,
)
from ._reducer import NetworkReducer
from ._spec import (
    TL,
    Admittance,
    AdmittanceData,
    Autotransformer,
    BalancedLine,
    Branch,
    Cable,
    Driven,
    DrivenCurrent,
    FloatingBalun,
    Load,
    Network,
    Port,
    PortAtEdge,
    PortAtEnd,
    PortAtVertex,
    PortOnWire,
    PortOnWireFloating,
    PortVirtual,
    Shunt,
    Source,
    TouchstoneLoad,
    TouchstoneTwoPort,
    Transformer,
    TwoPort,
    load_impedance,
    load_series_admittance,
)

__all__ = [
    "C_LIGHT",
    "FEET_PER_M",
    "NEPER_PER_DB",
    "RCOND_SINGULAR",
    "RCOND_SUSPECT",
    "Z_REF_DEFAULT",
    "MNASystem",
    "SingularNetworkError",
    "balanced_admittance_4x4",
    "magnetizing_impedance",
    "poison_singular_sample",
    "tl_abcd",
    "tl_admittance_2x2",
    "NetworkReducer",
    "TL",
    "Admittance",
    "AdmittanceData",
    "Autotransformer",
    "BalancedLine",
    "Branch",
    "Cable",
    "Driven",
    "DrivenCurrent",
    "FloatingBalun",
    "Load",
    "Network",
    "Port",
    "PortAtEdge",
    "PortAtEnd",
    "PortAtVertex",
    "PortOnWire",
    "PortOnWireFloating",
    "PortVirtual",
    "Shunt",
    "Source",
    "TouchstoneLoad",
    "TouchstoneTwoPort",
    "Transformer",
    "TwoPort",
    "load_impedance",
    "load_series_admittance",
]
