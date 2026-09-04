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
    """The regression `applies_to` exists to prevent, asserted as an ABSENCE.

    MEMBERSHIP, NEVER A COUNT. This used to assert `len(...) == 1`, which
    stopped meaning anything the moment momwire#888 added four rows — and a
    count cannot distinguish "the right rows" from "some rows". What is
    actually being protected is the mis-attribution: `bspline` can be
    configured to `kernel=extended`, so a filter keyed on value reachability
    would hand it the Galerkin-only rows, and `BSplineSolver` has no
    `near_correction` keyword at all (measured: TypeError, not a refusal). A
    constraint naming one would be advice about a control the user lacks.
    """
    r = _rows()
    forbids = {(c["axis"], c["forbids_axis"]) for c in r["bspline"]["constraints"]}
    # The absence half — this is the guard.
    assert ("kernel", "near_correction") not in forbids
    assert ("kernel", "junction_ports") not in forbids
    # The presence half, so the absence cannot pass by returning nothing.
    assert ("kernel", "wire_position") in forbids
    assert ("kernel", "singular_enrichment") in forbids


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
    """Exact class match, not `issubclass`.

    `ArrayBlockSolver` inherits `HMatrixSolver`'s buried refusal; it must be
    told about its OWN solve strategy and not its parent's, or the two rows
    stop meaning anything. Asserted as membership on the solve_strategy axis
    specifically — the two also share the `contact+refl-coef` row now, so a
    set of ALL their values would no longer separate them.
    """
    r = _rows()
    strat = {
        n: {c["value"] for c in r[n]["constraints"] if c["axis"] == "solve_strategy"}
        for n in ("hmatrix", "arrayblock")
    }
    assert strat["hmatrix"] == {"aca"}
    assert strat["arrayblock"] == {"element-block"}
    # ...and neither carries the other's, which is the actual claim.
    assert "element-block" not in strat["hmatrix"]
    assert "aca" not in strat["arrayblock"]


def test_empty_is_not_None_even_though_no_shipped_BACKEND_is_empty_now():
    """ "No constraints" and "cannot be asked" are different answers.

    This used to ride on `razor-2p == []`. momwire#888's `contact+refl-coef`
    row names all six momwire classes, so NO shipped backend is empty any
    more — and a test asserting the distinction through a backend would have
    quietly stopped exercising the empty case while still passing on the None
    half. So the empty case is now exercised directly on the function that
    produces it, with a spec whose class no coupling names.

    The frontend renders the two differently and inferring one from the other
    is the failure #1103's rule exists for, so the distinction is worth
    keeping a test for even when no real row shows it.
    """
    import dataclasses

    r = _rows()
    assert r["pynec"]["constraints"] is None
    assert r["nec5"]["constraints"] is None

    momwire_spec = next(b for b in _BACKENDS if b.kind == "momwire" and b.solver)

    class _Unnamed:  # a class no COUPLINGS row's applies_to mentions
        capabilities = momwire_spec.solver.capabilities

    got = _backend_constraints(dataclasses.replace(momwire_spec, solver=_Unnamed))
    assert got == [], got
    assert got is not None


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
    with `forbids_is_axis=False`, and the frontend decides.

    Membership rather than "all of them": sinusoidal-galerkin now carries the
    `contact+refl-coef` row too, whose forbidden side IS an axis, so an
    `all(... is False)` sweep would fail for the right payload.
    """
    r = _rows()
    by_axis = {c["forbids_axis"]: c for c in r["sinusoidal-galerkin"]["constraints"]}
    for kwarg_side in ("near_correction", "junction_ports"):
        assert kwarg_side in by_axis
        assert by_axis[kwarg_side]["forbids_is_axis"] is False
    # ...and a genuinely compositional side on the same backend is marked the
    # other way, so the flag is tracking something rather than constant.
    assert by_axis["ground_model"]["forbids_is_axis"] is True


def test_every_served_row_traces_back_to_a_COUPLINGS_row():
    """Completeness, without a count.

    A row can neither appear from nowhere nor vanish silently: every served
    constraint must correspond to a real entry in momwire's table, and every
    entry whose `applies_to` names a served backend must reach that backend.
    Counts were what this file used before and they broke on the first table
    change while proving nothing about correctness; this survives new rows and
    still fails if the seam invents or drops one.
    """
    from momwire._couplings import COUPLINGS

    table = {(c.axis_a, c.value_a, c.axis_b, c.value_b): c for c in COUPLINGS}
    by_name = {b.name: b for b in _BACKENDS}

    for name, row in _rows().items():
        if row["constraints"] is None:
            continue
        served = {
            (c["axis"], c["value"], c["forbids_axis"], c["forbids_value"])
            for c in row["constraints"]
        }
        # Nothing invented.
        unknown = served - set(table)
        assert not unknown, f"{name}: served rows not in COUPLINGS: {sorted(unknown)}"
        # Nothing dropped: every table row naming this class must be served.
        solver_cls = by_name[name].solver
        expected = {
            key
            for key, c in table.items()
            if solver_cls is not None and solver_cls.__name__ in c.applies_to
        }
        assert expected <= served, (
            f"{name}: COUPLINGS names it but the seam dropped "
            f"{sorted(expected - served)}"
        )


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
