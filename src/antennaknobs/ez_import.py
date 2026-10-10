"""Import an EZNEC model (``.ez``) as a NEC deck (AK#1958).

An ``.ez`` is EZNEC's saved model: a binary file of fixed-size records (the
model header, then one record per table row -- media, wires, sources, loads
and transmission lines share each record -- then two fixed records) followed
by optional typed blocks for the later features (insulation, per-wire loss,
line loss, transformers, Y-parameter and L networks, virtual segments, ...).
`read_ez` turns one into the same :class:`~antennaknobs.nec_import.NecDeck`
a ``.nec`` deck becomes, so an ``.ez`` opens wherever a deck does: the CLI's
``@file``, the designs folder, the workbench's Open....

The layout follows the format description EZNEC's author publishes for
writers of ``.ez`` files (version 7.0), read with the census of real files
recorded on AK#1958. This module is a reader written from that description;
it carries none of the description's text.

**What is refused, and how.** Four kinds of refusal are kept apart, each a
``ValueError`` subclass of `EzRefusal` naming the file, the field and the value:

* `EzUnknownFormat` -- a file version, block type or block revision the
  format description does not define. The format is still moving, so these
  are refused by name rather than guessed at, in every mode. The one decided
  exception: the info block's revision 1 (written by EZNEC 5 and 6, absent
  from the description) is accepted, and its contents -- provenance only, no
  model data -- are skipped. A negative (custom) block type is skipped by its
  length, as the description says a reader should.
* `EzUndefined` -- a reading the description leaves undefined (a trap's
  topology, the law a frequency-variable resistance follows, a Laplace load's
  variable, where a split source sits, ...). Refused by default. Where a
  reading has been checked against real files it can be taken on purpose,
  with ``accept_guesses=True`` (``ANTENNAKNOBS_EZ_ACCEPT_GUESSES=1`` for the
  CLI and the app); every reading taken is listed in the import's notes.
* `EzNotRepresentable` -- something the model here has no element for: a
  second ground medium, NEC radials, an active plane-wave source, a lossy
  wire insulation, a magnetic wire.
* `EzMalformed` -- a file that contradicts itself (counts, lengths, an
  integrity word that is not EZNEC's).

A field that only changes what EZNEC DISPLAYS (plot ranges, units, the
near-field request) and holds a value outside its set is a warning in the
notes, not a refusal.

**How the model maps.**

* Wires keep EZNEC's own segment counts; the stored diameter halves to the
  radius. Values are rounded to the seven significant digits EZNEC prints,
  which is what its own ``.nec`` export carries, so a model opens here as
  its export does.
* A position (% from end 1) lands on segment ``ceil(p·N/100)`` (at least 1),
  as EZNEC's export writes it. EZNEC's own calculating engines (its NEC-2
  and NEC-4 cores) put sources and loads at segment CENTRES, so the deck is
  read in NEC-2's spelling -- unless the file says EZNEC was set to the
  external NEC-5 engine, which connects at segment ENDS, and the deck is then
  read in NEC-5's spelling (a 0 % load or line end at the wire's end).
* Sources: RMS magnitudes (×√2 into the deck, as EZNEC's export writes);
  voltage sources drive volts, current sources force amps.
* Loads keep their type, so a frequency sweep evaluates each at every
  frequency instead of at the model frequency only: R + jX is a fixed
  impedance, series and parallel RLC are the frequency-dependent ``Load``
  (zero is a missing part, as the description says), and the readings that
  need ``accept_guesses`` -- a trap, a frequency-variable R, a Laplace load
  -- are evaluated per frequency from their own formula.
* Transmission lines: lossless lines are ``TL`` with their reversal (a
  crossed line), length and velocity factor; a stub end becomes the line
  into an open or a short, so it also follows frequency. A lossy line is the
  two-port EZNEC's export writes at the model frequency, which the app flags
  away from it (the law its loss follows with frequency is undefined); with
  ``accept_guesses`` it follows ``loss ∝ √f`` from its loss frequency.
* Transformers are EZNEC's own two-port (an ideal ratio behind a small
  series resistance); Y-parameter networks are their fixed admittances; L
  networks are their two branches -- fixed R + jX, or R/L/C parts that
  follow frequency. A zero branch resistance is 1 mΩ, as EZNEC's export
  writes it.
* Wire loss: the per-wire block when present, else the model-wide
  resistivity. Insulation becomes the wire's jacket (outer radius and
  permittivity); a jacket with dielectric loss is refused.
* Ground: free space, perfect, or real with EZNEC's high-accuracy
  (Sommerfeld) or MININEC-type analysis, from the first medium.
* Virtual segments: EZNEC stores them as one extra wire and its own export
  rebuilds that wire 100 λ away, which the NEC reader then reads as circuit
  nodes. This import does the same. (A first-class virtual feed node, which
  would make the far wire unnecessary, is AK#1966.)
"""

from __future__ import annotations

import cmath
import datetime
import math
import os
import struct
from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np

from . import network as _net
from .nec_import import GeometryLimitError, GeometryLimits, NecDeck, parse_nec

__all__ = [
    "ACCEPT_GUESSES_ENV",
    "EzImport",
    "EzMalformed",
    "EzNotRepresentable",
    "EzRefusal",
    "EzUndefined",
    "EzUnknownFormat",
    "accept_guesses_from_env",
    "decode_ez",
    "ez_source_view",
    "read_ez",
]

#: Set to 1 to take the readings the format leaves undefined (see the module
#: docstring). Read by the file loaders, so the CLI and the app honour it.
ACCEPT_GUESSES_ENV = "ANTENNAKNOBS_EZ_ACCEPT_GUESSES"

HEADER_BYTES = 170  # the model header is 170 bytes; the red control moves it
RECORD_BYTES = 170
_CHECK_WORD = 1304
_C0 = 299_792_458.0
_SQRT2 = math.sqrt(2.0)
# EZNEC's export spells a zero branch resistance in an L network as 1 mΩ.
_LNET_ZERO_R = 1e-3

# The writing program's version code (an i16 in the header). The values the
# census found with a layout the description accounts for, and the value the
# description tells other writers to use.
_KNOWN_VERCODES = frozenset({51, 50, 49, 48, 46, 45, 31, 30})
_PGM_VERCODE_OTHER_WRITER = 62_000_000

# Block type -> (name, revisions this reader knows).
_BLOCKS = {
    11: ("frequency sweep", frozenset({1})),
    12: ("wire insulation", frozenset({1})),
    13: ("wire loss", frozenset({1})),
    14: ("transmission-line loss", frozenset({1})),
    15: ("transformer", frozenset({1})),
    16: ("Y-parameter network", frozenset({1})),
    17: ("L network", frozenset({2})),
    18: ("virtual segment", frozenset({1})),
    31: ("plane-wave source", frozenset({1})),
    # Revision 1 is not in the description; accepted with its contents
    # skipped (decided on AK#1958: the block carries provenance only).
    101: ("info", frozenset({1, 2})),
    102: ("calculating engine", frozenset({2})),
}

# The external NEC-5 engine's code in the calculating-engine block (census:
# 2 and 4 are EZNEC's own NEC-2 and NEC-4 cores, 8 the external NEC-5).
_ENGINE_NEC5 = 8
_ENGINE_NEC4 = 4


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


class EzRefusal(ValueError):
    """An ``.ez`` the import will not read. ``kind`` names which of the four
    refusals it is; ``field`` the field (or block) and ``detail`` the value."""

    kind = "refused"

    def __init__(self, name: str, field: str, detail: str):
        self.name = name
        self.field = field
        self.detail = detail
        super().__init__(self._message())

    def _message(self) -> str:
        return f"{self.name}: {self.field}: {self.detail}"


class EzUnknownFormat(EzRefusal):
    """A version, block type or block revision the format does not define."""

    kind = "unknown-format"

    def _message(self) -> str:
        return (
            f"{self.name}: {self.field}: {self.detail}. This EZNEC format "
            "version is not one this reader knows, so the file is refused "
            "rather than guessed at; open it in EZNEC and export it to .nec"
        )


class EzUndefined(EzRefusal):
    """A reading the format leaves undefined. ``reading`` is the one this
    import can take on request (None when there is none)."""

    kind = "undefined"

    def __init__(self, name: str, field: str, detail: str, reading: str | None):
        self.reading = reading
        super().__init__(name, field, detail)

    def _message(self) -> str:
        head = f"{self.name}: {self.field}: {self.detail}, which the .ez format leaves undefined"
        if self.reading is None:
            return head + "; open it in EZNEC and export it to .nec"
        return (
            f"{head}. To read it as {self.reading}, set "
            f"{ACCEPT_GUESSES_ENV}=1 (the reading is then listed in the notes)"
        )


class EzNotRepresentable(EzRefusal):
    """Something the model here has no element for."""

    kind = "not-representable"

    def _message(self) -> str:
        return f"{self.name}: {self.field}: {self.detail} -- not representable here"


class EzMalformed(EzRefusal):
    """A file that contradicts itself."""

    kind = "malformed"


