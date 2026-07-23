"""KJ6ER's "POTA PERformer" — elevated quarter-wave with tuned radials.

A faithful model of a popular published portable design: Greg Mihran
KJ6ER's PERformer (Portable, Elevated, Resonant), a one-band-at-a-time
quarter-wave vertical for 40M–6M. A 17' telescoping stainless whip on a
tripod/spike puts the feedpoint 52" up; two elevated tuned radials run
from the feed down to stakes at 36", giving a small droop angle. With the
radials 90° apart the antenna is mildly directional toward the radial
span; 180° apart it is omnidirectional. Plans (free PDF, rev 2025-02):
https://www.vhfclub.org/pdf/PERformer%20Antenna%20by%20KJ6ER%20(2025-02).pdf

The reason this design is in the tree is the efficiency story. KJ6ER
publishes ">90% efficient" (structural: conductor + component loss —
which we CONFIRM: the stainless whip and copper radials burn only a few
percent, and elevated radials really do remove the ground-coupled loss
resistance that eats half a ground-mounted vertical's power in-circuit).
But gain and efficiency are one measurement: integrate the published
pattern and ~70% of the input power is absorbed by real earth in the
near/far field — his own +0.31 dBi peak-gain plot *is* a ~25% radiated
fraction, stated in dB (a lossless quarter-wave with this beam shape
would show ~+5.5 dBi). Three independent engines agree on the absolute
level (15M, average ground, two radials 90°):

    KJ6ER 4NEC2:   +0.31 dBi @ 24°, F/B 3.37, el BW 46°  → ~24% radiated
    VA3KOT EZNEC:  +1.19 dBi @ 25°, F/B 3.34, el BW 47°  → ~30%
    momwire:       +1.06 dBi @ 24°, F/B 2.91, el BW 44°  →  29%
    PyNEC:         +1.02 dBi @ 23°, F/B ~3,   same shape →  34%

(VA3KOT = John, hamradiooutsidethebox.ca, independent EZNEC build of
this antenna, 2025-05; he also modeled the single-radial config —
`n_radials` reproduces it: slightly more gain and F/B, narrower el/wider
az coverage.) None of this makes the PERformer a bad antenna — ground
absorption at these heights is the same tax on every portable vertical,
so KJ6ER's *relative* claims (elevated beats ground-mounted, the
90°-span directionality) all hold up. See the advanced docs page for the
full three-ledger power accounting.

Modeling notes: the feed is a short gap wire at the whip base (ports
live in wire interiors); the feedline choke KJ6ER itemizes (−0.12 dB) is
line hygiene, not modeled. Wire material is stainless (17-7 class,
1.35e6 S/m) at the whip's mid-taper radius everywhere — the real radials
are 18 AWG copper, but wire material is per-design, and stainless
everywhere is the conservative bound (conductor loss ~2–3% either way).
Default configuration is the 15M directional (90° span) setup from the
plans' reference tables, radial span bisector on +x so the main lobe
lands on the workbench's forward direction.
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire, WireSpec

_IN = 0.0254

# Telescoping 17' stainless whip: ~10 mm diameter at the taper midpoint,
# 17-7 PH-class conductivity. Used for all wires (see modeling notes).
_STAINLESS = WireSpec(radius=0.005, conductivity=1.35e6)


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # 15M — the band KJ6ER publishes detailed model claims for.
            # Whip/radial lengths straight from the plans' per-band table
            # (144" / 120"); no retune, the point is duplicating HIS numbers.
            "freq": 21.35,
            # Geometry is per-band absolute inches; design_freq only anchors
            # auto_mesh's density scale (nominal_nsegs per quarter-wave at
            # the band the lengths are cut for), so it is hidden from the
            # UI. Each band variant restates it alongside its freq.
            "design_freq": 21.35,
            "whip_len_m": 144 * _IN,
            "radial_len_m": 120 * _IN,
            "h_feed": 52 * _IN,
            # Radial ends clip to fiberglass stakes at 36": droop ≈ 7.7°.
            "radial_end_h": 36 * _IN,
            # 90° span = directional (KJ6ER's field default); 180° = omni.
            "radial_span_deg": 90.0,
            "n_radials": 2,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "xz",
                    "design_freq": {"hidden": True},
                    # Max covers band20's 207" = 5.26 m (17' whip + stud).
                    "whip_len_m": {"min": 1.0, "max": 5.3, "unit": "m"},
                    "radial_len_m": {"min": 0.5, "max": 5.1, "unit": "m"},
                    "h_feed": {"min": 0.5, "max": 2.5, "unit": "m"},
                    "radial_end_h": {"min": 0.2, "max": 2.0, "unit": "m"},
                    "radial_span_deg": {"min": 30.0, "max": 180.0},
                    "n_radials": {"min": 1, "max": 2},
                }
            ),
        }
    )

    # Omnidirectional configuration: radials opposite each other.
    omni_params = MappingProxyType({"radial_span_deg": 180.0})

    # VA3KOT's single-radial field simplification (EZNEC: +1.34 dBi,
    # F/B 4.6 vs 1.19/3.34 for the pair). The lone radial runs along +x.
    single_radial_params = MappingProxyType({"n_radials": 1})

    # Per-band whip/radial lengths from the plans (target freqs + inches).
    # design_freq tracks the band so the auto-mesh density follows the
    # wavelength the lengths are cut for.
    band20_params = MappingProxyType(
        {
            "freq": 14.25,
            "design_freq": 14.25,
            "whip_len_m": 207 * _IN,
            "radial_len_m": 198 * _IN,
        }
    )
    band17_params = MappingProxyType(
        {
            "freq": 18.14,
            "design_freq": 18.14,
            "whip_len_m": 165 * _IN,
            "radial_len_m": 149 * _IN,
        }
    )
    band12_params = MappingProxyType(
        {
            "freq": 24.94,
            "design_freq": 24.94,
            "whip_len_m": 126 * _IN,
            "radial_len_m": 96 * _IN,
        }
    )
    band10_params = MappingProxyType(
        {
            "freq": 28.40,
            "design_freq": 28.40,
            "whip_len_m": 113 * _IN,
            "radial_len_m": 80 * _IN,
        }
    )
    band6_params = MappingProxyType(
        {
            "freq": 51.00,
            "design_freq": 51.00,
            "whip_len_m": 64 * _IN,
            "radial_len_m": 43 * _IN,
        }
    )

    def build_wire_material(self):
        return _STAINLESS

    def build_wires(self):
        eps = 0.05
        h = self.h_feed

        # Droop angle from the feed down to the staked radial ends.
        drop = max(0.0, h - self.radial_end_h)
        droop = math.asin(min(1.0, drop / self.radial_len_m))

        tups = [
            # Gap wire at the whip base carries the port (ev on its one
            # segment); the whip proper stacks on top of it.
            Wire((0, 0, h), (0, 0, h + eps), ex=1 + 0j),
            Wire((0, 0, h + eps), (0, 0, h + self.whip_len_m)),
        ]

        n = int(self.n_radials)
        # Two radials straddle +x by ±span/2 so the lobe fires forward;
        # a single radial runs along +x itself.
        phis = (
            [0.0] if n == 1 else [-self.radial_span_deg / 2, self.radial_span_deg / 2]
        )
        # Radials mesh at the design density like every other wire (#525
        # stage 3 retired the old max(5, N//3) hand floor).
        for phi_deg in phis:
            p = math.radians(phi_deg)
            end = (
                self.radial_len_m * math.cos(droop) * math.cos(p),
                self.radial_len_m * math.cos(droop) * math.sin(p),
                h - self.radial_len_m * math.sin(droop),
            )
            tups.append(Wire((0, 0, h), end))
        return tups
