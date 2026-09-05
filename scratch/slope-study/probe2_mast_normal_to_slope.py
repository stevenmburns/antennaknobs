"""A vertical NORMAL to a sloping ground (the QRZ thread's case): in the
ground's frame this IS the level-ground deck, so the buried connected family
serves it with no tilt. Only the far-field read-out rotates: a ray at
interface elevation psi in the downhill azimuth has true elevation psi - slope,
in the uphill azimuth psi + slope. Below the plane is behind the hill."""

import math
import sys

from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.far_field import pattern_metrics

from probe1_planar_slope import SOIL, TRUE_ELEVS, gain_at

if __name__ == "__main__":
    slope = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0
    surface_cls = type("S", (Builder,), dict(Builder.surface_params))
    for name, cls in (
        ("buried, connected", Builder),
        ("surface (radials on grass)", surface_cls),
    ):
        eng = MomwireEngine(cls(), ground=SOIL)
        z = eng.impedance()[0]
        ff = eng.far_field()
        pm = pattern_metrics(ff)
        print(
            f"\n=== {name}: Z = {z:.3f} (unchanged by the slope)  peak {pm['peak_gain_dbi']:.2f} dBi at ground-frame takeoff {pm['takeoff_deg']:.0f} deg"
        )
        print(f"  slope {slope:g} deg, true elev | downhill dBi | uphill dBi")
        for e in TRUE_ELEVS:
            psi_dn = e + slope
            psi_up = e - slope
            gd = gain_at(ff, psi_dn, 180.0) if psi_dn <= 90 else float("nan")
            gu = gain_at(ff, psi_up, 0.0) if psi_up >= 0 else float("nan")
            tag = "   (behind the hill)" if math.isnan(gu) else ""
            print(f"  {e:8.0f}  |  {gd:11.2f}  |  {gu:9.2f}{tag}")
