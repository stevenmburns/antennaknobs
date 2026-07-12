"""EFHW sloper + unun showcase (issue #329): the end-fed half wave fed
through a real 49:1 transformer, composing Transformer (#301), lossy line
(#297), lossy wire (#316–#318), and the power budget (#299).

Stock tune targets the workbench default (finite-fast ground, B-spline
solver), same convention as the station designs.
"""

import pytest

from antennaknobs.designs.wire.efhw_sloper import UNUN_TURNS, Builder
from antennaknobs.engines import MomwireEngine

GROUND = dict(ground=("finite-fast", 10.0, 0.002), ground_z=0.0)


def _with_params(**overrides):
    return Builder(params={**Builder.default_params, **overrides})


def _budget_fractions(eng):
    eng.current_distribution()
    p_in = eng._excited_p_in
    return {label: max(0.0, w) / p_in for label, w in eng._excited_power_budget}


def test_discoverable():
    from antennaknobs.cli import list_builtin_designs

    assert "wire.efhw_sloper" in set(list_builtin_designs())


def test_stock_tune_matches_fifty_ohms():
    """The tuned length_factor lands the rig near 50 Ω at 14.1 MHz: the
    ~2.2 kΩ end-fed feed, stepped down 49:1, through comp cap and coax."""
    (z,) = MomwireEngine(Builder(), **GROUND).impedance()
    gamma = abs((z - 50.0) / (z + 50.0))
    assert (1 + gamma) / (1 - gamma) < 1.3  # measured 1.17


def test_unun_ratio_sanity():
    """With the unun idealized (huge lmag, no comp cap, ~zero line) the rig
    impedance is exactly the feedpoint stepped down by turns²: switching
    ratios rescales Z by the turns-ratio quotient."""

    def rig_z(ratio):
        b = _with_params(
            unun_ratio=ratio, lmag_uH=1e6, qlmag=0.0, comp_c_pF=0.0, line_len_m=1e-9
        )
        return complex(MomwireEngine(b, **GROUND).impedance()[0])

    z49 = rig_z("49:1")
    for ratio, turns in UNUN_TURNS.items():
        expected = turns**2 / UNUN_TURNS["49:1"] ** 2
        assert complex(z49 / rig_z(ratio)) == pytest.approx(expected, rel=1e-5)


def test_budget_itemizes_unun_line_and_wire():
    """The power budget answers "where do the watts go in a 49:1?" — unun
    core loss, coax, and wire I²R each visible; winding row and ideal comp
    cap burn nothing; efficiency in the measured-EFHW range."""
    eng = MomwireEngine(Builder(), **GROUND)
    fr = _budget_fractions(eng)
    assert fr["Transformer pri→ant"] < 1e-9  # no winding R by default
    assert fr["Shunt pri"] < 1e-9  # ideal comp cap
    assert 0.002 < fr["Transformer pri→ant (mag)"] < 0.05  # core loss
    assert 0.02 < fr["TL rig→pri"] < 0.15  # 5 m RG-58
    assert 0.02 < fr["wire loss (I²R)"] < 0.15  # 28 AWG half wave
    assert 0.80 < eng._excited_efficiency < 0.95  # measured 0.873


def test_thicker_wire_recovers_watts():
    """28 AWG → 18 AWG cuts the wire-loss fraction ~3× (measured 6.1 % →
    1.9 %) — the high-current half-wave middle makes gauge matter."""
    fr28 = _budget_fractions(MomwireEngine(Builder(), **GROUND))
    fr18 = _budget_fractions(
        MomwireEngine(_with_params(wire_type="18-awg-pvc"), **GROUND)
    )
    assert fr18["wire loss (I²R)"] < 0.5 * fr28["wire loss (I²R)"]


def test_cross_engine_pynec():
    """Matched-basis cross-check at the transformed rig port, with the
    FULL stock wire model on both engines (momwire#134 sinusoidal loading
    vs NEC LD-5 + LD-2). The counterpoise + gap-wire feed keeps the
    high-Z end well-conditioned — far from the zepp's bare-end-port
    spread."""
    pytest.importorskip("antennaknobs.engines.pynec")
    from antennaknobs.engines import PyNECEngine
    from momwire import SinusoidalSolver

    zm = MomwireEngine(Builder(), ground=None, solver=SinusoidalSolver).impedance()[0]
    zn = PyNECEngine(Builder(), ground=None).impedance()[0]
    assert abs(zm - zn) / abs(zm) < 0.01
