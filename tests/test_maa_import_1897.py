"""MMANA-GAL ``.maa`` models open like decks (AK#1897).

Every fixture here is written for this module -- synthetic, minimal models in
MMANA's layout -- and none is a copy of a third-party file. The corpus
(`test_maa_corpus_1897.py`) is where real files are read, from a local
checkout, never vendored.

What the module pins, by layer:

* the reader: positional blocks under any header spelling, cp1251 bytes, CRLF,
  a missing final newline, the Cyrillic centre letter, phase BEFORE volts on
  a source line, load lines by type, the Use-loads switch;
* the mesh rule (`maa_import._auto_mesh`): MMANA's -1 / -2 / -3 / 0 expanded
  from the file's own DM1, DM2, SC, EC, never left as one segment per wire;
* positions: pulses become ports at segment ends, exact on a manual count,
  a centre that is not on the mesh is CUT, never snapped;
* the refusals, each by name;
* the ground and material lines, and the design the file becomes;
* the physics that MMANA's oracle sitting measured and a solve here can
  re-measure: a load on the feed pulse is in series with the source, and
  MMANA's real ground is perfect ground for the impedance.
"""

from __future__ import annotations

import cmath
import math

import pytest

from antennaknobs import maa_import
from antennaknobs.builder import C_LIGHT_MHZ_M
from antennaknobs.cli import get_builder
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_text
from antennaknobs.maa_import import MAA_DEFAULT_SOIL, decode_maa, read_maa
from antennaknobs.nec_import import GeometryLimits


def maa(
    wires,
    sources=("w1c,\t0.0,\t1.0",),
    loads=(),
    *,
    title="test dipole",
    freq="14.05",
    loads_on=1,
    seg="400,\t40,\t2.0,\t1",
    ground="0,\t0.0,\t0,\t50.0,\t120,\t60,\t0",
    count=None,
    tail="",
    headers=("***Wires***", "***Source***", "***Load***", "***Segmentation***"),
    gh="***G/H/M/R/AzEl/X***",
    eol="\n",
):
    """An MMANA-GAL model in its own layout, from its parts."""
    lines = [title, "*", freq, headers[0], count or str(len(wires)), *wires]
    lines += [headers[1], f"{len(sources)},\t1", *sources]
    lines += [headers[2], f"{len(loads)},\t{loads_on}", *loads]
    lines += [headers[3], seg, gh, ground]
    text = eol.join(lines) + eol
    return text + tail


# A 20 m dipole, 10.34 m long, 1 mm radius, on the y axis at z = 0.
DIPOLE_WIRE = "0.0,\t-5.17,\t0.0,\t0.0,\t5.17,\t0.0,\t0.001,\t-1"
DIPOLE = maa([DIPOLE_WIRE])


def _z(cls) -> complex:
    return complex(MomwireEngine(cls(), ground=cls.file_ground).impedance()[0])


def _knot_feeds(deck):
    """Each feed's place along the deck, as a point."""
    out = []
    for f in deck.feeds:
        w = deck.wires[f.wire]
        k = f.seg - 1 if f.edge == 1 else f.seg
        t = k / w.n_seg
        out.append(tuple(a + (b - a) * t for a, b in zip(w.p1, w.p2, strict=True)))
    return out


# --- the reader -------------------------------------------------------------


def test_a_dipole_reads_as_an_mmana_deck():
    imp = read_maa(DIPOLE, name="dp.maa")
    d = imp.deck
    assert imp.freq_mhz == 14.05 and imp.ref_z == 50.0
    assert d.dialect == "maa" and not d.extended_kernel_by_dialect
    # Sources sit at a segment END (a pulse), the centre of the wire.
    assert all(f.edge in (1, 2) for f in d.feeds)
    assert _knot_feeds(d) == [pytest.approx((0.0, 0.0, 0.0), abs=1e-12)]
    assert imp.notes[0].startswith("Read as MMANA-GAL (MININEC)")
    assert "(400, 40, 2, 1)" in imp.notes[1]


