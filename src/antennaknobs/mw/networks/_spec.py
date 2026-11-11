"""Port-based network spec for transmission lines and lumped elements.

A `Network` describes how the antenna's feed-edges (named real ports) and
purely-logical nodes (virtual ports) hook together via two-port branches.
Engines consume the network as a post-processing layer on top of the
multi-port antenna Y matrix: every branch and source stamps into one
Modified Nodal Analysis system (see `._reducer`), which is solved for the
driven-port impedances and the physical port voltages in one shot.

Arrived from antennaknobs per ``docs/design/networks-move-into-the-engine.md``
(momwire#456 workstream 2, phase B), near-verbatim: this is the circuit half
of that repo's ``network.py``. Two things changed deliberately in the move,
both recorded where they land:

* `Cable` is promoted here as the formal line-spec type, and
  `TL.from_cable` now takes one instead of a catalog name — momwire carries
  no catalog, and name -> spec resolution belongs to the caller (the
  ``CABLES`` dict stays in antennaknobs with the rest of the physical stock).
* `Network` is FLAT. The authoring hierarchy (`Composite`/`Instance` and its
  flattening) stays in antennaknobs, which flattens before handing momwire a
  Network; ``branch_paths`` therefore becomes a passable field rather than a
  derived one, so the app's hierarchy layer can still attribute power-budget
  rows to the box they came from.

Docstrings below keep their antennaknobs vocabulary where it names the
CALLER's contract rather than anything here: ``build_wires()`` tuples,
``designs/...`` showcases, ``station``/``schematic``/``touchstone``/
``ferrite`` modules, and `Instance`'s dotted-node convention all live in
antennaknobs, which is the consumer of this module.
"""

from __future__ import annotations

import math
import numbers
from dataclasses import KW_ONLY, dataclass, field, replace
from typing import Optional, Protocol, Union

import numpy as np

from ._reduce import _series_rlc_impedance


@dataclass(frozen=True)
class Cable:
    """Catalog entry for a feedline type: characteristic impedance, velocity
    factor, and matched-loss coefficients (dB/100 ft = k1·√f_MHz + k2·f_MHz).

    Promoted in momwire#456 ws2 from an antennaknobs catalog record to the
    FORMAL line spec `TL.from_cable` accepts: momwire ships no cable table,
    so a caller resolves whatever names it has against its own catalog and
    hands the resulting `Cable` down. The ``CABLES`` dict stays in
    antennaknobs."""

    z0: float
    vf: float
    k1: float
    k2: float


@dataclass(frozen=True)
class PortOnWire:
    """Real port ON a wire of the geometry: a delta gap on the wire whose
    `build_wires()` tuple carries that label as its 5th element. By default
    the port's own `name` is the wire's label and the gap sits at the wire's
    MIDDLE (momwire: the arclength midpoint; PyNEC: segment (n_seg+1)//2 —
    identical placement for odd segment counts, which named port wires should
    therefore use). A port must interrupt a CURRENT PATH, which is why the
    middle is the default and why an endpoint used to be refused outright —
    but an endpoint has a current path exactly when the wire END STANDS IN THE
    GROUND PLANE (momwire#1135). That is the ground-contact feed: the image
    supplies the other side of the gap, `tests/test_contact_nec5_lane.py`
    drives its base-fed monopoles at ``feed_arclength=0.0`` and certifies them
    against NEC-5 over five grounds and five densities, and
    ``momwire.dropin.nec5.serve`` places a deck's contact feed there. A FREE wire
    end still has nothing to interrupt — the current is zero there — and this
    type cannot tell the two apart, because ground is not in its vocabulary.
    So the endpoints are ADMITTED here and the physics is gated where the
    ground is known; see the refusal note on `at` below.

    ``wire`` and ``at`` put it elsewhere (momwire#1059). ``wire`` names the
    geometry wire when that differs from the port's name, which is how one
    wire carries several ports: a NEC deck's feed and its `LD` loads, say.
    ``at`` is a position along that wire as an arclength FRACTION from its
    authored ``p0``, in the CLOSED interval [0, 1]; None is the middle. The
    endpoints mean the ground-contact feed above, and asking for one at a free
    end is a physics error this type does not catch — the solver does, once it
    knows where the ground is. A fraction
    survives a length knob and a remesh. Turning it into a site a given mesh
    can carry is the caller's job (antennaknobs chooses segment counts per
    solver), and every solver reports where each feed actually landed
    (``feed_placements()``), so a feed never moves silently.

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
    wire: Optional[str] = None
    at: Optional[float] = None

    def __post_init__(self):
        if self.wire is not None and not (isinstance(self.wire, str) and self.wire):
            raise ValueError(
                f"PortOnWire wire must be a non-empty wire name, got {self.wire!r}"
            )
        if self.at is None:
            return
        if (
            isinstance(self.at, bool)
            or not isinstance(self.at, numbers.Real)
            or not math.isfinite(self.at)
            or not 0.0 <= self.at <= 1.0
        ):
            raise ValueError(
                f"PortOnWire at is an arclength fraction in [0, 1], got {self.at!r}"
            )
        if self.distributed:
            raise ValueError(
                "PortOnWire(distributed=True) spans its whole wire, so it takes no `at`"
            )
        object.__setattr__(self, "at", float(self.at))

    @property
    def wire_name(self) -> str:
        """The geometry wire this port sits on: ``wire``, else the port's name."""
        return self.name if self.wire is None else self.wire


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


