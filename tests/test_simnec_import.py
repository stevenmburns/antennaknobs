"""SimNEC .ssn import (the read-side twin of ``simnec_export``).

Round-trips against ``export_ssn`` cover the exporter-shaped files; hand-written
XML covers the foreign-file cases (units, station elements, unknown directives,
malformed input) a SimNEC-saved circuit can carry.
"""

from types import MappingProxyType

import pytest

from antennaknobs import user_designs
from antennaknobs.builder import AntennaBuilder
from antennaknobs.network import Wire
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


def test_station_elements_are_recorded_not_translated():
    extra = """
            <element>
                <type>SERIES_TLINE</type>
                <p><n>Zo</n><v>450</v></p>
            </element>
            <element>
                <type>SHUNT_CAP</type>
                <p><n>pF</n><v>74</v></p>
            </element>"""
    c = parse_ssn(_ssn(_SCRIPT_M, extra_elements=extra), name="t.ssn")
    assert c.other_elements == ("SERIES_TLINE", "SHUNT_CAP")
    note = c.skipped_note()
    assert "SERIES_TLINE" in note and "antenna block only" in note
    # the antenna still imported
    assert len(c.deck.wires) == 1


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
        return read_ssn(self, "antenna.ssn", network=True).deck.network()
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
