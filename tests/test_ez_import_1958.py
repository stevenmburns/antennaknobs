"""EZNEC ``.ez`` models open like decks (AK#1958).

The fixtures here are written by this module's own small ``.ez`` writer
(`ez_file`): synthetic, minimal models laid out the way the importer reads
them. A writer and a reader that share one misunderstanding agree with each
other, so the real-file tests at the bottom read EZNEC-written files that
their author licensed for reuse (``fixtures/ez_lonney9_1958``, MIT; see its
NOTICE). The comparisons against EZNEC's own ``.nec`` exports use files that
are not ours to publish and live in `test_ez_oracles_1958.py`, which skips
without them.

What is pinned, by layer:

* the reader: the record layout, the version gate, each block, positions;
* the four refusals, kept apart -- an unknown version / block / revision, a
  reading the format leaves undefined (refused unless asked for), something
  not representable here, a self-contradicting file -- and a display-only
  oddity that is only a warning;
* typed loads, lines, stubs and networks that a frequency sweep evaluates at
  every frequency, each against a twin holding that frequency's impedance;
* the virtual-segment wire, rebuilt as EZNEC's export does and read as nodes;
* wire loss, insulation and ground;
* the routes: the CLI's @file, the designs folder, the hosted /deck.
"""

from __future__ import annotations

import cmath
import math
import struct
from pathlib import Path

import numpy as np
import pytest

from antennaknobs import ez_import, network
from antennaknobs.engines import MomwireEngine
from antennaknobs.ez_import import (
    EzMalformed,
    EzNotRepresentable,
    EzUndefined,
    EzUnknownFormat,
    decode_ez,
    read_ez,
)
from antennaknobs.file_designs import builder_from_file, builder_from_text
from antennaknobs.nec_import import GeometryLimitError, GeometryLimits

FIXTURES = Path(__file__).parent / "fixtures" / "ez_lonney9_1958"


# --------------------------------------------------------------------------
# A minimal .ez writer
# --------------------------------------------------------------------------


def _block(typ: int, rev: int, body: bytes) -> bytes:
    return struct.pack("<hiB", typ, 7 + len(body), rev) + body


def _put(buf: bytearray, off: int, fmt: str, *vals) -> None:
    struct.pack_into("<" + fmt, buf, off, *vals)


def ez_file(
    wires,
    *,
    freq=14.2,
    title="test",
    sources=((1, 50.0, 1.0, 0.0, "V"),),
    loads=(),
    lines=(),
    ground="F",
    analysis="H",
    media=None,
    wrho=0.0,
    wmu=1.0,
    load_type="Z",
    lnet_type="Z",
    vercode=50,
    pgm=70_000_004,
    blocks=(),
    counts=None,
    ck=1304,
    units="M",
    hag="",
    plot_type="A",
    nr=0,
) -> bytes:
    """An .ez from its parts.

    ``wires``: (x1, y1, z1, x2, y2, z2, diameter, segments). ``sources``:
    (wire, %, rms, phase deg, type). ``loads``: dicts with wire, pct and one
    of z=(R, X), rlc=(type, R, L, C, F), laplace=(num6, den6); conn. ``lines``:
    (wire1, %1, wire2, %2, z0, length, vf). ``media``: [(sigma, eps_r)].
    ``counts``: (nx, nn, nl, nvirt) for the network blocks in ``blocks``."""
    media = list(
        media if media is not None else ([(0.005, 13.0)] if ground == "R" else [])
    )
    n = max(len(media), len(wires), len(sources), len(loads), len(lines))
    h = bytearray(170)
    _put(h, 0x00, "h", min(n, 32767))
    _put(h, 0x02, "h", len(media))
    h[0x04] = ord("R")
    _put(h, 0x05, "f", freq)
    h[0x09] = ord("A")
    _put(h, 0x0E, "f", 5.0)
    h[0x12:0x30] = title.encode("latin-1").ljust(30)[:30]
    _put(h, 0x30, "h", len(wires))
    _put(h, 0x32, "h", len(sources))
    _put(h, 0x34, "h", len(loads))
    h[0x36] = ord(ground)
    _put(h, 0x37, "h", nr)
    _put(h, 0x3D, "h", -1)
    _put(h, 0x3F, "h", ck)
    h[0x41] = ord(units)
    h[0x42], h[0x43] = ord("F"), ord("T")
    _put(h, 0x44, "f", 1304.0)
    h[0x50] = ord("Z")
    h[0x59] = ord(lnet_type)
    _put(h, 0x5A, "f", 5.0)
    _put(h, 0x62, "f", wrho)
    _put(h, 0x66, "f", wmu)
    _put(h, 0x6E, "f", 75.0)
    _put(h, 0x72, "h", vercode)
    if load_type:
        h[0x75] = ord(load_type)
    _put(h, 0x76, "h", 1)
    _put(h, 0x78, "h", len(lines))
    h[0x7A] = ord(plot_type)
    h[0x7B] = ord(analysis) if analysis else 0
    _put(h, 0x7C, "i", n)
    _put(h, 0x80, "i", len(wires))
    _put(h, 0x88, "f", 5.0)
    _put(h, 0x90, "i", pgm)
    _put(h, 0x94, "f", 40.0)
    nx, nn, nl, nv = counts or (0, 0, 0, 0)
    _put(h, 0x98, "hhhh", nx, nn, nl, nv)
    if hag:
        h[0xA2] = ord(hag)

    recs = bytearray(170 * n)
    for k in range(n):
        r = memoryview(recs)[170 * k : 170 * (k + 1)]
        if k < len(media):
            struct.pack_into("<ff", r, 0, *media[k])
        if k < len(wires):
            *c, dia, nseg = wires[k]
            struct.pack_into("<6ffhh", r, 16, *c, dia, -1, nseg)
        if k < len(sources):
            w, p, mag, ph, typ = sources[k]
            struct.pack_into("<hfffc", r, 48, w, p, mag, ph, typ.encode())
        if k < len(loads):
            ld = loads[k]
            R, X = ld.get("z", (0.0, 0.0))
            struct.pack_into("<hfff", r, 63, ld["wire"], ld["pct"], R, X)
            if "laplace" in ld:
                num, den = ld["laplace"]
                struct.pack_into("<12f", r, 77, *num, *den)
            r[149] = ord(ld.get("conn", "S"))
            if "rlc" in ld:
                t, R, L, C, F = ld["rlc"]
                struct.pack_into("<cffff", r, 150, t.encode(), R, L, C, F)
        if k < len(lines):
            w1, p1, w2, p2, z0, ln, vf = lines[k]
            struct.pack_into("<hfhffff", r, 125, w1, p1, w2, p2, z0, ln, vf)
    tail = bytes(340)
    return bytes(h) + bytes(recs) + tail + b"".join(_block(*b) for b in blocks)


