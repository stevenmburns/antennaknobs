"""antennaknobs' general network reducer (AK#2219 phase 3, stage 1).

A COPY of momwire's ``momwire.networks`` taken at momwire commit 03a2357e
(momwire 0.89.0), with the same four module names. From that commit on it is
antennaknobs' code: bug fixes and new branch models land here, on
antennaknobs' release cycle, and are not ported back. momwire keeps its own
``momwire.networks`` for its deck path and drop-ins and, after a deprecation
window, trims it to the NEC-card subset (``PortOnWire``, ``TL``,
``Admittance`` as ``NT``, ``Driven`` and lumped port loads; stage 3 of the
plan in AK#2219). ``tests/test_mw_networks_ab_2219.py`` holds this copy equal
to momwire's, bit for bit, on every branch type, on the dense path (all of
its cases sit below the sparse threshold; see the second list below); a
change here that is meant to move a number updates that test on purpose.

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

What the copy has added since (it is antennaknobs' code; these are the
deliberate divergences from momwire, not drift):

* **Sparse MNA for large networks (AK#2241, stage 2 of AK#2219 phase 3).**
  At and above `_reduce.SPARSE_MIN_UNKNOWNS` (200, in MNA unknowns n + m),
  `apply_branches` assembles the system as COO triples summed into a CSC
  matrix, never allocating n × n or (n+m)², and `MNASystem.solve` factors it
  with SuperLU after ``zgesvx``'s own equilibration, refines as ``zgesvx``
  does, and estimates the reciprocal condition as ``zgecon`` does, against
  the same `RCOND_SINGULAR` / `RCOND_SUSPECT`, with the same refusal and
  warning. Below the threshold the path is momwire's dense ``zgesvx``.
  Every network the catalog ships is 34 unknowns or fewer, and every case of
  the A/B is under the threshold, which is why that A/B is still bit for
  bit; ``tests/test_sparse_mna_2241.py`` holds the two paths to each
  other.

* **One assembly, and repeated ports sum.** Both paths read one emitter,
  `_reduce._MNAStamps.triples`: every stamp as a COO triple, in the order
  the old dense code performed its additions. Small systems densify it in
  triple order, large ones sum it into CSC. Below the threshold every system
  is bit for bit what momwire builds, with one exception. A multiport whose
  ports repeat a node (an `Admittance` on ``(a, a)``, a `TouchstoneTwoPort`
  with ``a == b``) now SUMS its entries there: I1 + I2 =
  (y11 + y12 + y21 + y22)·V. momwire's dense stamp, a buffered fancy-index
  add, keeps one of them. Summing is the physics, and it is NEC's behaviour:
  licensed NEC-5 and NEC-4.2 sum the four Y entries of an ``NT`` card whose
  ends are one segment, with no warning, so ``NT 1 6 1 6`` equals ``LD 4``
  with Z = 1/(y11 + 2·y12 + y22), and a zero-sum Y leaves the gap open
  (momwire#1887, which is also momwire's side of the fix). AK's NEC
  importer accepts such a card and reduces it that way.
  ``tests/test_mna_unified_assembly.py`` holds it.

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
    Through,
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
    "Through",
    "TouchstoneLoad",
    "TouchstoneTwoPort",
    "Transformer",
    "TwoPort",
    "load_impedance",
    "load_series_admittance",
]
