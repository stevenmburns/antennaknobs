"""Terminated end-fed long-wire: the directional single wire (L. B. Cebik,
W4RNL, "Long-Wire Antennas", Part 2).

Completes the catalog's traveling-wave set: `longwire` is the resonant
single wire, `vbeam` the resonant V, `rhombic` the terminated diamond --
this is the TERMINATED SINGLE WIRE the other three are built from. A
horizontal wire several wavelengths long (Cebik models 3-11 wl; 10 wl here)
at ~1 wl height, fed at the near end between a vertical leg and GROUND, with
the far end brought down a matching leg and terminated to ground through a
non-inductive resistor. The resistor absorbs the forward wave, so the
current is progressive rather than standing and the pattern collapses to
ONE main lobe, low and off the terminated end.

Cebik's working termination is ~800 ohm (RL = 138*log10(4h/d) gives ~680 for
his test wire; 600-1000 all work), and his headline numbers for the 10 wl
model over average ground: 10.47 dBi at 11 deg takeoff, F/B 20.3 dB, feed
544 +j87 -> SWR(600) 1.20 nearly flat across bands ("extreme
frequency-changing agility"). Two corrections to the folklore he stresses,
both pinned by the tests: the terminator burns ~25% of the power, NOT 50%
(this model reads ~29%), and termination costs ~3.5 dB against the same wire
unterminated -- the price of the clean unidirectional pattern.

This is the catalog's first ground-CONNECTED design: both legs end at
exactly z=0 and the PyNEC engine joins them to the ground image (the GE-flag
support added alongside this design). Solve it OVER GROUND -- free space
leaves the legs dangling and the circuit open. NEC-2 restriction worth
knowing: ground contact is only physical over PEC ground ("pec"); the
Sommerfeld/reflection-coefficient finite grounds do not support touching
wires (a NEC-4 feature), so quantitative work stays on PEC and Cebik's
average-ground figures are the field-expectation reference.

Geometry, in the framework's (x, y, z) convention:
  - x : the wire axis; feed leg at x=0, terminated leg at x=L; beam --> +x
  - z : legs run from ground (z=0) to `height_frac` wl; wire horizontal
  - y : 0 everywhere (the structure is planar in y=0)
Horizontally polarised off the long run, with the legs' vertical
contribution shaping the low-angle response.

    F================================T   z = h (~1 wl, ~10 wl long)
    |                                |
    G  --> beam toward +x            R   R = term_r to ground
   ---------------------------------------  z = 0 (ground plane)
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Load, Network, PortOnWire, Wire
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Horizontal run length in wavelengths. Cebik's tables run 3-11;
            # 10 wl is his primary test case. Longer = more gain, narrower
            # main lobe.
            "length_frac": 10.0,
            # Height of the horizontal run in wavelengths (Cebik: 1 wl).
            "height_frac": 1.0,
            # Terminating resistance (ohm) at the bottom of the far leg.
            # Cebik's working value; RL = 138*log10(4h/d) ~ 680 for his
            # wire, anything 600-1000 is usable.
            "term_r": 800.0,
            "ui_params": MappingProxyType(
                {
                    # The feed tracks the termination: ~600 ohm open-wire
                    # territory (Cebik: 544 +j87, SWR(600) 1.20).
                    "target_z0": 600.0,
                    # Planar in y=0: the xz view shows the run and both legs.
                    "default_view": "xz",
                    "length_frac": {
                        "min": 3.0,
                        "max": 11.0,
                        "step": 0.5,
                        "precision": 2,
                    },
                    "height_frac": {
                        "min": 0.5,
                        "max": 1.5,
                    },
                    "term_r": {"min": 400.0, "max": 1000.0, "step": 10.0},
                }
            ),
        }
    )

    def build_wires(self):
        wavelength = 299.792458 / self.design_freq

        L = self.length_frac * wavelength
        h = self.height_frac * wavelength
        pe = 0.3  # feed / termination edge length at the leg bottoms, m

        G0 = (0.0, 0.0, 0.0)  # feed-leg ground end
        F1 = (0.0, 0.0, pe)
        A = (0.0, 0.0, h)  # near top corner
        B = (L, 0.0, h)  # far top corner
        T1 = (L, 0.0, pe)
        GT = (L, 0.0, 0.0)  # terminated-leg ground end

        # Every wire — the feed/termination edges included — meshes at the
        # design density (#525 stage 4, closing #526's chief case). The
        # edges were long pinned at one segment on evidence that refining
        # them turned a flat ladder into a 20 %+ drift; re-probing on the
        # modern port machinery (MNA network + PortOnWire keeping the
        # source/load on the wire's middle segment as it refines) shows
        # the opposite: with density-meshed edges bs2 and sin converge to
        # the *same* value (mutual limit 436−44j at N=161 on the 3 λ
        # variant) where the pinned model left the bases ~2.4 % apart
        # forever, and the Cebik anchors (terminator dissipation, SWR(600),
        # gain/F-B) are unchanged at the default mesh. The old drift was
        # an artifact of the pre-MNA port readout, not physics.
        return [
            # Near leg: driven edge at the ground end, then up to the run.
            Wire(G0, F1, name="feed"),
            Wire(F1, A),
            # The long horizontal run.
            Wire(A, B),
            # Far leg down to the termination edge at the ground end.
            Wire(B, T1),
            Wire(T1, GT, name="term"),
        ]

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed"), "term": PortOnWire("term")},
            branches=[Load(port="term", r=self.term_r)],
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )
