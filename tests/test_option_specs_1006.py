"""`_OPTION_SPECS` is one source for the sanitiser AND the schema (#1006 G2-6).

Before this, `_HOSTED_MODEL_OPTIONS` was a dict of opaque closures. Everything
a UI needs in order to RENDER a knob — its type, its range, its enum values,
whether null means auto — existed only as free variables captured inside them,
so the frontend hand-wrote all of it a second time. That second copy is why
`BackendConfigModal` carried a bespoke panel per engine at all.

THE RISK THIS FILE EXISTS FOR is that the rewrite quietly changed what the
hosted endpoint accepts. It is a public boundary: a range that widened by one
is a validation hole, and a rejection message that reworded breaks a client
parsing it. So the OLD behaviour was recorded from the closures BEFORE they
were replaced — 262 (kwarg, input) outcomes over each option's own boundaries
(lo-1, lo, hi, hi+1, midpoint), the wrong types, None, the non-finite floats,
and for enums every member plus case variants — and the derived sanitisers are
required to reproduce it exactly, accept/reject AND message text.

Recorded, not written by hand. A hand-written expectation is a second guess at
the same thing and would have agreed with whatever I believed the closures did.

WHY NOT `__closure__`. Reading the bounds back out of the cell contents was
the obvious shortcut and is deliberately not what ships: it is introspection
archaeology that keeps working right up until a sanitiser is rewritten, and
then reports the old bounds with no error. It was used ONCE, to generate the
baseline below, which is a different thing — that ran against the code it was
describing, at a moment when it was still true.
"""

from __future__ import annotations

import json
import math
import pathlib

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.web.adapter import (
    _AUTO_WHEN_NULL,
    _HOSTED_MODEL_OPTIONS,
    _OPTION_SPECS,
)

BASELINE = json.loads(
    (
        pathlib.Path(__file__).parent / "data/hosted_option_sanitiser_baseline.json"
    ).read_text()
)


def _revive(text: str):
    """The recorded `repr` back into a value.

    `eval` on a repr this file generated itself, over a fixed literal set —
    not client input. `nan`/`inf` need the math names in scope.
    """
    return eval(text, {"nan": math.nan, "inf": math.inf, "__builtins__": {}})  # noqa: S307


def test_the_baseline_is_not_empty_and_covers_every_kwarg():
    """A fixture that lost its contents would make every case below vacuous —
    the failure mode where a check cannot tell "nothing wrong" from "nothing
    measured"."""
    assert set(BASELINE) == set(_HOSTED_MODEL_OPTIONS) == set(_OPTION_SPECS)
    assert len(BASELINE) == 13
    total = sum(len(v) for v in BASELINE.values())
    assert total >= 250, total
    # ...and it must record BOTH outcomes. An all-reject baseline would be
    # satisfied by a sanitiser that refuses everything.
    accepts = sum(1 for v in BASELINE.values() for r in v if r["ok"])
    assert accepts >= 40, accepts
    assert total - accepts >= 40


@pytest.mark.parametrize("key", sorted(BASELINE))
def test_the_derived_sanitiser_matches_the_closure_it_replaced(key):
    """Accept/reject AND the message, character for character."""
    check = _HOSTED_MODEL_OPTIONS[key]
    for rec in BASELINE[key]:
        value = _revive(rec["in"])
        if rec["ok"]:
            got = check(value)
            assert repr(got) == rec["out"], f"{key}({rec['in']}) -> {got!r}"
        else:
            with pytest.raises(Exception) as exc:  # noqa: PT011 — shape is recorded
                check(value)
            assert f"{type(exc.value).__name__}: {exc.value}" == rec["err"], (
                f"{key}({rec['in']}) raised {exc.value!r}, recorded {rec['err']!r}"
            )


def test_every_spec_kind_is_one_the_builder_knows():
    for name, spec in _OPTION_SPECS.items():
        assert spec.kind in ("int", "float", "bool", "enum"), (name, spec.kind)
        if spec.kind in ("int", "float"):
            assert spec.lo is not None and spec.hi is not None, name
            assert spec.lo < spec.hi, name
            assert not spec.values, f"{name}: range kind with enum values"
        if spec.kind == "enum":
            assert len(spec.values) >= 2, name
            assert spec.lo is None and spec.hi is None, name


