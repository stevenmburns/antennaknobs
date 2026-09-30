"""nec4_corpus.py -- a NEC-4.2 regression corpus from the public NEC-2 decks.

The NEC-4.2 twin of `scripts/nec5_corpus/nec5_corpus.py`, and a thin one: it
READS decks with that tool's reader (4nec2 `SY` symbols, comma / tab
separators, fused mnemonics, `'` and `!` comments, `#nn` AWG gauges, Fortran D
exponents, the "not valid NEC input" and duplicate-wire checks), imported from
the file beside it, and writes them for NEC-4.2 instead of NEC-5:

    python nec4_corpus.py translate --src raw --out corpus/public
    python ../nec4_corpus/export_catalog_nec4.py --out corpus/catalog --gn3-twins
    python nec4_corpus.py manifest  --root corpus
    python nec4_corpus.py check     --exe nec42cl --src corpus --jobs 4
    python nec4_corpus.py twins     corpus/check-report.jsonl

(`fetch` is the NEC-5 tool's: `python ../nec5_corpus/nec5_corpus.py fetch`.)

What `translate` does NOT do is the NEC-5 half: NEC-4.2 reads NEC-2's cards
with sources, loads and ports at segment CENTRES, so no mesh is touched, no
source moves, no EX / LD / TL field is renumbered, and an untagged wire keeps
tag 0. Meshes are as authored. The NEC-4.2 rules, each measured on a licensed
NEC-4.2 binary (black box, probe decks) rather than taken from anything else:

  * every GN 2 (Sommerfeld) card ends ``NOFILE`` -- without it the binary
    writes its Sommerfeld tables (``SOMD.NEC``) into the working directory;
  * every deck that ends up on GN 2 is written TWICE, ``<name>.gn2.nec`` and a
    ``<name>.gn3.nec`` twin identical but for ``GN 3`` (NEC-4.2's newer
    Sommerfeld evaluation) -- the pair a GN 2 / GN 3 fix is judged on;
  * wires below ground over GN 2 need ``GE -1``: ``GE 1`` stops with
    "SEGMENT ... EXTENDS BELOW GROUND"; a deck that spells it 0 or 1 is
    rewritten to -1 and the change recorded (``GE 0`` and ``GE -1`` print the
    same impedance there; ``GE 1`` would have connected a wire ending on the
    plane to its image, so a deck whose rewrite would cut such a wire loose is
    skipped instead);
  * buried wires under GN 0 / GN 1 are skipped (NEC-4.2 stops, "MUST USE
    SOMMERFELD FOR INTERACTION ACROSS THE INTERFACE"), and so is a wire whose
    segment straddles z=0 (solved wrong without a warning);
  * 4nec2's ``GN 3`` is its MININEC-type ground, NOT NEC-4.2's GN 3 -- such a
    deck is skipped, since passing it through would silently swap the ground;
  * a radial screen on GN 2 is skipped (NEC-4.2: "RADIAL WIRE G. S.
    APPROXIMATION MAY NOT BE USED WITH SOMMERFELD GROUND OPTION");
  * 4nec2's ``EX 6`` (its current source, which 4nec2 runs as a NEC-2 gyrator)
    is written as NEC-4.2's native ``EX 6 tag seg 0 Ire Iim`` segment current
    source -- measured to be the same model as the gyrator -- and the deck is
    skipped where the card is ambiguous (`_check_ex6`);
  * 4nec2's LD 7 insulated wire becomes NEC-4's IS sheath and its LD 6 LC trap
    an LD 1 parallel RLC (`_ld_4nec2`); NEC-4.2 stops on both as written;
  * nec2++'s MP and NEC-2's GF (a Green's function file this corpus does not
    have) are skipped: NEC-4.2 stops on each;
  * NEC-2's GH has other fields than NEC-4.2's (`_nec2_gh`): a right-handed
    constant-radius helix is respelled in NEC-4's fields, any other helix is
    written as its GW pieces on NEC-2's geometry, and 4nec2's flat one-turn
    loop (NEC-4.2 stops, "DATAGN: SEGMENT DATA ERROR") likewise -- same
    segments, same tag;
  * a deck with no execution request gets ``XQ 0`` (NEC-4.2 computes nothing);
  * EK and KH are kept, noted: NEC-4.2 prints "THE EK AND KH COMMANDS HAVE NO
    EFFECT IN NEC-4".

Every change is a ``CM nec4_corpus:`` line in the deck and a note in the
manifest. `check` runs each deck as ``<exe> model.nec model.out`` in a fresh
temp dir and keeps no printout unless asked (`--keep-dir`, local only).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERSION = "1.0"


def _load_nec5():
    """The NEC-5 tool, by path: its reader IS this tool's reader.

    Imported rather than copied so the two corpora read a deck identically, and
    by file path rather than as a package so nothing is installed and the NEC-5
    tool (a signed, released, standard-library-only file) is not edited."""
    path = Path(__file__).resolve().parents[1] / "nec5_corpus" / "nec5_corpus.py"
    spec = importlib.util.spec_from_file_location("nec5_corpus_for_nec4", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


n5 = _load_nec5()
Card = n5.Card
DeckError, Refused, InvalidNEC = n5.DeckError, n5.Refused, n5.InvalidNEC
_log = n5._log


# ---------------------------------------------------------------------------
# where the conductors are (for the ground rules)
# ---------------------------------------------------------------------------
def _rot(p, ax, ay, az):
    """NEC's GM rotation: about X, then Y, then Z, angles in degrees."""
    x, y, z = p
    for axis, deg in (("x", ax), ("y", ay), ("z", az)):
        if not deg:
            continue
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        if axis == "x":
            y, z = c * y - s * z, s * y + c * z
        elif axis == "y":
            x, z = c * x + s * z, -s * x + c * z
        else:
            x, y = c * x - s * y, s * x + c * y
    return (x, y, z)


