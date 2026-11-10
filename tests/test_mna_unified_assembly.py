"""One MNA assembly for both solve paths, and what it fixed: a multiport whose
ports repeat a node SUMS its entries there.

`antennaknobs.mw.networks` assembles every network's MNA system once, as COO
triples in stamp order (`_reduce._MNAStamps.triples`), then densifies it below
`_reduce.SPARSE_MIN_UNKNOWNS` or sums it into CSC at and above. Before that,
the dense path stamped a multiport with ``G[np.ix_(idxs, idxs)] += yb``, a
buffered fancy-index add: with ``idxs = [a, a]`` the four entries land on one
element and only one survives. A two-port with both terminals node-to-datum on
one node injects I1 + I2 = (y11 + y12 + y21 + y22)·V there, and that sum is
also what licensed NEC-5 and NEC-4.2 do with an ``NT`` card whose two ends are
one segment (momwire#1887: ``NT 1 6 1 6`` equals ``LD 4`` with
Z = 1/(y11 + 2·y12 + y22) to every printed digit, and a zero-sum Y leaves the
gap open).

Recorded on origin/main 25886e90 (before this change), the 2-port case below
(`test_a_two_port_on_one_node_is_its_summed_one_port`, 14.2 MHz, the antenna
40 − j25 Ω): dense 37.0429 − j19.8409 Ω, which is 1/(y_ant + y22), i.e. y22
alone; forced sparse 22.6262 − j14.7805 Ω, the right answer. The two paths
disagreed, and the dense one is what every real network took. All three
repeated-port tests here fail on that tree, on the dense path.

momwire's own `momwire.networks` still drops them (momwire#1887 is its side),
so repeated-port cases live HERE and not in ``test_mw_networks_ab_2219.py``,
whose cases are byte-for-byte against momwire: there they would fail for the
right reason. When momwire's fix lands, `test_momwire_still_drops_them`
fails, and the cases can join the A/B.
"""

from __future__ import annotations

import contextlib
import math

import momwire.networks as core
import numpy as np
import pytest

import antennaknobs.mw.networks as ak
from antennaknobs.mw.networks import _reduce

C = 299_792_458.0
F_HZ = 14.2e6
WL = C / F_HZ
TOL = 1e-12
#: The antenna one-port the networks hang on.
Y_ANT = np.array([[1.0 / (40.0 - 25.0j)]])

Y2 = np.array([[0.01 + 0.005j, 0.002j], [0.002j, 0.003 + 0j]])
Y3 = np.array(
    [
        [0.012 + 0.004j, -0.003 + 0.001j, 0.002 - 0.0005j],
        [-0.003 + 0.001j, 0.009 - 0.002j, 0.0015j],
        [0.002 - 0.0005j, 0.0015j, 0.006 + 0.003j],
    ]
)


@contextlib.contextmanager
def forced(path):
    old = _reduce.SPARSE_MIN_UNKNOWNS
    _reduce.SPARSE_MIN_UNKNOWNS = 0 if path == "sparse" else 10**12
    try:
        yield
    finally:
        _reduce.SPARSE_MIN_UNKNOWNS = old


def _fold(y, nodes, order):
    """``y`` over ports wired to ``nodes``, as a block over ``order``: each
    port's row and column added onto its node's, i.e. PᵀYP for the port to
    node incidence P."""
    out = np.zeros((len(order), len(order)), dtype=np.complex128)
    at = {n: i for i, n in enumerate(order)}
    for i, ni in enumerate(nodes):
        for j, nj in enumerate(nodes):
            out[at[ni], at[nj]] += y[i, j]
    return out


def _tup(y):
    return tuple(tuple(complex(v) for v in row) for row in y)


def _system(ns, ports, branches, path):
    net = ns.Network(ports=ports, branches=branches, sources=[ns.Driven("ant")])
    idx = {n: i for i, n in enumerate(ports)}
    red = ns.NetworkReducer(net, idx, len(idx))
    with forced(path):
        z = complex(np.ravel(red.driven_impedance(Y_ANT, WL))[0])
        system = red.apply_branches(Y_ANT, WL)
    return z, system


