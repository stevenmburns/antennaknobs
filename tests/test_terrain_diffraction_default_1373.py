"""Issue #1373 — where `Terrain.diffraction` is ON and where it is pinned OFF.

The flag defaults to True as of this change, so shadowing + UTD wedge
diffraction is what a `Terrain` MEANS unless a caller says otherwise. Two
kinds of caller say otherwise, and both are load-bearing:

* the #534 gates and the study probes, which are about the geometric-optics
  field or compare against references (plain Sommerfeld, nec2c's GN+GD) that
  have no diffraction term of their own — they name the flag in place;
* the **web path**, which cannot afford the diffracted field on every knob
  drag: 0.47–1.03 s for a 45×72 grid against 0.017 s, paid per direction. It
  pins specular in `_terrain_from_request` (the solve) and
  `_terrain_from_packed` (the cuts), and the follow-on PR replaces that pin
  with the dwell path — specular while dragging, the diffracted field composed
  once on settle, labelled while the two differ.

This file is the tripwire for the pin. Reading the flag is not enough on its
own: a test that only checked `is False` would still pass if the two fields
happened to agree, so `test_the_pin_is_not_vacuous` measures that they do not.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from antennaknobs import merge_params
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.terrain import (
    Facet,
    Sector,
    Terrain,
    cliff_terrain,
    flat_terrain,
    hillside_terrain,
    levee_terrain,
)
from antennaknobs.web import server  # first: adapter cannot be imported alone
from antennaknobs.web import adapter
from momwire import BSplineSolver

F, H0 = 21.2, 6.1
SOIL = (13.0, 0.005)
PRESETS = ("levee", "cliff", "hillside")


def _engine(ground):
    p = merge_params(Builder.default_params, {"design_freq": F, "freq": F, "base": H0})
    return MomwireEngine(
        Builder(p), solver=BSplineSolver, solver_kwargs={"degree": 2}, ground=ground
    )


def _grid(eng):
    """Gain in dBi on the (theta, phi) grid."""
    return np.asarray(eng.far_field(n_theta=90, n_phi=72, del_theta=1, del_phi=5).rings)


def _req(preset: str) -> dict:
    return {
        "geometry": "dipoles.invvee",
        "momwire_model": "bspline",
        "ground": True,
        "ground_model": "terrain",
        "terrain": {"preset": preset},
    }


# ---------------------------------------------------------------------------
# the default itself
# ---------------------------------------------------------------------------


def test_diffraction_is_on_by_default():
    """Bare construction and every shipped constructor, not just the dataclass."""
    one = (Facet(None, 0.0, *SOIL),)
    assert (
        Terrain(sectors=(Sector(az0=0.0, az1=360.0, facets=one),)).diffraction is True
    )
    assert flat_terrain(*SOIL).diffraction is True
    assert cliff_terrain(
        edge=10.0, drop=10.0, inner=SOIL, outer=(80.0, 1e-3)
    ).diffraction
    assert hillside_terrain(
        flat_width=20.0, up_slope_deg=15.0, down_slope_deg=10.0
    ).diffraction
    assert levee_terrain(
        crest_width=3.0,
        slope_deg=20.0,
        drop_water=10.67,
        drop_land=7.6,
        water=(80.0, 1e-3),
        land=SOIL,
    ).diffraction


# ---------------------------------------------------------------------------
# the web pin
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("preset", PRESETS)
def test_the_web_solve_path_pins_specular(preset):
    assert adapter._terrain_from_request(_req(preset)).diffraction is False


@pytest.mark.parametrize("preset", PRESETS)
def test_the_web_cuts_path_pins_specular(preset):
    """A cut has to be a cut OF the grid it is read against.

    The packed wire form carries facets only — never the flag — so the cuts
    side cannot inherit the choice from the request and has to make the same
    one independently. If these two ever disagree, the chart draws one field's
    cut across the other field's pattern and nothing in the payload says so.
    """
    t = adapter._terrain_from_request(_req(preset))
    assert server._terrain_from_packed(adapter._pack_terrain(t)).diffraction is False


def test_the_pin_is_not_vacuous():
    """The pinned field and the default field genuinely differ.

    Without this, every assertion above would survive a world in which
    diffraction changed nothing — which is the world in which the pin, the
    dwell path and the cost measurement are all pointless. On the hillside
    preset the uphill band is the loud part: geometric optics reports grazing
    cancellation through a hill that in fact shadows it.
    """
    spec = adapter._terrain_from_request(_req("hillside"))
    assert spec.diffraction is False
    utd = dataclasses.replace(spec, diffraction=True)
    g_spec = _grid(_engine(("terrain", spec)))
    g_utd = _grid(_engine(("terrain", utd)))
    assert np.max(np.abs(g_utd - g_spec)) > 1.0  # dB
