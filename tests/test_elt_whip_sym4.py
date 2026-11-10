"""verticals.elt_whip:sym4 is the W8IO ELT whip made exactly four-fold (C4v)
about the whip, for symmetry studies: every segment maps onto a segment under
the group, and the four posts carry the same load. The deck's own form keeps
its hand-drawn, not-quite-symmetric outline."""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs.cli import get_builder
from antennaknobs.network import Load


def _segments(name):
    b = get_builder(name)()
    out = []
    for w in b.build_wires():
        if hasattr(w, "p0"):
            p0, p1, n = np.array(w.p0), np.array(w.p1), w.n_seg
        else:
            p0, p1, n = np.array(w[0]), np.array(w[1]), w[2]
        for k in range(n):
            a = p0 + (p1 - p0) * k / n
            c = p1 if k == n - 1 else p0 + (p1 - p0) * (k + 1) / n
            out.append((a, c))
    return b, out


def _key(a, c):
    return tuple(sorted([tuple(np.round(a, 9)), tuple(np.round(c, 9))]))


def _rot(t):
    return np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1]])


C4V = {
    "rotate 90": _rot(np.pi / 2),
    "rotate 180": _rot(np.pi),
    "rotate 270": _rot(3 * np.pi / 2),
    "mirror x": np.diag([-1.0, 1.0, 1.0]),
    "mirror y": np.diag([1.0, -1.0, 1.0]),
    "mirror x=y": np.array([[0.0, 1, 0], [1, 0, 0], [0, 0, 1]]),
    "mirror x=-y": np.array([[0.0, -1, 0], [-1, 0, 0], [0, 0, 1]]),
}


@pytest.mark.parametrize("op", sorted(C4V))
def test_sym4_maps_onto_itself_under_every_c4v_operation(op):
    _b, segs = _segments("verticals.elt_whip:sym4")
    have = {_key(a, c) for a, c in segs}
    M = C4V[op]
    missing = [i for i, (a, c) in enumerate(segs) if _key(M @ a, M @ c) not in have]
    assert not missing, (op, len(missing))


def test_the_deck_form_is_not_four_fold():
    """The control: the deck's outline and its two posts on the x axis break
    the 90-degree turn, so the test above would fail on it."""
    _b, segs = _segments("verticals.elt_whip")
    have = {_key(a, c) for a, c in segs}
    M = C4V["rotate 90"]
    assert any(_key(M @ a, M @ c) not in have for a, c in segs)


def test_sym4s_four_posts_carry_the_same_load():
    b, _segs = _segments("verticals.elt_whip:sym4")
    loads = [br for br in b.build_network().branches if isinstance(br, Load)]
    assert sorted(br.port for br in loads) == ["post0", "post1", "post2", "post3"]
    assert all(br.l is None and br.c == pytest.approx(0.9e-12) for br in loads), loads
