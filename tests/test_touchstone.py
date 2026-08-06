"""Touchstone (.s1p/.s2p) import as build_network() elements (issue #593).

Two layers, mirroring test_admittance_branch.py: the parser + parameter
conversions (pure), then the reducer stamps on a synthetic antenna Y — since
both Touchstone elements are group-1 verbatim-Y stamps, the exact oracle is the
bare nodal solve of the augmented admittance, exactly as for Admittance.
"""

import math
from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs import AntennaBuilder, read_touchstone
from antennaknobs.network import (
    TL,
    Driven,
    Network,
    PortOnWire,
    PortVirtual,
    TouchstoneLoad,
    TouchstoneTwoPort,
    Wire,
)
from antennaknobs.network_reduce import (
    C_LIGHT,
    NetworkReducer,
    SingularNetworkError,
    tl_admittance_2x2,
)
from antennaknobs.touchstone import parse_touchstone

FREQ_MHZ = 14.0
WL = C_LIGHT / (FREQ_MHZ * 1e6)


# ---------------------------------------------------------------------------
# harness (shared with test_admittance_branch.py in spirit)
# ---------------------------------------------------------------------------
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


def nodal_reference(y_full, driven):
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


def _s2p_from_matrix(freqs_hz, s_of_f):
    """Build .s2p text (HZ, RI) from a function f→2×2 S."""
    out = ["# HZ S RI R 50"]
    for f in freqs_hz:
        s = s_of_f(f)
        vals = [s[0, 0], s[1, 0], s[0, 1], s[1, 1]]  # Touchstone order
        out.append(f"{f} " + " ".join(f"{v.real} {v.imag}" for v in vals))
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# 1. parser + conversions
# ---------------------------------------------------------------------------
def test_s1p_ri_impedance_and_admittance():
    """S11 = 1/3 at z0=50 → Z = 100 Ω, Y = 0.01 S."""
    t = parse_touchstone("# MHZ S RI R 50\n10 0.333333333333 0\n30 0.333333333333 0\n")
    assert t.nports == 1 and t.z0 == 50.0
    assert t.z_at(20e6)[0, 0] == pytest.approx(100.0, rel=1e-9)
    assert t.y_at(20e6)[0, 0] == pytest.approx(0.01, rel=1e-9)


def test_ri_ma_db_formats_agree():
    val = 0.1 + 0.2j
    mag, ang, db = (
        abs(val),
        math.degrees(math.atan2(0.2, 0.1)),
        20 * math.log10(abs(val)),
    )
    ri = parse_touchstone("# HZ S RI R 50\n1e7 0.1 0.2\n2e7 0.1 0.2\n")
    ma = parse_touchstone(f"# HZ S MA R 50\n1e7 {mag} {ang}\n2e7 {mag} {ang}\n")
    dbf = parse_touchstone(f"# HZ S DB R 50\n1e7 {db} {ang}\n2e7 {db} {ang}\n")
    assert np.allclose(ri.s_at(1.5e7), ma.s_at(1.5e7))
    assert np.allclose(ri.s_at(1.5e7), dbf.s_at(1.5e7))


@pytest.mark.parametrize(
    "unit,scale", [("HZ", 1.0), ("KHZ", 1e3), ("MHZ", 1e6), ("GHZ", 1e9)]
)
def test_frequency_units(unit, scale):
    t = parse_touchstone(f"# {unit} S RI R 50\n1 0 0\n2 0 0\n")
    assert t.freqs[0] == pytest.approx(1 * scale) and t.freqs[1] == pytest.approx(
        2 * scale
    )


def test_linear_interpolation_midpoint():
    t = parse_touchstone("# HZ S RI R 50\n10 0 0\n20 0.4 0.2\n")
    assert t.s_at(15)[0, 0] == pytest.approx(0.2 + 0.1j, rel=1e-12)


def test_out_of_range_raises():
    t = parse_touchstone("# MHZ S RI R 50\n10 0 0\n20 0 0\n")
    with pytest.raises(ValueError, match="outside the Touchstone data range"):
        t.y_at(5e6)
    with pytest.raises(ValueError, match="outside the Touchstone data range"):
        t.y_at(25e6)


