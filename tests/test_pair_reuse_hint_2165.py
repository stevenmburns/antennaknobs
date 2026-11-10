"""The momwire engine hands its mesh's congruent edge pairs to the solver
(AK#2165 stage 2, momwire#1809), when asked.

Off by default; on by ``pair_reuse=True`` or ``ANTENNAKNOBS_PAIR_REUSE=1``.
momwire checks each claimed pair against its own geometry before copying a
block, so a solve with the hint differs from one without by a few ulp. The
tests that solve skip on a momwire that takes no hint (the recorded pointer
until it passes momwire#1810).
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from antennaknobs import Wire
from antennaknobs.cli import make_engine_factory
from antennaknobs.engines.momwire import _takes_kwarg, _takes_pair_reuse
from antennaknobs.structure import ReuseHint, edges_from_wires, pair_reuse_hint

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
    # The switch also passes offset_reuse (momwire#1809 step 2, 0.87.1), whose
    # route sums each element's own block in another order: 2.3e-13 measured
    # on this Yagi, inside the 1e-12 eval-order tolerance.
    assert np.max(np.abs(z1 - z0) / np.abs(z0)) <= 1e-12


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
    # The switch also passes offset_reuse (momwire#1809 step 2, 0.87.1), whose
    # route sums each element's own block in another order: 2.3e-13 measured
    # on this Yagi, inside the 1e-12 eval-order tolerance.
    assert np.max(np.abs(z1 - z0) / np.abs(z0)) <= 1e-12


def momwire_bspline_module():
    import momwire.bspline as bs

    return bs


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
    f0 = getattr(momwire_bspline_module(), "FREE_OFFSET_EDGES", 0)
    z1 = np.asarray(e.impedance(), dtype=complex)
    assert seen and all(kw.get("offset_reuse") is True for kw in seen)
    assert all("pair_reuse" not in kw for kw in seen)  # nothing repeats
    # Step 1's Toeplitz reg block, or (momwire 0.87.1, step 2) the edge's own
    # block assembled by offset, which replaces it on a whole-mesh fill.
    free = getattr(momwire_bspline_module(), "FREE_OFFSET_EDGES", 0)
    assert K.REG_TOEPLITZ_EDGES + free > c0 + f0
    assert np.max(np.abs(z1 - z0) / np.abs(z0)) <= 1e-12


# --- momwire#1854: the vectorised hint, the decline floor, the digest key ----


def reversed_director_yagi(D):
    """`fed_yagi` with its first director wired the other way round."""
    ws = list(fed_yagi(D).build_wires())
    w = ws[2]
    ws[2] = Wire(w.p1, w.p0, n_seg=w.n_seg)
    return design(ws)


def _end_order_key(e, f):
    pts = [np.asarray(p, float) for p in (e.p0, e.p1, f.p0, f.p1)]
    d = [
        np.linalg.norm(pts[i] - pts[j]) for i, j in itertools.combinations(range(4), 2)
    ]
    return (e is f, e.n, f.n, e.material, f.material, *np.round(np.array(d) / 1e-9))


def test_every_pair_that_repeats_in_end_order_is_in_one_class():
    """A brute-force oracle over every unordered pair of a small grid with a
    reversed director beside it: two pairs go together exactly when one of
    the second's two orders reads the first's six distances in end order,
    which is the copy momwire makes. The pairwise search kept only members
    whose lowest reading needed no reversal, losing those a pair-order swap
    matches."""
    ws = list(wire_grid(cells=3).build_wires()) + list(
        reversed_director_yagi(3).build_wires()
    )
    edges = edges_from_wires(design(ws))
    by_key: dict = {}
    for i, j in itertools.combinations_with_replacement(range(len(edges)), 2):
        e, f = edges[i], edges[j]
        keys = {_end_order_key(e, f), _end_order_key(f, e)}
        by_key.setdefault(min(keys), set()).add(frozenset((i, j)))
    ref = {(e.wire, e.sub): k for k, e in enumerate(edges)}
    classes = [
        {frozenset((ref[a], ref[b])) for a, b in c} for c in pair_reuse_hint(edges)
    ]
    want = [g for g in by_key.values() if len(g) > 1]
    assert sorted(
        map(sorted, map(lambda g: [tuple(sorted(x)) for x in g], classes))
    ) == sorted(map(sorted, map(lambda g: [tuple(sorted(x)) for x in g], want)))


@takes_hint
def test_momwire_takes_every_member_of_the_reordered_hint(monkeypatch):
    e = engine(reversed_director_yagi(6), pair_reuse=True)
    solvers = []
    spy(monkeypatch, e, solvers)
    e.impedance()
    assert solvers
    for s in solvers:
        s._pair_reuse_plan(s._build_geometry())
        assert s.pair_reuse_dropped == ()


def copied_pairs_mean(edges, hint):
    """momwire's per-member count (`_pair_reuse_worth`), over every member
    but the representatives, at one thread, computed from the hint as given."""
    n = {(e.wire, e.sub): e.n for e in edges}
    pairs = [n[a] * n[b] * (2 if a != b else 1) for c in hint for a, b in c[1:]]
    return sum(pairs) / len(pairs)


def test_the_decline_floor_is_the_mean_momwire_takes():
    edges = edges_from_wires(fed_yagi(5))
    full = pair_reuse_hint(edges)
    mean = copied_pairs_mean(edges, full)
    assert pair_reuse_hint(edges, mean * (1 - 1e-9)) == full
    assert pair_reuse_hint(edges, mean * (1 + 1e-9)) == []
    assert pair_reuse_hint(edges, None) == full


def wire_grid(cells=12, side=0.5, h=0.3):
    """A ground screen of one-segment edges, momwire#1854's shape: the hint's
    blocks are 1-2 segment pairs, under momwire's floor of 8."""
    ws = []
    for i in range(cells + 1):
        for j in range(cells):
            ws.append(
                Wire((i * side, j * side, h), (i * side, (j + 1) * side, h), n_seg=1)
            )
            ws.append(
                Wire((j * side, i * side, h), ((j + 1) * side, i * side, h), n_seg=1)
            )
    w = ws[0]
    ws[0] = Wire(w.p0, w.p1, n_seg=1, ex=1 + 0j)
    return design(ws)