def test_auto_when_null_is_derived_and_not_restated():
    """The set was a literal beside the dict; it is now a view of the specs.

    Mutating the SPEC must move the set — that is what makes it one fact
    rather than two that agree today. (Mutate the data a gate reads, not the
    code that reads it.)
    """
    assert _AUTO_WHEN_NULL == frozenset({"n_qp_pair"})
    assert _OPTION_SPECS["n_qp_pair"].auto_when_null is True
    assert all(
        not s.auto_when_null for k, s in _OPTION_SPECS.items() if k != "n_qp_pair"
    )


def test_shown_when_names_a_real_option_and_never_encodes_a_refusal():
    """`shown_when` is pure UI gating. A genuine cross-axis refusal is
    momwire's to state and reaches the client through served `constraints` —
    inventing one here would be the retyped-prose failure momwire#888 is
    about, one layer up.

    The specific trap: the extended kernel and singular enrichment are
    mutually exclusive, and it would be easy to spell that as
    `shown_when="not extended_kernel"`. That is a REFUSAL, it belongs to
    momwire, and this asserts nobody wrote it here.
    """
    for name, spec in _OPTION_SPECS.items():
        if spec.shown_when is None:
            continue
        assert spec.shown_when in _OPTION_SPECS, (name, spec.shown_when)
        # TRUTHY, not "is True". `n_qp_source` is shown while
        # `feed_smoothing_factor` is a non-null number, so a gate naming a
        # boolean is the common case and not the rule. What IS required is
        # that the gate can be falsy at all — a gate on a knob that is always
        # set would be a control that never hides, i.e. not a gate.
        gate = _OPTION_SPECS[spec.shown_when]
        assert gate.kind == "bool" or gate.allow_none or gate.auto_when_null, (
            f"{name}: shown_when names {spec.shown_when}, which is neither a "
            "boolean nor nullable — it can never be falsy, so the gate is a "
            "no-op"
        )
        assert "extended_kernel" != spec.shown_when, (
            f"{name}: the EK/enrichment exclusion is a momwire REFUSAL "
            "(momwire#888), not UI gating — it belongs in served constraints"
        )


def test_the_labels_are_present_for_everything_a_panel_must_draw():
    """A generic renderer cannot invent a caption; an unlabelled spec would
    render as a blank field rather than fail loudly."""
    for name, spec in _OPTION_SPECS.items():
        assert spec.label.strip(), name


# --------------------------------------------------------------------------
# What reaches the client
# --------------------------------------------------------------------------


def test_the_catalogue_serves_all_thirteen_and_is_json():
    import json

    from antennaknobs.web.adapter import model_option_specs

    served = model_option_specs()
    assert set(served) == set(_OPTION_SPECS)
    assert len(served) == 13
    assert json.loads(json.dumps(served)) == served


def test_every_served_row_carries_what_a_renderer_needs_for_its_kind():
    """A generic renderer draws from these alone. A row missing its bounds
    would render as an unbounded box that the hosted sanitiser then rejects —
    the control would look available and fail on solve."""
    from antennaknobs.web.adapter import model_option_specs

    for key, row in model_option_specs().items():
        assert row["label"], key
        assert row["kind"] in ("int", "float", "bool", "enum"), key
        if row["kind"] in ("int", "float"):
            assert row["min"] is not None and row["max"] is not None, key
            assert row["step"], key
        if row["kind"] == "enum":
            assert len(row["values"]) >= 2, key
            assert row["default"] in row["values"], key
        if row["kind"] == "bool":
            assert row["default"] in (True, False), key


def test_the_served_ACCEPTS_bounds_are_the_sanitiser_bounds():
    """The claim the whole refactor rests on: one source.

    Now stated against `accepts_min`/`accepts_max`, because `min`/`max` became
    the RENDER pair (#1006 G2-6) and are deliberately narrower. Mutate the
    spec and both the served numbers and the validator must move together;
    asserted by pushing each served accepted bound through the live sanitiser
    and requiring just past it to fail.
    """
    from antennaknobs.web.adapter import _HOSTED_MODEL_OPTIONS, model_option_specs

    for key, row in model_option_specs().items():
        check = _HOSTED_MODEL_OPTIONS[key]
        if row["kind"] not in ("int", "float"):
            continue
        assert check(row["accepts_max"]) is not None
        step = 1 if row["kind"] == "int" else 0.5
        with pytest.raises(ValueError):
            check(row["accepts_max"] + step)
        with pytest.raises(ValueError):
            check(row["accepts_min"] - step)


