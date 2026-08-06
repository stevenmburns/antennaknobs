"""Γ-referenced driven ports (issue #746, increment 3).

The reducer used to pin a driven port at its EMF: an IDEAL generator, Z_s = 0.
That is what made a short across the port unsolvable — not the short, which is
an ordinary circuit, but the source model, which cannot deliver a finite
current into 0 Ω. Stamping the EMF behind a reference impedance instead costs
nothing (Z = E/j − z_ref is algebraically the same answer) and buys three
things at once: a system that stays conditioned at the short, a native Γ, and
a finite +1 where Z is reported as ∞.

The far-field path deliberately keeps the ideal generator — its port voltages
ARE the excitation and p_in is defined at the source terminals — so this file
also pins that the two solves stay separate.
"""

import numpy as np
import pytest

from antennaknobs.network import (
    TL,
    Driven,
    DrivenCurrent,
    Load,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
)
from antennaknobs.network_reduce import (
    C_LIGHT,
    RCOND_SINGULAR,
    NetworkReducer,
    SingularNetworkError,
    Z_REF_DEFAULT,
)

F_MHZ = 14.0
WL = C_LIGHT / (F_MHZ * 1e6)


def _reducer(net):
    real = [n for n, p in net.ports.items() if isinstance(p, PortOnWire)]
    virt = [n for n, p in net.ports.items() if isinstance(p, PortVirtual)]
    idx = {n: i for i, n in enumerate(real + virt)}
    return NetworkReducer(net, idx, len(idx))


def _bare(z_ant, branches=(), sources=None, n1=False):
    """One real port carrying `z_ant`, driven, plus whatever branches.

    ``n1`` adds a spare virtual node for branches that need a far end; it is
    left out otherwise, because a node nothing touches is exactly the
    genuinely-singular topology these tests must not accidentally build.
    """
    ports = {"feed": PortOnWire("feed")}
    if n1:
        ports["n1"] = PortVirtual("n1")
    net = Network(
        ports=ports,
        branches=list(branches),
        sources=list(sources or [Driven(port="feed")]),
    )
    return _reducer(net), np.array([[1.0 / z_ant]], dtype=np.complex128)


def _rcond(system):
    from scipy.linalg.lapack import zgesvx

    return float(zgesvx(system.A, system.rhs.reshape(-1, 1))[8])


# ---------------------------------------------------------------------------
# 1. Γ agrees with the conversion it replaces, and Z does not move
# ---------------------------------------------------------------------------
def test_native_gamma_equals_the_downstream_conversion():
    """Gate (a): the native readout and (Z − z0)/(Z + z0) are the same number
    at ordinary frequencies. Measured worst |ΔΓ| here: ~1e-16."""
    rng = np.random.default_rng(4)
    worst = 0.0
    for _ in range(200):
        z_ant = complex(rng.uniform(3.0, 900.0), rng.uniform(-800.0, 800.0))
        red, y = _bare(z_ant)
        z = red.driven_impedance(y, WL)[0]
        g = red.driven_reflection(y, WL)[0]
        worst = max(worst, abs(g - (z - Z_REF_DEFAULT) / (z + Z_REF_DEFAULT)))
    assert worst < 1e-10, worst


def test_the_impedance_answer_is_independent_of_the_reference():
    """Z = E/j − z_ref really is z_ref-free: three references, one answer,
    and it is the ideal generator's."""
    red, y = _bare(
        73.0 + 42.0j, branches=[TL("feed", "n1", z0=450.0, length=3.1)], n1=True
    )
    ideal = red.impedance_from_y(red.apply_branches(y, WL))[0]
    for zr in (12.5, 50.0, 600.0):
        assert red.driven_impedance(y, WL, z_ref=zr)[0] == pytest.approx(
            ideal, rel=1e-10
        )


