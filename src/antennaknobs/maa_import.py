"""Import an MMANA-GAL model (``.maa``) as a NEC deck (AK#1897).

MMANA-GAL is MININEC-based, and a ``.maa`` file is its saved model: wires,
sources, loads, its automatic-segmentation parameters and a ground line, in a
fixed POSITIONAL layout. ``read_maa`` turns one into the same
:class:`~antennaknobs.nec_import.NecDeck` a ``.nec`` deck becomes, so a
``.maa`` opens wherever a deck does (the CLI's ``@file``, the designs folder,
the workbench's Open...).

How the file is read (the field meanings are the MMANA-GAL help plus the
oracle sitting recorded with the census, ``scratch/maa-census/REPORT.md`` §7):

* **Layout.** Title; a bare ``*``; the design frequency (MHz); then the
  Wires, Source, Load, Segmentation and G/H/M/R/AzEl/X blocks, in that order,
  each behind a header line; then an optional ``$$$`` taper-wire table and an
  optional ``###`` comment. The header lines are cosmetic and localised
  (``***Wires***``, ``* Провода *``), so a block is found by its position,
  never by its header's text. Fields split on commas, tabs and spaces.
* **Wires** ``X1 Y1 Z1 X2 Y2 Z2 R SEG``, metres. R is the radius in metres (the
  GUI shows mm); a negative R points into the taper-wire table; R = 0 is
  MMANA's insulator wire and is refused. SEG: -1 tapered automatic (both
  ends), -2 / -3 tapered at the start / end only, 0 regular automatic, > 0 a
  manual segment count.
* **Positions** ``w<wire><b|c|e>[offset]``: wire start, centre or end, and an
  offset in pulses (``c+1`` toward the end, ``e1`` inward). MMANA puts sources
  and loads on PULSES, which straddle the junction between two segments; here
  each becomes a port at that segment end (a knot), which is what NEC-5's
  segment-end sources are, so the deck is built in NEC-5's spelling.
* **Sources** ``POS, phase (deg), volts``: phase BEFORE magnitude.
* **Loads** by type: 0 = ``L uH, C pF, Q`` (C = 0 an inductor, L = 0 a
  capacitor, both a parallel L||C trap); 1 = ``R, jX`` ohms, fixed at every
  frequency; 2 = MMANA's Laplace (S) form, refused. The load count line's
  second field is the "Use loads" switch: 0 means the file's loads are off,
  and they are not applied.
* **Segmentation** ``DM1, DM2, SC, EC``. MMANA's own mesher is not emulated
  (the 09-23 no-re-mesh-emulation precedent): every automatic wire is
  meshed by `_auto_mesh` from these four numbers, and the note says so.
* **Ground** ``G, H, M, R, Az, El, X``: G 0 free, 1 perfect, 2 real; H is
  added to every z; M is the wire material; R the reference impedance for
  SWR; Az/El the F/B rear ranges (pattern readouts, not physics). MMANA's real
  ground is MININEC-type -- perfect ground for the currents, the soil only in
  the pattern -- and the soil is NOT in the file (MMANA keeps it in its own
  settings), so a stated default soil is assumed.

Whatever the file says that cannot be modelled is refused BY NAME, with its
line: a stack, a Laplace load, an insulator wire, a user-defined or iron
material, an offset on an automatically meshed wire (its pulse depends on
MMANA's own mesh), a source or load at a free wire end, ... Nothing is
snapped: a position that is not on the mesh cuts the wire there.
"""

from __future__ import annotations

import cmath
import math
import re
from dataclasses import dataclass, replace

from .builder import C_LIGHT_MHZ_M
from .nec_import import GeometryLimits, NecDeck, parse_nec

__all__ = [
    "MAA_DEFAULT_SOIL",
    "MaaImport",
    "decode_maa",
    "read_maa",
]

#: The soil a ``.maa``'s real ground is given (eps_r, sigma S/m). The file
#: does not carry MMANA's soil -- it lives in MMANA's own settings file, per
#: installation -- so the import assumes the app's usual average ground and
#: says so. Under MMANA's MININEC-type ground it shapes the pattern only.
MAA_DEFAULT_SOIL = (13.0, 0.005)

# MMANA's wire material list (the ground line's M), by list position, as the
# oracle sitting read it off MMANA-GAL Basic 3.5. Copper and aluminium map to
# their bulk conductivities; MMANA's "wire" and "pipe" entries differ by a
# few hundredths of an ohm on its 20 m dipole (73.17 vs 73.24 ohms), which
# nothing here reproduces, so both spellings take the one value.
_MATERIALS = {
    0: ("lossless (perfect) wire", None),
    1: ("copper wire", 5.8e7),
    2: ("copper pipe", 5.8e7),
    3: ("aluminium wire", 3.5e7),
    4: ("aluminium pipe", 3.5e7),
}
_MATERIALS_REFUSED = {
    5: (
        "iron wire",
        "MMANA's iron is magnetic (its loss is set by a permeability as well as "
        "a conductivity), and a wire here carries a conductivity only",
    ),
    6: (
        "iron pipe",
        "MMANA's iron is magnetic (its loss is set by a permeability as well as "
        "a conductivity), and a wire here carries a conductivity only",
    ),
    7: (
        "user-defined material",
        "MMANA keeps that material's constants in its own settings file, not in "
        "the .maa, so they cannot be read",
    ),
}

_GROUNDS = {0: "free space", 1: "perfect ground", 2: "real ground"}

# Bounds work before any list is built from a field, whatever the caller's
# limits (the CLI passes none).
_HARD_SEGMENT_CAP = 200_000

_SPLIT = re.compile(r"[,\t ]+")
# The centre letter may be the Cyrillic с (U+0441), which MMANA accepts and
# applies (oracle sitting E12; MMANA's own Match\Dipole+L match.maa has it).
_POS = re.compile(r"^[wW](\d+)([bBcCeEсС])([+-]?\d+)?$")

# Positions on one wire closer than this fraction of its length are one point.
_SAME_T = 1e-9


class _Refusal(ValueError):
    pass


