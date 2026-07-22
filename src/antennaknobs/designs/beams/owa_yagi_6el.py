"""6-element OWA Yagi — Cebik's 2 m band-flat beam, wavelength-scaled
(issue #497's first VHF-native design).

Same NW3Z/WA3FET Optimized Wideband Antenna concept as the 4-element
`beams.owa_yagi`, in the longer-boom form Cebik published for VHF: a
reflector, driver, the OWA **coupled resonator** D1 parked ~0.052 λ off
the driver (vs ~0.14 λ to D2), and three more directors on a ~0.67 λ
boom. D1 buys almost no gain — it flattens the driving-point impedance
at 50 Ω across the whole band, so the feed is direct coax.

Source geometry: Cebik's `144-6elOWAYagi` model (ARRL VHF/UHF
collection) — 6 elements of 3/16" aluminum tube at 146 MHz — held here
as fractions of the design wavelength so `design_freq` retunes the
whole beam (the 2m/70cm band tabs, issue #497). The tube radius is a
wavelength fraction too (0.00116 λ — within 4 % of the 10 m OWA's 1"
tube fraction: Cebik scaled his tubing with the band), because the
OWA's bandwidth *depends* on fat elements.

What the model reproduces at the stock 2 m setting (free space,
momwire bs2, matching the deck solved directly): **SWR(50) ≤ ~1.2 over
all of 144–148 MHz** while gain holds ~10.1–10.2 dBi and F/B runs
21–36 dB. As with the 4-el: drag `d1_length_factor` off unity and the
whole-band match collapses while the pattern barely moves — the
matching network is that one element.

Geometry (x, y, z): elements parallel to y, boom along +x (the firing
axis), constant height `base`. The beam fires +x, toward the directors —
the workbench's forward direction, same as `beams.owa_yagi`.
"""

from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import WireSpec


class Builder(AntennaBuilder):
    # Cebik's 144-6elOWAYagi, metres -> fractions of the 146 MHz
    # wavelength: (element half-length, boom position).
    TABLE = (
        (0.250614, 0.0),  # reflector
        (0.247163, 0.125307),  # driver
        (0.231169, 0.177162),  # D1 -- the coupled resonator (0.052 wl gap)
        (0.224575, 0.320702),  # D2
        (0.224575, 0.461174),  # D3
        (0.216226, 0.670671),  # D4
    )
    DRIVER = 1
    D1 = 2

    default_params = MappingProxyType(
        {
            "design_freq": 146.0,
            "freq": 146.0,
            "base": 10.0,
            # Overall element-length scale; unity IS the published design
            # (unlike the 10 m 4-el, no re-centering was needed — the
            # native mesh reproduces the deck's window as-is).
            "length_factor": 1.0,
            # Scale on D1 alone -- the OWA-mechanism knob.
            "d1_length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    # Single-band beam: snap the GUI sweep to the band.
                    "sweep_policy": {"band_locked": True},
                    "default_view": "xy",
                    "length_factor": {"min": 0.95, "max": 1.05},
                    "d1_length_factor": {"min": 0.9, "max": 1.1},
                }
            ),
        }
    )

    # 70 cm: the same fractions at design_freq 435 -- a ~46 cm-boom beam
    # with ~1.6 mm-diameter elements (the wavelength-fraction tube shrinks
    # with the band; Cebik's own 432 MHz OWAs use disproportionately fatter
    # tube and their own tweaked lengths, so this is the *scaled* design,
    # not his 432 deck).
    band70cm_params = MappingProxyType({"design_freq": 435.0, "freq": 435.0})

    def build_wire_material(self):
        # 3/16" aluminum tube at 146 MHz, held as a wavelength fraction
        # (0.0023813 m / lambda) so the fat-element behaviour survives
        # rescaling; aluminum conductivity per the source deck's LD 5.
        wavelength = 299.792458 / self.design_freq
        return WireSpec(radius=0.0011597 * wavelength, conductivity=2.5e7)

    def build_wires(self):
        wavelength = 299.792458 / self.design_freq
        eps = 0.025 * wavelength / 2.053373  # feed-gap half-width, scaled
        quarter = 0.25 * wavelength
        b = self.base

        tups = []
        for i, (half_frac, pos_frac) in enumerate(self.TABLE):
            half = half_frac * wavelength * self.length_factor
            if i == self.D1:
                half *= self.d1_length_factor
            x = pos_frac * wavelength
            if i == self.DRIVER:
                # Driver: one-segment centre gap carries the direct feed.
                arm = self.segs_for(half - eps, quarter)
                tups.append(((x, -half, b), (x, -eps, b), arm, None))
                tups.append(
                    ((x, -eps, b), (x, eps, b), self.segs_for(2 * eps, quarter), 1 + 0j)
                )
                tups.append(((x, eps, b), (x, half, b), arm, None))
            else:
                ns = self.segs_for(2 * half, quarter)
                tups.append(((x, -half, b), (x, half, b), ns, None))
        return tups
