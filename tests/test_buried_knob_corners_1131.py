"""The app's mesh for `verticals.buried_radial_vertical`, gated at the corners
of the knob ranges the web exposes (issue #1131).

The design ships one banked answer measured at one point in a five-dimensional
knob space, and the web hands a user sliders over all of it. These gates pin
the app's own answer — auto mesh, quadrature omitted, exactly the call the web
makes — at the corners of `ui_params`, plus the degree-1/degree-2 pair as the
same-trunk second reading. razor and NEC-5 are not asked below ground.

WHAT THIS DOES NOT PROVE, stated up front because the omission would otherwise
look like a claim. The three refinement axes are WEAK LEVERS on this deck: the
#1131 ladder measures node ×3 ≤ 0.100 Ω, far ×3 ≤ 0.126 Ω and n_qp 64 ≤ 0.007 Ω
over every served corner — but a **7× coarsening** of the mesh only moves the
answer 0.362 Ω, and removing the in-medium sizing entirely (the momwire#983
defect shape, 248 segments → 84) moves it 0.058 Ω, i.e. *closer* to the refined
reference than the app's own answer. Driving-point impedance is simply not the
quantity a buried-mesh defect degrades, and Z is all these tests read. So an
"is the mesh fine enough" assertion on these axes would pass for a badly meshed
deck too, and is deliberately NOT what is gated here.

What is gated is what has power:

  * the banked per-corner answer, tight enough that a real change in the
    geometry, the mesher or the fill moves it;
  * the degree pair being NON-DEGENERATE as well as bounded — a bug that
    silently ignored `degree` would collapse the separation to zero, which a
    one-sided `< 1.5 Ω` bar would wave through;
  * `worst_dense` refusing BY NAME rather than crashing or returning a number.

Marked `antenna_computation_check`: each solve is 7–25 s, past the suite's 5 s
unmarked ceiling, and that marker is the main-only CI lane. Deliberately NOT
`heavy_mesh`, which is excluded from CI entirely and would give no protection.
"""

from __future__ import annotations

import warnings

import pytest

from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines.momwire import MomwireEngine

pytestmark = pytest.mark.antenna_computation_check

SOIL_A = ("finite", 13.0, 0.005)
SOIL_B = ("finite", 20.0, 0.03)
SOIL_C = ("finite", 5.0, 0.001)

# Banked 2026-09-03 by scratch/buried-unit4/probe_knob_corners.py on momwire
# 84211f8. The default row reproduces scratch/g1b-bs1-bs2/RESULTS.md's hub
# values to the digit (75.8502+40.4507j, bs1 75.6774+39.9275j), which is what
# ties this file to the record rather than to one run of one probe.
#
# Tolerance is 0.10 Ω, and the number was MEASURED rather than chosen to look
# safe. 0.5 Ω was the first draft and it is vacuous: a 7x mesh coarsening
# (nominal_nsegs 21 -> 3) moves the default corner only 0.289 Ω, so a half-ohm
# bar waves through every coarsening this deck can express. At 0.10 Ω the gate
# catches a 3x coarsening (nominal 7, 0.140 Ω) and worse; it does NOT catch a
# 2x one (nominal 11, 0.070 Ω), and that is the honest limit rather than a
# number to round away. Cross-machine agreement is ~1e-4 (this file's default
# row matches the laptop-measured RESULTS.md to four decimals), so 0.10 Ω is
# three orders of margin over hardware drift.
CORNERS = {
    "default": ({}, SOIL_A, 75.8502 + 40.4507j, 0.551),
    "n_radials_min": ({"n_radials": 1}, SOIL_A, 168.1857 + 43.0702j, 0.593),
    "depth_max": ({"depth": 0.5}, SOIL_A, 76.4130 + 56.6759j, 0.542),
    "length_max": ({"length_factor": 1.2}, SOIL_A, 117.9832 + 225.7894j, 0.687),
    "radial_max": ({"radial_factor": 1.5}, SOIL_A, 75.7392 + 37.6876j, 0.552),
    "soil_B_dense": ({}, SOIL_B, 56.9466 + 35.6788j, 0.550),
    "mild_sparse": (
        {"n_radials": 1, "depth": 0.05, "length_factor": 0.8, "radial_factor": 0.3},
        SOIL_C,
        139.9202 - 344.1216j,
        0.363,
    ),
}

Z_TOL = 0.10  # ohm, against the banked answer — see the note above
PAIR_BAR = 1.5  # ohm, the underground degree-pair bar (momwire#862)
PAIR_FLOOR = 0.05  # ohm — below this the two "degrees" are not distinct


def _solve(params, ground, degree=2):
    from momwire import BSplineSolver

    b = Builder()
    for k, v in params.items():
        setattr(b, k, v)
    with warnings.catch_warnings():
        # A momwire advisory is not this gate's subject; a REFUSAL still raises.
        warnings.simplefilter("ignore")
        eng = MomwireEngine(
            b,
            solver=BSplineSolver,
            solver_kwargs={"degree": degree},
            ground=ground,
            ground_z=0.0,
        )
        return complex(eng.impedance()[0])


@pytest.mark.parametrize("name", sorted(CORNERS))
def test_the_apps_own_answer_is_pinned_at_each_exposed_corner(name):
    """The web's call, at each corner of `ui_params`, against its banked value."""
    params, ground, want, _ = CORNERS[name]
    got = _solve(params, ground)
    assert abs(got - want) <= Z_TOL, f"{name}: {got:.4f} vs banked {want:.4f}"


@pytest.mark.parametrize("name", sorted(CORNERS))
def test_the_degree_pair_is_bounded_AND_non_degenerate(name):
    """The same-trunk second reading, gated on both sides.

    The upper bar is momwire#862's 1.5 Ω. The FLOOR is the half that earns its
    keep: if a change made `degree` a no-op, both solves would return the same
    number, the separation would be 0.000, and a one-sided bar would report
    that as the best result it had ever seen.
    """
    params, ground, _, want_pair = CORNERS[name]
    got = abs(_solve(params, ground, degree=1) - _solve(params, ground, degree=2))
    assert got <= PAIR_BAR, f"{name}: pair {got:.3f} over the {PAIR_BAR} bar"
    assert got >= PAIR_FLOOR, (
        f"{name}: pair {got:.3f} is degenerate — the two degrees are not "
        "solving different bases"
    )
    assert abs(got - want_pair) <= Z_TOL, (
        f"{name}: pair {got:.3f} vs banked {want_pair}"
    )


def test_the_all_knobs_max_corner_refuses_BY_NAME():
    """A combination the UI lets a user reach, which cannot solve (#1131).

    `n_radials=4, depth=0.5, length_factor=1.2, radial_factor=1.5` over soil B
    is inside every advertised range, and its buried structure exceeds the
    below/below remainder table. That it refuses is correct — refusal over a
    confident wrong number. What this gate holds is that it refuses *by name*,
    naming the separation and the cap, rather than crashing, hanging, or
    returning a plausible number. If the cap moves again (it went 2 → 4 λ_m in
    momwire#847, which is what made this design's own docstring stale), this
    test is where that surfaces.
    """
    with pytest.raises(ValueError) as exc:
        _solve(
            {
                "n_radials": 4,
                "depth": 0.5,
                "length_factor": 1.2,
                "radial_factor": 1.5,
            },
            SOIL_B,
        )
    msg = str(exc.value)
    assert "below/below" in msg
    assert "in-medium wavelength" in msg