def decode_maa(raw: bytes) -> str:
    """A ``.maa`` file's text from its bytes. MMANA writes ASCII or cp1251
    (Cyrillic headers, titles and comments; no file in the corpus is UTF-8),
    so ASCII and UTF-8 are tried first and cp1251 is the fallback -- every
    byte decodes in cp1251 but one, which is replaced."""
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1251", errors="replace")


# --------------------------------------------------------------------------
# The file, as read
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Wire:
    p1: tuple[float, float, float]
    p2: tuple[float, float, float]
    radius: float
    seg: int
    line: int


@dataclass(frozen=True)
class _Pos:
    text: str
    wire: int  # 1-based, as written
    anchor: str  # "b" / "c" / "e"
    offset: int


@dataclass(frozen=True)
class _Source:
    pos: _Pos
    phase_deg: float
    volts: float
    line: int


@dataclass(frozen=True)
class _Load:
    pos: _Pos
    kind: int
    values: tuple[float, ...]
    line: int


@dataclass(frozen=True)
class _Taper:
    pointer: float
    kind: int
    sections: tuple[tuple[float, float], ...]  # (length m, radius m); last open
    line: int


@dataclass(frozen=True)
class _MaaFile:
    title: str
    freq_mhz: float
    wires: tuple[_Wire, ...]
    sources: tuple[_Source, ...]
    loads: tuple[_Load, ...]
    loads_on: bool
    dm1: float
    dm2: float
    sc: float
    ec: float
    ground: int
    height: float
    material: int
    ref_z: float
    tapers: tuple[_Taper, ...]


class _Lines:
    """The file's non-blank lines, numbered, read in order."""

    def __init__(self, text: str, name: str):
        self.name = name
        self.lines = [
            (k, s.strip())
            for k, s in enumerate(text.splitlines(), 1)
            if s.strip() != ""
        ]
        self.i = 0

    def err(self, line: int | None, msg: str) -> ValueError:
        where = f"{self.name} line {line}" if line else self.name
        return ValueError(f"{where}: {msg}")

    def peek(self):
        return self.lines[self.i] if self.i < len(self.lines) else None

    def take(self, what: str):
        if self.i >= len(self.lines):
            raise self.err(None, f"the file ends before its {what}")
        out = self.lines[self.i]
        self.i += 1
        return out

    def header(self, what: str) -> None:
        k, s = self.take(f"{what} header")
        if not s.startswith(("*", "#", "$")):
            raise self.err(
                k,
                f"expected the {what} block's header line (a line starting with "
                f"'*'), found {s[:40]!r} -- a count above it does not match its "
                "lines",
            )

    def fields(self, what: str) -> tuple[int, list[str]]:
        k, s = self.take(what)
        if s.startswith(("*", "#", "$")):
            raise self.err(k, f"expected the {what}, found the header line {s[:40]!r}")
        return k, [f for f in _SPLIT.split(s) if f]


def _num(tok: str, line: int, what: str, lines: _Lines) -> float:
    try:
        v = float(tok)
    except ValueError:
        raise lines.err(line, f"{what} is {tok!r}, not a number") from None
    if not math.isfinite(v):
        raise lines.err(line, f"{what} is {tok!r}, not a finite number")
    return v


def _int(tok: str, line: int, what: str, lines: _Lines) -> int:
    v = _num(tok, line, what, lines)
    if v != int(v):
        raise lines.err(line, f"{what} is {tok!r}, not a whole number")
    return int(v)


def _count(line: int, f: list[str], what: str, lines: _Lines) -> int:
    n = _int(f[0], line, f"the {what} count", lines)
    if n < 0:
        raise lines.err(line, f"the {what} count is {n}")
    return n


def _pos(tok: str, line: int, lines: _Lines) -> _Pos:
    m = _POS.match(tok)
    if m is None:
        raise lines.err(
            line,
            f"position {tok!r} is not MMANA's w<wire><b|c|e>[offset] "
            "(e.g. w1c, w2b, w3e1, w1c-1)",
        )
    anchor = m.group(2)
    anchor = "c" if anchor in ("\u0441", "\u0421") else anchor.lower()
    return _Pos(tok, int(m.group(1)), anchor, int(m.group(3) or 0))


