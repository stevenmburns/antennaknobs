"""Fan dipole — parallel dipoles off one feed for several bands."""

import logging
import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder

logger = logging.getLogger(__name__)


C_LIGHT_MHZ_M = 299.792458

# Max bands the cone geometry supports — fixes the spoke layout so
# variants with fewer active bands can still share a single bands tuple
# of this length (cleaner variant overlay on the frontend).
_MAX_BANDS = 5


# Canonical per-band defaults. Variants pick a subset (n_bands of these
# slots become the active bands) but always carry a length-5 tuple so
# selectVariant's wholesale overlay of `bands` keeps the frontend's
# preallocated group instances aligned with max_repeats.
_BAND_20M = {"freq": 14.300, "length_factor": 0.4892}
_BAND_17M = {"freq": 18.1575, "length_factor": 0.4994}
_BAND_15M = {"freq": 21.383, "length_factor": 0.4984}
_BAND_12M = {"freq": 24.97, "length_factor": 0.4971}
_BAND_10M = {"freq": 28.47, "length_factor": 0.5004}


class Builder(AntennaBuilder):
    # Each band's element is a half-wave dipole sized to its own band
    # frequency: half_length = length_factor × (c / freq). The factor
    # ≈ 0.5 (slight end-effect shortening on the higher bands). The
    # cone-spoke layout is fixed at _MAX_BANDS spokes; n_bands controls
    # how many of `bands` get realised, so the same Builder backs the
    # 5-band, 17/15 pair, and 12/10 pair variants.
    default_params = MappingProxyType(
        {
            "freq": _BAND_10M["freq"],
            "base": 7.0,
            "angle_deg": 26.5651,
            "n_bands": _MAX_BANDS,
            "bands": (_BAND_20M, _BAND_17M, _BAND_15M, _BAND_12M, _BAND_10M),
            "ui_params": MappingProxyType(
                {
                    "sweep_policy": {
                        "anchor": "meas_freq",
                        "band_locked": True,
                    },
                    # Group config: tuple-of-dicts in default_params
                    # becomes a ParamGroupSpec in the schema. The dict
                    # under the same key gives the adapter the group's
                    # label_template, repeat_count name, max_repeats,
                    # link_meas_freq_to_param, plus per-leaf override
                    # hints (precision, range, step).
                    "bands": {
                        "label_template": "band {i}",
                        "repeat_count": "n_bands",
                        "max_repeats": _MAX_BANDS,
                        "link_meas_freq_to_param": "freq",
                        "freq": {
                            "min": 13.5,
                            "max": 30.2,
                            "step": 0.001,
                            "precision": 3,
                            "unit": " MHz",
                        },
                        "length_factor": {
                            "min": 0.40,
                            "max": 0.55,
                            "step": 0.0001,
                            "precision": 4,
                        },
                    },
                    "n_bands": {
                        "min": 1,
                        "max": _MAX_BANDS,
                        "step": 1,
                    },
                }
            ),
        }
    )

    # Explicit alias so the variant selector lists the 5-band
    # configuration even if the user is already on a pair variant.
    five_band_params = default_params

    # 17m/15m pair — the two active bands first, remaining slots padded
    # with the other bands so bumping n_bands back up reveals a sensible
    # 5-band fall-back instead of empty placeholders.
    # Pair variants overlay default_params (base / angle_deg come from default);
    # each drops n_bands to 2 and reorders the band tuple to lead with its pair.
    pair_17_15_params = MappingProxyType(
        {
            "freq": _BAND_15M["freq"],
            "n_bands": 2,
            "bands": (_BAND_17M, _BAND_15M, _BAND_20M, _BAND_12M, _BAND_10M),
        }
    )

    # 12m/10m pair.
    pair_12_10_params = MappingProxyType(
        {
            "freq": _BAND_10M["freq"],
            "n_bands": 2,
            "bands": (_BAND_12M, _BAND_10M, _BAND_20M, _BAND_17M, _BAND_15M),
        }
    )

    def build_wires(self):
        eps = 0.01

        radius = 0.12
        t0 = radius * math.sqrt(2)

        n_bands = int(self.n_bands)
        if not 1 <= n_bands <= _MAX_BANDS:
            raise ValueError(f"n_bands must be in [1, {_MAX_BANDS}], got {n_bands}")
        active_bands = tuple(self.bands)[:n_bands]

        # Spoke layout uses the geometric max so individual spokes
        # always sit at the same azimuth across variants. (Re-laying
        # out per-n_bands would rotate the antenna under the user
        # whenever they toggled n_bands.)
        n = _MAX_BANDS
        lst = [
            (math.cos(math.radians(i)), math.sin(math.radians(i)))
            for i in range(360 // (2 * n), 360, 360 // n)
        ][:n_bands]

        def build_path(lst, ns, ex):
            return ((a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:]))

        def ry(p):
            return p[0], -p[1], p[2]

        # Zc, Zs are the cos/sin of the droop angle — the unit fan-spoke
        # direction (0, Zc, -Zs) from the cone apex outward.
        theta = math.radians(self.angle_deg)
        Zc = math.cos(theta)
        Zs = math.sin(theta)

        S = (0, eps, 0)
        T = ry(S)

        C = (S[0], S[1] + t0 * Zc, S[2] - t0 * Zs)

        A = [
            (C[0] + radius * x, C[1] + radius * y * Zs, C[2] + radius * y * Zc)
            for (x, y) in lst
        ]

        def dist(p0, p1):
            return math.sqrt(sum((x0 - x1) ** 2 for x0, x1 in zip(p0, p1)))

        logger.debug("t0: %s dist: %s", t0, dist(S, C))
        logger.debug("t0: %s dists from C: %s", t0, [dist(C, a) for a in A])
        logger.debug("radius: %s dists from S: %s", radius, [dist(S, a) for a in A])

        # Per-band physical length = length_factor × (c / freq).
        lengths = [
            float(b["length_factor"]) * (C_LIGHT_MHZ_M / float(b["freq"]))
            for b in active_bands
        ]

        ls = [(q / 2 - dist(S, a)) for (q, a) in zip(lengths, A)]

        B = [(AA[0], AA[1] + q * Zc, AA[2] - q * Zs) for q, AA in zip(ls, A)]

        Ay = [ry(p) for p in A]
        By = [ry(p) for p in B]

        for i in range(n_bands):
            wire_length = dist(S, A[i]) + dist(A[i], B[i])
            logger.debug(
                "%d length %s %s %s",
                i,
                wire_length,
                lengths[i] / 2,
                (wire_length - lengths[i] / 2) / lengths[i],
            )

        n_seg0 = self.nominal_nsegs
        # The feed wire (T → S) keeps n_seg=3: some bases need an
        # interior knot at the feed (n_seg=1 left the retired triangular
        # solver with zero interior knots and a crash), and 3 matches the
        # convention the rest of the design library uses for short feed
        # wires.
        n_seg1 = max(3, self.nominal_nsegs // 7)

        tups = []
        for i in range(n_bands):
            tups.extend(build_path([S, A[i], B[i]], n_seg0, None))
            tups.extend(build_path([T, Ay[i], By[i]], n_seg0, None))
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
