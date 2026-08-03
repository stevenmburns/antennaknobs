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

import numpy as np
import pytest

from antennaknobs.network import (
    BalancedLine,
    Driven,
    FloatingBalun,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
)
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer

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


def test_the_primary_is_pinned_by_the_constitutive_row_not_a_datum_path():
    """A `FloatingBalun` primary counts as common-mode determinate, and the
    reason is the constitutive row ``v_a − v_b − n·v_p = r·j`` rather than any
    path to the datum (issue #660).

    The obvious-looking reason — the magnetizing shunt ``G[p, p] += y_mag`` —
    is stamped only when the element declares a magnetizing branch, and the
    ideal balun the catalog uses declares none. So an ideal balun has NO datum
    path at its primary, and the network must still build.
    """
    from antennaknobs.network_reduce import magnetizing_impedance

    ideal = _fb(1.0)
    assert magnetizing_impedance(ideal, OMEGA) is None  # no shunt to the datum

    def net(branches):
        return Network(
            ports={
                "p": PortVirtual("p"),  # balun primary AND a CM-open terminal
                "q": PortVirtual("q"),
                "w1": PortOnWire("w1"),
                "w2": PortOnWire("w2"),
                "s1": PortOnWire("s1"),
                "s2": PortOnWire("s2"),
            },
            branches=branches,
            sources=[Driven("q", 1 + 0j)],
        )

    line = BalancedLine(a1="p", a2="q", b1="w1", b2="w2", zdiff=450.0, length=1.0)
    # "p" is reachable only through the CM-open line and the balun primary, so
    # the primary rule is the only thing making it determinate.
    net([line, FloatingBalun(primary="p", a="s1", b="s2", n=1.0)])
    # ...and without the balun, the same node is rejected — which is what
    # makes this a test of the rule rather than of the rest of the network.
    with pytest.raises(ValueError, match=r"'p'"):
        net([line])


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
# end-to-end: the shipped `wire.doublet_balanced_tuner` catalog showcase
# (issue #589 acceptance criterion) — the Palstar BT1500A balanced-tuner idiom
# on a real doublet, through Driven → rig → FloatingBalun → split-leg L-network
# → BalancedLine → PortAtEnd × 2 → doublet.
# ---------------------------------------------------------------------------
def _showcase_builder(**over):
    from antennaknobs.cli import list_builtin_designs
    from antennaknobs.designs.wire.doublet_balanced_tuner import Builder

    assert "wire.doublet_balanced_tuner" in set(list_builtin_designs())
    return Builder(dict(Builder.default_params, **over))


@pytest.mark.antenna_computation_check
def test_doublet_balanced_tuner_showcase():
    """The shipped catalog design: the stock ~0.72 λ doublet on ladder line
    matches near 50 Ω at the rig, the ideal 1:1 balun's ratio row burns
    nothing while the roller-coil legs carry the tuner's loss, and the whole
    balanced chain reaches the datum-locked source with a physical pattern."""
    from antennaknobs.engines.momwire import MomwireEngine

    eng = MomwireEngine(_showcase_builder(), ground=None)
    (z,) = eng.impedance()
    gamma = abs((z - 50.0) / (z + 50.0))
    assert (1 + gamma) / (1 - gamma) < 1.3  # matched at the rig

    eng.current_distribution()
    fr = {
        label: max(0.0, w) / eng._excited_p_in for label, w in eng._excited_power_budget
    }
    # the ideal FloatingBalun ratio row dissipates nothing...
    assert fr["tuner: FloatingBalun rig→(sL,sR)"] < 1e-9
    # ...while the split roller-coil legs carry the tuner's (finite-Q) loss
    assert fr["tuner: TwoPort sL→liL"] > 0.0
    assert fr["tuner: TwoPort sR→liR"] > 0.0

    ff = eng.far_field(n_theta=45, n_phi=180, del_theta=2, del_phi=2)
    peak = max(max(ring) for ring in ff.rings)
    assert 0.0 < peak < 5.0  # a horizontal doublet in free space, ~2 dBi class


@pytest.mark.antenna_computation_check
def test_balanced_tuner_cap_retunes_the_rig_impedance():
    """The roller L and differential C actually tune: sweeping the cap changes
    the driven-point impedance at the rig, so the L-network is live (not an
    inert pass-through) through the floating balun."""
    from antennaknobs.engines.momwire import MomwireEngine

    def zin(c_pF):
        return complex(
            MomwireEngine(_showcase_builder(tuner_c_pF=c_pF), ground=None).impedance()[
                0
            ]
        )

    z_lo, z_hi = zin(40.0), zin(160.0)
    assert abs(z_hi - z_lo) / abs(z_lo) > 0.05  # the cap visibly retunes the rig Z