def test_the_roster_names_only_kwargs_the_catalogue_describes():
    """A backend advertising a knob with no description is a control the
    renderer cannot draw — it would silently vanish rather than fail."""
    from antennaknobs.web.adapter import backend_roster, model_option_specs

    described = set(model_option_specs())
    rows = backend_roster(have_pynec=True, have_nec5=True)
    assert rows
    seen = set()
    for row in rows:
        for k in row["model_kwargs"]:
            assert k in described, f"{row['name']}: {k} has no served spec"
            seen.add(k)
    # ...and the catalogue is not carrying descriptions nobody can reach.
    assert seen == described, f"described but unreachable: {sorted(described - seen)}"


# --------------------------------------------------------------------------
# Render bounds (#1006 G2-6): what the control OFFERS vs what the server TAKES
# --------------------------------------------------------------------------


def test_the_render_range_is_a_SUBSET_of_what_the_sanitiser_accepts():
    """The one shape that must be impossible.

    A control offering a value the endpoint rejects is a knob that looks
    available and fails on solve — the user does the right thing and gets an
    error. The reverse (a control narrower than the sanitiser) is fine and is
    the normal case: `feed_smoothing_factor` offers 0.5..10 of an accepted
    0..100, because the panel has always been the tighter of the two.
    """
    from antennaknobs.web.adapter import model_option_specs

    served = model_option_specs()
    checked = 0
    for key, row in served.items():
        if row["kind"] not in ("int", "float"):
            continue
        assert row["min"] >= row["accepts_min"], f"{key}: render min below accepted"
        assert row["max"] <= row["accepts_max"], f"{key}: render max above accepted"
        checked += 1
    assert checked >= 8, checked


def test_the_subset_gate_is_not_vacuous():
    """At least one option must actually NARROW, or the check above passes for
    a table where render bounds were never set at all."""
    from antennaknobs.web.adapter import model_option_specs

    served = model_option_specs()
    narrowed = [
        k
        for k, r in served.items()
        if r["kind"] in ("int", "float")
        and (r["min"] > r["accepts_min"] or r["max"] < r["accepts_max"])
    ]
    assert "feed_smoothing_factor" in narrowed, narrowed
    assert len(narrowed) >= 4, narrowed


def test_every_render_bound_still_passes_the_sanitiser():
    """The subset claim, exercised rather than compared.

    Pushing the served min and max through the live validator is what proves
    a renderer can offer them — an off-by-one in the subset arithmetic would
    satisfy the comparison above and still hand a user a rejected value.
    """
    from antennaknobs.web.adapter import _HOSTED_MODEL_OPTIONS, model_option_specs

    for key, row in model_option_specs().items():
        if row["kind"] not in ("int", "float"):
            continue
        check = _HOSTED_MODEL_OPTIONS[key]
        assert check(row["min"]) is not None or row["min"] == 0
        assert check(row["max"]) is not None


def test_a_gate_label_exists_wherever_a_knob_can_be_switched_off():
    """A nullable knob renders as a checkbox plus a field, and the checkbox
    needs a caption that `label` does not supply: the gates read
    "n_qp_pair: auto" and "feed source smoothing" against labels of
    "n_qp_pair (GL pts/axis)" and "α (bump width / h_feed)"."""
    for name, spec in _OPTION_SPECS.items():
        if spec.allow_none or spec.auto_when_null:
            assert spec.gate_label, f"{name}: nullable with no gate caption"
        else:
            assert spec.gate_label is None, (
                f"{name}: has a gate caption but nothing to gate"
            )


def test_the_gate_polarity_is_derivable_and_the_two_cases_both_exist():
    """`auto_when_null` means checked-when-null ("auto"); `allow_none` alone
    means checked-when-set. The polarity is therefore not stored — but that
    only works while both cases are real, so both are pinned here."""
    auto = [k for k, s in _OPTION_SPECS.items() if s.auto_when_null]
    optional = [
        k for k, s in _OPTION_SPECS.items() if s.allow_none and not s.auto_when_null
    ]
    assert auto == ["n_qp_pair"], auto
    assert optional == ["feed_smoothing_factor"], optional
