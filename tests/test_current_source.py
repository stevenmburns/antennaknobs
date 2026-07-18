"""DrivenCurrent — the MNA forced-current source (4nec2's EX 6, issue #442).

Same harness philosophy as `test_network_mna.py`: synthetic antenna Y, so
every expectation is hand circuit theory and the file runs with no MoM
solves. The one physical invariant doing most of the work: a one-port's
driving-point impedance does not depend on what kind of ideal source
excites it, so every current-source readout can be cross-checked against
the voltage-source path that the rest of the suite already trusts.
"""

import numpy as np
import pytest

from antennaknobs.network import (
    Driven,
    DrivenCurrent,
    Load,
    Network,
    PortOnWire,
)
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer

FREQ_MHZ = 28.0
WL = C_LIGHT / (FREQ_MHZ * 1e6)


def synth_y(n, seed):
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))
    y = 0.004 * (a + a.T) / 2.0
    return y + np.eye(n) * (0.02 + 0.008j)


def reducer(net, n_real):
    port_to_idx = {name: i for i, name in enumerate(net.ports)}
    return NetworkReducer(net, port_to_idx, n_real)


def ports(*names):
    return {n: PortOnWire(n) for n in names}


def test_bare_current_port_matches_voltage_impedance():
    """One port: Z must be 1/Y₀₀ regardless of source kind, and the solved
    gap voltage is I/Y₀₀."""
    y = synth_y(1, 0)
    z_v = reducer(
        Network(ports=ports("f"), sources=[Driven(port="f")]), 1
    ).driven_impedance(y, WL)[0]
    net_i = Network(ports=ports("f"), sources=[DrivenCurrent(port="f", current=2j)])
    red = reducer(net_i, 1)
    z_i = red.driven_impedance(y, WL)[0]
    assert z_i == pytest.approx(z_v, rel=1e-12)
    v, eff, p_in, _budget = red.excited_state(y, WL)
    assert v[0] == pytest.approx(2j / y[0, 0], rel=1e-12)
    assert eff == 1.0
    assert p_in == pytest.approx(0.5 * float(np.real(v[0] * np.conj(2j))), rel=1e-12)


def test_phased_pair_forced_ratio():
    """Two current sources with a K6STI-style complex ratio: node voltages
    are the direct nodal solution v = Y⁻¹·i and each port's impedance is
    v_k / I_k — the mutual coupling lands in Z, not in the currents."""
    y = synth_y(2, 7)
    i0, i1 = 1.0 + 0j, -0.86 + 0.508j
    net = Network(
        ports=ports("a", "b"),
        sources=[
            DrivenCurrent(port="a", current=i0),
            DrivenCurrent(port="b", current=i1),
        ],
    )
    v_ref = np.linalg.solve(y, np.array([i0, i1]))
    red = reducer(net, 2)
    z = red.driven_impedance(y, WL)
    np.testing.assert_allclose(z, v_ref / np.array([i0, i1]), rtol=1e-9)
    v, _eff, p_in, _budget = red.excited_state(y, WL)
    np.testing.assert_allclose(v[:2], v_ref, rtol=1e-9)
    p_ref = 0.5 * float(np.real(v_ref @ np.conj([i0, i1])))
    assert p_in == pytest.approx(p_ref, rel=1e-9)


def test_series_load_drops_inside_the_source_loop():
    """A series Load on a current-driven port must not change the antenna
    solve at all (the forced current IS the port current); it adds its
    impedance to the reported Z and its dissipation to the budget."""
    y = synth_y(1, 3)
    r_load = 37.0
    bare = Network(ports=ports("f"), sources=[DrivenCurrent(port="f")])
    loaded = Network(
        ports=ports("f"),
        branches=[Load(port="f", r=r_load)],
        sources=[DrivenCurrent(port="f")],
    )
    z_bare = reducer(bare, 1).driven_impedance(y, WL)[0]
    red = reducer(loaded, 1)
    z_loaded = red.driven_impedance(y, WL)[0]
    assert z_loaded == pytest.approx(z_bare + r_load, rel=1e-12)
    v_bare = reducer(bare, 1).excited_state(y, WL)[0]
    v, eff, p_in, budget = red.excited_state(y, WL)
    assert v[0] == pytest.approx(v_bare[0], rel=1e-12)  # gap voltage unchanged
    p_load = 0.5 * r_load * abs(1.0) ** 2
    ((label, w),) = budget
    assert label.startswith("Load") and w == pytest.approx(p_load, rel=1e-12)
    assert p_in == pytest.approx(
        0.5 * float(np.real(v[0] * np.conj(1.0))) + p_load, rel=1e-12
    )
    assert eff == pytest.approx(1.0 - p_load / p_in, rel=1e-9)


def test_mixed_voltage_and_current_sources():
    """Voltage on port a, current into port b: v_a pinned at E, KCL at b
    gives v_b = (I − Y₁₀·E)/Y₁₁; impedances read per source kind."""
    y = synth_y(2, 11)
    e, i = 1.0 + 0j, 0.25 - 0.5j
    net = Network(
        ports=ports("a", "b"),
        sources=[Driven(port="a", voltage=e), DrivenCurrent(port="b", current=i)],
    )
    v_b = (i - y[1, 0] * e) / y[1, 1]
    j_a = y[0, 0] * e + y[0, 1] * v_b  # current the a-termination delivers
    z = reducer(net, 2).driven_impedance(y, WL)
    assert z[0] == pytest.approx(e / j_a, rel=1e-9)
    assert z[1] == pytest.approx(v_b / i, rel=1e-9)


def test_parallel_current_sources_sum():
    """Two DrivenCurrent entries on one port sum by KCL, and each reported
    impedance uses the total forced current (same termination branch)."""
    y = synth_y(1, 5)
    net = Network(
        ports=ports("f"),
        sources=[
            DrivenCurrent(port="f", current=1 + 0j),
            DrivenCurrent(port="f", current=0.5j),
        ],
    )
    i_tot = 1 + 0.5j
    z = reducer(net, 1).driven_impedance(y, WL)
    v = i_tot / y[0, 0]
    assert z[0] == pytest.approx(v / i_tot, rel=1e-12)
    assert z[1] == pytest.approx(v / i_tot, rel=1e-12)


def test_voltage_and_current_on_same_port_raises():
    net = Network(
        ports=ports("f"),
        sources=[Driven(port="f"), DrivenCurrent(port="f")],
    )
    with pytest.raises(ValueError, match="contradictory"):
        reducer(net, 1).driven_impedance(synth_y(1, 0), WL)


def test_current_into_resonant_trap_raises():
    """Forcing a current through an exactly-at-resonance parallel trap is an
    open circuit — unphysical, so it must raise, not return inf/NaN."""
    omega = 2.0 * np.pi * FREQ_MHZ * 1e6
    l = 1e-6
    c = 1.0 / (omega**2 * l)  # resonant at exactly FREQ_MHZ
    net = Network(
        ports=ports("f"),
        branches=[Load(port="f", l=l, c=c, parallel=True)],
        sources=[DrivenCurrent(port="f")],
    )
    with pytest.raises(ValueError, match="open"):
        reducer(net, 1).driven_impedance(synth_y(1, 2), WL)
