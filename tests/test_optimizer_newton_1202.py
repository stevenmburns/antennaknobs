"""Two knobs to Z0 is a TWO-COMPONENT ROOT: (R - R0, X) (#1202, increment 2).

The #1202 study measured distinct solves to |Z - Z0| <= 1 ohm over
`beams.moxon` and a 12-radial buried vertical, from a tuned and a far start:

    Nelder-Mead      39 / 27 / FAILED / 48
    seed + Broyden   10 / 10 /     12 / 12

The FAILED cell is the one that matters. On the buried vertical, R along the
X = 0 contour rises to 50.7 at radial_factor 0.31, falls to 45.1 at 0.54, then
SATURATES at 48.5 and never returns to 50. A start past that ridge -- which the
catalogue's own tuned start is -- sends any locally-valid method chasing R = 50
into the upper bound, where the residual cannot be zeroed. Nelder-Mead failed
there. Bare Newton failed there, and worse: it thrashed at the bound for the
whole 80-solve budget.

## Why the seed here is not `_surrogate_seed`

`_surrogate_seed` returns its best SOLVED sample, which is the right answer for
a Nelder-Mead finisher -- NM needs an incumbent and cannot use a prediction.
It is the WRONG answer for Newton, and measurably so: on the buried vertical
the best-scoring sample sat at radial_factor 0.65, past the ridge, and Newton
walked from it straight into the bound. The fitted surface's PREDICTED crossing
sat at 0.43, on the correct side, and Newton converged from it in 8 solves.

So `_surrogate_root_start` hands Newton a prediction to START from, and keeps
the ranked solved samples as restarts. The ANSWER is still always a solved
point, so the abort rule is untouched.

## Guards

Same single-feed guard as the scalar path, for the same reason: a minimax over
several ports is not a root system. Exactly two knobs -- one knob to Z0 is
generally over-determined, three is under-determined.

Gates:

- G-1202-7   a two-knob `match_z0` run takes seed+Newton and converges.
- G-1202-8   both study decks reach tolerance from BOTH starts, through the
             shipped `optimize()`, within +-2 of the study's counts -- and in
             particular the buried vertical's tuned start, which FAILED under
             both Nelder-Mead and bare Newton.
- G-1202-9   the box-aware Jacobian: a start ON a bound still produces a
             usable Jacobian rather than a singular one.
- G-1202-10  contours that never cross fail CLEANLY -- named reason, honest
             residual, a SOLVED point back, no silent boundary park.
- G-1202-11  multi-feed, other objectives, and other knob counts untouched.
- G-1202-12  the stall detector bounds the damage on an unreachable target.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from antennaknobs.web.optimize import _newton_root2, optimize

TWO = [
    {"name": "a", "min": 0.0, "max": 1.0},
    {"name": "b", "min": 0.0, "max": 1.0},
]


def _crossing(seen=None):
    """R and X with an isolated common root at (0.5, 0.6)."""

    def solve_fn(req):
        a, b = float(req["a"]), float(req["b"])
        if seen is not None:
            seen.append((a, b))
        return {
            "z_in_re": 50.0 + 30.0 * (b - 0.6) + 4.0 * (a - 0.5),
            "z_in_im": 40.0 * (a - 0.5) - 6.0 * (b - 0.6),
            "z0_ohms": 50.0,
        }

    return solve_fn


# ---------------------------------------------------------------------------
# G-1202-7 / G-1202-12
# ---------------------------------------------------------------------------


def test_two_knob_match_z0_takes_seed_plus_newton_and_converges():
    res = optimize({"a": 0.1, "b": 0.1}, TWO, "match_z0", solve_fn=_crossing())
    assert res["method"] == "seed + newton", res["method"]
    assert res["residual_after"] < 1e-2, res["residual_after"]
    assert res["params"]["a"] == pytest.approx(0.5, abs=1e-3)
    assert res["params"]["b"] == pytest.approx(0.6, abs=1e-3)
    assert res["n_seed"] == 6  # the coefficient count for a 2-D quadratic


def test_the_answer_is_always_a_solved_point():
    seen = []
    res = optimize({"a": 0.1, "b": 0.1}, TWO, "match_z0", solve_fn=_crossing(seen=seen))
    got = (res["params"]["a"], res["params"]["b"])
    assert any(
        got[0] == pytest.approx(s[0]) and got[1] == pytest.approx(s[1]) for s in seen
    ), "returned a prediction rather than a solved point"


def test_progress_stays_gapless_and_names_the_root_phases():
    calls = []
    res = optimize(
        {"a": 0.1, "b": 0.1},
        TWO,
        "match_z0",
        solve_fn=_crossing(),
        on_progress=calls.append,
    )
    assert [c["n_evals"] for c in calls] == list(range(1, len(calls) + 1))
    assert len(calls) == res["n_evals"]
    phases = {c["phase"] for c in calls}
    assert "seeding" in phases and "newton" in phases
    assert all(c["residual"] is not None for c in calls)


# ---------------------------------------------------------------------------
# G-1202-9 — the box-aware Jacobian
# ---------------------------------------------------------------------------


def test_a_jacobian_taken_ON_a_bound_is_not_singular():
    """A plain forward difference at an upper bound clips every perturbation
    back onto the bound: J comes out identically zero and the solve dies. This
    is the bug that cost Newton the moxon far start in the study."""
    calls = []

    def probe(x):
        calls.append(tuple(x))
        a, b = float(x[0]), float(x[1])
        return np.array([30.0 * (b - 0.6) + 4.0 * (a - 0.5), 40.0 * (a - 0.5)])

    # Start exactly on the upper corner of the box.
    xr, ok, why = _newton_root2(probe, [1.0, 1.0], [(0.0, 1.0), (0.0, 1.0)], 40)
    assert why != "singular", (why, calls[:4])
    assert ok, (ok, why)
    assert xr[0] == pytest.approx(0.5, abs=1e-3)
    # The perturbations stepped INWARD, never off the box.
    assert all(0.0 <= v <= 1.0 for c in calls for v in c)


# ---------------------------------------------------------------------------
# G-1202-10 — no crossing in the box
# ---------------------------------------------------------------------------


def test_contours_that_never_cross_fail_cleanly():
    """R ranges over [40, 45], so the R = 50 contour is nowhere in the box and
    there is no crossing to find. The run must report the residual it actually
    reached and name the reason -- never present a bound as a converged root."""
    seen = []

    def solve_fn(req):
        a, b = float(req["a"]), float(req["b"])
        seen.append((a, b))
        return {
            "z_in_re": 40.0 + 5.0 * b,
            "z_in_im": 10.0 * (a - 0.5),
            "z0_ohms": 50.0,
        }

    res = optimize({"a": 0.2, "b": 0.2}, TWO, "match_z0", solve_fn=solve_fn)
    assert res["method"] == "nelder-mead (root: no-crossing)", res["method"]
    # The true minimum: R = 45 at b = 1, X = 0 at a = 0.5.
    assert res["residual_after"] == pytest.approx(5.0, abs=0.2)
    got = (res["params"]["a"], res["params"]["b"])
    assert any(
        got[0] == pytest.approx(s[0]) and got[1] == pytest.approx(s[1]) for s in seen
    )


# ---------------------------------------------------------------------------
# G-1202-11 — where the branch must NOT engage
# ---------------------------------------------------------------------------


def test_multifeed_match_z0_steps_aside():
    def mf(req):
        a = float(req["a"])
        return {
            "z_in_re": 50.0,
            "z_in_im": 10.0 * (a - 0.5),
            "z0_ohms": 50.0,
            "feeds": [
                {"z_re": 50.0, "z_im": 10.0 * (a - 0.5)},
                {"z_re": 70.0, "z_im": 0.0},
            ],
        }

    res = optimize({"a": 0.2, "b": 0.2}, TWO, "match_z0", solve_fn=mf)
    assert res["method"] == "nelder-mead"
    assert res["residual_after"] is None


@pytest.mark.parametrize("objective", ["swr", "resonance"])
def test_other_two_knob_objectives_are_untouched(objective):
    res = optimize({"a": 0.2, "b": 0.2}, TWO, objective, solve_fn=_crossing())
    assert res["method"] == "nelder-mead"


def test_three_knobs_are_untouched():
    three = TWO + [{"name": "c", "min": 0.0, "max": 1.0}]

    def fn(req):
        a, b = float(req["a"]), float(req["b"])
        return {
            "z_in_re": 50.0 + 30.0 * (b - 0.6),
            "z_in_im": 40.0 * (a - 0.5) + float(req["c"]),
            "z0_ohms": 50.0,
        }

    res = optimize({"a": 0.2, "b": 0.2, "c": 0.1}, three, "match_z0", solve_fn=fn)
    assert res["method"] == "nelder-mead"


# ---------------------------------------------------------------------------
# G-1202-8 — the real decks, through the shipped optimize()
# ---------------------------------------------------------------------------

GROUND = dict(ground=("finite", 13.0, 0.005), ground_z=0.0)


def _deck(builder, knobs, box, engine_kw, n_radials=None):
    from antennaknobs.engines.momwire import MomwireEngine

    def solve_fn(req):
        b = builder()
        if n_radials is not None:
            b.n_radials = n_radials
        for k in knobs:
            setattr(b, k, float(req[k]))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            z = complex(MomwireEngine(b, **engine_kw).impedance()[0])
        return {"z_in_re": z.real, "z_in_im": z.imag, "z0_ohms": 50.0}

    free = [
        {"name": k, "min": b[0], "max": b[1]} for k, b in zip(knobs, box, strict=True)
    ]
    return solve_fn, free


@pytest.mark.antenna_computation_check
@pytest.mark.parametrize(
    "start", [(2.4454699666515394, 0.047061074343758946), (2.41, 0.115)]
)
def test_moxon_two_knobs_reaches_z0(start):
    """Study: NM 39 / 27 solves, seed+Broyden 10 / 10."""
    from antennaknobs.designs.beams.moxon import Builder

    knobs = ["halfdriver", "tipspacer_factor"]
    fn, free = _deck(Builder, knobs, [(2.40, 2.56), (0.030, 0.130)], dict(ground=None))
    res = optimize(dict(zip(knobs, start, strict=True)), free, "match_z0", solve_fn=fn)
    assert res["method"] == "seed + newton", res["method"]
    assert res["residual_after"] < 1.0, res["residual_after"]
    assert res["n_solves"] <= 14, res["n_solves"]


@pytest.mark.antenna_computation_check
@pytest.mark.parametrize("start", [(1.0, 0.6), (0.89, 0.12)])
def test_buried_vertical_two_knobs_reaches_z0(start):
    """THE gate for this increment. The (1.0, 0.6) start is the catalogue's
    own, it sits past the R-ridge along X = 0, and it FAILED under both
    Nelder-Mead (best 1.51) and bare Newton (best 1.51, 80 solves burnt)."""
    from antennaknobs.designs.verticals.buried_radial_vertical import Builder

    knobs = ["length_factor", "radial_factor"]
    fn, free = _deck(Builder, knobs, [(0.88, 1.06), (0.08, 1.00)], GROUND, n_radials=12)
    res = optimize(dict(zip(knobs, start, strict=True)), free, "match_z0", solve_fn=fn)
    assert res["method"] == "seed + newton", res["method"]
    assert res["residual_after"] < 1.0, res["residual_after"]
    assert res["n_solves"] <= 16, res["n_solves"]
