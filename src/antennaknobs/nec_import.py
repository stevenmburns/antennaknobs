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
and output requests (FR/RP/NE/NH/XQ/...). Those cards are recorded in
``NecDeck.ignored`` (and FR in ``NecDeck.freq_mhz``) rather than translated,
so a caller can tell the user what the deck asked for that the app decides
differently.

Excitation: only voltage sources (EX type 0 and 5) can drive an antenna in
antennaknobs; plane-wave and current-source excitations raise. The engine
feeds a wire tuple at its middle segment, so ``NecDeck.wire_tuples`` splits a
wire whose EX segment is off-centre into colinear pieces that preserve the
deck's exact segment boundaries and put the feed on its own 1-segment wire.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .design_data import read_data

__all__ = ["NecDeck", "NecFeed", "NecWire", "parse_nec", "read_nec"]

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
    "EK": "extended thin-wire kernel",
    "CP": "coupling request",
    "PL": "plot request",
    "WG": "NGF write request",
    "ZO": "impedance normalisation (xnec2c)",
}

_UNSUPPORTED_CARDS = {
    "GC": "a tapered wire (GW with zero radius + GC continuation)",
    "SP": "a surface patch (SP)",
    "SM": "a multiple-patch surface (SM)",
    "GF": "a numerical Green's function file (GF)",
    "SY": "symbolic variables (SY, a 4nec2 extension)",
}


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
    """A voltage-source EX card resolved onto a wire: 1-based segment ``seg``
    of ``deck.wires[wire]`` is driven with ``voltage``."""

    wire: int
    seg: int
    voltage: complex


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

    def wire_tuples(self):
        """The deck as ``build_wires()`` tuples: ``(p1, p2, n_seg, ex)``.

        A wire whose fed segment is not its middle segment is split into
        colinear pieces on the deck's segment boundaries, so the feed lands on
        a 1-segment wire the engine drives at its centre — same geometry, same
        segmentation, same feed point as the original deck.
        """
        if not self.feeds:
            raise ValueError(
                "NEC deck has no voltage-source EX card — nothing drives the antenna"
            )
        by_wire: dict[int, list[NecFeed]] = {}
        for f in self.feeds:
            by_wire.setdefault(f.wire, []).append(f)

        tups = []
        for i, w in enumerate(self.wires):
            fs = sorted(by_wire.get(i, ()), key=lambda f: f.seg)
            if not fs:
                tups.append((w.p1, w.p2, w.n_seg, None))
                continue
            if len({f.seg for f in fs}) != len(fs):
                raise ValueError(
                    f"NEC deck drives segment {fs[0].seg} of wire {i + 1} "
                    f"with more than one EX card"
                )
            n = w.n_seg
            if len(fs) == 1 and n % 2 == 1 and fs[0].seg == (n + 1) // 2:
                # Fed at the wire's middle segment — the engine's native feed
                # position; keep the wire whole.
                tups.append((w.p1, w.p2, n, fs[0].voltage))
                continue

            def point(k, w=w, n=n):
                """Endpoint after ``k`` of the wire's ``n`` segments. The same
                expression for adjoining pieces yields bitwise-equal points,
                which is how wires are recognised as connected."""
                t = k / n
                return tuple(a + (b - a) * t for a, b in zip(w.p1, w.p2))

            prev = 0
            for f in fs:
                if f.seg - 1 > prev:
                    tups.append((point(prev), point(f.seg - 1), f.seg - 1 - prev, None))
                tups.append((point(f.seg - 1), point(f.seg), 1, f.voltage))
                prev = f.seg
            if prev < n:
                tups.append((point(prev), point(n), n - prev, None))
        return tups


def read_nec(builder, name: str) -> NecDeck:
    """``read_data`` followed by ``parse_nec`` — load a NEC card deck that
    ships next to ``builder``'s design, with the same folder confinement as
    ``read_json``."""
    return parse_nec(read_data(builder, name), name=name)


def _float(token: str, where: str) -> float:
    try:
        return float(token)
    except ValueError:
        # Old Fortran decks write D exponents ("1.0D+03").
        try:
            return float(token.upper().replace("D", "E"))
        except ValueError:
            raise ValueError(f"{where}: bad number {token!r}") from None


