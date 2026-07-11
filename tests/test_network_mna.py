"""Tests for the MNA core of `NetworkReducer` (issue #285).

Two layers:

1. **Circuit-theory oracles.** On finite-element networks the MNA solution
   must match independent hand circuit theory: closed-form transforms (TL
   input impedance, L-match, series load) and a ten-line bare nodal
   reduction (`nodal_reference`) built directly from the boundary-condition
   definitions. The MNA formulation was additionally brought up side by side
   against the legacy admittance reducer and matched it to 1e-9 on every
   branch/BC combination — see the flag-gated commits introducing this file.

2. **Degenerate elements only MNA can stamp.** Ideal shorts (0 Ω, 0 H,
   all-omitted branches), a literal inert L-matchbox, and an exactly-at-
   resonance trap in the excited path. The old admittance-only formulation
   raised (or diverged) on these; MNA must return the physical limit.

No MoM solves here — the antenna Y is synthetic, so the whole file is fast.
The engine-level oracle suite (`test_tl_composition`, the `nt_card` oracle,
the L-match and `delta_looparray` cross-engine checks) remains the harness
for the real thing.
"""

import numpy as np
import pytest

from antennaknobs.network import (
    TL,
    Driven,
    Load,
    Network,
    PortAtEdge,
    PortVirtual,
    Shunt,
    TwoPort,
)
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer, tl_admittance_2x2

FREQ_MHZ = 28.0
WL = C_LIGHT / (FREQ_MHZ * 1e6)
OMEGA = 2.0 * np.pi * FREQ_MHZ * 1e6


def synth_y(n, seed):
    """Reciprocal (symmetric), diagonally-dominant complex Y with antenna-ish
    magnitudes (tens of mS on the diagonal) so the systems are well
    conditioned and disagreements are formulation bugs, not conditioning."""
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))
    y = 0.004 * (a + a.T) / 2.0
    return y + np.eye(n) * (0.02 + 0.008j)


def reducer(net, n_real):
    """Build a reducer with the standard port indexing: real PortAtEdge
    ports first in declaration order, virtual ports after."""
    real = [n for n, p in net.ports.items() if isinstance(p, PortAtEdge)]
    virt = [n for n, p in net.ports.items() if isinstance(p, PortVirtual)]
    assert len(real) == n_real
    port_to_idx = {n: i for i, n in enumerate(real + virt)}
    return NetworkReducer(net, port_to_idx, len(real) + len(virt))


def nodal_reference(y_full, driven):
    """Independent oracle: bare nodal reduction written straight from the
    boundary-condition definitions — driven nodes pinned at their EMF, every
    other node floating with I_ext = 0, currents read as Y·V. Only valid
    when every element is a finite admittance stamp (fold loads as shunt
    admittances first; no source may carry a series impedance)."""
    n = y_full.shape[0]
    idx = sorted(driven)
    other = [i for i in range(n) if i not in driven]
    v = np.zeros(n, dtype=np.complex128)
    for k, e in driven.items():
        v[k] = e
    if other:
        rhs = -y_full[np.ix_(other, idx)] @ np.array([driven[k] for k in idx])
        v[other] = np.linalg.solve(y_full[np.ix_(other, other)], rhs)
    return v, y_full @ v


# ---------------------------------------------------------------------------
# 1. Circuit-theory oracles
# ---------------------------------------------------------------------------


def test_bare_driven_port():
    """One driven port, no branches: Z = 1/Y₀₀ and V = E exactly."""
    net = Network(ports={"f": PortAtEdge("f")}, sources=[Driven(port="f")])
    y = synth_y(1, 0)
    red = reducer(net, 1)
    assert red.driven_impedance(y, WL)[0] == pytest.approx(1.0 / y[0, 0], rel=1e-12)
    v, eff, p_in, *_ = red.excited_state(y, WL)
    assert v[0] == pytest.approx(1.0)
    assert eff == 1.0
    assert p_in == pytest.approx(0.5 * float(np.real(np.conj(y[0, 0]))), rel=1e-12)