def _assert_same(rep, eq, path, *, exact_z=None):
    (z_rep, s_rep), (z_eq, s_eq) = rep, eq
    assert s_rep.sparse is (path == "sparse")
    assert abs(z_rep - z_eq) <= TOL * abs(z_eq), (path, z_rep, z_eq)
    if exact_z is not None:
        assert abs(z_rep - exact_z) <= TOL * abs(exact_z), (path, z_rep, exact_z)
    # The matrices too, to TOL rather than exactly: the antenna's own entry
    # is the first triple on that node, so the repeated form sums
    # ((y_ant + y11) + y12) + … where the equivalent adds y_ant + Σy.
    a_rep, a_eq = (s.A.toarray() if s.sparse else s.A for s in (s_rep, s_eq))
    assert np.max(np.abs(a_rep - a_eq)) <= TOL * np.max(np.abs(a_eq))


class _Measured:
    """A fixed 2-port `AdmittanceData` (duck-typed)."""

    nports = 2

    def __init__(self, y):
        self._y = np.asarray(y, dtype=np.complex128)

    def y_at(self, f_hz):
        return self._y


PATHS = ("dense", "sparse")


@pytest.mark.parametrize("path", PATHS)
def test_a_two_port_on_one_node_is_its_summed_one_port(path):
    ports = {"ant": ak.PortOnWire("ant")}
    rep = _system(ak, ports, [ak.Admittance(("ant", "ant"), _tup(Y2))], path)
    eq = _system(ak, ports, [ak.Admittance(("ant",), _tup(_fold(Y2, "aa", "a")))], path)
    # The closed form: the antenna in parallel with the summed admittance.
    _assert_same(rep, eq, path, exact_z=1.0 / (Y_ANT[0, 0] + Y2.sum()))


@pytest.mark.parametrize("path", PATHS)
def test_a_three_port_with_a_repeated_pair_is_its_folded_two_port(path):
    # Ports (ant, v, ant): terminals 1 and 3 share the antenna node.
    ports = {"ant": ak.PortOnWire("ant"), "v": ak.PortVirtual("v")}
    shunt = ak.Shunt("v", r=75.0)
    rep = _system(
        ak, ports, [ak.Admittance(("ant", "v", "ant"), _tup(Y3)), shunt], path
    )
    folded = _fold(Y3, ("ant", "v", "ant"), ("ant", "v"))
    eq = _system(ak, ports, [ak.Admittance(("ant", "v"), _tup(folded)), shunt], path)
    # By hand: a 2-port reduced at its far node (Y_v = y22 + 1/75 there).
    yaa = Y3[0, 0] + Y3[0, 2] + Y3[2, 0] + Y3[2, 2]
    yav, yva = Y3[0, 1] + Y3[2, 1], Y3[1, 0] + Y3[1, 2]
    y_in = yaa - yav * yva / (Y3[1, 1] + 1.0 / 75.0)
    _assert_same(rep, eq, path, exact_z=1.0 / (Y_ANT[0, 0] + y_in))


@pytest.mark.parametrize("path", PATHS)
def test_a_touchstone_two_port_on_one_node_is_its_summed_shunt(path):
    ports = {"ant": ak.PortOnWire("ant")}
    rep = _system(ak, ports, [ak.TouchstoneTwoPort("ant", "ant", _Measured(Y2))], path)
    eq = _system(ak, ports, [ak.Admittance(("ant",), _tup(_fold(Y2, "aa", "a")))], path)
    _assert_same(rep, eq, path, exact_z=1.0 / (Y_ANT[0, 0] + Y2.sum()))


def test_momwire_still_drops_them():
    """momwire#1887, momwire's side: its dense stamp keeps one entry (y22,
    measured) rather than the sum. When this fails, momwire sums too: move
    the cases above into the byte-for-byte A/B and delete this test."""
    ports = {"ant": core.PortOnWire("ant")}
    net = core.Network(
        ports=ports,
        branches=[core.Admittance(("ant", "ant"), _tup(Y2))],
        sources=[core.Driven("ant")],
    )
    z = complex(
        np.ravel(core.NetworkReducer(net, {"ant": 0}, 1).driven_impedance(Y_ANT, WL))[0]
    )
    summed = 1.0 / (Y_ANT[0, 0] + Y2.sum())
    assert abs(z - summed) > 1e-3 * abs(summed)


# --- the densify step accumulates in triple order --------------------------------


