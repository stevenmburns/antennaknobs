"""End-fed half-wave sloper matched with a tapped autotransformer — the
49:1 box most builds actually are (issue #2062).

The sibling of ``wire.efhw_sloper``: the same POTA sloper (counterpoise,
short "ant" gap wire, radiator climbing toward −x), but the box is ONE tapped
winding on a ferrite toroid rather than the isolated two-winding transformer
`station.unun` builds, and the coax is part of the antenna.

Physics worth knowing before turning the knobs:

* **The box is coupled inductors, not an ideal ratio.**
  `station.autotransformer` (#594) models the tapped winding: the common
  section (datum to tap, ``taps`` primary turns) carries the DIFFERENCE of
  the rig and antenna currents, and the coupling ``k`` below 1 leaves a
  leakage inductance in series with the high-Z side. ``taps`` picks the
  turns (2:14 and 3:21 are both 7:1, so 49:1; 2:16 is 64:1); the section
  inductances follow from ``al_nH``, the core's A_L (FT240-43 ≈ 1075 nH/N²).
  At ``k`` → 1 with large inductances the tap sees Z_ant/n², exactly the
  ideal unun; at a realistic ``k`` the leakage reactance is a sizeable
  fraction of the ~2–3 kΩ end-fed feed, which is why ``k`` is a
  load-bearing knob and why the comp cap's best value here is not the
  sloper's.
* **The comp cap compensates that leakage.** ``comp_c_pF`` sits across the
  tap (rig) side. In the ideal-transformer sloper it barely matters at
  14 MHz; here it is the knob that recovers the match, and its default is
  tuned with the winding in place.
* **Core loss is a fixed ``ql``, not the ferrite.** `Autotransformer` takes
  no ``core=`` (unlike `Transformer`), so #43's frequency-dependent
  permeability is not modelled; both sections get one Q, and the winding
  loss lands in the power budget as a resistive row.
* **The coax is an antenna wire.** The feedline's shield runs from the feed
  point straight down to ``shield_h_m`` and then along the ground (+y) for
  the rest of ``line_len_m``. Without a choke the shield is a second
  counterpoise and pulls the feed impedance a long way (SWR 1.91 at the
  defaults); ``choke`` puts a common-mode choke ``choke_at_m`` down the
  shield, modelled as a parallel R‖L‖C with peak resistance ``choke_kohm``
  at ``choke_f0_mhz`` (Q 1, broadband, as a mix-31 multi-turn choke
  measures). Where it sits matters: at the feed point the box's datum
  swings at nearly the full end-fed voltage, so the choke row in the power
  budget is the heat a real choke there takes. ``choke="none"`` leaves the
  shield bare; ``choke="ideal"`` drops the shield wires, the line-hygiene
  idealization ``wire.efhw_sloper`` makes.

SimNEC export refuses `Autotransformer`, so this design does not export to
SimNEC; the NEC deck writers spell the box as a network they can carry or
say why not.

Geometry is ``wire.efhw_sloper``'s `Drone` flight, plus the shield:

    apex (derived)
        /
       /  radiator ≈ λ/2 · length_factor   (wire_type from WIRES)
      /   slope_deg above horizontal
     F=========            z = h_feed        main lobe → +x
     |  counterpoise (+x)  F = "ant" port: autotransformer top
     |                     tap → comp cap ∥ → coax (TL) → rig
     |  shield (choke choke_at_m down)
     +------------- along +y, shield_h_m above ground
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder, Drone
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
    as_wire,
    cable_from_catalog,
)
from antennaknobs.station import autotransformer, autotransformer_ratio

# taps dropdown → (primary turns, total turns) on the one winding. The
# impedance ratio is (total / primary)²: 49:1 for both 7:1 builds, 64:1 for
# 2:16.
TAPS = {
    "2:14": (2, 14),
    "3:21": (3, 21),
    "2:16": (2, 16),
}

# The coax shield as a wire: bare copper at the braid's radius (RG-58 class).
SHIELD = WireSpec(radius=0.0018, conductivity=5.8e7)

CHOKES = ("ferrite", "none", "ideal")


def section_uH(taps: str, al_nH: float) -> tuple[float, float]:
    """``(lower, upper)`` section inductances in µH for ``taps`` on a core
    of A_L ``al_nH`` (nH per turn²): the common section has the primary
    turns, the upper section the remainder."""
    pri, total = TAPS[taps]
    return al_nH * pri**2 * 1e-3, al_nH * (total - pri) ** 2 * 1e-3


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 14.1,
            "freq": 14.1,
            # The sloper's geometry and its stock wire.
            "slope_deg": 63.0,
            "h_feed": 1.5,
            # Tuned with the stock box, comp cap and choke below for the best
            # rig-side SWR at 14.1 MHz over average ground (Sommerfeld,
            # εr 13, σ 0.005): 1.238. Shorter than the sloper's 0.8965,
            # because the winding's leakage adds series reactance at the top.
            "length_factor": 0.8815,
            "wire_type": "28-awg-pvc",
            "cp_len_m": 1.05,
            # The winding: 2:14 turns on an FT240-43 (A_L ≈ 1075 nH/N²) is
            # 4.3 µH common section, 155 µH upper section.
            "taps": "2:14",
            "al_nH": 1075.0,
            "k": 0.98,
            # Both sections' Q: 300 burns ~5 % in the winding at the stock
            # tune, a box inside the bench-measured 85–90 % range.
            "ql": 300.0,
            # The comp cap, tuned WITH the length (best SWR at each value,
            # same conditions as length_factor):
            #
            #     C pF   length_factor   SWR
            #     100       0.8961       1.330
            #     150       0.8815       1.238
            #     200       0.8677       1.146
            #     283       0.8468       1.001
            #
            # A perfect match exists, but at a cap twice the customary size
            # and a length off the bottom of the knob's range; 150 pF is the
            # top of what builds fit and clears 1.3.
            "comp_c_pF": 150.0,
            # The coax: its line, and its shield as antenna wire.
            "cable": "RG-58",
            "line_len_m": 5.0,
            "shield_h_m": 0.05,
            "choke": "ferrite",
            "choke_kohm": 5.0,
            "choke_f0_mhz": 14.0,
            # 1 m down the shield's drop. At the feed point the box's datum
            # swings at nearly the full end-fed voltage, and a 5 kΩ choke
            # there burns 17 % (efficiency 0.685); 1 m down it burns 7 %
            # (0.772).
            "choke_at_m": 1.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "xz",
                    "length_factor": {"min": 0.80, "max": 1.10},
                    "slope_deg": {"min": 10.0, "max": 85.0},
                    "h_feed": {"min": 0.2, "max": 4.0, "unit": "m"},
                    "cp_len_m": {"min": 0.3, "max": 6.0, "unit": "m"},
                    "wire_type": {"enum_options": tuple(sorted(WIRES))},
                    "taps": {"enum_options": tuple(TAPS)},
                    "al_nH": {"min": 100.0, "max": 3000.0},
                    "k": {"min": 0.90, "max": 1.0},
                    "ql": {"min": 0.0, "max": 500.0},
                    "comp_c_pF": {"min": 0.0, "max": 330.0, "unit": "pF"},
                    "cable": {"enum_options": tuple(sorted(CABLES))},
                    "line_len_m": {"min": 2.0, "max": 30.0, "unit": "m"},
                    "shield_h_m": {"min": 0.01, "max": 1.0, "unit": "m"},
                    "choke": {"enum_options": CHOKES},
                    "choke_kohm": {"min": 0.1, "max": 50.0},
                    "choke_f0_mhz": {"min": 1.0, "max": 60.0},
                    "choke_at_m": {"min": 0.0, "max": 3.5, "unit": "m"},
                    "sweep_policy": {"anchor": "meas_freq", "band_locked": True},
                    # Keys are the structural labels the solver emits — keep
                    # in sync with build_network below.
                    "budget_labels": {
                        "box: Autotransformer pri→ant (lower)": "winding, common section",
                        "box: Autotransformer pri→ant (upper)": "winding, upper section",
                        "Shunt pri": "comp cap",
                        "Load choke": "common-mode choke",
                        "TL rig→pri": "feedline",
                    },
                }
            ),
        }
    )

    @property
    def turns_ratio(self) -> float:
        """The ideal (k → 1) voltage ratio of the chosen taps."""
        return autotransformer_ratio(*section_uH(self.taps, self.al_nH))

    def build_wires(self):
        eps = 0.05
        length = 0.5 * self.design_wavelength * self.length_factor

        # The sloper's flight: counterpoise in along −x to the feed point,
        # pitch up, gap wire, radiator climbing toward −x.
        d = Drone((self.cp_len_m, 0.0, self.h_feed))
        d.face((-1.0, 0.0, 0.0))
        d.pay_out().forward(self.cp_len_m)
        d.pitch(-self.slope_deg)
        d.forward(eps)
        d.forward(length - eps)
        wires = d.wires()
        gap = as_wire(wires[1])
        wires[1] = Wire(gap.p0, gap.p1, name="ant")
        if self.choke == "ideal":
            return wires

        # The shield: the drop from the feed point to shield_h_m, with a
        # short "choke" wire choke_at_m down it (the choke is a port in its
        # interior), then the run along +y for what is left of the line.
        drop = self.h_feed - self.shield_h_m
        if self.line_len_m <= drop + eps:
            raise ValueError(
                f"line_len_m {self.line_len_m:g} m does not reach the ground "
                f"from h_feed {self.h_feed:g} m"
            )
        if not 0.0 <= self.choke_at_m <= drop - eps:
            raise ValueError(
                f"choke_at_m {self.choke_at_m:g} m is not on the shield's "
                f"{drop:g} m drop to the ground"
            )
        z0 = self.h_feed - self.choke_at_m
        knee = (0.0, 0.0, self.shield_h_m)
        end = (0.0, self.line_len_m - drop, self.shield_h_m)
        shield = []
        if self.choke_at_m > 0:
            shield.append(Wire((0.0, 0.0, self.h_feed), (0.0, 0.0, z0), spec=SHIELD))
        shield += [
            Wire(
                (0.0, 0.0, z0),
                (0.0, 0.0, z0 - eps),
                # A named wire is a port edge; without a choke it is plain shield.
                name="choke" if self.choke == "ferrite" else None,
                spec=SHIELD,
            ),
            Wire((0.0, 0.0, z0 - eps), knee, spec=SHIELD),
            Wire(knee, end, spec=SHIELD),
        ]
        return wires + shield

    def build_network(self):
        lower, upper = section_uH(self.taps, self.al_nH)
        ports = {
            "ant": PortOnWire("ant"),
            "pri": PortVirtual("pri"),  # the tap: the rig side of the box
            "rig": PortVirtual("rig"),
        }
        branches = [
            Instance(
                "box",
                autotransformer(
                    lower, upper, k=self.k, ql=self.ql if self.ql > 0 else None
                ),
                tap="pri",
                top="ant",
            ),
            TL.from_cable(
                cable_from_catalog(self.cable), "rig", "pri", self.line_len_m
            ),
        ]
        if self.comp_c_pF > 0:
            branches.insert(1, Shunt("pri", c=self.comp_c_pF * 1e-12))
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
