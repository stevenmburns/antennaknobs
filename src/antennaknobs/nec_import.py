"""Import a NEC2 card deck (``.nec``) as antennaknobs wire geometry.

The read-side twin of :mod:`antennaknobs.nec_export`: where ``export_nec``
emits a card deck for other NEC tools, ``parse_nec`` consumes one — so a deck
written by xnec2c, 4nec2, EZNEC, or found in an antenna handbook can be loaded
as a data-driven design (see ``read_nec``).

Geometry card semantics (GW/GA/GH/GM/GX/GR/GS) are transcribed from the
``nec2c`` 1.3.1 sources (``geometry.c``: ``wire``/``arc``/``helix``/``move``/
``reflc``) so transforms replicate what a NEC engine would build, including
the quirks: ``GM`` repetitions compound (each copy transforms the previous
copy), ``GX`` doubles the tag increment after every reflection plane, tag 0
never increments, and ``GS`` supports xnec2c's tag-range extension. Only the
*wire* model is translated; patches (SP/SM) and tapered wires (GC) raise.

A NEC deck also carries run configuration that antennaknobs manages itself —
ground (GN/GD), loading (LD), networks and transmission lines (TL/NT), sweep
and output requests (FR/RP/NE/NH/XQ/...). By default those cards are recorded
in ``NecDeck.ignored`` (and FR in ``NecDeck.freq_mhz``) rather than
translated, so a caller can tell the user what the deck asked for that the
app decides differently.

With ``network=True``, the LD/TL/NT cards that antennaknobs' port-network
system can express exactly are translated instead of ignored (issue #385):
lumped LD loads become ``Load`` branches on named 1-segment wires, LD 5 wire
conductivity surfaces as ``NecDeck.conductivity`` (feed it to ``WireSpec``),
TL cards become ``TL`` branches (crossed lines, zero-length = port
separation, end shunts — a conductance as a ``Shunt``, a reactive G+jB as a
fixed 1-port ``Admittance``, issue #423), an NT card becomes its exact
resistive pi when the Y matrix is all-real (``TwoPort`` + ``Shunt``) or a
2-port ``Admittance`` when it carries susceptance, an LD 4 reactive load
(fixed R+jX) becomes a fixed-complex-Z ``Load`` (issue #422), and 4nec2's
LD 7 wire insulation becomes per-wire ``WireSpec`` jackets via
``wire_insulation`` (issue #447). An LD 2 whose fields spell the a′+L′
jacket pair AK's own writers emit (``engines._nec_wire.nec_wire_material``,
issue #1523) inverts back to a jacket the same way, via
``engines._nec_wire.jacket_from_equivalent_radius`` — the conductor radius
comes back exact, surfacing through ``wire_insulation`` alongside a
canonical (not measured) insulation radius/permittivity, and the GW card's
own radius is corrected from a′ back to that conductor radius via
``wire_conductor_radius``. What still cannot be expressed exactly —
distributed RLC proper (LD 3, and an LD 2 that is not that pair), partial-wire
conductivity or insulation ranges — stays in ``ignored`` with a per-card
reason in ``ignored_detail``.
``wire_tuples()`` then emits *named* wires (no legacy
``ex`` markers) and ``network()`` returns the matching ``Network``, ready to
return from ``build_wires`` / ``build_network``.

Two dialects, and which one a deck is in: 4nec2 writes NEC-2 and EZNEC's
export writes NEC-5, and they read the same ``EX``, ``LD``, ``TL`` and ``NT``
cards differently — NEC-2 attaches at a segment CENTRE, NEC-5 at a segment
END (``I4`` picks it, or the sign of the segment field does). A deck declares
NEC-5 by saying so: EZNEC's own stamp line (``CM ! Written by EZNEC/Pro+ v.
7.0 in NEC-5 format.``, AK#1579 — its NEC-2 and NEC-4.2 writers stamp the
same frame with their own word and keep the NEC-2 reading; a word we have
never captured refuses), a bare ``CM NEC-5``
(AK#1476), a ``GN`` card's ``NOFILE`` sentinel, or an ``EX`` in the edge form
NEC-2 has no spelling for. Declared, the whole deck reads NEC-5: sources and
probes at knots, a discrete ``LD`` as ONE knot load rather than a segment
range (AK#1483), ``TL``/``NT`` ends at knots, and ``GN 0`` as Sommerfeld
rather than the reflection-coefficient approximation. The one knot the port
model cannot reach is a LONE wire end — the node's only through path is the
ground contact — so a network end there keeps the segment its card names and
the deck reports it in ``net_ends_demoted``.

Excitation: voltage sources (EX type 0 and 5) drive an antenna in any mode;
4nec2's EX type 6 current source (issue #442) and NEC-5's EX type 4 current
source (issue #1243, the form EZNEC's NEC-5 export writes) drive it in
network mode as a ``DrivenCurrent``; plane-wave excitations and NEC-2's
type 4 (an elementary current source at a point in space) raise. In network
mode a source, load or transmission-line end is a port at its position along
its wire (AK#1469), so the wire keeps the deck's segments — unless it lands on
a wire that is not geometry at all: EZNEC parks a wire ~100 λ away and uses
its segments as circuit nodes to spell a source behind a transformer or a
line, and each such segment imports as a ``PortVirtual`` with the wire itself
dropped (AK#1577). When what that phantom segment drives is an ``NT`` GYRATOR
(zero diagonal, ``Y12 = Y21 = jB``) it is not a source behind a component at
all — it is the only way NEC-2 can spell a CURRENT source, so the phantom node
and the gyrator collapse into a ``DrivenCurrent`` on the real segment
(``_collapse_gyrator_drives``, AK#1595) and all three dialects of one antenna
import to one network. Default mode's
engine feeds a wire tuple at its middle segment, so there
``NecDeck.wire_tuples`` splits a wire whose EX segment is off-centre into
colinear pieces that preserve the deck's exact segment boundaries and put the
feed on its own 1-segment wire.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from functools import cached_property
from itertools import pairwise

from . import network as _net
from .design_data import read_data

__all__ = [
    "NecDeck",
    "NecFeed",
    "NecLoad",
    "NecNT",
    "NecTL",
    "NecWire",
    "parse_nec",
    "read_nec",
    "resolve_sy",
]

_DEG = math.pi / 180.0

# Cards that configure a NEC *run* rather than the wire list. antennaknobs has
# its own engine settings for these concerns (ground, loading, feedlines,
# sweeps, pattern output), so they are recorded, not translated.
_IGNORED_CARDS = {
    "GN": "ground parameters",
    "GD": "additional ground medium",
    "LD": "loading",
    "TL": "transmission line",
    "NT": "two-port network",
    "RP": "radiation-pattern request",
    "NE": "near-E-field request",
    "NH": "near-H-field request",
    "XQ": "execute request",
    "PT": "current print control",
    "PQ": "charge print control",
    "KH": "interaction limit",
    "CP": "coupling request",
    "PL": "plot request",
    "WG": "NGF write request",
    "ZO": "impedance normalisation (xnec2c)",
    "IS": "insulated-wire sheath",
    "NX": "next structure -- only the first structure in the file was imported",
}

_UNSUPPORTED_CARDS = {
    # SP is refused by FORM, not from this table — see `classify_sp` and the
    # dispatch in the parse loop. It is absent here deliberately.
    "SC": "a NEC-2/NEC-4 surface-patch continuation (SC)",
    "SM": "a multiple-patch surface (SM)",
    "GF": "a numerical Green's function file (GF)",
    # NEC-5's triangle-mesh surface (stl2nec5 / gmsh2nec5 output, #1067).
    # Listed here so the filename field never reaches the SY evaluator.
    "NL": "an NL triangle-mesh surface (NEC-5)",
}


_SP_BY_FORM = {
    "nec5": "a NEC-5 sphere (SP)",
    "patch": "a NEC-2/NEC-4 surface patch (SP)",
}


def classify_sp(fields) -> str:
    """``"nec5"`` for NEC-5's sphere spelling of SP, ``"patch"`` for NEC-2/4's.

    `fields` is the card's fields AS WRITTEN (the tokens after the mnemonic),
    because the literal spelling carries the signal: an integral value is not
    an integer literal.

    The two cards share a mnemonic and nothing else. NEC-2/NEC-4:
    ``SP I1 I2 F1 .. F6`` — two integers (I2 = patch shape 0..3) then real
    coordinates, at most 8 fields. NEC-5 (Users Manual, "SP – Sphere"):
    ``SP ITAG NTH NPH IALT X0 Y0 Z0 RAD TH1 TH2 PH1 PH2`` — FOUR integers, two
    of them patch-edge counts (so >= 1), then eight reals with radius > 0.
    So fields 3 and 4 are integer counts in NEC-5 and real coordinates in
    NEC-2; a decimal point or exponent in either settles it on sight, and when
    both are integer literals the field count and a positive radius do. The
    manual's Example 4 card, ``SP 0 0 .1 .05 .05 0. 0.``, is a patch on sight.

    This importer reads BOTH dialects — 4nec2's NEC-2 and EZNEC's NEC-5 export
    (#456, #1243) — so naming every SP a surface patch was wrong for half the
    decks it sees. Refusing is still right (antennaknobs models wires only);
    only the name changes.

    TWIN of `_classify_sp_fields` in `scripts/nec5_corpus/nec5_corpus.py`,
    where the rule was derived from the NEC-5 Users Manual's SP layout and
    measured against the manual's own examples. #1337 lifted it here and had
    the script import it; #1376 put a copy back in the script, because the
    script's promise to the working group is "one file, standard library
    only" and an import of this package broke that. Two copies are how the
    two drift, so `tests/test_nec_import.py` pins the function bodies equal
    token for token; edit both or fail the suite.
    """
    if len(fields) < 8 or not all(_is_int_literal(t) for t in fields[:4]):
        return "patch"
    try:
        nth, nph, radius = int(fields[1]), int(fields[2]), float(fields[7])
    except ValueError:
        return "patch"
    if nth < 1 or nph < 1 or radius <= 0:
        return "patch"
    return "nec5"


def _is_int_literal(token: str) -> bool:
    return token.lstrip("+-").isdigit()


# EZNEC stamps every deck it writes with the writer that wrote it:
# `! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.` (AK#1579). That sentence
# is a DECLARATION — the first and strongest of the NEC-5 tells this importer
# already has — so a `CM` carrying it puts the deck on the AK#1476 reading:
# sources, probes, discrete loads and network ends at segment ENDS.
#
# Matched by PHRASE, never by a substring of "NEC-5": prose that mentions the
# dialect is still prose (`CM converted from a NEC-5 deck`). The separator
# between the two halves of the product name is loose because our own AC6LA
# fixture spells it `EZNEC Pro+`; the format word is read from the END of the
# sentence, which is where EZNEC puts it.
_EZNEC_STAMP = re.compile(r"written\s+by\s+eznec\s*/?\s*pro\+", re.IGNORECASE)
_EZNEC_FORMAT = re.compile(r"\bin\s+(\S+)\s+format\s*\.?\s*\Z", re.IGNORECASE)


# The format words we have a capture for. EZNEC drives three engine slots and
# writes a different deck for each (all three captured 2026-09-18):
#
#   NEC-5   — the export this whole rule exists for: sources, probes, discrete
#             loads and network ends at segment ENDS.
#   NEC-2   — what File > Save As writes. An ordinary NEC-2 deck, read
#             natively; a current source becomes a virtual wire carrying an
#             `EX 0` and an `NT` injector, which is AK#1577's idiom already.
#   NEC-4.2 — the External NEC-4.2 slot. NEC-2 geometry and card semantics
#             with NEC-4's `EX 6` segment current source, which is the NEC-2
#             reading here too (issue #442) — `I4` is a print flag in both,
#             not an end.
#
# Only NEC-5 is a DECLARATION; the other two are the reading this importer
# already had. A word we have never seen refuses rather than guessing which.
_EZNEC_NEC5_WRITER = ("NEC-5", "NEC5")
_EZNEC_NEC2_WRITERS = ("NEC-2", "NEC2", "NEC-4.2", "NEC4.2")


def _eznec_declares_nec5(text: str, where: str) -> bool:
    """Is this ``CM`` comment EZNEC's writer stamp, and does it declare NEC-5?

    False when the comment is not a stamp at all, and False for the two
    captured writers whose decks read as NEC-2. True for the NEC-5 writer.
    Any OTHER format word raises: a writer we have not seen spells its
    sources and loads its own way, and guessing is what AK#1579 was.
    """
    if not _EZNEC_STAMP.search(text):
        return False
    m = _EZNEC_FORMAT.search(text)
    word = (m.group(1) if m else "").upper()
    if word in _EZNEC_NEC5_WRITER:
        return True
    if word in _EZNEC_NEC2_WRITERS:
        return False
    named = f"in {word} format" if word else "in a format this stamp does not name"
    raise ValueError(
        f"{where}: EZNEC wrote this deck {named}, which this importer has no "
        f"capture for — only EZNEC's NEC-5, NEC-4.2 and NEC-2 writers have "
        f"been captured, and a writer we have not seen spells sources, loads "
        f"and network ends its own way, so reading this deck as any of them "
        f"would place them wrong (AK#1579)"
    )


def _knot_of(seg: int, edge: int) -> int:
    """The knot a NEC-5 end field names on a wire: end 1 of 1-based segment
    ``seg`` is knot ``seg - 1``, end 2 is knot ``seg``. ``edge`` 0 has no
    knot — that is NEC-2's centre attachment — and callers check first."""
    return seg - 1 if edge == 1 else seg


@dataclass(frozen=True)
class NecWire:
    """One straight wire after all geometry transforms: NEC's GW columns."""

    tag: int
    n_seg: int
    p1: tuple[float, float, float]
    p2: tuple[float, float, float]
    radius: float


@dataclass(frozen=True)
class NecFeed:
    """A source EX card resolved onto a wire: 1-based segment ``seg`` of
    ``deck.wires[wire]`` is driven with ``voltage`` volts — or, when
    ``current`` is True (4nec2's EX 6, issue #442; NEC-5's EX 4, issue
    #1243), that complex value is the forced current in amps and the feed
    becomes a ``DrivenCurrent`` in ``deck.network()``.

    ``edge`` (issue #824, the NEC-5 edge-source form): 0 is the ordinary
    NEC-2 center gap; 1/2 places the source at that END of ``seg`` — a
    knot source, which ``network()`` renders as a ``PortAtVertex`` (the
    series apex feed, #898) on a wire piece ending at that knot. An EX 4
    feed always carries an edge: NEC-5 has no center source."""

    wire: int
    seg: int
    voltage: complex
    current: bool = False
    edge: int = 0
    # A 4nec2 percentage position ("50%"): the exact place along the wire as a
    # fraction from end 1, which the network path keeps; `seg` is then the
    # segment whose centre is nearest (AK#1496).
    at: float | None = None


@dataclass(frozen=True)
class NecLoad:
    """One translated lumped LD element (``network=True``): an R/L/C in
    series with 1-based segment ``seg`` of ``deck.wires[wire]`` — exactly
    NEC's per-segment ld_card semantics, so a multi-segment LD range appears
    as one ``NecLoad`` per segment. ``parallel`` distinguishes LD type 1
    (parallel RLC, the trap idiom) from type 0/4 (series). Legs the card
    left at zero are ``None`` (omitted), matching ``network.Load``.

    ``z`` carries an LD type 4 reactive load as a fixed complex impedance
    R + jX (issue #422); it is mutually exclusive with r/l/c, and a
    conductance-only type 4 (X = 0) stays a plain ``r`` instead.

    ``edge`` is 0 for NEC-2's load at the centre of ``seg``. On a NEC-5 deck
    it is 1 or 2, the END of ``seg`` the load sits at: NEC-5 addresses a
    discrete load by knot, as it does a source (AK#1483)."""

    wire: int
    seg: int
    r: float | None
    l: float | None  # named to match network.Load's field name
    c: float | None
    parallel: bool
    z: complex | None = None
    edge: int = 0
    at: float | None = None  # a 4nec2 percentage position, as on NecFeed


@dataclass(frozen=True)
class NecTL:
    """One translated TL card (``network=True``), resolved onto its two
    segments. ``z0`` is positive — a negative card z0 (NEC's crossed line)
    becomes ``transposed=True``, matching the ``network.TL`` convention.
    ``length`` is resolved: the card's length, or the straight-line distance
    between the segment midpoints when the card says 0 (NEC semantics).
    ``shunt_r_*`` carry conductance-only end admittances as 1/G resistances;
    a reactive end (susceptance ≠ 0, issue #423) is kept as a complex
    ``shunt_y_*`` and stamped as a fixed 1-port ``Admittance`` instead — see
    ``_end_shunt``.

    ``virtual_a`` / ``virtual_b`` mark an end that lands on a virtualized
    remote TL-anchor wire (issue #427): that segment carries no geometry, so
    ``network()`` terminates the line on a ``PortVirtual`` circuit node
    instead of a ``PortOnWire``, and the anchor wire is dropped from
    ``wire_tuples()``. A virtual end's full complex end admittance is kept in
    ``shunt_y_a`` / ``shunt_y_b`` and stamped as a 1-port ``Admittance`` on the
    virtual node (the shorted-stub variant); a zero ``shunt_y`` leaves the node
    an ideal open (the open-stub variant).
    The ``shunt_r_*`` / ``shunt_y_*`` fields are mutually exclusive per end:
    a real end uses ``shunt_r``, a virtual end uses ``shunt_y``.

    ``edge_a`` / ``edge_b`` are 0 for NEC-2's connection at the centre of the
    named segment. On a NEC-5 deck they are 1 or 2, the END of that segment
    the line attaches to: NEC-5 addresses a network connection by knot, as it
    does a source (AK#1579)."""

    wire_a: int
    seg_a: int
    wire_b: int
    seg_b: int
    z0: float
    length: float
    transposed: bool
    shunt_r_a: float | None
    shunt_r_b: float | None
    virtual_a: bool = False
    virtual_b: bool = False
    shunt_y_a: complex | None = None
    shunt_y_b: complex | None = None
    at_a: float | None = None  # 4nec2 percentage positions, as on NecFeed
    at_b: float | None = None
    edge_a: int = 0  # NEC-5 knot ends (AK#1579), as on NecFeed/NecLoad
    edge_b: int = 0


@dataclass(frozen=True)
class NecNT:
    """One translated NT card (``network=True``).

    All-real Y matrix: decomposed into its exact resistive pi — a series
    resistance between the ports (from −Y12) plus a shunt resistance at each
    port (Y11+Y12, Y22+Y12); real Y-parameters are frequency-independent so the
    pi is exact at every frequency. ``series_r`` / ``shunt_r_*`` carry it and
    ``y`` is ``None``.

    Y matrix with susceptance anywhere: no resistive pi exists, so the full 2×2
    complex short-circuit admittance is kept in ``y`` (issue #416) and the
    resistive-pi fields are ``None``. ``network()`` emits it as a general
    ``Admittance`` branch. ``None`` pi legs are absent elements.

    ``edge_a`` / ``edge_b`` carry the NEC-5 knot end, as on ``NecTL``
    (AK#1579)."""

    wire_a: int
    seg_a: int
    wire_b: int
    seg_b: int
    series_r: float | None = None
    shunt_r_a: float | None = None
    shunt_r_b: float | None = None
    y: tuple[tuple[complex, complex], tuple[complex, complex]] | None = None
    at_a: float | None = None  # 4nec2 percentage positions, as on NecFeed
    at_b: float | None = None
    edge_a: int = 0  # NEC-5 knot ends (AK#1579), as on NecFeed/NecLoad
    edge_b: int = 0


@dataclass(frozen=True)
class NecDeck:
    """A parsed NEC deck: final wire list, resolved feeds, and the run
    configuration the deck asked for (kept for reporting, not applied)."""

    wires: tuple[NecWire, ...]
    feeds: tuple[NecFeed, ...]
    freq_mhz: tuple[float, float] | None  # FR card sweep range (lo, hi)
    ground: bool  # deck requested a ground plane (GE flag or GN card)
    comments: tuple[str, ...]  # CM card text
    ignored: tuple[str, ...]  # run-config card mnemonics seen but not applied
    # network=True translation results (all empty in the default mode):
    loads: tuple[NecLoad, ...] = ()
    # The ground the deck MODELS, in the CLI's `--ground` shape (AK#1432):
    # None = free space (GE 0 and no GN, or GN -1), "pec" = a perfect ground
    # (GN 1, or GE 1 with no GN — NEC's default), ("finite", eps_r, sigma)
    # for GN 2 and ("finite-fast", eps_r, sigma) for a NEC-2 deck's GN 0 (a
    # NEC-5 deck's GN 0 is Sommerfeld, so "finite"), the card's own medium
    # either way. `ground_method` names the
    # finite model the deck asked for: "sommerfeld" (GN 2) or "fast" (GN 0,
    # the reflection-coefficient approximation); None otherwise. The folder
    # route seeds the app's ground switch from these; the CLI's `@file` route
    # uses them when `--ground` is not given.
    ground_spec: object = None
    ground_method: str | None = None
    # The GN card the ground came from ("GN 0" / "GN 2"), None without one.
    ground_card: str | None = None
    # The deck shows NEC-5's dialect: the GN card's NOFILE sentinel, or an EX
    # source at a segment END (#824). NEC-2 has neither. It decides what GN 0
    # means: NEC-5 has no reflection-coefficient ground, so its GN 0 is the
    # full Sommerfeld solution.
    nec5_dialect: bool = False
    tls: tuple[NecTL, ...] = ()
    nts: tuple[NecNT, ...] = ()
    conductivity: float | None = None  # whole-structure LD 5, S/m
    # Ranged LD 5 (issue #388): (wire index, S/m) for every wire an LD 5
    # card covers in full. Baked into wire_tuples(specs=True) specs.
    wire_conductivity: tuple[tuple[int, float], ...] = ()
    # LD 7 wire insulation (issue #447, 4nec2 dialect): (wire index,
    # (jacket outer radius m, jacket relative permittivity)) for every
    # wire an LD 7 card covers in full — a whole-structure card covers
    # them all. Baked into wire_tuples(specs=True) specs. An LD 2 a'+L'
    # jacket pair (issue #1591) also lands here, through
    # engines._nec_wire.jacket_from_equivalent_radius: the (radius, eps_r)
    # reported is one member of the electrically-equivalent family that
    # inductance implies, not a measurement of the physical jacket.
    wire_insulation: tuple[tuple[int, tuple[float, float]], ...] = ()
    # The conductor radius an LD 2 jacket-pair inversion (issue #1591)
    # recovered for a wire whose GW card carries the fattened equivalent
    # radius a' instead: (wire index, true conductor radius m). Overrides
    # that wire's GW radius in wire_tuples(specs=True) specs — every other
    # wire's WireSpec radius is still its GW radius unchanged.
    wire_conductor_radius: tuple[tuple[int, float], ...] = ()
    # (mnemonic, reason) per card instance that network mode still could not
    # translate — skipped_note() prefers these over the generic descriptions.
    ignored_detail: tuple[tuple[str, str], ...] = ()
    network_mode: bool = False  # parsed with network=True
    # Deck asked for NEC's extended thin-wire kernel (EK card, #414). Applied
    # by the PyNEC engine (`extended_thin_wire_kernel=True`) so fat-wire
    # decks compare kernel-for-kernel against nec2c; momwire's kernels are
    # its own formulation, so this is reference fidelity, not a momwire knob.
    # Deck-level: True if any EK card other than `EK -1` (off) appears.
    extended_kernel: bool = False
    # Wire indices (into ``wires``) whose geometry was replaced by virtual
    # circuit nodes. They are dropped from wire_tuples() and every port on
    # them is a PortVirtual in network(). Empty unless parsed with
    # network=True and virtualize_anchors=True. Two idioms land here:
    # issue #427's remote TL anchor (a 1-segment wire parked ≫λ away,
    # referenced only as a TL far-end termination) and AK#1577's EZNEC
    # virtual wire, which is the subset named below.
    virtual_anchors: frozenset[int] = frozenset()
    # The AK#1577 subset of ``virtual_anchors``: EZNEC's virtual wire, whose
    # every referenced SEGMENT is one circuit node — so one wire can carry
    # several, and a source on one of them is a drive on that node rather
    # than a feed on geometry (`_virtual_segment_wires`).
    virtual_segment_wires: frozenset[int] = frozenset()
    # The idiom's LD 4 open-circuit pins (AK#1577), as
    # ``(wire index, segment, impedance)``: the card EZNEC writes on every
    # virtual segment it uses, to stop that segment carrying antenna current.
    # Virtualizing the wire is what actually removes the segment, so the pin
    # survives only as what it leaves behind — a 1-port ``Admittance`` of
    # 1/Z on the node, the same ideal open ``_end_shunt`` gives a #427
    # shorted stub. Keeping it matters: a virtual node held by nothing else
    # (EZNEC spells a parallel load as an NT whose far half is all zeros) is
    # a singular row without it.
    virtual_pins: tuple[tuple[int, int, complex], ...] = ()
    # AK#1579: (wire index, knot) for every NEC-5 network end whose knot is a
    # LONE wire end. NEC-5 connects there; the port model cannot, so the end
    # stays on the segment the card names. Counted rather than routed through
    # `ignored`, for the same reason the symmetry drop below is: the card IS
    # modelled, just not at the node NEC-5 puts it on.
    net_ends_demoted: tuple[tuple[int, int], ...] = ()
    # GX/GR symmetry (issue #946): the cell size in segments while the
    # symmetry is still live at GE (None when a later GW collapsed it, the
    # common case), and how many LD segments NEC discarded because they
    # addressed an image rather than the cell. Reported, not refused — the
    # discard IS the deck's physics under NEC.
    symmetry_cell: int | None = None
    symmetry_dropped_loads: int = 0
    # antennaknobs#1460: False when the deck's GE card is NEGATIVE (`GE -1`),
    # which NEC reads as the ground plane WITHOUT the ground-contact current
    # expansion. Every engine here serves the interpolated (`GE 1`) contact,
    # so a free end standing in the plane is refused wherever an engine
    # applies a ground (`ge_minus_one_contact_refusal`).
    ground_contact_interpolates: bool = True

    def free_plane_ends(self) -> tuple[tuple[int, str], ...]:
        """Every wire end standing in the ground plane (z = 0) that is NOT a
        crossing junction, as ``(wire index, "p1" | "p2")`` (antennaknobs#1460).

        The same definition as momwire's deck reader (momwire#1052,
        `deck/_nec2.py::_crossing_junction_at`), so the two readers agree deck
        for deck. In the plane means |z| within `_NEC_SMIN` of the end's
        segment length (nec2c's `conect` rule). A crossing junction is an
        in-plane node where some wire with an end there continues ABOVE the
        plane and another continues BELOW it, with ends coinciding within the
        larger of the two wires' tolerances. A buried wire that only reaches up
        to the plane is a free end.
        """

        def tol(w):
            return _NEC_SMIN * math.dist(w.p1, w.p2) / max(int(w.n_seg), 1)

        out = []
        for i, w in enumerate(self.wires):
            t = tol(w)
            for name, end in (("p1", w.p1), ("p2", w.p2)):
                if abs(float(end[2])) > t:
                    continue
                above = below = False
                for v in self.wires:
                    tv = max(t, tol(v))
                    for e, other in ((v.p1, v.p2), (v.p2, v.p1)):
                        if all(
                            abs(float(e[k]) - float(end[k])) <= tv for k in range(3)
                        ):
                            z = float(other[2])
                            if z > tv:
                                above = True
                            elif z < -tv:
                                below = True
                if not (above and below):
                    out.append((i, name))
        return tuple(out)

    def refined(self, r: int) -> NecDeck:
        """The same deck with every wire's segment count multiplied by ``r``.

        This is the refinement path for an imported deck (U2 of
        docs/plan-buried-scope-closure.md): a Builder refines through its own
        mesh knobs, but a deck's only mesh is its GW counts, so a ladder over a
        deck needs this. Every segment is divided, the source region included.
        A ladder that holds the fed segment fixed converges in the far mesh
        alone, which is how momwire#1027 read a numerical difference as a
        physical one.

        ``r`` must be ODD. An old segment's centre is then the centre of its
        middle piece, and an old knot is still a knot. So a centre gap stays a
        centre gap and a knot source stays a knot source at every rung. An even
        ``r`` would turn a centre feed into a knot feed, which is a change of
        port, not a refinement (antennaknobs#1456).

        References move with the mesh: a centre attachment (feed, lumped load,
        TL/NT end) goes to the middle piece of its old segment, and a knot
        source or NEC-5 knot load keeps its knot. A lumped load stays ONE element. Per-wire
        materials are per-wire and do not move. A virtualized wire (a #427 TL
        anchor, an AK#1577 EZNEC virtual wire) has no mesh to refine and keeps
        its segments, so the nodes its ports name stay where they were.
        """
        if not isinstance(r, int) or r < 1 or r % 2 == 0:
            raise ValueError(
                f"refinement factor must be an odd positive integer, got {r!r}"
            )
        if r == 1:
            return self
        anchors = self.virtual_anchors

        def centre(wire: int, seg: int) -> int:
            return seg if wire in anchors else (seg - 1) * r + (r + 1) // 2

        def feed(f: NecFeed) -> NecFeed:
            if f.wire in anchors:
                return f
            if f.edge == 1:
                return replace(f, seg=(f.seg - 1) * r + 1)
            if f.edge == 2:
                return replace(f, seg=f.seg * r)
            return replace(f, seg=centre(f.wire, f.seg))

        return replace(
            self,
            wires=tuple(
                w if i in anchors else replace(w, n_seg=w.n_seg * r)
                for i, w in enumerate(self.wires)
            ),
            feeds=tuple(feed(f) for f in self.feeds),
            loads=tuple(
                replace(ld, seg=(ld.seg - 1) * r + 1 if ld.edge == 1 else ld.seg * r)
                if ld.edge
                else replace(ld, seg=centre(ld.wire, ld.seg))
                for ld in self.loads
            ),
            tls=tuple(
                replace(
                    t, seg_a=centre(t.wire_a, t.seg_a), seg_b=centre(t.wire_b, t.seg_b)
                )
                for t in self.tls
            ),
            nts=tuple(
                replace(
                    t, seg_a=centre(t.wire_a, t.seg_a), seg_b=centre(t.wire_b, t.seg_b)
                )
                for t in self.nts
            ),
            symmetry_cell=None
            if self.symmetry_cell is None
            else self.symmetry_cell * r,
        )

    def virtual_anchor_tags(self) -> tuple[int, ...]:
        """The NEC tags of the wires whose geometry was replaced by virtual
        circuit nodes, in wire order — for honest benchmark/UI labeling.
        Both idioms: issue #427's TL anchors and AK#1577's EZNEC virtual
        wires."""
        return tuple(self.wires[i].tag for i in sorted(self.virtual_anchors))

    def dominant_radius(self) -> float:
        """The deck's wire radius, length-weighted where wires differ.

        ``build_wires()`` tuples carry no radius — the engines take one
        radius for the whole antenna via ``build_wire_material()`` — so a
        deck with mixed radii is approximated by the radius that makes up
        the greatest total wire length. Feed this to
        ``WireSpec(radius=...)`` so the import keeps the deck's reactance
        (the engines' 0.5 mm idealization is far off a typical 4-10 mm
        Yagi element).
        """
        length_by_radius: dict[float, float] = {}
        for w in self.wires:
            ln = math.dist(w.p1, w.p2)
            length_by_radius[w.radius] = length_by_radius.get(w.radius, 0.0) + ln
        return max(length_by_radius.items(), key=lambda kv: kv[1])[0]

    def skipped_note(self) -> str | None:
        """One human-readable sentence naming the run configuration the deck
        asked for that the app decides itself: the ``ignored`` cards with
        their descriptions, plus the deck's ground request (which can come
        from the GE flag alone, with no GN card). Deck-backed design stubs
        put this under ``ui_params["notes"]`` so the web UI can tell the
        user why readouts may differ from the deck's published numbers.
        None when the deck carries nothing the app overrides.
        """
        parts = []
        # GN is not listed: the app seeds its ground switch from the deck's
        # GE/GN (AK#1432) and the `@file` route applies it, so calling it "not
        # applied" contradicted the ground panel beside it (AC6LA, 2026-09-13).
        shown = tuple(m for m in self.ignored if m != "GN")
        if shown:
            why: dict[str, list[str]] = {}
            for m, reason in self.ignored_detail:
                if reason not in why.setdefault(m, []):
                    why[m].append(reason)

            def describe(m: str) -> str:
                if m in why:
                    return f"{m} ({'; '.join(why[m])})"
                if m in _IGNORED_CARDS:
                    return f"{m} ({_IGNORED_CARDS[m]})"
                return m

            cards = ", ".join(describe(m) for m in shown)
            parts.append(f"deck cards not applied: {cards}")
        anchors = self.virtual_anchors - self.virtual_segment_wires
        if anchors:
            tags = ", ".join(str(self.wires[i].tag) for i in sorted(anchors))
            n = len(anchors)
            parts.append(
                f"{n} remote TL-anchor wire{'s' if n > 1 else ''} "
                f"(tag{'s' if n > 1 else ''} {tags}) modeled as ideal virtual "
                f"terminations"
            )
        if self.virtual_segment_wires:
            # AK#1577: say both halves of what was translated — the wire that
            # stopped being geometry, and the pins that stopped being loads —
            # because both are things the deck says and the solve does not.
            tags = ", ".join(
                str(self.wires[i].tag) for i in sorted(self.virtual_segment_wires)
            )
            n = len(self.virtual_segment_wires)
            # A gyrator drive (AK#1595) leaves no node behind: the phantom and
            # the NT collapse into a forced current on the segment they drive,
            # so the count here would otherwise name nodes the solve never sees.
            collapsed = self._network_parts()[3]
            gyr = len(collapsed)
            nodes = (
                sum(
                    1
                    for (wi, _seg) in self._port_plan
                    if wi in self.virtual_segment_wires
                )
                - gyr
            )
            became = []
            if nodes:
                became.append(f"{nodes} virtual circuit node{'s' if nodes > 1 else ''}")
            if gyr:
                became.append(
                    f"{gyr} NT-gyrator current source{'s' if gyr > 1 else ''} "
                    f"forced on the segment{'s' if gyr > 1 else ''} "
                    f"{'they' if gyr > 1 else 'it'} drive{'' if gyr > 1 else 's'}"
                )
            part = (
                f"{n} EZNEC virtual wire{'s' if n > 1 else ''} "
                f"(tag{'s' if n > 1 else ''} {tags}) imported as "
                + " and ".join(became)
            )
            # A pin on a collapsed node went with it — the forced current is
            # the whole of what that node became — so only the survivors are
            # opens the solve still carries.
            k = sum(
                1
                for (wi, seg, _z) in self.virtual_pins
                if self._port_plan.get((wi, seg)) not in collapsed
            )
            if k:
                part += (
                    f", with {k} LD 4 open-circuit pin{'s' if k > 1 else ''} "
                    "kept as the idiom's ideal open rather than applied as "
                    f"{'loads' if k > 1 else 'a load'}"
                )
            parts.append(part)
        if self.net_ends_demoted:
            n = len(self.net_ends_demoted)
            where = ", ".join(
                f"wire {i + 1} knot {k}" for i, k in self.net_ends_demoted
            )
            parts.append(
                f"{n} NEC-5 network connection{'s' if n > 1 else ''} at a wire "
                f"END with no other conductor there ({where}) kept on the "
                "segment the card names: the node itself is a port between a "
                "lone conductor end and its ground contact, which no engine "
                "here hosts"
            )
        if self.symmetry_dropped_loads:
            n = self.symmetry_dropped_loads
            parts.append(
                f"{n} load segment{'s' if n > 1 else ''} addressed a GX/GR "
                "image rather than the symmetry cell, which NEC discards"
            )
        if not parts:
            return None
        body = "; ".join(parts)
        return (
            body[0].upper() + body[1:] + " — the app's own settings are used instead."
        )

    @cached_property
    def _net_ends(self) -> tuple[tuple[str, int, int, int], ...]:
        """(port name, wire index, 1-based segment, end) for every TL and NT
        end, in the order the names are minted. One sequence so the four
        plans below agree on which name a connection point carries, whether
        it is a segment (NEC-2) or a knot (NEC-5, AK#1579)."""
        out: list[tuple[str, int, int, int]] = []
        for k, tl in enumerate(self.tls, 1):
            out.append((f"tl{k}a", tl.wire_a, tl.seg_a, tl.edge_a))
            out.append((f"tl{k}b", tl.wire_b, tl.seg_b, tl.edge_b))
        for k, nt in enumerate(self.nts, 1):
            out.append((f"nt{k}a", nt.wire_a, nt.seg_a, nt.edge_a))
            out.append((f"nt{k}b", nt.wire_b, nt.seg_b, nt.edge_b))
        return tuple(out)

    def _knot_end(self, wire: int, seg: int, edge: int) -> bool:
        """Does this attachment address a KNOT that is a place on a wire? A
        virtualized wire has no places — its segment IS the circuit node, so
        the end a NEC-5 card names there is not one (AK#1577)."""
        return bool(edge) and wire not in self.virtual_anchors

    @cached_property
    def _port_plan(self) -> dict[tuple[int, int], str]:
        """(wire index, 1-based local segment) → port name, for every
        segment the network attaches to (network mode). Feeds claim names
        first — a single feed is ``"feed"``, matching the catalog
        convention — and later attachments to an already-claimed segment
        share its port: an LD on the fed segment becomes a ``Load`` and a
        ``Driven`` on one port (the Group-2 termination branch), a TL
        chain's shared element gets one port per segment however many
        lines land there."""
        plan: dict[tuple[int, int], str] = {}
        single = len(self.feeds) == 1
        for k, f in enumerate(self.feeds, 1):
            if f.edge and f.wire not in self.virtual_anchors:
                continue  # knot sources: _vertex_plan (#824) or _site_plan
            # On a virtualized wire the END the EX names is not a place: the
            # segment IS the node, so the source claims it like any other
            # attachment and shares it with the TL/NT ends that land there
            # (AK#1577).
            key = (f.wire, f.seg)
            if key in plan:
                raise ValueError(
                    f"NEC deck drives segment {f.seg} of wire {f.wire + 1} "
                    f"with more than one EX card"
                )
            plan[key] = "feed" if single else f"feed{k}"
        for k, ld in enumerate(self.loads, 1):
            if ld.edge:
                continue  # a knot load rides its knot's port (AK#1483)
            plan.setdefault((ld.wire, ld.seg), f"load{k}")
        for pname, wi, seg, edge in self._net_ends:
            if self._knot_end(wi, seg, edge):
                continue  # a knot end: _vertex_plan or _site_plan (AK#1579)
            plan.setdefault((wi, seg), pname)
        return plan

    @cached_property
    def _attachment_positions(self) -> dict[tuple[int, int], float]:
        """(wire index, segment) -> the exact position a 4nec2 percentage gave
        an attachment there, as a fraction of the wire from end 1 (AK#1496).
        Two different positions rounding to one segment would be one port in
        two places, so that is refused by name."""
        out: dict[tuple[int, int], float] = {}

        def put(wire, seg, at):
            if at is None:
                return
            prev = out.get((wire, seg))
            if prev is not None and abs(prev - at) > 1e-12:
                raise ValueError(
                    f"wire {wire + 1}, segment {seg}: two percentage positions "
                    f"({prev * 100:g}% and {at * 100:g}%) fall on one segment; "
                    "give the wire more segments"
                )
            out[(wire, seg)] = at

        for f in self.feeds:
            if not f.edge:
                put(f.wire, f.seg, f.at)
        for ld in self.loads:
            if not ld.edge:
                put(ld.wire, ld.seg, ld.at)
        for tl in (*self.tls, *self.nts):
            put(tl.wire_a, tl.seg_a, tl.at_a)
            put(tl.wire_b, tl.seg_b, tl.at_b)
        return out

    @cached_property
    def _vertex_wires(self) -> frozenset[int]:
        """Wires that keep the #824 cut and the PortAtVertex spelling (AK#1469
        part B).

        A knot source at a wire END (knot 0 or n_seg), an EX 4 current source,
        and a knot source on a junction cut all need a wire end to feed, and so
        does a NEC-5 knot load at either place (AK#1483). The
        engines refuse a wire referenced by both a gap port and a vertex port,
        so every attachment on such a wire keeps today's cut spelling. Every
        other wire keeps its authored segments and carries its attachments as
        positioned ports (`_site_plan`).

        A VIRTUALIZED wire is never here, whatever its sources say (AK#1577):
        it has no ends, so a knot source on it is a drive on the node its
        segment became, claimed in `_port_plan` like any other attachment.
        """
        if not self.network_mode:
            return frozenset()
        out = set()

        def needs_a_wire_end(wire: int, seg: int, edge: int) -> bool:
            knot = _knot_of(seg, edge)
            return knot in (
                0,
                self.wires[wire].n_seg,
            ) or knot in self._junction_cuts.get(wire, frozenset())

        for f in self.feeds:
            if not self._knot_end(f.wire, f.seg, f.edge):
                # A source on a virtualized wire (AK#1577) drives a circuit
                # NODE: there is no wire end for a vertex port to sit on, and
                # the end the EX names is not a place. `_port_plan` claims it
                # as an ordinary port on its segment's node instead.
                continue
            if f.current or needs_a_wire_end(f.wire, f.seg, f.edge):
                out.add(f.wire)
        for ld in self.loads:
            if self._knot_end(ld.wire, ld.seg, ld.edge) and needs_a_wire_end(
                ld.wire, ld.seg, ld.edge
            ):
                out.add(ld.wire)
        # A NEC-5 network end at a wire END or a junction cut needs the same
        # wire end a knot source does (AK#1579): a line landing on the OCF
        # feedpoint is the shape, and it is a PortAtVertex or it is nothing.
        for _p, wi, seg, edge in self._net_ends:
            if self._knot_end(wi, seg, edge) and needs_a_wire_end(wi, seg, edge):
                out.add(wi)
        return frozenset(out)

    @cached_property
    def _site_plan(self) -> dict[int, dict]:
        """wire index -> the positioned spelling of its attachments (AK#1469
        part B): ``{"pieces": [(first knot, last knot, name or None)],
        "ports": {port name: (piece name, at)}, "knots": {knot: port name}}``.

        The wire is cut only where another wire touches it (`_junction_cuts`).
        An attachment at segment k of an n-segment piece sits at
        ``(k - 1/2) / n``, and an interior voltage knot source at knot k at
        ``k / n``. The exact middle is None, so a wire whose one port sits at
        its middle imports as it always did. A piece carrying one port is named
        after it; a piece carrying several is named ``w<tag>`` (``w<tag>.<i>``
        when junction cuts split the wire). Wires in `_vertex_wires` and
        virtual anchors are absent.
        """
        if not self.network_mode:
            return {}
        single = len(self.feeds) == 1
        claims: dict[int, list[tuple[str, str, int]]] = {}
        for (wi, seg), pname in self._port_plan.items():
            if wi in self.virtual_anchors or wi in self._vertex_wires:
                continue
            claims.setdefault(wi, []).append((pname, "seg", seg))

        def claim_knot(wire, seg, edge, pname, share=True):
            if wire in self._vertex_wires or not self._knot_end(wire, seg, edge):
                # AK#1577: on a virtualized wire the segment IS the node, so
                # there is no knot to claim and no pin to turn into a load.
                return
            knot = _knot_of(seg, edge)
            items = claims.setdefault(wire, [])
            # A NEC-5 knot load (AK#1483) or network end (AK#1579) shares the
            # port of a knot another attachment already claimed.
            if share and any(kind == "knot" and idx == knot for _p, kind, idx in items):
                return
            items.append((pname, "knot", knot))

        for k, f in enumerate(self.feeds, 1):
            claim_knot(
                f.wire, f.seg, f.edge, "feed" if single else f"feed{k}", share=False
            )
        for k, ld in enumerate(self.loads, 1):
            claim_knot(ld.wire, ld.seg, ld.edge, f"load{k}")
        for pname, wi, seg, edge in self._net_ends:
            claim_knot(wi, seg, edge, pname)
        plan: dict[int, dict] = {}
        for wi, items in claims.items():
            n = self.wires[wi].n_seg
            bounds = [0, *sorted(self._junction_cuts.get(wi, frozenset())), n]
            pieces = list(pairwise(bounds))
            placed: dict = {}
            for pname, kind, idx in items:
                pos = (
                    self._attachment_positions.get((wi, idx)) if kind == "seg" else None
                )
                if pos is not None:
                    # A 4nec2 percentage: the exact point, on its junction piece.
                    x = pos * n
                    j = next((j for j, (a, b) in enumerate(pieces) if a < x < b), None)
                    if j is None:
                        raise ValueError(
                            f"wire {wi + 1}: the position {pos * 100:g}% lands "
                            "exactly where another wire joins it"
                        )
                    a, b = pieces[j]
                    at = (x - a) / (b - a)
                    at = None if abs(at - 0.5) < 1e-9 else at
                elif kind == "seg":
                    j = next(j for j, (a, b) in enumerate(pieces) if a < idx <= b)
                    a, b = pieces[j]
                    c, local = b - a, idx - a
                    at = (
                        None
                        if (c % 2 == 1 and 2 * local == c + 1)
                        else (local - 0.5) / c
                    )
                else:
                    j = next(j for j, (a, b) in enumerate(pieces) if a < idx < b)
                    a, b = pieces[j]
                    c, local = b - a, idx - a
                    at = None if 2 * local == c else local / c
                placed[pname] = (j, at)
            on_piece: dict[int, list[str]] = {}
            for pname, (j, _at) in placed.items():
                on_piece.setdefault(j, []).append(pname)
            multi = len(pieces) > 1

            def piece_name(j, on_piece=on_piece, multi=multi, wi=wi):
                names = on_piece.get(j)
                if not names:
                    return None
                if len(names) == 1:
                    return names[0]
                return f"w{wi + 1}.{j + 1}" if multi else f"w{wi + 1}"

            plan[wi] = {
                "pieces": [(a, b, piece_name(j)) for j, (a, b) in enumerate(pieces)],
                "ports": {p: (piece_name(j), at) for p, (j, at) in placed.items()},
                "knots": {idx: p for p, kind, idx in items if kind == "knot"},
            }
        return plan

    def _site_port(self, wi: int, pname: str):
        """The PortOnWire for a positioned attachment (`_site_plan`). A port at
        its own piece's middle is written plainly, so it also builds on a
        momwire without the position fields (0.54.0)."""
        piece, at = self._site_plan[wi]["ports"][pname]
        if piece == pname and at is None:
            return _net.PortOnWire(pname)
        return _net.PortOnWire(pname, wire=None if piece == pname else piece, at=at)

    @cached_property
    def _vertex_plan(self) -> dict[tuple[int, int], tuple[str, str]]:
        """(wire index, local knot 0..n_seg) → (port name, "p0"|"p1") for
        every NEC-5 edge source (issue #824). The knot is the shared feed
        naming sequence with `_port_plan` (a lone feed is ``"feed"``); the
        end token names which authored end of the EMITTED wire piece the
        knot is: an interior knot cuts the wire and the port rides the
        piece ENDING there ("p1"); knot 0 is the whole piece's "p0"."""
        plan: dict[tuple[int, int], tuple[str, str]] = {}
        single = len(self.feeds) == 1
        for k, f in enumerate(self.feeds, 1):
            if not f.edge or f.wire not in self._vertex_wires:
                continue
            knot = _knot_of(f.seg, f.edge)
            key = (f.wire, knot)
            if key in plan:
                raise ValueError(
                    f"NEC deck drives knot {knot} of wire {f.wire + 1} "
                    f"with more than one EX card"
                )
            end = "p0" if knot == 0 else "p1"
            plan[key] = ("feed" if single else f"feed{k}", end)
        for k, ld in enumerate(self.loads, 1):
            if not ld.edge or ld.wire not in self._vertex_wires:
                continue
            knot = _knot_of(ld.seg, ld.edge)
            # A load on a source's knot shares its port (AK#1483).
            plan.setdefault((ld.wire, knot), (f"load{k}", "p0" if knot == 0 else "p1"))
        # ... and so does a NEC-5 network end on that knot (AK#1579): `TL
        # 3,2,2,-1` and `EX 4,2,-1` name ONE node, which is one port here.
        for pname, wi, seg, edge in self._net_ends:
            if not edge or wi not in self._vertex_wires:
                continue
            knot = _knot_of(seg, edge)
            plan.setdefault((wi, knot), (pname, "p0" if knot == 0 else "p1"))
        return plan

    @cached_property
    def _junction_cuts(self) -> dict[int, frozenset[int]]:
        """wire index → interior segment boundaries (1..n_seg−1) where some
        OTHER wire has a segment endpoint.

        NEC connects *segments* whose ends coincide — the grouping into GW
        wires is irrelevant to it — so a deck may run one long wire straight
        through another and rely on the crossing carrying current (the W8IO
        whip's matching straps cross the whip axis mid-wire). antennaknobs'
        engines junction wires at wire ENDS only, so ``wire_tuples()`` must
        shatter wires at these boundaries to reproduce the deck's electrical
        graph. The split is lossless: same segments, same boundaries, and
        the KCL junction at the shared node is exactly NEC's connection.
        """
        eps = 1e-9

        def key(p):
            return tuple(round(c / eps) for c in p)

        def boundary(w, k):
            # Must match wire_tuples' point() bitwise so the shattered
            # pieces land exactly on the detected nodes.
            t = k / w.n_seg
            return tuple(a + (b - a) * t for a, b in zip(w.p1, w.p2, strict=True))

        owners: dict[tuple, set[int]] = {}
        for i, w in enumerate(self.wires):
            for k in range(w.n_seg + 1):
                owners.setdefault(key(boundary(w, k)), set()).add(i)
        cuts: dict[int, frozenset[int]] = {}
        for i, w in enumerate(self.wires):
            shared = {
                k for k in range(1, w.n_seg) if len(owners[key(boundary(w, k))]) > 1
            }
            if shared:
                cuts[i] = frozenset(shared)
        return cuts

    def wire_tuples(self, specs: bool = False):
        """The deck as ``build_wires()`` tuples.

        Default mode: ``(p1, p2, n_seg, ex)`` with the deck's EX voltages as
        legacy ``ex`` markers. Network mode (``network=True``): every segment
        the network attaches to — feeds, loads, TL/NT connections — becomes a
        *named* wire instead, ``(p1, p2, n_seg, None, name)``, and no tuple
        carries ``ex`` (the drive comes from ``network()``'s ``Driven``
        sources).

        ``specs=True`` (issue #388) emits ``Wire`` named tuples instead,
        each carrying a per-wire ``WireSpec`` with the deck wire's OWN
        radius — no ``dominant_radius()`` compromise — its effective
        conductivity (a ranged LD 5 over the whole wire, else the deck's
        whole-structure LD 5), and its LD 7 insulation jacket when the
        deck carries one (issue #447). PyNEC honors both per wire; momwire honors
        both too since momwire#147 (complete in momwire 0.13.0 across all
        four solver bases, the H-matrix family included). With
        ``specs=True`` a ``build_wire_material()`` fallback is unnecessary
        (every wire carries its spec) — though a design may still define
        one for the weight readout of spec-less wires it adds itself.

        Any boundary another wire touches is cut, so the crossing becomes a
        wire-end junction (``_junction_cuts``: NEC connects segment ends
        regardless of wire grouping, and the engines junction wire ends only).
        In network mode that is the only cut on most wires: each attachment is
        a port positioned along its wire (`_site_plan`, AK#1469), and each
        engine chooses a count that puts the port on its grid. A wire with a
        wire-end knot source, an EX 4 current source or a knot source on a
        junction cut keeps the older spelling (`_vertex_wires`). A virtualized
        wire is not emitted at all: its segments are circuit nodes, not wire
        (issue #427, AK#1577). There, and in
        default mode, a marked segment that is not the wire's middle segment is
        isolated on its own 1-segment wire so the delta gap lands exactly where
        the deck put it, and a claimed interior knot cuts the wire. Either way
        the geometry, segmentation and electrical graph are the deck's own.
        """
        if not self.feeds:
            raise ValueError(
                "NEC deck has no voltage-source EX card — nothing drives the antenna"
            )
        # (wire index) → {segment: (ex voltage | None, port name | None)}
        marks: dict[int, dict[int, tuple[complex | None, str | None]]] = {}
        if self.network_mode:
            for (wi, seg), pname in self._port_plan.items():
                marks.setdefault(wi, {})[seg] = (None, pname)
        else:
            for f in self.feeds:
                per = marks.setdefault(f.wire, {})
                if f.seg in per:
                    raise ValueError(
                        f"NEC deck drives segment {f.seg} of wire {f.wire + 1} "
                        f"with more than one EX card"
                    )
                per[f.seg] = (f.voltage, None)

        sigma_by_wire = dict(self.wire_conductivity)
        ins_by_wire = dict(self.wire_insulation)
        radius_by_wire = dict(self.wire_conductor_radius)

        def spec_for(i, w):
            """Per-wire spec (issue #388): the deck wire's own radius, with
            its effective conductivity baked in — a ranged LD 5 on this wire
            wins over the whole-structure one — and its LD 7 insulation
            jacket (issue #447), when one covers the wire. Baking is
            required: engines treat an explicit spec as complete (no
            field-level fallback to build_wire_material), so leaving
            conductivity None would turn a copper deck into PEC wire by
            wire. An LD 2 jacket-pair inversion (issue #1591) overrides the
            GW radius itself: that card's wire carries the fattened
            equivalent radius a' on its GW card, not the conductor radius
            WireSpec wants."""
            if not specs:
                return None
            ins = ins_by_wire.get(i)
            return _net.WireSpec(
                radius=radius_by_wire.get(i, w.radius),
                conductivity=sigma_by_wire.get(i, self.conductivity),
                insulation_radius=ins[0] if ins else None,
                insulation_eps_r=ins[1] if ins else None,
            )

        tups = []

        def emit(p0, p1, n, ex, pname=None, spec=None):
            if spec is not None:
                tups.append(_net.Wire(p0, p1, n, ex, pname, spec))
            elif pname:
                tups.append((p0, p1, n, ex, pname))
            else:
                tups.append((p0, p1, n, ex))

        for i, w in enumerate(self.wires):
            if i in self.virtual_anchors:
                # Not geometry: a remote TL anchor (issue #427) or EZNEC's
                # virtual wire (AK#1577). Every port on it is a PortVirtual
                # in network(), so emit nothing here.
                continue
            per = marks.get(i, {})
            cutset = self._junction_cuts.get(i, frozenset())
            # Knot sources (issue #824): wire pieces are cut at each claimed
            # interior knot, and the piece whose authored end lands ON the
            # knot carries the port name — network() then hosts a
            # PortAtVertex there. Empty outside network mode (the parser
            # refuses edge sources without it).
            vper = {
                knot: nm_end
                for (wi, knot), nm_end in self._vertex_plan.items()
                if wi == i
            }
            n = w.n_seg
            spec = spec_for(i, w)
            site = self._site_plan.get(i)
            if site is not None:
                # AK#1469 part B: the wire keeps its authored segments, cut
                # only where another wire touches it, and each attachment is a
                # port at its position on its piece (`_site_plan`).
                if len(site["pieces"]) == 1:
                    emit(w.p1, w.p2, n, None, site["pieces"][0][2], spec)
                else:
                    for a, b, name in site["pieces"]:
                        # The same expression as `point()` and
                        # `_junction_cuts`, so adjoining pieces meet bitwise.
                        p_a = tuple(
                            x + (y - x) * (a / n)
                            for x, y in zip(w.p1, w.p2, strict=True)
                        )
                        p_b = tuple(
                            x + (y - x) * (b / n)
                            for x, y in zip(w.p1, w.p2, strict=True)
                        )
                        emit(p_a, p_b, b - a, None, name, spec)
                continue
            if not per and not cutset and not vper:
                emit(w.p1, w.p2, n, None, spec=spec)
                continue
            if not cutset and not vper and len(per) == 1 and n % 2 == 1:
                (seg, (ex, pname)) = next(iter(per.items()))
                if seg == (n + 1) // 2:
                    # Marked at the wire's middle segment — the engine's
                    # native attachment position; keep the wire whole.
                    emit(w.p1, w.p2, n, ex, pname, spec)
                    continue

            def point(k, w=w, n=n):
                """Endpoint after ``k`` of the wire's ``n`` segments. The same
                expression for adjoining pieces yields bitwise-equal points,
                which is how wires are recognised as connected."""
                t = k / n
                return tuple(a + (b - a) * t for a, b in zip(w.p1, w.p2, strict=True))

            # Cut at every junction boundary, around every marked segment
            # so it sits alone on a 1-segment piece, and at every claimed
            # interior knot (#824).
            bounds = set(cutset)
            for seg in per:
                bounds.update((seg - 1, seg))
            bounds.update(k for k in vper)
            bounds -= {0, n}
            if 0 in vper:
                # Knot 0 rides the wire's FIRST piece (its "p0"), same as
                # every other claimed knot rides the piece ENDING at it — so
                # a knot-0 claim and the next claimed knot collide on that
                # one first piece unless something already cuts between
                # them. A cut at 1 always separates them, and always fits,
                # UNLESS the next claimed knot IS 1: a 1-segment piece has
                # only one end and cannot host both (#1594; the two-attachment
                # case genuinely has no room and falls through to the
                # ValueError below).
                nxt = min((b for b in bounds if b > 0), default=n)
                if nxt in vper and nxt >= 2:
                    bounds.add(1)
            prev = 0
            for b in [*sorted(bounds), n]:
                count = b - prev
                mark = per.get(b) if count == 1 else None
                # Vertex claim on this piece: knot 0 rides the first piece
                # (its "p0"); every other knot rides the piece ENDING there.
                vclaims = ([vper[0][0]] if prev == 0 and 0 in vper else []) + (
                    [vper[b][0]] if b in vper else []
                )
                if len(vclaims) > 1 or (vclaims and mark is not None):
                    raise ValueError(
                        f"wire {i + 1}: piece between knots {prev} and {b} "
                        "is claimed by more than one attachment (a knot "
                        "source needs its own wire end, #824)"
                    )
                if mark is not None:
                    ex, pname = mark
                    emit(point(prev), point(b), 1, ex, pname, spec)
                else:
                    emit(
                        point(prev),
                        point(b),
                        count,
                        None,
                        vclaims[0] if vclaims else None,
                        spec,
                    )
                prev = b
        return tups

    def network(self):
        """The deck's translated LD/TL/NT cards as a ``network.Network``,
        with ports on the named wires ``wire_tuples()`` emits and one
        ``Driven`` per EX card — ready to return from ``build_network()``.
        A deck with no translatable cards still gets its ``Driven`` feeds,
        so a network-mode stub can always define ``build_network``. Only
        available when the deck was parsed with ``network=True``."""
        ports, branches, sources, _gyr = self._network_parts()
        return _net.Network(ports=ports, branches=branches, sources=sources)

    def _network_parts(self):
        """``(ports, branches, sources, gyrators)`` — ``network()``'s pieces
        before they are sealed into a ``Network``, which is what lets
        ``skipped_note`` say which of the two an EZNEC virtual wire became
        without sealing a second one. ``gyrators`` maps each collapsed virtual
        node (AK#1595) to the real port its forced current moved to; it is
        empty for every other deck."""
        if not self.network_mode:
            raise ValueError(
                "deck was not parsed for network translation — call "
                "parse_nec/read_nec with network=True"
            )
        plan = self._port_plan
        # A port on a virtualized wire — a #427 TL anchor, or one of the
        # segments of an AK#1577 EZNEC virtual wire — is a pure circuit node
        # (PortVirtual), no geometry; every other port is on a real wire.
        ports = {
            pname: (
                _net.PortVirtual(pname)
                if wi in self.virtual_anchors
                else self._site_port(wi, pname)
                if wi in self._site_plan
                else _net.PortOnWire(pname)
            )
            for (wi, _seg), pname in plan.items()
        }
        # Knot sources (issue #824): the NEC-5 edge form becomes the series
        # apex feed — a PortAtVertex on the wire piece whose authored end
        # sits on the claimed knot (wire name == port name, the PortOnWire
        # convention).
        for (_wi, _knot), (pname, end) in self._vertex_plan.items():
            ports[pname] = _net.PortAtVertex(pname, end=end)
        # Knot sources positioned along their wire (AK#1469 part B).
        for wi, site in self._site_plan.items():
            for pname in site["ports"]:
                if pname not in ports:
                    ports[pname] = self._site_port(wi, pname)

        def knot_port(wire, seg, edge):
            """The port name an attachment carries — its knot's, when it
            names one (AK#1483, AK#1579), so everything landing on one knot
            lands on one port."""
            if not edge:
                return plan[(wire, seg)]
            knot = _knot_of(seg, edge)
            if (wire, knot) in self._vertex_plan:
                return self._vertex_plan[(wire, knot)][0]
            return self._site_plan[wire]["knots"][knot]

        def load_port(ld):
            return knot_port(ld.wire, ld.seg, ld.edge)

        def net_port(wire, seg, edge):
            if not self._knot_end(wire, seg, edge):
                return plan[(wire, seg)]
            return knot_port(wire, seg, edge)

        branches: list = []
        for ld in self.loads:
            branches.append(
                _net.Load(
                    port=load_port(ld),
                    r=ld.r,
                    l=ld.l,
                    c=ld.c,
                    parallel=ld.parallel,
                    z=ld.z,
                )
            )
        for tl in self.tls:
            a = net_port(tl.wire_a, tl.seg_a, tl.edge_a)
            b = net_port(tl.wire_b, tl.seg_b, tl.edge_b)
            branches.append(
                _net.TL(a=a, b=b, z0=tl.z0, length=tl.length, transposed=tl.transposed)
            )
            if tl.shunt_r_a is not None:
                branches.append(_net.Shunt(port=a, r=tl.shunt_r_a))
            if tl.shunt_r_b is not None:
                branches.append(_net.Shunt(port=b, r=tl.shunt_r_b))
            # Virtual-anchor far-end admittance (issue #427): the full complex
            # end Y as a fixed 1-port Admittance on the virtual node. Absent
            # (None) leaves the node an ideal open — the open-stub variant.
            if tl.shunt_y_a is not None:
                branches.append(_net.Admittance(ports=(a,), y=((tl.shunt_y_a,),)))
            if tl.shunt_y_b is not None:
                branches.append(_net.Admittance(ports=(b,), y=((tl.shunt_y_b,),)))
        for wi, seg, z in self.virtual_pins:
            # AK#1577: what the idiom's LD 4 leaves behind once its segment
            # is a node — an ideal open, and the only branch holding a node
            # the deck's networks reach through an all-zero half.
            pname = plan.get((wi, seg))
            if pname is not None and z:
                branches.append(_net.Admittance(ports=(pname,), y=((1.0 / z,),)))
        for nt in self.nts:
            a = net_port(nt.wire_a, nt.seg_a, nt.edge_a)
            b = net_port(nt.wire_b, nt.seg_b, nt.edge_b)
            if nt.y is not None:
                # Complex Y (susceptance present): the full 2×2 as one general
                # Admittance branch (issue #416).
                branches.append(_net.Admittance(ports=(a, b), y=nt.y))
                continue
            if nt.series_r is not None:
                branches.append(_net.TwoPort(a=a, b=b, r=nt.series_r))
            if nt.shunt_r_a is not None:
                branches.append(_net.Shunt(port=a, r=nt.shunt_r_a))
            if nt.shunt_r_b is not None:
                branches.append(_net.Shunt(port=b, r=nt.shunt_r_b))

        single = len(self.feeds) == 1

        def feed_port(k, f):
            if self._knot_end(f.wire, f.seg, f.edge):
                knot = _knot_of(f.seg, f.edge)
                if (f.wire, knot) in self._vertex_plan:
                    return self._vertex_plan[(f.wire, knot)][0]
                return "feed" if single else f"feed{k}"
            return plan[(f.wire, f.seg)]

        sources = [
            _net.DrivenCurrent(port=feed_port(k, f), current=f.voltage)
            if f.current
            else _net.Driven(port=feed_port(k, f), voltage=f.voltage)
            for k, f in enumerate(self.feeds, 1)
        ]
        return _collapse_gyrator_drives(ports, branches, sources)


def read_nec(
    builder, name: str, *, network: bool = False, virtualize_anchors: bool = True
) -> NecDeck:
    """``read_data`` followed by ``parse_nec`` — load a NEC card deck that
    ships next to ``builder``'s design, with the same folder confinement as
    ``read_json``. ``network=True`` translates the deck's expressible
    LD/TL/NT cards into ``deck.network()`` (see the module docstring);
    ``virtualize_anchors`` forwards to ``parse_nec`` (issue #427, AK#1577)."""
    return parse_nec(
        read_data(builder, name),
        name=name,
        network=network,
        virtualize_anchors=virtualize_anchors,
    )


# nec2c-readable plain number. Deliberately stricter than Python's float()
# (which also takes "nan", "inf" and digit underscores) and excludes Fortran
# D exponents, so anything unusual is routed through evaluation + reformat.
_PLAIN_NUM_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\Z")
# A filename field (SOMEX10.NEC, radials.vg): a stem, a dot, an alphabetic
# extension -- never a number, never a 4nec2 expression.
_FILENAME_RE = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z][A-Za-z0-9]{1,4}")