def test_z_and_y_parameter_files():
    """Z- and Y-parameter Touchstone convert correctly (not just S)."""
    tz = parse_touchstone("# HZ Z RI R 50\n1e7 100 0\n2e7 100 0\n")
    assert tz.y_at(1.5e7)[0, 0] == pytest.approx(0.01, rel=1e-12)
    ty = parse_touchstone("# HZ Y RI R 50\n1e7 0.01 0\n2e7 0.01 0\n")
    assert ty.z_at(1.5e7)[0, 0] == pytest.approx(100.0, rel=1e-12)


def test_infer_port_count_from_width():
    assert parse_touchstone("# HZ S RI R 50\n1 0 0\n2 0 0\n").nports == 1
    assert (
        parse_touchstone(
            "# HZ S RI R 50\n1 0 0 0.9 0 0.9 0 0 0\n2 0 0 0.9 0 0.9 0 0 0\n"
        ).nports
        == 2
    )


def test_gh_parameters_rejected():
    with pytest.raises(ValueError, match="not supported"):
        parse_touchstone("# HZ G RI R 50\n1 0 0\n")


# ---------------------------------------------------------------------------
# 1b. the poles of the parameter conversions (issue #746)
#
# S is bounded for every passive network; Y and Z are not. Each conversion is
# a Möbius transform whose pole is a physical short (S = −1) or open (S = +1),
# and the two ways a bare `np.linalg.inv` used to report that pole — an
# untyped LinAlgError exactly on it, astronomical finite numbers just off it —
# were both useless to the person holding the file.
# ---------------------------------------------------------------------------
def _s1p(s11, *, name=""):
    return parse_touchstone(
        f"# HZ S RI R 50\n1e7 {s11.real!r} {s11.imag!r}\n"
        f"2e7 {s11.real!r} {s11.imag!r}\n",
        name=name,
    )


def test_s1p_at_a_dead_short_raises_the_house_error():
    """S11 = −1 exactly: `inv(I + S)` used to raise a bare LinAlgError."""
    with pytest.raises(SingularNetworkError) as exc:
        _s1p(-1.0 + 0j, name="shorted.s1p").y_at(1.5e7)
    msg = str(exc.value)
    assert "shorted.s1p" in msg  # which file
    assert "15 MHz" in msg  # ...at which frequency
    assert "I + S" in msg and "short circuit" in msg  # ...and why


def test_s1p_a_hair_off_the_short_raises_too():
    """The silent half of the bug: just off the pole there was no exception at
    all, only a 1e13-siemens admittance stamped into the reducer's G."""
    with pytest.raises(SingularNetworkError, match="I \\+ S"):
        _s1p(-1.0 + 1e-13j).y_at(1.5e7)


def test_s1p_near_but_not_at_the_short_is_finite_and_says_so(caplog):
    """1e-10 from the pole is a legitimate near-short, not a singularity: the
    admittance is enormous but correct, and the warning is the whole report."""
    with caplog.at_level("WARNING"):
        y = _s1p(-1.0 + 1e-10j, name="near.s1p").y_at(1.5e7)[0, 0]
    # Y = (1/z0)(1 − S)/(1 + S) with S = −1 + 1e-10j
    assert y == pytest.approx((1.0 / 50.0) * (2.0 - 1e-10j) / 1e-10j, rel=1e-6)
    assert "near.s1p" in caplog.text and "nearly singular" in caplog.text


def test_s1p_at_an_open_raises_from_z_at():
    """The dual pole: S11 = +1 is an open, and it is `z_at` that hits it."""
    with pytest.raises(SingularNetworkError) as exc:
        _s1p(1.0 + 0j).z_at(1.5e7)
    assert "I − S" in str(exc.value) and "open circuit" in str(exc.value)
    # ...while the admittance of that same open is a perfectly ordinary zero.
    assert _s1p(1.0 + 0j).y_at(1.5e7)[0, 0] == pytest.approx(0.0, abs=1e-15)