def test_a_series_load_stays_inside_the_impedance():
    """The reference plane sits between the source impedance and the load
    chain, so Z keeps including the Load the way it always did."""
    net = Network(
        ports={"feed": PortOnWire("feed")},
        branches=[Load(port="feed", r=25.0)],
        sources=[Driven(port="feed")],
    )
    red = _reducer(net)
    y = np.array([[1.0 / 50.0]], dtype=np.complex128)
    z = red.driven_impedance(y, WL)[0]
    assert z == pytest.approx(75.0, rel=1e-10)
    g = red.driven_reflection(y, WL)[0]
    assert g == pytest.approx((75.0 - 50.0) / (75.0 + 50.0), rel=1e-10)


# ---------------------------------------------------------------------------
# 2. the two boundary cases Z cannot express
# ---------------------------------------------------------------------------
def test_a_shorted_port_is_gamma_minus_one_and_well_conditioned():
    """Gate (b), in its pure form: a 0 Ω shunt across the driven port. The
    ideal generator's system is rank-deficient; the referenced one is not."""
    red, y = _bare(50.0, branches=[Shunt(port="feed", r=0.0)])
    assert _rcond(red.apply_branches(y, WL)) < RCOND_SINGULAR
    referenced = red.apply_branches(y, WL, z_ref=Z_REF_DEFAULT)
    assert _rcond(referenced) > 0.1
    assert abs(red.impedance_from_y(referenced)[0]) < 1e-12
    assert abs(red.reflection_from_y(referenced)[0] + 1.0) < 1e-12


def test_an_open_port_is_exactly_gamma_plus_one():
    """Gate (c). Z is reported as a clean real ∞ (issue #289) and cannot be
    anything else; Γ is +1, exactly, with no sentinel and no clamp."""
    # The port itself must be the open, not merely lead to one: a
    # parallel-LC trap Load at its own resonance.
    net = Network(
        ports={"feed": PortOnWire("feed")},
        branches=[
            Load(
                port="feed",
                parallel=True,
                l=1e-6,
                c=1.0 / (1e-6 * (2 * np.pi * F_MHZ * 1e6) ** 2),
            )
        ],
        sources=[Driven(port="feed")],
    )
    red = _reducer(net)
    y = np.array([[1.0 / 50.0]], dtype=np.complex128)
    system = red.apply_branches(y, WL, z_ref=Z_REF_DEFAULT)
    z = red.impedance_from_y(system)[0]
    assert z == complex(float("inf"), 0.0)
    assert red.reflection_from_y(system)[0] == 1.0 + 0j


# ---------------------------------------------------------------------------
# 3. where the reference is NOT stamped, and why
# ---------------------------------------------------------------------------
def test_two_generators_keep_the_ideal_operating_point():
    """A driven array's Z_k = V_k/I_k is defined with every other feed held at
    its stated voltage. A source impedance at port 0 changes v0 itself — the
    mutual term y01·E1 injects current independently of it — so the ratio
    moves, measured 23 % on this fixture. The reducer therefore declines to
    stamp a reference at all when more than one source is active, and quotes Γ
    from Z instead."""
    net = Network(
        ports={"f1": PortOnWire("f1"), "f2": PortOnWire("f2")},
        sources=[Driven(port="f1", voltage=1 + 0j), Driven(port="f2", voltage=0.5j)],
    )
    red = _reducer(net)
    y = np.array([[0.02 + 0.008j, 0.004 + 0.001j], [0.004 + 0.001j, 0.02 + 0.008j]])
    system = red.apply_branches(y, WL, z_ref=Z_REF_DEFAULT)
    assert system.z_ref_at == {}  # nothing stamped
    zs = red.impedance_from_y(system)
    ideal = red.impedance_from_y(red.apply_branches(y, WL))
    np.testing.assert_allclose(zs, ideal, rtol=1e-12)
    gs = red.reflection_from_y(system)
    for g, z in zip(gs, zs):
        assert g == pytest.approx((z - 50.0) / (z + 50.0), rel=1e-12)


