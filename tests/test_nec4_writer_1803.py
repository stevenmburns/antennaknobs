"""AK#1803: the NEC-4 (NEC-4.2) deck writer, `export_nec(..., dialect="nec42")`.

What the NEC-2 lane's writer refused or spelled NEC-2's way, and this dialect
writes NEC-4's way: graded meshes as chained GW cards (renumbered references),
native ``EX 6`` current sources (no gyrator), buried wires under ``GE -1``,
Sommerfeld cards ending ``NOFILE``, and a GN 3 near-field request near the
zenith refused by name. Every card stays inside NEC's 80-column record.

No NEC-4.2 binary is needed here: the round trips run through `nec_import`,
and the licensed-binary lane is `test_nec4_writer_binary_1803.py`.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.engines.nec42 import GN3_ZENITH_WINDOW_DEG, refuse_gn3_near_field
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_export import (
    CARD_COLUMNS,
    NearField,
    export_nec,
    export_nec_structure,
    deck_engine_cls,
)
from antennaknobs.network import (
    Driven,
    DrivenCurrent,
    GradedSegments,
    Load,
    Network,
    PortOnWire,
    Wire,
    as_wire,
)
from antennaknobs.web.examples import REGISTRY

SOIL = ("finite", 13.0, 0.005)
CARDIOID4 = (
    Path(__file__).parent / "fixtures" / "eznec_gyrator_1595" / "Cardioidmodnec4.nec"
)


def _cards(deck: str, kind: str) -> list[str]:
    return [ln for ln in deck.splitlines() if ln.split()[:1] == [kind]]


def _body(deck: str) -> list[str]:
    lines = deck.splitlines()
    return lines[lines.index("CE") + 1 :]


def _builder(wires, network=None, freq: float = 14.0):
    class B(AntennaBuilder):
        default_params = MappingProxyType({"freq": freq})

        def build_wires(self):
            return list(wires)

        def build_network(self):
            return network

    b = B()
    b.freq = freq
    return b


def _graded_then_loaded():
    """A graded wire FIRST, so every tag after it moves: a fed wire and a
    loaded wire, both addressed by EX / LD cards."""
    wires = [
        Wire((0, -2.5, 5), (0, 2.5, 5), GradedSegments((0.25, 0.75), (3, 5, 3))),
        Wire((0, 2.5, 5), (0, 2.5, 8), 11, name="feed"),
        Wire((0, 2.5, 8), (0, 6.5, 8), 9, name="coil"),
    ]
    net = Network(
        ports={"feed": PortOnWire("feed"), "coil": PortOnWire("coil")},
        branches=[Load(port="coil", l=2e-6)],
        sources=[Driven(port="feed", voltage=1 + 0j)],
    )
    return _builder(wires, net)


def _nec42(builder, ground="free", **kw):
    return export_nec(builder, ground=ground, include_rp=False, dialect="nec42", **kw)


def _round_trip(deck: str, tmp_path: Path) -> tuple[str, object]:
    """Read `deck` back through `nec_import` and write it again."""
    path = tmp_path / "deck.nec"
    path.write_text(deck)
    cls = builder_from_file(str(path))
    return _nec42(cls(), cls.file_ground), cls


# --------------------------------------------------------------------------
# graded meshes
# --------------------------------------------------------------------------


def test_a_graded_wire_is_chained_gw_cards_with_references_renumbered():
    deck = _nec42(_graded_then_loaded())
    gw = _cards(deck, "GW")
    assert [int(c.split()[1]) for c in gw] == [1, 2, 3, 4, 5]
    assert [int(c.split()[2]) for c in gw] == [3, 5, 3, 11, 9]
    # The panels chain: each ends where the next begins, at 25 % and 75 %.
    ends = [(c.split()[3:6], c.split()[6:9]) for c in gw[:3]]
    assert ends[0][1] == ends[1][0] and ends[1][1] == ends[2][0]
    assert [float(v) for v in ends[0][1]] == [0.0, -1.25, 5.0]
    # The feed was tag 2 and the load tag 3 as authored; both moved by the two
    # extra panels, and stay on their wires' CENTRE segments.
    assert _cards(deck, "EX") == ["EX 0 4 6 0 1 0"]
    assert _cards(deck, "LD") == ["LD 0 5 5 5 0 2e-06 0"]


def test_the_nec2_dialect_still_refuses_a_graded_wire_and_points_at_nec4():
    with pytest.raises(NotImplementedError, match="or the NEC-4 deck"):
        export_nec(_graded_then_loaded(), ground="free", include_rp=False)


def test_the_catalog_graded_buried_vertical_is_written():
    b = REGISTRY["verticals.buried_radial_vertical"].builder_cls()
    deck = _nec42(b, SOIL)
    assert _cards(deck, "GE") == ["GE -1"]
    assert _cards(deck, "GN") == ["GN 2 0 0 0 13 0.005 NOFILE"]
    # The feed is the one-segment gap wire's centre: segment 1 of an odd count.
    (ex,) = _cards(deck, "EX")
    tag = int(ex.split()[2])
    assert int(_cards(deck, "GW")[tag - 1].split()[2]) % 2 == 1


# --------------------------------------------------------------------------
# EX 6
# --------------------------------------------------------------------------


def _current_dipole(current=1 + 0j):
    return _builder(
        [Wire((-2.5, 0, 0), (2.5, 0, 0), 21, name="feed")],
        Network(
            ports={"feed": PortOnWire("feed")},
            branches=[],
            sources=[DrivenCurrent(port="feed", current=current)],
        ),
        freq=28.47,
    )


def test_a_current_source_is_a_native_ex6_with_no_gyrator():
    deck = _nec42(_current_dipole(0.5 - 0.25j))
    assert _cards(deck, "EX") == ["EX 6 1 11 0 0.5 -0.25"]
    assert _cards(deck, "NT") == []
    assert len(_cards(deck, "GW")) == 1, "no phantom wire"
    # ... where the NEC-2 dialect writes the gyrator.
    nec2 = export_nec(_current_dipole(), ground="free", include_rp=False)
    assert _cards(nec2, "NT") and len(_cards(nec2, "GW")) == 2


def test_the_ex6_dipole_is_the_check_sets_hand_written_deck():
    """The check set's `coverage.ex6_dipole.free` was written by hand; the
    writer reproduces its cards (radius and frequency spelled the same)."""
    deck = _nec42(_current_dipole())
    body = [ln for ln in _body(deck) if ln.split()[0] != "GW"]
    assert body == ["GE 0", "EX 6 1 11 0 1 0", "FR 0 1 0 0 28.47 0", "XQ 0", "EN"]
    (gw,) = _cards(deck, "GW")
    assert gw.split()[:9] == "GW 1 21 -2.5 0 0 2.5 0 0".split()


def test_eznecs_nec4_cardioid_writes_back_its_ex6_cards():
    """AC6LA's EZNEC-written NEC-4.2 deck: two EX 6 sources, read in as
    `DrivenCurrent`s (issue #442) and written out as the same two cards."""
    cls = builder_from_file(str(CARDIOID4))
    deck = _nec42(cls(), cls.file_ground)
    assert _cards(deck, "EX") == ["EX 6 1 1 0 1.414214 0", "EX 6 2 1 0 0 -1.414214"]
    assert _cards(deck, "NT") == []


# --------------------------------------------------------------------------
# round trips through nec_import (the issue's gate)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("make", "ground"),
    [
        pytest.param(
            lambda: REGISTRY["dipoles.invvee"].builder_cls(), "free", id="dipole"
        ),
        pytest.param(_current_dipole, "free", id="ex6"),
        pytest.param(
            lambda: REGISTRY["verticals.buried_radial_vertical"].builder_cls(),
            SOIL,
            id="graded-buried-vertical",
        ),
        pytest.param(
            lambda: REGISTRY["dipoles.short_dipole_loaded"].builder_cls(),
            "free",
            id="loaded",
        ),
        pytest.param(_graded_then_loaded, "pec", id="graded-loaded-pec"),
        pytest.param(
            lambda: REGISTRY["dipoles.invvee"].builder_cls(), SOIL, id="sommerfeld"
        ),
    ],
)
def test_the_deck_round_trips_through_nec_import(make, ground, tmp_path):
    """Write, read back, write again: the card body is a fixed point, and the
    imported design carries the ground, sources and loads the deck said."""
    deck = _nec42(make(), ground)
    again, cls = _round_trip(deck, tmp_path)
    assert _body(again) == _body(deck)
    assert cls.file_ground == (None if ground == "free" else ground)
    net = cls().build_network()
    n_ex6 = sum(ln.startswith("EX 6") for ln in deck.splitlines())
    if n_ex6:
        assert net is not None
        assert sum(isinstance(s, DrivenCurrent) for s in net.sources) == n_ex6