# Block bodies.


def loss_block(rows):
    return (
        13,
        1,
        struct.pack("<i", len(rows)) + b"".join(struct.pack("<ff", *r) for r in rows),
    )


def insulation_block(rows):
    return (
        12,
        1,
        struct.pack("<i", len(rows)) + b"".join(struct.pack("<fff", *r) for r in rows),
    )


def line_loss_block(rows):
    """rows: (dB/m, loss frequency MHz) per line."""
    return (
        14,
        1,
        struct.pack("<i", len(rows))
        + b"".join(struct.pack("<f", r[0]) for r in rows)
        + b"".join(struct.pack("<f", r[1]) for r in rows),
    )


def _port_arrays(ports):
    """ports: [((w1, p1), (w2, p2)), ...] -> the wires and positions arrays,
    with the dummy entry 0 first."""
    allp = [((0, 0.0), (0, 0.0)), *ports]
    w = b"".join(struct.pack("<ii", a[0], b[0]) for a, b in allp)
    p = b"".join(struct.pack("<ff", a[1], b[1]) for a, b in allp)
    return w, p


def transformer_block(xs):
    """xs: [((w1, p1), (w2, p2), z1, z2)]."""
    w, p = _port_arrays([(a, b) for a, b, *_ in xs])
    z = struct.pack("<ff", 0, 0) + b"".join(
        struct.pack("<ff", z1, z2) for *_, z1, z2 in xs
    )
    return (15, 1, struct.pack("<i", len(xs)) + w + p + z)


def ynet_block(ns):
    """ns: [((w1, p1), (w2, p2), y11, y12, y22, normrev)]."""
    w, p = _port_arrays([(a, b) for a, b, *_ in ns])
    y = bytes(28) + b"".join(
        struct.pack(
            "<7f", y11.real, y11.imag, y12.real, y12.imag, y22.real, y22.imag, nr
        )
        for _a, _b, y11, y12, y22, nr in ns
    )
    return (16, 1, struct.pack("<i", len(ns)) + w + p + y)


def lnet_block(ns, rlc=None):
    """ns: [((w1, p1), (w2, p2), zs, zp)]; rlc: per network
    ((Rs, Ls, Cs, Fs, ts), (Rp, Lp, Cp, Fp, tp))."""
    w, p = _port_arrays([(a, b) for a, b, *_ in ns])
    z = bytes(16) + b"".join(
        struct.pack("<4f", zs.real, zs.imag, zp.real, zp.imag) for *_, zs, zp in ns
    )
    body = struct.pack("<i", len(ns)) + w + p + z
    if rlc is None:
        return (17, 2, body + struct.pack("<i", 0))
    vals = bytes(32) + b"".join(
        struct.pack("<8f", s[0], q[0], s[1], q[1], s[2], q[2], s[3], q[3])
        for s, q in rlc
    )
    types = b"\0\0" + b"".join((s[4] + q[4]).encode() for s, q in rlc)
    return (17, 2, body + struct.pack("<i", len(ns)) + vals + types)


def virtual_block(labels, wire):
    return (
        18,
        1,
        struct.pack("<ii", len(labels), wire)
        + b"".join(struct.pack("<i", x) for x in labels),
    )


def info_block(program="TestWriter", version="1.0", rev=2):
    if rev == 1:
        return (101, 1, b"\x02\x00\x00\x00 an older layout, not described anywhere")

    def s(t):
        return struct.pack("<i", len(t)) + t.encode()

    return (
        101,
        2,
        struct.pack("<id", 2000, 45000.0)
        + s(program)
        + s(version)
        + struct.pack("<i", 1)
        + s(""),
    )


def engine_block(code, name):
    return (
        102,
        2,
        struct.pack("<ii", code, len(name)) + name.encode() + struct.pack("<i", 0),
    )


# A 20 m dipole, 10.3 m long, 2 mm diameter, 21 segments, along y at z = 10.
F0 = 14.2
DIPOLE = [(0.0, -5.15, 10.0, 0.0, 5.15, 10.0, 0.002, 21)]


def _z(cls, freq=None) -> complex:
    b = cls()
    if freq is not None:
        b.freq = freq
    return complex(MomwireEngine(b, ground=cls.file_ground).impedance()[0])


def _open(raw: bytes, name="test.ez", **kw):
    return builder_from_text(name, raw.decode("latin-1"), **kw)


# --------------------------------------------------------------------------
# The reader
# --------------------------------------------------------------------------