def test_a_zero_volt_pin_keeps_its_hard_short():
    """`Driven(port, 0)` is the datum trick, not a generator: it must stay a
    hard V = 0 pin, and it leaves the rest of the network passive so the OTHER
    port still gets its reference."""
    net = Network(
        ports={"f1": PortOnWire("f1"), "f2": PortOnWire("f2")},
        sources=[Driven(port="f1"), Driven(port="f2", voltage=0j)],
    )
    red = _reducer(net)
    y = np.array([[0.02 + 0.008j, 0.004 + 0.001j], [0.004 + 0.001j, 0.02 + 0.008j]])
    system = red.apply_branches(y, WL, z_ref=Z_REF_DEFAULT)
    assert list(system.z_ref_at) == [0]  # f1 referenced, f2 pinned
    v, _j = system.solve()
    assert v[1] == 0j
    assert red.impedance_from_y(system)[1] == 0.0


def test_a_current_source_is_its_own_reference():
    """Z_s = ∞ already: no z_ref is stamped, and Γ comes from Z."""
    net = Network(
        ports={"feed": PortOnWire("feed")},
        sources=[DrivenCurrent(port="feed", current=1 + 0j)],
    )
    red = _reducer(net)
    y = np.array([[1.0 / (120.0 - 30.0j)]], dtype=np.complex128)
    system = red.apply_branches(y, WL, z_ref=Z_REF_DEFAULT)
    assert system.z_ref_at == {}
    z = red.impedance_from_y(system)[0]
    assert z == pytest.approx(120.0 - 30.0j, rel=1e-10)
    assert red.reflection_from_y(system)[0] == pytest.approx(
        (z - 50.0) / (z + 50.0), rel=1e-12
    )


def test_gamma_from_an_ideal_generator_solve_is_refused():
    """There is no reference plane to reflect against — say so rather than
    return (2E − E)/E = 1 for every network."""
    red, y = _bare(50.0)
    with pytest.raises(ValueError, match="ideal-generator"):
        red.reflection_from_y(red.apply_branches(y, WL))


# ---------------------------------------------------------------------------
# 4. the excited path is untouched
# ---------------------------------------------------------------------------
def test_the_excited_solve_keeps_the_ideal_generator():
    """Gate (d): p_in and the port voltages are the drive, so a source
    impedance would halve the excitation and rescale every gain. The excited
    path stamps z_ref = 0 and its numbers are the historical ones."""
    red, y = _bare(50.0 + 0j)
    v, eff, p_in, _budget = red.excited_state(y, WL)
    assert v[0] == pytest.approx(1.0 + 0j, rel=1e-12)  # the applied EMF, whole
    assert p_in == pytest.approx(0.5 * (1.0 / 50.0), rel=1e-12)
    assert eff == 1.0


def test_a_shorted_port_has_an_impedance_but_no_far_field():
    """The documented asymmetry the split produces. Driving a dead short with
    an ideal source takes unbounded current, so there is nothing to normalise
    a pattern against — while the impedance question still has its answer."""
    red, y = _bare(50.0, branches=[Shunt(port="feed", r=0.0)])
    assert abs(red.driven_impedance(y, WL)[0]) < 1e-12
    with pytest.raises(SingularNetworkError):
        red.excited_state(y, WL)


def test_the_reference_leaves_no_trace_in_the_power_budget():
    """z_ref is a modelling reference, not a resistor in the design: the Load
    probe reports the Load's watts and nothing else, at either stamp."""
    net = Network(
        ports={"feed": PortOnWire("feed")},
        branches=[Load(port="feed", r=25.0)],
        sources=[Driven(port="feed")],
    )
    red = _reducer(net)
    y = np.array([[1.0 / 50.0]], dtype=np.complex128)
    watts = []
    for zr in (0j, Z_REF_DEFAULT):
        system = red.apply_branches(y, WL, z_ref=zr)
        probe = system.probes[0]
        assert probe[0] == "Load feed"
        watts.append(system.branch_power(probe))
    # ½·R·|j|² at each stamp's own current; the referenced solve draws less,
    # but neither reading contains a watt of z_ref.
    for w, system_zr in zip(watts, (0j, Z_REF_DEFAULT)):
        system = red.apply_branches(y, WL, z_ref=system_zr)
        _v, j = system.solve()
        col = system.terminations[0][0]
        assert w == pytest.approx(0.5 * 25.0 * abs(j[col]) ** 2, rel=1e-10)
