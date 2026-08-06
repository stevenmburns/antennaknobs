"""Port-based network spec for transmission lines and lumped elements.

A `Network` describes how the antenna's feed-edges (named real ports) and
purely-logical nodes (virtual ports) hook together via two-port branches.
Engines consume the network as a post-processing layer on top of the
multi-port antenna Y matrix: every branch and source stamps into one
Modified Nodal Analysis system (see `network_reduce`), which is solved for
the driven-port impedances and the physical port voltages in one shot.

Compared with the legacy `build_tls()` API:
  - No dummy stub wire is required for the driver — virtual ports exist
    only in the network reduction, not in the geometry.
  - Branches refer to ports by name; no manual segment-index counting.
  - Same shape covers transmission lines (`TL`) and (planned) lumped
    elements (`Load`, `TwoPort` — coming in a follow-up).

For PyNECEngine, this spec gets translated back into the NEC2-shaped
`tl_card` / `ld_card` / `nt_card` calls, with virtual ports synthesised
as tiny stub wires at sensible locations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import NamedTuple, Optional, Union

from .touchstone import Touchstone


@dataclass(frozen=True)
class PortOnWire:
    """Real port ON a named wire of the geometry: `name` matches the label
    a `build_wires()` tuple carries as its 5th element, and the port is a
    delta gap at that wire's MIDDLE segment (momwire: the arclength
    midpoint; PyNEC: segment (n_seg+1)//2 — identical placement for odd
    segment counts, which named port wires should therefore use). A port
    must interrupt a current path, so it lives in a wire's interior, never
    at an endpoint — to put a feed "at" some point of a structure, author
    a short named wire there.

    This is the only port type that touches geometry (contrast
    `PortVirtual`, a pure circuit node): it becomes one row/column of the
    antenna's multiport short-circuit Y that the network stamps onto.

    ``distributed=True`` makes the port a FINITE gap spanning the whole
    named wire instead of a delta gap on one segment: the excitation is a
    constant field over the wire's fixed physical length (one sub-feed per
    segment, voltages split by length), and the port row of Y is the
    length-weighted contraction of the sub-feed rows. A delta gap's
    readout moves whenever mesh refinement subdivides the port wire (the
    gap narrows with the segment — issue #477's port-drift class:
    sterba_tl's pinned ports, zepp's jump when its port wire first
    subdivides); the finite gap's width is set by geometry, not by the
    mesh, so the port impedance is mesh-stable by construction and the
    port wire may refine like every other wire. The value it converges to
    is the finite-gap answer for THAT physical width — for the short port
    stubs this models, within a couple percent of the delta-gap limit,
    and (unlike the pinned delta gap) basis-independent.

    Formerly `PortAtEdge` ("edge" in the wire-graph sense, which read as
    "wire end"); that name remains as a deprecated alias."""

    name: str
    distributed: bool = False


@dataclass(frozen=True)
class PortVirtual:
    """Logical port with no geometry. Exists only as a row/column in the
    network Y matrix; doesn't radiate, doesn't have a basis function.
    Used for driver feeds that branch out via TLs to real ports."""

    name: str


@dataclass(frozen=True)
class PortOnWireFloating(PortOnWire):
    """A `PortOnWire` whose BOTH terminals are exposed as circuit nodes.

    An ordinary gap port is stamped node-to-datum: its second terminal is
    bonded to the common return, so a branch can only connect to one side of
    the gap. That is a *stamping convention*, not physics — the MoM only ever
    knows gap voltage and gap current, so every delta gap is inherently a
    floating two-terminal object. This port type stops imposing the bond.

    The two terminals are addressed as dotted sub-nodes — ``"feed.p"`` and
    ``"feed.n"`` for a port named ``feed`` — the same way `Instance` exposes a
    composite's interior nodes (``"tuner.m"``). Branches reference those names;
    the bare port name is not a node.

    Use it to hang a genuinely balanced element off the structure: the two
    terminals may go to *different* branches, which a node-to-datum port
    cannot express. SimNEC models NEC feeds this way as a matter of course —
    its `NECSource({w1,w2}, wire, percent)` takes two arbitrary circuit nets,
    and its Ruthroff/Guanella balun sample runs the two sides of one antenna
    gap into two different choke inductors.

    Unlike `PortAtEnd` this needs nothing new from the solver — it changes only
    how the shared reducer stamps the antenna's multiport Y — so it works on
    every engine, PyNEC included.

    NOTE a single floating gap is a 1-port: its Y has one degree of freedom, so
    the stamp is purely differential and supplies NO common-mode path. Either
    give the network a CM return, or model the CM path as its own gap port —
    a 2-port Y couples the two gaps and carries that physics itself.
    """


# Deprecated alias — the pre-rename class name ("edge" meant a wire-graph
# edge, i.e. one build_wires() tuple, but read as "wire end"). Kept so any
# externally-authored design importing it keeps working.
PortAtEdge = PortOnWire


@dataclass(frozen=True)
class PortAtEnd:
    """Port AT a wire ENDPOINT (issue #579) — the attachment a floating
    multi-terminal element (`BalancedLine`) needs and a `PortOnWire` gap
    cannot provide (a gap is a series insertion; issue #576's validation
    mapped the dead-end-stub and bridge-idiom failure modes).

    ``wire`` names a `build_wires()` tuple (names must be unique); ``end``
    picks its authored ``"p0"`` or ``"p1"`` endpoint. The port resolves to
    the shared NODE at that point: geometry translation forces a polyline
    boundary there and momwire hosts a junction port (momwire#172) — the
    node's KCL row becomes the port's drive/readout vector, so driving the
    port injects current INTO the node and the port voltage is the node's
    Lagrange dual. When several wire ends coincide at the point, the port
    attaches to the whole shared junction group (declare it on ONE of the
    wires). Unlike `PortOnWire`, no gap is cut in the wire — the name only
    identifies the geometry, and a wire name may be referenced by either
    port kind, not both.

    momwire-only: NEC-2 has no junction-node port (NT/TL cards attach to
    segment interiors), so `PyNECEngine` rejects designs using this port
    type — a deliberate, declared engine-parity break."""

    wire: str
    end: str = "p1"

    def __post_init__(self):
        if self.end not in ("p0", "p1"):
            raise ValueError(f"PortAtEnd end must be 'p0' or 'p1', got {self.end!r}")


Port = Union[PortOnWire, PortOnWireFloating, PortAtEnd, PortVirtual]


@dataclass(frozen=True)
class TL:
    """Transmission line between two ports — lossless by default, lossy when
    matched-loss coefficients are given (issue #297).

    z0:     characteristic impedance in Ω
    length: physical length in meters

    The electrical length βl is computed at solve time from the antenna's
    operating wavelength and `vf`. Both endpoints can be either real or
    virtual.

    transposed: crossed ("half-twist") line — inverts port B's polarity,
    flipping the sign of the off-diagonal transfer terms. This is the
    phase reversal a transposed-feeder array (LPDA, ZL-Special) needs.
    Prefer it over a negative z0, which would wrongly negate the diagonal
    self terms too.

    vf: velocity factor — phase velocity as a fraction of c, so
    β = 2π/(vf·λ₀). The default 1.0 preserves the historical behavior
    (physical length read as free-space electrical length).

    k1, k2: matched-loss coefficients in the cable-table convention,
        matched loss [dB per 100 ft] = k1·√f_MHz + k2·f_MHz
    (k1 = conductor/skin-effect term, k2 = dielectric term). α is derived
    from these at each operating frequency, so sweeps get the loss slope
    for free, and SWR-dependent additional loss emerges from the circuit
    solution rather than a formula. Defaults 0.0 → lossless. Use
    `TL.from_cable()` for real cables.
    """

    a: str  # port name
    b: str
    z0: float
    length: float
    transposed: bool = False
    vf: float = 1.0
    k1: float = 0.0
    k2: float = 0.0

    @classmethod
    def from_cable(cls, cable, a, b, length, transposed=False):
        """A `TL` with z0/vf/k1/k2 taken from the `CABLES` catalog entry
        named `cable` (e.g. ``TL.from_cable("RG-8X", "rig", "feed", 30.48)``)."""
        if cable not in CABLES:
            raise KeyError(
                f"unknown cable {cable!r}; available: {', '.join(sorted(CABLES))}"
            )
        c = CABLES[cable]
        return cls(
            a=a, b=b, z0=c.z0, length=length, transposed=transposed,
            vf=c.vf, k1=c.k1, k2=c.k2,
        )  # fmt: skip


@dataclass(frozen=True)
class Cable:
    """Catalog entry for a feedline type: characteristic impedance, velocity
    factor, and matched-loss coefficients (dB/100 ft = k1·√f_MHz + k2·f_MHz)."""

    z0: float
    vf: float
    k1: float
    k2: float


# Nominal catalog values assembled from typical published matched-loss tables
# (dB/100 ft at HF/VHF) — vendor datasheets vary by a few tens of percent
# between constructions, so treat these as representative, not as any one
# manufacturer's spec.
CABLES = {
    "RG-58": Cable(z0=50.0, vf=0.66, k1=0.40, k2=0.008),
    "RG-8X": Cable(z0=50.0, vf=0.80, k1=0.27, k2=0.0055),
    "RG-213": Cable(z0=50.0, vf=0.66, k1=0.18, k2=0.003),
    "LMR-400": Cable(z0=50.0, vf=0.85, k1=0.122, k2=0.0003),
    "window-450": Cable(z0=450.0, vf=0.91, k1=0.035, k2=0.0002),
    "openwire-600": Cable(z0=600.0, vf=0.95, k1=0.02, k2=0.0001),
}


COPPER_CONDUCTIVITY = 5.8e7  # S/m (annealed copper, the IACS reference)


@dataclass(frozen=True)
class WireSpec:
    """Catalog entry for the antenna wire itself (issue #316): conductor
    radius and conductivity for skin-effect loss, optional dielectric
    jacket for the insulated-wire velocity-factor effect, and weight per
    meter (jacket included) for the how-heavy-is-this-antenna readout.

    `conductivity=None` means PEC (today's idealization with a real
    radius); `insulation_radius=None` means bare wire. Engines consume
    this via `Builder.build_wire_material()` — momwire models both
    effects, PyNEC models conductor loss natively (ld_card type 5) but
    has no NEC-2 card for insulation and solves the bare wire.
    """

    radius: float  # conductor radius, m
    conductivity: float | None = None  # S/m; None = PEC
    insulation_radius: float | None = None  # jacket outer radius, m
    insulation_eps_r: float | None = None  # jacket relative permittivity
    weight_g_per_m: float = 0.0  # conductor + jacket


# Nominal catalog values: bare-copper AWG diameters, copper at 5.8e7 S/m,
# and for the insulated variants a representative PVC hookup-wire jacket
# (εr ≈ 3.5 at HF, jacket ODs typical of stranded hookup wire — vendor
# constructions vary, treat as representative). Weights from copper at
# 8.96 g/cm³ + PVC at 1.4 g/cm³.
WIRES = {
    "28-awg": WireSpec(
        radius=0.160e-3, conductivity=COPPER_CONDUCTIVITY, weight_g_per_m=0.72
    ),
    "22-awg": WireSpec(
        radius=0.321e-3, conductivity=COPPER_CONDUCTIVITY, weight_g_per_m=2.91
    ),
    "18-awg": WireSpec(
        radius=0.512e-3, conductivity=COPPER_CONDUCTIVITY, weight_g_per_m=7.37
    ),
    "28-awg-pvc": WireSpec(
        radius=0.160e-3,
        conductivity=COPPER_CONDUCTIVITY,
        insulation_radius=0.50e-3,
        insulation_eps_r=3.5,
        weight_g_per_m=1.71,
    ),
    "22-awg-pvc": WireSpec(
        radius=0.321e-3,
        conductivity=COPPER_CONDUCTIVITY,
        insulation_radius=0.80e-3,
        insulation_eps_r=3.5,
        weight_g_per_m=5.27,
    ),
    "18-awg-pvc": WireSpec(
        radius=0.512e-3,
        conductivity=COPPER_CONDUCTIVITY,
        insulation_radius=1.05e-3,
        insulation_eps_r=3.5,
        weight_g_per_m=11.07,
    ),
}


def wire_from_catalog(name):
    """The `WIRES` entry for `name`, with the same unknown-key ergonomics
    as `TL.from_cable`."""
    if name not in WIRES:
        raise KeyError(f"unknown wire {name!r}; available: {', '.join(sorted(WIRES))}")
    return WIRES[name]


class Wire(NamedTuple):
    """One ``build_wires()`` entry, named (issue #388). A drop-in superset
    of the plain-tuple contract: a ``Wire`` IS a tuple, so indexing,
    unpacking, and the ``t[4]``-style name access keep working, and designs
    may freely mix plain 4/5-tuples and ``Wire`` entries in one list.

    With every field after the endpoints defaulted, keyword construction
    is the recommended brief spelling — ``Wire(a, b)`` is a structural
    wire at the design density, ``Wire(t, s, ex=1 + 0j)`` the feed,
    ``Wire(ti, to, name="trap_b0")`` a named attachment wire — with no
    positional ``None`` placeholders. (Plain tuples stay 4-6 fields;
    short plain tuples are rejected because a bare third element would
    be ambiguous between a count and an excitation.)

    ``n_seg=None`` means "mesh me at the design density" — resolved by
    ``AntennaBuilder.auto_mesh`` as part of the stack (nominal_nsegs
    segments per design_freq quarter-wave); an integer is honored
    verbatim.

    ``spec=None`` means "the design default": engines fall back to
    ``build_wire_material()``. Precedence, defined once: an explicit
    per-wire ``spec`` wins; the web ``wire_radius`` override only moves
    the default. Transforms, array placement, and scale knobs never scale
    a ``spec`` — it describes the physical wire stock the antenna is
    built from, not the geometry.
    """

    p0: tuple
    p1: tuple
    n_seg: int | None = None
    ex: complex | None = None
    name: str | None = None
    spec: WireSpec | None = None


def as_wire(t) -> Wire:
    """Normalize one ``build_wires()`` entry — plain 4/5/6-tuple or
    ``Wire`` — to a ``Wire``. This is the single choke point for
    tuple-shape discrimination: consumers should call this instead of
    inspecting ``len(t)``, because a ``Wire``'s defaults make its ``len()``
    always 6, which an arity check misreads."""
    if isinstance(t, Wire):
        return t
    if not 4 <= len(t) <= 6:
        raise ValueError(
            "build_wires() entry must have 4-6 fields "
            f"(p0, p1, n_seg, ex[, name[, spec]]), got {len(t)}"
        )
    return Wire(*t)


# Reserved for follow-up PR — sketched here so the discriminated-union
# pattern is established but not consumed yet by any engine.
@dataclass(frozen=True)
class Load:
    """R/L/C load inserted in series with a single segment's current path.

    `parallel=False` (default): series R + jωL + 1/(jωC). The whole expression
    is a single series impedance Z_load that adds to the segment's MoM Z[k,k].
    NEC2 calls this `ld_card` type 0.

    `parallel=True`: parallel R || jωL || 1/(jωC). The branch's effective
    series impedance Z_load = 1 / (1/R + 1/(jωL) + jωC). At ω₀ = 1/√(LC)
    the parallel-LC has Y → 0 → Z_load → ∞, which is exactly the trap idiom:
    the segment's current is interrupted at the trap's resonant frequency.
    NEC2 calls this `ld_card` type 1.

    Either way the effect is "lumped impedance in series with the segment":
    in the MNA reduction the load becomes the port's termination branch, a
    series Z_load between the segment's gap and the common return — the same
    physics as NEC2's ld_card modifying the segment's self-Z. The classic
    dual-band trap dipole uses Load(parallel=True) at a single segment in
    each arm — see designs/multiband/trap_dipole.py.

    `z` sets a FIXED, frequency-independent series impedance R + jX directly
    (NEC2 `ld_card` type 4, issue #422): unlike the R/L/C legs whose reactance
    scales with ω, `z` is used verbatim at every frequency. It is mutually
    exclusive with r/l/c/parallel/ql/qc — a load is either the RLC form or the
    fixed-Z form, never both. The reactive counterpart to `Admittance` for the
    *series* (in-the-current-path) case, where a shunt would be wrong.
    """

    port: str
    r: float | None = None
    l: float | None = None
    c: float | None = None
    parallel: bool = False
    ql: float | None = None  # coil Q: adds series R = omega*L/Q (issue #298)
    qc: float | None = None  # capacitor Q: adds ESR = 1/(omega*C*Q)
    z: complex | None = None  # fixed R+jX series impedance (ld_card 4, #422)

    def __post_init__(self):
        if self.z is not None and any(
            v not in (None, False)
            for v in (self.r, self.l, self.c, self.parallel, self.ql, self.qc)
        ):
            raise ValueError(
                "Load.z (fixed complex impedance) is mutually exclusive with "
                "the r/l/c/parallel/ql/qc legs — a load is either the RLC form "
                "or the fixed-Z form"
            )


@dataclass(frozen=True)
class TwoPort:
    """Lumped series R+jωL+1/(jωC) bridging two ports. Any of r/l/c may be
    None (omitted term). Unlike `Load` — a series termination on ONE port's
    current path — a TwoPort is a series element connecting two DISTINCT
    ports, Z = R + jωL + 1/(jωC).

    Both engines stamp this through the shared `NetworkReducer` as an MNA
    Group-2 element (the branch current is an explicit unknown, issue #285),
    so the degenerate values are physics, not errors: Z = 0 — a 0 Ω / 0 H
    element, an all-omitted branch, or exact series-LC resonance — is an
    ideal short identifying the two nodes, and C = 0 is an open. PyNECEngine
    can instead emit a native NEC2 `nt_card` (construct with
    ``native_nt=True``), which bakes the 2×2 short-circuit admittance
    Y = (1/Z)·[[1, -1], [-1, 1]] into one context and solves it
    simultaneously with the MoM currents — the correctness oracle for this
    stamp, analogous to `tl_card` for TL. The showcase and cross-engine
    cross-check is `designs/arrays/lumped_coupled_pair.py` (issue #65 piece
    (B)).

    For the trap-dipole idiom (a segment self-interrupted at resonance) use
    `Load(parallel=True)`, not TwoPort."""

    a: str
    b: str
    r: float | None = None
    l: float | None = None
    c: float | None = None
    ql: float | None = None  # coil Q: adds series R = omega*L/Q (issue #298)
    qc: float | None = None  # capacitor Q: adds ESR = 1/(omega*C*Q)


@dataclass(frozen=True)
class Shunt:
    """Lumped R/L/C from a single port to the common reference — a shunt to
    "ground", where ground is the port's own return terminal (a circuit node,
    not the antenna's earth plane): a current drains from the node to the
    common return, exactly a shunt element across the feed terminals. Since
    the MNA core (issue #285) a series-mode shunt is a Group-2 element, so
    Z = 0 (a 0 Ω / 0 H arm or exact series-LC resonance) is a legal hard
    short of the port to common, and C = 0 an open (no element).

    This is the element issue #65 Q2 deferred. With it, `Shunt` + a series
    `TwoPort` express an L-match (and pi / T networks) directly: drive a
    virtual input node, run a series `TwoPort` to the antenna feed and a
    `Shunt` across the input, read the input impedance. See
    `designs/loops/skyloop_lmatch.py`.

    series (default): y = 1/(R + jωL + 1/(jωC)) — a single C gives y=jωC, a
        single L gives y=1/(jωL); a series LC is a shunt trap.
    parallel:         y = 1/R + 1/(jωL) + jωC — a parallel-LC tank, y→0 at
        resonance (an open shunt, i.e. no element).
    Any of r/l/c may be None (omitted term).

    Both engines stamp this through the shared `NetworkReducer`; there is no
    native NEC card for a 1-port shunt-to-common, so a `Shunt` always takes the
    reducer path on PyNECEngine (never the baked-context native path)."""

    port: str
    r: float | None = None
    l: float | None = None
    c: float | None = None
    parallel: bool = False
    ql: float | None = None  # coil Q: adds series R = omega*L/Q (issue #298)
    qc: float | None = None  # capacitor Q: adds ESR = 1/(omega*C*Q)


@dataclass(frozen=True)
class Transformer:
    """Ideal transformer between two ports, with optional loss — the
    balun/unun element (issue #301). Each winding spans its port's node to
    the common datum (the same two-terminal convention every branch uses).

    n is the a:b turns ratio: v_a = n·v_b and i_b = −n·i_a, so the
    impedance seen at port a is n²·Z_b — a 4:1 balun stepping a ~300 Ω
    folded-dipole feed down to ~75 Ω line is `Transformer(a=line_side,
    b=feed, n=0.5)`. n = 1 (with no loss) is an ideal through-connection;
    n = 0 is rejected at stamp time (it would pin v_a = 0 while
    open-circuiting b — no physical transformer does that).

    Loss model, deliberately minimal (enough to reproduce a published
    insertion-loss curve's shape, not a full transformer model):
      r     — series winding resistance in Ω, referred to side a
              (constitutive row v_a − n·v_b = r·i_a);
      lmag  — magnetizing inductance in H, shunted across side a: at low
              frequency ωL_mag stops dwarfing the source impedance and
              insertion loss rises, the classic balun low-end rolloff;
      qlmag — finite Q of the magnetizing branch (core loss), same
              convention as `ql` elsewhere (issue #298).

    Reducer-only on both engines: there is no native NEC card for an
    ideal transformer (nt_card could bake a lossy 2×2 but not the ideal
    ratio), so a Transformer always takes the shared MNA path. Its
    dissipation (winding + magnetizing) itemizes in the power budget
    (issue #299)."""

    a: str
    b: str
    n: float
    r: float | None = None
    lmag: float | None = None
    qlmag: float | None = None
    #: A `ferrite.FerriteCore` (issue #599). When set it SUPERSEDES
    #: ``lmag``/``qlmag`` wholesale — it is the core, not a default, exactly as
    #: ``TL.from_cable``'s cable is the cable. The magnetizing branch then
    #: follows the mix's complex permeability at each frequency: μ′ sets the
    #: inductance, μ″ the loss, and the effective Q (μ′/μ″) moves with
    #: frequency the way a real choke's does.
    core: object | None = None


@dataclass(frozen=True)
class Autotransformer:
    """Tapped single winding — the auto-transformer (issue #594).

    `Transformer` is an *isolation* transformer: two windings, coupled only by
    the core. An autotransformer has **one** winding with a tap, so primary and
    secondary are galvanically connected and share the common turns. That is
    not a detail of construction — it changes the constitutive law, because the
    current in the common section is the *difference* of the input and output
    currents rather than a ratio-scaled copy.

    So this is not modelled as an ideal ratio. It is two **mutually coupled
    inductors** in series up one leg:

        datum ──[ l_lower ]── a (tap) ──[ l_upper ]── b (top)

    with mutual ``M = k·√(l_lower·l_upper)`` between them, stamped as two
    Group-2 branch-current rows plus their off-diagonal coupling. The turns
    ratio, the magnetizing behaviour, and the loss all fall *out* of that L/M
    matrix instead of being asserted — which is the point: an ideal-ratio model
    would get the common-section current wrong.

    In the ideal limit (``k`` → 1, inductances ≫ the load reactance) it
    reproduces the textbook tapped ratio

        n = 1 + √(l_upper / l_lower)          (turns go as √L on one core)

    so the impedance at the tap is the load at the top divided by n² —
    :func:`~antennaknobs.station.autotransformer_ratio` computes it.

    ``ql`` gives both sections the same finite Q (core + winding loss as a
    series r = ωL/Q, the ``ql`` convention used elsewhere); it itemizes in the
    power budget as *resistive* dissipation only, never the reactive power the
    two windings exchange.

    ``k`` must satisfy 0 ≤ k ≤ 1. Above 1 the inductance matrix stops being
    positive semi-definite — M² > L₁L₂ means the pair can deliver more energy
    than it stores — and the element would quietly generate power. SimSmith
    permits it and calls it non-physical; we refuse it, because our power
    budget claims to balance.

    Reducer-only, like `Transformer`: no NEC card, both engines.
    """

    a: str  # the tap — the low-impedance side
    b: str  # the top of the winding — the high-impedance side
    l_lower: float  # henries, datum → tap (the common section)
    l_upper: float  # henries, tap → top
    k: float = 1.0
    ql: float | None = None


@dataclass(frozen=True)
class Admittance:
    """A fixed, frequency-INDEPENDENT complex admittance branch (issue #416) —
    the general primitive a reactive NT card, a reactive TL end-shunt, and a
    fixed-jX (LD 4) load reduce to. Unlike Load/TwoPort/Shunt, whose reactance
    scales with ω, this short-circuit admittance matrix is stamped verbatim at
    every frequency.

    ``ports`` names the port(s) the branch spans and ``y`` is the matching
    admittance matrix in siemens (``len(ports) × len(ports)``, indexed to
    ``ports``):

    - 1-port ``ports=(p,)``, ``y=((yval,),)`` — a fixed ``y`` from the port
      node to the datum, the fixed-admittance sibling of ``Shunt`` (a reactive
      TL end-shunt, or a fixed-Z load folded as ``y = 1/Z``).
    - 2-port ``ports=(a, b)``, ``y=((y11, y12), (y21, y22))`` — the full 2×2
      short-circuit admittance, exactly NEC's NT-card Y (reciprocal decks give
      ``y21 = y12``, but a general matrix is accepted).

    Both engines stamp it through the shared ``NetworkReducer`` as a Group-1
    node-admittance block (no ω scaling, no auxiliary current), so it composes
    with every other branch and itemises in the power budget. There is no
    native NEC card for a 1-port shunt-to-common and PyNEC's ``nt_card`` maps
    the 2-port, but the default path on both engines is the reducer (like
    ``Shunt`` / ``Transformer``)."""

    ports: tuple[str, ...]
    y: tuple[tuple[complex, ...], ...]

    def __post_init__(self):
        n = len(self.ports)
        if n == 0:
            raise ValueError("Admittance needs at least one port")
        if len(self.y) != n or any(len(row) != n for row in self.y):
            raise ValueError(
                f"Admittance y must be {n}×{n} to match ports {self.ports}; "
                f"got {len(self.y)}×{len(self.y[0]) if self.y else 0}"
            )


@dataclass(frozen=True)
class TouchstoneLoad:
    """A measured / vendor 1-port (``.s1p``) as a frequency-dependent load
    (issue #593) — a node-to-datum admittance the reducer stamps at each solve
    frequency by interpolating the Touchstone data. Use it to terminate the
    model with a *measured* antenna feedpoint (NanoVNA/VNA) or a real load
    instead of an ideal one. The admittance is ``y = 1/Z(f)`` from the file, so
    it is the measured-data sibling of a 1-port ``Admittance`` / ``Shunt``.

    ``data`` is a 1-port :class:`~antennaknobs.touchstone.Touchstone`
    (see ``read_touchstone``). Works on both engines (post-MoM reducer math)."""

    port: str
    data: Touchstone

    def __post_init__(self):
        if self.data.nports != 1:
            raise ValueError(
                f"TouchstoneLoad on port {self.port!r} needs a 1-port (.s1p) "
                f"file; got a {self.data.nports}-port"
            )


@dataclass(frozen=True)
class TouchstoneTwoPort:
    """A measured / vendor 2-port (``.s2p``) as an in-line branch between ports
    ``a`` and ``b`` (issue #593) — the SimSmith "S block" analog. The file's
    measured ``[S]`` is converted to ``[Y]`` and stamped as a 2×2 Group-1 block,
    like ``TL``/``Admittance`` but from real data: a characterized balun, coax
    section, filter, or tuner dropped in as a black box.

    ``data`` is a 2-port :class:`~antennaknobs.touchstone.Touchstone`
    (see ``read_touchstone``). Works on both engines (post-MoM reducer math)."""

    a: str
    b: str
    data: Touchstone

    def __post_init__(self):
        if self.data.nports != 2:
            raise ValueError(
                f"TouchstoneTwoPort {self.a!r}→{self.b!r} needs a 2-port (.s2p) "
                f"file; got a {self.data.nports}-port"
            )


@dataclass(frozen=True)
class BalancedLine:
    """Balanced / differential two-conductor transmission line (issue #575) —
    the differential sibling of `TL`. Where a `TL(a, b)` is single-ended (each
    end referenced to the one network common), a BalancedLine models a pair of
    conductors carrying ±I with the return current riding the *partner* wire:
    open-wire feeder, twisted pair, the Sterba curtain's offset-pair verticals.

    Four terminals in two pairs — port A = ``(a1, a2)``, port B = ``(b1, b2)``,
    the two ends of the 2-conductor line. It is characterised by a single
    **differential impedance ``zdiff``** (the number off the ladder-line spool:
    300 / 450 / 600 Ω) plus physical ``length``, ``vf``, and optional
    matched-loss ``k1``/``k2`` — mirroring `TL`. For anyone coming from the
    microwave even/odd convention, ``zdiff = 2·z0o``.

    **Differential by default, with an optional common-mode path** (``zcomm``,
    issue #576). The default ``zcomm=None`` stamps only the odd-mode block,
    which structurally forces ``I(a1) = −I(a2)`` at each end — exactly the ±I
    cancellation the Sterba pair relies on, enforced by construction. That
    default follows the physics of an isolated pair: it supports exactly one
    TEM mode (the differential one); the even ("common") mode's return is a
    third conductor that isn't there, its Z0 is ill-defined, and even-mode
    current is really antenna-mode current that radiates, which a network
    branch cannot faithfully represent.

    BUT — the #576 end-to-end finding — a differential-only stamp also
    deletes the pair's *conductor continuity*: a real pair, however tightly
    coupled, still transports its end-to-end common-mode boundary condition,
    and in multi-loop structures (the multi-bay Sterba curtain) that
    constraint is load-bearing even where the CM *current* is small (measured
    5–15% of DM there, yet its removal costs 5 dB and steers the beam). Set
    ``zcomm`` — the pair-driven-as-one-conductor CM impedance — to add the
    orthogonal even-mode block and restore the path. Honesty notes: at
    resonant lengths (≈ k·vf·λ/2, e.g. the Sterba's risers) the CM line is a
    repeater and results are insensitive to the value (measured identical
    over 25–400 Ω), so any plausible number is fine; away from resonance
    ``zcomm`` is a genuine approximation for a radiating path — estimate it
    from geometry and treat results accordingly. The CM stamp still cannot
    radiate; a structure whose riser antenna-mode current matters beyond its
    boundary condition needs real wires.

    Stamped through the shared `NetworkReducer` as one chain-matrix 2-port
    per mode (issue #746): in differential variables it is an ordinary 2-port
    TL with z0 = zdiff, carried on the pair incidence (+1, −1) at each end;
    ``zcomm`` adds a second, orthogonal 2-port on the (½, ½) common-mode
    incidence — the exact even/odd decomposition, no cross-terms, so the
    differential behaviour is untouched. ``network_reduce.
    balanced_admittance_4x4`` is the closed 4×4 form of the same thing, kept
    as the oracle. A lossless line at exactly k·vf·λ/2 is an ordinary
    through-line here (the addendum below); real open-wire ``k1`` loss is
    still worth giving the exactly-λ/2 riser, but for its physics rather than
    to dodge a pole.

    Addendum 2026-08-06 (issue #746): before the chain-matrix stamp, a
    lossless k·vf·λ/2 line RAISED — the 4×4 admittance form has a pole
    there — and designs carried length fudges to avoid it. That is gone; the
    half-wave case is now the best-conditioned length there is.

    **No ``transposed`` flag**: with four explicit terminals a crossover (the
    Sterba's half-twist) is just wiring port B as ``(b2, b1)`` — visible in
    the design source. (A crossover flips only the differential sign; the CM
    block is symmetric under it.)

    With ``zcomm=None`` the common mode is structurally open (the 4×4 is
    rank-2 by construction), so each terminal node must be
    common-mode-determinate from elsewhere — attached to a radiating wire
    (`PortOnWire`), driven, or wired to a non-BalancedLine branch. A node
    reachable *only* through CM-open BalancedLine terminals is rejected by
    `Network.__post_init__` (it would make MNA singular at solve time); a
    ``zcomm``-carrying BalancedLine is itself a common-mode return, so its
    terminals count as determinate.

    Both engines stamp it through the shared `NetworkReducer` (a pure
    admittance block, no native NEC card — exactly like `TL`, `Shunt`,
    `Transformer`, `Admittance`), so PyNEC and momwire agree on it to
    MoM-basis tolerance and nec2++ serves as an independent oracle for the
    differential stamp. There is no native-card path: NEC-2 has no coupled-
    line card, but the reducer never needed one. (Physics validation of the
    differential *model* against real coupled structures — the isolation
    oracle and end-to-end TL Sterba — is issue #576.)
    """

    a1: str
    a2: str
    b1: str
    b2: str
    zdiff: float
    length: float
    vf: float = 1.0
    k1: float = 0.0
    k2: float = 0.0
    zcomm: Optional[float] = None

    @classmethod
    def from_geometry(
        cls,
        a1,
        a2,
        b1,
        b2,
        *,
        spacing,
        length,
        conductor,
        conductor2=None,
        eps_r=None,
        fill=None,
        k1=0.0,
        k2=0.0,
        zcomm=None,
    ):
        """A `BalancedLine` whose ``zdiff``/``vf`` come from the line's physical
        dimensions instead of a spool label (issue #596).

        ``conductor`` (and ``conductor2`` for an unequal pair) is a radius in
        metres, a `WireSpec`, or a `WIRES` catalog key — so a jacketed catalog
        wire brings its own insulation along::

            BalancedLine.from_geometry(
                "t1", "t2", "a1", "a2",
                spacing=0.0254, length=20.0, conductor="18-awg-pvc",
            )

        ``spacing`` is centre-to-centre in metres. See :func:`two_wire_params`
        for the electrical model and, importantly, for what the insulation
        estimators can and cannot claim. ``k1``/``k2``/``zcomm`` pass straight
        through — geometry says nothing about matched loss or the common-mode
        path, which stay explicit.
        """
        r1, ins1, er1 = _conductor_geometry(conductor)
        r2, ins2, er2 = (
            (None, None, None)
            if conductor2 is None
            else _conductor_geometry(conductor2)
        )
        if ins1 is not None and ins2 is not None and ins1 != ins2:
            raise ValueError(
                "the two conductors declare different insulation radii "
                f"({ins1} vs {ins2} m); the shell model assumes one jacket "
                "thickness — pass `fill` (with eps_r) instead"
            )
        insulation_radius = ins1 if ins1 is not None else ins2
        eps_r = eps_r if eps_r is not None else (er1 if er1 is not None else er2)
        zdiff, vf = two_wire_params(
            spacing,
            r1,
            r2,
            insulation_radius=insulation_radius,
            eps_r=eps_r,
            fill=fill,
        )
        return cls(
            a1=a1, a2=a2, b1=b1, b2=b2, zdiff=zdiff, length=length,
            vf=vf, k1=k1, k2=k2, zcomm=zcomm,
        )  # fmt: skip


# Free-space wave impedance, √(μ₀/ε₀). The two-wire line formula below is
# η₀/π ≈ 119.917 Ω per unit of acosh — the familiar "276·log₁₀(2D/d)" of the
# handbooks is this same constant in base-10 clothing.
ETA0 = 376.730313668


def _conductor_geometry(spec):
    """``(radius, insulation_radius, eps_r)`` from a radius, `WireSpec`, or
    `WIRES` key — the three ways a caller can name a conductor."""
    if isinstance(spec, str):
        spec = wire_from_catalog(spec)
    if isinstance(spec, WireSpec):
        return spec.radius, spec.insulation_radius, spec.insulation_eps_r
    return float(spec), None, None


def two_wire_params(
    spacing: float,
    radius: float,
    radius2: float | None = None,
    *,
    insulation_radius: float | None = None,
    eps_r: float | None = None,
    fill: float | None = None,
) -> tuple[float, float]:
    """``(zdiff, vf)`` of a two-conductor line from its physical dimensions
    (issue #596).

    ``spacing`` is centre-to-centre, ``radius``/``radius2`` are the conductor
    radii (``radius2=None`` → equal conductors); all lengths in metres, to
    match the rest of ``network.py``. Use it when you know the *line* — "#14
    wire, six inches apart" — rather than the number off a spool:

        zdiff, vf = two_wire_params(0.1524, 0.000815)   # ≈ 627 Ω, 1.0

    **Bare conductors** are exact, from the general unequal-radius form

        Z = (η₀/2π)·acosh((D² − a₁² − a₂²) / (2·a₁·a₂))

    which collapses to the textbook ``(η₀/π)·acosh(D/d)`` for equal radii
    (evaluated in that direct form when the radii match, which is both exactly
    the identity ``acosh(2x²−1) = 2·acosh(x)`` and better conditioned for
    closely-spaced wires).

    **Insulation** is where the honesty caveats live, because a real balanced
    line is a *partial* dielectric fill — some of the field is in the plastic,
    most is in the air — and no closed form covers every construction. Two
    documented estimators, both reducing the result by ``√ε_eff`` (the
    inductance is unchanged: the jacket is not magnetic), so
    ``vf = 1/√ε_eff``:

    - ``insulation_radius`` + ``eps_r`` — the **coaxial-shell** model: each
      conductor wears a jacket of outer radius ``b``, and the potential
      integral splits into a dielectric part ``(1/εᵣ)·ln(b/a)`` and an air part
      ``ln(D/b)``. Right for jacketed wire and for window line, where the
      conductors are round, jacketed, and separated by mostly air. It uses the
      wide-spacing (``D ≫ b``) logarithmic form for the *correction only* — the
      bare value it corrects stays exact — and it is refused outright when the
      jackets touch (``b₁ + b₂ ≥ D``), where the assumption of air between them
      is simply false.
    - ``fill`` + ``eps_r`` — the **mixing rule** ``ε_eff = 1 + fill·(εᵣ − 1)``
      for the constructions the shell model can't describe: solid-web twinlead,
      or windowed line whose webbing you want to account for empirically.
      ``fill`` is the fraction of the field energy sitting in dielectric, and
      it is a fitted number, not a derived one (≈0.5 for solid twinlead,
      ≈0.15–0.25 for windowed line). Supply it when you have a nameplate ``vf``
      to match; prefer the shell model when you don't.

    Manufacturers' "450 Ω" and "300 Ω" are round numbers over a range of real
    constructions, so expect geometry-derived values to land within a few
    percent of a nameplate, not on it. When you know the nameplate ``vf``,
    it is better data than either estimator here.
    """
    a1 = float(radius)
    a2 = float(radius if radius2 is None else radius2)
    d = float(spacing)
    if a1 <= 0 or a2 <= 0:
        raise ValueError("conductor radii must be positive")
    if d <= a1 + a2:
        raise ValueError(
            f"centre spacing {d} m must exceed the sum of the radii "
            f"({a1 + a2} m) — these conductors overlap"
        )

    if a1 == a2:
        z_bare = (ETA0 / math.pi) * math.acosh(d / (2.0 * a1))
    else:
        z_bare = (ETA0 / (2.0 * math.pi)) * math.acosh(
            (d * d - a1 * a1 - a2 * a2) / (2.0 * a1 * a2)
        )

    eps_eff = 1.0
    if fill is not None:
        if eps_r is None:
            raise ValueError("fill needs eps_r (the insulation's permittivity)")
        if not 0.0 <= fill <= 1.0:
            raise ValueError(f"fill must be a fraction in [0, 1]; got {fill}")
        eps_eff = 1.0 + fill * (float(eps_r) - 1.0)
    elif insulation_radius is not None:
        if eps_r is None:
            raise ValueError("insulation_radius needs eps_r")
        b = float(insulation_radius)
        b1 = b2 = b
        if b1 <= a1 or b2 <= a2:
            raise ValueError(
                f"insulation radius {b} m must exceed the conductor radius"
            )
        if b1 + b2 >= d:
            raise ValueError(
                f"the jackets touch at this spacing ({b1 + b2} m of insulation "
                f"across a {d} m gap): there is no air path between the "
                "conductors, so the coaxial-shell model does not apply. Give "
                "`fill` (with eps_r) for a solid-web line, or pass the "
                "nameplate zdiff/vf directly."
            )
        er = float(eps_r)
        bare_terms = math.log(d / a1) + math.log(d / a2)
        clad_terms = (
            math.log(b1 / a1) / er
            + math.log(d / b1)
            + math.log(b2 / a2) / er
            + math.log(d / b2)
        )
        eps_eff = bare_terms / clad_terms

    return z_bare / math.sqrt(eps_eff), 1.0 / math.sqrt(eps_eff)


@dataclass(frozen=True)
class FloatingBalun:
    """Floating-secondary transformer / link-coupling — the differential twin
    of `Transformer` (issue #589). Where `Transformer` spans both windings
    node-to-datum (a single-ended:single-ended balun *ratio*, but NOT the
    unbalanced↔balanced *transition*), a FloatingBalun has a single-ended
    **primary** (``primary`` node to the datum, e.g. a 50 Ω rig) and a
    genuinely **floating differential secondary** — the terminal pair
    ``(a, b)``, neither leg bonded to the datum. It is the one primitive that
    closes the balanced chain ``Driven → rig → FloatingBalun → balanced tuner
    → BalancedLine → antenna`` to a datum-locked source without injecting the
    common-mode current a balanced feed exists to avoid.

    Reference topology: the Palstar BT1500A "double roller balanced tuner"
    places a 1:1 choke (current) balun at its 50 Ω input, converting the
    unbalanced coax to a balanced condition for the floating L-network; the
    balun is literally the first component and sits at the benign resistive
    input on purpose. `FloatingBalun(n=1)` is that element.

    ``n`` is the primary→secondary ratio in the constitutive relation

        v(a) − v(b) = n · v(primary)        (v(primary) is vs. the datum)

    so the *differential* impedance across the floating secondary is referred
    to the primary as ``Z_primary = Z_secondary / n²`` — a 1:1 balun (``n=1``,
    no loss) presents the balanced load impedance to the rig unchanged, and a
    4:1 current balun stepping a 200 Ω balanced load down to 50 Ω at the rig
    is ``n=2``. ``n = 1`` is a legal ideal element (no value is inverted);
    ``n = 0`` is rejected at stamp time (it would pin the secondary
    differential voltage to 0 — no physical balun does that).

    Loss model, mirroring `Transformer` (minimal, shape-of-the-curve only):
      r     — series winding resistance in Ω, referred to the secondary
              (constitutive row v_a − v_b − n·v_primary = r·j, j the
              secondary current);
      lmag  — magnetizing / choke inductance in H, shunted across the primary
              node to the datum: at low frequency ωL_mag stops dwarfing the
              source and insertion loss rises, the classic balun low-end
              rolloff. This models the *balun's own* common-mode choking and
              is distinct from `BalancedLine.zcomm` (the *line's* CM path);
      qlmag — finite Q of the magnetizing branch (core loss), same
              convention as `Transformer.qlmag` / `ql` elsewhere.

    Common-mode note: the constitutive row constrains only the secondary
    *differential* voltage; the secondary common mode ``(v_a + v_b)/2`` is
    genuinely floating (an isolated winding), and the element draws zero
    common-mode current (``I(a) = −I(b)`` at the element by construction).
    So the secondary pair needs a common-mode return from elsewhere — the
    antenna it feeds (a radiating structure grounds it), or a
    ``zcomm``-carrying `BalancedLine` — exactly like a CM-open `BalancedLine`
    terminal, and `Network.__post_init__` enforces this.

    Reducer-only on both engines, like `Transformer` (there is no native NEC
    card for an ideal transformer); its dissipation itemises in the power
    budget (issue #299)."""

    primary: str
    a: str
    b: str
    n: float
    r: float | None = None
    lmag: float | None = None
    qlmag: float | None = None
    #: See `Transformer.core` — same supersede-wholesale semantics (issue #599).
    core: object | None = None


Branch = Union[
    TL,
    Load,
    TwoPort,
    Shunt,
    Transformer,
    Autotransformer,
    Admittance,
    BalancedLine,
    FloatingBalun,
]


def _branch_port_refs(br):
    """Port names a branch references, regardless of branch type."""
    if isinstance(br, Admittance):
        return tuple(br.ports)
    if isinstance(br, BalancedLine):
        return (br.a1, br.a2, br.b1, br.b2)
    if isinstance(br, FloatingBalun):  # has .a/.b too — must precede the fallback
        return (br.primary, br.a, br.b)
    if hasattr(br, "a"):  # TL, TwoPort, Transformer
        return (br.a, br.b)
    return (br.port,)  # Load, Shunt


def _rewrite_branch(br, ren):
    """Copy of ``br`` with every port reference passed through ``ren``."""
    if isinstance(br, Admittance):
        return replace(br, ports=tuple(ren(p) for p in br.ports))
    if isinstance(br, BalancedLine):
        return replace(br, a1=ren(br.a1), a2=ren(br.a2), b1=ren(br.b1), b2=ren(br.b2))
    if isinstance(br, FloatingBalun):  # has .a/.b too — must precede the fallback
        return replace(br, primary=ren(br.primary), a=ren(br.a), b=ren(br.b))
    if hasattr(br, "a"):  # TL, TwoPort, Transformer
        return replace(br, a=ren(br.a), b=ren(br.b))
    return replace(br, port=ren(br.port))


def validate_named_wires_referenced(named_wires, network):
    """Reject named ``build_wires()`` wires that no `PortOnWire` references
    (issue #578).

    The geometry layer registers EVERY named wire as a port edge; a port row
    the network never references is left electrically open, and an open
    series gap CUTS the current path at that wire. The failure is silent and
    masquerades as plausible physics (the solve succeeds with the structure
    partitioned), so it is an init-time error. A wire named purely for
    documentation is almost certainly this bug; a deliberately-open gap
    should be an explicit `Load`/branch on a referenced port.

    Engines call this once the flattened network and the final wire list are
    both known (composite expansion has already namespaced port names).
    """
    gap_names = {n for n, p in network.ports.items() if isinstance(p, PortOnWire)}
    end_names = {p.wire for p in network.ports.values() if isinstance(p, PortAtEnd)}
    both = sorted(gap_names & end_names)
    if both:
        raise ValueError(
            f"wire name(s) {both} are referenced by both a PortOnWire and a "
            "PortAtEnd — a gap port cuts a delta gap in the wire while an "
            "end port must leave it gapless (issue #579); use separate wires."
        )
    orphaned = sorted(set(named_wires) - {None} - gap_names - end_names)
    if orphaned:
        raise ValueError(
            f"named wire(s) {orphaned} are not referenced by any PortOnWire "
            "or PortAtEnd in build_network(); a named wire becomes a port "
            "edge, and an unreferenced port is an OPEN gap that cuts the "
            "wire there (issue #578). Reference each name in Network.ports, "
            "or drop the name."
        )


# ---------------------------------------------------------------------------
# Composite components (issue #489): reusable sub-networks with hierarchy
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Composite:
    """A reusable sub-network template: a formal port interface plus a body
    of branches (and, optionally, nested :class:`Instance` s) that reference
    either those formal ports or private internal nodes.

    Design record: issue #489. The model follows the convergent shape of
    the HCL survey there ("generators are code, modules are data", Hdl21):
    a Composite is plain data; *factory functions* like
    ``station.t_network_tuner(...)`` are the parameter mechanism, so there
    is no template registry and no formal-parameter machinery — Python
    call arguments are the parameter list.

    - ``ports`` are the formal external ports. At instantiation each formal
      is bound to a name in the parent's namespace (`Instance` kwargs — the
      Verilog named port map).
    - Any other name a body branch references is an internal node, private
      to the instance: expansion namespaces it as ``"<instance>.<name>"``
      and declares it as a `PortVirtual` automatically. Internals cannot be
      referenced from outside (boundary hygiene — the ROHD lesson).
    - ``aliases`` merge two of the composite's own names into one electrical
      node (union-find at expansion). This is how a body connects a formal
      directly to another formal (a pass-through such as ``station.bypass()``)
      or surfaces one internal node under several formal names — cases a
      branch body cannot express (see the #489 aliasing note). SPICE's
      0 V-source idiom is deliberately NOT the mechanism: aliasing is a
      naming fact, not an element.
    - Bodies contain only branches and nested instances. Sources (`Driven`)
      and geometry ports live at the top level of the design's `Network`.
    """

    ports: tuple[str, ...]
    branches: tuple = ()
    aliases: tuple[tuple[str, str], ...] = ()
    #: How this box DRAWS (issue #652): a tuple of `schematic.Element`, or a
    #: zero-argument callable returning one. Optional — a box without it falls
    #: back to per-branch default symbols, which is a picture but an anonymous
    #: one. Written with `schematic.series` / `shunt`, which are plain data, so
    #: declaring one costs this module no drawing-library import.
    schematic: object = None

    def __post_init__(self):
        if len(set(self.ports)) != len(self.ports):
            raise ValueError(f"duplicate formal port in {self.ports!r}")
        for item in self.branches:
            if not isinstance(item, (*Branch.__args__, Instance)):
                raise ValueError(
                    f"Composite bodies hold branches or Instances, got {item!r}"
                    " (sources and geometry ports belong in the Network)"
                )


class Instance:
    """One instantiation of a :class:`Composite` inside a `Network` (or
    inside another Composite): ``Instance("tuner1", t_network_tuner(...),
    rig="rig", out="li")``.

    - ``name`` becomes the namespace prefix for the composite's internal
      nodes (``"tuner1.m"``) and the power-budget attribution path.
    - Keyword arguments are the formal/actual port map: every formal port
      of the composite must be bound to a port name in the parent's
      namespace (binding one actual to several formals is legal and simply
      fuses them). Missing or extra formals raise immediately.
    """

    def __init__(self, name: str, of: Composite, **portmap: str):
        if not name or "." in name:
            raise ValueError(
                f"instance name {name!r} must be non-empty and contain no '.'"
                " (dots are the namespace separator)"
            )
        formals, bound = set(of.ports), set(portmap)
        if formals != bound:
            missing, extra = formals - bound, bound - formals
            raise ValueError(
                f"instance {name!r} port map mismatch:"
                + (f" missing formals {sorted(missing)}" if missing else "")
                + (f" unknown formals {sorted(extra)}" if extra else "")
                + f"; composite ports are {of.ports!r}"
            )
        self.name = name
        self.of = of
        self.portmap = dict(portmap)


def _expand_instance(
    inst, formal_to_final, prefix, flat, paths, aliases, internals, composites=None
):
    """Recursively flatten ``inst`` into ``flat``/``paths``, collecting alias
    pairs and auto-created internal node names. ``formal_to_final`` maps the
    composite's formals to FINAL (fully resolved) names; ``prefix`` is the
    instance path ("tuner1." / "sta.tuner1.")."""

    def resolve(n):
        if n in formal_to_final:
            return formal_to_final[n]
        final = prefix + n
        internals.add(final)
        return final

    if composites is not None:
        # Keep the Composite that produced these branches, keyed by the same
        # path `branch_paths` uses. Flattening otherwise erases every trace of
        # the box, which is exactly what a schematic (issue #652) needs: the
        # author's fragment lives on the Composite, not on its branches.
        composites[prefix] = inst.of
    for item in inst.of.branches:
        if isinstance(item, Instance):
            child_map = {f: resolve(a) for f, a in item.portmap.items()}
            _expand_instance(
                item, child_map, prefix + item.name + ".",
                flat, paths, aliases, internals, composites,
            )  # fmt: skip
        else:
            flat.append(_rewrite_branch(item, resolve))
            paths.append(prefix)
    for a, b in inst.of.aliases:
        aliases.append((resolve(a), resolve(b)))


def _resolve_aliases(pairs, ports):
    """Union-find over alias ``pairs``; returns a rename map name → canonical.

    Canonical preference (deterministic): a real `PortOnWire` name beats any
    virtual (its name is welded to geometry and must never be rewritten),
    then top-level names beat instance-internal ones (fewer dots), then the
    shorter / lexicographically-smaller name. Merging two real ports is an
    error — two distinct geometry locations cannot be fused by naming."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    classes = {}
    for n in parent:
        classes.setdefault(find(n), []).append(n)

    rename = {}
    for members in classes.values():
        real = [n for n in members if isinstance(ports.get(n), (PortOnWire, PortAtEnd))]
        if len(real) > 1:
            raise ValueError(
                f"aliases merge distinct geometry ports {sorted(real)} — "
                "two real feed locations cannot be fused by naming"
            )
        canon = min(
            members,
            key=lambda n: (
                0 if n in real else 1,
                n.count("."),
                len(n),
                n,
            ),
        )
        for n in members:
            if n != canon:
                rename[n] = canon
    return rename


def _series_rlc_impedance(r, l, c, omega, ql=None, qc=None):
    """Series R + jωL + 1/(jωC). Any of r/l/c may be None (omitted term).

    Finite component Q (issue #298): `ql` adds the coil's series loss
    R_coil = ωL/Q_L; `qc` adds the capacitor's ESR = 1/(ωC·Q_C). Both are
    frequency-dependent by construction — a fixed `r` cannot express them
    across a sweep. None (default) = ideal component.

    Q is treated as frequency-INDEPENDENT: R = ωL/Q is re-derived at each
    solve frequency, so across a sweep R grows ∝ f. Physical truth for an
    air-core HF coil sits between the two expressible models — skin effect
    gives R ∝ √f (i.e. Q ∝ √f) — so constant Q overestimates loss above
    the frequency where the quoted Q is true and underestimates below it,
    while a fixed resistance (use plain `r` = ω_ref·L/Q for that) errs the
    opposite way. At a single operating frequency, with Q quoted at that
    frequency, all three agree. A √f reference-frequency model would slot
    in here if sweep fidelity ever warrants it."""
    z = 0.0 + 0.0j
    if r is not None:
        z += r
    if l is not None:
        z += 1j * omega * l
        if ql is not None:
            z += omega * l / ql
    if c is not None:
        z += 1.0 / (1j * omega * c)
        if qc is not None:
            z += 1.0 / (omega * c * qc)
    return z


def _parallel_rlc_admittance(r, l, c, omega, ql=None, qc=None):
    """Parallel 1/R + 1/(jωL) + jωC. Any of r/l/c may be None (omitted term).
    Trap dipoles use this: parallel-LC has Y → 0 at ω₀ = 1/√(LC), so the
    branch opens at the trap's resonant frequency.

    Finite Q (issue #298) lossifies each leg: the L leg becomes
    1/(ωL/Q_L + jωL), the C leg 1/(1/(jωC) + 1/(ωC·Q_C)). A lossy trap no
    longer opens completely — its resonant impedance tops out at the
    textbook ≈ Q·ω₀L instead of ∞."""
    y = 0.0 + 0.0j
    if r is not None:
        y += 1.0 / r
    if l is not None:
        zl = 1j * omega * l
        if ql is not None:
            zl += omega * l / ql
        y += 1.0 / zl
    if c is not None:
        if qc is not None:
            y += 1.0 / (1.0 / (1j * omega * c) + 1.0 / (omega * c * qc))
        else:
            y += 1j * omega * c
    return y


def load_series_admittance(br, omega):
    """Series-branch admittance y_load = 1/Z_load of a Load branch at ω.

    This is the quantity the MNA termination stamp uses for a parallel-mode
    Load (see network_reduce.NetworkReducer.apply_branches): it stays finite
    exactly where Z_load blows up.

    Parallel mode: y_load IS the parallel-LC tank admittance,
        y = 1/R + 1/(jωL) + jωC,
    which goes cleanly to 0 at ω₀ = 1/√(LC) — the trap-resonance open
    circuit. No singularity: the "infinite impedance" only ever appeared
    when we formed Z_load = 1/y and then took 1/Z_load again.

    Series mode: y_load = 1/(R + jωL + 1/(jωC)); returns complex inf when
    the series impedance is exactly 0 (series-LC short circuit), which the
    caller treats as "no series element" (the wire is unbroken)."""
    if br.z is not None:
        # Fixed R+jX (issue #422): admittance 1/z, inf at z = 0 (a short).
        return complex(float("inf"), 0.0) if br.z == 0 else 1.0 / complex(br.z)
    if br.parallel:
        return _parallel_rlc_admittance(br.r, br.l, br.c, omega, br.ql, br.qc)
    z = _series_rlc_impedance(br.r, br.l, br.c, omega, br.ql, br.qc)
    if z == 0:
        return complex(float("inf"), 0.0)
    return 1.0 / z


def load_impedance(br, omega):
    """Effective series impedance of a Load branch at angular ω.
    Series mode: Z = R + jωL + 1/(jωC).
    Parallel mode: Z = 1 / (1/R + 1/(jωL) + jωC) — equals the parallel-LC
    tank impedance, diverging at ω₀ = 1/√(LC) (the trap idiom).

    Returns complex inf at parallel-LC resonance rather than raising —
    Z→∞ is the physically-intended open circuit of a trap. Consumers that
    stamp the load into a port-Y matrix should prefer
    `load_series_admittance`, which avoids forming this infinity at all."""
    if br.z is not None:
        return complex(br.z)  # fixed R+jX, frequency-independent (issue #422)
    if br.parallel:
        y = _parallel_rlc_admittance(br.r, br.l, br.c, omega, br.ql, br.qc)
        if y == 0:
            return complex(float("inf"), 0.0)
        return 1.0 / y
    return _series_rlc_impedance(br.r, br.l, br.c, omega, br.ql, br.qc)


@dataclass(frozen=True)
class Driven:
    """Voltage source applied at a port. Multiple Driven entries are
    allowed — they're all driven simultaneously with their specified
    voltages (matching the multi-feed Y semantics)."""

    port: str
    voltage: complex = 1 + 0j


@dataclass(frozen=True)
class DrivenCurrent:
    """Ideal current source applied at a port — ``current`` amps forced
    into the port node from the common return (4nec2's ``EX 6``
    excitation, issue #442). The phased-array idiom: element drive
    RATIOS are what the designer specifies, and only a current source
    holds them regardless of the mutual coupling (K6STI-style feeds).

    Stamped by the shared ``NetworkReducer`` as a Group-2 forced-current
    branch, so it works identically on every engine that supplies a
    multiport Y. Series ``Load`` branches on the same port drop voltage
    inside the source loop without changing the forced current — exactly
    NEC's LD-in-segment semantics — and the reported driving-point
    impedance includes them, like the voltage case. May be freely mixed
    with ``Driven`` sources on *other* ports; a voltage and a current
    source on the SAME port is a contradiction and raises."""

    port: str
    current: complex = 1 + 0j


Source = Union[Driven, DrivenCurrent]


@dataclass
class Network:
    """Complete network spec returned by `build_network()`.

    ports:    dict mapping name → Port (real or virtual)
    branches: list of Branch (TL / Load / TwoPort / …) — may also contain
              `Instance` items (issue #489), which are flattened in
              ``__post_init__``: internal nodes become auto-declared
              `PortVirtual` s named "<instance>.<node>", composite aliases
              are resolved by node merging, and each flattened branch's
              instance path lands in ``branch_paths`` (same order as
              ``branches``; "" for top-level branches) for power-budget
              attribution. Engines and reducers only ever see plain
              branches.
    sources:  list of Source (currently just Driven)

    The engine's job: assemble the antenna Y matrix at the real ports,
    pad to include virtual ports, stamp every branch, then reduce to the
    driven-port impedances.
    """

    ports: dict[str, Port]
    branches: list[Branch] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    branch_paths: list[str] = field(default_factory=list)
    #: Instance path → the `Composite` it came from, filled by flattening
    #: (issue #652). Derived, like ``branch_paths``.
    composites: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.branch_paths:
            raise ValueError("branch_paths is derived — do not pass it")
        self._expand_instances()
        for name, port in self.ports.items():
            # A PortAtEnd is keyed by its PORT name alone; its `wire` field
            # names geometry, not the port (two end ports may share a wire),
            # so there is no redundant name field to cross-check.
            if not isinstance(port, PortAtEnd) and port.name != name:
                raise ValueError(
                    f"port dict key {name!r} doesn't match Port.name {port.name!r}"
                )
        port_names = set(self.ports)
        # A floating gap port is addressed by its two terminals, never by the
        # bare name: branches reference "<name>.p" / "<name>.n" (the dotted
        # sub-node convention Instance already uses for composite interiors).
        for name, port in self.ports.items():
            if isinstance(port, PortOnWireFloating):
                port_names.discard(name)
                port_names.update((f"{name}.p", f"{name}.n"))
        for br in self.branches:
            for ref in _branch_port_refs(br):
                if ref not in port_names:
                    raise ValueError(f"branch {br!r} references unknown port {ref!r}")
        for src in self.sources:
            if isinstance(self.ports.get(src.port), PortOnWireFloating):
                raise ValueError(
                    f"source {src!r} drives floating gap port {src.port!r}: a "
                    "floating gap is an attachment point, not a drive point "
                    "(which terminal would be the reference?). Drive through "
                    "the network instead, or use a plain PortOnWire."
                )
            if src.port not in port_names:
                raise ValueError(f"source {src!r} references unknown port")
        if not self.sources:
            raise ValueError("Network has no driven sources")
        self._validate_common_mode()

    def _validate_common_mode(self):
        """A CM-open `BalancedLine` (``zcomm=None``) stamps only the
        differential block, contributing nothing to its terminals' common
        mode; a `FloatingBalun`'s secondary pair ``(a, b)`` is likewise
        CM-floating — its constitutive row constrains only the differential
        voltage and the element draws zero common-mode current (issue #589).
        A node reachable ONLY through such terminals is common-mode floating,
        which makes the MNA singular at solve time — raise a clear,
        node-naming error here at build time instead. A node is
        common-mode-determinate if it is a real `PortOnWire` or `PortAtEnd`
        (an antenna-Y row grounds it), is driven by a source, is referenced by
        any non-BalancedLine branch or by a ``zcomm``-carrying BalancedLine
        (its CM block is itself a return), or is a `FloatingBalun` *primary*
        — issues #575/#576/#589.

        The primary is pinned by the element's CONSTITUTIVE ROW, not by any
        path to the datum: ``v_a − v_b − n·v_p = r·j`` determines ``v_p`` once
        the secondary pair is determinate (which the check above already
        requires), and ``n = 0`` is rejected at stamp time so the coefficient
        is never zero. The datum path one might reach for — the magnetizing
        shunt ``G[p, p] += y_mag`` — is stamped only when the element declares
        a magnetizing branch, and both `station.floating_balun` and
        `station.balanced_l_tuner` default ``lmag_uH=None``, so for the common
        ideal-balun case there is no such path at all (issue #660)."""
        cm_open = [
            b for b in self.branches if isinstance(b, BalancedLine) and b.zcomm is None
        ]
        fbaluns = [b for b in self.branches if isinstance(b, FloatingBalun)]
        if not cm_open and not fbaluns:
            return
        determinate = {
            n for n, p in self.ports.items() if isinstance(p, (PortOnWire, PortAtEnd))
        }
        determinate.update(src.port for src in self.sources)
        for br in self.branches:
            if isinstance(br, BalancedLine) and br.zcomm is None:
                continue  # CM-open line is not itself a common-mode return
            if isinstance(br, FloatingBalun):
                # Only the primary — pinned by the constitutive row, see the
                # docstring. The secondary pair is what we are checking FOR.
                determinate.add(br.primary)
                continue
            determinate.update(_branch_port_refs(br))
        touched = set()
        for br in cm_open:
            touched.update(_branch_port_refs(br))
        for br in fbaluns:
            touched.update((br.a, br.b))  # the floating secondary pair
        floating = sorted(touched - determinate)
        if floating:
            raise ValueError(
                f"node(s) {floating} attach only via terminals whose common "
                "mode is structurally open (a CM-open BalancedLine, or a "
                "FloatingBalun secondary) — the MNA would be singular. Give "
                "each a common-mode return: attach it to a radiating wire "
                "(PortOnWire), drive it, wire it to a non-BalancedLine branch, "
                "or set zcomm on the BalancedLine."
            )

    def _expand_instances(self):
        """Flatten `Instance` items (issue #489): namespace internals,
        resolve aliases, stamp per-branch instance paths."""
        flat, paths, alias_pairs, internals = [], [], [], set()
        composites: dict[str, Composite] = {}
        for item in self.branches:
            if isinstance(item, Instance):
                for actual in item.portmap.values():
                    if actual not in self.ports:
                        raise ValueError(
                            f"instance {item.name!r} binds to unknown port "
                            f"{actual!r} — actuals must be declared Network "
                            "ports"
                        )
                _expand_instance(
                    item, dict(item.portmap), item.name + ".",
                    flat, paths, alias_pairs, internals, composites,
                )  # fmt: skip
            else:
                flat.append(item)
                paths.append("")
        self.branches = flat
        self.branch_paths = paths
        self.composites = composites
        for n in sorted(internals):
            if n in self.ports:
                raise ValueError(f"internal node {n!r} collides with a port")
            self.ports[n] = PortVirtual(n)
        if not alias_pairs:
            return
        rename = _resolve_aliases(alias_pairs, self.ports)
        if not rename:
            return
        ren = lambda n: rename.get(n, n)  # noqa: E731
        self.branches = [_rewrite_branch(br, ren) for br in self.branches]
        self.ports = {n: p for n, p in self.ports.items() if n not in rename}
        merged_sources = []
        for src in self.sources:
            src = replace(src, port=ren(src.port))
            for prev in merged_sources:
                if prev.port == src.port:
                    if prev != src:
                        raise ValueError(
                            f"aliasing merged conflicting sources on port "
                            f"{src.port!r}: {prev!r} vs {src!r}"
                        )
                    break
            else:
                merged_sources.append(src)
        self.sources = merged_sources