def test_densify_accumulates_in_triple_order():
    """1e16 + 1 rounds back to 1e16, so the three orders of one entry's
    triples give different sums; `_densify` must give the in-order one."""
    rows = np.zeros(3, dtype=np.int64)
    for order, want in (((0, 1, 2), 0.0), ((0, 2, 1), 1.0), ((2, 1, 0), 0.0)):
        vals = np.array([1e16, 1.0, -1e16], dtype=np.complex128)[list(order)]
        D = _reduce._densify(rows, rows, vals, 1, [])
        assert D[0, 0] == want, (order, D[0, 0])


def test_densify_keeps_a_negative_zero_the_old_code_assigned():
    """An assigned entry starts from −0, so a lone −0j triple lands as −0j
    (the old ``A[col, col] = c_j``), while an added one lands as +0."""
    rows = np.array([0, 1], dtype=np.int64)
    vals = np.array([complex(-0.0, -0.0)] * 2)
    D = _reduce._densify(rows, rows, vals, 2, [(slice(0, 1), slice(0, 1))])
    assert math.copysign(1.0, D[0, 0].real) == -1.0
    assert math.copysign(1.0, D[0, 0].imag) == -1.0
    assert math.copysign(1.0, D[1, 1].real) == 1.0
    assert math.copysign(1.0, D[1, 1].imag) == 1.0


# --- NEC: an NT card with both ends on one segment --------------------------------

_DECK = (
    "CM synthetic: two parallel dipoles, the second's centre loaded\n"
    "CE\n"
    "GW 1 11 0 -5 10 0 5 10 0.001\n"
    "GW 2 11 3 -5 10 3 5 10 0.001\n"
    "GE 0\n"
    "{card}\n"
    "EX 0 1 6 0 1 0\n"
    "FR 0 1 0 0 14.2 0\n"
    "EN\n"
)


def _deck_z(card, y_ant):
    from antennaknobs.nec_import import parse_nec

    net = parse_nec(_DECK.format(card=card), name="t.nec", network=True).network()
    real = [n for n, p in net.ports.items() if not isinstance(p, ak.PortVirtual)]
    # The feed first, then the loaded gap: the order `y_ant` is written in.
    real.sort(key=lambda n: n != "feed")
    idx = {n: i for i, n in enumerate(real)}
    for n in net.ports:
        idx.setdefault(n, len(idx))
    z = ak.NetworkReducer(net, idx, len(idx)).driven_impedance(y_ant, WL)
    return complex(np.ravel(z)[0])


#: A synthetic coupled two-gap admittance (feed, loaded gap).
_Z2 = np.array([[73.0 + 42.0j, 18.0 - 30.0j], [18.0 - 30.0j, 70.0 + 38.0j]])
_Y_ANT2 = np.linalg.inv(_Z2)


def _nt(y11, y12, y22):
    return (
        f"NT 2 6 2 6 {y11.real!r} {y11.imag!r} {y12.real!r} {y12.imag!r} "
        f"{y22.real!r} {y22.imag!r}"
    )


@pytest.mark.parametrize(
    "y11, y12, y22",
    [
        # momwire#1887's measured card: susceptance, so a general Admittance.
        (0.01 + 0.005j, 0.002j, 0.003 + 0j),
        # All real: the importer's resistive pi, whose series leg runs from
        # the node to itself and whose two shunts sum.
        (0.01 + 0j, -0.002 + 0j, 0.004 + 0j),
    ],
)
def test_an_nt_card_on_one_segment_reduces_as_its_ld4(y11, y12, y22):
    zsum = 1.0 / (y11 + 2.0 * y12 + y22)
    z_nt = _deck_z(_nt(y11, y12, y22), _Y_ANT2)
    z_ld = _deck_z(f"LD 4 2 6 6 {zsum.real!r} {zsum.imag!r}", _Y_ANT2)
    assert abs(z_nt - z_ld) <= TOL * abs(z_ld), (z_nt, z_ld)


def test_a_zero_sum_nt_card_on_one_segment_leaves_the_gap_open():
    # Complex, so it imports as an Admittance whose entries cancel.
    z = _deck_z(_nt(0.01 + 0.004j, -0.01 - 0.004j, 0.01 + 0.004j), _Y_ANT2)
    z_open = _Z2[0, 0]  # no current in the second gap
    assert abs(z - z_open) <= TOL * abs(z_open), (z, z_open)