def _wire_points(c: Card) -> list:
    """The segment end points of one geometry card, before any transform.
    CW is taken as its chord and GH (in NEC-4's fields) as a linear-radius
    helix: both are only ever asked which side of z=0 they are on."""
    n = max(c.int(1), 1)
    if c.mn in ("GW", "CW"):
        a = (c.num(2), c.num(3), c.num(4))
        b = (c.num(5), c.num(6), c.num(7))
        return [
            tuple(a[k] + (b[k] - a[k]) * i / n for k in range(3)) for i in range(n + 1)
        ]
    if c.mn == "GA":
        r, a1, a2 = c.num(2), c.num(3), c.num(4)
        return [
            (
                r * math.cos(math.radians(a1 + (a2 - a1) * i / n)),
                0.0,
                r * math.sin(math.radians(a1 + (a2 - a1) * i / n)),
            )
            for i in range(n + 1)
        ]
    if c.mn == "GH":
        # NEC-4's layout: `_nec2_gh` has rewritten every NEC-2 helix by now.
        turns, hl = c.num(2), abs(c.num(3))
        r1, r2 = c.num(4), c.num(5)
        pts = []
        for i in range(n + 1):
            t = i / n
            ang = 2.0 * math.pi * turns * t
            r = r1 + (r2 - r1) * t
            pts.append((r * math.cos(ang), r * math.sin(ang), hl * t))
        return pts
    return []


def conductors(cards: list) -> list:
    """``[(tag, [points])]`` for every wire after GM / GR / GX / GS, in the
    geometry section. Only positions are tracked -- enough to say which wires
    are below, on or across the ground plane."""
    wires = []
    for c in cards:
        mn = c.mn
        if mn == "GE":
            break
        try:
            if mn in ("GW", "CW", "GA", "GH"):
                wires.append((c.int(0), _wire_points(c)))
            elif mn == "GM":
                itsi, nrpt = c.int(0), c.int(1)
                rx, ry, rz = c.num(2), c.num(3), c.num(4)
                dx, dy, dz = c.num(5), c.num(6), c.num(7)
                a, b = n5.Geometry._its_range(c.f[8]) if len(c.f) > 8 else (0, 0)

                def pick(tag, a=a, b=b):
                    return a <= 0 or (tag >= a and (b <= 0 or tag <= b))

                def move(pts, rx=rx, ry=ry, rz=rz, dx=dx, dy=dy, dz=dz):
                    out = []
                    for p in pts:
                        x, y, z = _rot(p, rx, ry, rz)
                        out.append((x + dx, y + dy, z + dz))
                    return out

                if nrpt == 0:
                    wires = [
                        (t + (itsi if t else 0), move(p)) if pick(t) else (t, p)
                        for t, p in wires
                    ]
                else:
                    base = [(t, p) for t, p in wires if pick(t)]
                    for i in range(1, nrpt + 1):
                        cur = []
                        for t, p in base:
                            q = p
                            for _ in range(i):
                                q = move(q)
                            cur.append((t + itsi * i if t else 0, q))
                        wires.extend(cur)
            elif mn == "GR":
                its, nr = c.int(0), c.int(1)
                base = list(wires)
                for i in range(1, max(nr, 1)):
                    deg = 360.0 * i / nr
                    wires.extend(
                        (t + its * i if t else 0, [_rot(p, 0, 0, deg) for p in pts])
                        for t, pts in base
                    )
            elif mn == "GX":
                its = c.int(0)
                planes = str(c.int(1)).zfill(3)
                k = 1
                for axis, bit in enumerate(planes[:3]):
                    if bit != "1":
                        continue
                    base = list(wires)
                    for t, pts in base:
                        wires.append(
                            (
                                t + its * k if t else 0,
                                [
                                    tuple(
                                        -v if j == axis else v for j, v in enumerate(p)
                                    )
                                    for p in pts
                                ],
                            )
                        )
                    k *= 2
            elif mn == "GS":
                f = c.num(2, 1.0)
                wires = [
                    (t, [tuple(v * f for v in p) for p in pts]) for t, pts in wires
                ]
        except (DeckError, ValueError, IndexError):
            continue
    return wires


def _plane_tol(wires) -> float:
    extent = max((abs(v) for _, pts in wires for p in pts for v in p), default=1.0)
    return max(extent, 1e-3) * 1e-9


def ground_geometry(cards: list) -> dict:
    """Which wires sit below, across or on z=0 -- measured on the transformed
    geometry, so a GM that lowers a radial counts."""
    wires = conductors(cards)
    tol = _plane_tol(wires)
    buried, straddle = False, []
    plane_ends = []
    for tag, pts in wires:
        if any(p[2] < -tol for p in pts):
            buried = True
        for i in range(len(pts) - 1):
            p, q = pts[i], pts[i + 1]
            if (p[2] < -tol and q[2] > tol) or (p[2] > tol and q[2] < -tol):
                straddle.append(tag)
                break
        if len(pts) >= 2:
            for end, nxt in ((pts[0], pts[1]), (pts[-1], pts[-2])):
                if abs(end[2]) <= tol:
                    plane_ends.append((end, nxt[2] < -tol))
    # A node on the plane is "continued below" when some conductor leaves it
    # downward; one that only rises from it is cut loose by GE -1.
    loose = []
    for end, down in plane_ends:
        if down:
            continue
        if not any(d and math.dist(end, e) <= max(tol, 1e-9) for e, d in plane_ends):
            loose.append(end)
    return {"buried": buried, "straddle": straddle, "loose_plane_ends": loose}


# ---------------------------------------------------------------------------
# translation
# ---------------------------------------------------------------------------
_SKIP_CARDS = {
    "GF": "GF reads a numerical Green's function file this corpus does not have",
    "MP": "MP (nec2++ medium-parameters card): NEC-4.2 stops, FAULTY INPUT "
    "COMMAND LABEL (measured); dropping it would change the medium",
}
_ZERO = ("0", "0.", "0.0", "-0", "+0")


def _ground_label(types: set) -> str:
    """free / pec / rc / gn2 (gn3 on a twin), '+'-joined when a deck asks for
    more than one ground across its runs."""
    names = {-1: "free", 0: "rc", 1: "pec", 2: "gn2", 3: "gn3"}
    real = sorted(t for t in types if t != -1)
    if not real:
        return "free"
    return "+".join(names.get(t, f"gn{t}") for t in real)


