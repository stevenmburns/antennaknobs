"""Sterba curtain whose interior risers are ideal balanced line, not wire (momwire-only).

The third member of the Sterba family: where `wire.sterba` models the whole
curtain as wires (verticals as tightly-spaced offset pairs) and
`wire.sterba_tl` is a deliberately one-high single-conductor study (~4 dB
short of the curtain by construction), this design keeps `wire.sterba`'s
exact two-conductor radiator geometry and replaces every INTERIOR riser pair
with a `BalancedLine` network element — reproducing the all-wire curtain's
broadside gain within ~0.2 dB at n_cells = 3 (+15.4 vs +15.2 dBi over
average ground) and scaling n_cells 1 → 7 broadside like the original.

Construction (issues #575/#576/#579):
  - Both conductors' horizontal spans are real wires, authored as two named
    halves per span so each interior boundary is a NODE. The two
    single-conductor END verticals stay real wires, as in `wire.sterba`.
  - Four `PortAtEnd` junction ports per boundary attach one `BalancedLine`
    by physical conductor pairing: port A = the two top-rail ends, port B =
    the two bottom-rail ends, conductor 1 = the A-conductor riser. The
    Sterba crossover is that wiring — no polarity flags.
  - `zdiff` defaults to the analytic pair impedance (η0/π)·acosh(s/2a); real
    open-wire loss `k1` regularises the exactly-λ/2 line (no length-factor
    fudge, unlike `sterba_tl`); `end_corr` is the measured pair end effect.
  - `zcomm` enables the element's common-mode path. This is load-bearing:
    the physical riser pair also provides conductor continuity, and in the
    multi-loop curtain that boundary condition — a λ/2 CM *repeater*
    (V → −V, I → −I regardless of impedance) — is what phases the outer
    spans. Differential-only (zcomm = 0) drops ~5 dB with the beam steered
    ~35° off broadside. Because the risers are resonant, the result is
    insensitive to the `zcomm` value (measured identical 25–400 Ω).

Engine support: **momwire only.** `PortAtEnd` resolves to a junction-node
port (current injection into the KCL row; the row's Lagrange multiplier is
the voltage dual) — NEC-2 has no equivalent card (NT attaches to segment
interiors), so `PyNECEngine` rejects the design at construction and the UI
offers only momwire backends for it.

Known model residual: the CM stamp neither radiates nor dissipates the real
pair's small antenna-mode current, so the model runs progressively hot at
high n (+0.2 dB at n=3 → +0.8 dB at n=7 vs the all-wire curtain).
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import (
    BalancedLine,
    Driven,
    Network,
    PortAtEnd,
    PortOnWire,
    Wire,
)

ETA0_OVER_PI = 376.730313668 / math.pi
WIRE_RADIUS = 0.0005


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            "length_factor": 1.0,
            # Odd; number of full half-wave middle sections per rail.
            "n_cells": 3,
            # Riser-pair conductor spacing in metres (sets the analytic zdiff).
            "spacing": 0.04,
            # 0 -> analytic (η0/π)·acosh(spacing/2a) from the pair geometry.
            "zdiff": 0.0,
            # Common-mode path impedance; the λ/2 risers make the result
            # insensitive to the value. 0 -> differential-only (the documented
            # ~5 dB failure — exposed for the modelling study, not for use).
            "zcomm": 200.0,
            # Open-wire matched loss (dB/100ft·√MHz): physically regularises
            # the exactly-λ/2 stamp singularity.
            "k1": 0.02,
            # Measured pair end-effect elongation (m), from the #576 oracle.
            "end_corr": 0.030,
            "ui_params": MappingProxyType(
                {
                    # Same feed class as wire.sterba: ~600 ohm at the central
                    # gap, open-wire line to a tuner.
                    "target_z0": 600.0,
                    # Narrowband 10m antenna: snap the GUI sweep to the band.
                    "sweep_policy": {"band_locked": True},
                    "n_cells": {"min": 1, "max": 7, "step": 2},
                    "spacing": {"min": 0.01, "max": 0.2, "step": 0.01},
                    # zcomm insensitivity is the point; give the slider the
                    # measured-flat range so users can see it for themselves.
                    "zcomm": {"min": 0.0, "max": 400.0, "step": 25.0},
                }
            ),
        }
    )

    # ---- layout ---------------------------------------------------------
    def _layout(self):
        wl = self.design_wavelength
        h = 0.5 * wl * self.length_factor
        q = 0.5 * h
        n = int(self.n_cells)
        assert n >= 1 and n % 2 == 1, "n_cells must be a positive odd integer"
        n_sections = n + 2
        yb = [0.0, q] + [q + k * h for k in range(1, n + 1)] + [2 * q + n * h]
        return wl, h, n_sections, yb

    def _lvl(self, i, cond):
        """Rail of conductor `cond` ('A'/'B') on span i — A on top for even
        spans, exactly wire.sterba's interleave."""
        _, h, _, _ = self._layout()
        a_top = i % 2 == 0
        top, bot = self.base + h, self.base
        if cond == "A":
            return top if a_top else bot
        return bot if a_top else top

    def _feed_cond(self, n_sections):
        """The bottom-rail conductor of the central span carries the feed."""
        center = (n_sections - 1) // 2
        return center, ("A" if self._lvl(center, "A") == self.base else "B")

    def build_wires(self):
        _, h, n_sections, yb = self._layout()
        s = self.spacing
        pe = 0.2  # feed-gap edge length (m)
        center, feed_cond = self._feed_cond(n_sections)

        tups = []
        for cond in ("A", "B"):
            x = 0.0 if cond == "A" else s
            for i in range(n_sections):
                z = self._lvl(i, cond)
                y0, y1 = yb[i], yb[i + 1]
                # Only halves whose outer end meets an interior boundary are
                # named (#578: unreferenced names would be open gaps).
                la = f"{cond}{i}a" if i > 0 else None
                lb = f"{cond}{i}b" if i < n_sections - 1 else None
                if cond == feed_cond and i == center:
                    yc = 0.5 * (y0 + y1)
                    tups.append(Wire((x, y0, z), (x, yc - 0.5 * pe, z), name=la))
                    tups.append(
                        Wire(
                            (x, yc - 0.5 * pe, z), (x, yc + 0.5 * pe, z), name="feed"
                        )  # fmt: skip
                    )
                    tups.append(Wire((x, yc + 0.5 * pe, z), (x, y1, z), name=lb))
                else:
                    ym = 0.5 * (y0 + y1)
                    tups.append(Wire((x, y0, z), (x, ym, z), name=la))
                    tups.append(Wire((x, ym, z), (x, y1, z), name=lb))
        # Single-conductor end closures, real wires exactly as wire.sterba
        # (the small x offset folded into the diagonal). Each closure endpoint
        # shares its node with a span end.
        tups.append(Wire((0.0, 0.0, self._lvl(0, "A")), (s, 0.0, self._lvl(0, "B"))))
        yl = yb[-1]
        tups.append(
            Wire(
                (0.0, yl, self._lvl(n_sections - 1, "A")),
                (s, yl, self._lvl(n_sections - 1, "B")),
            )  # fmt: skip
        )
        return tups

    def build_network(self):
        _, h, n_sections, yb = self._layout()
        zd = self.zdiff if self.zdiff else (
            ETA0_OVER_PI * math.acosh(self.spacing / (2.0 * WIRE_RADIUS))
        )  # fmt: skip
        length = h + self.end_corr
        top = self.base + h
        ports = {"feed": PortOnWire("feed", distributed=True)}
        branches = []
        for k in range(1, n_sections):
            i = k - 1
            # Four span ends meet at boundary k. Pair by RAIL: port A = the
            # two TOP-rail ends, port B = the two BOTTOM-rail ends;
            # conductor 1 = the A-conductor riser (a1 <-> b1).
            pa = f"eA{k}"  # A-conductor: span i right end
            pa2 = f"eA{k}n"  # A-conductor: span k left end
            pb = f"eB{k}"  # B-conductor: span i right end
            pb2 = f"eB{k}n"  # B-conductor: span k left end
            ports[pa] = PortAtEnd(f"A{i}b", end="p1")
            ports[pa2] = PortAtEnd(f"A{k}a", end="p0")
            ports[pb] = PortAtEnd(f"B{i}b", end="p1")
            ports[pb2] = PortAtEnd(f"B{k}a", end="p0")
            a_top = self._lvl(i, "A") == top
            a1, b1 = (pa, pa2) if a_top else (pa2, pa)
            a2, b2 = (pb2, pb) if a_top else (pb, pb2)
            branches.append(
                BalancedLine(
                    a1=a1,
                    a2=a2,
                    b1=b1,
                    b2=b2,
                    zdiff=zd,
                    length=length,
                    k1=self.k1,
                    zcomm=self.zcomm or None,
                )  # fmt: skip
            )
        return Network(
            ports=ports,
            branches=branches,
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )
