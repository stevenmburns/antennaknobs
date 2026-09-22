"""The L tuner that tunes itself: ``l_network_tuner(tune_to=...)`` (AK#1646).

The interface is the app's own station component, not SimNEC's element (USER
DECISIONS 2026-09-22):

* a switch on `l_network_tuner`: ``tune_to`` in place of the two values;
* ``mode`` "low" / "high" / "ll" / "cc", the parts, and ``shunt_at`` "out" /
  "rig" / "auto", the side, defaulting to "out" as the fixed tuner does;
  "auto" takes the side the load calls for;
* tuned once, at ``tune_at_mhz`` else the design frequency, and held: it does
  not retune as the measurement frequency moves;
* a load it cannot match is reported and the tuner bypassed.

SimNEC's XMATCH imports AS this component. The design rule is pinned against
SimNEC's own output: from its antenna impedance for AC6LA's
``snBydipole1-LC1.ssn``, 76.78 - j65.79 ohm at 14 MHz with Qc 2000 and Ql
200, the low-pass tuning is C = 37.520 pF and L = 731.94 nH, the two values
SimNEC shows greyed in that element.
"""

from __future__ import annotations

import numpy as np
import pytest
from conftest import needs_pynec

from antennaknobs.auto_match import NoMatch, TunerAdvisory, design_l_match
from antennaknobs.file_designs import builder_from_file
from antennaknobs.simnec_import import parse_ssn
from antennaknobs.network import TwoPort
from antennaknobs.station import l_network_tuner

SIMNEC_Z = 76.78 - 65.79j

# --- the rule --------------------------------------------------------------


def test_the_rule_reproduces_simnecs_own_values():
    d = design_l_match(
        SIMNEC_Z, 50.0, 14.0, "low", shunt_at="auto", qc=2000.0, ql=200.0
    )
    assert (d.mode, d.shunt_at) == ("low", "out")
    assert d.shunt * 1e12 == pytest.approx(37.52, abs=0.005)
    assert d.series * 1e9 == pytest.approx(731.9, abs=0.05)


def test_the_q_terms_are_what_move_c():
    assert design_l_match(SIMNEC_Z, 50.0, 14.0).shunt * 1e12 == pytest.approx(
        36.945, abs=0.005
    )


def test_the_side_defaults_to_out_and_a_fixed_side_steps_one_way():
    # 20 ohm must come UP to 50: a shunt across out cannot do that.
    with pytest.raises(NoMatch, match="with its shunt at out"):
        design_l_match(20 + 0j, 50.0, 14.0, "low")
    d = design_l_match(20 + 0j, 50.0, 14.0, "low", shunt_at="rig")
    assert d.shunt_at == "rig"


def test_auto_takes_the_side_the_load_calls_for():
    assert design_l_match(SIMNEC_Z, 50.0, 14.0, shunt_at="auto").shunt_at == "out"
    assert design_l_match(20 + 5j, 50.0, 14.0, shunt_at="auto").shunt_at == "rig"


def test_auto_falls_back_when_that_side_cannot_match():
    # R 5 says "up" (rig), but with +j30 only a shunt across out can make it
    # with a low-pass L.
    with pytest.raises(NoMatch):
        design_l_match(5 + 30j, 50.0, 14.0, "low", shunt_at="rig")
    assert design_l_match(5 + 30j, 50.0, 14.0, "low", shunt_at="auto").shunt_at == "out"


@pytest.mark.parametrize("mode", ["low", "high"])
def test_low_and_high_never_match_from_both_sides(mode):
    """So "auto" and SimNEC's rule agree on every XMATCH, whether SimNEC
    reads "the impedance must be increased" as R or as |Z|."""
    for r in np.geomspace(1, 2000, 25):
        for x in np.linspace(-3000, 3000, 41):
            sides = []
            for side in ("out", "rig"):
                try:
                    design_l_match(complex(r, x), 50.0, 14.0, mode, shunt_at=side)
                    sides.append(side)
                except NoMatch:
                    pass
            assert len(sides) < 2, (mode, r, x)


@pytest.mark.parametrize("mode, z_load", [("cc", 10 + 40j), ("ll", 10 - 80j)])
def test_for_ll_and_cc_auto_prefers_the_natural_side(mode, z_load):
    # Each load matches from both sides; R 10 < 50 says "up", so rig.
    for side in ("out", "rig"):
        design_l_match(z_load, 50.0, 14.0, mode, shunt_at=side)
    assert design_l_match(z_load, 50.0, 14.0, mode, shunt_at="auto").shunt_at == "rig"


