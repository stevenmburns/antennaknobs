"""SimNEC .ssn import (the read-side twin of ``simnec_export``).

Round-trips against ``export_ssn`` cover the exporter-shaped files; hand-written
XML covers the foreign-file cases (units, station elements, unknown directives,
malformed input) a SimNEC-saved circuit can carry.
"""

from types import MappingProxyType

import pytest

from antennaknobs import user_designs
from antennaknobs.builder import AntennaBuilder
from antennaknobs.network import (
    TL,
    Driven,
    PortVirtual,
    Shunt,
    Transformer,
    TwoPort,
    Wire,
)
from antennaknobs.simnec_export import export_ssn
from antennaknobs.simnec_import import parse_ssn, read_ssn


class _Dipole(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0, "design_freq": 14.0})

    def build_wires(self):
        # up at z=10 m so the ground-plane cases (pec/finite) are valid geometry
        return [Wire((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), n_seg=11, ex=1 + 0j)]


def _roundtrip(**export_kw):
    return parse_ssn(export_ssn(_Dipole(), **export_kw), name="rt.ssn")


# A hand-written .ssn in the shape SimNEC saves (minimal), with the script
# injectable so foreign-dialect cases are easy to express.
def _ssn(script, extra_elements="", generator=True):
    gen = (
        """
            <element>
                <type>GENERATOR</type>
                <p><n>MHz</n><v>7.1</v></p>
                <p><n>Zo</n><v>50</v></p>
            </element>"""
        if generator
        else ""
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<SimNEC1p0>
    <SmithChartCircuit>
        <XMLVersionControl>SimNEC:5.1a1</XMLVersionControl>
        <CIRCUIT>
            <element>
                <type>LOAD</type>
                <p><n>ohms</n><v>1000000000</v></p>
            </element>
            <element>
                <type>NETWORK</type>
                <escapeHatch/>
                <p><n>equ</n><v>{script}</v></p>
            </element>{extra_elements}{gen}
        </CIRCUIT>
    </SmithChartCircuit>
</SimNEC1p0>
"""


_SCRIPT_M = """//dip40
P1 w1 gnd;
P2 w2 gnd;
NECUnits meters, meters;
NEC2
GW 1 11 0 -5 10 0 5 10 0.0005
FR 0 1 0 0 7.1 0
EX 0 1 6 0 1 0
NECEND"""


# --- round-trips against the exporter ---------------------------------------


def test_roundtrip_geometry_and_feed():
    c = _roundtrip(freq_mhz=14.1, ground=None)
    (w,) = c.deck.wires
    assert w.p1 == (0.0, -5.0, 10.0) and w.p2 == (0.0, 5.0, 10.0)
    assert w.n_seg == 11 and w.radius == pytest.approx(0.0005)
    (f,) = c.deck.feeds
    assert (f.wire, f.seg, f.voltage) == (0, 6, 1 + 0j)


def test_roundtrip_frequency_comes_from_generator():
    c = _roundtrip(freq_mhz=14.1, ground=None)
    assert c.freq_mhz == pytest.approx(14.1)
    # the deck's advisory FR is still visible on the deck itself
    assert c.deck.freq_mhz == (pytest.approx(14.1), pytest.approx(14.1))


def test_roundtrip_grounds():
    assert _roundtrip(freq_mhz=14.1, ground=None).ground is None
    assert _roundtrip(freq_mhz=14.1, ground="pec").ground == "pec"
    g = _roundtrip(freq_mhz=14.1, ground=("finite", 20.0, 0.0303)).ground
    assert g[0] == "finite"
    assert g[1] == pytest.approx(20.0) and g[2] == pytest.approx(0.0303)
    # a SommerfeldGround maps back as the accurate model even from finite-fast
    g = _roundtrip(freq_mhz=14.1, ground=("finite-fast", 13.0, 0.005)).ground
    assert g == ("finite", pytest.approx(13.0), pytest.approx(0.005))


def test_roundtrip_ground_sets_deck_flag():
    assert _roundtrip(freq_mhz=14.1, ground="pec").deck.ground is True
    assert _roundtrip(freq_mhz=14.1, ground=None).deck.ground is False


def test_roundtrip_seg_per_wl_and_name():
    c = _roundtrip(freq_mhz=14.1, ground=None, seg_per_wl=120, name="dip20")
    assert c.seg_per_wl == 120
    assert c.name == "dip20"
    assert _roundtrip(freq_mhz=14.1, ground=None).seg_per_wl is None


def test_roundtrip_sweep():
    assert _roundtrip(freq_mhz=14.1, ground=None).sweep is None
    c = _roundtrip(freq_mhz=14.1, ground=None, sweep=(13.0, 15.0))
    assert c.sweep == (pytest.approx(13.0), pytest.approx(15.0))


def test_roundtrip_scaffold_is_not_reported():
    """The exporter's open LOAD + 50 Ohm GENERATOR are scaffold, not station
    elements; a clean round-trip has nothing to warn about."""
    c = _roundtrip(freq_mhz=14.1, ground=None)
    assert c.other_elements == ()
    assert c.ignored_directives == ()
    assert c.gen_zo == pytest.approx(50.0)
    assert c.skipped_note() is None


def test_roundtrip_real_builtin_design():
    from antennaknobs.designs.dipoles.invvee import Builder as InvVee

    ssn = export_ssn(InvVee(), ground=("finite", 13.0, 0.005), seg_per_wl=80)
    c = parse_ssn(ssn, name="invvee.ssn")
    assert c.name == "invvee"
    assert len(c.deck.wires) >= 2 and len(c.deck.feeds) == 1
    assert c.ground == ("finite", pytest.approx(13.0), pytest.approx(0.005))


# --- foreign files -----------------------------------------------------------


def test_hand_written_minimal_file():
    c = parse_ssn(_ssn(_SCRIPT_M), name="t.ssn")
    assert c.name == "dip40"
    assert c.freq_mhz == pytest.approx(7.1)
    (w,) = c.deck.wires
    assert w.p2 == (0.0, 5.0, 10.0)


def test_necunits_feet_scales_to_metres():
    script = _SCRIPT_M.replace("NECUnits meters, meters;", "NECUnits feet, feet;")
    (w,) = parse_ssn(_ssn(script), name="t.ssn").deck.wires
    assert w.p2[1] == pytest.approx(5 * 0.3048)
    assert w.p2[2] == pytest.approx(10 * 0.3048)
    assert w.radius == pytest.approx(0.0005 * 0.3048)


def test_necunits_mixed_units_scale_radius_separately():
    script = _SCRIPT_M.replace("NECUnits meters, meters;", "NECUnits feet, mm;")
    (w,) = parse_ssn(_ssn(script), name="t.ssn").deck.wires
    assert w.p2[1] == pytest.approx(5 * 0.3048)
    assert w.radius == pytest.approx(0.0005 * 0.001)


def test_necunits_unknown_unit_raises():
    script = _SCRIPT_M.replace("NECUnits meters, meters;", "NECUnits cubits, m;")
    with pytest.raises(ValueError, match="cubits"):
        parse_ssn(_ssn(script), name="t.ssn")


def test_wire_conductivity_directive():
    script = _SCRIPT_M.replace("NEC2", "NECOptions.mhosPerMeter = 5.8e7;\nNEC2")
    c = parse_ssn(_ssn(script), name="t.ssn")
    assert c.conductivity == pytest.approx(5.8e7)
    # 0 = perfect wires -> None
    script = _SCRIPT_M.replace("NEC2", "NECOptions.mhosPerMeter = 0;\nNEC2")
    assert parse_ssn(_ssn(script), name="t.ssn").conductivity is None


def test_non_open_load_is_recorded():
    ssn = _ssn(_SCRIPT_M).replace("1000000000", "50")
    c = parse_ssn(ssn, name="t.ssn")
    assert "LOAD" in c.other_elements


def test_unknown_directive_is_recorded():
    script = _SCRIPT_M.replace("NEC2", "FancyNewThing(1, 2);\nNEC2")
    c = parse_ssn(_ssn(script), name="t.ssn")
    assert c.ignored_directives == ("FancyNewThing(1, 2)",)
    assert "FancyNewThing" in c.skipped_note()


def test_missing_generator_leaves_freq_none():
    c = parse_ssn(_ssn(_SCRIPT_M, generator=False), name="t.ssn")
    assert c.freq_mhz is None and c.gen_zo is None
    # the deck's advisory FR still gives the caller a band to seed from
    assert c.deck.freq_mhz == (pytest.approx(7.1), pytest.approx(7.1))


def test_network_mode_translates_lumped_loads():
    script = _SCRIPT_M.replace("FR 0", "LD 0 1 3 3 10 2.5e-6 0\nFR 0")
    c = parse_ssn(_ssn(script), name="t.ssn", network=True)
    (ld,) = c.deck.loads
    assert (ld.r, ld.l) == (10.0, 2.5e-6)
    net = c.deck.network()  # ready for build_network
    assert net.sources


def test_malformed_xml_raises_with_name():
    with pytest.raises(ValueError, match=r"bad\.ssn.*not well-formed"):
        parse_ssn("<SimNEC1p0><oops>", name="bad.ssn")


def test_non_circuit_xml_raises():
    with pytest.raises(ValueError, match="no <CIRCUIT> elements"):
        parse_ssn("<foo><bar/></foo>", name="t.ssn")


def test_no_nec_block_raises():
    ssn = _ssn("P1 w1 gnd; // just a circuit script, no NEC cards")
    with pytest.raises(ValueError, match="no NEC-portal antenna block"):
        parse_ssn(ssn, name="t.ssn")


def test_two_nec_blocks_raise():
    extra = f"""
            <element>
                <type>NETWORK</type>
                <escapeHatch/>
                <p><n>equ</n><v>{_SCRIPT_M}</v></p>
            </element>"""
    with pytest.raises(ValueError, match="2 NEC-portal blocks"):
        parse_ssn(_ssn(_SCRIPT_M, extra_elements=extra), name="t.ssn")


def test_missing_necend_raises():
    script = _SCRIPT_M.replace("\nNECEND", "")
    with pytest.raises(ValueError, match="missing its NECEND"):
        parse_ssn(_ssn(script), name="t.ssn")


def test_stray_en_card_does_not_defeat_units_or_ground():
    """An EN inside the block must not truncate the appended GS/GE cards."""
    script = _SCRIPT_M.replace(
        "NECUnits meters, meters;", "NECUnits feet, feet;\nPerfectGround();"
    ).replace("NECEND", "EN\nNECEND")
    c = parse_ssn(_ssn(script), name="t.ssn")
    assert c.deck.wires[0].p2[1] == pytest.approx(5 * 0.3048)
    assert c.ground == "pec" and c.deck.ground is True


# --- station chains (the read side of the #604 station export) ---------------


def _el(typ, params, label=None):
    """One chain <element> in the station exporter's emission shape."""
    lbl = f"<sweeperLabel>{label}</sweeperLabel>" if label else ""
    ps = "".join(f"<p><n>{n}</n><v>{v}</v></p>" for n, v in params.items())
    return f"""
            <element>
                <type>{typ}</type>{lbl}{ps}
            </element>"""


# The Track-1 ladder tuner's cascade, in .ssn file order (right-to-left saves
# put the antenna-side element first): openwire line, 500 pF line-side cap,
# tee coil, 81.2 pF rig-side cap — exactly what the station exporter emits
# for wire.doublet_ladder_tuner.
_LADDER = (
    _el(
        "SERIES_TLINE",
        {
            "Zo": 600,
            "VFnom": 0.95,
            "ft": 100,
            "k0": 0,
            "k1": 0.02,
            "k2": 0.0001,
        },
        label="T1",
    )
    + _el("SERIES_CAP", {"F": "5e-10", "Q": 0, "@MHz": 7.1}, label="C2")
    + _el("SHUNT_IND", {"H": "4.218e-06", "Q": 200, "@MHz": 7.1}, label="L1")
    + _el("SERIES_CAP", {"F": "8.12e-11", "Q": 0, "@MHz": 7.1}, label="C1")
)


def test_station_chain_is_parsed_generator_to_antenna():
    c = parse_ssn(_ssn(_SCRIPT_M, extra_elements=_LADDER), name="t.ssn")
    assert [el.typ for el in c.chain] == [
        "SERIES_CAP",
        "SHUNT_IND",
        "SERIES_CAP",
        "SERIES_TLINE",
    ]
    assert [el.label for el in c.chain] == ["C1", "L1", "C2", "T1"]
    # every chain element is translatable — nothing to warn about
    assert c.other_elements == ()
    assert c.skipped_note() is None


def test_station_network_rebuilds_the_full_ladder():
    """network() is the inverse of the station exporter's cascade walk: the
    Driven moves to a virtual rig node and the chain hangs rig → … → feed."""
    c = parse_ssn(_ssn(_SCRIPT_M, extra_elements=_LADDER), name="t.ssn", network=True)
    net = c.network()
    (src,) = net.sources
    assert isinstance(src, Driven) and src.port == "rig"
    assert isinstance(net.ports["rig"], PortVirtual)

    tl = next(b for b in net.branches if isinstance(b, TL))
    assert (tl.a, tl.b) == ("chain2", "feed")
    assert tl.z0 == pytest.approx(600.0)
    assert tl.length == pytest.approx(100 * 0.3048)
    assert tl.vf == pytest.approx(0.95)
    assert tl.k1 == pytest.approx(0.02) and tl.k2 == pytest.approx(0.0001)

    caps = [b for b in net.branches if isinstance(b, TwoPort)]
    assert [(b.a, b.b) for b in caps] == [("rig", "chain1"), ("chain1", "chain2")]
    assert caps[0].c == pytest.approx(8.12e-11)  # rig-side C1
    assert caps[1].c == pytest.approx(5e-10)  # line-side C2
    assert caps[0].qc is None  # Q = 0 -> the ideal component

    (coil,) = [b for b in net.branches if isinstance(b, Shunt)]
    assert coil.port == "chain1"  # the tee node, between the caps
    assert coil.l == pytest.approx(4.218e-6) and coil.ql == pytest.approx(200.0)


def test_station_deck_trap_loads_ride_along():
    """Trap Loads travel as deck LD cards on export; they come back as Load
    branches next to the chain."""
    from antennaknobs.network import Load

    script = _SCRIPT_M.replace("FR 0", "LD 0 1 3 3 10 2.5e-6 0\nFR 0")
    c = parse_ssn(_ssn(script, extra_elements=_LADDER), name="t.ssn", network=True)
    net = c.network()
    assert any(isinstance(b, Load) for b in net.branches)
    (src,) = net.sources
    assert src.port == "rig"


def test_station_ideal_transformer2():
    extra = _el("TRANSFORMER2", {"Mdl": "ideal", "N": 2}, label="X1")
    c = parse_ssn(_ssn(_SCRIPT_M, extra_elements=extra), name="t.ssn", network=True)
    (x,) = [b for b in c.network().branches if isinstance(b, Transformer)]
    # SimNEC's N is the antenna:generator voltage ratio (validated on 5.1a0,
    # PR #696), so entered generator-side, Transformer n = 1/N.
    assert (x.a, x.b, x.n) == ("rig", "feed", 0.5)


def test_station_non_ideal_transformer2_rejected():
    extra = _el("TRANSFORMER2", {"Mdl": "lossy", "N": 2})
    c = parse_ssn(_ssn(_SCRIPT_M, extra_elements=extra), name="t.ssn", network=True)
    with pytest.raises(ValueError, match="ideal"):
        c.network()


def test_station_k0_loss_rejected():
    extra = _el("SERIES_TLINE", {"Zo": 50, "ft": 100, "k0": 0.5})
    c = parse_ssn(_ssn(_SCRIPT_M, extra_elements=extra), name="t.ssn", network=True)
    with pytest.raises(ValueError, match="k0"):
        c.network()


def test_station_shunt_only_chain_hangs_across_the_feed():
    """With no series element between generator and feed, the shunts sit
    straight across the feed terminals and the Driven stays at the feed."""
    extra = _el("SHUNT_CAP", {"F": "1e-10"})
    c = parse_ssn(_ssn(_SCRIPT_M, extra_elements=extra), name="t.ssn", network=True)
    net = c.network()
    (sh,) = [b for b in net.branches if isinstance(b, Shunt)]
    assert sh.port == "feed" and sh.c == pytest.approx(1e-10)
    (src,) = net.sources
    assert src.port == "feed"
    assert "rig" not in net.ports


def test_station_unknown_chain_element_recorded_and_refused():
    """An untranslatable element inside the cascade is reported, and
    network() refuses rather than silently dropping it from the circuit."""
    extra = _el("SERIES_RES", {"ohms": 10}) + _el("SHUNT_CAP", {"F": "1e-10"})
    c = parse_ssn(_ssn(_SCRIPT_M, extra_elements=extra), name="t.ssn", network=True)
    assert c.other_elements == ("SERIES_RES",)
    assert "SERIES_RES" in c.skipped_note()
    with pytest.raises(ValueError, match="SERIES_RES"):
        c.network()


def test_station_missing_param_names_the_element():
    extra = _el("SERIES_IND", {"Q": 100}, label="L1")
    c = parse_ssn(_ssn(_SCRIPT_M, extra_elements=extra), name="t.ssn", network=True)
    with pytest.raises(ValueError, match="SERIES_IND element L1.*'H'"):
        c.network()


def test_antenna_only_network_is_the_deck_network():
    c = parse_ssn(_ssn(_SCRIPT_M), name="t.ssn", network=True)
    net = c.network()
    (src,) = net.sources
    assert src.port == "feed"
    assert "rig" not in net.ports


def test_station_network_requires_network_mode():
    c = parse_ssn(_ssn(_SCRIPT_M, extra_elements=_LADDER), name="t.ssn")
    with pytest.raises(ValueError, match="network=True"):
        c.network()


# --- the design-stub consumption path ----------------------------------------

SSN_DESIGN = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder, read_ssn

class Builder(AntennaBuilder):
    default_params = MappingProxyType({"freq": 7.1})

    def build_wires(self):
        return read_ssn(self, "antenna.ssn", network=True).deck.wire_tuples(
            specs=True
        )

    def build_network(self):
        return read_ssn(self, "antenna.ssn", network=True).network()
"""


def test_read_ssn_from_a_user_design(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    (tmp_path / "ssn_design.py").write_text(SSN_DESIGN)
    (tmp_path / "antenna.ssn").write_text(export_ssn(_Dipole(), freq_mhz=14.0))
    cls = user_designs.resolve_user_design("ssn_design")
    b = cls()
    wires = b.build_wires()
    assert wires and any(len(w) >= 4 for w in wires)
    net = b.build_network()
    assert net.sources


def test_read_ssn_confined_to_design_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    (tmp_path / "ssn_design.py").write_text(SSN_DESIGN)
    (tmp_path / "antenna.ssn").write_text(export_ssn(_Dipole(), freq_mhz=14.0))
    b = user_designs.resolve_user_design("ssn_design")()
    with pytest.raises(ValueError, match="absolute"):
        read_ssn(b, "/etc/passwd")


# --- full round-trip: export_ssn -> parse_ssn, both sides on one branch ------


class _XfmrStation(AntennaBuilder):
    """n=2 ideal transformer between rig and dipole — pins the reciprocal
    TRANSFORMER2 N convention END TO END (export emits N=1/n, import reads
    n=1/N; the SimNEC 5.1a0 validation finding from PR #696), so the pair
    cannot drift apart again."""

    default_params = MappingProxyType({"freq": 14.0, "design_freq": 14.0})

    def build_wires(self):
        return [Wire((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), n_seg=11, name="feed")]

    def build_network(self):
        from antennaknobs.network import Network, PortOnWire

        return Network(
            ports={"feed": PortOnWire("feed"), "rig": PortVirtual("rig")},
            branches=[Transformer(a="rig", b="feed", n=2.0)],
            sources=[Driven(port="rig")],
        )


def test_roundtrip_transformer_n_identity():
    ssn = export_ssn(_XfmrStation(), freq_mhz=14.0, ground=None)
    net = parse_ssn(ssn, name="rt.ssn", network=True).network()
    (x,) = [b for b in net.branches if isinstance(b, Transformer)]
    assert x.n == pytest.approx(2.0)


def test_roundtrip_ladder_tuner_values():
    """The catalog station whose cascade was load-validated in SimNEC:
    every element value survives export -> import unchanged."""
    from antennaknobs.designs.wire.doublet_ladder_tuner import Builder

    ssn = export_ssn(Builder(), ground=None)
    net = parse_ssn(ssn, name="rt.ssn", network=True).network()
    (tl,) = [b for b in net.branches if isinstance(b, TL)]
    assert tl.z0 == pytest.approx(600.0) and tl.vf == pytest.approx(0.95)
    assert tl.k1 == pytest.approx(0.02) and tl.k2 == pytest.approx(0.0001)
    assert tl.length == pytest.approx(30.48)  # 100 ft
    caps = sorted(
        (b.c for b in net.branches if isinstance(b, TwoPort) and b.c is not None)
    )
    assert caps == [pytest.approx(8.12e-11), pytest.approx(5e-10)]
    (coil,) = [b for b in net.branches if isinstance(b, Shunt)]
    assert coil.l == pytest.approx(4.218e-6) and coil.ql == pytest.approx(200.0)
