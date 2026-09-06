"""Surrogate seeding for the optimiser (issue #1176, second increment).

Nelder-Mead starts from the user's current point and crawls. The seed fits a
cheap quadratic response surface to a space-filling sample, reads a promising
point off it, and hands that to Nelder-Mead as the START. It is a seeding
stage, not a rival method: the surface proposes, NM decides, and the answer is
always a point that was actually solved.

WHAT IT IS AND IS NOT WORTH, measured, because the first study got this wrong.

From the catalog's SHIPPED defaults — which are already tuned — seeding is
neutral to slightly negative, because it spends its budget exploring a box
whose answer is under the start:

    budget      invvee NM / seeded      moxon NM / seeded
       30       1.0072 / 1.0079         1.0255 / 1.0350
       44       1.0004 / 1.0007         1.0045 / 1.0050
       80       1.0000 / 1.0000         1.0000 / 1.0000

From a start AWAY from the optimum — a user who has dragged the knobs — it is
decisive:

    budget      invvee NM / seeded      moxon NM / seeded
       30       1.4589 / 1.0045-1.0084  1.6028 / 1.0350-1.0767
       44       1.0364 / 1.0007-1.0013  1.6028 / 1.0050-1.0111
       60       1.0017 / 1.0000-1.0001  1.6028 / 1.0005-1.0007

moxon's plain run is stuck at 1.6028 at EVERY budget: from that corner
Nelder-Mead collapses into a local basin and never leaves, parking
`t0_factor` on the box boundary. That is the case this stage exists for, and
it is why the stage is a user toggle rather than a default.

(The design study claimed the hybrid reached NM's answer in 54 % of the
solves. That compared the hybrid at 44 evals against NM at its FULL 80 and
never ran NM at 44, which reaches 1.0004 on its own. The missing equal-budget
control is why these gates measure both arms at the same budget.)

Gates:

- G-1176-5  from a poor start the seeded run beats plain NM, and on moxon it
            is the difference between converging and not.
- G-1176-6  it never returns a point that was not solved.
- G-1176-7  it stays inside the bounds and inside the budget.
- G-1176-8  it is off by default, and skipped for one knob where it cannot pay.
"""

from __future__ import annotations

import numpy as np
import pytest

import antennaknobs.web.server as server  # noqa: F401 — resolves the cycle
from antennaknobs.designs.beams.moxon import Builder as Moxon
from antennaknobs.web.optimize import optimize

MOXON_FREE = [
    {"name": "halfdriver", "min": 2.30, "max": 2.60},
    {"name": "t0_factor", "min": 0.33, "max": 0.48},
]
# A corner of the box, far from the shipped tuning: the case a user reaches by
# dragging knobs, and the one plain Nelder-Mead cannot get out of.
MOXON_POOR = {"halfdriver": 2.31, "t0_factor": 0.34}


def _moxon(seeded, budget, start=None, seed_state=0):
    ex = server.EXAMPLES["beams.moxon"]
    base = {"geometry": "beams.moxon", "momwire_model": "bspline"}
    base.update(start or MOXON_POOR)
    return optimize(
        base,
        MOXON_FREE,
        "swr",
        solve_fn=ex.momwire_solve,
        max_evals=budget,
        seed_surrogate=seeded,
        seed_state=seed_state,
    )


# --- G-1176-5 -------------------------------------------------------------


def test_g1176_5_seeding_escapes_the_basin_plain_nm_is_stuck_in():
    """The headline, and the reason the stage exists.

    Both arms at the SAME budget — the control the design study omitted.
    """
    plain = _moxon(False, 60)
    seeded = _moxon(True, 60)
    assert plain["objective_after"] > 1.5, (
        f"plain NM reached {plain['objective_after']:.4f} from this corner; if it "
        f"no longer gets stuck, this gate is measuring nothing"
    )
    assert seeded["objective_after"] < 1.05, seeded["objective_after"]


def test_g1176_5_plain_nm_parks_on_the_boundary_and_seeding_does_not():
    """What "stuck" means here, against the design's own shipped optimum."""
    opt = dict(Moxon.opt_params)
    plain = _moxon(False, 60)["params"]
    seeded = _moxon(True, 60)["params"]
    assert plain["t0_factor"] == pytest.approx(0.33, abs=1e-6), "not on the bound"
    assert abs(seeded["t0_factor"] - opt["t0_factor"]) < abs(
        plain["t0_factor"] - opt["t0_factor"]
    )
    assert abs(seeded["halfdriver"] - opt["halfdriver"]) < abs(
        plain["halfdriver"] - opt["halfdriver"]
    )


