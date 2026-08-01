"""Transmission-line stub matching elements (issue #598).

The four stub flavors are composition sugar over `TL` (shunt) and
`BalancedLine` (series) — no new reducer math — so the tests are analytic
oracles on the reduced network: a shorted stub must present jZ₀·tan(βl) and
an open one −jZ₀·cot(βl) at its port, with the sign flipping past λ/4, and
the lossless singularities must behave exactly as the TL guard says they do.

No MoM here: the "antenna" is a synthetic 1×1 Y (or nothing at all), so the
whole file is arithmetic.
"""

import numpy as np
import pytest

from antennaknobs.network import (
    TL,
    BalancedLine,
    Driven,
    Instance,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
)
from antennaknobs.network_reduce import C_LIGHT, NetworkReducer
from antennaknobs.station import (
    double_stub_tuner,
    series_open_stub,
    series_shorted_stub,
    shunt_open_stub,
    shunt_shorted_stub,
    single_stub_tuner,
)

F_MHZ = 14.0
WL = C_LIGHT / (F_MHZ * 1e6)
Z0 = 50.0
NO_ANTENNA = np.zeros((0, 0), dtype=np.complex128)


def reducer(net):
    """Standard port indexing: real PortOnWire ports first, virtual after."""
    real = [n for n, p in net.ports.items() if isinstance(p, PortOnWire)]
    virt = [n for n, p in net.ports.items() if isinstance(p, PortVirtual)]
    idx = {n: i for i, n in enumerate(real + virt)}
    return NetworkReducer(net, idx, len(idx))


def z_shunt(stub):
    """Driving-point impedance of a one-port stub hung on a bare virtual
    port: nothing else is attached, so this IS the stub's input impedance."""
    net = Network(
        ports={"rig": PortVirtual("rig")},
        branches=[Instance("stub", stub, port="rig")],
        sources=[Driven(port="rig")],
    )
    return reducer(net).driven_impedance(NO_ANTENNA, WL)[0]


def z_series(stub, z_load=Z0):
    """Driving-point impedance of a series stub inserted between the driven
    virtual port and a synthetic `z_load` antenna. A series element adds, so
    the answer must be exactly ``z_stub + z_load`` — which is also the proof
    that the element floats (any datum leakage would break the sum)."""
    net = Network(
        ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
        branches=[Instance("stub", stub, a="rig", b="ant")],
        sources=[Driven(port="rig")],
    )
    y = np.array([[1.0 / z_load]], dtype=np.complex128)
    return reducer(net).driven_impedance(y, WL)[0]


def z_shorted(length_wl, z0=Z0):
    """The closed form: Z_in = +j·Z₀·tan(βl), βl = 2π·length_wl."""
    return 1j * z0 * np.tan(2.0 * np.pi * length_wl)


def z_open(length_wl, z0=Z0):
    """The closed form: Z_in = −j·Z₀·cot(βl), βl = 2π·length_wl."""
    return -1j * z0 / np.tan(2.0 * np.pi * length_wl)


# ---------------------------------------------------------------------------
# the closed forms
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("length_wl", [0.02, 0.05, 0.125, 0.2, 0.24])
def test_shunt_shorted_stub_is_j_z0_tan(length_wl):
    """Below λ/4 a shorted stub is a pure inductive reactance +jZ₀·tan(βl)."""
    z = z_shunt(shunt_shorted_stub(F_MHZ, length_wl, z0=Z0))
    assert z == pytest.approx(z_shorted(length_wl), rel=1e-9)
    assert z.imag > 0.0  # inductive below λ/4


@pytest.mark.parametrize("length_wl", [0.02, 0.05, 0.125, 0.2, 0.24])
def test_shunt_open_stub_is_minus_j_z0_cot(length_wl):
    """Below λ/4 an open stub is a pure capacitive reactance −jZ₀·cot(βl)."""
    z = z_shunt(shunt_open_stub(F_MHZ, length_wl, z0=Z0))
    assert z == pytest.approx(z_open(length_wl), rel=1e-9)
    assert z.imag < 0.0  # capacitive below λ/4