def test_matched_coax_at_half_wave_s2p_no_longer_stamps_1e14():
    """The case the issue names: a 50 Ω coax measured into a 50 Ω reference at
    exactly 180° electrical has S = [[0, −1], [−1, 0]], so I + S is rank 1.
    Nothing about the file is unusual and nothing about the physics is
    singular — the *admittance description* of a half-wave line is what does
    not exist."""
    s21 = np.exp(-1j * np.pi)  # −1 to within one ulp, as a real file records it
    s = np.array([[0.0, s21], [s21, 0.0]], dtype=complex)
    t = parse_touchstone(
        _s2p_from_matrix([13e6, 15e6], lambda f: s), nports=2, name="coax180.s2p"
    )
    # What the unguarded conversion produced: no exception, just an absurdity.
    # The ulp is exactly what kept `inv` from noticing.
    eye = np.eye(2)
    y_unguarded = (1.0 / 50.0) * (eye - s) @ np.linalg.inv(eye + s)
    assert np.isfinite(y_unguarded).all() and abs(y_unguarded[0, 0]) > 1e13

    with pytest.raises(SingularNetworkError) as exc:
        t.y_at(14e6)
    assert "coax180.s2p" in str(exc.value) and "I + S" in str(exc.value)

    # And exactly on it, where `inv` raised an untyped LinAlgError instead.
    exact = parse_touchstone(
        _s2p_from_matrix([13e6, 15e6], lambda f: np.array([[0.0, -1.0], [-1.0, 0.0]])),
        nports=2,
    )
    with pytest.raises(SingularNetworkError):
        exact.y_at(14e6)


def test_an_open_y_file_still_has_an_ordinary_s():
    """`s_at` goes Y → S directly rather than through Z, because S exists where
    Z does not: a zero admittance is an open, whose reflection is simply +1."""
    t = parse_touchstone("# HZ Y RI R 50\n1e7 0 0\n2e7 0 0\n")
    assert t.s_at(1.5e7)[0, 0] == pytest.approx(1.0, rel=1e-12)
    with pytest.raises(SingularNetworkError, match="open circuit"):
        t.z_at(1.5e7)


def test_a_shorted_z_file_reports_the_short():
    t = parse_touchstone("# HZ Z RI R 50\n1e7 0 0\n2e7 0 0\n")
    with pytest.raises(SingularNetworkError, match="short circuit"):
        t.y_at(1.5e7)
    assert t.s_at(1.5e7)[0, 0] == pytest.approx(-1.0, rel=1e-12)


# ---------------------------------------------------------------------------
# 2. reciprocity / element validation
# ---------------------------------------------------------------------------
def test_reciprocal_2port_gives_symmetric_y():
    t = parse_touchstone(
        "# MHZ S RI R 50\n14 0.2 0.0 0.9 0.0 0.9 0.0 0.2 0.0\n"
        "15 0.2 0.0 0.9 0.0 0.9 0.0 0.2 0.0\n",
        nports=2,
    )
    y = t.y_at(14.5e6)
    assert np.allclose(y, y.T)  # S12 == S21 ⇒ Y12 == Y21


def test_passive_1port_has_positive_resistance():
    """|S11| < 1 ⇒ Re(Z) > 0 (a passive termination)."""
    t = parse_touchstone("# HZ S MA R 50\n1e7 0.5 45\n2e7 0.5 45\n")
    assert t.z_at(1.5e7)[0, 0].real > 0


def test_element_port_count_validation():
    one = parse_touchstone("# HZ S RI R 50\n1 0 0\n2 0 0\n")
    two = parse_touchstone(
        "# HZ S RI R 50\n1 0 0 0.9 0 0.9 0 0 0\n2 0 0 0.9 0 0.9 0 0 0\n", nports=2
    )
    with pytest.raises(ValueError, match="1-port"):
        TouchstoneLoad("a", two)
    with pytest.raises(ValueError, match="2-port"):
        TouchstoneTwoPort("a", "b", one)


