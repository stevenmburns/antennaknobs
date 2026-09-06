"""One knob to X = 0 is a SCALAR ROOT, so solve it with a secant (#1202).

The #1202 study measured, over `beams.moxon` and a 12-radial buried vertical
from a tuned and a far start, distinct solves to |X| <= 1 ohm:

    Nelder-Mead      11 / 10 / 11 / 16
    secant            4 /  4 /  3 /  3

The secant wins over a finite-difference Newton (5/5/3/3) for a structural
reason worth keeping: it REUSES its previous iterate, so it costs one new
solve per step where a FD derivative costs two.

## What is guarded, and why each guard is here

- **Single feed only.** `_objective_value(.., "resonance")` is `max(abs(X))`
  over the feeds. An absolute value has no sign change to bracket, and a
  minimax over several ports generally has no common root at all. So the
  branch asks `_signed_reactance` for a SIGNED scalar and steps aside when
  there isn't one — multi-feed runs are bit-for-bit the Nelder-Mead runs they
  were.
- **One knob only.** Two knobs to X = 0 is a curve of solutions, not a point.
- **No root in the box is REPORTED, not parked on.** A bracket scan that finds
  no sign change means the residual has no zero in the box. That falls back to
  Nelder-Mead and says so in `method`; it must never look like success.

## Tolerances

`_ROOT_XTOL` is deliberately the same 1e-4 Nelder-Mead passes as `xatol`, so
switching methods does not change how tightly a knob is resolved. `_ROOT_FTOL`
(1e-3 ohm) is where a root is called found. Neither is the study's 1 ohm
REPORTING tolerance — that is how the study scored a run, not where one stops.
The shipped path converges about three orders past it for one to two extra
solves, which is why the counts here run a little above the study's.

Gates:

- G-1202-1  a single-feed one-knob `resonance` run takes the secant, and
            reaches a residual far below the study's reporting tolerance.
- G-1202-2  it costs no more solves than Nelder-Mead, on both study decks
            from both starts, through the shipped `optimize()`.
- G-1202-3  multi-feed steps aside: same method, same answer as before.
- G-1202-4  every other objective and any 2-knob run is untouched.
- G-1202-5  no root in the box fails CLEANLY: the residual is reported, the
            reason is named, and the params are the best SOLVED point.
- G-1202-6  progress stays gapless (#1007) and carries `phase`/`residual`.
"""

from __future__ import annotations

import warnings

import pytest

from antennaknobs.web.optimize import _ROOT_FTOL, optimize

ONE = [{"name": "k", "min": 0.0, "max": 1.0}]


def _linear_x(root=0.62, seen=None):
    """X(k) with a single sign change at `root`."""

    def solve_fn(req):
        k = float(req["k"])
        if seen is not None:
            seen.append(k)
        return {"z_in_re": 50.0, "z_in_im": 40.0 * (k - root), "z0_ohms": 50.0}

    return solve_fn


# ---------------------------------------------------------------------------
# G-1202-1 / G-1202-6
# ---------------------------------------------------------------------------


def test_one_knob_resonance_takes_the_secant():
    res = optimize({"k": 0.1}, ONE, "resonance", solve_fn=_linear_x())
    assert res["method"] == "secant", res["method"]
    assert res["params"]["k"] == pytest.approx(0.62, abs=1e-4)
    assert res["residual_after"] <= _ROOT_FTOL
    # ...and far below the study's 1 ohm reporting tolerance.
    assert res["residual_after"] < 1.0
    assert res["residual_before"] == pytest.approx(abs(40.0 * (0.1 - 0.62)))


def test_a_linear_residual_is_solved_in_the_fewest_solves_a_secant_can_take():
    """X is linear here, so the first secant step lands exactly on the root:
    two points to define the line, one to confirm. Anything more means the
    iterate is not being reused."""
    res = optimize({"k": 0.1}, ONE, "resonance", solve_fn=_linear_x())
    assert res["n_solves"] <= 4, res["n_solves"]


def test_progress_stays_gapless_and_names_the_phase():
    calls = []
    res = optimize(
        {"k": 0.1},
        ONE,
        "resonance",
        solve_fn=_linear_x(),
        on_progress=calls.append,
    )
    # #1007: one callback per eval, contiguous, no dead zone at the start.
    assert [c["n_evals"] for c in calls] == list(range(1, len(calls) + 1))
    assert len(calls) == res["n_evals"]
    assert {c["phase"] for c in calls} <= {"search", "secant", "bracket", "fallback"}
    assert "secant" in {c["phase"] for c in calls}
    # The residual is what a root-finder is driving down, and it is on every
    # frame -- that is what the readout shows instead of a simplex's best-so-far.
    assert all(c["residual"] is not None for c in calls)
    assert min(c["residual"] for c in calls) <= _ROOT_FTOL


def test_the_memo_still_holds_on_the_secant_path():
    """G-1176-1 is not weakened by the new path: one solve per distinct tuple."""
    seen = []
    res = optimize({"k": 0.1}, ONE, "resonance", solve_fn=_linear_x(seen=seen))
    assert len(set(seen)) == res["n_solves"]


# ---------------------------------------------------------------------------
# G-1202-3 / G-1202-4 — where the branch must NOT engage
# ---------------------------------------------------------------------------