@pytest.mark.parametrize(
    "headers",
    [
        ("* Провода *", "*** Источ. ***", "*** Нагрузка ***", "*** Автосегм ***"),
        ("***Wires***", "*** Source ***", "***   Load   ***", "**Segmentation**"),
    ],
)
def test_blocks_are_found_by_position_not_by_header_text(headers):
    text = maa([DIPOLE_WIRE], headers=headers, gh="*GH/??/R/AzEl/X*")
    assert read_maa(text).deck.wires == read_maa(DIPOLE).deck.wires


def test_cp1251_crlf_no_final_newline_and_the_cyrillic_centre_letter():
    """MMANA's own library spells a centre ``w1с`` with a Cyrillic с (oracle
    sitting E12: accepted and applied). The bytes are cp1251 and CRLF."""
    text = maa(
        [DIPOLE_WIRE],
        sources=("w1с,\t0.0,\t1.0",),
        title="Диполь 20 м",
        headers=(
            "* Провода *",
            "*** Источ. ***",
            "*** Нагрузка ***",
            "*** Автосегм ***",
        ),
        eol="\r\n",
    ).rstrip("\r\n")
    raw = text.encode("cp1251")
    decoded = decode_maa(raw)
    assert "Диполь" in decoded
    imp = read_maa(decoded)
    assert _knot_feeds(imp.deck) == _knot_feeds(read_maa(DIPOLE).deck)
    assert imp.title == "Диполь 20 м"


def test_the_source_line_is_phase_then_volts():
    """``POS, PHASE, VOLTAGE`` -- the reverse of MMANA's GUI columns."""
    imp = read_maa(maa([DIPOLE_WIRE], sources=("w1c,\t90.0,\t2.0",)))
    v = imp.deck.feeds[0].voltage
    assert v == pytest.approx(cmath.rect(2.0, math.pi / 2))


def test_a_model_with_no_title_line_still_reads():
    text = DIPOLE.split("\n", 1)[1]  # starts at the bare '*'
    assert read_maa(text).title == ""


def test_the_comment_and_trailing_tabs_are_read_past():
    text = maa(
        [DIPOLE_WIRE + "\t\t"],
        tail="###Comment###\nanything at all\n*** even this ***\n",
    )
    assert read_maa(text).deck.wires == read_maa(DIPOLE).deck.wires


# --- the mesh -----------------------------------------------------------------


def _f(dm1=400, dm2=40, sc=2.0, ec=1):
    return maa_import._MaaFile(
        "", 14.05, (), (), (), True, dm1, dm2, sc, ec, 0, 0.0, 0, 50.0, ()
    )


def test_tapered_auto_mesh_follows_the_files_own_parameters():
    """Dan's point (AC6LA, QRZ): MMANA's -1 is NOT one segment per wire. The
    ends start at lambda/(DM1*EC), grow by SC, and the middle is lambda/DM2."""
    lam = C_LIGHT_MHZ_M / 14.05
    lens = maa_import._auto_mesh(10.34, lam, -1, _f(800, 80, 2.0, 2), 0.001)
    assert len(lens) > 30
    assert sum(lens) == pytest.approx(10.34)
    assert lens[0] == pytest.approx(lam / (800 * 2))
    assert lens[1] == pytest.approx(2 * lens[0])
    assert max(lens) <= lam / 80 * (1 + 1e-12)
    assert lens == lens[::-1]  # symmetric
    # An even count, so the centre is a segment end (a pulse).
    assert len(lens) % 2 == 0


def test_one_sided_and_regular_auto_meshes():
    lam = C_LIGHT_MHZ_M / 14.05
    start = maa_import._auto_mesh(5.0, lam, -2, _f(), 0.001)
    end = maa_import._auto_mesh(5.0, lam, -3, _f(), 0.001)
    assert start[0] == pytest.approx(lam / 400) and start == end[::-1]
    assert end[-1] == pytest.approx(lam / 400)
    reg = maa_import._auto_mesh(5.0, lam, 0, _f(), 0.001)
    assert len(set(round(x, 12) for x in reg)) == 1
    assert reg[0] <= lam / 40 and len(reg) == math.ceil(5.0 / (lam / 40))