# ---------------------------------------------------------------------------
# 3. reducer stamps (synthetic antenna Y; nodal oracle)
# ---------------------------------------------------------------------------
def test_touchstone_load_is_shunt_to_common():
    """A 1-port TouchstoneLoad at the driven port adds y = 1/Z(f): Z = 1/(Y₀₀+y)."""
    y = synth_y(1, 3)
    # S11 = 1/3 → Z = 100, y = 0.01 at z0 = 50
    t = parse_touchstone("# MHZ S RI R 50\n10 0.333333333333 0\n30 0.333333333333 0\n")
    net = Network(
        ports={"a": PortOnWire("a")},
        branches=[TouchstoneLoad("a", t)],
        sources=[Driven(port="a")],
    )
    z = reducer(net, 1).driven_impedance(y, WL)[0]
    assert z == pytest.approx(1.0 / (y[0, 0] + 0.01), rel=1e-9)


def test_touchstone_twoport_matches_augmented_nodal_solve():
    """A driven port + a measured 2-port to a floating port: the branch is a
    pure group-1 stamp, so the reference is the nodal solve of (antenna Y + [Y])."""
    y = synth_y(2, 11)
    # a reciprocal, well-behaved synthetic 2-port, constant across the band
    s = np.array([[0.2 + 0.05j, 0.7 - 0.1j], [0.7 - 0.1j, -0.15 + 0.02j]])
    txt = _s2p_from_matrix([13e6, 15e6], lambda f: s)
    t = parse_touchstone(txt, nports=2)
    net = Network(
        ports={"a": PortOnWire("a"), "b": PortOnWire("b")},
        branches=[TouchstoneTwoPort("a", "b", t)],
        sources=[Driven(port="a")],
    )
    z = reducer(net, 2).driven_impedance(y, WL)[0]
    yblock = t.y_at(C_LIGHT / WL)
    v, i = nodal_reference(y + yblock, {0: 1 + 0j})
    assert z == pytest.approx(v[0] / i[0], rel=1e-9)


def test_degenerate_s2p_of_ideal_tl_equals_TL_element():
    """An .s2p of an ideal lossless line reproduces the TL element's stamp,
    hence the identical driven-port impedance (acceptance criterion)."""
    y = synth_y(2, 5)
    zc, length = 75.0, 3.0
    y_tl = tl_admittance_2x2(zc, length, WL)
    eye = np.eye(2)
    s_tl = (eye - 50.0 * y_tl) @ np.linalg.inv(eye + 50.0 * y_tl)  # Y→S at z0=50
    t = parse_touchstone(_s2p_from_matrix([C_LIGHT / WL], lambda f: s_tl), nports=2)

    def net_with(branch):
        return Network(
            ports={"a": PortOnWire("a"), "b": PortOnWire("b")},
            branches=[branch],
            sources=[Driven(port="a")],
        )

    z_tl = reducer(net_with(TL("a", "b", zc, length)), 2).driven_impedance(y, WL)[0]
    z_ts = reducer(net_with(TouchstoneTwoPort("a", "b", t)), 2).driven_impedance(y, WL)[
        0
    ]
    assert z_ts == pytest.approx(z_tl, rel=1e-9)


# ---------------------------------------------------------------------------
# 4. folder-confined read
# ---------------------------------------------------------------------------
class _B(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0, "design_freq": 14.0})

    def build_wires(self):
        return [Wire((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), n_seg=11, ex=1 + 0j)]


def test_read_touchstone_confined_read_of_fixture():
    t = read_touchstone(_B(), "fixtures/measured_dipole.s1p")
    assert t.nports == 1 and t.z0 == 50.0
    assert t.freqs[0] == pytest.approx(13.5e6) and t.freqs[-1] == pytest.approx(14.5e6)


def test_read_touchstone_rejects_escape():
    with pytest.raises(ValueError, match="outside the design's folder"):
        read_touchstone(_B(), "../secrets.s1p")


def test_read_touchstone_requires_touchstone_extension():
    with pytest.raises(ValueError, match="expected a .s1p or .s2p"):
        read_touchstone(_B(), "fixtures/measured_dipole.txt")
