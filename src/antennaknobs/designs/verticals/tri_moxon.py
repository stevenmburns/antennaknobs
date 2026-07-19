r"""Tri-Moxon switched vertical array (L. B. Cebik, W4RNL, 10-10 News #51).

Full-horizon 10 m coverage with a COAX SWITCH instead of a rotator: three
vertically-oriented wire Moxon rectangles hang in a Y around one
non-conductive ~35' post, reflectors 48" out, 120 degrees apart, each
firing radially outward and covering ~125 degrees of azimuth. Switch to
whichever rectangle faces the DX. Per sector Cebik quotes ~6.6 dBi at the
11 degree takeoff with F/B ~13 dB ("in the range of a 2-element Yagi") and
under 1.7:1 SWR on 50-ohm coax across all of 28-29 MHz; the 22'-35' height
span is deliberate, giving elevation peaks at both 11 and 34 degrees for
long- and short-range paths.

The design premise the tests pin: a triple of beams this close OUGHT to
interact, but each Moxon's own front-to-back ratio protects its
neighbours, so the parked rectangles cost the active one only a whisker
(the Moxon's compactness is also what lets the Y fit a <10' radius). The
switching detail is modelled literally, per Cebik's recommendation that
idle feedpoints look OPEN: each parked driver hangs on a quarter-wave
50-ohm line shorted at the switch end -- here a real `TL` branch to a
virtual stub port hard-shorted by a `Shunt(r=0)`, the quarter wave
transforming that short to the open the parked feedpoint wants. (Half-wave
lines left open at the switch do the same job; "the difference ... does
not create enough difference to be called critical.")

Dimensions (AWG #14 wire at 28.35 MHz; work as-is for #12): A = 12.63'
vertical elements, B = 1.90' driver tails, C = 0.35' gap, D = 2.36'
reflector tails, E = 4.61' = B+C+D depth -- stored as wavelength fractions
so the design scales with `design_freq`.

Geometry, in the framework's (x, y, z) convention:
  - three vertical planes at 120 degrees; element k fires outward along
    azimuth (k-1) * 120 degrees (element 1 -> +x)
  - z : vertical elements span `base` to `base + A` (~22' to ~35')
  - reflector at `post_frac` radius, driver E further out; feed gap at the
    driver's mid-height

     top view                 side view (one rectangle)
        2                        D==| C |==B
         \                       |        |      A tall, feed at the
          *--- 1  (post at *)    |        F      driver's mid-height
         /                       |        |
        3                        D==| C |==B
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import (
    Driven,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
    TL,
    WireSpec,
)
import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    # The rotator replacement: pick which rectangle the switch feeds.
    dir2_params = MappingProxyType({"active": 2})
    dir3_params = MappingProxyType({"active": 3})

    default_params = MappingProxyType(
        {
            "design_freq": 28.35,
            "freq": 28.35,
            # Which of the three rectangles the coax switch drives (1-3);
            # the other two park on shorted quarter-wave lines.
            "active": 1,
            # Height of the rectangle bottoms ("just above 22'"). The 22-35'
            # span is chosen for the 11 + 34 degree elevation peaks.
            "base": 6.71,
            # Reflector distance from the post (48"), as a fraction of a
            # wavelength -- the interaction-control knob.
            "post_frac": 0.11529,
            # Cebik's rectangle dimensions as wavelength fractions:
            # A = 12.63' verticals, B = 1.90' driver tails, D = 2.36'
            # reflector tails, E = 4.61' depth (B + C + D; C is the gap
            # that remains).
            "a_frac": 0.36404,
            "b_frac": 0.05477,
            "d_frac": 0.06802,
            "e_frac": 0.13288,
            # The parked feedlines: 50-ohm coax, a quarter wave to the
            # shorted switch contact.
            "z0_feed": 50.0,
            "idle_len_frac": 0.25,
            # Overall scale knob.
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "xy",
                    "active": {"min": 1, "max": 3, "step": 1, "precision": 0},
                    "length_factor": {
                        "min": 0.95,
                        "max": 1.05,
                    },
                    "post_frac": {
                        "min": 0.08,
                        "max": 0.25,
                    },
                    "idle_len_frac": {"min": 0.05, "max": 0.5},
                }
            ),
        }
    )

    def build_wire_material(self):
        # AWG #14 copper wire (0.0641" diameter).
        return WireSpec(radius=0.0641 * 0.0254 / 2)

    def _element(self, k):
        """Wire tuples for rectangle k (1-3), standing in the vertical
        plane at azimuth (k-1)*120 deg, reflector nearest the post."""
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength
        lf = self.length_factor

        a = self.a_frac * wavelength * lf
        b = self.b_frac * wavelength * lf
        d = self.d_frac * wavelength * lf
        e = self.e_frac * wavelength * lf
        r_ref = self.post_frac * wavelength
        r_drv = r_ref + e

        phi = math.radians((k - 1) * 120.0)
        ux, uy = math.cos(phi), math.sin(phi)

        def at(r, z):
            return (r * ux, r * uy, z)

        zb = self.base
        zt = zb + a
        zm = zb + a / 2
        pe = 0.1  # feed-edge length, m

        vert = self.segs_for(a, quarter)
        half_drv = self.segs_for(a / 2 - pe / 2, quarter)
        tail_b = self.segs_for(b, quarter)
        tail_d = self.segs_for(d, quarter)

        return [
            # Reflector: vertical + fold-back tails toward the driver.
            (at(r_ref, zb), at(r_ref, zt), vert, None, None),
            (at(r_ref, zt), at(r_ref + d, zt), tail_d, None, None),
            (at(r_ref, zb), at(r_ref + d, zb), tail_d, None, None),
            # Driver: vertical in two halves around the mid-height feed gap,
            # plus its tails back toward the reflector (gap C left open).
            (at(r_drv, zb), at(r_drv, zm - pe / 2), half_drv, None, None),
            (
                at(r_drv, zm - pe / 2),
                at(r_drv, zm + pe / 2),
                self.segs_for(pe, quarter),
                None,
                f"feed_{k}",
            ),
            (at(r_drv, zm + pe / 2), at(r_drv, zt), half_drv, None, None),
            (at(r_drv, zt), at(r_drv - b, zt), tail_b, None, None),
            (at(r_drv, zb), at(r_drv - b, zb), tail_b, None, None),
        ]

    def build_wires(self):
        return [t for k in (1, 2, 3) for t in self._element(k)]

    def build_network(self):
        wavelength = 299.792458 / self.design_freq
        active = int(self.active)
        parked = [k for k in (1, 2, 3) if k != active]

        ports = {f"feed_{k}": PortOnWire(f"feed_{k}") for k in (1, 2, 3)}
        branches = []
        for k in parked:
            ports[f"stub_{k}"] = PortVirtual(f"stub_{k}")
            branches.append(
                # The idle feedline: a quarter wave of coax to the switch...
                TL(
                    a=f"feed_{k}",
                    b=f"stub_{k}",
                    z0=self.z0_feed,
                    length=self.idle_len_frac * wavelength,
                )
            )
            # ...whose contact is shorted, so the feedpoint sees an open.
            branches.append(Shunt(port=f"stub_{k}", r=0.0))

        return Network(
            ports=ports,
            branches=branches,
            sources=[Driven(port=f"feed_{active}", voltage=1 + 0j)],
        )