def test_a_dipole_opens_as_a_deck_with_the_source_at_its_segment_centre():
    imp = read_ez(ez_file(DIPOLE), name="dp.ez")
    deck = imp.deck
    assert len(deck.wires) == 1 and deck.wires[0].n_seg == 21
    assert deck.wires[0].radius == pytest.approx(0.001)
    (feed,) = deck.feeds
    # 50 % of 21 segments lands on segment 11 (EZNEC's ceiling rule), at its
    # centre: EZNEC's own engines are NEC-2/NEC-4 cores.
    assert (feed.seg, feed.edge, feed.current) == (11, 0, False)
    assert feed.voltage == pytest.approx(math.sqrt(2.0))  # RMS 1 V in the file
    assert imp.ground is None and imp.freq_mhz == pytest.approx(F0)
    assert "centre of the segment" in imp.notes[0]
    cls = _open(ez_file(DIPOLE), "dp.ez")
    z = _z(cls)
    assert 60 < z.real < 90


def test_stored_singles_are_read_as_eznec_prints_them():
    m = decode_ez(ez_file([(0.0, 0.0, 7.62, 0.0, 0.0, 0.0, 0.0005588, 9)]))
    # 7.62 and 0.0005588 are not exact in a single; EZNEC prints 7 digits.
    assert m.wires[0].p1 == (0.0, 0.0, 7.62)
    assert m.wires[0].diameter == 0.0005588


def test_position_lands_on_the_ceiling_segment_and_a_zero_on_segment_one():
    raw = ez_file(
        DIPOLE,
        sources=((1, 0.0, 1.0, 0.0, "V"),),
        loads=({"wire": 1, "pct": 100.0, "z": (5.0, 0.0)},),
    )
    deck = read_ez(raw).deck
    assert deck.feeds[0].seg == 1
    assert deck.loads[0].seg == 21


def test_the_nec5_engine_setting_reads_at_segment_ends():
    raw = ez_file(
        DIPOLE,
        loads=({"wire": 1, "pct": 0.0, "z": (5.0, 0.0)},),
        blocks=[engine_block(8, "Ext NEC-5")],
    )
    imp = read_ez(raw)
    assert imp.extended_kernel
    assert imp.deck.feeds[0].edge != 0
    # A 0 % load sits at the wire's end 1 (NEC-5's segment -1, as EZNEC's
    # NEC-5 export writes it).
    ld = imp.deck.loads[0]
    assert (ld.seg, ld.edge) == (1, 1)
    assert "segment ends" in imp.notes[0] and "Ext NEC-5" in imp.notes[0]


def test_the_reading_can_be_chosen_like_a_deck_dialect():
    raw = ez_file(DIPOLE)
    imp = read_ez(raw, reading="nec5")
    assert imp.deck.feeds[0].edge != 0
    assert "as chosen" in imp.notes[0]
    assert read_ez(raw, reading="nec4").extended_kernel
    assert not read_ez(raw).extended_kernel
    cls = _open(raw, dialect="nec5")
    assert cls.file_deck_parsed.feeds[0].edge != 0


def test_a_nec4_engine_setting_keeps_centres_and_the_extended_kernel():
    imp = read_ez(ez_file(DIPOLE, blocks=[engine_block(4, "EZCalc4D_70_x64.EXE")]))
    assert imp.deck.feeds[0].edge == 0 and imp.extended_kernel


# --------------------------------------------------------------------------
# Versions and blocks
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kw", "named"),
    [
        ({"vercode": 10}, "version code 10"),
        ({"pgm": 700_007}, "program version word 700007"),
        ({"pgm": 80_000_001}, "program version word 80000001"),
    ],
)
def test_an_unknown_file_version_is_refused_by_name(kw, named):
    for guesses in (False, True):
        with pytest.raises(EzUnknownFormat, match=named):
            read_ez(ez_file(DIPOLE, **kw), accept_guesses=guesses)


def test_an_unknown_block_type_is_refused_by_name():
    with pytest.raises(EzUnknownFormat, match="block type 77"):
        read_ez(ez_file(DIPOLE, blocks=[(77, 1, b"\x00" * 8)]))


@pytest.mark.parametrize("guesses", [False, True])
def test_an_unknown_block_revision_is_refused_by_name(guesses):
    rows = [(1.7e-8, 1.0)]
    with pytest.raises(EzUnknownFormat, match=r"block 13 \(wire loss\).*revision 2"):
        read_ez(
            ez_file(DIPOLE, blocks=[(13, 2, loss_block(rows)[2])]),
            accept_guesses=guesses,
        )
    with pytest.raises(EzUnknownFormat, match=r"block 17 \(L network\).*revision 1"):
        read_ez(ez_file(DIPOLE, blocks=[(17, 1, b"\0" * 40)]), accept_guesses=guesses)


def test_info_block_revision_1_is_accepted_and_its_contents_skipped():
    imp = read_ez(ez_file(DIPOLE, blocks=[info_block(rev=1)]))
    assert any("info block is revision 1" in n for n in imp.notes)


def test_info_block_revision_2_names_the_writer():
    imp = read_ez(ez_file(DIPOLE, blocks=[info_block("EZNEC Pro/2+", "7.0.4")]))
    assert any(
        n.startswith("Written by EZNEC Pro/2+ 7.0.4, saved 2023-03-15")
        for n in imp.notes
    )


def test_a_negative_custom_block_is_skipped_by_its_length():
    # Its body looks like a block header for an unknown type: never read.
    body = struct.pack("<hiB", 77, 11, 9) + b"junk"
    raw = ez_file(DIPOLE, blocks=[(-100, 2, body), info_block()])
    imp = read_ez(raw)
    assert any("custom block" in n for n in imp.notes)
    assert len(imp.deck.wires) == 1


# --------------------------------------------------------------------------
# The other refusals, kept apart
# --------------------------------------------------------------------------

