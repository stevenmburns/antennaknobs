"""FloatingBalun — floating-secondary transformer / link-coupling (issue #589).

The differential twin of `Transformer`: a single-ended primary (to the datum,
e.g. a 50 Ω rig) and a genuinely floating differential secondary pair. This is
the one primitive that closes the balanced chain
``Driven → rig → FloatingBalun → balanced tuner → BalancedLine → antenna`` to a
datum-locked source without injecting the common-mode current a balanced feed
exists to avoid.

Circuit-level oracles through the NetworkReducer with a synthetic differential
antenna load: the ideal ratio (Z_primary = Z_secondary / n² exactly), the 1:1
through, winding-resistance and magnetizing-branch loss in the power budget,
the balun low-end rolloff, the balance property (secondary drawn balanced about
ground — no common-mode injection), the build-time CM-floating guard, and an
end-to-end momwire showcase of the Palstar BT1500A balanced-tuner idiom.
"""

from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.network import (
    BalancedLine,
    Driven,
    FloatingBalun,
    Instance,
    Network,
    PortAtEnd,
    PortOnWire,
    PortVirtual,
    Shunt,
    Wire,
)
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer
from antennaknobs.station import balanced_l_tuner

F_MHZ = 10.0
WL = C_LIGHT / (F_MHZ * 1e6)
OMEGA = 2.0 * np.pi * F_MHZ * 1e6


# ---------------------------------------------------------------------------
# reducer harness: primary "rig" driven, floating secondary (al, ar) loaded
# by a synthetic 2×2 antenna Y = diag(2/z_l) — a differential impedance z_l
# with the common mode grounded through the two half-loads, so the floating
# secondary has a common-mode return (a real antenna provides this).
# ---------------------------------------------------------------------------
def _reducer(fb):
    net = Network(
        ports={
            "al": PortOnWire("al"),
            "ar": PortOnWire("ar"),
            "rig": PortVirtual("rig"),
        },
        branches=[fb],
        sources=[Driven("rig", 1 + 0j)],
    )
    return NetworkReducer(net, {"al": 0, "ar": 1, "rig": 2}, 3)


def _y_diff(z_l):
    y = 2.0 / z_l
    return np.array([[y, 0.0], [0.0, y]], dtype=np.complex128)


def _zin(fb, z_l, wl=WL):
    (z,) = _reducer(fb).driven_impedance(_y_diff(z_l), wl)
    return z


def _excited(fb, z_l, wl=WL):
    return _reducer(fb).excited_state(_y_diff(z_l), wl)


def _fb(n, **kw):
    return FloatingBalun(primary="rig", a="al", b="ar", n=n, **kw)


def test_ideal_ratio_is_secondary_over_n_squared():
    z_l = 300.0 - 40.0j
    for n in (1.0, 2.0, 0.5, 3.5):
        z = _zin(_fb(n), z_l)
        np.testing.assert_allclose(z, z_l / (n * n), rtol=1e-12)


def test_unity_ratio_presents_the_balanced_load_unchanged():
    """A 1:1 current balun (the BT1500A input choke) hands the rig the
    balanced differential load impedance untouched."""
    z_l = 73.0 + 42.5j
    np.testing.assert_allclose(_zin(_fb(1.0), z_l), z_l, rtol=1e-12)


def test_lossless_balun_dissipates_nothing():
    _v, eff, p_in, budget = _excited(_fb(0.5), 300.0)
    assert eff == 1.0
    assert p_in > 0
    (label, w) = budget[0]
    assert label == "FloatingBalun rig→(al,ar)"
    assert abs(w) < 1e-12 * p_in


def test_winding_resistance_referred_to_secondary():
    z_l, n, r = 300.0 + 0j, 0.5, 1.2
    z = _zin(_fb(n, r=r), z_l)
    np.testing.assert_allclose(z, (z_l + r) / (n * n), rtol=1e-12)
    v, eff, p_in, budget = _excited(_fb(n, r=r), z_l)
    # secondary current flows through the two grounded half-loads: the antenna
    # power is ½·Re(y)·(|v_al|² + |v_ar|²) with y = 1/(z_l/2)
    y = 2.0 / z_l
    p_ant = 0.5 * np.real(y) * (abs(v[0]) ** 2 + abs(v[1]) ** 2)
    p_network = sum(w for _l, w in budget)
    np.testing.assert_allclose(p_ant + p_network, p_in, rtol=1e-12)
    assert eff < 1.0
    np.testing.assert_allclose(eff, 1.0 - p_network / p_in, rtol=1e-12)


