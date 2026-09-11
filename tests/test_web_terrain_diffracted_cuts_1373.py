"""Issue #1373 — the DIFFRACTED field at the cuts layer.

The app draws a faceted terrain through the two polar cuts, and those go
through `_mag2_at_directions`, which until now had only #534's specular
composer. The diffracted branch does not add a term to that: it hands the
directions to `momwire.terrain_utd_power` — the one implementation of the
physics — grouped by azimuth, because the composer is written over a grid and
a #744-refined cut is not one.

What is worth gating here is the PLUMBING around that call, not the physics
(`test_terrain_utd_slicing_1373.py` gates the composer's exactness under
slicing, and the composer is now literally shared with the engine):

* the same direction evaluated through a scattered cut and through a
  rectangular grid gets the same answer — i.e. the azimuth grouping is
  shape-agnostic, and a cut sample is not quietly picking up a neighbour's
  azimuth;
* the response says which field it is, because a drag and a settle land in the
  same client-side cache and the label the user reads has to be driven by what
  the server actually composed;
* the two fields genuinely differ here, so none of the above can pass in a
  world where the branch is a no-op;
* below-horizon samples, which the diffracted branch SKIPS rather than
  evaluates, still come back floored exactly as the specular path leaves them;
* the PEC ledger's reference integral is refused a diffracted numerator.
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs.terrain import Terrain, cliff_terrain, flat_terrain, levee_terrain
from antennaknobs.web.server import (
    _CUT_FLOOR_DBI,
    _mag2_at_directions,
    _pattern_cuts,
)

# Imported after server: adapter and examples import each other cyclically,
# and only the examples-first entry order (which server triggers) resolves.
import antennaknobs.web.adapter as adapter  # noqa: E402
from antennaknobs.web.adapter import _pack_terrain  # noqa: E402

from test_web_terrain import _hertzian_over  # noqa: E402

AZ_EL, EL_AZ = 15.0, 30.0
SOIL, WATER = adapter._TERRAIN_LAND, adapter._TERRAIN_WATER

CASES = {
    "levee": levee_terrain(
        crest_width=3.0, slope_deg=20.0, drop_water=10.7, drop_land=7.6
    ),
    "cliff": cliff_terrain(edge=10.0, drop=10.0, inner=SOIL, outer=WATER),
}


def _out(terrain: Terrain) -> dict:
    """A solve response over `terrain`. The packed form carries facets only, so
    the flag never rides along — which is the whole reason the caller has to
    name it."""
    return _hertzian_over(terrain)


def _rhat(cut: str, out_cuts: dict) -> np.ndarray:
    """The directions `_pattern_cuts` sampled, rebuilt from its own echoed
    parameterisation so this test cannot drift from the production circles."""
    n = len(out_cuts[cut])
    t = np.radians(np.arange(n) * 360.0 / n)
    if cut == "azimuth":
        a = np.radians(out_cuts["az_elev_deg"])
        return np.stack(
            [np.cos(a) * np.cos(t), np.cos(a) * np.sin(t), np.full_like(t, np.sin(a))],
            axis=-1,
        )
    e = np.radians(out_cuts["elev_az_deg"])
    return np.stack([np.cos(e) * np.cos(t), np.sin(e) * np.cos(t), np.sin(t)], axis=-1)


@pytest.mark.parametrize("name", sorted(CASES))
@pytest.mark.parametrize("cut", ["azimuth", "elevation"])
def test_a_cut_sample_equals_the_same_direction_in_a_grid(name, cut):
    """Scattered directions and a rectangular grid must agree, exactly.

    The grouping walks `np.unique` over quantised azimuths and writes results
    back through a boolean mask. On a grid each group is a whole column; on the
    elevation cut the groups are two interleaved half-circles. An off-by-one in
    that mask, or an azimuth quantised onto its neighbour, would show up here
    and essentially nowhere else — a wrong-but-plausible cut trace is exactly
    the kind of thing a smooth polar chart hides.
    """
    out = _out(CASES[name])
    cuts = _pattern_cuts(out, AZ_EL, EL_AZ, diffraction=True)
    assert cuts is not None
    r = _rhat(cut, cuts)
    # Same directions, presented as a (1, N) grid instead of a (N,) list.
    grid = _mag2_at_directions(out, r[None, :, :], diffraction=True)
    flat = _mag2_at_directions(out, r, diffraction=True)
    assert np.array_equal(grid[0], flat)

    norm = float(out["directivity_norm"])
    with np.errstate(divide="ignore"):
        dbi = 10.0 * np.log10(
            np.maximum(norm * np.where(r[:, 2] < 0.0, 0.0, flat), 0.0)
        )
    dbi = np.where(np.isfinite(dbi), dbi, _CUT_FLOOR_DBI)
    assert [round(float(v), 3) for v in dbi] == cuts[cut]


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_response_says_which_field_it_is(name):
    out = _out(CASES[name])
    assert _pattern_cuts(out, AZ_EL, EL_AZ)["diffraction"] is False
    assert _pattern_cuts(out, AZ_EL, EL_AZ, diffraction=True)["diffraction"] is True


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_two_fields_differ(name):
    """Otherwise every assertion in this file passes on a no-op branch."""
    spec = _pattern_cuts(_out(CASES[name]), AZ_EL, EL_AZ)
    diff = _pattern_cuts(_out(CASES[name]), AZ_EL, EL_AZ, diffraction=True)
    moved = max(
        abs(a - b)
        for c in ("azimuth", "elevation")
        for a, b in zip(spec[c], diff[c], strict=True)
        if a > _CUT_FLOOR_DBI and b > _CUT_FLOOR_DBI
    )
    assert moved > 1.0, f"{name}: the diffracted branch moved at most {moved:.3f} dB"


def test_below_horizon_samples_are_floored_not_evaluated():
    """The diffracted branch skips rz <= 0 entirely — half the elevation cut.

    Skipping is an optimisation the caller's floor makes safe, and this is the
    test that keeps it safe: the floored half must be indistinguishable from
    the specular path's, whose values ARE computed and then floored.
    """
    out = _out(CASES["levee"])
    spec = _pattern_cuts(out, AZ_EL, 0.0)["elevation"]
    diff = _pattern_cuts(out, AZ_EL, 0.0, diffraction=True)["elevation"]
    n = len(spec)
    below = [i for i in range(n) if np.sin(2 * np.pi * i / n) < 0.0]
    assert below, "the elevation circle must dip below the horizon"
    assert all(spec[i] == _CUT_FLOOR_DBI for i in below)
    assert [diff[i] for i in below] == [spec[i] for i in below]


# A sample this far below the peak is numerical zero, not a field: a vertical
# dipole's zenith null lands near -320 dBi, and which of two arithmetic routes
# to zero reports -319 and which -322 is not a fact about the physics. Every
# real sample on these cuts is inside 40 dB of the peak.
_NUMERICAL_ZERO_DBI = -100.0


def test_flat_terrain_diffracted_matches_the_plain_ground():
    """#534's gate 1, through the diffracted composer at the cuts layer.

    One unbroken facet has no wedge to diffract from, so the answer is the
    plain finite ground's — but reached by imaging each segment across the
    facet's own plane rather than through the horizontal-mirror formula, so the
    agreement is to round-off and not bit-for-bit. The specular arm's
    bit-identity is `test_web_terrain.py`'s to keep.

    Samples at numerical zero are compared as "both zero" rather than by
    difference: the zenith null is one, and a 3 dB gap between -319 and -322 dBi
    is not a disagreement about anything.
    """
    plain = _pattern_cuts(_hertzian_over(None), AZ_EL, EL_AZ)
    utd = _pattern_cuts(
        _hertzian_over(flat_terrain(*SOIL)), AZ_EL, EL_AZ, diffraction=True
    )
    for c in ("azimuth", "elevation"):
        a, b = np.asarray(plain[c]), np.asarray(utd[c])
        zero = (a < _NUMERICAL_ZERO_DBI) | (b < _NUMERICAL_ZERO_DBI)
        assert np.all(a[zero] < _NUMERICAL_ZERO_DBI), "a real field went missing"
        assert np.all(b[zero] < _NUMERICAL_ZERO_DBI), "a real field appeared"
        live = ~zero
        # The elevation circle spends half its parameter below the horizon and
        # is floored there by design, so 0.4 rather than something near 1 — the
        # guard is against a comparison that quietly has nothing left in it, not
        # a claim about how much of a circle is above ground.
        assert live.sum() > 0.4 * live.size, "the comparison emptied out"
        assert np.max(np.abs(a[live] - b[live])) < 1e-3  # dB, at 3-dp rounding


def test_the_horizon_sample_does_not_spike():
    """The elevation circle's t = 180 deg sample, on every request, forever.

    `sin(180 deg)` is +1.2e-16 in float, so the sample is above the horizon by
    arithmetic and escapes the below-horizon floor. There the composer's
    specular point has run to infinity and `reflections` resolves no reflected
    path, so it would return the DIRECT wave alone — +1.761 dBi on a flat
    terrain where the truth is a grazing null at -298. Not a rounding
    disagreement: a bright spot on the horizon of every diffracted elevation
    cut. `_UTD_GRAZING_RZ` is why it is floored instead; this is the test that
    keeps it floored.
    """
    for terrain in (flat_terrain(*SOIL), CASES["levee"]):
        el = _pattern_cuts(_hertzian_over(terrain), AZ_EL, 0.0, diffraction=True)[
            "elevation"
        ]
        n = len(el)
        assert n % 2 == 0, "the uniform circle must land a sample on t = 180 deg"
        assert el[n // 2] == _CUT_FLOOR_DBI, (
            f"horizon sample read {el[n // 2]:.3f} dBi, not the floor"
        )


def test_the_grazing_floor_is_narrower_than_any_real_sample():
    """It must fix the horizon spike WITHOUT eating a band of real field.

    `_UTD_GRAZING_RZ` corresponds to 5.7e-7 degrees of elevation. Just above it
    the diffracted cut has to carry the levee's grazing field — which is a real
    and large effect, the crest edge diffracting into a direction geometric
    optics says is 100 dB darker — rather than the floor.
    """
    out = _hertzian_over(CASES["levee"])
    # Held to 0.1 deg and below, where geometric optics is 11 dB or more down
    # on the diffracted field. Higher up the two converge (2.1 dB apart at 1 deg,
    # 1.7 at 5), which is the model behaving: the crest edge matters most where
    # the specular ray is most thoroughly blocked.
    els = [1e-6, 1e-4, 1e-2, 0.1]
    d = _pattern_cuts(out, AZ_EL, 0.0, elev_angles_deg=els, diffraction=True)
    s = _pattern_cuts(out, AZ_EL, 0.0, elev_angles_deg=els)
    assert all(v > _NUMERICAL_ZERO_DBI for v in d["elevation"]), d["elevation"]
    # ... and it is the diffracted field there, not a copy of the specular one.
    assert all(
        dv > sv + 5.0 for dv, sv in zip(d["elevation"], s["elevation"], strict=True)
    ), list(zip(s["elevation"], d["elevation"], strict=True))


def test_the_pec_ledger_refuses_a_diffracted_numerator():
    """`terrain_pec` is a ratio against a reference differing ONLY in the media.

    The composer has no PEC mode, so a diffracted numerator over a specular
    denominator would report the geometric restructuring the ratio exists to
    cancel — as ground absorption. Refused rather than approximated.
    """
    out = _out(CASES["levee"])
    r = _rhat("elevation", _pattern_cuts(out, AZ_EL, EL_AZ))
    with pytest.raises(AssertionError, match="PEC ledger"):
        _mag2_at_directions(out, r, terrain_pec=True, diffraction=True)
    # Each alone is fine.
    assert _mag2_at_directions(out, r, terrain_pec=True).shape == r.shape[:-1]
    assert _mag2_at_directions(out, r, diffraction=True).shape == r.shape[:-1]


def test_the_packed_form_carries_no_flag():
    """Which is why `_terrain_from_packed` has to be told, and why the cuts
    response has to say. A flag that rode the wire would make both redundant —
    and if one is ever added, this test is the reminder to simplify rather than
    leave two sources of truth."""
    packed = _pack_terrain(Terrain(sectors=flat_terrain(*SOIL).sectors))
    assert "diffraction" not in packed