def _gn_nec42(c: Card, notes: list) -> str:
    """One GN card for NEC-4.2. Only the Sommerfeld one changes: NOFILE."""
    iperf = c.int(0)
    if iperf == 3:
        raise Refused(
            "GN 3 in a NEC-2 / 4nec2 deck is 4nec2's MININEC-type ground; NEC-4.2 "
            "reads GN 3 as its newer Sommerfeld ground, so passing it through would "
            "swap the ground model"
        )
    if iperf != 2:
        return c.text()
    nradl = c.int(1) if len(c.f) > 1 else 0
    if nradl > 0:
        raise Refused(
            f"GN 2 with a {nradl}-radial ground screen: NEC-4.2 stops, RADIAL WIRE "
            "G. S. APPROXIMATION MAY NOT BE USED WITH SOMMERFELD GROUND OPTION "
            "(measured)"
        )
    fields = list(c.f)
    if fields and not n5._PLAIN_NUM_RE.fullmatch(fields[-1]):
        word = fields.pop()
        if word.upper() != "NOFILE":
            notes.append(f"GN 2: table file name {word!r} replaced by NOFILE")
    return " ".join(["GN", *fields, "NOFILE"])


def _check_ex6(cards: list, geo, notes: list) -> dict:
    """{id(card): canonical text} for 4nec2 EX 6 cards NEC-4.2 can run natively,
    or Refused when one is ambiguous.

    4nec2 runs EX 6 (its current source) as NEC-2's gyrator idiom: a phantom
    wire, an NT with Y11 = Y22 = 0 and Y12 = j tying it to the addressed
    segment, an EX 0 of V = jI on the phantom. NEC-4.2's EX 6 is a native
    segment current source, and measured on the licensed binary the two are the
    same model, not just alike:

    * a dipole driven EX 6 prints the impedance of its EX 0 twin to every digit,
      with I4 (0, 1, 10) and a trailing F3 making no difference;
    * on a segment that is also a TL port, and on one carrying an LD 4 load,
      native EX 6 and the hand-built gyrator give every segment current to the
      printed digit (the current divides with the line exactly as the
      gyrator's does).

    So the card carries over as ``EX 6 tag seg 0 Ire Iim``. It is refused, with
    the deck, only where the deck does not say one thing:

    * two sources on one segment (NEC-4.2 sums two EX 6 there, and with an EX 0
      beside the EX 6 it printed no impedance at all);
    * a zero current as written (``EX 6 1 1 1 0``: which field was meant?).
    """
    out = {}
    ex6 = [c for c in cards if c.mn == "EX" and c.f and c.int(0) == 6]
    if not ex6:
        return out

    def seg_of(c):
        r = geo.resolve(c.int(1), c.int(2), "EX", c.line)
        return (r[0], r[2], r[3])  # tag, index within the tag, local seg

    sources = {}
    for c in cards:
        if c.mn == "EX" and c.f and c.int(0) in (0, 5, 6):
            key = seg_of(c)
            sources[key] = sources.get(key, 0) + 1
    for c in ex6:
        why = None
        ire = c.num(4) if len(c.f) > 4 else 0.0
        iim = c.num(5) if len(c.f) > 5 else 0.0
        if sources.get(seg_of(c), 0) > 1:
            why = "another source sits on the same segment"
        elif ire == 0.0 and iim == 0.0:
            why = (
                f"its current is zero as written ({c.text()!r}): the fields do not "
                "say what was meant"
            )
        if why:
            raise Refused(
                f"4nec2 EX 6 (a current source 4nec2 runs as a NEC-2 gyrator) on line "
                f"{c.line} is ambiguous as NEC-4.2's native EX 6: {why}"
            )
        vr = c.f[4] if len(c.f) > 4 else "1"
        vi = c.f[5] if len(c.f) > 5 else "0"
        out[id(c)] = f"EX 6 {c.f[1]} {c.f[2]} 0 {vr} {vi}"
    notes.append(
        f"EX 6: {len(ex6)} 4nec2 current source(s) (run by 4nec2 as a NEC-2 gyrator) "
        "written as NEC-4.2's native EX 6 segment current source"
    )
    return out


def _first_fr_mhz(cards: list):
    for c in cards:
        if c.mn == "FR" and len(c.f) > 4:
            return c.num(4)
    return None


def _ld_4nec2(c: Card, cards: list, notes: list):
    """4nec2's own load types as NEC-4.2 cards, or None to drop a no-op.

    Their meanings are the ones `antennaknobs.nec_import` reads (issues #444 and
    #447), not guessed here:

    * LD 7 is 4nec2's insulated wire: F1 the jacket's relative permittivity,
      F2 its outer radius in metres. NEC-4 has that model as its IS card
      (``IS 0 tag seg1 seg2 eps_r sigma radius``), measured on the licensed
      binary: a 1 mm dipole with a 1.6 mm eps_r 4.5 jacket prints 69.16+1.54j
      against 69.17+1.60j for the a'+L' equivalent, and IS addresses a whole
      structure (tag 0) or tag (segments 0) the way LD does.
    * LD 6 is 4nec2's LC trap: F1 the coil's unloaded Q (0 means 100), F2 / F3
      L and C, which 4nec2 runs as a parallel RLC with R = Q*omega*L at the FIRST
      FR card's frequency. Written as that LD 1.
    """
    typ = c.int(0)
    addr = " ".join((c.f + ["0", "0", "0"])[1:4])
    if typ == 7:
        eps, b = c.num(4), c.num(5)
        if eps <= 1.0 or b <= 0.0:
            notes.append(
                f"LD 7 on line {c.line} dropped: a vacuum or zero jacket is no load"
            )
            return None
        notes.append(
            f"LD 7 (4nec2 insulated wire) on line {c.line} written as NEC-4's IS "
            "sheath: same permittivity and outer radius, sigma 0"
        )
        return f"IS 0 {addr} {c.f[4]} 0 {c.f[5]}"
    if typ == 6:
        q, ind = c.num(4), c.num(5)
        cap = c.f[6] if len(c.f) > 6 else "0"
        f_mhz = _first_fr_mhz(cards)
        if ind <= 0.0:
            raise Refused(f"LD 6 (4nec2 LC trap) on line {c.line} has no inductance")
        if f_mhz is None:
            raise Refused(
                f"LD 6 (4nec2 LC trap) on line {c.line}: its loss resistance is set at "
                "the first FR frequency, and the deck has no FR card"
            )
        r = (q or 100.0) * 2.0 * math.pi * f_mhz * 1e6 * ind
        notes.append(
            f"LD 6 (4nec2 LC trap, Q {q or 100.0:g}) on line {c.line} written as LD 1 "
            f"parallel RLC, R = Q*omega*L = {r:.6g} ohm at the first FR, {f_mhz:g} MHz"
        )
        return f"LD 1 {addr} {n5._format_field(r)} {c.f[5]} {cap}"
    raise Refused(
        f"LD {typ} is not a NEC load type (4nec2 defines 6 and 7): NEC-4.2 stops, "
        "IMPROPER LOAD TYPE (measured)"
    )


