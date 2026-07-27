"""BalancedLine — the differential two-conductor transmission-line element
(issue #575).

A `BalancedLine` is a purely-differential 4-terminal element: port A =
(a1, a2), port B = (b1, b2), characterised by a single differential impedance
`zdiff`. Its stamp is `tl_admittance_2x2(zdiff, …)` incidence-expanded to a
4×4 Group-1 admittance block — each 2×2 entry `y` becomes the block
`y·[[1,−1],[−1,1]]` over the terminal pair, i.e. `kron(Y_2x2, [[1,-1],[-1,1]])`.
The common mode is structurally open (the block is rank-2 by construction).

These tests all have exact expected answers; the physics validation against
real structures (isolation oracle + end-to-end TL Sterba) is issue #576.
"""

import numpy as np
import pytest

from antennaknobs.network import (
    BalancedLine,
    Branch,
    Driven,
    Network,
    PortOnWire,
    PortVirtual,
    _branch_port_refs,
)
from antennaknobs.network_reduce import (
    C_LIGHT,
    NetworkReducer,
    balanced_admittance_4x4,
    tl_admittance_2x2,
)

FREQ_MHZ = 28.0
WL = C_LIGHT / (FREQ_MHZ * 1e6)


def synth_y(n, seed):
    """Reciprocal, diagonally-dominant complex antenna-ish Y (mirrors the
    test_network_mna helper) so the combined system is well conditioned."""
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))
    y = 0.004 * (a + a.T) / 2.0
    return y + np.eye(n) * (0.02 + 0.008j)


def nodal_reference(y_full, driven):
    """Bare nodal reduction: driven nodes pinned at their EMF, every other
    node floating with I_ext = 0, currents read as Y·V. Valid because the
    BalancedLine is a pure finite-admittance stamp."""
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
# 1. The stamp helper — exact-answer structural properties
# ---------------------------------------------------------------------------


def test_balanced_stamp_is_kron_of_tl_and_diff_incidence():
    """The 4×4 is exactly the differential 2×2 tensored with the pair
    incidence [[1,−1],[−1,1]] — the definition, to machine precision."""
    y2 = tl_admittance_2x2(450.0, 0.3 * WL, WL)
    y4 = balanced_admittance_4x4(450.0, 0.3 * WL, WL)
    expected = np.kron(y2, np.array([[1.0, -1.0], [-1.0, 1.0]]))
    np.testing.assert_allclose(y4, expected, rtol=0, atol=1e-18)


def test_degenerate_case_collapses_to_tl_exactly():
    """Acceptance criterion: grounding conductor 2 at both ends (a2 = b2 =
    datum → drop those rows/cols) collapses the 4×4 to tl_admittance_2x2 to
    MACHINE precision, not an approximate check. Rows/cols (a1, b1) = (0, 2)."""
    y2 = tl_admittance_2x2(450.0, 0.3 * WL, WL)
    y4 = balanced_admittance_4x4(450.0, 0.3 * WL, WL)
    collapsed = y4[np.ix_([0, 2], [0, 2])]
    np.testing.assert_array_equal(collapsed, y2)


def test_reciprocity_symmetric():
    """A reciprocal line: the 4×4 is symmetric (not merely Hermitian)."""
    y4 = balanced_admittance_4x4(300.0, 0.37 * WL, WL, vf=0.91, k1=0.05)
    np.testing.assert_allclose(y4, y4.T, rtol=0, atol=1e-18)


def test_common_mode_open_and_rank_two():
    """Differential-only structure: each pair's common mode draws no current
    (Y·[1,1,0,0] = 0 and Y·[0,0,1,1] = 0), so the block has rank 2."""
    y4 = balanced_admittance_4x4(450.0, 0.3 * WL, WL)
    np.testing.assert_allclose(y4 @ np.array([1, 1, 0, 0]), 0, atol=1e-12)
    np.testing.assert_allclose(y4 @ np.array([0, 0, 1, 1]), 0, atol=1e-12)
    np.testing.assert_allclose(y4 @ np.array([1, 1, 1, 1]), 0, atol=1e-12)
    assert np.linalg.matrix_rank(y4, tol=1e-9) == 2


def test_lossless_conserves_power():
    """A lossless line (k1 = k2 = 0) dissipates nothing: ½·Re(v†·Y·v) = 0 for
    any excitation, because the lossless admittance is purely imaginary."""
    y4 = balanced_admittance_4x4(450.0, 0.3 * WL, WL)
    rng = np.random.default_rng(7)
    v = rng.normal(size=4) + 1j * rng.normal(size=4)
    p = 0.5 * np.real(np.conj(v) @ (y4 @ v))
    assert p == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------------------