@pytest.mark.parametrize("length_wl", [0.26, 0.3, 0.375, 0.45])
def test_stub_reactance_sign_flips_past_quarter_wave(length_wl):
    """Past λ/4 both flavors swap character — the same closed forms keep
    holding, tan/cot having gone through their pole."""
    z_sh = z_shunt(shunt_shorted_stub(F_MHZ, length_wl, z0=Z0))
    z_op = z_shunt(shunt_open_stub(F_MHZ, length_wl, z0=Z0))
    assert z_sh == pytest.approx(z_shorted(length_wl), rel=1e-9)
    assert z_op == pytest.approx(z_open(length_wl), rel=1e-9)
    assert z_sh.imag < 0.0 and z_op.imag > 0.0  # capacitive / inductive now


def test_stub_impedance_scales_with_z0():
    """Z₀ is a plain multiplier on the reactance — a 450 Ω ladder-line stub
    of the same electrical length is 9× the 50 Ω one."""
    z50 = z_shunt(shunt_shorted_stub(F_MHZ, 0.1, z0=50.0))
    z450 = z_shunt(shunt_shorted_stub(F_MHZ, 0.1, z0=450.0))
    assert z450 == pytest.approx(9.0 * z50, rel=1e-12)


# ---------------------------------------------------------------------------
# the length convention: wavelengths ON THE LINE at the design frequency
# ---------------------------------------------------------------------------
def test_length_is_electrical_and_vf_is_applied_for_you():
    """``length_wl`` is electrical length in wavelengths on the line, so vf
    changes the METRES cut, never the reactance presented at ``freq_mhz``."""
    lossless = shunt_shorted_stub(F_MHZ, 0.125, z0=Z0, vf=1.0)
    coax = shunt_shorted_stub(F_MHZ, 0.125, z0=Z0, vf=0.66)
    assert z_shunt(coax) == pytest.approx(z_shunt(lossless), rel=1e-12)
    (tl_l, _short_l) = lossless.branches
    (tl_c, _short_c) = coax.branches
    assert tl_l.length == pytest.approx(0.125 * WL, rel=1e-12)
    assert tl_c.length == pytest.approx(0.66 * 0.125 * WL, rel=1e-12)


def test_stub_detunes_off_the_design_frequency_like_real_coax():
    """The composite bakes METRES, so a sweep re-derives βl: at 2× the
    design frequency a 0.1 λ stub is a 0.2 λ stub."""
    stub = shunt_shorted_stub(F_MHZ, 0.1, z0=Z0)
    net = Network(
        ports={"rig": PortVirtual("rig")},
        branches=[Instance("stub", stub, port="rig")],
        sources=[Driven(port="rig")],
    )
    z = reducer(net).driven_impedance(NO_ANTENNA, WL / 2.0)[0]
    assert z == pytest.approx(z_shorted(0.2), rel=1e-9)


def test_cable_keyword_takes_z0_vf_and_loss_from_the_catalog():
    """``cable=`` is the one-word spelling of "cut it from this reel"."""
    from antennaknobs.network import CABLES

    c = CABLES["RG-213"]
    (tl, _short) = shunt_shorted_stub(F_MHZ, 0.125, cable="RG-213").branches
    assert (tl.z0, tl.vf, tl.k1, tl.k2) == (c.z0, c.vf, c.k1, c.k2)
    assert tl.length == pytest.approx(0.125 * c.vf * WL, rel=1e-12)


def test_unknown_cable_reuses_from_cable_ergonomics():
    with pytest.raises(KeyError, match="unknown cable"):
        shunt_open_stub(F_MHZ, 0.125, cable="RG-8XX")


