"""KJ6ER's "Challenger" — off-center-fed halfwave vertical with 4:1 unun.

Second of the KJ6ER trio (see verticals.pota_performer for the first and
the advanced docs page for the claim-checking story). A 25' telescoping
aluminum whip is the top ~77% of a halfwave; a short linked counterpoise
(~10% λ) off the unun ground completes it. The 4:1 unun (200 Ω : 50 Ω)
sits on a tripod with the feed ~3.5' up. Plans (rev 2025-02):
https://www.vhfclub.org/pdf/Challenger%20Antenna%20by%20KJ6ER%20(2025-02).pdf

Published claims this model duplicates (4NEC2, 15M = 21.350 MHz,
"Computer Model" lengths 205" radiator / 65" counterpoise):
peak −0.32 dBi @ 20° elevation, −3 dB beamwidth 33°, SWR 1.04 (at
200 Ω); "structural efficiency" 94.3%; measured unun insertion loss
−0.34 dB (LDG RU-4:1) or −0.24 dB (Palomar Bullet, the "Challenger+" —
the `plus` variant). The same two efficiency ledgers apply as on the
PERformer: the structural numbers check out, while the far-field
radiated fraction over average ground is ~¼ — see the docs page.

The unun is a real `Transformer` branch: `lmag_uH`/`qlmag` are NOT
derived from core datasheets — they are calibrated so the power
budget's (mag) row reproduces the measured insertion loss at the 15M
reference frequency (loss varies ~1/f across bands, a modeling
simplification the measured broadband figures gloss over too). The
feedline choke (−0.12 dB) is line hygiene, not modeled.

Geometry: gap wire at the whip base carries the "ant" port; the
counterpoise slopes from the feed down toward a near-ground end
(`cp_end_h`), running along +x — "drops at 30–45° then along the
ground" per the plans.
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import (
    Driven,
    Network,
    PortOnWire,
    PortVirtual,
    Transformer,
    WireSpec,
)

_IN = 0.0254

# 25' telescoping aluminum whip (6063-class), mid-taper radius.
_ALUMINUM = WireSpec(radius=0.006, conductivity=3.5e7)


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # 15M — the band the plans publish detailed 4NEC2 claims for.
            "freq": 21.35,
            # "Computer Model" columns: 12" pigtail + whip = total radiator.
            "whip_len_m": 205 * _IN,
            "cp_len_m": 65 * _IN,
            # Feed ~3.5' up on the tripod ("roughly 3-4 feet").
            "h_feed": 42 * _IN,
            # Counterpoise end lands just off the ground (droop ≈ 35°).
            "cp_end_h": 0.12,
            # Calibrated to the LDG RU-4:1's measured −0.34 dB at 21.35 MHz
            # (see module docstring). The `plus` variant re-lands −0.24 dB.
            "lmag_uH": 1.22,
            "qlmag": 3.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "xz",
                    "whip_len_m": {"min": 1.0, "max": 8.0, "unit": "m"},
                    "cp_len_m": {"min": 0.3, "max": 3.0, "unit": "m"},
                    "h_feed": {"min": 0.3, "max": 1.5, "unit": "m"},
                    "cp_end_h": {"min": 0.02, "max": 1.0, "unit": "m"},
                    "lmag_uH": {"min": 0.2, "max": 50.0},
                    "qlmag": {"min": 0.0, "max": 200.0},
                    "sweep_policy": MappingProxyType(
                        {"anchor": "meas_freq", "band_locked": True}
                    ),
                }
            ),
        }
    )

    # Challenger+: Palomar Bullet 4:1, measured −0.24 dB.
    plus_params = MappingProxyType({"lmag_uH": 1.75, "qlmag": 3.0})

    # Per-band "Computer Model" radiator/counterpoise lengths.
    band20_params = MappingProxyType(
        {"freq": 14.25, "whip_len_m": 304 * _IN, "cp_len_m": 99 * _IN}
    )
    band17_params = MappingProxyType(
        {"freq": 18.14, "whip_len_m": 240 * _IN, "cp_len_m": 76 * _IN}
    )
    band12_params = MappingProxyType(
        {"freq": 24.94, "whip_len_m": 175 * _IN, "cp_len_m": 56 * _IN}
    )
    band10_params = MappingProxyType(
        {"freq": 28.40, "whip_len_m": 154 * _IN, "cp_len_m": 49 * _IN}
    )
    band6_params = MappingProxyType(
        {"freq": 51.00, "whip_len_m": 87 * _IN, "cp_len_m": 26 * _IN}
    )

    # Transformer turns ratio: 4:1 impedance = 2:1 turns, rig side low.
    turns = 2.0

    def build_wire_material(self):
        return _ALUMINUM

    def build_wires(self):
        eps = 0.05
        h = self.h_feed

        droop = math.asin(min(1.0, max(0.0, h - self.cp_end_h) / self.cp_len_m))

        return [
            (
                (0, 0, h),
                (0, 0, h + eps),
                self.segs_for(eps, self.whip_len_m),
                None,
                "ant",
            ),
            ((0, 0, h + eps), (0, 0, h + self.whip_len_m), self.nominal_nsegs, None),
            (
                (0, 0, h),
                (
                    self.cp_len_m * math.cos(droop),
                    0.0,
                    h - self.cp_len_m * math.sin(droop),
                ),
                max(5, self.nominal_nsegs // 3),
                None,
            ),
        ]

    def build_network(self):
        return Network(
            ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
            branches=[
                Transformer(
                    a="rig",
                    b="ant",
                    n=1.0 / self.turns,
                    lmag=self.lmag_uH * 1e-6,
                    qlmag=self.qlmag if self.qlmag > 0 else None,
                )
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