def _two_feed(req):
    k = float(req["k"])
    return {
        "z_in_re": 50.0,
        "z_in_im": 40.0 * (k - 0.62),
        "z0_ohms": 50.0,
        "feeds": [
            {"z_re": 50.0, "z_im": 40.0 * (k - 0.62)},
            {"z_re": 50.0, "z_im": 40.0 * (k - 0.20)},
        ],
    }


def test_multifeed_resonance_steps_aside():
    """|X| maximised over ports has no common root; the branch must not fire."""
    res = optimize({"k": 0.1}, ONE, "resonance", solve_fn=_two_feed)
    assert res["method"] == "nelder-mead"
    assert res["residual_after"] is None  # not a scalar root
    assert res["objective_after"] <= res["objective_before"]


@pytest.mark.parametrize("objective", ["swr", "match_z0"])
def test_other_objectives_are_untouched(objective):
    res = optimize({"k": 0.1}, ONE, objective, solve_fn=_linear_x())
    assert res["method"] == "nelder-mead"


def test_two_knobs_are_untouched():
    two = [
        {"name": "k", "min": 0.0, "max": 1.0},
        {"name": "j", "min": 0.0, "max": 1.0},
    ]

    def solve_fn(req):
        return {
            "z_in_re": 50.0,
            "z_in_im": 40.0 * (float(req["k"]) - 0.62) + float(req["j"]),
            "z0_ohms": 50.0,
        }

    res = optimize({"k": 0.1, "j": 0.5}, two, "resonance", solve_fn=solve_fn)
    assert res["method"] == "nelder-mead"


# ---------------------------------------------------------------------------
# G-1202-5 — no root in the box
# ---------------------------------------------------------------------------


def test_no_root_in_the_box_fails_cleanly_with_the_residual_reported():
    """X < 0 everywhere in the box. The run must not present a boundary park as
    a converged root: it names the reason, reports the residual it actually
    reached, and returns a SOLVED point."""
    solved = []

    def solve_fn(req):
        k = float(req["k"])
        solved.append(k)
        return {"z_in_re": 50.0, "z_in_im": -(20.0 + k), "z0_ohms": 50.0}

    res = optimize({"k": 0.5}, ONE, "resonance", solve_fn=solve_fn)
    assert res["method"] == "nelder-mead (root: no-sign-change)"
    assert res["residual_after"] is not None
    assert res["residual_after"] >= 20.0  # the honest residual, not 0
    # The answer is a point that was actually solved, never a prediction.
    assert res["params"]["k"] in [pytest.approx(v) for v in solved]


# ---------------------------------------------------------------------------
# G-1202-2 — the real decks, through the shipped optimize()
# ---------------------------------------------------------------------------

GROUND = dict(ground=("finite", 13.0, 0.005), ground_z=0.0)


def _deck_solve(builder, knob, fixed_name, fixed_val, engine_kw, n_radials=None):
    from antennaknobs.engines.momwire import MomwireEngine

    def solve_fn(req):
        b = builder()
        if n_radials is not None:
            b.n_radials = n_radials
        setattr(b, fixed_name, fixed_val)
        setattr(b, knob, float(req[knob]))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            z = complex(MomwireEngine(b, **engine_kw).impedance()[0])
        return {"z_in_re": z.real, "z_in_im": z.imag, "z0_ohms": 50.0}

    return solve_fn


def _run(solve_fn, knob, start, lo, hi, objective="resonance"):
    return optimize(
        {knob: start},
        [{"name": knob, "min": lo, "max": hi}],
        objective,
        solve_fn=solve_fn,
    )


@pytest.mark.parametrize("start", [2.4454699666515394, 2.41])
def test_moxon_one_knob_beats_nelder_mead(start):
    """The study's moxon cells: NM 11/10 solves, secant 4/4 to |X| <= 1 ohm.
    Here the secant runs to `_ROOT_FTOL` instead, which costs a solve or two
    more and lands three orders tighter."""
    from antennaknobs.designs.beams.moxon import Builder

    fn = _deck_solve(
        Builder,
        "halfdriver",
        "tipspacer_factor",
        0.047061074343758946,
        dict(ground=None),
    )
    res = _run(fn, "halfdriver", start, 2.40, 2.56)
    assert res["method"] == "secant", res["method"]
    assert res["residual_after"] < 1.0, res["residual_after"]
    assert res["n_solves"] <= 9, res["n_solves"]


@pytest.mark.antenna_computation_check
@pytest.mark.parametrize("start", [1.0, 0.89])
def test_buried_vertical_one_knob_beats_nelder_mead(start):
    """The expensive deck: ~6 s a solve, so every solve saved is real time.
    Study cells: NM 11/16, secant 3/3."""
    from antennaknobs.designs.verticals.buried_radial_vertical import Builder

    fn = _deck_solve(
        Builder, "length_factor", "radial_factor", 0.6, GROUND, n_radials=12
    )
    res = _run(fn, "length_factor", start, 0.88, 1.06)
    assert res["method"] == "secant", res["method"]
    assert res["residual_after"] < 1.0, res["residual_after"]
    assert res["n_solves"] <= 8, res["n_solves"]