def _parse(text: str, name: str) -> _MaaFile:
    lines = _Lines(text, name)
    if not lines.lines:
        raise lines.err(None, "the file is empty")
    # Title: the line(s) before the first bare '*'. One corpus file omits it.
    title_parts = []
    while True:
        k, s = lines.take("'*' line after the title")
        if s == "*":
            break
        title_parts.append(s)
        if len(title_parts) > 3:
            raise lines.err(
                k,
                "no bare '*' line after the title -- this is not an MMANA-GAL "
                ".maa model",
            )
    title = " ".join(title_parts)
    k, f = lines.fields("design frequency")
    freq = _num(f[0], k, "the design frequency", lines)
    if freq <= 0.0:
        # MMANA silently solves a 0.0 at its compiled-in 14.15 MHz and writes
        # that back (oracle sitting E12); the frequency is the model's, so a
        # file without one is refused rather than given a guess.
        raise lines.err(
            k,
            f"the design frequency is {f[0]} MHz; MMANA would silently use its "
            "built-in 14.15 MHz, and that is not this model's frequency -- set "
            "the model's frequency in MMANA and save it again",
        )

    # Wires.
    lines.header("Wires")
    k, f = lines.fields("wire count line")
    nw = _count(k, f, "wire", lines)
    if len(f) == 6:
        rows = _num(f[1], k, "the stack's first count", lines)
        cols = _num(f[2], k, "the stack's second count", lines)
        if rows * cols != 1:
            raise lines.err(
                k,
                f"the wire count line {', '.join(f)} is MMANA's Make Stack "
                f"setting: MMANA solves a {f[1]} x {f[2]} stack of these "
                f"{nw} wires. The stack dialog's spacing axes and placement "
                "are not yet mapped, so it is not built here -- and reading "
                "only the first field would model one antenna of the stack",
            )
    elif len(f) != 1:
        raise lines.err(
            k,
            f"the wire count line has {len(f)} fields ({', '.join(f)}); MMANA "
            "writes 1 (the count) or 6 (the count and a stack)",
        )
    if nw == 0:
        raise lines.err(k, "the model has no wires")
    wires = []
    for _ in range(nw):
        k, f = lines.fields("wire line")
        if len(f) != 8:
            raise lines.err(
                k,
                f"a wire line has 8 fields (X1 Y1 Z1 X2 Y2 Z2 R SEG), this one "
                f"{len(f)}",
            )
        v = [_num(t, k, "a wire field", lines) for t in f[:7]]
        seg = _int(f[7], k, "the wire's segmentation (SEG)", lines)
        wires.append(_Wire(tuple(v[0:3]), tuple(v[3:6]), v[6], seg, k))

    # Sources: count line `n, flag`. The flag is unidentified (no GUI change
    # moved it in the oracle sitting, and MMANA rewrites it on a plain save),
    # so it is read past.
    lines.header("Source")
    k, f = lines.fields("source count line")
    ns = _count(k, f, "source", lines)
    sources = []
    for _ in range(ns):
        k, f = lines.fields("source line")
        if len(f) != 3:
            raise lines.err(
                k,
                f"a source line has 3 fields (position, phase in degrees, "
                f"volts), this one {len(f)}",
            )
        sources.append(
            _Source(
                _pos(f[0], k, lines),
                _num(f[1], k, "the source's phase", lines),
                _num(f[2], k, "the source's voltage", lines),
                k,
            )
        )

    # Loads: count line `n, use-loads`.
    lines.header("Load")
    k, f = lines.fields("load count line")
    nl = _count(k, f, "load", lines)
    loads_on = True
    if len(f) >= 2:
        flag = _int(f[1], k, "the load switch (Use loads)", lines)
        if flag not in (0, 1):
            raise lines.err(
                k, f"the load switch (Use loads) is {flag}; MMANA writes 0 or 1"
            )
        loads_on = flag == 1
    loads = []
    for _ in range(nl):
        k, f = lines.fields("load line")
        if len(f) < 2:
            raise lines.err(k, "a load line needs a position and a type")
        pos = _pos(f[0], k, lines)
        kind = _int(f[1], k, "the load type", lines)
        want = {0: 5, 1: 4, 2: 12}.get(kind)
        if want is None:
            raise lines.err(
                k,
                f"load type {kind} is not one MMANA writes (0 = L/C/Q, "
                "1 = R+jX, 2 = Laplace)",
            )
        if len(f) != want:
            raise lines.err(
                k, f"a type {kind} load line has {want} fields, this one {len(f)}"
            )
        vals = tuple(_num(t, k, "a load value", lines) for t in f[2:])
        loads.append(_Load(pos, kind, vals, k))

    lines.header("Segmentation")
    k, f = lines.fields("segmentation line (DM1, DM2, SC, EC)")
    if len(f) != 4:
        raise lines.err(
            k,
            f"the segmentation line has 4 fields (DM1, DM2, SC, EC), this one {len(f)}",
        )
    dm1, dm2, sc, ec = (_num(t, k, "a segmentation field", lines) for t in f)
    seg_line = k

    lines.header("G/H/M/R/AzEl/X")
    k, f = lines.fields("ground line (G, H, M, R, Az, El, X)")
    if len(f) != 7:
        raise lines.err(
            k,
            f"the ground line has 7 fields (G, H, M, R, Az, El, X), this one "
            f"{len(f)} -- the line is incomplete",
        )
    g = _int(f[0], k, "the ground type (G)", lines)
    h = _num(f[1], k, "the added height (H)", lines)
    mat = _int(f[2], k, "the wire material (M)", lines)
    ref_z = _num(f[3], k, "the reference impedance (R)", lines)
    x = _num(f[6], k, "the ground line's last field (X)", lines)
    ground_line = k

    tapers = []
    nxt = lines.peek()
    if nxt is not None and nxt[1].startswith("$"):
        lines.take("taper wire set header")
        k, f = lines.fields("taper wire set count")
        nt = _count(k, f, "taper wire set", lines)
        for _ in range(nt):
            k, f = lines.fields("taper wire set row")
            if len(f) < 4 or len(f) % 2:
                raise lines.err(
                    k,
                    "a taper wire set row is the pointer, the type, then "
                    "(length, radius) pairs",
                )
            vals = [_num(t, k, "a taper wire set field", lines) for t in f]
            secs = tuple(zip(vals[2::2], vals[3::2], strict=True))
            tapers.append(_Taper(vals[0], int(vals[1]), secs, k))
    nxt = lines.peek()
    if nxt is not None and not nxt[1].startswith("#"):
        raise lines.err(
            nxt[0],
            f"unexpected line after the ground line: {nxt[1][:40]!r} (only the "
            "taper wire set and the comment follow it)",
        )

    # The fields that are read but cannot be modelled, by name.
    if g not in _GROUNDS:
        raise lines.err(
            ground_line, f"the ground type (G) is {g}; MMANA writes 0, 1 or 2"
        )
    if mat in _MATERIALS_REFUSED:
        what, why = _MATERIALS_REFUSED[mat]
        raise lines.err(
            ground_line, f"the wire material (M = {mat}) is MMANA's {what}: {why}"
        )
    if mat not in _MATERIALS:
        raise lines.err(
            ground_line,
            f"the wire material (M) is {mat}; MMANA's list runs 0 to 7",
        )
    if x != 0.0:
        raise lines.err(
            ground_line,
            f"the ground line's last field (X) is {f[6]}; every MMANA file seen "
            "writes 0, and what a non-zero value means is not settled",
        )
    if not (dm1 > 0 and dm2 > 0 and ec >= 1 and sc >= 1):
        raise lines.err(
            seg_line,
            f"the segmentation line ({dm1:g}, {dm2:g}, {sc:g}, {ec:g}) needs "
            "DM1 > 0, DM2 > 0, SC >= 1 and EC >= 1",
        )
    return _MaaFile(
        title=title,
        freq_mhz=freq,
        wires=tuple(wires),
        sources=tuple(sources),
        loads=tuple(loads),
        loads_on=loads_on,
        dm1=dm1,
        dm2=dm2,
        sc=sc,
        ec=ec,
        ground=g,
        height=h,
        material=mat,
        ref_z=ref_z,
        tapers=tuple(tapers),
    )


