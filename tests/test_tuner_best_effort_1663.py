"""A tuner that cannot reach its target tunes for the lowest SWR its parts
give, applies it, and says what it got (AK#1663).

Three states, kept distinguishable in the readout and the advisories:

* exact — the target, by algebra (unchanged);
* best effort — the topology could match in principle, but a part's range
  rules the exact answer out (or a T has two parts given): the parts go in
  circuit at the setting with the least reflection, and the SWR reached is
  reported;
* bypassed — no network of this kind could match at all, a best effort is no
  better than the load's own SWR, or the design asked for it.

The known-answer case is derived by hand in its docstring; the engine case
checks the setting is APPLIED, i.e. the solved port reads the SWR reported.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest
from test_t_tuner_tune_1661 import _engine, _skyloop

from antennaknobs.auto_match import (
    LTuner,
    Ranges,
    TTuner,
    TunerAdvisory,
    _t_z_in,
    tuner_advisories,
)

F = 14.0
OMEGA = 2 * math.pi * F * 1e6


def _swr(z, r_t=50.0):
    g = abs((z - r_t) / (z + r_t))
    return (1 + g) / (1 - g)


def test_a_coil_short_of_its_value_gives_the_hand_derived_best():
    """Low-pass L, shunt at rig, lossless, on a 12.5 Ω resistive load.

    Exact needs a series reactance X = √(R (R_t − R)) = 21.65 Ω. With the coil
    capped at 0.15 µH (X_max = 13.19 Ω at 14 MHz), fix X: the shunt only moves
    Im Y, and |Γ| in admittance form, ((G_t−G)² + b²)/((G_t+G)² + b²), is least
    at b = 0, i.e. B = X/(R² + X²), leaving Z_in = (R² + X²)/R, real and below
    R_t. That rises with X, so the optimum is X = X_max: Z_in = 26.42 Ω, SWR
    = 50/26.42 = 1.892.
    """
    r = 12.5
    tuner = LTuner(50.0, "low", "rig", ranges=Ranges(l_max=0.15e-6))
    _, d = tuner.body("rig", "out", complex(r, 0.0), F)
    x = OMEGA * 0.15e-6
    assert not d.bypass and not d.matched
    assert d.series == pytest.approx(0.15e-6, rel=1e-9)
    assert d.shunt == pytest.approx(x / (r * r + x * x) / OMEGA, rel=1e-6)
    assert d.best_swr == pytest.approx(50.0 / ((r * r + x * x) / r), rel=1e-9)
    assert "0.15 µH" in d.no_match and "above its maximum" in d.no_match


def test_in_range_it_is_still_exact():
    _, d = LTuner(50.0, "low", "rig").body("rig", "out", 12.5 + 0j, F)
    assert d.matched and d.best_swr is None and d.no_match is None


def test_a_topology_with_no_solution_in_principle_still_bypasses():
    # Shunt across the load can only bring R down; 12.5 Ω needs it brought up.
    _, d = LTuner(50.0, "low", "out").body("rig", "out", 12.5 + 0j, F)
    assert d.bypass and not d.matched and d.best_swr is None
    assert d.no_match.startswith("no low L network with its shunt at out")


def test_on_no_match_bypass_is_honoured():
    tuner = LTuner(
        50.0, "low", "rig", ranges=Ranges(l_max=0.15e-6), on_no_match="bypass"
    )
    _, d = tuner.body("rig", "out", 12.5 + 0j, F)
    assert d.bypass and d.best_swr is None


def test_a_t_with_two_parts_given_tunes_the_third_for_least_swr():
    z_load = complex(500.0, 300.0)  # 11.5:1 bypassed
    tuner = TTuner(50.0, c1=120e-12, c2=300e-12)
    _, d = tuner.body("rig", "out", z_load, F, "m")
    assert not d.bypass and d.best_swr < _swr(z_load)
    assert (d.c1, d.c2) == (120e-12, 300e-12) and d.given == ("c1", "c2")
    # Against an independent brute-force scan of the one free part.
    ls = np.geomspace(0.01e-6, 100e-6, 200_001)
    brute = min(_swr(_t_z_in(120e-12, ls, 300e-12, z_load, OMEGA, None, None)))
    assert d.best_swr <= brute + 1e-9
    assert d.best_swr == pytest.approx(
        _swr(_t_z_in(d.c1, d.l, d.c2, z_load, OMEGA, None, None))
    )
    # Deterministic: the same call, the same answer to the bit.
    assert tuner.body("rig", "out", z_load, F, "m")[1] == d


def test_a_best_effort_worse_than_the_bypass_is_not_put_in_circuit():
    # A T with its coil capped at 0.5 µH on the 80 m skyloop: its best is far
    # worse than leaving the load alone, so it bypasses and says why.
    b = _skyloop(c_max_pF=250.0, l_max_uH=0.5)
    eng = _engine("momwire", b)
    with pytest.warns(TunerAdvisory, match="bypassed"):
        eng.impedance_sweep(np.array([b.design_freq]))
    d = eng._reducer.design
    assert d.bypass and d.best_swr is None
    assert "is no better than the load's own" in d.no_match


def test_the_engine_applies_the_best_effort_and_the_readout_says_so():
    # C1 needs 8.9 pF; at 4 pF the T gets the loop to about 1.6:1, where
    # bypassed it reads 2.3:1.
    b = _skyloop(c_max_pF=4.0)
    eng = _engine("momwire", b)
    with pytest.warns(TunerAdvisory, match="best effort"):
        z = complex(np.atleast_1d(eng.impedance_sweep(np.array([b.design_freq]))[0])[0])
    d = eng._reducer.design
    assert not d.bypass and not d.matched
    # Applied: the solved port reads the SWR the tuner reported.
    assert _swr(z) == pytest.approx(d.best_swr, rel=1e-9)
    rows = {r["label"]: r for r in eng._reducer.tuner_rows()}
    assert rows["SWR reached"]["value"] == pytest.approx(d.best_swr, abs=1e-3)
    assert "best effort" in rows["tuned"]["value"]
    [adv] = tuner_advisories(eng)
    assert "tuned as close as its parts allow" in adv["text"]


def test_the_three_states_read_differently():
    def rows_and_advice(**kw):
        b = _skyloop(**kw)
        eng = _engine("momwire", b)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", TunerAdvisory)
            eng.impedance_sweep(np.array([b.design_freq]))
        return (
            {r["label"]: r["value"] for r in eng._reducer.tuner_rows()},
            tuner_advisories(eng),
        )

    exact, exact_adv = rows_and_advice(c_max_pF=250.0)
    best, best_adv = rows_and_advice(c_max_pF=4.0)
    bypassed, bypassed_adv = rows_and_advice(c_max_pF=4.0, on_no_match="bypass")
    assert "SWR reached" not in exact and not exact_adv
    assert "SWR reached" in best and "best effort" in best["tuned"]
    assert bypassed["tuned"].startswith("no match") and "SWR reached" not in bypassed
    assert "tuned as close" in best_adv[0]["text"]
    assert "bypassed" in bypassed_adv[0]["text"]
