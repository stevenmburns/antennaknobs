"""A basis that cannot take node gaps refuses with a sentence (#1264).

`dipoles.invvee_apex` has a `PortAtVertex` feed, so the engine passes
`node_gaps=` to whatever solver it was handed. What happened next depended on
how the class declined, which is not a difference a user should be able to
see:

  * `SinusoidalSolver` does not declare the parameter at all, so Python raised
    `TypeError: SinusoidalSolver.__init__() got an unexpected keyword argument
    'node_gaps'` — a bare type error where every other refusal in the catalog
    is a sentence naming what to run instead.
  * `HarringtonSolver` also does not declare it, but absorbs it through
    `**kwargs` and raises momwire's own `NotImplementedError` carrying the
    row's prose. That was already right.

The fix asks the capability ROW rather than the constructor's signature, so
both answer identically. These tests are parametrised over the rows for the
same reason: a hand-list written from the symptom would have named razor too
(the served restriction sentence does — see the last test in this file), and
`RazorSolver` has served node gaps since momwire#603.
"""

from __future__ import annotations

import warnings

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.designs.dipoles.invvee_apex import Builder
from antennaknobs.engines.momwire import MomwireEngine, _node_gaps_refusal
from antennaknobs.web.adapter import (
    _BACKENDS,
    _VERTEX_PORT_BACKENDS,
    _VERTEX_PORT_WITHHELD,
)
from momwire.deck._solver import BASES


def _classes():
    """The distinct solver classes momwire's basis roster names."""
    out = {}
    for cls, _kw in BASES.values():
        out.setdefault(cls.__name__, cls)
    return sorted(out.values(), key=lambda c: c.__name__)


REFUSING = [c for c in _classes() if c.capabilities.node_gaps is False]
SERVING = [c for c in _classes() if c.capabilities.node_gaps is not False]


def _solve(cls):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return complex(MomwireEngine(Builder(), solver=cls).impedance()[0])


def test_the_two_lists_are_both_non_empty():
    """Both parametrised tests below iterate a list built from the rows. If
    either list were empty its test would pass having asserted nothing, which
    is the failure mode this whole file is about."""
    assert REFUSING, "no basis declares node_gaps=False; the guard is untested"
    assert SERVING, "no basis serves node_gaps; the design cannot be solved at all"


@pytest.mark.parametrize("cls", REFUSING, ids=lambda c: c.__name__)
def test_a_basis_that_cannot_take_node_gaps_refuses_with_momwires_sentence(cls):
    """Not a TypeError, and not a sentence of antennaknobs' own invention.

    NOTE ON WHAT EACH ARM PROVES. Only the `SinusoidalSolver` arm changes
    behaviour: `HarringtonSolver` already raised this exception with this
    prose before the guard existed, so its arm passes either way. It is here
    because the guard's whole point is that the two stop differing — an arm
    that would pass anyway still fails if a future momwire makes Harrington
    leak a TypeError the way Sinusoidal did.
    """
    with pytest.raises(NotImplementedError) as ei:
        _solve(cls)
    reason = cls.capabilities.refusal("node_gaps")
    assert reason, f"{cls.__name__} declares node_gaps=False with no prose"
    # The message IS momwire's, not a paraphrase: compared against the row
    # rather than against a literal, so a reworded row cannot leave a stale
    # copy behind here.
    assert reason in str(ei.value), f"{cls.__name__}: {ei.value}"


@pytest.mark.parametrize("cls", SERVING, ids=lambda c: c.__name__)
def test_a_basis_that_serves_node_gaps_still_solves_the_design(cls):
    """The guard must not be a blanket refusal. Every serving basis has to
    come back with a real impedance on the same design — including
    `RazorSolver`, which the served restriction sentence claims cannot."""
    z = _solve(cls)
    assert 10.0 < z.real < 500.0, (cls.__name__, z)
    assert abs(z.imag) < 500.0, (cls.__name__, z)


def test_the_refusal_is_read_from_the_row_and_not_from_the_signature():
    """The bug was that the ANSWER depended on how a class declines: one
    class omits the parameter, another absorbs it through `**kwargs`. Asking
    the row makes those two indistinguishable, so the helper is checked
    directly against the row for every class."""
    for cls in _classes():
        assert _node_gaps_refusal(cls) == cls.capabilities.refusal("node_gaps")


# ----------------------------------------------------------------------
# The served restriction, against the same rows
# ----------------------------------------------------------------------


def _solver_for(name):
    return next(b.solver for b in _BACKENDS if b.name == name)


def test_the_vertex_port_allowlist_never_admits_a_basis_that_refuses():
    """Soundness. Allowing a backend whose row refuses node gaps would put
    the exact TypeError this issue is about back in front of a user, this
    time from a tab the app told them to use."""
    for name in _VERTEX_PORT_BACKENDS:
        spec = next((b for b in _BACKENDS if b.name == name), None)
        if spec is None or spec.kind != "momwire":
            continue  # nec5 is not a momwire class and has no row
        assert _node_gaps_refusal(spec.solver) is None, name


def test_every_serving_backend_is_either_offered_or_named_as_withheld():
    """The bidirectional census, replacing a word test on prose.

    The first spelling of this gate looked for solver family words in
    `_RESTRICTION_REASONS["vertex_ports"]`, and it could not survive contact
    with English: "sinusoidal" names two backends whose rows disagree, and
    once the sentence was corrected to say razor *does* serve the port but is
    not offered, the word was still present in a now-TRUE clause. A substring
    test cannot tell a false claim from a true one, so it is not the gate.

    What is checkable is the STRUCTURE the sentence describes. Every momwire
    backend whose row serves node gaps is either offered for a vertex-port
    design or named in `_VERTEX_PORT_WITHHELD` — checked BOTH ways, so a
    backend can neither drop out of the tab list unremarked nor linger in the
    withheld list after its row changes.
    """
    serving = {
        b.name
        for b in _BACKENDS
        if b.kind == "momwire" and _node_gaps_refusal(b.solver) is None
    }
    assert serving, "no momwire backend serves node gaps"
    offered = serving & set(_VERTEX_PORT_BACKENDS)
    assert offered, "no serving backend is offered; the design would have no tab"
    assert serving - offered == set(_VERTEX_PORT_WITHHELD), (
        f"serving={sorted(serving)} offered={sorted(offered)} "
        f"withheld={sorted(_VERTEX_PORT_WITHHELD)}"
    )


def test_nothing_withheld_is_also_offered():
    """The two lists are a partition, not overlapping opinions."""
    assert not set(_VERTEX_PORT_WITHHELD) & set(_VERTEX_PORT_BACKENDS)
