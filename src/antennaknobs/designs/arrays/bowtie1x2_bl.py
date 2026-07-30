"""1x2 stacked bowtie array with a balanced-line corporate feed.

A worked example of feeding a phased array through `BalancedLine` rather than
the framework's per-element delta-gap phasing (`Array2x2Builder`). Two bowtie
elements are stacked half a wavelength apart and combined by a matched
balanced-line corporate feed:

    element (~100 Ω)  --~100 Ω BalancedLine half-->  center tap  <--half-- element
                                                      |
                                            50 Ω coax (single-ended)

The impedance ladder is the intent: two ~100 Ω-class elements combined by
~100 Ω half-lines that parallel to 50 Ω at the center tap — a 1:1 match to
50 Ω coax (SWR ~1.01 at the design frequency), +5.7 dBi bidirectional
broadside (φ = 0/180) with deep endfire nulls. In practice the geometry is
tuned so the *tap* presents 50 Ω directly, NOT by matching each element to a
transparent line: an element's impedance in an array is feed-dependent (the
current ratio the balanced network sets differs from an isolated or delta-gap
drive), so there is no feed-independent "100 Ω element" — the tuned
element-plus-line network as a whole realizes the 50 Ω tap. The tune is also
feed-MODEL-dependent: the pre-#608 `PortAtEnd` authoring of this same design
tuned to (44.0°, 0.560, 100 Ω); the floating-gap authoring below retunes to
(46.5°, 0.555, 97 Ω) for the same SWR ~1.01 — the restored bridge metal and
gap drive shift each element's driving-point by a few percent.

Against ideal equal-current feeding of the same geometry the balanced feed is
pattern-identical (within ~0.2 dB everywhere): it is lossless and matched, so
it faithfully delivers the broadside excitation — the corporate feed costs
nothing in gain or pattern here.

Freq-based geometry (unlike `specialty.bowtie`, whose dimensions are hand-tuned
absolute metres): every length is a wavelength factor, so the whole antenna and
its feed scale with `freq`.

Construction (issues #575/#576/#605; re-authored engine-portable per #608):
  - Each bowtie keeps its real center feed-bridge wire (as `specialty.bowtie`
    has), carrying a `PortOnWireFloating` delta gap at its middle segment.
    Both gap faces are LIVE — each connects through the element's own loop
    (solid top bridge) — which is exactly the attachment class a gap is FOR,
    and why this re-authoring works where `wire.sterba_bl`'s cannot: the
    corporate feed only ever drives differential element current through a
    live loop; no net current injection at a conductor end is required
    anywhere. (Contrast the sterba verdict in `wire/sterba_bl.py`: its riser
    boundaries need net inter-rail current transfer, which by KCL needs metal
    or a junction-node port.)
  - One `BalancedLine` per element runs from the gap pair (``feed{idx}.p`` /
    ``feed{idx}.n``) to the shared center-tap `PortVirtual` pair.
  - The center tap models 50 Ω coax single-ended: `Driven` on one tap
    conductor, the other bonded to the common datum (the coax shield).
  - CM level pins: a floating gap passes zero common-mode current
    structurally, so with the CM-open lines the gap pair's common LEVEL
    references nothing and the MNA would be singular. A 100 MΩ `Shunt` to
    datum at each gap terminal pins the level while carrying ~zero current.
    Do NOT use `zcomm` for this: the λ/4 half-lines would transform the
    element-side CM open into a CM short at the grounded tap, shorting the
    driven node. `zcomm` remains exposed for the modelling study only.

Engine support: **all engines.** The floating gap is stamped entirely in the
shared reducer (#605/#607), so momwire (every basis) and PyNEC both run this
design; measured 2026-07-30 at the retuned point: momwire 5.70 dBi broadside,
tap 49.80−0.39j (SWR 1.009); PyNEC 5.70 dBi, 49.74−1.26j (SWR 1.026) —
0.01 dB and ~1 Ω apart, both mesh-stable nsegs 21→41. This closed the
bowtie half of issue #608 (the sterba half measured "no"; see that design).
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import (
    BalancedLine,
    Driven,
    Network,
    PortOnWireFloating,
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
            # tuned so the center TAP presents 50 Ohm to the coax (SWR ~1.01)
            # under the floating-gap feed model (#608 re-authoring).
            "angle_deg": 46.5,
            "length_factor": 0.555,
            # Element stacking distance / wavelength (sets the half-line length).
            "del_z_factor": 0.5,
            # Corporate-feed line impedance (matched to the element).
            "zdiff": 97.0,
            # Feeders are common-mode-open (0 -> None): the physical model.
            # Exposed for the modelling study only — see the docstring note
            # on why zcomm must NOT be used as the CM level pin here.
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
        """One bowtie at vertical offset `zoff`, WITH its center feed bridge;
        the bridge is named ``feed{idx}`` and hosts the floating gap."""
        _, y, z = self._element_geo()
        eps = 0.05  # feed-bridge half-width (m)
        specs = [
            ((-y, 0.0), (-y, z), None),
            ((-y, z), (-eps, eps), None),
            ((-eps, eps), (eps, eps), None),  # top bridge (solid)
            ((eps, eps), (y, z), None),
            ((y, z), (y, 0.0), None),
            ((-y, 0.0), (-y, -z), None),
            ((-y, -z), (-eps, -eps), None),
            ((-eps, -eps), (eps, -eps), f"feed{idx}"),  # feed bridge (gapped)
            ((eps, -eps), (y, -z), None),
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
            ports[f"feed{idx}"] = PortOnWireFloating(f"feed{idx}")
            # port A = element gap pair, port B = shared center tap; same
            # polarity on both elements -> in-phase (broadside).
            branches.append(
                BalancedLine(
                    a1=f"feed{idx}.p",
                    a2=f"feed{idx}.n",
                    b1="JC1",
                    b2="JC2",
                    zdiff=self.zdiff,
                    length=line_len,
                    zcomm=zc,
                )
            )
            # CM level pins (see docstring): ~zero current, no resonant
            # transformation. Both terminals only because the CM validator
            # counts nodes independently; the gap already ties p<->n.
            branches.append(Shunt(port=f"feed{idx}.p", r=1e8))
            branches.append(Shunt(port=f"feed{idx}.n", r=1e8))
        # 50 Ohm coax at the tap: JC1 = center conductor (driven), JC2 = shield
        # (bonded to the common datum). The ground also pins the feed CM.
        branches.append(Shunt(port="JC2", l=0.0))
        return Network(
            ports=ports,
            branches=branches,
            sources=[Driven(port="JC1", voltage=1 + 0j)],
        )