def test_multi_driven_ports():
    """Two simultaneous sources: every port pinned, I = Y·V directly."""
    net = Network(
        ports={"f1": PortAtEdge("f1"), "f2": PortAtEdge("f2")},
        sources=[Driven(port="f1", voltage=1 + 0j), Driven(port="f2", voltage=0.5j)],
    )
    y = synth_y(2, 1)
    v_ref, i_ref = nodal_reference(y, {0: 1 + 0j, 1: 0.5j})
    z = reducer(net, 2).driven_impedance(y, WL)
    np.testing.assert_allclose(z, v_ref[[0, 1]] / i_ref[[0, 1]], rtol=1e-9)


def test_zero_volt_source_pins_node():
    """The `Driven(port, 0)` datum trick: a 0 V source is a hard V = 0 pin."""
    net = Network(
        ports={"f1": PortAtEdge("f1"), "f2": PortAtEdge("f2")},
        sources=[Driven(port="f1"), Driven(port="f2", voltage=0j)],
    )
    y = synth_y(2, 3)
    red = reducer(net, 2)
    v = red.resolve_voltages(red.apply_branches(y, WL))
    v_ref, i_ref = nodal_reference(y, {0: 1 + 0j, 1: 0j})
    np.testing.assert_allclose(v, v_ref, rtol=1e-9, atol=1e-15)
    z = red.driven_impedance(y, WL)
    assert z[0] == pytest.approx(v_ref[0] / i_ref[0], rel=1e-9)
    assert z[1] == 0.0  # 0 V across a finite current


def test_virtual_driver_with_tl_matches_line_transform():
    """Virtual input → ideal line → antenna: the classic closed form
    Z_in = Z₀ (Z_L + jZ₀ tanθ)/(Z₀ + jZ_L tanθ), efficiency 1 (lossless)."""
    z0, length = 300.0, 0.31 * WL
    net = Network(
        ports={"f": PortAtEdge("f"), "in": PortVirtual("in")},
        branches=[TL(a="in", b="f", z0=z0, length=length)],
        sources=[Driven(port="in")],
    )
    y = synth_y(1, 2)
    z_l = 1.0 / y[0, 0]
    t = np.tan(2.0 * np.pi * length / WL)
    z_expect = z0 * (z_l + 1j * z0 * t) / (z0 + 1j * z_l * t)
    red = reducer(net, 1)
    assert red.driven_impedance(y, WL)[0] == pytest.approx(z_expect, rel=1e-9)
    _v, eff, _p, *_ = red.excited_state(y, WL)
    assert eff == 1.0


def test_transposed_tl_pair():
    """Two lines off one virtual driver, one crossed — check the full
    voltage vector against the bare nodal reduction with the same stamps."""
    net = Network(
        ports={
            "f1": PortAtEdge("f1"),
            "f2": PortAtEdge("f2"),
            "in": PortVirtual("in"),
        },
        branches=[
            TL(a="in", b="f1", z0=300.0, length=0.18 * WL),
            TL(a="in", b="f2", z0=300.0, length=0.18 * WL, transposed=True),
        ],
        sources=[Driven(port="in")],
    )
    y = synth_y(2, 4)
    y_full = np.zeros((3, 3), dtype=np.complex128)
    y_full[:2, :2] = y
    y_full[np.ix_([2, 0], [2, 0])] += tl_admittance_2x2(300.0, 0.18 * WL, WL)
    y_full[np.ix_([2, 1], [2, 1])] += tl_admittance_2x2(
        300.0, 0.18 * WL, WL, transposed=True
    )
    v_ref, i_ref = nodal_reference(y_full, {2: 1 + 0j})
    red = reducer(net, 2)
    v = red.resolve_voltages(red.apply_branches(y, WL))
    np.testing.assert_allclose(v, v_ref, rtol=1e-9)
    assert red.driven_impedance(y, WL)[0] == pytest.approx(
        v_ref[2] / i_ref[2], rel=1e-9
    )


