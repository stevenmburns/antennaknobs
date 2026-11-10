"""verticals.elt_whip:hex6 is the W8IO ELT whip made exactly six-fold (C6v)
about the whip, for symmetry studies: a triangular-lattice ground disc, six
posts and six spokes, and every segment maps onto a segment under all twelve
operations of the group. The deck form and sym4 keep their geometry."""

from __future__ import annotations

import hashlib

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


def _mirror(t):
    """Reflection through the line at angle t in the xy plane."""
    c, s = np.cos(2 * t), np.sin(2 * t)
    return np.array([[c, s, 0], [s, -c, 0], [0, 0, 1]])


C6V = {f"rotate {60 * k}": _rot(np.pi * k / 3) for k in range(6)}
C6V |= {f"mirror {30 * k}": _mirror(np.pi * k / 6) for k in range(6)}


def _unmapped(name, M):
    _b, segs = _segments(name)
    have = {_key(a, c) for a, c in segs}
    return [i for i, (a, c) in enumerate(segs) if _key(M @ a, M @ c) not in have]


def test_c6v_has_twelve_operations():
    assert len(C6V) == 12


@pytest.mark.parametrize("op", sorted(C6V))
def test_hex6_maps_onto_itself_under_every_c6v_operation(op):
    missing = _unmapped("verticals.elt_whip:hex6", C6V[op])
    assert not missing, (op, len(missing))


def test_hex6_is_not_four_fold():
    """The control: a triangular lattice does not survive a 90-degree turn."""
    assert _unmapped("verticals.elt_whip:hex6", _rot(np.pi / 2))


def test_sym4_is_not_six_fold():
    """The other control: the square grid does not survive a 60-degree turn."""
    assert _unmapped("verticals.elt_whip:sym4", _rot(np.pi / 3))


def test_hex6s_six_posts_carry_the_same_load():
    b, _segs = _segments("verticals.elt_whip:hex6")
    loads = [br for br in b.build_network().branches if isinstance(br, Load)]
    assert sorted(br.port for br in loads) == [f"post{k}" for k in range(6)]
    first = loads[0]
    assert all(br.l == first.l and br.c == first.c for br in loads), loads


def test_hex6s_post_feet_sit_on_ground_junctions():
    """Every post foot is a wire endpoint shared, bitwise, with ground wires:
    the radial lattice edges are split there."""
    b = get_builder("verticals.elt_whip:hex6")()
    wires = b.build_wires()
    ends = {}
    for w in wires:
        if hasattr(w, "p0"):
            continue
        for p in (w[0], w[1]):
            ends[p] = ends.get(p, 0) + 1
    posts = [w for w in wires if not hasattr(w, "p0") and len(w) > 4]
    posts = [w for w in posts if w[4].startswith("post")]
    assert len(posts) == 6
    for w in posts:
        assert ends[w[0]] == 3, w  # the post and the two radial pieces


def _wires_digest(name):
    rows = []
    for w in get_builder(name)().build_wires():
        if hasattr(w, "p0"):
            rows.append(repr((tuple(w.p0), tuple(w.p1), w.n_seg, w.spec)))
        else:
            rows.append(repr(tuple(w)))
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


@pytest.mark.parametrize(
    ("name", "digest"),
    [
        (
            "verticals.elt_whip",
            "a4b0dc231c6c07425a5b2478dcc3c9da5a415d85361bfbc8109988cdbb29b1d9",
        ),
        (
            "verticals.elt_whip:sym4",
            "d527f1df43afac79b74311caac04aaa66ca94531647805f442a00e726710daf8",
        ),
    ],
)
def test_the_deck_form_and_sym4_geometry_are_unchanged(name, digest):
    """Pinned before hex6 was added: the hex_grid knob defaults off."""
    assert _wires_digest(name) == digest
