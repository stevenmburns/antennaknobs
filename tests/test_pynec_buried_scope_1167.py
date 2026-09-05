"""PyNEC's buried scope, measured (antennaknobs#1167).

`_backend_serves_buried` answered None for PyNEC — "cannot be asked" — while
the docstring beside it asserted that "PyNEC refuses a wire below z = 0
outright". Measuring that found the opposite, and the opposite in the worst
direction: PyNEC does not refuse a buried wire. It solves one, without
warning, as though the conductor were still in air.

The evidence is PyNEC's own continuity across the interface, which needs no
second engine to be damning. Moving this catalog's buried dipole from 5 cm
above the plane to 5 cm below barely moves PyNEC's impedance — while the
physics changes completely, the conductor going from radiating in air to
immersed in lossy soil. momwire's buried fill shows that change; PyNEC does
not see it.

These tests are the WARRANT for the refusal sentence the roster now serves.
momwire's buried refusals carry momwire's own prose, so the engine is their
source; PyNEC raises nothing to carry, so AK authors the sentence and this
file is the only thing standing behind it. That is a weaker provenance, and
it is why the measurement is pinned here rather than described in a comment.

Gates:

- G-1167-1  PyNEC SOLVES a wholly buried deck — the docstring claim is false,
            asserted directly so it cannot come back.
- G-1167-2  PyNEC's impedance is continuous across the interface where
            momwire's is not: the measurement the sentence quotes.
- G-1167-3  the roster serves False + the sentence + the right issue.
- G-1167-4  a wrapper with no measured row still answers None, tested through
            the mechanism rather than through `nec5`, so the NEC-5 half of
            #1167 can land its row without editing this file.
- G-1167-5  no momwire row moved.
- G-1167-6  `buried_radial_vertical`'s PyNEC refusal is about the graded-mesh
            spelling, NOT about depth — the one place the wrapper does raise
            on a buried deck, and attributing it to burial would have made the
            false docstring look measured.
"""

from __future__ import annotations

import warnings

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.designs.specialty.buried_dipole import Builder as BuriedDipole
from antennaknobs.designs.verticals.buried_radial_vertical import (
    Builder as BuriedRadialVertical,
)
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.pynec import PyNECEngine
from antennaknobs.web.adapter import (
    _BACKENDS,
    _backend_buried_issue,
    _backend_buried_refusal,
    _backend_serves_buried,
    backend_roster,
)

GROUND = ("finite", 10.0, 0.002)


def _spec(name):
    for b in _BACKENDS:
        if b.name == name:
            return b
    raise AssertionError(f"no backend named {name}")


def _dipole_z(engine, depth, **kw):
    b = BuriedDipole()
    b.depth = depth  # +ve is below the interface; the builder sets z = -depth
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return complex(engine(b, ground=GROUND, **kw).impedance()[0])


# --- G-1167-1: PyNEC does not refuse -------------------------------------


def test_g1167_1_pynec_solves_a_wholly_buried_deck():
    """The docstring said PyNEC "refuses a wire below z = 0 outright". It does
    not. Pinned as the positive fact rather than as the absence of a raise, so
    a wrapper that started refusing would fail here loudly and this file would
    be revisited rather than silently over-gating."""
    z = _dipole_z(PyNECEngine, 0.15)
    assert z.real != 0.0 and z.imag != 0.0, z


def test_g1167_1_the_false_docstring_claim_is_gone():
    """The specific sentence, by text. This is the assertion that stops the
    original error returning through a revert or a copy-paste — the claim was
    wrong for years precisely because nothing read it."""
    import antennaknobs.web.adapter as adapter

    src = open(adapter.__file__, encoding="utf-8").read()
    assert "refuses a wire below z = 0 outright" not in src


# --- G-1167-2: the measurement the sentence quotes ------------------------