def test_twoport_bridge():
    """Lumped series R+jωL bridging two ports = its 2×2 admittance stamp."""
    r, l = 20.0, 0.4e-6
    net = Network(
        ports={"f1": PortAtEdge("f1"), "f2": PortAtEdge("f2")},
        branches=[TwoPort(a="f1", b="f2", r=r, l=l)],
        sources=[Driven(port="f1")],
    )
    y = synth_y(2, 5)
    y_br = 1.0 / (r + 1j * OMEGA * l)
    y_full = y + y_br * np.array([[1, -1], [-1, 1]])
    v_ref, i_ref = nodal_reference(y_full, {0: 1 + 0j})
    red = reducer(net, 2)
    assert red.driven_impedance(y, WL)[0] == pytest.approx(
        v_ref[0] / i_ref[0], rel=1e-9
    )
    v, _eff, _p, *_ = red.excited_state(y, WL)
    np.testing.assert_allclose(v, v_ref, rtol=1e-9)


def test_twoport_open_zero_capacitor():
    """c = 0 F is an open series path: exactly as if the branch weren't
    there (the inert endpoint of a matching-network capacitor slider)."""
    net = Network(
        ports={"f1": PortAtEdge("f1"), "f2": PortAtEdge("f2")},
        branches=[TwoPort(a="f1", b="f2", c=0.0)],
        sources=[Driven(port="f1")],
    )
    y = synth_y(2, 6)
    v_ref, i_ref = nodal_reference(y, {0: 1 + 0j})
    assert reducer(net, 2).driven_impedance(y, WL)[0] == pytest.approx(
        v_ref[0] / i_ref[0], rel=1e-12
    )


@pytest.mark.parametrize("seed", range(5))
def test_lmatch_matches_two_element_transform(seed):
    """Series-L TwoPort + shunt-C across the antenna feed: the exact
    two-element transform Z_in = jωL + 1/(jωC + Y_ant)."""
    ls, cp = 0.873e-6, 59.57e-12
    net = Network(
        ports={"feed": PortAtEdge("feed"), "in": PortVirtual("in")},
        branches=[
            TwoPort(a="in", b="feed", l=ls),
            Shunt(port="feed", c=cp),
        ],
        sources=[Driven(port="in")],
    )
    y = synth_y(1, seed)
    z_expect = 1j * OMEGA * ls + 1.0 / (1j * OMEGA * cp + y[0, 0])
    assert reducer(net, 1).driven_impedance(y, WL)[0] == pytest.approx(
        z_expect, rel=1e-9
    )


def test_parallel_shunt_is_tank_admittance_on_diagonal():
    net = Network(
        ports={"f": PortAtEdge("f")},
        branches=[Shunt(port="f", r=1000.0, l=1e-6, c=30e-12, parallel=True)],
        sources=[Driven(port="f")],
    )
    y = synth_y(1, 7)
    y_tank = 1.0 / 1000.0 + 1.0 / (1j * OMEGA * 1e-6) + 1j * OMEGA * 30e-12
    assert reducer(net, 1).driven_impedance(y, WL)[0] == pytest.approx(
        1.0 / (y[0, 0] + y_tank), rel=1e-9
    )


