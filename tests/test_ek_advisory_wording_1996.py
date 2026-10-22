"""The "ExtendedKernel" advisory in plain words, and whose choice it was (AK#1996).

G8HUL (antenna-research #1620) opened a deck with no EK card and a ground
stake, read as NEC-4, and was told "This deck asks for the extended (fat-wire)
kernel", with momwire's refusal sentence behind Details: an issue number and a
Python argument. The deck had asked for nothing; the reading turned the kernel
on. So the summary now says which it was, and the details say what was
affected, what caused it, how much it matters and what the app offers.

The engine tests go through `builder_from_text` and `MomwireEngine`, the seam
that composes the advisory in production; the web route's own pins are in
`test_ek_by_dialect_1891.py` and `test_web_nec2_ek_card_1893.py`.
"""

from __future__ import annotations

import logging

import momwire
import pytest
from momwire import (
    BSplineSolver,
    HarringtonSolver,
    RazorSolver,
    SinusoidalGalerkinSolver,
)

from test_ez_import_1958 import DIPOLE, engine_block, ez_file

from antennaknobs import advisory_words
from antennaknobs.engines import MomwireEngine
from antennaknobs.engines.momwire import _capability_refusal
from antennaknobs.file_designs import builder_from_text

MATTERS = " The difference matters for fat wires on short segments."
WHOLE = ", so this whole solve used the standard thin-wire kernel."

WHY_ON = {
    ("dialect", "nec4"): (
        "This deck is read as NEC-4, which is solved with the extended "
        "(fat-wire) kernel."
    ),
    ("dialect", "nec5"): (
        "This deck is read as NEC-5, which is solved with the extended "
        "(fat-wire) kernel."
    ),
    ("ez_engine", "nec4"): (
        "This EZNEC model is set to the NEC-4 engine, so it is solved with the "
        "extended (fat-wire) kernel."
    ),
    ("ez_engine", "nec5"): (
        "This EZNEC model is set to the NEC-5 engine, so it is solved with the "
        "extended (fat-wire) kernel."
    ),
    ("ez_reading", "nec4"): (
        "This EZNEC model is read as NEC-4, which is solved with the extended "
        "(fat-wire) kernel."
    ),
    ("ez_reading", "nec5"): (
        "This EZNEC model is read as NEC-5, which is solved with the extended "
        "(fat-wire) kernel."
    ),
    ("card", None): "This deck's EK card asks for the extended (fat-wire) kernel.",
    ("default", None): (
        "This design is solved with the extended (fat-wire) kernel by default."
    ),
}

CAUSE = {
    "basis": "This solver does not have it",
    "enrichment": "This solver does not have it together with singular enrichment",
    "buried": "It is not available for wires below the ground",
    "stepped": "It is not available where wires of different radii meet",
}

HOW_MUCH = (
    "How much it matters: the two kernels differ where a wire is fat for its "
    "segments. Expect a fraction of a percent where the segments are more "
    "than about 10 wire radii long, and several percent where they are "
    "shorter than about 3. A thin wire on ordinary segments is hardly "
    "affected."
)

FACTS = {
    "buried": {"depth_m": 0.5},
    "stepped": {"joints": [(0.0, 0.0, 0.0)]},
    "basis": {},
    "enrichment": {},
}

DETAILS = {
    "basis": (
        "What was affected: the whole solve. Every wire used the standard "
        "thin-wire kernel. What caused it: the solver chosen for this slot "
        f"has no extended kernel. {HOW_MUCH} What you can do: to solve with "
        "the extended kernel, open the slot's options (the gear beside the "
        'solver slot) and choose a solver that shows the "extended kernel '
        '(EK)" switch.'
    ),
    "enrichment": (
        "What was affected: the whole solve. Every wire used the standard "
        "thin-wire kernel. What caused it: singular enrichment is switched "
        "on for this solver, and the two cannot be used together. "
        f"{HOW_MUCH} What you can do: to solve with the extended kernel, "
        "open the slot's options (the gear beside the solver slot) and "
        'switch off "K≥3 junction singular enrichment".'
    ),
    "buried": (
        "What was affected: the whole solve. Every wire used the standard "
        "thin-wire kernel, not only the wires below the ground. What caused "
        "it: this model has wire below the ground, down to 0.5 m deep. "
        f"{HOW_MUCH} What you can do: to use the extended kernel on the wires "
        "above the ground, open the slot's options (the gear beside the "
        "solver slot) and choose B-spline (the default) or Razor (2-point). "
        "The wires below the ground keep the standard kernel on every solver."
    ),
    "stepped": (
        "What was affected: the whole solve. Every wire used the standard "
        "thin-wire kernel, not only the wires at that joint. What caused it: "
        "wires of different radii meet at x = 0 m, y = 0 m, z = 0 m. "
        f"{HOW_MUCH} What you can do: to solve with the extended kernel, "
        "open the slot's options (the gear beside the solver slot) and "
        "choose another solver. Not every solver has this limit."
    ),
}

