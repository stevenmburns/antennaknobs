"""`/capabilities` serves which axis values cannot be combined (#1006 G2-4b).

The axes are not freely combinable. momwire#885 measured five cross-axis
couplings and holds them as data, each carrying the prose its own refusal
raises; this is the seam that carries them to a panel, so a greyed-out cell
can say WHY instead of vanishing — #1006 point 4.

THE GATE THAT MATTERS IS ATTRIBUTION. A coupling belongs to the class that
raises it, and the obvious filter — "show the couplings whose `value_a` this
backend can be configured to" — mis-attributes three of the six rows. It would
tell a `bspline` user that the extended kernel forbids `near_correction=False`,
a keyword `BSplineSolver` does not have at all (measured: TypeError, not a
refusal). `applies_to` exists because of that, and the tests below assert the
mis-attribution does NOT happen rather than merely asserting the right rows
appear — a filter that returned everything would satisfy the second and fail
the first.

Matched EXACTLY, not by subclass. `ArrayBlockSolver` inherits
`HMatrixSolver`'s buried refusal but carries its own row, because the two rows
exist precisely to say their solve strategies differ. An `issubclass` match
would hand it both and undo the distinction the amendment was for.

MUTATE THE DATA A GATE READS, NOT THE CODE THAT READS IT — the rule this unit
wrote down in `test_roster_filters_1006.py` after three vacuous gates in one
day. The attribution gates here are checked by moving a row's `applies_to` in
momwire and requiring the served payload to follow.
"""

from __future__ import annotations

import json

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.web.adapter import _BACKENDS, _backend_constraints, backend_roster

_couplings = pytest.importorskip(
    "momwire._couplings", reason="momwire predates momwire#885 (no COUPLINGS table)"
)


def _rows():
    return {r["name"]: r for r in backend_roster(have_pynec=True, have_nec5=True)}


def test_a_backend_is_told_only_about_couplings_that_apply_to_IT():
    """The regression `applies_to` exists to prevent, asserted as an absence.

    `bspline` can be configured to `kernel=extended`, so a reachability filter
    hands it the Galerkin-only rows. It must not: `BSplineSolver` has no
    `near_correction` keyword, and a constraint naming one would be advice
    about a control the user does not have.
    """
    r = _rows()
    forbids = {(c["axis"], c["forbids_axis"]) for c in r["bspline"]["constraints"]}
    assert ("kernel", "near_correction") not in forbids
    assert ("kernel", "junction_ports") not in forbids
    # ...and the row it SHOULD have is there, so this is not passing by
    # returning nothing.
    assert ("kernel", "wire_position") in forbids
    assert len(r["bspline"]["constraints"]) == 1


def test_the_galerkin_pair_is_split_the_right_way_round():
    """`sinusoidal` refuses the point gap; its Galerkin sibling SERVES it.

    Getting this backwards would be invisible in a count — both have
    constraints — so the direction is asserted, not the quantity.
    """
    r = _rows()
    sin = {(c["axis"], c["forbids_axis"]) for c in r["sinusoidal"]["constraints"]}
    sg = {
        (c["axis"], c["forbids_axis"]) for c in r["sinusoidal-galerkin"]["constraints"]
    }
    assert ("testing", "feed_model") in sin
    assert ("testing", "feed_model") not in sg, (
        "the Galerkin solver serves the point gap — that is the whole reason "
        "the pair exists"
    )


def test_the_accelerators_get_their_own_row_not_their_parents():
    """Exact match, not `issubclass`. `ArrayBlockSolver` inherits
    `HMatrixSolver`'s buried refusal; it must still be told about its OWN
    solve strategy and not its parent's, or the two rows stop meaning
    anything."""
    r = _rows()
    hm = {c["value"] for c in r["hmatrix"]["constraints"]}
    ab = {c["value"] for c in r["arrayblock"]["constraints"]}
    assert hm == {"aca"}
    assert ab == {"element-block"}


def test_a_backend_with_no_coupling_says_so_with_an_empty_list():
    """Empty is not None. `razor-2p` has no coupling naming `RazorSolver`, and
    "no constraints" must be distinguishable from "cannot be asked" — the
    frontend renders those differently and inferring one from the other is the
    failure #1103's rule exists for."""
    r = _rows()
    assert r["razor-2p"]["constraints"] == []
    assert r["pynec"]["constraints"] is None
    assert r["nec5"]["constraints"] is None


def test_the_condition_travels_verbatim_and_is_None_when_flat():
    """ "Refused" and "refused when X" are different sentences. Collapsing them
    would tell a user the extended kernel refuses junctions outright — false,
    and it would send them to the wrong workaround, since uniform-radius
    junctions are the common case and are untouched."""
    r = _rows()
    by_axis = {c["forbids_axis"]: c for c in r["sinusoidal-galerkin"]["constraints"]}
    assert by_axis["junction_ports"]["condition"] == "a radius step at the junction"
    assert by_axis["near_correction"]["condition"] is None


def test_the_non_axis_rows_are_served_with_their_marker_not_dropped():
    """A constraint the panel cannot draw as a cell is still a constraint.

    Dropping them here would decide a presentation question in the seam and
    leave a user picking the extended kernel with no warning at all. Served
    with `forbids_is_axis=False`, the frontend decides.
    """
    r = _rows()
    sg = r["sinusoidal-galerkin"]["constraints"]
    assert sg and all(c["forbids_is_axis"] is False for c in sg)
    assert {c["forbids_axis"] for c in sg} == {"near_correction", "junction_ports"}


def test_the_reason_is_momwires_own_prose():
    """Referenced, not retyped — the same string object momwire's refusal
    raises, which is what makes drift impossible rather than unlikely."""
    from momwire._couplings import COUPLINGS

    served = {
        (c["axis"], c["value"], c["forbids_axis"]): c["reason"]
        for row in _rows().values()
        if row["constraints"]
        for c in row["constraints"]
    }
    for c in COUPLINGS:
        key = (c.axis_a, c.value_a, c.axis_b)
        if key in served:
            assert served[key] is c.reason


def test_the_payload_is_json():
    rows = _rows()
    assert json.loads(json.dumps(rows["sinusoidal-galerkin"]))["constraints"]


def test_a_momwire_without_the_table_answers_None():
    """Feature probe, exercised. A version check cannot do this job: momwire
    reported 0.47.0 both before and after the pointer move that brought this
    table, so the version is the same number on both sides of the question."""
    import sys

    spec = next(b for b in _BACKENDS if b.kind == "momwire" and b.solver is not None)
    saved = sys.modules.pop("momwire._couplings", None)
    sys.modules["momwire._couplings"] = None  # makes the import raise ImportError
    try:
        assert _backend_constraints(spec) is None
    finally:
        if saved is not None:
            sys.modules["momwire._couplings"] = saved
        else:
            del sys.modules["momwire._couplings"]