# 2. Singularity guard + loss regularisation (inherited from tl_admittance_2x2)
# ---------------------------------------------------------------------------


def test_lossless_half_wave_raises():
    """A lossless line at exactly λ/2 inherits tl_admittance_2x2's singularity
    guard (sinh γl → 0) and raises rather than returning garbage."""
    with pytest.raises(ValueError, match="singular"):
        balanced_admittance_4x4(450.0, 0.5 * WL, WL)


def test_loss_regularizes_exact_half_wave():
    """Real open-wire loss (k1 > 0) regularises the exactly-λ/2 riser: the
    stamp is finite and well-conditioned, and it dissipates positive power."""
    y4 = balanced_admittance_4x4(450.0, 0.5 * WL, WL, k1=0.02)
    assert np.all(np.isfinite(y4))
    rng = np.random.default_rng(3)
    v = rng.normal(size=4) + 1j * rng.normal(size=4)
    p = 0.5 * np.real(np.conj(v) @ (y4 @ v))
    assert p > 0.0


# ---------------------------------------------------------------------------
# 3. Dataclass + Network wiring
# ---------------------------------------------------------------------------


def test_balanced_line_in_branch_union():
    """BalancedLine is a member of the Branch discriminated union."""
    assert BalancedLine in Branch.__args__


def test_branch_port_refs_returns_four_terminals():
    """All four terminals are reported (used by validation and rename)."""
    bl = BalancedLine("a1", "a2", "b1", "b2", zdiff=450.0, length=0.3 * WL)
    assert _branch_port_refs(bl) == ("a1", "a2", "b1", "b2")


def test_unknown_terminal_rejected():
    """__post_init__ validates every terminal against the port dict."""
    with pytest.raises(ValueError, match="unknown port"):
        Network(
            ports={"a1": PortOnWire("a1"), "a2": PortOnWire("a2")},
            branches=[
                BalancedLine("a1", "a2", "b1", "b2", zdiff=450.0, length=0.3 * WL)
            ],
            sources=[Driven(port="a1")],
        )


def test_common_mode_floating_rejected_at_build_time():
    """Acceptance criterion: a node attached ONLY via BalancedLine terminals
    is common-mode floating (the stamp contributes nothing to its common
    mode). Raise a clear error at build/validate time, naming the node, rather
    than letting MNA go singular at solve time."""
    with pytest.raises(ValueError, match="common mode"):
        Network(
            ports={
                "a1": PortOnWire("a1"),
                "a2": PortOnWire("a2"),
                "v1": PortVirtual("v1"),
                "v2": PortVirtual("v2"),
            },
            branches=[
                BalancedLine("a1", "a2", "v1", "v2", zdiff=450.0, length=0.3 * WL)
            ],
            sources=[Driven(port="a1")],
        )


def test_all_real_terminals_are_common_mode_determinate():
    """Four real PortOnWire terminals each carry an antenna-Y row, so the
    common mode is determinate and no error is raised."""
    net = Network(
        ports={n: PortOnWire(n) for n in ("a1", "a2", "b1", "b2")},
        branches=[BalancedLine("a1", "a2", "b1", "b2", zdiff=450.0, length=0.3 * WL)],
        sources=[Driven(port="a1")],
    )
    assert len(net.branches) == 1


# ---------------------------------------------------------------------------
# 4. Reducer stamp — matches an independent nodal oracle
# ---------------------------------------------------------------------------


def test_reducer_stamp_matches_nodal_reference():
    """The BalancedLine, stamped as a Group-1 block through NetworkReducer,
    reproduces the bare nodal reduction: build y_full = antenna Y + the 4×4
    block by hand and compare driven-port impedances."""
    net = Network(
        ports={n: PortOnWire(n) for n in ("a1", "a2", "b1", "b2")},
        branches=[BalancedLine("a1", "a2", "b1", "b2", zdiff=450.0, length=0.3 * WL)],
        sources=[Driven(port="a1", voltage=1 + 0j), Driven(port="b1", voltage=0.5j)],
    )
    port_to_idx = {n: i for i, n in enumerate(("a1", "a2", "b1", "b2"))}
    red = NetworkReducer(net, port_to_idx, 4)

    y = synth_y(4, 11)
    y_full = y.copy()
    y_full += balanced_admittance_4x4(450.0, 0.3 * WL, WL)  # ports already 0..3
    v_ref, i_ref = nodal_reference(y_full, {0: 1 + 0j, 2: 0.5j})

    z = red.driven_impedance(y, WL)
    np.testing.assert_allclose(z, [v_ref[0] / i_ref[0], v_ref[2] / i_ref[2]], rtol=1e-9)


