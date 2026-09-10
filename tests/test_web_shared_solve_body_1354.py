"""One web solve body for every card-deck engine lane (#1354).

`pynec_solve` and `nec5_solve` were two ~90-line copies that agreed line for
line except in five places. The duplication was not the cost — #1342 was: the
NEC-5 copy unpacked `NEC5Engine._sources` as 3-tuples after the engine grew a
fourth field, so every multi-feed design broke on that lane while the PyNEC copy
stayed right. A field added to the response, or a bug fixed, had to be applied
twice to be applied at all.

These tests pin the five seams and the two properties the shared body buys:
the lanes cannot drift in shape, and each lane's own rule is preserved rather
than averaged into a single one.
"""

from __future__ import annotations

import pytest

import antennaknobs.web.server  # noqa: F401 — must load before adapter (import cycle)
from antennaknobs.web.adapter import (
    _NEC5_SEAMS,
    _PEC_GROUND_EPS_R,
    _PYNEC_SEAMS,
    _nec5_ground_constants,
    _pynec_ground_constants,
    _SolveSeams,
)
from antennaknobs.web.examples import example_for


class _FakeGround:
    def __init__(self, ground):
        self.ground = ground


def test_both_lanes_are_thin_wrappers_over_one_body():
    """The whole point: neither lane has a body of its own to drift in."""
    ex = example_for("dipoles.invvee")
    for fn in (ex.pynec_solve, ex.nec5_solve):
        names = fn.__code__.co_names + fn.__code__.co_freevars
        assert "_engine_solve" in names, (fn, names)
        # A wrapper, not a copy: one call and a return.
        assert fn.__code__.co_stacksize <= 4, fn.__code__.co_stacksize


def test_the_seams_are_exactly_the_five_differences():
    """A sixth seam is a design change, not a refactor — if one appears, it
    should be argued for rather than arrive."""
    assert _SolveSeams._fields == (
        "make_engine",
        "run",
        "ground_constants",
        "ground_applied",
        "feed_values",
    )


# --------------------------------------------------------------------------
# the #1342 seam
# --------------------------------------------------------------------------


def test_the_nec5_feed_values_seam_reads_four_tuples():
    """#1342 in its new home. `_sources` carries
    `(wire_index, ex_type, value, knot)`; the old NEC-5 copy of the body
    unpacked three and every multi-feed design on that lane broke."""
    eng = type(
        "E", (), {"_sources": [(9, 0, 1 + 0j, "center"), (10, 4, 0.5 - 0.25j, "p0")]}
    )()
    assert _NEC5_SEAMS.feed_values(eng) == [1 + 0j, 0.5 - 0.25j]


def test_the_pynec_feed_values_seam_reads_three_tuples():
    """PyNEC's `excitation_pairs` is `(tag, sub_seg, voltage)` — a different
    shape, which is why this is a seam and not shared code."""
    eng = type("E", (), {"excitation_pairs": [(1, 3, 2 + 1j), (2, 3, 1 + 0j)]})()
    assert _PYNEC_SEAMS.feed_values(eng) == [2 + 1j, 1 + 0j]


def test_a_lane_with_no_sources_yields_no_values_rather_than_raising():
    """`excitation_pairs` can be None; the body pads to len(zs) after."""
    assert _PYNEC_SEAMS.feed_values(type("E", (), {"excitation_pairs": None})()) == []


