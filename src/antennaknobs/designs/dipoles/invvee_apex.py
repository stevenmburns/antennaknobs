"""Inverted-vee fed at its exact apex — no bridge wire (issue #898).

The stock ``dipoles.invvee`` feeds through the short-center-wire idiom:
a 0.1 m bridge between the arm roots carries the delta gap, because a
gap port must live in a wire's interior. That idiom exists for NEC-2's
sake — its sources sit at segment CENTERS, so a vee can only be fed by
giving the vertex a tiny wire to host one. NEC-5 users don't do this:
its sources sit at segment ENDS (knots), so they drive the apex knot
directly (AC6LA, groups.io 2026-08-12). This design is that model —
both arms meet at one point and a `PortAtVertex` inserts the voltage in
series with an arm's connection to it, momwire's series node gap
(momwire#305) / NEC-5's native ``EX`` at the shared knot.

**What the bridge idiom is worth** (the A/B this design exists to make
askable — measured 2026-08-12 at the stock 10 m defaults, free space):
bridge 55.11 − j10.28 Ω vs apex 54.46 − j12.38 Ω. About 2.2 Ω, nearly
all reactance — the bridge's two extra junctions and its 0.1 m of
horizontal wire read as a touch of series capacitance the true vertex
doesn't have. Real, worth knowing, and small enough that the idiom was
never wrong to use; `tests/test_invvee_apex.py` pins both readings so
the gap between the models stays measured rather than remembered.

Engine support is the port's: momwire (all `PortAtVertex` backends) and
NEC-5 natively; NEC-2-shaped engines refuse by name — on this design
that refusal is the honest answer, and the stock ``dipoles.invvee`` IS
the NEC-2 spelling.

Same knobs as the stock invvee (`base`, `length_factor`, `angle_deg`);
arm length runs the full 0.25·λ·length_factor from the vertex (the
stock design's arms start 0.05 m out, at the bridge ends).
"""

import math

from antennaknobs.designs.dipoles.invvee import Builder as InvVee
from antennaknobs.network import Driven, Network, PortAtVertex, Wire


class Builder(InvVee):
    # Same default_params as the stock invvee: the geometry difference is
    # the feed model, not the tuning — keeping the knobs identical is what
    # makes the A/B a one-variable experiment.

    def build_wires(self):
        wavelength = self.design_wavelength
        driver_y = 0.25 * wavelength * self.length_factor
        angle = math.radians(self.angle_deg)
        b = self.base

        apex = (0.0, 0.0, b)
        a_end = (
            0.0,
            driver_y * math.cos(angle),
            b - driver_y * math.sin(angle),
        )
        d_end = (a_end[0], -a_end[1], a_end[2])

        return [
            Wire(apex, a_end, name="arm"),
            Wire(d_end, apex),
        ]

    def build_network(self):
        return Network(
            ports={"apex": PortAtVertex("arm", end="p0")},
            branches=[],
            sources=[Driven(port="apex", voltage=1 + 0j)],
        )
