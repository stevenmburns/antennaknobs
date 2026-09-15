"""AK#1520: what drives bs2's ~0.1 % whole-wire vs split residual beside k3's
end load (measure only).

  PYTHONPATH=<momwire src>:src python scratch/1520-near-end-residual/study_1520.py --mesh
  PYTHONPATH=<momwire src>:src \\
      python scratch/1520-near-end-residual/study_1520.py --out rows.jsonl

The split study's k3 deck: a 10.5 m dipole (0, -5.25, 10) -> (0, 5.25, 10),
radius 1 mm, 14.2 MHz, free space, the feed at 0.31 and 50 ohm series loads at
0.77 and 0.04. `study.py` is the split study's harness, copied from
scratch/1511-bs2-split-study at 4bcf7b2 for its constants and helpers;
`partb_rows.jsonl` is that study's records, for the reproduction check.

Geometries:
  A    the whole wire, each port a PortOnWire at its exact arclength. On bs2 the
       authored count exactly (antennaknobs' positioned-port re-count and parity
       bump suppressed, so every variant keeps the same density). On sinusoidal
       and PyNEC, antennaknobs main's own whole-wire placement (they snap a port
       no count reaches, or re-count), labelled per row.
  B    #1511's split rule as the split study built it (`split_pieces(guard="rule")`,
       asserted equal to `study.split_b`).
  Bp   the same rule with the guard disabled: every end limit is b/3.
  Bg   the guard forced: an end limit is b (not b/3) whenever b is within the
       port's other limits, whatever h is, so the 0.04 piece runs to the wire end
       at every n.

Cases (the 0.31 feed and the 0.77 load in all):
  base    the end port at 0.04 carries its 50 ohm load (the split study's k3).
  moved   the end load at 0.10 instead.
  noload  no port at 0.04: A is the wire with two ports; B keeps base's pieces,
          the 0.04 piece unnamed. Geometry alone.
  short   the 0.04 port carries a 0 ohm load.
"""

from __future__ import annotations

import argparse
import contextlib
import itertools
import json
import math
import re
import shutil
import sys
import time
from pathlib import Path
from types import MappingProxyType

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import study

NS = (41, 81, 161, 321)
CASES = {
    "base": (("end", 0.04, "load"), ("feed", 0.31, "feed"), ("far", 0.77, "load")),
    "moved": (("end", 0.10, "load"), ("feed", 0.31, "feed"), ("far", 0.77, "load")),
    "noload": (("end", 0.04, "none"), ("feed", 0.31, "feed"), ("far", 0.77, "load")),
    "short": (("end", 0.04, "short"), ("feed", 0.31, "feed"), ("far", 0.77, "load")),
}
_SNAP = re.compile(r"([0-9.]+(?:e[-+]?[0-9]+)?) mm away")


def _nearest_odd(v):
    return max(1, 2 * round((v - 1) / 2) + 1)


def split_pieces(ats, n, guard="rule"):
    """#1511's split rule with the guard as the split study built it ("rule"),
    disabled ("off"), or forced to take b whenever b is within the port's other
    limits ("forced"). [(lo, hi, count, index of the port or None)]."""
    h = 1.0 / n
    k = len(ats)
    xs = []
    for i, u in enumerate(ats):
        neigh = []
        if i > 0:
            neigh.append((u - ats[i - 1]) / 4)
        if i < k - 1:
            neigh.append((ats[i + 1] - u) / 4)
        ends = []
        if i == 0:
            ends.append(u)
        if i == k - 1:
            ends.append(1.0 - u)
        limits = list(neigh)
        for j, b in enumerate(ends):
            others = neigh + [e / 3 for jj, e in enumerate(ends) if jj != j]
            other = min(others) if others else math.inf
            if guard == "rule":
                fires = b <= h and b <= other
            elif guard == "off":
                fires = False
            elif guard == "forced":
                fires = b <= other
            else:
                raise ValueError(guard)
            limits.append(b if fires else b / 3)
        xs.append(min(limits))
    pieces, cursor = [], 0.0
    for i, (u, x) in enumerate(zip(ats, xs, strict=True)):
        lo, hi = u - x, u + x
        if lo - cursor > 1e-12:
            pieces.append((cursor, lo, max(1, round((lo - cursor) / h)), None))
        pieces.append((lo, hi, _nearest_odd(2 * x / h), i))
        cursor = hi
    if 1.0 - cursor > 1e-12:
        pieces.append((cursor, 1.0, max(1, round((1.0 - cursor) / h)), None))
    return pieces


