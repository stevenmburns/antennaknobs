"""Issue #416: a general fixed complex-Y (frequency-independent) branch.

`Admittance` stamps a fixed short-circuit admittance matrix verbatim into the
`NetworkReducer` (group-1 node-admittance block) — the branch a reactive NT
card, a reactive TL end-shunt, or a fixed-jX load reduce to. Unlike
Load/TwoPort/Shunt, whose reactance scales with ω, the Y is used as-is at every
frequency.

Two layers, mirroring test_network_mna.py: circuit-theory oracles on a
synthetic antenna Y (fast, no MoM), then a cross-engine MoM check that PyNEC and
momwire agree once the branch is in the solve.
"""

import numpy as np
import pytest

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines import MomwireEngine, PyNECEngine
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import (
    Admittance,
    Driven,
    Network,
    PortOnWire,
    PortVirtual,
)
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer
from momwire import SinusoidalSolver

FREQ_MHZ = 28.0
WL = C_LIGHT / (FREQ_MHZ * 1e6)


def synth_y(n, seed):
    """Reciprocal, diagonally-dominant complex antenna Y (well conditioned)."""
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))
    y = 0.004 * (a + a.T) / 2.0
    return y + np.eye(n) * (0.02 + 0.008j)


def reducer(net, n_real):
    real = [n for n, p in net.ports.items() if isinstance(p, PortOnWire)]
    virt = [n for n, p in net.ports.items() if isinstance(p, PortVirtual)]
    port_to_idx = {n: i for i, n in enumerate(real + virt)}
    return NetworkReducer(net, port_to_idx, len(real) + len(virt))


def nodal_reference(y_full, driven):
    """Bare nodal reduction: driven nodes pinned at their EMF, the rest
    floating (I_ext = 0), currents I = Y·V. Exact when every element is a
    finite admittance stamp — which `Admittance` is."""
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
# 1. Circuit-theory oracles (synthetic antenna Y)
# ---------------------------------------------------------------------------
def test_admittance_2port_matches_augmented_nodal_solve():
    """A driven port + a fixed complex 2-port Admittance to a floating port:
    since the branch is a pure group-1 stamp, the exact reference is the bare
    nodal solve of the augmented admittance (antenna Y + the branch Y-block)."""
    y = synth_y(2, 11)
    yadm = np.array([[0.02 + 0.01j, -0.01 + 0.002j], [-0.01 + 0.002j, 0.015 - 0.004j]])
    net = Network(
        ports={"a": PortOnWire("a"), "b": PortOnWire("b")},
        branches=[Admittance(ports=("a", "b"), y=tuple(map(tuple, yadm)))],
        sources=[Driven(port="a")],
    )
    z = reducer(net, 2).driven_impedance(y, WL)[0]
    v, i = nodal_reference(y + yadm, {0: 1 + 0j})
    assert z == pytest.approx(v[0] / i[0], rel=1e-9)


def test_admittance_1port_is_fixed_shunt_to_common():
    """A 1-port Admittance at the driven port adds its y to the node: the
    fixed-admittance sibling of Shunt. Z = 1/(Y₀₀ + y)."""
    y = synth_y(1, 3)
    ysh = 0.003 - 0.002j
    net = Network(
        ports={"a": PortOnWire("a")},
        branches=[Admittance(ports=("a",), y=((ysh,),))],
        sources=[Driven(port="a")],
    )
    z = reducer(net, 1).driven_impedance(y, WL)[0]
    assert z == pytest.approx(1.0 / (y[0, 0] + ysh), rel=1e-12)


def test_admittance_is_frequency_independent():
    """The Y is stamped as-is at every frequency — unlike a Shunt capacitor
    whose jωC scales. With a fixed synthetic antenna Y, a pure-susceptance
    Admittance gives the identical driving-point impedance at two wavelengths."""
    y = synth_y(1, 7)
    ysh = 1j * 0.004  # fixed susceptance
    net = Network(
        ports={"a": PortOnWire("a")},
        branches=[Admittance(ports=("a",), y=((ysh,),))],
        sources=[Driven(port="a")],
    )
    red = reducer(net, 1)
    z1 = red.driven_impedance(y, C_LIGHT / 10e6)[0]
    z2 = red.driven_impedance(y, C_LIGHT / 30e6)[0]
    assert z1 == pytest.approx(z2, rel=1e-12)
    assert z1 == pytest.approx(1.0 / (y[0, 0] + ysh), rel=1e-12)


def test_admittance_rejects_shape_mismatch():
    with pytest.raises((ValueError, AssertionError)):
        Admittance(ports=("a", "b"), y=((0.01,),))  # 2 ports, 1×1 matrix


# ---------------------------------------------------------------------------
# 2. nec_import translation of a reactive NT card (issue #416)
# ---------------------------------------------------------------------------
_REACTIVE_NT_DECK = """\
GW 1 5 0 -1 0 0 1 0 0.001
GW 2 5 1 -1 0 1 1 0 0.001
GE 0
EX 0 1 3 0 1 0
NT 1 3 2 3 0.02 0.01 -0.01 0 0.015 0
EN
"""


def test_reactive_nt_translates_to_admittance():
    """An NT card with susceptance is no longer dropped — it becomes an
    Admittance carrying the full complex short-circuit Y (Y21 = Y12)."""
    deck = parse_nec(_REACTIVE_NT_DECK, network=True)
    assert "NT" not in deck.ignored
    assert not any(m == "NT" for m, _ in deck.ignored_detail)
    adm = [b for b in deck.network().branches if isinstance(b, Admittance)]
    assert len(adm) == 1
    np.testing.assert_allclose(
        np.array(adm[0].y, dtype=complex),
        [[0.02 + 0.01j, -0.01 + 0j], [-0.01 + 0j, 0.015 + 0j]],
    )


# ---------------------------------------------------------------------------
# 3. Cross-engine MoM oracle: PyNEC and momwire agree with the branch in-solve
# ---------------------------------------------------------------------------
def _deck_builder(deck, freq=FREQ_MHZ):
    class B(AntennaBuilder):
        default_params = {"freq": freq}

        def build_wires(self):
            return deck.wire_tuples()

        def build_network(self):
            return deck.network()

        def build_wire_material(self):
            return WireSpec(radius=deck.dominant_radius())

    return B()


def test_reactive_nt_cross_engine_agrees():
    """The reactive 2-port is stamped through the shared NetworkReducer on both
    engines, so PyNEC (nec2++ antenna Y) and momwire (sinusoidal Y) return the
    same driving-point impedance to the MoM-basis tolerance."""
    deck = parse_nec(_REACTIVE_NT_DECK, network=True)
    builder = _deck_builder(deck)
    z_pynec = PyNECEngine(builder, ground="free").impedance()[0]
    z_mw = MomwireEngine(builder, solver=SinusoidalSolver, ground="free").impedance()[0]
    assert abs(z_pynec - z_mw) / abs(z_mw) < 0.02
