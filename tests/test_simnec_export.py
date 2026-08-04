"""SimNEC .ssn export — antenna-only (issue #600) and stations (issue #604).

Covers the parts that are verifiable without a SimNEC/Java runtime: the
NEC-portal daemon script (geometry cards reused verbatim from ``export_nec``,
ground/units/segmentation directives), the ``.ssn`` XML wrapper (well-formed,
carries the escaped script, frequency on the Generator), and for stations the
branch→element cascade mapping plus the common-mode rejections. The XML
scaffold's acceptance *by SimNEC* is a separate Windows validation step.
"""

import xml.etree.ElementTree as ET
from types import MappingProxyType

import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.nec_export import export_nec
from antennaknobs.network import (
    TL,
    BalancedLine,
    Driven,
    DrivenCurrent,
    FloatingBalun,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
    Transformer,
    Wire,
)
from antennaknobs.simnec_export import (
    SsnUnsupported,
    build_nec_portal_script,
    export_ssn,
)


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


def test_generator_is_measured_block():
    """The GENERATOR carries showInSmith so its impedance is measured/displayed
    (and plotted during a sweep) without the user turning a block on."""
    ssn = export_ssn(_Dipole(), freq_mhz=14.1, ground=None)
    root = ET.fromstring(ssn)
    gen = next(el for el in root.iter("element") if el.findtext("type") == "GENERATOR")
    assert gen.findtext("showInSmith") == "true"


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


def test_cli_writes_utf8_even_under_a_non_utf8_default(tmp_path, cp1252_default_open):
    """``--name`` is echoed verbatim into the script's first //comment; a
    name outside cp1252 reproduces the Windows failure mode here on Linux
    (issue #772). Real CLI, real export_ssn, no mocking — the write site is
    exercised exactly as a user hits it."""
    from antennaknobs.simnec_export import main

    out = tmp_path / "deck.ssn"
    main(["dipoles.invvee", "--freq", "14.1", "--name", "Ω-tuned", "--out", str(out)])

    text = out.read_text(encoding="utf-8")
    assert "Ω-tuned" in text


# --- phase 2: networked (station) export — issue #604 -----------------------


def _types_in_order(ssn):
    root = ET.fromstring(ssn)
    return [el.findtext("type") for el in root.iter("element")]


def _params_of(ssn, typ, label=None):
    """{name: value} of the first <element> of ``typ`` (and sweeperLabel, if
    given)."""
    for el in ET.fromstring(ssn).iter("element"):
        if el.findtext("type") != typ:
            continue
        if label is not None and el.findtext("sweeperLabel") != label:
            continue
        return {p.findtext("n"): p.findtext("v") for p in el.findall("p")}
    raise AssertionError(f"no {typ} element in .ssn")


class _NamedDipole(AntennaBuilder):
    """One wire named "feed" — the minimal real-port anchor for synthetic
    station networks (the network itself comes from a per-test subclass)."""

    default_params = MappingProxyType({"freq": 14.0, "design_freq": 14.0})

    def build_wires(self):
        return [Wire((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), n_seg=11, name="feed")]


class _TwoArm(AntennaBuilder):
    """Two named arm wires (fL/fR) — the anchor for the four-terminal
    (BalancedLine / FloatingBalun) rejection cases: both pair terminals land
    on radiating wires, so the Network's common-mode validation passes and
    the exporter's own rejection is what fires."""

    default_params = MappingProxyType({"freq": 14.0, "design_freq": 14.0})

    def build_wires(self):
        return [
            Wire((0.0, -5.0, 10.0), (0.0, -0.1, 10.0), n_seg=11, name="fL"),
            Wire((0.0, 0.1, 10.0), (0.0, 5.0, 10.0), n_seg=11, name="fR"),
        ]