def accept_guesses_from_env() -> bool:
    """Whether ``ANTENNAKNOBS_EZ_ACCEPT_GUESSES`` asks for the undefined
    readings (1 / true / yes)."""
    return os.environ.get(ACCEPT_GUESSES_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


# --------------------------------------------------------------------------
# The decoded model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EzWire:
    p1: tuple[float, float, float]
    p2: tuple[float, float, float]
    diameter: float
    segments: int


@dataclass(frozen=True)
class EzEnd:
    """Where an object attaches: a wire (1-based, the stored numbering) and a
    position in % from end 1; or a stub end (``stub`` "short" / "open")."""

    wire: int
    pct: float
    stub: str | None = None


@dataclass(frozen=True)
class EzSource:
    at: EzEnd
    rms: complex  # volts or amps, RMS
    kind: str  # V, I, W (split V), J (split I)

    @property
    def current(self) -> bool:
        return self.kind in ("I", "J")


@dataclass(frozen=True)
class EzLoad:
    at: EzEnd
    stored_z: complex  # the impedance EZNEC stores beside every load
    kind: str  # "Z" (R + jX), "R" (RLC), "L" (Laplace)
    rlc_type: str = ""  # S, P, T
    r: float = 0.0
    l: float = 0.0
    c: float = 0.0
    r_freq_mhz: float = 0.0  # where a frequency-variable R holds; 0 = fixed
    laplace: tuple[tuple[float, ...], tuple[float, ...]] | None = None


@dataclass(frozen=True)
class EzLine:
    end1: EzEnd
    end2: EzEnd
    z0: float
    reversed: bool
    length: float  # > 0 metres, < 0 degrees, 0 = the physical distance
    vf: float
    loss_db_per_m: float = 0.0
    loss_freq_mhz: float = 0.0


@dataclass(frozen=True)
class EzTransformer:
    port1: EzEnd
    port2: EzEnd
    z1: float
    z2: float
    reversed: bool


@dataclass(frozen=True)
class EzYNetwork:
    port1: EzEnd
    port2: EzEnd
    y11: complex
    y12: complex
    y22: complex
    reversed: bool


@dataclass(frozen=True)
class EzBranch:
    """One L-network branch: fixed R + jX, or R/L/C parts (``kind`` S / P,
    zero = missing) with the frequency a variable R holds at."""

    rx: complex
    kind: str = ""  # "" for the R + jX form
    r: float = 0.0
    l: float = 0.0
    c: float = 0.0
    r_freq_mhz: float = 0.0


@dataclass(frozen=True)
class EzLNetwork:
    port1: EzEnd
    port2: EzEnd
    series: EzBranch
    shunt: EzBranch


@dataclass(frozen=True)
class EzModel:
    """An ``.ez`` decoded: what the import builds from."""

    name: str
    title: str
    freq_mhz: float
    version: tuple[int, int]  # (version code, program version code)
    ground: str  # "free", "perfect", "real"
    analysis: str  # "H" high accuracy, "M" MININEC (real ground only)
    eps_r: float
    sigma: float
    wires: tuple[EzWire, ...]  # the user's wires (the virtual wire is not one)
    # The virtual-segment numbers, in the stored wire's segment order, and
    # that wire's segment count; None / 0 without virtual segments.
    virtual_labels: tuple[int, ...] | None
    virtual_wire_segments: int
    sources: tuple[EzSource, ...]
    loads: tuple[EzLoad, ...]
    lines: tuple[EzLine, ...]
    transformers: tuple[EzTransformer, ...]
    ynetworks: tuple[EzYNetwork, ...]
    lnetworks: tuple[EzLNetwork, ...]
    wire_loss: tuple[tuple[float, float], ...]  # per user wire (rho, mu_r)
    insulation: tuple[tuple[float, float, float], ...]  # (eps_r, thickness, tan d)
    engine: tuple[int, str] | None  # the calculating-engine block's (code, name)
    program: str | None  # the info block's program and version, when read
    accept_guesses: bool
    guesses: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def nec5(self) -> bool:
        """EZNEC was set to the external NEC-5 engine (segment-end placement)."""
        return self.engine is not None and self.engine[0] == _ENGINE_NEC5


# --------------------------------------------------------------------------
# Decoding
# --------------------------------------------------------------------------


def _f32(b: bytes, o: int) -> float:
    return struct.unpack_from("<f", b, o)[0]


def _i16(b: bytes, o: int) -> int:
    return struct.unpack_from("<h", b, o)[0]


def _i32(b: bytes, o: int) -> int:
    return struct.unpack_from("<i", b, o)[0]


def _ch(b: bytes, o: int) -> str:
    return chr(b[o]) if b[o] else ""


def _one_line(text: str) -> str:
    """Text for a CM card: control characters (a CR or LF would start a new
    card) become spaces."""
    return "".join(" " if (ord(c) < 32 or ord(c) == 127) else c for c in text)


def _r7(x: float) -> float:
    """A stored single as EZNEC prints it: seven significant digits."""
    if x == 0 or not math.isfinite(x):
        return x
    return float(f"{x:.7g}")


def _pgm_version_word(pv: int, vc: int) -> str | None:
    """The program version word read as a version, None when unknown."""
    if pv == _PGM_VERCODE_OTHER_WRITER:
        return "a non-EZNEC writer"
    if pv == 0:
        # Files from before the field existed; their 5.0+ fields are checked
        # to be zero.
        return "not recorded" if vc < 48 else None
    major, minor, build = pv // 10_000_000, (pv // 100_000) % 100, pv % 100_000
    if 4 <= major <= 7 and minor == 0:
        return f"{major}.{minor}.{build}"
    return None


class _Reader:
    """One decode: the bytes, the mode, and what it has noted so far."""

    def __init__(self, data: bytes, name: str, accept_guesses: bool):
        self.d = data
        self.name = name
        self.accept = accept_guesses
        self.guesses: list[str] = []
        self.warnings: list[str] = []

    # -- refusals ------------------------------------------------------------

    def malformed(self, fld: str, detail: str):
        raise EzMalformed(self.name, fld, detail)

    def unknown(self, fld: str, detail: str):
        raise EzUnknownFormat(self.name, fld, detail)

    def unrepresentable(self, fld: str, detail: str):
        raise EzNotRepresentable(self.name, fld, detail)

    def undefined(self, fld: str, detail: str, reading: str | None = None) -> None:
        """Refuse an undefined reading -- or, when guesses are accepted and
        there is a ``reading``, record it and carry on."""
        if self.accept and reading is not None:
            self.guesses.append(f"{fld}: {detail}, read as {reading}")
            return
        raise EzUndefined(self.name, fld, detail, reading)

    def warn(self, text: str) -> None:
        self.warnings.append(text)

    def rec(self, k: int) -> bytes:
        o = HEADER_BYTES + RECORD_BYTES * k
        return self.d[o : o + RECORD_BYTES]


def decode_ez(
    raw: bytes, *, name: str = "EZNEC model", accept_guesses: bool = False
) -> EzModel:
    """Decode an ``.ez`` file's bytes into an `EzModel`, or raise the
    `EzRefusal` that names why not (see the module docstring)."""
    rd = _Reader(bytes(raw), name, accept_guesses)
    d = rd.d
    if len(d) < HEADER_BYTES:
        rd.malformed("length", f"{len(d)} bytes is shorter than the model header")
    ck = _i16(d, 0x3F)
    if ck != _CHECK_WORD:
        rd.malformed(
            "integrity word",
            f"{ck}, where every EZNEC file holds {_CHECK_WORD} (not an .ez file?)",
        )

    # -- version gate --------------------------------------------------------
    vc, pv = _i16(d, 0x72), _i32(d, 0x90)
    problems = []
    if vc not in _KNOWN_VERCODES:
        problems.append(f"version code {vc}")
    if _pgm_version_word(pv, vc) is None:
        problems.append(f"program version word {pv}")
    if problems:
        rd.unknown("file version", " and ".join(problems))
    pre5 = pv < 50_000_000  # 0 included: older than the field

    # -- counts ----------------------------------------------------------------
    n_media, n_src, n_load, n_line = (
        _i16(d, 0x02),
        _i16(d, 0x32),
        _i16(d, 0x34),
        _i16(d, 0x78),
    )
    if vc >= 50:
        n_rec, n_wire = _i32(d, 0x7C), _i32(d, 0x80)
        if _i16(d, 0x00) != min(n_rec, 32767) or _i16(d, 0x30) != min(n_wire, 32767):
            rd.malformed(
                "counts",
                f"the short counts ({_i16(d, 0x00)} records, {_i16(d, 0x30)} wires) "
                f"disagree with the long ones ({n_rec}, {n_wire})",
            )
    else:
        n_rec, n_wire = _i16(d, 0x00), _i16(d, 0x30)
    for what, n in (
        ("media", n_media),
        ("sources", n_src),
        ("loads", n_load),
        ("lines", n_line),
    ):
        if n < 0:
            rd.malformed(f"{what} count", str(n))
    if n_wire < 1:
        rd.malformed("wire count", str(n_wire))
    if n_rec != max(n_media, n_wire, n_src, n_load, n_line):
        rd.malformed(
            "record count",
            f"{n_rec}, where the largest table has {max(n_media, n_wire, n_src, n_load, n_line)} rows",
        )
    blocks_at = HEADER_BYTES + RECORD_BYTES * (n_rec + 2)
    if len(d) < blocks_at:
        rd.malformed("length", f"{len(d)} bytes; {n_rec} records need {blocks_at}")

    n_xfmr, n_ynet, n_lnet, n_virt = (_i16(d, o) for o in (0x98, 0x9A, 0x9C, 0x9E))
    if pre5 and (n_xfmr or n_ynet or n_lnet or n_virt):
        rd.malformed(
            "5.0 fields",
            "a file from before EZNEC 5.0 counts transformers, networks or virtual segments",
        )
    if min(n_xfmr, n_ynet, n_lnet, n_virt) < 0:
        rd.malformed("network counts", f"{(n_xfmr, n_ynet, n_lnet, n_virt)}")

    title = _one_line(d[0x12:0x30].decode("latin-1")).rstrip(" ")
    freq = _r7(_f32(d, 0x05))
    if not (math.isfinite(freq) and freq > 0):
        rd.malformed("frequency", f"{freq} MHz")

    _check_display_fields(rd)
    ground, analysis = _read_ground(rd, n_media)
    eps_r = sigma = 0.0
    if ground == "real":
        r0 = rd.rec(0)
        sigma, eps_r = _r7(_f32(r0, 0)), _r7(_f32(r0, 4))
        if not (sigma >= 0 and eps_r >= 1):
            rd.malformed("medium 1", f"sigma {sigma} S/m, eps_r {eps_r}")

    lnet_form = _ch(d, 0x59)
    if n_lnet and lnet_form not in ("Z", "R"):
        rd.undefined("L-network form", f"{lnet_form!r} beside {n_lnet} L networks")
    load_kind = _load_kind(rd, n_load)

    # -- records ----------------------------------------------------------------
    stored_wires = [_wire(rd, k) for k in range(n_wire)]
    sources = [_source(rd, k) for k in range(n_src)]
    loads = [_load(rd, k, load_kind) for k in range(n_load)]
    lines = [_line(rd, k) for k in range(n_line)]
    for k in range(n_rec):
        if any(rd.rec(k)[167:170]):
            rd.undefined(f"record {k + 1} reserved bytes", rd.rec(k)[167:170].hex())
    _record3(rd, n_rec)
    r4 = d[HEADER_BYTES + RECORD_BYTES * (n_rec + 1) : blocks_at]
    if any(r4):
        rd.undefined("record 4", "holds data where the format reserves zeros", "unused")

    # -- blocks -------------------------------------------------------------------
    blocks = _walk_blocks(rd, blocks_at)
    engine = _engine_block(rd, blocks.get(102))
    program = _info_block(rd, blocks.get(101))
    if 11 in blocks:
        _sweep_block(rd, blocks[11][0])
    _plane_wave(rd, blocks.get(31), n_src)

    virtual = None
    if n_virt or 18 in blocks:
        if 18 not in blocks:
            rd.malformed(
                "virtual segments", f"{n_virt} counted but no virtual-segment block"
            )
        virtual = _virtual_block(rd, blocks[18][0], n_virt, n_wire)
    n_user = n_wire - (1 if virtual is not None else 0)
    if n_user < 1:
        rd.malformed("wires", "the only wire is the virtual-segment wire")
    wires = stored_wires[:n_user]

    insulation = _insulation_block(rd, blocks.get(12), n_wire)
    wire_loss = _loss_block(rd, blocks.get(13), n_wire)
    if wire_loss is None:
        rho, mu = _r7(_f32(d, 0x62)), _r7(_f32(d, 0x66))
        wire_loss = [(rho, mu)] * n_wire
    if 14 in blocks:
        lines = _line_loss_block(rd, blocks[14][0], lines)
    transformers = _transformer_block(rd, blocks.get(15), n_xfmr)
    ynetworks = _ynet_block(rd, blocks.get(16), n_ynet)
    lnetworks = _lnet_block(rd, blocks.get(17), n_lnet, lnet_form)

    # -- attachments ---------------------------------------------------------------
    def check(end: EzEnd, what: str):
        if end.stub is not None:
            return
        if not 1 <= end.wire <= n_wire:
            rd.malformed(what, f"wire {end.wire} (the model has {n_wire})")
        if not (0.0 <= end.pct <= 100.0):
            rd.malformed(what, f"position {end.pct} %")
        if virtual is not None and end.wire == n_wire:
            seg = _segment(end.pct, stored_wires[-1].segments)
            if seg > len(virtual):
                rd.malformed(
                    what, f"virtual-wire segment {seg} has no virtual segment number"
                )

    for k, s in enumerate(sources, 1):
        check(s.at, f"source {k}")
    for k, ld in enumerate(loads, 1):
        check(ld.at, f"load {k}")
    for k, t in enumerate(lines, 1):
        check(t.end1, f"line {k} end 1")
        check(t.end2, f"line {k} end 2")
        if t.end1.stub and t.end2.stub:
            rd.malformed(f"line {k}", "both ends are stubs")
    for label, objs in (
        ("transformer", transformers),
        ("Y network", ynetworks),
        ("L network", lnetworks),
    ):
        for k, x in enumerate(objs, 1):
            check(x.port1, f"{label} {k} port 1")
            check(x.port2, f"{label} {k} port 2")

    return EzModel(
        name=name,
        title=title,
        freq_mhz=freq,
        version=(vc, pv),
        ground=ground,
        analysis=analysis,
        eps_r=eps_r,
        sigma=sigma,
        wires=tuple(wires),
        virtual_labels=None if virtual is None else tuple(virtual),
        virtual_wire_segments=0 if virtual is None else stored_wires[-1].segments,
        sources=tuple(sources),
        loads=tuple(loads),
        lines=tuple(lines),
        transformers=tuple(transformers),
        ynetworks=tuple(ynetworks),
        lnetworks=tuple(lnetworks),
        wire_loss=tuple(wire_loss[:n_user]),
        insulation=tuple(insulation[:n_user]) if insulation else (),
        engine=engine,
        program=program,
        accept_guesses=accept_guesses,
        guesses=tuple(rd.guesses),
        warnings=tuple(rd.warnings),
    )


def _check_display_fields(rd: _Reader) -> None:
    """Fields that change only what EZNEC shows: a value outside the set the
    format names is a warning, never a refusal."""
    d = rd.d
    odd = []
    for off, label, allowed in (
        (0x41, "display units", ("M", "L", "F", "I", "W")),
        (0x42, "plot range", ("F", "P")),
        (0x7A, "plot type", ("A", "E", "3", "2")),
    ):
        c = _ch(d, off)
        if c not in allowed:
            odd.append(f"{label} {c!r}")
    if not 1 <= _i16(d, 0x76) <= 7:
        odd.append(f"plot polarisation {_i16(d, 0x76)}")
    if odd:
        rd.warn(
            "Display settings outside the format's values, which do not change the model: "
            + ", ".join(odd)
            + "."
        )
    flags = _i32(d, 0x8C)
    if flags & ~0b11:
        rd.undefined("header flags", f"{flags:#x} sets bits the format reserves")
    if any(d[0xA0:0xA2]) or any(d[0xA3:0xAA]):
        rd.undefined("header reserved bytes", d[0xA0:0xAA].hex())


def _read_ground(rd: _Reader, n_media: int) -> tuple[str, str]:
    d = rd.d
    gt = _ch(d, 0x36)
    kinds = {"F": "free", "P": "perfect", "R": "real"}
    if gt not in kinds:
        rd.undefined("ground type", repr(gt))
    ground = kinds[gt]
    nr = _i16(d, 0x37)
    if nr < 0:
        rd.malformed("NEC radials", str(nr))
    if ground != "real":
        if n_media > 1 or nr > 0:
            rd.warn(
                f"The file keeps {n_media} ground media and {nr} radials, unused over "
                f"{'free space' if ground == 'free' else 'perfect ground'}."
            )
        return ground, ""
    if n_media < 1:
        rd.malformed("media", "real ground with no medium")
    if n_media > 1:
        rd.unrepresentable(
            "media", f"{n_media} ground media (a second medium or boundary)"
        )
    if nr > 0:
        rd.unrepresentable(
            "NEC radials", f"{nr} radials in EZNEC's NEC radial ground screen"
        )
    ga = _ch(d, 0x7B)
    if ga == "F":
        # Older EZNEC's "fast" ground analysis; EZNEC 4.0 and later read it
        # as high accuracy, and so does this import.
        rd.warn(
            "The ground analysis is the pre-4.0 'fast' type, which EZNEC reads as high accuracy."
        )
        ga = "H"
    if ga not in ("H", "M"):
        rd.undefined("ground analysis", repr(ga))
    if ga == "H":
        hag = _ch(d, 0xA2)
        if hag == "X":
            rd.undefined(
                "high-accuracy ground type",
                "'X' (EZNEC Pro/4's extended ground)",
                "the high-accuracy (Sommerfeld) ground",
            )
        elif hag not in ("", "H"):
            rd.undefined("high-accuracy ground type", repr(hag))
    return ground, ga


def _load_kind(rd: _Reader, n_load: int) -> str:
    d = rd.d
    lt = _ch(d, 0x75)
    if not n_load:
        return lt
    if lt in ("Z", "R", "L"):
        return lt
    old = _ch(d, 0x50)
    if lt in ("", " ") and old in ("Z", "S"):
        # Files from before the field existed name the type in the older one.
        rd.undefined(
            "load type",
            f"{lt!r} (a pre-3.0 file)",
            f"the older load-type field's {old!r}",
        )
        return {"Z": "Z", "S": "L"}[old]
    rd.undefined("load type", repr(lt))
    return lt  # pragma: no cover - undefined() raised


def _segment(pct: float, n: int) -> int:
    """The segment a position lands on, as EZNEC's export writes it."""
    return min(n, max(1, math.ceil(pct * n / 100.0 - 1e-9)))


def _wire(rd: _Reader, k: int) -> EzWire:
    r = rd.rec(k)
    c = [_r7(_f32(r, 16 + 4 * i)) for i in range(6)]
    dia = _r7(_f32(r, 40))
    nseg = _i16(r, 46)
    if nseg < 1:
        rd.malformed(f"wire {k + 1}", f"{nseg} segments")
    if not all(math.isfinite(v) for v in c) or not (dia > 0 and math.isfinite(dia)):
        rd.malformed(f"wire {k + 1}", f"ends {c}, diameter {dia}")
    return EzWire(tuple(c[:3]), tuple(c[3:]), dia, nseg)


def _source(rd: _Reader, k: int) -> EzSource:
    r = rd.rec(k)
    kind = _ch(r, 62)
    if kind not in ("V", "I", "W", "J"):
        rd.undefined(f"source {k + 1} type", repr(kind))
    mag, ph = _r7(_f32(r, 54)), _r7(_f32(r, 58))
    rms = mag * cmath.exp(1j * math.radians(ph))
    return EzSource(EzEnd(_i16(r, 48), _r7(_f32(r, 50))), rms, kind)


def _load(rd: _Reader, k: int, kind: str) -> EzLoad:
    r = rd.rec(k)
    conn = _ch(r, 149)
    if conn == "P":
        rd.undefined(
            f"load {k + 1} connection",
            "'P' (a parallel-connected load: what it is connected across is not defined)",
        )
    elif conn != "S":
        rd.undefined(f"load {k + 1} connection", repr(conn))
    at = EzEnd(_i16(r, 63), _r7(_f32(r, 65)))
    stored = complex(_r7(_f32(r, 69)), _r7(_f32(r, 73)))
    if kind == "L":
        num = tuple(_f32(r, 77 + 4 * i) for i in range(6))
        den = tuple(_f32(r, 101 + 4 * i) for i in range(6))
        return EzLoad(at, stored, "L", laplace=(num, den))
    if any(r[77:125]):
        rd.warn(f"Load {k + 1} keeps Laplace coefficients it does not use.")
    if kind == "R":
        t = _ch(r, 150)
        if t not in ("S", "P", "T"):
            rd.undefined(f"load {k + 1} RLC type", repr(t))
        # Parts as stored (not rounded for print): a trap near resonance
        # amplifies the seventh digit, and EZNEC computes from the singles.
        R, L, C, F = (_f32(r, o) for o in (151, 155, 159, 163))
        if min(R, L, C, F) < 0:
            rd.malformed(f"load {k + 1}", f"negative part R {R}, L {L}, C {C}, F {F}")
        return EzLoad(at, stored, "R", t, R, L, C, F)
    if any(r[150:167]):
        rd.undefined(f"load {k + 1}", "R/L/C values on a load that is not an RLC load")
    return EzLoad(at, stored, "Z")


def _line(rd: _Reader, k: int) -> EzLine:
    r = rd.rec(k)

    def end(w: int, p: float) -> EzEnd:
        if w == -1:
            return EzEnd(w, 0.0, "short")
        if w == -2:
            return EzEnd(w, 0.0, "open")
        return EzEnd(w, _r7(p))

    z0, ln, vf = _r7(_f32(r, 137)), _r7(_f32(r, 141)), _r7(_f32(r, 145))
    if z0 == 0 or not (vf > 0) or not math.isfinite(ln):
        rd.malformed(f"line {k + 1}", f"Z0 {z0}, velocity factor {vf}, length {ln}")
    return EzLine(
        end(_i16(r, 125), _f32(r, 127)),
        end(_i16(r, 131), _f32(r, 133)),
        abs(z0),
        z0 < 0,
        ln,
        vf,
    )


def _record3(rd: _Reader, n_rec: int) -> None:
    """The near-field request: no effect on the model, so oddities warn."""
    o = HEADER_BYTES + RECORD_BYTES * n_rec
    r = rd.d[o : o + RECORD_BYTES]
    if _ch(r, 0) not in ("", "E", "H") or _ch(r, 1) not in ("", "C", "S"):
        rd.warn(
            "The near-field request holds values outside the format's set (no effect on the model)."
        )


def _walk_blocks(rd: _Reader, o: int) -> dict[int, tuple[bytes, int]]:
    d = rd.d
    out: dict[int, tuple[bytes, int]] = {}
    custom = 0
    while o < len(d):
        if o + 7 > len(d):
            rd.malformed("blocks", f"a block header is cut short at byte {o}")
        typ, ln = struct.unpack_from("<hi", d, o)
        rev = d[o + 6]
        if ln < 7 or o + ln > len(d):
            rd.malformed(f"block {typ}", f"length {ln} at byte {o}")
        body = d[o + 7 : o + ln]
        o += ln
        if typ < 0:
            custom += 1  # a custom block: skipped, as the format says
            continue
        if typ not in _BLOCKS:
            rd.unknown(f"block {typ}", f"block type {typ} (revision {rev}, {ln} bytes)")
        bname, revs = _BLOCKS[typ]
        if rev not in revs:
            rd.unknown(
                f"block {typ} ({bname})",
                f"revision {rev} (known: {', '.join(map(str, sorted(revs)))})",
            )
        if typ in out:
            rd.malformed(f"block {typ} ({bname})", "appears twice")
        out[typ] = (body, rev)
    if custom:
        rd.warn(
            f"{custom} custom block{'s' if custom != 1 else ''} (another program's data) skipped."
        )
    return out


def _engine_block(rd: _Reader, blk) -> tuple[int, str] | None:
    if blk is None:
        return None
    b = blk[0]
    try:
        code, n1 = _i32(b, 0), _i32(b, 4)
        name = b[8 : 8 + n1].decode("latin-1")
        n2 = _i32(b, 8 + n1)
        ok = n1 >= 0 and n2 >= 0 and 12 + n1 + n2 == len(b)
    except struct.error:
        ok = False
    if not ok:
        rd.malformed("block 102 (calculating engine)", "its lengths do not add up")
    return code, name


def _info_block(rd: _Reader, blk) -> str | None:
    """The writing program's name and version, for the notes. Revision 1 is
    skipped (decided exception); revision 2 that does not parse is a warning
    -- the block holds no model data."""
    if blk is None:
        return None
    b, rev = blk
    if rev == 1:
        rd.warn(
            "The file's info block is revision 1, which the format does not describe; its contents (provenance only) are skipped."
        )
        return None
    try:
        o = 12
        strs = []
        for _ in range(2):
            n = _i32(b, o)
            if n < 0 or o + 4 + n > len(b):
                raise struct.error
            strs.append(b[o + 4 : o + 4 + n].decode("latin-1").strip())
            o += 4 + n
        date = struct.unpack_from("<d", b, 4)[0]
    except struct.error:
        rd.warn(
            "The file's info block does not parse; it holds no model data and is skipped."
        )
        return None
    when = ""
    try:
        if date > 0:
            dt = datetime.datetime(
                1899, 12, 30, tzinfo=datetime.UTC
            ) + datetime.timedelta(days=date)
            when = f", saved {dt:%Y-%m-%d}"
    except (OverflowError, ValueError):
        pass
    who = " ".join(s for s in strs if s)
    return (who + when) if who else None


def _sweep_block(rd: _Reader, b: bytes) -> None:
    """The frequency-sweep settings: EZNEC's sweep dialog, not the model."""
    ok = len(b) >= 32 and _i32(b, 0) == 16 and _i16(b, len(b) - 2) == 12345
    if not ok:
        rd.warn(
            "The frequency-sweep block does not follow the format; it holds EZNEC's sweep settings only and is skipped."
        )


def _plane_wave(rd: _Reader, blk, n_src: int) -> None:
    active = False
    if blk is not None:
        b = blk[0]
        if len(b) != 32:
            rd.malformed("block 31 (plane-wave source)", f"{len(b)} bytes")
        st = _i32(b, 0)
        if st not in (0, 1):
            rd.undefined("plane-wave source type", str(st))
        active = st == 1
    if active:
        rd.unrepresentable(
            "plane-wave source", "the active excitation is an incident plane wave"
        )
    if n_src == 0:
        rd.malformed("sources", "none, and no active plane-wave source")


def _count(rd: _Reader, b: bytes, what: str, want: int) -> None:
    if len(b) < 4 or _i32(b, 0) != want:
        rd.malformed(
            what,
            f"counts {_i32(b, 0) if len(b) >= 4 else '?'} where the header counts {want}",
        )


def _virtual_block(rd: _Reader, b: bytes, n_virt: int, n_wire: int) -> list[int]:
    what = "block 18 (virtual segments)"
    _count(rd, b, what, n_virt)
    if len(b) != 8 + 4 * n_virt:
        rd.malformed(what, f"{len(b)} bytes for {n_virt} segments")
    if _i32(b, 4) != n_wire:
        rd.malformed(
            what, f"names wire {_i32(b, 4)}; the stored virtual wire is {n_wire}"
        )
    return [_i32(b, 8 + 4 * i) for i in range(n_virt)]


def _insulation_block(rd: _Reader, blk, n_wire: int):
    if blk is None:
        return None
    b = blk[0]
    what = "block 12 (wire insulation)"
    _count(rd, b, what, n_wire)
    if len(b) != 4 + 12 * n_wire:
        rd.malformed(what, f"{len(b)} bytes for {n_wire} wires")
    return [
        tuple(_r7(_f32(b, 4 + 12 * k + 4 * i)) for i in range(3)) for k in range(n_wire)
    ]


def _loss_block(rd: _Reader, blk, n_wire: int):
    if blk is None:
        return None
    b = blk[0]
    what = "block 13 (wire loss)"
    _count(rd, b, what, n_wire)
    if len(b) != 4 + 8 * n_wire:
        rd.malformed(what, f"{len(b)} bytes for {n_wire} wires")
    return [(_r7(_f32(b, 4 + 8 * k)), _r7(_f32(b, 8 + 8 * k))) for k in range(n_wire)]


def _line_loss_block(rd: _Reader, b: bytes, lines: list[EzLine]) -> list[EzLine]:
    nt = len(lines)
    what = "block 14 (line loss)"
    _count(rd, b, what, nt)
    if len(b) != 4 + 8 * nt:
        rd.malformed(what, f"{len(b)} bytes for {nt} lines")
    # Every line's loss (dB/m), then every line's loss frequency (MHz).
    out = []
    for k, t in enumerate(lines):
        loss, lf = _r7(_f32(b, 4 + 4 * k)), _r7(_f32(b, 4 + 4 * nt + 4 * k))
        if loss < 0 or lf < 0:
            rd.malformed(f"line {k + 1} loss", f"{loss} dB/m at {lf} MHz")
        out.append(replace(t, loss_db_per_m=loss, loss_freq_mhz=lf))
    return out


def _ports(b: bytes, n: int, k: int) -> tuple[EzEnd, EzEnd]:
    """Network ``k``'s two ports (1-based ``k``; entry 0 is a dummy)."""
    m = n + 1
    w = [_i32(b, 4 + 4 * i) for i in (2 * k, 2 * k + 1)]
    p = [_r7(_f32(b, 4 + 8 * m + 4 * i)) for i in (2 * k, 2 * k + 1)]
    return EzEnd(w[0], p[0]), EzEnd(w[1], p[1])


def _transformer_block(rd: _Reader, blk, n: int) -> list[EzTransformer]:
    if not n:
        return []
    what = "block 15 (transformers)"
    if blk is None:
        rd.malformed(what, f"{n} transformers counted but no block")
    b = blk[0]
    _count(rd, b, what, n)
    m = n + 1
    if len(b) != 4 + 24 * m:
        rd.malformed(what, f"{len(b)} bytes for {n} transformers")
    out = []
    for k in range(1, m):
        z1, z2 = (_r7(_f32(b, 4 + 16 * m + 4 * i)) for i in (2 * k, 2 * k + 1))
        if not (z1 > 0) or z2 == 0:
            rd.malformed(f"transformer {k}", f"port impedances {z1}, {z2}")
        if z2 < 0:
            rd.undefined(
                f"transformer {k}",
                "a reversed connection",
                "port 2's polarity swapped (the transfer terms negated)",
            )
        p1, p2 = _ports(b, n, k)
        out.append(EzTransformer(p1, p2, z1, abs(z2), z2 < 0))
    return out


def _ynet_block(rd: _Reader, blk, n: int) -> list[EzYNetwork]:
    if not n:
        return []
    what = "block 16 (Y-parameter networks)"
    if blk is None:
        rd.malformed(what, f"{n} networks counted but no block")
    b = blk[0]
    _count(rd, b, what, n)
    m = n + 1
    if len(b) != 4 + 16 * m + 28 * m:
        rd.malformed(what, f"{len(b)} bytes for {n} networks")
    y0 = 4 + 16 * m
    out = []
    for k in range(1, m):
        v = [_r7(_f32(b, y0 + 28 * k + 4 * i)) for i in range(7)]
        if v[6] not in (1.0, -1.0):
            rd.malformed(f"Y network {k}", f"normal/reverse flag {v[6]}")
        if v[6] == -1.0:
            rd.undefined(
                f"Y network {k}",
                "a reversed connection",
                "port 2's polarity swapped (Y12 and Y21 negated)",
            )
        p1, p2 = _ports(b, n, k)
        out.append(
            EzYNetwork(
                p1,
                p2,
                complex(v[0], v[1]),
                complex(v[2], v[3]),
                complex(v[4], v[5]),
                v[6] == -1.0,
            )
        )
    return out


def _lnet_block(rd: _Reader, blk, n: int, form: str) -> list[EzLNetwork]:
    if not n:
        return []
    what = "block 17 (L networks)"
    if blk is None:
        rd.malformed(what, f"{n} L networks counted but no block")
    b = blk[0]
    _count(rd, b, what, n)
    m = n + 1
    o_z, o_nr = 4 + 16 * m, 4 + 32 * m
    if len(b) < o_nr + 4:
        rd.malformed(what, f"{len(b)} bytes for {n} L networks")
    n_rlc = _i32(b, o_nr)
    o_rlc, o_type = o_nr + 4, o_nr + 4 + 32 * m
    want = o_nr + 4 + ((32 * m + 2 * m) if n_rlc else 0)
    if n_rlc not in (0, n) or len(b) != want:
        rd.malformed(what, f"{n_rlc} RLC networks in {len(b)} bytes (expected {want})")
    if form == "R" and not n_rlc:
        rd.malformed(what, "the R/L/C form is chosen but the block has no R/L/C values")
    out = []
    for k in range(1, m):
        rx = [_r7(_f32(b, o_z + 16 * k + 4 * i)) for i in range(4)]
        ser = EzBranch(complex(rx[0], rx[1]))
        sh = EzBranch(complex(rx[2], rx[3]))
        if form == "R":
            v = [_f32(b, o_rlc + 32 * k + 4 * i) for i in range(8)]
            types = b[o_type + 2 * k : o_type + 2 * k + 2].decode("latin-1")
            # R, L, C and the reference frequency, each series then shunt.
            parts = []
            for j, t in enumerate(types):
                if t not in ("S", "P"):
                    rd.undefined(f"L network {k} branch {j + 1} type", repr(t))
                R, L, C, F = v[j], v[2 + j], v[4 + j], v[6 + j]
                if min(R, L, C, F) < 0:
                    rd.malformed(
                        f"L network {k}", f"negative part R {R}, L {L}, C {C}, F {F}"
                    )
                if t == "P":
                    if not (R or L or C):
                        rd.undefined(
                            f"L network {k} branch {j + 1}",
                            "a parallel branch with no parts",
                        )
                    rd.undefined(
                        f"L network {k} branch {j + 1}",
                        "a parallel R/L/C branch (the format defines a missing part only for loads)",
                        "a missing part being absent (open), as for a parallel RLC load",
                    )
                parts.append(EzBranch(complex(rx[2 * j], rx[2 * j + 1]), t, R, L, C, F))
            ser, sh = parts
        out.append(EzLNetwork(*_ports(b, n, k), ser, sh))
    return out


# --------------------------------------------------------------------------
# Elements evaluated at each frequency
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _YOf:
    """A frequency-dependent admittance block built from an impedance
    function (Ω at Hz): a one-port ``y = 1/z``, or the series two-port
    ``(1/z)·[[1, -1], [-1, 1]]``, or (``y1`` / ``y2``) a one- or two-port
    admittance function."""

    z: Callable[[float], complex] | None = None
    series: bool = False
    y1: Callable[[float], complex] | None = None
    y2: (
        Callable[[float], tuple[tuple[complex, complex], tuple[complex, complex]]]
        | None
    ) = None

    @property
    def nports(self) -> int:
        return 2 if (self.series or self.y2 is not None) else 1

    def y_at(self, f_hz: float) -> np.ndarray:
        if self.y2 is not None:
            return np.array(self.y2(f_hz), dtype=complex)
        if self.y1 is not None:
            return np.array([[self.y1(f_hz)]], dtype=complex)
        z = self.z(f_hz)
        if z == 0:
            raise ValueError(
                f"a zero impedance at {f_hz / 1e6:g} MHz has no admittance"
            )
        y = 1.0 / z
        if self.series:
            return np.array([[y, -y], [-y, y]], dtype=complex)
        return np.array([[y]], dtype=complex)


@dataclass(frozen=True)
class _OnePort:
    """An element at one site (`NecLoad.custom`): ``terminate`` when nothing
    else connects there, ``series`` when a line or network does (it then
    sits between the wire and them, as a NEC load inside the segment does).
    ``native`` builds the termination from the circuit's own elements when
    there is a spelling; otherwise the impedance function is stamped."""

    label: str
    z: Callable[[float], complex]
    native: Callable[[str], tuple[list, dict]] | None = None
    native_series: Callable[[str, str], tuple[list, dict]] | None = None

    def terminate(self, port: str):
        if self.native is not None:
            return self.native(port)
        return [_net.TouchstoneLoad(port, _YOf(z=self.z))], {}

    def series(self, a: str, b: str):
        if self.native_series is not None:
            return self.native_series(a, b)
        return [_net.TouchstoneTwoPort(a, b, _YOf(z=self.z, series=True))], {}


@dataclass(frozen=True)
class _StubLine:
    """A stub (`NecLoad.custom` with ``line``): a line ending at one site, so
    it hangs across the segment gap like any line end there -- in parallel
    with a source or another line at that site, never in series."""

    label: str
    build: Callable[[str], tuple[list, dict]]
    line: bool = True

    def terminate(self, port: str):
        return self.build(port)


@dataclass(frozen=True)
class _TwoPort:
    """A two-port (`NecNT.custom`): ``between(a, b)`` builds it."""

    label: str
    build: Callable[[str, str], tuple[list, dict]]

    def between(self, a: str, b: str):
        return self.build(a, b)


def _omega(f_hz: float) -> float:
    return 2.0 * math.pi * f_hz


def _rlc_z(kind: str, R: float, L: float, C: float, w: float) -> complex:
    """A branch of R, L and C (zero = missing): ``S`` series, ``P`` parallel,
    ``T`` the trap reading -- R and L in series, across C."""
    if kind == "S":
        z = complex(R, w * L)
        if C:
            z += 1.0 / (1j * w * C)
        return z
    if kind == "P":
        y = 0j
        if R:
            y += 1.0 / R
        if L:
            y += 1.0 / (1j * w * L)
        if C:
            y += 1j * w * C
        return 1.0 / y if y else complex(math.inf)
    zl = complex(R, w * L)
    zc = 1.0 / (1j * w * C)
    if zl + zc == 0:
        return complex(math.inf)  # a lossless trap at its resonance: open
    return zl * zc / (zl + zc)


def _var_r(R: float, F_mhz: float, f_hz: float) -> float:
    """A frequency-variable R (an undefined reading): ∝ √f from F."""
    return R * math.sqrt(f_hz / (F_mhz * 1e6)) if F_mhz else R


# --------------------------------------------------------------------------
# The import
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EzImport:
    """An ``.ez`` read as a deck: the `NecDeck` the file design builds from,
    its frequency and ground (in the CLI's ``--ground`` shape), the notes the
    app shows, and the NEC card text the deck was parsed from (`nec_text`,
    shown in the Files view and kept for tests)."""

    deck: NecDeck
    model: EzModel
    freq_mhz: float
    ground: object
    ground_method: str | None
    ground_word: str
    notes: tuple[str, ...]
    nec_text: str
    title: str
    extended_kernel: bool


def _fmt(v: float) -> str:
    r = repr(float(v))
    return "0" if r in ("0.0", "-0.0") else r


class _Deck:
    """The NEC cards being written, with the elements no card spells."""

    def __init__(self, m: EzModel, nec5: bool):
        self.m = m
        self.nec5 = nec5
        self.lam = _C0 / (m.freq_mhz * 1e6)
        self.cards: list[str] = []
        self.ld: list[tuple[int, int, object]] = []  # (tag, seg, custom) per LD card
        self.nt: list[tuple[int, int, int, int, object]] = []  # per NT card
        self.notes: list[str] = []
        self.fixed: list[str] = []  # elements held at the model frequency
        self.guesses: list[str] = []  # readings taken while writing the cards
        self.vtag = len(m.wires) + 1 if m.virtual_labels else None

    def guess(self, fld: str, detail: str, reading: str) -> None:
        """An undefined reading met while writing the cards: refused, or
        (``accept_guesses``) taken and listed, as `_Reader.undefined`."""
        if not self.m.accept_guesses:
            raise EzUndefined(self.m.name, fld, detail, reading)
        self.guesses.append(f"{fld}: {detail}, read as {reading}")

    # -- addresses --------------------------------------------------------------

    def where(self, e: EzEnd) -> tuple[int, int]:
        """The ``(tag, segment)`` an attachment is written at. Under NEC-5,
        which connects everything at segment ends, a 0 % position is the
        wire's end 1 -- segment -1, as EZNEC's NEC-5 export writes a load or
        line end there -- for every kind of attachment alike."""
        m = self.m
        if self.vtag is not None and e.wire == len(m.wires) + 1:
            # The stored virtual wire: its segment k carries virtual segment
            # number labels[k - 1]. The rebuilt wire gives each number its
            # own segment, in increasing order (EZNEC's export does this).
            labels = m.virtual_labels
            label = labels[_segment(e.pct, m.virtual_wire_segments) - 1]
            return self.vtag, sorted(labels).index(label) + 1
        n = m.wires[e.wire - 1].segments
        if self.nec5 and e.pct == 0:
            return e.wire, -1
        return e.wire, _segment(e.pct, n)

    def seg_field(self, seg: int) -> str:
        """An LD/TL card's segment pair as written: NEC-5's knot form names
        the segment once (``seg 0``), NEC-2's the range ``seg seg``."""
        return f"{seg} 0" if self.nec5 else f"{seg} {seg}"

    # -- cards ----------------------------------------------------------------------

    def load_card(
        self,
        at: EzEnd,
        typ: int,
        f1: float,
        f2: float,
        f3: float,
        custom=None,
        label: str = "",
    ):
        tag, seg = self.where(at)
        if custom is not None:
            self.cards.append(
                f"CM ! LD {typ} on wire {tag} segment {seg} stands for {label}"
            )
        self.cards.append(
            f"LD {typ} {tag} {self.seg_field(seg)} {_fmt(f1)} {_fmt(f2)} {_fmt(f3)}"
        )
        self.ld.append((tag, seg, custom))

    def nt_card(
        self,
        p1: EzEnd,
        p2: EzEnd,
        y11: complex,
        y12: complex,
        y22: complex,
        custom=None,
        label: str = "",
    ):
        t1, s1 = self.where(p1)
        t2, s2 = self.where(p2)
        if custom is not None:
            self.cards.append(
                f"CM ! NT from wire {t1} segment {s1} to wire {t2} segment {s2} stands for {label}"
            )
        self.cards.append(
            f"NT {t1} {s1} {t2} {s2} "
            + " ".join(
                _fmt(v)
                for v in (y11.real, y11.imag, y12.real, y12.imag, y22.real, y22.imag)
            )
        )
        self.nt.append((t1, s1, t2, s2, custom))


def _source_cards(dk: _Deck) -> None:
    m = dk.m
    for k, s in enumerate(m.sources, 1):
        v = _clean(s.rms * _SQRT2)
        typ = (4 if dk.nec5 else 6) if s.current else 0
        if s.kind in ("V", "I"):
            tag, seg = dk.where(s.at)
            dk.cards.append(f"EX {typ} {tag} {seg} 0 {_fmt(v.real)} {_fmt(v.imag)}")
            continue
        _split_source(dk, k, s, typ, v)


def _clean(v: complex) -> complex:
    """A phasor with the rounding left by a 90° phase removed."""
    tiny = 1e-12 * abs(v)
    return complex(
        0.0 if abs(v.real) <= tiny else v.real, 0.0 if abs(v.imag) <= tiny else v.imag
    )


def _split_source(dk: _Deck, k: int, s: EzSource, typ: int, v: complex) -> None:
    """A split source (W/J): EZNEC places it across a junction; where, and
    how it shares the excitation, the format does not say. The reading taken
    with ``accept_guesses``: at a wire END that meets exactly one other wire
    end, one source on each side's end segment -- a voltage halved, a
    current repeated -- with the sign following the two wires' directions."""
    m = dk.m
    dk.guess(
        f"source {k}",
        "a split source",
        "one source either side of the wire-end junction it sits at",
    )
    w = s.at.wire
    if (dk.vtag is not None and w == len(m.wires) + 1) or s.at.pct not in (0.0, 100.0):
        raise EzNotRepresentable(
            m.name,
            f"source {k}",
            f"a split source at {s.at.pct} % (only a wire end is read)",
        )
    wires = m.wires
    at_end2 = s.at.pct == 100.0
    p = wires[w - 1].p2 if at_end2 else wires[w - 1].p1
    hits = []
    for j, ww in enumerate(wires):
        if j == w - 1:
            continue
        for e2, q in ((False, ww.p1), (True, ww.p2)):
            if all(abs(p[i] - q[i]) <= 1e-6 * max(1.0, abs(p[i])) for i in range(3)):
                hits.append((j, e2))
    if len(hits) != 1:
        raise EzNotRepresentable(
            m.name,
            f"source {k}",
            "a split source at a wire end that does not meet exactly one other wire end",
        )
    j, j_end2 = hits[0]
    same = at_end2 != j_end2
    vv = v / 2 if typ == 0 else v
    seg_a = wires[w - 1].segments if at_end2 else 1
    seg_b = wires[j].segments if j_end2 else 1
    for tag, seg, vx in ((w, seg_a, vv), (j + 1, seg_b, vv if same else -vv)):
        dk.cards.append(f"EX {typ} {tag} {seg} 0 {_fmt(vx.real)} {_fmt(vx.imag)}")


def _load_cards(dk: _Deck) -> None:
    m = dk.m
    for k, ld in enumerate(m.loads, 1):
        name = f"load {k}"
        if ld.kind == "Z":
            if ld.stored_z != 0:
                dk.load_card(ld.at, 4, ld.stored_z.real, ld.stored_z.imag, 0.0)
            continue
        if ld.kind == "R" and ld.r_freq_mhz:
            ld = replace(ld, r_freq_mhz=_held_r(dk, name, ld.r, ld.r_freq_mhz))
        if ld.kind == "L":
            z = _laplace(dk, k, ld)
        else:
            z = _rlc_load(dk, k, ld)
        zf0 = z(m.freq_mhz * 1e6)
        if not (math.isfinite(zf0.real) and math.isfinite(zf0.imag)):
            raise EzMalformed(
                m.name,
                name,
                f"its impedance is infinite at the model frequency {m.freq_mhz:g} MHz "
                "(a lossless resonance): it would cut the wire",
            )
        _check_stored(m, name, ld.stored_z, zf0)
        if ld.kind == "R" and ld.rlc_type in ("S", "P") and not ld.r_freq_mhz:
            # Plain series / parallel RLC: NEC's own LD 0 / LD 1, which
            # follow frequency (a zero part is missing, as in EZNEC).
            if ld.rlc_type == "S" and not (ld.r or ld.l or ld.c):
                continue  # a short: no load
            dk.load_card(ld.at, 0 if ld.rlc_type == "S" else 1, ld.r, ld.l, ld.c)
            continue
        native = native_series = None
        if ld.kind == "R" and ld.rlc_type == "T" and not ld.r_freq_mhz:
            R, L, C = ld.r or None, ld.l or None, ld.c

            def native(p, R=R, L=L, C=C):
                return [_net.Shunt(port=p, r=R, l=L), _net.Shunt(port=p, c=C)], {}

            def native_series(a, b, R=R, L=L, C=C):
                return [
                    _net.TwoPort(a=a, b=b, r=R, l=L),
                    _net.TwoPort(a=a, b=b, c=C),
                ], {}

        label = f"{name} ({_load_word(ld)})"
        dk.load_card(
            ld.at,
            4,
            1.0,
            0.0,
            0.0,
            _OnePort(label, z, native, native_series),
            label,
        )


def _held_r(dk: _Deck, what: str, R: float, F: float) -> float:
    """The frequency a variable R scales from, after the strict rule: a
    variable R given AT the model frequency is exact there, so without
    ``accept_guesses`` it is held at that value (and listed); given anywhere
    else it needs the undefined law and is refused. With ``accept_guesses``
    the law is taken (R ∝ √f) and F is kept."""
    m = dk.m
    if m.accept_guesses or abs(F - m.freq_mhz) > 1e-4 * m.freq_mhz:
        dk.guess(
            what,
            f"a resistance given at {F:g} MHz that varies with frequency, in a model at {m.freq_mhz:g} MHz",
            "R ∝ √f (skin effect), F in MHz",
        )
        return F
    dk.fixed.append(f"{what}'s R of {R:g} Ω (given at the model frequency)")
    return 0.0


def _load_word(ld: EzLoad) -> str:
    if ld.kind == "L":
        return "a Laplace load"
    word = {"S": "series RLC", "P": "parallel RLC", "T": "trap"}[ld.rlc_type]
    return word + (f", R variable from {ld.r_freq_mhz:g} MHz" if ld.r_freq_mhz else "")


def _laplace(dk: _Deck, k: int, ld: EzLoad) -> Callable[[float], complex]:
    m = dk.m
    dk.guess(f"load {k}", "a Laplace load", "a function of s = jω (rad/s)")
    num, den = ld.laplace

    def z(f_hz: float) -> complex:
        s = 1j * _omega(f_hz)
        n = sum(c * s**i for i, c in enumerate(num))
        dd = sum(c * s**i for i, c in enumerate(den))
        if dd == 0:
            raise ValueError(
                f"{m.name}: load {k}: the Laplace denominator is zero at {f_hz / 1e6:g} MHz"
            )
        return n / dd

    return z


def _rlc_load(dk: _Deck, k: int, ld: EzLoad) -> Callable[[float], complex]:
    m = dk.m
    if ld.rlc_type == "T":
        dk.guess(f"load {k}", "a trap", "R and L in series, across C")
    if ld.rlc_type == "T" and not ld.c:
        raise EzMalformed(m.name, f"load {k}", "a trap with no capacitor")
    if ld.rlc_type == "P" and not (ld.r or ld.l or ld.c):
        raise EzUndefined(m.name, f"load {k}", "a parallel RLC load with no parts")
    t, R, L, C, F = ld.rlc_type, ld.r, ld.l, ld.c, ld.r_freq_mhz

    def z(f_hz: float) -> complex:
        return _rlc_z(t, _var_r(R, F, f_hz), L, C, _omega(f_hz))

    return z


def _check_stored(m: EzModel, what: str, stored: complex, z: complex) -> None:
    """EZNEC stores every load's impedance at the model frequency beside its
    parts; a reading that disagrees with it is not EZNEC's."""
    if stored != 0 and abs(z - stored) > 2e-3 * max(1.0, abs(stored)):
        raise EzUndefined(
            m.name,
            what,
            f"its parts give {z:.6g} Ω at {m.freq_mhz:g} MHz but the file stores {stored:.6g} Ω",
            None,
        )


def _line_length(dk: _Deck, k: int, t: EzLine) -> float:
    """A line's physical length, metres."""
    m = dk.m
    if t.length > 0:
        return t.length
    if t.length < 0:
        dk.guess(
            f"line {k} length",
            f"{-t.length:g} degrees",
            "electrical degrees in the line at the model frequency",
        )
        return -t.length / 360.0 * dk.lam * t.vf
    dk.guess(
        f"line {k} length",
        "0 (the physical distance; between which points is not defined)",
        "the distance between the two segment centres",
    )
    if t.end1.stub or t.end2.stub:
        raise EzMalformed(
            m.name, f"line {k}", "a stub whose length is the distance between its ends"
        )
    pts = []
    for e in (t.end1, t.end2):
        if dk.vtag is not None and e.wire == len(m.wires) + 1:
            raise EzNotRepresentable(
                m.name, f"line {k}", "a physical-distance length to a virtual segment"
            )
        w = m.wires[e.wire - 1]
        s = _segment(e.pct, w.segments)
        u = (s - 0.5) / w.segments
        pts.append(tuple(a + u * (b - a) for a, b in zip(w.p1, w.p2, strict=True)))
    length = math.dist(*pts)
    if length == 0:
        raise EzMalformed(
            m.name, f"line {k}", "the physical distance between its ends is zero"
        )
    return length


def _line_model(t: EzLine, law: bool):
    """``(gamma(f), zc(f))`` of a lossy line. ``law``: loss follows √f from
    the loss frequency (0: held constant) -- the reading taken with
    ``accept_guesses``; otherwise the model frequency's loss is used, which is
    exact there."""
    vf, z0 = t.vf, t.z0
    loss_np_m = t.loss_db_per_m / (20.0 / math.log(10.0))

    def alpha(f_hz: float) -> float:
        if law and t.loss_freq_mhz:
            return loss_np_m * math.sqrt(f_hz / (t.loss_freq_mhz * 1e6))
        return loss_np_m

    def gz(f_hz: float):
        a = alpha(f_hz)
        b = _omega(f_hz) / (vf * _C0)
        return complex(a, b), z0 * complex(1.0, -a / b)

    return gz


def _two_port_line_y(gz, length: float, reversed_: bool):
    def y2(f_hz: float):
        g, zc = gz(f_hz)
        y11 = 1.0 / (zc * cmath.tanh(g * length))
        y12 = -1.0 / (zc * cmath.sinh(g * length))
        if reversed_:
            y12 = -y12
        return ((y11, y12), (y12, y11))

    return y2


def _line_cards(dk: _Deck) -> None:
    m = dk.m
    f0 = m.freq_mhz * 1e6
    for k, t in enumerate(m.lines, 1):
        length = _line_length(dk, k, t)
        lossy = t.loss_db_per_m > 0
        if (
            lossy
            and t.loss_freq_mhz
            and abs(t.loss_freq_mhz - m.freq_mhz) > 1e-4 * m.freq_mhz
        ):
            dk.guess(
                f"line {k} loss",
                f"{t.loss_db_per_m:g} dB/m given at {t.loss_freq_mhz:g} MHz, the model at {m.freq_mhz:g} MHz",
                "loss ∝ √f",
            )
        elif lossy and m.accept_guesses:
            dk.guess(
                f"line {k} loss",
                f"{t.loss_db_per_m:g} dB/m"
                + (
                    f" given at {t.loss_freq_mhz:g} MHz"
                    if t.loss_freq_mhz
                    else " at no stated frequency"
                ),
                "loss ∝ √f"
                if t.loss_freq_mhz
                else "a loss that holds at every frequency",
            )
        gz = _line_model(t, law=m.accept_guesses)
        stub = t.end1.stub or t.end2.stub
        if stub:
            far, near = (t.end1, t.end2) if t.end1.stub else (t.end2, t.end1)

            def yin(f_hz, far=far, gz=gz, length=length, k=k):
                """The stub's input admittance (a lossy line never resonates
                exactly; the guard names the case if one does)."""
                g, zc = gz(f_hz)
                th = cmath.tanh(g * length)
                if far.stub == "open":
                    return th / zc
                if th == 0:
                    raise ValueError(
                        f"{m.name}: line {k}: the shorted stub is a short "
                        f"circuit at {f_hz / 1e6:g} MHz"
                    )
                return 1.0 / (zc * th)

            label = f"line {k} ({far.stub}-circuit stub)"
            if lossy and not m.accept_guesses:
                # Held at the model frequency (its loss law is not defined).
                dk.fixed.append(label)
                y0 = yin(f0)

                def build(p, y0=y0):
                    return [_net.Admittance(ports=(p,), y=((y0,),))], {}

            elif lossy:

                def build(p, yin=yin):
                    return [_net.TouchstoneLoad(p, _YOf(y1=yin))], {}

            else:

                def build(p, t=t, length=length, short=far.stub == "short"):
                    node = f"{p}#stub"
                    brs = [_net.TL(a=p, b=node, z0=t.z0, length=length, vf=t.vf)]
                    if short:
                        brs.append(_net.Shunt(port=node, r=0.0))
                    return brs, {node: _net.PortVirtual(node)}

            dk.load_card(near, 4, 1.0, 0.0, 0.0, _StubLine(label, build), label)
            continue
        if not lossy:
            # NEC's TL length is electrical: the physical length over VF. A
            # reversed line is NEC's crossed line (negative Z0).
            t1, s1 = dk.where(t.end1)
            t2, s2 = dk.where(t.end2)
            z0 = -t.z0 if t.reversed else t.z0
            dk.cards.append(
                f"TL {t1} {s1} {t2} {s2} {_fmt(z0)} {_fmt(length / t.vf)} 0 0 0 0"
            )
            continue
        y2 = _two_port_line_y(gz, length, t.reversed)
        (y11, y12), (_, y22) = y2(f0)
        if m.accept_guesses:
            label = f"line {k} (lossy, {t.z0:g} Ω)"
            dk.nt_card(
                t.end1,
                t.end2,
                1.0,
                0.0,
                1.0,
                _TwoPort(
                    label,
                    lambda a, b, y2=y2: (
                        [_net.TouchstoneTwoPort(a, b, _YOf(y2=y2))],
                        {},
                    ),
                ),
                label,
            )
        else:
            # EZNEC's own spelling: the line's Y at the model frequency, which
            # the app flags at any other frequency.
            dk.nt_card(t.end1, t.end2, y11, y12, y22)


def _network_cards(dk: _Deck) -> None:
    m = dk.m
    for k, x in enumerate(m.transformers, 1):
        # EZNEC's two-port for a transformer of port "impedances" Z1:Z2, as
        # its export writes it: Y = k·[[1, -n], [-n, n²]] with k = 500/Z1 and
        # n = √(Z1/Z2) -- an ideal n:1 ratio behind a series Z1/500 Ω. Built
        # as exactly that, rather than read back from a rounded card.
        n = math.sqrt(x.z1 / x.z2) * (-1.0 if x.reversed else 1.0)
        r = x.z1 / 500.0
        label = f"transformer {k} ({x.z1:g}:{x.z2:g})"
        dk.nt_card(
            x.port1,
            x.port2,
            1.0,
            0.0,
            1.0,
            _TwoPort(
                label,
                lambda a, b, n=n, r=r: ([_net.Transformer(a=a, b=b, n=n, r=r)], {}),
            ),
            label,
        )
    for k, x in enumerate(m.ynetworks, 1):
        y12 = -x.y12 if x.reversed else x.y12
        y = ((x.y11, y12), (y12, x.y22))
        label = f"Y network {k}"
        dk.nt_card(
            x.port1,
            x.port2,
            1.0,
            0.0,
            1.0,
            _TwoPort(
                label, lambda a, b, y=y: ([_net.Admittance(ports=(a, b), y=y)], {})
            ),
            label,
        )
    for k, x in enumerate(m.lnetworks, 1):
        label = f"L network {k}"
        dk.nt_card(
            x.port1,
            x.port2,
            1.0,
            0.0,
            1.0,
            _TwoPort(label, _lnet_builder(dk, k, x)),
            label,
        )


def _lnet_branch_z(br: EzBranch) -> Callable[[float], complex]:
    if not br.kind:
        z = complex(br.rx.real or _LNET_ZERO_R, br.rx.imag)
        return lambda f_hz, z=z: z
    R = br.r if (br.r or br.kind == "P") else _LNET_ZERO_R

    def z(f_hz: float) -> complex:
        return _rlc_z(br.kind, _var_r(R, br.r_freq_mhz, f_hz), br.l, br.c, _omega(f_hz))

    return z


def _lnet_builder(dk: _Deck, k: int, x: EzLNetwork):
    """The L network: the series branch between its ports, the shunt branch
    across port 2 (EZNEC's arrangement, as its export spells it)."""
    ser, sh = x.series, x.shunt
    if ser.kind and ser.r_freq_mhz:
        ser = replace(
            ser,
            r_freq_mhz=_held_r(
                dk, f"L network {k} series branch", ser.r, ser.r_freq_mhz
            ),
        )
    if sh.kind and sh.r_freq_mhz:
        sh = replace(
            sh,
            r_freq_mhz=_held_r(dk, f"L network {k} shunt branch", sh.r, sh.r_freq_mhz),
        )
    zs, zp = _lnet_branch_z(ser), _lnet_branch_z(sh)
    if not (ser.kind or sh.kind):
        ya, yb = 1.0 / zs(0.0), 1.0 / zp(0.0)
        y = ((ya, -ya), (-ya, ya + yb))
        return lambda a, b, y=y: ([_net.Admittance(ports=(a, b), y=y)], {})

    def fixed_r(br: EzBranch):
        return br.kind and not br.r_freq_mhz

    if fixed_r(ser) and fixed_r(sh):

        def build(a, b):
            brs = []
            if ser.kind == "S":
                brs.append(
                    _net.TwoPort(
                        a=a,
                        b=b,
                        r=ser.r or _LNET_ZERO_R,
                        l=ser.l or None,
                        c=ser.c or None,
                    )
                )
            else:
                brs += [
                    _net.TwoPort(a=a, b=b, **{part: v})
                    for part, v in (("r", ser.r), ("l", ser.l), ("c", ser.c))
                    if v
                ]
            if sh.kind == "S":
                brs.append(
                    _net.Shunt(
                        port=b, r=sh.r or _LNET_ZERO_R, l=sh.l or None, c=sh.c or None
                    )
                )
            else:
                brs.append(
                    _net.Shunt(
                        port=b,
                        r=sh.r or None,
                        l=sh.l or None,
                        c=sh.c or None,
                        parallel=True,
                    )
                )
            return brs, {}

        return build

    def y2(f_hz: float):
        ya, yb = 1.0 / zs(f_hz), 1.0 / zp(f_hz)
        return ((ya, -ya), (-ya, ya + yb))

    return lambda a, b: ([_net.TouchstoneTwoPort(a, b, _YOf(y2=y2))], {})


def _ground_cards(dk: _Deck) -> tuple[str, str]:
    """The ground cards, and the ground in EZNEC's words for the panel."""
    m = dk.m
    if m.ground == "free":
        dk.cards.append("GN -1")
        return "", "EZNEC free space"
    if m.ground == "perfect":
        dk.cards.append("GN 1")
        return "", "EZNEC perfect ground"
    e, s = _fmt(m.eps_r), _fmt(m.sigma)
    if m.analysis == "M":
        if dk.nec5:
            dk.cards.append(f"GD 0 0 0 0 {e} {s} 1 0")
        else:
            dk.cards += ["GN 1 0 0 0 0 0", f"GD 2 0 0 0 {e} {s} 0 0"]
        return "mininec", "EZNEC real ground, MININEC-type"
    # High accuracy: Sommerfeld -- NEC-5's GN 0, NEC-2's GN 2.
    dk.cards.append(f"GN {0 if dk.nec5 else 2} 0 0 0 {e} {s}")
    return "sommerfeld", "EZNEC real ground, high accuracy"


def _loss_cards(dk: _Deck) -> None:
    m = dk.m
    rows = m.wire_loss
    for k, (rho, mu) in enumerate(rows, 1):
        if rho < 0 or (rho > 0 and not math.isfinite(rho)):
            raise EzMalformed(m.name, f"wire {k} loss", f"resistivity {rho} Ω·m")
        if rho > 0 and mu not in (0.0, 1.0):
            raise EzNotRepresentable(
                m.name,
                f"wire {k} loss",
                f"relative permeability {mu:g} (a wire here carries a conductivity only)",
            )
    lossy = [rho > 0 for rho, _ in rows]
    if not any(lossy):
        return
    rhos = {rho for rho, _ in rows}
    if all(lossy) and len(rhos) == 1 and dk.vtag is None:
        dk.cards.append(f"LD 5 0 0 0 {_fmt(1.0 / rows[0][0])}")
        return
    for k, (rho, _mu) in enumerate(rows, 1):
        if rho > 0:
            dk.cards.append(f"LD 5 {k} 0 0 {_fmt(1.0 / rho)}")


def _wire_cards(dk: _Deck) -> None:
    m = dk.m
    for k, w in enumerate(m.wires, 1):
        dk.cards.append(
            f"GW {k} {w.segments} "
            + " ".join(_fmt(v) for v in (*w.p1, *w.p2, w.diameter / 2.0))
        )
    if dk.vtag is not None:
        # EZNEC's export rebuilds the virtual wire 100 λ out, one segment per
        # virtual segment plus one, 0.001 λ per segment along each axis, of
        # radius 1e-4 λ; the NEC reader reads it as circuit nodes (AK#1577).
        # A first-class virtual node is AK#1966.
        lam = dk.lam
        ns = len(m.virtual_labels) + 1
        a = (100 * lam, 100 * lam, 101 * lam)
        b = tuple(v + 0.001 * lam * ns for v in a)
        dk.cards.append(
            f"GW {dk.vtag} {ns} " + " ".join(_fmt(v) for v in (*a, *b, 1e-4 * lam))
        )


def _insulation(dk: _Deck, deck: NecDeck) -> NecDeck:
    m = dk.m
    out = []
    for k, (eps, th, tand) in enumerate(m.insulation, 1):
        if th == 0:
            continue
        if th < 0 or eps < 1:
            raise EzMalformed(
                m.name, f"wire {k} insulation", f"thickness {th} m, eps_r {eps}"
            )
        if tand:
            raise EzNotRepresentable(
                m.name,
                f"wire {k} insulation",
                f"a jacket with loss tangent {tand:g} (a jacket here is lossless)",
            )
        if eps == 1:
            continue  # air: no jacket
        out.append((k - 1, (m.wires[k - 1].diameter / 2.0 + th, eps)))
    if out:
        dk.notes.append(
            f"{len(out)} insulated wire{'s' if len(out) != 1 else ''}: each wears a jacket of "
            "the file's thickness and permittivity."
        )
    return replace(deck, wire_insulation=tuple(out)) if out else deck


def _attach_customs(m: EzModel, dk: _Deck, deck: NecDeck) -> NecDeck:
    """Put each placeholder card's element on the `NecLoad` / `NecNT` it
    became, checking the reader kept the cards' order and sites."""
    if len(deck.loads) != len(dk.ld) or len(deck.nts) != len(dk.nt):
        raise ValueError(
            f"{m.name}: internal: {len(dk.ld)} LD and {len(dk.nt)} NT cards were "
            f"written but {len(deck.loads)} loads and {len(deck.nts)} networks read back"
        )
    tag_of = [w.tag for w in deck.wires]
    loads = []
    for ld, (tag, seg, custom) in zip(deck.loads, dk.ld, strict=True):
        if tag_of[ld.wire] != tag or (seg > 0 and ld.seg != seg):
            raise ValueError(
                f"{m.name}: internal: a load card read back at another site"
            )
        loads.append(replace(ld, custom=custom) if custom is not None else ld)
    nts = []
    for nt, (t1, s1, t2, s2, custom) in zip(deck.nts, dk.nt, strict=True):
        if (tag_of[nt.wire_a], tag_of[nt.wire_b]) != (t1, t2) or any(
            want > 0 and got != want for got, want in ((nt.seg_a, s1), (nt.seg_b, s2))
        ):
            raise ValueError(
                f"{m.name}: internal: a network card read back at another site"
            )
        nts.append(replace(nt, custom=custom) if custom is not None else nt)
    return replace(deck, loads=tuple(loads), nts=tuple(nts))


def _check_limits(m: EzModel, limits: GeometryLimits | None) -> None:
    if limits is None:
        return
    n_seg = sum(w.segments for w in m.wires)
    limits.check(len(m.wires), n_seg, m.name)


def read_ez(
    raw: bytes,
    *,
    name: str = "EZNEC model",
    limits: GeometryLimits | None = None,
    accept_guesses: bool = False,
    reading: str | None = None,
) -> EzImport:
    """Read an ``.ez`` file's bytes into an `EzImport` (see the module
    docstring). Raises an `EzRefusal` (a ``ValueError``) naming the field for
    anything the import will not read, and ``GeometryLimitError`` when the
    structure is over ``limits``.

    ``reading`` overrides where the file's engine setting puts sources and
    loads, as a ``.nec`` deck's dialect can be chosen: "nec2" or "nec4"
    (segment centres, EZNEC's own engines) or "nec5" (segment ends); None
    follows the file."""
    if reading not in (None, "nec2", "nec4", "nec5"):
        raise ValueError(f"{name}: reading must be nec2, nec4 or nec5, not {reading!r}")
    m = decode_ez(raw, name=name, accept_guesses=accept_guesses)
    _check_limits(m, limits)
    nec5 = m.nec5 if reading is None else reading == "nec5"
    dk = _Deck(m, nec5)
    dialect = "nec5" if nec5 else "nec2"
    head = [
        f"CM {m.title}" if m.title else "CM EZNEC model",
        f"CM read from {_one_line(name)} (EZNEC .ez)",
        "CE",
    ]
    _wire_cards(dk)
    dk.cards.append(f"GE {0 if m.ground == 'free' else 1}")
    _load_cards(dk)
    _line_cards(dk)
    _loss_cards(dk)
    dk.cards.append(f"FR 0 1 0 0 {_fmt(m.freq_mhz)} 0")
    method, ground_word = _ground_cards(dk)
    _source_cards(dk)
    _network_cards(dk)
    dk.cards.append("EN")
    # The placeholder comments go into the card list where their cards are;
    # keep the deck's CM block at the head, as NEC requires.
    body = [c for c in dk.cards if not c.startswith("CM ")]
    marks = [c for c in dk.cards if c.startswith("CM ")]
    nec_text = "\n".join(head[:-1] + marks + head[-1:] + body) + "\n"

    deck_limits = None
    if limits is not None:
        deck_limits = GeometryLimits(
            max_segments=limits.max_segments,
            max_wires=limits.max_wires + 1,  # the rebuilt virtual wire
            note=limits.note,
        )
    try:
        deck = parse_nec(
            nec_text, name=name, network=True, limits=deck_limits, dialect=dialect
        )
    except GeometryLimitError:
        raise
    except ValueError as e:
        raise ValueError(f"{name}: the model cannot be built here: {e}") from None
    deck = _attach_customs(m, dk, deck)
    deck = _insulation(dk, deck)
    try:
        # Built once here, so a model the port model cannot host is refused
        # when it opens, not at its first solve.
        deck.wire_tuples(specs=True)
        deck.network()
    except ValueError as e:
        raise ValueError(
            f"{name}: this model's sources and loads cannot be placed here: {e}"
        ) from None
    deck = replace(
        deck,
        dialect="ez",
        dialect_reason="an EZNEC .ez model",
        dialect_detected="ez",
        dialect_detected_reason="an EZNEC .ez model",
        dialect_chosen=None,
    )
    if reading is None:
        ext_kernel = m.engine is not None and m.engine[0] in (
            _ENGINE_NEC4,
            _ENGINE_NEC5,
        )
    else:
        ext_kernel = reading in ("nec4", "nec5")
    notes = _notes(m, dk, deck, reading)
    ground = deck.ground_spec
    return EzImport(
        deck=deck,
        model=m,
        freq_mhz=m.freq_mhz,
        ground=ground,
        ground_method=method or None,
        ground_word=ground_word,
        notes=tuple(notes),
        nec_text=nec_text,
        title=m.title,
        extended_kernel=ext_kernel,
    )


def _notes(m: EzModel, dk: _Deck, deck: NecDeck, reading: str | None) -> list[str]:
    out = []
    engine = f" ({m.engine[1]})" if m.engine and m.engine[1] else ""
    if reading is not None:
        how = "as chosen" + (
            "; the file's engine setting reads it at segment ends"
            if m.nec5
            else "; the file's engine setting reads it at segment centres"
        )
    elif m.nec5:
        how = "as EZNEC's NEC-5 engine reads it" + engine
    else:
        how = "as EZNEC's own engines read it" + engine
    if dk.nec5:
        out.append(
            f"Read {how}: sources, loads and lines connect at segment ends, at "
            "the segment EZNEC's position lands on."
        )
    else:
        out.append(
            f"Read {how}: sources, loads and lines sit at the centre of the "
            "segment EZNEC's position lands on."
        )
    if m.program:
        out.append(f"Written by {m.program}.")
    n_seg = sum(w.segments for w in m.wires)
    out.append(
        f"{len(m.wires)} wire{'s' if len(m.wires) != 1 else ''}, {n_seg} segments, "
        f"at {m.freq_mhz:g} MHz."
    )
    if m.virtual_labels:
        out.append(
            f"{len(m.virtual_labels)} virtual segment{'s' if len(m.virtual_labels) != 1 else ''} "
            "rebuilt as EZNEC's export does, on a wire far away that the import reads "
            "as circuit nodes."
        )
    if dk.fixed:
        out.append(
            "Held at their model-frequency values at every frequency (how they "
            "vary with frequency is not defined): " + "; ".join(dk.fixed) + "."
        )
    fixed_nt = deck.fixed_frequency_note()
    if fixed_nt:
        out.append(fixed_nt)
    out.extend(dk.notes)
    guesses = [*m.guesses, *dk.guesses]
    if guesses:
        out.append(
            "Readings taken on request (the format leaves them undefined): "
            + "; ".join(guesses)
            + "."
        )
    out.extend(m.warnings)
    return out


def ez_source_view(raw: bytes, name: str, reading: str | None = None) -> str:
    """What the Files view shows for an ``.ez``: the NEC cards it was read
    into (the file itself is binary), or why it was refused."""
    try:
        imp = read_ez(
            raw, name=name, accept_guesses=accept_guesses_from_env(), reading=reading
        )
    except ValueError as e:
        return (
            f"CM {name} is an EZNEC .ez file (binary); it was not read:\nCM {e}\nEN\n"
        )
    return imp.nec_text
