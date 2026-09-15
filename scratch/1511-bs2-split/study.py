"""The bs2 split-equivalence study for positioned ports (the #1511 split rule).

  PYTHONPATH=<momwire src>:src python scratch/1511-bs2-split/study.py --mesh
  NEC5_EXE=<nec5cl> PYTHONPATH=<momwire src>:src \\
      python scratch/1511-bs2-split/study.py --out rows.jsonl

One 10.5 m dipole, (0, -5.25, 10) -> (0, 5.25, 10), radius 1 mm, 14.2 MHz, with
k positioned ports: a feed and 50 ohm series loads. PLAN.md registers what is
measured and why. The geometries, all built by hand here (the #1511 code is not
used):

  A   the whole wire, each port a PortOnWire at its exact arclength, meshed as
      antennaknobs' engine meshes it (which may re-count the wire so a port sits
      on the solver's grid, AK#1469).
  A0  control: the same wire with that re-count suppressed, so the wire keeps
      its parity count at the authored n and the port positions are not on
      the grid.
  B   the #1511 split rule: a fed piece centred on each port, fillers between.
  C   break at every port: pieces cut at each port, each port a PortAtVertex at
      the p1 end of the piece before its cut.
  D5  the plain centre-fed wire, no loads: razor-2p against NEC-5 on one mesh.
  Ce  C with every vertex-fed piece authored at an even count, so momwire razor
      (which bumps a named wire to even) and NEC-5 (which exempts a vertex-only
      wire) mesh identical geometry.

Engines: momwire bs2 (A, A0, B), momwire SinusoidalSolver (A, A0, B), momwire
razor-2p (A, A0, C) and NEC-5 (C). Every row records the meshed segment list
and, for B and C, the segment-length ratio at each cut.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import itertools
import json
import math
import os
import re
import time
from pathlib import Path
from types import MappingProxyType

import numpy as np

FREQ = 14.2
P0 = (0.0, -5.25, 10.0)
P1 = (0.0, 5.25, 10.0)
LENGTH = 10.5
RADIUS = 1e-3
GROUND = ("finite", 13.0, 0.005)
LOAD_R = 50.0
NS = (10, 21, 41, 81, 161)
CASES = {
    "k1": (("feed", 1 / 3),),
    "k2": (("feed", 0.31), ("load", 0.77)),
    "k3": (("load_a", 0.04), ("feed", 0.31), ("load_b", 0.77)),
}


# ----------------------------------------------------------------- the rules


def _nearest_odd(v):
    return max(1, 2 * round((v - 1) / 2) + 1)


def split_b(ports, n):
    """The #1511 split rule on the normalised wire: [(lo, hi, count, port)].

    For port i the limits are g/4 per neighbouring port at gap g, and b/3 for an
    end port's wire end at distance b. The guard: for an end limit b, OTHER is
    the smallest of that port's remaining limits (a neighbour's g/4, or for a
    lone port the other end's b'/3); if b <= h and b <= OTHER the limit is b.
    x_i is the smallest limit. The fed piece [u - x, u + x] takes the odd count
    nearest 2x/h (at least 1); fillers take max(1, round(len/h)); a zero-length
    filler is omitted."""
    h = 1.0 / n
    us = [u for _name, u in ports]
    k = len(us)
    xs = []
    for i, u in enumerate(us):
        neigh = []
        if i > 0:
            neigh.append((u - us[i - 1]) / 4)
        if i < k - 1:
            neigh.append((us[i + 1] - u) / 4)
        ends = []
        if i == 0:
            ends.append(u)
        if i == k - 1:
            ends.append(1.0 - u)
        limits = list(neigh)
        for j, b in enumerate(ends):
            others = neigh + [e / 3 for jj, e in enumerate(ends) if jj != j]
            other = min(others) if others else math.inf
            limits.append(b if (b <= h and b <= other) else b / 3)
        xs.append(min(limits))
    pieces = []
    cursor = 0.0
    for (name, u), x in zip(ports, xs, strict=True):
        lo, hi = u - x, u + x
        if lo - cursor > 1e-12:
            pieces.append((cursor, lo, max(1, round((lo - cursor) / h)), None))
        pieces.append((lo, hi, _nearest_odd(2 * x / h), name))
        cursor = hi
    if 1.0 - cursor > 1e-12:
        pieces.append((cursor, 1.0, max(1, round((1.0 - cursor) / h)), None))
    return pieces


def break_c(ports, n):
    """Cut at every port: [(lo, hi, count, port at this piece's p1 or None)]."""
    h = 1.0 / n
    cuts = [u for _name, u in ports]
    names = [name for name, _u in ports]
    edges = [0.0, *cuts, 1.0]
    return [
        (lo, hi, max(1, round((hi - lo) / h)), names[i] if i < len(names) else None)
        for i, (lo, hi) in enumerate(itertools.pairwise(edges))
    ]


# ----------------------------------------------------------------- builders


def _point(frac):
    if frac == 0.0:
        return P0
    if frac == 1.0:
        return P1
    return tuple(float(a + frac * (b - a)) for a, b in zip(P0, P1, strict=True))


def builder(case, geometry, n):
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import (
        Driven,
        Load,
        Network,
        PortAtVertex,
        PortOnWire,
        Wire,
        WireSpec,
    )

    ports = CASES.get(case, ())
    spec = WireSpec(radius=RADIUS)
    if geometry == "D5":
        # D5: the plain centre-fed wire, no loads, for razor-2p against NEC-5 on
        # the same even mesh: their usual centre-fed difference (P4's scale).
        wires = [Wire(P0, P1, n_seg=n, name="w", spec=spec)]
        net_ports = {"feed": PortOnWire("feed", wire="w")}
        pieces = [(0.0, 1.0, n, None)]
        ports = ()
    elif geometry in ("A", "A0"):
        wires = [Wire(P0, P1, n_seg=n, name="w", spec=spec)]
        net_ports = {name: PortOnWire(name, wire="w", at=u) for name, u in ports}
        pieces = [(0.0, 1.0, n, None)]
    elif geometry == "B":
        pieces = split_b(ports, n)
        wires, net_ports = [], {}
        for i, (lo, hi, count, port) in enumerate(pieces):
            wname = f"piece_{port}" if port else None
            wires.append(
                Wire(_point(lo), _point(hi), n_seg=count, name=wname, spec=spec)
            )
            if port:
                net_ports[port] = PortOnWire(port, wire=wname)
            del i
    elif geometry in ("C", "Ce"):
        pieces = break_c(ports, n)
        if geometry == "Ce":
            # Ce: every vertex-fed piece authored at an even count, so an
            # even-parity engine that bumps a named wire (momwire razor) and one
            # that exempts a vertex-only wire (NEC-5) mesh the same geometry.
            pieces = [
                (lo, hi, count + (count % 2) if port else count, port)
                for lo, hi, count, port in pieces
            ]
        wires, net_ports = [], {}
        for lo, hi, count, port in pieces:
            wname = f"before_{port}" if port else None
            wires.append(
                Wire(_point(lo), _point(hi), n_seg=count, name=wname, spec=spec)
            )
            if port:
                net_ports[port] = PortAtVertex(wire=wname, end="p1")
    else:
        raise ValueError(geometry)
    loads = [Load(port=name, r=LOAD_R) for name, _u in ports if name != "feed"]
    network = Network(ports=net_ports, branches=loads, sources=[Driven(port="feed")])

    class Deck(AntennaBuilder):
        default_params = MappingProxyType({"freq": FREQ, "design_freq": FREQ})

        def build_wires(self):
            return list(wires)

        def build_network(self):
            return network

    return Deck(), pieces


@contextlib.contextmanager
def no_site_recount():
    """A0's control: antennaknobs' positioned-port re-count (AK#1469) off."""
    import antennaknobs.engine as eng

    saved = eng.site_count
    eng.site_count = lambda *args, **kwargs: None
    try:
        yield
    finally:
        eng.site_count = saved


# ----------------------------------------------------------------- engines


def make_engine(engine, b, ground, solve=True):
    from momwire import BSplineSolver, RazorSolver, SinusoidalSolver

    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.engines.nec5 import NEC5Engine

    if engine == "bs2":
        return MomwireEngine(b, solver=BSplineSolver, ground=ground)
    if engine == "sin":
        return MomwireEngine(b, solver=SinusoidalSolver, ground=ground)
    if engine == "razor":
        return MomwireEngine(
            b,
            solver=RazorSolver,
            solver_kwargs={"nec5_quadrature": True},
            ground=ground,
        )
    if engine == "nec5":
        return NEC5Engine(b, ground=ground, require_exe=solve)
    raise ValueError(engine)


def meshed_segments(eng):
    """The meshed wire, p0 -> p1, as [(length_m, count)] per straight piece."""
    tups = getattr(eng, "tups", None)
    if tups is not None:
        from antennaknobs.network import as_wire

        out = []
        for t in tups:
            w = as_wire(t)
            out.append((math.dist(w.p0, w.p1), int(w.n_seg)))
        return out
    out = []
    for pl, counts in zip(eng._polylines, eng._edge_segments, strict=True):
        poly = np.asarray(pl)
        lengths = np.linalg.norm(np.diff(poly, axis=0), axis=1)
        if poly[0][1] > poly[-1][1]:  # walked P1 -> P0: report p0 -> p1
            lengths, counts = lengths[::-1], list(counts)[::-1]
        out += [(float(ln), int(c)) for ln, c in zip(lengths, counts, strict=True)]
    return out


def junction_ratios(segments):
    """At each interior cut, the larger adjacent segment over the smaller."""
    return [
        max(la / ca, lb / cb) / min(la / ca, lb / cb)
        for (la, ca), (lb, cb) in itertools.pairwise(segments)
    ]


_OFFSET = re.compile(r"([0-9.]+(?:e[-+]?[0-9]+)?) mm away")


def offsets_mm(eng):
    notes = [a for a in eng.advisories if a.get("category") == "FeedPlacement"]
    return [
        {
            "text": a["text"],
            "offset_mm": float(m.group(1))
            if (m := _OFFSET.search(a["text"]))
            else None,
        }
        for a in notes
    ]


PLAN_RUNS = (
    ("bs2", ("A", "A0", "B")),
    ("sin", ("A", "A0", "B")),
    ("razor", ("A", "A0", "C", "Ce")),
    ("nec5", ("C", "Ce")),
)


def runs():
    for gname, ground in (("free", None), ("somm13", GROUND)):
        for n in NS:
            for engine in ("razor", "nec5"):
                yield "d5", gname, ground, n, engine, "D5"
    for case in CASES:
        grounds = [("free", None)]
        if case == "k2":
            grounds.append(("somm13", GROUND))
        for gname, ground in grounds:
            for n in NS:
                for engine, geoms in PLAN_RUNS:
                    for geom in geoms:
                        yield case, gname, ground, n, engine, geom


def one(case, gname, ground, n, engine, geom, solve):
    b, pieces = builder(case, geom, n)
    ctx = no_site_recount() if geom == "A0" else contextlib.nullcontext()
    rec = dict(case=case, ground=gname, n=n, engine=engine, geometry=geom)
    rec["authored_pieces"] = [[lo, hi, c, p] for lo, hi, c, p in pieces]
    t0 = time.perf_counter()
    try:
        with ctx:
            eng = make_engine(engine, b, ground, solve)
            segs = meshed_segments(eng)
            rec["meshed"] = [[ln, c] for ln, c in segs]
            rec["junction_ratios"] = (
                junction_ratios(segs) if geom in ("B", "C", "Ce") else []
            )
            if solve:
                z = complex(np.atleast_1d(eng.impedance())[0])
                rec["z"] = [z.real, z.imag]
                rec["placements"] = offsets_mm(eng)
        rec["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 - one refused run is a recorded row
        rec["status"] = "error"
        rec["error"] = f"{type(exc).__name__}: {exc}"[:400]
    rec["secs"] = round(time.perf_counter() - t0, 3)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", action="store_true", help="mesh only, no solve")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--only", default="", help="comma list of case:ground:n filters")
    args = ap.parse_args()
    import momwire

    exe = os.environ.get("NEC5_EXE", "")
    meta = dict(
        _meta=True,
        momwire=str(Path(momwire.__file__).resolve().parent),
        momwire_version=getattr(momwire, "__version__", "?"),
        nec5_exe=exe,
        nec5_sha256=hashlib.sha256(Path(exe).read_bytes()).hexdigest() if exe else None,
        solve=not args.mesh,
    )
    filt = [f.split(":") for f in args.only.split(",") if f]
    out = open(args.out, "w") if args.out else None  # noqa: SIM115
    if out:
        out.write(json.dumps(meta) + "\n")
    for case, gname, ground, n, engine, geom in runs():
        if filt and not any(
            (not c or c == case) and (not g or g == gname) and (not m or int(m) == n)
            for c, g, m in filt
        ):
            continue
        if engine == "nec5" and not args.mesh and not exe:
            continue
        rec = one(case, gname, ground, n, engine, geom, solve=not args.mesh)
        line = json.dumps(rec)
        if out:
            out.write(line + "\n")
            out.flush()
        z = rec.get("z")
        print(
            f"{case} {gname} n={n} {engine}/{geom}: {rec['status']} "
            f"segs={sum(c for _l, c in rec.get('meshed', []))} "
            f"pieces={len(rec.get('meshed', []))} "
            f"ratios={[round(r, 2) for r in rec.get('junction_ratios', [])]} "
            + (f"Z={z[0]:.4f}{z[1]:+.4f}j " if z else "")
            + (
                f"offsets={[p['offset_mm'] for p in rec.get('placements', [])]} "
                if rec.get("placements")
                else ""
            )
            + (rec.get("error", "") if rec["status"] != "ok" else ""),
            flush=True,
        )
    if out:
        out.close()


if __name__ == "__main__":
    main()
