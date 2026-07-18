"""Per-branch power budget (issue #299).

The MNA solve carries every branch current explicitly, so "where did the
watts go" is a readout: excited_state now returns a per-branch (label,
watts) budget, and efficiency counts EVERY dissipative network branch —
resistive TwoPort/Shunt elements and lossy TLs included, not just Load
terminations (the pre-#299 parity gap).
"""

import numpy as np

from antennaknobs.designs.arrays.lumped_coupled_pair import Builder as CoupledPair
from antennaknobs.network import (
    TL,
    Driven,
    Load,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
    TwoPort,
)
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer

F_MHZ = 10.0
WL = C_LIGHT / (F_MHZ * 1e6)
OMEGA = 2.0 * np.pi * F_MHZ * 1e6


def _station_reducer():
    """Rig → lossy coax → lossy L-match → antenna: one of everything."""
    net = Network(
        ports={
            "ant": PortOnWire("ant"),
            "tuner": PortVirtual("tuner"),
            "rig": PortVirtual("rig"),
        },
        branches=[
            TL("rig", "tuner", z0=50.0, length=30.48, vf=0.66, k1=0.40, k2=0.008),
            TwoPort(a="tuner", b="ant", l=2.2e-6, ql=100.0),
            Shunt(port="tuner", c=150e-12, qc=500.0),
            Load(port="ant", r=10.0),
        ],
        sources=[Driven("rig", 1 + 0j)],
    )
    return NetworkReducer(net, {"ant": 0, "tuner": 1, "rig": 2}, 3)


def test_budget_sums_to_p_in():
    """radiated (= power into the antenna Y) + every branch's watts = p_in."""
    reducer = _station_reducer()
    z_ant = 60.0 + 25.0j
    y_real = np.array([[1.0 / z_ant]], dtype=np.complex128)
    v, eff, p_in, budget = reducer.excited_state(y_real, WL)
    p_ant = 0.5 * abs(v[0]) ** 2 * np.real(1.0 / z_ant)
    p_network = sum(w for _l, w in budget)
    np.testing.assert_allclose(p_ant + p_network, p_in, rtol=1e-12)
    # One entry per branch, labelled, every one dissipative here.
    labels = [label for label, _w in budget]
    assert labels == ["TL rig→tuner", "TwoPort tuner→ant", "Shunt tuner", "Load ant"]
    assert all(w > 0 for _l, w in budget)
    # Consistent efficiency: 1 - all network dissipation / p_in.
    np.testing.assert_allclose(eff, 1.0 - p_network / p_in, rtol=1e-12)


def test_lossless_network_reports_unity_and_zero_watts():
    net = Network(
        ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
        branches=[
            TL("rig", "ant", z0=50.0, length=13.0),
            Shunt(port="ant", c=20e-12),
        ],
        sources=[Driven("rig", 1 + 0j)],
    )
    reducer = NetworkReducer(net, {"ant": 0, "rig": 1}, 2)
    _v, eff, p_in, budget = reducer.excited_state(
        np.array([[1.0 / 50.0]], dtype=np.complex128), WL
    )
    assert eff == 1.0
    assert p_in > 0
    for _label, w in budget:
        assert abs(w) < 1e-12 * p_in  # float noise only


def test_load_only_efficiency_matches_the_pre_299_accounting():
    """For Load-only networks the termination probe IS the old p_diss sum,
    so the shipped efficiency numbers (T2FD, terminated designs) hold."""
    net = Network(
        ports={"feed": PortOnWire("feed"), "term": PortOnWire("term")},
        branches=[Load(port="term", r=390.0)],
        sources=[Driven("feed", 1 + 0j)],
    )
    reducer = NetworkReducer(net, {"feed": 0, "term": 1}, 2)
    y = np.array([[0.02, -0.015], [-0.015, 0.02]], dtype=np.complex128)
    v, eff, p_in, budget = reducer.excited_state(y, WL)
    (label, w) = budget[0]
    assert label == "Load term"
    # Recompute the old Load-only accounting directly: ½Re((E−v)·j*) over
    # terminations with E=0 at the loaded port.
    system = reducer.apply_branches(y, WL)
    v2, j2 = system.solve()
    col, e, _kind, _z_chain = system.terminations[1]
    old = 0.5 * float(np.real((e - v2[1]) * np.conj(j2[col])))
    np.testing.assert_allclose(w, old, rtol=1e-12)
    np.testing.assert_allclose(eff, 1.0 - old / p_in, rtol=1e-12)


def test_coupled_pair_coupling_resistor_now_counts():
    """lumped_coupled_pair bridges its feeds with a series R+jωL TwoPort.
    Pre-#299 the R burned power (visible in gain via p_in) while efficiency
    read 1.0; now the budget itemizes it and efficiency drops below 1."""
    from antennaknobs.engines import MomwireEngine
    from momwire import SinusoidalSolver

    eng = MomwireEngine(CoupledPair(), ground=None, solver=SinusoidalSolver)
    eng.current_distribution()
    budget = eng._excited_power_budget
    assert len(budget) == 1 and budget[0][0].startswith("TwoPort")
    assert budget[0][1] > 0
    assert 0.0 < eng._excited_efficiency < 1.0
    np.testing.assert_allclose(
        eng._excited_efficiency,
        1.0 - budget[0][1] / eng._excited_p_in,
        rtol=1e-9,
    )