# ---------------------------------------------------------------------------
# the lossless singularities — same policy as the TL guard
# ---------------------------------------------------------------------------
def test_quarter_wave_shorted_stub_is_an_open_and_needs_no_guard():
    """λ/4 shorted = the metal insulator: Z_in → ∞, which is a plain zero
    admittance the stamp handles without complaint."""
    z = z_shunt(shunt_shorted_stub(F_MHZ, 0.25, z0=Z0))
    assert abs(z) > 1e12


def test_lossless_quarter_wave_open_stub_raises_like_the_tl_guard():
    """λ/4 open = a dead short across the port: singular, and refused at
    construction with the TL guard's message shape and escape hatch."""
    with pytest.raises(ValueError, match=r"odd multiple of λ/4"):
        shunt_open_stub(F_MHZ, 0.25, z0=Z0)
    with pytest.raises(ValueError, match=r"odd multiple of λ/4"):
        series_open_stub(F_MHZ, 0.75, z0=Z0)  # every odd multiple, not just λ/4


def test_loss_is_the_escape_hatch_for_the_quarter_wave_open_stub():
    """With real cable loss the λ/4 open stub is finite and REAL: coth of
    (αl + jπ/2) is tanh(αl), so Z_in ≈ Z₀·αl — the stub's own copper."""
    from antennaknobs.network import CABLES
    from antennaknobs.network_reduce import FEET_PER_M, NEPER_PER_DB

    c = CABLES["RG-213"]
    z = z_shunt(shunt_open_stub(F_MHZ, 0.25, cable="RG-213"))
    alpha = (
        (c.k1 * np.sqrt(F_MHZ) + c.k2 * F_MHZ) * NEPER_PER_DB * FEET_PER_M / 100.0
    )  # fmt: skip
    length = 0.25 * c.vf * WL
    assert z == pytest.approx(c.z0 * np.tanh(alpha * length), rel=1e-9)
    assert z.real > 0.0 and abs(z.imag) < 1e-9


def test_half_wave_shorted_stub_trips_the_tl_guard_at_stamp_time():
    """The other face of the same coin is TL's own: a lossless k·λ/2 line has
    no finite admittance, so the reducer raises when it stamps."""
    with pytest.raises(ValueError, match="sinh γl"):
        z_shunt(shunt_shorted_stub(F_MHZ, 0.5, z0=Z0))


# ---------------------------------------------------------------------------
# series stubs — floating, via BalancedLine
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("length_wl", [0.05, 0.125, 0.375])
def test_series_shorted_stub_adds_j_z0_tan_in_series(length_wl):
    z = z_series(series_shorted_stub(F_MHZ, length_wl, z0=Z0))
    assert z == pytest.approx(Z0 + z_shorted(length_wl), rel=1e-9)


@pytest.mark.parametrize("length_wl", [0.05, 0.125, 0.375])
def test_series_open_stub_adds_minus_j_z0_cot_in_series(length_wl):
    z = z_series(series_open_stub(F_MHZ, length_wl, z0=Z0))
    assert z == pytest.approx(Z0 + z_open(length_wl), rel=1e-9)


def test_series_stub_is_floating_not_a_shunt():
    """The whole point of the BalancedLine spelling: the same electrical
    length in series and in shunt give different answers, and only the series
    one adds to the load. (A datum-referenced TL could not do this.)"""
    z_ser = z_series(series_shorted_stub(F_MHZ, 0.125, z0=Z0), z_load=100.0)
    assert z_ser == pytest.approx(100.0 + z_shorted(0.125), rel=1e-9)
    # the shunt twin on the same load is the parallel combination instead
    net = Network(
        ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
        branches=[
            Instance("stub", shunt_shorted_stub(F_MHZ, 0.125, z0=Z0), port="rig"),
            TL(a="rig", b="ant", z0=Z0, length=1e-9),  # a nominal wire, not a line
        ],
        sources=[Driven(port="rig")],
    )
    y = np.array([[1.0 / 100.0]], dtype=np.complex128)
    z_sh = reducer(net).driven_impedance(y, WL)[0]
    assert z_sh == pytest.approx(1.0 / (1.0 / 100.0 + 1.0 / z_shorted(0.125)), rel=1e-6)


