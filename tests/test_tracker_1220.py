"""The "keep the target while I drag" tracker (#1220), built on #1202/#1216.

The app's real case is not "optimise" but "I am dragging knob A, hold the
target with the optimise-marked knobs". That is numerical CONTINUATION, and the
cost model is the whole point: a tick costs ONE solve regardless, because the
app must display Z at the new knob position, so what matters is EXTRA solves.

## The guard, and why each clause is here (all measured in #1202/#1216)

- LATCH ON HOLDABILITY, not on the fold. Near a saddle-node the residual curve
  GRAZES zero, so the target stays holdable ~15 ticks past the point where the
  root formally vanishes. Latching at the fold stops a run the user would not
  have noticed anything wrong with.
- ARM ONLY ONCE A TANGENT EXISTS. On the first tick the drag partial is
  unknown, the "prediction" is *do not move*, and its error fires any
  threshold — demote at tick 1, latch at tick 2.
- DEMOTE IS SCALAR ONLY, and is now OFF BY DEFAULT everywhere. It stops the
  thrash when a scalar root folds. The two-knob case has no fold to protect
  against (det(J) stays healthy to the box edge) and its prediction errors
  routinely exceed half the tolerance on a HEALTHY stretch, so enabling it
  there fires ~35 ticks early. Driving the SCALAR path in the running app then
  showed the same failure on a healthy drag (see `Tracker.demote`), so it is
  opt-in via `demote=True` and the gates below opt in explicitly.
- RATE-LIMIT BY DRAG DISTANCE. Four separate per-tick quantities failed to
  survive a change of drag resolution during the study.

Gates:

- G-1220-1  the count/objective check refuses by name, never guesses.
- G-1220-2  tracking a moving root costs ZERO extra solves.
- G-1220-3  the cold-start tick does not fire the guard.
- G-1220-4  holdability latch: the target genuinely unreachable → latched, with
            a message naming the CAUSE (a knob against the end of its
            optimize range, or no root within reach) and the user's fix, with
            the knobs left at their last good value.
- G-1220-5  re-acquire on drag reversal, from pre-freeze history.
- G-1220-6  the two-knob path never demotes.
- G-1220-7  a preempted solve leaves the tracker exactly as it was.
- G-1220-8  the real fold deck from #1202 latches, and not before the target is
            genuinely lost.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from antennaknobs.web.tracker import Tracker, refusal

ONE = [{"name": "hold", "min": 0.0, "max": 1.0}]
TWO = [
    {"name": "h1", "min": 0.0, "max": 1.0},
    {"name": "h2", "min": 0.0, "max": 1.0},
]


def _linear(slope_hold=40.0, slope_drag=-8.0, root=0.5, a0=0.2):
    """X = slope_hold*(hold-root) + slope_drag*(drag-a0): the root walks."""

    def fn(req):
        h, d = float(req["hold"]), float(req["drag"])
        return {
            "z_in_re": 50.0,
            "z_in_im": slope_hold * (h - root) + slope_drag * (d - a0),
            "z0_ohms": 50.0,
        }

    return fn


# ---------------------------------------------------------------------------
# G-1220-1
# ---------------------------------------------------------------------------


def test_swr_is_refused_as_not_a_root():
    msg = refusal("swr", 1)
    assert msg and "minimisation" in msg


@pytest.mark.parametrize(
    "objective,n,want",
    [
        ("resonance", 2, "exactly 1"),
        ("resonance", 0, "exactly 1"),
        ("match_z0", 1, "exactly 2"),
        ("match_z0", 3, "exactly 2"),
    ],
)
def test_the_wrong_knob_count_refuses_with_the_count_in_it(objective, n, want):
    msg = refusal(objective, n)
    assert msg and want in msg and str(n) in msg


def test_the_right_counts_are_accepted():
    assert refusal("resonance", 1) is None
    assert refusal("match_z0", 2) is None


def test_constructing_with_a_bad_count_raises_the_same_message():
    with pytest.raises(ValueError, match="exactly 1"):
        Tracker({"hold": 0.3}, TWO, "resonance", solve_fn=_linear())


# ---------------------------------------------------------------------------
# G-1220-2 / G-1220-3
# ---------------------------------------------------------------------------


def test_tracking_a_moving_root_costs_no_extra_solves():
    t = Tracker({"hold": 0.30, "drag": 0.20}, ONE, "resonance", solve_fn=_linear())
    t.start("drag", 0.20)
    base = t.n_solves
    ok = 0
    for d in np.linspace(0.21, 0.60, 20):
        r = t.tick(float(d))
        ok += bool(r["predicted_ok"])
    assert r["status"] == "tracking", r
    # The root at drag=0.60 is hold = 0.5 + 8*0.4/40 = 0.58.
    assert r["params"]["hold"] == pytest.approx(0.58, abs=0.02)
    assert ok == 20, "the tangent should predict a linear root exactly"
    assert t.n_solves - base == 20, "one solve per tick, no correctors"


def test_the_cold_start_tick_does_not_fire_the_guard():
    """Tick 1 has no drag partial, so its prediction is "do not move" and its
    error fires any threshold. The guard must be unarmed until a tangent
    exists, or every run latches immediately."""
    t = Tracker({"hold": 0.30, "drag": 0.20}, ONE, "resonance", solve_fn=_linear())
    t.start("drag", 0.20)
    assert t.dFda is None, "no tangent yet"
    r = t.tick(0.25)  # a big first step: prediction cannot help
    assert r["status"] == "tracking", r


# ---------------------------------------------------------------------------
# G-1220-4 — holdability latch
# ---------------------------------------------------------------------------


def test_a_target_that_leaves_the_box_latches_with_the_right_wording():
    """The root walks out past hold = 1.0. Once it is unreachable the tracker
    must latch, say the target disappears, and leave the knobs where they last
    worked -- not blame a knob for hitting a limit."""
    t = Tracker(
        {"hold": 0.50, "drag": 0.20},
        ONE,
        "resonance",
        solve_fn=_linear(slope_drag=-40.0),
    )
    t.start("drag", 0.20, drag_span=1.0)
    last_good = None
    # The root is hold = 0.5 + (drag - 0.2), so it walks out of the box past
    # drag = 0.7 and is genuinely unreachable after that.
    for d in np.linspace(0.22, 0.95, 30):
        r = t.tick(float(d))
        if r["status"] == "tracking":
            last_good = r["params"]["hold"]
        if r["status"] == "latched":
            break
    assert r["status"] == "latched", r
    # CAUSE: the knob really is against a bound, so the message must name the
    # limit the user set and can widen -- not the geometry.
    assert t.blocked == ["hold"], ("the corrector was not driven to a bound", t.blocked)
    assert r["message"] == (
        "Resonance not held: hold is at the end of its optimize range "
        "— widen it to keep going"
    ), r["message"]
    assert r["params"]["hold"] == pytest.approx(last_good, abs=1e-9)


# ---------------------------------------------------------------------------
# G-1220-5 — re-acquire on reversal
# ---------------------------------------------------------------------------


def test_reversing_the_drag_re_acquires():
    t = Tracker(
        {"hold": 0.50, "drag": 0.20},
        ONE,
        "resonance",
        solve_fn=_linear(slope_drag=-40.0),
    )
    t.start("drag", 0.20, drag_span=1.0)
    ds = list(np.linspace(0.22, 0.95, 30))
    for d in ds:
        r = t.tick(float(d))
        if r["status"] == "latched":
            break
    assert r["status"] == "latched"
    for d in reversed(ds[:-1]):
        r = t.tick(float(d))
        if r["status"] == "tracking":
            break
    assert r["status"] == "tracking", "dragging back should re-acquire"


def test_two_knobs_at_their_bounds_are_both_named():
    """Match Z0 holds with two knobs, so both can be against a bound at once and
    the sentence has to say so -- naming one would send the user to widen a
    range that is not the whole problem."""

    def out_of_reach(req):
        h1, h2 = float(req["h1"]), float(req["h2"])
        d = float(req["drag"])
        # Both components need to go far past 1.0 as the drag advances, so both
        # clip against the upper bound.
        return {
            "z_in_re": 50.0 + 60.0 * (h1 - (0.5 + 4.0 * (d - 0.2))),
            "z_in_im": 60.0 * (h2 - (0.5 + 4.0 * (d - 0.2))),
            "z0_ohms": 50.0,
        }

    t = Tracker(
        {"h1": 0.5, "h2": 0.5, "drag": 0.2}, TWO, "match_z0", solve_fn=out_of_reach
    )
    t.start("drag", 0.2, drag_span=1.0)
    for d in np.linspace(0.21, 0.60, 30):
        r = t.tick(float(d))
        if r["status"] == "latched":
            break
    assert r["status"] == "latched", r
    # The precondition is on the CORRECTOR'S clipped attempt, not the frozen
    # point: the frozen point is the last value that still held, and on a drag
    # this coarse it sits short of the bound the root went past between ticks.
    assert t.blocked == ["h1", "h2"], (t.blocked, t.frozen)
    assert r["message"] == (
        "Match not held: h1 and h2 are at the ends of their optimize "
        "ranges — widen them to keep going"
    ), r["message"]


def test_the_message_names_the_objective_not_the_method():
    """Match Z0 says "Match", Resonance says "Resonance" -- the user picked an
    objective by that name, not a root-finding method."""
    t = Tracker(
        {"hold": 0.5, "drag": 0.2}, ONE, "resonance", solve_fn=_linear(slope_drag=-40.0)
    )
    t.start("drag", 0.2, drag_span=1.0)
    for d in np.linspace(0.22, 0.95, 30):
        r = t.tick(float(d))
        if r["status"] == "latched":
            break
    assert r["message"].startswith("Resonance not held:"), r["message"]
    # And the retired wording is gone: "here" was a place on a drag the user
    # cannot see, and it named neither the cause nor the fix.
    assert "disappears here" not in r["message"]


# ---------------------------------------------------------------------------
# G-1228 — forward re-acquire, and its limit
# ---------------------------------------------------------------------------


def _root_leaves_and_returns():
    """X = 40*(hold - root(drag)), where root(drag) climbs OUT of the box and
    then comes back down through the value the tracker froze at.

        drag 0.20 -> root 0.50      in the box, tracking
        drag 0.30 -> root 1.00      at the top edge
        drag 0.32 -> root 1.10      gone: nothing in the box holds X = 0
        drag 0.40 -> root 0.70      back, and it passes the frozen value

    The drag only ever increases, so nothing here is a reversal.
    """

    def solve_fn(req):
        h, d = float(req["hold"]), float(req["drag"])
        root = 0.5 + 5.0 * (d - 0.2) - 10.0 * max(d - 0.32, 0.0)
        return {"z_in_re": 50.0, "z_in_im": 40.0 * (h - root), "z0_ohms": 50.0}

    return solve_fn


def test_a_forward_drag_re_acquires_without_reversing():
    """#1228. Reversal-only read as a bug in use: drag forward through a gap
    where the target disappears and out the other side, where it is holdable
    again, and the tracker stayed latched until you dragged back."""
    t = Tracker(
        {"hold": 0.5, "drag": 0.2},
        ONE,
        "resonance",
        solve_fn=_root_leaves_and_returns(),
    )
    t.start("drag", 0.2, drag_span=1.0)
    seen = []
    for d in np.linspace(0.205, 0.45, 50):  # monotonically FORWARD
        seen.append(t.tick(float(d))["status"])
    assert "latched" in seen, "the target must actually be lost in between"
    # ...and it comes back, without the drag ever reversing.
    assert seen[-1] == "tracking", seen[-8:]
    assert seen.index("tracking", seen.index("latched")) > seen.index("latched")


def test_the_general_forward_case_stays_latched():
    """The limit of the rule, not just the rule. When the root reappears
    somewhere OTHER than the frozen point, re-acquiring would need a fresh root
    find while dragging forward -- which is the branch-switching case #1216
    measured (seeding out where the branches have separated handed back 0.9249
    against the user's 0.9150). That stays reversal-only."""

    def elsewhere(req):
        h, d = float(req["hold"]), float(req["drag"])
        # The root climbs out of the box, then reappears far away at 0.10 --
        # nowhere near the ~1.0 the tracker froze at.
        root = 0.5 + 5.0 * (d - 0.2) if d < 0.32 else 0.10
        return {"z_in_re": 50.0, "z_in_im": 40.0 * (h - root), "z0_ohms": 50.0}

    t = Tracker({"hold": 0.5, "drag": 0.2}, ONE, "resonance", solve_fn=elsewhere)
    t.start("drag", 0.2, drag_span=1.0)
    seen = []
    for d in np.linspace(0.205, 0.45, 50):
        seen.append(t.tick(float(d))["status"])
    assert "latched" in seen
    assert seen[-1] == "latched", seen[-8:]


def test_reversal_still_re_acquires_through_the_seeded_path():
    """The two directions re-acquire from DIFFERENT points and both must work:
    forward adopts the frozen point (it is itself a root), reversing runs the
    seeded root find because the branch has come back somewhere the frozen
    point merely happens to be near."""
    t = Tracker(
        {"hold": 0.50, "drag": 0.20},
        ONE,
        "resonance",
        solve_fn=_linear(slope_drag=-40.0),
    )
    t.start("drag", 0.20, drag_span=1.0)
    ds = list(np.linspace(0.22, 0.95, 30))
    for d in ds:
        r = t.tick(float(d))
        if r["status"] == "latched":
            break
    assert r["status"] == "latched"
    for d in reversed(ds[:-1]):
        r = t.tick(float(d))
        if r["status"] == "tracking":
            break
    assert r["status"] == "tracking"


# ---------------------------------------------------------------------------
# G-1220-6 — the two-knob path never demotes
# ---------------------------------------------------------------------------


def test_demote_is_off_unless_asked_for():
    """It demoted four ticks into a healthy real drag and then declared the
    resonance gone (#1220, and see `Tracker.demote`). The holdability latch was
    exact in all 12 study cells without it, so it is opt-in.

    The surface here reproduces the mechanism rather than the deck: the root's
    speed jumps partway through, so the tangent lags and the prediction error
    lands in the 0.5-1 ohm BAND -- above the demote threshold (0.5 x tol) but
    below the corrector's trigger (tol), so nothing ever corrects it and it
    counts against the tangent tick after tick.
    """

    def kinked(req):
        h, d = float(req["hold"]), float(req["drag"])
        # The root walks 25x faster past 0.205, so the first ticks after the
        # kink carry a prediction error the corrector will not touch.
        far = max(d - 0.205, 0.0)
        return {
            "z_in_re": 50.0,
            "z_in_im": 40.0 * (h - 0.5) - 8.0 * (d - 0.2) - 800.0 * far,
            "z0_ohms": 50.0,
        }

    def statuses(**kw):
        t = Tracker({"hold": 0.5, "drag": 0.2}, ONE, "resonance", solve_fn=kinked, **kw)
        # A span of 0.05 with 0.001 steps puts the probe distance at one tick,
        # so the rate limit is not what is under test here.
        t.start("drag", 0.2, drag_span=0.05)
        return {t.tick(float(d))["status"] for d in np.linspace(0.201, 0.212, 12)}

    assert "frozen" not in statuses(), "demote must be off by default"
    # ...and the stage still works for whoever tunes it later.
    assert "frozen" in statuses(demote=True), "the opt-in path must still work"


def test_the_two_knob_path_never_demotes():
    """Demote exists to stop fold thrash. The two-knob case has no fold, and its
    prediction errors routinely exceed half the tolerance on a healthy stretch,
    so enabling it there fires ~35 ticks early (#1216)."""

    def fn(req):
        h1, h2, d = float(req["h1"]), float(req["h2"]), float(req["drag"])
        return {
            "z_in_re": 50.0 + 30.0 * (h2 - 0.6) + 4.0 * (h1 - 0.5) - 5.0 * (d - 0.2),
            "z_in_im": 40.0 * (h1 - 0.5) - 6.0 * (h2 - 0.6) + 3.0 * (d - 0.2),
            "z0_ohms": 50.0,
        }

    # demote=True deliberately: the stage is OFF by default now (it demoted
    # four ticks into a healthy real drag, see `Tracker.demote`), so without
    # opting in this gate would pass for the wrong reason and prove nothing.
    t = Tracker(
        {"h1": 0.5, "h2": 0.6, "drag": 0.2},
        TWO,
        "match_z0",
        solve_fn=fn,
        demote=True,
    )
    t.start("drag", 0.2)
    seen = set()
    for d in np.linspace(0.21, 0.50, 20):
        seen.add(t.tick(float(d))["status"])
    assert "frozen" not in seen, seen


# ---------------------------------------------------------------------------
# G-1220-7 — a cancelled solve must not corrupt the state
# ---------------------------------------------------------------------------


def test_a_preempted_solve_leaves_the_tracker_untouched():
    """The server preempts an in-flight solve the moment a newer request lands,
    so a corrector can be cancelled. `tick` must mutate nothing until every
    solve it needed has returned."""
    boom = {"on": False}
    inner = _linear()

    def fn(req):
        if boom["on"]:
            raise RuntimeError("cancelled")
        return inner(req)

    t = Tracker({"hold": 0.30, "drag": 0.20}, ONE, "resonance", solve_fn=fn)
    t.start("drag", 0.20)
    for d in (0.22, 0.24, 0.26):
        t.tick(d)
    before = (t.x.copy(), t.drag_value, t.mode, t.F.copy(), t.dFda.copy())
    boom["on"] = True
    with pytest.raises(RuntimeError):
        t.tick(0.28)
    assert np.array_equal(t.x, before[0])
    assert t.drag_value == before[1]
    assert t.mode == before[2]
    assert np.array_equal(t.F, before[3])
    assert np.array_equal(t.dFda, before[4])


# ---------------------------------------------------------------------------
# G-1220-8 — the real fold deck from #1202
# ---------------------------------------------------------------------------


class _CoupledPair:
    """The #1202 fold deck. Knobs live on a SUBCLASS, not on an instance: the
    engine re-instantiates the builder class during meshing, so instance
    attributes would not survive."""

    @staticmethod
    def solve_fn(req):
        from types import MappingProxyType

        from antennaknobs.designs.arrays.lumped_coupled_pair import Builder
        from antennaknobs.engines.momwire import MomwireEngine

        class _B(Builder):
            default_params = MappingProxyType(
                {
                    **Builder.default_params,
                    "length_factor": float(req["length_factor"]),
                    "spacing_factor": 0.13,
                    "coupling_l_uH": float(req["coupling_l_uH"]),
                }
            )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            z = complex(MomwireEngine(_B(), ground=None).impedance()[0])
        return {"z_in_re": z.real, "z_in_im": z.imag, "z0_ohms": 50.0}


def test_the_coupled_pair_fold_latches_only_once_the_target_is_lost():
    """`coupling_l_uH` dragged down sinks X(length_factor)'s local maximum
    through zero and the two roots annihilate at L ~ 0.533. #1216 measured that
    the target stays HOLDABLE to L ~ 0.518 -- the curve grazes zero -- so a
    guard that latches at the fold stops ~15 ticks early."""
    free = [{"name": "length_factor", "min": 0.880, "max": 0.960}]
    t = Tracker(
        {"length_factor": 0.9087, "coupling_l_uH": 0.60},
        free,
        "resonance",
        solve_fn=_CoupledPair.solve_fn,
    )
    s = t.start("coupling_l_uH", 0.60)
    assert s["status"] == "tracking", s
    latched_at = None
    for i, L in enumerate(np.linspace(0.595, 0.495, 15), 1):
        r = t.tick(float(L))
        if r["status"] == "latched":
            latched_at = float(L)
            break
    assert latched_at is not None, "the branch does end in this range"
    # Not before the fold at 0.533, and not far past where it is still holdable.
    assert latched_at < 0.533, ("latched before the roots even merged", latched_at)
    assert latched_at > 0.500, ("latched far too late", latched_at)
    # CAUSE: nothing is against a bound here -- the two roots annihilated, so
    # the target itself is gone and widening a range would not bring it back.
    assert t.blocked == [], ("the fold case must not be blocked by the box", t.blocked)
    assert r["message"] == (
        "Resonance not held: none within reach — drag back to recover it"
    ), r["message"]