def _format_field(v: float) -> str:
    """Shortest exact decimal for a resolved card field; integral values are
    written without a decimal point so integer-read fields stay clean."""
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return repr(v)


def _close_parens(line: str) -> str:
    """Remove whitespace (and separating commas) inside balanced parentheses,
    so a 4nec2 expression written with spaces stays one field (#1273):
    ``GM 0 0 0 0 0 (dHelix/2 - dCplLoop/2 - clSep)/1000 0 clZ/1000 1``."""
    out, depth = [], 0
    for ch in line:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif depth > 0 and ch in " \t,":
            continue
        out.append(ch)
    return "".join(out)


_NUMBER_TOKEN = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eEdD][+-]?\d+)?$")


def _split_card_fields(line: str) -> list[str]:
    """Card fields, free format. Commas and whitespace separate; an expression
    inside parentheses keeps its spaces (#1273); and on a TAB-delimited 4nec2
    card an expression with spaces around its operators inside one tab field
    (``Fz + 0.24529``) is rejoined: tabs split first, a tab field then splits
    on spaces, and only a bare operator token glues its two neighbours back
    together, so a mixed tab/space deck keeps its plain numbers apart."""
    if "(" in line:
        line = _close_parens(line)
    if "\t" not in line:
        return line.replace(",", " ").split()
    out: list[str] = []
    for field in re.split(r"[\t,]+", line):
        parts = field.split()
        i = 0
        while i < len(parts):
            if parts[i] in ("+", "-", "*", "/", "^") and 0 < i < len(parts) - 1 and out:
                out[-1] = out[-1] + parts[i] + parts[i + 1]
                i += 2
                continue
            # A number followed by a unit symbol in the SAME tab field (`-68 ft`,
            # `60.7 uh`) is the juxtaposed product the SY evaluator already
            # reads (`SY X=135 ft`). Splitting it shifted every later column: a
            # sloper became a wire 68 m underground. Glued, it evaluates as one
            # value; a number followed by anything else (`4.0 #12`) stays apart.
            if (
                i + 1 < len(parts)
                and _NUMBER_TOKEN.match(parts[i])
                and parts[i + 1].lower() in _SY_UNITS
            ):
                out.append(parts[i] + parts[i + 1])
                i += 2
                continue
            out.append(parts[i])
            i += 1
    return out


