"""AK's single-valued-soil advisory (issue #1175, follow-on #1188).

The app serves six fixed (εr, σ) presets. Real soil disperses: in K6STI's
Hagn/Messier tables (GC 1.0) pastoral εr falls 33 → 15 between 1.8 and
28.5 MHz while σ roughly doubles. #1175 measured what that costs, comparing
the served single-valued "average" soil against the frequency-dependent value
at each band:

    buried_radial_vertical      1.8   5.9 %    14.2  17.7 %
    (48 radials)                7.1  10.4 %    28.5  31.9 %

    invvee, apex 7 m            7.1   9.1 %    14.2   2.6 %
    (elevated)                                 28.5   1.3 %

Opposite trends, and the reason is geometric rather than spectral: a
ground-mounted screen never gets electrically further from the ground, an
antenna at fixed height does. So this note belongs to the buried class and
firing it elsewhere would be exactly the noise #1144's ranking exists to
prevent.

It is AK's advisory, not momwire's — the fact is about the app's soil table,
not the solver, which is handed two numbers and uses them correctly. It rides
the #1144 channel, which carries category + text and does not care who raised
it.

Gates:

- G-1175-1  it fires on a buried deck at and above the band where the error
            passes ~15 %, and carries this deck's own frequency.
- G-1175-2  it is SILENT below that, on an elevated deck, without ground, and
            over PEC — four separate ways to be wrong in the noisy direction.
- G-1175-3  the text carries the measured numbers and both issue numbers, so
            a reader can check it rather than trust it.
- G-1175-4  it reaches the served response beside momwire's own advisories.
"""

from __future__ import annotations

import warnings

import pytest

import antennaknobs.web.server as server  # noqa: F401 — resolves the cycle
import momwire.bspline as _bs
from antennaknobs.web.adapter import (
    SOIL_DISPERSION_CATEGORY,
    SOIL_DISPERSION_MHZ,
    _soil_dispersion_advisory,
)

COARSE = 4


def _req(**over) -> dict:
    r = {
        "geometry": "verticals.buried_radial_vertical",
        "backend": "bspline",
        "ground": True,
        "ground_model": "sommerfeld",
        "n_per_wire": COARSE,
        "design_freq_mhz": 28.5,
        "measurement_freq_mhz": 28.5,
    }
    r.update(over)
    return r


def _solve(**over) -> dict:
    _bs._GEOMETRY_CACHE.clear()
    _bs._BASIS_POLY_CACHE.clear()
    server._SOLVE_CACHE.clear()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return server.solve(_req(**over))


def _cats(out) -> list[str]:
    return [a["category"] for a in out.get("advisories", [])]


# --- G-1175-1 -------------------------------------------------------------


@pytest.mark.parametrize("freq", [14.0, 21.0, 28.5])
def test_g1175_1_it_fires_on_a_buried_deck_at_the_bands_that_matter(freq):
    out = _solve(design_freq_mhz=freq, measurement_freq_mhz=freq)
    assert SOIL_DISPERSION_CATEGORY in _cats(out), out.get("advisories")


def test_g1175_1_the_text_names_this_decks_own_frequency():
    """The class figures were already writable in a docstring; the deck's own
    frequency is what a live advisory adds."""
    out = _solve(design_freq_mhz=21.0, measurement_freq_mhz=21.0)
    text = next(
        a["text"]
        for a in out["advisories"]
        if a["category"] == SOIL_DISPERSION_CATEGORY
    )
    assert "21 MHz" in text, text


# --- G-1175-2: the four ways to be noisy ---------------------------------


def test_g1175_2_silent_below_the_band_where_it_matters():
    """At 7 MHz #1175 measured 10.4% and at 1.8 MHz 5.9%, inside the spread
    of the preset menu itself. Warning there would be noise."""
    assert SOIL_DISPERSION_CATEGORY not in _cats(
        _solve(design_freq_mhz=7.0, measurement_freq_mhz=7.0)
    )


def test_g1175_2_silent_on_an_elevated_deck():
    """The opposite trend: 1.3% at 28.5 MHz on the inv-vee. This is the gate
    that stops the note becoming a banner on every high-band solve."""
    out = _solve(
        geometry="dipoles.invvee", design_freq_mhz=28.47, measurement_freq_mhz=28.47
    )
    assert SOIL_DISPERSION_CATEGORY not in _cats(out)


@pytest.mark.parametrize(
    "over", [{"ground": False}, {"ground": True, "ground_model": "pec"}]
)
def test_g1175_2_silent_without_finite_soil(over):
    """Over free space or PEC there are no soil constants for the note to be
    about — asserted through the helper, since these two paths do not all
    reach a solve."""
    assert _soil_dispersion_advisory(_req(**over), True, 28.5) is None


def test_g1175_2_silent_when_the_deck_is_not_buried():
    assert _soil_dispersion_advisory(_req(), False, 28.5) is None


def test_g1175_2_the_band_edge_is_inclusive_and_pinned():
    """A bar nobody can see the value of is a bar nobody can re-measure."""
    assert SOIL_DISPERSION_MHZ == 14.0
    assert _soil_dispersion_advisory(_req(), True, SOIL_DISPERSION_MHZ) is not None
    assert _soil_dispersion_advisory(_req(), True, SOIL_DISPERSION_MHZ - 0.01) is None


# --- G-1175-3: the prose is checkable ------------------------------------


def test_g1175_3_the_text_carries_the_measured_numbers_and_its_issues():
    a = _soil_dispersion_advisory(_req(), True, 28.5)
    text = a["text"]
    for token in ("17.7", "31.9", "5.9", "33", "15", "1175", "1188"):
        assert token in text, token
    low = text.lower()
    assert "indicative" in low, "the note must say what to do, not only what is true"
    assert "advisory" in low and "refused" in low, "it must not read as a failure"


def test_g1175_3_the_category_is_aks_own_not_momwires():
    """It rides momwire's channel but it is not a momwire advisory: the
    frontend must render an unfamiliar category in full rather than collapse
    it, which is what its own gate in solverAdvisories.test.tsx pins."""
    from antennaknobs.engines.momwire import _is_momwire_advisory

    class _Fake:
        __module__ = "antennaknobs.web.adapter"

    assert not _is_momwire_advisory(_Fake)
    assert not SOIL_DISPERSION_CATEGORY.startswith("momwire")


# --- G-1175-4: it reaches the wire ---------------------------------------


def test_g1175_4_it_is_served_beside_the_solvers_own():
    """The channel is one list. This pins that AK's note does not displace
    momwire's — on this deck at this mesh momwire raises none, so the
    assertion is that ours is present and the list shape is intact."""
    out = _solve()
    adv = out["advisories"]
    assert adv and all(set(a) == {"category", "text"} for a in adv)
    assert adv[-1]["category"] == SOIL_DISPERSION_CATEGORY, "AK's goes last"