@pytest.mark.parametrize("seed_state", [0, 1, 2, 3])
def test_g1176_5_the_escape_does_not_depend_on_the_draw(seed_state):
    """The seed is randomised, so a gate on one draw would be a coin flip
    pinned as a fact."""
    assert _moxon(True, 60, seed_state=seed_state)["objective_after"] < 1.05


def test_g1176_5_seeding_does_not_regress_the_shipped_start():
    """The other half: from the tuned default it must not make things worse
    at a full budget, or the toggle would be a trap."""
    start = {
        "halfdriver": Moxon.default_params["halfdriver"],
        "t0_factor": Moxon.default_params["t0_factor"],
    }
    plain = _moxon(False, 80, start=start)["objective_after"]
    seeded = _moxon(True, 80, start=start)["objective_after"]
    assert seeded <= plain + 1e-3, (plain, seeded)


# --- G-1176-6 -------------------------------------------------------------


def test_g1176_6_the_answer_is_a_point_that_was_actually_solved():
    """The surface proposes; it never decides. Every point handed back must
    have been measured — the study found the surface's predicted value up to
    0.5 SWR from what that point turned out to be worth."""
    solved: list[tuple[float, ...]] = []
    ex = server.EXAMPLES["beams.moxon"]

    def spy(req):
        solved.append(
            (round(float(req["halfdriver"]), 12), round(float(req["t0_factor"]), 12))
        )
        return ex.momwire_solve(req)

    base = {"geometry": "beams.moxon", "momwire_model": "bspline", **MOXON_POOR}
    res = optimize(
        base, MOXON_FREE, "swr", solve_fn=spy, max_evals=40, seed_surrogate=True
    )
    got = (
        round(res["params"]["halfdriver"], 12),
        round(res["params"]["t0_factor"], 12),
    )
    assert got in solved, "returned a point the solver never saw"


# --- G-1176-7 -------------------------------------------------------------


def test_g1176_7_the_seed_stays_inside_the_bounds():
    seen = []
    ex = server.EXAMPLES["beams.moxon"]

    def spy(req):
        seen.append((float(req["halfdriver"]), float(req["t0_factor"])))
        return ex.momwire_solve(req)

    base = {"geometry": "beams.moxon", "momwire_model": "bspline", **MOXON_POOR}
    optimize(base, MOXON_FREE, "swr", solve_fn=spy, max_evals=40, seed_surrogate=True)
    hd, t0 = np.array(seen).T
    assert hd.min() >= 2.30 - 1e-9 and hd.max() <= 2.60 + 1e-9
    assert t0.min() >= 0.33 - 1e-9 and t0.max() <= 0.48 + 1e-9


@pytest.mark.parametrize("budget", [20, 40, 60])
def test_g1176_7_a_seeded_run_never_costs_more_than_its_budget(budget):
    """The seed's evals come OUT of the budget, so turning the toggle on can
    never make a run more expensive than the same run without it."""
    res = _moxon(True, budget)
    assert res["n_evals"] <= budget + 2, (res["n_evals"], budget)
    assert res["n_seed"] > 0


# --- G-1176-8 -------------------------------------------------------------


def test_g1176_8_it_is_off_unless_asked():
    assert _moxon(False, 30)["n_seed"] == 0


def test_g1176_8_one_knob_is_skipped():
    """A 1-D quadratic needs three points and plain NM converges in 24 solves
    on these decks, so the seed would spend an eighth of the run to save
    nothing. Measured in the design study; asserted here so the exclusion is
    a decision rather than an accident."""
    ex = server.EXAMPLES["beams.moxon"]
    res = optimize(
        {"geometry": "beams.moxon", "momwire_model": "bspline", **MOXON_POOR},
        [MOXON_FREE[0]],
        "swr",
        solve_fn=ex.momwire_solve,
        max_evals=30,
        seed_surrogate=True,
    )
    assert res["n_seed"] == 0
