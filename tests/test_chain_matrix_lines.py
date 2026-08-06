"""Transmission lines stamped as chain matrices (issue #746, increment 2).

A line's 2×2 nodal admittance is 1/(Z0 sinh γl) × …, a ratio with a pole: at a
lossless k·λ/2 the line HAS no admittance matrix, and the reducer used to
refuse the whole solve there. Its chain (ABCD) matrix is entire — [[±1, 0],
[0, ±1]] at exactly that point, which is what a through-line is — so the
reducer now carries two auxiliary currents per line and stamps

    v_a − A·v_b − B·j₂ = 0
    j₁  − C·v_b − D·j₂ = 0

instead. These tests pin the three things that buys: exactness AT the pole,
a well-conditioned system there, and bit-for-bit-equivalent answers
everywhere the admittance form was valid.
"""

import numpy as np
import pytest

from antennaknobs.network import (
    TL,
    BalancedLine,
    Driven,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
)
from antennaknobs.network_reduce import (
    C_LIGHT,
    NetworkReducer,
    SingularNetworkError,
    balanced_admittance_4x4,
    tl_abcd,
    tl_admittance_2x2,
)

F_MHZ = 10.0
WL = C_LIGHT / (F_MHZ * 1e6)


def _rig(tl):
    """Virtual "rig" port driven through `tl` into the real "ant" port."""
    net = Network(
        ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
        branches=[tl],
        sources=[Driven("rig", 1 + 0j)],
    )
    return NetworkReducer(net, {"ant": 0, "rig": 1}, 2)


def _rcond(system):
    """The equilibrated reciprocal condition the solve itself measures."""
    from scipy.linalg.lapack import zgesvx

    return float(zgesvx(system.A, system.rhs.reshape(-1, 1))[8])


def _y1(z):
    return np.array([[1.0 / z]], dtype=np.complex128)


# ---------------------------------------------------------------------------
# 1. the chain matrix itself
# ---------------------------------------------------------------------------
def test_abcd_and_the_admittance_stamp_describe_the_same_line():
    """Where both exist they are the same 2-port: y11 = D/B, y12 = −1/B,
    y22 = A/B — and AD − BC = 1, the reciprocity the pair of them encodes."""
    for z0, length, vf, k1 in [
        (50.0, 3.7, 1.0, 0.0),
        (300.0, 0.18 * WL, 0.91, 0.0),
        (75.0, 12.0, 0.66, 0.31),
    ]:
        a, b, c, d = tl_abcd(z0, length, WL, vf=vf, k1=k1)
        y = tl_admittance_2x2(z0, length, WL, vf=vf, k1=k1)
        assert a * d - b * c == pytest.approx(1.0, rel=1e-14)
        assert y[0, 0] == pytest.approx(d / b, rel=1e-12)
        assert y[0, 1] == pytest.approx(-1.0 / b, rel=1e-12)
        assert y[1, 1] == pytest.approx(a / b, rel=1e-12)


def test_the_half_wave_chain_matrix_is_the_identity_up_to_sign():
    """The point of the whole exercise: the description the admittance form
    cannot spell is the simplest one there is."""
    a, b, c, d = tl_abcd(50.0, WL / 2.0, WL)
    assert (a, d) == pytest.approx((-1.0, -1.0), abs=1e-15)
    assert abs(b) < 1e-13 and abs(c) < 1e-15


# ---------------------------------------------------------------------------
# 2. the acceptance criterion: exact AT the pole
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("k", [1, 2, 3])
@pytest.mark.parametrize("z_load", [120.0 + 0j, 12.0 - 90.0j, 3000.0 + 1.0j])
def test_a_lossless_half_wave_line_repeats_its_load_exactly(k, z_load):
    """A k·λ/2 line is an impedance repeater. Measured worst case across this
    grid: 8.5e-14 relative — the analytic answer, not an approximation to it.
    Under the admittance stamp this raised."""
    for vf in (1.0, 0.66):
        tl = TL("rig", "ant", z0=50.0, length=k * vf * WL / 2.0, vf=vf)
        z = _rig(tl).driven_impedance(_y1(z_load), WL)[0]
        assert abs(z - z_load) / abs(z_load) < 1e-12


def test_the_half_wave_solve_is_well_conditioned_not_merely_survivable():
    """Equilibrated rcond at the exact pole: 0.1667, five orders above
    RCOND_SUSPECT. The answer is not being scraped off a near-singularity —
    there is no singularity."""
    tl = TL("rig", "ant", z0=50.0, length=WL / 2.0)
    red = _rig(tl)
    assert _rcond(red.apply_branches(_y1(120.0 + 0j), WL)) > 0.1


