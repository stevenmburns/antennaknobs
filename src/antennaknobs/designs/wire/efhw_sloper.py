"""End-fed half-wave sloper with a real 49:1 unun — "the POTA antenna,
complete" (issue #329).

The classic park activation: ~10 m of thin wire hoisted to a mast apex,
sloping down to a feed point near the ground, fed through a step-down
transformer and a short run of coax. This design composes every station
piece the modelling arcs built — `Transformer` with core loss (#301),
lossy line (#297), lossy wire (#316–#318) — and the power budget (#299)
answers the end-fed question honestly: *where do the watts go in a 49:1?*

Physics worth knowing before turning the knobs:

* **The end of a half wave is a voltage antinode.** The feed impedance
  there is a few kΩ — which is why the unun exists. `unun_ratio` picks
  the classic step-downs: 49:1 (7:1 turns, ~2450 Ω → 50 Ω), 64:1 (8:1,
  ~3200 Ω), 225:4 (7.5:1, ~2812 Ω). The feed sits near the half-wave
  ANTI-resonance, historically a numerically nasty spot — the wire loss
  modelled since v0.23 damps that singularity, which is also physically
  why a real EFHW is more forgiving than an ideal-wire model suggests.
* **The unun is not free.** Its magnetizing branch (`lmag_uH` shunting
  the 50 Ω side, with core-loss Q `qlmag`) burns a visible slice of the
  power budget — the (mag) row. Real FT240-43-class 49:1s measure
  85–90 % efficient; the defaults land in that range. The ~`comp_c_pF`
  across the primary is the compensation capacitor every published
  build hangs there — it tames the transformer's HF rolloff.
* **The counterpoise is a knob, not a footnote.** `cp_len_m` defaults to
  ~0.05 λ (the classic minimal counterpoise); the coax shield past the
  unun plays this role in many field setups. Shrink it and watch the
  feedpoint conditioning and SWR drift.
* **The wire is a knob** (`wire_type`, the `WIRES` catalog): 28 AWG PVC
  is the POTA classic here, and the high-current half-wave middle makes
  gauge loss matter more than on a centre-fed dipole — the *wire loss
  (I²R)* budget row and the weight readout quantify the tradeoff.

The default `length_factor` is tuned so the stock 28 AWG PVC wire
presents its best rig-side match near 14.1 MHz at the default slope over
average ground; bare or thicker wire tunes higher — retune with the
length knob (the insulated-wire velocity factor, same story as
`dipoles.pota_invvee`).

Geometry is a `Drone` flight in the x–z plane: fly the counterpoise
horizontally (along −x) to the feed point at (0, 0, `h_feed`), pitch up
by `slope_deg`, lay the short named "ant" gap wire (ports live in wire
interiors — the feed needs its own short wire), then the radiator to the
apex, climbing toward −x. The slope is a *rise angle*, not an apex
height, so every knob combination is a valid sloper — the apex simply
lands at h_feed + length·sin(slope_deg) (≈10 m at the defaults, a
typical mast). A sloper fires mostly downhill, off the low feed end —
the radiator climbs toward −x precisely so the main lobe lands on **+x**
(the workbench's forward direction).

    apex (derived)
        /
       /  radiator ≈ λ/2 · length_factor   (wire_type from WIRES)
      /   slope_deg above horizontal
     F=========            z = h_feed        main lobe → +x
     counterpoise (+x)   F = "ant" port → unun (49:1) → coax → rig
"""

from types import MappingProxyType

from ... import AntennaBuilder, Drone
from ...network import (
    CABLES,
    Driven,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
    TL,
    Transformer,
    WIRES,
)

