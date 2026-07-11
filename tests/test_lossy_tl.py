"""Lossy transmission lines (issue #297).

These tests exercise the complex-γ TL stamp and the cable catalog at the
NetworkReducer level with a synthetic one-port antenna Y — no MoM solve, so
they are pure circuit oracles:

  - the lossless limit reproduces the historical stamp exactly;
  - a matched lossy line dissipates exactly the k1·√f + k2·f matched loss;
  - a mismatched lossy line's input impedance matches the analytic
    Zin = Z0(Z_L + Z0 tanh γl)/(Z0 + Z_L tanh γl) wave solution, and its
    total loss exceeds matched loss (the SWR penalty emerges from the
    circuit, not a formula);
  - loss regularizes the half-wave singularity.
"""

import numpy as np
import pytest

from antennaknobs.network import CABLES, TL, Driven, Network, PortAtEdge, PortVirtual
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer, tl_admittance_2x2

F_MHZ = 10.0
WL = C_LIGHT / (F_MHZ * 1e6)
FT100 = 30.48  # 100 ft in meters


def _rig_fed_network(tl):
    """Virtual "rig" port driven through `tl` into the real "ant" port."""
    net = Network(
        ports={"ant": PortAtEdge("ant"), "rig": PortVirtual("rig")},
        branches=[tl],
        sources=[Driven("rig", 1 + 0j)],
    )
    return NetworkReducer(net, {"ant": 0, "rig": 1}, 2)


def _gamma(tl, wavelength):
    """The same α + jβ the stamp derives, for analytic cross-checks."""
    f_mhz = C_LIGHT / wavelength / 1e6
    db_per_m = (tl.k1 * np.sqrt(f_mhz) + tl.k2 * f_mhz) / (100.0 * 0.3048)
    alpha = db_per_m * np.log(10.0) / 20.0
    beta = 2.0 * np.pi / (tl.vf * wavelength)
    return alpha + 1j * beta


def _powers(reducer, z_ant):
    """(p_in at the rig, power delivered into the antenna resistance)."""
    y_real = np.array([[1.0 / z_ant]], dtype=np.complex128)
    v, _eff, p_in, *_ = reducer.excited_state(y_real, WL)
    p_ant = 0.5 * abs(v[0]) ** 2 * np.real(1.0 / z_ant)
    return p_in, p_ant


def test_lossless_limit_is_exact():
    for z0, length in [(50.0, 3.7), (300.0, 0.18 * WL), (600.0, 21.0)]:
        theta = 2.0 * np.pi * length / WL
        s, c = np.sin(theta), np.cos(theta)
        legacy = (1.0 / (1j * z0 * s)) * np.array([[c, -1.0], [-1.0, c]])
        got = tl_admittance_2x2(z0, length, WL)
        np.testing.assert_allclose(got, legacy, rtol=1e-12)


def test_matched_line_dissipates_exactly_the_matched_loss():
    tl = TL("rig", "ant", z0=50.0, length=FT100, vf=0.66, k1=0.40, k2=0.008)
    reducer = _rig_fed_network(tl)
    p_in, p_ant = _powers(reducer, 50.0)
    loss_db = 10.0 * np.log10(p_in / p_ant)
    expected_db = tl.k1 * np.sqrt(F_MHZ) + tl.k2 * F_MHZ  # per 100 ft, matched
    np.testing.assert_allclose(loss_db, expected_db, rtol=1e-9)
    # Matched termination: the rig sees Z0 regardless of line length.
    (zin,) = reducer.driven_impedance(np.array([[1.0 / 50.0]]), WL)
    np.testing.assert_allclose(zin, 50.0 + 0j, rtol=1e-9)


def test_mismatched_zin_matches_the_wave_solution():
    tl = TL("rig", "ant", z0=50.0, length=FT100, vf=0.80, k1=0.27, k2=0.0055)
    z_l = 200.0 + 0j
    reducer = _rig_fed_network(tl)
    (zin,) = reducer.driven_impedance(np.array([[1.0 / z_l]]), WL)
    t = np.tanh(_gamma(tl, WL) * tl.length)
    zin_analytic = tl.z0 * (z_l + tl.z0 * t) / (tl.z0 + z_l * t)
    np.testing.assert_allclose(zin, zin_analytic, rtol=1e-9)


def test_swr_penalty_emerges_from_the_circuit():
    tl = TL("rig", "ant", z0=50.0, length=FT100, vf=0.80, k1=0.27, k2=0.0055)
    matched_db = tl.k1 * np.sqrt(F_MHZ) + tl.k2 * F_MHZ
    p_in, p_ant = _powers(_rig_fed_network(tl), z_ant=200.0)  # SWR 4:1
    total_db = 10.0 * np.log10(p_in / p_ant)
    assert total_db > matched_db  # mismatch always adds loss
    assert total_db < 4.0 * matched_db  # ...but stays in a sane range at SWR 4


def test_loss_regularizes_the_halfwave_singularity():
    vf = 0.66
    halfwave = vf * WL / 2.0
    with pytest.raises(ValueError, match="singular"):
        tl_admittance_2x2(50.0, halfwave, WL, vf=vf)
    y = tl_admittance_2x2(50.0, halfwave, WL, vf=vf, k1=0.40)
    assert np.all(np.isfinite(y))
    # A lossy half-wave line still ~repeats its load impedance.
    tl = TL("rig", "ant", z0=50.0, length=halfwave, vf=vf, k1=0.40)
    (zin,) = _rig_fed_network(tl).driven_impedance(np.array([[1.0 / 120.0]]), WL)
    assert abs(zin - 120.0) < 15.0


def test_velocity_factor_scales_electrical_length():
    got = tl_admittance_2x2(50.0, 10.0, WL, vf=0.66)
    equivalent = tl_admittance_2x2(50.0, 10.0 / 0.66, WL, vf=1.0)
    np.testing.assert_allclose(got, equivalent, rtol=1e-12)


def test_transposed_flips_only_the_off_diagonal():
    kw = dict(vf=0.80, k1=0.27, k2=0.0055)
    y = tl_admittance_2x2(50.0, FT100, WL, **kw)
    y_t = tl_admittance_2x2(50.0, FT100, WL, transposed=True, **kw)
    np.testing.assert_allclose(np.diag(y_t), np.diag(y), rtol=1e-15)
    np.testing.assert_allclose(y_t[0, 1], -y[0, 1], rtol=1e-15)
    np.testing.assert_allclose(y_t[1, 0], -y[1, 0], rtol=1e-15)


def test_from_cable_catalog():
    tl = TL.from_cable("RG-8X", "rig", "ant", FT100)
    c = CABLES["RG-8X"]
    assert (tl.z0, tl.vf, tl.k1, tl.k2) == (c.z0, c.vf, c.k1, c.k2)
    assert (tl.a, tl.b, tl.length) == ("rig", "ant", FT100)
    with pytest.raises(KeyError, match="RG-8X"):  # message lists availables
        TL.from_cable("RG-9000", "rig", "ant", FT100)
