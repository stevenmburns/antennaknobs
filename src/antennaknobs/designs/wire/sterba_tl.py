"""Sterba curtain, transmission-line sister design of `sterba.py`.

Where `wire.sterba` models the curtain as a single continuous wire
(Cebik's offset-pair trick, verticals as real wires), this variant models
the vertical phasing sections as **ideal transmission lines** via
`build_network()`.

Simplified single-conductor form: a flat meander at x=0 made of
`n_cells + 2` horizontal sections (a quarter-wave at each end, `n_cells`
half-waves in the middle) at alternating heights — bottom rail (z = base)
and top rail (z = base + h), h = half a wavelength. Consecutive sections
are NOT joined by wire; each junction is bridged by a half-wave TL that
plays the role of the vertical phasing line. With n_cells = 3 that's five
sections joined by four TLs. The feed is a delta-gap at the centre of the
central (lower) section.

Differences from the all-wires `sterba`:
  - One conductor, not the offset pair, so the curtain is one-high (a
    staircase of sections) rather than two-high stacked. Expect somewhat
    lower gain than the all-wires version; this is a modelling study of
    the TL abstraction, not a higher-performance antenna.
  - The verticals carry no geometry: their current/phase lives entirely
    in the TL stamp, so there is nothing to radiate from them by
    construction (the all-wires version achieves the same end by current
    cancellation in the offset pair).

Note on the half-wave TL: this engine's nodal TL admittance
1/(jZ0 sin βl)·[[cos βl,-1],[-1,cos βl]] is SINGULAR at βl = π (length =
λ/2). The phasing lines are nominally λ/2, so `length_factor` defaults to
0.99 (TL length ≈ 0.495 λ) to sit just off the singularity. lf = 1.0
exactly will raise in `network_reduce.tl_admittance_2x2`; keep lf away from 1.0.
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Network, PortOnWire, TL
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            # Off 1.0 on purpose: at lf = 1.0 the half-wave phasing TLs hit
            # the βl = π nodal-admittance singularity. 0.99 sits just off it.
            "length_factor": 0.99,
            # Odd; number of full half-wave middle sections. TLs = n_cells + 1.
            "n_cells": 3,
            # Characteristic impedance of the phasing lines (the twisted pair
            # the TL stands in for); ~500 ohm for a close-spaced 2-wire line.
            "z0": 500.0,
            "ui_params": MappingProxyType(
                {
                    # Unlike the all-wires (~600 ohm) Sterba, the single-
                    # conductor TL-fed form presents ~70 ohm at the central
                    # delta-gap (near resonance at lf ~ 0.997), so reference
                    # SWR to 75 ohm.
                    "target_z0": 75.0,
                    # Single-band 10m antenna: snap the GUI sweep to the band.
                    "sweep_policy": {"band_locked": True},
                    # Keep length_factor near (but not at) 1.0; below ~0.96
                    # the phasing degrades, and 1.0 is the TL singularity.
                    "length_factor": {
                        "min": 0.96,
                        "max": 0.999,
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
        n = int(self.n_cells)
        assert n >= 1 and n % 2 == 1, "n_cells must be a positive odd integer"

        n0 = self.nominal_nsegs
        pe = max(0.2, 0.06 * h)  # short port/feed edge length (m)

        # y breakpoints and per-section heights (alternate, start on bottom
        # so both ends and the centre sit on the lower rail).
        yb = [0.0] + [q + k * h for k in range(n + 1)] + [2 * q + n * h]
        n_sections = n + 2
        center_sec = (n_sections - 1) // 2

        def level(i):
            return bot if i % 2 == 0 else top

        self._tl_length = h  # consumed by build_network()

        tups = []

        def edge(ya, yb_, z, name):
            seg_len = abs(yb_ - ya)
            # Named TL-port edges refine like every other wire: the
            # distributed ports in build_network() span the edge's fixed
            # physical extent, so the port model no longer narrows as the
            # mesh refines (issue #477). This retired the old 3-segment
            # pin, whose flat ladder was flat at a basis-DEPENDENT value
            # (sin 72.96−16.59j vs bs2 72.64−14.89j); the finite-gap port
            # is flat at the value the bases agree on.
            ns = (
                max(1, round(n0 * seg_len / h))
                if name is not None
                else max(5, round(n0 * seg_len / h))
            )
            tups.append(((0.0, ya, z), (0.0, yb_, z), ns, None, name))

        for i in range(n_sections):
            y0, y1, z = yb[i], yb[i + 1], level(i)
            left = f"p{i}_b" if i > 0 else None  # joins TL from junction i
            right = f"p{i + 1}_a" if i < n_sections - 1 else None
            feed = "feed" if i == center_sec else None

            cur = y0
            if left is not None:
                edge(cur, cur + pe, z, left)
                cur += pe
            body_end = (y1 - pe) if right is not None else y1
            if feed is not None:
                yc = 0.5 * (y0 + y1)
                edge(cur, yc - 0.5 * pe, z, None)
                edge(yc - 0.5 * pe, yc + 0.5 * pe, z, "feed")
                cur = yc + 0.5 * pe
            edge(cur, body_end, z, None)
            cur = body_end
            if right is not None:
                edge(cur, y1, z, right)

        return tups

    def build_network(self):
        # build_wires must run first to populate _tl_length.
        self.build_wires()
        n = int(self.n_cells)
        n_sections = n + 2
        z0 = self.z0
        length = self._tl_length

        # Every port is a distributed (finite-gap) port over its short named
        # edge (issue #477): mesh-stable by construction, so the edges can
        # refine and the ladder is flat at the basis-agreed value.
        ports = {"feed": PortOnWire("feed", distributed=True)}
        branches = []
        # One TL per junction j (1..n_sections-1): connects the right-end
        # port of section j-1 to the left-end port of section j — the
        # half-wave vertical phasing line, now ideal.
        for j in range(1, n_sections):
            a, b = f"p{j}_a", f"p{j}_b"
            ports[a] = PortOnWire(a, distributed=True)
            ports[b] = PortOnWire(b, distributed=True)
            branches.append(TL(a=a, b=b, z0=z0, length=length))

        return Network(
            ports=ports,
            branches=branches,
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )
