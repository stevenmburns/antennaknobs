"""The `rotational_symmetry` checkbox (momwire#1029's sector route), AK's
half: a bool on `_OPTION_SPECS`, offered per-backend through a live
momwire-capability probe rather than a hand-kept name list, and left OFF the
wire entirely for a backend that does not offer it — on BOTH the hosted and
the local-verbatim request path.

Steve's ask (issue thread, 2026-09-18): enable the route in AK, but not
advertise it — a checkbox on the bspline engine panel, "coded up through the
roster". Unadvertised means: no site page, no release-note headline, no docs
beyond the option's own label and tooltip.

THIS FILE RUNS UNDER WHATEVER MOMWIRE IS ON THE PATH, submodule pointer
(0.58.0, no sector route) included — every assertion here holds true whether
or not momwire has landed #1029, which is the whole point of deriving
exposure from a feature probe instead of a version number. The decks that
need the ROUTE itself (a real sector solve, a real refusal) are
`test_rotational_symmetry_sector_route_1029.py` beside this file, which skips
on the capability when it is absent.
"""

from __future__ import annotations

import warnings

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.cli import resolve_class
from antennaknobs.web import user_designs
from antennaknobs.web.adapter import (
    _BACKENDS,
    _BACKENDS_BY_NAME,
    _OPTION_SPECS,
    _offers_rotational_symmetry,
    _build_builder,
    _make_momwire_engine,
    axis_value_labels,
    backend_roster,
    model_option_specs,
    reword_rotational_symmetry_refusal,
    sanitize_model_options,
)

# Backends whose OWN momwire capability row never carries the sector axis
# value, whatever momwire is on the path: HMatrixSolver and ArrayBlockSolver
# declare a DIFFERENT `solve_strategy` than BSplineSolver
# (`{"aca"}` / `{"element-block"}` vs `{"dense", "sector"}`), and every other
# momwire row is `("dense",)` only. So this list is true under the submodule
# pointer AND under a momwire that has landed #1029 — unlike bspline itself,
# whose answer depends on which momwire is on the path.
NEVER_OFFERS = (
    "hmatrix",
    "arrayblock",
    "sinusoidal",
    "sinusoidal-galerkin",
    "razor-2p",
    "pulse",
)


def test_the_option_is_a_plain_unadvertised_bool():
    spec = _OPTION_SPECS["rotational_symmetry"]
    assert spec.kind == "bool"
    assert spec.default is False
    # No brand, no engine name, no kwarg name in the copy a user reads.
    for forbidden in ("momwire", "bspline", "rotational_symmetry=", "BSplineSolver"):
        assert forbidden not in spec.label
        assert forbidden not in (spec.description or "")


def test_the_served_spec_carries_the_description_as_a_tooltip():
    row = model_option_specs()["rotational_symmetry"]
    assert row["kind"] == "bool"
    assert row["label"] == _OPTION_SPECS["rotational_symmetry"].label
    assert row["description"]
    assert "rotational_symmetry=" not in row["description"]


def test_every_other_served_spec_keeps_its_description_field_and_it_is_usually_none():
    """Adding the field to the NamedTuple must not disturb an existing spec's
    served row — `description` is optional and most options carry none."""
    rows = model_option_specs()
    for key, row in rows.items():
        assert "description" in row
        if key != "rotational_symmetry":
            assert row["description"] is None


def test_backends_whose_own_capability_excludes_sector_never_offer_it():
    """True under ANY momwire — the assertion this file can make without
    caring whether #1029 has landed."""
    for name in NEVER_OFFERS:
        spec = _BACKENDS_BY_NAME[name]
        assert _offers_rotational_symmetry(spec) is False, name


def test_the_roster_never_serves_it_for_those_backends_either():
    rows = {r["name"]: r for r in backend_roster(have_pynec=True, have_nec5=True)}
    for name in NEVER_OFFERS:
        assert "rotational_symmetry" not in rows[name]["model_kwargs"], name


def test_the_families_share_tuple_identity_is_undisturbed():
    """test_backend_model_kwargs_1006.py pins
    `by_name["bspline"] is by_name["hmatrix"] is by_name["arrayblock"]` on the
    STATIC `_BackendSpec.model_kwargs` field. The sector kwarg is appended
    only in the SERVED roster (`backend_roster`), never written into that
    shared tuple, so the identity — and that 1006 test — survive whether or
    not momwire has landed #1029."""
    by_name = {b.name: b.model_kwargs for b in _BACKENDS if b.kind == "momwire"}
    assert by_name["bspline"] is by_name["hmatrix"] is by_name["arrayblock"]
    assert "rotational_symmetry" not in by_name["bspline"]