TRAP = {"wire": 1, "pct": 75.0, "rlc": ("T", 2.0, 2e-6, 60e-12, 0.0)}


def test_an_undefined_reading_is_refused_unless_asked_for_and_then_listed():
    raw = ez_file(DIPOLE, loads=(TRAP,), load_type="R")
    with pytest.raises(EzUndefined) as err:
        read_ez(raw)
    assert err.value.kind == "undefined" and "trap" in str(err.value)
    assert ez_import.ACCEPT_GUESSES_ENV in str(err.value)
    imp = read_ez(raw, accept_guesses=True)
    assert any("Readings taken on request" in n and "trap" in n for n in imp.notes)


def test_the_environment_switch_opts_in_through_the_file_loader(tmp_path, monkeypatch):
    p = tmp_path / "trap.ez"
    p.write_bytes(ez_file(DIPOLE, loads=(TRAP,), load_type="R"))
    monkeypatch.delenv(ez_import.ACCEPT_GUESSES_ENV, raising=False)
    with pytest.raises(EzUndefined):
        builder_from_file(str(p))
    monkeypatch.setenv(ez_import.ACCEPT_GUESSES_ENV, "1")
    assert builder_from_file(str(p))().freq == pytest.approx(F0)


def test_an_undefined_value_with_no_reading_stays_refused_on_request():
    raw = ez_file(
        DIPOLE, loads=({"wire": 1, "pct": 75.0, "z": (5.0, 0.0), "conn": "P"},)
    )
    for guesses in (False, True):
        with pytest.raises(EzUndefined, match="parallel-connected"):
            read_ez(raw, accept_guesses=guesses)


@pytest.mark.parametrize(
    ("kw", "named"),
    [
        ({"ground": "R", "media": [(0.005, 13.0), (0.01, 5.0)]}, "2 ground media"),
        ({"ground": "R", "nr": 8}, "8 radials"),
        (
            {"blocks": [(31, 1, struct.pack("<ii6f", 1, 1, 10, 0, 0, 0, 1, 0))]},
            "plane wave",
        ),
        ({"blocks": [insulation_block([(3.5, 0.001, 0.01)])]}, "loss tangent"),
        ({"wrho": 1e-7, "wmu": 200.0}, "permeability 200"),
    ],
)
def test_what_has_no_element_here_is_refused_as_not_representable(kw, named):
    with pytest.raises(EzNotRepresentable, match=named) as err:
        read_ez(ez_file(DIPOLE, **kw), accept_guesses=True)
    assert err.value.kind == "not-representable"


@pytest.mark.parametrize(
    ("raw", "named"),
    [
        (ez_file(DIPOLE, ck=1303), "integrity word"),
        (ez_file(DIPOLE)[:200], "length"),
        (ez_file(DIPOLE, blocks=[loss_block([(0.0, 1.0), (0.0, 1.0)])]), "wire loss"),
        (ez_file(DIPOLE) + b"\x0d\x00\x40", "cut short"),
        (ez_file(DIPOLE, sources=((3, 50.0, 1.0, 0.0, "V"),)), "wire 3"),
    ],
    ids=["integrity", "short", "loss-count", "block-cut", "source-wire"],
)
def test_a_file_that_contradicts_itself_is_malformed(raw, named):
    with pytest.raises(EzMalformed, match=named):
        read_ez(raw)


def test_a_display_only_oddity_is_a_warning_not_a_refusal():
    imp = read_ez(ez_file(DIPOLE, units="Q", plot_type="Z"))
    assert any("Display settings" in n and "display units 'Q'" in n for n in imp.notes)


def test_limits_bound_the_structure_before_it_is_built():
    raw = ez_file([(0.0, -5.0, 10.0, 0.0, 5.0, 10.0, 0.002, 400)])
    with pytest.raises(GeometryLimitError):
        read_ez(raw, limits=GeometryLimits(max_segments=300, max_wires=10))


# --------------------------------------------------------------------------
# Typed loads follow frequency
# --------------------------------------------------------------------------

SWEEP = (12.0, 14.2, 16.5)


def _series(R, L, C, w):
    z = complex(R, w * L)
    return z + (1 / (1j * w * C) if C else 0)


def _parallel(R, L, C, w):
    y = (1 / R if R else 0) + (1 / (1j * w * L) if L else 0) + (1j * w * C if C else 0)
    return 1 / y


def _trap(R, L, C, w):
    a, b = complex(R, w * L), 1 / (1j * w * C)
    return a * b / (a + b)


def _laplace_z(num, den, w):
    s = 1j * w
    return sum(c * s**i for i, c in enumerate(num)) / sum(
        c * s**i for i, c in enumerate(den)
    )


LOADS = {
    "series RLC": (
        {"rlc": ("S", 10.0, 1.5e-6, 100e-12, 0.0)},
        False,
        lambda f, w: _series(10.0, 1.5e-6, 100e-12, w),
    ),
    "parallel RLC": (
        {"rlc": ("P", 2000.0, 1e-6, 50e-12, 0.0)},
        False,
        lambda f, w: _parallel(2000.0, 1e-6, 50e-12, w),
    ),
    "trap": (
        {"rlc": ("T", 2.0, 2e-6, 60e-12, 0.0)},
        True,
        lambda f, w: _trap(2.0, 2e-6, 60e-12, w),
    ),
    "variable R": (
        {"rlc": ("S", 8.0, 1e-6, 0.0, 10.0)},
        True,
        lambda f, w: _series(8.0 * math.sqrt(f / 10.0), 1e-6, 0.0, w),
    ),
    "Laplace": (
        {"laplace": ((5.0, 2e-6, 0, 0, 0, 0), (1.0, 0, 0, 0, 0, 0))},
        True,
        lambda f, w: _laplace_z((5.0, 2e-6, 0, 0, 0, 0), (1.0, 0, 0, 0, 0, 0), w),
    ),
}