# --------------------------------------------------------------------------
# The mesh
# --------------------------------------------------------------------------


def _auto_mesh(length: float, lam: float, seg: int, f: _MaaFile, radius: float):
    """The segment lengths of one automatically meshed wire (SEG <= 0).

    MMANA's mesher is its own and is not emulated. Its parameters are read
    for what they say:

    * SEG = 0, regular: equal segments no longer than lambda / DM2.
    * SEG = -1 / -2 / -3, tapered at both ends / the start / the end: at each
      tapered end the segments start at lambda / (DM1 * EC) and grow by the
      factor SC per segment until they reach lambda / DM2, which is the
      segment length over the rest of the wire. A both-ends wire is meshed
      symmetrically, with an even count in the middle, so its centre is
      always a segment end (a pulse) -- where ``w<n>c`` puts its port.

    The help states the taper in two inconsistent forms (lambda / (DM1 * EC)
    to lambda / (SC * DM2), and lambda / (SC * DM1) to lambda / DM2); this
    takes the finer end of the first and the coarser end of the second.

    No segment is shorter than two radii: below that no thin-wire kernel
    here is valid (NEC's own limit for its extended kernel)."""
    floor = 2.0 * radius
    dmax = max(lam / f.dm2, floor)
    if seg == 0:
        n = math.ceil(length / dmax - 1e-9)
        if n > _HARD_SEGMENT_CAP:
            raise _Refusal(f"would take {n} segments")
        n = max(1, n)
        return [length / n] * n
    dmin = max(lam / (f.dm1 * f.ec), floor)
    run = []
    s = dmin
    while s < dmax * (1 - 1e-12):
        run.append(s)
        if len(run) > _HARD_SEGMENT_CAP:
            raise _Refusal("its taper would take too many segments")
        s *= f.sc
        if f.sc == 1.0:
            break
    ends = 2 if seg == -1 else 1
    while run and ends * sum(run) > length * (1 + 1e-12):
        run.pop()
    middle = length - ends * sum(run)
    n_mid = math.ceil(middle / dmax - 1e-9) if middle > length * 1e-9 else 0
    if n_mid > _HARD_SEGMENT_CAP:
        raise _Refusal(f"would take {n_mid} segments")
    if seg == -1:
        if n_mid % 2:
            n_mid += 1
        if n_mid == 0 and not run:
            n_mid = 2
    elif n_mid == 0 and not run:
        n_mid = 1
    mid = [middle / n_mid] * n_mid if n_mid else []
    if seg == -1:
        return [*run, *mid, *reversed(run)]
    if seg == -2:
        return [*run, *mid]
    return [*mid, *reversed(run)]


@dataclass
class _Piece:
    """One MMANA wire after its taper sections and mesh: knot fractions
    along the WHOLE wire (0 .. 1) and each segment's radius."""

    knots: list[float]
    radii: list[float]
    manual: int | None  # the manual count, when SEG > 0


def _sections(w: _Wire, length: float, tapers: dict, line_err):
    """``[(t0, t1, radius)]``: the wire's radius sections along it, as
    fractions. A plain wire is one section; a negative R points into the
    taper wire set (``$$$`` rows ``pointer, type, L0, R0, L1, R1, ...,
    99999.9, Rlast``). Type 0 (``<>``) is symmetric about the centre with L0
    the WHOLE centre section and each later L a section on each side; type 1
    (``->``) runs from the wire's start. Types 2 and 3 are refused: what
    their ``*`` changes is not settled."""
    if w.radius > 0:
        return [(0.0, 1.0, w.radius)]
    if w.radius == 0:
        raise line_err(
            w.line,
            "this wire has radius 0, MMANA's insulator wire (it joins wires "
            "without electrical contact), which nothing here models",
        )
    row = tapers.get(w.radius)
    if row is None:
        raise line_err(
            w.line,
            f"this wire's radius {w.radius:g} points into the taper wire set, "
            "which has no row for it",
        )
    secs = list(row.sections)
    if row.kind not in (0, 1):
        raise line_err(
            row.line,
            f"taper wire set type {row.kind} (MMANA's starred <>* / ->* forms) "
            "is not read here: what the star changes is not yet settled",
        )
    if any(r <= 0 for _, r in secs) or any(ln <= 0 for ln, _ in secs):
        raise line_err(
            row.line, "a taper wire set section has a non-positive length or radius"
        )
    if row.kind == 1:
        out, at = [], 0.0
        for ln, r in secs:
            t1 = min(1.0, at + ln / length)
            if t1 > at:
                out.append((at, t1, r))
            at = t1
            if at >= 1.0:
                break
        if at < 1.0:
            out[-1] = (out[-1][0], 1.0, out[-1][2])
        return out
    # Type 0: symmetric. The centre section first, then outward.
    half = 0.5
    bounds = []  # (half-width fraction reached, radius)
    reach = min(half, 0.5 * secs[0][0] / length)
    bounds.append((reach, secs[0][1]))
    for ln, r in secs[1:]:
        if reach >= half:
            break
        reach = min(half, reach + ln / length)
        bounds.append((reach, r))
    if bounds[-1][0] < half:
        bounds[-1] = (half, bounds[-1][1])
    out = []
    inner = 0.0
    right = []
    for reach, r in bounds:
        right.append((0.5 + inner, 0.5 + reach, r))
        inner = reach
    left = [(1.0 - b, 1.0 - a, r) for a, b, r in reversed(right)]
    # The centre section spans both sides as one.
    centre = (left[-1][0], right[0][1], right[0][2])
    out = [*left[:-1], centre, *right[1:]]
    return [s for s in out if s[1] - s[0] > _SAME_T]