# A physical line that starts with a number is not a card: NEC cards open with
# a two-letter mnemonic. Some decks wrap a card's trailing fields onto the next
# line (arrl/RHOM.NEC wraps EVERY card, the GW radius included), so such a line
# continues the card before it (#1295).
_CONTINUATION_START = frozenset("0123456789+-.")


def _logical_lines(text: str):
    """``(line number, text)`` per card, with wrapped continuation lines joined.

    A continuation joins only onto a card line: never onto a blank line, a
    ``CM``/``CE`` comment, or a line carrying a ``'`` comment (the joined fields
    would land after the comment and be dropped with it). The card keeps its
    FIRST line's number, so an error still points at the line the user sees the
    mnemonic on. A deck with no wrapped lines passes through unchanged (#1295).
    """
    pending = None
    for line_no, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if (
            pending is not None
            and stripped[:1] in _CONTINUATION_START
            and stripped
            and pending[1].strip()
            and pending[1].strip()[:2].upper() not in ("CM", "CE")
            and "'" not in pending[1]
        ):
            pending = (pending[0], pending[1].rstrip() + " " + stripped)
            continue
        if pending is not None:
            yield pending
        pending = (line_no, raw)
    if pending is not None:
        yield pending


def resolve_sy(text: str, *, name: str = "NEC deck") -> str:
    """Resolve a 4nec2-dialect deck into plain NEC-2 card text (issue #439).

    Evaluates every ``SY`` symbol (#417, #424 grammar) in deck order and
    substitutes each card field that is not already a plain number —
    symbolic expressions, ``#nn`` AWG gauges, Fortran D exponents — with
    its numeric value, so the deck becomes readable by reference engines
    that know nothing of the dialect (vanilla nec2c). Purely lexical: no
    modelling restrictions apply, and cards ``parse_nec`` would refuse
    (SP, GF, plane-wave EX, ...) pass through with their fields resolved.

    Tolerant-tokenizer forms nec2c cannot read (#418) are normalized too:
    ``'`` comment lines and end-of-line comments are dropped, fused
    mnemonics (``GW1,8,...``) are split, and comma separators become
    spaces. ``SY`` cards are consumed, not emitted. Comment cards keep
    their leading position (a ``CE`` is inserted before the first real
    card if the deck never wrote one); glued mid-deck comments
    (``cmRP ...`` commented-out cards) are dropped. Text after ``EN`` is
    dropped. Numbers already plain are kept byte-for-byte.

    Raises ``ValueError`` (with ``name`` and the line number) on a
    malformed card mnemonic or ``SY`` definition. A card *field* that
    fails to evaluate is kept verbatim instead (filename fields on
    GN/WG/GF cards look like expressions but aren't).
    """
    syms: dict[str, float] = {}
    out: list[str] = []
    in_comments = True
    wrote_comment = False
    for line_no, raw in _logical_lines(text):
        stripped = raw.strip()
        if not stripped:
            continue
        where = f"{name}, line {line_no}"
        if stripped.startswith("'"):
            continue
        head = stripped[:2].upper()
        if head == "CM":
            if in_comments:
                rest = stripped[2:].strip()
                out.append(f"CM {rest}" if rest else "CM")
                wrote_comment = True
            continue
        if head == "CE":
            if in_comments:
                rest = stripped[2:].strip()
                out.append(f"CE {rest}" if rest else "CE")
                in_comments = False
            continue
        stripped = stripped.split("'", 1)[0].rstrip()
        if not stripped:
            continue
        tokens = _split_card_fields(stripped)
        if (
            len(tokens[0]) > 2
            and tokens[0][:2].isalpha()
            and tokens[0][2] in "0123456789.+-"
        ):
            tokens = [tokens[0][:2], tokens[0][2:], *tokens[1:]]
        mnemonic = tokens[0].upper()
        if len(mnemonic) != 2 or not mnemonic.isalpha():
            raise ValueError(
                f"{where}: expected a NEC card mnemonic, got {tokens[0]!r}"
            )
        if mnemonic == "SY":
            _define_sy(stripped[2:], syms, where)
            continue
        if in_comments:
            if wrote_comment:
                out.append("CE")
            in_comments = False
        fields = []
        for tok in tokens[1:]:
            if _PLAIN_NUM_RE.fullmatch(tok):
                fields.append(tok)
                continue
            try:
                fields.append(_format_field(_value(tok, where, syms)))
            except ValueError:
                # Not everything lettered is an expression: GN/WG/GF cards
                # carry *filename* fields ("WG radials-vg"). Keep the token
                # verbatim — the reference engine sees the most faithful
                # text, and a genuinely undefined symbol in a numeric field
                # surfaces as that engine's own card error, not a silent
                # substitution.
                fields.append(tok)
        out.append(" ".join([mnemonic, *fields]))
        if mnemonic == "EN":
            break
    return "\n".join(out) + "\n"


