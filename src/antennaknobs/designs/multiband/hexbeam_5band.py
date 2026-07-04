"""Stacked hexbeam: up to 5 concentric hexbeam shapes stacked along z,
each sized to its own band's wavelength and driven by its own feed.

Each band reuses the single-band hexbeam geometry (driver hex with t0/t1
tip segments, reflector hex, 1-segment T->S feed gap). Per-band sizing
follows the momwire convention: halfdriver = halfdriver_factor * lambda/4.
Bands stack along z at z = base + (n_bands - 1 - i) * z_spacing, so
band 0 (longest wavelength) sits on top and band N-1 sits at base —
the usual physical convention for stacked Yagi/hexbeam towers.

Two feed modes are exposed via daisy_chain:
  * False (default) — multi-feed: every band driven independently with
    V = 1+0j. The response carries one entry in feeds[] per band so the
    Smith chart shows per-band driving-point Z.
  * True — daisy-chain: only band 0 is driven externally; the lower
    bands couple via 50ohm TL jumpers of length z_spacing between
    successive feeds. build_tls() emits the jumper specs. Momwire engines
    don't support TLs yet; the frontend greys out the toggle when a
    momwire slot is active.
"""

import math
from types import MappingProxyType

from ... import AntennaBuilder

C_LIGHT_MHZ_M = 299.792458

_MAX_BANDS = 5

# Per-band canonical defaults. Each band carries its own freq plus the
# three shape factors that scale the hexbeam against its wavelength.
# Variants pick a subset (n_bands of these become active) but the tuple
# always has length _MAX_BANDS so variant overlay stays aligned with the
# frontend's preallocated group instances.
_BAND_20M = {
    "freq": 14.300,
    "halfdriver_factor": 1.071,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.1243,
}
_BAND_17M = {
    "freq": 18.1575,
    "halfdriver_factor": 1.071,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.1243,
}
_BAND_15M = {
    "freq": 21.383,
    "halfdriver_factor": 1.071,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.1243,
}
_BAND_12M = {
    "freq": 24.97,
    "halfdriver_factor": 1.071,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.1243,
}
_BAND_10M = {
    "freq": 28.47,
    "halfdriver_factor": 1.071,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.1243,
}

# Feed-gap half-spacing in meters between T and S knots. Matches the
# single-band hexbeam (designs/hexbeam.py:28).
_FEED_GAP = 0.05


def _band_anchors(halfdriver, tipspacer_factor, t0_factor):
    """Hex anchors for one band at z=0. Lifted from designs/hexbeam.py
    so the 5-band file stays self-contained — if a third user appears,
    factor into a shared helper module."""
    radius = halfdriver / (2 - t0_factor - tipspacer_factor)
    tipspacer = radius * tipspacer_factor
    t0 = radius * t0_factor
    t1 = radius - tipspacer - t0

    sin30 = 0.5
    cos30 = math.sqrt(3) / 2

    def rx(p):
        return -p[0], p[1], p[2]

    def ry(p):
        return p[0], -p[1], p[2]

    A = (radius * cos30, radius * sin30, 0)
    B = (A[0] - t1 * cos30, A[1] + t1 * sin30, 0)
    D = (0, radius, 0)
    C = (D[0] + t0 * cos30, D[1] - t0 * sin30, 0)
    E = rx(A)
    F = ry(E)
    G = ry(D)
    H = ry(C)
    II = ry(B)
    J = ry(A)
    S = (_FEED_GAP * cos30, _FEED_GAP * sin30, 0)
    T = ry(S)

    return {
        "S": S,
        "A": A,
        "B": B,
        "C": C,
        "D": D,
        "E": E,
        "F": F,
        "G": G,
        "H": H,
        "I": II,
        "J": J,
        "T": T,
    }


