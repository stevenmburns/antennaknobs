"""Wire and cable stock: the physical-materials half of the old `network`
module (momwire#456 workstream 2, phases A and B).

`network.py` grew two unrelated populations: the circuit spec (ports,
branches, sources, `Network`), which moved down into `momwire.networks`,
and this — the catalog of physical wire and feedline stock
(`WireSpec`/`WIRES`, `CABLES`), the named `build_wires()` entry
(`Wire`/`as_wire`), the two-wire line geometry (`two_wire_params`,
`balanced_line_from_geometry`), and the named-wire/port cross-check
(`validate_named_wires_referenced`). None of it is circuit math; all of it
is geometry and engine-contract code that stays in antennaknobs.

This module is where physical STOCK is resolved to electrical numbers, so
it owns both name→spec resolvers the circuit types no longer carry:
`cable_from_catalog` (momwire's `TL.from_cable` takes a `Cable`, never a
name — momwire ships no catalog) and `balanced_line_from_geometry`
(momwire's `BalancedLine` has no `from_geometry`, because deriving zdiff/vf
from conductors needs `WIRES`).

Import compatibility: `antennaknobs.network` re-exports everything here, so
existing `from antennaknobs.network import Wire, CABLES, ...` imports keep
working unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple

# `Cable` is momwire's now — promoted in momwire#456 ws2 from a local catalog
# record to the FORMAL line spec `TL.from_cable` takes. Re-exported from here
# (and, through here, from `antennaknobs.network`) so the catalog's entries and
# every `from antennaknobs.network import Cable` keep their one type.
from momwire.networks import BalancedLine, Cable, PortAtEnd, PortAtVertex, PortOnWire

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


def cable_from_catalog(name):
    """The `CABLES` entry for `name` — e.g. ``cable_from_catalog("RG-8X")``,
    with the same unknown-key ergonomics as `wire_from_catalog`.

    This is the name→spec step `TL.from_cable` used to do for itself
    (momwire#456 ws2): the branch class lives in momwire, which ships no
    cable table, so the catalog lookup belongs here and the resulting `Cable`
    is what gets passed down::

        TL.from_cable(cable_from_catalog("RG-8X"), "rig", "feed", 30.48)
    """
    if name not in CABLES:
        raise KeyError(
            f"unknown cable {name!r}; available: {', '.join(sorted(CABLES))}"
        )
    return CABLES[name]


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


# ---------------------------------------------------------------------------
# Two-wire line geometry: physical stock → the electrical numbers a
# `BalancedLine` takes. Moved here from `network.py` in momwire#456 ws2 phase
# B — it resolves conductors out of `WIRES`, which is this module's business,
# and momwire's `BalancedLine` has no catalog to reach for.
# ---------------------------------------------------------------------------

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
    match the rest of the package. Use it when you know the *line* — "#14
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


def balanced_line_from_geometry(
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

        balanced_line_from_geometry(
            "t1", "t2", "a1", "a2",
            spacing=0.0254, length=20.0, conductor="18-awg-pvc",
        )

    ``spacing`` is centre-to-centre in metres. See :func:`two_wire_params`
    for the electrical model and, importantly, for what the insulation
    estimators can and cannot claim. ``k1``/``k2``/``zcomm`` pass straight
    through — geometry says nothing about matched loss or the common-mode
    path, which stay explicit.

    A plain function rather than ``BalancedLine.from_geometry`` (momwire#456
    ws2): the class lives in momwire now and has no catalog to resolve
    ``conductor`` against, so the constructor stays where `WIRES` is.
    """
    r1, ins1, er1 = _conductor_geometry(conductor)
    r2, ins2, er2 = (
        (None, None, None) if conductor2 is None else _conductor_geometry(conductor2)
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
    return BalancedLine(
        a1=a1, a2=a2, b1=b1, b2=b2, zdiff=zdiff, length=length,
        vf=vf, k1=k1, k2=k2, zcomm=zcomm,
    )  # fmt: skip


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
    verbatim. ``n_seg`` may also be a :class:`GradedSegments` (a wire
    meshed geometrically toward one end) — always built via
    :func:`graded_wire`, never by hand; generic consumers doing
    ``int(w[2])`` arithmetic must treat that case (isinstance-check it)
    or refuse it by name.

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


class GradedSegments(NamedTuple):
    """``n_seg`` spelling for a wire meshed geometrically toward one end
    (momwire#674's node-grading recipe, promoted to a first-class
    spelling by the buried-radial default-mesh fix).

    The wire stays ONE ``build_wires()`` entry and ONE polyline edge
    chain: `flat_wires_to_polylines` expands it into interior vertices
    with per-edge counts INSIDE its polyline, so grading can never
    change the junction topology — the defect hand-split wires have on
    coincident bundles, where every shared split point mints a spurious
    KCL row (measured on the buried screen: 8-member junctions at every
    graded vertex).

    ``fracs``: interior vertex positions as fractions of the wire length
    measured from ``p0``, strictly increasing in (0, 1). ``counts``:
    per-sub-edge segment counts, ``p0 → p1`` order, one longer than
    ``fracs``. Build these with :func:`graded_wire` rather than by hand.

    A graded wire is structural only — the geometry walk rejects one
    carrying an excitation or a port name (a delta gap inside a graded
    chain would re-mesh the feed model; see the buried-radial builder's
    feed-gap note).

    SCOPE-FROZEN (maintainer decision, 2026-08-28, PR #1024): this
    spelling has ONE consumer (the buried-radial vertical's default
    mesh) and stays exactly this size until a second consumer exists.
    Extensions each have a recorded unfreeze trigger — card-engine
    expansion via :meth:`subdivide` (a graded design needing NEC
    export), bend-grading (someone chasing the measured hub-bend
    0.1–0.2 Ω class), momwire-side knot multiplicity (a second
    slope-freedom consumer; momwire#449's closure records it) — and
    every unfreeze starts with a named consumer, an issue, and a
    measurement, in that order. Do not grow this spelling ahead of
    that.
    """

    fracs: tuple
    counts: tuple

    def subdivide(self, p0, p1):
        """Expand to explicit ``(q0, q1, n)`` sub-wires — for card-based
        consumers (the .nec exporter) where per-wire uniform segment
        counts are the native spelling anyway."""
        import numpy as _np

        a = _np.asarray(p0, dtype=float)
        b = _np.asarray(p1, dtype=float)
        cuts = [a] + [a + f * (b - a) for f in self.fracs] + [b]
        return [
            (tuple(q0), tuple(q1), int(n))
            for q0, q1, n in zip(cuts, cuts[1:], self.counts)
        ]


def graded_wire(
    p0,
    p1,
    *,
    toward,
    h_node=0.0125,
    growth=4.0,
    per_panel=2,
    rest_h=None,
    name=None,
    spec=None,
) -> Wire:
    """A structural wire graded toward one end (``toward`` = ``"p0"`` or
    ``"p1"``): panel boundaries at ``h_node * growth**k`` from the graded
    end (the #674 recipe — its defaults reproduce the measured-converged
    6.25 mm node mesh: boundaries 12.5 mm, 50 mm, … capped at the wire
    length), ``per_panel`` segments per panel. ``rest_h`` (metres), when
    given, meshes the final far panel at that segment length instead —
    pass the design's own segment length so a long wire's far end stays
    at catalog density.
    """
    import math as _math

    length = _math.dist(tuple(p0), tuple(p1))
    if toward not in ("p0", "p1"):
        raise ValueError(f"toward must be 'p0' or 'p1', got {toward!r}")
    if not 0 < h_node < length:
        raise ValueError(f"h_node {h_node} outside (0, wire length {length:.4g})")
    bounds = []
    b = h_node
    while b < length * (1 - 1e-9):
        bounds.append(b)
        b *= growth
    counts = [per_panel] * (len(bounds) + 1)
    if rest_h is not None:
        rest_len = length - (bounds[-1] if bounds else 0.0)
        counts[-1] = max(per_panel, round(rest_len / rest_h))
    if toward == "p1":
        fracs = tuple(1.0 - b / length for b in reversed(bounds))
        counts = list(reversed(counts))
    else:
        fracs = tuple(b / length for b in bounds)
    return Wire(
        tuple(p0),
        tuple(p1),
        n_seg=GradedSegments(fracs=fracs, counts=tuple(int(c) for c in counts)),
        name=name,
        spec=spec,
    )


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
    # The port types are imported at module scope (from momwire.networks —
    # see the header). Until momwire#456 ws2 phase B they had to be imported
    # here at CALL time, because they lived in `antennaknobs.network`, which
    # imports this module for its compatibility re-exports; the circuit half
    # moving down dissolved that cycle.
    gap_names = {n for n, p in network.ports.items() if isinstance(p, PortOnWire)}
    # End and vertex ports both name geometry without cutting a gap, so
    # they share one rule against gap ports (a wire may carry BOTH an end
    # and a vertex port — on different or even the same endpoint, where
    # momwire's own shunt+series conflict rule then applies).
    end_names = {
        p.wire
        for p in network.ports.values()
        if isinstance(p, (PortAtEnd, PortAtVertex))
    }
    both = sorted(gap_names & end_names)
    if both:
        raise ValueError(
            f"wire name(s) {both} are referenced by both a PortOnWire and a "
            "PortAtEnd/PortAtVertex — a gap port cuts a delta gap in the "
            "wire while an end or vertex port must leave it gapless "
            "(issues #579, #898); use separate wires."
        )
    orphaned = sorted(set(named_wires) - {None} - gap_names - end_names)
    if orphaned:
        raise ValueError(
            f"named wire(s) {orphaned} are not referenced by any PortOnWire, "
            "PortAtEnd or PortAtVertex in build_network(); a named wire "
            "becomes a port edge, and an unreferenced port is an OPEN gap "
            "that cuts the wire there (issue #578). Reference each name in "
            "Network.ports, or drop the name."
        )