@pytest.mark.parametrize("form", list(LOADS))
def test_a_typed_load_is_evaluated_at_every_frequency_of_a_sweep(form, monkeypatch):
    """The load's impedance at each frequency equals a fixed R + jX twin
    holding exactly that frequency's value -- and moves across the sweep."""
    spec, guesses, zf = LOADS[form]
    kind = "L" if "laplace" in spec else "R"
    w0 = 2 * math.pi * F0 * 1e6
    z0 = zf(F0, w0)
    load = {"wire": 1, "pct": 75.0, "z": (float(z0.real), float(z0.imag)), **spec}
    raw = ez_file(DIPOLE, loads=(load,), load_type=kind)
    imp = read_ez(raw, accept_guesses=guesses)
    if guesses:
        with pytest.raises(EzUndefined):
            read_ez(raw)
        monkeypatch.setenv(ez_import.ACCEPT_GUESSES_ENV, "1")
    cls = _open(raw)
    assert imp.deck.loads
    zs = []
    for f in SWEEP:
        zl = zf(f, 2 * math.pi * f * 1e6)
        twin = _open(
            ez_file(DIPOLE, loads=({"wire": 1, "pct": 75.0, "z": (zl.real, zl.imag)},)),
            "twin.ez",
        )
        got, want = _z(cls, f), _z(twin, f)
        # The twin stores its R + jX as singles: agreement to ~1e-7.
        assert got == pytest.approx(want, rel=1e-6), (form, f)
        zs.append(got)
    held = _open(
        ez_file(DIPOLE, loads=({"wire": 1, "pct": 75.0, "z": (z0.real, z0.imag)},)),
        "held.ez",
    )
    assert abs(_z(held, SWEEP[0]) - zs[0]) > 1e-3 * abs(zs[0])  # not collapsed to f0


def test_plain_rlc_loads_are_the_decks_own_frequency_dependent_load():
    raw = ez_file(
        DIPOLE,
        loads=({"wire": 1, "pct": 75.0, **LOADS["series RLC"][0]},),
        load_type="R",
    )
    (br,) = [
        b for b in read_ez(raw).deck.network().branches if isinstance(b, network.Load)
    ]
    assert (br.r, br.l, br.c, br.parallel) == (
        10.0,
        pytest.approx(1.5e-6),
        pytest.approx(100e-12),
        False,
    )


def test_a_variable_r_given_at_the_model_frequency_is_held_there_unless_asked():
    spec = {"wire": 1, "pct": 75.0, "rlc": ("S", 8.0, 1e-6, 0.0, F0)}
    imp = read_ez(ez_file(DIPOLE, loads=(spec,), load_type="R"))
    assert any(
        "Held at their model-frequency values" in n and "R of 8" in n for n in imp.notes
    )
    elsewhere = {**spec, "rlc": ("S", 8.0, 1e-6, 0.0, 7.0)}
    with pytest.raises(EzUndefined, match="given at 7 MHz"):
        read_ez(ez_file(DIPOLE, loads=(elsewhere,), load_type="R"))


def test_a_stored_impedance_that_disagrees_with_the_parts_is_refused():
    spec = {
        "wire": 1,
        "pct": 75.0,
        "z": (10.0, 999.0),
        "rlc": ("S", 10.0, 1.5e-6, 100e-12, 0.0),
    }
    with pytest.raises(EzUndefined, match="stores"):
        read_ez(ez_file(DIPOLE, loads=(spec,), load_type="R"))


def test_a_fixed_r_jx_load_holds_at_every_frequency():
    raw = ez_file(DIPOLE, loads=({"wire": 1, "pct": 75.0, "z": (5.0, -40.0)},))
    (br,) = [
        b for b in read_ez(raw).deck.network().branches if isinstance(b, network.Load)
    ]
    assert br.z == complex(5.0, -40.0)


# --------------------------------------------------------------------------
# Lines, stubs and networks
# --------------------------------------------------------------------------

# Two parallel dipoles 5 m apart, fed at the first.
PAIR = [
    (0.0, -5.15, 10.0, 0.0, 5.15, 10.0, 0.002, 21),
    (5.0, -5.15, 10.0, 5.0, 5.15, 10.0, 0.002, 21),
]


def test_a_lossless_line_keeps_its_reversal_length_and_velocity_factor():
    raw = ez_file(PAIR, lines=((1, 50.0, 2, 50.0, -75.0, 6.0, 0.66),))
    (tl,) = read_ez(raw).deck.tls
    assert tl.transposed and tl.z0 == 75.0
    assert tl.length == pytest.approx(6.0 / 0.66)


@pytest.mark.parametrize("stub", ["short", "open"])
def test_a_stub_follows_frequency(stub):
    code = -1 if stub == "short" else -2
    length, vf, z0 = 2.0, 0.8, 50.0
    raw = ez_file(DIPOLE, lines=((1, 75.0, code, 0.0, z0, length, vf),))
    cls = _open(raw)
    for f in SWEEP:
        bl = 2 * math.pi * f * 1e6 / (vf * 299_792_458.0) * length
        zl = 1j * z0 * math.tan(bl) if stub == "short" else -1j * z0 / math.tan(bl)
        twin = _open(
            ez_file(DIPOLE, loads=({"wire": 1, "pct": 75.0, "z": (zl.real, zl.imag)},))
        )
        assert _z(cls, f) == pytest.approx(_z(twin, f), rel=1e-7), (stub, f)


