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
(antennaknobs#1389).

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

from .engines.nec2 import refuse_nec2_geometry
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


def _ground_cards(ground):
    """Ground cards matching PyNECEngine._apply_ground_card, as a list of
    lines. Empty for free space (no GN card).

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
        return [f"GN {iperf} 0 0 0 {_num(eps_r)} {_num(sigma)}"]
    raise ValueError(f"unrecognised ground spec: {ground!r}")


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
    """
    # Refused HERE rather than inside PyNECEngine, for two reasons the QRZ
    # thread made plain (#1389). The sentence must say "a NEC-2 deck", not
    # "PyNEC": a user with NEC-5 in every slot has not selected PyNEC and does
    # not know this writer borrows its name. And it must point at the NEC-5
    # download, which serves exactly the designs this refuses.
    tups = list(builder.build_wires())
    for i, t in enumerate(tups):
        if isinstance(as_wire(t).n_seg, GradedSegments):
            raise NotImplementedError(
                f"a NEC-2 deck cannot express wire {i}'s graded mesh "
                "(GradedSegments): a card deck numbers wires by tag, and a "
                "graded expansion would shift every EX/LD/NT reference — "
                "download the NEC-5 deck instead, whose writer expands a graded "
                "wire into chained GW cards and renumbers the references "
                "(issue #1108)"
            )
    refuse_nec2_geometry(tups, ground, suggest_download=True)
    # AK#1597: ask WHY the network reduces, not merely whether. A network whose
    # only reducer reason is its current sources HAS a faithful single-deck
    # NEC-2 spelling — the gyrator idiom EZNEC itself writes — so it is built
    # with the writer-only flag that takes the native path and records those
    # sources for `_gyrator_cards`. Every other reason still refuses.
    probe = PyNECEngine(builder, ground=ground)
    reasons = probe._reducer_reasons()
    gyrators = reasons == frozenset({"current-source"})
    eng = (
        PyNECEngine(builder, ground=ground, _export_current_sources=True)
        if gyrators
        else probe
    )
    if eng._use_reducer:
        raise NotImplementedError(
            "a NEC-2 deck cannot express TL/virtual-driver networks (or "
            "distributed finite-gap ports, issue #477): the app solves those by "
            "a multiport-Y reduction over one deck per driven port, not by "
            "native NEC cards, so there is no faithful single-deck "
            "representation. The NEC-5 deck cannot express them either."
        )
    freq = builder.freq if freq is None else float(freq)

    title = title or f"{type(builder).__module__}.{type(builder).__qualname__}"
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
    gy_gw, gy_nt, gy_ex = _gyrator_cards(eng, eng.tups, freq)
    lines.extend(gy_gw)
    # The engine's own flag, not a constant (AK#1597). GE 1 is what tells NEC
    # a wire END standing at z=0 is CONNECTED to the ground plane, so the
    # touching segments' currents interpolate onto their images; with GE 0
    # that end is silently insulated and the deck models a different antenna.
    # This writer's whole premise is to be a text twin of what PyNECEngine
    # hands PyNEC, and PyNECEngine has always used `_ge_flag()` here.
    lines.append(f"GE {eng._ge_flag()}")

    # --- Load branches -> LD cards (type 0 series / 1 parallel RLC, type 4
    # fixed R + jX): the cards `PyNECEngine._emit_load_card` hands PyNEC ---
    if eng._network is not None:
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

    lines.extend(_ground_cards(eng.ground))

    # --- networks (NT), then excitations (EX), frequency (FR), pattern (RP) ---
    # Order matters and is not cosmetic: NEC requires the network cards of one
    # configuration to be contiguous, and it DROPS a voltage source read before
    # a network card, so every NT precedes every EX (AK#1597; the same hazard
    # `gyrator_reference` documents, where it silently lost a TL).
    lines.extend(gy_nt)
    for tag, seg, v in eng.excitation_pairs:
        v = complex(v)
        lines.append(f"EX 0 {tag} {seg} 0 {_num(v.real)} {_num(v.imag)}")
    lines.extend(gy_ex)

    lines.append(f"FR 0 {npoints} 0 0 {_num(freq)} {_num(df)}")
    if include_rp:
        # RP triggers the solve and prints input parameters + the pattern.
        # Hemisphere cut matching PyNECEngine._collect_pattern defaults.
        lines.append(f"RP {rp_mode(eng.ground)} 19 37 1000 0 0 10 10")
    else:
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
