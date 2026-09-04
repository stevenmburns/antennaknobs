"""`/capabilities` serves what each backend is MADE OF (issue #1006 G2-3).

The served row has always said what a backend SERVES. momwire#882 added the
compositional axes — basis, testing, charge support, kernel, quadrature, solve
strategy, feed model, plus the derived ground model and wire position — and
this is the seam that carries them to the panel, so a user can see that
`bspline` and `hmatrix` are the same physics differing in assembly and that
`sinusoidal-galerkin` differs from `sinusoidal` in the testing.

Three things are gated here, and the third is the one with content.

READ THROUGH `axes_for`, NEVER RE-DERIVED. `ground_model` comes from
`grounds` and `wire_position` from `buried`/`contact`, inside momwire. A
second implementation on this side is the drift momwire's own module refuses
to allow, and the test below compares the served payload against `axes_for`
rather than against a literal, so a re-derivation here fails even if it
happens to agree today.

PROBED AS A FEATURE, NEVER AS A VERSION. The submodule pointer runs ahead of
the PyPI pin by design, so momwire reports the same version with and without
`axes_for` — a version check reads one number in the two cases it exists to
tell apart. `_backend_axes` asks whether the capability row carries the field.

AND THE AXES ARE NOT FREELY COMBINABLE, which is what the panel must respect.
Two couplings are measured, both refusals with named reasons, and both are
gated below because a panel that renders these as independent controls will
offer a user a combination momwire will refuse:

  * `testing=point-matching` forbids `feed_model=point-gap` — a zero-width gap
    on a match point is undefined for point-matched collocation
    (`_reject_point_feed_model`, momwire#212);
  * `solve_strategy` of `aca` or `element-block` forbids
    `wire_position=buried` — the fast operator has no per-segment medium
    (momwire#553 U5).
"""

from __future__ import annotations

import json

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.web.adapter import _BACKENDS, _backend_axes, backend_roster

_HAS_AXES = "axes" in getattr(
    getattr(next(b for b in _BACKENDS if b.kind == "momwire").solver, "capabilities"),
    "_fields",
    (),
)

pytestmark = pytest.mark.skipif(
    not _HAS_AXES,
    reason="momwire predates antennaknobs#1006 G2-1 (no `axes` capability cell)",
)


def _rows():
    return {r["name"]: r for r in backend_roster(have_pynec=True, have_nec5=True)}


def test_every_momwire_backend_describes_itself_and_the_others_say_so():
    """A momwire row carries axes; a non-momwire row answers None.

    None is not "no axes" — it is "this cannot be asked", which the frontend
    renders as *not described*, the same rendering momwire's generated matrix
    already uses for an undeclared row. PyNEC and NEC-5 have no momwire
    capability row at all and their composition is their own wrapper's
    business, so None is the honest answer rather than a gap to fill.
    """
    for name, row in _rows().items():
        if row["kind"] == "momwire":
            assert row["axes"], f"{name}: momwire backend describes nothing"
            assert "basis" in row["axes"] and "solve_strategy" in row["axes"]
        else:
            assert row["axes"] is None, f"{name}: non-momwire row invented axes"


def test_the_payload_is_axes_for_verbatim_and_not_a_re_derivation():
    """The served values ARE `axes_for`'s, including the derived pair.

    This is the gate that matters for drift: `ground_model` and
    `wire_position` are computed inside momwire from `grounds` / `buried` /
    `contact`, and antennaknobs must not learn to compute them too. Comparing
    against `axes_for` rather than against a literal means a re-derivation on
    this side fails here even while it still agrees.
    """
    from momwire._capabilities import axes_for

    for b in _BACKENDS:
        if b.kind != "momwire" or b.solver is None:
            continue
        want = {a: sorted(v) for a, v in axes_for(b.solver.capabilities).items()}
        assert _backend_axes(b) == want, b.name


def test_a_momwire_without_the_feature_answers_None_rather_than_guessing():
    """The feature probe, exercised rather than asserted.

    A version check cannot do this job: the pointer runs ahead of the pin, so
    momwire reports the same version whether or not it has `axes_for`. Here
    the capability row is replaced by one lacking the field, which is what an
    older momwire actually looks like from this side.
    """
    import dataclasses
    from collections import namedtuple

    spec = next(b for b in _BACKENDS if b.kind == "momwire" and b.solver is not None)
    Old = namedtuple("Old", "grounds buried contact")  # no `axes` field
    stand_in = type("OldSolver", (), {"capabilities": Old(frozenset(), False, False)})
    assert _backend_axes(dataclasses.replace(spec, solver=stand_in)) is None


def test_the_payload_is_json_and_stable():
    """Sets are not JSON, and set iteration order is not stable across runs —
    a response fixture built on either would churn. The seam sorts."""
    rows = _rows()
    assert json.loads(json.dumps(rows["bspline"])) == rows["bspline"]
    for values in rows["bspline"]["axes"].values():
        assert values == sorted(values)


# --------------------------------------------------------------------------
# The couplings. These are the content: a panel that treats the axes as
# independent controls offers combinations momwire refuses by name.
# --------------------------------------------------------------------------


def test_the_one_axis_pairs_are_visible_through_the_seam():
    """#1006's opening claim, end to end: each of these pairs differs in the
    one axis the pair exists to isolate, and a user can now see it."""
    r = _rows()
    for a, b, axis in (
        ("hmatrix", "arrayblock", "solve_strategy"),
        ("sinusoidal", "sinusoidal-galerkin", "testing"),
    ):
        differ = {k for k in r[a]["axes"] if r[a]["axes"][k] != r[b]["axes"][k]}
        assert axis in differ, f"{a} vs {b}: {axis} not visible"


def test_point_matching_forbids_the_point_gap_feed():
    """Coupling 1 (momwire#212). `sinusoidal` and `sinusoidal-galerkin` are
    one basis differing in testing — and the testing DRAGS the feed model
    with it, because a zero-width gap sitting on a match point is undefined
    for point-matched collocation. So the pair differs in two axes, and the
    second is forced by the first rather than independent of it."""
    r = _rows()
    assert r["sinusoidal"]["axes"]["testing"] == ["point-matching"]
    assert "point-gap" not in r["sinusoidal"]["axes"]["feed_model"]
    assert r["sinusoidal-galerkin"]["axes"]["testing"] == ["galerkin"]
    assert "point-gap" in r["sinusoidal-galerkin"]["axes"]["feed_model"]


def test_the_accelerators_cannot_reach_the_buried_cell():
    """Coupling 2 (momwire#553 U5). Picking an accelerated assembly REMOVES a
    wire position: the fast operator has no per-segment medium, so `hmatrix`
    and `arrayblock` refuse buried geometry where their dense parent serves
    it. Same physics, same basis, and a strictly smaller reachable space —
    which is exactly the kind of unreachable cell #1006 asks the product
    space to make countable."""
    r = _rows()
    assert "buried" in r["bspline"]["axes"]["wire_position"]
    for accel in ("hmatrix", "arrayblock"):
        assert "buried" not in r[accel]["axes"]["wire_position"], accel
        # ...and nothing else about the geometry moved: still above ground
        # and still in contact with the plane.
        assert r[accel]["axes"]["wire_position"] == ["above", "contact"]