def test_no_segment_is_shorter_than_two_radii():
    lam = C_LIGHT_MHZ_M / 14.05
    lens = maa_import._auto_mesh(10.0, lam, -1, _f(6000, 40, 2.0, 16), 0.01)
    assert min(lens) >= 2 * 0.01 * (1 - 1e-12)


def test_a_manual_count_is_kept_or_rounded_up_to_even():
    """A manual SEG is the segment count; an odd one is rounded up to even,
    as MMANA does (the 10-06 sitting: SEG 7 gave 8)."""
    with pytest.raises(ValueError, match="free wire end"):
        # The source must be off the wire's free end.
        read_maa(maa([DIPOLE_WIRE.replace("\t-1", "\t22")], sources=("w1b,\t0,\t1",)))
    for seg, n in ((22, 22), (21, 22)):
        text = maa([DIPOLE_WIRE.replace("\t-1", f"\t{seg}")], sources=("w1b3,\t0,\t1",))
        imp = read_maa(text)
        assert sum(w.n_seg for w in imp.deck.wires) == n
        assert _knot_feeds(imp.deck) == [
            pytest.approx((0.0, -5.17 + 3 * 10.34 / n, 0.0))
        ]


# --- positions ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("pos", "knot"),
    [("w1b2", 2), ("w1e3", 7), ("w1c", 5), ("w1c+1", 6), ("w1c-2", 3), ("w1e1", 9)],
)
def test_pulse_offsets_on_a_manual_wire(pos, knot):
    """Offsets count pulses: ``b`` inward from the start, ``e`` inward from
    the end, ``c`` toward the end when positive (the help's W3C1 / W2C-2 /
    W5E3)."""
    wire = "0.0,\t0.0,\t0.0,\t0.0,\t10.0,\t0.0,\t0.001,\t10"
    imp = read_maa(maa([wire], sources=(f"{pos},\t0,\t1",)))
    assert _knot_feeds(imp.deck)[0] == pytest.approx((0.0, float(knot), 0.0))


def test_an_odd_manual_count_is_rounded_up_to_even_as_mmana_does():
    """MMANA rounds an odd SEG up to even (the 10-06 sitting: SEG 7 gave 8
    segments), so ``w1c`` is a pulse and nothing is cut."""
    wire = "0.0,\t0.0,\t0.0,\t0.0,\t10.0,\t0.0,\t0.001,\t5"
    imp = read_maa(maa([wire]))
    assert _knot_feeds(imp.deck)[0] == pytest.approx((0.0, 5.0, 0.0))
    assert sum(w.n_seg for w in imp.deck.wires) == 6
    assert any("wire 1, 5 -> 6" in n for n in imp.notes)
    assert not any(n.startswith("Cut, not snapped") for n in imp.notes)


def test_an_off_mesh_centre_is_cut_not_snapped():
    """A regular (SEG 0) mesh with an odd count has no segment end at its
    centre: 10 m at lambda/40 of 14.05 MHz takes 19. The port goes at the
    exact centre, which cuts the wire there, and the note says so."""
    wire = "0.0,\t0.0,\t0.0,\t0.0,\t10.0,\t0.0,\t0.001,\t0"
    imp = read_maa(maa([wire]))
    assert _knot_feeds(imp.deck)[0] == pytest.approx((0.0, 5.0, 0.0))
    assert sum(w.n_seg for w in imp.deck.wires) == 20
    assert any(n.startswith("Cut, not snapped: w1c") for n in imp.notes)


def test_an_offset_on_an_auto_meshed_wire_is_refused_by_name():
    """Where MMANA's pulse k is depends on its own mesh, which is not
    emulated (the census: 41 corpus files)."""
    with pytest.raises(
        ValueError, match=r"line 9: source w1c1 .* automatically segmented"
    ):
        read_maa(maa([DIPOLE_WIRE], sources=("w1c1,\t0,\t1",)))


def test_an_offset_from_the_centre_of_an_odd_manual_wire_counts_on_the_even_mesh():
    """SEG 5 is meshed as 6, so ``w1c1`` is one pulse past the centre: the
    knot at 4/6 of the wire."""
    wire = "0.0,\t0.0,\t0.0,\t0.0,\t10.0,\t0.0,\t0.001,\t5"
    imp = read_maa(maa([wire], sources=("w1c1,\t0,\t1",)))
    assert _knot_feeds(imp.deck)[0] == pytest.approx((0.0, 40.0 / 6.0, 0.0))


