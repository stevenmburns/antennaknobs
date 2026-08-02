"""The tapped-winding auto-transformer (issue #594).

`Transformer` is an *isolation* transformer — two windings coupled only by the
core. An autotransformer has one winding with a tap, so the sections are
galvanically connected and the common section carries the *difference* of the
input and output currents. That difference is constitutive, so the element is
modelled as two mutually coupled inductors rather than as an ideal ratio, and
the ratio has to *fall out* of the L/M matrix. These tests check that it does,
and that the coupled pair does not quietly break the power budget.
"""

import math

import numpy as np
import pytest

from antennaknobs.network import (
    Autotransformer,
    Driven,
    Instance,
    Network,
    PortVirtual,
    Shunt,
)
from antennaknobs.network_reduce import NetworkReducer
from antennaknobs.station import autotransformer, autotransformer_ratio

FREQ = 14.0
OMEGA = 2.0 * math.pi * FREQ * 1e6
WAVELENGTH = 299_792_458.0 / (FREQ * 1e6)
NO_ANTENNA = np.zeros((0, 0), dtype=complex)  # pure-circuit tests: no wires


def build(lower_uH, upper_uH, k, *, rload=None, ql=None, drive="tap"):
    branches = [
        Instance(
            "xf",
            autotransformer(lower_uH, upper_uH, k=k, ql=ql),
            tap="tap",
            top="top",
        )
    ]
    if rload is not None:
        load_at = "top" if drive == "tap" else "tap"
        branches.append(Shunt(port=load_at, r=rload, parallel=True))
    net = Network(
        ports={"tap": PortVirtual("tap"), "top": PortVirtual("top")},
        branches=branches,
        sources=[Driven(port=drive)],
    )
    return NetworkReducer(net, {"tap": 0, "top": 1}, 2)


def z_in(*args, **kw):
    red = build(*args, **kw)
    return complex(red.impedance_from_y(red.apply_branches(NO_ANTENNA, WAVELENGTH))[0])


def budget_of(*args, **kw):
    """(efficiency, p_in, {label: watts}) — every probed branch."""
    red = build(*args, **kw)
    _v, eff, p_in, rows = red.excited_state(NO_ANTENNA, WAVELENGTH)
    return eff, p_in, dict(rows)


def winding_rows(rows):
    """Just the two coupled sections — the load Shunt is a probed branch too."""
    return {k: v for k, v in rows.items() if "Autotransformer" in k}


# ---------------------------------------------------------------------------
# the constitutive model, checked where it has a closed form
# ---------------------------------------------------------------------------
def test_uncoupled_open_winding_is_just_its_inductance():
    """k = 0, top open: the tap sees the lower section alone. Exact."""
    z = z_in(2.0, 8.0, 0.0)
    assert z.real == pytest.approx(0.0, abs=1e-9)
    assert z.imag == pytest.approx(OMEGA * 2.0e-6, rel=1e-12)


def test_uncoupled_loaded_is_the_analytic_parallel_combination():
    """k = 0 decouples the sections, leaving lower ∥ (upper + load) — a
    two-element network with an exact answer, so any sign or factor error in
    the stamp shows up here rather than as a plausible-looking number."""
    z = z_in(2.0, 8.0, 0.0, rload=200.0)
    z_lower = 1j * OMEGA * 2.0e-6
    z_branch = 1j * OMEGA * 8.0e-6 + 200.0
    expect = 1.0 / (1.0 / z_lower + 1.0 / z_branch)
    assert z == pytest.approx(expect, rel=1e-12)


def test_the_ideal_ratio_falls_out_of_the_coupled_pair():
    """The acceptance criterion: at k → 1 with the magnetizing reactance far
    above the load, the tap sees load / n² with n = 1 + √(upper/lower) —
    reproduced, not asserted anywhere in the stamp."""
    n = autotransformer_ratio(2.0, 8.0)
    assert n == pytest.approx(3.0)  # 1 + √4
    z = z_in(2.0 * 10_000, 8.0 * 10_000, 1.0, rload=200.0)
    assert z.real == pytest.approx(200.0 / n**2, rel=1e-4)
    assert abs(z.imag) < 1e-3 * z.real  # magnetizing reactance is out of the way


@pytest.mark.parametrize(
    "lower,upper,n", [(1.0, 1.0, 2.0), (2.0, 8.0, 3.0), (4.0, 4.0, 2.0)]
)
def test_several_taps_hit_their_analytic_ratios(lower, upper, n):
    assert autotransformer_ratio(lower, upper) == pytest.approx(n)
    z = z_in(lower * 10_000, upper * 10_000, 1.0, rload=100.0)
    assert z.real == pytest.approx(100.0 / n**2, rel=1e-3)


def test_driving_the_top_steps_the_other_way():
    """An autotransformer is symmetric: feed the top, and the tap load looks
    n² *larger* rather than smaller."""
    n = autotransformer_ratio(2.0, 8.0)
    z = z_in(2.0 * 10_000, 8.0 * 10_000, 1.0, rload=20.0, drive="top")
    assert z.real == pytest.approx(20.0 * n**2, rel=1e-3)


def test_imperfect_coupling_adds_series_leakage_reactance():
    """Real coils are not perfectly coupled, and the leakage that produces is
    the reason this is a coupled-inductor model instead of a ratio."""
    ideal = z_in(2.0 * 100, 8.0 * 100, 1.0, rload=200.0)
    loose = z_in(2.0 * 100, 8.0 * 100, 0.9, rload=200.0)
    assert abs(ideal.imag) < 1.0
    assert loose.imag > 100.0  # inductive, and large — leakage ∝ (1 − k²)·L
    # Passive network, so the reactance must be inductive at every coupling.
    for k in (0.5, 0.8, 0.95, 0.99):
        assert z_in(2.0 * 100, 8.0 * 100, k, rload=200.0).imag > 0.0