def test_a_lossy_line_is_held_at_the_model_frequency_and_flagged():
    raw = ez_file(
        PAIR,
        lines=((1, 50.0, 2, 50.0, 50.0, 6.0, 0.66),),
        blocks=[line_loss_block([(0.02, F0)])],
    )
    deck = read_ez(raw).deck
    assert deck.fixed_frequency_nts() == (1,)
    assert any("NT card #1" in n for n in read_ez(raw).notes)


def test_a_lossy_line_follows_root_f_on_request():
    raw = ez_file(
        PAIR,
        lines=((1, 50.0, 2, 50.0, 50.0, 6.0, 0.66),),
        blocks=[line_loss_block([(0.02, 7.0)])],
    )
    with pytest.raises(EzUndefined, match="given at 7 MHz"):
        read_ez(raw)
    deck = read_ez(raw, accept_guesses=True).deck
    assert deck.fixed_frequency_nts() == ()
    (br,) = [
        b for b in deck.network().branches if isinstance(b, network.TouchstoneTwoPort)
    ]
    for f in SWEEP:
        a = 0.02 / (20 / math.log(10)) * math.sqrt(f / 7.0)
        b = 2 * math.pi * f * 1e6 / (0.66 * 299_792_458.0)
        g, zc = complex(a, b), 50.0 * complex(1, -a / b)
        y11 = 1 / (zc * cmath.tanh(g * 6.0))
        y12 = -1 / (zc * cmath.sinh(g * 6.0))
        np.testing.assert_allclose(
            br.data.y_at(f * 1e6), [[y11, y12], [y12, y11]], rtol=1e-12
        )


def test_a_transformer_is_eznecs_ratio_behind_its_series_resistance():
    raw = ez_file(
        PAIR,
        lines=(),
        blocks=[transformer_block([((1, 50.0), (2, 50.0), 50.0, 200.0)])],
        counts=(1, 0, 0, 0),
    )
    (x,) = [
        b
        for b in read_ez(raw).deck.network().branches
        if isinstance(b, network.Transformer)
    ]
    assert x.n == pytest.approx(0.5) and x.r == pytest.approx(0.1)
    rev = ez_file(
        PAIR,
        blocks=[transformer_block([((1, 50.0), (2, 50.0), 50.0, -200.0)])],
        counts=(1, 0, 0, 0),
    )
    with pytest.raises(EzUndefined, match="reversed"):
        read_ez(rev)
    (x,) = [
        b
        for b in read_ez(rev, accept_guesses=True).deck.network().branches
        if isinstance(b, network.Transformer)
    ]
    assert x.n == pytest.approx(-0.5)


def test_a_y_network_is_its_fixed_admittance():
    y11, y12, y22 = 0.01 - 0.02j, -0.005 + 0.01j, 0.02 + 0.0j
    raw = ez_file(
        PAIR,
        blocks=[ynet_block([((1, 50.0), (2, 50.0), y11, y12, y22, 1.0)])],
        counts=(0, 1, 0, 0),
    )
    deck = read_ez(raw).deck
    (a,) = [b for b in deck.network().branches if isinstance(b, network.Admittance)]
    np.testing.assert_allclose(np.array(a.y), [[y11, y12], [y12, y22]], rtol=1e-6)
    assert deck.fixed_frequency_nts() == ()  # constant by definition, no advisory


def test_an_l_network_in_rx_form_writes_a_zero_resistance_as_one_milliohm():
    raw = ez_file(
        PAIR,
        blocks=[lnet_block([((1, 50.0), (2, 50.0), 0 + 30j, 0 - 200j)])],
        counts=(0, 0, 1, 0),
    )
    (a,) = [
        b
        for b in read_ez(raw).deck.network().branches
        if isinstance(b, network.Admittance)
    ]
    ya, yb = 1 / complex(1e-3, 30), 1 / complex(1e-3, -200)
    np.testing.assert_allclose(np.array(a.y), [[ya, -ya], [-ya, ya + yb]], rtol=1e-12)


def test_an_l_network_in_rlc_form_is_series_then_shunt_parts_that_follow_frequency():
    rlc = [((0.0, 1e-6, 0.0, 0.0, "S"), (0.0, 0.0, 200e-12, 0.0, "S"))]
    raw = ez_file(
        PAIR,
        lnet_type="R",
        blocks=[lnet_block([((1, 50.0), (2, 50.0), 0j, 0j)], rlc)],
        counts=(0, 0, 1, 0),
    )
    brs = read_ez(raw).deck.network().branches
    (tp,) = [b for b in brs if isinstance(b, network.TwoPort)]
    (sh,) = [b for b in brs if isinstance(b, network.Shunt)]
    assert (tp.r, tp.l, tp.c) == (1e-3, pytest.approx(1e-6), None)
    assert (sh.r, sh.l, sh.c, sh.parallel) == (
        1e-3,
        None,
        pytest.approx(200e-12),
        False,
    )
    # A parallel branch is a reading the format leaves undefined for networks.
    par = [((0.0, 1e-6, 0.0, 0.0, "S"), (500.0, 1e-6, 0.0, 0.0, "P"))]
    raw = ez_file(
        PAIR,
        lnet_type="R",
        blocks=[lnet_block([((1, 50.0), (2, 50.0), 0j, 0j)], par)],
        counts=(0, 0, 1, 0),
    )
    with pytest.raises(EzUndefined, match="parallel"):
        read_ez(raw)
    read_ez(raw, accept_guesses=True)


# --------------------------------------------------------------------------
# Virtual segments
# --------------------------------------------------------------------------