def test_an_offset_from_an_off_mesh_centre_is_refused():
    wire = "0.0,\t0.0,\t0.0,\t0.0,\t10.0,\t0.0,\t0.001,\t0"
    with pytest.raises(ValueError, match="automatically segmented|odd segment count"):
        read_maa(maa([wire], sources=("w1c1,\t0,\t1",)))


def test_a_source_at_a_junction_is_a_series_gap_at_that_wire_end():
    """An inverted L fed where its two wires meet: ``w2b`` is the pulse at
    wire 2's start, which is a junction, so it exists."""
    wires = [
        "0.0,\t0.0,\t10.0,\t0.0,\t-5.0,\t10.0,\t0.001,\t-1",
        "0.0,\t0.0,\t10.0,\t0.0,\t5.0,\t10.0,\t0.001,\t-1",
    ]
    imp = read_maa(maa(wires, sources=("w2b,\t0,\t1",)))
    assert _knot_feeds(imp.deck)[0] == pytest.approx((0.0, 0.0, 10.0))


def test_a_source_at_a_free_end_is_refused():
    with pytest.raises(ValueError, match="free wire end.*MININEC has no pulse"):
        read_maa(maa([DIPOLE_WIRE], sources=("w1e,\t0,\t1",)))


def test_a_ground_fed_vertical():
    """A monopole standing on perfect ground, fed at its base: the pulse at a
    z = 0 end exists (the help's rule), and it is a port on the ground."""
    wire = "0.0,\t0.0,\t0.0,\t0.0,\t0.0,\t5.3,\t0.001,\t-1"
    g1 = "1,\t0.0,\t0,\t50.0,\t120,\t60,\t0"
    imp = read_maa(maa([wire], sources=("w1b,\t0,\t1",), ground=g1))
    assert imp.ground == "pec"
    assert _knot_feeds(imp.deck)[0] == pytest.approx((0.0, 0.0, 0.0))


def test_a_ground_end_lifted_by_the_added_height_is_refused():
    """E2 is open: whether MMANA's z = 0 pulse rule reads z or z + H."""
    wire = "0.0,\t0.0,\t0.0,\t0.0,\t0.0,\t5.3,\t0.001,\t-1"
    g = "1,\t2.0,\t0,\t50.0,\t120,\t60,\t0"
    with pytest.raises(ValueError, match="H = 2 m lifts it off the ground"):
        read_maa(maa([wire], sources=("w1b,\t0,\t1",), ground=g))


# --- loads --------------------------------------------------------------------


def _load_model(*loads, on=1):
    return maa([DIPOLE_WIRE.replace("\t-1", "\t20")], loads=loads, loads_on=on)


def test_load_types_and_units():
    w0 = 2 * math.pi * 14.05e6
    imp = read_maa(
        _load_model(
            "w1b5,\t0,\t2.5,\t0.0,\t200.0",  # coil, 2.5 uH, Q 200
            "w1b7,\t0,\t0.0,\t100.0,\t0.0",  # capacitor, 100 pF
            "w1e5,\t0,\t1.0,\t128.3,\t300.0",  # parallel L||C trap, Q 300
            "w1e7,\t1,\t5.0,\t-40.0",  # R + jX, fixed
        )
    )
    by_seg = sorted(imp.deck.loads, key=lambda ld: (ld.wire, ld.seg))
    coil, cap, trap, rx = (
        next(ld for ld in by_seg if ld.l == pytest.approx(2.5e-6) and not ld.parallel),
        next(ld for ld in by_seg if ld.c == pytest.approx(100e-12) and not ld.parallel),
        next(ld for ld in by_seg if ld.parallel),
        next(ld for ld in by_seg if ld.z is not None),
    )
    assert coil.r == pytest.approx(w0 * 2.5e-6 / 200)
    assert cap.r is None and cap.l is None
    assert trap.l == pytest.approx(1e-6) and trap.c == pytest.approx(128.3e-12)
    assert trap.r == pytest.approx(300 * w0 * 1e-6)
    assert rx.z == 5.0 - 40.0j
    assert any("held at the file's 14.05 MHz" in n for n in imp.notes)


