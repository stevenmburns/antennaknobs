"""Two-band fan (parallel) dipole — two dipoles bonded at a common feed.

Unlike `fandipole` (a cone of azimuthally-separated spokes sized by
length_factor), this is the classic PARALLEL/FAN dipole: the two bands hang in
two near-parallel vertical planes, splitting at the feed a distance `s` out, and
each band is tuned by its own ABSOLUTE length. Band 0 fans to +x, band 1 to -x;
with `gap_angle_deg = 0` the two stay in their own x = ±s/√2 planes.

The design doubles as a methodology study of the feed-junction spacing `s` (the
s01..s07 variants sweep it), which is why the per-band lengths are hand-tuned
absolutes rather than freq×factor.

Per-band knobs (freq / length / droop angle) are grouped under `bands`, the
shared multiband-design idiom (cf. fandipole, trap_fan_dipole); the feed-split
`s`, feed-gap `eps`, and in-plane `gap_angle_deg` are shared across both bands.
"""

import logging
import math
from math import sqrt
from types import MappingProxyType

from antennaknobs import AntennaBuilder

logger = logging.getLogger(__name__)


def _variant(freq, s, eps, *, len12, freq12, len10, freq10, angle=26.5651):
    """A value-preset dict in the grouped (bands) shape, as an overlay on
    default_params — it states only the swept knobs (freq / s / eps) and the
    per-band lengths; base / gap_angle_deg / n_bands come from default.

    Band 0 is the 12m element (fans to +x), band 1 the 10m element (-x), matching
    the original A/B placement so geometry is unchanged by the regrouping.
    """
    return MappingProxyType(
        {
            "freq": freq,
            "s": s,
            "eps": eps,
            # Plain dicts (NOT MappingProxyType): the adapter detects a band
            # group via isinstance(x, dict), which MappingProxyType fails.
            "bands": (
                {"freq": freq12, "length": len12, "angle_deg": angle},
                {"freq": freq10, "length": len10, "angle_deg": angle},
            ),
        }
    )


class Builder(AntennaBuilder):
    # Feed-junction spacing sweep (s = 0.7 → 0.1) + an eps perturbation and the
    # as-built "current_physical" point. The per-band lengths were re-tuned for
    # resonance at each s.
    s07_params = _variant(
        28.57, 0.7, 0.01, len12=5.1102, freq12=24.97, len10=4.4682, freq10=28.57
    )
    s05_params = _variant(
        28.57, 0.5, 0.01, len12=5.2949, freq12=24.97, len10=4.6531, freq10=28.57
    )
    s03_params = _variant(
        28.57, 0.3, 0.01, len12=5.4725, freq12=24.97, len10=4.8370, freq10=28.57
    )
    s025_params = _variant(
        24.97, 0.25, 0.01, len12=5.5153, freq12=24.97, len10=4.8837, freq10=28.57
    )
    s02_params = _variant(
        24.97, 0.2, 0.01, len12=5.5571, freq12=24.97, len10=4.9312, freq10=28.57
    )
    s015_params = _variant(
        24.97, 0.15, 0.01, len12=5.5978, freq12=24.97, len10=4.9803, freq10=28.57
    )
    s01_params = _variant(
        24.97, 0.10, 0.01, len12=5.6371, freq12=24.97, len10=5.0331, freq10=28.57
    )
    s01_eps001_params = _variant(
        24.97, 0.10, 0.001, len12=5.7628, freq12=24.97, len10=5.0717, freq10=28.57
    )
    current_physical_params = _variant(
        28.47, 0.15, 0.015, len12=5.494, freq12=26.6, len10=5.0517, freq10=29.3
    )

    default_params = MappingProxyType(
        {
            # Measurement frequency the live solve evaluates Z_in at. Geometry
            # doesn't read it — each band sizes itself from its own `length`.
            # The band group's link_meas_freq_to_param wires each band's `freq`
            # leaf to this when a band row is selected.
            "freq": 28.47,
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
                {"freq": 24.0, "length": 5.877, "angle_deg": 26.5651},
                {"freq": 28.7, "length": 5.19, "angle_deg": 26.5651},
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
        n_seg0 = self.nominal_nsegs

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

        # Feed gap T->S refines with the mesh (issue #435); band 0's arm
        # (junction -> tip) is the reference-length wire carrying n_seg0.
        n_seg1 = self.segs_for(math.dist(T, S), math.dist(junctions[0], tips[0]))

        # Emit in the original order: +y junctions, +y arms, -y junctions,
        # -y arms, then the feed gap — so the wire list is unchanged for the
        # 2-band case.
        tups = []
        for G in junctions:
            tups.append((S, G, 5, None))
        for G, tip in zip(junctions, tips):
            tups.append((G, tip, n_seg0, None))
        for G in junctions:
            tups.append((T, ry(G), 5, None))
        for G, tip in zip(junctions, tips):
            tups.append((ry(G), ry(tip), n_seg0, None))
        tups.append((T, S, n_seg1, 1 + 0j))

        return [
            (
                (x0, y0, z0 + self.base),
                (x1, y1, z1 + self.base),
                ns,
                ev,
            )
            for ((x0, y0, z0), (x1, y1, z1), ns, ev) in tups
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
