"""SimNEC .ssn export for antenna-only designs (issue #600).

Covers the parts that are verifiable without a SimNEC/Java runtime: the
NEC-portal daemon script (geometry cards reused verbatim from ``export_nec``,
ground/units/segmentation directives) and the ``.ssn`` XML wrapper (well-formed,
carries the escaped script, frequency on the Generator). The XML scaffold's
acceptance *by SimNEC* is a separate Windows validation step.
"""

import xml.etree.ElementTree as ET
from types import MappingProxyType

import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.nec_export import export_nec
from antennaknobs.network import Wire
from antennaknobs.simnec_export import build_nec_portal_script, export_ssn


class _Dipole(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0, "design_freq": 14.0})

    def build_wires(self):
        # up at z=10 m so the ground-plane cases (pec/finite) are valid geometry
        return [Wire((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), n_seg=11, ex=1 + 0j)]


def _script(**kw):
    return build_nec_portal_script(_Dipole(), freq_mhz=14.0, **kw)


def test_geometry_cards_match_export_nec():
    """The portal script carries exactly export_nec's GW/FR/EX cards (as a set),
    regrouped into canonical GW → FR → EX order (see test_card_order_gw_fr_ex)."""
    deck = export_nec(_Dipole(), ground=None, freq=14.0, include_rp=False)
    deck_cards = {
        s.strip()
        for s in deck.splitlines()
        if s.strip().startswith(("GW ", "FR ", "EX "))
    }
    script = _script(ground=None)
    body = script.split("NEC2", 1)[1].split("NECEND", 1)[0]
    script_cards = {
        ln.strip()
        for ln in body.splitlines()
        if ln.strip().startswith(("GW ", "FR ", "EX "))
    }
    assert script_cards == deck_cards
    assert deck_cards, "expected at least one GW and one EX card"


def test_card_order_gw_fr_ex():
    """SimNEC-saved decks order GW … FR … EX; export_nec emits EX before FR, so
    the portal regroups. Guard the order the module guarantees."""
    body = _script(ground=None).split("NEC2", 1)[1].split("NECEND", 1)[0]
    kinds = [
        ln.strip()[:2]
        for ln in body.splitlines()
        if ln.strip().startswith(("GW ", "FR ", "EX "))
    ]
    assert kinds.index("GW") < kinds.index("FR") < kinds.index("EX")


def test_fr_card_is_kept():
    """FR stays in the deck — SimNEC's own .ssn carries it alongside a G.MHz
    sweep (advisory; the solve frequency comes from the Generator)."""
    body = _script(ground=None).split("NEC2", 1)[1].split("NECEND", 1)[0]
    assert "FR " in body


def test_structural_cards_are_dropped():
    script = _script(ground=None)
    body = script.split("NEC2", 1)[1].split("NECEND", 1)[0]
    for card in ("RP ", "XQ", "GE ", "GN ", "EN"):
        assert card not in body, f"{card!r} should not be inside NEC2..NECEND"
    assert "NEC2" in script and "NECEND" in script


def test_free_space_has_no_ground_call():
    script = _script(ground=None)
    assert "SommerfeldGround" not in script
    assert "PerfectGround" not in script
    assert "NECOptions.mhosPerMeter = 0;" in script


def test_pec_ground_is_perfectground():
    assert "PerfectGround();" in _script(ground="pec")


def test_finite_ground_maps_sigma_then_epsr():
    """SimNEC's SommerfeldGround(mhos, dielectric) == (sigma, eps_r) — the
    reverse of our ('finite', eps_r, sigma) tuple. Order matters."""
    script = _script(ground=("finite", 20.0, 0.0303))
    assert "SommerfeldGround(0.0303, 20);" in script


def test_seg_per_wl_directive():
    assert "NECOptions.segmentsPerWavelength = 120;" in _script(
        ground=None, seg_per_wl=120
    )
    # absent when not requested
    assert "segmentsPerWavelength" not in _script(ground=None)


def test_ports_and_units_boilerplate():
    script = _script(ground=None)
    assert "P1 w1 gnd;" in script
    assert "P2 w2 gnd;" in script
    assert "NECUnits meters, meters;" in script


def test_export_ssn_is_wellformed_xml_carrying_the_script():
    ssn = export_ssn(_Dipole(), freq_mhz=14.1, ground=None)
    root = ET.fromstring(ssn)  # raises if malformed
    # find the NETWORK element's equ param and the GENERATOR MHz
    equ = None
    mhz = None
    for el in root.iter("element"):
        typ = el.findtext("type")
        for p in el.findall("p"):
            if p.findtext("n") == "equ":
                equ = p.findtext("v")
            if typ == "GENERATOR" and p.findtext("n") == "MHz":
                mhz = p.findtext("v")
    assert equ is not None and "NEC2" in equ and "GW " in equ  # ET unescapes text
    assert mhz == "14.1"


