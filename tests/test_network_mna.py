"""Cross-checks for the MNA reformulation of `NetworkReducer` (issue #285).

Two layers:

1. **Formulation equivalence.** On finite-element networks the MNA system and
   the legacy admittance reduction are algebraically the same circuit, so
   `driven_impedance` / `excited_state` must agree to numerical precision.
   These tests run both formulations over synthetic (reciprocal, well-
   conditioned) antenna Y matrices covering every branch type and boundary-
   condition combination the legacy code special-cased: TL, transposed TL,
   TwoPort, series/parallel Shunt, series/parallel Load, driven+loaded ports,
   multi-driven networks, virtual drivers, and 0 V sources.

2. **Degenerate elements only MNA can stamp.** Ideal shorts (0 Ω, 0 H,
   all-omitted branches), a literal inert L-matchbox, and an exactly-at-
   resonance trap in the excited path. The legacy formulation raises (or
   diverges) on these; MNA must return the physical limit.

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
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer

FREQ_MHZ = 28.0
WL = C_LIGHT / (FREQ_MHZ * 1e6)
OMEGA = 2.0 * np.pi * FREQ_MHZ * 1e6


def synth_y(n, seed):
    """Reciprocal (symmetric), diagonally-dominant complex Y with antenna-ish
    magnitudes (tens of mS on the diagonal) so both formulations are well
    conditioned and disagreements are formulation bugs, not conditioning."""
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))
    y = 0.004 * (a + a.T) / 2.0
    return y + np.eye(n) * (0.02 + 0.008j)


def reducers(net, n_real, extra_virtual=()):
    """Build (legacy, mna) reducers with the standard port indexing: real
    PortAtEdge ports first in declaration order, virtual ports after."""
    real = [n for n, p in net.ports.items() if isinstance(p, PortAtEdge)]
    virt = [n for n, p in net.ports.items() if isinstance(p, PortVirtual)]
    assert len(real) == n_real
    port_to_idx = {n: i for i, n in enumerate(real + virt)}
    n_total = len(real) + len(virt)
    return (
        NetworkReducer(net, port_to_idx, n_total, formulation="admittance"),
        NetworkReducer(net, port_to_idx, n_total, formulation="mna"),
    )


def assert_formulations_agree(net, n_real, seed=0, check_legacy_voltages=True):
    """Impedances and excited-state outputs must match across formulations.

    `check_legacy_voltages=False` for networks with loads: there the legacy
    impedance path pins loaded-port V = 0 (a bookkeeping value) while MNA
    reports the physical gap voltage, so only `excited_state`'s voltages —
    physical in both — are comparable.
    """
    y = synth_y(n_real, seed)
    legacy, mna = reducers(net, n_real)

    z_legacy = legacy.driven_impedance(y, WL)
    z_mna = mna.driven_impedance(y, WL)
    np.testing.assert_allclose(z_mna, z_legacy, rtol=1e-9, atol=1e-12)

    v_legacy, eff_legacy, pin_legacy = legacy.excited_state(y, WL)
    v_mna, eff_mna, pin_mna = mna.excited_state(y, WL)
    np.testing.assert_allclose(v_mna, v_legacy, rtol=1e-9, atol=1e-12)
    assert eff_mna == pytest.approx(eff_legacy, rel=1e-9)
    assert pin_mna == pytest.approx(pin_legacy, rel=1e-9)

    if check_legacy_voltages:
        v_legacy = legacy.resolve_voltages(legacy.apply_branches(y, WL))
        v_mna = mna.resolve_voltages(mna.apply_branches(y, WL))
        np.testing.assert_allclose(v_mna, v_legacy, rtol=1e-9, atol=1e-12)


# ---------------------------------------------------------------------------
# 1. Formulation equivalence
# ---------------------------------------------------------------------------


def test_bare_driven_port():
    net = Network(ports={"f": PortAtEdge("f")}, sources=[Driven(port="f")])
    assert_formulations_agree(net, 1)


def test_multi_driven_ports():
    net = Network(
        ports={"f1": PortAtEdge("f1"), "f2": PortAtEdge("f2")},
        sources=[Driven(port="f1", voltage=1 + 0j), Driven(port="f2", voltage=0.5j)],
    )
    assert_formulations_agree(net, 2)


def test_zero_volt_source_pins_node():
    """The `Driven(port, 0)` datum trick: a 0 V source is a hard V = 0 pin."""
    net = Network(
        ports={"f1": PortAtEdge("f1"), "f2": PortAtEdge("f2")},
        sources=[Driven(port="f1"), Driven(port="f2", voltage=0j)],
    )
    assert_formulations_agree(net, 2)
    y = synth_y(2, 3)
    _, mna = reducers(net, 2)
    v = mna.resolve_voltages(mna.apply_branches(y, WL))
    assert v[1] == pytest.approx(0.0)


def test_virtual_driver_with_tl():
    net = Network(
        ports={"f": PortAtEdge("f"), "in": PortVirtual("in")},
        branches=[TL(a="in", b="f", z0=300.0, length=0.31 * WL)],
        sources=[Driven(port="in")],
    )
    assert_formulations_agree(net, 1)


def test_transposed_tl_pair():
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
    assert_formulations_agree(net, 2)


def test_twoport_bridge():
    net = Network(
        ports={"f1": PortAtEdge("f1"), "f2": PortAtEdge("f2")},
        branches=[TwoPort(a="f1", b="f2", r=20.0, l=0.4e-6)],
        sources=[Driven(port="f1")],
    )
    assert_formulations_agree(net, 2)


def test_twoport_open_zero_capacitor():
    """c = 0 F is an open series path: no coupling, on either formulation."""
    net = Network(
        ports={"f1": PortAtEdge("f1"), "f2": PortAtEdge("f2")},
        branches=[TwoPort(a="f1", b="f2", c=0.0)],
        sources=[Driven(port="f1")],
    )
    assert_formulations_agree(net, 2)


def test_shunt_series_and_parallel():
    net = Network(
        ports={"f": PortAtEdge("f"), "in": PortVirtual("in")},
        branches=[
            TwoPort(a="in", b="f", l=0.2e-6),
            Shunt(port="in", c=40e-12),
            Shunt(port="f", r=1000.0, l=1e-6, c=30e-12, parallel=True),
        ],
        sources=[Driven(port="in")],
    )
    assert_formulations_agree(net, 1)


def test_series_load_terminated_port():
    """Series R load on an undriven second port (terminated-antenna idiom)."""
    net = Network(
        ports={"f": PortAtEdge("f"), "term": PortAtEdge("term")},
        branches=[Load(port="term", r=600.0)],
        sources=[Driven(port="f")],
    )
    assert_formulations_agree(net, 2, check_legacy_voltages=False)


def test_driven_and_loaded_same_port():
    """Centre-loaded driven short dipole: source and series load chain on
    one port (the Thevenin BC the legacy excited path hand-coded)."""
    net = Network(
        ports={"f": PortAtEdge("f")},
        branches=[Load(port="f", r=5.0, l=2e-6)],
        sources=[Driven(port="f")],
    )
    assert_formulations_agree(net, 1, check_legacy_voltages=False)


def test_parallel_trap_load_off_resonance():
    net = Network(
        ports={"f": PortAtEdge("f"), "arm": PortAtEdge("arm")},
        branches=[Load(port="arm", l=1.5e-6, c=30e-12, parallel=True)],
        sources=[Driven(port="f")],
    )
    assert_formulations_agree(net, 2, check_legacy_voltages=False)


def test_everything_at_once():
    """TL + transposed TL + TwoPort + both Shunt modes + both Load modes +
    two sources, seven ports — the BC zoo in one network."""
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
            TL(a="in", b="f1", z0=450.0, length=0.27 * WL),
            TL(a="in", b="n1", z0=300.0, length=0.12 * WL, transposed=True),
            TwoPort(a="n1", b="f2", r=10.0, c=120e-12),
            Shunt(port="in", c=25e-12),
            Shunt(port="n1", r=800.0, l=0.9e-6, c=45e-12, parallel=True),
            Load(port="f3", r=300.0, l=0.5e-6),
            Load(port="f4", l=1.2e-6, c=40e-12, parallel=True),
        ],
        sources=[Driven(port="in"), Driven(port="f3", voltage=0.3 - 0.4j)],
    )
    assert_formulations_agree(net, 4, check_legacy_voltages=False)


@pytest.mark.parametrize("seed", range(5))
def test_lmatch_seeded(seed):
    """The skyloop L-match shape over several synthetic antennas."""
    net = Network(
        ports={"feed": PortAtEdge("feed"), "in": PortVirtual("in")},
        branches=[
            TwoPort(a="in", b="feed", l=0.873e-6),
            Shunt(port="feed", c=59.57e-12),
        ],
        sources=[Driven(port="in")],
    )
    assert_formulations_agree(net, 1, seed=seed)


def test_load_on_virtual_port_rejected_by_mna():
    net = Network(
        ports={"f": PortAtEdge("f"), "v": PortVirtual("v")},
        branches=[TL(a="f", b="v", z0=50.0, length=0.1 * WL), Load(port="v", r=50.0)],
        sources=[Driven(port="f")],
    )
    _, mna = reducers(net, 1)
    with pytest.raises(ValueError, match="virtual port"):
        mna.driven_impedance(synth_y(1, 0), WL)


# ---------------------------------------------------------------------------
# 2. Degenerate elements only MNA can stamp
# ---------------------------------------------------------------------------


def _mna_z(net, n_real, seed=0):
    _, mna = reducers(net, n_real)
    return mna.driven_impedance(synth_y(n_real, seed), WL)[0]


def _series_twoport_z(r=None, l=None, c=None):
    net = Network(
        ports={"f1": PortAtEdge("f1"), "f2": PortAtEdge("f2")},
        branches=[TwoPort(a="f1", b="f2", r=r, l=l, c=c)],
        sources=[Driven(port="f1")],
    )
    return _mna_z(net, 2)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"r": 0.0},  # 0 Ω resistor
        {"l": 0.0},  # 0 H ideal wire
        {},  # all-omitted branch
    ],
    ids=["zero-ohm", "zero-henry", "all-omitted"],
)
def test_ideal_short_twoport_is_finite_and_identifies_nodes(kwargs):
    """A z = 0 series TwoPort is an ideal short: finite result, and exactly
    the small-but-finite limit the legacy formulation could still stamp."""
    z_short = _series_twoport_z(**kwargs)
    assert np.isfinite(z_short)
    z_almost = _series_twoport_z(r=1e-9)
    assert z_short == pytest.approx(z_almost, rel=1e-6)
    # Node identification: the shorted pair behaves as one merged node.
    y = synth_y(2, 0)
    merged = np.array([[y[0, 0] + y[0, 1] + y[1, 0] + y[1, 1]]])
    net = Network(ports={"m": PortAtEdge("m")}, sources=[Driven(port="m")])
    _, mna = reducers(net, 1)
    z_merged = mna.driven_impedance(merged, WL)[0]
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
    _, mna = reducers(net, 2)
    system = mna.apply_branches(y, WL)
    v = mna.resolve_voltages(system)
    assert v[1] == pytest.approx(0.0, abs=1e-15)
    z = mna.impedance_from_y(system)[0]
    assert np.isfinite(z)
    # With v₂ pinned at 0 the short-circuit Y applies directly: Z = 1/Y₁₁.
    z_expect = 1.0 / y[0, 0]
    assert z == pytest.approx(z_expect, rel=1e-9)


def test_inert_lmatchbox_stamped_literally():
    """TwoPort(l=0) + Shunt(c=0) stamped LITERALLY is a pass-through:
    Z_in = Z_ant, with no design-level topology special-casing (the interim
    dodge `skyloop_lmatch.build_network` used on the admittance reducer)."""
    inert = Network(
        ports={"feed": PortAtEdge("feed"), "in": PortVirtual("in")},
        branches=[TwoPort(a="in", b="feed", l=0.0), Shunt(port="feed", c=0.0)],
        sources=[Driven(port="in")],
    )
    bare = Network(ports={"feed": PortAtEdge("feed")}, sources=[Driven(port="feed")])
    y = synth_y(1, 7)
    _, mna_inert = reducers(inert, 1)
    _, mna_bare = reducers(bare, 1)
    z_inert = mna_inert.driven_impedance(y, WL)[0]
    z_bare = mna_bare.driven_impedance(y, WL)[0]
    assert z_inert == pytest.approx(z_bare, rel=1e-12)


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
    _, mna = reducers(net, 2)
    v, eff, p_in = mna.excited_state(y, WL)
    assert np.all(np.isfinite(v)) and np.isfinite(p_in)
    assert eff == pytest.approx(1.0)  # an open burns nothing
    # Open termination at the arm: the arm port floats (I_ext = 0), which is
    # the same network as having no Load branch at all.
    bare = Network(
        ports={"f": PortAtEdge("f"), "arm": PortAtEdge("arm")},
        sources=[Driven(port="f")],
    )
    _, mna_bare = reducers(bare, 2)
    v_bare, _, _ = mna_bare.excited_state(y, WL)
    np.testing.assert_allclose(v, v_bare, rtol=1e-9)