SOLVER_CLASSES = sorted(n for n in dir(momwire) if n.endswith("Solver"))
JARGON = ("momwire", "#", "extended_kernel", "=True", "=False", "O(a", "workaround")


def _user_facing_is_plain(text: str) -> None:
    for word in (*JARGON, *SOLVER_CLASSES):
        assert word not in text, (word, text)
    assert "reduced kernel" not in text


def test_momwire_names_solver_classes_to_look_for():
    # The jargon gate below must actually have names to look for.
    assert {"BSplineSolver", "HarringtonSolver", "RazorSolver"} <= set(SOLVER_CLASSES)


@pytest.mark.parametrize("cause", sorted(CAUSE))
@pytest.mark.parametrize(("source", "dialect"), sorted(WHY_ON, key=str))
def test_every_summary(cause, source, dialect):
    summary, details = advisory_words.extended_kernel_fallback(
        cause, source, dialect, FACTS[cause]
    )
    assert summary == f"{WHY_ON[source, dialect]} {CAUSE[cause]}{WHOLE}{MATTERS}"
    # Why the kernel was on does not change what happened or what to do.
    assert details == DETAILS[cause]
    _user_facing_is_plain(summary)
    _user_facing_is_plain(details)


def test_only_a_card_is_said_to_ask():
    for (source, dialect), lead in WHY_ON.items():
        assert ("asks" in lead) is (source == "card"), (source, dialect)


def test_the_causes_and_sources_are_all_covered():
    assert set(CAUSE) == set(advisory_words.EK_CAUSE_WORDS)
    assert {s for s, _d in WHY_ON} == set(advisory_words.EK_SOURCES)


@pytest.mark.parametrize("source", ["dialect", "ez_engine", "ez_reading"])
def test_a_reading_the_words_do_not_know_claims_nothing(source):
    # A source that names a dialect this module has no word for says only
    # what is certain, rather than naming a reading it cannot spell.
    summary, _d = advisory_words.extended_kernel_fallback("basis", source, "nec2")
    assert summary.startswith(WHY_ON["default", None])


def test_facts_the_engine_could_not_supply_are_left_out():
    _s, buried = advisory_words.extended_kernel_fallback("buried")
    assert "this model has wire below the ground. How much" in buried
    _s, stepped = advisory_words.extended_kernel_fallback("stepped")
    assert "wires of different radii meet at a joint. How much" in stepped


@pytest.mark.parametrize(
    ("n", "tail"),
    [(2, " and at 1 other joint."), (4, " and at 3 other joints.")],
)
def test_several_stepped_joints_are_counted(n, tail):
    joints = [(0.0, 1.5, 10.0)] * n
    _s, details = advisory_words.extended_kernel_fallback(
        "stepped", facts={"joints": joints}
    )
    assert f"meet at x = 0 m, y = 1.5 m, z = 10 m{tail}" in details


# --------------------------------------------------------------------------
# through the engine: what the seam knows about why the kernel was on
# --------------------------------------------------------------------------
_DIPOLE = (
    "CM {cm}\nCE\nGW 1 {n} 0 0 -2.5 0 0 2.5 0.001\n{ek}GE 0\n"
    "EX 0 1 11 {i4} 1 0\nFR 0 1 0 0 28.0\nEN\n"
)
NEC4 = _DIPOLE.format(cm="NEC-4.2", n=21, i4=0, ek="")
NEC5 = _DIPOLE.format(cm="NEC-5", n=22, i4=2, ek="")
NEC2_EK = _DIPOLE.format(cm="dipole", n=21, i4=0, ek="EK\n")
NEC2 = _DIPOLE.format(cm="dipole", n=21, i4=0, ek="")
BURIED = (
    "CM NEC-4.2\nCE\nGW 1 11 0 -2 -0.5 0 2 -0.5 0.001\nGE 1\n"
    "GN 2 0 0 0 13 0.005\nEX 0 1 6 0 1 0\nFR 0 1 0 0 14.0\nEN\n"
)
STEPPED = (
    "CM NEC-4.2\nCE\nGW 1 11 0 0 -2.5 0 0 0 0.001\n"
    "GW 2 11 0 0 0 0 0 2.5 0.004\nGE 0\n"
    "EX 0 1 6 0 1 0\nFR 0 1 0 0 28.0\nEN\n"
)


