"""Sterba curtain: a broadside, bidirectional, horizontally-polarised curtain
array (E. J. Sterba, Bell Labs, 1930s).

Topology follows L. B. Cebik's (W4RNL) "models with remarkable ease" recipe
for the Sterba in NEC. The curtain is a single continuous closed wire that
meanders between a bottom rail (z = base) and a top rail (z = base + h),
where h = half a wavelength. Each horizontal half-wave run radiates; the
vertical half-wave runs phase-reverse the standing wave so every horizontal
section ends up in phase -> broadside gain off both faces.

The "twisted vertical line pairs" of the textbook drawing are NOT modelled as
transmission lines. Cebik's trick: run two conductors offset by a tiny space
(`spacing`) in x, one out-and-back, so the verticals sit as ordinary wires
correctly oriented in both planes and no half-twist or TL card is needed.
At 7.2 MHz Cebik used 0.5 ft of offset for a 2.5 wl curtain "without the
slightest distortion in antenna performance"; we scale a comparable offset.

Geometry, in the framework's (x, y, z) convention:
  - y  : the long axis of the curtain (Cebik's x)
  - z  : height; bottom rail at `base`, top rail at `base + h`
  - x  : the small twisted-pair offset (Cebik's y); curtain fires +/- x

The curtain has `n_cells` full half-wave sections in the middle plus a
quarter-wave section at each end, so the total length is
(n_cells + 1) * (lambda/2 * length_factor). n_cells must be odd so the
structure is symmetric and a bottom-rail half-wave section sits dead centre.

Feedpoint: the centre of the central lower (bottom-rail) half-wave section --
the classic "feed the middle of a lower 1/2-wl dipole section" point. The
input impedance is high (~600 ohm, reactive); in practice you feed it with
open-wire line to a tuner. With n_cells = 3 (~2 wl) this model gives, at
28.47 MHz, Z ~ 600 ohm, ~10.5 dBi bidirectional broadside in free space, and
~16 dBi at a ~14-deg elevation over average ground with the bottom rail at
7 m. length_factor near 1.0 maximises gain (and resonates near ~0.99);
gain falls off quickly below ~0.96 as the half-wave phasing breaks down.
"""

from antennaknobs import AntennaBuilder
import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            # Scales the half-wave unit (both horizontal section length and
            # vertical rail spacing). Tuned by the optimiser for resonance;
            # Cebik's table sits near ~0.98.
            "length_factor": 1.0,
            # Number of full half-wave sections in the middle of the curtain.
            # Must be odd. 3 -> ~2 lambda (Cebik's example); 5 -> ~3 lambda.
            "n_cells": 3,
            # Twisted-pair offset in x, in metres. Small vs wavelength; just
            # large enough to keep the two conductors from merging.
            "spacing": 0.04,
            "ui_params": MappingProxyType(
                {
                    # The curtain's driving-point impedance is ~600 ohm; it's
                    # fed with open-wire line to a tuner, so the SWR readout is
                    # referenced to 600 ohm rather than the auto 50 ohm default.
                    "target_z0": 600.0,
                    # Narrowband, 10m-specific antenna: snap the GUI freq
                    # sweep to the band containing design_freq (28.0-29.7 MHz)
                    # instead of the default broad +/-25% out-of-band view.
                    "sweep_policy": {"band_locked": True},
                    # Below ~0.96 the half-wave phasing breaks down (gain
                    # collapses) and the input reactance swings through a
                    # sharp anti-resonance; keep the slider/optimiser in the
                    # window where the curtain actually behaves as a Sterba.
                    "length_factor": {
                        "min": 0.96,
                        "max": 1.05,
                    },
                    "n_cells": {
                        "min": 1,
                        "max": 7,
                        "step": 2,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        wavelength = 299.792458 / self.design_freq

        h = 0.5 * wavelength * self.length_factor  # half-wave unit
        q = 0.5 * h  # quarter-wave end section
        bot = self.base
        top = self.base + h
        dx = self.spacing
        n = int(self.n_cells)

        assert n >= 1 and n % 2 == 1, "n_cells must be a positive odd integer"

        # y breakpoints: quarter-wave, then n half-waves, then quarter-wave.
        yb = [0.0, q] + [q + k * h for k in range(1, n + 1)] + [2 * q + n * h]
        Ltot = yb[-1]
        ymid = 0.5 * Ltot

        # Conductor A (x = 0): horizontal section i is on the top rail when i
        # is even, bottom rail when odd. Starts top-left, and -- because there
        # are n + 2 sections and n is odd -> odd count -> ends top-right.
        def lvl_a(i):
            return top if i % 2 == 0 else bot

        A = [(0.0, yb[0], lvl_a(0))]
        for i in range(n + 2):
            A.append((0.0, yb[i + 1], lvl_a(i)))  # horizontal run
            if i < n + 1:
                A.append((0.0, yb[i + 1], lvl_a(i + 1)))  # vertical riser
        A.append((0.0, Ltot, bot))  # right-end vertical down to bottom rail

        # Conductor B (x = dx): the return pass, right -> left, levels flipped
        # so it interleaves with A. Its first quarter-wave run starts from A's
        # bottom-right corner (so x ramps 0 -> dx within that run, exactly as
        # Cebik's wire table does -- no degenerate tiny jog wire).
        ybr = list(reversed(yb))

        def lvl_b(j):
            return bot if j % 2 == 0 else top

        B = [(dx, ybr[1], lvl_b(0))]
        B.append((dx, ybr[1], lvl_b(1)))
        for j in range(1, n + 2):
            B.append((dx, ybr[j + 1], lvl_b(j)))
            if j < n + 1:
                B.append((dx, ybr[j + 1], lvl_b(j + 1)))
        # B ends at (dx, 0, bot); the loop closes B[-1] -> A[0] (left-end
        # near-vertical riser, with the small x offset folded in).

        loop = A + B
        N = len(loop)

        tups = []
        feed_count = 0
        for k in range(N):
            p0 = loop[k]
            p1 = loop[(k + 1) % N]
            seg_len = math.dist(p0, p1)
            nseg = self.segs_for(seg_len, h)

            is_horizontal = abs(p0[2] - p1[2]) < 1e-9
            at_bottom = abs(p0[2] - bot) < 1e-9 and abs(p1[2] - bot) < 1e-9
            midy = 0.5 * (p0[1] + p1[1])
            # Feed = centre of the central lower half-wave section.
            is_feed = (
                is_horizontal
                and at_bottom
                and seg_len > 0.6 * h
                and abs(midy - ymid) < 0.01 * h
            )

            ev = None
            if is_feed:
                feed_count += 1
                if nseg % 2 == 0:
                    nseg += 1  # odd -> a segment sits exactly at centre
                ev = 1 + 0j

            tups.append((p0, p1, nseg, ev))

        assert feed_count == 1, f"expected exactly one feed edge, got {feed_count}"

        return tups
