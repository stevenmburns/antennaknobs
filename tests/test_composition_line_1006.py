"""The composition line's served vocabulary (#1006 G2-7).

Point 2 of the issue, made visible: each tab states what it is made of, in
words, from `axes` + `bound`. The frontend renders that line and owns none of
its vocabulary — the axes are momwire's, the phrasing is served from here, and
the no-engine-name grep test is what keeps it that way.

WHAT THIS FILE GUARDS is the two ways a line can lie. It can omit something
that matters (an axis that starts varying independently, a value with no
phrase — which would render as a raw token or a blank), or it can assert a
constraint the engine does not have (the pinned-axis rule). A line speaks with
authority about the engine, so a wrong segment is worse than no line.
"""

from __future__ import annotations

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.web.adapter import (
    _COMPOSITION_AXES,
    axis_value_labels,
    backend_roster,
    composition_axes,
)

DERIVED = ("ground_model", "wire_position")


def _rows():
    rows = backend_roster(have_pynec=True, have_nec5=True)
    assert rows, "empty roster — everything below would be vacuous"
    return rows


def test_charge_support_is_still_a_function_of_basis():
    """The reason `charge_support` is NOT on the line.

    Every basis value implies exactly one charge support today, so a segment
    for it would restate the basis segment in other words. That is a
    measurement, not a preference — and if it ever stops being true the line
    is missing something real, so this fails rather than the line quietly
    staying wrong.
    """
    implied: dict[str, set[str]] = {}
    for row in _rows():
        ax = row["axes"]
        if not ax:
            continue
        for basis in ax["basis"]:
            implied.setdefault(basis, set()).update(ax["charge_support"])
    assert implied, "no basis values seen"
    multi = {k: sorted(v) for k, v in implied.items() if len(v) > 1}
    assert not multi, (
        f"charge_support now varies independently of basis ({multi}) — it "
        "should join _COMPOSITION_AXES, because the line is no longer stating "
        "it by implication"
    )


def test_the_line_states_every_axis_that_is_not_derived_or_implied():
    """Nothing silently dropped.

    The six on the line plus `charge_support` (implied, above) must account
    for every non-derived axis any backend declares. An axis nobody listed
    would simply never be shown, and no other test would notice.
    """
    seen: set[str] = set()
    for row in _rows():
        if row["axes"]:
            seen.update(row["axes"])
    unaccounted = seen - set(_COMPOSITION_AXES) - {"charge_support"} - set(DERIVED)
    assert not unaccounted, f"axes no composition segment states: {sorted(unaccounted)}"


def test_every_value_any_backend_can_take_has_a_phrase():
    """A missing phrase renders as a raw momwire token or a blank.

    Both are worse than the value being absent: one leaks internal vocabulary
    into a sentence, the other silently shortens the description.
    """
    labels = axis_value_labels()
    missing = []
    for row in _rows():
        ax = row["axes"]
        if not ax:
            continue
        for axis, values in ax.items():
            if axis in DERIVED:
                continue
            for v in values:
                if v not in labels.get(axis, {}):
                    missing.append(f"{row['name']}: {axis}={v}")
    assert not missing, missing


def test_no_phrase_is_the_raw_value_or_empty():
    """A phrase equal to the token is a placeholder someone forgot to write —
    except where the token IS the English word, which is asserted by name so
    the exception cannot spread silently."""
    SAME_ON_PURPOSE = {
        ("basis", "tent"),
        ("solve_strategy", "dense"),
        ("solve_strategy", "element-block"),
    }
    for axis, values in axis_value_labels().items():
        for value, phrase in values.items():
            assert phrase.strip(), f"{axis}={value} has an empty phrase"
            if phrase == value:
                assert (axis, value) in SAME_ON_PURPOSE, (
                    f"{axis}={value}: phrase is the raw token"
                )


def test_the_axis_order_is_stable_and_reading_order_not_alphabetical():
    """The line is a sentence, so its order is a choice.

    Alphabetical would read "basis · feed_model · kernel · quadrature ·
    solve_strategy · testing", which separates basis from testing — the two
    that together name the method. Pinned so a tidy-up cannot silently
    resort it.
    """
    assert composition_axes() == [
        "basis",
        "testing",
        "kernel",
        "quadrature",
        "solve_strategy",
        "feed_model",
    ]
    assert composition_axes() != sorted(composition_axes())


@pytest.mark.parametrize("name", ["pynec", "nec5"])
def test_a_backend_that_cannot_describe_itself_gets_no_line(name):
    """(e): stated once, never fabricated. `axes: null` is "cannot be asked",
    and a line invented for it would be the one thing this feature must never
    do — assert a composition nobody measured."""
    row = next(r for r in _rows() if r["name"] == name)
    assert row["axes"] is None
