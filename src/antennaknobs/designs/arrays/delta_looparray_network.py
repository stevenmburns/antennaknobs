"""delta_looparray driven by two TLs from a central virtual driver.

Same antenna geometry as the legacy `build_tls` variant (two slanted delta
loops spaced along y), driven the same way (two Z0=100 transmission lines from a
single driver, lengths set by `twist`). That legacy Builder now lives only as a
test oracle at `tests/fixtures/delta_looparray_with_tls.py` (it is not a catalog
design). This Builder is the canonical version: it uses the port-based network
spec (`build_network()`), so

  - there is no dummy `WWW`-`WW` stub wire in `build_wires()`,
  - the loop feed edges are named (`"loop1"`, `"loop2"`),
  - the central driver is a `PortVirtual` — exists only as a row/column
    in the network Y matrix during the nodal reduction.

The geometry is authored with the `Cell`/`Placement` hierarchy (the geometry
analog of `Composite`/`Instance`): one delta-loop `Cell` is stamped twice, and
the formal feed name `"feed"` is renamed to `"loop1"`/`"loop2"` by the
placement map — the single source of truth `build_network()` binds its ports
to. The two placements are a mirror pair across y = 0, but expressed as pure
placement rather than an explicit `ry` on the geometry: loop2 negates both the
y-offset (`-del_y`) and the slant. Negating the slant is what keeps it a true
reflection at any tilt — a y-mirror conjugates the tilt (`ry . rotX(-s) . ry =
rotX(+s)`). Combined with the base loop's own y-reflection symmetry, this
reproduces the legacy mirror construction edge-for-edge (including the fed
edge) for every `slant_deg`, not just the default 0.

MomwireEngine produces the same impedance as the legacy `build_tls` fixture to
numerical precision; the showcase for the network-spec API in #65.
"""

from antennaknobs import (
    AntennaBuilder,
    Cell,
    Placement,
    Transform,
    flatten_placements,
)
from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL, Wire

import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            "length_factor": 1.0664,
            "angle_deg": 61.2377,
            "slant_deg": 0.0,
            "twist": 0.125,
            "del_y": 4.0,
        }
    )

    def build_wires(self):
        eps = 0.05
        b = self.base
        wavelength = self.design_wavelength
        driver = wavelength * self.length_factor
        angle = math.radians(self.angle_deg)
        cos_t = math.cos(angle)
        tan_t = math.tan(angle)

        def ry(p):
            return p[0], -p[1], p[2]

        # One delta loop in LOCAL coordinates, symmetric about y = 0: the
        # bottom edge T → S is the named feed, the other three edges close the
        # loop. y is the top-corner half-width in closed form.
        y = (cos_t * (driver - 2 * eps) + 2 * eps) / (2 * (cos_t + 1))
        S = (0, eps, b - (y - eps) * tan_t)
        A = (0, y, b)
        B, T = ry(A), ry(S)
        loop = Cell(
            feeds=("feed",),
            wires=[
                Wire(S, A),
                Wire(A, B),
                Wire(B, T),
                Wire(T, S, name="feed"),
            ],
        )

        # Element pose: raise by the base height, apply the slant, shift along
        # y. The two loops are a mirror pair across y = 0, expressed as pure
        # placement: loop2 negates BOTH the y-offset and the slant. Negating
        # the slant is what makes it a true reflection at any tilt — a y-mirror
        # conjugates the tilt, ry . rotX(-s) . ry = rotX(+s), so the reflected
        # loop is tilted the opposite way. The placement map renames the formal
        # "feed" edge to the per-loop actual build_network() binds a port to.
        def pose(dy, slant):
            return (
                Transform.translate(0, 0, b)
                .postmult(Transform.rotX(-slant))
                .postmult(Transform.translate(0, dy, -b))
            )

        return flatten_placements(
            [
                Placement("loop1", loop, pose(self.del_y, self.slant_deg), feed="loop1"),
                Placement("loop2", loop, pose(-self.del_y, -self.slant_deg), feed="loop2"),
            ]
        )

    def build_network(self):
        wavelength = self.design_wavelength
        tl_lengths = (
            self.del_y - wavelength * self.twist,
            self.del_y + wavelength * self.twist,
        )
        return Network(
            ports={
                "loop1": PortOnWire("loop1"),
                "loop2": PortOnWire("loop2"),
                "driver": PortVirtual("driver"),
            },
            branches=[
                TL(a="driver", b="loop1", z0=100.0, length=tl_lengths[0]),
                TL(a="driver", b="loop2", z0=100.0, length=tl_lengths[1]),
            ],
            sources=[Driven(port="driver", voltage=1 + 0j)],
        )