def test_series_stub_far_end_reference_pin_carries_no_current():
    """The datum bond at ``far2`` is a common-mode reference, not a return:
    it must dissipate nothing and leave the element's power budget to the
    line itself."""
    stub = series_shorted_stub(F_MHZ, 0.125, z0=Z0, k1=0.2)
    net = Network(
        ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
        branches=[Instance("stub", stub, a="rig", b="ant")],
        sources=[Driven(port="rig")],
    )
    y = np.array([[1.0 / Z0]], dtype=np.complex128)
    _v, _eff, _p_in, budget = reducer(net).excited_state(y, WL)
    watts = dict(budget)
    assert watts["stub: Shunt far2"] == pytest.approx(0.0, abs=1e-18)
    assert watts["stub: TwoPort far1→far2"] == pytest.approx(0.0, abs=1e-18)
    assert watts["stub: BalancedLine rig,ant→far1,far2"] > 0.0


def test_series_stubs_are_balancedline_shaped():
    """Structure, so the "why not TL" decision stays visible: the series
    flavors are a differential (CM-open) line with its far end terminated."""
    line, strap, pin = series_shorted_stub(F_MHZ, 0.1, z0=300.0).branches
    assert isinstance(line, BalancedLine) and line.zcomm is None
    assert (line.a1, line.a2, line.b1, line.b2) == ("a", "b", "far1", "far2")
    assert line.zdiff == 300.0
    assert (strap.a, strap.b, strap.r) == ("far1", "far2", 0.0)
    assert (pin.port, pin.r) == ("far2", 0.0)
    _line, open_end, pin = series_open_stub(F_MHZ, 0.1, z0=300.0).branches
    assert (open_end.port, open_end.c) == ("far1", 0.0)  # 0 F = no element
    assert (pin.port, pin.r) == ("far2", 0.0)


# ---------------------------------------------------------------------------
# the tuners
# ---------------------------------------------------------------------------
def test_single_stub_tuner_matches_a_real_load_to_z0():
    """The textbook worked case: for a purely real load n = R_L/Z₀ the tap
    is at tan(βd) = √n and the shorted stub at cot(βl) = (n−1)/√n. With
    n = 2 both angles collapse to atan(√2) — one length, cut twice — and the
    tuner must land on exactly Z₀."""
    n = 2.0
    d = np.arctan(np.sqrt(n)) / (2.0 * np.pi)
    stub_wl = np.arctan(np.sqrt(n) / (n - 1.0)) / (2.0 * np.pi)
    assert stub_wl == pytest.approx(d, rel=1e-12)  # the n = 2 coincidence
    net = Network(
        ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
        branches=[
            Instance(
                "t", single_stub_tuner(F_MHZ, d, stub_wl, z0=Z0), rig="rig", ant="ant"
            )  # fmt: skip
        ],
        sources=[Driven(port="rig")],
    )
    y = np.array([[1.0 / (n * Z0)]], dtype=np.complex128)
    z = reducer(net).driven_impedance(y, WL)[0]
    assert z == pytest.approx(Z0 + 0j, rel=1e-9, abs=1e-9)


def test_single_stub_tuner_open_flavor_matches_the_same_load():
    """Same match with an open stub: the susceptance to cancel is the same,
    so the open stub is a quarter wave shorter (mod λ/2)."""
    n = 2.0
    d = np.arctan(np.sqrt(n)) / (2.0 * np.pi)
    stub_wl = d + 0.25  # open stub = shorted stub + λ/4
    net = Network(
        ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
        branches=[
            Instance(
                "t",
                single_stub_tuner(F_MHZ, d, stub_wl, z0=Z0, shorted=False),
                rig="rig",
                ant="ant",
            )  # fmt: skip
        ],
        sources=[Driven(port="rig")],
    )
    y = np.array([[1.0 / (n * Z0)]], dtype=np.complex128)
    z = reducer(net).driven_impedance(y, WL)[0]
    assert z == pytest.approx(Z0 + 0j, rel=1e-9, abs=1e-9)