# ---------------------------------------------------------------------------
# power — the part a coupled pair could silently break
# ---------------------------------------------------------------------------
def test_a_lossless_winding_dissipates_exactly_nothing():
    """The subtle one. A generic branch probe reads ½Re((v_a − v_b)·j*), which
    for coupled windings also picks up the *reactive* power the two sections
    exchange — real-valued, sloshing back and forth, and not loss. One row
    would read positive and the other negative. The resistive-only probe must
    read exactly zero on both.
    """
    eff, p_in, rows = budget_of(2.0, 8.0, 0.98, rload=200.0)
    windings = winding_rows(rows)
    assert len(windings) == 2  # both sections itemised
    for label, watts in windings.items():
        assert watts == 0.0, (label, watts)
    assert p_in > 0.0
    # The only sink is the load, so efficiency is "not burned in the network".
    assert eff < 1.0


def test_finite_q_dissipates_and_itemises():
    _eff, p_in, rows = budget_of(2.0, 8.0, 0.98, rload=200.0, ql=50.0)
    windings = winding_rows(rows)
    assert len(windings) == 2
    assert all(w > 0.0 for w in windings.values())
    # Less than the input, and less than the load gets — a matching coil that
    # burned most of the power would be a broken model, not a lossy one.
    assert sum(windings.values()) < 0.5 * p_in
    # (`efficiency` is "fraction reaching the antenna", and this rig has no
    # antenna — every watt lands in a probed branch — so it reads 0 here.)


def test_power_balances_against_the_load():
    """Input power = load dissipation + winding dissipation, to machine
    precision. Coupled branch currents are exactly where that would go wrong.
    """
    for ql in (None, 30.0):
        _eff, p_in, rows = budget_of(2.0, 8.0, 0.98, rload=200.0, ql=ql)
        # No antenna in this circuit, so every watt in must be accounted for by
        # a probed branch: the two windings plus the load.
        assert p_in == pytest.approx(sum(rows.values()), rel=1e-9)


def test_lower_q_burns_more():
    _e1, _p1, rows_hi = budget_of(2.0, 8.0, 0.98, rload=200.0, ql=200.0)
    _e2, _p2, rows_lo = budget_of(2.0, 8.0, 0.98, rload=200.0, ql=20.0)
    assert sum(winding_rows(rows_lo).values()) > sum(winding_rows(rows_hi).values())


def test_both_sections_are_named_in_the_budget():
    _eff, _p, rows = budget_of(2.0, 8.0, 0.98, rload=200.0, ql=50.0)
    labels = " ".join(winding_rows(rows))
    assert "lower" in labels and "upper" in labels
    assert "Autotransformer" in labels


# ---------------------------------------------------------------------------
# refusals
# ---------------------------------------------------------------------------
def test_overcoupling_is_refused():
    """k > 1 means M² > L₁L₂: the inductance matrix stops being positive
    semi-definite and the pair can deliver more energy than it stores. SimSmith
    allows it and calls it non-physical; we refuse, because the power budget
    claims to balance."""
    with pytest.raises(ValueError, match="0 ≤ k ≤ 1") as exc:
        z_in(2.0, 8.0, 1.5)
    assert "power budget" in str(exc.value)


def test_negative_coupling_is_refused():
    with pytest.raises(ValueError, match="0 ≤ k ≤ 1"):
        z_in(2.0, 8.0, -0.2)


def test_nonpositive_inductances_are_refused():
    with pytest.raises(ValueError, match="positive"):
        z_in(0.0, 8.0, 0.98)
    with pytest.raises(ValueError, match="positive"):
        autotransformer_ratio(2.0, 0.0)


# ---------------------------------------------------------------------------
# it composes like every other station box
# ---------------------------------------------------------------------------
def test_the_factory_declares_the_documented_formals():
    box = autotransformer(2.0, 8.0)
    assert box.ports == ("tap", "top")
    (br,) = box.branches
    assert isinstance(br, Autotransformer)
    assert br.l_lower == pytest.approx(2e-6) and br.l_upper == pytest.approx(8e-6)


def test_it_matches_a_real_antenna_on_both_engines():
    """End to end: a 22 Ω vertical stepped up toward 50 Ω by a tapped coil."""
    from antennaknobs.designs.verticals.vertical import Builder as V
    from antennaknobs.engines import MomwireEngine
    from antennaknobs.network import Driven as D
    from antennaknobs.network import PortOnWire, as_wire

    class Tapped(V):
        def build_wires(self):
            return [
                w._replace(ex=None, name="feed") if w.ex is not None else w
                for w in map(as_wire, super().build_wires())
            ]

        def build_network(self):
            # The ANTENNA sits at the tap and the rig at the top, so the
            # 22 Ω feedpoint is stepped UP by n² toward 50 Ω:
            # n = 1 + √(1.05/4.0) ≈ 1.51, n² ≈ 2.3.
            return Network(
                ports={"feed": PortOnWire("feed"), "rig": PortVirtual("rig")},
                branches=[
                    Instance(
                        "xf",
                        autotransformer(4.0, 1.05, k=0.99),
                        tap="feed",
                        top="rig",
                    )
                ],
                sources=[D(port="rig")],
            )

    z = complex(MomwireEngine(Tapped(), ground=None).impedance()[0])
    assert np.isfinite(z)
    # A step-up from the 22 Ω feedpoint: the rig side sees ~n² more.
    assert 35.0 < z.real < 70.0
