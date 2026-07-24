"""Levee bracketing harness (scripts/bench_levee_bracket.py, issue #535).

Pins the validity-band geometry, the first-lobe picker, and — nec2c-gated —
the GD-cliff deck authoring, including the trap the harness exists to
encode: the two-media cliff only affects the pattern under ``RP 2``, never
``RP 0``. If nec2c's behavior (or our card authoring) drifts, the cliff and
flat decks stop differing and the low-angle assertion here catches it.
"""

from __future__ import annotations

import importlib.util
import math
import shutil
from pathlib import Path

import numpy as np
import pytest

_PATH = Path(__file__).parent.parent / "scripts" / "bench_levee_bracket.py"
_spec = importlib.util.spec_from_file_location("bench_levee_bracket", _PATH)
lb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lb)

needs_nec2c = pytest.mark.skipif(
    shutil.which("nec2c") is None, reason="nec2c not on PATH"
)


# The motivating QTH (issue #534/#535): 20 ft pole, 10 ft crest, 20 deg
# slopes, 25 ft to land / 35 ft to water.
H0, CHW, SLOPE = 6.1, 1.5, 20.0
DROP_LAND, DROP_WATER = 7.62, 10.67


def test_validity_bands_land_side():
    psi_crest, psi_plain, x_toe, h_eff = lb.validity_bands(H0, CHW, SLOPE, DROP_LAND)
    assert psi_crest == pytest.approx(76.2, abs=0.1)
    assert h_eff == pytest.approx(13.72, abs=0.01)
    assert x_toe == pytest.approx(22.4, abs=0.1)
    assert psi_plain == pytest.approx(31.5, abs=0.2)


def test_validity_bands_water_side():
    _, psi_plain, x_toe, h_eff = lb.validity_bands(H0, CHW, SLOPE, DROP_WATER)
    assert h_eff == pytest.approx(16.77, abs=0.01)
    assert x_toe == pytest.approx(30.8, abs=0.1)
    assert psi_plain == pytest.approx(28.6, abs=0.2)


def test_validity_bands_flat_limit():
    """Zero drop degenerates to the flat model: the plain band reaches all
    the way up to the crest band and h_eff is the pole height itself."""
    psi_crest, psi_plain, _, h_eff = lb.validity_bands(H0, CHW, SLOPE, 0.0)
    assert h_eff == H0
    assert psi_plain == pytest.approx(psi_crest, abs=1e-9)


def test_first_lobe_picks_lowest_local_max():
    el = np.arange(0.0, 46.0)
    gain = np.sin(np.radians(el * 6)) * 5  # peaks at 15 deg, then again higher
    lobe_el, lobe_g = lb.first_lobe(el, gain)
    assert lobe_el == pytest.approx(15.0, abs=1.0)
    assert lobe_g == pytest.approx(5.0, abs=0.1)


def test_first_lobe_monotone_falls_back_to_max():
    el = np.arange(1.0, 46.0)
    gain = el * 0.1  # no interior local max
    lobe_el, _ = lb.first_lobe(el, gain)
    assert lobe_el == 45.0


@needs_nec2c
def test_cliff_deck_rp2_differs_from_flat_rp0_at_low_angles():
    """The whole point of RP 2: a water cliff 10.7 m below must raise the
    low-elevation gain by several dB over the flat crest model — and under
    RP 0 the very same GD card must do nothing at all."""
    freq, soil = 21.2, ("finite", 13.0, 0.005)
    cliff = (80.0, 0.005, CHW, DROP_WATER)

    flat = lb.run_nec2c_pattern(
        lb.author_cliff_deck("dipoles.invvee", freq, H0, soil, None, 0)
    )
    rp0_gd = lb.run_nec2c_pattern(
        lb.author_cliff_deck("dipoles.invvee", freq, H0, soil, cliff, 0)
    )
    rp2 = lb.run_nec2c_pattern(
        lb.author_cliff_deck("dipoles.invvee", freq, H0, soil, cliff, 2)
    )

    el_f, g_f = lb.cliff_elevation_cut(flat, phi=0.0)
    el_0, g_0 = lb.cliff_elevation_cut(rp0_gd, phi=0.0)
    el_2, g_2 = lb.cliff_elevation_cut(rp2, phi=0.0)

    # RP 0 ignores GD bit-for-bit (the documented nec2c trap).
    assert np.array_equal(g_f, g_0)

    # RP 2 must lift the low-angle field substantially (measured: +7 to +9 dB
    # at 5-10 deg for this geometry).
    for angle, min_lift in ((5.0, 5.0), (10.0, 4.0)):
        lift = lb.gain_at(el_2, g_2, angle) - lb.gain_at(el_f, g_f, angle)
        assert lift > min_lift, f"cliff lift at {angle} deg: {lift:.2f} dB"

    # And the cliff should approach the raised-effective-height physics at
    # low angles: the first lobe lands well below the flat model's.
    lobe_cliff, _ = lb.first_lobe(el_2, g_2)
    lobe_flat, _ = lb.first_lobe(el_f, g_f)
    assert lobe_cliff < lobe_flat


def test_deck_has_gd_card_only_when_cliff_given():
    deck_flat = lb.author_cliff_deck(
        "dipoles.invvee", 21.2, H0, ("finite", 13.0, 0.005), None, 0
    )
    deck_cliff = lb.author_cliff_deck(
        "dipoles.invvee",
        21.2,
        H0,
        ("finite", 13.0, 0.005),
        (80.0, 0.005, 1.5, 10.67),
        2,
    )
    assert not any(ln.startswith("GD") for ln in deck_flat.splitlines())
    gd = [ln for ln in deck_cliff.splitlines() if ln.startswith("GD")]
    # 4 leading integer fields then eps2 sig2 clt cht — nec2c card format.
    assert len(gd) == 1 and gd[0].split()[1:5] == ["0", "0", "0", "0"]
    assert [float(x) for x in gd[0].split()[5:9]] == [80.0, 0.005, 1.5, 10.67]
    assert any(ln.startswith("RP 2") for ln in deck_cliff.splitlines())


def test_specular_distance_geometry():
    """Sanity: the specular point d = h/tan(psi) crosses the crest edge at
    psi_crest and the slope toe at psi_plain — the bands tile the quadrant."""
    psi_crest, psi_plain, x_toe, h_eff = lb.validity_bands(H0, CHW, SLOPE, DROP_LAND)
    assert H0 / math.tan(math.radians(psi_crest)) == pytest.approx(CHW)
    assert h_eff / math.tan(math.radians(psi_plain)) == pytest.approx(x_toe)
    assert 0 < psi_plain < psi_crest < 90