# --------------------------------------------------------------------------
# the preserved difference
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ground", "pynec_ships_them", "nec5_ships_them"),
    [
        (("finite", 13.0, 0.005), True, True),
        # THE difference. PyNEC ships any tuple ground's constants; NEC-5 only a
        # `finite` one, because its IPERF 0 is full Sommerfeld and it has no
        # reflection-coefficient option, so `finite-fast` never reaches a solve.
        (("finite-fast", 13.0, 0.005), True, False),
        ("pec", False, False),
        (None, False, False),
    ],
)
def test_the_two_ground_rules_are_preserved_not_averaged(
    ground, pynec_ships_them, nec5_ships_them
):
    """A shared body must not quietly change a lane it is only moving. The
    `finite-fast` row is unreachable on the NEC-5 lane today (the engine refuses
    it upstream) and is kept anyway: this is a refactor, and a refactor that
    "tidies" a difference away is a behaviour change wearing the wrong label.
    """
    p = _pynec_ground_constants(_FakeGround(ground))
    n = _nec5_ground_constants(_FakeGround(ground))
    assert (p[0] != _PEC_GROUND_EPS_R) is pynec_ships_them, p
    assert (n[0] != _PEC_GROUND_EPS_R) is nec5_ships_them, n
    if pynec_ships_them:
        assert p == (13.0, 0.005)
    if nec5_ships_them:
        assert n == (13.0, 0.005)


# --------------------------------------------------------------------------
# the run seam, whose ORDER is load-bearing
# --------------------------------------------------------------------------


def test_pynec_runs_impedance_before_currents():
    """`current_distribution()` is what stamps `_excited_efficiency` and
    `_excited_p_in`, which the body reads further down. Reversing these two
    calls would leave the efficiency at its 1.0 fallback on every solve —
    silently, because the fallback is a plausible number."""
    order = []

    class E:
        def impedance(self):
            order.append("z")
            return [50 + 0j]

        def current_distribution(self):
            order.append("i")
            return ["currents"]

    zs, currents = _PYNEC_SEAMS.run(E())
    assert order == ["z", "i"], order
    assert zs == [50 + 0j] and currents == ["currents"]


def test_nec5_runs_one_subprocess_not_two():
    """A web solve must not spawn the binary twice. `solve_snapshot` serves
    impedances, currents and the budget from one printout; the budget is dropped
    here and re-read off the engine by `_budget_rows`, where every lane gets
    it."""
    calls = []

    class E:
        def solve_snapshot(self):
            calls.append("snapshot")
            return ([50 + 0j], ["currents"], {"input_w": 1.0})

        def impedance(self):  # pragma: no cover - must not be reached
            raise AssertionError("a second run")

        def current_distribution(self):  # pragma: no cover - must not be reached
            raise AssertionError("a second run")

    zs, currents = _NEC5_SEAMS.run(E())
    assert calls == ["snapshot"]
    assert zs == [50 + 0j] and currents == ["currents"]


# --------------------------------------------------------------------------
# and the property the shared body buys
# --------------------------------------------------------------------------


def test_the_two_lanes_serve_the_same_response_KEYS(monkeypatch):
    """The drift #1342 was a symptom of, made unrepresentable.

    Run both lanes over one design with a stubbed engine each, and require the
    key sets to be equal. Before the shared body a field could be added to one
    copy and not the other, and nothing said so; the two would have differed
    here.
    """
    pytest.importorskip("PyNEC")
    ex = example_for("dipoles.invvee")
    req = {"geometry": "dipoles.invvee", "measurement_freq_mhz": 28.47}

    pynec_payload = ex.pynec_solve(req)

    # Drive the NEC-5 lane with the SAME engine PyNEC uses, swapped in at the
    # seam: no binary, and any key difference is then the body's, not physics'.
    import antennaknobs.web.adapter as adapter

    monkeypatch.setattr(
        adapter,
        "_NEC5_SEAMS",
        adapter._NEC5_SEAMS._replace(
            make_engine=adapter._PYNEC_SEAMS.make_engine,
            run=adapter._PYNEC_SEAMS.run,
            ground_constants=adapter._PYNEC_SEAMS.ground_constants,
            ground_applied=adapter._PYNEC_SEAMS.ground_applied,
            feed_values=adapter._PYNEC_SEAMS.feed_values,
        ),
    )
    nec5_payload = example_for("dipoles.invvee").nec5_solve(req)
    assert set(pynec_payload) == set(nec5_payload), set(pynec_payload) ^ set(
        nec5_payload
    )