def test_the_virtual_wire_is_rebuilt_as_eznecs_export_does_and_read_as_nodes():
    """EZNEC stores virtual segments on an extra wire; segment k of it carries
    virtual segment number labels[k - 1]. The import rebuilds the wire 100 λ
    away with one segment per number in increasing order, as EZNEC's export
    does, and the NEC reader turns it into circuit nodes. Here a current
    source on virtual segment 7 drives a 1:1 transformer onto the dipole's
    centre: the driving point is the dipole's own Z plus the transformer's
    Z1/500 series resistance."""
    vwire = (100.0, 100.0, 100.0, 100.0, 100.0, 101.0, 0.001, 2)
    wires = [*DIPOLE, vwire]
    # Stored segment 1 -> number 7, stored segment 2 -> number 3 (out of
    # order, as one corpus writer stores them): rebuilt, 3 is segment 1 and 7
    # segment 2.
    raw = ez_file(
        wires,
        sources=((2, 25.0, 1.0, 0.0, "I"),),
        blocks=[
            transformer_block([((2, 25.0), (1, 50.0), 50.0, 50.0)]),
            virtual_block([7, 3], 2),
        ],
        counts=(1, 0, 0, 2),
    )
    imp = read_ez(raw)
    lam = 299_792_458.0 / (F0 * 1e6)
    gw = [ln for ln in imp.nec_text.splitlines() if ln.startswith("GW 2 ")]
    (vw,) = gw
    f = [float(x) for x in vw.split()[3:]]
    assert int(vw.split()[2]) == 3  # two numbers + 1
    assert f[:3] == pytest.approx([100 * lam, 100 * lam, 101 * lam])
    assert f[3] - f[0] == pytest.approx(0.003 * lam)
    assert [ln for ln in imp.nec_text.splitlines() if ln.startswith("EX ")] == [
        f"EX 6 2 2 0 {math.sqrt(2)!r} 0"
    ]
    deck = imp.deck
    assert deck.virtual_segment_wires == frozenset({1})
    assert len(deck.wire_tuples(specs=True)) == 1
    net = deck.network()
    (src,) = net.sources
    assert isinstance(src, network.DrivenCurrent)
    assert isinstance(net.ports[src.port], network.PortVirtual)
    z = _z(_open(raw))
    z_dip = _z(_open(ez_file(DIPOLE)))
    assert z == pytest.approx(z_dip + 0.1, rel=1e-6)
    assert any("virtual segments rebuilt" in n for n in imp.notes)


def test_a_position_on_the_virtual_wire_with_no_number_is_malformed():
    vwire = (100.0, 100.0, 100.0, 100.0, 100.0, 101.0, 0.001, 3)
    raw = ez_file(
        [*DIPOLE, vwire],
        sources=((2, 100.0, 1.0, 0.0, "I"),),
        blocks=[
            transformer_block([((2, 100.0), (1, 50.0), 50.0, 50.0)]),
            virtual_block([4, 5], 2),
        ],
        counts=(1, 0, 0, 2),
    )
    with pytest.raises(EzMalformed, match="no virtual segment number"):
        read_ez(raw)


# --------------------------------------------------------------------------
# Wire loss, insulation, ground
# --------------------------------------------------------------------------


def test_wire_loss_comes_from_the_model_wide_resistivity_without_the_block():
    deck = read_ez(ez_file(PAIR, wrho=1.72e-8)).deck
    assert deck.conductivity == pytest.approx(1 / 1.72e-8, rel=1e-6)


def test_the_per_wire_loss_block_overrides_the_model_wide_value():
    raw = ez_file(PAIR, wrho=1.72e-8, blocks=[loss_block([(2.65e-8, 1.0), (0.0, 1.0)])])
    deck = read_ez(raw).deck
    assert deck.conductivity is None
    assert dict(deck.wire_conductivity) == {0: pytest.approx(1 / 2.65e-8, rel=1e-6)}
    assert read_ez(ez_file(PAIR)).deck.conductivity is None  # zero = lossless


def test_insulation_becomes_the_wires_jacket():
    raw = ez_file(PAIR, blocks=[insulation_block([(3.5, 0.001, 0.0), (1.0, 0.0, 0.0)])])
    deck = read_ez(raw).deck
    assert deck.wire_insulation == ((0, (pytest.approx(0.002), pytest.approx(3.5))),)
    specs = deck.wire_tuples(specs=True)
    assert len(specs) == 2


@pytest.mark.parametrize(
    ("kw", "spec", "method", "word"),
    [
        ({"ground": "F"}, None, None, "free space"),
        ({"ground": "P"}, "pec", None, "perfect"),
        (
            {"ground": "R", "analysis": "H"},
            ("finite", 13.0, 0.005),
            "sommerfeld",
            "high accuracy",
        ),
        (
            {"ground": "R", "analysis": "M"},
            ("mininec", 13.0, 0.005),
            "mininec",
            "MININEC",
        ),
        (
            {"ground": "R", "analysis": "F"},
            ("finite", 13.0, 0.005),
            "sommerfeld",
            "high accuracy",
        ),
    ],
)
def test_the_ground_is_eznecs(kw, spec, method, word):
    imp = read_ez(ez_file(DIPOLE, **kw))
    assert imp.ground == spec and imp.ground_method == method
    assert word in imp.ground_word
    cls = _open(ez_file(DIPOLE, **kw))
    assert cls.file_ground == spec
    assert cls.default_params["ui_params"]["ground_card"] == imp.ground_word


def test_extended_high_accuracy_ground_is_a_reading():
    raw = ez_file(DIPOLE, ground="R", hag="X")
    with pytest.raises(EzUndefined, match="extended"):
        read_ez(raw)
    assert read_ez(raw, accept_guesses=True).ground_method == "sommerfeld"


# --------------------------------------------------------------------------
# The routes
# --------------------------------------------------------------------------


def test_the_cli_at_file_opens_an_ez(tmp_path):
    from antennaknobs.cli import get_builder

    p = tmp_path / "dp.ez"
    p.write_bytes(ez_file(DIPOLE))
    cls = get_builder(f"@{p}")
    assert cls.__name__ == "dp" and cls().freq == pytest.approx(F0)