def _gyrator_nt(cards: list) -> int:
    """NT cards spelling the EZNEC / 4nec2 hand-built gyrator (Y11 = Y22 = 0,
    Y12 = +-j): valid NEC-2 that NEC-4.2 runs as written, recorded only."""
    k = 0
    for c in cards:
        if c.mn != "NT" or len(c.f) < 10:
            continue
        try:
            y = [float(v) for v in c.f[4:10]]
        except ValueError:
            continue
        if y[0] == y[1] == y[4] == y[5] == 0.0 and y[2] == 0.0 and abs(y[3]) > 0:
            k += 1
    return k


def _nec2_gh(cards: list, notes: list) -> list:
    """NEC-2's GH as NEC-4.2 reads it, or refused.

    The two programs share the mnemonic and not the fields. NEC-2's GH is
    ``GH tag ns S HL A1 B1 A2 B2 RAD`` (turn spacing, axial length -- negative
    for a left-handed helix -- and the x/y radii at each end); NEC-4.2's,
    measured from its own geometry printout, is ``GH tag ns TURNS LENGTH RH1 RH2
    RW1 RW2`` (turns, length, helix radius and wire radius at each end, a taper
    being a log spiral). Passed through, a NEC-2 helix is silently another
    antenna: Cebik's conical 4-5a became a wire of 0.16 m radius and printed an
    impedance of 1e-7 ohm. So:

    * a right-handed helix of one constant circular radius is written as
      NEC-4.2's GH (``TURNS = HL / S``), measured to reproduce nec2c's segment
      centres exactly;
    * any other NEC-2 helix (left-handed, tapered, elliptical) is written as
      its ``ns`` straight GW pieces on NEC-2's own geometry -- z = |HL| t, radii
      linear in t, phi = 2 pi z / S, (A cos phi, B sin phi) right-handed and
      (B sin phi, A cos phi) left-handed, checked against nec2c's segment
      table -- one segment each on the GH's tag, so (tag, seg) addressing is
      unchanged (NEC-4.2's own left-handed helix is NEC-2's turned 90 degrees);
    * a GH with neither layout's field count is refused.
    """
    out = []
    for c in cards:
        if c.mn != "GH":
            out.append(c)
            continue
        if len(c.f) != 9:
            raise Refused(
                f"GH on line {c.line} has {len(c.f) - 2} real fields, neither NEC-2's "
                "7 (S HL A1 B1 A2 B2 RAD) nor NEC-4's 6: its geometry is ambiguous"
            )
        ns = c.int(1)
        s, hl = c.num(2), c.num(3)
        a1, b1, a2, b2 = (c.num(k) for k in range(4, 8))
        if s == 0.0:
            raise Refused(f"GH on line {c.line} has zero turn spacing")
        if hl > 0 and a1 == b1 == a2 == b2:
            out.append(
                Card(
                    "GH",
                    [
                        c.f[0],
                        c.f[1],
                        n5._format_field(hl / s),
                        c.f[3],
                        c.f[4],
                        c.f[4],
                        c.f[8],
                        c.f[8],
                    ],
                    c.line,
                )
            )
            notes.append(
                f"GH tag {c.f[0]}: NEC-2 helix (spacing {s:g}, length {hl:g}) written in "
                f"NEC-4's GH fields ({hl / s:.10g} turns; helix and wire radius twice)"
            )
            continue
        pts = []
        for i in range(ns + 1):
            t = i / ns
            z = abs(hl) * t
            a, b = a1 + (a2 - a1) * t, b1 + (b2 - b1) * t
            ph = 2.0 * math.pi * z / s
            pts.append(
                (a * math.cos(ph), b * math.sin(ph), z)
                if hl >= 0
                else (b * math.sin(ph), a * math.cos(ph), z)
            )
        for i in range(ns):
            out.append(
                Card(
                    "GW",
                    [c.f[0], "1"]
                    + [n5._format_field(v) for v in (*pts[i], *pts[i + 1])]
                    + [c.f[8]],
                    c.line,
                )
            )
        kind = "left-handed" if hl < 0 else "tapered or elliptical"
        notes.append(
            f"GH tag {c.f[0]}: {kind} NEC-2 helix written as its {ns} GW pieces on "
            "NEC-2's geometry (NEC-4.2's GH has other fields and no such shape)"
        )
    return out