def test_high_pass_uses_a_series_c_and_a_shunt_l():
    d = design_l_match(SIMNEC_Z, 50.0, 14.0, "high", qc=2000.0, ql=200.0)
    assert (d.series_kind, d.shunt_kind) == ("C", "L")


def test_ll_and_cc_are_there_by_name():
    d = design_l_match(20 - 60j, 50.0, 14.0, "ll", shunt_at="auto")
    assert (d.series_kind, d.shunt_kind) == ("L", "L")
    d = design_l_match(20 + 60j, 50.0, 14.0, "cc", shunt_at="auto")
    assert (d.series_kind, d.shunt_kind) == ("C", "C")


def test_no_match_is_said():
    # A shunt L cannot bring 100 ohm down to 50 behind a series L.
    with pytest.raises(NoMatch, match="no ll L network with its shunt on either side"):
        design_l_match(100 + 0j, 50.0, 14.0, "ll", shunt_at="auto")


def test_a_load_already_at_the_target_is_a_matched_bypass():
    d = design_l_match(50 + 0j, 50.0, 14.0, "low")
    assert d.bypass and d.matched


# --- the component -----------------------------------------------------------


def test_the_component_carries_its_tuning():
    comp = l_network_tuner(tune_to=50.0, tune_at_mhz=14.0, mode="high", ql=200.0)
    assert comp.ports == ("rig", "out")
    t = comp.tuner
    assert (t.target, t.mode, t.shunt_at, t.f_mhz) == (50.0, "high", "out", 14.0)


@pytest.mark.parametrize(
    "kw, said",
    [
        ({"series_l_uH": 1.0, "tune_to": 50.0}, "chooses its own"),
        ({"series_l_uH": 1.0}, "needs series_l_uH and shunt_c_pF"),
        ({"series_l_uH": 1.0, "shunt_c_pF": 50.0, "mode": "high"}, "fixed values"),
        ({"tune_to": 50.0, "mode": "pi"}, "not one of"),
        ({"tune_to": 50.0, "mode": "auto"}, "not one of"),
        ({"tune_to": 50.0, "shunt_at": "middle"}, "not one of"),
        (
            {"series_l_uH": 1.0, "shunt_c_pF": 50.0, "shunt_at": "auto"},
            "fixed values sit",
        ),
        ({"tune_to": 50 + 5j}, "positive resistance"),
    ],
)
def test_the_component_refuses_what_it_cannot_mean(kw, said):
    with pytest.raises(ValueError, match=said):
        l_network_tuner(**kw)


def test_an_untuned_unit_is_a_bypass_with_its_mechanism_attached():
    """No invented component values anywhere: until it tunes, the box is a
    wire, and the mechanism attached to it owns the topology."""
    from antennaknobs.auto_match import LTuner

    net = _skyloop().build_network()
    [(br, path)] = list(zip(net.branches, net.branch_paths, strict=True))
    assert path == "match."
    assert isinstance(br, TwoPort) and br.l == 0.0 and br.c is None
    assert isinstance(net.composites["match."].tuner, LTuner)


@pytest.mark.parametrize(
    "mode, side, kinds", [("low", "out", ("l", "c")), ("high", "out", ("c", "l"))]
)
def test_the_tuned_body_is_the_real_topology(mode, side, kinds):
    """What the engine solves holds the parts the mechanism chose, where it
    put them — and shunt_at moves the shunt branch, it does not annotate it."""
    b = _skyloop(mode=mode, shunt_at=side)
    eng = _engine("momwire", b)
    eng.impedance_sweep(np.array([b.design_freq]))
    tuned = eng._reducer.tuned_network()
    series, shunt = tuned.branches
    assert [p for p in tuned.branch_paths] == ["match.", "match."]
    assert getattr(series, kinds[0]) > 0 and series.a == "in" and series.b == "feed"
    assert getattr(shunt, kinds[1]) > 0
    assert shunt.port == ("feed" if side == "out" else "in")


@pytest.mark.parametrize("side, node", [("out", "out"), ("rig", "rig")])
def test_shunt_at_moves_the_branch(side, node):
    """The mechanism emits the shunt where it belongs; nothing annotates a
    fixed branch with a side."""
    from antennaknobs.auto_match import LTuner

    # 20 + j5 must come UP to 50, which the rig side does; the out side is
    # reached by 300 + j5, which must come down.
    z_load = 20 + 5j if side == "rig" else 300 + 5j
    body, design = LTuner(target=50.0, mode="low", shunt_at=side).body(
        "rig", "out", z_load, 14.0
    )
    series, shunt = body
    assert design.matched and not design.bypass
    assert (series.a, series.b) == ("rig", "out") and series.l > 0
    assert shunt.port == node and shunt.c > 0