def test_an_ez_in_the_designs_folder_is_a_design(tmp_path, monkeypatch):
    import antennaknobs.web.examples  # noqa: F401 -- bootstraps the registry
    from antennaknobs import user_designs
    from antennaknobs.web.examples import REGISTRY

    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    (tmp_path / "dp20.ez").write_bytes(ez_file(DIPOLE))
    try:
        assert [s for s, _ in user_designs.iter_design_files()] == ["dp20"]
        assert user_designs.resolve_user_design("dp20")().freq == pytest.approx(F0)
    finally:
        for key in [k for k in REGISTRY if k.startswith("user.")]:
            del REGISTRY[key]


def test_the_hosted_payload_keeps_an_ez_byte_for_byte():
    import base64
    import zlib

    from antennaknobs.web import decks

    raw = ez_file(DIPOLE, title="Gr\xfc\xdfe")
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    z = base64.urlsafe_b64encode(c.compress(raw) + c.flush()).decode().rstrip("=")
    st = decks.DeckSettings(hosted=True)
    name, text = decks.decode_payload({"name": "dp.ez", "z": z}, st)
    assert name == "dp.ez" and text.encode("latin-1") == raw
    name, text = decks.decode_payload(
        {"name": "dp.ez", "text": raw.decode("latin-1")}, st
    )
    assert text.encode("latin-1") == raw
    with pytest.raises(decks.DeckError, match="binary"):
        decks.decode_payload({"name": "dp.ez", "text": "GW €"}, st)
    big = ez_file(DIPOLE) + bytes(70_000)
    with pytest.raises(decks.DeckError) as err:
        decks.decode_payload({"name": "big.ez", "text": big.decode("latin-1")}, st)
    assert err.value.status == 413


def test_an_ez_opens_solves_and_shows_its_cards_through_the_routes(monkeypatch):
    import base64
    import json
    import zlib

    from fastapi.testclient import TestClient

    from antennaknobs.web import decks, server

    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(st.opens_per_min))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    raw = ez_file(DIPOLE, title="hosted dipole")
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    z = base64.urlsafe_b64encode(c.compress(raw) + c.flush()).decode()
    client = TestClient(server.app)
    try:
        r = client.post("/deck", json={"name": "dp.ez", "z": z.rstrip("=")})
        assert r.status_code == 200, r.text
        key = r.json()["key"]
        assert "centre of the segment" in r.json()["example"]["notes"]
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"geometry": key, "_session": "s", "_seq": 1}))
            out = json.loads(ws.receive_text())
        assert "error" not in out, out
        assert 60 < out["z_in_re"] < 90
        src = client.post("/design_source", json={"geometry": key}).json()
        assert src["language"] == "nec" and src["text"].startswith("CM hosted dipole")
        bad = client.post(
            "/deck",
            json={
                "name": "v.ez",
                "text": ez_file(DIPOLE, vercode=10).decode("latin-1"),
            },
        )
        assert bad.status_code == 422 and "version code 10" in bad.json()["detail"]
    finally:
        for k in list(server.EXAMPLES):
            if decks.is_deck(k):
                del server.EXAMPLES[k]


# --------------------------------------------------------------------------
# Real EZNEC-written files (lonney9/Antenna-Models, MIT; see the NOTICE)
# --------------------------------------------------------------------------

REAL = {
    # file: (wires, sources, loads, lines, L networks, virtual, ground, engine)
    "40m-Dipole.ez": (1, 1, 0, 0, 0, False, "realH", None),
    "20m-2-Dipoles-1-CF.ez": (2, 1, 0, 2, 1, True, "realH", 2),
    "W6NBC_40m_Vert_2El_OVF.ez": (8, 1, 2, 2, 2, True, "realH", None),
    "Basic-NEC5-DLoop-Vert-Inv.ez": (3, 1, 0, 1, 0, True, "realH", 8),
    "K6STI-RX-Loop.ez": (4, 1, 0, 2, 0, True, "realH", None),
}


@pytest.mark.parametrize("fname", sorted(REAL))
def test_a_real_eznec_file_opens(fname):
    raw = (FIXTURES / fname).read_bytes()
    imp = read_ez(raw, name=fname)
    m = imp.model
    nw, ns, nl, nt, nln, virt, ground, engine = REAL[fname]
    assert (
        len(m.wires),
        len(m.sources),
        len(m.loads),
        len(m.lines),
        len(m.lnetworks),
    ) == (nw, ns, nl, nt, nln)
    assert (m.virtual_labels is not None) == virt
    assert m.ground + m.analysis == ground
    assert (m.engine[0] if m.engine else None) == engine
    assert imp.deck.network() is not None
    assert len(imp.deck.wire_tuples(specs=True)) >= nw


def test_a_real_file_with_insulation_wears_jackets():
    imp = read_ez((FIXTURES / "K6STI-RX-Loop.ez").read_bytes())
    assert imp.deck.wire_insulation


def test_a_real_file_with_a_trap_is_refused_until_asked():
    raw = (FIXTURES / "20m-10m-GP-WA7ARK.ez").read_bytes()
    with pytest.raises(EzUndefined, match="trap"):
        read_ez(raw)
    imp = read_ez(raw, accept_guesses=True)
    assert any(isinstance(ld.custom, ez_import._OnePort) for ld in imp.deck.loads)


def test_a_real_file_with_eznecs_extended_ground_is_a_reading():
    raw = (FIXTURES / "Basic-NEC5-Dipole-40m.ez").read_bytes()
    with pytest.raises(EzUndefined, match="extended"):
        read_ez(raw)
    assert read_ez(raw, accept_guesses=True).deck.feeds
