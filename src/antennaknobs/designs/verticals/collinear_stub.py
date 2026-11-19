"""Two-section collinear vertical (λ/4 under λ/2) and the stub that co-phases it, against three substitutes that do not.

A quarter-wave vertical, base-fed over three horizontal quarter-wave radials,
with a half-wave vertical stacked above it. Between the two, at the top of the
quarter-wave (point A), a quarter-wave SHORTED stub runs out horizontally as a
hairpin. Without the stub, a continuous 3λ/4 wire carries antiphase current in
its upper half-wave and fires a high-angle cone; the stub is there to put the
upper section's current in phase with the lower's, so the pattern stays on the
horizon. On 40 m (7.1 MHz) that is a 10.6 m lower section, a 21.1 m upper
section and a 10.6 m hairpin, about 32 m tall in all.

The usual substitutes for the hairpin — leaving A open, a parallel-resonant LC
trap at A, or the stub folded coaxially inside the element as a sleeve — all
present a high impedance at A, and the antenna radiates with any of them. They
do NOT co-phase it. The variants measure that, alongside two network models of
the stub itself.

Variants (``stub`` knob):

- ``default`` — the reference (call it ``wire_stub``): the hairpin as three
  real wires, the two legs ``spacing`` apart (10 cm: a 636 Ω open-wire pair
  with the default 1 mm wire), the far end shorted.
- ``bl_stub`` — the hairpin as a `BalancedLine` on two `PortAtEnd` junction
  ports (the lower section's top, the upper section's bottom), its far end
  shorted, and ``zcomm`` on. The `wire.sterba_bl` construction.
- ``bl_stub_diffonly`` — the same line with ``zcomm = 0``: differential only.
- ``open_circuit`` — no stub. The upper section starts ``spacing`` above A.
- ``lc_trap`` — a parallel LC across a one-segment gap at A, resonant at
  ``design_freq`` (``trap_l_uh``, coil Q ``trap_q``).
- ``coax_sleeve`` — a gap at A loaded by a λ/4 shorted coax stub (``cable``,
  at its velocity factor). That is the coaxial sleeve's physics: its outside is
  the element, continuous through A, and the only thing it adds is the stub's
  input impedance in series at the sleeve's open end.

The vertical geometry is identical in all six: the same break of ``spacing``
at A, the same feed gap, the same radials (``n_radials``, evenly spaced from
+x, the first one under the hairpin, each λ/4 long).

Measured 2026-11-19, 40 m (7.1 MHz), base 0.5 m, three radials, momwire
`nec5-bspline` (the default engine) at the design density (149 segments for
the hairpin, 106-107 for the others), design frequency. Δφ is the phase of the
current at the centre of the λ/2 section less that at the centre of the λ/4
section, both taken upward along the axis; co-phased means Δφ near 0°. Gains in
dBi.

Free space ("horizon" is the gain at 0° elevation):

    variant            Δφ     |I_λ/4|  |I_λ/2|  peak  at el  horizon  Z (Ω)
    wire_stub         +10°     4.9 mA   5.5 mA  3.0    -4.5°   2.9    144 + j94
    bl_stub           +14°     4.9      5.5     3.2    -2.5°   3.2    139 + j110
    bl_stub_diffonly  -162°   35.7     20.5     3.6    37°    -6.5     17 − j10
    open_circuit      -162°   35.7     20.5     3.6    37°    -6.5     17 − j10
    lc_trap           -169°   32.7     20.1     2.7    38.5°  -10.5    20 − j9
    coax_sleeve       +180°   19.9     18.6     1.3    40.5°  -10.8    34 − j10

Average ground (Sommerfeld, εr 13, σ 0.005, the CLI's default; "5-15°" is
the power mean over those elevations on the peak's azimuth, as the
"the stub and its substitutes" analysis reports it):

    variant            Δφ     peak  at el   5-15°   Z (Ω)
    wire_stub         +10°    0.2   14.5°   -0.7    164 + j89
    bl_stub           +13°    0.2   14°     -0.7    158 + j99
    bl_stub_diffonly  -171°   3.1   41°     -4.7     32 + j5
    open_circuit      -171°   3.1   41°     -4.7     32 + j5
    lc_trap           -177°   2.9   42°     -6.0     35 + j7
    coax_sleeve       +175°   3.0   44.5°   -7.5     50 + j9

PyNEC agrees on the four variants it can run (free space: Δφ +10.4°,
−161.7°, −168.5°, +179.6°; Z within 2 Ω).

Only the hairpin and the BalancedLine with its common-mode path co-phase the
sections. The other four are antiphase to within 20° and put the lobe at
37-45°. Over ground each of them has MORE peak gain than the co-phased antenna,
which is why "it radiates" says nothing about whether it works as a collinear:
at 5-15° the co-phased versions are 4-7 dB stronger.

Radials. Azimuth asymmetry (max − min gain round the ring at the main lobe's
elevation, average ground):

    n_radials   wire_stub   bl_stub   open_circuit
        2        0.60 dB    0.11 dB     0.40 dB
        3        0.70       0.09        0.13
        4        0.64       0.00        0.01

More radials take the radials' own asymmetry away (bl_stub and the open
circuit, which have no hairpin wire, go to zero at 4), but the hairpin's
asymmetry stays at about 0.6-0.7 dB whatever the count: past two radials, the
hairpin sets the pattern's roundness, not the radials. Δφ does not move with
the radial count (within 0.1°).

Why the common mode is the whole story (the `wire.sterba_bl` lesson, met from
the other side). Three measurements, then the reading of them.

1. A shorted λ/4 line's DIFFERENTIAL input impedance at resonance is an open,
   so in its differential mode the stub is the open circuit:
   ``bl_stub_diffonly`` and ``open_circuit`` agree to four figures.
2. With ``zcomm`` on, bl_stub reads the same at 50, 200 and 800 Ω.
3. The control: keep ``zcomm`` on but short the common mode at the far end
   (a `Shunt` from the far node to the datum), and bl_stub lands on the
   open-circuit numbers exactly (Δφ −162°, lobe at 37°).

So the co-phasing lives entirely in the stub's COMMON mode. On the hairpin
that mode is the two legs together: an open-ended λ/4 conductor hanging off
A. An open λ/4 line has a near-zero input impedance whatever its Z0 (hence
2), so it holds the common-mode voltage at A near zero, and that makes the
voltage at the upper section's foot the negative of the voltage at the lower
section's top. That inversion is what turns the upper section's current
round; shorting the far end (3) turns the λ/4 null into an open at A and
releases it. In the Sterba curtain the same V → −V constraint arrives through
a λ/2 common-mode repeater; here it arrives through a λ/4 common-mode null.
In both, a differential-only line deletes it. The coax sleeve fails for the
same reason: its outside is the element itself, so there is no side
conductor to hold A's common-mode voltage down, only a series impedance.

bl_stub tracks the hairpin to within 0.25 dB in peak gain, 4° in Δφ and about
j10-j16 Ω in feed reactance, and is mesh-stable (nominal_nsegs 20 → 40 moves
nothing past the third figure). The residual is, most likely, what the stamp
leaves out: its common mode neither radiates nor couples to the vertical,
where the hairpin's legs do a little of both.

Neither section is tuned: the fractions are the nominal λ/4 and λ/2, so the
feed is not at resonance. On the hairpin, ``stub_frac`` moves the feed
reactance through zero near 0.24 λ while Δφ stays within 7-27° over
0.22-0.26 λ, so tuning the match does not undo the co-phasing.

Engine support: ``bl_stub`` and ``bl_stub_diffonly`` are **momwire only**:
`PortAtEnd` is a junction-node port, which NEC-2 has no card for, so
`PyNECEngine` rejects those two variants at construction. The other four
(wires, gap ports, a `Load` and a `TL` stub) run on every engine.
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs import analyses as an
from antennaknobs.network import (
    CABLES,
    BalancedLine,
    Driven,
    Instance,
    Load,
    Network,
    PortAtEnd,
    PortOnWire,
    PortVirtual,
    Shunt,
    Wire,
)
from antennaknobs.station import shunt_shorted_stub

ETA0_OVER_PI = 376.730313668 / math.pi
WIRE_RADIUS = 0.0005
#: The feed gap at the radiator's foot, in wavelengths at design_freq: 0.21 m
#: at 40 m. A fixed few centimetres would be a segment some 80x shorter than
#: its neighbours there, which NEC-2 does not take well.
FEED_GAP_FRAC = 0.005

#: What sits at A: the hairpin as wires, the hairpin as a BalancedLine, nothing,
#: a parallel LC trap, or a coaxial sleeve stub.
STUBS = ("wire", "bl", "open", "trap", "coax")


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 7.1,
            "freq": 7.1,
            # Feed and radials just clear of the ground, as the 40 m
            # verticals.elevated_buried_counterpoise (and verticals.vertical).
            "base": 0.5,
            # Three λ/4 radials at 120°, the first along +x, under the hairpin.
            "n_radials": 3,
            # Section lengths in wavelengths at design_freq. The radials are
            # lower_frac long too.
            "lower_frac": 0.25,
            "upper_frac": 0.5,
            # Stub length (wavelengths) and the hairpin's leg spacing (m),
            # which is also the break between the sections at A in every
            # variant, so the vertical geometry is the same in all of them.
            # 10 cm with the default 1 mm-diameter wire is a 636 Ω open-wire
            # pair, (η0/π)·acosh(s/2a): ordinary home-made ladder line.
            "stub_frac": 0.25,
            "spacing": 0.10,
            "stub": "wire",
            # BalancedLine only. 0 -> zdiff from the pair geometry,
            # (η0/π)·acosh(spacing/2a). zcomm 0 -> differential only.
            "zdiff": 0.0,
            "zcomm": 200.0,
            # LC trap: coil inductance (µH) and coil Q; C resonates it at
            # design_freq.
            "trap_l_uh": 4.0,
            "trap_q": 200.0,
            # Coax sleeve: the stub's cable (z0, vf, loss).
            "cable": "RG-213",
            "ui_params": MappingProxyType(
                {
                    # Radials in the xy plane, hairpin along x, sections in z.
                    "default_view": "iso",
                    "stub": {"enum_options": STUBS},
                    "cable": {"enum_options": tuple(sorted(CABLES))},
                    "n_radials": {"min": 1, "max": 16, "step": 1},
                    "stub_frac": {"min": 0.2, "max": 0.3, "step": 0.002},
                    "spacing": {"min": 0.02, "max": 0.5, "step": 0.01},
                    "zcomm": {"min": 0.0, "max": 800.0, "step": 25.0},
                    "trap_l_uh": {"min": 0.5, "max": 20.0, "step": 0.5},
                    "trap_q": {"min": 20.0, "max": 400.0, "step": 10.0},
                }
            ),
        }
    )

    bl_stub_params = MappingProxyType({"stub": "bl"})
    bl_stub_diffonly_params = MappingProxyType({"stub": "bl", "zcomm": 0.0})
    open_circuit_params = MappingProxyType({"stub": "open"})
    lc_trap_params = MappingProxyType({"stub": "trap"})
    coax_sleeve_params = MappingProxyType({"stub": "coax"})

    def heights(self):
        """``(z_feed_top, z_a, z_b, z_top)``: the feed gap's top, the lower
        section's top (A), the upper section's foot and its top, in metres."""
        wl = self.design_wavelength
        z_a = self.base + self.lower_frac * wl
        z_b = z_a + self.spacing
        return self.base + FEED_GAP_FRAC * wl, z_a, z_b, z_b + self.upper_frac * wl

    def section_centres(self):
        """The heights the co-phasing is read at: the centres of the λ/4 and
        the λ/2 sections."""
        z_ft, z_a, z_b, z_top = self.heights()
        return 0.5 * (z_ft + z_a), 0.5 * (z_b + z_top)

    def build_wires(self):
        if self.stub not in STUBS:
            raise ValueError(f"stub is one of {STUBS}, got {self.stub!r}")
        z_ft, z_a, z_b, z_top = self.heights()
        base = self.base
        # The junction ports name the two section ends; any other variant
        # leaves them unnamed (an unreferenced name would cut a gap, #578).
        jn = self.stub == "bl"
        tups = [
            Wire((0, 0, base), (0, 0, z_ft), name="feed"),
            Wire((0, 0, z_ft), (0, 0, z_a), name="lower" if jn else None),
            Wire((0, 0, z_b), (0, 0, z_top), name="upper" if jn else None),
        ]
        r_len = self.lower_frac * self.design_wavelength
        n = max(1, round(self.n_radials))
        for i in range(n):
            # Evenly spaced from +x, as verticals.vertical spaces them.
            th = 2 * math.pi * i / n
            tups.append(
                Wire((0, 0, base), (r_len * math.cos(th), r_len * math.sin(th), base))
            )
        if self.stub == "wire":
            ls = self.stub_frac * self.design_wavelength
            tups += [
                Wire((0, 0, z_a), (ls, 0, z_a)),
                Wire((ls, 0, z_a), (ls, 0, z_b)),  # the shorting bar
                Wire((ls, 0, z_b), (0, 0, z_b)),
            ]
        elif self.stub in ("trap", "coax"):
            # One segment bridging the break; its gap carries the element.
            tups.append(Wire((0, 0, z_a), (0, 0, z_b), n_seg=1, name="gap"))
        return tups

    def build_network(self):
        ports = {"feed": PortOnWire("feed")}
        branches = []
        f = self.design_freq
        if self.stub == "bl":
            zd = self.zdiff or ETA0_OVER_PI * math.acosh(
                self.spacing / (2.0 * WIRE_RADIUS)
            )
            ports["a1"] = PortAtEnd("lower", end="p1")
            ports["a2"] = PortAtEnd("upper", end="p0")
            # The shorting bar: both conductors end on one node. Nothing else
            # touches it, so the common mode is OPEN there, as on the hairpin.
            ports["far"] = PortVirtual("far")
            branches.append(
                BalancedLine(
                    a1="a1",
                    a2="a2",
                    b1="far",
                    b2="far",
                    zdiff=zd,
                    length=self.stub_frac * self.design_wavelength,
                    zcomm=self.zcomm or None,
                )
            )
            if not self.zcomm:
                # Differential only, the far node's common-mode voltage is
                # undetermined and nothing at A depends on it: pinning it is
                # a gauge fix, not physics. (With zcomm on it would be
                # physics: it would short the common mode.)
                branches.append(Shunt("far", r=0.0))
        elif self.stub == "trap":
            l_h = self.trap_l_uh * 1e-6
            w = 2 * math.pi * f * 1e6
            ports["gap"] = PortOnWire("gap")
            branches.append(
                Load("gap", l=l_h, c=1.0 / (w * w * l_h), parallel=True, ql=self.trap_q)
            )
        elif self.stub == "coax":
            ports["gap"] = PortOnWire("gap")
            sleeve = shunt_shorted_stub(f, self.stub_frac, cable=self.cable)
            branches.append(Instance("sleeve", sleeve, port="gap"))
        return Network(
            ports=ports,
            branches=branches,
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )

    def build_analyses(self):
        """The stub against its substitutes, as patterns; and the stub length
        swept, as the take-off angle. A far-field metric cannot read the
        current phase (no metric kind reads currents), but the take-off angle
        is its signature here: on the horizon co-phased, near 40° not."""
        me = "verticals.collinear_stub"
        states = (
            an.State("hairpin", design=me),
            an.State("BalancedLine", design=me, variant="bl_stub"),
            an.State("BL diff-only", design=me, variant="bl_stub_diffonly"),
            an.State("open", design=me, variant="open_circuit"),
            an.State("LC trap", design=me, variant="lc_trap"),
            an.State("coax sleeve", design=me, variant="coax_sleeve"),
        )
        low = an.ElevationWindow("5-15° gain", 5, 15, step=1.0)
        group = "Co-phasing"
        return [
            an.Analysis(
                "the stub and its substitutes",
                None,
                cross=an.Cross(states=states),
                views=(an.Elevation(az=90), an.PatternTable(metrics=(low,))),
                group=group,
            ),
            an.Analysis(
                "stub length",
                an.Sweep("stub_frac", 0.22, 0.28, points=13),
                cross=an.Cross(states=states[:2]),
                views=(an.MetricPlot(an.TakeOff()), an.MetricPlot(low), an.Rx()),
                group=group,
            ),
        ]