def test_series_load_terminated_port():
    """Series R load on an undriven second port (terminated-antenna idiom):
    a shunt impedance Z_L from the gap to the common return, and its
    dissipation drives the efficiency readout."""
    r_l = 600.0
    net = Network(
        ports={"f": PortAtEdge("f"), "term": PortAtEdge("term")},
        branches=[Load(port="term", r=r_l)],
        sources=[Driven(port="f")],
    )
    y = synth_y(2, 8)
    y_full = y + np.diag([0.0, 1.0 / r_l]).astype(np.complex128)
    v_ref, i_ref = nodal_reference(y_full, {0: 1 + 0j})
    red = reducer(net, 2)
    assert red.driven_impedance(y, WL)[0] == pytest.approx(
        v_ref[0] / i_ref[0], rel=1e-9
    )
    v, eff, p_in, *_ = red.excited_state(y, WL)
    np.testing.assert_allclose(v, v_ref, rtol=1e-9)
    p_in_ref = 0.5 * float(np.real(v_ref[0] * np.conj(i_ref[0])))
    p_diss_ref = 0.5 * r_l * abs(v_ref[1] / r_l) ** 2
    assert p_in == pytest.approx(p_in_ref, rel=1e-9)
    assert eff == pytest.approx(1.0 - p_diss_ref / p_in_ref, rel=1e-9)


def test_driven_and_loaded_same_port():
    """Centre-loaded driven short dipole: source and series load chain on
    one port. Exact one-port circuit: Z_seen = Z_L + 1/Y₀₀, the gap voltage
    divides accordingly, and only Re(Z_L) burns power."""
    z_l = 5.0 + 1j * OMEGA * 2e-6
    net = Network(
        ports={"f": PortAtEdge("f")},
        branches=[Load(port="f", r=5.0, l=2e-6)],
        sources=[Driven(port="f")],
    )
    y = synth_y(1, 9)
    z_ant = 1.0 / y[0, 0]
    red = reducer(net, 1)
    assert red.driven_impedance(y, WL)[0] == pytest.approx(z_l + z_ant, rel=1e-9)
    v, eff, p_in, *_ = red.excited_state(y, WL)
    i = 1.0 / (z_l + z_ant)
    assert v[0] == pytest.approx(z_ant * i, rel=1e-9)  # physical gap voltage
    assert p_in == pytest.approx(0.5 * float(np.real(np.conj(i))), rel=1e-9)
    assert eff == pytest.approx(
        1.0 - (0.5 * 5.0 * abs(i) ** 2) / (0.5 * float(np.real(np.conj(i)))), rel=1e-9
    )


def test_parallel_trap_load_off_resonance():
    """Parallel-LC trap off resonance: a finite shunt impedance at the port."""
    l, c = 1.5e-6, 30e-12
    net = Network(
        ports={"f": PortAtEdge("f"), "arm": PortAtEdge("arm")},
        branches=[Load(port="arm", l=l, c=c, parallel=True)],
        sources=[Driven(port="f")],
    )
    y = synth_y(2, 10)
    y_tank = 1.0 / (1j * OMEGA * l) + 1j * OMEGA * c
    y_full = y + np.diag([0.0, 1.0]).astype(np.complex128) * y_tank
    v_ref, i_ref = nodal_reference(y_full, {0: 1 + 0j})
    red = reducer(net, 2)
    assert red.driven_impedance(y, WL)[0] == pytest.approx(
        v_ref[0] / i_ref[0], rel=1e-9
    )
    v, _eff, _p, *_ = red.excited_state(y, WL)
    np.testing.assert_allclose(v, v_ref, rtol=1e-9)


