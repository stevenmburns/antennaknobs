"""#1135: the below/below reach is pre-flighted at construction.

`verticals.buried_radial_vertical` advertises knob ranges that include
combinations momwire cannot solve, and the user used to learn that only when
the fill raised -- tens of seconds in, after the mixed-medium set-up. The
engine now asks momwire before the solve, so the app's knob panel can grey the
combination instead of offering it.

The bound is momwire's and is ASKED rather than re-derived here: its cap is in
in-medium wavelengths and its grazing floor moved 0.1 -> 0.05 deg at
momwire#935, so a formula copied into this repo would silently stop matching.
That is the failure mode `_buried_refusal`'s own note names.

These gates SKIP on a momwire without `below_reach_refusal` -- the submodule
pointer may sit behind the momwire PR that adds it, and an install too old to
be asked is not a refusal.
"""

import pathlib
import re

import numpy as np
import pytest

from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines.momwire import MomwireEngine

momwire = pytest.importorskip("momwire")

pytestmark = pytest.mark.skipif(
    not hasattr(momwire, "below_reach_refusal"),
    reason="momwire predates below_reach_refusal (stevenmburns/momwire#1135)",
)


def _pinned_momwire_version():
    """The `momwire==X.Y.Z` string in pyproject — the contract users install
    against, which is what the fallback is keyed to (not the submodule, whose
    pointer deliberately runs ahead)."""
    text = (pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    m = re.search(r'"momwire==([^"]+)"', text)
    assert m, "no momwire== pin found in pyproject.toml"
    return m.group(1)


SOIL_A = ("finite", 13.0, 0.005)
SOIL_B = ("finite", 20.0, 0.03)


def _deck(**knobs):
    b = Builder()
    for k, v in knobs.items():
        setattr(b, k, v)
    return b


def _constructs(ground, **knobs):
    try:
        MomwireEngine(_deck(**knobs), ground=ground)
        return True, None
    except ValueError as e:
        return False, str(e)


def test_the_shipped_catalog_deck_is_not_refused():
    """The defaults are what the app opens on. A pre-flight that greyed them
    would be worse than none."""
    ok, why = _constructs(SOIL_A)
    assert ok, why


def test_the_issues_own_case_refuses_by_name():
    """#1135's headline: n_radials=4, length_factor=1.2, radial_factor=1.5
    over soil B, where the opposite tips are 38.0 m apart against a 19.06 m
    cap. The sentence is momwire's own, so it carries the deck's numbers."""
    ok, why = _constructs(SOIL_B, length_factor=1.2, radial_factor=1.5)
    assert not ok
    assert "below/below" in why and "in-medium wavelengths" in why


def test_the_threshold_sits_where_the_issue_measured_it():
    """#1135 verified the soil-B boundary by SOLVING across it -- 0.85 serves,
    0.95 refuses, predicted 0.903 between them. The pre-flight has to land in
    the same place, or it is a different bound wearing the same name."""
    assert _constructs(SOIL_B, radial_factor=0.85)[0]
    assert not _constructs(SOIL_B, radial_factor=0.95)[0]


def test_a_shallow_deck_the_935_floor_just_made_servable_passes(monkeypatch):
    """momwire#935 moved the grazing floor 0.1 -> 0.05 deg. This deck sits
    between the two, so it was refused before #935 and is served now, and the
    pre-flight must track the floor as it IS -- the gate a copied constant
    fails.

    `depth=0.0126, radial_factor=0.9` gives theta_min = 0.076 deg (measured,
    not derived). The obvious candidate -- a 3 mm depth -- is not available:
    the rise is graded with a 12.5 mm node panel, so `graded_wire` refuses any
    depth under that outright, and no BRV deck shallower than ~12.6 mm can be
    BUILT whatever the floor says. Worth knowing before someone reaches for a
    millimetre-class depth to test this bound.
    """
    from momwire import _sommerfeld_below

    knobs = dict(depth=0.0126, radial_factor=0.9)
    ok, why = _constructs(SOIL_A, **knobs)
    assert ok, why
    # and it really is BETWEEN the two floors: put the old one back and it
    # must refuse, or this deck is not testing the floor at all.
    monkeypatch.setattr(_sommerfeld_below, "_SOMM_BELOW_TH_MIN_DEG", 0.1)
    ok_old, why_old = _constructs(SOIL_A, **knobs)
    assert not ok_old, (
        "the deck is served at a 0.1 deg floor too, so it does not straddle "
        "the change momwire#935 made and this gate proves nothing"
    )
    assert "grazing floor" in why_old


def test_refl_coef_is_not_pre_flighted():
    """Only the Sommerfeld model builds a below/below grid. `finite-fast` is
    refl-coef everywhere, so a deck past the below cap is not its problem and
    must not be refused for it."""
    ok, why = _constructs(
        ("finite-fast", 20.0, 0.03), length_factor=1.2, radial_factor=1.5
    )
    assert ok, why


@pytest.mark.parametrize("radial_factor", [0.3, 0.6, 0.9, 1.2, 1.5])
@pytest.mark.parametrize("ground", [SOIL_A, SOIL_B])
def test_the_preflight_agrees_with_the_solve(ground, radial_factor):
    """The gate that matters, on the app's own knob axis: whatever the
    pre-flight says, the SOLVE must say the same. A false refusal greys a
    combination the app could have offered; a false pass is the 20 s failure
    this issue is about.
    """
    ok, why = _constructs(ground, radial_factor=radial_factor)
    if not ok:
        # It refused at construction. Confirm the fill would have too, by
        # asking momwire directly on the same geometry -- building the engine
        # is the only way to get the polylines, and it is what just refused.
        assert "below/below" in why
        return
    eng = MomwireEngine(_deck(radial_factor=radial_factor), ground=ground)
    pts = np.concatenate([np.asarray(pl, float) for pl in eng._polylines])
    assert (
        momwire.below_reach_refusal(pts, 0.0, (ground[1], ground[2]), 7.1e6) is None
    ), "constructed but momwire's own check refuses the same geometry"


# ---------------------------------------------------------------------------
# the fallback's own expiry
# ---------------------------------------------------------------------------

# The momwire pin this fallback exists FOR. `_below_reach_refusal` reaches
# momwire's helper through `getattr` and returns None when it is absent, so an
# install resolving momwire from PyPI keeps working in the window before the
# release that carries it. `below_reach_refusal` landed on momwire main AFTER
# 0.49.0, so every 0.49.0 install lacks it and the fallback is load-bearing.
_FALLBACK_EXPIRES_AFTER_PIN = "0.49.0"


def test_the_getattr_fallback_expires_with_the_pin():
    """A self-firing tripwire for the fallback in `_below_reach_refusal`.

    Green while the pin still reads the version that predates the helper;
    RED the moment it is bumped, so the fallback is deleted then rather than
    outliving its reason. Keyed on the PIN STRING, deliberately not on a
    capability probe: the submodule already has the helper, so `hasattr`
    is true in dev mode today and a probe-keyed tripwire would never fire.

    The failure mode this is against is already in this tree's history — an
    audit found a fallback whose conditions had been met two pin bumps
    earlier, with a docstring still claiming the old pin.
    """
    pinned = _pinned_momwire_version()
    assert pinned == _FALLBACK_EXPIRES_AFTER_PIN, (
        f"the momwire pin is now {pinned}, past the {_FALLBACK_EXPIRES_AFTER_PIN} "
        "that `_below_reach_refusal`'s getattr fallback exists for. If that "
        "release carries `below_reach_refusal`, DELETE the fallback (and this "
        "test, and the module-level skipif above): the pin is `==`, so there "
        "is no resolution path to an older momwire and the fallback is "
        "provably dead rather than probably unused. See antennaknobs#1135."
    )
