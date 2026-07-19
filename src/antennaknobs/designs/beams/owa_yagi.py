"""OWA Yagi: 4 elements, whole-band flat 50-ohm feed (NW3Z/WA3FET concept,
systematized by L. B. Cebik, W4RNL).

The Optimized Wideband Antenna is a Yagi with one deliberately "wasted"
element: a FIRST DIRECTOR parked unusually close to the driver (~0.05 wl
here, vs ~0.18 wl to the next director). That element barely adds gain --
it is a COUPLED RESONATOR that flattens the driving-point impedance at
50 ohm across an entire band: the matching network IS an element, so the
feed is direct coax with no beta/gamma/stub hardware. Cebik published OWA
families for 20/10/6/2 m; this is his 10 m 4-element on a 13.5' boom
(reflector 17.68', driver 17.20' @ 5.12', D1 16.14' @ 6.87', D2 15.20'
@ 13.0', 1" tubing), with lengths held as wavelength fractions so the
design scales with `design_freq`.

What the model reproduces (free space, length_factor 0.985 to centre the
band for this segmentation): SWR(50) stays 1.10-1.32 over ALL of
28.0-29.0 MHz while gain runs ~8.3-8.7 dBi and F/B ~12-14 dB. The two
contrasts that make the point:
  - the catalog's `beams.yagi` (a conventional driver-reflector-directors
    design) swings past 5:1 SWR over the same span;
  - delete D1 (or drag `d1_length_factor` off unity) and the OWA's own
    match collapses to 2.7-5.9 -- the wideband feed lives in that one
    close-coupled element, not in the driver.
The trade Cebik documents: ~0.2 dB of peak gain given up for total-band
consistency, and fat elements matter (thin-wire OWAs narrow; the 1" tubing
is part of the published design, modelled via the wire-material spec).

Geometry, in the framework's (x, y, z) convention:
  - y : element axis (all four elements parallel to y)
  - x : boom / firing axis; the beam fires +x (toward the directors)
  - z : constant height `base`

      refl      driver  D1              D2
       |          |     |                |
       |          F     |                |          (F = direct 50-ohm feed)
       |          |     |                |
    x= 0        .148  .198             .375  (wl)
                     ^^ the OWA coupled resonator
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import WireSpec
from types import MappingProxyType


class Builder(AntennaBuilder):
    # Cebik's 10 m 4-el OWA (ant36), feet -> fractions of the 28.4 MHz
    # wavelength: (element half-length, boom position).
    TABLE = (
        (0.255250, 0.0),  # reflector
        (0.248319, 0.147837),  # driver
        (0.233017, 0.198367),  # D1 -- the coupled resonator
        (0.219445, 0.375366),  # D2
    )
    DRIVER = 1
    D1 = 2

    default_params = MappingProxyType(
        {
            "design_freq": 28.4,
            "freq": 28.4,
            "base": 10.0,
            # Overall element-length scale. 0.985 centres the published
            # design's flat-SWR window on 28.0-29.0 MHz for this
            # segmentation (Cebik's feet assume his NEC model's meshing).
            "length_factor": 0.985,
            # Scale on D1 alone -- the knob that shows the OWA mechanism:
            # off unity, the whole-band match collapses while the pattern
            # barely moves.
            "d1_length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    # Single-band 10 m beam: snap the GUI sweep to the band.
                    "sweep_policy": {"band_locked": True},
                    "default_view": "xy",
                    "length_factor": {
                        "min": 0.95,
                        "max": 1.02,
                    },
                    "d1_length_factor": {
                        "min": 0.9,
                        "max": 1.1,
                    },
                }
            ),
        }
    )

    def build_wire_material(self):
        # 1" aluminum tubing idealized as PEC, held as a wavelength fraction
        # (0.0127 m at 28.4 MHz) so the fat-element behaviour -- which the
        # OWA's bandwidth depends on -- survives rescaling to other bands.
        wavelength = 299.792458 / self.design_freq
        return WireSpec(radius=0.001203 * wavelength)

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength
        b = self.base

        tups = []
        for i, (half_frac, pos_frac) in enumerate(self.TABLE):
            half = half_frac * wavelength * self.length_factor
            if i == self.D1:
                half *= self.d1_length_factor
            x = pos_frac * wavelength
            if i == self.DRIVER:
                # Driver: one-segment centre gap carries the direct feed.
                arm = self.segs_for(half - eps, quarter)
                tups.append(((x, -half, b), (x, -eps, b), arm, None))
                tups.append(
                    ((x, -eps, b), (x, eps, b), self.segs_for(2 * eps, quarter), 1 + 0j)
                )
                tups.append(((x, eps, b), (x, half, b), arm, None))
            else:
                ns = self.segs_for(2 * half, quarter)
                tups.append(((x, -half, b), (x, half, b), ns, None))
        return tups
