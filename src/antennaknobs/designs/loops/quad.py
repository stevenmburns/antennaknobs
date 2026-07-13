"""Two-element cubical quad beam (L. B. Cebik, W4RNL).

A parasitic beam built from full-wave LOOPS instead of linear elements: a
driven square loop of ~1 wavelength circumference plus a slightly larger
parasitic reflector loop (~1.06 wl) spaced ~0.15 wl behind it. The driver is
fed at the centre of its bottom wire, so the horizontal bottom (and top)
wires carry the in-phase current maxima and the beam is HORIZONTALLY
POLARISED, firing broadside to the loop planes (toward the driver, away from
the reflector).

This fills the loop-beam gap in the catalog: the existing delta (triangle)
and diamond loops are single radiators, not the square-loop driver/reflector
beam. Versus a 2-element Yagi the quad gives a little more gain for its
boom length and a lower feed impedance.

Cebik's wideband 20 m proportions (frequency-independent ratios):
  driver    circumference 1.010 wl (side 0.2525 wl)
  reflector circumference 1.065 wl (side 0.2663 wl)
  spacing   0.155 wl
giving ~6.6-7.5 dBi forward gain across the band.

Geometry, in the framework's (x, y, z) convention:
  - x : boom axis; reflector behind at x = -spacing, driver at x = 0,
        beam fires toward +x
  - y : horizontal width of each square loop
  - z : height; both loop bottoms at `base`
The loops lie in planes of constant x.

       reflector (x=-spacing)      driver (x=0)
        TL----TR                    TL----TR        z = base + side
        |      |                    |      |
        |      |                    |      |
        BL----BR                    BL--F--BR        z = base
                          beam --> +x
"""

from antennaknobs import AntennaBuilder
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the loop bottom wires above ground.
            "base": 7.0,
            # Loop circumferences as fractions of a wavelength. Driver near
            # 1.0 wl (resonant); reflector larger -> inductive -> reflector.
            "driver_circ": 1.010,
            "reflector_circ": 1.065,
            # Driver-reflector spacing as a fraction of a wavelength.
            "spacing_factor": 0.155,
            "ui_params": MappingProxyType(
                {
                    # Quad driver feed is ~60-130 ohm; reference SWR to 50.
                    "target_z0": 50.0,
                    # Boom along x, loops span y/z; the xz view shows the
                    # driver-reflector spacing edge-on.
                    "default_view": "xz",
                    "driver_circ": {
                        "min": 0.95,
                        "max": 1.08,
                    },
                    "reflector_circ": {
                        "min": 1.0,
                        "max": 1.15,
                    },
                    "spacing_factor": {
                        "min": 0.1,
                        "max": 0.3,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05

        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        side_d = self.driver_circ * wavelength / 4
        side_r = self.reflector_circ * wavelength / 4
        spacing = self.spacing_factor * wavelength

        def square_loop(x, side, fed):
            """A square loop in the plane of constant x, bottom wire at
            z = base. If `fed`, a one-segment driven gap sits at the centre
            of the bottom wire (horizontal polarisation)."""
            half = side / 2
            z0, z1 = self.base, self.base + side
            BL = (x, -half, z0)
            BR = (x, half, z0)
            TR = (x, half, z1)
            TL = (x, -half, z1)
            ns = self.segs_for(side, quarter)
            wires = []
            if fed:
                # bottom wire: BL -> (-eps) -> [feed] -> (+eps) -> BR
                C0 = (x, -eps, z0)
                C1 = (x, eps, z0)
                wires.append((BL, C0, self.segs_for(half - eps, quarter), None))
                wires.append((C0, C1, 1, 1 + 0j))
                wires.append((C1, BR, self.segs_for(half - eps, quarter), None))
            else:
                wires.append((BL, BR, ns, None))
            # remaining three sides (passive for both loops)
            wires.append((BR, TR, ns, None))
            wires.append((TR, TL, ns, None))
            wires.append((TL, BL, ns, None))
            return wires

        tups = []
        tups.extend(square_loop(-spacing, side_r, fed=False))  # reflector
        tups.extend(square_loop(0.0, side_d, fed=True))  # driver
        return tups