# Per-band shape factors after a sequential single-band tune against
# Z = 50 + 0j on PyNEC (free space, no ground). One band at a time with
# n_bands=1 — scripts/tune_hexbeam_5band_band.py. Inter-band coupling
# wasn't modelled in this pass; expect Z to drift a few ohms when all
# five bands coexist. Use as a starting point for full 5-band joint
# tuning.
_BAND_20M_OPT = {
    "freq": 14.300,
    "halfdriver_factor": 1.0533,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.1448,
}
_BAND_17M_OPT = {
    "freq": 18.1575,
    "halfdriver_factor": 1.0556,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.1431,
}
_BAND_15M_OPT = {
    "freq": 21.383,
    "halfdriver_factor": 1.0572,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.1417,
}
_BAND_12M_OPT = {
    "freq": 24.97,
    "halfdriver_factor": 1.0590,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.1403,
}
_BAND_10M_OPT = {
    "freq": 28.47,
    "halfdriver_factor": 1.0582,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.1379,
}


# Coupled-mode tune from scripts/tune_hexbeam_5band_coupled.py — bands
# stay present at every objective evaluation so the optimiser sees real
# inter-band coupling. Four passes converged with worst |Z - 50| ≈ 7.7 Ω
# on band 1 (resistance stuck at ~42; reactance went to ~0 everywhere).
# Better starting point than _BAND_*_OPT for the joint solve, but you'd
# need a 3-knob tune (add tipspacer_factor) or relax R to push closer
# to a perfect 50+0j match.
_BAND_20M_COUPLED = {
    "freq": 14.300,
    "halfdriver_factor": 1.04834,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.14394,
}
_BAND_17M_COUPLED = {
    "freq": 18.1575,
    "halfdriver_factor": 1.05036,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.14025,
}
_BAND_15M_COUPLED = {
    "freq": 21.383,
    "halfdriver_factor": 1.04961,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.14056,
}
_BAND_12M_COUPLED = {
    "freq": 24.97,
    "halfdriver_factor": 1.04908,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.14045,
}
_BAND_10M_COUPLED = {
    "freq": 28.47,
    "halfdriver_factor": 1.06693,
    "tipspacer_factor": 0.1312,
    "t0_factor": 0.14665,
}


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 14.300,
            "freq": 14.300,
            "base": 7.0,
            "z_spacing": 0.2,
            "daisy_chain": False,
            "n_bands": _MAX_BANDS,
            "bands": (_BAND_20M, _BAND_17M, _BAND_15M, _BAND_12M, _BAND_10M),
            "ui_params": MappingProxyType(
                {
                    "sweep_policy": {
                        "anchor": "meas_freq",
                        "band_locked": True,
                    },
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
                        "halfdriver_factor": {
                            "min": 0.9,
                            "max": 1.2,
                        },
                        "tipspacer_factor": {
                            "min": 0.05,
                            "max": 0.30,
                        },
                        "t0_factor": {
                            "min": 0.05,
                            "max": 0.30,
                        },
                    },
                    "n_bands": {
                        "min": 1,
                        "max": _MAX_BANDS,
                        "step": 1,
                    },
                    "z_spacing": {
                        "min": 0.05,
                        "max": 3.0,
                        "step": 0.01,
                        "precision": 2,
                        "unit": " m",
                    },
                    "daisy_chain": {
                        "label": "Daisy-chain feed (PyNEC only)",
                    },
                }
            ),
        }
    )

    # Sequential single-band tune against Z = 50 + 0j on PyNEC.
    # See _BAND_*_OPT comment and scripts/tune_hexbeam_5band_band.py.
    # Tuned variants overlay default_params, differing only in the per-band
    # shape factors (design_freq / freq / base / z_spacing / daisy_chain /
    # n_bands all come from default).
    opt_params = MappingProxyType(
        {
            "bands": (
                _BAND_20M_OPT,
                _BAND_17M_OPT,
                _BAND_15M_OPT,
                _BAND_12M_OPT,
                _BAND_10M_OPT,
            ),
        }
    )

    # Coupled multi-band tune; see _BAND_*_COUPLED comment.
    opt_coupled_params = MappingProxyType(
        {
            "bands": (
                _BAND_20M_COUPLED,
                _BAND_17M_COUPLED,
                _BAND_15M_COUPLED,
                _BAND_12M_COUPLED,
                _BAND_10M_COUPLED,
            ),
        }
    )

    def build_wires(self):
        n_bands = int(self.n_bands)
        if not 1 <= n_bands <= _MAX_BANDS:
            raise ValueError(f"n_bands must be in [1, {_MAX_BANDS}], got {n_bands}")
        active_bands = tuple(self.bands)[:n_bands]

        n_seg0 = self.nominal_nsegs
        # Tip segments stay short; floor at 1 matches single-band hexbeam
        # (designs/hexbeam.py:66 leaves the tip count at 1 too).
        n_seg_tip = max(1, self.nominal_nsegs // 21)
        n_seg_feed = 1  # the T->S feed gap is always one segment

        tups = []
        # build_wires() emits, per band, six edges from the driver hex,
        # one tip edge on the reflector, three reflector edges, one more
        # reflector tip, and finally the 1-segment feed across T->S.
        # The feed tuple's index inside the flat list is recorded so
        # build_tls() can wire daisy-chain jumpers between successive
        # feeds without re-running build_wires().
        self._feed_wire_indices = []

        for band_idx, band in enumerate(active_bands):
            wavelength = C_LIGHT_MHZ_M / float(band["freq"])
            halfdriver = float(band["halfdriver_factor"]) * wavelength / 4.0
            anchors = _band_anchors(
                halfdriver,
                float(band["tipspacer_factor"]),
                float(band["t0_factor"]),
            )

            # z-stagger: band 0 sits on top.
            zoff = self.base + (n_bands - 1 - band_idx) * self.z_spacing

            def at_z(p):
                return (p[0], p[1], p[2] + zoff)

            S = at_z(anchors["S"])
            A = at_z(anchors["A"])
            B = at_z(anchors["B"])
            C = at_z(anchors["C"])
            D = at_z(anchors["D"])
            E = at_z(anchors["E"])
            F = at_z(anchors["F"])
            G = at_z(anchors["G"])
            H = at_z(anchors["H"])
            II = at_z(anchors["I"])
            J = at_z(anchors["J"])
            T = at_z(anchors["T"])

            def build_path(lst, ns):
                return [(a, b, ns, None) for a, b in zip(lst[:-1], lst[1:])]

            tups.extend(build_path([S, A, B], n_seg0))
            tups.extend(build_path([C, D], n_seg_tip))
            tups.extend(build_path([D, E, F, G], n_seg0))
            tups.extend(build_path([G, H], n_seg_tip))
            tups.extend(build_path([II, J, T], n_seg0))
            # The feed wire (one per band). Daisy-chain mode strips the
            # excitation on bands 1..N-1 inside build_tls; multi-feed
            # mode leaves every band's excitation in place.
            tups.append((T, S, n_seg_feed, 1 + 0j))
            self._feed_wire_indices.append(len(tups))  # 1-indexed NEC tag

        if self.daisy_chain:
            # Daisy-chain mode: only band 0 stays excited. The TL jumpers
            # added in build_tls() couple bands 1..N-1 to their upstream
            # neighbour.
            for idx in self._feed_wire_indices[1:]:
                p0, p1, ns, _ = tups[idx - 1]
                tups[idx - 1] = (p0, p1, ns, None)

        return tups

    def build_tls(self):
        """50ohm jumpers between successive band feeds in daisy-chain mode.
        Each tuple is (idx1, seg1, idx2, seg2, impedance, length) — the
        shape PyNECEngine.tl_card expects. Momwire engines reject any
        non-empty list (engines/momwire.py:90), which the frontend should
        guard against by greying out the toggle when a momwire slot is
        active."""
        if not getattr(self, "daisy_chain", False):
            return []
        # build_wires must run first to populate _feed_wire_indices.
        if not hasattr(self, "_feed_wire_indices"):
            self.build_wires()
        feeds = self._feed_wire_indices
        # Feed wire has n_seg_feed=1 segment, so the centre segment is
        # always 1.
        seg = 1
        tls = []
        for i in range(len(feeds) - 1):
            tls.append((feeds[i], seg, feeds[i + 1], seg, 50.0, self.z_spacing))
        return tls