def test_station_ladder_tuner_full_cascade():
    """The showcase station (Track 1 of the SimNEC comparison): 88 ft doublet
    → 100 ft openwire-600 → T-network tuner → rig. Every reducer branch lands
    as a SimNEC element, in cascade order (file order is right-to-left:
    antenna side first, generator last)."""
    from antennaknobs.designs.wire.doublet_ladder_tuner import Builder

    ssn = export_ssn(Builder(), ground=None)
    assert _types_in_order(ssn) == [
        "LOAD",
        "NETWORK",
        "SERIES_TLINE",  # the openwire line, antenna side
        "SERIES_CAP",  # C2 (500 pF, line side of the tee)
        "SHUNT_IND",  # the tee coil
        "SERIES_CAP",  # C1 (81.2 pF, rig side)
        "GENERATOR",
    ]
    tl = _params_of(ssn, "SERIES_TLINE")
    assert tl["Zo"] == "600" and tl["VFnom"] == "0.95" and tl["ft"] == "100"
    assert tl["k1"] == "0.02" and tl["k2"] == "0.0001"
    coil = _params_of(ssn, "SHUNT_IND")
    assert coil["H"] == "4.218e-06"
    assert coil["Q"] == "200" and coil["@MHz"] == "7.1"
    # Walk-order labels: C1 is the rig-side cap — which is the design's
    # series_c1_pF (81.2 pF); C2 the 500 pF line-side cap.
    assert _params_of(ssn, "SERIES_CAP", label="C1")["F"] == "8.12e-11"
    assert _params_of(ssn, "SERIES_CAP", label="C2")["F"] == "5e-10"


def test_station_deck_drives_the_feed_port():
    """The NEC block carries the antenna alone — geometry, FR, and an EX
    delta gap at the station's feed port (where the cascade attaches)."""
    from antennaknobs.designs.wire.doublet_ladder_tuner import Builder

    ssn = export_ssn(Builder(), ground=None)
    equ = _params_of(ssn, "NETWORK")["equ"]
    body = equ.split("NEC2", 1)[1].split("NECEND", 1)[0]
    kinds = [ln.strip().split()[0] for ln in body.splitlines() if ln.strip()]
    assert kinds.count("EX") == 1 and kinds.count("FR") == 1
    assert kinds.index("GW") < kinds.index("FR") < kinds.index("EX")


def test_station_ideal_transformer_maps_to_transformer2():
    class _Xfmr(_NamedDipole):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "rig": PortVirtual("rig")},
                branches=[Transformer(a="rig", b="feed", n=2.0)],
                sources=[Driven(port="rig")],
            )

    ssn = export_ssn(_Xfmr(), freq_mhz=14.0, ground=None)
    x = _params_of(ssn, "TRANSFORMER2")
    assert x["Mdl"] == "ideal" and x["N"] == "2"

    class _XfmrFlipped(_NamedDipole):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "rig": PortVirtual("rig")},
                branches=[Transformer(a="feed", b="rig", n=2.0)],
                sources=[Driven(port="rig")],
            )

    # Entered at b: the generator-side ratio inverts.
    ssn = export_ssn(_XfmrFlipped(), freq_mhz=14.0, ground=None)
    assert _params_of(ssn, "TRANSFORMER2")["N"] == "0.5"


def test_station_lossy_transformer_rejected():
    class _Lossy(_NamedDipole):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "rig": PortVirtual("rig")},
                branches=[Transformer(a="rig", b="feed", n=1.0, lmag=10e-6)],
                sources=[Driven(port="rig")],
            )

    with pytest.raises(SsnUnsupported, match="ideal"):
        export_ssn(_Lossy(), freq_mhz=14.0, ground=None)


def test_station_rejects_common_mode_balancedline():
    """The fundamental limitation (issue #604): a zcomm-carrying line's
    physics cannot be represented by SimNEC's purely differential
    SERIES_TLINE — reject, naming the branch, rather than silently dropping
    the common mode."""

    class _Zcomm(_TwoArm):
        def build_network(self):
            return Network(
                ports={
                    "fL": PortOnWire("fL"),
                    "fR": PortOnWire("fR"),
                    "li1": PortVirtual("li1"),
                    "li2": PortVirtual("li2"),
                },
                branches=[
                    BalancedLine(
                        a1="li1",
                        a2="li2",
                        b1="fL",
                        b2="fR",
                        zdiff=450.0,
                        length=10.0,
                        zcomm=200.0,
                    )  # fmt: skip
                ],
                sources=[Driven(port="li1")],
            )

    with pytest.raises(SsnUnsupported, match="zcomm.*BalancedLine|BalancedLine.*zcomm"):
        export_ssn(_Zcomm(), freq_mhz=14.0, ground=None)