def translate_deck(comments: list, cards: list, name: str) -> tuple:
    """``(deck text, notes, ground types, twin)`` for ONE structure.
    ``twin`` is True when the deck is on GN 2 and gets a GN 3 twin."""
    n5._validate_nec(cards)
    dup = n5._duplicate_wire(cards)
    if dup:
        raise InvalidNEC(
            n5._INVALID + f"the same wire is listed twice ({dup}), which makes the "
            "moment matrix singular"
        )
    notes = []
    cards = n5._expand_flat_gh(cards, notes)
    notes = [
        n.replace(
            "NEC-5's GH gives it zero wire length",
            "NEC-4.2 stops on it (DATAGN: SEGMENT DATA ERROR, measured)",
        )
        for n in notes
    ]
    cards = _nec2_gh(cards, notes)
    # Tag resolution on COPIES: the NEC-5 Geometry gives an untagged wire a
    # synthetic tag, which NEC-4.2 does not need, so the deck keeps tag 0.
    geo = n5.Geometry()
    in_geometry = True
    for c in cards:
        if c.mn in _SKIP_CARDS:
            raise Refused(_SKIP_CARDS[c.mn])
        if in_geometry:
            if c.mn == "GE":
                in_geometry = False
                continue
            if c.mn in ("GW", "GA", "GH", "CW", "GM", "GX", "GR"):
                geo.feed(copy.deepcopy(c))
    if not geo.order and not any(c.mn in ("SP", "SM", "SC") for c in cards):
        raise Refused("no wire segments and no patches (a geometry-less deck)")

    # Addresses the deck contradicts on its own are invalid, as in the NEC-5 tool.
    for c in cards:
        if c.mn == "EX" and c.f and c.int(0) in (0, 5, 6) and geo.order:
            geo.resolve(c.int(1), c.int(2), "EX", c.line)
        elif c.mn in ("TL", "NT") and len(c.f) >= 4 and geo.order:
            geo.resolve(c.int(0), c.int(1), c.mn + " port 1", c.line)
            geo.resolve(c.int(2), c.int(3), c.mn + " port 2", c.line)
    ld4 = {}
    for c in cards:
        if c.mn == "LD" and c.f and c.int(0) not in (-1, 0, 1, 2, 3, 4, 5):
            ld4[id(c)] = _ld_4nec2(c, cards, notes)
    ex6 = _check_ex6(cards, geo, notes)
    ngy = _gyrator_nt(cards)
    if ngy:
        notes.append(
            f"NT gyrator idiom ({ngy} NT card(s) with Y11 = Y22 = 0, Y12 = j: a "
            "hand-built current source) kept as written; NEC-4.2 runs it as NEC-2 does"
        )

    gtypes = set()
    for c in cards:
        if c.mn == "GN" and c.f:
            gtypes.add(c.int(0))
    ge = next((c for c in cards if c.mn == "GE"), None)
    ge_flag = ge.int(0) if ge is not None and ge.f else 0
    grounded = bool(gtypes - {-1})
    new_ge = None
    if grounded:
        g = ground_geometry(cards)
        if g["straddle"]:
            raise Refused(
                f"wire tag {g['straddle'][0]} has a segment straddling z=0: NEC-4.2 "
                "solves a segment across the interface wrong without a warning "
                "(measured on a 6 m vertical: 38-621j for 167-125j ohm)"
            )
        if g["buried"]:
            if not gtypes <= {-1, 2}:
                raise Refused(
                    "wires below ground over a ground that is not Sommerfeld "
                    f"({_ground_label(gtypes)}): NEC-4.2 stops, MUST USE SOMMERFELD "
                    "FOR INTERACTION ACROSS THE INTERFACE (measured)"
                )
            if ge_flag != -1:
                if ge_flag == 1 and g["loose_plane_ends"]:
                    x, y, _ = g["loose_plane_ends"][0]
                    raise Refused(
                        f"wires below ground under GE 1, and a conductor ending on "
                        f"the plane at ({x:g}, {y:g}, 0) that GE 1 connects to its "
                        "image; NEC-4.2 needs GE -1 for the buried wires, which "
                        "would leave that end open-circuited"
                    )
                new_ge = "GE -1"
                notes.append(
                    f"GE {ge_flag} -> GE -1: the deck has wires below ground over "
                    "GN 2, which NEC-4.2 spells GE -1 (GE 1 stops, SEGMENT EXTENDS "
                    "BELOW GROUND)"
                )

    kh_ek = sorted({c.mn for c in cards if c.mn in ("EK", "KH")})
    if kh_ek:
        notes.append(
            f"{'/'.join(kh_ek)} kept; NEC-4.2 prints THE EK AND KH COMMANDS HAVE NO "
            "EFFECT IN NEC-4 and uses its own kernel"
        )

    out = []
    for c in cards:
        mn = c.mn
        if mn == "GE" and new_ge is not None:
            out.append(new_ge)
            continue
        if mn == "GN" and c.f:
            out.append(_gn_nec42(c, notes))
            continue
        if mn == "EX" and id(c) in ex6:
            out.append(ex6[id(c)])
            continue
        if id(c) in ld4:
            if ld4[id(c)] is not None:
                out.append(ld4[id(c)])
            continue
        out.append(c.text())
    if out and out[-1] == "EN":
        out.pop()
    if not any(ln.split()[0] in ("XQ", "RP", "NE", "NH") for ln in out if ln.strip()):
        out.append("XQ 0")
        notes.append("XQ 0 added: the deck had no execution request (XQ/RP/NE/NH)")
    out.append("EN")
    header = [f"CM {ln}" if ln else "CM" for ln in comments]
    header.append(f"CM nec4_corpus {VERSION}: translated from {name}")
    header.extend(f"CM nec4_corpus: {n}" for n in notes)
    header.append("CE")
    return "\n".join(header + out) + "\n", notes, gtypes, 2 in gtypes


_GN2_RE = re.compile(r"^GN 2(?= )", re.M)


def gn3_twin(deck: str) -> str:
    """The GN 3 twin of a translated GN 2 deck: every Sommerfeld card's type,
    and nothing else, plus one CM line saying so."""
    body = _GN2_RE.sub("GN 3", deck)
    return body.replace(
        "\nCE\n",
        "\nCM nec4_corpus: GN 3 twin -- identical to the .gn2 deck but for GN 3\nCE\n",
        1,
    )


def translate_file(path: Path, rel: str) -> dict:
    rec = {"file": rel, "status": "translated", "outputs": [], "notes": []}
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
        comments, cards = n5.normalize(text, rel)
        parts = n5._split_nx(cards)
        if len(parts) > 1:
            rec["notes"].append(
                f"NX: split into {len(parts)} decks (one structure each)"
            )
        for i, part in enumerate(parts, 1):
            deck, notes, gtypes, twin = translate_deck(comments, part, rel)
            rec["notes"].extend(
                notes if len(parts) == 1 else [f"[{i}] {n}" for n in notes]
            )
            rec["outputs"].append(
                (i if len(parts) > 1 else 0, deck, gtypes, twin, notes)
            )
    except InvalidNEC as e:
        rec.update(status="invalid", reason=str(e), outputs=[])
    except Refused as e:
        rec.update(status="refused", reason=str(e), outputs=[])
    except DeckError as e:
        rec.update(status="unreadable", reason=str(e), outputs=[])
    except (ValueError, IndexError, RecursionError, KeyError) as e:
        rec.update(status="unreadable", reason=f"{type(e).__name__}: {e}", outputs=[])
    return rec