def test_everything_at_once():
    """TL + transposed TL + TwoPort + both Shunt modes + both Load modes +
    two sources, six nodes — the whole stamp set in one network, against
    the bare nodal reduction with loads folded as shunts."""
    lengths = {"tl1": 0.27 * WL, "tl2": 0.12 * WL}
    net = Network(
        ports={
            "f1": PortAtEdge("f1"),
            "f2": PortAtEdge("f2"),
            "f3": PortAtEdge("f3"),
            "f4": PortAtEdge("f4"),
            "in": PortVirtual("in"),
            "n1": PortVirtual("n1"),
        },
        branches=[
            TL(a="in", b="f1", z0=450.0, length=lengths["tl1"]),
            TL(a="in", b="n1", z0=300.0, length=lengths["tl2"], transposed=True),
            TwoPort(a="n1", b="f2", r=10.0, c=120e-12),
            Shunt(port="in", c=25e-12),
            Shunt(port="n1", r=800.0, l=0.9e-6, c=45e-12, parallel=True),
            Load(port="f3", r=300.0, l=0.5e-6),
            Load(port="f4", l=1.2e-6, c=40e-12, parallel=True),
        ],
        sources=[Driven(port="in"), Driven(port="f2", voltage=0.3 - 0.4j)],
    )
    y = synth_y(4, 11)
    # in = node 4, n1 = node 5.
    y_full = np.zeros((6, 6), dtype=np.complex128)
    y_full[:4, :4] = y
    y_full[np.ix_([4, 0], [4, 0])] += tl_admittance_2x2(450.0, lengths["tl1"], WL)
    y_full[np.ix_([4, 5], [4, 5])] += tl_admittance_2x2(
        300.0, lengths["tl2"], WL, transposed=True
    )
    y_2p = 1.0 / (10.0 + 1.0 / (1j * OMEGA * 120e-12))
    y_full[np.ix_([5, 1], [5, 1])] += y_2p * np.array([[1, -1], [-1, 1]])
    y_full[4, 4] += 1j * OMEGA * 25e-12
    y_full[5, 5] += 1.0 / 800.0 + 1.0 / (1j * OMEGA * 0.9e-6) + 1j * OMEGA * 45e-12
    y_full[2, 2] += 1.0 / (300.0 + 1j * OMEGA * 0.5e-6)
    y_full[3, 3] += 1.0 / (1j * OMEGA * 1.2e-6) + 1j * OMEGA * 40e-12
    v_ref, i_ref = nodal_reference(y_full, {4: 1 + 0j, 1: 0.3 - 0.4j})
    red = reducer(net, 4)
    z = red.driven_impedance(y, WL)
    np.testing.assert_allclose(z, v_ref[[4, 1]] / i_ref[[4, 1]], rtol=1e-9)
    v, _eff, _p, *_ = red.excited_state(y, WL)
    np.testing.assert_allclose(v, v_ref, rtol=1e-9)


def test_load_on_virtual_port_rejected():
    net = Network(
        ports={"f": PortAtEdge("f"), "v": PortVirtual("v")},
        branches=[TL(a="f", b="v", z0=50.0, length=0.1 * WL), Load(port="v", r=50.0)],
        sources=[Driven(port="f")],
    )
    with pytest.raises(ValueError, match="virtual port"):
        reducer(net, 1).driven_impedance(synth_y(1, 0), WL)


# ---------------------------------------------------------------------------
# 2. Degenerate elements only MNA can stamp
# ---------------------------------------------------------------------------


def _series_twoport_z(r=None, l=None, c=None):
    net = Network(
        ports={"f1": PortAtEdge("f1"), "f2": PortAtEdge("f2")},
        branches=[TwoPort(a="f1", b="f2", r=r, l=l, c=c)],
        sources=[Driven(port="f1")],
    )
    return reducer(net, 2).driven_impedance(synth_y(2, 0), WL)[0]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"r": 0.0},  # 0 Ω resistor
        {"l": 0.0},  # 0 H ideal wire
        {},  # all-omitted branch
        {"l": 1e-6, "c": 1.0 / (OMEGA**2 * 1e-6)},  # exact series-LC resonance
    ],
    ids=["zero-ohm", "zero-henry", "all-omitted", "series-lc-resonance"],
)
def test_ideal_short_twoport_is_finite_and_identifies_nodes(kwargs):
    """A z = 0 series TwoPort is an ideal short: finite result, the limit of
    a vanishing resistance, and exact node identification."""
    z_short = _series_twoport_z(**kwargs)
    assert np.isfinite(z_short)
    z_almost = _series_twoport_z(r=1e-9)
    assert z_short == pytest.approx(z_almost, rel=1e-6)
    # Node identification: the shorted pair behaves as one merged node.
    y = synth_y(2, 0)
    merged = np.array([[y[0, 0] + y[0, 1] + y[1, 0] + y[1, 1]]])
    net = Network(ports={"m": PortAtEdge("m")}, sources=[Driven(port="m")])
    z_merged = reducer(net, 1).driven_impedance(merged, WL)[0]
    assert z_short == pytest.approx(z_merged, rel=1e-9)