def test_fixed_values_are_unchanged():
    comp = l_network_tuner(0.73, 37.5, ql=200.0)
    assert comp.tuner is None
    series, shunt = comp.branches
    assert (series.l, series.ql, shunt.c) == pytest.approx((0.73e-6, 200.0, 37.5e-12))
    assert shunt.port == "out"


def test_fixed_values_can_put_the_shunt_at_rig():
    comp = l_network_tuner(0.73, 37.5, shunt_at="rig")
    assert comp.branches[1].port == "rig"
    # Drawn from the rig side: the capacitor first.
    assert [e.kind for e in comp.schematic] == ["capacitor", "inductor"]


# --- a native design tunes, on every network engine --------------------------


def _skyloop(tune_to=50.0, mode="low", tune_at_mhz=None, shunt_at="out"):
    """The catalog skyloop with its fixed L-match swapped for the tuner."""
    from antennaknobs.designs.loops.skyloop_lmatch import Builder as Skyloop
    from antennaknobs.network import (
        Driven,
        Instance,
        Network,
        PortOnWire,
        PortVirtual,
    )

    class Tuned(Skyloop):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "in": PortVirtual("in")},
                branches=[
                    Instance(
                        "match",
                        l_network_tuner(
                            tune_to=tune_to,
                            tune_at_mhz=tune_at_mhz,
                            mode=mode,
                            shunt_at=shunt_at,
                            ql=200.0,
                            qc=2000.0,
                        ),
                        rig="in",
                        out="feed",
                    )
                ],
                sources=[Driven(port="in", voltage=1 + 0j)],
            )

    return Tuned()


def _engine(name, builder, ground=None):
    if name == "momwire":
        from antennaknobs.engines.momwire import MomwireEngine

        return MomwireEngine(builder, ground=ground)
    from antennaknobs.engines.pynec import PyNECEngine

    return PyNECEngine(builder, ground=ground)


ENGINES = ["momwire", pytest.param("pynec", marks=needs_pynec)]


@pytest.mark.parametrize("name", ENGINES)
def test_it_tunes_at_the_design_frequency_and_holds(name):
    b = _skyloop()
    eng = _engine(name, b)
    f0 = b.design_freq
    z = complex(np.atleast_1d(eng.impedance_sweep(np.array([f0]))[0])[0])
    assert z == pytest.approx(50.0, abs=1e-6)
    # Held, not retuned: 3 % off the design frequency it is detuned.
    z_off = complex(np.atleast_1d(eng.impedance_sweep(np.array([1.03 * f0]))[0])[0])
    assert abs(z_off - 50.0) > 1.0
    rows = {r["label"]: r["value"] for r in eng._reducer.tuner_rows()}
    assert rows["series L"] > 0 and rows["shunt C"] > 0
    assert rows["tuned"].startswith(f"low at {f0:g} MHz")


def test_tune_at_mhz_is_where_it_tunes():
    b = _skyloop(tune_at_mhz=None)
    f1 = 1.02 * b.design_freq
    eng = _engine("momwire", _skyloop(tune_at_mhz=f1))
    z = complex(np.atleast_1d(eng.impedance_sweep(np.array([f1]))[0])[0])
    assert z == pytest.approx(50.0, abs=1e-6)


def test_no_match_bypasses_and_says_so():
    from antennaknobs.auto_match import tuner_advisories

    # A 1 ohm target is out of reach of an L-L for this loop, so the tuner
    # stands aside and the readout shows the bare antenna.
    eng = _engine("momwire", _skyloop(tune_to=1.0, mode="ll"))
    bare = _engine("momwire", _skyloop(tune_to=1.0, mode="ll"))
    with pytest.warns(TunerAdvisory, match="bypassed"):
        z = complex(np.atleast_1d(eng.impedance())[0])
    assert eng._reducer.design.bypass and not eng._reducer.design.matched
    [adv] = tuner_advisories(eng)
    assert adv["category"] == "tuner" and "bypassed" in adv["text"]
    assert z == pytest.approx(
        bare._reducer._load_impedance(
            bare._compute_y_matrix(bare._wavelength_for(bare.builder.freq))
        ),
        rel=1e-9,
    )


# --- SimNEC's XMATCH is this component ------------------------------------------

