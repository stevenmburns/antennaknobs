"""Do two ``build_wires()`` lists describe the same metal?

``compare_wires(left, right)`` answers for two wire lists (``Wire`` or plain
tuples), ``compare_builders`` for two builder instances, and the CLI's
``compare_wires`` command for two builder specs. The use is checking that two
ways of constructing a design agree — a ``TransformStack`` mirror against the
explicit wires, or either against the ``.nec`` deck it was transcribed from.

What counts as "the same":

* **Order, direction and segment counts are ignored.** A wire is the unordered
  pair of its end points; ``p0``/``p1`` swapped is the same wire.
* **How a run of wire is chopped up is ignored.** Every wire is first cut at
  any end point of EITHER list that lies strictly inside it, so one 2 m wire
  equals two 1 m pieces end to end. An exact duplicate is still extra metal:
  the spans are counted, not just collected.
* **Points within ``tol`` metres are one point.** Distinct points closer than
  ``100 * tol`` are reported as near misses, since a transcription slip often
  looks like that, but do not by themselves make the lists differ.
* **Feeds are compared by position**: the midpoint of each wire carrying
  ``ex``. A design fed through a network (``Driven`` on a named wire, no
  ``ex``) has no feeds here, so only its geometry is compared.
"""

from collections import Counter
from itertools import pairwise
from math import dist
from typing import NamedTuple

from .wire_catalog import as_wire


class WireDiff(NamedTuple):
    """What differs between two wire lists. Spans and points are ``(x, y, z)``
    tuples in metres; ``same`` is true when no span or feed differs."""

    only_left: list  # [(p, q), ...]: spans in the left list and not the right
    only_right: list
    feeds_left: list  # feed midpoints with no match on the other side
    feeds_right: list
    near_misses: list  # [(p, q, distance)]: distinct points within 100 * tol

    @property
    def same(self):
        return not (
            self.only_left or self.only_right or self.feeds_left or self.feeds_right
        )


def _lerp(p, q, t):
    return tuple(a + t * (b - a) for a, b in zip(p, q, strict=True))


def _cut(wires, points, tol):
    """Every wire as its spans, cut at each point lying strictly inside it."""
    spans = []
    for w in wires:
        p0, p1 = tuple(w.p0), tuple(w.p1)
        length = dist(p0, p1)
        if length <= tol:
            continue  # a zero-length wire is no metal
        d = [b - a for a, b in zip(p0, p1, strict=True)]
        ts = set()
        for q in points:
            t = (
                sum((qi - ai) * di for qi, ai, di in zip(q, p0, d, strict=True))
                / length**2
            )
            inside = tol / length < t < 1 - tol / length
            if inside and dist(_lerp(p0, p1, t), q) <= tol:
                ts.add(t)
        knots = [p0] + [_lerp(p0, p1, t) for t in sorted(ts)] + [p1]
        spans += list(pairwise(knots))
    return spans


def compare_wires(left, right, tol=1e-6) -> WireDiff:
    """Compare two ``build_wires()`` lists; ``tol`` is in metres."""
    left = [as_wire(w) for w in left]
    right = [as_wire(w) for w in right]

    # One representative per distinct point, clustering anything within tol.
    reps: list[tuple] = []

    def pid(p):
        for i, r in enumerate(reps):
            if dist(p, r) <= tol:
                return i
        reps.append(tuple(p))
        return len(reps) - 1

    for w in left + right:
        pid(w.p0)
        pid(w.p1)

    def spans(wires):
        return Counter(
            frozenset((pid(p), pid(q))) for p, q in _cut(wires, list(reps), tol)
        )

    def points(counter):
        return [
            tuple(reps[i] for i in sorted(k))
            for k, n in counter.items()
            for _ in range(n)
        ]

    sl, sr = spans(left), spans(right)

    def feeds(wires):
        return [_lerp(w.p0, w.p1, 0.5) for w in wires if w.ex is not None]

    fl, fr = feeds(left), feeds(right)
    near = [
        (p, q, dist(p, q))
        for i, p in enumerate(reps)
        for q in reps[i + 1 :]
        if dist(p, q) <= 100 * tol
    ]
    return WireDiff(
        points(sl - sr),
        points(sr - sl),
        [f for f in fl if not any(dist(f, g) <= tol for g in fr)],
        [g for g in fr if not any(dist(f, g) <= tol for f in fl)],
        near,
    )


def format_diff(diff: WireDiff, names=("left", "right")) -> list[str]:
    """The diff as report lines, one per difference (or one saying none)."""

    def pt(p):
        return "(" + ", ".join(f"{c:.4f}" for c in p) + ")"

    lines = []
    if diff.same:
        lines.append(f"{names[0]} and {names[1]}: same wires and feeds")
    for side, found in ((names[0], diff.only_left), (names[1], diff.only_right)):
        lines += [f"only in {side}: {pt(p)} -> {pt(q)}" for p, q in found]
    for side, found in ((names[0], diff.feeds_left), (names[1], diff.feeds_right)):
        lines += [f"feed only in {side}: at {pt(f)}" for f in found]
    lines += [
        f"close but not the same ({d:.2g} m): {pt(p)} {pt(q)}"
        for p, q, d in diff.near_misses
    ]
    return lines


def compare_builders(left, right, tol=1e-6, names=("left", "right")) -> WireDiff:
    """Compare two builder instances' ``build_wires()``; prints the report."""
    diff = compare_wires(left.build_wires(), right.build_wires(), tol)
    print("\n".join(format_diff(diff, names)))
    return diff


def with_params(cls, **overrides):
    """A ``cls`` builder with some knobs changed. ``AntennaBuilder(params)``
    REPLACES the defaults rather than merging them, so start from them."""
    return cls({**cls.default_params, **overrides})
