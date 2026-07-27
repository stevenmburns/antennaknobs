"""1x2 stacked bowtie array with a balanced-line corporate feed.

A worked example of feeding a phased array through `BalancedLine` rather than
the framework's per-element delta-gap phasing (`Array2x2Builder`). Two bowtie
elements are stacked half a wavelength apart and combined by a matched
balanced-line corporate feed:

    element (~100 Ω)  --100 Ω BalancedLine half-->  center tap  <--half-- element
                                                      |
                                            50 Ω coax (single-ended)

The impedance ladder is the intent: two ~100 Ω-class elements combined by
100 Ω half-lines that parallel to 50 Ω at the center tap — a 1:1 match to 50 Ω
coax (SWR ~1.01 at the design frequency), +5.9 dBi bidirectional broadside
(φ = 0/180) with deep endfire nulls. In practice the geometry is tuned so the
*tap* presents 50 Ω directly, NOT by matching each element to a transparent
100 Ω line: an element's impedance in an array is feed-dependent (the current
ratio the balanced network sets differs from an isolated or delta-gap drive),
so there is no feed-independent "100 Ω element" — the tuned element-plus-line
network as a whole realizes the 50 Ω tap. (Setting each element to exactly
100+0j under a delta-gap drive gives ~43+23j at the tap, SWR 1.7, not 50 Ω —
which is why the tune targets the tap.)

Against ideal equal-current feeding of the same geometry the balanced feed is
pattern-identical (within ~0.2 dB everywhere): it is lossless and matched, so
it faithfully delivers the broadside excitation — the corporate feed costs
nothing in gain or pattern here.

Freq-based geometry (unlike `specialty.bowtie`, whose dimensions are hand-tuned
absolute metres): every length is a wavelength factor, so the whole antenna and
its feed scale with `freq`.

Construction (issues #575/#576/#579):
  - Each bowtie is authored WITHOUT its center feed-bridge wire, so the two
    feed-gap ends are free conductor ENDS. `PortAtEnd` grabs each end (four
    junction ports total), and one `BalancedLine` per element pairs them to the
    shared center-tap nodes.
  - The center tap is a `PortVirtual` node pair. The 50 Ω coax is modelled as a
    single-ended feed there: `Driven` on one tap conductor, the other bonded to
    the common datum (the coax shield) — i.e. coax straight onto the balanced
    tap, no balun. That single-ended grounding also pins the feed network's
    common mode, so `zcomm` is not needed (the lines are pure feeders, not
    loop conductors — contrast `wire.sterba_bl`, whose risers close radiating
    loops and REQUIRE `zcomm`). `zcomm` is exposed for study but defaults off.

Engine support: **momwire only** — `PortAtEnd` resolves to a junction-node port
(momwire#172) that NEC-2 has no card for, so `PyNECEngine` rejects the design.
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import (
    BalancedLine,
    Driven,
    Network,
    PortAtEnd,
    PortVirtual,
    Shunt,
    Wire,
)


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": 28.47,
            # design_freq scales the geometry AND anchors auto_mesh; hidden.
            "design_freq": 28.47,
            # Bowtie flare half-angle and length (as a wavelength factor),
            # tuned so the center TAP presents 50 Ohm to the coax (SWR ~1.01).
            "angle_deg": 44.0,
            "length_factor": 0.560,
            # Element stacking distance / wavelength (sets the half-line length).
            "del_z_factor": 0.5,
            # Corporate-feed line impedance (matched to the element).
            "zdiff": 100.0,
            # Feeders are common-mode-open (0 -> None): the single-ended tap
            # pins the CM. Exposed for the modelling study only.
            "zcomm": 0.0,
            "ui_params": MappingProxyType(
                {
                    "design_freq": {"hidden": True},
                    "target_z0": 50.0,
                    "angle_deg": {"min": 30.0, "max": 60.0, "step": 0.5},
                    "length_factor": {"min": 0.45, "max": 0.65, "step": 0.005},
                    "del_z_factor": {"min": 0.35, "max": 0.75, "step": 0.05},
                    "zdiff": {"min": 50.0, "max": 300.0, "step": 10.0},
                    "zcomm": {"min": 0.0, "max": 400.0, "step": 25.0},
                }
            ),
        }
    )

    # ---- geometry -------------------------------------------------------
    def _element_geo(self):
        """(wavelength, half-width y, half-height z) of one bowtie."""
        wl = self.design_wavelength
        length = self.length_factor * wl
        theta = math.radians(self.angle_deg)
        half = 0.5 * length / (1.0 + math.sin(theta))
        return wl, half * math.cos(theta), half * math.sin(theta)

    def _element_wires(self, idx, zoff):
        """One bowtie at vertical offset `zoff`, feed-bridge omitted; the two
        feed-gap ends are named ``feedL{idx}`` / ``feedR{idx}`` for PortAtEnd."""
        _, y, z = self._element_geo()
        eps = 0.05  # feed-gap half-width (m)
        nameL, nameR = f"feedL{idx}", f"feedR{idx}"
        # (y, z) pairs in the element's own plane (x = 0); name only the two
        # feed-leg wires whose inner end is a feed terminal (#578: a named wire
        # must be referenced — both are, by PortAtEnd).
        specs = [
            ((-y, 0.0), (-y, z), None),
            ((-y, z), (-eps, eps), None),
            ((-eps, eps), (eps, eps), None),  # top bridge (solid)
            ((eps, eps), (y, z), None),
            ((y, z), (y, 0.0), None),
            ((-y, 0.0), (-y, -z), None),
            ((-y, -z), (-eps, -eps), nameL),  # left feed leg: end p1 = (-eps,-eps)
            ((eps, -eps), (y, -z), nameR),  # right feed leg: end p0 = (eps,-eps)
            ((y, -z), (y, 0.0), None),
        ]
        return [
            Wire((0.0, y0, z0 + zoff), (0.0, y1, z1 + zoff), name=nm)
            for ((y0, z0), (y1, z1), nm) in specs
        ]

    def build_wires(self):
        wl, _, _ = self._element_geo()
        dz = self.del_z_factor * wl
        # Two elements straddling z = 0, so the center tap sits at mid-height.
        return self._element_wires(0, -0.5 * dz) + self._element_wires(1, +0.5 * dz)

    # ---- feed network ---------------------------------------------------
    def build_network(self):
        wl, _, _ = self._element_geo()
        dz = self.del_z_factor * wl
        line_len = 0.5 * dz  # element feed -> center tap
        zc = self.zcomm or None

        ports = {"JC1": PortVirtual("JC1"), "JC2": PortVirtual("JC2")}
        branches = []
        for idx in range(2):
            pL, pR = f"eL{idx}", f"eR{idx}"
            ports[pL] = PortAtEnd(f"feedL{idx}", end="p1")
            ports[pR] = PortAtEnd(f"feedR{idx}", end="p0")
            # port A = element pair, port B = shared center tap; same polarity
            # on both elements -> in-phase (broadside).
            branches.append(
                BalancedLine(
                    a1=pL,
                    a2=pR,
                    b1="JC1",
                    b2="JC2",
                    zdiff=self.zdiff,
                    length=line_len,
                    zcomm=zc,
                )
            )
        # 50 Ohm coax at the tap: JC1 = center conductor (driven), JC2 = shield
        # (bonded to the common datum). The ground also pins the feed CM.
        branches.append(Shunt(port="JC2", l=0.0))
        return Network(
            ports=ports,
            branches=branches,
            sources=[Driven(port="JC1", voltage=1 + 0j)],
        )
