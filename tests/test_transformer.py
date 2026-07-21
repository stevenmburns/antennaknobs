"""Transformer/balun network element (issue #301).

Circuit-level oracles through the NetworkReducer with a synthetic one-port
antenna Y: the ideal ratio (Z_in = n²·Z_L exactly), the degenerate
through-connection at n = 1, winding-resistance and magnetizing-branch loss
landing in the power budget (#299), and the low-frequency insertion-loss
rolloff a real balun shows.
"""

import numpy as np
import pytest

from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, Transformer
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer

F_MHZ = 10.0
WL = C_LIGHT / (F_MHZ * 1e6)
OMEGA = 2.0 * np.pi * F_MHZ * 1e6


def _reducer(xfmr):
    net = Network(
        ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
        branches=[xfmr],
        sources=[Driven("rig", 1 + 0j)],
    )
    return NetworkReducer(net, {"ant": 0, "rig": 1}, 2)


def _zin(xfmr, z_l, wl=WL):
    red = _reducer(xfmr)
    (z,) = red.driven_impedance(np.array([[1.0 / z_l]], dtype=np.complex128), wl)
    return z


def _excited(xfmr, z_l, wl=WL):
    red = _reducer(xfmr)
    return red.excited_state(np.array([[1.0 / z_l]], dtype=np.complex128), wl)


def test_ideal_ratio_is_exactly_n_squared():
    z_l = 300.0 - 40.0j
    for n in (2.0, 0.5, 3.5):
        z = _zin(Transformer(a="rig", b="ant", n=n), z_l)
        np.testing.assert_allclose(z, n * n * z_l, rtol=1e-12)


def test_unity_ratio_is_a_through_connection():
    z_l = 73.0 + 42.5j
    np.testing.assert_allclose(
        _zin(Transformer(a="rig", b="ant", n=1.0), z_l), z_l, rtol=1e-12
    )


def test_lossless_transformer_dissipates_nothing():
    _v, eff, p_in, budget = _excited(Transformer(a="rig", b="ant", n=0.5), 300.0)
    assert eff == 1.0
    assert p_in > 0
    (label, w) = budget[0]
    assert label == "Transformer rig→ant"
    assert abs(w) < 1e-12 * p_in


def test_winding_resistance_adds_referred_to_side_a():
    z_l, n, r = 300.0 + 0j, 0.5, 1.2
    z = _zin(Transformer(a="rig", b="ant", n=n, r=r), z_l)
    np.testing.assert_allclose(z, n * n * z_l + r, rtol=1e-12)
    v, eff, p_in, budget = _excited(Transformer(a="rig", b="ant", n=n, r=r), z_l)
    p_ant = 0.5 * abs(v[0]) ** 2 * np.real(1.0 / z_l)
    p_network = sum(w for _l, w in budget)
    np.testing.assert_allclose(p_ant + p_network, p_in, rtol=1e-12)
    assert eff < 1.0
    np.testing.assert_allclose(eff, 1.0 - p_network / p_in, rtol=1e-12)


def test_magnetizing_branch_matches_the_parallel_formula():
    z_l, n, lmag = 300.0 + 0j, 0.5, 10e-6
    z = _zin(Transformer(a="rig", b="ant", n=n, lmag=lmag), z_l)
    z_ideal = n * n * z_l
    z_mag = 1j * OMEGA * lmag
    np.testing.assert_allclose(z, z_ideal * z_mag / (z_ideal + z_mag), rtol=1e-12)


def test_core_loss_rises_toward_low_frequency():
    """Finite-Q magnetizing branch: the classic balun low-end rolloff —
    the (mag) budget entry grows as the frequency drops."""
    xf = Transformer(a="rig", b="ant", n=0.5, lmag=10e-6, qlmag=50.0)

    def mag_fraction(f_mhz):
        wl = C_LIGHT / (f_mhz * 1e6)
        _v, _eff, p_in, budget = _excited(xf, 300.0, wl=wl)
        return dict(budget)["Transformer rig→ant (mag)"] / p_in

    assert mag_fraction(1.8) > 3.0 * mag_fraction(28.0)
    assert mag_fraction(1.8) > 0.0


def test_zero_turns_ratio_is_rejected():
    red = _reducer(Transformer(a="rig", b="ant", n=0.0))
    with pytest.raises(ValueError, match="turns ratio n = 0"):
        red.driven_impedance(np.array([[1.0 / 50.0]], dtype=np.complex128), WL)


def test_folded_invvee_balun_showcase():
    """The showcase design: ~218 Ω folded inv-vee feed stepped to ~55 Ω by
    the 4:1 balun, onto 50 Ω coax — SWR at the rig near 1, the transformer's
    ideal-ratio row lossless, and both engines agreeing."""
    from antennaknobs.cli import list_builtin_designs
    from antennaknobs.designs.dipoles.folded_invvee_balun import Builder
    from antennaknobs.engines import MomwireEngine
    from momwire import SinusoidalSolver

    assert "dipoles.folded_invvee_balun" in set(list_builtin_designs())
    eng = MomwireEngine(Builder(), ground=None, solver=SinusoidalSolver)
    (z,) = eng.impedance()
    gamma = abs((z - 50.0) / (z + 50.0))
    assert (1 + gamma) / (1 - gamma) < 1.3  # matched at the rig
    eng.current_distribution()
    fr = {
        label: max(0.0, w) / eng._excited_p_in for label, w in eng._excited_power_budget
    }
    assert fr["balun: Transformer bal→feed"] < 1e-9  # ideal ratio burns nothing
    assert 0.0 < fr["balun: Transformer bal→feed (mag)"] < 0.01  # tiny at 28 MHz
    assert fr["TL rig→bal"] > 0.25  # RG-8X at 10 m, the familiar ~31%

    pynec = pytest.importorskip("antennaknobs.engines.pynec")
    zn = pynec.PyNECEngine(Builder(), ground=None).impedance()[0]
    assert abs(z - zn) / abs(z) < 0.01