def test_switched_off_loads_are_not_applied_and_the_note_says_so():
    """The load count line's second field is MMANA's Use loads (sitting E5):
    10 corpus files carry loads switched off. A switched-off load on a wire
    the model does not have is not resolved either (40CQ's w13c)."""
    imp = read_maa(_load_model("w13c,\t0,\t55.49,\t0.0,\t0.0", on=0))
    assert imp.deck.loads == ()
    assert any("switched off" in n for n in imp.notes)
    with pytest.raises(ValueError, match="names wire 13; the model has 1 wires"):
        read_maa(_load_model("w13c,\t0,\t55.49,\t0.0,\t0.0", on=1))


def test_a_laplace_load_is_refused_by_name():
    s = "w1c,\t2,\t0.0,1.0,1.4e-06,0.0,0.0,1.3e-16,8.0e-23,0.0,0.0,3.7e-33"
    with pytest.raises(ValueError, match=r"Laplace \(S\) form"):
        read_maa(_load_model(s))


# --- refusals by name ---------------------------------------------------------


@pytest.mark.parametrize(
    ("kw", "match"),
    [
        ({"count": "1,\t2,\t2,\t10.0,\t10.0,\t0"}, "Make Stack"),
        ({"freq": "0.0"}, "built-in 14.15 MHz"),
        ({"ground": "0,\t0.0,\t7,\t50.0,\t120,\t60,\t0"}, "user-defined material"),
        ({"ground": "0,\t0.0,\t5,\t50.0,\t120,\t60,\t0"}, "iron wire"),
        ({"ground": "0,\t0.0,\t0,\t50.0,\t120,\t60,\t3"}, r"last field \(X\)"),
        ({"ground": "2,\t12.2,\t1,"}, "the line is incomplete"),
        ({"ground": "3,\t0.0,\t0,\t50.0,\t120,\t60,\t0"}, "ground type"),
        ({"sources": ()}, "has no source"),
        ({"sources": ("w1c,\t0,\t0.0",)}, "zero volts"),
    ],
)
def test_refused_by_name(kw, match):
    with pytest.raises(ValueError, match=match):
        read_maa(maa([DIPOLE_WIRE], **kw), name="m.maa")


def test_a_stack_of_one_is_no_stack():
    text = maa([DIPOLE_WIRE], count="1,\t1,\t1,\t0.0,\t0.0,\t0")
    assert read_maa(text).deck.wires == read_maa(DIPOLE).deck.wires


def test_an_insulator_wire_is_refused():
    with pytest.raises(ValueError, match="insulator wire"):
        read_maa(maa([DIPOLE_WIRE.replace("0.001", "0.0")]))


def test_crossing_wires_and_an_end_on_a_wire_are_refused():
    cross = [DIPOLE_WIRE, "-5.0,\t0.0,\t0.0,\t5.0,\t0.0,\t0.0,\t0.001,\t-1"]
    with pytest.raises(ValueError, match="cross between their ends"):
        read_maa(maa(cross))
    tee = [DIPOLE_WIRE, "0.0,\t2.0,\t0.0,\t3.0,\t2.0,\t0.0,\t0.001,\t-1"]
    with pytest.raises(ValueError, match="lies on wire 1 between its ends"):
        read_maa(maa(tee))


def test_a_nec_deck_named_maa_is_refused():
    with pytest.raises(ValueError, match="not an MMANA-GAL .maa model"):
        read_maa("CM a NEC deck\nCE\nGW 1 11 0 0 0 0 0 1 .001\nEX 0 1 6 0 1 0\nEN\n")


# --- tapers -------------------------------------------------------------------