def test_the_admittance_form_still_refuses_and_says_which_form_to_ask_for():
    """`tl_admittance_2x2` keeps its guard — the admittance genuinely does not
    exist there — but the message now points at the form that does."""
    with pytest.raises(SingularNetworkError, match="tl_abcd"):
        tl_admittance_2x2(50.0, WL / 2.0, WL)


def test_a_zero_length_line_is_an_ideal_short():
    """The other end of the same story: the admittance form's other pole."""
    z = _rig(TL("rig", "ant", z0=50.0, length=0.0)).driven_impedance(
        _y1(73.0 + 42.0j), WL
    )[0]
    assert z == pytest.approx(73.0 + 42.0j, rel=1e-12)


# ---------------------------------------------------------------------------
# 3. no drift where the old stamp was valid
# ---------------------------------------------------------------------------
def test_agrees_with_the_admittance_stamp_wherever_that_existed():
    """The regression this change could plausibly cause. 600 random lines
    (z0, length, vf, loss, transposition) against the nodal solve of the
    admittance stamp: worst relative |ΔZ| measured 1.4e-12."""
    rng = np.random.default_rng(0)
    worst, n = 0.0, 0
    for _ in range(600):
        z0 = float(rng.uniform(35.0, 700.0))
        length = float(rng.uniform(0.02, 3.0)) * WL
        vf = float(rng.uniform(0.6, 1.0))
        k1 = float(rng.choice([0.0, 0.0, 0.3]))
        transposed = bool(rng.integers(0, 2))
        z_load = complex(rng.uniform(5.0, 500.0), rng.uniform(-500.0, 500.0))
        try:
            y_tl = tl_admittance_2x2(
                z0, length, WL, transposed=transposed, vf=vf, k1=k1
            )
        except SingularNetworkError:
            continue  # exactly the samples the old stamp could not answer
        y_full = y_tl.copy()
        y_full[0, 0] += 1.0 / z_load
        v = np.array([-y_full[0, 1] / y_full[0, 0], 1.0 + 0j])
        z_old = v[1] / (y_full @ v)[1]
        tl = TL("rig", "ant", z0=z0, length=length, vf=vf, k1=k1, transposed=transposed)
        z_new = _rig(tl).driven_impedance(_y1(z_load), WL)[0]
        worst = max(worst, abs(z_new - z_old) / abs(z_old))
        n += 1
    assert n > 500
    assert worst < 1e-9, worst


def test_transposition_is_a_negated_port_weight():
    """A half-twist inverts port B's polarity: the driving-point impedance is
    blind to it (the load is the same load), the far-end voltage is not."""
    kw = dict(z0=450.0, length=0.31 * WL)
    z_load = 220.0 - 60.0j
    straight, crossed = TL("rig", "ant", **kw), TL("rig", "ant", transposed=True, **kw)
    zs = _rig(straight).driven_impedance(_y1(z_load), WL)[0]
    zc = _rig(crossed).driven_impedance(_y1(z_load), WL)[0]
    assert zc == pytest.approx(zs, rel=1e-12)
    red_s, red_c = _rig(straight), _rig(crossed)
    v_s = red_s.resolve_voltages(red_s.apply_branches(_y1(z_load), WL))
    v_c = red_c.resolve_voltages(red_c.apply_branches(_y1(z_load), WL))
    assert v_c[0] == pytest.approx(-v_s[0], rel=1e-12)


# ---------------------------------------------------------------------------
# 4. the power budget across the new element
# ---------------------------------------------------------------------------
def test_a_lossy_half_wave_line_reports_its_attenuation_in_the_budget():
    """The 2-current probe reads ½Re(v_a·j₁* − v_b·j₂*): in minus out. At the
    half-wave point, which the budget could not previously reach at all."""
    tl = TL("rig", "ant", z0=50.0, length=WL / 2.0, k1=0.40, k2=0.008)
    _v, eff, p_in, budget = _rig(tl).excited_state(_y1(50.0 + 0j), WL)
    ((label, watts),) = budget
    assert label == "TL rig→ant"
    matched_db = tl.k1 * np.sqrt(F_MHZ) + tl.k2 * F_MHZ
    # 100 ft of catalog loss over a λ/2 (15 m) section, matched at both ends.
    expect_db = matched_db * (tl.length / (100.0 * 0.3048))
    assert 10.0 * np.log10(p_in / (p_in - watts)) == pytest.approx(expect_db, rel=1e-9)
    assert eff == pytest.approx(1.0 - watts / p_in, rel=1e-12)