def test_magnetizing_branch_matches_the_parallel_formula():
    z_l, n, lmag = 300.0 + 0j, 1.0, 10e-6
    z = _zin(_fb(n, lmag=lmag), z_l)
    z_ideal = z_l / (n * n)
    z_mag = 1j * OMEGA * lmag
    np.testing.assert_allclose(z, z_ideal * z_mag / (z_ideal + z_mag), rtol=1e-12)


def test_core_loss_rises_toward_low_frequency():
    """Finite-Q magnetizing branch: the classic balun low-end rolloff — the
    (mag) budget entry grows as the frequency drops."""
    fb = _fb(1.0, lmag=10e-6, qlmag=50.0)

    def mag_fraction(f_mhz):
        wl = C_LIGHT / (f_mhz * 1e6)
        _v, _eff, p_in, budget = _excited(fb, 300.0, wl=wl)
        return dict(budget)["FloatingBalun rig→(al,ar) (mag)"] / p_in

    assert mag_fraction(1.8) > 3.0 * mag_fraction(28.0)
    assert mag_fraction(1.8) > 0.0


def test_zero_turns_ratio_is_rejected():
    red = _reducer(_fb(0.0))
    with pytest.raises(ValueError, match="turns ratio n = 0"):
        red.driven_impedance(_y_diff(50.0), WL)


def test_secondary_is_balanced_about_ground():
    """The balance property (acceptance criterion): with an ideal balun into a
    SYMMETRIC differential load, the two secondary legs sit equal-and-opposite
    about the datum (v_al = −v_ar) — zero common-mode voltage, the property
    that bonding a leg to the datum (a `Shunt`) would destroy."""
    v, _eff, _p_in, _budget = _excited(_fb(1.0), 200.0)
    np.testing.assert_allclose(v[0], -v[1], rtol=1e-12)
    # contrast: bond one leg to the datum and the pair is no longer balanced
    net = Network(
        ports={
            "al": PortOnWire("al"),
            "ar": PortOnWire("ar"),
            "rig": PortVirtual("rig"),
        },
        branches=[_fb(1.0), Shunt(port="al", r=1e-6)],
        sources=[Driven("rig", 1 + 0j)],
    )
    red = NetworkReducer(net, {"al": 0, "ar": 1, "rig": 2}, 3)
    vv, *_ = red.excited_state(_y_diff(200.0), WL)
    assert abs(vv[0] + vv[1]) > 0.1 * abs(vv[1])  # common mode no longer ~0


def test_floating_secondary_needs_a_common_mode_return():
    """The secondary pair is CM-floating; a node reachable ONLY through a
    FloatingBalun secondary and a CM-open BalancedLine is rejected at build
    time (the MNA would be singular), naming the offending node."""
    with pytest.raises(ValueError, match="common mode"):
        Network(
            ports={
                "rig": PortVirtual("rig"),
                "al": PortVirtual("al"),
                "ar": PortVirtual("ar"),
                "fa": PortVirtual("fa"),
                "fb": PortVirtual("fb"),
            },
            branches=[
                _fb(1.0),
                # CM-open feedline onward — leaves al/ar/fa/fb CM-floating
                BalancedLine(
                    a1="al", a2="ar", b1="fa", b2="fb", zdiff=450.0, length=1.0
                ),
            ],
            sources=[Driven("rig", 1 + 0j)],
        )