def test_a_symmetric_taper_steps_the_radius_from_the_centre():
    """Type 0 (``<>``): L0 is the whole centre section, each later L one
    section on each side, the last radius to the ends."""
    wire = "0.0,\t-5.0,\t0.0,\t0.0,\t5.0,\t0.0,\t-0.001,\t-1"
    tail = "$$$Taper wire set$$$\n1\n-0.001,\t0,\t2.0,\t0.015,\t2.0,\t0.0125,\t99999.9,\t0.01\n"
    imp = read_maa(maa([wire], tail=tail))
    radius_at = {}
    for w in imp.deck.wires:
        for y in (w.p1[1], w.p2[1]):
            radius_at.setdefault(round(y, 9), set()).add(w.radius)
    mid = [w for w in imp.deck.wires if abs(w.p1[1]) < 1 and abs(w.p2[1]) <= 1 + 1e-9]
    assert {w.radius for w in mid} == {0.015}
    assert radius_at[1.0] == {0.015, 0.0125} and radius_at[-3.0] == {0.0125, 0.01}


def test_starred_taper_types_are_refused():
    wire = "0.0,\t-5.0,\t0.0,\t0.0,\t5.0,\t0.0,\t-0.001,\t-1"
    tail = "$$$Taper wire set$$$\n1\n-0.001,\t2,\t2.0,\t0.015,\t99999.9,\t0.01\n"
    with pytest.raises(ValueError, match="taper wire set type 2"):
        read_maa(maa([wire], tail=tail))


# --- the ground, the material, the design ------------------------------------


def test_ground_line_maps_to_the_apps_grounds_and_adds_h():
    real = maa([DIPOLE_WIRE], ground="2,\t20.0,\t1,\t75.0,\t120,\t60,\t0")
    imp = read_maa(real)
    assert imp.ground == ("mininec", *MAA_DEFAULT_SOIL)
    assert imp.ref_z == 75.0
    assert {w.p1[2] for w in imp.deck.wires} == {20.0}
    assert imp.deck.conductivity == pytest.approx(5.8e7)
    assert any("eps_r 13, sigma 0.005 S/m is assumed" in n for n in imp.notes)
    cls = builder_from_text("real.maa", real)
    ui = cls.default_params["ui_params"]
    assert ui["ground_seed"] == "mininec" and ui["ground_card"].startswith(
        "MMANA G = 2"
    )
    assert ui["target_z0"] == 75.0
    assert cls.c_light_mhz_m == C_LIGHT_MHZ_M  # SI: MMANA is not NEC
    assert not ui.get("extended_kernel_default")


def test_the_design_refuses_a_dialect_and_a_refinement():
    with pytest.raises(ValueError, match="read as MMANA writes it"):
        builder_from_text("d.maa", DIPOLE, dialect="nec5")


def test_limits_count_mmana_wires_and_the_meshed_segments():
    with pytest.raises(ValueError, match=r"segments \(the limit is 20\); go local"):
        builder_from_text("d.maa", DIPOLE, limits=GeometryLimits(20, 200, "go local"))
    many = maa([DIPOLE_WIRE.replace("0.0,\t-5.17", f"{k}.0,\t-5.17") for k in range(3)])
    with pytest.raises(ValueError, match=r"3 wires \(the limit is 2\)"):
        read_maa(many, limits=GeometryLimits(3000, 2))


def test_at_file_loads_cp1251_bytes(tmp_path):
    p = tmp_path / "ДП20.MAA"
    p.write_bytes(
        maa(
            [DIPOLE_WIRE],
            headers=(
                "* Провода *",
                "*** Источ. ***",
                "*** Нагрузка ***",
                "*** Автосегм ***",
            ),
        ).encode("cp1251")
    )
    cls = get_builder(f"@{p}")
    b = cls()
    assert b.freq == 14.05
    assert b.build_wires() and b.build_network().sources


# --- physics the oracle sitting measured --------------------------------------


def test_a_load_on_the_feed_pulse_is_in_series_with_the_source():
    """MMANA, 40CQ (sitting E12): 120.8 + j0.029 without the load, 120.6 +
    j2594 with 55.49 uH on the feed pulse -- the load adds j*w*L in series.
    Here: the same difference, exactly."""
    plain = builder_from_text("d.maa", DIPOLE)
    loaded = builder_from_text(
        "d.maa", maa([DIPOLE_WIRE], loads=("w1c,\t0,\t55.49,\t0.0,\t0.0",))
    )
    dz = _z(loaded) - _z(plain)
    assert dz.real == pytest.approx(0.0, abs=1e-6)
    assert dz.imag == pytest.approx(2 * math.pi * 14.05e6 * 55.49e-6, rel=1e-9)