def test_generator_impedance_uses_zo_tag():
    """SimNEC's GENERATOR impedance param is <n>Zo</n> (the LOAD uses <n>ohms</n>).
    Reconciled against a SimNEC 5.1a1-saved .ssn."""
    ssn = export_ssn(_Dipole(), freq_mhz=14.1, ground=None)
    root = ET.fromstring(ssn)
    zo = None
    for el in root.iter("element"):
        if el.findtext("type") == "GENERATOR":
            for p in el.findall("p"):
                if p.findtext("n") == "Zo":
                    zo = p.findtext("v")
            assert all(p.findtext("n") != "ohms" for p in el.findall("p"))
    assert zo == "50"


def test_version_control_string_is_simnec_shaped():
    ssn = export_ssn(_Dipole(), freq_mhz=14.1, ground=None)
    vc = ET.fromstring(ssn).find(".//XMLVersionControl").text
    assert vc.startswith("SimNEC:")


def test_name_comment_is_short_leaf_name():
    """SimNEC shows the first //comment as the block name (~12-char budget), so
    the default is the design's short leaf name — not the full dotted path."""
    # a real design → its module leaf, e.g. "invvee"
    from antennaknobs.designs.dipoles.invvee import Builder as InvVee

    assert (
        build_nec_portal_script(InvVee(), freq_mhz=14.1).splitlines()[0] == "//invvee"
    )
    # a script-defined builder (__module__ == "__main__") → the class qualname
    Script = type("FlatDoublet", (_Dipole,), {})
    Script.__module__ = "__main__"
    assert build_nec_portal_script(Script(), freq_mhz=14.0).splitlines()[0] == (
        "//FlatDoublet"
    )


def test_name_override():
    ssn = export_ssn(_Dipole(), freq_mhz=14.1, ground=None, name="dip20")
    assert "//dip20" in ssn


def test_no_generator_sweep_by_default():
    """Minimal by default: no <sweepParam> on the Generator (SimNEC supplies its
    own default, disabled range), and no SCATTERGUN arming."""
    ssn = export_ssn(_Dipole(), freq_mhz=14.1, ground=None)
    assert "<sweepParam>" not in ssn
    assert "doSweep" not in ssn
    assert "SCATTERGUN" not in ssn


def test_sweep_arms_scattergun_and_chart():
    """A requested sweep also arms it: SCATTERGUN names G.MHz (without it doSweep
    does nothing) and the chart goes to Sweep mode. ET-parseable."""
    ssn = export_ssn(_Dipole(), freq_mhz=14.1, ground=None, sweep=(13.0, 15.0))
    ET.fromstring(ssn)  # well-formed
    assert "<SCATTERGUN><n>G.MHz</n></SCATTERGUN>" in ssn
    assert "<displayMode>Sweep</displayMode>" in ssn


def test_sweep_enabled_when_requested():
    ssn = export_ssn(_Dipole(), freq_mhz=14.1, ground=None, sweep=(13.0, 15.0))
    root = ET.fromstring(ssn)  # well-formed
    gen_mhz = None
    for el in root.iter("element"):
        if el.findtext("type") == "GENERATOR":
            for p in el.findall("p"):
                if p.findtext("n") == "MHz":
                    gen_mhz = p
    sp = gen_mhz.find("sweepParam")
    assert sp is not None and sp.findtext("name") == "G.MHz"
    got = {p.findtext("n"): p.findtext("v") for p in sp.findall("p")}
    assert got["from"] == "13" and got["to"] == "15"
    assert got["doSweep"] == "y"


def test_cli_sweep_auto_band(capsys):
    """Bare --sweep enables an auto +/-10% band around the design frequency."""
    from antennaknobs.simnec_export import main

    main(["dipoles.invvee", "--freq", "10", "--sweep"])
    out = capsys.readouterr().out
    sp = ET.fromstring(out).find(".//sweepParam")
    got = {p.findtext("n"): p.findtext("v") for p in sp.findall("p")}
    assert got["from"] == "9" and got["to"] == "11" and got["doSweep"] == "y"


def test_networked_design_raises():
    from antennaknobs.designs.wire.zepp import Builder as Zepp

    with pytest.raises(NotImplementedError):
        export_ssn(Zepp(), freq_mhz=14.1, ground=None)


def test_smoke_real_builtin_antenna_only():
    from antennaknobs.designs.dipoles.invvee import Builder as InvVee

    ssn = export_ssn(InvVee(), ground=("finite", 13.0, 0.005), seg_per_wl=80)
    ET.fromstring(ssn)  # well-formed
    assert "SommerfeldGround(0.005, 13);" in ssn
    assert "segmentsPerWavelength = 80;" in ssn