def test_station_rejects_cm_open_balancedline_too():
    """Even a differential-only (zcomm=None) BalancedLine has no faithful
    two-terminal cascade equivalent — the pair topology itself is the
    problem, not just the common-mode block."""

    class _Pair(_TwoArm):
        def build_network(self):
            return Network(
                ports={
                    "fL": PortOnWire("fL"),
                    "fR": PortOnWire("fR"),
                    "li1": PortVirtual("li1"),
                    "li2": PortVirtual("li2"),
                },
                branches=[
                    BalancedLine(
                        a1="li1",
                        a2="li2",
                        b1="fL",
                        b2="fR",
                        zdiff=450.0,
                        length=10.0,
                    ),  # fmt: skip
                    # Grounds li2's common mode so the Network itself builds;
                    # the exporter's rejection is what we're testing.
                    Shunt(port="li2", c=100e-12),
                ],
                sources=[Driven(port="li1")],
            )

    with pytest.raises(SsnUnsupported, match="four-terminal"):
        export_ssn(_Pair(), freq_mhz=14.0, ground=None)


def test_station_rejects_floating_balun():
    class _Balun(_TwoArm):
        def build_network(self):
            return Network(
                ports={
                    "fL": PortOnWire("fL"),
                    "fR": PortOnWire("fR"),
                    "rig": PortVirtual("rig"),
                },
                branches=[FloatingBalun(primary="rig", a="fL", b="fR", n=1.0)],
                sources=[Driven(port="rig")],
            )

    with pytest.raises(SsnUnsupported, match="FloatingBalun"):
        export_ssn(_Balun(), freq_mhz=14.0, ground=None)


def test_station_rejects_branching_topology():
    """SimNEC's circuit is one generator→antenna ladder; a tee to a second
    chain is not exportable."""

    class _Tee(_NamedDipole):
        def build_network(self):
            return Network(
                ports={
                    "feed": PortOnWire("feed"),
                    "rig": PortVirtual("rig"),
                    "x": PortVirtual("x"),
                },
                branches=[
                    TL(a="rig", b="feed", z0=50.0, length=10.0),
                    TL(a="rig", b="x", z0=50.0, length=5.0),
                    Shunt(port="x", c=100e-12),
                ],
                sources=[Driven(port="rig")],
            )

    with pytest.raises(SsnUnsupported, match="cascade|ladder"):
        export_ssn(_Tee(), freq_mhz=14.0, ground=None)


def test_station_rejects_current_source():
    class _ISrc(_NamedDipole):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "rig": PortVirtual("rig")},
                branches=[TL(a="rig", b="feed", z0=50.0, length=10.0)],
                sources=[DrivenCurrent(port="rig")],
            )

    with pytest.raises(SsnUnsupported, match="voltage source"):
        export_ssn(_ISrc(), freq_mhz=14.0, ground=None)


def test_station_rejects_distributed_feed_port():
    """zepp's finite-gap (distributed) port is a different feed model from
    the deck's single-segment EX delta gap — rejected, not approximated.
    (This keeps the phase-1 'networked design raises' contract for zepp:
    SsnUnsupported IS a NotImplementedError.)"""
    from antennaknobs.designs.wire.zepp import Builder as Zepp

    with pytest.raises(SsnUnsupported, match="distributed"):
        export_ssn(Zepp(), freq_mhz=14.1, ground=None)


def test_station_sweep_composes():
    from antennaknobs.designs.wire.doublet_ladder_tuner import Builder

    ssn = export_ssn(Builder(), ground=None, sweep=(6.9, 7.3))
    ET.fromstring(ssn)  # well-formed with both chain and sweep state
    assert "<SCATTERGUN><n>G.MHz</n></SCATTERGUN>" in ssn
    got = {
        p.findtext("n"): p.findtext("v")
        for p in ET.fromstring(ssn).find(".//sweepParam").findall("p")
    }
    assert got["from"] == "6.9" and got["to"] == "7.3"


def test_station_cli_smoke(capsys):
    from antennaknobs.simnec_export import main

    main(["wire.doublet_ladder_tuner", "--ground", "free"])
    out = capsys.readouterr().out
    assert "SERIES_TLINE" in out and ET.fromstring(out) is not None


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
