"""Issue #422: a fixed-complex-Z (frequency-independent) series Load.

A NEC ``LD`` card type 4 is a fixed ``R + jX`` impedance in SERIES with a
segment's current path. Unlike the shunt-to-common ``Admittance`` (issue #416,
which handles the reactive NT / TL-end-shunt cases), this is the series sibling:
it becomes the reducer's group-2 termination, composed with any feed EMF, so on
a *driven+loaded* segment it correctly adds to the driving-point Z where a shunt
would be silently wrong.

Two layers, mirroring test_admittance_branch.py: circuit-theory oracles on a
synthetic antenna Y (fast, no MoM), then a cross-engine MoM check that PyNEC
(native ld_card type 4) and momwire (reducer stamp) agree once the load is in
the solve — including the load-on-the-fed-segment case.
"""

import numpy as np
import pytest

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines import MomwireEngine, PyNECEngine
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import (
    Driven,
    Load,
    Network,
    PortOnWire,
    PortVirtual,
    load_impedance,
)
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer
from momwire import SinusoidalSolver

FREQ_MHZ = 28.0
WL = C_LIGHT / (FREQ_MHZ * 1e6)


def synth_y(n, seed):
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))
    y = 0.004 * (a + a.T) / 2.0
    return y + np.eye(n) * (0.02 + 0.008j)


def reducer(net, n_real):
    real = [n for n, p in net.ports.items() if isinstance(p, PortOnWire)]
    virt = [n for n, p in net.ports.items() if isinstance(p, PortVirtual)]
    port_to_idx = {n: i for i, n in enumerate(real + virt)}
    return NetworkReducer(net, port_to_idx, len(real) + len(virt))


# ---------------------------------------------------------------------------
# 1. Primitive: Load.z is a fixed series impedance
# ---------------------------------------------------------------------------
def test_fixed_z_load_impedance_is_z_at_every_frequency():
    br = Load(port="p", z=30.0 - 40.0j)
    assert load_impedance(br, 2 * np.pi * 10e6) == 30.0 - 40.0j
    assert load_impedance(br, 2 * np.pi * 30e6) == 30.0 - 40.0j


def test_fixed_z_series_load_on_driven_port_adds_to_z():
    """Z_seen = Z_L + 1/Y00 — the load is in series with the feed (a shunt
    would instead give 1/(Y00 + 1/Z_L)). Frequency-independent, so identical
    at two wavelengths despite a reactive Z_L."""
    y = synth_y(1, 5)
    z_l = 60.0 + 25.0j
    net = Network(
        ports={"f": PortOnWire("f")},
        branches=[Load(port="f", z=z_l)],
        sources=[Driven(port="f")],
    )
    red = reducer(net, 1)
    z1 = red.driven_impedance(y, C_LIGHT / 10e6)[0]
    z2 = red.driven_impedance(y, C_LIGHT / 30e6)[0]
    assert z1 == pytest.approx(z_l + 1.0 / y[0, 0], rel=1e-12)
    assert z1 == pytest.approx(z2, rel=1e-12)  # fixed, not jωL-scaled


def test_fixed_z_load_rejects_rlc_legs():
    # z is mutually exclusive with the frequency-dependent R/L/C legs.
    with pytest.raises(ValueError):
        Load(port="p", z=10 + 5j, r=3.0)
    with pytest.raises(ValueError):
        Load(port="p", z=10 + 5j, l=1e-6)
    with pytest.raises(ValueError):
        Load(port="p", z=10 + 5j, parallel=True)


# ---------------------------------------------------------------------------
# 2. nec_import translation of an LD 4 reactive load (issue #422)
# ---------------------------------------------------------------------------
def _dipole7(*cards):
    return (
        "GW 1 7 0 -3.5 10 0 3.5 10 0.001\nGE 0\nEX 0 1 4 0 1 0\n"
        + "".join(c + "\n" for c in cards)
        + "EN\n"
    )


def test_ld4_reactive_translates_to_fixed_z_load():
    """LD 4 tag s0 s1 R X (X != 0) is no longer dropped — it becomes a fixed
    complex-Z series Load, exact at every frequency."""
    deck = parse_nec(_dipole7("LD 4 1 2 2 100 -50"), network=True)
    assert "LD" not in deck.ignored
    assert not any(m == "LD" for m, _ in deck.ignored_detail)
    (ld,) = deck.loads
    assert ld.z == complex(100.0, -50.0)
    assert ld.r is None and ld.l is None and ld.c is None
    (br,) = deck.network().branches
    assert isinstance(br, Load) and br.z == complex(100.0, -50.0)


# ---------------------------------------------------------------------------
# 3. Cross-engine MoM oracle: PyNEC (native ld_card 4) and momwire (reducer)
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


def _mw_z(deck):
    return MomwireEngine(
        _deck_builder(deck), solver=SinusoidalSolver, ground="free"
    ).impedance()[0]


def _cross_engine(deck):
    b = _deck_builder(deck)
    z_pynec = PyNECEngine(b, ground="free").impedance()[0]
    z_mw = MomwireEngine(b, solver=SinusoidalSolver, ground="free").impedance()[0]
    return z_pynec, z_mw


def test_ld4_reactive_on_fed_segment_cross_engine_agrees():
    """The load sits on the FED segment — the case a shunt gets wrong (the
    ideal source pins the node, so a shunt never reaches the driving-point Z).
    As a series Load it adds to Z: Z = Z_bare + (120 − 60j), exactly the
    independent circuit calc, and PyNEC's native ld_card type 4 agrees with
    momwire's reducer stamp. (Both assertions fail if the load is dropped.)"""
    deck = parse_nec(_dipole7("LD 4 1 4 4 120 -60"), network=True)
    z_pynec, z_mw = _cross_engine(deck)
    assert abs(z_pynec - z_mw) / abs(z_mw) < 0.02
    z_bare = _mw_z(parse_nec(_dipole7(), network=True))
    assert z_mw == pytest.approx(z_bare + (120.0 - 60.0j), rel=0.02)


def test_ld4_reactive_on_parasitic_segment_cross_engine_agrees():
    """A reactively-loaded parasite (two-element deck): the load is on an
    undriven segment; both engines agree, and the reactive load measurably
    shifts the driven Z (so the test fails if the load is dropped)."""
    loaded = (
        "GW 1 7 0 -3.5 10 0 3.5 10 0.001\n"
        "GW 2 7 1.5 -3.5 10 1.5 3.5 10 0.001\n"
        "GE 0\n"
        "EX 0 1 4 0 1 0\n"
        "{ld}"
        "EN\n"
    )
    deck = parse_nec(loaded.format(ld="LD 4 2 4 4 80 40\n"), network=True)
    z_pynec, z_mw = _cross_engine(deck)
    assert abs(z_pynec - z_mw) / abs(z_mw) < 0.02
    z_bare = _mw_z(parse_nec(loaded.format(ld=""), network=True))
    assert abs(z_mw - z_bare) > 1.0
