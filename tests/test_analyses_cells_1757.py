"""AK#1757, sweep framework step 7 unit 4, the spec half: ``an.Cross(cells=)``,
``an.State(variant=)`` and a group knob's value in a state
(docs/design/sweep-framework-step7.md, the ``cells=`` ruling).

The contract:

- ``cells=`` lists whole cells, a UNION: one curve per listed cell, never
  multiplied with another cross (refused by name), under the cap of 6;
- a cell names its design through its state (``Cell(design=)`` is refused
  and points at that spelling); what it leaves out follows the analysis;
- ``variant=`` builds the state's design at that variant's defaults, and
  needs ``design=``;
- a group knob (fan_dipole's ``bands``) takes a tuple of its entries, each
  a dict of the group's leaves; a shape that does not fit the knob is
  refused by name when the analysis is listed;
- all of it prints back (``to_code``) and reads back (``to_data`` /
  ``from_data``) to an equal value.
"""

from __future__ import annotations

import json

import pytest

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import studies
from antennaknobs.cli import get_builder

INVVEE = "dipoles.invvee"
FAN = "multiband.fandipole"

BANDS = (
    {"freq": 14.3, "length_factor": 0.4892},
    {"freq": 18.1575, "length_factor": 0.4994},
    {"freq": 21.383, "length_factor": 0.4984},
    {"freq": 24.97, "length_factor": 0.4971},
    {"freq": 28.47, "length_factor": 0.49},
)


def _pins() -> an.Analysis:
    return an.Analysis(
        "pins",
        an.Sweep("length_factor", values=(0.95, 1.0)),
        cross=an.Cross(
            cells=(
                an.Cell(an.State("low", design=INVVEE, base=5.0), engine="nec5"),
                an.Cell(
                    an.State("tall", design=INVVEE, variant="dipole", base=12.0),
                    engine="momwire:bspline",
                    ground="finite-fast:13.0,0.005",
                ),
            )
        ),
    )


# ── the values ──────────────────────────────────────────────────────────


def test_a_cell_names_its_state_engine_ground_and_plane():
    st = an.State("tall", design=INVVEE, base=12.0)
    c = an.Cell(st, engine="nec5", ground="free", plane="feed")
    assert (c.state, c.engine, c.ground, c.plane) == (st, "nec5", "free", "feed")
    assert c.label == f"{INVVEE}, tall, nec5, free, feed"
    assert an.Cell().label == ""
    assert hash(c) == hash(an.Cell(st, engine="nec5", ground="free", plane="feed"))


@pytest.mark.parametrize(
    ("make", "err", "words"),
    [
        (
            lambda: an.Cell(design=INVVEE),
            TypeError,
            "names its design through its state",
        ),
        (lambda: an.Cell("x"), TypeError, "state is an an.State or None"),
        (lambda: an.Cell(engine=""), TypeError, "engine is a spec string"),
        (lambda: an.State("x", variant="dipole"), ValueError, "give design= too"),
        (lambda: an.State("x", design=INVVEE, variant="a:b"), TypeError, "variant"),
        (lambda: an.State("x", bands=({"f": 1}, 2)), TypeError, "bands takes a number"),
        (lambda: an.State("x", bands=({},)), TypeError, "bands takes a number"),
        (
            lambda: an.Cross(cells=(an.State("x"),)),
            TypeError,
            "cells holds an.Cell values",
        ),
    ],
)
def test_a_malformed_cell_or_state_is_refused_when_built(make, err, words):
    with pytest.raises(err, match=words):
        make()


def test_cells_never_multiply_with_another_cross():
    with pytest.raises(ValueError, match="does not multiply with another cross"):
        an.Analysis(
            "x",
            an.Sweep("base"),
            cross=(
                an.Cross(cells=(an.Cell(engine="nec5"),)),
                an.Cross(engines=("nec2",)),
            ),
        )


def test_cells_are_a_union_under_the_cap_and_each_listed_once():
    b = get_builder(INVVEE)()
    pins = _pins()
    assert pins.curves == 2 and an.problems(pins, b) == []
    seven = an.Analysis(
        "seven",
        an.Sweep("length_factor"),
        cross=an.Cross(
            cells=tuple(
                an.Cell(an.State(f"s{i}", design=INVVEE, base=5.0 + i))
                for i in range(7)
            )
        ),
    )
    assert an.problems(seven, b) == ["REFUSED: 7 cells = 7 curves, over the cap of 6"]
    twice = an.Analysis(
        "twice",
        an.Sweep("length_factor"),
        cross=an.Cross(cells=(an.Cell(engine="nec5"), an.Cell(engine="nec5"))),
    )
    assert an.problems(twice, b) == ["REFUSED: the cross over cells names 'nec5' twice"]


