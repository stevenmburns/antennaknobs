"""Expanded Lazy-H: two stacked EDZs fed through a real phasing harness
(L. B. Cebik, W4RNL).

Cebik's favourite "big cheap wire gain" antenna, from "The Expanded Lazy-H":
take the standard lazy-H and stretch BOTH knobs -- elements from 1 wl to
1.25 wl (the EDZ length, see `wire.edz`) and the stack from 1/2 wl to 5/8 wl.
On 10 m that is two 44' wires 22' apart. The wider in-phase stack pulls the
EDZ pair's high-angle energy into one dominant low broadside lobe: this model
reads ~10.1 dBi free space vs ~8.1 dBi for the catalog's standard `lazy_h`
(Cebik's famous 15.1 dBi at 8 deg takeoff adds the height-over-ground gain).
Fed through open-wire line and a wide-range tuner it stays useful far below
the design band -- full performance 10-17 m, pressable to 40 -- with the
stacking gain fading as the fixed 22' stack shrinks in wavelengths
(~7.2 dBi at 21.1 MHz, ~4.1 dBi at 14.1 MHz free space here).

Where the catalog's `lazy_h` IMPOSES equal in-phase drive as two ideal
centre sources, this design models Cebik's actual feed: equal legs of
open-wire line from both element centres to a junction at mid-stack height,
as ideal `TL` branches, driven at the junction (the sister-design move of
`sterba` vs `sterba_tl`). By symmetry the two legs still deliver identical
in-phase drive, but the driving-point the tuner actually sees is the
junction: the two transformed element impedances in parallel, low-R and
strongly reactive -- honest ladder-line-plus-tuner territory, not a coax
match (target_z0 300, like `lazy_h`).

Geometry, in the framework's (x, y, z) convention:
  - y : the long axis (both 1.25 wl wires run along y)
  - z : height; lower wire at `base`, upper at `base + spacing`
  - x : firing axis; radiation is broadside off +/- x
The structure is planar in x = 0; the harness is electrical (TL branches).

    ===================C===================   z = base + spacing  (1.25 wl)
                       |
                       J  <- junction feed (virtual port, mid-stack)
                       |
    ===================C===================   z = base            (1.25 wl)
              (C = named centre ports; equal TL legs C-J)
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL, Wire
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the lower element above ground.
            "base": 10.0,
            # Element length as a fraction of a wavelength: 1.25 wl is the
            # EDZ stretch (the standard lazy-H uses 1.0).
            "elem_frac": 1.25,
            # Vertical stacking distance as a fraction of a wavelength:
            # 5/8 wl is the expansion (the standard lazy-H uses 1/2).
            "spacing_frac": 0.625,
            # Characteristic impedance of the two harness legs (open-wire
            # phasing line; Cebik discusses 300-600 ohm builds).
            "z0_harness": 450.0,
            "ui_params": MappingProxyType(
                {
                    # Reactive junction fed via open-wire line + tuner.
                    "target_z0": 300.0,
                    "default_view": "yz",
                    "elem_frac": {
                        "min": 0.8,
                        "max": 1.4,
                    },
                    "spacing_frac": {
                        "min": 0.3,
                        "max": 0.75,
                    },
                    "z0_harness": {
                        "min": 300.0,
                        "max": 600.0,
                        "step": 1.0,
                        "precision": 1,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05

        wavelength = 299.792458 / self.design_freq

        elem = self.elem_frac * wavelength
        spacing = self.spacing_frac * wavelength
        half = elem / 2

        def element(z, name):
            """A 1.25 wl horizontal wire along y at height z with a named
            centre port (the harness attaches here; no direct voltage
            source)."""
            L = (0.0, -half, z)
            R = (0.0, half, z)
            C0 = (0.0, -eps, z)
            C1 = (0.0, eps, z)
            return [
                Wire(L, C0),
                Wire(C0, C1, name=name),
                Wire(C1, R),
            ]

        tups = []
        tups.extend(element(self.base, "lo"))  # lower element
        tups.extend(element(self.base + spacing, "hi"))  # upper element
        return tups

    def build_network(self):
        wavelength = 299.792458 / self.design_freq
        # Equal legs from each element centre to the mid-stack junction --
        # equal length is what makes the drive in-phase.
        leg = 0.5 * self.spacing_frac * wavelength
        return Network(
            ports={
                "lo": PortOnWire("lo"),
                "hi": PortOnWire("hi"),
                "junction": PortVirtual("junction"),
            },
            branches=[
                TL(a="junction", b="lo", z0=self.z0_harness, length=leg),
                TL(a="junction", b="hi", z0=self.z0_harness, length=leg),
            ],
            sources=[Driven(port="junction", voltage=1 + 0j)],
        )