def _mesh_wire(w: _Wire, f: _MaaFile, lam: float, tapers: dict, line_err) -> _Piece:
    length = math.dist(w.p1, w.p2)
    if length <= 0.0:
        raise line_err(w.line, "this wire has zero length")
    if w.seg < -3:
        raise line_err(
            w.line,
            f"SEG is {w.seg}; MMANA writes -1, -2 or -3 (tapered), 0 (regular) "
            "or a manual segment count",
        )
    secs = _sections(w, length, tapers, line_err)
    if w.seg > 0:
        if len(secs) > 1:
            raise line_err(
                w.line,
                f"a manual segment count ({w.seg}) on a stepped-radius taper "
                "wire: how MMANA shares it among the sections is not settled",
            )
        if w.seg > _HARD_SEGMENT_CAP:
            raise line_err(w.line, f"SEG asks for {w.seg} segments")
        n = w.seg
        return _Piece([k / n for k in range(n + 1)], [secs[0][2]] * n, n)
    knots, radii = [0.0], []
    for t0, t1, r in secs:
        try:
            lens = _auto_mesh((t1 - t0) * length, lam, w.seg, f, r)
        except _Refusal as e:
            raise line_err(w.line, f"this wire {e}") from None
        span = sum(lens)
        at = t0
        for k, ln in enumerate(lens):
            at = t1 if k == len(lens) - 1 else at + (t1 - t0) * ln / span
            knots.append(at)
            radii.append(r)
    return _Piece(knots, radii, None)


# --------------------------------------------------------------------------
# The import
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MaaImport:
    """A ``.maa`` read as a deck: the `NecDeck` the file designs build from,
    the frequency and reference impedance it names, its ground in the CLI's
    ``--ground`` shape, the notes the app shows, and the NEC-5 card text the
    deck was parsed from (`nec_text`, kept for reading and tests)."""

    deck: NecDeck
    freq_mhz: float
    ref_z: float | None
    ground: object
    notes: tuple[str, ...]
    nec_text: str
    title: str
    # The ground as the file spells it, for the app's ground panel.
    ground_word: str = ""


def _fmt(v: float) -> str:
    r = repr(float(v))
    return "0" if r in ("0.0", "-0.0") else r


