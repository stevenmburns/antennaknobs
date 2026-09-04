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

from antennaknobs import AntennaBuilder, Drone
from antennaknobs.network import (
    CABLES,
    Driven,
    Instance,
    Network,
    PortOnWire,
    PortVirtual,
    TL,
    Wire,
    WIRES,
    as_wire,
    cable_from_catalog,
)
from antennaknobs.station import unun

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
            #
            # THIS VALUE IS NOT LOAD-BEARING IN THIS MODEL at the design
            # frequency. Every value from 0 to 100 pF clears the < 1.3 gate
            # at stock length, in both ground models. Fit what is in the
            # drawer, or fit nothing:
            #
            #     C pF        finite-fast              Sommerfeld
            #      0 (none)   44.22 - 5.43j  1.184     45.15 - 6.36j  1.183
            #     37.6 (-20%) 50.88 - 3.97j  1.084     51.81 - 5.17j  1.114
            #     47   (E6)   52.72 - 3.72j  1.094     53.65 - 4.99j  1.127
            #     56.4 (+20%) 54.64 - 3.52j  1.118     55.55 - 4.87j  1.150
            #     60          55.40 - 3.46j  1.129     56.30 - 4.84j  1.161
            #
            # WHY IT IS NOT LOAD-BEARING, and what that does NOT say. The
            # model's unun is an ideal Transformer plus a magnetizing shunt
            # (lmag/qlmag) plus this capacitor — there is NO LEAKAGE
            # INDUCTANCE term anywhere in it (see `station.unun` and
            # momwire's `Transformer`, whose own docstring calls its loss
            # model "deliberately minimal"). A physical FT240-43 49:1 carries
            # ~100 pF to compensate leakage across the bands, which is a
            # bench measurement on a real box. This model cannot represent
            # that, so nothing here argues against the customary 100 pF in a
            # build — it only says the number does not earn its keep at
            # 14.1 MHz in this simulation.
            #
            # 47 pF: an E6 part, in every kit, and near the bottom of the
            # SWR bowl. The bowl against C is monotone above its minimum, so
            # the earlier 60 pF sat up the rising flank:
            #
            #                        finite-fast      Sommerfeld
            #     bowl minimum        37 pF 1.084      34 pF 1.112
            #     47 pF +-20 % worst        1.118            1.150
            #
            # Near the minimum the sensitivity to C is first-order zero,
            # which is why a sloppy +-20 % E6 part is fine here and a
            # precision part buys nothing.
            #
            # EVERY FIGURE ABOVE NAMES ITS GROUND MODEL, and that is not
            # pedantry. `("finite", ...)` is true Sommerfeld; `("finite-fast",
            # ...)` is the reflection-coefficient approximation, and
            # `tests/test_efhw_sloper.py`'s GROUND constant is the FAST one
            # while this comment's numbers were originally taken in
            # Sommerfeld. At the old 60 pF that is 1.129 against 1.161 — and
            # quoting only the second, unlabelled, is what made a later
            # reader bisect eight momwire commits looking for a regression
            # that was never there.
            #
            # Antenna-side, for scale: at the `ant` port with the unun, comp
            # cap and coax removed (the multiport Y before the network), the
            # upper X = 0 crossing sits at 2676 ohm finite-fast / 2556 ohm
            # Sommerfeld, swept in frequency at stock length. An earlier
            # comment quoted 3240.8 -> 2611.7 for the pre/post-momwire#874
            # pair; the 2611.7 is not reproducible by either a frequency or a
            # length sweep in either ground model (all four land within 2.5 %
            # of it and none on it), so measured values replace it. The
            # ~19 % DROP across #874 — the coated pair lowering Zc, and with
            # it the end-fed's feed R — is the part that mattered and stands.
            "comp_c_pF": 47.0,
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
                    # Display names for the power-budget rows (issue #489).
                    # Keys are the STRUCTURAL labels the solver emits —
                    # keep in sync with build_network below (the "unun"
                    # instance and its pri/ant port bindings); unmatched
                    # rows pass through unchanged.
                    "budget_labels": {
                        "unun: Transformer pri→ant": "unun windings",
                        "unun: Transformer pri→ant (mag)": "unun core (mag)",
                        "unun: Shunt pri": "unun comp cap",
                        "TL rig→pri": "feedline",
                    },
                }
            ),
        }
    )

    # 40 m: the same POTA box — unun, comp cap, coax untouched — with twice
    # the wire. The ~19 m radiator needs a gentler rise: 30° lands the apex
    # near 11 m (a tall mast or a friendly tree limb), and the counterpoise
    # scales to ~0.05 λ. length_factor retuned for the stock 28 AWG PVC wire:
    # rig-side SWR 1.36 at 7.1 MHz. The 100 pF comp cap is a 20 m-flavored
    # compromise that caps the match here (~200 pF would buy 1.19 — turn the
    # knob if you'd rebuild the unun), and the longer thin wire burns ~10 %
    # in I²R (efficiency 84 %) — the gauge tradeoff, amplified. At ~0.26 λ
    # up the pattern is near-NVIS (takeoff ≈ 78°, essentially omni) — which
    # is exactly how 40 m POTA actually works: regional skywave, not DX.
    band40_params = MappingProxyType(
        {
            "design_freq": 7.1,
            "freq": 7.1,
            "slope_deg": 30.0,
            "length_factor": 0.8935,
            "cp_len_m": 2.1,
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = self.design_wavelength
        length = 0.5 * wavelength * self.length_factor

        # Fly it: face −x so the radiator climbs toward −x and the sloper's
        # downhill main lobe lands on +x; counterpoise in to the feed
        # point, pitch up by the rise angle (Drone pitch is nose-down
        # positive), gap wire, radiator.
        d = Drone((self.cp_len_m, 0.0, self.h_feed))
        d.face((-1.0, 0.0, 0.0))
        d.pay_out().forward(self.cp_len_m)
        d.pitch(-self.slope_deg)
        d.forward(eps)
        d.forward(length - eps)
        wires = d.wires()
        # The short gap edge becomes the named "ant" port wire: the port
        # interrupts the current path between counterpoise and radiator —
        # the end-fed's feed.
        gap = as_wire(wires[1])
        wires[1] = Wire(gap.p0, gap.p1, name="ant")
        return wires

    def build_network(self):
        return Network(
            ports={
                "ant": PortOnWire("ant"),
                "pri": PortVirtual("pri"),  # unun line-side terminals
                "rig": PortVirtual("rig"),
            },
            branches=[
                # Step-down unun: the line side "pri" sees Z_feed / turns².
                Instance(
                    "unun",
                    unun(
                        turns=UNUN_TURNS[self.unun_ratio],
                        lmag_uH=self.lmag_uH,
                        qlmag=self.qlmag if self.qlmag > 0 else None,
                        comp_c_pF=self.comp_c_pF if self.comp_c_pF > 0 else None,
                    ),
                    line="pri",
                    ant="ant",
                ),
                TL.from_cable(
                    cable_from_catalog(self.cable), "rig", "pri", self.line_len_m
                ),
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