def test_the_runner_makes_one_cell_per_listed_cell_in_order():
    got = ar.cells(_pins(), "momwire")
    assert [(c.label, c.engine, c.ground, c.design) for c in got] == [
        (f"{INVVEE}, low, nec5", "nec5", None, INVVEE),
        (
            f"{INVVEE}:dipole, tall, momwire:bspline, finite-fast:13.0,0.005",
            "momwire:bspline",
            "finite-fast:13.0,0.005",
            f"{INVVEE}:dipole",
        ),
    ]
    # What a cell leaves out follows the analysis.
    loose = an.Analysis(
        "loose",
        an.Sweep("base"),
        cross=an.Cross(cells=(an.Cell(an.State("a", design=INVVEE)),)),
        engine="nec2",
        ground="pec",
    )
    (c,) = ar.cells(loose, "momwire")
    assert (c.engine, c.ground) == ("nec2", "pec")


def test_a_variant_and_a_group_knob_are_set_as_the_design_writes_them():
    st = an.State("bands", design=FAN, variant="five_band", bands=BANDS)
    assert st.spec == f"{FAN}:five_band" and st.label == f"{FAN}:five_band, bands"
    # Plain data: what a builder is set to, the shape default_params writes.
    assert st.settings == {"bands": BANDS}
    assert all(type(e) is dict for e in st.settings["bands"])
    assert hash(st) == hash(
        an.State("bands", design=FAN, variant="five_band", bands=BANDS)
    )


def test_a_group_knob_of_the_wrong_shape_is_refused_by_name():
    b = get_builder(FAN)()

    def listed(**knobs):
        a = an.Analysis(
            "g",
            an.Sweep(an.FREQUENCY),
            cross=an.Cross(states=(an.State("s", **knobs),)),
        )
        return an.problems(a, b)

    assert listed(bands=BANDS) == []
    assert listed(bands=1.0) == [
        "REFUSED: state 's' sets bands to 1.0, and bands is a group knob: give a "
        "tuple of its entries"
    ]
    assert listed(base=(1.0, 2.0)) == [
        "REFUSED: state 's' sets base to a tuple, and base is a single value, not "
        "a group knob"
    ]
    assert listed(bands=(*BANDS, BANDS[0])) == [
        "REFUSED: state 's' sets bands to 6 entries, and the design's bands holds "
        "at most 5"
    ]
    assert listed(bands=({"freq": 14.3},)) == [
        "REFUSED: state 's' sets bands entry 1 with the leaves freq; the group's "
        "leaves are freq, length_factor"
    ]


def test_cells_variants_and_groups_print_back_and_read_back():
    a = an.Analysis(
        "all of it",
        an.Sweep(an.FREQUENCY, values=(28.0, 28.5)),
        cross=an.Cross(
            cells=(
                *_pins().cross.cells,
                an.Cell(an.State("bands", design=FAN, bands=BANDS), plane="feed"),
            )
        ),
        views=(an.Swr(), an.Rx()),
    )
    text = an.to_code(a)
    assert (
        'variant="dipole"' in text and '{"freq": 28.47, "length_factor": 0.49}' in text
    )
    assert eval(text, {"an": an}) == a
    assert an.from_data(json.loads(json.dumps(an.to_data(a)))) == a
    # Indented, as a study file's list holds it: every line fits from there.
    lines = an.to_code(a, indent=8).splitlines()
    assert 8 + len(lines[0]) <= 88
    assert all(len(line) <= 88 for line in lines[1:])


@pytest.mark.parametrize(
    ("data", "words"),
    [
        ({"an": "os.system"}, "is not a spec value"),
        ({"an": "State", "name": "x", "knobs": [["design", 1]]}, "is not a knob name"),
        (
            {"an": "State", "name": "x", "knobs": [["a", 1], ["a", 2]]},
            "sets a knob twice",
        ),
        ({"an": "Sweep", "knob": "base", "evil": 1}, "has no field 'evil'"),
        (
            {"an": "State", "name": "x", "knobs": [["__import__('os')", 1]]},
            "not a knob",
        ),
    ],
)
def test_from_data_builds_only_spec_values_through_their_constructors(data, words):
    with pytest.raises((TypeError, ValueError), match=words):
        an.from_data(data)


def test_a_study_of_cells_names_its_designs_through_them():
    assert an.named_designs(_pins()) == (INVVEE,)
    assert studies.refusal(_pins()) is None
    loose = an.Analysis(
        "loose", an.Sweep("base"), cross=an.Cross(cells=(an.Cell(engine="nec5"),))
    )
    assert "a study names its designs" in studies.refusal(loose)
    half = an.Analysis(
        "half",
        an.Sweep("base"),
        cross=an.Cross(
            cells=(an.Cell(an.State("a", design=INVVEE)), an.Cell(engine="nec5"))
        ),
    )
    assert studies.refusal(half) == (
        "REFUSED: the cells 'nec5' name no design, and a study has no 'this "
        "design' to set them on; give each its design=, or cross designs=(...) "
        "to set them on every design"
    )
