"""Beverage receiving antenna with a ground rod at each end (AK#1707).

The low, long, terminated wire H. H. Beverage built for transatlantic
reception in the early 1920s (Beverage, Rice and Kellogg, "The Wave Antenna",
Trans. AIEE, 1923), and still the 160 m and 80 m DXer's receiving antenna of
record (J. Devoldere ON4UN, *Low-Band DXing*; W8JI's Beverage pages). A
vertically polarised wave arriving over lossy ground has its wavefront
TILTED forward, so it carries a horizontal electric field along the wire.
A signal arriving from the terminated end induces current that travels
toward the receiver in step with the wave and builds up; one arriving from
the feed end travels toward the far end and is absorbed in the terminating
resistor. **The beam points toward the terminated end** — +x here.

It is the cousin of `terminated_longwire`, which is the same terminated
traveling wave, but ~1 wl up and for transmitting, with its legs touching a
PEC plane. Here the wire is 2.5 m up, the ground is lossy by necessity (over
PEC there is no wave tilt, the image cancels the wire, and the pattern is
gone), and each end is a vertical down-lead to a GROUND ROD: a real conductor
driven into the soil, crossing z = 0. The rods and the soil are part of the
antenna; the `contact` variant replaces them with a perfect connection to the
interface, for comparison.

Geometry, (x, y, z), planar in y = 0:

      +-----------------------------------------+   z = height_m (2.5 m)
      |                                         |
      F  feed, 9:1 to the rig      term_r  ->   T   beam --> +x
    ==|=========================================|==  z = 0, soil below
      |  rod                                rod |
      |  rod_depth                              |

  * run: `length_frac` wl at the design frequency, #14 bare copper. The
    default 1.5 wl at 1.83 MHz is 245.8 m.
  * feed end (x = 0): the feed edge (0.25 m, named "feed") stands on the rod
    at z = 0, and the down-lead rises from it to the run. The source is a
    `Transformer` (impedance ratio `xfmr_ratio`, 9:1 by default) from a
    virtual rig port — the usual Beverage matching transformer.
  * far end (x = L): the down-lead comes down to the termination edge
    ("term", a `term_r` resistor), which stands on the second rod.
  * rods: vertical, `rod_depth` into the soil (1.8 m default; the knob runs
    0.6-3 m, and an 8 ft rod driven full length is 2.4 m).

TERMINATION. The run's characteristic impedance over ground is the textbook
Z0 = 138 log10(4h/d) = 523 ohm for #14 at 2.5 m; `term_r` defaults to
500 ohm. The `contact` variant confirms it: with a perfect connection at
each end the feed reads 532.2 - 0.3j ohm (momwire razor-2p over average
soil), a matched line.

THE RODS ARE NOT A PERFECT GROUND, and that is the point of modelling them.
They put the soil's resistance in series with both the feed and the
termination: the feed moves from 532.2 - 0.3j (contact) to 677.0 - 97.6j
ohm (rods), the terminator's share of the input power falls from 51.7 % to
32.9 %, and F/B from 20.4 to 19.1 dB (all razor-2p, average soil).

MODELLED NUMBERS, at the defaults (1.5 wl, 2.5 m, 500 ohm, 9:1, 1.8 m rods
at the wire's own radius), 1.83 MHz. Soils are the app's presets (ARRL
Table 3.1): average eps_r 13 / sigma 0.005, poor eps_r 13 / sigma 0.002.
"Feed" is the antenna side of the transformer; RDF is `far_field.rdf_db`
(full-sphere average gain; see there); "term" is the terminator's share of
the input power (momwire's power budget; NEC-5 has no such row here):

                     feed Z (ohm)    peak dBi takeoff F/B dB RDF dB  term
  razor-2p, average  677.0 -  97.6j   -9.10    29.1   19.1   11.95  32.9 %
  NEC-5,    average  677.0 -  97.6j   -9.10    29     19.2   11.95
  razor-2p, poor     750.9 - 269.8j   -8.14    29.7   19.5   12.22  18.4 %
  NEC-5,    poor     751.0 - 270.0j   -8.14    30     19.3   12.22
  razor-2p, average, contact variant
                     532.2 -   0.3j   -8.26    28.4   20.4   12.09  51.7 %
  razor-2p, average, termination removed
                     540.2 - 619.8j   -7.15    34.6    3.1    9.92

ROD DEPTH is worth its knob (razor-2p, average): 1.2 m reads 732.4 - 143.3j
ohm, F/B 17.9 dB and 27.7 % in the terminator; 2.4 m reads 649.1 - 70.5j,
19.5 dB and 36.2 %. Deeper rods are a better ground, and the antenna moves
toward the contact variant.

NEC-5 is the licensed binary (`--engine nec5`) at the same mesh; its F/B
and takeoff come off the 1-degree grid, momwire's off the refined peak
(#1669), so those two can differ by a few tenths. On the impedance the two
engines agree to 0.02 ohm on the rig side (NEC-5 reads 75.222 - 10.849j
against razor-2p's 75.221 - 10.841j over average soil). Doubling the mesh
(`nominal_nsegs` 42) moves the rig-side impedance 0.22 ohm (0.3 %) on both.

The absolute gain is -8 to -9 dBi and that is not a defect: a Beverage
radiates well under 1 % of what it is given (average gain -21 dB here). On
receive it is judged by RDF, not gain, because gain and average gain carry
the same loss.

ENGINES, as measured today:

  * momwire razor-2p SERVES the rod design over both soils. Its buried
    pre-flight passes to 3 wl at the default mesh, and to 1.5 wl at twice
    the mesh; past that the rod tops' pair meets the grazing floor below.
  * momwire B-spline and sinusoidal-Galerkin REFUSE it by name. Two crossing
    nodes are served (plan U9), but the pair of rod tops — ~246 m apart,
    with those lanes' quadrature points within a centimetre of the
    interface — is under the 1-arc-minute grazing floor their below/below
    tables start at. razor-2p's remainder points sit deeper and clear it.
  * NEC-5 (licensed, local) serves it and agrees, above.
  * PyNEC and NEC-2 are REFUSED by name in the app: neither has a medium
    below the ground, and both solve a buried wire as if it were in air.

The `contact` variant is the comparison case for the NEC-2 family (AK#1707's
decision). momwire (B-spline and razor-2p) and NEC-5 agree on it to 0.4 ohm
on the rig side (3.4 ohm at the feed, over average soil). PyNEC solves it
too, but it is a poor reference: NEC-2 joins a wire ending on a Sommerfeld
ground to a perfectly conducting point, which is outside its formulation,
and it reads 978.7 - 358.8j ohm at the feed where the other three read
~532.

MODELLING CONVENTIONS, and why:

  * ONE WIRE RADIUS, so the rods are #14 too by default. momwire refuses a
    crossing deck with two radii AND more than one crossing node (plans U5 and
    U9 were each measured alone). A thin rod reads more ground resistance
    than a real 16 mm one: NEC-5 with `rod_radius_m=0.008` reads 637.0 -
    72.9j ohm (average) against 677.0 - 97.6j, with F/B 19.0 against 19.2 dB
    and RDF 11.98 against 11.95 dB; over poor soil 687.8 - 202.6j against
    751.0 - 270.0j. `rod_radius_m` is there for NEC-5 comparisons; momwire
    refuses it by name.
  * THE RODS ARE MESHED AT THE DESIGN DENSITY, not graded into the node the
    way `buried_radial_vertical` grades its rise. A graded rod puts
    quadrature points a fraction of a millimetre below the interface, and
    with two rods a Beverage's length apart that pair is under the grazing
    floor on every momwire lane, razor-2p included. The in-medium density
    comes from `design_eps_r` / `design_sigma` (average soil) and never
    tracks the solve's ground, so a soil sweep never remeshes.
  * Every segment is horizontal or vertical, and each crossing node has one
    wire above it (the feed or termination edge): the crossing serve's
    measured shape.

REQUIRES A FINITE (Sommerfeld) GROUND: `--ground finite:13,0.005`. The web
app selects it on load. A razor-2p solve at the defaults peaks at ~350 MB;
the first one in a process takes 1-2.5 minutes, most of it building the
below-ground tables, and re-solves in the same process take 5-10 s.
"""

