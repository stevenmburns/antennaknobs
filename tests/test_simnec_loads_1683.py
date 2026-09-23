"""SimNEC export writes lumped loads in a spelling SimNEC solves (AK#1683).

The export used to put ``LD 0`` / ``LD 1`` cards inside the NEC2 block, and
SimNEC's NEC2 reader ignores every card but GW / GM / GS / EX / NT (NECPortal
manual, "NEC2 Decks"). Checked on SimNEC 5.3: a series 4.65 uH at a dipole's
centre read 13.06 - j825 (the no-load answer) and LD 1 traps 529 + j1147,
and SimNEC's own ``lastConstructedNEC.nec`` had no LD line.

A load is now an N-block ``R`` component attached to its ``$GW_<tag>`` wire
by a ``NECSource`` (the manual's "Loading"; AC6LA's EZNEC-to-SimNEC files
spell a deck's ``LD`` card this way), and a load on the fed segment is a
series circuit element at the feed. SimNEC's GUI cannot run here, so every
case is a round trip: export, read back with ``parse_ssn``, solve both, compare.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from types import MappingProxyType

import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.designs.dipoles.short_dipole_loaded import Builder as ShortLoaded
from antennaknobs.designs.multiband.trap_dipole import Builder as TrapDipole
from antennaknobs.engines.pynec import PyNECEngine
from antennaknobs.network import (
    Driven,
    Load,
    Network,
    PortOnWire,
    TwoPort,
    Wire,
)
from antennaknobs.simnec_export import (
    SsnUnsupported,
    build_nec_portal_script,
    export_ssn,
)
from antennaknobs.simnec_import import parse_ssn
from antennaknobs.wire_catalog import wire_from_catalog


def _equ(ssn: str) -> str:
    for el in ET.fromstring(ssn).iter("element"):
        if el.findtext("type") == "NETWORK":
            for p in el.findall("p"):
                if p.findtext("n") == "equ":
                    return p.findtext("v")
    raise AssertionError("no NETWORK script")


def _block(ssn: str) -> list[str]:
    body = _equ(ssn).split("\nNEC2\n", 1)[1].split("\nNECEND", 1)[0]
    return [ln.strip() for ln in body.splitlines() if ln.strip()]


def _types(ssn: str) -> list[str]:
    return [el.findtext("type") for el in ET.fromstring(ssn).iter("element")]


def _roundtrip_builder(ssn: str, freq: float):
    c = parse_ssn(ssn, name="rt.ssn", network=True)

    class RoundTrip(AntennaBuilder):
        default_params = MappingProxyType({"freq": freq})

        def build_wires(self):
            return c.deck.wire_tuples(specs=True)

        def build_network(self):
            return c.network()

    return c, RoundTrip()


def _z(builder) -> complex:
    return complex(PyNECEngine(builder, ground=None).impedance()[0])


# --- the two designs Steve checked in SimNEC 5.3 -----------------------------


def test_no_ld_card_reaches_the_nec2_block():
    """The regression itself: on main both exports carried an LD card that
    SimNEC dropped without a word."""
    for b in (ShortLoaded(), TrapDipole()):
        cards = _block(export_ssn(b, ground=None))
        assert not [c for c in cards if c.split()[0] == "LD"], cards


def test_trap_dipole_traps_are_necsource_loads():
    ssn = export_ssn(TrapDipole(), ground=None)
    loads = [ln for ln in _equ(ssn).splitlines() if "NECSource" in ln]
    # Each trap is a one-segment wire, so its centre is 50 % of it.
    assert loads == [
        "R1 (L(5e-06) ||| C(6.46181018127e-12)) ld1a ld1b;  "
        "dcl Load1 = NECSource({ld1a,ld1b}, $GW_2, 50);",
        "R2 (L(5e-06) ||| C(6.46181018127e-12)) ld2a ld2b;  "
        "dcl Load2 = NECSource({ld2a,ld2b}, $GW_4, 50);",
    ]
    # after the block, where SimNEC has named the wires $GW_<tag>
    equ = _equ(ssn)
    assert equ.index("NECEND") < equ.index("NECSource")


def test_trap_dipole_round_trips_to_the_same_impedance():
    b = TrapDipole()
    ssn = export_ssn(b, ground=None)
    c, rt = _roundtrip_builder(ssn, b.freq)
    assert [(ld.wire, ld.seg, ld.parallel) for ld in c.deck.loads] == [
        (1, 1, True),
        (3, 1, True),
    ]
    assert c.ignored_directives == ()
    z0, z1 = _z(b), _z(rt)
    # nec2c with the traps: 81.97 + j55.93 (without them 491 + j1115)
    assert z0 == pytest.approx(81.97 + 55.96j, abs=0.1)
    assert z1 == pytest.approx(z0, rel=1e-5)


def test_short_dipole_feed_load_is_a_series_element_at_the_feed():
    """Its coil is on the fed segment, where SimNEC puts the EX card's own
    NECSource, so it is written as SERIES_IND between the antenna block and
    the generator: in series with the source, as the LD card was."""
    ssn = export_ssn(ShortLoaded(), ground=None)
    assert _types(ssn) == ["LOAD", "NETWORK", "SERIES_IND", "GENERATOR"]
    ind = next(
        el
        for el in ET.fromstring(ssn).iter("element")
        if el.findtext("type") == "SERIES_IND"
    )
    params = {p.findtext("n"): p.findtext("v") for p in ind.findall("p")}
    assert params["H"] == "4.65e-06" and params["Q"] == "0"
    assert "NECSource" not in _equ(ssn)


def test_short_dipole_round_trips_to_the_same_impedance():
    b = ShortLoaded()
    ssn = export_ssn(b, ground=None)
    c, rt = _roundtrip_builder(ssn, b.freq)
    (coil,) = [br for br in c.network().branches if isinstance(br, TwoPort)]
    assert coil.l == pytest.approx(4.65e-6) and coil.ql is None
    z0, z1 = _z(b), _z(rt)
    # nec2c with the coil: 13.78 - j12.46 (without it 13.8 - j830.5)
    assert z0 == pytest.approx(13.78 - 12.42j, abs=0.1)
    # The LD card spreads its impedance over the segment's current, the
    # series element meets the gap current: the same answer to 1e-5 of the
    # coil's 818 ohm reactance.
    assert z1 == pytest.approx(z0, abs=0.05)


def test_the_script_alone_refuses_a_feed_segment_load():
    b = ShortLoaded()
    with pytest.raises(SsnUnsupported, match="fed segment.*export_ssn"):
        build_nec_portal_script(b, freq_mhz=b.freq)


# --- every load form, and the refusals ---------------------------------------


class _Loaded(AntennaBuilder):
    """A dipole fed on its one-segment 'feed' wire, with one Load, built per
    test, on the one-segment 'tip' wire (tag 4) or on the feed."""

    default_params = MappingProxyType({"freq": 14.0, "design_freq": 14.0})
    load: Load = Load(port="tip", r=50.0)
    spec = None

    def build_wires(self):
        return [
            Wire((0.0, -5.0, 10.0), (0.0, 0.0, 10.0), n_seg=10, spec=self.spec),
            Wire(
                (0.0, 0.0, 10.0),
                (0.0, 0.2, 10.0),
                n_seg=1,
                name="feed",
                spec=self.spec,
            ),
            Wire((0.0, 0.2, 10.0), (0.0, 4.0, 10.0), n_seg=10, spec=self.spec),
            Wire(
                (0.0, 4.0, 10.0),
                (0.0, 5.0, 10.0),
                n_seg=1,
                name="tip",
                spec=self.spec,
            ),
        ]

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed"), "tip": PortOnWire("tip")},
            branches=[self.load],
            sources=[Driven(port="feed")],
        )


def _with(load: Load, spec=None) -> _Loaded:
    # A subclass, not instance attributes: a builder absorbs those as params.
    return type("_Loaded", (_Loaded,), {"load": load, "spec": spec})()


@pytest.mark.parametrize(
    ("load", "expr", "ld"),
    [
        (Load(port="tip", r=50.0), "50", (0, 50.0, 0.0, 0.0)),
        (
            Load(port="tip", r=5.0, l=2e-6, c=1e-10),
            "5 + L(2e-06) + C(1e-10)",
            (0, 5.0, 2e-6, 1e-10),
        ),
        (
            Load(port="tip", l=2e-6, c=1e-10, parallel=True),
            "L(2e-06) ||| C(1e-10)",
            (1, 0.0, 2e-6, 1e-10),
        ),
        (Load(port="tip", z=30 - 40j), "30 - j*40", (4, 30.0, -40.0, 0.0)),
    ],
)
def test_each_load_form_round_trips(load, expr, ld):
    b = _with(load)
    ssn = export_ssn(b, ground=None)
    assert f"R1 ({expr}) ld1a ld1b;" in _equ(ssn)
    assert "NECSource({ld1a,ld1b}, $GW_4, 50);" in _equ(ssn)
    c, rt = _roundtrip_builder(ssn, b.freq)
    (got,) = c.deck.loads
    assert got.wire == 3 and got.seg == 1
    ldtyp, f1, f2, f3 = ld
    if ldtyp == 4:
        assert got.z == pytest.approx(complex(f1, f2))
    else:
        assert got.parallel is (ldtyp == 1)
        assert (got.r or 0.0, got.l or 0.0, got.c or 0.0) == pytest.approx((f1, f2, f3))
    assert _z(rt) == pytest.approx(_z(b), rel=1e-6)


def test_a_finite_q_load_is_refused_by_name():
    b = _with(Load(port="tip", l=2e-6, ql=200.0))
    with pytest.raises(SsnUnsupported, match=r"Load\(tip\).*finite-Q"):
        export_ssn(b, ground=None)


@pytest.mark.parametrize(
    "load",
    [
        Load(port="feed", r=10.0),
        Load(port="feed", z=10 + 5j),
        Load(port="feed", l=2e-6, c=1e-10, parallel=True),
    ],
)
def test_a_feed_segment_load_without_a_series_element_is_refused(load):
    with pytest.raises(SsnUnsupported, match=r"Load\(feed\).*fed segment"):
        export_ssn(_with(load), ground=None)


def test_a_jacketed_design_is_refused_by_name():
    """The export writes the bare conductor and no LD 2, so the jacket would
    have been silently missing (the issue's item 3)."""
    b = _with(Load(port="tip", r=50.0), spec=wire_from_catalog("18-awg-pvc"))
    with pytest.raises(SsnUnsupported, match=r"wires 1, 2, 3, 4 carry an insul"):
        export_ssn(b, ground=None)


# --- the importer, on files it did not write ---------------------------------


def _script_ssn(tail: str) -> str:
    equ = (
        "//t\nP1 w1 gnd;\nP2 w2 gnd;\nNEC2\n"
        "GW 1 11 0 -5 10 0 5 10 0.0005\nGW 2 3 0 5 10 0 6 10 0.0005\n"
        "EX 0 1 6 0 1 0\nNECEND\n" + tail
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?><SimNEC1p0><SmithChartCircuit>'
        "<CIRCUIT><element><type>NETWORK</type><escapeHatch/>"
        f"<p><n>equ</n><v>{equ}</v></p></element></CIRCUIT>"
        "</SmithChartCircuit></SimNEC1p0>"
    )


def test_a_suffixed_load_reads_as_its_value():
    """SimNEC's own SI suffixes, as AC6LA writes his trap values."""
    c = parse_ssn(
        _script_ssn(
            "R1 (L(1.054u) ||| C(30p)) r1a r1b;  "
            "dcl T = NECSource({r1a,r1b}, $GW_2, 50);"
        ),
        network=True,
    )
    (ld,) = c.deck.loads
    assert ld.parallel and ld.l == pytest.approx(1.054e-6)
    assert ld.c == pytest.approx(30e-12)


def test_a_load_between_segment_centres_is_refused_not_moved():
    with pytest.raises(ValueError, match=r"2% of \$GW_2.*not a segment centre"):
        parse_ssn(
            _script_ssn("R1 (50) r1a r1b;  NECSource({r1a,r1b}, $GW_2, 2);"),
            network=True,
        )


def test_a_load_it_cannot_evaluate_is_reported_not_applied():
    """AC6LA's files name the values with dcl variables; they are not
    evaluated here, so both statements are reported as not applied."""
    c = parse_ssn(
        _script_ssn(
            "dcl Lt = 1u;\nR1 (L(Lt, 300) ||| C(30p)) r1a r1b;  "
            "dcl T = NECSource({r1a,r1b}, $GW_2, 50);"
        ),
        network=True,
    )
    assert c.deck.loads == ()
    assert any("NECSource" in d for d in c.ignored_directives)
    assert any(d.startswith("R1 (") for d in c.ignored_directives)