def _meta_row(step: str, **fields) -> str:
    meta = {"tool": "nec4_corpus.py", "version": VERSION, "step": step}
    meta.update(fields)
    meta["started"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return json.dumps({"_meta": meta}) + "\n"


def cmd_translate(args) -> int:
    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report) if args.report else out / "translate-report.jsonl"
    counts = {
        "translated": 0,
        "refused": 0,
        "invalid": 0,
        "unreadable": 0,
        "collision": 0,
    }
    reasons, note_kinds = {}, {}
    written_n = 0
    sources = []
    for p in n5._iter_decks(src):
        rel = p.relative_to(src).as_posix()
        if args.only and args.only not in rel:
            continue
        sources.append((p, rel))
        if args.limit and len(sources) >= args.limit:
            break
    kept_over = n5._output_collisions([rel for _, rel in sources])
    with open(report_path, "w", encoding="utf-8") as report:
        report.write(_meta_row("translate", src=str(src)))
        for p, rel in sources:
            if rel in kept_over:
                rec = {
                    "file": rel,
                    "status": "collision",
                    "notes": [],
                    "outputs": [],
                    "reason": f"translates to the same output path as {kept_over[rel]}, "
                    "which is kept",
                }
            else:
                rec = translate_file(p, rel)
            stem = re.sub(r"\.(nec|inp)$", "", rel, flags=re.I)
            rec["written"] = []
            decks = []
            for idx, deck, gtypes, twin, notes in rec.pop("outputs"):
                base = stem + (f"_{idx}" if idx else "")
                label = _ground_label(gtypes)
                if twin:
                    g2, g3 = base + ".gn2.nec", base + ".gn3.nec"
                    decks.append((g2, deck, label, g3, notes))
                    decks.append(
                        (g3, gn3_twin(deck), label.replace("gn2", "gn3"), g2, notes)
                    )
                else:
                    decks.append((base + ".nec", deck, label, None, notes))
            for rel_out, deck, label, partner, notes in decks:
                dest = out / rel_out
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(deck, encoding="ascii", errors="replace", newline="\n")
                rec["written"].append(
                    {"path": rel_out, "ground": label, "twin": partner, "notes": notes}
                )
                written_n += 1
            counts[rec["status"]] += 1
            if rec["status"] != "translated":
                key = re.sub(r"\d+", "N", rec["reason"])[:100]
                reasons[key] = reasons.get(key, 0) + 1
            for n in rec["notes"]:
                key = re.sub(r"\d+(\.\d+)?", "N", re.sub(r"^\[\d+\] ", "", n))[:90]
                note_kinds[key] = note_kinds.get(key, 0) + 1
            report.write(json.dumps(rec) + "\n")
    _log(
        f"files: {len(sources)}  "
        + "  ".join(f"{k}: {v}" for k, v in counts.items())
        + f"  decks written: {written_n}"
    )
    if reasons:
        _log("\nskipped, by reason:")
        for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
            _log(f"  {v:5d}  {k}")
    if note_kinds:
        _log("\nchanges applied (decks x notes):")
        for k, v in sorted(note_kinds.items(), key=lambda kv: -kv[1]):
            _log(f"  {v:5d}  {k}")
    _log(f"\nreport: {report_path}")
    return 0


# ---------------------------------------------------------------------------
# manifest: one jsonl for the whole corpus
# ---------------------------------------------------------------------------
def cmd_manifest(args) -> int:
    """Merge the public translate report and the catalog manifest into
    ``<root>/manifest.jsonl``: one row per written deck and one per skipped
    source, with source, relative path, ground, twin and what changed."""
    root = Path(args.root)
    rows = []
    pub = root / args.public / "translate-report.jsonl"
    if pub.is_file():
        for line in pub.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if "_meta" in rec:
                continue
            coll = rec["file"].split("/", 1)[0]
            if not rec.get("written"):
                rows.append(
                    {
                        "source": "public",
                        "collection": coll,
                        "file": rec["file"],
                        "path": None,
                        "ground": None,
                        "status": rec["status"],
                        "reason": rec.get("reason"),
                        "changes": rec.get("notes", []),
                    }
                )
            for w in rec.get("written", []):
                rows.append(
                    {
                        "source": "public",
                        "collection": coll,
                        "file": rec["file"],
                        "path": f"{args.public}/{w['path']}",
                        "ground": w["ground"],
                        "twin": f"{args.public}/{w['twin']}" if w["twin"] else None,
                        "status": "written",
                        "changes": w["notes"],
                    }
                )
    cat = root / args.catalog / "manifest.json"
    if cat.is_file():
        m = json.loads(cat.read_text(encoding="utf-8"))
        for w in m["written"]:
            rows.append(
                {
                    "source": "catalog",
                    "collection": "antennaknobs-catalog",
                    "file": f"{w['design']} ({w['rung']}, {w['ground']})",
                    "path": f"{args.catalog}/{w['file']}",
                    "ground": w.get("gn", "free" if w["ground"] == "free" else "gn2"),
                    "twin": f"{args.catalog}/{w['twin']}" if w.get("twin") else None,
                    "status": "written",
                    "changes": [],
                }
            )
        for s in m["skipped"]:
            rows.append(
                {
                    "source": "catalog",
                    "collection": "antennaknobs-catalog",
                    "file": f"{s['design']} ({s['rung']}, {s['ground']})",
                    "path": None,
                    "ground": None,
                    "status": "skipped",
                    "reason": s["why"],
                    "changes": [],
                }
            )
    out = root / "manifest.jsonl"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(_meta_row("manifest", root=str(root)))
        for r in rows:
            f.write(json.dumps(r) + "\n")
    written = [r for r in rows if r["status"] == "written"]
    by_ground, by_status = {}, {}
    for r in written:
        key = (r["source"], r["ground"])
        by_ground[key] = by_ground.get(key, 0) + 1
    for r in rows:
        if r["status"] != "written":
            by_status[(r["source"], r["status"])] = (
                by_status.get((r["source"], r["status"]), 0) + 1
            )
    _log(f"decks written: {len(written)}")
    for (s, g), v in sorted(by_ground.items()):
        _log(f"  {s:8s} {g:12s} {v:5d}")
    _log("skipped sources:")
    for (s, st), v in sorted(by_status.items()):
        _log(f"  {s:8s} {st:12s} {v:5d}")
    pairs = sum(1 for r in written if r.get("twin") and r["ground"].endswith("gn2"))
    _log(f"GN 2 / GN 3 pairs: {pairs}")
    _log(f"manifest: {out}")
    return 0


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
# What NEC-4.2 says when it stops. Case-sensitive: the printout echoes the deck's
# CM lines, and those are removed from the scan besides.
_ERROR_RE = re.compile(
    r"\bERROR\b|FAULTY|INVALID|IMPROPER|MAY NOT BE USED|MUST USE|STOP\b"
    r"|Segmentation fault|SIGSEGV|SIGBUS|SIGFPE|Allocation would exceed|Cannot allocate"
    r"|invalid pointer|double free|corrupted"
)
_NOT_ERROR_RE = re.compile(r"IEEE_|% error|NO ERRORS")
_AIP_HEADER = "ANTENNA INPUT PARAMETERS"
# TAG, an optional `*` (NEC-4.2 flags an EX 5 source row so), SEG, then nine
# numbers that may run together where a minus sign took the separator.
_AIP_ROW_RE = re.compile(r"^\s*(\d+)\s*\*?\s+(\d+)(?=[\s+-])(.*)$")
_NUMBER = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+)(?:[EeDd][-+]?\d+)?")
_NUMBERS_ONLY = re.compile(rf"(?:\s*{_NUMBER.pattern})+\s*")
_SOURCE_CARD_RE = re.compile(r"^EX\s+[056]\b", re.M)