def test_single_stub_tuner_is_the_hand_composition():
    """Sugar, not math: the tuner is exactly a line section plus a stub at
    the tap, and must reduce identically to that hand-built network."""
    d, stub_wl = 0.15, 0.2
    sugar = Network(
        ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
        branches=[
            Instance(
                "t", single_stub_tuner(F_MHZ, d, stub_wl, z0=Z0), rig="rig", ant="ant"
            )  # fmt: skip
        ],
        sources=[Driven(port="rig")],
    )
    hand = Network(
        ports={
            "ant": PortOnWire("ant"),
            "rig": PortVirtual("rig"),
            "far": PortVirtual("far"),
        },
        branches=[
            TL(a="rig", b="ant", z0=Z0, length=d * WL),
            TL(a="rig", b="far", z0=Z0, length=stub_wl * WL),
            Shunt(port="far", r=0.0),
        ],
        sources=[Driven(port="rig")],
    )
    y = np.array([[1.0 / (30.0 + 40.0j)]], dtype=np.complex128)
    z_sugar = reducer(sugar).driven_impedance(y, WL)[0]
    z_hand = reducer(hand).driven_impedance(y, WL)[0]
    assert z_sugar == pytest.approx(z_hand, rel=1e-12)


def test_double_stub_tuner_places_both_stubs_across_the_spacing():
    """Two stubs, one fixed spacing — again pure composition, checked
    against the hand-built three-branch network."""
    spacing, l1, l2 = 0.125, 0.1, 0.3
    sugar = Network(
        ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
        branches=[
            Instance(
                "t",
                double_stub_tuner(F_MHZ, spacing, l1, l2, z0=Z0),
                rig="rig",
                ant="ant",
            )  # fmt: skip
        ],
        sources=[Driven(port="rig")],
    )
    hand = Network(
        ports={
            "ant": PortOnWire("ant"),
            "rig": PortVirtual("rig"),
            "f1": PortVirtual("f1"),
            "f2": PortVirtual("f2"),
        },
        branches=[
            TL(a="ant", b="f1", z0=Z0, length=l1 * WL),
            Shunt(port="f1", r=0.0),
            TL(a="rig", b="ant", z0=Z0, length=spacing * WL),
            TL(a="rig", b="f2", z0=Z0, length=l2 * WL),
            Shunt(port="f2", r=0.0),
        ],
        sources=[Driven(port="rig")],
    )
    y = np.array([[1.0 / (80.0 - 25.0j)]], dtype=np.complex128)
    assert reducer(sugar).driven_impedance(y, WL)[0] == pytest.approx(
        reducer(hand).driven_impedance(y, WL)[0], rel=1e-12
    )


def test_lossy_stub_itemizes_under_its_instance_in_the_power_budget():
    """A stub cut from real coax burns real watts, attributed to its
    instance path like every other composite (issue #299/#489)."""
    net = Network(
        ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
        branches=[
            Instance(
                "tuner",
                single_stub_tuner(F_MHZ, 0.15, 0.2, cable="RG-58"),
                rig="rig",
                ant="ant",
            )  # fmt: skip
        ],
        sources=[Driven(port="rig")],
    )
    y = np.array([[1.0 / (30.0 + 40.0j)]], dtype=np.complex128)
    _v, eff, p_in, budget = reducer(net).excited_state(y, WL)
    watts = dict(budget)
    assert set(watts) == {"tuner: TL rig→ant", "tuner.stub: TL rig→far",
                          "tuner.stub: Shunt far"}  # fmt: skip
    assert watts["tuner.stub: TL rig→far"] > 0.0  # the stub's own copper
    assert watts["tuner.stub: Shunt far"] == pytest.approx(0.0, abs=1e-18)
    assert 0.0 < 1.0 - eff < 1.0 and p_in > 0.0