def _float(token: str, where: str) -> float:
    try:
        return float(token)
    except ValueError:
        # Old Fortran decks write D exponents ("1.0D+03").
        try:
            return float(token.upper().replace("D", "E"))
        except ValueError:
            raise ValueError(f"{where}: bad number {token!r}") from None


# ---------------------------------------------------------------------------
# SY symbolic variables (4nec2 extension, issue #417)
# ---------------------------------------------------------------------------
# 4nec2's expression language is BASIC-flavored: `^` is power, trig works in
# DEGREES (the corpus is full of `sin(360*x)`), `sqr` is square root, `atn`
# arctangent (returning degrees), `int` truncates. Names are matched
# case-insensitively. Evaluation is a whitelisted ast walk — no eval().
_SY_FUNCS = {
    "sin": lambda x: math.sin(math.radians(x)),
    "cos": lambda x: math.cos(math.radians(x)),
    "tan": lambda x: math.tan(math.radians(x)),
    "atn": lambda x: math.degrees(math.atan(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "sqr": math.sqrt,
    "sqrt": math.sqrt,
    "abs": abs,
    "int": lambda x: float(int(x)),
    "log": math.log,
    "exp": math.exp,
}
_SY_CONSTANTS = {
    "pi": math.pi,
    # 4nec2 predefined unit-scale symbols (`SY r = 1.5 * mm`): factors to
    # metres. A deck's own SY definition of the same name wins (the symbol
    # table is consulted before these constants).
    "mm": 1e-3,
    "cm": 1e-2,
    "dm": 0.1,
    "m": 1.0,
    "in": 0.0254,
    "ft": 0.3048,
    # electrical component suffixes (`SY C=36.6pF`, `SY L=0.5uH`)
    "pf": 1e-12,
    "nf": 1e-9,
    "uf": 1e-6,
    "nh": 1e-9,
    "uh": 1e-6,
    "mh": 1e-3,
}


_SY_UNITS = frozenset(
    ("mm", "cm", "dm", "m", "in", "ft", "pf", "nf", "uf", "nh", "uh", "mh")
)
_SY_MAX_LEN = 512
_SY_MAX_TOKENS = 128
_SY_MAX_DEPTH = 32
# number | identifier | operator/paren. Numbers cover 1, 2.5, 3., .5, 1e-3;
# "1..5" tokenizes as two adjacent numbers and fails in the parser.
_SY_TOKEN = re.compile(
    r"\s*(?:"
    r"(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)"
    r"|([A-Za-z_]\w*)"
    r"|([()+\-*/^%])"
    r")"
)

# Binding powers (precedence climbing). 4nec2's expression language follows
# the BASIC convention: ^ is right-associative and binds tighter than unary
# minus (-2^2 = -(2^2) = -4; Excel is the famous outlier). Unary sits
# between * and ^ so -2*3 = (-2)*3 but -2^2 = -(2^2).
_SY_BP = {
    "+": (10, 11),
    "-": (10, 11),
    "*": (20, 21),
    "/": (20, 21),
    "%": (20, 21),
    "^": (40, 39),
}
_SY_UNARY_BP = 30


def _eval_sy_expr(expr: str, syms: dict, where: str) -> float:
    """Evaluate one 4nec2 expression with a dedicated precedence-climbing
    (Pratt) parser (#424) — the grammar is exactly 4nec2's, not Python's:
    no CPython parser in the path, explicit size/depth caps, and a hard
    contract: every failure is a ValueError, every success a finite float.
    """
    text = expr.strip()

    def err(msg: str) -> ValueError:
        return ValueError(f"{where}: SY expression {expr!r}: {msg}")

    # `#14` wire-gauge shorthand inside an expression (`SY D = #12/in`,
    # #1272): substitute the radius before tokenising.
    text = re.sub(r"#(\d+)", lambda m: repr(_awg_radius(int(m.group(1)))), text)
    if not text:
        raise err("empty")
    if len(text) > _SY_MAX_LEN:
        raise err(f"longer than {_SY_MAX_LEN} characters")

    # ---- tokenize -------------------------------------------------------
    tokens: list[tuple[str, object]] = []
    pos = 0
    while pos < len(text):
        m = _SY_TOKEN.match(text, pos)
        if m is None or m.end() == m.start():
            rest = text[pos:].lstrip()
            if not rest:
                break
            raise err(f"unexpected character {rest[0]!r}")
        pos = m.end()
        num, ident, op = m.group(1), m.group(2), m.group(3)
        if num is not None:
            v = float(num)
            if not math.isfinite(v):
                raise err(f"non-finite number literal {num!r}")
            tokens.append(("num", v))
        elif ident is not None:
            tokens.append(("ident", ident.lower()))
        else:
            tokens.append(("op", op))
        if len(tokens) > _SY_MAX_TOKENS:
            raise err(f"more than {_SY_MAX_TOKENS} tokens")
    if not tokens:
        raise err("empty")

    # ---- parse + evaluate in one pass ------------------------------------
    idx = 0

    def peek():
        return tokens[idx] if idx < len(tokens) else (None, None)

    def take():
        nonlocal idx
        t = tokens[idx]
        idx += 1
        return t

    def finite(v: float, what: str) -> float:
        if not math.isfinite(v):
            raise err(f"{what} is not finite")
        return v

    def lookup(name: str) -> float:
        if name in syms:
            return syms[name]
        if name in _SY_CONSTANTS:
            return _SY_CONSTANTS[name]
        raise ValueError(f"{where}: undefined symbol {name!r}")

    def primary(depth: int) -> float:
        kind, val = peek()
        if kind == "num":
            take()
            v = float(val)
            # juxtaposed/glued unit product: `135 ft`, `61ft`, `36.6pF`
            k2, v2 = peek()
            if k2 == "ident" and v2 in _SY_UNITS:
                nxt = tokens[idx + 1] if idx + 1 < len(tokens) else (None, None)
                if nxt != ("op", "("):
                    take()
                    v *= lookup(v2)
            return v
        if kind == "ident":
            take()
            k2, _v2 = peek()
            if k2 == "op" and tokens[idx][1] == "(":
                fn = _SY_FUNCS.get(val)
                if fn is None:
                    raise err(f"unknown function {val!r}")
                take()  # (
                arg = climb(0, depth + 1)
                k3, v3 = peek()
                if (k3, v3) != ("op", ")"):
                    raise err(f"expected ')' after {val}(...)")
                take()
                try:
                    return finite(float(fn(arg)), f"{val}(...)")
                except (ArithmeticError, ValueError) as e:
                    if isinstance(e, ValueError) and str(e).startswith(where):
                        raise
                    raise err(f"{val}({arg:g}) failed: {e}") from None
            return lookup(val)
        if kind == "op" and val == "(":
            take()
            v = climb(0, depth + 1)
            k2, v2 = peek()
            if (k2, v2) != ("op", ")"):
                raise err("unbalanced parenthesis")
            take()
            return v
        if kind == "op" and val in ("-", "+"):
            take()
            v = climb(_SY_UNARY_BP, depth + 1)
            return -v if val == "-" else v
        if kind is None:
            raise err("ends unexpectedly")
        raise err(f"unexpected {val!r}")

    def apply(op: str, a: float, b: float) -> float:
        try:
            if op == "+":
                r = a + b
            elif op == "-":
                r = a - b
            elif op == "*":
                r = a * b
            elif op == "/":
                r = a / b
            elif op == "%":
                r = math.fmod(a, b)
                if b == 0.0:
                    raise ZeroDivisionError("modulo by zero")
            else:
                r = a**b
        except (ArithmeticError, ValueError) as e:
            raise err(f"'{a:g} {op} {b:g}' failed: {e}") from None
        return finite(r, f"'{a:g} {op} {b:g}'")

    def climb(min_bp: int, depth: int) -> float:
        if depth > _SY_MAX_DEPTH:
            raise err(f"nested deeper than {_SY_MAX_DEPTH}")
        lhs = primary(depth)
        while True:
            kind, val = peek()
            if kind != "op" or val not in _SY_BP:
                return lhs
            lbp, rbp = _SY_BP[val]
            if lbp < min_bp:
                return lhs
            take()
            rhs = climb(rbp, depth + 1)
            lhs = apply(val, lhs, rhs)

    result = climb(0, 0)
    if idx != len(tokens):
        raise err(f"unexpected {tokens[idx][1]!r} after a complete expression")
    return finite(float(result), "result")


def _define_sy(rest: str, syms: dict, where: str) -> None:
    """Apply one SY card: ``name=expr[, name=expr...]['comment]``."""
    body = rest.split("'", 1)[0].strip()  # 4nec2 trailing comment
    if not body:
        raise ValueError(f"{where}: SY card without an assignment")
    # Split on top-level commas only (function args never contain commas in
    # the 4nec2 single-argument vocabulary, but stay paren-aware anyway).
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(body):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(body[start:i])
            start = i + 1
    parts.append(body[start:])
    for part in parts:
        if "=" not in part:
            raise ValueError(f"{where}: SY assignment {part.strip()!r} has no '='")
        name, expr = part.split("=", 1)
        name = name.strip()
        if not name.isidentifier():
            raise ValueError(f"{where}: SY name {name!r} is not a valid symbol")
        syms[name.lower()] = _eval_sy_expr(expr, syms, where)


def _awg_radius(gauge: int) -> float:
    """AWG gauge -> wire radius in metres."""
    return 0.5 * 0.127e-3 * 92.0 ** ((36.0 - gauge) / 39.0)


def _value(token: str, where: str, syms: dict | None) -> float:
    """A card field: a plain number, 4nec2's ``#nn`` AWG wire-gauge
    shorthand (a radius, in metres), or (when the deck defined SY symbols
    or the token contains a letter) a 4nec2 expression."""
    if token.startswith("#"):
        # AWG gauge n -> diameter 0.127 mm * 92^((36-n)/39); field is a
        # radius in metres. 4nec2 writes `#14`-style GW radius fields (#418),
        # and `#12/ft` / `#14/in` when the deck's own unit is feet or inches
        # (the radius then reads in that unit, like `.1in/ft`, #1272): the
        # tail after the gauge is an expression applied to the radius.
        m = re.match(r"#(\d+)(.*)\Z", token)
        if m is None:
            raise ValueError(f"{where}: bad wire gauge {token!r}")
        radius = _awg_radius(int(m.group(1)))
        if m.group(2):
            return _eval_sy_expr(repr(radius) + m.group(2), syms or {}, where)
        return radius
    try:
        return _float(token, where)
    except ValueError:
        if syms is not None and any(c.isalpha() or c in "()*/+-^" for c in token):
            return _eval_sy_expr(token, syms, where)
        raise


class _Card:
    """One card line: mnemonic + zero-padded numeric field access."""

    def __init__(
        self,
        mnemonic: str,
        tokens: list[str],
        where: str,
        syms: dict | None = None,
    ):
        self.mnemonic = mnemonic
        self.where = where
        # 4nec2 lets EX, LD, TL and NT give a segment as a percentage of the
        # wire's length from end 1 ("50%", AK#1496). Such a field is kept
        # here; only `percent()` reads it, and `f()` / `i()` refuse it.
        self.pct: dict[int, float] = {}
        self.vals = []
        for k, token in enumerate(tokens):
            if len(token) > 1 and token.endswith("%"):
                self.pct[k] = _value(token[:-1], where, syms)
                self.vals.append(0.0)
            else:
                self.vals.append(_value(token, where, syms))

    def f(self, k: int) -> float:
        if k in self.pct:
            raise self.error(
                f"field {k + 1} is a percentage ({self.pct[k]:g}%), which 4nec2 "
                "allows only as a position on a wire, in EX, LD, TL and NT"
            )
        return self.vals[k] if k < len(self.vals) else 0.0

    def percent(self, k: int) -> float | None:
        """The percentage in field ``k``, or None when it is a plain number."""
        return self.pct.get(k)

    def i(self, k: int) -> int:
        return int(round(self.f(k)))

    def error(self, msg: str) -> ValueError:
        return ValueError(f"{self.where}: {self.mnemonic} card: {msg}")


# Internal mutable wire: [tag, n_seg, [x,y,z], [x,y,z], radius].


def _gw(card, wires):
    tag, n_seg = card.i(0), card.i(1)
    if n_seg < 1:
        raise card.error(f"segment count must be >= 1, got {n_seg}")
    radius = card.f(8)
    p1 = [card.f(2), card.f(3), card.f(4)]
    p2 = [card.f(5), card.f(6), card.f(7)]
    # A zero radius is NEC's announcement that a GC continuation follows and
    # carries the taper (#1294). The wire is parked as-is; `_gc` pops it and
    # expands it, and `_no_pending_taper` refuses it if the GC never comes.
    wires.append([tag, n_seg, p1, p2, radius])


def _taper_steps(n_seg, total, rdel, rad1, rad2):
    """Per-segment (length, radius) for a GC-tapered run.

    Both progressions are GEOMETRIC, which is what nec2c produces and what
    this was derived from rather than assumed:

    * lengths -- ``L[i+1] = L[i] * rdel``, scaled so the run still spans the
      GW's own endpoints. On `ch-3/3-1a-nec2.nec` (9 segments over 0.232 m,
      rdel 0.8163265) that predicts L1 = 0.050785 and nec2c prints 0.0508.
    * radii -- geometric from ``rad1`` to ``rad2``. On `YI20_40B.NEC`
      (16 segments, .006 -> .011) the ratio is (11/6)^(1/15) = 1.041237 and
      every one of nec2c's sixteen printed radii matches.
    """
    if rdel == 1.0:
        lengths = [total / n_seg] * n_seg
    else:
        first = total * (1.0 - rdel) / (1.0 - rdel**n_seg)
        lengths = [first * rdel**i for i in range(n_seg)]
    if n_seg == 1 or rad1 == rad2:
        radii = [rad1] * n_seg
    else:
        ratio = (rad2 / rad1) ** (1.0 / (n_seg - 1))
        radii = [rad1 * ratio**i for i in range(n_seg)]
    return lengths, radii


def _gc(card, wires):
    """Tapered-wire continuation: expand the preceding zero-radius GW into a
    run of 1-segment wires with stepped radii and RDEL-progressed lengths.

    They keep the GW's tag, so NEC's ``(tag, segment)`` addressing on EX / LD
    / TL still resolves -- `_locate_segment` accumulates across every wire
    carrying the tag, which is the same thing `_gh` relies on.
    """
    if not wires or wires[-1][4] > 0.0:
        raise card.error(
            "a GC continuation must follow a GW with zero radius, which is "
            "how NEC announces a tapered wire"
        )
    itg, ns = card.i(0), card.i(1)
    if itg != 0 or ns != 0:
        raise card.error(
            f"only the plain continuation form (GC 0 0 RDEL RAD1 RAD2) is "
            f"translated, got tag {itg} and segment count {ns}"
        )
    rdel, rad1, rad2 = card.f(2), card.f(3), card.f(4)
    if rdel <= 0.0:
        raise card.error(f"segment-length ratio must be > 0, got {rdel}")
    if rad1 <= 0.0 or rad2 <= 0.0:
        raise card.error(f"both taper radii must be > 0, got {rad1} and {rad2}")
    tag, n_seg, p1, p2, _zero = wires.pop()
    d = [p2[k] - p1[k] for k in range(3)]
    total = math.sqrt(sum(c * c for c in d))
    if total <= 0.0:
        raise card.error("the tapered wire has zero length")
    unit = [c / total for c in d]
    lengths, radii = _taper_steps(n_seg, total, rdel, rad1, rad2)
    at = list(p1)
    for length, radius in zip(lengths, radii, strict=True):
        nxt = [at[k] + unit[k] * length for k in range(3)]
        wires.append([tag, 1, list(at), nxt, radius])
        at = nxt


def _snap_nec_connections(wires):
    """Snap wire ends that NEC considers connected onto exact shared
    coordinates, in place.

    NEC engines connect segments whose ends coincide within 1e-3 of a
    segment length — the grouping into GW wires is irrelevant. The exact
    rule in nec2c's ``conect()``: L1 (Manhattan) separation <= SMIN=1e-3
    times the CONNECTING segment's own length, applied per end (so a
    mixed-length pair effectively links under the larger tolerance). We
    match the L1 norm and take the per-pair MINIMUM segment length — the
    conservative intersection: never connects what any NEC build would
    leave open, at the cost of missing pairs in the narrow
    (1e-3*min, 1e-3*max) band.
    antennaknobs' engines junction wire ends on (near-)exact coordinate
    matches instead (``flat_wires_to_polylines`` quantizes at 1e-6 m,
    ``_junction_cuts`` at 1e-9 m), so a deck whose corners sit
    microscopically apart solves as a BROKEN electrical graph: current
    pinned to zero at every unmatched end. That is not a hypothetical —
    GM-rotated copies of 6-significant-digit card coordinates land ~1e-6 m
    off the endpoints they must join (the qantenna delta-loop-15m corners
    sit 1.1 um apart, and every momwire basis solved three broken
    triangles that never resonate while nec2c/nec2++/NEC-5 all connected
    them — momwire#302).

    Two passes, both endpoint moves <= the NEC tolerance (<= 0.1 % of one
    segment — far below solver noise):

      1. cluster wire ENDPOINTS under the per-pair NEC tolerance
         (union-find) and rewrite each cluster to its first member;
      2. snap remaining endpoints onto OTHER wires' interior segment
         boundaries within tolerance, computed with bitwise the same
         ``a + (b - a) * (k / n_seg)`` formula ``_junction_cuts`` and
         ``wire_tuples`` use, so the mid-wire touch is later detected as
         a cut (NEC connects a wire end running into another wire's
         segment boundary the same way).

    Gaps wider than the tolerance are left alone — NEC treats those as
    open, so deliberately gapped geometry is unaffected.
    """

    def l1(a, b):
        return sum(abs(x - y) for x, y in zip(a, b, strict=True))

    end_seg_len = []  # per endpoint (2 per wire): its wire's segment length
    pts = []  # (coordinate tuple) per endpoint, index = 2*wire + (0|1)
    for _tag, n_seg, p1, p2, _rad in wires:
        seg = math.dist(p1, p2) / n_seg
        for p in (p1, p2):
            end_seg_len.append(seg)
            pts.append(tuple(float(c) for c in p))

    max_tol = 1e-3 * max(end_seg_len)
    if max_tol <= 0.0:
        return

    def cell(p):
        return tuple(math.floor(c / max_tol) for c in p)

    def neighborhood(grid, p):
        cx, cy, cz = cell(p)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    yield from grid.get((cx + dx, cy + dy, cz + dz), ())

    # Pass 1: endpoint clusters. Union-find under the per-pair tolerance.
    grid = {}
    for k, p in enumerate(pts):
        grid.setdefault(cell(p), []).append(k)
    parent = list(range(len(pts)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for k, p in enumerate(pts):
        for j in neighborhood(grid, p):
            if j <= k:
                continue
            if l1(p, pts[j]) <= 1e-3 * min(end_seg_len[k], end_seg_len[j]):
                parent[find(j)] = find(k)

    for k in range(len(pts)):
        root = find(k)
        if root != k:
            wi, end = divmod(k, 2)
            wires[wi][2 + end] = list(pts[root])
            pts[k] = pts[root]

    # Pass 2: endpoints onto other wires' interior segment boundaries
    # (recomputed after pass 1 so moved ends shift their boundaries too).
    bgrid = {}
    boundaries = []  # (wire_idx, coordinate tuple)
    for wi, (_tag, n_seg, p1, p2, _rad) in enumerate(wires):
        for k in range(1, n_seg):
            t = k / n_seg
            b = tuple(a + (b_ - a) * t for a, b_ in zip(p1, p2, strict=True))
            bgrid.setdefault(cell(b), []).append(len(boundaries))
            boundaries.append((wi, b))

    for k, p in enumerate(pts):
        wi, end = divmod(k, 2)
        best = None
        for j in neighborhood(bgrid, p):
            bw, b = boundaries[j]
            if bw == wi or b == p:
                continue
            d = l1(p, b)
            seg_b = end_seg_len[2 * bw]
            if d <= 1e-3 * min(end_seg_len[k], seg_b) and (best is None or d < best[0]):
                best = (d, b)
        if best is not None:
            wires[wi][2 + end] = list(best[1])


def _ga(card, wires):
    """Wire arc in the XZ plane (nec2c ``arc``): ``n_seg`` 1-segment chords."""
    tag, n_seg = card.i(0), card.i(1)
    rada, ang1, ang2, radius = card.f(2), card.f(3), card.f(4), card.f(5)
    if n_seg < 1:
        raise card.error(f"segment count must be >= 1, got {n_seg}")
    if radius <= 0.0:
        raise card.error("wire radius must be > 0")
    if abs(ang2 - ang1) >= 360.00001:
        raise card.error("arc angle exceeds 360 degrees")
    ang = ang1 * _DEG
    dang = (ang2 - ang1) * _DEG / n_seg
    x1, z1 = rada * math.cos(ang), rada * math.sin(ang)
    for _ in range(n_seg):
        ang += dang
        x2, z2 = rada * math.cos(ang), rada * math.sin(ang)
        wires.append([tag, 1, [x1, 0.0, z1], [x2, 0.0, z2], radius])
        x1, z1 = x2, z2


def _gh(card, wires):
    """Helix/spiral about +Z (nec2c ``helix``): ``n_seg`` 1-segment chords."""
    tag, n_seg = card.i(0), card.i(1)
    s, hl = card.f(2), card.f(3)
    a1, b1, a2, b2 = card.f(4), card.f(5), card.f(6), card.f(7)
    radius = card.f(8)
    if n_seg < 1:
        raise card.error(f"segment count must be >= 1, got {n_seg}")
    if radius <= 0.0:
        raise card.error("wire radius must be > 0")
    if s == 0.0 or hl == 0.0:
        raise card.error("turn spacing and helix length must be nonzero")
    zinc = abs(hl / n_seg)
    if a2 == a1 and b1 == 0.0:
        b1 = a1
    if a2 != a1 and b2 == 0.0:
        b2 = a2

    def point(z):
        if a2 == a1:
            a, b = a1, b1
        else:
            a = a1 + (a2 - a1) * z / abs(hl)
            b = b1 + (b2 - b1) * z / abs(hl)
        x = a * math.cos(2.0 * math.pi * z / s)
        y = b * math.sin(2.0 * math.pi * z / s)
        # hl < 0 winds the helix left-handed (nec2c swaps x and y).
        return [y, x, z] if hl < 0.0 else [x, y, z]

    z1 = 0.0
    for _ in range(n_seg):
        z2 = z1 + zinc
        wires.append([tag, 1, point(z1), point(z2), radius])
        z1 = z2


def _first_wire_with_tag(wires, tag, card):
    if tag <= 0:
        return 0
    for i, w in enumerate(wires):
        if w[0] == tag:
            return i
    raise card.error(f"no wire has tag {tag}")


def _gm(card, wires):
    """Move / replicate (nec2c ``move``): rotate about X then Y then Z (deg),
    translate, optionally repeat cumulatively with a tag increment."""
    itgi, nrpt = card.i(0), card.i(1)
    rox, roy, roz = card.f(2) * _DEG, card.f(3) * _DEG, card.f(4) * _DEG
    xs, ys, zs = card.f(5), card.f(6), card.f(7)
    its = int(card.f(8) + 0.5)  # nec2c reads ITS as a float and rounds

    sps, cps = math.sin(rox), math.cos(rox)
    sth, cth = math.sin(roy), math.cos(roy)
    sph, cph = math.sin(roz), math.cos(roz)
    m = (
        (cph * cth, cph * sth * sps - sph * cps, cph * sth * cps + sph * sps),
        (sph * cth, sph * sth * sps + cph * cps, sph * sth * cps - cph * sps),
        (-sth, cth * sps, cth * cps),
    )

    def xf(p):
        return [
            p[0] * m[0][0] + p[1] * m[0][1] + p[2] * m[0][2] + xs,
            p[0] * m[1][0] + p[1] * m[1][1] + p[2] * m[1][2] + ys,
            p[0] * m[2][0] + p[1] * m[2][1] + p[2] * m[2][2] + zs,
        ]

    i1 = _first_wire_with_tag(wires, its, card)
    if nrpt == 0:
        for w in wires[i1:]:
            w[2], w[3] = xf(w[2]), xf(w[3])
        return
    block = wires[i1:]
    for _ in range(nrpt):
        # Each repetition transforms the *previous* copy, so rotations and
        # translations compound — that is how one loop side GM-replicates
        # into a square, or one bay into a stack.
        block = [
            [tag + itgi if tag != 0 else 0, ns, xf(p1), xf(p2), rad]
            for tag, ns, p1, p2, rad in block
        ]
        wires.extend(block)


def _reflect(card, wires, axis, iti, plane_name):
    new = []
    for tag, ns, p1, p2, rad in wires:
        e1, e2 = p1[axis], p2[axis]
        if abs(e1) + abs(e2) <= 1.0e-5 or e1 * e2 < -1.0e-6:
            raise card.error(
                f"a wire lies in or crosses the {plane_name} symmetry plane"
            )
        q1, q2 = list(p1), list(p2)
        q1[axis], q2[axis] = -e1, -e2
        new.append([tag + iti if tag != 0 else 0, ns, q1, q2, rad])
    wires.extend(new)


def _gx(card, wires):
    """Reflect in the Z=0, then Y=0, then X=0 planes (nec2c ``reflc``). The
    tag increment doubles after each reflection so every image stays unique."""
    iti = card.i(0)
    code = card.i(1)
    ix, iy, iz = (code // 100) % 10, (code // 10) % 10, code % 10
    for axis, flag, plane in ((2, iz, "Z=0"), (1, iy, "Y=0"), (0, ix, "X=0")):
        if flag:
            _reflect(card, wires, axis, iti, plane)
            iti *= 2


def _gr(card, wires):
    """Rotate about Z to form a cylindrical structure of ``nop`` copies."""
    itg, nop = card.i(0), card.i(1)
    if nop < 1:
        raise card.error(f"structure count must be >= 1, got {nop}")
    sam = 2.0 * math.pi / nop
    cs, ss = math.cos(sam), math.sin(sam)
    block = wires[:]
    for _ in range(nop - 1):
        block = [
            [
                tag + itg if tag != 0 else 0,
                ns,
                [p1[0] * cs - p1[1] * ss, p1[0] * ss + p1[1] * cs, p1[2]],
                [p2[0] * cs - p2[1] * ss, p2[0] * ss + p2[1] * cs, p2[2]],
                rad,
            ]
            for tag, ns, p1, p2, rad in block
        ]
        wires.extend(block)


def _gs(card, wires):
    """Scale all dimensions; xnec2c extension: nonzero I1..I2 scales only
    wires whose tag falls in that range."""
    lo, hi, factor = card.i(0), card.i(1), card.f(2)
    if factor <= 0.0:
        raise card.error(f"scale factor must be > 0, got {factor}")
    ranged = lo > 0 and hi >= lo
    for w in wires:
        if ranged and not (lo <= w[0] <= hi):
            continue
        w[2] = [c * factor for c in w[2]]
        w[3] = [c * factor for c in w[3]]
        w[4] *= factor


@dataclass(frozen=True)
class _Pct:
    """A percentage segment field, parked until the geometry is final."""

    value: float


def _percent_position(wires, tag, pct, card, *, legacy=False):
    """4nec2's percentage position (AK#1496): ``pct`` percent of the length of
    the one wire tagged ``tag``, measured from its end 1. Returns (wire index,
    the 1-based segment whose centre is nearest, the position as a fraction).

    The segment is what a path without positioned ports (``legacy``) feeds. A
    position exactly on the boundary between two segments is equally near
    both centres, so that path refuses it rather than choose one (AK#1510).
    The network path feeds the fraction instead: the exact position (a port at
    that point, AK#1469), or None at 0 % or 100 %, where a gap cannot sit, so
    the end segment's centre is used. Its segment takes the lower of two at a
    boundary."""
    if not 0.0 <= pct <= 100.0:
        raise card.error(f"a position of {pct:g}% is off the wire (0% to 100%)")
    if tag == 0:
        raise card.error(
            f"a percentage position ({pct:g}%) needs a wire tag: tag 0 names no wire"
        )
    matches = [i for i, w in enumerate(wires) if w[0] == tag]
    if not matches:
        raise card.error(f"no wire has tag {tag}")
    if len(matches) > 1:
        raise card.error(
            f"tag {tag} names {len(matches)} wires, so {pct:g}% of the wire is "
            "ambiguous; give each wire its own tag"
        )
    i = matches[0]
    n = wires[i][1]
    x = pct / 100.0 * n
    boundary = round(x)
    # The same 1e-9 of a segment within which the ceiling below reads a
    # position as sitting on a boundary.
    if legacy and 0 < boundary < n and abs(x - boundary) <= 1e-9:
        raise card.error(
            f"{pct:g}% of tag {tag} falls exactly on the boundary between "
            f"segments {boundary} and {boundary + 1} of its {n}, so it names no "
            "single segment; parse with network=True, which feeds the exact "
            "position"
        )
    seg = min(n, max(1, math.ceil(x - 1e-9)))
    frac = pct / 100.0
    return i, seg, (frac if 0.0 < frac < 1.0 else None)


def _attach(wires, card, tag_k, seg_k, nec5=False):
    """(wire index, local segment, position or None, end) for a (tag, segment)
    field pair in either spelling: a segment number or a 4nec2 percentage.

    ``nec5`` reads the segment field the way NEC-5 does on a TL/NT card
    (AK#1579): it names a segment END, not a centre — positive is end 2 of
    that segment, negative is end 1, exactly the sign rule ``EX`` takes with
    ``I4 = 0``. Verified against our licensed NEC-5, which both ECHOES the
    sign back in its NETWORK DATA block and moves the answer: on a 10-segment
    dipole a line attached at ``2`` and at ``-3`` solve bit-identically (one
    knot), and ``2`` and ``-2`` do not. ``end`` is 0 in the NEC-2 reading,
    where the field is the segment whose centre carries the connection.
    """
    pct = card.percent(seg_k)
    if pct is None:
        field = card.i(seg_k)
        end = 0 if not nec5 or field == 0 else (1 if field < 0 else 2)
        wi, seg = _locate_segment(
            wires, card.i(tag_k), abs(field) if end else field, card
        )
        return wi, seg, None, end
    return (*_percent_position(wires, card.i(tag_k), pct, card), 0)


def _knot_sharing(wires):
    """``(lone ends, cuts)`` for the parse-time wire list.

    ``lone ends`` is every ``(wire index, knot)`` at a wire END that no other
    wire touches. A NEC-5 network end there names a node whose only through
    path is the ground contact, and a port in that path is a gap between a
    lone conductor end and its image — which neither engine here hosts:
    momwire refuses a series ``node_gaps`` entry at a one-member junction and
    a shunt ``junction_ports`` entry at a grounded node, and the NEC-5
    multiport route cannot address either. ``cuts`` is ``_junction_cuts``
    computed on the same points, which the collision guard needs before a
    ``NecDeck`` exists (AK#1579).
    """
    eps = 1e-9

    def key(w, k):
        # The same expression `_junction_cuts` uses, so the two agree on
        # which points coincide.
        t = k / w[1]
        return tuple(
            round((a + (b - a) * t) / eps) for a, b in zip(w[2], w[3], strict=True)
        )

    owners: dict[tuple, set[int]] = {}
    for i, w in enumerate(wires):
        for k in range(w[1] + 1):
            owners.setdefault(key(w, k), set()).add(i)
    lone = {
        (i, k)
        for i, w in enumerate(wires)
        for k in (0, w[1])
        if len(owners[key(w, k)]) < 2
    }
    cuts = {
        i: frozenset(k for k in range(1, w[1]) if len(owners[key(w, k)]) > 1)
        for i, w in enumerate(wires)
    }
    return lone, cuts


def _locate_segment(wires, tag, seg, card):
    """Resolve NEC's (tag, segment) addressing to (wire index, 1-based local
    segment): the ``seg``-th segment among wires with that tag, or the
    absolute ``seg``-th segment when ``tag`` is 0."""
    if seg <= 0:
        seg = 1
    acc = 0
    for i, w in enumerate(wires):
        if tag != 0 and w[0] != tag:
            continue
        if acc + w[1] >= seg:
            return i, seg - acc
        acc += w[1]
    if tag != 0 and acc == 0:
        raise card.error(f"no wire has tag {tag}")
    raise card.error(
        f"segment {seg} is out of range — "
        + (f"tag {tag} has" if tag != 0 else "the deck has")
        + f" only {acc} segments"
    )


# How many segments an LD 0/1/4 range may cover before the importer refuses
# to expand it into per-segment Load branches: each expanded segment becomes
# its own named 1-segment wire + MoM port + MNA row, so a wide range (which
# usually means "the whole element" — really distributed loading) would
# shred the mesh for no fidelity gain.
_LD_EXPAND_MAX = 8


def _seg_mid(w, seg: int, at: float | None = None):
    """Midpoint of 1-based local segment ``seg`` of a parse-time wire
    ``[tag, n_seg, p1, p2, radius]`` — NEC's connection point for a
    zero-length TL's straight-line-distance rule — or the exact point a 4nec2
    percentage position ``at`` names."""
    t = (seg - 0.5) / w[1] if at is None else at
    return [a + (b - a) * t for a, b in zip(w[2], w[3], strict=True)]


def _end_shunt(y: complex, virtual: bool) -> tuple[float | None, complex | None]:
    """Translate one TL end admittance ``y = G + jB`` into a ``(shunt_r,
    shunt_y)`` pair for ``NecTL`` — at most one is non-None:

    - conductance-only (``B == 0``, real end) → ``shunt_r = 1/G`` (a
      frequency-dependent ``Shunt`` in ``network()``);
    - reactive (``B != 0``, issue #423) or any virtual-node termination
      (remote TL anchor, issue #427) → ``shunt_y = y``, a fixed 1-port
      ``Admittance`` carrying the full complex Y, exact at every frequency;
    - a zero end is an open (both ``None``).

    A reactive end is no longer dropped: NEC's constant ``B`` is
    frequency-independent, which is exactly what the fixed ``Admittance``
    primitive (issue #416) expresses.
    """
    if y == 0:
        return None, None
    if y.imag != 0.0 or virtual:
        return None, y
    return 1.0 / y.real, None


# A gyrator's whole transfer IS its off-diagonal, and that off-diagonal is
# purely reactive. Below this susceptance the branch forces nothing, so
# reading it as a current source would be reading float noise as a drive.
# EZNEC and 4nec2 both write Y12 = ±j exactly.
_GYRATOR_MIN_B = 1e-12


def _collapse_gyrator_drives(ports, branches, sources):
    """``(ports, branches, sources, gyrators)`` with NEC-2's gyrator-emulated
    current sources read as the current sources they are (AK#1595).

    NEC-2 has no current-source ``EX`` card, so EZNEC — and 4nec2, see
    ``scripts/bench_nec_corpus.py``'s ``gyrator_reference``, which builds this
    same construction from the other side — spells one as a GYRATOR: an ``NT``
    with Y11 = Y22 = 0 and Y12 = Y21 = jB tying a phantom segment carrying an
    ``EX 0`` voltage source to the real feed segment. Read literally (AK#1577
    makes that phantom segment a ``PortVirtual``) the CIRCUIT is right and the
    READOUT is not: a gyrator inverts impedance, Z_in = 1/(B²·Z_load), so the
    driving point reported where the source sits is the reciprocal of the
    antenna's. Measured on Dan AC6LA's Cardioid, the same antenna EZNEC also
    wrote with ``EX 6``: 0.021584 + 0.011249j against 36.4347 − 18.9882j.

    ``nec_import`` already turns NEC-4's ``EX 6`` and NEC-5's ``EX 4`` into a
    ``DrivenCurrent`` on the real segment. This is the same physical object
    spelled the only way NEC-2 can spell it, so it imports to the same thing
    and all three dialects of one antenna give one network.

    The forced current is ``I = −Y_rv·V``. The reducer stamps ``y`` as a nodal
    admittance block, so ``(y·V)_r`` is the current leaving node r INTO the
    branch and the antenna receives its negative. Sign and scale are EZNEC's
    own to check: Y12 = +j with V = 1.414214j gives 1.414214, which is exactly
    what the NEC-4.2 twin's ``EX 6`` asks for — on both of the Cardioid's
    ports, whose drives differ in phase.

    Detection has to be NARROW, because the same phantom wire legitimately
    spells a source behind a TRANSFORMER or a transmission LINE (AK#1577,
    ``tests/fixtures/eznec_virtual_wire_1577/``) and there the source-side
    impedance is precisely what the user asked for. All of these must hold:

    - zero diagonal, and off-diagonals equal and purely reactive. An EZNEC
      transformer is an all-real Y, which arrives as its exact resistive pi
      and is not an ``Admittance`` branch at all; a lossy line is lossy, so
      its 2×2 has a nonzero diagonal. Neither survives the first test;
    - exactly one side on a ``PortVirtual``, the other on real geometry. A
      line between two virtual nodes drives nothing, and a gyrator between two
      real ports is a component of the model rather than a source;
    - that virtual node carries one source, a ``Driven`` with a nonzero EMF —
      the voltage the gyrator converts. Zero is the datum pin, not a drive.

    Other branches on the node must be 1-ports: the idiom's own ``LD 4 …
    1.E+10`` open-circuit pin lands there, and a shunt across an ideal voltage
    source injects nothing into the rest of the circuit, so it collapses with
    the node it was holding up.
    """
    src_at: dict[str, list[int]] = {}
    for i, s in enumerate(sources):
        src_at.setdefault(s.port, []).append(i)
    touch: dict[str, set[int]] = {}
    for i, br in enumerate(branches):
        for p in _net._branch_port_refs(br):
            touch.setdefault(p, set()).add(i)

    gyrators: dict[str, str] = {}
    drop_branches: set[int] = set()
    swap: dict[int, object] = {}
    for i, br in enumerate(branches):
        if not isinstance(br, _net.Admittance) or len(br.ports) != 2:
            continue
        (y11, y12), (y21, y22) = br.y
        if y11 or y22 or y12 != y21:
            continue
        if y12.real or abs(y12.imag) < _GYRATOR_MIN_B:
            continue
        virtual = [p for p in br.ports if isinstance(ports.get(p), _net.PortVirtual)]
        if len(virtual) != 1:
            continue
        v = virtual[0]
        real = br.ports[1] if br.ports[0] == v else br.ports[0]
        # The real port must be free: it becomes the driven one, and a second
        # source (or a second gyrator) there would be two drives on one node.
        if src_at.get(real) or real in gyrators.values():
            continue
        held = src_at.get(v, ())
        if len(held) != 1:
            continue
        src = sources[held[0]]
        if not isinstance(src, _net.Driven) or not src.voltage:
            continue
        if any(len(_net._branch_port_refs(branches[j])) != 1 for j in touch[v] - {i}):
            continue
        gyrators[v] = real
        drop_branches |= touch[v]
        swap[held[0]] = _net.DrivenCurrent(port=real, current=-y12 * src.voltage)

    if not gyrators:
        return ports, branches, sources, gyrators
    return (
        {n: p for n, p in ports.items() if n not in gyrators},
        [br for i, br in enumerate(branches) if i not in drop_branches],
        [swap.get(i, s) for i, s in enumerate(sources)],
        gyrators,
    )


def _segment_range(wires, tag, sf, st, card):
    """All (wire index, local segment) pairs an LD card's range covers:
    NEC's tag/range addressing — tag 0 + range 0 is the whole structure,
    tag 0 + a range is absolute segment numbers, a tag with range 0 is
    every segment of that tag, and a tag with a range is local segment
    numbers within the tag."""
    if tag == 0 and sf == 0:
        return [(i, s) for i, w in enumerate(wires) for s in range(1, w[1] + 1)]
    if sf == 0:
        pairs = [
            (i, s)
            for i, w in enumerate(wires)
            if w[0] == tag
            for s in range(1, w[1] + 1)
        ]
        if not pairs:
            raise card.error(f"no wire has tag {tag}")
        return pairs
    st = max(st, sf)
    return [_locate_segment(wires, tag, s, card) for s in range(sf, st + 1)]


def _abs_segment(wires, wi, seg):
    """1-based absolute segment number of local segment ``seg`` on wire
    ``wi`` — NEC numbers segments consecutively in structure order."""
    return sum(w[1] for w in wires[:wi]) + seg


def _from_abs_segment(wires, idx):
    """Inverse of ``_abs_segment``: (wire index, local segment), or None
    when the absolute number falls outside the structure."""
    for i, w in enumerate(wires):
        if idx <= w[1]:
            return (i, idx)
        idx -= w[1]
    return None


def _symmetry_cell_pairs(wires, pairs, cell):
    """Apply NEC's symmetry-cell rule to a card's (wire, segment) pairs
    (issue #946), returning ``(pairs, dropped)``.

    ``GX``/``GR`` declare the structure symmetric, and NEC then builds the
    matrix on one *cell* — the structure as it stood when the card fired.
    Anything that enters the matrix can therefore only be expressed
    cell-wide, and ``LOAD`` finishes by stamping the cell's loading onto
    every copy (NEC-2 Fortran: ``NOP=N/NP`` then
    ``DO 3 I=1,NP ... ZARRAY(L1)=ZT``). Two consequences, both reproduced
    on nec2c and nec5cl:

    * a pair inside the cell applies to the same segment of every copy;
    * a pair outside the cell is *overwritten* by that pass — the card is
      written and then destroyed, so it has no effect at all.

    ``cell`` is the cell size in segments, or None when the structure
    carries no live symmetry (the common case — any ``GW`` after the
    replication collapses it).
    """
    total = sum(w[1] for w in wires)
    if not cell or cell >= total:
        return pairs, 0
    nop = total // cell
    out: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    dropped = 0
    for wi, s in pairs:
        idx = _abs_segment(wires, wi, s)
        if idx > cell:
            dropped += 1
            continue
        for k in range(nop):
            p = _from_abs_segment(wires, idx + k * cell)
            if p is not None and p not in seen:
                seen.add(p)
                out.append(p)
    return out, dropped


def _symmetry_after(mnemonic, card, wires, segs_before, cell):
    """The symmetry cell (in segments) after a geometry card, or None for
    no symmetry — the preserve/destroy rules, from the NEC-2 Fortran.

    Only ``GX``/``GR`` create symmetry, and they set the cell to whatever
    the structure was when they fired (``REFLC``: ``NP=N``). It survives a
    congruence of the *whole* structure and dies the moment anything is
    added or transformed selectively:

    * ``GW``/``GA``/``GH`` — ``WIRE``/``HELIX`` unconditionally do
      ``NP=N; IPSYM=0``: the new structure belongs to no copy.
    * ``GM`` — ``MOVE`` returns early, leaving symmetry intact, only for
      ``IF ((NRPT.EQ.0).AND.(IX.EQ.1))``: no replication, and the move
      starting at the first segment.
    * ``GS`` — whole-structure scaling keeps it (measured). The tag-ranged
      form is an xnec2c extension NEC-2 has no field for, and it *is*
      selective, so it drops symmetry rather than claiming a parity we
      cannot check.
    """
    if mnemonic in ("GX", "GR"):
        return segs_before or None
    if mnemonic in ("GW", "GA", "GH"):
        return None
    if mnemonic == "GM":
        its = int(card.f(8) + 0.5)
        if card.i(1) == 0 and _first_wire_with_tag(wires, its, card) == 0:
            return cell
        return None
    if mnemonic == "GS":
        lo, hi = card.i(0), card.i(1)
        return None if lo > 0 and hi >= lo else cell
    return cell


# Clearance, in wavelengths, beyond which a 1-segment TL-terminated wire is
# treated as an electrically irrelevant remote anchor (issue #427). The
# corpus family parks anchors ~100–500 λ away; NEC's own thin-wire coupling is
# long dead by 10 λ, so a wire this far from everything else is there only to
# give a TL card a far-end segment. Kept conservative so nothing intentional
# (a real end-loaded stub a fraction of a wavelength away) is ever swallowed.
_ANCHOR_CLEARANCE_LAMBDA = 10.0
# The EZNEC virtual wire is electrically negligible in its own right, not
# merely far away (AK#1577): this bounds its end-to-end extent in
# wavelengths. Measured 0.0052 λ on the idiom's own decks.
_VIRTUAL_EXTENT_LAMBDA = 0.05
# At or above this, an LD 4 is not a load but the open-circuit pin the
# EZNEC idiom writes on every virtual segment it uses (AK#1577). EZNEC
# writes 1.E+10 exactly; the margin is for a deck that spells it 1e9.
_VIRTUAL_PIN_OHMS = 1e9
_C_MPS = 299_792_458.0  # speed of light, for wavelength = c / f


def _remote_wire_tests(wires):
    """``(touches, clearance)`` over ``wires`` — the geometry half shared by
    both virtualization idioms (issue #427, AK#1577).

    ``touches(i)`` is True when wire ``i`` shares a segment boundary with any
    other wire (the same ``key()`` quantisation ``wire_tuples`` uses, so the
    two agree on what "connected" means). ``clearance(i)`` is the nearest
    endpoint-to-endpoint distance from wire ``i`` to any other wire — a lower
    bound on true separation, ample at the ≫10 λ scales both idioms park at.

    Closures rather than a precomputed set: the callers test a handful of
    candidate wires, and ``clearance`` is O(n) per call.
    """
    eps = 1e-9

    def key(p):
        return tuple(round(c / eps) for c in p)

    def boundary(w, k):
        t = k / w[1]
        return tuple(a + (b - a) * t for a, b in zip(w[2], w[3], strict=True))

    owners: dict[tuple, set[int]] = {}
    for i, w in enumerate(wires):
        for k in range(w[1] + 1):
            owners.setdefault(key(boundary(w, k)), set()).add(i)

    def touches(i):
        w = wires[i]
        return any(len(owners[key(boundary(w, k))]) > 1 for k in range(w[1] + 1))

    def clearance(i):
        wi = wires[i]
        pts_i = (wi[2], wi[3])
        best = math.inf
        for j, wj in enumerate(wires):
            if j == i:
                continue
            for pj in (wj[2], wj[3]):
                for pi in pts_i:
                    d = math.dist(pi, pj)
                    if d < best:
                        best = d
        return best

    return touches, clearance


def _load_wires(wires, lds_raw):
    """``(loaded, pinned)``: wire indices an LD card singles out, split by
    whether the card is one of the open-circuit PINS the EZNEC virtual-wire
    idiom writes (AK#1577) or a real element.

    A pin is an ``LD 4`` (fixed R + jX) of at least ``_VIRTUAL_PIN_OHMS`` —
    EZNEC writes ``1.E+10`` on every virtual segment it uses, which is how it
    keeps that segment from carrying antenna current. LD 5 is a material
    conductivity, not an element, and a whole-structure card singles out no
    wire; neither appears in either set.
    """
    loaded: set[int] = set()
    pinned: set[int] = set()
    for card in lds_raw:
        if card.i(0) == 5:
            continue  # LD 5 is a material conductivity, not an element
        tag, sf, st = card.i(1), card.i(2), card.i(3)
        if card.percent(2) is not None or card.percent(3) is not None:
            # A 4nec2 percentage position: its wire, whatever the value.
            loaded.add(
                _attach(wires, card, 1, 2 if card.percent(2) is not None else 3)[0]
            )
            continue
        if tag == 0 and sf == 0:
            continue  # whole-structure load — does not single out a wire
        pin = card.i(0) == 4 and abs(complex(card.f(4), card.f(5))) >= _VIRTUAL_PIN_OHMS
        into = pinned if pin else loaded
        for wi, _ in _segment_range(wires, tag, sf, st, card):
            into.add(wi)
    return loaded, pinned


def _anchor_wires(wires, tls_raw, nts_raw, feeds, lds_raw, freq_mhz):
    """Wire indices that are remote TL-anchor wires (issue #427).

    A wire qualifies (all must hold) when it is a 1-segment wire referenced
    ONLY as a TL endpoint — not driven (EX), not carrying a lumped/distributed
    LD, not an NT endpoint, not sharing a node with any other wire — and sits
    a clearance of more than ``_ANCHOR_CLEARANCE_LAMBDA`` wavelengths (and far
    more than its own extent) from the rest of the structure. Such a wire is a
    NEC modeling artifact: it exists to terminate a ``TL`` card and is designed
    to be electrically irrelevant, so ``network()`` replaces it with a
    ``PortVirtual`` termination and ``wire_tuples()`` drops it.

    Needs a frequency to measure clearance in wavelengths: with no FR card
    (``freq_mhz is None``) nothing is virtualized — the safe default is to
    model the deck exactly as written.
    """
    if freq_mhz is None or len(wires) < 2:
        return set()
    # Largest wavelength in the sweep (lowest frequency) — the most
    # conservative clearance threshold.
    lam = _C_MPS / (min(freq_mhz) * 1e6)

    def loc(card, a, b):
        return _attach(wires, card, a, b)[0]

    tl_refs: set[int] = set()
    for card in tls_raw:
        tl_refs.add(loc(card, 0, 1))
        tl_refs.add(loc(card, 2, 3))
    if not tl_refs:
        return set()

    # Wires the network otherwise uses electrically — never anchors. A pin
    # counts here exactly as any other LD does: a 1-segment anchor carrying
    # one is outside this idiom (AK#1577 reads that shape instead).
    excluded: set[int] = {f.wire for f in feeds}
    for card in nts_raw:
        excluded.add(loc(card, 0, 1))
        excluded.add(loc(card, 2, 3))
    loaded, pinned = _load_wires(wires, lds_raw)
    excluded |= loaded | pinned

    touches, clearance = _remote_wire_tests(wires)

    anchors: set[int] = set()
    for i in tl_refs:
        w = wires[i]
        if w[1] != 1 or i in excluded or touches(i):
            continue
        extent = math.dist(w[2], w[3])
        clr = clearance(i)
        if clr > _ANCHOR_CLEARANCE_LAMBDA * lam and clr > 100.0 * extent:
            anchors.add(i)
    return anchors


def _virtual_segment_wires(wires, tls_raw, nts_raw, feeds, lds_raw, freq_mhz):
    """Wire indices that are EZNEC's *virtual wire* (AK#1577).

    EZNEC spells a source that sits behind a transformer or a transmission
    line by parking ONE extra wire ~100 λ away and using its segments as
    circuit nodes: the network cards (``NT``/``TL``) and the source address
    those segments, and each segment it uses is pinned open with an
    ``LD 4 … 1.E+10`` so it carries no antenna current. The deck's own
    ``! *Wire #N for virtual segments.`` comment names it, but that is
    corroboration, not the rule — this detector is structural.

    A wire qualifies when all hold:

    - at least one ``TL``/``NT`` end lands on it (it is a circuit anchor, not
      a far-away antenna);
    - an ``NT`` end or an ``EX`` lands on it — the two shapes today's reading
      cannot serve. A wire that only TERMINATES ``TL`` cards is left exactly
      as it is: that deck imports and solves today (Dan's CardTL.ez class),
      and virtualizing it would move a working answer by 0.53 % — measured on
      an open stub into a pinned 3-segment remote wire, the difference
      between an ideal open and the pinned segment's own small admittance.
      Serving the pin's intent there is right, but it is a change to working
      output and belongs to whatever issue asks for it;
    - it has MORE THAN ONE segment. The 1-segment remote shape belongs to
      issue #427's detector, which reads it as a bare TL termination and whose
      negatives pin a *driven* 1-segment remote wire as electrically real;
    - no LD other than the idiom's own ≥ ``_VIRTUAL_PIN_OHMS`` pins touches
      it (a real load means a real wire);
    - it shares no node with any other wire, stands more than
      ``_ANCHOR_CLEARANCE_LAMBDA`` wavelengths and 100× its own extent clear
      of the structure (issue #427's thresholds), and is itself electrically
      negligible — extent under ``_VIRTUAL_EXTENT_LAMBDA`` λ. Measured: the
      EZNEC virtual wire is 0.0052 λ end to end and the #427 corpus anchors
      0.0025 λ, while the smallest thing anyone models on purpose at that
      distance (a remote element in a coupling study) is a sizable fraction
      of a wavelength. Without this gate a genuinely remote antenna fed
      through a feedline could be swallowed whole.

    A source ON the wire is a TRIGGER here, where issue #427 excludes a driven
    wire by name: the EX becoming a drive on a virtual node is the whole point
    of the idiom.
    """
    if freq_mhz is None or len(wires) < 2:
        return set()
    lam = _C_MPS / (min(freq_mhz) * 1e6)

    net_refs: set[int] = set()  # a TL or NT end lands here
    forcing: set[int] = {f.wire for f in feeds}  # ... and today's reading fails
    for card in nts_raw:
        for a, b in ((0, 1), (2, 3)):
            wi = _attach(wires, card, a, b)[0]
            net_refs.add(wi)
            forcing.add(wi)
    for card in tls_raw:
        net_refs.add(_attach(wires, card, 0, 1)[0])
        net_refs.add(_attach(wires, card, 2, 3)[0])
    candidates = net_refs & forcing
    if not candidates:
        return set()

    loaded, _pinned = _load_wires(wires, lds_raw)
    touches, clearance = _remote_wire_tests(wires)

    out: set[int] = set()
    for i in candidates:
        w = wires[i]
        if w[1] < 2 or i in loaded or touches(i):
            continue
        extent = math.dist(w[2], w[3])
        clr = clearance(i)
        if (
            clr > _ANCHOR_CLEARANCE_LAMBDA * lam
            and clr > 100.0 * extent
            and extent < _VIRTUAL_EXTENT_LAMBDA * lam
        ):
            out.add(i)
    return out


def _translate_network_cards(
    wires,
    lds_raw,
    tls_raw,
    nts_raw,
    feeds,
    freq_mhz,
    virtualize_anchors,
    fr_first_mhz=None,
    is_raw=(),
    sym_cell=None,
    nec5_dialect=False,
):
    """Turn the collected LD/TL/NT cards into NecLoad/NecTL/NecNT records,
    plus (mnemonic, reason) detail for every card instance that stays
    unmodelled. TL/NT resolve first so loads can refuse to co-locate with a
    connection point — our ``Load`` is the port's termination branch, which
    would sit in *parallel* with a TL/NT attached to the same port, not in
    series inside the segment the way NEC composes them."""
    detail: list[tuple[str, str]] = []
    skipped: set[str] = set()

    def skip(mnemonic: str, reason: str) -> None:
        skipped.add(mnemonic)
        if (mnemonic, reason) not in detail:
            detail.append((mnemonic, reason))

    # Two idioms, one representation (a PortVirtual circuit node): issue
    # #427's remote 1-segment TL anchor and AK#1577's EZNEC virtual wire.
    # `anchors` is the union — every site downstream asks "is this wire
    # geometry?" — while `virtual_segments` stays separate for the parts that
    # differ: which LD cards are the idiom's pins, and what skipped_note()
    # says about the wire.
    anchors = (
        _anchor_wires(wires, tls_raw, nts_raw, feeds, lds_raw, freq_mhz)
        if virtualize_anchors
        else set()
    )
    virtual_segments = (
        _virtual_segment_wires(wires, tls_raw, nts_raw, feeds, lds_raw, freq_mhz)
        if virtualize_anchors
        else set()
    )
    anchors |= virtual_segments
    # Anchors actually replaced by a virtual end. Every virtual-segment wire
    # is one by construction (a TL/NT end is what detects it), so they go in
    # whole; a #427 anchor is added by the TL that terminates on it.
    virtualized: set[int] = set(virtual_segments)
    # (wire, segment, Z) per LD 4 pin the idiom writes (AK#1577).
    virtual_pins: list[tuple[int, int, complex]] = []

    def knot_at(wi, seg, edge):
        """Where a NEC-5 knot end sits along its wire, as ``_seg_mid`` takes
        it — the connection point a zero-length TL measures from (AK#1579)."""
        return _knot_of(seg, edge) / wires[wi][1] if edge else None

    lone_ends, wire_cuts = _knot_sharing(wires) if nec5_dialect else (set(), {})
    # Knots a SOURCE already needs as a port. The model carries that node
    # either way, so a network end landing on one is kept even at a lone wire
    # end: demoting it would put the source on the knot and the line on the
    # segment beside it, which is one piece with two attachments (#824).
    driven_knots = {
        (f.wire, _knot_of(f.seg, f.edge))
        for f in feeds
        if f.edge and f.wire not in anchors
    }
    demoted: list[tuple[int, int]] = []

    def shares_a_piece_with_a_source(wi, knot):
        """Would a vertex port at ``knot`` land on the same emitted wire piece
        as a knot SOURCE? ``wire_tuples`` gives each vertex port the piece
        ENDING on its knot and lets knot 0 ride the FIRST piece, so the only
        pairing its cut plan cannot separate is knot 0 against another claim
        with no junction cut between them — which is the #824 refusal."""
        cuts = wire_cuts.get(wi, frozenset())
        return any(
            min(knot, m) == 0 and not any(0 < c < max(knot, m) for c in cuts)
            for w, m in driven_knots
            if w == wi and m != knot
        )

    def hosted(wi, seg, edge):
        """``edge``, or 0 when the knot it names is one the port model cannot
        host a network connection at: a lone wire end (`_knot_sharing`), or a
        knot sharing a piece with a source. A virtualized wire has no ends at
        all, so its segment keeps being the node (AK#1577)."""
        if not edge or wi in anchors:
            return edge
        knot = _knot_of(seg, edge)
        lone = (wi, knot) in lone_ends and (wi, knot) not in driven_knots
        if not lone and not shares_a_piece_with_a_source(wi, knot):
            return edge
        if (wi, knot) not in demoted:
            demoted.append((wi, knot))
        return 0

    tls: list[NecTL] = []
    for card in tls_raw:
        wa, sa, at_a, ea = _attach(wires, card, 0, 1, nec5_dialect)
        wb, sb, at_b, eb = _attach(wires, card, 2, 3, nec5_dialect)
        ea, eb = hosted(wa, sa, ea), hosted(wb, sb, eb)
        va, vb = wa in anchors, wb in anchors
        # End admittances G+jB: a conductance-only end becomes a Shunt(1/G),
        # a reactive one (#423) or a virtual-node termination (#427) a fixed
        # 1-port Admittance. See _end_shunt — susceptance is expressible now,
        # so a reactive end no longer sinks the whole TL.
        shunt_r_a, shunt_y_a = _end_shunt(complex(card.f(6), card.f(7)), va)
        shunt_r_b, shunt_y_b = _end_shunt(complex(card.f(8), card.f(9)), vb)
        z0 = card.f(4)
        if z0 == 0.0:
            raise card.error("characteristic impedance must be nonzero")
        length = card.f(5)
        if length == 0.0:
            # NEC: zero length means the straight-line distance between
            # the connection points — the knots themselves on a NEC-5 deck.
            length = math.dist(
                _seg_mid(
                    wires[wa], sa, at_a if at_a is not None else knot_at(wa, sa, ea)
                ),
                _seg_mid(
                    wires[wb], sb, at_b if at_b is not None else knot_at(wb, sb, eb)
                ),
            )
        tls.append(
            NecTL(
                wire_a=wa,
                seg_a=sa,
                wire_b=wb,
                seg_b=sb,
                z0=abs(z0),
                length=length,
                transposed=z0 < 0.0,
                shunt_r_a=shunt_r_a,
                shunt_r_b=shunt_r_b,
                virtual_a=va,
                virtual_b=vb,
                shunt_y_a=shunt_y_a,
                shunt_y_b=shunt_y_b,
                at_a=at_a,
                at_b=at_b,
                edge_a=ea,
                edge_b=eb,
            )
        )
        if va:
            virtualized.add(wa)
        if vb:
            virtualized.add(wb)

    nts: list[NecNT] = []
    for card in nts_raw:
        wa, sa, at_a, ea = _attach(wires, card, 0, 1, nec5_dialect)
        wb, sb, at_b, eb = _attach(wires, card, 2, 3, nec5_dialect)
        ea, eb = hosted(wa, sa, ea), hosted(wb, sb, eb)
        # NEC's NT card is reciprocal: it gives Y11, Y12, Y22 (real+imag each)
        # and Y21 = Y12.
        y11 = complex(card.f(4), card.f(5))
        y12 = complex(card.f(6), card.f(7))
        y22 = complex(card.f(8), card.f(9))
        # An all-zero Y is NOT a no-op (issue #961). nec2c accepts the card
        # and OPEN-circuits both addressed segments — measured 0.68923 −
        # j4651.8 against a no-card control's 0.10161 + j514.86 on the same
        # deck. Skipping it here left the segments UNCUT, i.e. a shorted gap
        # where NEC has an open: a different antenna, silently. So it falls
        # through like any other real-Y card and lands on the resistive pi
        # below with every leg zero — which is exactly the open, because the
        # ports still get CUT and `network()` emits no branch for a None
        # leg. The cutting is the whole content of the card.
        if card.f(5) or card.f(7) or card.f(9):
            # Susceptance anywhere: no resistive pi. Keep the full complex Y —
            # network() emits it as a general Admittance branch (issue #416).
            nts.append(
                NecNT(
                    wire_a=wa,
                    seg_a=sa,
                    wire_b=wb,
                    seg_b=sb,
                    y=((y11, y12), (y12, y22)),
                    at_a=at_a,
                    at_b=at_b,
                    edge_a=ea,
                    edge_b=eb,
                )
            )
            continue
        # All-real Y → exact resistive pi: series −Y12 between the ports,
        # shunts Y11+Y12 / Y22+Y12 at each. Real Y is frequency-independent,
        # so this holds at every frequency.
        ys, ya, yb = -y12.real, y11.real + y12.real, y22.real + y12.real
        nts.append(
            NecNT(
                wire_a=wa,
                seg_a=sa,
                wire_b=wb,
                seg_b=sb,
                series_r=1.0 / ys if ys else None,
                shunt_r_a=1.0 / ya if ya else None,
                shunt_r_b=1.0 / yb if yb else None,
                at_a=at_a,
                at_b=at_b,
                edge_a=ea,
                edge_b=eb,
            )
        )

    # Where the networks connect, keyed the way a load addresses the same
    # place: a NEC-2 card names a segment centre, a NEC-5 card a knot
    # (AK#1579), and the two never collide because a deck is one or the other.
    def site(wi, seg, edge):
        return (wi, _knot_of(seg, edge)) if edge else (wi, "seg", seg)

    connected = {site(t.wire_a, t.seg_a, t.edge_a) for t in (*tls, *nts)}
    connected |= {site(t.wire_b, t.seg_b, t.edge_b) for t in (*tls, *nts)}
    # A demoted end still OCCUPIES the knot NEC-5 put it on, so a knot load
    # there is co-located with it exactly as it was before AK#1579 — without
    # this the load would be kept AND the demoted end marked on its segment,
    # which is the #824 collision on one piece.
    connected |= set(demoted)

    dropped_by_symmetry = 0

    def ld_range(tag, sf, st, card):
        """``_segment_range`` under NEC's symmetry-cell rule (#946). On a
        structure with live ``GX``/``GR`` symmetry a load lands on the cell
        and therefore on every copy, or lands outside the cell and is
        destroyed by the same pass — see ``_symmetry_cell_pairs``."""
        pairs = _segment_range(wires, tag, sf, st, card)
        if sym_cell is None:
            return pairs
        kept, dropped = _symmetry_cell_pairs(wires, pairs, sym_cell)
        # Parity with NEC, but not silently: NEC discards these without a
        # word, and a load the user wrote going missing is worth saying.
        # Counted rather than routed through ``skip`` on purpose — this is
        # not a card we failed to express, it is one we express exactly,
        # so it must not read as a partial network (the same reason remote
        # TL anchors get their own field instead of an ignored entry).
        nonlocal dropped_by_symmetry
        dropped_by_symmetry += dropped
        return kept

    loads: list[NecLoad] = []
    loaded: set[tuple[int, int]] = set()
    conductivity: float | None = None
    wire_conductivity: dict[int, float] = {}
    wire_insulation: dict[int, tuple[float, float]] = {}
    wire_conductor_radius: dict[int, float] = {}
    for card in lds_raw:
        ldtyp = card.i(0)
        tag = card.i(1)
        # 4nec2 percentage positions (AK#1496): each end of the range becomes
        # its nearest segment, and a load at ONE position keeps that exact
        # position on the network path.
        psf, pst = card.percent(2), card.percent(3)
        ld_at = None
        if psf is not None or pst is not None:
            sf, at_f = (
                _percent_position(wires, tag, psf, card)[1:]
                if psf is not None
                else (card.i(2), None)
            )
            st, at_t = (
                _percent_position(wires, tag, pst, card)[1:]
                if pst is not None
                else (card.i(3), None)
            )
            if st <= sf and (pst is None or at_t == at_f):
                st, ld_at = sf, at_f
        else:
            sf, st = card.i(2), card.i(3)
        if ldtyp in (0, 1, 4, 6):
            edge = 0
            if nec5_dialect and sf != 0 and psf is None and pst is None:
                # NEC-5 addresses a discrete load as it does EX: I3 is the
                # segment and I4 its END, so the card is ONE load at a knot,
                # never a segment range (AK#1483). I4 = 0 takes EX's sign rule.
                edge = st if st in (1, 2) else (1 if sf < 0 else 2)
                sf = st = abs(sf)
            pairs = ld_range(tag, sf, st, card)
            if len(pairs) > _LD_EXPAND_MAX:
                skip(
                    "LD",
                    f"range spans {len(pairs)} segments — the importer "
                    f"expands at most {_LD_EXPAND_MAX} into per-segment loads",
                )
                continue
            z = None
            if ldtyp == 4:
                # Type 4: a fixed series impedance R + jX (F1=R, F2=X). A pure
                # resistance stays a plain Load(r=R); a reactive one (X != 0,
                # issue #422) becomes a fixed complex-Z Load.
                r, x = card.f(4), card.f(5)
                if x != 0.0:
                    z, r, le, c = complex(r, x), None, None, None
                else:
                    r, le, c = (r or None), None, None
            elif ldtyp == 6:
                # 4nec2's LC-trap extension (issue #444): F1 is the coil's
                # UNLOADED Q (0 → 100, the documented default), F2/F3 = L/C.
                # 4nec2 converts it internally to a parallel RLC whose loss
                # resistance is evaluated at the initial FR card's frequency:
                # R_p = Q·ωL. Same conversion here, so all engines and the
                # nec2c reference (reference_deck does the text-level twin)
                # solve the physics 4nec2 would hand its own engine.
                le = card.f(5) or None
                c = card.f(6) or None
                if le is None:
                    skip("LD", "type 6 LC-trap without inductance")
                    continue
                q = card.f(4) or 100.0
                omega = 2.0 * math.pi * (fr_first_mhz or 299.8) * 1e6
                r = q * omega * le
            else:
                r = card.f(4) or None
                le = card.f(5) or None
                c = card.f(6) or None
            if r is None and le is None and c is None and z is None:
                continue  # zero-valued load — a no-op
            for pair in pairs:
                if pair[0] in virtual_segments:
                    # The idiom's own open-circuit pin (AK#1577), not a load
                    # on geometry: the segment it opens is becoming a circuit
                    # node. Kept as the node's residual admittance rather
                    # than reported as a card we could not express.
                    virtual_pins.append(
                        (*pair, z if z is not None else complex(r or 0.0, 0.0))
                    )
                    continue
                if site(*pair, edge) in connected:
                    skip(
                        "LD",
                        "load on a segment with a TL/NT connection — the "
                        "series-inside-the-segment composition is not modelled",
                    )
                    continue
                where = (*pair, edge)
                if where in loaded:
                    skip("LD", "a second load on one segment is not merged")
                    continue
                loaded.add(where)
                loads.append(
                    NecLoad(
                        pair[0],
                        pair[1],
                        r,
                        le,
                        c,
                        ldtyp in (1, 6),
                        z=z,
                        edge=edge,
                        at=ld_at if len(pairs) == 1 else None,
                    )
                )
        elif ldtyp == 2:
            # AK's own writers spell a jacket as the a'+L' pair (issue #1523,
            # engines._nec_wire.nec_wire_material): GW carries the fattened
            # equivalent radius a', and F2 here is the jacket's series
            # inductance L' [H/m] alone (F1 = F3 = 0). A real capture can
            # carry a nonzero F1 too (the wire's own per-length resistance,
            # e.g. EZNEC's own R' at its design frequency) — that is not
            # part of AK's jacket model (a lossless dielectric, momwire#131,
            # the same reason the IS card refuses a conductive sheath below)
            # and is dropped: the wire's own loss is LD 5 / WireSpec
            # conductivity, a separate card, not this one. A nonzero F3 (C')
            # is genuine distributed capacitance the pair never writes, so
            # it is the discriminator that keeps a true distributed-RLC LD 2
            # from being misread as a jacket.
            _r_per_len, l_ins, c_per_len = card.f(4), card.f(5), card.f(6)
            if c_per_len != 0.0 or l_ins <= 0.0:
                # A nonzero C' is genuine distributed capacitance the pair
                # never writes — real LD 3/general-RLC territory, not this
                # shape. l_ins <= 0 is the same tell: the pair always writes
                # a positive L' (a jacket only ever ADDS inductance), so
                # nothing here is worth the range/whole-wire work below.
                skip("LD", "type 2 distributed per-metre loading is not translated")
                continue
            pairs = ld_range(tag, sf, st, card)
            by_wire: dict[int, set[int]] = {}
            for wi, s in pairs:
                by_wire.setdefault(wi, set()).add(s)
            if not all(
                segs == set(range(1, wires[wi][1] + 1)) for wi, segs in by_wire.items()
            ):
                skip(
                    "LD",
                    "type 2 distributed per-metre loading is not translated "
                    "on a partial-wire segment range — per-wire specs cover "
                    "whole wires only",
                )
                continue
            # Momwire is a heavy, compiled optional dependency (accelerator
            # .so); nec_import must stay importable without it, so this is
            # pulled in only for a deck that actually carries a jacket pair
            # to invert.
            from .engines._nec_wire import (  # noqa: PLC0415
                jacket_from_equivalent_radius,
            )

            for wi in by_wire:
                inverted = jacket_from_equivalent_radius(wires[wi][4], l_ins)
                if inverted is None:
                    # Defensive only: l_ins > 0 already guarantees a smaller
                    # conductor radius than this wire's own GW radius (see
                    # the module docstring's identity) for any positive GW
                    # radius, so this fires only on a malformed GW radius —
                    # not a case this corpus produces, but not a card to
                    # silently misread either.
                    skip(
                        "LD",
                        "type 2 inductance does not invert to a smaller "
                        "conductor radius on this wire's GW radius — not "
                        "read as a jacket pair",
                    )
                    continue
                radius, insulation_radius, eps_r = inverted
                wire_conductor_radius[wi] = radius
                wire_insulation[wi] = (insulation_radius, eps_r)
            if _r_per_len != 0.0:
                # The jacket IS translated; R' is the part of the card that
                # is not, and this module's contract is that what cannot be
                # expressed is named rather than dropped in silence (module
                # docstring). EZNEC writes it for a lossy dielectric --
                # capture 0219 carries 1.655357 ohm/m from a Loss Tan of
                # 0.01 -- and AK's jacket is lossless (momwire#131), so the
                # number has nowhere to go. Reported per card, once.
                skip(
                    "LD",
                    "a jacket pair's per-metre resistance R' is dielectric "
                    "loss the jacket model does not carry and was dropped; "
                    "the jacket inductance on this card WAS applied",
                )
        elif ldtyp == 3:
            skip("LD", "type 3 distributed per-metre loading is not translated")
        elif ldtyp == 5:
            if tag == 0 and sf == 0:
                conductivity = card.f(4)
            else:
                # Ranged conductivity (issue #388): whole wires can carry
                # their own WireSpec conductivity, so a range that covers
                # each touched wire in full translates per wire (NEC's
                # last-card-wins per segment becomes last-wins per wire).
                pairs = ld_range(tag, sf, st, card)
                by_wire: dict[int, set[int]] = {}
                for wi, s in pairs:
                    by_wire.setdefault(wi, set()).add(s)
                if all(
                    segs == set(range(1, wires[wi][1] + 1))
                    for wi, segs in by_wire.items()
                ):
                    for wi in by_wire:
                        wire_conductivity[wi] = card.f(4)
                else:
                    skip(
                        "LD",
                        "type 5 conductivity on a partial-wire segment "
                        "range — per-wire specs cover whole wires only",
                    )
        elif ldtyp == 7:
            # 4nec2's insulated-wire extension (issue #447; NEC proper has
            # no such type — nec2c aborts with IMPROPER LOAD TYPE): F1 is
            # the jacket's relative permittivity, F2 its outer radius in
            # metres (either may be an SY expression, e.g. `w1/2`).
            # WireSpec carries exactly this dielectric-jacket model (the
            # lossy-wire arc), so a range that covers each touched wire in
            # full translates per wire like the ranged LD 5 conductivity —
            # last card wins per wire.
            eps_r, b = card.f(4), card.f(5)
            if b <= 0.0 or eps_r <= 1.0:
                continue  # no jacket, or a vacuum one — electrically a no-op
            pairs = ld_range(tag, sf, st, card)
            by_wire = {}
            for wi, s in pairs:
                by_wire.setdefault(wi, set()).add(s)
            if not all(
                segs == set(range(1, wires[wi][1] + 1)) for wi, segs in by_wire.items()
            ):
                skip(
                    "LD",
                    "type 7 insulation on a partial-wire segment "
                    "range — per-wire specs cover whole wires only",
                )
                continue
            for wi in by_wire:
                if b <= wires[wi][4]:
                    # A jacket that doesn't clear the conductor is a deck
                    # bug; the engines would reject the spec outright, so
                    # leave the wire bare and say why.
                    skip(
                        "LD",
                        "type 7 insulation whose outer radius does not "
                        "exceed the wire's conductor radius",
                    )
                    continue
                wire_insulation[wi] = (b, eps_r)
        else:
            skip("LD", f"type {ldtyp} is not recognised")

    for card in is_raw:
        # NEC-4's insulated-sheath card, in the spelling SimNEC's NECSource
        # emits — ``IS 0 tag first last  eps_r sigma b`` (issue #873; format
        # string pinned in the 2026-08-08 execute-grammar doc §16.6): F1 the
        # jacket's relative permittivity, F2 its conductivity, F3 its outer
        # radius in metres. Same per-wire WireSpec jacket as 4nec2's LD 7
        # (#447), same whole-wire constraint, last card wins per wire (and,
        # deck-order aside, an IS beats an LD 7 on the same wire because it
        # translates after the LD loop). momwire's jacket model is a lossless
        # dielectric (King quasi-static L', momwire#131), so a conductive
        # sheath stays unmodelled BY NAME rather than silently dropping F2.
        tag, sf, st = card.i(1), card.i(2), card.i(3)
        eps_r, sigma, b = card.f(4), card.f(5), card.f(6)
        if sigma != 0.0:
            skip(
                "IS",
                "a conductive sheath (F2 != 0) is not modelled — the "
                "jacket loading is a lossless dielectric",
            )
            continue
        if b <= 0.0 or eps_r <= 1.0:
            continue  # no jacket, or a vacuum one — electrically a no-op
        pairs = _segment_range(wires, tag, sf, st, card)
        by_wire = {}
        for wi, s in pairs:
            by_wire.setdefault(wi, set()).add(s)
        if not all(
            segs == set(range(1, wires[wi][1] + 1)) for wi, segs in by_wire.items()
        ):
            skip(
                "IS",
                "insulation on a partial-wire segment range — per-wire "
                "specs cover whole wires only",
            )
            continue
        for wi in by_wire:
            if b <= wires[wi][4]:
                skip(
                    "IS",
                    "insulation whose outer radius does not exceed the "
                    "wire's conductor radius",
                )
                continue
            wire_insulation[wi] = (b, eps_r)

    return (
        tuple(loads),
        tuple(tls),
        tuple(nts),
        conductivity,
        tuple(sorted(wire_conductivity.items())),
        tuple(sorted(wire_insulation.items())),
        tuple(sorted(wire_conductor_radius.items())),
        detail,
        skipped,
        frozenset(virtualized),
        frozenset(virtual_segments),
        tuple(virtual_pins),
        dropped_by_symmetry,
        tuple(demoted),
    )


# nec2c's `conect` contact tolerance, momwire's `_SMIN`: an end is AT a point
# when it lies within SMIN of its own segment length (antennaknobs#1460).
_NEC_SMIN = 1.0e-3


def ge_minus_one_contact_refusal(deck, ground):
    """The refusal message for a `GE -1` deck with a FREE wire end in the
    ground plane under an APPLIED ground, else None (antennaknobs#1460).

    `GE -1` declares the plane without the ground-contact current expansion,
    and every engine here serves the interpolated (`GE 1`) contact, so serving
    such an end would be a silently different answer: nec2c prints 39.8+23.3j
    and 57-4012j for the two readings of a grounded quarter-wave (momwire#489).
    A crossing junction is not a contact end (`NecDeck.free_plane_ends`). The
    message is momwire's deck reader's, word for word.

    `ground` is the engine's RESOLVED ground, and None or "free" is free space,
    with no image to disagree about. The engines call this at construction
    (`SimulationEngine._refuse_ge_minus_one_contact`), not the parser: the CLI's
    `--ground` and the app's ground switch apply a ground after parsing.
    """
    if deck is None or ground is None or ground == "free":
        return None
    if deck.ground_contact_interpolates:
        return None
    ends = deck.free_plane_ends()
    if not ends:
        return None
    i, name = ends[0]
    w = deck.wires[i]
    z = float((w.p1 if name == "p1" else w.p2)[2])
    return (
        f"GE -1 declares the ground plane without the "
        f"ground-contact current expansion, and wire "
        f"{w.tag}'s end stands in the plane "
        f"(z = {z:g}); this engine serves "
        f"the interpolated (GE 1) contact only — "
        f"write GE 1, or lift the wire clear of the "
        f"plane"
    )


def parse_nec(
    text: str,
    *,
    name: str = "NEC deck",
    network: bool = False,
    virtualize_anchors: bool = True,
) -> NecDeck:
    """Parse the text of a NEC2 card deck into a :class:`NecDeck`.

    ``network=True`` additionally translates the deck's expressible LD/TL/NT
    cards into ``deck.network()`` branches instead of recording them in
    ``ignored`` — see the module docstring for exactly what translates.

    ``virtualize_anchors`` (network mode only, default on) replaces a wire
    that is a circuit artifact rather than an antenna with ``PortVirtual``
    circuit nodes, and drops it from ``wire_tuples()``. Two idioms:

    - issue #427's remote TL anchor — a 1-segment wire ≫10 λ from everything
      else, referenced only to give a TL card a far-end segment. Its TL end
      becomes an ideal open, or a 1-port ``Admittance`` for a shorted-stub
      far-Y;
    - AK#1577's EZNEC virtual wire — the same parking trick with SEVERAL
      segments, each one a node the deck's ``NT``/``TL`` cards and its ``EX``
      address, pinned open with ``LD 4 … 1.E+10``. That is how EZNEC spells a
      source behind a transformer or a transmission line.

    Set it ``False`` to model such wires as real geometry.

    Raises ``ValueError`` (with ``name`` and the line number) on cards that
    are malformed or describe things antennaknobs cannot model — patches,
    tapered wires, plane-wave or current-source excitation.
    """
    wires: list[list] = []
    comments: list[str] = []
    ignored: set[str] = set()
    feeds_raw: list[tuple[int, int, complex, str]] = []
    lds_raw: list[_Card] = []
    is_raw: list[_Card] = []
    tls_raw: list[_Card] = []
    nts_raw: list[_Card] = []
    freq_mhz: tuple[float, float] | None = None
    fr_first_mhz: float | None = None
    ground = False
    ground_contact_interpolates = True
    ground_spec, ground_method = None, None
    ground_card = None
    nec5_dialect = False
    # A `CM NEC-5` card declares the deck NEC-5 (AK#1476). It is the only
    # way a deck with no NOFILE and no explicit EX end field can say so.
    nec5_declared = False
    extended_kernel = False
    syms: dict[str, float] = {}  # SY symbol table (#417)
    sym_cell: int | None = None  # GX/GR symmetry cell, in segments (#946)

    geometry = {
        "GW": _gw,
        "GC": _gc,
        "GA": _ga,
        "GH": _gh,
        "GM": _gm,
        "GX": _gx,
        "GR": _gr,
        "GS": _gs,
    }

    for line_no, raw in _logical_lines(text):
        stripped = raw.strip()
        if not stripped:
            continue
        where = f"{name}, line {line_no}"
        # 4nec2 comment convention (#418): a leading ' comments out the
        # whole line (including commented-out cards, `'GW ...`); anywhere
        # else ' starts an end-of-line comment. CM/CE lines are exempt —
        # their free text legitimately contains apostrophes.
        if stripped.startswith("'"):
            continue
        if stripped[:2].upper() == "CM":
            # NEC identifies cards by the first two columns, so a glued
            # "CMtext..." is a comment too (wild decks write "cmRP ..." to
            # comment out cards). Tolerated after CE as well (#418).
            text = stripped[2:].strip()
            comments.append(text)
            # Either the whole comment is the declaration — a comment that
            # merely mentions NEC-5 ("converted from a NEC-5 deck") is prose,
            # not a dialect (AK#1476) — or it is EZNEC's writer stamp naming
            # the format it wrote (AK#1579), which refuses by name for a
            # writer we have never captured.
            if text.upper() in ("NEC-5", "NEC5") or _eznec_declares_nec5(text, where):
                nec5_declared = True
            continue
        if stripped[:2].upper() == "CE":
            # Like CM, identified by its first two columns: "CEFOR THIS RUN"
            # is the end-of-comments card with its text glued on (#1272).
            continue
        stripped = stripped.split("'", 1)[0].rstrip()
        if not stripped:
            continue
        # Cards are free-format in practice: mnemonic, then numbers separated
        # by spaces and/or commas (parentheses and tab fields kept whole).
        tokens = _split_card_fields(stripped)
        # Fused mnemonics (#418): ARRL-era decks glue the mnemonic to the
        # first field ("GW1,8,...", "GE1", "EX5,1,..."). Split when two
        # alphabetic characters run straight into a number.
        if (
            len(tokens[0]) > 2
            and tokens[0][:2].isalpha()
            and tokens[0][2] in "0123456789.+-"
        ):
            tokens = [tokens[0][:2], tokens[0][2:], *tokens[1:]]
        mnemonic = tokens[0].upper()
        if len(mnemonic) != 2 or not mnemonic.isalpha():
            raise ValueError(
                f"{where}: expected a NEC card mnemonic, got {tokens[0]!r}"
            )

        if mnemonic == "EN":
            break
        if mnemonic == "NX":
            # Next-structure terminator (#1275): the first structure is
            # complete at this point (it follows an RP/WG/XQ), so import it
            # and stop, saying so in the skipped note rather than silently
            # dropping the second antenna.
            ignored.add(mnemonic)
            break
        if mnemonic == "SY":
            # 4nec2 symbolic variables (#417): bind name=expr (possibly
            # several per card, possibly with a trailing ' comment) into the
            # symbol table consulted by every later card field.
            _define_sy(stripped[2:], syms, where)
            continue
        if mnemonic == "SP":
            # Refused either way — antennaknobs models wires only — but by the
            # right name. A NEC-2-form patch in a deck read as NEC-5 is a
            # DIALECT error: stock NEC5CL reads those cards as spheres and
            # solves the remaining wires with no box at all (#1337, from the
            # manual's Example 4).
            raise ValueError(
                f"{where}: this deck uses {_SP_BY_FORM[classify_sp(tokens[1:])]}, "
                f"which antennaknobs cannot model"
            )
        if mnemonic in _UNSUPPORTED_CARDS:
            raise ValueError(
                f"{where}: this deck uses {_UNSUPPORTED_CARDS[mnemonic]}, "
                f"which antennaknobs cannot model"
            )
        if mnemonic == "GN":
            # NEC-5's GN names a ground file, and the magic name NOFILE says
            # there is none (NEC-5 Users Manual, GN card). antennaknobs' own
            # NEC-5 decks carry it (NEC5Engine, the corpus tool), so a deck
            # saved from a capture must open again (AC6LA, 2026-09-13). NEC-2
            # has no such field, so it also settles the dialect.
            if tokens[-1].upper() == "NOFILE":
                tokens = tokens[:-1]
                nec5_dialect = True
            # A trailing filename is NEC-4's tabulated Sommerfeld ground
            # (``GN 2 0 0 0 10. 0.01 SOMEX10.NEC``, #1274) -- the same shape
            # as NL's mesh file (#1067). Refuse it by name before the field
            # reaches the SY evaluator, which would call the "." a syntax
            # error in an expression the deck never wrote.
            fname = next((t for t in tokens[1:] if _FILENAME_RE.fullmatch(t)), None)
            if fname is not None:
                raise ValueError(
                    f"{where}: GN card names a Sommerfeld ground file ({fname}): "
                    "NEC-4's tabulated ground is not supported here; use the "
                    "GN card's own eps_r / sigma fields instead"
                )
            # The type field decides (#1066): GN -1 is NEC's "nullify the
            # ground parameters and set the free-space condition", the same
            # I1 = -1 convention LD and NT use below. Any other GN asks for
            # a ground plane. Nullification also drops the earlier GN from
            # the skipped note, since nothing of it survives to be skipped.
            card = _Card(mnemonic, tokens[1:], where, syms)
            if card.i(0) == -1:
                ground = False
                ground_spec, ground_method, ground_card = None, None, None
                ignored.discard(mnemonic)
            else:
                ground = True
                ignored.add(mnemonic)
                gtype = card.i(0)
                ground_card = f"GN {gtype}"
                if gtype == 1:
                    ground_spec, ground_method = "pec", None
                else:
                    # GN 0 (reflection coefficients) and GN 2 (Sommerfeld)
                    # both carry eps_r in F1 and sigma (S/m) in F2; the CLI
                    # spells the two models "finite-fast" and "finite".
                    kind = "finite" if gtype == 2 else "finite-fast"
                    ground_spec = (kind, card.f(4), card.f(5))
                    ground_method = "sommerfeld" if gtype == 2 else "fast"
            continue
        if network and mnemonic in ("LD", "TL", "NT", "IS"):
            # Collected raw and translated after the loop, once the wire
            # list is final (their tag/segment addressing resolves against
            # the transformed geometry, exactly like EX).
            card = _Card(mnemonic, tokens[1:], where, syms)
            if mnemonic == "LD":
                if card.i(0) == -1:
                    lds_raw.clear()  # NEC: nullify all previous loads
                else:
                    lds_raw.append(card)
            elif mnemonic == "IS":
                # NEC-4's insulated-sheath card (issue #873). Kept apart
                # from lds_raw so an LD -1 nullification cannot sweep away
                # insulation, which is a wire property here, not a load.
                is_raw.append(card)
            elif mnemonic == "TL":
                tls_raw.append(card)
            else:
                if card.i(0) == -1:
                    # NEC: an NT with I1 = -1 cancels all previous
                    # network AND transmission-line data.
                    nts_raw.clear()
                    tls_raw.clear()
                else:
                    nts_raw.append(card)
            continue
        if mnemonic == "EK":
            # Extended thin-wire kernel (#414): honored (via PyNEC), not
            # ignored. `EK -1` switches back to the standard kernel; any
            # other form turns it on. NEC scopes EK to subsequent geometry;
            # decks in the wild use it globally, so one deck-level flag.
            card = _Card(mnemonic, tokens[1:], where, syms)
            extended_kernel = card.i(0) != -1
            continue
        if mnemonic in _IGNORED_CARDS:
            ignored.add(mnemonic)
            continue

        card = _Card(mnemonic, tokens[1:], where, syms)

        if mnemonic in geometry:
            segs_before = sum(w[1] for w in wires)
            geometry[mnemonic](card, wires)
            # GX/GR leave the structure symmetric, which changes how NEC
            # resolves anything entering the matrix (#946).
            sym_cell = _symmetry_after(mnemonic, card, wires, segs_before, sym_cell)
        elif mnemonic == "GE":
            # A zero-radius GW is only legal as the announcement of a GC that
            # carries the taper (#1294). If the geometry closes with one still
            # parked, the deck is incomplete rather than tapered -- and the
            # message must not claim a taper we never saw.
            for w in wires:
                if w[4] <= 0.0:
                    raise card.error(
                        f"wire tag {w[0]} has zero radius and no GC "
                        "continuation followed it; a zero radius is only "
                        "meaningful as the announcement of a tapered wire"
                    )
            ground = ground or card.i(0) != 0
            # antennaknobs#1460: keep the SIGN. GE -1 is the plane WITHOUT the
            # ground-contact current expansion (momwire#489).
            ground_contact_interpolates = card.i(0) >= 0
        elif mnemonic == "FR":
            if freq_mhz is None:
                nfrq = max(card.i(1), 1)
                start, step = card.f(4), card.f(5)
                if card.i(0) == 0:  # linear sweep
                    end = start + (nfrq - 1) * step
                else:  # multiplicative sweep
                    end = start * step ** (nfrq - 1) if step > 0 else start
                freq_mhz = (min(start, end), max(start, end))
                # The raw F1 of the initial FR card, pre min/max
                # normalization — 4nec2 evaluates LD 6 trap loss at
                # exactly this frequency (issue #444).
                fr_first_mhz = start
        elif mnemonic == "EX":
            ex_type = card.i(0)
            if ex_type in (1, 2, 3):
                raise ValueError(
                    f"{where}: EX card asks for plane-wave excitation, which "
                    f"is a scattering run, not a driven antenna"
                )
            if ex_type == 4 and card.i(2) == 0:
                # NEC-2's EX 4 is an ELEMENTARY current source — a point
                # source in space (F1-F3 its position, F4-F5 its
                # orientation, F6 its moment) with I2/I3 blank. It drives
                # nothing on the structure, so it is not a feed. NEC-5
                # reuses the type number for a segment current source
                # (below) and always addresses a segment, so a blank I3 is
                # the NEC-2 meaning.
                raise card.error(
                    "EX type 4 with no segment addressed is NEC-2's "
                    "elementary current source, a point source in space "
                    "rather than a feed on the structure; antennaknobs can "
                    "only drive feeds on wires"
                )
            current = ex_type in (4, 6)
            if current:
                # A current source: 4nec2's type 6 (issue #442, the
                # phased-array idiom — element drive RATIOS in amps) or
                # NEC-5's type 4 (issue #1243, the source EZNEC's NEC-5
                # export writes, F1/F2 in amps). Only the network path can
                # express either: it becomes a DrivenCurrent through the
                # shared MNA reducer. NEC-2 proper has no segment current
                # source (nec2c misparses type 6 as a plane wave), so there
                # is no native path to fall back on.
                flavour = "4nec2's" if ex_type == 6 else "NEC-5's"
                if not network:
                    raise ValueError(
                        f"{where}: EX type {ex_type} is {flavour} current-source "
                        f"excitation, which needs the network path — "
                        f"parse with network=True"
                    )
            elif ex_type not in (0, 5):
                raise ValueError(
                    f"{where}: EX excitation type {ex_type} is not a voltage "
                    f"source; antennaknobs can only drive voltage feeds"
                )
            # NEC-5 edge-source dialect detection (#824, semantics pinned by
            # the NEC-5 Users Manual during #825): NEC-5 places a source at a
            # segment END — I4 = 1/2 picks the end, and with I4 = 0 the SIGN
            # of I3 does (negative → end 1). NEC-2's EX I4 is a print-control
            # field instead (legal values 0/1/10/11), so a negative segment
            # or I4 = 2 can only be the NEC-5 form. I4 = 1 is genuinely
            # ambiguous (legal NEC-2 print flag) and keeps its NEC-2 meaning.
            # Since #898 the port model HAS the wire-end port (PortAtVertex →
            # momwire's series node gap / NEC-5's native knot source), so the
            # form imports faithfully — through the network path, which is
            # where vertex ports live.
            #
            # EX 4 settles the dialect by itself (NEC-2's type 4 was refused
            # above), so it takes NEC-5's full end rule with no ambiguity
            # left: I4 = 1/2 names the end; I4 = 0 defers to the sign of I3,
            # end 1 when negative and end 2 when positive. There is no
            # center reading to fall back on — NEC-5 has no center source.
            edge = 0
            pct = card.percent(2)
            if pct is not None and (ex_type == 4 or nec5_declared or card.i(3) == 2):
                raise card.error(
                    "a percentage position is 4nec2's spelling and cannot also "
                    "name a NEC-5 segment end"
                )
            seg_field = 1 if pct is not None else card.i(2)
            if ex_type == 4:
                if card.i(3) in (1, 2):
                    edge = card.i(3)
                else:
                    edge = 1 if seg_field < 0 else 2
            elif nec5_declared or seg_field < 0 or card.i(3) == 2:
                if not network:
                    raise card.error(
                        "this is the NEC-5 edge-source form (a source at a "
                        "segment END — I4 selects the end, or a negative "
                        "segment number selects end 1): it imports as a "
                        "PortAtVertex, which needs the network path — parse "
                        "with network=True (issue #824)"
                    )
                if nec5_declared and card.i(3) in (1, 2):
                    # A declared NEC-5 deck (AK#1476) takes the manual's full
                    # rule, as EX 4 does: I4 = 1/2 names the end. I4 = 1 is
                    # ambiguous only while the dialect is unknown.
                    edge = card.i(3)
                else:
                    # I4 = 0 defers to the sign of I3 (negative = end 1). In a
                    # declared deck that is Dan's EX 0 1 10 0: end 2 of
                    # segment 10, the centre of a 20-segment wire.
                    edge = 1 if seg_field < 0 else 2
            if edge:
                nec5_dialect = True
            feeds_raw.append(
                (
                    card.i(1),
                    _Pct(pct) if pct is not None else abs(seg_field),
                    # NEC drives a voltage source written with zero volts at
                    # 1 V (measured 2026-09-14: nec2c 1.3.1 and SimNEC's ae6ty
                    # build print V = 1.0 for `EX 0 1 6 0 0. 0.` and for the
                    # five-field `EX 0 1 6 1 0`). Taken literally the port is
                    # undriven, which is momwire#962's z = [inf, 0].
                    (
                        1 + 0j
                        if not current and complex(card.f(4), card.f(5)) == 0
                        else complex(card.f(4), card.f(5))
                    ),
                    current,
                    edge,
                    where,
                )
            )
        else:
            raise ValueError(f"{where}: unrecognised NEC card {mnemonic!r}")

    if not wires:
        raise ValueError(f"{name}: deck defines no wires")

    _snap_nec_connections(wires)

    feeds = []
    for tag, seg, voltage, current, edge, where in feeds_raw:
        card = _Card("EX", [], where)
        if isinstance(seg, _Pct):
            idx, local, at = _percent_position(
                wires, tag, seg.value, card, legacy=not network
            )
        else:
            (idx, local), at = _locate_segment(wires, tag, seg, card), None
        feeds.append(NecFeed(idx, local, voltage, current, edge, at=at))

    loads: tuple[NecLoad, ...] = ()
    tls: tuple[NecTL, ...] = ()
    nts: tuple[NecNT, ...] = ()
    conductivity: float | None = None
    wire_conductivity: tuple[tuple[int, float], ...] = ()
    wire_insulation: tuple[tuple[int, tuple[float, float]], ...] = ()
    wire_conductor_radius: tuple[tuple[int, float], ...] = ()
    detail: list[tuple[str, str]] = []
    virtual_anchors: frozenset[int] = frozenset()
    virtual_segment_wires: frozenset[int] = frozenset()
    virtual_pins: tuple[tuple[int, int, complex], ...] = ()
    net_ends_demoted: tuple[tuple[int, int], ...] = ()
    # A declared deck is NEC-5 for every card, its loads included (AK#1476,
    # AK#1483).
    if nec5_declared:
        nec5_dialect = True
    symmetry_dropped = 0
    if network:
        (
            loads,
            tls,
            nts,
            conductivity,
            wire_conductivity,
            wire_insulation,
            wire_conductor_radius,
            detail,
            skipped,
            virtual_anchors,
            virtual_segment_wires,
            virtual_pins,
            symmetry_dropped,
            net_ends_demoted,
        ) = _translate_network_cards(
            wires,
            lds_raw,
            tls_raw,
            nts_raw,
            feeds,
            freq_mhz,
            virtualize_anchors,
            fr_first_mhz,
            is_raw,
            sym_cell,
            nec5_dialect,
        )
        ignored |= skipped

    # NEC-5 has no reflection-coefficient ground: its GN 0, like GN 2, is the
    # full Sommerfeld solution. Reading a NEC-5 deck's GN 0 the NEC-2 way
    # seeded the app with the approximation the deck never asked for (AC6LA,
    # 2026-09-13).
    if nec5_dialect and ground_method == "fast":
        ground_spec = ("finite", *ground_spec[1:])
        ground_method = "sommerfeld"

    return NecDeck(
        wires=tuple(
            NecWire(tag, ns, tuple(p1), tuple(p2), rad)
            for tag, ns, p1, p2, rad in wires
        ),
        feeds=tuple(feeds),
        freq_mhz=freq_mhz,
        ground=ground,
        ground_contact_interpolates=ground_contact_interpolates,
        # GE 1 with no GN card is NEC's perfect ground.
        ground_spec=("pec" if ground and ground_spec is None else ground_spec),
        ground_method=ground_method,
        ground_card=ground_card,
        nec5_dialect=nec5_dialect,
        comments=tuple(comments),
        ignored=tuple(sorted(ignored)),
        loads=loads,
        tls=tls,
        nts=nts,
        conductivity=conductivity,
        wire_conductivity=wire_conductivity,
        wire_insulation=wire_insulation,
        wire_conductor_radius=wire_conductor_radius,
        ignored_detail=tuple(detail),
        network_mode=network,
        extended_kernel=extended_kernel,
        virtual_anchors=virtual_anchors,
        virtual_segment_wires=virtual_segment_wires,
        virtual_pins=virtual_pins,
        symmetry_cell=sym_cell,
        symmetry_dropped_loads=symmetry_dropped,
        net_ends_demoted=net_ends_demoted,
    )
