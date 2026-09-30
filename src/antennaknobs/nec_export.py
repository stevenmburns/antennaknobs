"""Export an antennaknobs builder to a NEC2 card deck (``.nec``).

NEC tools (xnec2c, 4nec2, EZNEC, nec2c, …) all speak the NEC ``.nec`` card
format, but antennaknobs has only ever *consumed* NEC cards (via PyNEC's
card API) — it could not emit them. This module closes that gap.

The deck is built by reusing :class:`PyNECEngine`'s already-resolved geometry:
the segment-parity-coerced wire tuples (``eng.tups``), the resolved feed
locations (``eng.excitation_pairs``), the ground spec, and any ``Load`` network
branches. That makes the emitted deck a faithful text twin of exactly what
PyNECEngine hands to PyNEC's in-memory card API — so a NEC engine reading the
deck (``nec2c``) reproduces PyNECEngine's impedance.

Not supported: TL/virtual-driver networks. PyNECEngine solves those by a
multiport-Y reduction (a circuit post-process on the field solution), not by
native NEC ``tl_card``s, so there is no faithful single-deck representation.
``export_nec`` raises ``NotImplementedError`` for them, in the DIALECT's name
rather than PyNEC's: a user reading a download error has not chosen an engine
(antennaknobs#1389). The refusal is of a single DECK, not of the design:
``NEC2Engine`` solves those networks the way PyNEC does, one structure deck per
port through :func:`export_nec_structure` and the reducer on the resulting Y
(AK#1678).

CURRENT SOURCES are the exception that used to be swept in with them
(AK#1597). ``DrivenCurrent`` forces the reducer because NEC's ``EX`` drives
VOLTS, so the refusal above caught it too — and that premise was false: a
NEC-2 deck expresses an ideal current source perfectly well, as a phantom wire
parked far from the antenna carrying an ``EX 0``, tied to the real feed
segment by an ``NT`` GYRATOR (Y11 = Y22 = 0, Y12 = Y21 = j). EZNEC writes
exactly that when asked to save a current-driven model as NEC-2, and 4nec2
builds it to emulate ``EX 6``; ``scripts/bench_nec_corpus.py``'s
``gyrator_reference`` (AK#475) is the same construction from the other side.
So a network whose ONLY reducer reason is its current sources is written, not
refused — see :func:`_gyrator_cards`. Dan AC6LA's ``Cardioidmodnec2.nec`` is
the reporting deck, and it is one EZNEC itself wrote.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

from .engine import expand_graded_wires
from .engines.nec2 import refuse_nec2_geometry
from .engines.nec42 import refuse_gn3_near_field, refuse_nec42_geometry
from .engines._nec_wire import JACKET_COMMENT_CARDS
from .engines.pynec import DEFAULT_GROUND, PyNECEngine
from .network import GradedSegments, Load, as_wire


def _gyrator_cards(eng, tups, freq_mhz):
    """``(gw, nt, ex)`` card lists spelling every forced current in ``eng``
    as NEC-2's gyrator idiom (AK#1597), or three empty lists.

    NEC-2 has no current-source ``EX``. The idiom, which EZNEC writes and
    4nec2 uses to emulate ``EX 6``, is per current source:

    1. a phantom 1-segment wire parked far from the structure, so its coupling
       to the antenna is negligible;
    2. an ``NT`` gyrator tying phantom -> real feed segment with Y11 = Y22 = 0
       and Y12 = Y21 = j, which forces a current into the real segment
       regardless of what that segment is loaded with;
    3. an ``EX 0`` voltage source on the phantom of V = j*I, since the
       delivered current at the far port is -j*V.

    The geometry follows ``scripts/bench_nec_corpus.py``'s ``gyrator_reference``
    (AK#475), which is verified against 4nec2/NEC-2D to <0.2 %: park the
    phantom 10x the structure extent plus 200 wavelengths away, one segment of
    lambda/50 with a lambda/10000 radius.

    Sign and scale are exactly what ``nec_import._collapse_gyrator_drives``
    reads back (AK#1595), which is what makes the round trip an identity
    rather than an approximation: it recovers ``I = -Y12*V = -(j)(j*I) = I``.
    """
    if not eng.current_sources:
        return [], [], []
    lam = 299.792458 / float(freq_mhz)
    coords = [c for t in tups for p_ in (t[0], t[1]) for c in p_]
    extent = max((abs(float(c)) for c in coords), default=0.0)
    zbase = 10.0 * extent + 200.0 * lam
    # ONE phantom wire carrying a node per source, which is the shape EZNEC
    # writes (its `! *Wire #N for virtual segments.` wire) and the shape our
    # own reader accepts. Two constraints fix the geometry, and both are the
    # importer's (`_virtual_segment_wires`), so getting them wrong costs the
    # round trip rather than the deck:
    #
    #  - MORE THAN ONE SEGMENT. The 1-segment remote wire belongs to issue
    #    #427's detector, which reads it as a bare TL termination and pins a
    #    driven one as electrically REAL — so a per-source 1-segment phantom
    #    (`gyrator_reference`'s shape, which only ever fed nec2c) reads back
    #    as geometry and reports the phantom port, i.e. 1/Z.
    #  - EXTENT UNDER 0.05 lambda end to end, so it stays electrically
    #    negligible. Sized at lambda/200 total however many sources there are,
    #    matching EZNEC's own 0.0052 lambda wire, rather than growing per
    #    source and walking into that gate.
    nseg = max(2, len(eng.current_sources))
    total = lam / 200.0
    prad = total / nseg / 200.0
    # Segment numbering is cumulative over the emitted GW cards, and the
    # phantom comes last so it cannot shift any real segment's number.
    seg_base, acc = [], 0
    for t in tups:
        seg_base.append(acc)
        acc += as_wire(t).n_seg
    ptag = len(tups) + 1
    gw = [
        f"GW {ptag} {nseg} 0. 0. {_num(zbase)} "
        f"{_num(total)} 0. {_num(zbase)} {_num(prad)}"
    ]
    nt, ex = [], []
    for j, (tag, seg, current) in enumerate(eng.current_sources, start=1):
        # Port 2 addressed as tag 0 + ABSOLUTE segment number, NEC's tag-0
        # convention — no within-tag rank to recompute.
        nt.append(f"NT {ptag} {j} 0 {seg_base[tag - 1] + seg} 0. 0. 0. 1. 0. 0.")
        v = 1j * complex(current)
        ex.append(f"EX 0 {ptag} {j} 0 {_num(v.real)} {_num(v.imag)}")
    return gw, nt, ex


def _ex6_cards(eng):
    """One NEC-4 ``EX 6`` card per forced current in ``eng`` (AK#1803).

    ``EX 6`` is NEC-4.2's segment current source: I2/I3 the tag and segment,
    F1/F2 the current in amps, and the source sits at the segment CENTRE, as
    ``EX 0`` does. Measured on the licensed binary: a dipole driven ``EX 6``
    prints the same impedance, to every printed digit, as its ``EX 0`` twin.
    `nec_import` reads the card back as a `DrivenCurrent` (issue #442)."""
    return [
        f"EX 6 {tag} {seg} 0 {_num(complex(i).real)} {_num(complex(i).imag)}"
        for tag, seg, i in eng.current_sources
    ]


class NearField(NamedTuple):
    """A rectangular near-field grid: NEC's ``NE 0`` (electric) or ``NH 0``
    (magnetic) card. ``counts`` points along x, y, z from ``start`` in steps of
    ``step`` (metres), NEC's own parametrisation, so the card is the grid."""

    counts: tuple[int, int, int]
    start: tuple[float, float, float]
    step: tuple[float, float, float]
    magnetic: bool = False

    def points(self) -> np.ndarray:
        """Every field point, ``(n, 3)``."""
        axes = [
            s0 + d * np.arange(int(n))
            for n, s0, d in zip(self.counts, self.start, self.step, strict=True)
        ]
        grid = np.meshgrid(*axes, indexing="ij")
        return np.stack([g.ravel() for g in grid], axis=1)


def near_field_card(nf: NearField) -> str:
    nx, ny, nz = (int(n) for n in nf.counts)
    vals = " ".join(_num(v) for v in (*nf.start, *nf.step))
    return f"{'NH' if nf.magnetic else 'NE'} 0 {nx} {ny} {nz} {vals}"


def _segment_centres(tups) -> np.ndarray:
    """Every segment centre of the uniform wires `tups`, ``(n, 3)``."""
    out = []
    for t in tups:
        w = as_wire(t)
        p0 = np.asarray(w.p0, dtype=float)
        p1 = np.asarray(w.p1, dtype=float)
        n = int(w.n_seg)
        f = (np.arange(n) + 0.5) / n
        out.append(p0 + f[:, None] * (p1 - p0))
    return np.concatenate(out) if out else np.zeros((0, 3))


# NEC-2 reads a card as an 80-column record (AK#1628). The Fortran builds read
# free-format numbers INSIDE those 80 columns and drop the rest without a word:
# AC6LA's nec2dxs11k.exe cut `GW 1 20 ... 5.682399E+00  5.000000E-04` at
# column 80, read Z2 as 5 and the radius as 0, and stopped on GEOMETRY DATA
# CARD ERROR. nec2c has no such limit, which is why every check here passed.
CARD_COLUMNS = 80


def _num(x, digits=7, bare=False):
    """A NEC free-format real, as short as it can be written: `digits`
    significant figures (7 is what the `.6E` spelling this replaced carried)
    and no padding, so a card fits NEC-2's 80-column record. 4nec2 and EZNEC
    write their decks the same way (`GW 1 12 0.0 0.0 0.0 0.0 0.0 23.5 .04`).
    ``bare`` drops a leading zero (`.0005`, `-.05`), as EZNEC does, which both
    the Fortran readers and nec2c take."""
    s = f"{float(x):.{digits}g}"
    if s == "-0":
        return "0"
    if bare and s.startswith(("0.", "-0.")):
        s = s.replace("0.", ".", 1)
    return s


def _gw(tag, n_seg, p0, p1, radius):
    """A GW card, inside `CARD_COLUMNS`. The only card with seven reals, so the
    only one that can overflow: three of the catalog's run to 81 columns at 7
    figures (the helices, the fan dipole). Such a card first drops its leading
    zeros, which costs nothing, then one significant figure at a time, never
    below 5, and refuses rather than let the reader truncate it."""
    values = (*p0, *p1, radius)
    for digits, bare in ((7, False), (7, True), (6, True), (5, True)):
        card = f"GW {tag} {n_seg} " + " ".join(_num(v, digits, bare) for v in values)
        if len(card) <= CARD_COLUMNS:
            return card
    raise ValueError(
        f"GW {tag} cannot be written inside NEC-2's {CARD_COLUMNS}-column card "
        f"even at 5 significant figures: {card!r}"
    )


# The deck dialects this writer spells (AK#1603). NEC-4.2 reads NEC-2's cards
# with three differences the writer owns: its Sommerfeld ground caches tables to
# files in the cwd unless the GN card ends NOFILE, it has a newer Sommerfeld
# (GN 3) beside GN 2, and its GE -1 admits buried wires.
DIALECTS = ("nec2", "nec42")


def _ground_cards(ground, dialect="nec2", sommerfeld=2):
    """Ground cards matching PyNECEngine._apply_ground_card, as a list of
    lines. Empty for free space (no GN card).

    NEC-4.2 (AK#1603): the Sommerfeld card takes `sommerfeld` as its type (2,
    or 3 for 4.2's newer evaluation) and always ends ``NOFILE``, so the binary
    writes no table file into whatever directory it runs in. The MININEC-type
    pair is refused there, measured: NEC-4.2 accepts the ``GD`` card and a
    cliff-mode ``RP 3``, and prints the PEC pattern to the digit — the medium
    is not read the way NEC-2 reads it (antennaknobs#1803).

    The MININEC-type ground (AK#1655) is two cards in NEC-2: ``GN 1`` for the
    currents, then a ``GD`` second medium whose circular cliff sits at radius 0
    and height 0, so every reflection point lies in it. That medium is read by
    a cliff-mode pattern request alone (`rp_mode`); under ``XQ`` or ``RP 0`` the
    pair is byte for byte a perfect ground, which is what the impedance is.
    """
    if ground is None or ground == "free":
        return []
    if ground == "pec":
        return ["GN 1 0 0 0 0 0"]
    if isinstance(ground, tuple) and len(ground) == 3 and ground[0] == "mininec":
        if dialect == "nec42":
            raise NotImplementedError(MININEC_NEC42_REFUSAL)
        _, eps_r, sigma = ground
        return [
            "GN 1 0 0 0 0 0",
            f"GD 0 0 0 0 {_num(eps_r)} {_num(sigma)} {_num(0.0)} {_num(0.0)}",
        ]
    if (
        isinstance(ground, tuple)
        and len(ground) == 3
        and ground[0]
        in (
            "finite",
            "finite-fast",
        )
    ):
        _, eps_r, sigma = ground
        # IPERF 2 = Sommerfeld-Norton, 0 = reflection-coefficient approximation.
        iperf = 2 if ground[0] == "finite" else 0
        if dialect == "nec42" and iperf == 2:
            return [f"GN {int(sommerfeld)} 0 0 0 {_num(eps_r)} {_num(sigma)} NOFILE"]
        return [f"GN {iperf} 0 0 0 {_num(eps_r)} {_num(sigma)}"]
    raise ValueError(f"unrecognised ground spec: {ground!r}")


MININEC_NEC42_REFUSAL = (
    "NEC-4.2 does not serve the MININEC-type ground as NEC-2's GN 1 + GD "
    "spelling: measured, it accepts the cards and prints the perfect-ground "
    "pattern to the digit, so the soil the pattern should reflect off is never "
    "read. Use the Sommerfeld or reflection-coefficient ground on this tab, or "
    "the NEC-2 / NEC-5 tab for the MININEC-type ground (antennaknobs#1803)"
)


class _NEC42DeckEngine(PyNECEngine):
    """The resolving `PyNECEngine` for a NEC-4.2 deck (AK#1603). NEVER SOLVED:
    it exists for its resolved wires, feeds and loads, like every engine this
    writer builds.

    Two differences. A graded wire (`GradedSegments`) is expanded into its
    panels, one uniform wire each, where PyNEC refuses it (AK#1803; see
    `engine.expand_graded_wires` for why no reference has to be renumbered).
    The other is about nec2++ rather than the deck. Building the
    PyNEC context with GE 1 over a design whose wires go below z=0 is refused
    by nec2++ ("SEGMENT EXTENDS BELOW GROUND") before the deck text is ever
    written — a rise from a buried hub touches z=0 and so asks for GE 1. The
    context here is built with GE 0 whenever a wire is buried, which nec2++
    accepts; the deck TEXT writes NEC-4.2's own flag (`_nec42_ge_flag`), -1.
    """

    def _ge_flag(self):
        if _has_buried_wire(self):
            return 0
        return super()._ge_flag()

    def _coerce_wire_tuples(self, tups):
        # A graded wire becomes its panels before any tag exists (AK#1803),
        # so every tag this engine resolves — feeds, loads, the structure
        # decks' ports — is already a panel-aware list position.
        out = super()._coerce_wire_tuples(tups)
        out, self._tup_authored = expand_graded_wires(
            out, getattr(self, "_tup_authored", None)
        )
        return out


def _has_buried_wire(eng) -> bool:
    return eng.ground not in (None, "free") and any(
        float(t[0][2]) < 0.0 or float(t[1][2]) < 0.0 for t in eng.tups
    )


def deck_engine_cls(dialect="nec2"):
    """The `PyNECEngine` class that resolves a deck of `dialect`."""
    return _NEC42DeckEngine if dialect == "nec42" else PyNECEngine


def _check_dialect(dialect, sommerfeld):
    if dialect not in DIALECTS:
        raise ValueError(f"unknown NEC deck dialect {dialect!r}: one of {DIALECTS}")
    if sommerfeld not in (2, 3):
        raise ValueError(f"sommerfeld must be 2 or 3, not {sommerfeld!r}")
    if sommerfeld == 3 and dialect != "nec42":
        raise ValueError("GN 3 is NEC-4.2's; a NEC-2 deck has only GN 2")


def rp_mode(ground) -> int:
    """The RP card's mode field (I1) for a pattern over `ground` in NEC-2.

    3, the circular cliff, over the MININEC-type ground: it is the only mode
    that reads the ``GD`` medium `_ground_cards` writes, and with the cliff at
    radius 0 it reads it everywhere (AK#1655; 4nec2 asks for its ``GN 3`` patterns the
    same way). 2, the linear cliff, would read it only on the x > 0 side.
    0, the normal mode, for every other ground.
    """
    if isinstance(ground, tuple) and ground and ground[0] == "mininec":
        return 3
    return 0


def export_nec(
    builder,
    *,
    ground=DEFAULT_GROUND,
    freq=None,
    df=0.0,
    npoints=1,
    include_rp=True,
    title=None,
    jacket_pair=True,
    wire_radius=None,
    dialect="nec2",
    sommerfeld=2,
    near_field=None,
):
    """Return a NEC2 card deck (str) for ``builder``.

    ground   : same spec as PyNECEngine — None/"free", "pec",
               ("finite", eps_r, sigma) (Sommerfeld-Norton), or
               ("finite-fast", eps_r, sigma) (reflection-coefficient).
    freq     : design frequency in MHz; defaults to ``builder.freq``.
    df       : FR-card frequency step in MHz (for a sweep).
    npoints  : FR-card frequency count.
    include_rp: append an RP card so the deck also computes a far-field pattern.
    title    : CM comment text; defaults to the builder's qualified name.
    jacket_pair: write an insulation jacket as momwire's coated-wire pair (the
               default, issue #1523). False writes the bare radius plus LD 2,
               for a consumer that drops the LD cards.
    wire_radius: the web slot's radius field (QRZ #170), PyNECEngine's
               ``wire_radius``: 0.0005 or None is "auto" (the design's own).
    dialect  : "nec2" (the default) or "nec42" (AK#1603): NEC-4.2's ground
               cards (``GN ... NOFILE``, ``GE -1`` when a wire is buried), and
               its geometry rules in place of NEC-2's, so a buried design is
               written rather than refused.
    sommerfeld: the NEC-4.2 Sommerfeld card's type for a "finite" ground, 2 or
               3 (4.2's newer evaluation). NEC-2 has only 2.
    near_field: a `NearField` grid, written as one ``NE`` (or ``NH``) card
               after ``FR``. Under ``GN 3`` a grid with a point near the
               zenith of any segment is refused (`refuse_gn3_near_field`).

    The NEC-4.2 dialect is this writer's, not a patch over the NEC-2 deck
    (AK#1803): besides the ground cards above it expands a graded wire into
    chained GW cards (`engine.expand_graded_wires`), drives a current source
    with NEC-4's native ``EX 6`` instead of NEC-2's gyrator, and serves buried
    wires under ``GE -1`` (`refuse_nec42_geometry` holds what it refuses).
    Feeds stay on segment centres, the NEC-2/4 convention.
    """
    _check_dialect(dialect, sommerfeld)
    # Refused HERE rather than inside PyNECEngine, for two reasons the QRZ
    # thread made plain (#1389). The sentence must say "a NEC-2 deck", not
    # "PyNEC": a user with NEC-5 in every slot has not selected PyNEC and does
    # not know this writer borrows its name. And it must point at the NEC-5
    # download, which serves exactly the designs this refuses.
    tups = list(builder.build_wires())
    for i, t in enumerate(tups if dialect == "nec2" else ()):
        if isinstance(as_wire(t).n_seg, GradedSegments):
            raise NotImplementedError(
                f"a NEC-2 deck cannot express wire {i}'s graded mesh "
                "(GradedSegments): a card deck numbers wires by tag, and a "
                "graded expansion would shift every EX/LD/NT reference — "
                "download the NEC-5 deck instead, whose writer expands a graded "
                "wire into chained GW cards and renumbers the references "
                "(issue #1108), or the NEC-4 deck, which does the same (AK#1803)"
            )
    if dialect == "nec42":
        # Against the panels, which are what the deck carries: a graded wire
        # whose panel boundary sits on z=0 does not cross the plane mid-span.
        refuse_nec42_geometry(expand_graded_wires(tups)[0], ground)
    else:
        refuse_nec2_geometry(tups, ground, suggest_download=True)
    # AK#1677 needs no separate handling here: `refuse_nec2_geometry` above
    # already refuses ANY wire dipping below z=0 under a real ground, jacketed
    # or bare, before a deck is ever assembled — so a NEC-2 download of a
    # jacketed buried wire cannot exist to need the momwire#1154 advisory.
    # Only `engines.nec5.NEC5Engine.deck` (buried, served natively) needs it;
    # see `engines._nec_wire.BURIED_JACKET_ADVISORY_CARDS`.
    # AK#1597: ask WHY the network reduces, not merely whether. A network whose
    # only reducer reason is its current sources HAS a faithful single-deck
    # NEC-2 spelling — the gyrator idiom EZNEC itself writes — so it is built
    # with the writer-only flag that takes the native path and records those
    # sources for `_gyrator_cards`. Every other reason still refuses.
    engine_cls = deck_engine_cls(dialect)
    probe = engine_cls(builder, ground=ground, wire_radius=wire_radius)
    reasons = probe._reducer_reasons()
    gyrators = reasons == frozenset({"current-source"})
    eng = (
        engine_cls(
            builder,
            ground=ground,
            _export_current_sources=True,
            wire_radius=wire_radius,
        )
        if gyrators
        else probe
    )
    if eng._use_reducer:
        # Worded for BOTH readers (AK#1678). This refuses a single DECK — the
        # download — and never a solve: the NEC-2 and NEC-5 engines (and PyNEC,
        # which the sentence does not name, #1389) serve these designs by
        # running one deck per port and reducing the network on the result. It
        # used to end "The NEC-5 deck cannot express them either", which a user
        # whose NEC-5 tab had just solved the same design read as nonsense.
        raise NotImplementedError(
            f"a single {'NEC-4' if dialect == 'nec42' else 'NEC-2'} deck cannot "
            "express TL/virtual-driver networks (or "
            "distributed finite-gap ports, issue #477): there are no native NEC "
            "cards for them, so there is no faithful single-deck representation "
            "to download, and a single NEC-5 deck has none either. The NEC-2 and "
            "NEC-5 engines still solve such a design, by a multiport-Y reduction "
            "over one deck per driven port."
        )
    freq = builder.freq if freq is None else float(freq)
    title = title or f"{type(builder).__module__}.{type(builder).__qualname__}"
    if near_field is not None and dialect == "nec42":
        refuse_gn3_near_field(
            eng.ground, sommerfeld, near_field.points(), _segment_centres(eng.tups)
        )
    return _deck_text(
        eng,
        freq=freq,
        df=df,
        npoints=npoints,
        include_rp=include_rp,
        title=title,
        jacket_pair=jacket_pair,
        dialect=dialect,
        sommerfeld=sommerfeld,
        near_field=near_field,
    )


def export_nec_structure(
    eng, *, freq, sources, df=0.0, npoints=1, dialect="nec2", sommerfeld=2
):
    """The deck of `eng`'s bare structure driven by `sources`, for the
    multiport-Y route (AK#1678). Never a download: see `export_nec`'s refusal.

    `eng` is a `PyNECEngine` on that route, which resolves every port and never
    solves here. `sources` is ``[(tag, segment, volts), ...]``, one ``EX 0``
    each at a segment CENTRE, NEC-2's source convention. The network itself
    writes NO card: its branches (plain loads included) are the reducer's to
    stamp, exactly as PyNEC's real-geometry context carries none. What the
    deck does carry is everything that belongs to the structure — the wires,
    the ground, the wire material — written by the same lines `export_nec`
    uses, so the two cannot disagree about the antenna. `dialect` and
    `sommerfeld` as `export_nec`'s; the engine has already refused whatever
    its dialect cannot carry.
    """
    _check_dialect(dialect, sommerfeld)
    builder = eng.builder
    return _deck_text(
        eng,
        freq=float(freq),
        df=df,
        npoints=npoints,
        include_rp=False,
        title=f"{type(builder).__module__}.{type(builder).__qualname__}",
        jacket_pair=True,
        excitations=[(int(t), int(g), complex(v)) for t, g, v in sources],
        dialect=dialect,
        sommerfeld=sommerfeld,
    )


def _nec42_ge_flag(eng):
    """NEC-4.2's GE flag (AK#1603): -1 when a real ground is present and any
    wire goes below z=0 — the flag that admits buried wires, and leaves the
    current expansion alone at z=0 — else NEC-2's `_ge_flag`."""
    if _has_buried_wire(eng):
        return -1
    return eng._ge_flag()


def _deck_text(
    eng,
    *,
    freq,
    df,
    npoints,
    include_rp,
    title,
    jacket_pair,
    excitations=None,
    dialect="nec2",
    sommerfeld=2,
    near_field=None,
):
    """The card text for a resolved `PyNECEngine`. With `excitations` None,
    the engine's own feeds, loads and gyrators (`export_nec`); otherwise the
    bare structure driven by those ``(tag, seg, volts)`` sources
    (`export_nec_structure`)."""
    structure_only = excitations is not None
    # Read only by the card text below; the PyNEC context the engine built is
    # never solved here.
    eng._jacket_pair = jacket_pair
    lines = [f"CM {title}", "CM exported by antennaknobs.nec_export"]
    if any(eng._gw_radius_for(t) != eng._radius_for(t) for t in eng.tups):
        lines.extend(JACKET_COMMENT_CARDS)
    lines.append("CE")

    # --- geometry: one GW per resolved wire tuple, then GE. GW carries a
    # radius natively, so a per-wire spec (issue #388) exports faithfully,
    # and a jacketed wire's is its equivalent radius (issue #1523) ---
    for tag, t in enumerate(eng.tups, start=1):
        lines.append(_gw(tag, t[2], t[0], t[1], eng._gw_radius_for(t)))
    # AK#1597: the phantom wires carrying forced currents. LAST, so no real
    # wire's absolute segment number moves and the NT addresses below stay put.
    if structure_only:
        gy_gw, gy_nt, gy_ex = [], [], []
    elif dialect == "nec42":
        # NEC-4.2 has the current source NEC-2 lacks (AK#1803): one native
        # `EX 6` per forced current, on the real feed segment, and no phantom.
        gy_gw, gy_nt, gy_ex = [], [], _ex6_cards(eng)
    else:
        gy_gw, gy_nt, gy_ex = _gyrator_cards(eng, eng.tups, freq)
    lines.extend(gy_gw)
    # The engine's own flag, not a constant (AK#1597). GE 1 is what tells NEC
    # a wire END standing at z=0 is CONNECTED to the ground plane, so the
    # touching segments' currents interpolate onto their images; with GE 0
    # that end is silently insulated and the deck models a different antenna.
    # This writer's whole premise is to be a text twin of what PyNECEngine
    # hands PyNEC, and PyNECEngine has always used `_ge_flag()` here.
    ge = _nec42_ge_flag(eng) if dialect == "nec42" else eng._ge_flag()
    lines.append(f"GE {ge}")

    # --- Load branches -> LD cards (type 0 series / 1 parallel RLC, type 4
    # fixed R + jX): the cards `PyNECEngine._emit_load_card` hands PyNEC ---
    if eng._network is not None and not structure_only:
        for br in eng._network.branches:
            if not isinstance(br, Load):
                continue
            tag, seg = eng._network_port_loc[br.port]
            if br.z is not None:
                # antennaknobs#1485: a fixed complex impedance, which is what an
                # LD 4 reactive load imports as (#422), has no R/L/C legs, so it
                # used to reach the all-zero `continue` below and vanish. The
                # NEC-2 tab then solved the design without its load. Type 4:
                # F1 = R, F2 = X (ohms); z == 0 is no load, as in PyNECEngine.
                z = complex(br.z)
                if z != 0:
                    lines.append(
                        f"LD 4 {tag} {seg} {seg} "
                        f"{_num(z.real)} {_num(z.imag)} {_num(0.0)}"
                    )
                continue
            r = float(br.r) if br.r is not None else 0.0
            l = float(br.l) if br.l is not None else 0.0
            c = float(br.c) if br.c is not None else 0.0
            if r == 0.0 and l == 0.0 and c == 0.0:
                continue
            ldtyp = 1 if br.parallel else 0
            lines.append(f"LD {ldtyp} {tag} {seg} {seg} {_num(r)} {_num(l)} {_num(c)}")

    # Wire material (issue #316): the same LD cards the engine emits —
    # conductor loss as LD 5 (spec conductivity from the design, else the
    # module-level oracle constant; normally None → card omitted, PEC) and
    # the insulation jacket's series inductance as LD 2 (H/m), with LD 5
    # rescaled on a jacketed wire for its equivalent GW radius (issue #1523).
    # Issue #1427: the same per-wire rule as `PyNECEngine._emit_wire_material`
    # — when any wire carries its own spec (a deck loaded from a file does),
    # every wire gets per-tag cards from its effective spec; otherwise one
    # global card per effect, byte-identical to before. The two paths are
    # exclusive.
    if any(as_wire(t).spec is not None for t in eng.tups):
        for tag, t in enumerate(eng.tups, start=1):
            mat = eng._material_for(t)
            if mat.conductivity is not None:
                lines.append(f"LD 5 {tag} 0 0 {_num(mat.conductivity)} 0. 0.")
            if mat.inductance is not None:
                lines.append(f"LD 2 {tag} 0 0 0. {_num(mat.inductance)} 0.")
    else:
        mat = eng._design_material()
        if mat.conductivity is not None:
            lines.append(f"LD 5 0 0 0 {_num(mat.conductivity)} 0. 0.")
        if mat.inductance is not None:
            lines.append(f"LD 2 0 0 0 0. {_num(mat.inductance)} 0.")

    lines.extend(_ground_cards(eng.ground, dialect, sommerfeld))

    # --- networks (NT), then excitations (EX), frequency (FR), pattern (RP) ---
    # Order matters and is not cosmetic: NEC requires the network cards of one
    # configuration to be contiguous, and it DROPS a voltage source read before
    # a network card, so every NT precedes every EX (AK#1597; the same hazard
    # `gyrator_reference` documents, where it silently lost a TL).
    lines.extend(gy_nt)
    for tag, seg, v in excitations if structure_only else eng.excitation_pairs:
        v = complex(v)
        lines.append(f"EX 0 {tag} {seg} 0 {_num(v.real)} {_num(v.imag)}")
    lines.extend(gy_ex)

    lines.append(f"FR 0 {npoints} 0 0 {_num(freq)} {_num(df)}")
    if include_rp:
        # RP triggers the solve and prints input parameters + the pattern.
        # Hemisphere cut matching PyNECEngine._collect_pattern defaults.
        lines.append(f"RP {rp_mode(eng.ground)} 19 37 1000 0 0 10 10")
    if near_field is not None:
        # NE / NH execute the solve themselves, so no XQ is needed beside one.
        lines.append(near_field_card(near_field))
    elif not include_rp:
        # No pattern requested: an explicit XQ still triggers the solve so the
        # deck reports ANTENNA INPUT PARAMETERS (impedance). Without an XQ/RP
        # card NEC reads the geometry but never executes.
        lines.append("XQ 0")
    lines.append("EN")
    # The tripwire for AK#1628: a card past column 80 is read silently
    # truncated by NEC-2's Fortran builds, so it is refused here instead.
    # Comments are exempt; a truncated CM line changes nothing.
    long = [ln for ln in lines if not ln.startswith("CM") and len(ln) > CARD_COLUMNS]
    if long:
        raise ValueError(
            f"NEC-2 card past column {CARD_COLUMNS}, which NEC-2 would read "
            f"truncated: {long[0]!r}"
        )
    return "\n".join(lines) + "\n"