def test_the_ex6_round_trip_keeps_the_impedance(tmp_path):
    """The imported EX 6 design solves as the design that wrote it."""
    from antennaknobs.engines import MomwireEngine

    b = _current_dipole()
    _again, cls = _round_trip(_nec42(b), tmp_path)
    z0 = MomwireEngine(b, ground=None).impedance()
    z1 = MomwireEngine(cls(), ground=None).impedance()
    assert np.asarray(z1) == pytest.approx(np.asarray(z0), rel=1e-3)


# --------------------------------------------------------------------------
# ground cards, buried wires, feeds
# --------------------------------------------------------------------------


@pytest.mark.parametrize("sommerfeld", [2, 3])
def test_the_sommerfeld_card_ends_nofile(sommerfeld):
    deck = _nec42(REGISTRY["dipoles.invvee"].builder_cls(), SOIL, sommerfeld=sommerfeld)
    assert _cards(deck, "GN") == [f"GN {sommerfeld} 0 0 0 13 0.005 NOFILE"]


def test_a_buried_design_is_ge_minus_1_and_the_nec2_dialect_refuses_it():
    b = REGISTRY["specialty.buried_dipole"].builder_cls()
    assert _cards(_nec42(b, SOIL), "GE") == ["GE -1"]
    with pytest.raises(NotImplementedError, match="download the NEC-5 deck instead"):
        export_nec(b, ground=SOIL, include_rp=False)