def test_zcomm_feedline_grounds_the_secondary_common_mode():
    """The same chain with a zcomm-carrying feedline is a valid common-mode
    return, so the network builds and solves."""
    net = Network(
        ports={
            "rig": PortVirtual("rig"),
            "al": PortVirtual("al"),
            "ar": PortVirtual("ar"),
            "fa": PortOnWire("fa"),
            "fb": PortOnWire("fb"),
        },
        branches=[
            _fb(1.0),
            BalancedLine(
                a1="al",
                a2="ar",
                b1="fa",
                b2="fb",
                zdiff=450.0,
                length=1.0,
                zcomm=300.0,
            ),  # fmt: skip
        ],
        sources=[Driven("rig", 1 + 0j)],
    )
    red = NetworkReducer(net, {"fa": 0, "fb": 1, "rig": 2, "al": 3, "ar": 4}, 5)
    (z,) = red.driven_impedance(_y_diff(600.0), WL)
    assert np.isfinite(z.real) and np.isfinite(z.imag)


# ---------------------------------------------------------------------------
# end-to-end: the Palstar BT1500A balanced-tuner idiom on a real doublet
# (issue #589 acceptance criterion) — a driven-port Z and a far-field pattern
# through Driven → rig → FloatingBalun → split-leg L-network → BalancedLine
# → PortAtEnd × 2 → doublet.
# ---------------------------------------------------------------------------
FREQ = 14.1
WLA = 299.792458 / FREQ
ARM = 0.24 * WLA
SPACING = 0.05


class _BalancedTunerDoublet(AntennaBuilder):
    """A doublet fed, through a balanced L-network tuner with a 1:1 floating
    balun at the rig, over a common-mode-carrying ladder line."""

    default_params = MappingProxyType(
        {
            "design_freq": FREQ,
            "freq": FREQ,
            "l_uH": 8.0,
            "c_pF": 120.0,
            "blen": 0.18 * WLA,
        }
    )

    def build_wires(self):
        s, z = SPACING, 0.5 * WLA
        return [
            Wire((0, 0, z), (0, -ARM, z), name="armA"),
            Wire((s, 0, z), (s, ARM, z), name="armB"),
        ]

    def build_network(self):
        return Network(
            ports={
                "ta": PortAtEnd("armA", end="p0"),
                "tb": PortAtEnd("armB", end="p0"),
                "rig": PortVirtual("rig"),
                "liL": PortVirtual("liL"),
                "liR": PortVirtual("liR"),
            },
            branches=[
                Instance(
                    "tuner",
                    balanced_l_tuner(l_uH=self.l_uH, c_pF=self.c_pF, n=1.0),
                    rig="rig",
                    outL="liL",
                    outR="liR",
                ),  # fmt: skip
                BalancedLine(
                    a1="liL",
                    a2="liR",
                    b1="ta",
                    b2="tb",
                    zdiff=450.0,
                    length=self.blen,
                    vf=0.91,
                    zcomm=250.0,
                ),  # fmt: skip
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )


@pytest.mark.antenna_computation_check
def test_bt1500a_idiom_solves_end_to_end():
    """The whole balanced chain reaches the datum-locked rig source: a finite
    driven-port impedance and a physical far-field pattern, with the tuner's
    single-ended balun primary the only datum reference in the RF path."""
    from antennaknobs.engines.momwire import MomwireEngine

    b = _BalancedTunerDoublet(dict(_BalancedTunerDoublet.default_params))
    eng = MomwireEngine(b, ground=None)
    (z,) = eng.impedance()
    assert np.isfinite(z.real) and np.isfinite(z.imag)
    assert z.real > 0  # a passive driving-point resistance at the rig

    ff = eng.far_field(n_theta=45, n_phi=180, del_theta=2, del_phi=2)
    peak = max(max(ring) for ring in ff.rings)
    assert 0.0 < peak < 5.0  # a horizontal doublet in free space, ~2 dBi class


@pytest.mark.antenna_computation_check
def test_tuning_the_balanced_l_network_moves_the_rig_impedance():
    """The roller L and differential C actually tune: sweeping the cap changes
    the driven-point impedance at the rig, so the L-network is live (not an
    inert pass-through) through the floating balun."""
    from antennaknobs.engines.momwire import MomwireEngine

    def zin(c_pF):
        b = _BalancedTunerDoublet(dict(_BalancedTunerDoublet.default_params, c_pF=c_pF))
        return complex(MomwireEngine(b, ground=None).impedance()[0])

    z_lo, z_hi = zin(60.0), zin(220.0)
    assert abs(z_hi - z_lo) / abs(z_lo) > 0.05  # the cap visibly retunes the rig Z