@dataclass(frozen=True)
class PortAtVertex:
    """SERIES port at a wire ENDPOINT's junction (issue #898) — the apex
    feed: a delta-gap voltage inserted in the current path THROUGH the
    node, in series with the named wire's connection to it. Feeding an
    inverted vee at its exact vertex — no bridge wire — is this port,
    and it is the model NEC-5 users build natively (``EX`` at a knot).

    NOT `PortAtEnd`, deliberately: that port is momwire's #172 junction
    port — the node's KCL row promoted to a port, a SHUNT/common-mode
    attachment whose drive injects net current INTO the node (right for
    ground contacts and `BalancedLine` terminals). For a series-fed
    two-wire apex the KCL-row port's current reads zero by symmetry —
    the two ports answer different physics questions, which is why this
    is a separate type and not a flag.

    ``wire`` names a `build_wires()` tuple (names must be unique);
    ``end`` picks its authored ``"p0"`` or ``"p1"`` endpoint, which must
    coincide with at least one other wire end (a vertex needs a through
    path — a lone conductor end is `PortAtEnd`'s job). The port current
    is the current flowing from the node INTO the named wire, so at a
    two-wire vertex the wire choice does not change the impedance; at a
    junction of degree ≥ 3 it names which arm the gap separates, exactly
    as NEC-5's tag/segment/end addressing does. No gap is cut in the
    wire; the name identifies geometry only.

    momwire resolves it to a `node_gaps` series feed (momwire#305);
    NEC-5 to its native knot source. NEC-2-shaped engines
    (`PyNECEngine`, deck export) refuse by name — NEC-2 has no end
    source, and the honest near-miss (the short-bridge idiom) is a
    DIFFERENT model the user must choose explicitly."""

    wire: str
    end: str = "p1"

    def __post_init__(self):
        if self.end not in ("p0", "p1"):
            raise ValueError(f"PortAtVertex end must be 'p0' or 'p1', got {self.end!r}")


Port = Union[PortOnWire, PortOnWireFloating, PortAtEnd, PortAtVertex, PortVirtual]


