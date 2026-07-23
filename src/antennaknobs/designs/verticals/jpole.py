"""J-pole: an end-fed half-wave matched by a quarter-wave stub (L. B. Cebik,
W4RNL).

An end-fed half-wave radiator presents a very high impedance at its base, so it
cannot take coax directly. The J-pole solves that with a quarter-wave parallel
("J") matching section -- a shorted stub that transforms the high radiator-base
impedance down to ~50 ohm at a tap a short way up from the short. The
half-wave radiator stands on top of the stub and does all the radiating:
VERTICALLY POLARISED, omnidirectional in azimuth, ~2 dBi like any vertical
half-wave, but ground-independent (no radials -- the stub is the counterpoise).

This fills the "stub-matched end-fed vertical" gap: the catalog's verticals are
all base-fed quarter-wave monopoles; the J-pole is the self-contained,
end-fed-half-wave topology, and a clean test of feeding across two close wires.

Geometry, in the framework's (x, y, z) convention:
  - z : the vertical axis -- the lambda/4 stub at the bottom, then the
        lambda/2 radiator continuing up one stub leg
  - x : the two stub legs sit at x = 0 and x = gap (close together)
  - y : 0 (planar in y = 0)

           | radiator (lambda/2)        z = base + Q + H
           |
           |  o   <- stub top (open on the short leg)
        leg|  | leg              lambda/4 stub
           F==|   <- feed tap across the two legs
           |__|   <- bottom short                z = base
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the bottom short above ground.
            "base": 4.0,
            # Radiator length as a fraction of a wavelength (~half-wave).
            "radiator_frac": 0.49,
            # Matching-stub length as a fraction of a wavelength (~1/4).
            "stub_frac": 0.25,
            # Stub leg-to-leg spacing as a fraction of a wavelength.
            "spacing_frac": 0.02,
            # Feed-tap height up the stub as a fraction of the stub length;
            # transforms the match toward 50 ohm (low tap -> low R).
            "tap_frac": 0.05,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    # Stub legs span x, structure rises in z -> xz view.
                    "default_view": "xz",
                    "radiator_frac": {
                        "min": 0.45,
                        "max": 0.55,
                    },
                    "tap_frac": {
                        "min": 0.03,
                        "max": 0.3,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        radiator = self.radiator_frac * wavelength
        stub = self.stub_frac * wavelength
        gap = self.spacing_frac * wavelength
        tap = self.tap_frac * stub

        z_short = self.base
        z_tap = self.base + tap
        z_stub_top = self.base + stub
        z_rad_top = z_stub_top + radiator

        # Leg A at x = 0 carries the radiator on top; leg B at x = gap is the
        # short open-ended stub leg.
        return [
            # Bottom short bar bridging the two legs (deliberately pinned at
            # one segment; retiring it is #525 stage 3).
            Wire((0.0, 0.0, z_short), (gap, 0.0, z_short), n_seg=1),
            # Leg A: short -> tap node -> stub top, then the radiator
            # continues up.
            Wire((0.0, 0.0, z_short), (0.0, 0.0, z_tap)),
            Wire((0.0, 0.0, z_tap), (0.0, 0.0, z_stub_top)),
            Wire((0.0, 0.0, z_stub_top), (0.0, 0.0, z_rad_top)),
            # Leg B: short -> tap node -> stub top (open).
            Wire((gap, 0.0, z_short), (gap, 0.0, z_tap)),
            Wire((gap, 0.0, z_tap), (gap, 0.0, z_stub_top)),
            # Feed: a driven bridge between the two legs at the tap, meshed
            # proportionally like every other edge so the delta gap refines
            # with the mesh (issue #435 — its empirical 2-segment default
            # comes from exactly this density; kept on segs_for verbatim).
            Wire(
                (0.0, 0.0, z_tap),
                (gap, 0.0, z_tap),
                n_seg=self.segs_for(gap, quarter),
                ex=1 + 0j,
            ),
        ]