def _check_rule_matches_split_study():
    """`split_pieces(guard="rule")` is the split study's `split_b`, piece for piece."""
    ports = (("a", 0.04), ("b", 0.31), ("c", 0.77))
    for n in (10, 21, 41, 81, 161, 321):
        ours = [
            (lo, hi, c, None if i is None else ports[i][0])
            for lo, hi, c, i in split_pieces([u for _p, u in ports], n)
        ]
        assert ours == study.split_b(ports, n), n


def builder(case, geom, n):
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Driven, Load, Network, PortOnWire, Wire, WireSpec

    spec = WireSpec(radius=study.RADIUS)
    ports = CASES[case]
    ats = [u for _name, u, _kind in ports]
    net_ports, branches = {}, []
    if geom == "A":
        wires = [Wire(study.P0, study.P1, n_seg=n, name="w", spec=spec)]
        pieces = [(0.0, 1.0, n, None)]
        for name, u, kind in ports:
            if kind != "none":
                net_ports[name] = PortOnWire(name, wire="w", at=u)
    elif geom in ("AF", "AL"):
        # Amendment 1: split only the feed (AF) or only the loads (AL), with the
        # rule's own pieces for them. Every other port stays at its exact
        # arclength on the unsplit run that contains it.
        h = 1.0 / n
        kept = {
            "AF": {"feed"},
            "AL": {nm for nm, _u, kd in ports if kd in ("load", "short")},
        }[geom]
        merged = []
        for lo, hi, count, i in split_pieces(ats, n, "rule"):
            if i is not None and ports[i][0] in kept:
                merged.append((lo, hi, count, i))
            elif merged and merged[-1][3] is None:
                plo = merged[-1][0]
                merged[-1] = (plo, hi, max(1, round((hi - plo) / h)), None)
            else:
                merged.append((lo, hi, max(1, round((hi - lo) / h)), None))
        pieces = merged
        wires = []
        for j, (lo, hi, count, i) in enumerate(pieces):
            if i is not None:
                wname = f"piece_{ports[i][0]}"
                net_ports[ports[i][0]] = PortOnWire(ports[i][0], wire=wname)
            else:
                inside = [
                    (nm, u)
                    for nm, u, kd in ports
                    if kd != "none" and nm not in kept and lo < u < hi
                ]
                wname = f"run_{j}" if inside else None
                for nm, u in inside:
                    net_ports[nm] = PortOnWire(nm, wire=wname, at=(u - lo) / (hi - lo))
            wires.append(
                Wire(
                    study._point(lo),
                    study._point(hi),
                    n_seg=count,
                    name=wname,
                    spec=spec,
                )
            )
    else:
        guard = {"B": "rule", "Bp": "off", "Bg": "forced"}[geom]
        pieces = split_pieces(ats, n, guard)
        wires = []
        for lo, hi, count, i in pieces:
            name, kind = (ports[i][0], ports[i][2]) if i is not None else (None, None)
            wname = f"piece_{name}" if (name and kind != "none") else None
            wires.append(
                Wire(
                    study._point(lo),
                    study._point(hi),
                    n_seg=count,
                    name=wname,
                    spec=spec,
                )
            )
            if wname:
                net_ports[name] = PortOnWire(name, wire=wname)
    for name, _u, kind in ports:
        if kind == "load":
            branches.append(Load(port=name, r=study.LOAD_R))
        elif kind == "short":
            branches.append(Load(port=name, r=0.0))
    network = Network(ports=net_ports, branches=branches, sources=[Driven(port="feed")])

    class Deck(AntennaBuilder):
        default_params = MappingProxyType(
            {"freq": study.FREQ, "design_freq": study.FREQ}
        )

        def build_wires(self):
            return list(wires)

        def build_network(self):
            return network

    return Deck(), pieces


@contextlib.contextmanager
def authored_count():
    """bs2's A: the authored count exactly (no parity bump, no re-count)."""
    import antennaknobs.engine as eng

    saved = eng.SimulationEngine.__dict__["coerce_n_seg"]
    eng.SimulationEngine.coerce_n_seg = staticmethod(
        lambda n_seg, parity: max(1, int(n_seg))
    )
    try:
        with study.no_site_recount():
            yield
    finally:
        eng.SimulationEngine.coerce_n_seg = saved


