"""A buried-radial vertical on a planar slope, in the ground's frame.

Rotate the problem so the interface is flat: the plumb mast tilts toward the
uphill side by the slope angle, the buried radials follow the ground and are
untouched. Then read the far field back in the true (gravity) frame: a ray at
interface elevation psi in the UPHILL azimuth has true elevation psi + slope,
in the DOWNHILL azimuth psi - slope. Uphill, true elevations below the slope
are behind the ground plane. Second column: the faceted-terrain far-field
ground (hillside_terrain) with the same slopes, whose impedance solve stays
level (crest-local), for comparison.
"""

import math
import sys

import numpy as np

from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.far_field import pattern_metrics
from antennaknobs.terrain import hillside_terrain

SOIL = ("finite", 13.0, 0.005)
UPHILL_PHI = 0.0  # +x is uphill; the mast leans toward +x
TRUE_ELEVS = (3, 5, 10, 20, 30, 45, 60)
CONVENTION = "surface"  # radials on the grass; see SlopedBuilder


def rotate_about_y(p, ang):
    x, y, z = (float(v) for v in p)
    c, s = math.cos(ang), math.sin(ang)
    # rotate the +z axis toward +x by ang
    return (x * c + z * s, y, -x * s + z * c)


class SlopedBuilder(Builder):
    """Tilt the mast toward +x (uphill) about the hub. For the buried
    (connected) convention the hub is the interface node at z = 0 and momwire
    REFUSES: the crossing fill's by-parts move is exact only for horizontal or
    vertical segments and the tilt tables do not exist (https://github.com/stevenmburns/momwire/issues/936). For the SURFACE convention (radials on the grass at
    h = a + insulation, mast bonded at the hub at that height) there is no
    crossing node and a tilted mast is ordinary geometry."""

    slope_deg = 0.0

    def build_wires(self):
        tups = super().build_wires()
        ang = math.radians(self.slope_deg)
        # the hub is the lowest point of the above-ground structure
        zs = sorted(
            {round(float(w.p0[2]), 9) for w in tups}
            | {round(float(w.p1[2]), 9) for w in tups}
        )
        hub_z = [z for z in zs if z >= 0.0][0]
        out = []
        for w in tups:
            z0, z1 = float(w.p0[2]), float(w.p1[2])
            if z0 >= hub_z and z1 >= hub_z and (z0 > hub_z + 1e-9 or z1 > hub_z + 1e-9):
                p0 = rotate_about_y((w.p0[0], w.p0[1], z0 - hub_z), ang)
                p1 = rotate_about_y((w.p1[0], w.p1[1], z1 - hub_z), ang)
                out.append(
                    w._replace(
                        p0=(p0[0], p0[1], p0[2] + hub_z),
                        p1=(p1[0], p1[1], p1[2] + hub_z),
                    )
                )
            else:
                out.append(w)
        return out


def gain_at(ff, elev_deg, phi_deg):
    """Interpolate the dBi ring table at interface elevation and azimuth."""
    theta = 90.0 - elev_deg
    th = np.asarray(ff.thetas)
    ph = np.asarray(ff.phis)
    rings = np.asarray(ff.rings)
    if theta < th[0] or theta > th[-1]:
        return float("nan")
    i = int(np.clip(np.searchsorted(th, theta) - 1, 0, len(th) - 2))
    j = int(np.clip(np.searchsorted(ph, phi_deg) - 1, 0, len(ph) - 2))
    ft = (theta - th[i]) / (th[i + 1] - th[i])
    fp = (phi_deg - ph[j]) / (ph[j + 1] - ph[j])
    g = rings[i, j] * (1 - ft) * (1 - fp) + rings[i + 1, j] * ft * (1 - fp)
    g += rings[i, j + 1] * (1 - ft) * fp + rings[i + 1, j + 1] * ft * fp
    return float(g)


def run(slope):
    # The engine re-instantiates the builder CLASS during meshing, so the
    # slope must live on the class, not the instance (that cost one run of
    # three identical impedances before it was noticed).
    attrs = dict(Builder.surface_params)  # the catalog's own surface variant
    attrs["slope_deg"] = float(slope)
    cls = type(f"Sloped{int(slope)}", (SlopedBuilder,), attrs)
    b = cls()
    assert (
        any(abs(float(w.p1[0])) > 1e-9 for w in b.build_wires() if float(w.p1[2]) > 1.0)
        or slope == 0
    )
    eng = MomwireEngine(b, ground=SOIL)
    z = eng.impedance()[0]
    ff = eng.far_field()
    pm = pattern_metrics(ff)
    return z, ff, pm


def run_terrain(slope):
    b = Builder()
    t = hillside_terrain(
        flat_width=0.5,
        up_slope_deg=slope,
        down_slope_deg=slope,
        medium=SOIL[1:],
        downhill_azimuth=180.0,
    )
    eng = MomwireEngine(b, ground=("terrain", t))
    z = eng.impedance()[0]
    ff = eng.far_field()
    pm = pattern_metrics(ff)
    return z, ff, pm


if __name__ == "__main__":
    slopes = [
        float(s) for s in (sys.argv[1] if len(sys.argv) > 1 else "0,10,45").split(",")
    ]
    rows = {}
    for s in slopes:
        z, ff, pm = run(s)
        rows[s] = (z, ff, pm)
        print(
            f"\n=== rotated frame, slope {s:g} deg: Z = {z:.3f}  peak {pm['peak_gain_dbi']:.2f} dBi "
            f"at interface takeoff {pm['takeoff_deg']:.0f} deg, az {pm['azimuth_deg']:.0f}"
        )
        print("  true elev |  downhill dBi |  uphill dBi")
        for e in TRUE_ELEVS:
            gd = gain_at(ff, e + s, UPHILL_PHI + 180.0)  # downhill: psi = e + s
            gu = gain_at(ff, e - s, UPHILL_PHI) if e - s >= 0 else float("nan")
            print(
                f"  {e:8.0f}  |  {gd:11.2f}  |  {gu:9.2f}"
                + ("   (behind the hill)" if math.isnan(gu) else "")
            )
    for s in slopes:
        if s == 0:
            continue
        z, ff, pm = run_terrain(s)
        print(
            f"\n=== hillside_terrain, slopes {s:g}/{s:g} deg, flat 0.5 m: Z = {z:.3f}  peak {pm['peak_gain_dbi']:.2f} dBi "
            f"at takeoff {pm['takeoff_deg']:.0f} deg, az {pm['azimuth_deg']:.0f}"
        )
        print("  true elev |  downhill dBi |  uphill dBi")
        for e in TRUE_ELEVS:
            print(
                f"  {e:8.0f}  |  {gain_at(ff, e, 180.0):11.2f}  |  {gain_at(ff, e, 0.0):9.2f}"
            )
