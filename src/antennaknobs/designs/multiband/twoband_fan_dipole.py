"""Two-band fan (parallel) dipole — two dipoles bonded at a common feed.

Unlike `fandipole` (a cone of azimuthally-separated spokes sized by
length_factor), this is the classic PARALLEL/FAN dipole: the two bands hang in
two near-parallel vertical planes, splitting at the feed a distance `s` out, and
each band is tuned by its own ABSOLUTE length. Band 0 fans to +x, band 1 to -x;
with `gap_angle_deg = 0` the two stay in their own x = ±s/√2 planes.

Each band is tuned by its absolute length rather than freq×factor, and the
feed-junction spacing `s` is a knob of its own. (A spacing sweep of variants,
s01..s07, once rode along; its lengths had gone stale against the geometry
and it was dropped, 2026-10-28.)

Per-band knobs (freq / length / droop angle) are grouped under `bands`, the
shared multiband-design idiom (cf. fandipole, trap_fan_dipole); the feed-split
`s`, feed-gap `eps`, and in-plane `gap_angle_deg` are shared across both bands.
"""

import logging
import math
from math import sqrt
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire

logger = logging.getLogger(__name__)


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # Measurement frequency the live solve evaluates Z_in at. Geometry
            # doesn't read it — each band sizes itself from its own `length`.
            # The band group's link_meas_freq_to_param wires each band's `freq`
            # leaf to this when a band row is selected.
            "freq": 28.5,
            # Geometry is hand-tuned per band in absolute metres;
            # design_freq only anchors auto_mesh's density scale
            # (nominal_nsegs per quarter-wave), so it is hidden from the UI.
            "design_freq": 28.5,
            "base": 7.0,
            # In-plane spread of the two bands about the y axis (deg). 0 keeps
            # each band in its own x = ±s/√2 plane (a true parallel fan).
            "gap_angle_deg": 0.0,
            # Feed-junction split: how far out (m) the two bands separate from
            # the shared feed. This is the design's swept methodology knob.
            "s": 0.15,
            # Feed-gap half-width (drives the center-segment size).
            "eps": 0.01,
            # Pinned at 2 — the topology is two dipoles (one each side of the
            # feed). Exposed so the `bands` group has a repeat_count to
            # reference, satisfying the schema adapter's contract.
            "n_bands": 2,
            # Per-band knobs grouped: each band carries its own freq (meas-freq
            # anchor) / absolute length / droop angle. Band 0 = 12m (+x),
            # band 1 = 10m (-x).
            "bands": (
                {"freq": 24.94, "length": 5.877, "angle_deg": 26.5651},
                {"freq": 28.5, "length": 5.19, "angle_deg": 26.5651},
            ),
            "ui_params": MappingProxyType(
                {
                    # n_bands is the bands group's repeat_count — the frontend
                    # reads its live value to know how many band rows to render,
                    # so it must stay a visible param (hiding it collapses the
                    # group to zero rows). Range 1–2 like trap_fan_dipole; the
                    # design is really two dipoles, n_bands=1 is a single arm.
                    "n_bands": {"min": 1, "max": 2, "step": 1},
                    # tuple-of-dicts becomes a ParamGroupSpec; this dict tells the
                    # adapter how to render each band row + per-leaf ranges.
                    "bands": {
                        "label_template": "band {i}",
                        "repeat_count": "n_bands",
                        "max_repeats": 2,
                        "link_meas_freq_to_param": "freq",
                        "freq": {
                            "min": 13.5,
                            "max": 30.2,
                            "step": 0.001,
                            "precision": 3,
                            "unit": " MHz",
                        },
                        "length": {
                            "min": 3.0,
                            "max": 7.0,
                            "step": 0.001,
                            "precision": 4,
                            "unit": " m",
                        },
                        "angle_deg": {"min": 0.0, "max": 60.0},
                    },
                    "s": {"min": 0.05, "max": 0.8, "step": 0.01, "precision": 2},
                    "design_freq": {"hidden": True},
                    "eps": {"min": 0.001, "max": 0.05, "step": 0.001, "precision": 3},
                    "gap_angle_deg": {"min": 0.0, "max": 30.0},
                }
            ),
        }
    )

    # invvee reference 5.8408

    def build_wires(self):
        eps = self.eps
        s = self.s
        gap = math.radians(self.gap_angle_deg)

        def ry(p):
            return p[0], -p[1], p[2]

        # Each half-element of length r = length/2 runs out to the tip at two
        # angles: droop (descent below horizontal; rho = r·cos(droop),
        # z = r·sin(droop)) and gap (in-plane spread; y = rho·cos(gap),
        # x = rho·sin(gap)).
        def compute(length, droop, gap):
            r = length / 2
            rho = r * math.cos(droop)
            z = r * math.sin(droop)
            y = rho * math.cos(gap)
            x = rho * math.sin(gap)
            return x, y, z

        n_bands = int(self.n_bands)
        active = tuple(self.bands)[:n_bands]

        S = (0, eps, 0)
        T = ry(S)

        # Per band: a junction point G a distance `s` out (band 0 to +x, band 1
        # to -x) and the drooping tip beyond it.
        junctions, tips = [], []
        for i, band in enumerate(active):
            sign = 1 if i == 0 else -1
            droop = math.radians(float(band["angle_deg"]))
            x_t, y_t, z_t = compute(float(band["length"]) - 2 * s, droop, gap)
            G = (sign * s / sqrt(2.0), eps + s / sqrt(2.0), 0)
            tip = (sign * x_t + G[0], y_t + G[1], -z_t)
            junctions.append(G)
            tips.append(tip)

        # Arms and the feed gap mesh at the design density (auto_mesh:
        # nominal_nsegs per design_freq quarter-wave; the feed gap thereby
        # refines with the mesh, issue #435). Band 0's arm is the links'
        # density reference.
        ref_arm = math.dist(junctions[0], tips[0])

        # The feed-split links must refine WITH the arms (issue #484): a
        # fixed count leaves the G junctions ever more graded as the mesh
        # refines, and sin/PyNEC drift monotonically off the bs2 value
        # (55.7 -> 67.0 ohm over the census ladder) while a proportional
        # link mesh stays flat. The floor of 5 keeps the links at least as
        # fine as they always were, so the default (N=21) mesh is unchanged.
        n_link = max(5, self.segs_for(math.dist(S, junctions[0]), ref_arm))

        # Emit in the original order: +y junctions, +y arms, -y junctions,
        # -y arms, then the feed gap — so the wire list is unchanged for the
        # 2-band case.
        tups = []
        for G in junctions:
            tups.append(Wire(S, G, n_seg=n_link))
        for G, tip in zip(junctions, tips, strict=True):
            tups.append(Wire(G, tip))
        for G in junctions:
            tups.append(Wire(T, ry(G), n_seg=n_link))
        for G, tip in zip(junctions, tips, strict=True):
            tups.append(Wire(ry(G), ry(tip)))
        tups.append(Wire(T, S, ex=1 + 0j))

        return [
            w._replace(
                p0=(w.p0[0], w.p0[1], w.p0[2] + self.base),
                p1=(w.p1[0], w.p1[1], w.p1[2] + self.base),
            )
            for w in tups
        ]


if __name__ == "__main__":

    def tofeet_inches(m):
        f, i = divmod(m / 0.0254, 12)
        ii, frac16 = divmod(i * 16, 16)
        frac16 = int(frac16 + 0.5)
        g = math.gcd(frac16, 16)
        return f"{m * 100:.1f} cm {f:.0f} ft {i:.3f} in ({ii:.0f} {frac16 // g}/{16 // g} in)"

    bands = Builder.default_params["bands"]
    len12, len10 = bands[0]["length"], bands[1]["length"]
    print(f"Quarter wave element on 12m: {tofeet_inches(len12 / 2)}")
    print(f"Quarter wave element on 10m: {tofeet_inches(len10 / 2)}")
    print(f"Ratio of 12m element to single band invvee: {len12 / 5.8408}")
    print(f"Ratio of 12m element to 10m element: {len12 / len10}")
