"""The pattern cut is continuous through elevation 0 over a perfect ground
(AK#1630).

AC6LA set the azimuth cut to elevation 0 on his cardioid over a perfect ground
and the antennaknobs trace vanished; at 1 degree it was there. A perfect ground
is shipped to the cut code as the placeholder eps_r = 1e10, and Fresnel on that
is PEC everywhere except exact grazing: there cos(theta) = 0 and
rho_v = (eps*0 - Q)/(eps*0 + Q) = -1 for any finite eps, so a vertical's image
cancelled instead of doubling. 6.7 dBi at elevation 1, -310 dBi at elevation 0.
A perfect ground now takes its exact coefficients, rho_h = -1 and rho_v = +1.

The NEC overlay was never the part that vanished: the chart clamps an
elevation past the grid's last row onto that row.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

import antennaknobs.web.examples  # noqa: F401  registration order
from antennaknobs.file_designs import builder_from_file
from antennaknobs.web import server
from antennaknobs.web.adapter import _make_example
from antennaknobs.web.server import _pattern_cuts

CARDIOID = (
    Path(__file__).parent / "fixtures" / "eznec_gyrator_1595" / "Cardioidmodnec5.nec"
)


def _vertical_hertzian(eps_r, sigma):
    """A 1 A, 1 cm vertical element standing on the ground, with the
    free-space closed-form norm, so free space would read 1.76 dBi at the
    horizon."""
    k = 0.44
    eps_im = -sigma / (2 * math.pi * 21e6 * 8.8541878128e-12) if sigma else 0.0
    return {
        "wires": [
            {
                "knot_positions": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.01]],
                "knot_currents_re": [1.0, 1.0],
                "knot_currents_im": [0.0, 0.0],
            }
        ],
        "k_meas_m_inv": k,
        "ground": True,
        "ground_eps_r": eps_r,
        "ground_eps_im": eps_im,
        "ground_sigma": sigma,
        "directivity_norm": 3.0 / (2.0 * 0.01 * 0.01),
    }


def test_over_a_perfect_ground_the_horizon_is_where_the_image_doubles():
    out = _vertical_hertzian(server._PEC_GROUND_EPS_R, 0.0)
    at_0 = np.asarray(_pattern_cuts(out, 0.0, 0.0)["azimuth"])
    at_1 = np.asarray(_pattern_cuts(out, 1.0, 0.0)["azimuth"])
    # Direct plus an in-phase image: four times the power, +6.02 dB on 1.76.
    assert np.allclose(at_0, 10 * math.log10(1.5 * 4), atol=1e-3)
    assert np.allclose(at_0, at_1, atol=0.01)


def test_over_a_real_ground_exact_grazing_stays_a_null():
    """Not the placeholder: over a finite medium rho_v -> -1 at grazing is
    physics (the space wave vanishes on the surface), and it stays."""
    out = _vertical_hertzian(13.0, 0.005)
    cuts = _pattern_cuts(out, 0.0, 0.0)
    assert max(cuts["azimuth"]) < -100.0
    assert max(_pattern_cuts(out, 5.0, 0.0)["azimuth"]) > -10.0


def test_the_cardioid_keeps_its_main_lobe_at_elevation_0():
    cls = builder_from_file(str(CARDIOID))
    ex = _make_example("Cardioidmodnec5", cls)
    f = cls().freq
    out = ex.momwire_solve(
        {
            "measurement_freq_mhz": f,
            "design_freq_mhz": f,
            "ground": True,
            "ground_model": "pec",
        }
    )
    server._attach_derived_em_fields(out)
    server._attach_gain_norm(out)
    peak = {el: max(_pattern_cuts(out, el, 0.0)["azimuth"]) for el in (0.0, 1.0)}
    # EZNEC puts this cardioid's peak AT the horizon, 6.78 dBi.
    assert peak[0.0] == pytest.approx(peak[1.0], abs=0.1)
    assert peak[0.0] == pytest.approx(6.78, abs=0.2)
