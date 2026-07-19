"""Koch fractal dipole (L. B. Cebik, W4RNL -- "fractal antennas").

A centre-fed dipole whose two arms, instead of being straight rods, are each a
KOCH CURVE: take a straight segment, cut it in thirds, and replace the middle
third with the other two sides of an outward equilateral triangle; repeat that
rule `iterations` times. Each pass multiplies the wire length by 4/3 while the
END-TO-END span stays the same, so the zig-zag arm packs more conductor into a
given width. A wire resonates near where its DEVELOPED LENGTH is a half wave,
so the Koch dipole resonates at a span noticeably SHORTER than a straight
half-wave dipole -- the headline (and much-hyped) fractal "miniaturisation".
Cebik's careful models showed the size reduction is real but modest and bought
at the price of a lower radiation resistance and narrower bandwidth, and that
beyond a couple of iterations you get diminishing returns -- all of which this
model reproduces. It stays HORIZONTALLY POLARISED with an essentially dipole
(figure-8) pattern; the kinks are small compared with a wavelength.

This fills the "fractal / meandered miniaturised element" gap. Its real value
to the project, though, is as a METHODOLOGY STRESS CASE: each arm is a dense
chain of short segments meeting at sharp 60deg/120deg interior angles, which
exercises the thin-wire kernel and the segmentation far harder than any smooth
element in the catalog -- exactly the kind of geometry where MoM bases can
start to disagree.

Geometry, in the framework's (x, y, z) convention:
  - y : the dipole axis (overall span runs along y, centre-fed at y = 0)
  - z : the Koch bumps zig-zag in z; the antenna is planar in x = 0
  - x : broadside (figure-8 nulls off the ends, like any dipole)

        /\\        /\\          each arm is a Koch curve; bumps in +z
    ___/  \\__F __/  \\___       F = centre feed at y = 0
"""

from antennaknobs import AntennaBuilder
import math
from types import MappingProxyType


def _koch(p0, p1, iterations):
    """Return the list of points of the Koch curve from p0 to p1 (each a
    (y, z) tuple) after `iterations` subdivisions. All triangles point to the
    same (+) side of the travelling direction, the classic Koch construction."""
    pts = [p0, p1]
    for _ in range(iterations):
        new = [pts[0]]
        cos60, sin60 = 0.5, math.sqrt(3) / 2
        for a, b in zip(pts[:-1], pts[1:]):
            vy, vz = b[0] - a[0], b[1] - a[1]
            c1 = (a[0] + vy / 3, a[1] + vz / 3)
            c2 = (a[0] + 2 * vy / 3, a[1] + 2 * vz / 3)
            # Apex = c1 + R(+60deg) * (c2 - c1): outward equilateral peak.
            wy, wz = c2[0] - c1[0], c2[1] - c1[1]
            apex = (c1[0] + cos60 * wy - sin60 * wz, c1[1] + sin60 * wy + cos60 * wz)
            new.extend([c1, apex, c2, b])
        pts = new
    return pts


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            "base": 5.0,
            # Number of Koch subdivisions per arm (0 = straight dipole).
            "iterations": 2,
            # Tip-to-tip span as a fraction of a wavelength. A straight dipole
            # resonates near ~0.47 wl; the Koch developed length lets it
            # resonate at a shorter span (tuned so X -> 0 at the default scale).
            "span_frac": 0.332,
            # Overall scale knob the optimiser tunes for resonance (X -> 0).
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    # Miniaturised dipole -> reduced radiation resistance.
                    "target_z0": 50.0,
                    "default_view": "yz",
                    # Degenerate with length_factor (span = span_frac * wl *
                    # length_factor); pin it and keep length_factor as the knob.
                    "span_frac": {"hidden": True},
                    "length_factor": {
                        "min": 0.85,
                        "max": 1.15,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        span = self.span_frac * wavelength * self.length_factor
        half = span / 2.0
        z = self.base
        it = int(self.iterations)

        tups = []
        # Centre feed: a one-segment driven gap along y at the origin.
        tups.append(
            ((0.0, -eps, z), (0.0, eps, z), self.segs_for(2 * eps, quarter), 1 + 0j)
        )

        # Right arm: Koch curve from the feed edge (y=+eps) out to the tip,
        # built in the (y, z) plane then emitted as straight chords.
        right = _koch((eps, 0.0), (half, 0.0), it)
        for (ya, za), (yb, zb) in zip(right[:-1], right[1:]):
            seg = math.hypot(yb - ya, zb - za)
            tups.append(
                (
                    (0.0, ya, z + za),
                    (0.0, yb, z + zb),
                    self.segs_for(seg, quarter),
                    None,
                )
            )

        # Left arm: mirror of the right arm in y.
        left = _koch((-eps, 0.0), (-half, 0.0), it)
        for (ya, za), (yb, zb) in zip(left[:-1], left[1:]):
            seg = math.hypot(yb - ya, zb - za)
            tups.append(
                (
                    (0.0, ya, z + za),
                    (0.0, yb, z + zb),
                    self.segs_for(seg, quarter),
                    None,
                )
            )

        return tups