from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import (
    COPPER_CONDUCTIVITY,
    Driven,
    Load,
    Network,
    PortOnWire,
    PortVirtual,
    Transformer,
    Wire,
    WireSpec,
)

# #14 AWG bare copper: 1.628 mm diameter, 18.5 g/m.
AWG14 = WireSpec(radius=0.814e-3, conductivity=COPPER_CONDUCTIVITY, weight_g_per_m=18.5)

# Length of the feed and termination edges at the bottom of each down-lead.
EDGE_M = 0.25


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # 160 m. The traveling-wave pattern holds across 80 m too (the run
            # is then ~3 wl); the default mesh is sized for 1.83 MHz.
            "freq": 1.83,
            "design_freq": 1.83,
            # NOMINAL SOIL for the mesh only (average): the rods are meshed
            # per in-medium quarter-wave off these (issue #983). The solve's
            # soil comes from the ground panel / `--ground` and may differ;
            # the mesh deliberately does not track it.
            "design_eps_r": 13.0,
            "design_sigma": 0.005,
            # Run length in wavelengths at the design frequency (1.5 wl =
            # 245.8 m at 1.83 MHz). razor-2p serves to 3 wl at this mesh.
            "length_frac": 1.5,
            # Height of the run, metres.
            "height_m": 2.5,
            # Terminating resistor, ohm: near Z0 = 138 log10(4h/d) = 523.
            "term_r": 500.0,
            # Impedance ratio of the feed transformer (9:1 into 50 ohm).
            "xfmr_ratio": 9.0,
            # Rod length into the soil, metres.
            "rod_depth": 1.8,
            # Rod radius, metres. None = the wire's own radius, the only
            # value momwire serves (see the module docstring); a real 16 mm
            # rod is 0.008, for NEC-5.
            "rod_radius_m": None,
            # Rods (True) or a contact on the plane (the `contact` variant).
            "rods": True,
            "ui_params": MappingProxyType(
                {
                    # The rods exist only under a Sommerfeld half-space: the
                    # app selects finite ground + Sommerfeld on load.
                    "ground_requirement": "sommerfeld",
                    # Planar in y = 0: x-z shows the run, the leads and rods.
                    "default_view": "xz",
                    "target_z0": 50.0,
                    "length_frac": {
                        "min": 1.0,
                        "max": 2.0,
                        "step": 0.05,
                        "label": "length (wl)",
                    },
                    "height_m": {"min": 1.0, "max": 4.0, "unit": "m"},
                    "term_r": {"min": 300.0, "max": 900.0, "step": 10.0},
                    "xfmr_ratio": {
                        "min": 1.0,
                        "max": 16.0,
                        "step": 0.5,
                        "label": "transformer Z ratio",
                    },
                    "rod_depth": {"min": 0.6, "max": 3.0, "unit": "m"},
                    # Chosen by the variant picker, not a checkbox.
                    "rods": {"hidden": True},
                }
            ),
        }
    )

    # The comparison case (AK#1707): the same down-leads stop ON the plane,
    # a perfect connection to the interface, the way `terminated_longwire`
    # grounds its legs. No wire is buried, so the NEC-2 family can be asked.
    contact_params = MappingProxyType({"rods": False})

    def build_wire_material(self):
        return AWG14

    def build_wires(self):
        L = self.length_frac * self.design_wavelength
        h = self.height_m
        # Every wire meshes at the design density (the catalog's #521/#522
        # rule, `test_delta_a_lint`), the rods at their in-medium one.
        above = [
            Wire((0.0, 0.0, 0.0), (0.0, 0.0, EDGE_M), name="feed"),
            Wire((0.0, 0.0, EDGE_M), (0.0, 0.0, h)),
            Wire((0.0, 0.0, h), (L, 0.0, h)),
            Wire((L, 0.0, h), (L, 0.0, EDGE_M)),
            Wire((L, 0.0, EDGE_M), (L, 0.0, 0.0), name="term"),
        ]
        if not self.rods:
            return above
        d = self.rod_depth
        rod_spec = None
        if self.rod_radius_m:
            rod_spec = WireSpec(
                radius=self.rod_radius_m, conductivity=COPPER_CONDUCTIVITY
            )
        # Auto-meshed at the in-medium density, NOT graded: see "THE RODS
        # ARE MESHED AT THE DESIGN DENSITY" in the module docstring.
        return [
            Wire((0.0, 0.0, -d), (0.0, 0.0, 0.0), spec=rod_spec),
            *above,
            Wire((L, 0.0, 0.0), (L, 0.0, -d), spec=rod_spec),
        ]

    def build_network(self):
        return Network(
            ports={
                "feed": PortOnWire("feed"),
                "term": PortOnWire("term"),
                "rig": PortVirtual("rig"),
            },
            branches=[
                Load(port="term", r=self.term_r),
                # n is the rig:feed VOLTAGE ratio, so the rig sees
                # Z_feed / xfmr_ratio.
                Transformer(a="rig", b="feed", n=(1.0 / self.xfmr_ratio) ** 0.5),
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
