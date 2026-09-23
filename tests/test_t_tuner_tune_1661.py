"""The T tuner that tunes itself: ``t_network_tuner(tune_to=...)`` (AK#1661).

A T has three parts (series C1 from the rig, shunt L at the tee midpoint,
series C2 to the antenna) for two conditions (R and X at the rig), so one is
held (USER DECISIONS 2026-09-22):

* any ONE of C1 / L / C2 may be given, and the other two are tuned;
* with none given, a capacitor is held at ``c_max_pF`` — ``pin`` "c1", "c2"
  or "auto" (the default: both, keeping the less lossy), measured in
  ``scratch/1661-t-tuner/pin_loss.py``;
* component ranges bound both tuners: a tuning outside them is no match.

The rest is #1646's machinery: tuned once at ``tune_at_mhz`` else the design
frequency and held, and a load it cannot match is reported and bypassed.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from conftest import needs_pynec

from antennaknobs.auto_match import (
    NoMatch,
    Ranges,
    TTuner,
    TunerAdvisory,
    _t_z_in,
    design_l_match,
    design_t_match,
)
from antennaknobs.network import PortVirtual, Shunt, TwoPort
from antennaknobs.station import l_network_tuner, t_network_tuner

F = 14.0
OMEGA = 2.0 * math.pi * F * 1e6
SIMNEC_Z = 76.78 - 65.79j


def _c(x_ohm):
    """The capacitance with reactance -x_ohm at F."""
    return 1.0 / (OMEGA * x_ohm)


# --- the rule --------------------------------------------------------------


def test_the_known_answer_every_reactance_is_100_ohm():
    """Worked by hand: C2 at -j100 leaves 200 - j100, whose admittance is
    0.004 + j0.002 S; a shunt L of +j100 (-j0.010 S) brings it to
    0.004 - j0.008 S, which is 50 + j100 ohm; C1 at -j100 cancels the +j100."""
    d = design_t_match(200 + 0j, 50.0, F, c2=_c(100.0))
    assert d.c1 == pytest.approx(_c(100.0), rel=1e-9)
    assert d.l == pytest.approx(100.0 / OMEGA, rel=1e-9)
    assert d.c2 == _c(100.0)
    assert d.efficiency == pytest.approx(1.0)
    assert (d.given, d.pinned) == (("c2",), None)


@pytest.mark.parametrize("held", ["c1", "l", "c2"])
def test_any_one_part_given_tunes_the_other_two_exactly(held):
    given = {"c1": 100e-12, "l": 1.5e-6, "c2": 150e-12}[held]
    d = design_t_match(SIMNEC_Z, 50.0, F, qc=1000.0, ql=150.0, **{held: given})
    assert getattr(d, held) == given
    z = _t_z_in(d.c1, d.l, d.c2, SIMNEC_Z, OMEGA, 1000.0, 150.0)
    assert z == pytest.approx(50.0, abs=1e-9)
    assert d.given == (held,) and 0.9 < d.efficiency < 1.0


def test_two_parts_given_leave_one_for_two_conditions():
    with pytest.raises(ValueError, match="at most one"):
        design_t_match(SIMNEC_Z, 50.0, F, c1=100e-12, c2=100e-12)


def test_all_free_needs_a_maximum_to_pin_at():
    with pytest.raises(ValueError, match="needs c_max"):
        design_t_match(SIMNEC_Z, 50.0, F)


def test_the_pins_reach_different_loads_and_auto_takes_either():
    """C2 at its maximum matches SimNEC's antenna; C1 at its maximum does not.
    50 + j80 is the other way round. "auto" matches both."""
    rng = Ranges(c_max=250e-12)
    with pytest.raises(NoMatch, match="C1 at its maximum"):
        design_t_match(SIMNEC_Z, 50.0, F, pin="c1", ranges=rng)
    assert design_t_match(SIMNEC_Z, 50.0, F, pin="c2", ranges=rng).c2 == 250e-12
    with pytest.raises(NoMatch, match="C2 at its maximum"):
        design_t_match(50 + 80j, 50.0, F, pin="c2", ranges=rng)
    assert design_t_match(50 + 80j, 50.0, F, pin="c1", ranges=rng).c1 == 250e-12
    for z, pinned in ((SIMNEC_Z, "c2"), (50 + 80j, "c1")):
        d = design_t_match(z, 50.0, F, ranges=rng)
        assert d.pinned == pinned
        assert _t_z_in(d.c1, d.l, d.c2, z, OMEGA, None, None) == pytest.approx(
            50.0, abs=1e-9
        )


@pytest.mark.parametrize("z_load", [60 + 1000j, 78 + 125j])
def test_auto_keeps_the_less_lossy_where_both_pins_match(z_load):
    """60 + j1000 loses less with C1 pinned, 78 + j125 with C2."""
    rng = Ranges(c_max=250e-12)
    effs = {
        pin: design_t_match(z_load, 50.0, F, pin=pin, qc=1000.0, ql=150.0, ranges=rng)
        for pin in ("c1", "c2")
    }
    best = max(effs.values(), key=lambda d: d.efficiency)
    auto = design_t_match(z_load, 50.0, F, qc=1000.0, ql=150.0, ranges=rng)
    assert auto.pinned == best.pinned
    assert auto.pinned == ("c1" if z_load.real < 70 else "c2")


def test_a_tuning_outside_the_ranges_is_no_match():
    # Unbounded, C2 given at 150 pF tunes SimNEC's antenna with C1 ~96 pF.
    with pytest.raises(NoMatch, match=r"within its component ranges \(C1 .* above"):
        design_t_match(SIMNEC_Z, 50.0, F, c2=150e-12, ranges=Ranges(c_max=90e-12))
    with pytest.raises(NoMatch, match="L .* below its minimum"):
        design_t_match(SIMNEC_Z, 50.0, F, c2=150e-12, ranges=Ranges(l_min=1e-6))


def test_the_l_tuner_honours_ranges_too():
    # SimNEC's own tuning needs 37.52 pF.
    with pytest.raises(NoMatch, match="shunt C 37.52 pF is above its maximum 30 pF"):
        design_l_match(
            SIMNEC_Z, 50.0, F, qc=2000.0, ql=200.0, ranges=Ranges(c_max=30e-12)
        )
    d = design_l_match(
        SIMNEC_Z, 50.0, F, qc=2000.0, ql=200.0, ranges=Ranges(c_max=40e-12)
    )
    assert d.shunt * 1e12 == pytest.approx(37.52, abs=0.005)


def test_a_load_already_at_the_target_is_a_matched_bypass():
    d = design_t_match(50 + 0j, 50.0, F, ranges=Ranges(c_max=250e-12))
    assert d.bypass and d.matched


# --- the component -----------------------------------------------------------


def test_the_component_carries_its_tuning():
    comp = t_network_tuner(tune_to=50.0, tune_at_mhz=14.0, c2_pF=200.0, ql=150.0)
    t = comp.tuner
    assert isinstance(t, TTuner)
    assert (t.target, t.f_mhz, t.c1, t.l, t.c2) == (50.0, 14.0, None, None, 200e-12)
    comp = t_network_tuner(tune_to=50.0, c_max_pF=250.0, l_max_uH=20.0)
    assert comp.tuner.pin == "auto"
    r = comp.tuner.ranges
    assert (r.c_min, r.l_min) == (None, None)
    assert (r.c_max, r.l_max) == pytest.approx((250e-12, 20e-6))


@pytest.mark.parametrize(
    "kw, said",
    [
        ({"tune_to": 50.0}, "needs c_max_pF"),
        (
            {"tune_to": 50.0, "c1_pF": 100.0, "l_uH": 1.0, "c2_pF": 100.0},
            "nothing left to tune",
        ),
        (
            {"tune_to": 50.0, "c1_pF": 100.0, "l_uH": 1.0, "on_no_match": "bypass"},
            "only tune for best effort",
        ),
        ({"tune_to": 50.0, "c1_pF": 100.0, "pin": "c2"}, "nothing to pin"),
        ({"tune_to": 50.0, "c_max_pF": 250.0, "pin": "l"}, "not one of"),
        ({"tune_to": 50.0 + 5j, "c_max_pF": 250.0}, "positive resistance"),
        ({"tune_to": 50.0, "c_max_pF": 10.0, "c_min_pF": 20.0}, "is above"),
        ({"c1_pF": 100.0, "l_uH": 1.0}, "needs c1_pF, c2_pF and l_uH"),
        ({"c1_pF": 100.0, "l_uH": 1.0, "c2_pF": 100.0, "c_max_pF": 250}, "fixed"),
    ],
)
def test_the_component_refuses_what_it_cannot_mean(kw, said):
    with pytest.raises(ValueError, match=said):
        t_network_tuner(**kw)


def test_the_l_tuner_takes_ranges_only_when_it_tunes():
    comp = l_network_tuner(tune_to=50.0, c_max_pF=300.0, l_max_uH=10.0)
    r = comp.tuner.ranges
    assert (r.c_max, r.l_max) == pytest.approx((300e-12, 10e-6))
    with pytest.raises(ValueError, match="fixed values choose nothing"):
        l_network_tuner(0.73, 37.5, c_max_pF=300.0)


def test_fixed_values_are_unchanged():
    comp = t_network_tuner(81.2, 500.0, 4.218, ql=200.0)
    assert comp.tuner is None
    c1, coil, c2 = comp.branches
    assert (c1.a, c1.b, c1.c, c1.qc) == ("rig", "m", pytest.approx(81.2e-12), None)
    assert (coil.port, coil.l, coil.ql) == ("m", pytest.approx(4.218e-6), 200.0)
    assert (c2.a, c2.b, c2.c) == ("m", "out", pytest.approx(500e-12))
    assert t_network_tuner(81.2, 500.0, 4.218, qc=1000.0).branches[0].qc == 1000.0


def test_an_untuned_unit_is_a_bypass_through_its_own_midpoint():
    """Two 0 H arms through the tee midpoint, so the flattened network
    already carries ``match.m`` for the tuned coil to hang on."""
    net = _skyloop().build_network()
    assert net.branch_paths == ["match.", "match."]
    a, b = net.branches
    assert (a.a, a.b, a.l, b.a, b.b, b.l) == (
        "in",
        "match.m",
        0.0,
        "match.m",
        "feed",
        0.0,
    )
    assert isinstance(net.ports["match.m"], PortVirtual)
    assert isinstance(net.composites["match."].tuner, TTuner)


# --- a native design tunes, on every network engine --------------------------


def _skyloop(tune_to=50.0, tune_at_mhz=None, **kw):
    """The catalog skyloop with its fixed L-match swapped for a T tuner."""
    from antennaknobs.designs.loops.skyloop_lmatch import Builder as Skyloop
    from antennaknobs.network import Driven, Instance, Network, PortOnWire

    kw = {"c_max_pF": 250.0, "ql": 150.0, "qc": 1000.0} | kw

    class Tuned(Skyloop):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "in": PortVirtual("in")},
                branches=[
                    Instance(
                        "match",
                        t_network_tuner(tune_to=tune_to, tune_at_mhz=tune_at_mhz, **kw),
                        rig="in",
                        out="feed",
                    )
                ],
                sources=[Driven(port="in", voltage=1 + 0j)],
            )

    return Tuned()


def _engine(name, builder):
    if name == "momwire":
        from antennaknobs.engines.momwire import MomwireEngine

        return MomwireEngine(builder)
    from antennaknobs.engines.pynec import PyNECEngine

    return PyNECEngine(builder)


ENGINES = ["momwire", pytest.param("pynec", marks=needs_pynec)]


def _z(eng, f):
    return complex(np.atleast_1d(eng.impedance_sweep(np.array([f]))[0])[0])


@pytest.mark.parametrize("name", ENGINES)
def test_it_tunes_at_the_design_frequency_and_holds(name):
    b = _skyloop()
    eng = _engine(name, b)
    f0 = b.design_freq
    assert _z(eng, f0) == pytest.approx(50.0, abs=1e-6)
    # Held, not retuned: 3 % off the design frequency it is detuned.
    assert abs(_z(eng, 1.03 * f0) - 50.0) > 1.0
    rows = {r["label"]: r["value"] for r in eng._reducer.tuner_rows()}
    assert rows["C1"] > 0 and rows["L"] > 0 and rows["C2"] > 0
    assert rows["tuned"].startswith(f"T at {f0:g} MHz, C")
    assert rows["tuned"].endswith("at its maximum")


# The loop presents about 113.7 + j1 ohm at 3.8 MHz. A C2 given at 180 pF
# wants C1 at 261 pF, so that case widens the capacitors' range.
@pytest.mark.parametrize(
    "held, kw",
    [
        ({"c1_pF": 120.0}, {}),
        ({"l_uH": 6.0}, {}),
        ({"c2_pF": 180.0}, {"c_max_pF": 300.0}),
    ],
)
def test_a_given_part_is_held_and_the_rest_tuned(held, kw):
    b = _skyloop(**held, **kw)
    eng = _engine("momwire", b)
    assert _z(eng, b.design_freq) == pytest.approx(50.0, abs=1e-6)
    [(label, value)] = held.items()
    name = {"c1_pF": "C1", "l_uH": "L", "c2_pF": "C2"}[label]
    rows = {r["label"]: r["value"] for r in eng._reducer.tuner_rows()}
    assert rows[name] == pytest.approx(value)
    assert rows["tuned"].endswith(f"{name} given")


def test_the_tuned_body_is_the_real_tee():
    b = _skyloop()
    eng = _engine("momwire", b)
    _z(eng, b.design_freq)
    c1, coil, c2 = eng._reducer.tuned_network().branches
    assert isinstance(c1, TwoPort) and (c1.a, c1.b) == ("in", "match.m") and c1.c > 0
    assert isinstance(coil, Shunt) and coil.port == "match.m" and coil.l > 0
    assert (c2.a, c2.b) == ("match.m", "feed") and c2.c > 0
    assert (c1.qc, coil.ql, c2.qc) == (1000.0, 150.0, 1000.0)


def test_tune_at_mhz_is_where_it_tunes():
    f1 = 1.02 * _skyloop().design_freq
    eng = _engine("momwire", _skyloop(tune_at_mhz=f1))
    assert _z(eng, f1) == pytest.approx(50.0, abs=1e-6)


def test_no_match_bypasses_and_says_so():
    from antennaknobs.auto_match import tuner_advisories

    # Capacitors that top out at 2 pF cannot tune the loop to anything; asked
    # to bypass rather than tune for best effort (AK#1663), it bypasses.
    eng = _engine("momwire", _skyloop(c_max_pF=2.0, on_no_match="bypass"))
    with pytest.warns(TunerAdvisory, match="bypassed"):
        eng.impedance()
    d = eng._reducer.design
    assert d.bypass and not d.matched
    [adv] = tuner_advisories(eng)
    assert "no T network with either capacitor at its maximum" in adv["text"]
    rows = eng._reducer.tuner_rows()
    assert rows[0]["value"].startswith("no match")


def test_the_schematic_draws_the_tuner_not_its_placeholders():
    from antennaknobs.schematic import lower, render_svg

    svg = render_svg(lower(_skyloop().build_network(), title="tuned"))
    assert "T tuner" in svg
    assert "0 µH" not in svg


def test_simnec_export_refuses_a_t_tuner_too():
    from antennaknobs.simnec_export import SsnUnsupported, export_ssn

    # SimNEC's matching element is an L; a T is written frozen (AK#1662).
    with pytest.raises(SsnUnsupported, match="is a T network"):
        export_ssn(_skyloop())