def test_crossover_is_wiring_not_a_flag():
    """No `transposed` flag: a half-twist is wiring port B as (b2, b1). The
    crossed stamp equals the straight stamp with its B-pair rows/cols swapped."""
    straight = balanced_admittance_4x4(450.0, 0.3 * WL, WL)
    # Swap b1 <-> b2 (indices 2, 3): the physical crossover.
    swap = [0, 1, 3, 2]
    crossed = straight[np.ix_(swap, swap)]
    y2 = tl_admittance_2x2(450.0, 0.3 * WL, WL)
    # Crossed differential incidence flips the transfer sign, exactly what
    # wiring b as (b2, b1) does.
    expected = np.kron(y2, np.array([[1.0, -1.0], [-1.0, 1.0]]))[np.ix_(swap, swap)]
    np.testing.assert_allclose(crossed, expected, atol=1e-18)


# ---------------------------------------------------------------------------
# 5. Cross-engine MoM oracle: PyNEC and momwire agree on the differential stamp
# ---------------------------------------------------------------------------


class _BalancedFourPortBuilder:
    """Four parallel port wires with mutual coupling, a BalancedLine stamped
    across all four terminals, one driven. Not a physically-meaningful antenna
    — a correctness fixture: same geometry + same network on both engines must
    agree, proving the differential stamp is a pure (engine-agnostic) reducer
    block on the antenna Y."""

    def build_wires(self):
        from antennaknobs.network import Wire

        length = 0.15 * WL
        ys = {"a1": 0.0, "a2": 0.6, "b1": 1.2, "b2": 1.8}
        return [
            Wire((0.0, y, 0.0), (length, y, 0.0), 3, name=name)
            for name, y in ys.items()
        ]

    def build_network(self):
        return Network(
            ports={n: PortOnWire(n) for n in ("a1", "a2", "b1", "b2")},
            branches=[
                BalancedLine("a1", "a2", "b1", "b2", zdiff=450.0, length=0.3 * WL)
            ],
            sources=[Driven(port="a1")],
        )


def test_balanced_line_cross_engine_agrees():
    """BalancedLine is a shared-NetworkReducer stamp with no native NEC card
    (like TL / Shunt / Transformer / Admittance), so it runs on PyNEC too:
    nec2++'s antenna Y and momwire's sinusoidal-basis Y, both reduced with the
    same 4×4 differential block, return the same driving-point impedance to
    MoM-basis tolerance. nec2++ is thus an independent oracle for the stamp."""
    from antennaknobs import AntennaBuilder, WireSpec
    from antennaknobs.engines import MomwireEngine, PyNECEngine
    from momwire import SinusoidalSolver

    class B(_BalancedFourPortBuilder, AntennaBuilder):
        default_params = {"freq": FREQ_MHZ}

        def build_wire_material(self):
            return WireSpec(radius=0.001)

    builder = B()
    z_mw = MomwireEngine(builder, solver=SinusoidalSolver, ground="free").impedance()[0]
    z_pynec = PyNECEngine(builder, ground="free").impedance()[0]
    assert abs(z_pynec - z_mw) / abs(z_mw) < 0.02


# ---------------------------------------------------------------------------
# 6. The optional common-mode path (zcomm, issue #576)
# ---------------------------------------------------------------------------


def test_zcomm_stamp_is_dm_plus_cm_kron():
    """With zcomm, the 4×4 is exactly the differential kron plus the CM 2×2
    tensored with ¼·ones — the even/odd decomposition, to machine precision."""
    y_dm = tl_admittance_2x2(450.0, 0.3 * WL, WL)
    y_cm = tl_admittance_2x2(200.0, 0.3 * WL, WL)
    y4 = balanced_admittance_4x4(450.0, 0.3 * WL, WL, zcomm=200.0)
    expected = np.kron(y_dm, np.array([[1.0, -1.0], [-1.0, 1.0]])) + np.kron(
        y_cm, np.full((2, 2), 0.25)
    )
    np.testing.assert_allclose(y4, expected, rtol=0, atol=1e-18)


