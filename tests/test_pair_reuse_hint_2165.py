"""The momwire engine hands its mesh's congruent edge pairs to the solver
(AK#2165 stage 2, momwire#1809), when asked.

Off by default; on by ``pair_reuse=True`` or ``ANTENNAKNOBS_PAIR_REUSE=1``.
momwire checks each claimed pair against its own geometry before copying a
block, so a solve with the hint differs from one without by a few ulp. The
tests that solve skip on a momwire that takes no hint (the recorded pointer
until it passes momwire#1810).
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs import Wire
from antennaknobs.cli import make_engine_factory
from antennaknobs.engines.momwire import _takes_kwarg, _takes_pair_reuse
from antennaknobs.structure import edges_from_wires, pair_reuse_hint

from test_structure_2165 import design, yagi

momwire_bspline = pytest.importorskip("momwire").BSplineSolver
takes_hint = pytest.mark.skipif(
    not _takes_pair_reuse(momwire_bspline),
    reason="this momwire's BSplineSolver takes no pair_reuse hint (momwire#1810)",
)


def fed_yagi(D, h=15.0):
    ws = yagi(D, aligned=False, h=h)
    w = ws[1]
    ws[1] = Wire(w.p0, w.p1, n_seg=w.n_seg, ex=1 + 0j)
    return design(ws)


def engine(builder, ground="free", **kw):
    return make_engine_factory("momwire:bspline", ground)(builder, **kw)


def spy(monkeypatch, e, solvers=None):
    """Record the kwargs (and, given a list, the instances) of every solver
    the engine constructs."""
    seen = []

    class Spy(e._solver):
        def __init__(self, **kwargs):
            seen.append(kwargs)
            super().__init__(**kwargs)
            if solvers is not None:
                solvers.append(self)

    monkeypatch.setattr(e, "_solver", Spy)
    return seen


def test_the_hint_names_each_repeated_director_pose():
    """Five directors: one class of director self-blocks and one per spacing
    with two or more pairs (spacings 1-3), the representative first."""
    hint = pair_reuse_hint(edges_from_wires(fed_yagi(5)))
    sizes = sorted(len(c) for c in hint)
    assert sizes == [2, 3, 4, 5]
    selfs = next(c for c in hint if len(c) == 5)
    assert all(a == b for a, b in selfs)


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("ANTENNAKNOBS_PAIR_REUSE", raising=False)
    e = engine(fed_yagi(4))
    seen = spy(monkeypatch, e)
    e.impedance()
    assert seen and all("pair_reuse" not in kw for kw in seen)


@takes_hint
@pytest.mark.parametrize("how", ["kwarg", "env"])
def test_on_passes_the_hint_and_moves_z_by_ulps(monkeypatch, how):
    monkeypatch.delenv("ANTENNAKNOBS_PAIR_REUSE", raising=False)
    z0 = np.asarray(engine(fed_yagi(6)).impedance(), dtype=complex)
    if how == "env":
        monkeypatch.setenv("ANTENNAKNOBS_PAIR_REUSE", "1")
        e = engine(fed_yagi(6))
    else:
        e = engine(fed_yagi(6), pair_reuse=True)
    seen = spy(monkeypatch, e)
    z1 = np.asarray(e.impedance(), dtype=complex)
    assert seen and all(kw.get("pair_reuse") for kw in seen)
    assert np.max(np.abs(z1 - z0) / np.abs(z0)) <= 1e-13


@takes_hint
def test_every_claim_holds_on_the_engines_own_mesh(monkeypatch):
    """The engine's hint comes from the mesh it solves, so momwire drops
    nothing."""
    e = engine(fed_yagi(6), pair_reuse=True)
    solvers = []
    spy(monkeypatch, e, solvers)
    e.impedance()
    assert solvers
    for s in solvers:
        s._pair_reuse_plan(s._build_geometry())
        assert s.pair_reuse_dropped == ()


@takes_hint
def test_over_sommerfeld_ground_the_remainder_copies():
    import momwire.bspline as bs

    acc = bs._acc
    if acc is None or not hasattr(acc, "remainder_q_reused_pairs"):
        pytest.skip("this momwire's remainder kernel takes no copy map")
    g = ("finite", 13.0, 0.005)
    z0 = np.asarray(engine(fed_yagi(4), g).impedance(), dtype=complex)
    c0 = acc.remainder_q_reused_pairs()
    z1 = np.asarray(engine(fed_yagi(4), g, pair_reuse=True).impedance(), dtype=complex)
    assert acc.remainder_q_reused_pairs() > c0
    assert np.max(np.abs(z1 - z0) / np.abs(z0)) <= 1e-13


takes_offset = pytest.mark.skipif(
    not _takes_kwarg(momwire_bspline, "offset_reuse"),
    reason="this momwire's BSplineSolver takes no offset_reuse (momwire#1815)",
)


@takes_offset
def test_the_switch_also_fills_a_straight_wire_by_offset(monkeypatch):
    """One long straight wire has no repeated edge pair, so no hint, but its
    own block repeats by segment offset: the switch passes offset_reuse."""
    import momwire._bspline_kernels as K

    L = 0.5 * 299.792458 / 14.2 * 4
    w = design([Wire((0, -L / 2, 10), (0, L / 2, 10), n_seg=81, ex=1 + 0j)])
    z0 = np.asarray(engine(w).impedance(), dtype=complex)
    e = engine(w, pair_reuse=True)
    seen = spy(monkeypatch, e)
    c0 = K.REG_TOEPLITZ_EDGES
    z1 = np.asarray(e.impedance(), dtype=complex)
    assert seen and all(kw.get("offset_reuse") is True for kw in seen)
    assert all("pair_reuse" not in kw for kw in seen)  # nothing repeats
    assert K.REG_TOEPLITZ_EDGES > c0
    assert np.max(np.abs(z1 - z0) / np.abs(z0)) <= 1e-12