def read_maa(
    text: str, *, name: str = "MMANA model", limits: GeometryLimits | None = None
) -> MaaImport:
    """Read the text of an MMANA-GAL ``.maa`` model (see the module
    docstring) into a `MaaImport`. Raises ``ValueError`` naming the file, the
    line and the field for anything malformed or anything the file asks for
    that cannot be modelled. ``limits`` bounds the structure, in MMANA's own
    wires and the expanded mesh's segments, before the deck is built."""
    f = _parse(text, name)

    def line_err(line, msg):
        return ValueError(f"{name} line {line}: {msg}" if line else f"{name}: {msg}")

    lam = C_LIGHT_MHZ_M / f.freq_mhz
    h = f.height
    tapers = {t.pointer: t for t in f.tapers}
    if limits is not None and len(f.wires) > limits.max_wires:
        raise line_err(
            None,
            f"this model has {len(f.wires)} wires (the limit is "
            f"{limits.max_wires})" + (f"; {limits.note}" if limits.note else ""),
        )

    # Geometry: H is added to every z (the help's "add height"). MMANA's own
    # 20 m dipole (DP20, G = 0, H = 20) lies at z = 0 in the file and solves
    # over perfect ground as a dipole 20 m up, so H is geometry.
    wires = [
        replace(
            w,
            p1=(w.p1[0], w.p1[1], w.p1[2] + h),
            p2=(w.p2[0], w.p2[1], w.p2[2] + h),
        )
        for w in f.wires
    ]
    grounded = f.ground != 0
    # Ends closer than this are one point; a z this close to 0 is on the
    # ground (H added to a file's z = -H need not cancel to the last bit).
    extent = max((abs(c) for w in wires for c in (*w.p1, *w.p2)), default=1.0) or 1.0
    tol = 1e-6 * extent
    if grounded:

        def flat(p):
            return (p[0], p[1], 0.0) if abs(p[2]) <= tol else p

        wires = [replace(w, p1=flat(w.p1), p2=flat(w.p2)) for w in wires]
        for w in wires:
            if min(w.p1[2], w.p2[2]) < 0.0:
                raise line_err(
                    w.line,
                    "this wire goes below the ground (z + H < 0); MMANA's "
                    "ground models nothing buried",
                )

    pieces = [_mesh_wire(w, f, lam, tapers, line_err) for w in wires]
    total = sum(len(p.radii) for p in pieces)
    if limits is not None and total > limits.max_segments:
        raise line_err(
            None,
            f"this model meshes to {total} segments (the limit is "
            f"{limits.max_segments})" + (f"; {limits.note}" if limits.note else ""),
        )

    # Shared ends: one coordinate per junction (MMANA joins wires where their
    # ends coincide), matched to `tol`, well inside any real gap.
    nodes: list[tuple[float, float, float]] = []
    ends: dict[tuple[int, int], int] = {}
    for i, w in enumerate(wires):
        for e, p in ((0, w.p1), (1, w.p2)):
            for k, q in enumerate(nodes):
                if math.dist(p, q) <= tol:
                    ends[(i, e)] = k
                    break
            else:
                ends[(i, e)] = len(nodes)
                nodes.append(p)
    degree: dict[int, int] = {}
    for k in ends.values():
        degree[k] = degree.get(k, 0) + 1
    # A wire end on another wire's INTERIOR: MMANA joins wires only at their
    # ends, and a mesh here could put a segment end on that very point and
    # join them, so the two programs would disagree. Refused, by name.
    for i, w in enumerate(wires):
        for j, v in enumerate(wires):
            if i == j:
                continue
            d = [b - a for a, b in zip(v.p1, v.p2, strict=True)]
            ln2 = sum(c * c for c in d)
            for e, p in ((0, w.p1), (1, w.p2)):
                t = sum((p[k] - v.p1[k]) * d[k] for k in range(3)) / ln2
                if not (1e-9 < t < 1 - 1e-9):
                    continue
                q = tuple(v.p1[k] + t * d[k] for k in range(3))
                if math.dist(p, q) <= tol:
                    raise line_err(
                        w.line,
                        f"wire {i + 1}'s {'start' if e == 0 else 'end'} lies on "
                        f"wire {j + 1} between its ends; MMANA joins wires only "
                        f"at their ends -- split wire {j + 1} there",
                    )
    # Two wires crossing between their ends: MMANA does not join them there
    # (its own library has such crossovers, e.g. DL2KQ's multi-turn loops),
    # so it solves two wires at zero spacing; a mesh here would join them
    # wherever both put a segment end on the crossing. Neither is the
    # antenna, so the model is refused by name.
    for i, w in enumerate(wires):
        u = [b - a for a, b in zip(w.p1, w.p2, strict=True)]
        for j in range(i + 1, len(wires)):
            v = wires[j]
            vv = [b - a for a, b in zip(v.p1, v.p2, strict=True)]
            r = [a - b for a, b in zip(w.p1, v.p1, strict=True)]
            a_ = sum(c * c for c in u)
            b_ = sum(x * y for x, y in zip(u, vv, strict=True))
            c_ = sum(c * c for c in vv)
            d_ = sum(x * y for x, y in zip(u, r, strict=True))
            e_ = sum(x * y for x, y in zip(vv, r, strict=True))
            den = a_ * c_ - b_ * b_
            if den <= 1e-12 * a_ * c_:
                continue  # parallel: an overlap puts an end inside, above
            sp = (b_ * e_ - c_ * d_) / den
            tq = (a_ * e_ - b_ * d_) / den
            if not (1e-9 < sp < 1 - 1e-9 and 1e-9 < tq < 1 - 1e-9):
                continue
            pp = [w.p1[k] + sp * u[k] for k in range(3)]
            qq = [v.p1[k] + tq * vv[k] for k in range(3)]
            if math.dist(pp, qq) <= tol:
                raise line_err(
                    w.line,
                    f"wires {i + 1} and {j + 1} cross between their ends. MMANA "
                    "does not join wires there, so it solves two wires passing "
                    "through each other at zero spacing, which no wire model "
                    "here solves faithfully. Split both there to join them, or "
                    "move one a few radii off the other (an insulated "
                    "crossover)",
                )

    def on_ground(i, e):
        return grounded and nodes[ends[(i, e)]][2] == 0.0

    notes: list[str] = []
    cut_notes: list[str] = []
    cut_wires: set[int] = set()

    def resolve(pos: _Pos, line: int, what: str) -> tuple[int, int]:
        """``(wire index, knot)`` for a position, cutting the wire at an
        exact centre that is not on the mesh."""
        if not 1 <= pos.wire <= len(wires):
            raise line_err(
                line,
                f"{what} {pos.text} names wire {pos.wire}; the model has "
                f"{len(wires)} wires",
            )
        i = pos.wire - 1
        pc = pieces[i]
        n = len(pc.radii)
        if pos.offset and pc.manual is None:
            raise line_err(
                line,
                f"{what} {pos.text} is {abs(pos.offset)} pulse"
                f"{'s' if abs(pos.offset) != 1 else ''} from the wire's "
                f"{_ANCHOR_WORD[pos.anchor]} on an automatically segmented wire "
                f"(SEG {wires[i].seg}): where that pulse is depends on MMANA's "
                "own mesh, which is not emulated here. Give the wire a manual "
                "segment count in MMANA to place it",
            )
        if pos.anchor == "b":
            knot = pos.offset
        elif pos.anchor == "e":
            knot = n - pos.offset
        else:
            mid = next(
                (k for k, t in enumerate(pc.knots) if abs(t - 0.5) <= _SAME_T), None
            )
            if mid is None or (pos.offset and i in cut_wires):
                if pos.offset:
                    raise line_err(
                        line,
                        f"{what} {pos.text} counts pulses from the centre of a "
                        f"wire with an odd segment count ({n}), which has no "
                        "pulse at its centre; which pulse MMANA takes as the "
                        "centre there is not settled",
                    )
                # Cut, never snap: the wire gets a segment end at its centre.
                k = next(k for k, t in enumerate(pc.knots) if t > 0.5)
                pc.knots.insert(k, 0.5)
                pc.radii.insert(k, pc.radii[k - 1])
                cut_wires.add(i)
                cut_notes.append(
                    f"{pos.text}: wire {pos.wire} has no segment end at its "
                    "centre, so it is cut there"
                )
                mid = k
            knot = mid + pos.offset
        n = len(pc.radii)
        if not 0 <= knot <= n:
            raise line_err(
                line,
                f"{what} {pos.text} is off wire {pos.wire}, which has {n} segments",
            )
        if knot in (0, n):
            e = 0 if knot == 0 else 1
            node = ends[(i, e)]
            if degree[node] < 2 and not on_ground(i, e):
                raw_z = (f.wires[i].p1 if e == 0 else f.wires[i].p2)[2]
                if grounded and raw_z == 0.0 and h != 0.0:
                    why = (
                        f" It is at z = 0 in the file, but the added height "
                        f"H = {h:g} m lifts it off the ground; whether MMANA "
                        "still puts a pulse there is not settled"
                    )
                elif not grounded and raw_z == 0.0:
                    why = (
                        " It is at z = 0, where MMANA puts a pulse over a "
                        "ground; what it does there in free space (G = 0) is "
                        "not settled"
                    )
                else:
                    why = ""
                raise line_err(
                    line,
                    f"{what} {pos.text} is at a free wire end (wire {pos.wire}'s "
                    f"{'start' if e == 0 else 'end'} joins no other wire and "
                    "is not on the ground), where MININEC has no pulse." + why,
                )
            if on_ground(i, e) and h != 0.0:
                raise line_err(
                    line,
                    f"{what} {pos.text} is where wire {pos.wire} meets the "
                    f"ground at z + H = 0, with the added height H = {h:g} m; "
                    "whether MMANA puts a pulse there (z = 0 in the file, or "
                    "z + H = 0) is not settled",
                )
        return i, knot

    # Sources.
    if not f.sources:
        raise line_err(None, "the model has no source")
    feeds = []
    for s in f.sources:
        if s.volts == 0.0:
            raise line_err(
                s.line,
                f"the source at {s.pos.text} has zero volts, which drives nothing",
            )
        at = resolve(s.pos, s.line, "source")
        feeds.append((at, cmath.rect(s.volts, math.radians(s.phase_deg)), s))
    seen = {}
    for at, _v, s in feeds:
        if at in seen:
            raise line_err(
                s.line,
                f"two sources ({seen[at]} and {s.pos.text}) are on one pulse",
            )
        seen[at] = s.pos.text

    # Loads.
    ld_cards = []  # (at, card mnemonic fields)
    q_notes = []
    omega0 = 2.0 * math.pi * f.freq_mhz * 1e6
    if f.loads and not f.loads_on:
        notes.append(
            f"The file's {len(f.loads)} load{'s are' if len(f.loads) != 1 else ' is'} "
            "switched off (MMANA's Use loads is unticked), so "
            f"{'they are' if len(f.loads) != 1 else 'it is'} not applied."
        )
    for ld in f.loads if f.loads_on else ():
        if ld.kind == 2:
            raise line_err(
                ld.line,
                f"the load at {ld.pos.text} is MMANA's Laplace (S) form, a "
                "rational impedance Z(s) that no element here spells",
            )
        at = resolve(ld.pos, ld.line, "load")
        if ld.kind == 1:
            r, x = ld.values
            if r < 0:
                raise line_err(
                    ld.line, f"the load at {ld.pos.text} has a negative resistance"
                )
            if r == 0 and x == 0:
                continue
            ld_cards.append((at, 4, r, x, 0.0, ld.pos.text))
            continue
        l_uh, c_pf, q = ld.values
        if l_uh < 0 or c_pf < 0 or q < 0:
            raise line_err(
                ld.line,
                f"the load at {ld.pos.text} has a negative L, C or Q",
            )
        lh, cf = l_uh * 1e-6, c_pf * 1e-12
        if lh == 0 and cf == 0:
            continue
        if lh and cf:
            # A parallel L||C trap. Q is the coil's: 4nec2's LD 6 reading,
            # a parallel loss R = Q * w0 * L at the file's frequency.
            rp = q * omega0 * lh if q else 0.0
            ld_cards.append((at, 1, rp, lh, cf, ld.pos.text))
            if q:
                q_notes.append(f"{ld.pos.text} (trap, {rp:.4g} ohm in parallel)")
        elif lh:
            rs = omega0 * lh / q if q else 0.0
            ld_cards.append((at, 0, rs, lh, 0.0, ld.pos.text))
            if q:
                q_notes.append(f"{ld.pos.text} (coil, {rs:.4g} ohm in series)")
        else:
            rs = 1.0 / (omega0 * cf * q) if q else 0.0
            ld_cards.append((at, 0, rs, 0.0, cf, ld.pos.text))
            if q:
                q_notes.append(f"{ld.pos.text} (capacitor, {rs:.4g} ohm in series)")

    # Objects on DIFFERENT wires' ends at one junction of three or more wire
    # ends. Each is a series gap at its own wire's end, which is what MMANA's
    # position names; the port model here serves one gap per junction
    # (AK#1886), so the model is refused rather than half-built.
    at_node: dict[int, dict[int, list[str]]] = {}
    for at, text_ in [(at, s.pos.text) for at, _v, s in feeds] + [
        (at, pos) for at, *_rest, pos in ld_cards
    ]:
        i, knot = at
        n = len(pieces[i].radii)
        if knot in (0, n):
            node = ends[(i, 0 if knot == 0 else 1)]
            at_node.setdefault(node, {}).setdefault(i, []).append(text_)
    for node, by_wire in at_node.items():
        if len(by_wire) > 1 and degree[node] >= 3:
            named = " and ".join(p for ps in by_wire.values() for p in ps)
            raise line_err(
                None,
                f"{named} sit at one junction of {degree[node]} wire ends, each "
                "at its own wire's end: that is a series gap in each of those "
                "wires, and this route serves one gap per junction (AK#1886). "
                "Put them on one wire's end there, or move one of them along "
                "its wire",
            )

    # Panels: one GW per run of equal segments of one radius, so every knot
    # a port lands on is a segment end of some GW. `seg_card` maps a wire's
    # 1-based segment to its (tag, segment) on the panels.
    gw_lines = []
    seg_card: dict[tuple[int, int], tuple[int, int]] = {}
    tag = 0

    def pt(i, t):
        if t == 0.0:
            return nodes[ends[(i, 0)]]
        if t == 1.0:
            return nodes[ends[(i, 1)]]
        w = wires[i]
        return tuple(a + (b - a) * t for a, b in zip(w.p1, w.p2, strict=True))

    for i, pc in enumerate(pieces):
        ks = pc.knots
        n = len(pc.radii)
        start = 0
        while start < n:
            stop = start + 1
            seg_len = ks[start + 1] - ks[start]
            while (
                stop < n
                and pc.radii[stop] == pc.radii[start]
                and abs((ks[stop + 1] - ks[stop]) - seg_len) <= 1e-9 * seg_len
            ):
                stop += 1
            tag += 1
            a, b = pt(i, ks[start]), pt(i, ks[stop])
            gw_lines.append(
                f"GW {tag} {stop - start} "
                + " ".join(_fmt(c) for c in (*a, *b))
                + f" {_fmt(pc.radii[start])}"
            )
            for k in range(start + 1, stop + 1):
                seg_card[(i, k)] = (tag, k - start)
            start = stop

    # Which side of its knot each port is spelled from: the end of the
    # segment BEFORE it (NEC-5's I4 = 2), or the start of the one after
    # (I4 = 1). The port model hosts one port per wire piece end, so two
    # ports on the two ends of one segment must not both ride that segment:
    # a port on knot 0 can only be spelled from segment 1, and the knot after
    # a knot spelled that way is spelled from its own segment after, too.
    claimed: dict[int, set[int]] = {}
    for at, *_ in [*feeds, *ld_cards]:
        claimed.setdefault(at[0], set()).add(at[1])
    side: dict[tuple[int, int], int] = {}
    for i, ks in claimed.items():
        n = len(pieces[i].radii)
        after = False
        prev = None
        for k in sorted(ks):
            after = k == 0 or (after and prev == k - 1 and k < n)
            side[(i, k)] = 1 if after else 2
            prev = k

    def addr(at):
        i, k = at
        if side[at] == 1:
            return (*seg_card[(i, k + 1)], 1)
        return (*seg_card[(i, k)], 2)

    cards = [f"CM {f.title}" if f.title else "CM MMANA-GAL model", "CM NEC-5", "CE"]
    cards += gw_lines
    cards.append(f"GE {1 if grounded else 0}")
    soil = None
    if f.ground == 1:
        cards.append("GN 1")
    elif f.ground == 2:
        soil = MAA_DEFAULT_SOIL
        cards.append(f"GD 0 0 0 0 {_fmt(soil[0])} {_fmt(soil[1])}")
    sigma = _MATERIALS[f.material][1]
    if sigma is not None:
        cards.append(f"LD 5 0 0 0 {_fmt(sigma)}")
    for at, typ, a, b, c, _pos_text in ld_cards:
        t, seg, end = addr(at)
        cards.append(f"LD {typ} {t} {seg} {end} {_fmt(a)} {_fmt(b)} {_fmt(c)}")
    for at, v, _s in feeds:
        t, seg, end = addr(at)
        cards.append(f"EX 0 {t} {seg} {end} {_fmt(v.real)} {_fmt(v.imag)}")
    cards.append(f"FR 0 1 0 0 {_fmt(f.freq_mhz)} 0")
    cards.append("EN")
    nec_text = "\n".join(cards) + "\n"

    deck_limits = None
    if limits is not None:
        # MMANA's wires were bounded above; the panels are this import's own
        # spelling of their mesh, bounded by the segment total.
        deck_limits = GeometryLimits(
            max_segments=limits.max_segments,
            max_wires=max(limits.max_segments, limits.max_wires),
            note=limits.note,
        )
    try:
        deck = parse_nec(
            nec_text, name=name, network=True, limits=deck_limits, dialect="nec5"
        )
        # Built once here, so a model the port model cannot host is refused
        # when it opens, not at its first solve.
        deck.wire_tuples(specs=True)
        deck.network()
    except ValueError as e:
        raise ValueError(
            f"{name}: this model's sources and loads cannot be placed here: {e}"
        ) from None
    # Read as MMANA: NEC-5's knot addressing, but not NEC-5's kernel default.
    deck = replace(
        deck,
        dialect="maa",
        dialect_reason="an MMANA-GAL .maa model",
        dialect_detected="maa",
        dialect_detected_reason="an MMANA-GAL .maa model",
        dialect_chosen=None,
    )

    # The notes, the dialect first.
    seg_word = {
        -1: "tapered at both ends",
        -2: "tapered at the start",
        -3: "tapered at the end",
        0: "regular",
    }
    auto = sorted({w.seg for w in wires if w.seg <= 0})
    n_auto = sum(1 for w in wires if w.seg <= 0)
    manual = len(wires) - n_auto
    parts = []
    if auto:
        parts.append(
            f"{n_auto} wire{'s' if n_auto != 1 else ''} MMANA meshes itself "
            f"({', '.join(seg_word[s] for s in auto)}) "
            f"{'are' if n_auto != 1 else 'is'} meshed here from the file's own "
            f"DM1, DM2, SC, EC ({f.dm1:g}, {f.dm2:g}, {f.sc:g}, {f.ec:g}) at "
            f"{f.freq_mhz:g} MHz: segments of {_len_word(lam / (f.dm1 * f.ec))} "
            f"(lambda/(DM1*EC)) at a tapered end, growing x{f.sc:g} per segment "
            f"to at most {_len_word(lam / f.dm2)} (lambda/DM2), and never "
            "shorter than two radii"
        )
    if manual:
        parts.append(
            f"{manual} wire{'s keep their' if manual != 1 else ' keeps its'} "
            "manual segment count"
        )
    mesh = (
        "MMANA's automatic segmentation is not emulated: "
        + "; ".join(parts)
        + f". {len(wires)} MMANA wire{'s' if len(wires) != 1 else ''}, "
        f"{sum(len(p.radii) for p in pieces)} segments."
    )
    head = (
        "Read as MMANA-GAL (MININEC): sources and loads sit at pulses, between "
        "two segments, so each is a port at a segment end here. MMANA's own "
        "numbers come from MININEC on its own mesh, so expect this solve's Z "
        "to differ from MMANA's by a few percent."
    )
    out = [head, mesh]
    if cut_notes:
        out.append("Cut, not snapped: " + "; ".join(cut_notes) + ".")
    if f.ground == 0:
        gnote = "Free space (G = 0)."
    elif f.ground == 1:
        gnote = "Perfect ground (G = 1)."
    else:
        gnote = (
            "Real ground (G = 2) is MMANA's MININEC type: perfect ground for the "
            "currents, the soil in the pattern only. The .maa does not carry "
            "MMANA's soil (MMANA keeps it in its own settings), so "
            f"eps_r {soil[0]:g}, sigma {soil[1]:g} S/m is assumed; set yours in "
            "the ground panel."
        )
    if h:
        gnote += f" The added height H = {h:g} m is added to every z."
    out.append(gnote)
    mname, msig = _MATERIALS[f.material]
    out.append(
        f"Wire material (M = {f.material}): {mname}"
        + (f", sigma {msig:g} S/m." if msig else ".")
    )
    if q_notes:
        out.append(
            "A load's Q is taken as its coil's (a capacitor's when it has no "
            "coil) and becomes a loss resistance held at the file's "
            f"{f.freq_mhz:g} MHz: " + "; ".join(q_notes) + "."
        )
    out.extend(notes)
    return MaaImport(
        deck=deck,
        freq_mhz=f.freq_mhz,
        ref_z=f.ref_z if f.ref_z > 0 else None,
        ground=(
            None
            if f.ground == 0
            else "pec"
            if f.ground == 1
            else ("mininec", soil[0], soil[1])
        ),
        notes=tuple(out),
        nec_text=nec_text,
        title=f.title,
        ground_word=(
            f"MMANA G = {f.ground}" + (", soil assumed" if f.ground == 2 else "")
        ),
    )


_ANCHOR_WORD = {"b": "start", "c": "centre", "e": "end"}


def _len_word(m: float) -> str:
    if m >= 1.0:
        return f"{m:.3g} m"
    if m >= 0.01:
        return f"{m * 100:.3g} cm"
    return f"{m * 1000:.3g} mm"
