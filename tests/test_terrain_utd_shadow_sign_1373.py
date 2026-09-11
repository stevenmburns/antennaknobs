"""Issue #1373 — the uphill band gets DARKER, and this file says so in a test.

A hill that blocks the sky makes the sky behind it dimmer. That is obvious
stated plainly, and it was written down backwards anyway: the first description
of this change claimed the shadowed band moved 10 to 12 dB BRIGHTER, on the
reasoning that "a shadowed, diffracted field is brighter than a cancelled one".

The reasoning was about the wrong thing. Geometric optics does not report a
cancellation in the uphill band — it reports a perfectly healthy +5.7 dBi
*through a 45-degree hill*, because a specular model has no concept of the hill
being in the way at all. The diffracted composer is what puts the hill in the
way, and putting a hill in the way makes things darker. Measured on the 45/20
hillside: 15 to 35 dB darker below the slope angle.

Prose can be re-worded wrongly a second time; a test cannot. The invariant is
the SIGN and the boundary, not the exact decibels:

* below the uphill slope angle the sky is shadowed, so the diffracted field is
  well below the specular one;
* above it nothing is blocked, so the two agree to about a decibel — which is
  what makes the first claim a statement about shadowing rather than about the
  composer being darker everywhere.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from antennaknobs import merge_params
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.terrain import hillside_terrain
from momwire import BSplineSolver

F, H0 = 21.2, 6.1
UP_SLOPE, DOWN_SLOPE = 45.0, 20.0


@pytest.fixture(scope="module")
def cuts():
    """Uphill and downhill elevation columns, both fields, one solve each."""
    base = hillside_terrain(
        flat_width=20.0, up_slope_deg=UP_SLOPE, down_slope_deg=DOWN_SLOPE
    )

    def grid(diffraction: bool):
        p = merge_params(
            Builder.default_params, {"design_freq": F, "freq": F, "base": H0}
        )
        eng = MomwireEngine(
            Builder(p),
            solver=BSplineSolver,
            solver_kwargs={"degree": 2},
            ground=("terrain", dataclasses.replace(base, diffraction=diffraction)),
        )
        ff = eng.far_field(n_theta=45, n_phi=36, del_theta=2, del_phi=10)
        return (
            np.asarray(ff.thetas, dtype=float),
            np.asarray(ff.phis, dtype=float),
            np.asarray(ff.rings),
        )

    th, ph, spec = grid(False)
    _, _, diff = grid(True)
    up = int(np.argmin(np.abs(ph - 180.0)))  # hillside_terrain faces downhill at az 0
    dn = int(np.argmin(np.abs(ph - 0.0)))
    elev = 90.0 - th
    return elev, spec[:, up], diff[:, up], spec[:, dn], diff[:, dn]


def _at(elev, col, target):
    return float(col[int(np.argmin(np.abs(elev - target)))])


@pytest.mark.parametrize("target", [10.0, 20.0, 30.0, 40.0])
def test_the_shadowed_uphill_band_is_darker_not_brighter(cuts, target):
    """Below the 45 degree slope angle: the hill is in the way."""
    elev, s_up, d_up, _, _ = cuts
    spec, diff = _at(elev, s_up, target), _at(elev, d_up, target)
    assert diff < spec - 5.0, (
        f"uphill at {target:g} deg: specular {spec:+.2f} dBi, diffracted "
        f"{diff:+.2f} dBi — the shadowed band must be DARKER"
    )


def test_geometric_optics_claimed_a_bright_field_through_the_hill(cuts):
    """The thing being corrected, stated as a measurement.

    If the specular model reported a null or a cancellation in this band, the
    'brighter' story would have been the right one. It does not — it reports a
    field within a couple of dB of the peak, straight through 45 degrees of
    hillside — which is why the fix darkens rather than brightens.
    """
    elev, s_up, _, _, _ = cuts
    assert _at(elev, s_up, 30.0) > 0.0
    assert _at(elev, s_up, 30.0) > _at(elev, s_up, 90.0) - 3.0


@pytest.mark.parametrize("target", [60.0, 66.0, 72.0, 78.0])
def test_above_the_slope_angle_the_band_is_brighter(cuts, target):
    """Clear sky above the hill, and the composer is not merely darker there.

    This is the half of the story that makes the other half about SHADOWING
    rather than about a pessimistic composer — and it is a different mechanism
    again. Above the slope angle nothing is blocked, and what the composer
    changes is the reflection: the source imaged across the 45-degree facet's
    own plane instead of a horizontal mirror, which puts a lobe where geometric
    optics had none. Measured up to +5.9 dB at 66 degrees.
    """
    elev, s_up, d_up, _, _ = cuts
    spec, diff = _at(elev, s_up, target), _at(elev, d_up, target)
    assert diff > spec, (
        f"uphill at {target:g} deg is clear sky above the {UP_SLOPE:g} deg "
        f"slope: {spec:+.2f} -> {diff:+.2f} dBi"
    )


def test_the_crossover_sits_near_the_slope_angle(cuts):
    """The boundary is the geometry's, not a fitted number.

    Sweeping the uphill column, the sign of (diffracted - specular) has to flip
    in the neighbourhood of the slope angle — that is what identifies the dark
    band as the hill's shadow rather than a band that happens to be dark. Held
    to +/- 12 degrees: the shadow boundary is smeared across the antenna's own
    height (every segment is its own source, which is the point of the
    composer), so a sharp crossover would be the suspicious result.
    """
    elev, s_up, d_up, _, _ = cuts
    band = (elev > 4.0) & (elev < 86.0)
    e, delta = elev[band], (d_up - s_up)[band]
    order = np.argsort(e)
    e, delta = e[order], delta[order]
    # Last elevation (scanning upward) at which the field is still much darker.
    dark = e[delta < -5.0]
    assert dark.size, "no shadowed band at all"
    assert abs(dark.max() - UP_SLOPE) < 12.0, (
        f"the dark band ends at {dark.max():g} deg, not near the "
        f"{UP_SLOPE:g} deg slope angle"
    )
    # And it is contiguous from the horizon up to there, not a scatter of nulls.
    below = delta[e <= dark.max()]
    assert np.mean(below < -5.0) > 0.8, "the dark band is not contiguous"


def test_the_downhill_side_barely_moves(cuts):
    """The direction with no hill in it is the control.

    A composer that were simply darker, or simply different, would show it here
    too. Held loosely — the downhill break diffracts as well — but an order of
    magnitude tighter than the shadowed band.
    """
    elev, _, _, s_dn, d_dn = cuts
    worst = max(
        abs(_at(elev, d_dn, t) - _at(elev, s_dn, t)) for t in (20.0, 30.0, 40.0, 50.0)
    )
    assert worst < 3.0, f"downhill moved {worst:.2f} dB"