# unun_ratio dropdown → transformer turns ratio (feed side : rig side).
# Impedance steps down by turns²: 49:1, 64:1, 225:4 (= 56.25:1).
UNUN_TURNS = {
    "49:1": 7.0,
    "64:1": 8.0,
    "225:4": 7.5,
}


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # 20 m: the bread-and-butter POTA band (multiband harmonic
            # operation — the EFHW's whole point — is a follow-up variant).
            "design_freq": 14.1,
            "freq": 14.1,
            # Rise angle of the radiator above horizontal. 63° puts the
            # apex of the stock ~9.5 m radiator at ≈10 m — a typical mast —
            # and any angle is geometrically valid (unlike the original
            # apex-height parameterization, which went inconsistent when
            # the rise exceeded the wire length).
            "slope_deg": 63.0,
            "h_feed": 1.5,
            # Tuned for the DEFAULT wire below (28 AWG PVC) to put the
            # rig-side SWR minimum near 14.1 MHz at the default slope
            # over average ground.
            "length_factor": 0.8965,
            "wire_type": "28-awg-pvc",
            # ~0.05 λ on 20 m — the classic minimal counterpoise.
            "cp_len_m": 1.05,
            "unun_ratio": "49:1",
            # Magnetizing inductance shunting the unun's 50 Ω side and its
            # core-loss Q: ~3 primary turns on an FT240-43-class core.
            "lmag_uH": 8.0,
            "qlmag": 10.0,
            # Compensation capacitor across the primary.
            "comp_c_pF": 100.0,
            "cable": "RG-58",
            "line_len_m": 5.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "xz",
                    "length_factor": {"min": 0.85, "max": 1.10},
                    "slope_deg": {"min": 10.0, "max": 85.0},
                    "h_feed": {"min": 0.2, "max": 4.0, "unit": "m"},
                    "cp_len_m": {"min": 0.3, "max": 6.0, "unit": "m"},
                    "wire_type": {"enum_options": tuple(sorted(WIRES))},
                    "unun_ratio": {"enum_options": tuple(UNUN_TURNS)},
                    "lmag_uH": {"min": 1.0, "max": 50.0},
                    "qlmag": {"min": 0.0, "max": 200.0},
                    "comp_c_pF": {"min": 0.0, "max": 330.0, "unit": "pF"},
                    "cable": {"enum_options": tuple(sorted(CABLES))},
                    "line_len_m": {"min": 1.0, "max": 30.0, "unit": "m"},
                    # The high-Z feed swings the rig-side trace around the
                    # Smith chart fast off-resonance — lock the sweep to
                    # the band being measured.
                    "sweep_policy": {"anchor": "meas_freq", "band_locked": True},
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength
        length = 0.5 * wavelength * self.length_factor

        # Fly it: face −x so the radiator climbs toward −x and the sloper's
        # downhill main lobe lands on +x; counterpoise in to the feed
        # point, pitch up by the rise angle (Drone pitch is nose-down
        # positive), gap wire, radiator.
        d = Drone(
            (self.cp_len_m, 0.0, self.h_feed),
            nominal_nsegs=self.nominal_nsegs,
            ref=quarter,
        )
        d.face((-1.0, 0.0, 0.0))
        d.pay_out().forward(self.cp_len_m)
        d.pitch(-self.slope_deg)
        d.forward(eps, nsegs=1)
        d.forward(length - eps)
        wires = d.wires()
        # The short gap edge becomes the named "ant" port wire: the port
        # interrupts the current path between counterpoise and radiator —
        # the end-fed's feed.
        p0, p1, nsegs, _ev = wires[1]
        wires[1] = (p0, p1, nsegs, None, "ant")
        return wires

    def build_network(self):
        turns = UNUN_TURNS[self.unun_ratio]
        branches = [
            # Step-down unun: rig side "pri" sees Z_feed / turns².
            Transformer(
                a="pri",
                b="ant",
                n=1.0 / turns,
                lmag=self.lmag_uH * 1e-6,
                qlmag=self.qlmag if self.qlmag > 0 else None,
            ),
        ]
        if self.comp_c_pF > 0:
            branches.append(Shunt(port="pri", c=self.comp_c_pF * 1e-12))
        branches.append(TL.from_cable(self.cable, "rig", "pri", self.line_len_m))
        return Network(
            ports={
                "ant": PortOnWire("ant"),
                "pri": PortVirtual("pri"),
                "rig": PortVirtual("rig"),
            },
            branches=branches,
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
