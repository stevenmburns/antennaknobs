r"""80 m triangular skyloop run on 17 m, matched to 50 Ω with an L-network —
the `Shunt`-branch showcase for issue #65 (Q2, shunt-to-common).

Geometry is inherited wholesale from `triangular_skyloop`: the same corner-fed
equilateral full-wave loop, flown with the `Drone` and meshed off
`nominal_nsegs`. Cut for 80 m (~85 m perimeter, 1 λ at 3.8 MHz) but operated on
the 17 m band (18.1 MHz), that perimeter is ~4.7 λ and the corner feed is
wildly reactive (~225 − 70j here), nowhere near 50 Ω — the classic "loop +
tuner" multiband situation.

An **L-match** fixes it with two reactive elements. Because R_load > 50 Ω the
network is a shunt across the antenna feed plus a series element to the source:

    source ──[ series TwoPort: L ]── feed
                                      │
                              [ Shunt: C ]── common

The port spec drives a virtual `in` node, runs a series `TwoPort(in→feed)`, and
puts a `Shunt` across `feed` to the common reference; the impedance read at `in`
is the matched input Z. Stock values land it at ~50 Ω / SWR ≈ 1.0 at 18.1 MHz;
retune `series_L_uH` / `shunt_C_pF` for other bands or a different loop.

`Shunt` — a lumped R/L/C from a single port to the common reference — is the
element issue #65 deferred as Q2. A matching network was the motivating use
case; this design is it. The showcase is the impedance/SWR transform, which
the reducer computes exactly on top of the extracted antenna Y. The stock
coil has Q = 200 (`coil_q = 0` recovers the ideal one); unlike the
inverted-L's high-Q tee this match runs modest circulating current, so the
coil burns only ~1 % of the input power — visible in the power-budget
readout rather than dominating it.
"""

from types import MappingProxyType

from antennaknobs.designs.loops.triangular_skyloop import Builder as TriangularSkyloop
from antennaknobs.network import (
    Driven,
    Instance,
    Network,
    PortOnWire,
    PortVirtual,
)
from antennaknobs.station import l_network_tuner


class Builder(TriangularSkyloop):
    default_params = MappingProxyType(
        {
            **TriangularSkyloop.default_params,
            # Loop is cut for 80 m (inherited design_freq) but operated on 17 m.
            "freq": 18.1,
            # L-match elements, tuned for ~50 Ω at 18.1 MHz on the stock
            # loop WITH the stock Q=200 coil (the ESR barely moves this
            # match — the loop's feed R needs no big virtual-resistance
            # ride, unlike inverted_l_tmatch's tee).
            "series_L_uH": 0.870,  # series arm, input → feed (TwoPort)
            "shunt_C_pF": 60.01,  # shunt arm, across the feed (Shunt)
            # Coil quality factor (issue #298): adds R = ωL/Q in series with
            # the matching inductor. Real air-wound coils run ~50–400;
            # default 200 matches the other tuner designs (0 = ideal coil
            # is still reachable, but a lossless matchbox hides the whole
            # power-budget readout).
            "coil_q": 200.0,
            "ui_params": MappingProxyType(
                {
                    # Matched to 50 Ω, so the SWR readout shows ~1:1.
                    "target_z0": 50.0,
                    "default_view": "xy",
                    "coil_q": {"min": 0.0, "max": 400.0},
                    # Display names for the power-budget rows (issue #489).
                    # Keys are the STRUCTURAL labels the solver emits —
                    # keep in sync with the "match" instance in
                    # build_network below.
                    "budget_labels": {
                        "match: TwoPort in→feed": "series coil",
                        "match: Shunt feed": "shunt cap",
                    },
                }
            ),
        }
    )

    def build_wires(self):
        # Reuse the corner-fed triangular_skyloop geometry verbatim; only rename
        # the driven chamfer as the network's "feed" port and clear its inline
        # excitation, since the L-match network supplies the source at the
        # virtual `in` node instead.
        wires = []
        for p0, p1, nseg, ex, *rest in super().build_wires():
            wires.append(
                (p0, p1, nseg, None, "feed") if ex is not None else (p0, p1, nseg, ex)
            )
        return wires

    def build_network(self):
        r"""L-match, stamped LITERALLY at whatever the sliders say: the MNA
        core (issue #285) handles the degenerate endpoints as physics, not
        special cases — a 0 H series arm is an ideal wire (Group-2 short
        identifying `in` with `feed`) and a 0 F shunt arm is an open (no
        element). With both arms zero the matchbox is fully inert — a
        pass-through — and the input impedance is just the bare antenna's
        (Z_in = Z_ant). `coil_q > 0` gives the series inductor a finite Q
        (R = ωL/Q, issue #298), turning the matchbox lossy the way a real
        tuner is; 0 keeps the ideal coil."""
        return Network(
            ports={"feed": PortOnWire("feed"), "in": PortVirtual("in")},
            branches=[
                Instance(
                    "match",
                    l_network_tuner(
                        series_l_uH=self.series_L_uH,
                        shunt_c_pF=self.shunt_C_pF,
                        ql=self.coil_q if self.coil_q > 0 else None,
                    ),
                    rig="in",
                    out="feed",
                ),
            ],
            sources=[Driven(port="in", voltage=1 + 0j)],
        )
