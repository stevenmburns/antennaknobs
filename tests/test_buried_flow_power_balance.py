"""Buried-flow unit 1: the efficiency leg has a physics gate and an outside
reference (2026-09-03, the buried radial flow plan).

Two legs of the buried radial flow were anchored before this file: the
feedpoint impedance (BLE 1937 in momwire, the bspline degree pair) and the
mesh. The radiated fraction — "where do the watts go" — was not. Two gates:

1. POWER BALANCE on the catalog deck. Gain is power density per input watt,
   so the hemispherical integral of linear gain is P_rad / P_in. It must not
   exceed one (a fill that double-counts the image, or a P_in taken from the
   wrong port, would push it over), and adding buried radials must raise it
   monotonically — that is the whole reason a screen is buried. Measured on
   verticals.buried_radial_vertical at soil A (eps_r 13, sigma 0.005):

       N   Z_in                 eta
       1   168.186 + 43.070j    0.0766
       2   107.964 + 43.057j    0.1189
       3    87.020 + 41.693j    0.1479
       4    75.850 + 40.451j    0.1699

   The same ordering holds on poor (5/0.001: 0.060 → 0.143) and good
   (20/0.03: 0.223 → 0.349) soil, and good > A > poor at every N.

2. AN OUTSIDE REFERENCE for the pattern code over a Sommerfeld ground. The
   buried deck itself has no second engine (NEC-2 has no buried wire, and NEC-5
   is not the reference below ground by decision), so the check is on a deck
   both engines serve — verticals.raised_vertical — and on the quantity that
   does not depend on which engine's input resistance you believe: the
   RADIATED POWER for a fixed drive, eta * R_in. Measured:

       ground        momwire  eta*R      nec2++  eta*R
       pec           49.52              49.57          (0.10 %)
       A 13/0.005    14.88              14.90          (0.13 %)
       good 20/0.03  17.96              17.98          (0.11 %)

   The two engines differ by 9 % in R_in on this deck (a basis-class question
   for the impedance leg, not this one); their far-field integrals agree to
   0.1 % once that is divided out. Bar 1 %.

   Recorded, not gated: nec2++'s own radiated fraction over PEC reads 1.057 —
   above unity — where momwire's reads 0.963 (grid clipping at the horizon,
   where the PEC vertical peaks). Filed as an AK issue from this unit.
"""

import pytest

from antennaknobs.designs.verticals.buried_radial_vertical import (
    Builder as BuriedRadialVertical,
)
from antennaknobs.designs.verticals.raised_vertical import Builder as RaisedVertical
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.far_field import radiated_fraction

from conftest import needs_pynec

SOIL_A = (13.0, 0.005)


def _eta_and_r(engine):
    z = engine.impedance()[0]
    eta = radiated_fraction(engine.far_field())
    return eta, z.real


@pytest.mark.antenna_computation_check
def test_bf1_buried_radials_raise_the_radiated_fraction_and_never_past_one(
    record_property,
):
    etas = []
    for n in (1, 2, 4):
        b = BuriedRadialVertical()
        b.n_radials = n
        eta, r = _eta_and_r(MomwireEngine(b, ground=("finite",) + SOIL_A, ground_z=0.0))
        record_property(f"eta_n{n}", eta)
        record_property(f"r_in_n{n}", r)
        assert 0.0 < eta <= 1.0, f"N={n}: radiated fraction {eta:.4f} is not a fraction"
        etas.append(eta)
    assert etas[0] < etas[1] < etas[2], (
        f"more buried radials must radiate more of the input power: {etas}"
    )
    # The screen is worth something: one to four radials is not a rounding
    # step (measured 0.077 -> 0.170; bar with margin).
    assert etas[2] - etas[0] > 0.05, etas


@needs_pynec
@pytest.mark.parametrize(
    "ground",
    ["pec", ("finite", 13.0, 0.005)],
    ids=["pec", "soil-a"],
)
def test_bf1_the_radiated_power_agrees_with_nec2_for_a_fixed_drive(
    ground, record_property
):
    from antennaknobs.engines.pynec import PyNECEngine

    eta_m, r_m = _eta_and_r(MomwireEngine(RaisedVertical(), ground=ground))
    eta_n, r_n = _eta_and_r(PyNECEngine(RaisedVertical(), ground=ground))
    p_m, p_n = eta_m * r_m, eta_n * r_n
    rel = abs(p_m - p_n) / (0.5 * (p_m + p_n))
    record_property("momwire_eta_R", p_m)
    record_property("nec2_eta_R", p_n)
    record_property("rel_diff", rel)
    assert 0.0 < eta_m <= 1.0, f"momwire radiated fraction {eta_m:.4f}"
    assert rel <= 0.01, (
        f"radiated power for a fixed drive: momwire {p_m:.3f} vs nec2++ {p_n:.3f} "
        f"({rel:.2%} apart, bar 1 %). The two engines' R_in differ by ~9 % on "
        "this deck and that is NOT what this gate measures; a miss here is the "
        "far-field integration or the ground reflection, on one side or the other."
    )
