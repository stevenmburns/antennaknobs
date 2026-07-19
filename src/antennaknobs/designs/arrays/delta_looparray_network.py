"""delta_looparray driven by two TLs from a central virtual driver.

Same antenna geometry as `delta_looparray_with_tls` (two slanted delta loops
spaced along y), driven the same way (two Z0=100 transmission lines from a
single driver, lengths set by `twist`). The difference: this Builder uses
the new port-based network spec (`build_network()`), so

  - there is no dummy `WWW`-`WW` stub wire in `build_wires()`,
  - the loop feed edges are named (`"loop1"`, `"loop2"`),
  - the central driver is a `PortVirtual` — exists only as a row/column
    in the network Y matrix during the nodal reduction.

MomwireEngine produces the same impedance as `delta_looparray_with_tls` to
numerical precision; the showcase for the network-spec API in #65.
"""

from antennaknobs import AntennaBuilder, Transform, TransformStack
from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL

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
        wavelength = 299.792458 / self.design_freq
        driver = wavelength * self.length_factor
        angle = math.radians(self.angle_deg)
        cos_t = math.cos(angle)
        tan_t = math.tan(angle)

        def build_path(lst, ns, ex, name=None):
            pairs = list(zip(lst[:-1], lst[1:]))
            for i, (a, c) in enumerate(pairs):
                # Only the centre feed-edge of the gap gets the name.
                yield (a, c, ns, ex, name if i == 0 and len(pairs) == 1 else None)

        def ry(p):
            return p[0], -p[1], p[2]

        n_seg0 = self.nominal_nsegs

        # y of the top corner (half the top-edge width), in closed form.
        y = (cos_t * (driver - 2 * eps) + 2 * eps) / (2 * (cos_t + 1))
        S = (0, eps, b - (y - eps) * tan_t)
        A = (0, y, b)
        B, T = ry(A), ry(S)

        n_seg1 = self.segs_for(math.dist(T, S), math.dist(S, A))

        st = TransformStack()
        st.push(Transform.translate(0, 0, b))
        st.push(Transform.rotX(-self.slant_deg))
        st.push(Transform.translate(0, self.del_y, -b))
        SS, AA, BB, TT = st.hit(S), st.hit(A), st.hit(B), st.hit(T)
        SSS, AAA, BBB, TTT = ry(SS), ry(AA), ry(BB), ry(TT)

        tups = []
        # Loop 1: SS → AA → BB → TT perimeter (no feed), then TT → SS named.
        tups.extend(build_path([SS, AA, BB, TT], n_seg0, None))
        tups.extend(build_path([TT, SS], n_seg1, None, name="loop1"))
        # Loop 2: mirror.
        tups.extend(build_path([SSS, AAA, BBB, TTT], n_seg0, None))
        tups.extend(build_path([SSS, TTT], n_seg1, None, name="loop2"))
        return tups

    def build_network(self):
        wavelength = 299.792458 / self.design_freq
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