class _Card:
    """One card line: mnemonic + zero-padded numeric field access."""

    def __init__(self, mnemonic: str, tokens: list[str], where: str):
        self.mnemonic = mnemonic
        self.where = where
        self.vals = [_float(t, where) for t in tokens]

    def f(self, k: int) -> float:
        return self.vals[k] if k < len(self.vals) else 0.0

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
    if radius <= 0.0:
        raise card.error(
            "zero wire radius announces "
            + _UNSUPPORTED_CARDS["GC"]
            + ", which antennaknobs cannot model"
        )
    p1 = [card.f(2), card.f(3), card.f(4)]
    p2 = [card.f(5), card.f(6), card.f(7)]
    wires.append([tag, n_seg, p1, p2, radius])


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


def parse_nec(text: str, *, name: str = "NEC deck") -> NecDeck:
    """Parse the text of a NEC2 card deck into a :class:`NecDeck`.

    Raises ``ValueError`` (with ``name`` and the line number) on cards that
    are malformed or describe things antennaknobs cannot model — patches,
    tapered wires, plane-wave or current-source excitation.
    """
    wires: list[list] = []
    comments: list[str] = []
    ignored: set[str] = set()
    feeds_raw: list[tuple[int, int, complex, str]] = []
    freq_mhz: tuple[float, float] | None = None
    ground = False
    in_comments = True

    geometry = {
        "GW": _gw,
        "GA": _ga,
        "GH": _gh,
        "GM": _gm,
        "GX": _gx,
        "GR": _gr,
        "GS": _gs,
    }

    for line_no, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        where = f"{name}, line {line_no}"
        # Cards are free-format in practice: mnemonic, then numbers separated
        # by spaces and/or commas.
        tokens = stripped.replace(",", " ").split()
        mnemonic = tokens[0].upper()
        if len(mnemonic) != 2 or not mnemonic.isalpha():
            raise ValueError(
                f"{where}: expected a NEC card mnemonic, got {tokens[0]!r}"
            )

        if mnemonic == "CM":
            if not in_comments:
                raise ValueError(f"{where}: CM card after the CE end-of-comments card")
            comments.append(stripped[2:].strip())
            continue
        if mnemonic == "CE":
            in_comments = False
            continue
        in_comments = False

        if mnemonic == "EN":
            break
        if mnemonic in _UNSUPPORTED_CARDS:
            raise ValueError(
                f"{where}: this deck uses {_UNSUPPORTED_CARDS[mnemonic]}, "
                f"which antennaknobs cannot model"
            )
        if mnemonic == "GN":
            ground = True
            ignored.add(mnemonic)
            continue
        if mnemonic in _IGNORED_CARDS:
            ignored.add(mnemonic)
            continue

        card = _Card(mnemonic, tokens[1:], where)

        if mnemonic in geometry:
            geometry[mnemonic](card, wires)
        elif mnemonic == "GE":
            ground = ground or card.i(0) != 0
        elif mnemonic == "FR":
            if freq_mhz is None:
                nfrq = max(card.i(1), 1)
                start, step = card.f(4), card.f(5)
                if card.i(0) == 0:  # linear sweep
                    end = start + (nfrq - 1) * step
                else:  # multiplicative sweep
                    end = start * step ** (nfrq - 1) if step > 0 else start
                freq_mhz = (min(start, end), max(start, end))
        elif mnemonic == "EX":
            ex_type = card.i(0)
            if ex_type in (1, 2, 3):
                raise ValueError(
                    f"{where}: EX card asks for plane-wave excitation, which "
                    f"is a scattering run, not a driven antenna"
                )
            if ex_type not in (0, 5):
                raise ValueError(
                    f"{where}: EX excitation type {ex_type} is not a voltage "
                    f"source; antennaknobs can only drive voltage feeds"
                )
            feeds_raw.append(
                (card.i(1), card.i(2), complex(card.f(4), card.f(5)), where)
            )
        else:
            raise ValueError(f"{where}: unrecognised NEC card {mnemonic!r}")

    if not wires:
        raise ValueError(f"{name}: deck defines no wires")

    feeds = []
    for tag, seg, voltage, where in feeds_raw:
        card = _Card("EX", [], where)
        idx, local = _locate_segment(wires, tag, seg, card)
        feeds.append(NecFeed(idx, local, voltage))

    return NecDeck(
        wires=tuple(
            NecWire(tag, ns, tuple(p1), tuple(p2), rad)
            for tag, ns, p1, p2, rad in wires
        ),
        feeds=tuple(feeds),
        freq_mhz=freq_mhz,
        ground=ground,
        comments=tuple(comments),
        ignored=tuple(sorted(ignored)),
    )