def test_g1167_2_pynec_barely_notices_the_interface_but_momwire_does():
    """5 cm above vs 5 cm below, one deck, one frequency.

    The bars are deliberately loose — 1.5x and 3x against a measured 1.12x and
    9.7x. The claim is a QUALITATIVE gulf between an engine that models the
    interface and one that does not, and a tight bar would turn a re-mesh or a
    momwire fill improvement into a failure of a fact that had not changed.
    """
    p_above = abs(_dipole_z(PyNECEngine, -0.05))
    p_below = abs(_dipole_z(PyNECEngine, 0.05))
    m_above = abs(_dipole_z(MomwireEngine, -0.05, ground_z=0.0))
    m_below = abs(_dipole_z(MomwireEngine, 0.05, ground_z=0.0))

    pynec_swing = max(p_above, p_below) / min(p_above, p_below)
    momwire_swing = max(m_above, m_below) / min(m_above, m_below)

    assert pynec_swing < 1.5, (
        f"PyNEC moved {pynec_swing:.2f}x across the interface; if it has "
        f"learned the below-interface case, this whole gate is stale"
    )
    assert momwire_swing > 3.0, (
        f"momwire moved only {momwire_swing:.2f}x — the reference for 'the "
        f"physics changes here' is what fell over, not PyNEC"
    )


def test_g1167_2_the_two_engines_agree_ABOVE_the_interface():
    """The control, and the reason the gate above means anything.

    Without it, "PyNEC disagrees with momwire on buried decks" is equally well
    explained by the two engines simply disagreeing. They do not: above the
    plane they track each other, and the divergence appears only on crossing.
    """
    p = abs(_dipole_z(PyNECEngine, -0.05))
    m = abs(_dipole_z(MomwireEngine, -0.05, ground_z=0.0))
    assert 0.5 < p / m < 2.0, (p, m)


# --- G-1167-3: what the roster serves -------------------------------------


def test_g1167_3_pynec_is_served_as_refusing_buried():
    spec = _spec("pynec")
    assert _backend_serves_buried(spec) is False
    assert _backend_buried_issue(spec) == "antennaknobs#1167"


def test_g1167_3_the_sentence_says_what_was_measured():
    """A boolean with no prose forces the gate to invent a reason. This checks
    the prose carries the two facts a user needs — that PyNEC does not refuse,
    and what to use instead — rather than merely being non-empty."""
    reason = _backend_buried_refusal(_spec("pynec"))
    assert reason and len(reason) > 80
    low = reason.lower()
    assert "below" in low
    assert "momwire" in low, "a refusal with no alternative is a dead end"
    assert "antennaknobs#1167" in reason, "the sentence must cite its measurement"


def test_g1167_3_the_row_reaches_the_served_roster():
    row = next(
        r
        for r in backend_roster(have_pynec=True, have_nec5=True)
        if r["name"] == "pynec"
    )
    assert row["buried"] is False
    assert row["buried_refusal"]
    assert row["buried_issue"] == "antennaknobs#1167"


# --- G-1167-4: an unmeasured wrapper still answers None -------------------


def test_g1167_4_an_unmeasured_wrapper_kind_answers_none():
    """Through the MECHANISM, not through `nec5`. The NEC-5 half of #1167 is
    measured on another box and lands after this; a gate naming `nec5` would
    make that a conflict in this file for no reason."""

    class _Stub:
        kind = "no-such-engine"
        solver = None

    stub = _Stub()
    assert _backend_serves_buried(stub) is None
    assert _backend_buried_refusal(stub) is None
    assert _backend_buried_issue(stub) is None


# --- G-1167-5: the momwire rows did not move ------------------------------


@pytest.mark.parametrize(
    "name,buried,issue",
    [
        ("bspline", True, None),
        ("razor-2p", False, "momwire#553"),
        ("hmatrix", False, "momwire#553"),
    ],
)
def test_g1167_5_no_momwire_row_moved(name, buried, issue):
    """The wrapper table must not have reached the momwire path. `bspline`
    carries the True that proves the None-vs-False distinction still works."""
    spec = _spec(name)
    assert _backend_serves_buried(spec) is buried
    assert _backend_buried_issue(spec) == issue
    if buried is False:
        assert _backend_buried_refusal(spec), f"{name} lost its momwire prose"


# --- G-1167-6: the one real PyNEC refusal is not about depth --------------


def test_g1167_6_the_radial_vertical_refusal_is_about_graded_mesh_not_depth():
    """`buried_radial_vertical` IS refused by the PyNEC wrapper — and reading
    that as a burial refusal is exactly the mistake that would have made the
    false docstring look confirmed. It is the graded-mesh spelling, which
    refuses above ground too."""
    b = BuriedRadialVertical()
    with pytest.raises(NotImplementedError) as ei:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            PyNECEngine(b, ground=GROUND).impedance()
    msg = str(ei.value).lower()
    assert "graded" in msg, msg
    assert "below" not in msg and "buried" not in msg, (
        "if this refusal ever becomes a depth refusal, the served capability "
        "and its sentence both need re-measuring"
    )
