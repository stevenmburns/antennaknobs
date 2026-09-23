"""Emit a SimNEC (``.ssn``) circuit for a design (issues #600 / #604).

SimNEC (AE6TY) is a Java Smith-chart / station tool that embeds NEC2 behind an
in-house MNA solver. Its native circuit file is ``.ssn`` (XML). This module
lets an antennaknobs design — antenna-only, or a differential-only *station*
(antenna + feedline + tuner + transformer chain) — be round-tripped into
SimNEC for cross-validation, without the fiddly UI step of hand-entering
geometry or circuit values.
The read-side twin is :mod:`antennaknobs.simnec_import` (``parse_ssn`` /
``read_ssn``), which loads a ``.ssn`` back as wire geometry and station
branches.

How it works — the escape-hatch route
-------------------------------------
A SimNEC ``.ssn`` is a list of circuit ``<element>``s. For an antenna model the
canonical shape is three elements — ``LOAD`` / ``NETWORK`` / ``GENERATOR`` —
where the antenna lives inside the ``NETWORK`` element's escape-hatch ``<equ>``
script, expressed in SimNEC's NEC-portal daemon language:

    P1 w1 gnd;                         // the two circuit ports; EX drives P2
    P2 w2 gnd;
    NECUnits meters, meters;
    SommerfeldGround(0.0303, 20);      // (mhos, dielectric) == (sigma, eps_r)
    NECOptions.mhosPerMeter = Conductivities.copper;  // 0 = perfect wire
    NEC2                               // NEC cards go between NEC2 and NECEND
    GW 1 11 ...
    EX 0 1 6 0 1. 0.
    NECEND
    $GW_1.JamSegments(11);             // the deck's own count, per wire

We reuse :func:`antennaknobs.nec_export.export_nec` for the geometry, then keep
the ``GW`` / ``FR`` / ``EX`` cards and translate the rest into daemon
directives: the Generator's ``MHz`` carries the (sweepable) solve frequency;
``GN`` → the ground call; ``LD 5`` → ``NECOptions.mhosPerMeter`` (SimNEC's
NEC2 reader ignores LD cards, and takes one conductivity for the whole block,
so a design whose wires differ is refused — AK#1680). SimNEC ignores a lumped
``LD 0`` / ``LD 1`` load just the same, and silently (AK#1683), so each one is
written as SimNEC's own ``NECSource`` load on its ``$GW_<tag>`` wire — or, on
the fed segment, as a series circuit element at the feed — and an insulated
wire is refused (see :func:`_wire_loads`, :func:`_refuse_jacket`). SimNEC
treats a ``GW`` card's segment count as advisory and re-meshes, so each wire
also gets a ``$GW_<tag>.JamSegments(N)`` carrying the deck's count (AK#1680),
unless ``seg_per_wl`` is given: that knob asks for SimNEC's own mesh at
``NECOptions.segmentsPerWavelength``, for a convergence comparison, and
writes no JamSegments. ``FR`` is left in the deck too: a SimNEC 5.1a1-saved
``.ssn`` carries ``FR`` alongside a live ``G.MHz`` sweep, so it is harmless
(advisory) and matches SimNEC's own output.

**Why a written count can differ from the file's own (AK#1576).** A source
sitting at a wire JUNCTION — the deck's exact centre on an even-segment
feed wire, e.g. a 2-segment ``GW`` fed at 50% — has no NEC-2 card spelling:
NEC-2's ``EX`` addresses a whole segment, with no end code (unlike NEC-5's
``EX ... 2``, which addresses a segment END and so can sit exactly on a
knot). The importer's own feed-position rule (AK#1510: the exact position is
kept; re-mesh ≤2× to land a segment centre under it; never snap) already
resolves this on the way IN — a 2-segment centre feed reads as a 3-segment
one with the source on the middle segment, exactly on the physical centre —
and :func:`export_nec` (which this module's geometry comes from) writes that
resolved, PyNEC-coerced mesh. Writing the deck's OWN even count instead
(2 segments, source on segment 1) was tried and reverted: NEC-2 syntax then
places the source at 25% of the wire, not the junction — a snap at the
writer, the same mistake the importer's rule exists to forbid, and a
measurably different antenna (PyNEC's driving-point impedance moves ~4% on
the reported deck). :mod:`nec5_export` is the one writer that CAN keep the
file's own count for this wire, because NEC-5's end code reaches the
junction NEC-2 cannot address at all.

Scope
-----
Two export shapes:

**Antenna-only** designs (no ``build_network`` TL/virtual-driver station) —
issue #600, the original scope: the three-element LOAD / NETWORK / GENERATOR
cascade above.

**Differential-only stations** (issue #604, phase 2): designs whose
``build_network`` is a single generator→antenna ladder of transmission lines,
lumped L/C tuner arms, and ideal transformers. Each reducer branch maps to a
SimNEC circuit element in cascade order — ``TL`` → ``SERIES_TLINE``,
``TwoPort``/``Shunt`` L/C legs → ``SERIES_IND`` / ``SERIES_CAP`` /
``SHUNT_IND`` / ``SHUNT_CAP``, ideal ``Transformer`` → ``TRANSFORMER2`` —
and the antenna keeps the NEC-portal NETWORK block, driven at the station's
``PortOnWire`` feed.

**The fundamental limitation — enforced, not papered over.** SimNEC's
``SERIES_TLINE`` is purely differential: there is no common-mode (``zcomm``)
knob. Any design whose physics lives in the common mode — a
``BalancedLine`` with ``zcomm`` (issue #576), a ``FloatingBalun``
(issue #589), the balanced tuners built from them — **cannot be faithfully
represented in SimNEC circuit elements**, and this module raises
:class:`SsnUnsupported` (naming the offending branch) rather than silently
dropping the common mode and emitting a confidently-wrong ``.ssn``. The
Track-2 comparison (docs/status/2026-07-28-simnec-comparison-handoff.md) is
the proof: breaking symmetry fans AntennaKNoBs across ``zcomm`` while SimNEC
is stuck on one value.

.. note::
   The station element XML (parameter names ``Zo``/``VFnom``/``ft``/``k0``…,
   ``F``/``H``/``Q``/``@MHz``, ``Mdl``/``N``) is authored from the schema
   survey of a SimNEC 5.1a1-saved ``lastCircuit.ssn`` (issue #604), and
   load-validated in SimNEC 5.1a0 (2026-08-07): the ladder-tuner cascade
   loads with correct element values and reproduces the Track-1 rig-side
   impedance at 7.1 MHz. ``TRANSFORMER2``'s ``N`` was found to read
   antenna-side:generator-side — the inverse of our ``Transformer`` ``n`` —
   so the exporter emits the reciprocal (see the emission comment).
   Also validated on 5.1a0: ``Q = 0`` means "ideal / no loss" (the SimSmith
   convention), and the ``k0``/``k1``/``k2`` loss coefficients round-trip a
   load/save intact with the recomputed ``/100f`` matching the coefficient
   formula. The ``SERIES_TLINE`` ``Mdl`` is pinned to ``k0k1k2`` explicitly:
   left unset it defaults to ``simplified``, which drives loss from the
   single ``/100f @frq`` point (right at the export frequency, wrong across
   a SimNEC-side sweep). The ``material`` params 5.1a0 adds on save are
   inert defaults for the physical-geometry loss models.

Licensing
---------
SimNEC is proprietary freeware. This module emits SimNEC's *open file format*
for interoperability (like emitting a NEC deck or a Touchstone file); it does
**not** copy SimNEC's bundled circuit files or assets. The daemon directives are
the documented NEC-portal API. The surrounding XML scaffold in
:data:`_SSN_TEMPLATE` is authored here (clean-room) from the format's structure.

.. note::
   Reconciled against a SimNEC 5.1a1-saved ``.ssn``: the root ``SimNEC1p0``,
   the ``SimNEC:<version>`` ``XMLVersionControl`` string, the Generator's ``Zo``
   impedance tag, and the retained ``FR`` card all match SimNEC's own output.
   The scaffold here is deliberately *minimal* (it omits SimNEC's display state
   — ``SPREADSHEET`` / charts / band menus — which SimNEC regenerates on load);
   a Windows load-test confirms SimNEC accepts that minimal subset. The Generator
   frequency sweep is off by default (SimNEC supplies its own range); pass
   ``sweep=(lo, hi)`` / ``--sweep`` to emit an enabled band.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from xml.sax.saxutils import escape as _xml_escape

from .auto_match import design_freq_mhz, find_tuners
from .engines._nec_wire import nec_wire_material
from .engines.pynec import DEFAULT_GROUND, WIRE_CONDUCTIVITY, PyNECEngine
from .nec_export import _gw, _num, export_nec
from .simnec_import import _RESISTIVITY_OHM_M
from .wire_catalog import gap_segment, port_at, port_wire
from .network import (
    TL,
    Admittance,
    Autotransformer,
    BalancedLine,
    Driven,
    FloatingBalun,
    Load,
    PortOnWire,
    Shunt,
    TouchstoneLoad,
    TouchstoneTwoPort,
    Transformer,
    TwoPort,
    _branch_port_refs,
    as_wire,
)

__all__ = ["export_ssn", "build_nec_portal_script", "SsnUnsupported"]


class SsnUnsupported(NotImplementedError):
    """The design (or one of its network branches) has no faithful SimNEC
    representation — most importantly the common-mode constructs
    (``BalancedLine.zcomm``, ``FloatingBalun``), which SimNEC's purely
    differential elements cannot express (issue #604). Subclasses
    ``NotImplementedError`` so phase-1 callers that treated "networked
    design" errors as a capability probe keep working unchanged. The
    message always names the offending construct and what to do about it."""


def _fmt(x: float) -> str:
    """Compact real for daemon directives (trim trailing zeros)."""
    return f"{float(x):g}"


def _ground_directive(ground) -> str | None:
    """Map an antennaknobs ground spec to a SimNEC daemon ground call, or
    ``None`` for free space. Note SimNEC's ``SommerfeldGround(mhos,
    dielectric)`` takes (sigma, eps_r) — the reverse of our
    ``("finite", eps_r, sigma)`` tuple. The WIRE conductivity is not a ground
    property; :func:`_conductivity_token` writes it (AK#1680).
    """
    if ground is None or ground == "free":
        return None
    if ground == "pec":
        return "PerfectGround();"
    if (
        isinstance(ground, tuple)
        and len(ground) == 3
        and ground[0] in ("finite", "finite-fast")
    ):
        _, eps_r, sigma = ground
        # SimNEC has no distinct reflection-coefficient ("finite-fast") ground;
        # both map to its Sommerfeld solve — the accurate model — which is also
        # what a validation run should compare against.
        return f"SommerfeldGround({_fmt(sigma)}, {_fmt(eps_r)});"
    if isinstance(ground, tuple) and len(ground) == 3 and ground[0] == "mininec":
        # SimNEC's own MININEC ground, same (mhos, dielectric) order (AK#1655).
        _, eps_r, sigma = ground
        return f"MiniNECGround({_fmt(sigma)}, {_fmt(eps_r)});"
    raise ValueError(f"unrecognised ground spec: {ground!r}")


def _conductivity_token(sigma: float | None) -> str:
    """The right-hand side of ``NECOptions.mhosPerMeter`` for a wire
    conductivity in S/m (None = perfect wire, which SimNEC spells 0).

    A value that IS one of SimNEC's ``Conductivities.<name>`` (the table
    :mod:`simnec_import` reads, so export and import are inverses) is written
    by name, as SimNEC's own files do; anything else as the shortest decimal
    that round-trips the float exactly (no ``+`` in the exponent)."""
    if sigma is None or sigma == 0.0:
        return "0"
    for name, rho in _RESISTIVITY_OHM_M.items():
        if math.isclose(sigma, 1.0 / rho, rel_tol=1e-12):
            return f"Conductivities.{name}"
    return repr(float(sigma)).replace("e+", "e")


def _uniform_conductivity(sigmas: dict[int, float | None]) -> float | None:
    """The one conductivity every wire shares (tag → S/m, None = perfect).

    SimNEC's NEC2 deck reader takes GW / GS / EX / NT and ignores every other
    card (NECPortal manual, "NEC2 Decks"), so an ``LD 5`` inside the block is
    not read: the conductivity has to be ``NECOptions.mhosPerMeter``, one
    value for the whole block. A design whose wires differ is refused, naming
    them, rather than written with one of its conductivities applied to all
    (AK#1680). The manual documents a per-wire ``$wire.Mhos(...)``, but not on
    a NEC2 block's ``$GW_<tag>`` wires, and it is unverified there."""
    values = set(sigmas.values())
    if len(values) <= 1:
        return next(iter(values), None)
    by_value: dict[float | None, list[int]] = {}
    for tag, v in sigmas.items():
        by_value.setdefault(v, []).append(tag)
    groups = "; ".join(
        ("perfect" if v is None else f"{v:g} S/m")
        + f" on wire{'s' if len(t) > 1 else ''} {', '.join(map(str, t))}"
        for v, t in by_value.items()
    )
    raise SsnUnsupported(
        f"the wires' conductivities differ ({groups}); SimNEC's NEC2 block "
        "takes one NECOptions.mhosPerMeter for every wire and ignores LD 5 "
        "cards, so the design is not exported rather than written with one "
        "conductivity applied to all (AK#1680)"
    )


def _jam_segments(cards) -> list[str]:
    """``$GW_<tag>.JamSegments(N);`` for every ``GW`` card, so SimNEC meshes
    each wire the way the deck (and so antennaknobs) did (AK#1680). SimNEC
    names a NEC2 block's wires ``$GW_<tag>`` after ``NECEND``; this is the
    spelling in AC6LA's own SimNEC files. The manual calls JamSegments a
    strong suggestion, not a guarantee: it does not suppress SimNEC's
    auto-segmentation (growth-rate / junction splits), so the counts SimNEC
    reports are still worth a look."""
    out = []
    for c in cards:
        parts = c.split()
        if parts[:1] == ["GW"]:
            out.append(f"$GW_{int(parts[1])}.JamSegments({int(parts[2])});")
    return out


def _nec_cards_for_portal(deck: str) -> list[str]:
    """Keep the cards SimNEC's NEC block wants: geometry (``GW``), frequency
    (``FR``) and excitation (``EX``). No ``LD`` card of any type: SimNEC's
    NEC2 reader takes GW / GM / GS / EX / NT and ignores the rest (NECPortal
    manual, "NEC2 Decks"), and Steve confirmed on SimNEC 5.3 that lumped
    ``LD 0`` / ``LD 1`` loads were dropped with no word (AK#1683). Lumped
    loads are written by :func:`_wire_loads` instead.

    ``FR`` is kept because SimNEC's own NEC-portal decks carry it — even while
    the Generator sweeps ``G.MHz`` (the deck's ``FR`` is advisory; the solve
    frequency comes from the Generator). Confirmed against a SimNEC 5.1a1-saved
    ``.ssn`` (``FR 0 1 0 0 <f> 0`` present alongside a live G.MHz sweep).

    Dropped: ``CM``/``CE``/``GE``/``RP``/``XQ``/``EN`` (structural), ``GN`` (→
    ground call), and every ``LD``.
    """
    # Group into canonical NEC order — geometry, then FR, then EX — to
    # match a SimNEC 5.1a1-saved deck (GW … FR … EX) rather than export_nec's
    # emission order, which puts EX before FR.
    geom: list[str] = []
    fr: list[str] = []
    ex: list[str] = []
    for raw in deck.splitlines():
        s = raw.strip()
        if s.startswith("GW "):
            geom.append(s)
        elif s.startswith("FR "):
            fr.append(s)
        elif s.startswith("EX "):
            ex.append(s)
        # LD cards are not kept (see above): LD 0 / 1 / 4 lumped loads are
        # written by `_wire_loads`, LD 5 as NECOptions.mhosPerMeter, and
        # LD 2 (the jacket) is never written, because `jacket_pair=False`.
    return geom + fr + ex


def _val(x: float) -> str:
    """A component value for a load expression: twelve significant figures
    (a float's last-bit noise, 4.9999999999999996e-06, is not a value anyone
    wrote), with no ``+`` in the exponent (SimNEC's own scripts write
    ``1e-3``)."""
    return f"{float(x):.12g}".replace("e+", "e")


def _load_legs(br: Load) -> tuple[float, float, float]:
    """(R, L, C) of a lumped RLC ``Load``, 0 for an absent leg (the LD card's
    own convention: 0 means the element is not there)."""
    return tuple(float(v) if v is not None else 0.0 for v in (br.r, br.l, br.c))


def _load_expr(br: Load) -> str:
    """The load as a SimNEC impedance expression, in the N-block functions of
    the Anvil manual ("Caps, Inductors, and Resistors"): ``L(henries)``,
    ``C(farads)``, a bare number for ohms, ``+`` for series and ``|||`` for
    parallel; a fixed ``z`` as ``R + j*X``. Evaluated per frequency, like the
    LD card it replaces."""
    if br.z is not None:
        z = complex(br.z)
        sign = "-" if z.imag < 0 else "+"
        return f"{_val(z.real)} {sign} j*{_val(abs(z.imag))}"
    r, l, c = _load_legs(br)
    terms = []
    if r:
        terms.append(_val(r))
    if l:
        terms.append(f"L({_val(l)})")
    if c:
        terms.append(f"C({_val(c)})")
    return (" ||| " if br.parallel else " + ").join(terms)


def _wire_loads(loads, feed_loc, n_segs, freq_mhz: float):
    """Lumped ``Load`` branches in the spelling SimNEC solves (AK#1683).

    ``loads`` is ``[(branch, name, (tag, seg))]``, ``feed_loc`` the fed
    ``(tag, seg)``, ``n_segs`` tag → the GW segment count. Returns
    ``(statements, feed_elements)``.

    SimNEC ignores LD cards in a NEC2 block (NECPortal manual, "NEC2 Decks":
    every card but GW / GM / GS / EX / NT is ignored), so a load is written
    the way its manual places one ("Loading": "The NECSource() function is
    used to place loads at specific places along a wire"), in the form
    AC6LA's EZNEC-to-SimNEC files use for a deck's own ``LD`` card — an
    N-block ``R`` component carrying the impedance, attached to the GW wire
    ``$GW_<tag>`` at a percentage of its length:

        R1 (L(5e-06) ||| C(6.46181018127e-12)) ld1a ld1b;  dcl Load1 = NECSource({ld1a,ld1b}, $GW_2, 50);

    The percentage is the load segment's centre, ``(seg - 1/2) / N``, and
    SimNEC re-meshes the wire so the load sits exactly there (the manual's
    "Source Placement"), whatever its own segmentation does to the count.

    A load on the FED segment cannot be written that way: SimNEC turns the
    ``EX`` card into a NECSource of its own at that place. There it is in
    series with the source, so the driving-point impedance is the antenna's
    plus the load's, exactly (NEC adds a segment load to the diagonal of the
    same row the gap voltage drives), and it is written as SimNEC's own
    series circuit elements between the antenna block and the generator:
    ``SERIES_IND`` / ``SERIES_CAP``, the two load-validated in SimNEC 5.1a0.
    A resistor, a fixed Z, or a parallel pair there is refused by name, as
    are a finite-Q load (R = ωL/Q re-derived per frequency) and a load that
    names no wire segment."""
    mk = _element_factory()
    statements: list[str] = []
    feed_elements: list[str] = []
    k = 0
    for br, name, (tag, seg) in loads:
        if br.ql is not None or br.qc is not None:
            raise SsnUnsupported(
                f"{name}: a finite-Q Load needs R = ωL/Q re-derived per "
                "frequency, which the export does not write"
            )
        if br.z is not None:
            if complex(br.z) == 0:
                continue
        elif not any(_load_legs(br)):
            continue
        if (tag, seg) == feed_loc:
            r, l, c = _load_legs(br)
            if br.z is not None or r or (br.parallel and l and c):
                raise SsnUnsupported(
                    f"{name}: this load sits on the fed segment, where SimNEC "
                    "places the EX source, so it can only be written as a "
                    "series circuit element at the feed, and only a series L "
                    "and/or C has one; move the load off the feed segment"
                )
            if l:
                feed_elements.append(
                    mk("SERIES_IND", "LD", [("H", _val(l)), *_q_params(None, freq_mhz)])
                )
            if c:
                feed_elements.append(
                    mk("SERIES_CAP", "LD", [("F", _val(c)), *_q_params(None, freq_mhz)])
                )
            continue
        k += 1
        pct = (seg - 0.5) / n_segs[tag] * 100.0
        statements.append(
            f"R{k} ({_load_expr(br)}) ld{k}a ld{k}b;  "
            f"dcl Load{k} = NECSource({{ld{k}a,ld{k}b}}, $GW_{tag}, {_val(pct)});"
        )
    return statements, feed_elements


def _refuse_jacket(eng) -> None:
    """Refuse a design with an insulated wire, by name (AK#1683 item 3).

    The export writes each conductor's bare radius (``jacket_pair=False``)
    and no LD 2, so a jacket would otherwise be silently missing. SimNEC has
    its own ``$wire.Insulation(thickness, permittivity, lossTangent)``, but
    its default is the K6OIK correction, not the coaxial-shell a′ + L′ model
    the engines here use, so writing it would be a different wire model under
    our name; that mapping is a follow-up."""
    tags = []
    for tag, t in enumerate(eng.tups, start=1):
        spec = as_wire(t).spec
        eff = spec if spec is not None else eng._wire_spec
        if eff is not None and getattr(eff, "insulation_radius", None):
            tags.append(tag)
    if tags:
        raise SsnUnsupported(
            f"wire{'s' if len(tags) > 1 else ''} {', '.join(map(str, tags))} "
            "carry an insulation jacket, which the SimNEC export does not "
            "write (SimNEC ignores LD cards, and its Insulation() correction "
            "is not the model the engines here use); export the design with "
            "bare wire"
        )


def _feed_loc(cards) -> tuple[int, int] | None:
    """The ``(tag, seg)`` the block's one ``EX`` card drives."""
    for c in cards:
        parts = c.split()
        if parts[:1] == ["EX"]:
            return int(parts[2]), int(parts[3])
    return None


def _default_block_name(builder) -> str:
    """SimNEC shows the script's first //comment as the block's display name,
    which only fits ~12 chars before the font shrinks to unreadable. So use
    the SHORT leaf name: the design's module leaf (e.g. "invvee") for a real
    design, or the class qualname for a script-defined (__main__) builder."""
    mod = type(builder).__module__
    qual = type(builder).__qualname__
    if mod != "__main__" and qual == "Builder":
        return mod.rsplit(".", 1)[-1]
    return qual


def _portal_wrap(cards, *, name, ground, seg_per_wl, conductivity, loads=()) -> str:
    """The NEC-portal daemon script (the ``<equ>`` body): comment header,
    ports/units/ground/conductivity/mesh directives, then ``cards`` between
    NEC2/NECEND, then a ``JamSegments`` per wire — unless ``seg_per_wl`` asks
    for SimNEC's own mesh, which is what that knob is for — then the lumped
    loads' statements (:func:`_wire_loads`)."""
    ground_call = _ground_directive(ground)
    lines = [
        f"//{name}",
        "// generated by antennaknobs.simnec_export",
        "P1 w1 gnd;",
        "P2 w2 gnd;",
        "NECUnits meters, meters;",
    ]
    if ground_call:
        lines.append(ground_call)
    lines.append(f"NECOptions.mhosPerMeter = {_conductivity_token(conductivity)};")
    if seg_per_wl is not None:
        lines.append(f"NECOptions.segmentsPerWavelength = {int(seg_per_wl)};")
    lines.append("NEC2")
    lines.extend(cards)
    lines.append("NECEND")
    if seg_per_wl is None:
        lines.extend(_jam_segments(cards))
    lines.extend(loads)
    return "\n".join(lines)


def build_nec_portal_script(
    builder,
    *,
    freq_mhz: float,
    ground=DEFAULT_GROUND,
    seg_per_wl: int | None = None,
    name: str | None = None,
) -> str:
    """The SimNEC NEC-portal daemon script (the ``<equ>`` body) for an
    antenna-only ``builder``: :func:`_antenna_portal`'s script. A load on the
    fed segment is a circuit element outside the script (see
    :func:`_wire_loads`), so a design with one is refused here; use
    :func:`export_ssn`, which writes the whole circuit."""
    script, feed_elements = _antenna_portal(
        builder, freq_mhz=freq_mhz, ground=ground, seg_per_wl=seg_per_wl, name=name
    )
    if feed_elements:
        raise SsnUnsupported(
            "a load on the fed segment is written as a circuit element next "
            "to the antenna block, which the script alone cannot carry; use "
            "export_ssn for the whole circuit"
        )
    return script


def _antenna_portal(
    builder,
    *,
    freq_mhz: float,
    ground=DEFAULT_GROUND,
    seg_per_wl: int | None = None,
    name: str | None = None,
) -> tuple[str, list[str]]:
    """The NEC-portal script for an antenna-only ``builder``, and the series
    circuit elements for any load on its fed segment (:func:`_wire_loads`).
    Reuses :func:`export_nec` for the geometry,
    unchanged (AK#1576 considered and rejected rewriting a deck-faithful
    even-count centre-fed wire's ``GW``/``EX`` back to the file's own count:
    NEC-2 syntax has no end-code, so "segment 1 of 2" IS a source at 25% of
    the wire, not at the junction — a SNAP the project's feed-position rule
    (AK#1510: keep the exact position; re-mesh ≤2× to land a segment centre
    under it; never snap) forbids at the writer just as much as at the
    importer. ``export_nec``'s PyNEC-coerced mesh (the SAME re-mesh AK#1510
    already applies on import) is the sanctioned spelling, so this writer
    keeps it verbatim; only :mod:`nec5_export` can keep the deck's OWN count,
    because NEC-5's end code addresses the junction exactly, which NEC-2 (and
    therefore SimNEC) cannot.
    """
    # jacket_pair=False: SimNEC ignores the LD cards, and the equivalent
    # radius without its LD 2 inductance would be half of the jacket's model
    # (issue #1523). The conductor's own radius keeps it a bare-wire model,
    # and a jacketed design is refused rather than written bare (AK#1683).
    #
    # AK#1677 needs no separate handling here, for the same reason as
    # `nec_export.export_nec` itself: this call IS that function, so its
    # `refuse_nec2_geometry` already refuses any below-z=0 wire before a
    # SimNEC script can be built.
    eng = PyNECEngine(builder, ground=ground)
    _refuse_jacket(eng)
    deck = export_nec(
        builder, ground=ground, freq=freq_mhz, include_rp=False, jacket_pair=False
    )
    cards = _nec_cards_for_portal(deck)
    conductivity = _uniform_conductivity(_wire_conductivities(eng))
    n_feeds = sum(1 for c in cards if c.startswith("EX"))
    if n_feeds > 1:
        # SimNEC's cascade template has ONE generator, so a multi-feed deck's
        # relative drive phasing is silently lost on load — SimNEC ties every
        # EX to the one source and drives them in phase. Measured live on
        # wire.w8jk (issue #815): the out-of-phase design read the IN-phase
        # impedance (384.7+505.3j vs the true 23.7+515.7j). A wrong-but-
        # plausible circuit is exactly what this exporter promises never to
        # emit, so refuse until per-feed SimNEC sources are modeled.
        raise SsnUnsupported(
            f"{n_feeds} feedpoints: SimNEC's cascade has one GENERATOR, so "
            "the deck's relative drive phasing would be silently lost "
            "(every feed driven in phase — issue #815); multi-feed designs "
            "are not exported until per-feed sources are modeled"
        )
    net = eng._network
    loads = (
        [
            (
                br,
                _brname(br, net.branch_paths[bi] if bi < len(net.branch_paths) else ""),
                eng._network_port_loc[br.port],
            )
            for bi, br in enumerate(net.branches)
            if isinstance(br, Load)
        ]
        if net is not None
        else []
    )
    statements, feed_elements = _wire_loads(
        loads,
        _feed_loc(cards),
        {tag: t[2] for tag, t in enumerate(eng.tups, 1)},
        freq_mhz,
    )
    if name is None:
        name = _default_block_name(builder)
    script = _portal_wrap(
        cards,
        name=name,
        ground=ground,
        seg_per_wl=seg_per_wl,
        conductivity=conductivity,
        loads=statements,
    )
    return script, feed_elements


# --- phase 2: networked (station) export — issue #604 -----------------------

C_MHZ_M = 299.792458  # c in MHz·m: λ[m] = C_MHZ_M / f[MHz]
M_PER_FT = 0.3048


def _brname(br, path: str) -> str:
    """Actionable branch name for rejection messages: instance path + type +
    the ports it spans, e.g. ``tuner.FloatingBalun(rig, sL, sR)``."""
    return f"{path}{type(br).__name__}({', '.join(_branch_port_refs(br))})"


def _element_factory():
    """Returns ``mk(typ, prefix, params)`` building one ``<element>`` XML
    fragment at the scaffold's indentation, with per-prefix numbered
    ``sweeperLabel``s (T1, C1, C2, L1, X1 …) in emission order. The LOAD /
    NETWORK / GENERATOR labels are single letters (L/A/G), so numbered chain
    labels can never collide with them."""
    counts: dict[str, int] = {}

    def mk(typ: str, prefix: str, params) -> str:
        counts[prefix] = counts.get(prefix, 0) + 1
        label = f"{prefix}{counts[prefix]}"
        body = "".join(
            f"\n                <p><n>{_xml_escape(str(n))}</n>"
            f"<v>{_xml_escape(str(v))}</v></p>"
            for n, v in params
        )
        return (
            "            <element>\n"
            f"                <type>{typ}</type>\n"
            f"                <sweeperLabel>{label}</sweeperLabel>"
            f"{body}\n"
            "            </element>"
        )

    return mk


def _q_params(q: float | None, freq_mhz: float):
    """SimNEC quotes component Q at a frequency (``Q`` / ``@MHz``). Our
    ``ql``/``qc`` are frequency-independent, so at the export frequency the
    two models agree exactly. ``Q = 0`` is emitted for the ideal component
    (no ``ql``/``qc``) — the SimSmith "loss model off" convention (see the
    module-note validation caveats)."""
    return [("Q", _fmt(q if q else 0.0)), ("@MHz", _fmt(freq_mhz))]


def _series_elements(br, entered_at: str, freq_mhz: float, mk, name: str):
    """SimNEC element(s) for one series (two-node) branch, in cascade order.
    A branch may emit several elements (a TwoPort with both L and C legs is a
    series pair — order between them is electrically irrelevant) or none (an
    all-omitted TwoPort is an ideal short: a plain wire-through)."""
    if isinstance(br, TL):
        if br.transposed:
            raise SsnUnsupported(
                f"{name}: a transposed (half-twist) line has no SimNEC "
                "cascade element — SERIES_TLINE cannot flip polarity"
            )
        # SimNEC's loss convention matches the cable-table one ours uses:
        # dB/100 ft = k0 + k1·√f + k2·f, displayed as `/100f` at `@frq`.
        # `~deg`/`@MHz` are the displayed electrical length, advisory (SimNEC
        # recomputes them from Zo/VFnom/ft). `Mdl` pins the loss model to
        # "k0k1k2" (option string verified against SimNEC 5.1a0): the default
        # "simplified" model reads the single `/100f @frq` point instead of
        # the coefficients, which agrees at the export frequency but not
        # across a SimNEC-side sweep.
        loss_100ft = br.k1 * math.sqrt(freq_mhz) + br.k2 * freq_mhz
        deg = 360.0 * br.length * freq_mhz / (br.vf * C_MHZ_M)
        return [
            mk(
                "SERIES_TLINE",
                "T",
                [
                    ("Mdl", "k0k1k2"),
                    ("Zo", _fmt(br.z0)),
                    ("VFnom", _fmt(br.vf)),
                    ("ft", _fmt(br.length / M_PER_FT)),
                    ("~deg", _fmt(deg)),
                    ("@MHz", _fmt(freq_mhz)),
                    ("/100f", _fmt(loss_100ft)),
                    ("@frq", _fmt(freq_mhz)),
                    ("k0", "0"),
                    ("k1", _fmt(br.k1)),
                    ("k2", _fmt(br.k2)),
                ],
            )
        ]
    if isinstance(br, TwoPort):
        if br.r is not None:
            raise SsnUnsupported(
                f"{name}: a plain series R is not in the captured SimNEC "
                "element set; express the loss as a component Q (ql/qc)"
            )
        out = []
        if br.l is not None:
            out.append(
                mk("SERIES_IND", "L", [("H", _fmt(br.l)), *_q_params(br.ql, freq_mhz)])
            )
        if br.c is not None:
            out.append(
                mk("SERIES_CAP", "C", [("F", _fmt(br.c)), *_q_params(br.qc, freq_mhz)])
            )
        return out
    if isinstance(br, Transformer):
        if br.n == 1.0 and br.r is None and br.lmag is None and br.core is None:
            # The ideal 1:1 is a through-connection, a plain wire in a
            # datum-referenced cascade — as the SimNEC importer's pass-through
            # between two block nodes is (AK#1679). Like the all-omitted
            # TwoPort, it emits nothing.
            return []
        if br.r is not None or br.lmag is not None or br.core is not None:
            raise SsnUnsupported(
                f"{name}: only the IDEAL transformer maps to TRANSFORMER2 "
                "(Mdl ideal); winding loss / magnetizing branches are not "
                "exported — drop r/lmag/core or model them explicitly in "
                "SimNEC after loading"
            )
        # Orientation: our Transformer(a, b, n) has v_a = n·v_b, so the
        # impedance at a is n²·Z_b; n_eff is that generator-side:antenna-side
        # ratio — entering the branch at `a` keeps n, entering at `b` inverts
        # it. SimNEC's TRANSFORMER2 N reads the OTHER way (measured on 5.1a0,
        # 2026-08-07: an n=2 step-up emitted as N=2 read Z/4 at the generator
        # instead of 4Z), so the emitted value is 1/n_eff.
        n_eff = br.n if entered_at == br.a else 1.0 / br.n
        return [mk("TRANSFORMER2", "X", [("Mdl", "ideal"), ("N", _fmt(1.0 / n_eff))])]
    raise SsnUnsupported(f"{name}: no SimNEC mapping for this branch type")


def _shunt_elements(br: Shunt, freq_mhz: float, mk, name: str):
    """SimNEC element(s) for a Shunt-to-common. Adjacent shunt elements at
    one node are electrically parallel, so a parallel-form L+C emits both;
    a series-form L+C (a shunt series-LC trap) has no captured element."""
    if br.r is not None:
        raise SsnUnsupported(
            f"{name}: a plain shunt R is not in the captured SimNEC element "
            "set; express the loss as a component Q (ql/qc)"
        )
    if br.l is not None and br.c is not None and not br.parallel:
        raise SsnUnsupported(
            f"{name}: a series-LC shunt (trap to common) has no single "
            "SimNEC element, and two stacked shunts would be parallel"
        )
    out = []
    if br.l is not None:
        out.append(
            mk("SHUNT_IND", "L", [("H", _fmt(br.l)), *_q_params(br.ql, freq_mhz)])
        )
    if br.c is not None:
        out.append(
            mk("SHUNT_CAP", "C", [("F", _fmt(br.c)), *_q_params(br.qc, freq_mhz)])
        )
    return out


@dataclass(frozen=True)
class _TunerSpan:
    """A self-tuning tuner in the ladder walk (AK#1662): one series position
    from its ``rig`` node to its ``out`` node, standing for every branch of
    its body. Emitted as SimNEC's own XMATCH, never as its bypass arms, which
    would write a wire and silently drop the tuner."""

    a: str
    b: str
    indices: tuple[int, ...]
    #: ``emit(mk)`` -> the element's XML, numbered in walk order.
    emit: object


def _xmatch(tuner, design, f_mhz: float, mk) -> str:
    """SimNEC's LC matching component in automatic mode for an L tuner, the
    inverse of the importer's XMATCH translation: ``pass`` is the mode, ``R``
    the target (``X`` 0), ``Qc`` / ``Ql`` the parts' Q's (0 is lossless), and
    ``MHz`` the tune frequency. SimNEC tunes it against its own antenna solve,
    as the app tunes against its own; the element survives the trip, not the
    values."""
    m = tuner.mechanism
    name = f"XMATCH for tuner {tuner.name!r}"
    way_out = (
        "export with freeze_tuners=True (CLI --freeze-tuners) to write its "
        "tuned parts as fixed elements instead"
    )
    if not hasattr(m, "mode"):
        raise SsnUnsupported(
            f"tuner {tuner.name!r} is a T network; SimNEC's LC matching "
            f"component is an L network only. {way_out[0].upper()}{way_out[1:]}"
        )
    if m.mode not in ("low", "high"):
        raise SsnUnsupported(
            f"{name}: mode {m.mode!r} has no XMATCH form, which is low- or "
            f"high-pass only; {way_out}"
        )
    if m.ranges != type(m.ranges)():
        raise SsnUnsupported(
            f"{name}: the component ranges (c_min_pF … l_max_uH) have no "
            f"XMATCH parameter, and SimNEC would tune without them; {way_out}"
        )
    if design is not None and design.bypass and not design.matched:
        # For low and high only one side can match a load (AK#1646), so a
        # fixed side that matched is the side SimNEC picks. One that could
        # not match is the case SimNEC's automatic element would differ on.
        raise SsnUnsupported(
            f"{name}: with its shunt fixed at {m.shunt_at!r} it finds no match "
            f"at {f_mhz:g} MHz and is bypassed, while SimNEC's automatic "
            f"element chooses its side and would match; {way_out}"
        )
    return mk(
        "XMATCH",
        "LC",
        [
            ("mode", "auto"),
            ("pass", m.mode),
            ("R", _fmt(m.target)),
            ("X", "0"),
            ("Qc", _fmt(m.qc or 0.0)),
            ("Ql", _fmt(m.ql or 0.0)),
            ("MHz", _fmt(f_mhz)),
        ],
    )


def _station_chain(net, freq_mhz: float, spans=()):
    """Map the network's branches onto SimNEC's linear cascade.

    Returns ``(feed_port, elements, deck_loads)``: the antenna-side
    ``PortOnWire`` the walk terminates on, the chain's element XML fragments
    in generator→antenna walk order, and the ``(Load, name)`` branches that
    sit on the antenna's wires rather than in the circuit (:func:`_wire_loads`).

    Raises :class:`SsnUnsupported` for anything that is not a single
    generator→antenna ladder of representable elements — most importantly
    the common-mode constructs (see the module note)."""
    # --- per-branch vetting; index the representable ones -------------------
    series_at: dict[str, list] = {}
    shunts_at: dict[str, list] = {}
    deck_loads: list[Load] = []
    in_span: set[int] = set()
    for span in spans:
        in_span.update(span.indices)
        name = f"tuner {span.a}->{span.b}"
        series_at.setdefault(span.a, []).append((span.indices[0], span, name))
        series_at.setdefault(span.b, []).append((span.indices[0], span, name))
    # A tuner's body outside a span is its BYPASS, a 0 H arm that would be
    # written as a plain wire: the tuner silently gone (AK#1662). Never.
    tuner_paths = {
        path
        for path, comp in (getattr(net, "composites", None) or {}).items()
        if getattr(comp, "tuner", None) is not None
    }
    for bi, br in enumerate(net.branches):
        if bi in in_span:
            continue
        path = net.branch_paths[bi] if bi < len(net.branch_paths) else ""
        if path in tuner_paths:
            raise SsnUnsupported(
                f"tuner {path.rstrip('.')!r} would be written as its bypass, a "
                "plain wire, which drops the tuner from the circuit"
            )
        name = _brname(br, path)
        if isinstance(br, BalancedLine):
            if br.zcomm is not None:
                raise SsnUnsupported(
                    f"{name}: this design's physics lives in the line's "
                    f"common mode (zcomm={br.zcomm:g} Ω, issue #576), and "
                    "SimNEC's SERIES_TLINE is purely differential — there is "
                    "no zcomm knob, so no .ssn can represent it faithfully "
                    "(the Track-2 divergence). Not exported."
                )
            raise SsnUnsupported(
                f"{name}: a BalancedLine is a four-terminal conductor pair; "
                "SimNEC's cascade elements are two-terminal, so there is no "
                "faithful single-ended equivalent. Not exported."
            )
        if isinstance(br, FloatingBalun):
            raise SsnUnsupported(
                f"{name}: a FloatingBalun's secondary is a genuinely floating "
                "differential pair (issue #589); SimNEC's datum-referenced "
                "cascade cannot represent it (the balanced-tuner common-mode "
                "limitation, issue #604). Not exported."
            )
        if isinstance(br, Autotransformer):
            raise SsnUnsupported(
                f"{name}: the autotransformer is a coupled-inductor model "
                "(issue #594), not an ideal ratio — mapping it onto "
                "TRANSFORMER2 (Mdl ideal) would misrepresent the common-"
                "section current. Not exported."
            )
        if isinstance(br, (Admittance, TouchstoneLoad, TouchstoneTwoPort)):
            raise SsnUnsupported(f"{name}: no SimNEC element mapping (yet)")
        if isinstance(br, Load):
            # Its value is vetted where it is written (`_wire_loads`).
            if not isinstance(net.ports.get(br.port), PortOnWire):
                raise SsnUnsupported(
                    f"{name}: a series Load on a virtual node has no SimNEC "
                    "cascade element (use a TwoPort for an in-line series "
                    "impedance)"
                )
            deck_loads.append((br, name))
        elif isinstance(br, Shunt):
            shunts_at.setdefault(br.port, []).append((bi, br, name))
        elif isinstance(br, (TL, TwoPort, Transformer)):
            series_at.setdefault(br.a, []).append((bi, br, name))
            series_at.setdefault(br.b, []).append((bi, br, name))
        else:
            raise SsnUnsupported(f"{name}: no SimNEC mapping for this branch type")

    # --- the generator end --------------------------------------------------
    if len(net.sources) != 1:
        raise SsnUnsupported(
            f"{len(net.sources)} sources; SimNEC's cascade has exactly one "
            "GENERATOR — multi-feed stations are not exported"
        )
    src = net.sources[0]
    if not isinstance(src, Driven):
        raise SsnUnsupported(
            f"source {type(src).__name__} on {src.port!r}: SimNEC's GENERATOR "
            "is a voltage source; current-forced feeds are not exported"
        )

    # --- walk the ladder from the generator to the antenna ------------------
    mk = _element_factory()
    elements: list[str] = []
    visited: set[int] = set()
    seen_nodes: set[str] = set()
    node = src.port
    while True:
        seen_nodes.add(node)
        for bi, br, name in shunts_at.pop(node, []):
            visited.add(bi)
            elements.extend(_shunt_elements(br, freq_mhz, mk, name))
        if isinstance(net.ports.get(node), PortOnWire):
            feed_port = node
            break
        avail = [
            (bi, br, name)
            for bi, br, name in series_at.get(node, [])
            if bi not in visited
        ]
        if len(avail) != 1:
            raise SsnUnsupported(
                f"node {node!r} has {len(avail)} onward series branches; "
                "SimNEC's circuit is a single generator→antenna cascade, so "
                "only a simple ladder (series elements plus shunts to "
                "common) is exported"
            )
        bi, br, name = avail[0]
        visited.add(bi)
        if isinstance(br, _TunerSpan):
            elements.append(br.emit(mk))
        else:
            elements.extend(_series_elements(br, node, freq_mhz, mk, name))
        node = br.b if br.a == node else br.a
        if node in seen_nodes:
            raise SsnUnsupported(
                f"branch {name} loops back to {node!r}; the cascade must be "
                "a simple generator→antenna path"
            )

    leftover = [
        name
        for lst in (*series_at.values(), *shunts_at.values())
        for bi, _br, name in lst
        if bi not in visited
    ]
    if leftover:
        raise SsnUnsupported(
            "branch(es) hang off the generator→antenna cascade: "
            f"{sorted(set(leftover))}; SimNEC's circuit is a single ladder"
        )
    if getattr(net.ports[feed_port], "distributed", False):
        raise SsnUnsupported(
            f"feed port {feed_port!r} is a distributed (finite-gap) port "
            "(issue #477); the NEC block's EX card is a single-segment delta "
            "gap, which is a different feed model — not exported"
        )
    return feed_port, elements, deck_loads


def _wire_conductivities(eng) -> dict[int, float | None]:
    """Per-tag wire conductivity (S/m, None = perfect), in the ``GW`` tag
    order both paths write (``eng.tups``, from 1): each wire's effective spec,
    the conductor's own value, unscaled — the portal writes the bare radius
    (``jacket_pair=False``). Read from the specs, not from an ``LD 5`` card,
    whose 7-figure spelling would move SimNEC's copper off its own name."""
    out: dict[int, float | None] = {}
    for tag, t in enumerate(eng.tups, start=1):
        spec = as_wire(t).spec
        eff = spec if spec is not None else eng._wire_spec
        out[tag] = nec_wire_material(
            eng._radius_for(t),
            eff.conductivity if eff is not None else WIRE_CONDUCTIVITY,
            eff,
            pair=False,
        ).conductivity
    return out


def _station_cards(eng, feed_port: str, deck_loads, freq_mhz: float):
    """The station's NEC-block cards — geometry, FR, and an EX delta gap at
    the station's feed port (which the portal wires to the block's circuit
    port — the cascade attaches there), in the antenna-only path's canonical
    GW → FR → EX grouping — and the lumped loads on its wires, as
    :func:`_wire_loads` writes them: ``(cards, statements, feed_elements)``."""
    wire_loc: dict[str, tuple[int, int]] = {}
    net = getattr(eng, "_network", None)

    def loc(port_name):
        # PyNEC's delta-gap placement (pynec.py): the segment `at` names on the
        # port's own wire, the middle segment when it names none (AK#1469).
        port = net.ports.get(port_name) if net is not None else None
        wire = port_wire(port) if isinstance(port, PortOnWire) else port_name
        tag, n_seg = wire_loc[wire]
        return tag, gap_segment(n_seg, port_at(port))

    geom: list[str] = []
    for tag, t in enumerate(eng.tups, start=1):
        geom.append(_gw(tag, t[2], t[0], t[1], eng._radius_for(t)))
        w = as_wire(t)
        if w.name is not None:
            wire_loc[w.name] = (tag, t[2])
    tag, seg = loc(feed_port)
    statements, feed_elements = _wire_loads(
        [(br, name, loc(br.port)) for br, name in deck_loads],
        (tag, seg),
        {tag: t[2] for tag, t in enumerate(eng.tups, start=1)},
        freq_mhz,
    )
    cards = geom + [
        f"FR 0 1 0 0 {_num(freq_mhz)} {_num(0.0)}",
        f"EX 0 {tag} {seg} 0 {_num(1.0)} {_num(0.0)}",
    ]
    return cards, statements, feed_elements


# --- minimal .ssn XML scaffold (see module note) ----------------------------
# Cascade, listed right-to-left the way SimNEC saves it: LOAD (open, right
# end) — NETWORK (the antenna, in the escape-hatch script) — {chain} (the
# station's circuit elements, antenna side first; "" for antenna-only) —
# GENERATOR (50 Ohm source, left end). Deliberately minimal — SimNEC
# regenerates the display state (SPREADSHEET / charts / band menus) it
# omits. The Generator's MHz carries an optional {gen_sweep} <sweepParam>.
_SSN_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<SimNEC1p0>
    <SmithChartCircuit>
        <XMLVersionControl>SimNEC:5.1a1</XMLVersionControl>
        <CIRCUIT>
            <element>
                <type>LOAD</type>
                <sweeperLabel>L</sweeperLabel>
                <p><n>ohms</n><v>1000000000</v></p>
            </element>
            <element>
                <type>NETWORK</type>
                <sweeperLabel>A</sweeperLabel>
                <escapeHatch/>
                <p><n>equ</n><v>{equ}</v></p>
            </element>{chain}
            <element>
                <type>GENERATOR</type>
                <sweeperLabel>G</sweeperLabel>
                <showInSmith>true</showInSmith>
                <p><n>MHz</n><v>{mhz}</v>{gen_sweep}</p>
                <p><n>Zo</n><v>50</v></p>
            </element>
        </CIRCUIT>{sweep_state}
    </SmithChartCircuit>
</SimNEC1p0>
"""

# When a sweep is requested, arm it: SCATTERGUN names the swept parameter (without
# it, doSweep=y on the param does nothing) and ROUNDCHART puts the chart in
# swept-trace mode. Confirmed against a SimNEC 5.1a1-saved, actively-sweeping file.
_SWEEP_STATE = (
    "\n        <SCATTERGUN><n>G.MHz</n></SCATTERGUN>"
    "\n        <ROUNDCHART><displayMode>Sweep</displayMode></ROUNDCHART>"
)


def _gen_sweep_block(lo: float, hi: float) -> str:
    """SimNEC ``<sweepParam>`` for the Generator's ``MHz``, enabled (``doSweep
    y``). Mirrors the structure of a SimNEC 5.1a1-saved file (confirmed to load);
    without it SimNEC falls back to its default (disabled) sweep range."""
    return (
        "<sweepParam><name>G.MHz</name><listed>true</listed>"
        "<p><n>points</n><v>100</v></p>"
        f"<p><n>from</n><v>{_fmt(lo)}</v></p>"
        f"<p><n>to</n><v>{_fmt(hi)}</v></p>"
        "<p><n>log</n><v>lin</v></p>"
        "<p><n>doSweep</n><v>y</v></p>"
        "<p><n>expr</n><v>Vary</v><fontScale>1</fontScale><w>640</w><h>360</h>"
        "<relx>0</relx><rely>360</rely><ProgrammingDialog><ThreeSplitPane>"
        "<errDiv>0.3</errDiv><outDiv>0.7</outDiv></ThreeSplitPane>"
        "</ProgrammingDialog></p></sweepParam>"
    )


def _tuner_spans(eng, builder, ground, freeze: bool):
    """The network to walk and the tuner spans in it (AK#1662). No tuner:
    the engine's network, no spans.

    A tuner is tuned here only when the export needs its answer: a frozen
    one needs its values, and an XMATCH for a box with a FIXED side needs to
    know whether that side matched. It is tuned on momwire, the app's own
    engine and always installed; the PyNEC engine this writer builds is
    geometry and network only and never solves (the bundle ships no PyNEC,
    #1354), so an auto-side XMATCH needs no solve at all."""
    net = eng._network
    tuners = find_tuners(net)
    if not tuners:
        return net, ()
    t = tuners[0]

    def tuned():
        from .engines.momwire import MomwireEngine

        red = MomwireEngine(builder, ground=ground)._reducer
        red.tune()
        return red

    if freeze:
        red = tuned()
        design = red.design
        if design.bypass:
            why = "is already at its target" if design.matched else "finds no match"
            raise SsnUnsupported(
                f"tuner {t.name!r} {why} at {red.f_mhz:g} MHz and is bypassed, "
                "so there are no tuned parts to freeze; export it without "
                "freeze_tuners to write SimNEC's own matching element"
            )
        # The tuned parts, as fixed values: the box is no longer a tuner.
        frozen = red.tuned_network()
        frozen.composites = {
            path: replace(comp, tuner=None) if comp.tuner is not None else comp
            for path, comp in frozen.composites.items()
        }
        return frozen, ()
    m = t.mechanism
    f_mhz = m.f_mhz or design_freq_mhz(builder)
    if not f_mhz:
        raise SsnUnsupported(
            f"tuner {t.name!r} has no tune_at_mhz and the design no design "
            "frequency, so there is no MHz to write"
        )
    design = tuned().design if getattr(m, "shunt_at", "auto") != "auto" else None
    return net, (
        _TunerSpan(t.rig, t.out, t.indices, lambda mk: _xmatch(t, design, f_mhz, mk)),
    )


def export_ssn(
    builder,
    *,
    freq_mhz: float | None = None,
    ground=DEFAULT_GROUND,
    seg_per_wl: int | None = None,
    sweep: tuple[float, float] | None = None,
    name: str | None = None,
    freeze_tuners: bool = False,
) -> str:
    """Return a SimNEC ``.ssn`` (str) for ``builder`` — antenna-only, or a
    differential-only station (issue #604; see the module Scope note).

    freq_mhz   : Generator frequency in MHz; defaults to ``builder.freq``.
    ground     : same spec as ``export_nec`` / PyNECEngine — None/"free",
                 "pec", ("finite", eps_r, sigma), ("finite-fast", eps_r, sigma),
                 ("mininec", eps_r, sigma) as SimNEC's MiniNECGround.
    seg_per_wl : SimNEC auto-mesh density (segments per wavelength). None (the
                 default) writes a ``$GW_<tag>.JamSegments(N)`` per wire, so
                 SimNEC meshes each wire as the deck does (AK#1680); set it to
                 hand the mesh to SimNEC's auto-segmentation instead, for a
                 convergence comparison (no JamSegments are written then).
    sweep      : ``(lo_mhz, hi_mhz)`` to enable the Generator's frequency sweep
                 over that band. ``None`` (default) leaves it minimal, so SimNEC
                 uses its own default (disabled) range — the single-point solve
                 at ``freq_mhz`` is still correct.
    name       : block display name (SimNEC's first ``//`` comment). Defaults to
                 the design's short leaf name; keep it ≤ ~12 chars — SimNEC
                 shrinks the font for longer names.
    freeze_tuners : a self-tuning tuner (AK#1646, #1661) is written as
                 SimNEC's own XMATCH element by default, which SimNEC retunes
                 against its antenna solve (low- and high-pass L tuners only).
                 True tunes it here (on momwire, the app's own engine) and
                 writes the tuned parts as fixed elements instead: the answer
                 for a T, an "ll" / "cc" L, or a tuner with component ranges,
                 and it re-imports as fixed values, not a tuner.

    Raises :class:`SsnUnsupported` (a ``NotImplementedError``) for networked
    designs SimNEC cannot faithfully represent — common-mode constructs
    (``BalancedLine.zcomm``, ``FloatingBalun``, balanced tuners), non-ladder
    topologies, and unmapped branch types. Component ``Q`` values are quoted
    at ``freq_mhz`` (SimNEC's ``Q``/``@MHz`` convention), so a station export
    is exact at that frequency and Q-model-approximate across a sweep.
    """
    freq_mhz = builder.freq if freq_mhz is None else float(freq_mhz)
    # PyNECEngine raises ValueError here for PortAtEnd / PortAtVertex
    # designs — NEC-2 (and therefore SimNEC's NEC block) has no
    # junction-node port and no segment-end source (issues #579, #898).
    eng = PyNECEngine(builder, ground=ground)
    if eng._use_reducer:
        # Station path (issue #604): circuit elements from the reducer
        # branches, the antenna alone in the NEC block, driven at the
        # station's feed port.
        _refuse_jacket(eng)
        net, spans = _tuner_spans(eng, builder, ground, freeze_tuners)
        feed_port, walk_elements, deck_loads = _station_chain(net, freq_mhz, spans)
        cards, statements, feed_elements = _station_cards(
            eng, feed_port, deck_loads, freq_mhz
        )
        script = _portal_wrap(
            cards,
            name=name if name is not None else _default_block_name(builder),
            ground=ground,
            seg_per_wl=seg_per_wl,
            conductivity=_uniform_conductivity(_wire_conductivities(eng)),
            loads=statements,
        )
        # A load on the fed segment is the antenna-most element (AK#1683).
        walk_elements = walk_elements + feed_elements
    else:
        script, walk_elements = _antenna_portal(
            builder, freq_mhz=freq_mhz, ground=ground, seg_per_wl=seg_per_wl, name=name
        )
    # File order is right-to-left (LOAD … GENERATOR), so the chain lands
    # after the antenna NETWORK element in antenna→generator order.
    chain = "".join("\n" + el for el in reversed(walk_elements))
    gen_sweep = (
        "" if sweep is None else _gen_sweep_block(float(sweep[0]), float(sweep[1]))
    )
    sweep_state = "" if sweep is None else _SWEEP_STATE
    return _SSN_TEMPLATE.format(
        equ=_xml_escape(script),
        chain=chain,
        mhz=_fmt(freq_mhz),
        gen_sweep=gen_sweep,
        sweep_state=sweep_state,
    )


def main(argv=None):
    """CLI: ``python -m antennaknobs.simnec_export <design> [opts]``."""
    import argparse

    from .cli import get_builder, parse_ground

    ap = argparse.ArgumentParser(
        prog="antennaknobs.simnec_export",
        description="Emit a SimNEC (.ssn) circuit for a design — antenna-only,"
        " or a differential-only station (antenna + feedline + tuner chain).",
    )
    ap.add_argument(
        "builder",
        help="Design name, e.g. dipoles.invvee[:variant] — or @file.nec to "
        "convert a NEC card deck straight to a SimNEC circuit",
    )
    ap.add_argument(
        "--freq", type=float, default=None, help="MHz (default: builder.freq)"
    )
    ap.add_argument(
        "--ground",
        default="free",
        help="free | pec | finite | finite:<eps_r>,<sigma> (default: free)",
    )
    ap.add_argument(
        "--seg-per-wl",
        type=int,
        default=None,
        help="SimNEC auto-mesh density (segments/wavelength)",
    )
    ap.add_argument(
        "--sweep",
        nargs="?",
        const="auto",
        default=None,
        metavar="LO,HI",
        help="Enable the Generator frequency sweep: bare '--sweep' for an auto "
        "band (+/-10%% around --freq), or '--sweep LO,HI' for an explicit MHz range.",
    )
    ap.add_argument(
        "--name",
        default=None,
        help="Block display name (default: design's short leaf name). SimNEC "
        "shrinks the font past ~12 chars, so keep it short.",
    )
    ap.add_argument(
        "--freeze-tuners",
        action="store_true",
        help="Write a self-tuning tuner's tuned parts as fixed elements instead "
        "of SimNEC's XMATCH (needed for a T, an ll/cc L, or component ranges)",
    )
    ap.add_argument("--out", default=None, help="Write here (default: stdout)")
    args = ap.parse_args(argv)

    builder = get_builder(args.builder)()
    freq = builder.freq if args.freq is None else args.freq
    sweep = None
    if args.sweep is not None:
        if args.sweep == "auto":
            sweep = (round(freq * 0.9, 6), round(freq * 1.1, 6))
        else:
            parts = args.sweep.split(",")
            if len(parts) != 2:
                ap.error("--sweep expects LO,HI (two MHz values), or bare for auto")
            sweep = (float(parts[0]), float(parts[1]))
    ssn = export_ssn(
        builder,
        freq_mhz=args.freq,
        ground=parse_ground(args.ground),
        seg_per_wl=args.seg_per_wl,
        sweep=sweep,
        name=args.name,
        freeze_tuners=args.freeze_tuners,
    )
    if args.out:
        # --name is echoed verbatim into the script's first //comment; pin
        # the encoding rather than trust the platform default (issue #772).
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(ssn)
        print(f"wrote {args.out}")
    else:
        print(ssn, end="")


if __name__ == "__main__":
    main()