def test_shunt_ideal_short_pins_port_to_common():
    """A 0 H shunt hard-shorts the port to the common reference: V_k = 0,
    with the (finite) short-circuit current flowing through the branch."""
    net = Network(
        ports={"f1": PortAtEdge("f1"), "f2": PortAtEdge("f2")},
        branches=[Shunt(port="f2", l=0.0)],
        sources=[Driven(port="f1")],
    )
    y = synth_y(2, 1)
    red = reducer(net, 2)
    system = red.apply_branches(y, WL)
    v = red.resolve_voltages(system)
    assert v[1] == pytest.approx(0.0, abs=1e-15)
    z = red.impedance_from_y(system)[0]
    assert np.isfinite(z)
    # With v₂ pinned at 0 the short-circuit Y applies directly: Z = 1/Y₁₁.
    assert z == pytest.approx(1.0 / y[0, 0], rel=1e-9)


def test_inert_lmatchbox_stamped_literally():
    """TwoPort(l=0) + Shunt(c=0) stamped LITERALLY is a pass-through:
    Z_in = Z_ant, with no design-level topology special-casing (the interim
    dodge `skyloop_lmatch.build_network` needed on the admittance reducer)."""
    inert = Network(
        ports={"feed": PortAtEdge("feed"), "in": PortVirtual("in")},
        branches=[TwoPort(a="in", b="feed", l=0.0), Shunt(port="feed", c=0.0)],
        sources=[Driven(port="in")],
    )
    y = synth_y(1, 7)
    z_inert = reducer(inert, 1).driven_impedance(y, WL)[0]
    assert z_inert == pytest.approx(1.0 / y[0, 0], rel=1e-12)


def test_open_circuited_source_reports_clean_infinity():
    """A driven port with no current path (its only branch is a 0 F series
    capacitor = an open) is a physical open circuit: Z = ∞. The readout must
    return a clean real infinity — no ZeroDivision, no numpy divide-by-zero
    warning, no NaN imaginary part (issue #289)."""
    import warnings

    net = Network(
        ports={"f": PortAtEdge("f"), "in": PortVirtual("in")},
        branches=[TwoPort(a="in", b="f", c=0.0)],
        sources=[Driven(port="in")],
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        z = reducer(net, 1).driven_impedance(synth_y(1, 0), WL)[0]
    assert np.isinf(z.real) and z.real > 0 and z.imag == 0.0, z


def test_trap_load_at_exact_resonance_is_open():
    """A parallel-LC Load exactly at ω₀ = 1/√(LC) is the intended open
    circuit. The legacy excited path formed Z_L = ∞ there; the MNA
    termination uses the tank admittance (0 at resonance), so the excited
    state is finite and the trap port carries no current."""
    l = 1.0e-6
    c = 1.0 / (OMEGA**2 * l)  # resonate the tank exactly at FREQ_MHZ
    net = Network(
        ports={"f": PortAtEdge("f"), "arm": PortAtEdge("arm")},
        branches=[Load(port="arm", l=l, c=c, parallel=True)],
        sources=[Driven(port="f")],
    )
    y = synth_y(2, 5)
    red = reducer(net, 2)
    v, eff, p_in, *_ = red.excited_state(y, WL)
    assert np.all(np.isfinite(v)) and np.isfinite(p_in)
    assert eff == pytest.approx(1.0)  # an open burns nothing
    # Open termination at the arm: the arm port floats (I_ext = 0), the same
    # network as having no Load branch at all.
    v_ref, _ = nodal_reference(y, {0: 1 + 0j})
    np.testing.assert_allclose(v, v_ref, rtol=1e-9)