def test_hosted_sanitiser_accepts_the_key_like_any_other_bool():
    assert sanitize_model_options({"model_options": {"rotational_symmetry": True}}) == {
        "rotational_symmetry": True
    }
    assert sanitize_model_options(
        {"model_options": {"rotational_symmetry": False}}
    ) == {"rotational_symmetry": False}


def test_axis_value_labels_name_the_sector_value_without_the_checkbox_wording():
    labels = axis_value_labels()
    assert labels["solve_strategy"]["sector"] == "sector"
    # It is NOT the checkbox's label — the composition line and the checkbox
    # are two different vocabularies (axis value vs. control caption).
    assert (
        labels["solve_strategy"]["sector"] != _OPTION_SPECS["rotational_symmetry"].label
    )


def test_the_refusal_rewrite_is_a_noop_on_an_unrelated_message():
    msg = "ValueError: wire_radius must be a positive, finite number (got -1)"
    assert reword_rotational_symmetry_refusal(msg) == msg


def test_the_refusal_rewrite_swaps_only_the_tail_it_recognises():
    tail = "Drop rotational_symmetry=True to solve this deck densely."
    msg = f"rotational symmetry: some condition failed. {tail}"
    got = reword_rotational_symmetry_refusal(msg)
    assert got == (
        "rotational symmetry: some condition failed. "
        "Untick 'rotational symmetry (radial screens)' to solve this design densely."
    )
    assert "rotational_symmetry=True" not in got


def test_a_hand_crafted_local_request_cannot_reach_a_backend_that_does_not_offer_it():
    """The local-verbatim path (no hosted whitelist) still drops the flag for
    a backend `_offers_rotational_symmetry` says no to — the code MUST be
    correct under whichever momwire is installed: nothing may raise, and the
    kwarg must never reach a constructor that has no axis for it. Exercised
    on `hmatrix`, which is NEVER offered (see NEVER_OFFERS), so this holds
    under the submodule pointer and under a momwire with #1029 landed alike.
    """
    design = "dipoles.invvee"
    cls = resolve_class(design)
    req = {
        "geometry": design,
        "solver": "momwire",
        "momwire_model": "hmatrix",
        "n_per_wire": 9,
        "model_options": {"rotational_symmetry": True},
    }
    builder = _build_builder(cls, req)
    builder.freq = 14.2
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        eng = _make_momwire_engine(req, builder)
        z = eng.impedance()  # must not raise
    assert z
    sim = eng._solved_cache[1][0]
    # The kwarg never reached the constructor at all — not even as False —
    # so the solver sits on ITS OWN default rather than a value we forced.
    assert getattr(sim, "rotational_symmetry", False) is False


def test_bspline_under_this_installed_momwire_behaves_consistently():
    """Whatever momwire is on THIS path, the roster and the engine must
    agree on whether `rotational_symmetry` was offered to bspline. This is
    the one assertion in this file whose OUTCOME depends on which momwire is
    installed — the file still runs unconditionally because the outcome it
    checks is internal consistency, not a specific answer.

    `dipoles.invvee` has no vertical axis of rotation, so when the route IS
    offered it is refused at construction (a `NotImplementedError`, tested
    properly against a real deck in
    test_rotational_symmetry_sector_route_1029.py); when it is NOT offered
    the flag never reaches the constructor at all and nothing raises. Both
    are "correct under this momwire" — this test asserts whichever one this
    momwire's answer implies, rather than assuming either.
    """
    offered = _offers_rotational_symmetry(_BACKENDS_BY_NAME["bspline"])
    rows = {r["name"]: r for r in backend_roster(have_pynec=True, have_nec5=True)}
    assert ("rotational_symmetry" in rows["bspline"]["model_kwargs"]) is offered

    design = "dipoles.invvee"
    cls = resolve_class(design)
    req = {
        "geometry": design,
        "solver": "momwire",
        "momwire_model": "bspline",
        "n_per_wire": 9,
        "model_options": {"degree": 2, "rotational_symmetry": True},
    }
    builder = _build_builder(cls, req)
    builder.freq = 14.2
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if not offered:
            eng = _make_momwire_engine(req, builder)
            z = eng.impedance()
            assert z
            sim = eng._solved_cache[1][0]
            # The kwarg never reached the constructor — sits on its default.
            assert getattr(sim, "rotational_symmetry", False) is False
        else:
            try:
                eng = _make_momwire_engine(req, builder)
                eng.impedance()
            except NotImplementedError as exc:
                reworded = user_designs.format_solve_error(exc)
                assert "Untick" in reworded
                assert "rotational_symmetry=True" not in reworded
            else:
                pytest.fail(
                    "offered and dipoles.invvee has no rotation axis — "
                    "expected momwire's own geometry refusal"
                )
