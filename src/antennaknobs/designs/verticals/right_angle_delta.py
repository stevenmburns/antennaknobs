r"""Right-Angle Delta: the coax-friendly SCV delta (L. B. Cebik, W4RNL).

From Cebik's "SCVs: A Family Album" -- the same self-contained-vertical
family as the catalog's `half_square`, `bobtail`, and `bruce`: closed or
one-piece 1 wl wire shapes that put their current maxima into vertical wire
sections, so the verticals' fields add (vertically polarised, low takeoff,
no radial system) while the horizontal members' radiation largely cancels.

This member is a 1 wl closed delta standing in a vertical plane, apex UP,
with a ~0.44 wl horizontal base and two equal ~0.31 wl sides meeting at a
RIGHT ANGLE, fed a quarter-wave down one side from the apex. That feed
position parks the current maximum in the sloping side's most vertical run;
the right-angle proportions are what Cebik singled out, because they bring
the feed to ~51 ohm -- direct coax, where the equilateral delta's same feed
sits at ~120 ohm (and gains ~0.4 dB less). This model reads ~48 ohm
near-resonant at length_factor 1.004 and ~3.6 dBi free space (Cebik: 3.3
dBi, 51 ohm at 7.15 MHz).

Family rank per Cebik, worth knowing when picking an SCV: half-square 4.6 >
rectangle 4.4 > RAD 3.3 > equilateral 2.9 dBi (the half-square wins on gain
but the RAD is a CLOSED loop and takes coax without any trimming). The delta
is the near-omni end of the family: front-to-side only ~3 dB (vs the
bobtail's ~28 dB), so it trades the curtains' broadside discipline for
whole-horizon DX coverage. The VP signature the tests pin: pattern peaks at
the horizon with a deep (~25 dB) null overhead -- opposite of the catalog's
`loops.delta_loop`, the corner-fed horizontally-dominant cousin.

Geometry, in the framework's (x, y, z) convention:
  - y : the horizontal base wire runs along y
  - z : height; base wire at `base`, apex ~0.22 wl higher
  - x : broadside; bidirectional off +/- x (front-to-side ~3 dB)
The structure is planar in x = 0.

           T          z = base + h   (apex, right angle)
          / \
         F   \        F = feed, 1/4 wl down the left side from T
        /     \
       A=======B      z = base       (~0.44 wl horizontal base)
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the horizontal base wire above ground. Low, like the
            # other SCVs: the verticals do the work.
            "base": 3.0,
            # Horizontal base length as a fraction of a wavelength; Cebik's
            # right-angle proportion (~0.44 wl base, apex angle 90 deg).
            "base_frac": 0.442,
            # Sloping side length as a fraction of a wavelength. With the
            # base above, the two sides meet at a right angle and the
            # perimeter comes out ~1.07 wl.
            "side_frac": 0.3126,
            # Feed position DOWN the left side from the apex, in wavelengths
            # (~1/4 wl puts the current max in the side's vertical run).
            "feed_frac": 0.25,
            # Overall scale knob; 1.004 is resonance (X ~ 0) for this
            # segmentation.
            "length_factor": 1.004,
            "ui_params": MappingProxyType(
                {
                    # The right-angle proportions' point: ~51 ohm direct coax.
                    "target_z0": 50.0,
                    "default_view": "yz",
                    "length_factor": {
                        "min": 0.9,
                        "max": 1.1,
                    },
                    "feed_frac": {
                        "min": 0.05,
                        "max": 0.28,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        wavelength = 299.792458 / self.design_freq
        lf = self.length_factor

        w = self.base_frac * wavelength * lf
        s = self.side_frac * wavelength * lf
        half_w = w / 2
        h = (s**2 - half_w**2) ** 0.5  # apex height above the base wire

        zb = self.base
        A = (0.0, -half_w, zb)  # left base corner
        B = (0.0, half_w, zb)  # right base corner
        T = (0.0, 0.0, zb + h)  # apex

        # Feed a quarter-wave down the LEFT side from the apex, measured
        # along the wire; a short one-segment driven edge (cf. half_square).
        d = min(self.feed_frac * wavelength, s - 0.1)
        pe = 0.1  # feed-edge length, m
        t0 = (d - pe / 2) / s
        t1 = (d + pe / 2) / s

        def lerp(p, q, t):
            return (
                p[0] + (q[0] - p[0]) * t,
                p[1] + (q[1] - p[1]) * t,
                p[2] + (q[2] - p[2]) * t,
            )

        F0 = lerp(T, A, t0)
        F1 = lerp(T, A, t1)

        return [
            # Left side: apex -> feed edge -> base corner (driven mid-side).
            Wire(T, F0),
            Wire(F0, F1, ex=1 + 0j),
            Wire(F1, A),
            # Horizontal base and right side close the delta.
            Wire(A, B),
            Wire(B, T),
        ]
