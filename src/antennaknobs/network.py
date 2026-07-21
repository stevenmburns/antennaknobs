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

from dataclasses import dataclass, field, replace
from typing import NamedTuple, Union


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


# Deprecated alias — the pre-rename class name ("edge" meant a wire-graph
# edge, i.e. one build_wires() tuple, but read as "wire end"). Kept so any
# externally-authored design importing it keeps working.
PortAtEdge = PortOnWire

Port = Union[PortOnWire, PortVirtual]


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

    ``spec=None`` means "the design default": engines fall back to
    ``build_wire_material()``. Precedence, defined once: an explicit
    per-wire ``spec`` wins; the web ``wire_radius`` override only moves
    the default. Transforms, array placement, and scale knobs never scale
    a ``spec`` — it describes the physical wire stock the antenna is
    built from, not the geometry.
    """

    p0: tuple
    p1: tuple
    n_seg: int
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


Branch = Union[TL, Load, TwoPort, Shunt, Transformer, Admittance]


def _branch_port_refs(br):
    """Port names a branch references, regardless of branch type."""
    if isinstance(br, Admittance):
        return tuple(br.ports)
    if hasattr(br, "a"):  # TL, TwoPort, Transformer
        return (br.a, br.b)
    return (br.port,)  # Load, Shunt


def _rewrite_branch(br, ren):
    """Copy of ``br`` with every port reference passed through ``ren``."""
    if isinstance(br, Admittance):
        return replace(br, ports=tuple(ren(p) for p in br.ports))
    if hasattr(br, "a"):  # TL, TwoPort, Transformer
        return replace(br, a=ren(br.a), b=ren(br.b))
    return replace(br, port=ren(br.port))


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


def _expand_instance(inst, formal_to_final, prefix, flat, paths, aliases, internals):
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

    for item in inst.of.branches:
        if isinstance(item, Instance):
            child_map = {f: resolve(a) for f, a in item.portmap.items()}
            _expand_instance(
                item, child_map, prefix + item.name + ".",
                flat, paths, aliases, internals,
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
        real = [n for n in members if isinstance(ports.get(n), PortOnWire)]
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

    def __post_init__(self):
        if self.branch_paths:
            raise ValueError("branch_paths is derived — do not pass it")
        self._expand_instances()
        for name, port in self.ports.items():
            if port.name != name:
                raise ValueError(
                    f"port dict key {name!r} doesn't match Port.name {port.name!r}"
                )
        port_names = set(self.ports)
        for br in self.branches:
            for ref in _branch_port_refs(br):
                if ref not in port_names:
                    raise ValueError(f"branch {br!r} references unknown port {ref!r}")
        for src in self.sources:
            if src.port not in port_names:
                raise ValueError(f"source {src!r} references unknown port")
        if not self.sources:
            raise ValueError("Network has no driven sources")

    def _expand_instances(self):
        """Flatten `Instance` items (issue #489): namespace internals,
        resolve aliases, stamp per-branch instance paths."""
        flat, paths, alias_pairs, internals = [], [], [], set()
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
                    flat, paths, alias_pairs, internals,
                )  # fmt: skip
            else:
                flat.append(item)
                paths.append("")
        self.branches = flat
        self.branch_paths = paths
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