def make_engine(engine, b):
    if engine in ("bs2", "sin"):
        from momwire import BSplineSolver, SinusoidalSolver

        from antennaknobs.engines.momwire import MomwireEngine

        return MomwireEngine(
            b, solver=BSplineSolver if engine == "bs2" else SinusoidalSolver
        )
    if engine == "pynec":
        from antennaknobs.engines.pynec import PyNECEngine

        return PyNECEngine(b, ground=None)
    if engine == "nec2":
        from antennaknobs.engines.nec2 import NEC2Engine

        return NEC2Engine(b, ground=None, nec2_exe=shutil.which("nec2c"))
    raise ValueError(engine)


def meshed(eng):
    tups = getattr(eng, "tups", None)
    if tups is not None:
        from antennaknobs.network import as_wire

        return [
            (math.dist(as_wire(t).p0, as_wire(t).p1), int(as_wire(t).n_seg))
            for t in tups
        ]
    return study.meshed_segments(eng)


def runs(have_nec2):
    out = []
    for n in NS:
        for case in CASES:
            for geom in ("A", "B", "Bp", "Bg"):
                out.append(("bs2", case, geom, n))
        for engine in ("sin", "pynec"):
            for case, geoms in (
                ("base", ("A", "B", "Bp", "Bg")),
                ("noload", ("A", "B")),
            ):
                for geom in geoms:
                    out.append((engine, case, geom, n))
        if have_nec2:
            for case in ("base", "noload"):
                out.append(("nec2", case, "B", n))
    return out


def one(engine, case, geom, n, solve):
    b, pieces = builder(case, geom, n)
    exact = engine == "bs2" and geom in ("A", "AF", "AL")
    ctx = authored_count() if exact else contextlib.nullcontext()
    rec = dict(engine=engine, case=case, geometry=geom, n=n)
    rec["authored_pieces"] = [[lo, hi, c, i] for lo, hi, c, i in pieces]
    t0 = time.perf_counter()
    try:
        with ctx:
            eng = make_engine(engine, b)
            segs = meshed(eng)
            rec["meshed"] = [[ln, c] for ln, c in segs]
            rec["segments"] = sum(c for _ln, c in segs)
            rec["cut_ratios"] = [
                max(la / ca, lb / cb) / min(la / ca, lb / cb)
                for (la, ca), (lb, cb) in itertools.pairwise(segs)
            ]
            end_i = next((j for j, p in enumerate(pieces) if p[3] == 0), None)
            rec["end_piece_index"] = end_i
            if solve:
                z = complex(np.atleast_1d(eng.impedance())[0])
                rec["z"] = [z.real, z.imag]
                notes = [
                    a["text"]
                    for a in eng.advisories
                    if a.get("category") == "FeedPlacement"
                ]
                rec["notes"] = notes
                rec["snap_mm"] = [
                    float(m.group(1)) for t in notes if (m := _SNAP.search(t))
                ]
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
    ap.add_argument(
        "--extra", action="store_true", help="Amendment 1's runs only (AF, AL)"
    )
    args = ap.parse_args()
    _check_rule_matches_split_study()
    have_nec2 = shutil.which("nec2c") is not None
    import momwire

    meta = dict(
        _meta=True,
        momwire=str(Path(momwire.__file__).resolve().parent),
        nec2c=shutil.which("nec2c"),
        solve=not args.mesh,
    )
    out = open(args.out, "w") if args.out else None  # noqa: SIM115
    if out:
        out.write(json.dumps(meta) + "\n")
    todo = (
        [("bs2", "base", g, n) for n in NS for g in ("AF", "AL")]
        if args.extra
        else runs(have_nec2)
    )
    for engine, case, geom, n in todo:
        rec = one(engine, case, geom, n, solve=not args.mesh)
        if out:
            out.write(json.dumps(rec) + "\n")
            out.flush()
        z = rec.get("z")
        print(
            f"{engine} {case} {geom} n={n}: {rec['status']} segs={rec.get('segments')} "
            f"pieces={len(rec.get('meshed', []))} ratios={[round(x, 2) for x in rec.get('cut_ratios', [])]} "
            + (f"Z={z[0]:.4f}{z[1]:+.4f}j snap={rec.get('snap_mm')} " if z else "")
            + rec.get("error", ""),
            flush=True,
        )
    if out:
        out.close()


if __name__ == "__main__":
    main()
