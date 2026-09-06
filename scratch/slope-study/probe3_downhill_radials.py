"""Radials only on the downhill side (the QRZ suggestion). In the ground's
frame the vertical and the soil are symmetric, so any preference for downhill
radials has to show up as impedance, efficiency or a pattern skew here; the
valley itself is outside a planar model. Downhill is azimuth 180."""

import math

import numpy as np

from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.far_field import pattern_metrics, radiated_fraction

SOIL = ("finite", 13.0, 0.005)
SLOPE = 45.0
DOWNHILL = 180.0


def sector_builder(n, sector_deg, lf=0.9531):
    """n radials spread evenly across a sector centred on downhill."""

    class B(Builder):
        length_factor = lf
        n_radials = n

        def build_wires(self):
            tups = super().build_wires()
            out, k = [], 0
            depth = self.depth
            if sector_deg >= 360.0:
                return tups
            for w in tups:
                z0, z1 = float(w.p0[2]), float(w.p1[2])
                is_radial = (
                    abs(z0 + depth) < 1e-9
                    and abs(z1 + depth) < 1e-9
                    and math.hypot(*w.p1[:2]) > 0.1
                )
                if not is_radial:
                    out.append(w)
                    continue
                r = math.hypot(float(w.p1[0]), float(w.p1[1]))
                phi = math.radians(
                    DOWNHILL - sector_deg / 2 + sector_deg * (k + 0.5) / n
                )
                k += 1
                out.append(
                    w._replace(p1=(r * math.cos(phi), r * math.sin(phi), -depth))
                )
            assert k == n, (k, n)
            return out

    return B


def gain(ff, elev, phi):
    rings = np.asarray(ff.rings)
    i = int(np.argmin(np.abs((90.0 - np.asarray(ff.thetas)) - elev)))
    j = int(np.argmin(np.abs(np.asarray(ff.phis) - phi)))
    return float(rings[i, j])


if __name__ == "__main__":
    cases = [
        (4, 360.0, "4 radials, full circle"),
        (4, 180.0, "4 radials, downhill half"),
        (4, 90.0, "4 radials, downhill quarter"),
        (8, 360.0, "8 radials, full circle"),
        (8, 180.0, "8 radials, downhill half"),
    ]
    print(
        f"{'case':30s} {'Z':>18s} {'rad.frac':>8s} {'peak':>6s} | ground frame 20°: dn / up | true 45° slope, 3° above downhill horizon"
    )
    for n, sec, name in cases:
        e = MomwireEngine(sector_builder(n, sec)(), ground=SOIL)
        z = e.impedance()[0]
        ff = e.far_field()
        pm = pattern_metrics(ff)
        rf = radiated_fraction(ff)
        g20d, g20u = gain(ff, 20, DOWNHILL), gain(ff, 20, 0.0)
        g3 = gain(ff, 3 + SLOPE, DOWNHILL)
        print(
            f"{name:30s} {z.real:7.2f}{z.imag:+8.2f}j {rf:8.4f} {pm['peak_gain_dbi']:6.2f} | {g20d:6.2f} / {g20u:6.2f}          | {g3:6.2f} dBi"
        )