GALERKIN = {"solver": SinusoidalGalerkinSolver}
# B-spline (momwire 0.78, momwire#1170) and razor-2p (momwire 0.82,
# momwire#1614) serve a buried deck in part, so the buried fallback is a
# sinusoidal one.
BURIED_REFUSER = GALERKIN


def _note(text, **kw):
    cls = builder_from_text("d.nec", text)
    kw.setdefault("solver", BSplineSolver)
    if getattr(cls, "file_ground", None) is not None:
        kw.setdefault("ground", cls.file_ground)
    eng = MomwireEngine(cls(), extended_kernel_default=True, **kw)
    assert eng._extended_kernel is False
    (note,) = [a for a in eng.advisories if a["category"] == "ExtendedKernel"]
    assert set(note) == {"category", "text", "summary"}
    _user_facing_is_plain(note["summary"])
    _user_facing_is_plain(note["text"])
    return note, eng


ENRICHED = {"solver_kwargs": {"use_singular_enrichment": True}}


@pytest.mark.parametrize(
    ("text", "kw", "source", "cause"),
    [
        (NEC4, {"solver": HarringtonSolver}, ("dialect", "nec4"), "basis"),
        (NEC5, ENRICHED, ("dialect", "nec5"), "enrichment"),
        (NEC4, ENRICHED, ("dialect", "nec4"), "enrichment"),
        (BURIED, BURIED_REFUSER, ("dialect", "nec4"), "buried"),
        (STEPPED, GALERKIN, ("dialect", "nec4"), "stepped"),
        (NEC2_EK, {"solver": HarringtonSolver}, ("card", None), "basis"),
        (NEC2_EK, ENRICHED, ("card", None), "enrichment"),
        # No card and a NEC-2 reading: the design gives no reason, so the
        # words claim none.
        (NEC2, {"solver": HarringtonSolver}, ("default", None), "basis"),
    ],
    ids=[
        "nec4-basis",
        "nec5-enrichment",
        "nec4-enrichment",
        "nec4-buried",
        "nec4-stepped",
        "card-basis",
        "card-enrichment",
        "unsaid-basis",
    ],
)
def test_the_engine_says_why_the_kernel_was_on_and_why_it_is_not(
    text, kw, source, cause
):
    note, _eng = _note(text, **kw)
    assert note["summary"] == f"{WHY_ON[source]} {CAUSE[cause]}{WHOLE}{MATTERS}"
    assert note["text"] == DETAILS[cause]


# An EZNEC .ez model is not a deck with a dialect: its kernel comes from the
# file's engine setting, or from the reading chosen for it when it is opened.
@pytest.mark.parametrize(
    ("blocks", "chosen", "source"),
    [
        ([engine_block(4, "EZCalc4D_70_x64.EXE")], None, ("ez_engine", "nec4")),
        ([engine_block(8, "Ext NEC-5")], None, ("ez_engine", "nec5")),
        ([], "nec4", ("ez_reading", "nec4")),
        # A chosen reading is the reason even where the file has a setting.
        ([engine_block(4, "EZCalc4D_70_x64.EXE")], "nec5", ("ez_reading", "nec5")),
    ],
    ids=["engine-nec4", "engine-nec5", "chosen-nec4", "chosen-over-engine"],
)
def test_an_eznec_model_names_its_engine_setting_or_its_chosen_reading(
    blocks, chosen, source
):
    raw = ez_file(DIPOLE, blocks=blocks).decode("latin-1")
    cls = builder_from_text("m.ez", raw, dialect=chosen)
    assert cls.file_extended_kernel_source == source
    eng = MomwireEngine(
        cls(),
        solver=HarringtonSolver,
        ground=cls.file_ground,
        extended_kernel_default=True,
    )
    (note,) = [a for a in eng.advisories if a["category"] == "ExtendedKernel"]
    assert note["summary"] == f"{WHY_ON[source]} {CAUSE['basis']}{WHOLE}{MATTERS}"
    assert note["text"] == DETAILS["basis"]
    _user_facing_is_plain(note["summary"])


