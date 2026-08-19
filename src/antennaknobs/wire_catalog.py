"""Wire and cable stock: the physical-materials half of the old `network`
module (momwire#456 workstream 2, phase A).

`network.py` grew two unrelated populations: the circuit spec (ports,
branches, sources, `Network`) that is destined to move down into
`momwire.networks`, and this — the catalog of physical wire and feedline
stock (`WireSpec`/`WIRES`, `Cable`/`CABLES`), the named `build_wires()`
entry (`Wire`/`as_wire`), and the named-wire/port cross-check
(`validate_named_wires_referenced`). None of it is circuit math; all of it
is geometry and engine-contract code that stays in antennaknobs when the
circuit half moves.

Import compatibility: `antennaknobs.network` re-exports everything here, so
existing `from antennaknobs.network import Wire, CABLES, ...` imports keep
working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple


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
    # The port types live in the circuit module, which imports THIS module
    # at scope for the compatibility re-exports — importing back at call
    # time keeps the pair acyclic (the same bridge `touchstone._inv` uses).
    # It dissolves in momwire#456 ws2 phase B, when the circuit half moves
    # to momwire.networks and this becomes an ordinary top-level import.
    from .network import PortAtEnd, PortAtVertex, PortOnWire

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