def test_a_mid_span_crossing_is_still_refused():
    b = _builder([Wire((0, 0, -1.0), (0, 0, 5.0), 29, ex=1 + 0j, name="feed")])
    with pytest.raises(NotImplementedError, match="crosses the ground plane"):
        _nec42(b, SOIL)


def test_feeds_sit_on_segment_centres():
    """NEC-2/4's convention: an odd count and the middle segment, never
    NEC-5's knot (an even count and `EX 0 t k 2`)."""
    deck = _nec42(_builder([Wire((0, -5, 10), (0, 5, 10), 10, ex=1 + 0j, name="f")]))
    assert _cards(deck, "GW")[0].split()[2] == "11"
    assert _cards(deck, "EX") == ["EX 0 1 6 0 1 0"]


# --------------------------------------------------------------------------
# TL / virtual-driver networks: per-port structure decks, never one deck
# --------------------------------------------------------------------------


def test_a_tl_network_refuses_a_single_nec4_deck():
    from antennaknobs.designs.arrays.delta_looparray_network import Builder

    with pytest.raises(NotImplementedError, match="a single NEC-4 deck"):
        _nec42(Builder())


def test_a_tl_networks_structure_decks_are_nec4():
    """The multiport-Y route's per-port deck: the bare structure in NEC-4's
    cards, one EX 0 on the port's centre segment, no network card."""
    from antennaknobs.designs.dipoles.invvee_coax_station import Builder

    eng = deck_engine_cls("nec42")(Builder(), ground=SOIL)
    assert eng._use_reducer
    name = eng._real_port_names[0]
    tag = 1 + [as_wire(t).name for t in eng.tups].index(eng._port_wire_of[name])
    ((seg, _w),) = eng._port_drive_points[name]
    deck = export_nec_structure(
        eng, freq=eng.builder.freq, sources=[(tag, seg, 1.0)], dialect="nec42"
    )
    assert _cards(deck, "GN") == ["GN 2 0 0 0 13 0.005 NOFILE"]
    assert _cards(deck, "NT") == [] and _cards(deck, "TL") == []
    assert _cards(deck, "EX") == [f"EX 0 {tag} {seg} 0 1 0"]


# --------------------------------------------------------------------------
# 80 columns (AK#1628)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "specialty.faceted_helix",
        "broadband.discone",
        "verticals.elevated_buried_counterpoise",
        "verticals.buried_radial_vertical",
        "dipoles.invvee",
    ],
)
def test_every_card_fits_80_columns(name):
    b = REGISTRY[name].builder_cls()
    ground = SOIL if "buried" in name else "free"
    deck = export_nec(b, ground=ground, include_rp=True, dialect="nec42")
    long = [ln for ln in deck.splitlines() if not ln.startswith("CM")]
    assert max(len(ln) for ln in long) <= CARD_COLUMNS