@dataclass(frozen=True)
class TL:
    """Transmission line between two ports — lossless by default, lossy when
    matched-loss coefficients are given (issue #297).

    Everything after the two port names is KEYWORD-ONLY (momwire#1792):
    ``TL("rig", "feed", z0=50.0, length=10.0, vf=0.82, k1=0.27, k2=0.0055)``.
    Every slot takes a number, so a positional call that put the cable's
    numbers in another order (z0, length, vf, k1, k2) used to solve wrong
    without a word; now it raises TypeError. The ports stay positional.

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
    `TL.from_cable()` for real cables. A lossy line's characteristic
    impedance is complex, z0·(1 − jα/β), as EZNEC's is (momwire#1706); z0
    names the lossless one.

    k0: a constant term, matched loss [dB per 100 ft] = k0 + k1·√f + k2·f,
        the conductors' DC resistance. Default 0.0, which leaves every line
        as it was.

    skin: solve the line as AC6LA's "Johnson" transmission-line model, the
    one TLDetails, Zplots, AutoEZ and SimNEC use for their K0K1K2 cables.
    Each coefficient gives a per-length element: R_dc = 2·z0·α₀ from k0,
    R_hf = 2·z0·α₁ from k1, G = 2·α₂/z0 from k2, with L and C from z0 and
    vf. The conductor's internal impedance Z_int = √(R_dc² + [R_hf·(1 + j)]²)
    carries the skin effect's reactance (ωLᵢ = R at high frequency, none at
    DC), and γ = √((Z_int + jωL)(G + jωC)), Zc = √((Z_int + jωL)/(G + jωC))
    exactly. The internal inductance lengthens the line as 1/√f, which no
    constant `vf` can say: 12 m of RG-58 at 3.55 MHz is 2.73 % longer than vf
    alone puts it. The α's are the table's, so the matched loss sits slightly
    below the table, as it does in those programs. With it, antennaknobs
    reproduces a SimNEC station's own trace to 3e-15 (antennaknobs#2200).
    Off by default, and off is the line exactly as before, which is EZNEC's
    lossy line (momwire#1706).
    """

    a: str  # port name
    b: str
    _: KW_ONLY
    z0: float
    length: float
    transposed: bool = False
    vf: float = 1.0
    k0: float = 0.0
    k1: float = 0.0
    k2: float = 0.0
    skin: bool = False

    def __post_init__(self):
        # A number here is always a slot slip (momwire#1792): a non-zero float
        # is truthy, so it would silently cross the line.
        if not isinstance(self.transposed, (bool, np.bool_)):
            raise TypeError(
                f"TL {self.a!r}->{self.b!r}: transposed must be True or False, "
                f"got {self.transposed!r} ({type(self.transposed).__name__}); "
                "a number here is usually a cable value in the wrong slot — "
                "pass z0=, length=, vf=, k1=, k2= by keyword"
            )
        if not isinstance(self.skin, (bool, np.bool_)):
            raise TypeError(
                f"TL {self.a!r}->{self.b!r}: skin must be True or False, "
                f"got {self.skin!r} ({type(self.skin).__name__})"
            )

    @classmethod
    def from_cable(cls, cable, a, b, length, transposed=False):
        """A `TL` with z0/vf/k1/k2 taken from a `Cable` spec, e.g.
        ``TL.from_cable(Cable(50.0, 0.80, 0.27, 0.0055), "rig", "feed",
        30.48)``.

        `cable` must BE a `Cable` (momwire#456 ws2), never a catalog name:
        momwire carries no cable table, so resolving a name is the caller's
        job — in antennaknobs, ``cable_from_catalog("RG-8X")`` over its
        ``CABLES`` dict.
        """
        if isinstance(cable, str):
            raise TypeError(
                f"TL.from_cable needs a Cable spec, not the name {cable!r}: "
                "momwire ships no cable catalog. Resolve the name where the "
                "catalog lives — antennaknobs has "
                f"`cable_from_catalog({cable!r})` — and pass the resulting "
                "Cable, or give z0/vf/k1/k2 to TL() directly."
            )
        c = cable
        return cls(
            a=a, b=b, z0=c.z0, length=length, transposed=transposed,
            vf=c.vf, k1=c.k1, k2=c.k2,
        )  # fmt: skip


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
class Through:
    """An ideal zero-impedance link between two nodes: a wire (AK#2270).

    It holds v_a = v_b with the branch current a real unknown, so the two
    nodes stay distinct in the MNA system and a measurement plane can sit
    on either side of the link. That is what an alias cannot do: merging
    the nodes would put a shunt hung on one side across the other (the
    AK#1679 defect). It is not a source and burns nothing, so it has no
    power-budget row.

    The SimNEC importer joins a .ssn's blocks with these. Before AK#2270 it
    used ``Transformer(a, b, n=1.0)``, which stamps the same row; `Through`
    is the explicit element, whose meaning does not ride on a balun's
    defaults. Reducer-only, like `Transformer`: NEC has no zero-impedance
    card."""

    a: str
    b: str


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


