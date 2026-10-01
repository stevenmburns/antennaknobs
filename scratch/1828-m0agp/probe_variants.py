"""Which unstated model details move the M0AGP reproduction (AK#1828)?

Runs reproduce.py's resonate-and-read at 70 ft and 20 ft of vertical section
under one change at a time, on one engine: the mesh density, the radials
turned parallel to the top wire, a 1 m feed gap, and the frequency. A probe,
not a gate: the catalog design is not changed by any of it.

Usage: python probe_variants.py ENGINE
"""

from __future__ import annotations

import math
import sys

import reproduce as rp

from antennaknobs.cli import make_engine_factory, parse_ground
from antennaknobs.designs.verticals import inverted_l
from antennaknobs.network import Wire

ORIG = inverted_l.Builder.build_wires
# The design's own geometry before meshing (the class wraps build_wires in
# auto_mesh; a replacement must mesh its own result the same way).
RAW = ORIG.__wrapped__


def radials_along_top(self):
    """The radials turned 90 degrees: along +y and -y, the top wire's axis."""
    out = []
    for w in RAW(self):
        p0, p1 = w[0], w[1]
        flat = abs(p0[2] - p1[2]) < 1e-12 and abs(p0[2] - self.base) < 1e-12
        if flat and abs(p1[0]) > 1e-9 or (flat and abs(p1[1]) > 1e-9 and p1[0] != 0.0):
            r = math.hypot(p1[0], p1[1])
            a = math.atan2(p1[1], p1[0]) + math.pi / 2
            out.append(Wire(p0, (r * math.cos(a), r * math.sin(a), p1[2])))
        else:
            out.append(w)
    return self.auto_mesh(out)


def gap(eps):
    def build(self):
        out = RAW(self)
        z = self.base
        fixed = []
        for w in out:
            if w.ex is not None:
                fixed.append(Wire((0.0, 0.0, z), (0.0, 0.0, z + eps), ex=w.ex))
            elif w[0] == (0.0, 0.0, z + 0.05):
                fixed.append(Wire((0.0, 0.0, z + eps), w[1]))
            else:
                fixed.append(w)
        return self.auto_mesh(fixed)

    return build


def run(label, factory, **set_freq):
    v = rp.resonate_vertical(factory)
    ref = rp.read(factory, v, 0.0)
    line = [f"{label:<22} vertical {v:6.2f} ft"]
    for vert in (70, 20):
        h = rp.resonate_top(factory, vert)
        got = rp.read(factory, vert, h)
        rel = {m: got[m] - ref[m] for m in ("az0", "az90", "MEAN_AZ")}
        line.append(
            f"{vert} ft (top {h:6.2f}): az0 {rel['az0']:+.2f} az90 {rel['az90']:+.2f} "
            f"mean {rel['MEAN_AZ']:+.2f} [M0AGP {rp.TABLE[vert]:+.2f}]"
        )
    print("  ".join(line), flush=True)


def main():
    engine = sys.argv[1]
    g = parse_ground("finite")
    run("baseline", make_engine_factory(engine, g))
    run("nominal_nsegs 63", make_engine_factory(engine, g, nominal_nsegs=63))
    inverted_l.Builder.build_wires = radials_along_top
    run("radials along top", make_engine_factory(engine, g))
    inverted_l.Builder.build_wires = gap(1.0)
    run("feed gap 1 m", make_engine_factory(engine, g))
    inverted_l.Builder.build_wires = ORIG
    for f in (1.80, 1.85):
        orig_builder = rp.builder

        def at(vert_ft, horiz_ft, f=f, orig_builder=orig_builder):
            b = orig_builder(vert_ft, horiz_ft)
            b.freq = f
            return b

        rp.builder = at
        run(f"freq {f} MHz", make_engine_factory(engine, g))
        rp.builder = orig_builder


if __name__ == "__main__":
    main()