def aip_rows(text: str) -> list:
    """[(tag, seg, Zre, Zim)] of the FIRST ANTENNA INPUT PARAMETERS block."""
    chunks = text.split(_AIP_HEADER)[1:]
    rows = []
    if not chunks:
        return rows
    for line in chunks[0].splitlines():
        m = _AIP_ROW_RE.match(line)
        rest = m.group(3) if m else ""
        nums = (
            [float(x) for x in _NUMBER.findall(rest)]
            if _NUMBERS_ONLY.fullmatch(rest)
            else []
        )
        if len(nums) != 9:
            if rows:
                break
            continue
        rows.append((int(m.group(1)), int(m.group(2)), nums[4], nums[5]))
    return rows


def _limit_memory(max_mb: int):
    if not max_mb:
        return None
    try:
        import resource
    except ImportError:  # Windows: no per-process address-space cap here
        return None

    def apply():
        lim = max_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (lim, lim))

    return apply


def run_exe(
    exe: str, deck_text: str, timeout: float, keep: Path = None, env=None, max_mb=0
) -> dict:
    """One deck through NEC-4.2 as ``exe model.nec model.out`` in a fresh temp
    dir (removed afterwards, with whatever the binary wrote there).

    ok (impedance printed), ok-no-source (no EX 0/5/6: nothing to print),
    no-impedance (a source but no ANTENNA INPUT PARAMETERS), no-printout
    (exit 0 and an empty printout), error (NEC-4.2 said so, exit 0 -- it
    exits 0 on its own input errors), crash (non-zero exit), timeout."""
    comments = {
        ln[2:].strip()
        for ln in deck_text.splitlines()
        if ln[:2] == "CM" and ln[2:].strip()
    }
    with tempfile.TemporaryDirectory(prefix="nec42c_") as td:
        tdp = Path(td)
        (tdp / "model.nec").write_text(deck_text, encoding="ascii", errors="replace")
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [exe, "model.nec", "model.out"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors="replace",
                cwd=td,
                timeout=timeout,
                env=env,
                preexec_fn=_limit_memory(max_mb),
            )
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "wall_s": time.perf_counter() - t0, "z": []}
        wall = time.perf_counter() - t0
        rc = proc.returncode
        outp = tdp / "model.out"
        printout = outp.read_text(errors="replace") if outp.is_file() else ""
        console = (proc.stdout or "") + (proc.stderr or "")
        errs = [
            ln.strip()
            for ln in (printout + "\n" + console).splitlines()
            if _ERROR_RE.search(ln)
            and not _NOT_ERROR_RE.search(ln)
            and ln.strip() not in comments
        ]
        rows = aip_rows(printout)
        if rc != 0:
            status = "crash"
            errs = [f"exit code {rc}" + (": " + errs[0] if errs else "")]
            rows = []
        elif errs:
            status = "error"
        elif rows:
            status = "ok"
        elif not printout.strip():
            status = "no-printout"
        elif not _SOURCE_CARD_RE.search(deck_text):
            status = "ok-no-source"
        else:
            status = "no-impedance"
        if keep is not None and status not in ("ok", "ok-no-source"):
            keep.parent.mkdir(parents=True, exist_ok=True)
            keep.write_text(
                printout + f"\n--- console (exit code {rc}) ---\n" + console,
                errors="replace",
            )
        return {
            "status": status,
            "exit_code": rc,
            "wall_s": round(wall, 4),
            "error": errs[0][:200] if errs else None,
            "z": [[r[0], r[1], r[2], r[3]] for r in rows[:8]],
        }