def test_a_card_past_column_80_is_refused(monkeypatch):
    """The tripwire runs on this dialect's decks too."""
    import antennaknobs.nec_export as ne

    monkeypatch.setattr(ne, "_ex6_cards", lambda eng: ["EX 6 1 11 0 " + "1" * 80])
    with pytest.raises(ValueError, match="past column 80"):
        _nec42(_current_dipole())


# --------------------------------------------------------------------------
# GN 3 near field
# --------------------------------------------------------------------------


def _vertical_dipole():
    return _builder([Wire((0, 0, 5), (0, 0, 15), 21, ex=1 + 0j, name="feed")])


# A vertical grid 20-32 m out and 5-17 m up: at least 20 m off every segment's
# vertical while no point is more than 32 m above a segment's image, so it
# sits well outside the cone.
_OFF_ZENITH = NearField(counts=(4, 1, 4), start=(20, 0, 5), step=(4, 0, 4))


def test_a_gn3_near_field_over_the_zenith_is_refused_by_name():
    over = NearField(counts=(3, 3, 1), start=(-1, -1, 30), step=(1, 1, 0))
    with pytest.raises(NotImplementedError, match="GN 3.*near the zenith"):
        _nec42(_vertical_dipole(), SOIL, sommerfeld=3, near_field=over)


def test_the_same_grid_is_written_over_gn2_and_in_free_space():
    over = NearField(counts=(3, 3, 1), start=(-1, -1, 30), step=(1, 1, 0))
    for ground, som in ((SOIL, 2), ("free", 3), ("pec", 3)):
        deck = _nec42(_vertical_dipole(), ground, sommerfeld=som, near_field=over)
        assert _cards(deck, "NE") == ["NE 0 3 3 1 -1 -1 30 1 1 0"]
        assert _cards(deck, "XQ") == [], "the NE card executes the run itself"


def test_a_gn3_near_field_off_the_zenith_is_written():
    deck = _nec42(_vertical_dipole(), SOIL, sommerfeld=3, near_field=_OFF_ZENITH)
    assert _cards(deck, "NE") == ["NE 0 4 1 4 20 0 5 4 0 4"]
    h = _OFF_ZENITH._replace(magnetic=True)
    assert _cards(_nec42(_vertical_dipole(), SOIL, sommerfeld=3, near_field=h), "NH")


def test_the_window_edge_is_measured_from_every_segment_and_its_image():
    """Just inside and just outside the cone, from one source point, in the
    direct geometry and in the image one (the source mirrored in z=0)."""
    c = np.array([[0.0, 0.0, 2.0]])
    t = np.tan(np.radians(GN3_ZENITH_WINDOW_DEG))
    dz = 10.0
    inside = np.array([[0.99 * t * dz, 0.0, 2.0 + dz]])
    outside = np.array([[1.01 * t * (dz + 4.0), 0.0, 2.0 + dz]])
    with pytest.raises(NotImplementedError):
        refuse_gn3_near_field(SOIL, 3, inside, c)
    refuse_gn3_near_field(SOIL, 3, outside, c)
    # Outside the direct cone but inside the image's: 1 m above the source,
    # 2t off its vertical, is 5 m above its mirror at z=-2.
    image_only = np.array([[2.0 * t, 0.0, 3.0]])
    with pytest.raises(NotImplementedError):
        refuse_gn3_near_field(SOIL, 3, image_only, c)
    # GN 2 and non-Sommerfeld grounds never refuse.
    refuse_gn3_near_field(SOIL, 2, inside, c)
    refuse_gn3_near_field("pec", 3, inside, c)


# --------------------------------------------------------------------------
# the CLI
# --------------------------------------------------------------------------


def test_the_cli_nec4_dialect_is_the_writers_deck(tmp_path):
    import antennaknobs

    out = tmp_path / "brv.nec"
    antennaknobs.cli(
        [
            "export",
            "--builder",
            "verticals.buried_radial_vertical",
            "--dialect",
            "nec4",
            "--ground",
            "finite:13,0.005",
            "--out",
            str(out),
        ]
    )
    expected = export_nec(
        REGISTRY["verticals.buried_radial_vertical"].builder_cls(),
        ground=SOIL,
        dialect="nec42",
    )
    assert out.read_text() == expected