class AdmittanceData(Protocol):
    """What a measured-data branch needs from its ``data``: a port count
    (validated at construction) and the short-circuit admittance matrix at a
    solve frequency (what the reducer stamps).

    :class:`~antennaknobs.touchstone.Touchstone` is the canonical
    implementation. Typing the branches to this protocol instead of that
    class keeps the circuit spec free of the Touchstone parser — the parser
    and its file reading stayed behind in antennaknobs when the circuit core
    moved down here (momwire#456 ws2), so there is no parser in momwire and
    this protocol IS the contract a measured-data branch is written to."""

    @property
    def nports(self) -> int: ...

    def y_at(self, f_hz: float) -> np.ndarray:
        """Admittance matrix (siemens, ``nports × nports``) at ``f_hz``."""
        ...


@dataclass(frozen=True)
class TouchstoneLoad:
    """A measured / vendor 1-port (``.s1p``) as a frequency-dependent load
    (issue #593) — a node-to-datum admittance the reducer stamps at each solve
    frequency by interpolating the Touchstone data. Use it to terminate the
    model with a *measured* antenna feedpoint (NanoVNA/VNA) or a real load
    instead of an ideal one. The admittance is ``y = 1/Z(f)`` from the file, so
    it is the measured-data sibling of a 1-port ``Admittance`` / ``Shunt``.

    ``data`` is any 1-port `AdmittanceData` — in practice a
    :class:`~antennaknobs.touchstone.Touchstone` (see ``read_touchstone``).
    Works on both engines (post-MoM reducer math)."""

    port: str
    data: AdmittanceData

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

    ``data`` is any 2-port `AdmittanceData` — in practice a
    :class:`~antennaknobs.touchstone.Touchstone` (see ``read_touchstone``).
    Works on both engines (post-MoM reducer math)."""

    a: str
    b: str
    data: AdmittanceData

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
    differential behaviour is untouched. ``_reduce.balanced_admittance_4x4``
    is the closed 4×4 form of the same thing, kept as the oracle. A lossless
    line at exactly k·vf·λ/2 is an ordinary
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

    Constructing one from the line's physical dimensions instead of a spool
    label lives with the wire catalogs it needs, in antennaknobs
    (``BalancedLine.from_geometry`` / ``two_wire_params``): geometry
    resolution is app-side, and this class takes the resulting
    ``zdiff``/``vf`` like any other.
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
    Through,
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
    if hasattr(br, "a"):  # TL, TwoPort, Transformer, Through
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
    if hasattr(br, "a"):  # TL, TwoPort, Transformer, Through
        return replace(br, a=ren(br.a), b=ren(br.b))
    return replace(br, port=ren(br.port))


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
    """Complete FLAT network spec: what the engines stamp and reduce.

    ports:    dict mapping name → Port (real or virtual)
    branches: list of Branch (TL / Load / TwoPort / …) — plain branches, in
              stamping order
    sources:  list of Source (Driven / DrivenCurrent)
    branch_paths: optional per-branch attribution path, same length and order
              as ``branches`` ("" for a branch that belongs to no box). The
              reducer prefixes its power-budget labels with it, so a caller
              with an authoring hierarchy can group a sub-network's rows
              under the box they came from. Empty (the default) normalizes to
              all-"", and any other length raises.

    FLAT is the deliberate part (momwire#456 ws2): the `Composite`/`Instance`
    authoring hierarchy — namespaced internals, alias resolution, per-branch
    instance paths — stays in antennaknobs, which flattens BEFORE handing
    momwire a Network and passes the ``branch_paths`` its flattening
    computed. momwire does not adopt hierarchy; it validates and solves what
    it is given.

    The engine's job: assemble the antenna Y matrix at the real ports,
    pad to include virtual ports, stamp every branch, then reduce to the
    driven-port impedances.
    """

    ports: dict[str, Port]
    branches: list[Branch] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    branch_paths: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.branch_paths:
            self.branch_paths = [""] * len(self.branches)
        elif len(self.branch_paths) != len(self.branches):
            raise ValueError(
                f"branch_paths has {len(self.branch_paths)} entries for "
                f"{len(self.branches)} branches — it is the per-branch "
                "attribution path, so it must align one-to-one (or be empty)"
            )
        for name, port in self.ports.items():
            # A PortAtEnd / PortAtVertex is keyed by its PORT name alone; its
            # `wire` field names geometry, not the port (two such ports may
            # share a wire), so there is no redundant name field to
            # cross-check.
            if not isinstance(port, (PortAtEnd, PortAtVertex)) and port.name != name:
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
            n
            for n, p in self.ports.items()
            if isinstance(p, (PortOnWire, PortAtEnd, PortAtVertex))
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