def cmd_check(args) -> int:
    exe = str(Path(args.exe).resolve())
    src = Path(args.src)
    decks = [
        p
        for p in sorted(src.rglob("*.nec"))
        if p.is_file() and (not args.only or args.only in p.as_posix())
    ]
    if args.limit:
        decks = decks[: args.limit]
    engine_env, threads, timing_valid = n5._engine_env(args.jobs)
    environment = n5._environment_meta(exe, jobs=args.jobs)
    environment["engine_threads"] = threads
    report_path = Path(args.report) if args.report else src / "check-report.jsonl"
    keep_dir = Path(args.keep_dir) if args.keep_dir else None
    resuming = bool(getattr(args, "resume", False)) and report_path.is_file()
    if resuming:
        # Keep the rows already written (a run stopped part-way) and run only
        # the decks the report does not have; the new rows are appended.
        _, done = n5._read_report(report_path)
        decks = [p for p in decks if p.relative_to(src).as_posix() not in done]
        _log(
            f"--resume: {len(done)} decks already in {report_path}, {len(decks)} to run"
        )
    counts, errors = {}, {}
    t0 = time.perf_counter()

    def one(p):
        rel = p.relative_to(src)
        keep = (keep_dir / rel.with_suffix(".out")) if keep_dir else None
        rec = run_exe(
            exe,
            p.read_text(errors="replace"),
            args.timeout,
            keep,
            engine_env,
            args.max_mem_mb,
        )
        rec["file"] = rel.as_posix()
        return rec

    with open(report_path, "a" if resuming else "w", encoding="utf-8") as report:
        report.write(
            _meta_row(
                "check-resume" if resuming else "check",
                exe=exe,
                timeout_s=args.timeout,
                max_mem_mb=args.max_mem_mb,
                timing_valid=timing_valid,
                environment=environment,
            )
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for i, rec in enumerate(pool.map(one, decks), 1):
                counts[rec["status"]] = counts.get(rec["status"], 0) + 1
                if rec.get("error"):
                    key = re.sub(r"[-+]?\d+(\.\d+)?", "N", rec["error"])[:90]
                    errors[key] = errors.get(key, 0) + 1
                report.write(json.dumps(rec) + "\n")
                report.flush()
                if i % 200 == 0:
                    _log(f"  {i}/{len(decks)}  {counts}")
    _log(f"\n{len(decks)} decks in {time.perf_counter() - t0:.0f} s: {counts}")
    if errors:
        _log("\nfailures, by message:")
        for k, v in sorted(errors.items(), key=lambda kv: -kv[1])[:30]:
            _log(f"  {v:5d}  {k}")
    _log(f"\nreport: {report_path}")
    return 0


# ---------------------------------------------------------------------------
# twins: GN 2 against GN 3 in one check report
# ---------------------------------------------------------------------------
def _pct(sorted_vals, q):
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def cmd_twins(args) -> int:
    """|Z_gn3 - Z_gn2| / |Z_gn2| on the first impedance row of every pair."""
    _, rows = n5._read_report(Path(args.report))
    pairs, both_ok, status_split, rels = 0, 0, [], []
    for f, r2 in sorted(rows.items()):
        if not f.endswith(".gn2.nec"):
            continue
        f3 = f[: -len(".gn2.nec")] + ".gn3.nec"
        r3 = rows.get(f3)
        if r3 is None:
            continue
        pairs += 1
        z2, z3 = n5._first_z(r2), n5._first_z(r3)
        if z2 is None or z3 is None:
            status_split.append((f, r2.get("status"), r3.get("status")))
            continue
        both_ok += 1
        rel = abs(z3 - z2) / abs(z2) if abs(z2) > 0 else float("inf")
        rels.append((rel, f[: -len(".gn2.nec")], z2, z3))
    rels.sort(key=lambda t: t[0])
    vals = [t[0] for t in rels]
    _log(f"GN 2 / GN 3 pairs: {pairs}; both with an impedance: {both_ok}")
    if vals:
        _log(
            f"|Z3-Z2|/|Z2|: median {_pct(vals, 0.5):.3e}  p95 {_pct(vals, 0.95):.3e}  "
            f"max {vals[-1]:.3e}"
        )
        for thr in (1e-6, 1e-4, 1e-3, 1e-2, 1e-1):
            _log(f"  > {thr:g}: {sum(v > thr for v in vals)}")
        _log(f"largest {args.top}:")
        for rel, name, z2, z3 in rels[::-1][: args.top]:
            _log(f"  {rel:.3e}  {name}  {n5._z_str(z2)} -> {n5._z_str(z3)}")
    if status_split:
        _log(f"pairs without an impedance on one side: {len(status_split)}")
        split_kinds = {}
        for _, s2, s3 in status_split:
            split_kinds[(s2, s3)] = split_kinds.get((s2, s3), 0) + 1
        for (s2, s3), v in sorted(split_kinds.items(), key=lambda kv: -kv[1]):
            _log(f"  gn2 {s2} / gn3 {s3}: {v}")
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            for rel, name, z2, z3 in rels[::-1]:
                f.write(
                    json.dumps(
                        {
                            "deck": name,
                            "rel": rel,
                            "z_gn2": [z2.real, z2.imag],
                            "z_gn3": [z3.real, z3.imag],
                        }
                    )
                    + "\n"
                )
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--version", action="version", version="nec4_corpus.py " + VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("translate", help="translate every deck under --src for NEC-4.2")
    t.add_argument("--src", default="raw")
    t.add_argument("--out", default="nec42/public")
    t.add_argument("--report", default=None)
    t.add_argument("--only", default=None, help="substring filter on the relative path")
    t.add_argument("--limit", type=int, default=0)
    t.set_defaults(fn=cmd_translate)

    m = sub.add_parser(
        "manifest", help="merge the public report and the catalog manifest"
    )
    m.add_argument("--root", required=True)
    m.add_argument("--public", default="public")
    m.add_argument("--catalog", default="catalog")
    m.set_defaults(fn=cmd_manifest)

    c = sub.add_parser(
        "check", help="run every .nec under --src through a NEC-4.2 executable"
    )
    c.add_argument("--exe", required=True)
    c.add_argument("--src", required=True)
    c.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    c.add_argument("--timeout", type=float, default=300.0)
    c.add_argument(
        "--max-mem-mb",
        type=int,
        default=0,
        help="address-space cap per engine process (POSIX); jobs x this bounds the run",
    )
    c.add_argument("--report", default=None)
    c.add_argument(
        "--keep-dir",
        default=None,
        help="save the printout of every deck that did not solve cleanly here (local only; "
        "NEC-4.2 printouts are never to be committed or shared)",
    )
    c.add_argument("--only", default=None)
    c.add_argument("--limit", type=int, default=0)
    c.add_argument(
        "--resume",
        action="store_true",
        help="append to an existing --report, running only the decks it lacks",
    )
    c.set_defaults(fn=cmd_check)

    w = sub.add_parser(
        "twins", help="GN 2 vs GN 3 impedance statistics from a check report"
    )
    w.add_argument("report")
    w.add_argument("--top", type=int, default=10)
    w.add_argument("--out", default=None, help="write every pair's numbers as jsonl")
    w.set_defaults(fn=cmd_twins)

    d = sub.add_parser("compare", help="the NEC-5 tool's deck-by-deck report diff")
    d.add_argument("a")
    d.add_argument("b")
    d.add_argument("--ignore-env", action="store_true")
    d.add_argument("--tol", type=float, default=1e-4)
    d.set_defaults(fn=n5.cmd_compare)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
