"""Multiband end-fed half wave (40/20/15/10 m) on a tapped autotransformer,
with a harmonic-aligning capacitor in the wire (issue #2062).

The classic multiband EFHW: a half wave on 40 m strung as a horizontal flat
top, so 20, 15 and 10 m are its 2nd, 3rd and 4th harmonics, each with a
high-impedance end the box can match. The box is ONE tapped winding on a
ferrite toroid -- the 49:1 most builds actually are -- rather than the
isolated two-winding transformer ``wire.efhw_sloper``'s `station.unun`
builds, and the coax is part of the antenna.

Physics worth knowing before turning the knobs:

* **A plain wire's harmonics do not land on the bands.** End effects and
  the feed make each harmonic fall progressively further from n times the
  fundamental, so a wire cut for 40 m drifts off 20, 15 and 10. A small
  series capacitor in the wire (``load_c_pF``, ``load_at`` of the way out
  from the feed) shortens the wire electrically by a different amount on
  each band -- it is in a different place on each band's standing wave --
  which is what pulls the harmonics back into line. Builds often hang a
  bleed resistor (~100 kΩ) across it so the far section cannot charge up
  with static; at RF it adds milliohms, so the model leaves it out.
* **The box is coupled inductors, not an ideal ratio.**
  `station.autotransformer` (#594) models the tapped winding: the common
  section (datum to tap, ``taps`` primary turns) carries the DIFFERENCE of
  the rig and antenna currents, and the coupling ``k`` below 1 leaves a
  leakage inductance in series with the high-Z side, which grows with
  frequency. ``taps`` picks the turns (2:14 and 3:21 are both 7:1, so 49:1;
  2:16 is 64:1); the section inductances follow from ``al_nH``, the core's
  A_L (FT240-43 ≈ 1075 nH/N²). At ``k`` → 1 with large inductances the tap
  sees Z_ant/n², exactly the ideal unun.
* **The comp cap compensates that leakage.** ``comp_c_pF`` sits across the
  tap (rig) side, and matters most on 10 m.
* **Core loss is a fixed ``ql``, not the ferrite.** `Autotransformer` takes
  no ``core=`` (unlike `Transformer`), so #43's frequency-dependent
  permeability is not modelled; both sections get one Q, and the winding
  loss lands in the power budget as a resistive row.
* **The coax is an antenna wire.** The feedline's shield runs from the feed
  point straight down to ``shield_h_m`` and then along the ground (+y) for
  the rest of ``line_len_m``. Without a choke the shield is a second
  counterpoise; ``choke`` puts a common-mode choke ``choke_at_m`` down the
  shield, modelled as a parallel R‖L‖C with peak resistance ``choke_kohm``
  at ``choke_f0_mhz`` (Q 1, broadband, as a mix-31 multi-turn choke
  measures). ``choke="none"`` leaves the shield bare; ``choke="ideal"``
  drops the shield wires, the line-hygiene idealization.
* **Where the impedance is read.** The workbench's measurement-plane
  picker offers the chain's three nodes: ``rig``, at the rig end of the coax
  (the default, what the radio sees); ``tap``, the box's tap with the comp
  cap across it and no coax, what an analyser clipped to the box reads; and
  ``ant``, across the feed gap with no box, the bare wire the box has to
  match. The shield wires stay at every plane, so the antenna is the same one
  each plane reads.

SimNEC export refuses `Autotransformer`, so this design does not export to
SimNEC.

Geometry, in the x-z plane with the coax along +y:

     counterpoise         F  radiator (+x)            load cap      far end
       (slopes down        ●=========================||============   z = height_m
        toward −x,         |  F = "ant" gap: autotransformer top;
        cp_slope_deg)      |  tap → comp cap ∥ → coax (TL) → rig
                           |  shield (choke choke_at_m down)
                           +------------- along +y, shield_h_m above ground
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs import analyses as an
from antennaknobs.network import (
    CABLES,
    Driven,
    Instance,
    Load,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
    TL,
    Wire,
    WireSpec,
    WIRES,
    cable_from_catalog,
)
from antennaknobs.station import autotransformer

# taps dropdown → (primary turns, total turns) on the one winding. The
# impedance ratio is (total / primary)²: 49:1 for both 7:1 builds, 64:1 for
# 2:16.
TAPS = {
    "2:14": (2, 14),
    "3:21": (3, 21),
    "2:16": (2, 16),
}

# The bands the antenna is for: (label, lo, hi) MHz, US edges.
BANDS = (
    ("40 m", 7.0, 7.3),
    ("20 m", 14.0, 14.35),
    ("15 m", 21.0, 21.45),
    ("10 m", 28.0, 29.7),
)

# Every wire meshes at 10 m's density, whatever band is solved, so a band
# change never re-meshes.
MESH_MHZ = 29.7

# The coax shield as a wire: bare copper at the braid's radius (RG-8X class).
SHIELD = WireSpec(radius=0.0024, conductivity=5.8e7)

CHOKES = ("ferrite", "none", "ideal")

# Short named wires that carry a port in their interior.
GAP_M = 0.05


def section_uH(taps: str, al_nH: float) -> tuple[float, float]:
    """``(lower, upper)`` section inductances in µH for ``taps`` on a core
    of A_L ``al_nH`` (nH per turn²): the common section has the primary
    turns, the upper section the remainder."""
    pri, total = TAPS[taps]
    return al_nH * pri**2 * 1e-3, al_nH * (total - pri) ** 2 * 1e-3


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 7.1,
            "freq": 7.1,
            "height_m": 9.0,
            # The radiator, as a fraction of a half wave at design_freq.
            # length_factor, load_c_pF, load_at and comp_c_pF are tuned
            # together for the lowest worst-case SWR at three points across
            # each of 40, 20 and 15 m and 28.0-28.6 MHz, over average ground
            # (Sommerfeld, εr 13, σ 0.005): 1.60. Without the load cap the
            # same wire's worst point is past 2.5.
            "length_factor": 0.999,
            "wire_type": "18-awg",
            "load_c_pF": 166.0,
            # Where the load cap sits, as a fraction of the radiator from
            # the feed point.
            "load_at": 0.583,
            # The counterpoise is the box's return, and it is load-bearing:
            # at 0.5 m the worst SWR is 2.40, and 4.05 with the coax choked
            # off ideally. With it at 4 m the shield carries little, so the
            # choke barely matters (no choke: 1.60; ideal: 1.80).
            "cp_len_m": 4.0,
            "cp_slope_deg": 60.0,
            "taps": "2:14",
            "al_nH": 1075.0,
            "k": 0.98,
            "ql": 300.0,
            "comp_c_pF": 43.0,
            "cable": "RG-8X",
            "line_len_m": 20.0,
            "shield_h_m": 0.05,
            "choke": "ferrite",
            "choke_kohm": 5.0,
            "choke_f0_mhz": 14.0,
            "choke_at_m": 0.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "xz",
                    "height_m": {"min": 3.0, "max": 20.0, "unit": "m"},
                    "length_factor": {"min": 0.85, "max": 1.15},
                    "wire_type": {"enum_options": tuple(sorted(WIRES))},
                    "load_c_pF": {"min": 0.0, "max": 1000.0, "unit": "pF"},
                    "load_at": {"min": 0.1, "max": 0.95},
                    "cp_len_m": {"min": 0.5, "max": 10.0, "unit": "m"},
                    "cp_slope_deg": {"min": 0.0, "max": 85.0},
                    "taps": {"enum_options": tuple(TAPS)},
                    "al_nH": {"min": 100.0, "max": 3000.0},
                    "k": {"min": 0.90, "max": 1.0},
                    "ql": {"min": 0.0, "max": 500.0},
                    "comp_c_pF": {"min": 0.0, "max": 330.0, "unit": "pF"},
                    "cable": {"enum_options": tuple(sorted(CABLES))},
                    "line_len_m": {"min": 5.0, "max": 40.0, "unit": "m"},
                    "shield_h_m": {"min": 0.01, "max": 1.0, "unit": "m"},
                    "choke": {"enum_options": CHOKES},
                    "choke_kohm": {"min": 0.1, "max": 50.0},
                    "choke_f0_mhz": {"min": 1.0, "max": 60.0},
                    "choke_at_m": {"min": 0.0, "max": 8.0, "unit": "m"},
                    # Keys are the structural labels the solver emits -- keep
                    # in sync with build_network below.
                    "budget_labels": {
                        "box: Autotransformer tap→ant (lower)": "winding, common section",
                        "box: Autotransformer tap→ant (upper)": "winding, upper section",
                        "Shunt tap": "comp cap",
                        "Load load": "load cap",
                        "Load choke": "common-mode choke",
                        "TL rig→tap": "feedline",
                    },
                }
            ),
        }
    )

    def build_analyses(self):
        """SWR from 3 to 30 MHz in one sweep (the fundamental and its
        harmonics), then each band on its own, over average ground
        (Sommerfeld, the workbench's default)."""
        ground = "finite:13,0.005"
        bands = "Bands"
        return [
            an.band_swr(
                name="SWR 3-30 MHz",
                sweep=an.Sweep(an.FREQUENCY, 3.0, 30.0, points=271),
                ground=ground,
                group=bands,
            ),
            *(
                an.band_swr(
                    name=f"SWR {label}",
                    sweep=an.Sweep(an.FREQUENCY, lo, hi, points=36),
                    ground=ground,
                    group=bands,
                )
                for label, lo, hi in BANDS
            ),
        ]

    def _segs(self, length: float) -> int:
        return self.segs_for(length, 0.25 * self.c_light_mhz_m / MESH_MHZ)

    def _wire(self, p0, p1, name=None, spec=None) -> Wire:
        n = self._segs(math.dist(p0, p1))
        return Wire(p0, p1, n, name=name, spec=spec)

    def _gapped(self, p0, p1, gaps, spec=None) -> list[Wire]:
        """The straight run p0 → p1, broken by one-segment GAP_M wires.

        ``gaps`` is ``(at_m, name)`` pairs in order along the run: each gap
        starts ``at_m`` from ``p0`` and carries ``name`` (a named wire is a
        port edge; None keeps it plain wire, so switching an element off
        leaves the mesh alone). A gap at 0 has no wire before it.
        """
        d = tuple((b - a) / math.dist(p0, p1) for a, b in zip(p0, p1, strict=True))

        def along(p, m):
            return tuple(a + u * m for a, u in zip(p, d, strict=True))

        wires, prev = [], p0
        for at_m, name in gaps:
            start = along(p0, at_m)
            if start != prev:
                wires.append(self._wire(prev, start, spec=spec))
            prev = along(start, GAP_M)
            wires.append(Wire(start, prev, 1, name=name, spec=spec))
        return [*wires, self._wire(prev, p1, spec=spec)]

    def build_wires(self):
        h = self.height_m
        length = 0.5 * self.design_wavelength * self.length_factor
        if not 0.0 < self.load_at < 1.0:
            raise ValueError(f"load_at {self.load_at:g} is not inside the radiator")
        cap_x = GAP_M + self.load_at * (length - GAP_M)
        s = math.radians(self.cp_slope_deg)
        cp_end = (-self.cp_len_m * math.cos(s), 0.0, h - self.cp_len_m * math.sin(s))
        if cp_end[2] <= 0.0:
            raise ValueError(
                f"the counterpoise ({self.cp_len_m:g} m at {self.cp_slope_deg:g}°) "
                f"reaches the ground from {h:g} m"
            )
        feed = (0.0, 0.0, h)
        # The radiator: the feed gap (the box's top sits across it), then the
        # load cap's gap.
        wires = [
            self._wire(cp_end, feed),
            *self._gapped(
                feed,
                (length, 0.0, h),
                [(0.0, "ant"), (cap_x, "load" if self.load_c_pF > 0 else None)],
            ),
        ]
        if self.choke == "ideal":
            return wires

        # The shield: the drop from the feed point to shield_h_m, with the
        # choke's gap choke_at_m down it, then the run along +y for what is
        # left of the line.
        drop = h - self.shield_h_m
        if self.line_len_m <= drop + GAP_M:
            raise ValueError(
                f"line_len_m {self.line_len_m:g} m does not reach the ground "
                f"from height_m {h:g} m"
            )
        if not 0.0 <= self.choke_at_m <= drop - GAP_M:
            raise ValueError(
                f"choke_at_m {self.choke_at_m:g} m is not on the shield's "
                f"{drop:g} m drop to the ground"
            )
        knee = (0.0, 0.0, self.shield_h_m)
        end = (0.0, self.line_len_m - drop, self.shield_h_m)
        choke = "choke" if self.choke == "ferrite" else None
        return [
            *wires,
            *self._gapped(feed, knee, [(self.choke_at_m, choke)], spec=SHIELD),
            self._wire(knee, end, spec=SHIELD),
        ]

    def plane_labels(self):
        """The measurement-plane picker's names for the chain's nodes."""
        return {
            "rig": "rig (end of the coax)",
            "tap": "tap (at the box)",
            "ant": "ant (bare feed gap)",
        }

    def build_network(self):
        lower, upper = section_uH(self.taps, self.al_nH)
        ports = {
            "rig": PortVirtual("rig"),
            "tap": PortVirtual("tap"),  # the box's tap: the rig side of the winding
            "ant": PortOnWire("ant"),
        }
        branches = [
            TL.from_cable(
                cable_from_catalog(self.cable), "rig", "tap", self.line_len_m
            ),
            Instance(
                "box",
                autotransformer(
                    lower, upper, k=self.k, ql=self.ql if self.ql > 0 else None
                ),
                tap="tap",
                top="ant",
            ),
        ]
        if self.comp_c_pF > 0:
            branches.append(Shunt("tap", c=self.comp_c_pF * 1e-12))
        if self.load_c_pF > 0:
            ports["load"] = PortOnWire("load")
            branches.append(Load("load", c=self.load_c_pF * 1e-12))
        if self.choke == "ferrite":
            # R‖L‖C, peak choke_kohm at choke_f0_mhz, Q 1: X_L = R there.
            r = self.choke_kohm * 1e3
            w0 = 2 * math.pi * self.choke_f0_mhz * 1e6
            ports["choke"] = PortOnWire("choke")
            branches.append(Load("choke", r=r, l=r / w0, c=1 / (w0 * r), parallel=True))
        return Network(
            ports=ports,
            branches=branches,
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
