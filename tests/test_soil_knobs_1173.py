"""Soil constants as knobs (issue #1173).

Until #1173 every finite-ground solve used one hard-coded soil
(``DEFAULT_GROUND`` = 10 / 0.002) and the user had no handle on it. These
tests pin the four things that were asked for and the two that are easy to
get silently wrong.

The load-bearing one is ``test_every_preset_survives_its_own_clamp``. It
already caught a real defect: the issue suggested an eps_r range of 1-80,
but sea water is eps_r 81, so the served "salt water" preset was being
clamped to 80.0 by the very endpoint that served it. A test that only
checked "a preset exists" or "the clamp clamps" would have passed through
that happily — the bug lives exactly in the seam between the two.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from antennaknobs.nec_export import _gn
from antennaknobs.web.server import _sweep_design_key, app

# Imported after server: adapter and examples import each other cyclically,
# and only the examples-first entry order (which server triggers) resolves.
from antennaknobs.web.adapter import (
    DEFAULT_GROUND,
    SOIL_EPS_R_RANGE,
    SOIL_SIGMA_RANGE,
    _ground_for_engine,
    _nec5_ground_spec,
    _pynec_ground_spec,
    _soil_from_request,
    soil_presets_schema,
    soil_ranges_schema,
)

# Every request-to-engine mapping the app has. Parametrising over all three
# is the point: the soil has to reach PyNEC and NEC-5 as well as momwire,
# and wiring only the one you happen to be testing is the obvious way to
# half-land this feature.
GROUND_SPECS = (
    ("momwire", _ground_for_engine),
    ("pynec", _pynec_ground_spec),
    ("nec5", _nec5_ground_spec),
)


def _req(**over) -> dict:
    return {"ground": True, "ground_model": "sommerfeld", **over}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# --- the defaults nothing may disturb ------------------------------------


@pytest.mark.parametrize("name,fn", GROUND_SPECS)
def test_a_request_without_soil_solves_exactly_what_it_did_before(name, fn):
    """The compatibility contract: every client that predates #1173, and
    every internal caller that never learned about the field, must keep
    getting DEFAULT_GROUND. This is what makes the feature shippable
    without re-baselining a single golden."""
    assert fn(_req()) == ("finite",) + tuple(DEFAULT_GROUND[1:])


def test_soil_defaults_are_default_ground():
    assert _soil_from_request({}) == (DEFAULT_GROUND[1], DEFAULT_GROUND[2])
    assert soil_ranges_schema()["eps_r"]["default"] == DEFAULT_GROUND[1]
    assert soil_ranges_schema()["sigma"]["default"] == DEFAULT_GROUND[2]


# --- the soil actually reaches every engine ------------------------------


@pytest.mark.parametrize("name,fn", GROUND_SPECS)
def test_requested_soil_reaches_every_engine(name, fn):
    spec = fn(_req(soil={"eps_r": 20.0, "sigma": 0.0303}))
    assert spec == ("finite", 20.0, 0.0303), name


@pytest.mark.parametrize("name,fn", GROUND_SPECS)
def test_soil_reaches_the_fast_model_too(name, fn):
    """The reflection-coefficient path takes the same constants. NEC-5 is
    the documented exception — it has no refl-coef model, so "fast" is
    served by its native Sommerfeld — but the SOIL must survive either
    way, which is what this asserts rather than the model name."""
    spec = fn(_req(ground_model="fast", soil={"eps_r": 20.0, "sigma": 0.0303}))
    assert spec[1:] == (20.0, 0.0303), name


def test_terrain_is_untouched_by_the_soil_knobs():
    """Non-goal guard (the issue says so explicitly): terrain media stay
    fixed, so a soil request must not leak into the terrain crest medium."""
    flat = _ground_for_engine(_req(soil={"eps_r": 81.0, "sigma": 5.0}))
    terrain = _ground_for_engine(
        _req(ground_model="terrain", soil={"eps_r": 81.0, "sigma": 5.0})
    )
    assert flat == ("finite", 81.0, 5.0)
    assert terrain[0] == "terrain"
    crest = terrain[1].crest_medium
    assert crest != (81.0, 5.0), "soil leaked into the terrain crest medium"


# --- the presets -----------------------------------------------------------


def test_every_preset_survives_its_own_clamp():
    """A served preset the serving endpoint would itself clamp is a bug.

    This caught the real one: eps_r 81 sea water against an 80 ceiling.
    Assert on the pair, not on the bounds — checking `preset <= max` would
    restate the clamp's own arithmetic instead of exercising it.
    """
    for p in soil_presets_schema():
        got = _soil_from_request({"soil": {"eps_r": p["eps_r"], "sigma": p["sigma"]}})
        assert got == (p["eps_r"], p["sigma"]), f"{p['name']} is mutated by the clamp"


def test_presets_are_distinct_and_named():
    presets = soil_presets_schema()
    assert len(presets) >= 5
    assert len({p["name"] for p in presets}) == len(presets)
    assert len({(p["eps_r"], p["sigma"]) for p in presets}) == len(presets)
    for p in presets:
        assert p["label"] and p["tooltip"]


def test_presets_span_the_ladder():
    """The menu is useless if every entry is the same order of magnitude:
    it has to reach from dry rock to sea water."""
    sigmas = [p["sigma"] for p in soil_presets_schema()]
    assert min(sigmas) <= 1e-3
    assert max(sigmas) >= 1.0


# --- untrusted input -------------------------------------------------------


@pytest.mark.parametrize(
    "junk",
    [
        {"eps_r": "NaN", "sigma": None},
        {"eps_r": float("nan"), "sigma": float("inf")},
        {"eps_r": -5.0, "sigma": -1.0},
        {"eps_r": 1e9, "sigma": 1e9},
        {"eps_r": None, "sigma": "0.01"},
        "not-a-mapping",
        None,
        [],
    ],
)
def test_junk_soil_never_escapes_the_clamp(junk):
    """These values would otherwise reach NEC's GN card and momwire's
    Sommerfeld grid."""
    eps_r, sigma = _soil_from_request({"soil": junk})
    assert SOIL_EPS_R_RANGE[0] <= eps_r <= SOIL_EPS_R_RANGE[1]
    assert SOIL_SIGMA_RANGE[0] <= sigma <= SOIL_SIGMA_RANGE[1]


# --- the sweep-Z cache key (issue ask 3) -----------------------------------


def test_a_soil_change_is_a_new_sweep_curve():
    """The issue's third ask. The key is a blocklist, so a new physics
    field invalidates by default — but "by default" is a property of the
    blocklist that a future edit could quietly remove, which is precisely
    why it is pinned here rather than assumed.
    """
    base = _req(geometry="dipole", freqs_mhz=[14.0, 14.1])
    average = _sweep_design_key({**base, "soil": {"eps_r": 13.0, "sigma": 0.005}})
    seawater = _sweep_design_key({**base, "soil": {"eps_r": 81.0, "sigma": 5.0}})
    assert average != seawater, "a soil change silently hit the cached curve"


def test_the_same_soil_still_hits_the_cache():
    """The other half — an invalidation that never hits is also a bug."""
    base = _req(geometry="dipole", freqs_mhz=[14.0])
    soil = {"eps_r": 13.0, "sigma": 0.005}
    assert _sweep_design_key({**base, "soil": dict(soil)}) == _sweep_design_key(
        {**base, "soil": dict(soil)}
    )


def test_only_the_frequency_list_is_outside_the_sweep_key():
    """Guards the cache namespace against the obvious over-correction:
    a soil field that also shredded the freq-list exemption would make
    every refinement round a miss."""
    base = _req(geometry="dipole", soil={"eps_r": 13.0, "sigma": 0.005})
    assert _sweep_design_key({**base, "freqs_mhz": [14.0]}) == _sweep_design_key(
        {**base, "freqs_mhz": [14.0, 21.0, 28.0]}
    )


# --- the NEC export card (issue ask 3) -------------------------------------


def _gn_media(card: str) -> tuple[float, float]:
    """The (eps_r, sigma) a GN card carries. Parsed as numbers, not matched
    as substrings: the card renders in Fortran-ish scientific notation
    ("2.000000E+01"), so a substring check for "20" passes on text that
    never contained the value and fails on text that did."""
    fields = card.split()
    return float(fields[-2]), float(fields[-1])


def test_the_exported_gn_card_carries_the_soil():
    """`GN 2 ... eps_r sigma` — the deck a user downloads has to describe
    the antenna they were looking at, soil included."""
    card = _gn(_ground_for_engine(_req(soil={"eps_r": 20.0, "sigma": 0.0303})))
    assert card.startswith("GN 2 ")
    assert _gn_media(card) == pytest.approx((20.0, 0.0303))


def test_the_exported_gn_card_tracks_the_fast_model():
    card = _gn(
        _ground_for_engine(
            _req(ground_model="fast", soil={"eps_r": 81.0, "sigma": 5.0})
        )
    )
    assert card.startswith("GN 0 ")
    assert _gn_media(card) == pytest.approx((81.0, 5.0))


def test_the_exported_gn_card_still_defaults_without_soil():
    card = _gn(_ground_for_engine(_req()))
    assert _gn_media(card) == pytest.approx(tuple(DEFAULT_GROUND[1:]))


# --- the served schema -----------------------------------------------------


def test_capabilities_serves_the_soil_catalog(client):
    caps = client.get("/capabilities").json()
    assert caps["soil_presets"], "no soil presets served"
    assert caps["soil_ranges"]["sigma"]["log"] is True
    served = {p["name"] for p in caps["soil_presets"]}
    assert {"average", "salt-water"} <= served
    for p in caps["soil_presets"]:
        assert set(p) >= {"name", "label", "eps_r", "sigma", "tooltip"}


# --- the response constants (/cuts and the near field, issue ask 3) --------
#
# /cuts is stateless and the near-field/Fresnel maths reads the constants
# off the RESPONSE, not off the request — so "the soil reaches the cuts"
# is really "the response ships the soil the solve used". That makes
# _momwire_ground_fields the seam worth pinning: it derives its numbers
# from the engine's own ground tuple, so a soil that reached the engine
# necessarily reaches the cuts.


class _FakeEngine:
    """Just the two attributes _momwire_ground_fields reads."""

    def __init__(self, ground, model="sommerfeld"):
        self._ground = ground
        self._ground_model = model


def test_the_response_ships_the_soil_the_solve_used():
    from antennaknobs.web.adapter import _momwire_ground_fields

    eng = _FakeEngine(_ground_for_engine(_req(soil={"eps_r": 20.0, "sigma": 0.0303})))
    out = _momwire_ground_fields(eng, _req())
    assert out["ground_eps_r"] == 20.0
    assert out["ground_sigma"] == 0.0303


def test_the_response_still_ships_the_default_soil_without_the_field():
    from antennaknobs.web.adapter import _momwire_ground_fields

    out = _momwire_ground_fields(_FakeEngine(_ground_for_engine(_req())), _req())
    assert (out["ground_eps_r"], out["ground_sigma"]) == tuple(DEFAULT_GROUND[1:])