def test_a_wire_grid_gets_no_hint_when_momwire_would_decline_it(monkeypatch):
    import antennaknobs.mw._private as private

    monkeypatch.setattr(private, "pair_reuse_min_pairs_per_member", lambda: 8.0)
    e = engine(wire_grid(cells=6), pair_reuse=True)
    assert pair_reuse_hint(edges_from_wires(wire_grid(cells=6)))  # it does repeat
    assert e._pair_reuse_hint() is None
    seen = spy(monkeypatch, e)
    e.impedance()
    assert seen and all("pair_reuse" not in kw for kw in seen)


def test_a_momwire_without_a_floor_keeps_the_hint(monkeypatch):
    import antennaknobs.mw._private as private

    monkeypatch.setattr(private, "pair_reuse_min_pairs_per_member", lambda: None)
    assert engine(wire_grid(cells=6), pair_reuse=True)._pair_reuse_hint()


def test_the_hint_carries_a_digest_of_its_content():
    a = pair_reuse_hint(edges_from_wires(fed_yagi(5)))
    b = pair_reuse_hint(edges_from_wires(fed_yagi(5)))
    c = pair_reuse_hint(edges_from_wires(fed_yagi(6)))
    assert isinstance(a, ReuseHint) and len(a.digest) == 32
    assert a.digest == b.digest != c.digest


def test_the_fill_key_names_the_hint_by_its_digest_not_its_members():
    """Two hints with one digest key alike whatever their members hold, which
    is what lets the key skip pickling them; a plain list is still keyed by
    its content."""
    from antennaknobs.engines.momwire import MomwireEngine, _z_fill_key

    def kw(h):
        return {"feeds": [(0, 0, 1.0)], "pair_reuse": h}

    x, y, z = ReuseHint([[1, 2]]), ReuseHint([["other"]]), ReuseHint([[1, 2]])
    x.digest = y.digest = b"d" * 32
    z.digest = b"e" * 32
    assert _z_fill_key(MomwireEngine, kw(x)) == _z_fill_key(MomwireEngine, kw(y))
    assert _z_fill_key(MomwireEngine, kw(x)) != _z_fill_key(MomwireEngine, kw(z))
    assert _z_fill_key(MomwireEngine, kw([[1, 2]])) != _z_fill_key(
        MomwireEngine, kw([[3, 4]])
    )
