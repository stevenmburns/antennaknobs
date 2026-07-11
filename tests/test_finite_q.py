"""Finite-Q components in lumped network branches (issue #298).

Circuit-level oracles at the NetworkReducer/helper level (no MoM solve):

  - a series inductor with Q has Z = ωL/Q + jωL exactly; a series capacitor
    with Q has ESR = 1/(ωC·Q);
  - a lossy parallel tank tops out at the textbook Z ≈ Q·ω₀L at resonance
    instead of opening completely;
  - ql/qc default to None and are bit-identical to the ideal expressions;
  - a series matching element with finite Q shifts the input impedance by
    exactly its loss resistance;
  - PyNEC routing: a finite-Q Load takes the reducer path (ld_card values
    are baked per context and cannot track R = ωL/Q across a sweep).
"""

import numpy as np
import pytest

from antennaknobs.designs.loops.skyloop_lmatch import Builder as LMatchBuilder
from antennaknobs.designs.verticals.inverted_l_tmatch import Builder as TMatchBuilder
from antennaknobs.network import (
    Driven,
    Network,
    PortAtEdge,
    PortVirtual,
    Shunt,
    TwoPort,
    _parallel_rlc_admittance,
    _series_rlc_impedance,
)
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer

F_MHZ = 10.0
WL = C_LIGHT / (F_MHZ * 1e6)
OMEGA = 2.0 * np.pi * F_MHZ * 1e6


def test_series_coil_q_is_exactly_omega_l_over_q():
    l, q = 2.2e-6, 150.0
    z = _series_rlc_impedance(None, l, None, OMEGA, ql=q)
    assert z == pytest.approx(OMEGA * l / q + 1j * OMEGA * l)


def test_series_capacitor_q_is_exactly_the_esr():
    c, q = 100e-12, 1000.0
    z = _series_rlc_impedance(None, None, c, OMEGA, qc=q)
    assert z == pytest.approx(1.0 / (OMEGA * c * q) + 1.0 / (1j * OMEGA * c))


def test_default_q_is_bit_identical_to_ideal():
    args = (10.0, 2.2e-6, 100e-12, OMEGA)
    assert _series_rlc_impedance(*args) == _series_rlc_impedance(
        *args, ql=None, qc=None
    )
    assert _parallel_rlc_admittance(*args) == _parallel_rlc_admittance(
        *args, ql=None, qc=None
    )


def test_lossy_tank_resonates_at_q_omega_l():
    l, c, q = 2.2e-6, 100e-12, 100.0
    w0 = 1.0 / np.sqrt(l * c)
    y = _parallel_rlc_admittance(None, l, c, w0, ql=q)
    z_res = 1.0 / y
    # Textbook parallel tank with lossy L: |Z| at resonance ≈ Q·ω₀L for
    # high Q (exact value Q·ω₀L·(1 + 1/Q²) with a small phase angle).
    assert abs(z_res) == pytest.approx(q * w0 * l, rel=2.0 / q)
    # The ideal tank at resonance is an open to float rounding — negligible
    # next to the lossy tank's finite conductance.
    assert abs(_parallel_rlc_admittance(None, l, c, w0)) < 1e-6 * abs(y)


def test_series_matching_coil_loss_adds_directly_to_zin():
    """Series TwoPort L between the source and a resistive port: finite Q
    must shift the input impedance by exactly ωL/Q + 0j."""
    l, q = 2.2e-6, 100.0

    def zin(ql):
        net = Network(
            ports={"ant": PortAtEdge("ant"), "in": PortVirtual("in")},
            branches=[TwoPort(a="in", b="ant", l=l, ql=ql)],
            sources=[Driven("in", 1 + 0j)],
        )
        reducer = NetworkReducer(net, {"ant": 0, "in": 1}, 2)
        (z,) = reducer.driven_impedance(np.array([[1.0 / 50.0]]), WL)
        return z

    np.testing.assert_allclose(zin(q) - zin(None), OMEGA * l / q + 0j, rtol=1e-12)


def test_lossy_shunt_coil_dissipates_power():
    """Shunt L with finite Q across a driven port burns power: p_in rises
    relative to the ideal-coil network for the same source voltage."""

    def p_in(ql):
        net = Network(
            ports={"ant": PortAtEdge("ant")},
            branches=[Shunt(port="ant", l=2.2e-6, ql=ql)],
            sources=[Driven("ant", 1 + 0j)],
        )
        reducer = NetworkReducer(net, {"ant": 0}, 1)
        _v, _eff, p = reducer.excited_state(np.array([[1.0 / 5000.0]]), WL)
        return p

    assert p_in(50.0) > p_in(None)


def test_tuner_designs_expose_the_coil_q_knob():
    # Default 0 = ideal coil: the branch carries ql=None (bit-identical).
    for builder_cls, lossy_branch in [
        (LMatchBuilder, TwoPort),
        (TMatchBuilder, Shunt),
    ]:
        net = builder_cls().build_network()
        coils = [
            b
            for b in net.branches
            if isinstance(b, lossy_branch) and getattr(b, "l", None)
        ]
        assert coils and all(b.ql is None for b in coils)
        net_q = builder_cls(
            params={**builder_cls.default_params, "coil_q": 200.0}
        ).build_network()
        coils_q = [
            b
            for b in net_q.branches
            if isinstance(b, lossy_branch) and getattr(b, "l", None)
        ]
        assert coils_q and all(b.ql == 200.0 for b in coils_q)


def test_pynec_routes_finite_q_loads_down_the_reducer():
    pynec_mod = pytest.importorskip("antennaknobs.engines.pynec")
    from antennaknobs.designs.multiband.trap_dipole import Builder as TrapBuilder
    from antennaknobs.network import Load

    class LossyTrapBuilder(TrapBuilder):
        def build_network(self):
            net = super().build_network()
            branches = [
                Load(port=b.port, r=b.r, l=b.l, c=b.c, parallel=b.parallel, ql=100.0)
                if isinstance(b, Load)
                else b
                for b in net.branches
            ]
            return Network(ports=net.ports, branches=branches, sources=net.sources)

    ideal = pynec_mod.PyNECEngine(TrapBuilder())
    lossy = pynec_mod.PyNECEngine(LossyTrapBuilder())
    assert not ideal._use_reducer, "ideal trap Loads should stay native (ld_card)"
    assert lossy._use_reducer, "finite-Q Loads must take the reducer path"