_DIPOLE = """NEC2
GW 1 11 0 -5.2 10 0 5.2 10 0.001
EX 0 1 6 0 1 0
FR 0 1 0 0 14 0
NECEND"""


def _ssn(xmatch_params: str, *, mhz: str = "14") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<SimNEC1p0>
    <SmithChartCircuit>
        <CIRCUIT>
            <element>
                <type>NETWORK</type>
                <escapeHatch/>
                <p><n>equ</n><v>{_DIPOLE}</v></p>
            </element>
            <element>
                <type>XMATCH</type>
                <sweeperLabel>LC1</sweeperLabel>
                {xmatch_params}
                <p><n>MHz</n><v>{mhz}</v></p>
            </element>
            <element>
                <type>GENERATOR</type>
                <p><n>MHz</n><v>14</v></p>
                <p><n>Zo</n><v>50</v></p>
            </element>
        </CIRCUIT>
    </SmithChartCircuit>
</SimNEC1p0>
"""


_AUTO = """<p><n>mode</n><v>auto</v></p>
                <p><n>pass</n><v>low</v></p>
                <p><n>R</n><v>0</v></p>
                <p><n>X</n><v>0</v></p>
                <p><n>Qc</n><v>2K</v></p>
                <p><n>Ql</n><v>200</v></p>"""


def _ssn_builder(tmp_path, params=_AUTO, **kw):
    path = tmp_path / "lc1.ssn"
    path.write_text(_ssn(params, **kw))
    return builder_from_file(str(path))


def test_xmatch_imports_as_the_tuner():
    from antennaknobs.auto_match import find_tuners

    net = parse_ssn(_ssn(_AUTO), network=True).network()
    [t] = find_tuners(net)
    assert t.name == "LC1"
    assert (t.mechanism.target, t.mechanism.mode, t.mechanism.f_mhz) == (
        50.0,
        "low",
        14.0,
    )
    # SimNEC picks the side itself in auto mode; the file stores only the pass.
    assert t.mechanism.shunt_at == "auto"
    assert (t.mechanism.qc, t.mechanism.ql) == (2000.0, 200.0)


def test_xmatch_mhz_zero_tunes_once_and_says_so():
    c = parse_ssn(_ssn(_AUTO, mhz="0"), network=True)
    from antennaknobs.auto_match import find_tuners

    [t] = find_tuners(c.network())
    assert t.mechanism.f_mhz == 14.0  # the generator's frequency
    assert "retunes at every frequency in SimNEC" in c.skipped_note()


@pytest.mark.parametrize(
    "swap, said",
    [
        (("<v>auto</v>", "<v>manual</v>"), "'manual' mode is not translated"),
        (("<n>X</n><v>0</v>", "<n>X</n><v>10</v>"), "complex target"),
    ],
)
def test_xmatch_refuses_what_it_does_not_translate(swap, said):
    with pytest.raises(ValueError, match=said):
        parse_ssn(_ssn(_AUTO.replace(*swap)), network=True).network()


@pytest.mark.parametrize("name", ENGINES)
def test_an_imported_xmatch_tunes_exactly(tmp_path, name):
    cls = _ssn_builder(tmp_path)
    eng = _engine(name, cls(), cls.file_ground)
    z = complex(np.atleast_1d(eng.impedance())[0])
    # Exact on momwire too, whose imported-deck wavelength is NEC's (AK#1607).
    assert z == pytest.approx(50.0, abs=1e-6)


# --- nothing shows the placeholders ------------------------------------------


def test_the_schematic_draws_the_tuner_not_its_placeholders(tmp_path):
    from antennaknobs.schematic import lower, render_svg

    svg = render_svg(lower(_skyloop().build_network(), title="tuned"))
    assert "L tuner" in svg
    assert "0.001 µH" not in svg and "1 pF" not in svg


def test_an_imported_xmatch_exports_as_an_xmatch_again(tmp_path):
    """SimNEC -> antennaknobs -> SimNEC gives back the element, not frozen
    numbers or placeholders (AK#1662)."""
    from antennaknobs.auto_match import find_tuners
    from antennaknobs.simnec_export import export_ssn

    cls = _ssn_builder(tmp_path)
    ssn = export_ssn(cls(), ground=cls.file_ground)
    [t] = find_tuners(parse_ssn(ssn, network=True).network())
    m = t.mechanism
    assert (m.target, m.mode, m.shunt_at, m.f_mhz) == (50.0, "low", "auto", 14.0)
    assert (m.qc, m.ql) == (2000.0, 200.0)