def test_real_ground_is_perfect_ground_for_the_impedance():
    """MMANA's real ground is MININEC-type (sitting E7: DP20 reads 76.95 -
    j9.966 over Perfect and over Real with any soil)."""
    g1 = maa([DIPOLE_WIRE], ground="1,\t20.0,\t0,\t50.0,\t120,\t60,\t0")
    g2 = maa([DIPOLE_WIRE], ground="2,\t20.0,\t0,\t50.0,\t120,\t60,\t0")
    z1 = _z(builder_from_text("g1.maa", g1))
    z2 = _z(builder_from_text("g2.maa", g2))
    assert z2 == pytest.approx(z1, rel=1e-9)


def test_the_dipole_lands_near_mmanas_own_number():
    """MMANA-GAL's DP20 (sitting E7), free space: 71.51 - j1.877. This
    fixture is the same geometry written here; MININEC on MMANA's mesh and
    MoM on this one differ by the expected gap, which is pinned loosely
    (measured 2026-10-05: 71.87 - j1.15)."""
    z = _z(builder_from_text("d.maa", DIPOLE))
    assert z.real == pytest.approx(71.51, rel=0.02)
    assert z.imag == pytest.approx(-1.877, abs=1.5)


# --- the workbench: Open..., the link, the designs folder --------------------


def test_an_opened_deck_payload_takes_a_maa():
    from antennaknobs.web import decks

    st = decks.DeckSettings(hosted=True)
    name, text = decks.decode_payload({"name": "dp.maa", "text": DIPOLE}, st)
    assert (name, text) == ("dp.maa", DIPOLE)


def test_a_maa_opens_solves_and_shows_its_source_through_the_routes(monkeypatch):
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
    # The browser decodes cp1251 and carries UTF-8 text in the link.
    text = maa([DIPOLE_WIRE], title="Диполь", sources=("w1с,\t0.0,\t1.0",))
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    z = base64.urlsafe_b64encode(c.compress(text.encode()) + c.flush()).decode()
    client = TestClient(server.app)
    try:
        r = client.post("/deck", json={"name": "dp.maa", "z": z.rstrip("=")})
        assert r.status_code == 200, r.text
        key = r.json()["key"]
        assert "Read as MMANA-GAL" in r.json()["example"]["notes"]
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"geometry": key, "_session": "s", "_seq": 1}))
            out = json.loads(ws.receive_text())
        assert "error" not in out, out
        assert out["z_in_re"] == pytest.approx(71.51, rel=0.02)
        src = client.post("/design_source", json={"geometry": key}).json()
        assert src["text"] == text and src["language"] == "maa"
        # A stack is refused by name, with the file's line.
        bad = client.post(
            "/deck",
            json={
                "name": "stack.maa",
                "text": maa([DIPOLE_WIRE], count="1,\t2,\t2,\t10.0,\t10.0,\t0"),
            },
        )
        assert bad.status_code == 422 and "Make Stack" in bad.json()["detail"]
    finally:
        for k in list(server.EXAMPLES):
            if decks.is_deck(k):
                del server.EXAMPLES[k]


def test_a_maa_in_the_designs_folder_is_a_design(tmp_path, monkeypatch):
    import antennaknobs.web.examples  # noqa: F401 — bootstraps the adapter + REGISTRY
    from antennaknobs import user_designs
    from antennaknobs.web.examples import REGISTRY

    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    (tmp_path / "dp20.maa").write_bytes(
        maa([DIPOLE_WIRE], title="Диполь").encode("cp1251")
    )
    try:
        assert [s for s, _ in user_designs.iter_design_files()] == ["dp20"]
        cls = user_designs.resolve_user_design("dp20")
        assert cls().freq == 14.05
    finally:
        for key in [k for k in REGISTRY if k.startswith("user.")]:
            del REGISTRY[key]
