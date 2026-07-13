"""KJ6ER's "Dominator" — end-fed halfwave vertical with 49:1 transformer.

Third of the KJ6ER trio (see verticals.pota_performer and
verticals.challenger). The full halfwave stands on end: a 25' telescoping
whip is the radiator, fed at its bottom end through a 49:1 (or 56:1)
step-down transformer ~4' up a tripod, with a long ~33% λ linked
counterpoise off the transformer ground sloping to the earth and along
it. The vertical EFHW — lowest takeoff of the trio. Plans (rev 2025-02):
https://www.vhfclub.org/pdf/Dominator%20Antenna%20by%20KJ6ER%20(2025-02).pdf

Published claims this model duplicates (4NEC2, 15M = 21.350 MHz,
"Computer Model" lengths 272" radiator / 175" counterpoise):
peak +0.60 dBi @ 18° elevation, −3 dB beamwidth 27°, SWR 1.006 (at
2450 Ω); "structural efficiency" 99.5%; measured transformer insertion
loss −0.96 dB (TennTennas 49:1) or −0.40 dB (MyAntennas 56:1, the
"Dominator+" — the `plus` variant). Note the honest asymmetry KJ6ER
himself points out: the EFHW's transformer is the lossiest component in
any of his three antennas — ~20% of input power for the stock 49:1 —
which is the same story our wire.efhw_sloper budget tells.

As with the Challenger, `lmag_uH`/`qlmag` are calibrated so the budget's
(mag) row reproduces the measured insertion loss at 21.35 MHz, not
derived from core data. The end-fed's high-Z feed uses the same
gap-wire + counterpoise conditioning as wire.efhw_sloper.
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

_ALUMINUM = WireSpec(radius=0.006, conductivity=3.5e7)

# xfmr_ratio dropdown → turns (feed side : rig side). 56:1 is 56.25 (7.5t).
XFMR_TURNS = {
    "49:1": 7.0,
    "56:1": 7.5,
}


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # 15M reference band ("Computer Model" columns).
            "freq": 21.35,
            "whip_len_m": 272 * _IN,
            "cp_len_m": 175 * _IN,
            # Feed 48–52" up ("I recommend the feedpoint be elevated
            # around 48-52 inches").
            "h_feed": 50 * _IN,
            # The long counterpoise slopes gently to just above the earth
            # (droop ≈ 15°) — "extended... to provide a reliable return
            # path".
            "cp_end_h": 0.08,
            "xfmr_ratio": "49:1",
            # Calibrated to the TennTennas 49:1's measured −0.96 dB at
            # 21.35 MHz. The `plus` variant re-lands the MyAntennas 56:1's
            # −0.40 dB.
            "lmag_uH": 0.33,
            "qlmag": 3.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "xz",
                    "whip_len_m": {"min": 2.0, "max": 8.5, "unit": "m"},
                    "cp_len_m": {"min": 1.0, "max": 6.0, "unit": "m"},
                    "h_feed": {"min": 0.3, "max": 1.6, "unit": "m"},
                    "cp_end_h": {"min": 0.02, "max": 1.0, "unit": "m"},
                    "xfmr_ratio": {"enum_options": tuple(XFMR_TURNS)},
                    "lmag_uH": {"min": 0.1, "max": 50.0},
                    "qlmag": {"min": 0.0, "max": 200.0},
                    "sweep_policy": MappingProxyType(
                        {"anchor": "meas_freq", "band_locked": True}
                    ),
                }
            ),
        }
    )

    # Dominator+: MyAntennas MEF-130-LP 56:1, measured −0.40 dB.
    plus_params = MappingProxyType(
        {"xfmr_ratio": "56:1", "lmag_uH": 0.74, "qlmag": 3.0}
    )

    # Per-band "Computer Model" radiator/counterpoise lengths.
    band17_params = MappingProxyType(
        {"freq": 18.14, "whip_len_m": 315 * _IN, "cp_len_m": 206 * _IN}
    )
    band12_params = MappingProxyType(
        {"freq": 24.94, "whip_len_m": 233 * _IN, "cp_len_m": 150 * _IN}
    )
    band10_params = MappingProxyType(
        {"freq": 28.40, "whip_len_m": 204 * _IN, "cp_len_m": 132 * _IN}
    )

    def build_wire_material(self):
        return _ALUMINUM

    def build_wires(self):
        eps = 0.05
        h = self.h_feed

        droop = math.asin(min(1.0, max(0.0, h - self.cp_end_h) / self.cp_len_m))

        return [
            ((0, 0, h), (0, 0, h + eps), 1, None, "ant"),
            ((0, 0, h + eps), (0, 0, h + self.whip_len_m), self.nominal_nsegs, None),
            (
                (0, 0, h),
                (
                    self.cp_len_m * math.cos(droop),
                    0.0,
                    h - self.cp_len_m * math.sin(droop),
                ),
                max(7, self.nominal_nsegs // 2),
                None,
            ),
        ]

    def build_network(self):
        turns = XFMR_TURNS[self.xfmr_ratio]
        return Network(
            ports={"ant": PortOnWire("ant"), "rig": PortVirtual("rig")},
            branches=[
                Transformer(
                    a="rig",
                    b="ant",
                    n=1.0 / turns,
                    lmag=self.lmag_uH * 1e-6,
                    qlmag=self.qlmag if self.qlmag > 0 else None,
                )
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