def test_a_model_with_no_kernel_default_records_no_reason():
    plain = builder_from_text("m.ez", ez_file(DIPOLE).decode("latin-1"))
    assert not plain.file_extended_kernel_default
    assert plain.file_extended_kernel_source is None
    assert builder_from_text("d.nec", NEC2).file_extended_kernel_source is None
    assert builder_from_text("d.nec", NEC4).file_extended_kernel_source == (
        "dialect",
        "nec4",
    )


def test_a_buried_deck_reports_its_own_depth():
    note, _eng = _note(BURIED.replace("-0.5", "-1.25"), **BURIED_REFUSER)
    assert "down to 1.25 m deep." in note["text"]


def test_a_stepped_deck_reports_where_the_radii_meet():
    lowered = STEPPED.replace("0 0 0 0.001", "0 0 -0.5 0.001").replace(
        "GW 2 11 0 0 0 ", "GW 2 11 0 0 -0.5 "
    )
    note, _eng = _note(lowered, **GALERKIN)
    assert "meet at x = 0 m, y = 0 m, z = -0.5 m." in note["text"]


# --------------------------------------------------------------------------
# "What you can do" is a claim about momwire: hold it to the installed one
# --------------------------------------------------------------------------
def _solvers():
    return [getattr(momwire, n) for n in SOLVER_CLASSES]


def test_only_bspline_and_razor_serve_the_extended_kernel_beside_a_buried_wire():
    # The buried details send the user to B-spline or razor-2p, and only
    # there. When another solver serves the extended kernel beside a buried
    # wire, or either of those stops, this fails and the words must be
    # revisited rather than left false.
    served = [
        c.__name__
        for c in _solvers()
        if _capability_refusal(c, "buried", "extended_kernel") is None
    ]
    assert served == ["BSplineSolver", "RazorSolver"]


@pytest.mark.parametrize("solver", [BSplineSolver, RazorSolver])
def test_a_partial_solver_keeps_the_kernel_on_a_buried_deck_and_says_where(solver):
    # No fallback note: the kernel stays on. momwire's own advisory says the
    # buried wires kept the standard kernel, in plain words once summarised.
    cls = builder_from_text("d.nec", BURIED)
    eng = MomwireEngine(
        cls(), solver=solver, ground=cls.file_ground,
        extended_kernel_default=True,
    )  # fmt: skip
    assert eng._extended_kernel is True
    assert not [a for a in eng.advisories if a["category"] == "ExtendedKernel"]
    eng.impedance()
    (note,) = [
        a for a in eng.advisories if a["category"] == "ExtendedKernelAboveGround"
    ]
    assert note["summary"].startswith(
        "The extended (fat-wire) kernel was used on the wires above the ground. "
        "The 1 wire below the ground (of 1) used the standard thin-wire kernel"
    )
    _user_facing_is_plain(note["summary"])


def test_another_solver_does_serve_a_radius_step():
    # The stepped details send the user to another solver.
    cell = ("extended_kernel", "stepped_radius_junction")
    assert _capability_refusal(SinusoidalGalerkinSolver, *cell) is not None
    assert _capability_refusal(BSplineSolver, *cell) is None


def test_some_solver_shows_the_switch_the_basis_details_name():
    assert _capability_refusal(HarringtonSolver, "extended_kernel") is not None
    assert _capability_refusal(BSplineSolver, "extended_kernel") is None


def test_the_solvers_own_refusal_is_kept_for_developers_only(caplog):
    with caplog.at_level(logging.DEBUG, logger="antennaknobs.engines.momwire"):
        note, eng = _note(BURIED, **BURIED_REFUSER)
    raw = eng._kernel_default_refusal
    # momwire's sentence, whatever it says today, reaches the log and the
    # engine attribute, and none of it reaches the user.
    assert raw and raw not in note["text"] and raw not in note["summary"]
    (record,) = [r for r in caplog.records if "extended kernel default" in r.message]
    assert raw in record.getMessage() and "buried" in record.getMessage()
