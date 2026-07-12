"""Station showcase designs (issue #300): invvee + real coax vs doublet +
open-wire line + lossy T-network tuner, both referenced to a virtual rig
port. Exercises the whole arc at once: lossy TL (#297), finite-Q coil
(#298), and the power budget (#299), cross-checked on both engines.
"""

import numpy as np
import pytest

from antennaknobs.designs.dipoles.invvee_coax_station import Builder as CoaxStation
from antennaknobs.designs.wire.doublet_ladder_tuner import Builder as DoubletStation
from antennaknobs.network import CABLES


def _momwire(builder):
    from antennaknobs.engines import MomwireEngine
    from momwire import SinusoidalSolver

    return MomwireEngine(builder, ground=None, solver=SinusoidalSolver)


def _with_params(cls, **overrides):
    return cls(params={**cls.default_params, **overrides})


def _budget_fractions(eng):
    eng.current_distribution()
    p_in = eng._excited_p_in
    return {label: max(0.0, w) / p_in for label, w in eng._excited_power_budget}


def test_designs_are_discoverable():
    from antennaknobs.cli import list_builtin_designs

    names = set(list_builtin_designs())
    assert "dipoles.invvee_coax_station" in names
    assert "wire.doublet_ladder_tuner" in names


def test_coax_station_line_loss_brackets_matched_loss_on_resonance():
    """Near-matched (SWR ≈ 1.2 at 28.47 MHz), the single TL entry sits just
    above the cable's matched loss and well below 1 dB extra."""
    eng = _momwire(CoaxStation())
    fr = _budget_fractions(eng)
    (tl_frac,) = fr.values()
    c = CABLES["RG-8X"]
    matched_db = c.k1 * np.sqrt(28.47) + c.k2 * 28.47  # per 100 ft = the run
    matched_frac = 1.0 - 10.0 ** (-matched_db / 10.0)
    assert matched_frac <= tl_frac < 1.0 - 10.0 ** (-(matched_db + 0.5) / 10.0)


def test_coax_station_swr_penalty_off_resonance():
    """Worked off-band (24.94 MHz) the same line burns far more than its
    matched loss — the SWR penalty emerges from the circuit solve."""
    eng = _momwire(_with_params(CoaxStation, freq=24.94))
    fr = _budget_fractions(eng)
    (tl_frac,) = fr.values()
    c = CABLES["RG-8X"]
    matched_db = c.k1 * np.sqrt(24.94) + c.k2 * 24.94
    matched_frac = 1.0 - 10.0 ** (-matched_db / 10.0)
    assert tl_frac > 2.0 * matched_frac
    assert eng._excited_efficiency < 0.5


def test_doublet_station_matches_fifty_ohms_with_coil_dominated_loss():
    """Stock tune targets the workbench default — finite-fast ground AND the
    B-spline solver — so solve with both. (The 100 ft high-SWR line amplifies
    basis-level feedpoint differences: the sinusoidal basis lands the rig tens
    of ohms away, and free space is ~SWR 2.)"""
    from antennaknobs.engines import MomwireEngine

    eng = MomwireEngine(DoubletStation(), ground=("finite-fast", 10.0, 0.002))
    (z,) = eng.impedance()
    assert abs(z - 50.0) < 1.0  # stock tune lands the rig at ~50 Ω
    fr = _budget_fractions(eng)
    coil = fr["Shunt m"]
    line = fr["TL li→feed"]
    caps = fr["TwoPort rig→m"] + fr["TwoPort m→li"]
    # The coil is the tuner's loss; the (ideal) caps burn nothing.
    assert coil > 0.02
    assert caps < 1e-6
    # Stock 40 m operating point: ~92% radiated, coil ≳ line.
    assert 0.85 < eng._excited_efficiency < 0.95
    assert coil > 0.8 * line


def test_doublet_coil_loss_scales_with_q():
    frac_q200 = _budget_fractions(_momwire(DoubletStation()))["Shunt m"]
    frac_q100 = _budget_fractions(_momwire(_with_params(DoubletStation, coil_q=100.0)))[
        "Shunt m"
    ]
    frac_ideal = _budget_fractions(_momwire(_with_params(DoubletStation, coil_q=0.0)))[
        "Shunt m"
    ]
    assert frac_ideal < 1e-9
    # Halving Q ~doubles the coil's share (the match shifts slightly, so
    # allow a generous band around exactly 2×).
    assert 1.5 * frac_q200 < frac_q100 < 3.0 * frac_q200


def test_both_stations_cross_check_on_pynec():
    pytest.importorskip("antennaknobs.engines.pynec")
    from antennaknobs.engines import PyNECEngine

    for cls in (CoaxStation, DoubletStation):
        zm = _momwire(cls()).impedance()[0]
        zn = PyNECEngine(cls(), ground=None).impedance()[0]
        assert abs(zm - zn) / abs(zm) < 0.01, f"{cls.__module__}: {zm} vs {zn}"