def test_zcomm_never_perturbs_differential_behaviour():
    """The ¼·ones incidence annihilates differential vectors, so the response
    to any pure-differential excitation is IDENTICAL with and without zcomm —
    no cross-terms between the modes."""
    y_plain = balanced_admittance_4x4(450.0, 0.3 * WL, WL)
    y_cm = balanced_admittance_4x4(450.0, 0.3 * WL, WL, zcomm=200.0)
    for v in (np.array([1, -1, 0, 0]), np.array([0, 0, 1, -1])):
        np.testing.assert_allclose(y_cm @ v, y_plain @ v, rtol=0, atol=1e-18)


def test_zcomm_common_mode_is_the_cm_tl():
    """Driving a pair with a pure common vector reproduces the CM 2×2 TL over
    (total current, average voltage): the pair current splits equally and the
    totals equal tl_admittance_2x2(zcomm)'s column."""
    y_cm = tl_admittance_2x2(200.0, 0.3 * WL, WL)
    y4 = balanced_admittance_4x4(450.0, 0.3 * WL, WL, zcomm=200.0)
    i = y4 @ np.array([1.0, 1.0, 0.0, 0.0])  # V_cm(A) = 1, V_cm(B) = 0
    assert i[0] == pytest.approx(i[1])  # splits equally
    assert i[2] == pytest.approx(i[3])
    assert i[0] + i[1] == pytest.approx(y_cm[0, 0])
    assert i[2] + i[3] == pytest.approx(y_cm[1, 0])


def test_zcomm_stamp_is_full_rank():
    """DM (rank 2) plus its orthogonal CM complement (rank 2) span all four
    terminal directions: the stamp is rank 4 — no floating mode left."""
    y4 = balanced_admittance_4x4(450.0, 0.3 * WL, WL, zcomm=200.0)
    assert np.linalg.matrix_rank(y4, tol=1e-9) == 4


def test_zcomm_crossover_flips_only_the_differential_sign():
    """Swapping (b1, b2) — the physical crossover — leaves the CM block
    untouched: the swapped-minus-straight difference is identical with and
    without zcomm."""
    swap = [0, 1, 3, 2]
    plain = balanced_admittance_4x4(450.0, 0.3 * WL, WL)
    with_cm = balanced_admittance_4x4(450.0, 0.3 * WL, WL, zcomm=200.0)
    d_plain = plain[np.ix_(swap, swap)] - plain
    d_cm = with_cm[np.ix_(swap, swap)] - with_cm
    np.testing.assert_allclose(d_cm, d_plain, rtol=0, atol=1e-18)


def test_zcomm_terminals_count_as_cm_determinate():
    """The exact network test_common_mode_floating_rejected_at_build_time
    rejects becomes valid once the BalancedLine carries a zcomm: its CM block
    is itself the return, so the virtual far end is determinate."""
    net = Network(
        ports={
            "a1": PortOnWire("a1"),
            "a2": PortOnWire("a2"),
            "v1": PortVirtual("v1"),
            "v2": PortVirtual("v2"),
        },
        branches=[
            BalancedLine(
                "a1", "a2", "v1", "v2", zdiff=450.0, length=0.3 * WL, zcomm=200.0
            )
        ],
        sources=[Driven(port="a1")],
    )
    assert len(net.branches) == 1


def test_reducer_passes_zcomm_through():
    """NetworkReducer stamps the zcomm-augmented block: same nodal-reference
    oracle as the differential case, with the CM block in y_full."""
    net = Network(
        ports={n: PortOnWire(n) for n in ("a1", "a2", "b1", "b2")},
        branches=[
            BalancedLine(
                "a1", "a2", "b1", "b2", zdiff=450.0, length=0.3 * WL, zcomm=200.0
            )
        ],
        sources=[Driven(port="a1", voltage=1 + 0j), Driven(port="b1", voltage=0.5j)],
    )
    port_to_idx = {n: i for i, n in enumerate(("a1", "a2", "b1", "b2"))}
    red = NetworkReducer(net, port_to_idx, 4)

    y = synth_y(4, 11)
    y_full = y.copy()
    y_full += balanced_admittance_4x4(450.0, 0.3 * WL, WL, zcomm=200.0)
    v_ref, i_ref = nodal_reference(y_full, {0: 1 + 0j, 2: 0.5j})

    z = red.driven_impedance(y, WL)
    np.testing.assert_allclose(z, [v_ref[0] / i_ref[0], v_ref[2] / i_ref[2]], rtol=1e-9)