def test_a_lossless_line_still_reports_no_dissipation():
    tl = TL("rig", "ant", z0=450.0, length=0.37 * WL)
    _v, eff, p_in, budget = _rig(tl).excited_state(_y1(180.0 + 40.0j), WL)
    assert abs(budget[0][1]) < 1e-9 * p_in
    assert eff == 1.0


# ---------------------------------------------------------------------------
# 5. BalancedLine: the same expansion, one 2-port per mode
# ---------------------------------------------------------------------------
def _grounded_pair(bl):
    """Conductor 2 bonded to the datum at both ends by ideal shorts, which is
    the wiring under which a balanced pair IS a coax (test_balanced_line's
    `y4 → y2` collapse, driven end to end)."""
    net = Network(
        ports={
            "a1": PortOnWire("a1"),
            "a2": PortVirtual("a2"),
            "b1": PortVirtual("b1"),
            "b2": PortVirtual("b2"),
        },
        branches=[bl, Shunt("a2", r=0.0), Shunt("b2", r=0.0)],
        sources=[Driven("b1", 1 + 0j)],
    )
    return NetworkReducer(net, {"a1": 0, "a2": 1, "b1": 2, "b2": 3}, 4)


@pytest.mark.parametrize("k", [1, 2])
def test_a_balanced_half_wave_pair_repeats_its_load_exactly(k):
    bl = BalancedLine("a1", "a2", "b1", "b2", zdiff=450.0, length=k * WL / 2.0)
    z_load = 180.0 + 40.0j
    z = _grounded_pair(bl).driven_impedance(_y1(z_load), WL)[0]
    assert abs(z - z_load) / abs(z_load) < 1e-12


def test_balanced_stamp_agrees_with_the_4x4_wherever_that_existed():
    """Same regression check as the coax, through the pair incidence."""
    rng = np.random.default_rng(1)
    worst, n = 0.0, 0
    for _ in range(200):
        zdiff = float(rng.uniform(200.0, 700.0))
        length = float(rng.uniform(0.02, 1.5)) * WL
        vf = float(rng.uniform(0.8, 1.0))
        k1 = float(rng.choice([0.0, 0.0, 0.05]))
        z_load = complex(rng.uniform(50.0, 600.0), rng.uniform(-300.0, 300.0))
        bl = BalancedLine(
            "a1", "a2", "b1", "b2", zdiff=zdiff, length=length, vf=vf, k1=k1
        )
        try:
            y4 = balanced_admittance_4x4(zdiff, length, WL, vf=vf, k1=k1)
        except SingularNetworkError:
            continue
        # Grounding conductor 2 at both ends drops rows/cols a2, b2.
        y_full = y4[np.ix_([0, 2], [0, 2])].copy()
        y_full[0, 0] += 1.0 / z_load
        v = np.array([-y_full[0, 1] / y_full[0, 0], 1.0 + 0j])
        z_old = v[1] / (y_full @ v)[1]
        z_new = _grounded_pair(bl).driven_impedance(_y1(z_load), WL)[0]
        worst = max(worst, abs(z_new - z_old) / abs(z_old))
        n += 1
    assert n > 150
    assert worst < 1e-9, worst


def test_zcomm_none_keeps_the_common_mode_structurally_open():
    """The load-bearing property of a differential-only pair: it forces
    I(a1) = −I(a2) at each end, so a common-mode drive sees nothing at all.

    In the 4×4 admittance form that was visible as rank 2. In the chain-matrix
    form it is the port weights: the differential leg's incidence is (+1, −1)
    at each end, so the branch's contribution to the two node rows cancels
    identically. Asserted on the assembled matrix because that is the claim —
    a topological zero, not a small number.
    """
    bl_open = BalancedLine("a1", "a2", "b1", "b2", zdiff=450.0, length=0.3 * WL)
    bl_cm = BalancedLine(
        "a1", "a2", "b1", "b2", zdiff=450.0, length=0.3 * WL, zcomm=200.0
    )
    for bl, cm_open in ((bl_open, True), (bl_cm, False)):
        system = _grounded_pair(bl).apply_branches(_y1(300.0), WL)
        cols = system.A[:, 4:]  # every Group-2 current column
        pair_a = cols[0] + cols[1]  # rows a1 + a2 — the common-mode direction
        pair_b = cols[2] + cols[3]
        # The two 0 Ω shunts also touch a2 and b2; look only at the line's own
        # two (or four) currents, which are stamped first.
        n_line = 2 if cm_open else 4
        assert np.all(pair_a[:n_line] == 0) == cm_open
        assert np.all(pair_b[:n_line] == 0) == cm_open
