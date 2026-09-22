"""SimNEC export writes a self-tuning L tuner back as an XMATCH (AK#1662).

A low- or high-pass tuner is SimNEC's own LC matching component in automatic
mode, so a ``.ssn`` round trips as a tuner: SimNEC tunes the element against
its antenna solve, as the app tunes against its own. What SimNEC's element
cannot say is refused by name, pointing at ``freeze_tuners``, which writes the
tuned parts as fixed elements instead. And no export ever writes a tuner's
bypass, which is a plain wire.
"""

from __future__ import annotations

import re

import pytest

from antennaknobs.auto_match import find_tuners
from antennaknobs.network import Driven, Instance, Network, PortOnWire, PortVirtual
from antennaknobs.simnec_export import SsnUnsupported, _station_chain, export_ssn
from antennaknobs.simnec_import import parse_ssn
from antennaknobs.station import l_network_tuner, t_network_tuner


def _skyloop(box):
    """The catalog skyloop fed through ``box``. On the exporter's default
    finite ground momwire, which it tunes on, sees about 128.5 + j53.8 ohm
    at the 3.8 MHz design frequency."""
    from antennaknobs.designs.loops.skyloop_lmatch import Builder as Skyloop

    class Tuned(Skyloop):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "in": PortVirtual("in")},
                branches=[Instance("match", box, rig="in", out="feed")],
                sources=[Driven(port="in", voltage=1 + 0j)],
            )

    return Tuned()


def _l(**kw):
    return l_network_tuner(**({"tune_to": 50.0, "ql": 200.0, "qc": 2000.0} | kw))


def _elements(ssn: str) -> list[str]:
    return re.findall(r"<type>(\w+)</type>", ssn)


def _xmatch_params(ssn: str) -> dict[str, str]:
    body = ssn[ssn.index("<type>XMATCH</type>") :]
    body = body[: body.index("</element>")]
    return dict(re.findall(r"<p><n>([^<]+)</n><v>([^<]*)</v></p>", body))


# --- the element -------------------------------------------------------------


@pytest.mark.parametrize("mode", ["low", "high"])
def test_a_low_or_high_tuner_is_one_xmatch(mode):
    ssn = export_ssn(_skyloop(_l(mode=mode, shunt_at="auto")))
    assert _elements(ssn) == ["LOAD", "NETWORK", "XMATCH", "GENERATOR"]
    assert _xmatch_params(ssn) == {
        "mode": "auto",
        "pass": mode,
        "R": "50",
        "X": "0",
        "Qc": "2000",
        "Ql": "200",
        "MHz": "3.8",
    }


def test_it_round_trips_as_the_same_tuner(tmp_path):
    b = _skyloop(_l(tune_at_mhz=3.75, shunt_at="auto", ql=150.0, qc=None))
    ssn = export_ssn(b)
    [t] = find_tuners(parse_ssn(ssn, network=True).network())
    m = t.mechanism
    assert (m.target, m.mode, m.shunt_at, m.f_mhz) == (50.0, "low", "auto", 3.75)
    assert (m.qc, m.ql) == (None, 150.0)


def test_the_tune_frequency_is_written_even_when_the_design_chose_it():
    """MHz 0 would make SimNEC retune at every frequency; the app holds."""
    assert _xmatch_params(export_ssn(_skyloop(_l())))["MHz"] == "3.8"


def test_a_fixed_side_that_matched_is_the_side_simnec_picks():
    # 128.5 ohm must come down to 50, which only a shunt across out does.
    assert "XMATCH" in _elements(export_ssn(_skyloop(_l(shunt_at="out"))))


# --- what the element cannot say ---------------------------------------------


@pytest.mark.parametrize(
    "box, said",
    [
        (_l(mode="ll", shunt_at="auto"), "mode 'll' has no XMATCH form"),
        (_l(mode="cc", shunt_at="auto"), "mode 'cc' has no XMATCH form"),
        (_l(c_max_pF=1000.0), "component ranges"),
        # A shunt fixed across rig cannot bring 128.5 ohm DOWN: bypassed here,
        # matched by SimNEC's automatic element.
        (_l(shunt_at="rig"), "finds no match at 3.8 MHz and is bypassed"),
        (t_network_tuner(tune_to=50.0, c_max_pF=250.0), "is a T network"),
    ],
)
def test_refusals_are_by_name_and_name_the_way_out(box, said):
    with pytest.raises(SsnUnsupported, match=said) as exc:
        export_ssn(_skyloop(box))
    assert "freeze_tuners=True" in str(exc.value)


def test_an_auto_side_xmatch_solves_nothing(monkeypatch):
    """The web export runs without PyNEC (the bundle ships none), so writing
    the element must not need a solve; only a fixed side or a freeze does."""
    from antennaknobs.engines import momwire, pynec

    def refuse(*a, **k):
        raise AssertionError("the export solved")

    monkeypatch.setattr(momwire.MomwireEngine, "__init__", refuse)
    monkeypatch.setattr(pynec.PyNECEngine, "_compute_y_matrix", refuse)
    assert "XMATCH" in _elements(export_ssn(_skyloop(_l(shunt_at="auto"))))


def test_no_export_ever_writes_a_tuners_bypass():
    """The walk refuses a tuner body it was not told to write as a tuner,
    rather than emit its 0 H arm as a wire."""
    net = _skyloop(_l()).build_network()
    with pytest.raises(SsnUnsupported, match="bypass, a plain wire"):
        _station_chain(net, 3.8)


# --- freeze -------------------------------------------------------------------


def test_freeze_writes_an_l_tuners_parts_and_reimports_them_fixed():
    ssn = export_ssn(_skyloop(_l(mode="high", shunt_at="auto")), freeze_tuners=True)
    assert "XMATCH" not in ssn
    net = parse_ssn(ssn, network=True).network()
    assert find_tuners(net) == []
    kinds = sorted(_elements(ssn))
    assert kinds == sorted(["LOAD", "NETWORK", "GENERATOR", "SERIES_CAP", "SHUNT_IND"])


def test_freeze_writes_a_t_as_its_three_parts():
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.simnec_export import DEFAULT_GROUND

    b = _skyloop(t_network_tuner(tune_to=50.0, c_max_pF=250.0, ql=150.0, qc=1000.0))
    ssn = export_ssn(b, freeze_tuners=True)
    # File order is antenna side first: C2, the coil, C1.
    chain = _elements(ssn)[2:-1]
    assert chain == ["SERIES_CAP", "SHUNT_IND", "SERIES_CAP"]
    # The exporter tunes on the ground it writes; momwire's own default is
    # free space, which would be a different load.
    eng = MomwireEngine(b, ground=DEFAULT_GROUND)
    eng._reducer.tune()
    d = eng._reducer.design
    farads = [float(v) for v in re.findall(r"<n>F</n><v>([^<]+)</v>", ssn)]
    henries = [float(v) for v in re.findall(r"<n>H</n><v>([^<]+)</v>", ssn)]
    assert farads == pytest.approx([d.c2, d.c1], rel=1e-6)
    assert henries == pytest.approx([d.l], rel=1e-6)


def test_freeze_refuses_a_bypassed_tuner():
    with pytest.raises(SsnUnsupported, match="no tuned parts to freeze"):
        export_ssn(_skyloop(_l(shunt_at="rig")), freeze_tuners=True)
