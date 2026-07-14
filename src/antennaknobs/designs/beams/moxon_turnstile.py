"""Moxon turnstile: two up-firing Moxons in real quadrature (L. B. Cebik,
W4RNL, QST Aug 2001 pp. 38-41 / "Some Notes on Turnstile Antenna
Properties", QEX).

Two Moxon rectangles (the catalog's `beams.moxon` geometry) stand in
perpendicular vertical planes, each with its reflector below its driver so
both fire STRAIGHT UP, and are fed 90 degrees out of phase -- the classic
turnstile, aimed at the sky for fixed satellite work. Against the dipole
turnstile Cebik's Fig. 12 comparison shows a smoother dome of overhead
coverage (and the reflectors kill the downward half, so no ground screen),
plus structural simplicity: the folded tips make each element self-
supportingly compact.

The QEX notes' central lesson, which this model implements literally, is
that turnstile quality is a CURRENT condition: the second element must carry
the same current magnitude 90 degrees behind the first, and the way to get
it is a quarter-wave phasing line whose z0 EQUALS the element feed R (his
model: ratio 0.976 at 89.98 deg; get the z0 wrong by 50->93 ohm and the
ratio degrades 30% into an oval pattern). Each Moxon is Cebik's ~50 ohm
coax-friendly resonant rectangle, so the phaseline is 50 ohm, the junction
reads ~25 ohm (two elements in parallel through the matched line), and a
quarter-wave 35 ohm transformer (RG-83, or two paralleled 70 ohm lines)
steps the junction back to ~49 ohm for the main feedline -- both lines are
real `TL` branches here, not idealized dual sources (contrast the catalog's
`dipole_turnstile`/`diamond_loop_turnstile`, which hard-code the quadrature
as two phased excitations).

Gain accounting worth getting right (the tests pin it): each element takes
half the power, but at the zenith the two fields are orthogonal
polarisations whose powers ADD BACK, so the total-field zenith gain equals
a single element's boresight (~5.6 dBi here) and the mid-elevation azimuth
ripple collapses from ~3 dB (one Moxon) to ~0.2 dB -- the dome. Cebik's
famous ~3 dB turnstile penalty is what a polarisation-MATCHED (linear or
single-CP-sense) receiver sees of that total field.

Geometry, in the framework's (x, y, z) convention:
  - element A: plane x = 0, driver runs along y; reflector below driver
  - element B: plane y = 0, driver runs along x, raised `gap_z` to clear A
  - z : both fire +z (up); `base` is the reflector height
Free space or over ground, the dome looks up.

      A-driver ===o===        (o = feed_a gap; B's driver crosses it
      A-reflector =====        gap_z higher, running along x)
           |
           | 1/4 wl z0_phase phaseline: feed_a -> feed_b (the 90 deg)
           | 1/4 wl z0_match transformer: shack -> feed_a
           S                   S = shack feed (virtual port)
"""

from antennaknobs import AntennaBuilder
from antennaknobs.designs.beams.moxon import Builder as Moxon
from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the reflectors above ground; the elements sit a
            # Moxon-width higher.
            "base": 7.0,
            # Vertical clearance element B gets over element A where the
            # wires cross (Cebik separated his crossed dipoles ~0.005 wl).
            "gap_z": 0.1,
            # Overall scale of the reused beams.moxon outline; 1.014 makes
            # one element read resonant (~62 ohm) at this segmentation --
            # the thin-wire HF cousin of Cebik's ~50 ohm tube-element VHF
            # build, so the harness z0s track 62 instead of 50.
            "length_factor": 1.014,
            # Quarter-wave phasing line, z0 = the ELEMENT feed R -- the QEX
            # current condition. This is the knob that breaks the turnstile
            # when wrong (50 -> 93 ohm cost Cebik 30% of the current ratio).
            "z0_phase": 62.0,
            "phase_len_frac": 0.25,
            # Quarter-wave step-down transformer to the main line:
            # sqrt(31 * 50) ~ 39 ohm (Cebik's 50 ohm elements wanted his
            # 35 ohm RG-83, or two paralleled 70 ohm lines).
            "z0_match": 39.4,
            "match_len_frac": 0.25,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    # The two driver runs span x and y; the xy view shows
                    # the crossed outline.
                    "default_view": "xy",
                    "length_factor": {
                        "min": 0.9,
                        "max": 1.1,
                    },
                    "z0_phase": {
                        "min": 30.0,
                        "max": 100.0,
                        "step": 0.5,
                        "precision": 1,
                    },
                    "z0_match": {
                        "min": 20.0,
                        "max": 75.0,
                        "step": 0.5,
                        "precision": 1,
                    },
                    "phase_len_frac": {"min": 0.15, "max": 0.35},
                    "match_len_frac": {"min": 0.15, "max": 0.35},
                }
            ),
        }
    )

    def _moxon_outline(self):
        """The reused beams.moxon wire list, scaled to this design's
        frequency, in the Moxon's own planar coordinates (u = beam axis,
        reflector at -short/2 and driver at +short/2; v = element run)."""
        m = Moxon(dict(Moxon.default_params, base=0.0))
        s = 28.57 / self.design_freq * self.length_factor
        return [
            ((t[0][0] * s, t[0][1] * s), (t[1][0] * s, t[1][1] * s), t[2], t[3])
            for t in m.build_wires()
        ]

    def _element(self, which):
        """One up-firing element: the planar outline stood in a vertical
        plane, beam axis (u) mapped onto +z so the reflector sits below the
        driver. Element A lives in x=0, B in y=0 raised by gap_z."""
        if which == "a":
            lift, name = 0.0, "feed_a"

            def place(u, v):
                return (0.0, v, self.base + u)

        else:
            lift, name = self.gap_z, "feed_b"

            def place(u, v):
                return (v, 0.0, self.base + u)

        # The outline's u runs from -short/2 to +short/2; shift so the
        # reflector (u min) lands at `base`.
        u0 = min(min(t[0][0], t[1][0]) for t in self._moxon_outline())
        tups = []
        for (au, av), (bu, bv), n, ev in self._moxon_outline():
            p0 = place(au - u0, av)
            p1 = place(bu - u0, bv)
            p0 = (p0[0], p0[1], p0[2] + lift)
            p1 = (p1[0], p1[1], p1[2] + lift)
            tups.append((p0, p1, n, None, name if ev is not None else None))
        return tups

    def build_wires(self):
        return self._element("a") + self._element("b")

    def build_network(self):
        wavelength = 299.792458 / self.design_freq
        return Network(
            ports={
                "feed_a": PortOnWire("feed_a"),
                "feed_b": PortOnWire("feed_b"),
                "shack": PortVirtual("shack"),
            },
            branches=[
                # The quadrature: a quarter wave of element-impedance line.
                TL(
                    a="feed_a",
                    b="feed_b",
                    z0=self.z0_phase,
                    length=self.phase_len_frac * wavelength,
                ),
                # The match: a quarter wave of low-Z line back to ~50 ohm.
                TL(
                    a="shack",
                    b="feed_a",
                    z0=self.z0_match,
                    length=self.match_len_frac * wavelength,
                ),
            ],
            sources=[Driven(port="shack", voltage=1 + 0j)],
        )
