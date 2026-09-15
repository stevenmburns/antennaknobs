"""Follow-up probe: what is the razor-vs-NEC-5 tail made of?

    NEC5_EXE=... python scratch/catalog-razor-nec5-bs2/probe_jacket.py

Six of 340 rows in the sweep exceed 5 % and they are three designs. This asks
two questions of them, and the answers are what section 6 of the README reports:

  1. **Is it discretisation?** Solve each on a mesh ladder. Razor and NEC-5 are
     both first order in the mesh, so a discretisation gap SHRINKS as the mesh
     refines. One that does not is a model difference.
  2. **Is it the jacket?** Every one of the three designs defaults to a
     PVC-insulated `wire_type`, and no other catalog design does. Re-solve the
     worst one with the jacket removed and nothing else changed.

Writes its own output; the README quotes it rather than re-deriving it.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import bench_converge as cvg

WORST = ("dipoles.pota_invvee", "dipoles.invvee_catenary", "dipoles.invvee")
LADDER = (21, 41, 81, 161)

# Section 0's table: the designs that falsify the segment-step hypothesis, plus
# the worst row in the study for contrast.
STEP_CASES = (
    "loops.triangular_skyloop",
    "multiband.fandipole",
    "verticals.raised_vertical",
    "verticals.vertical",
    "dipoles.pota_invvee",
)


def source_step(design):
    """(neighbour per-segment length) / (the source's own segment length).

    Only the wires that SHARE AN ENDPOINT with the fed wire count as
    neighbours. A median over every wire longer than the feed -- the first
    version of this -- answers about a trap or a loading gap somewhere else on
    the antenna, not about the source, and made the hypothesis look untestable
    rather than false.
    """
    import statistics

    import numpy as np

    from antennaknobs.engine import _builder_network, as_wire

    b = cvg.load_design(design)()
    b.nominal_nsegs = 21
    ws = [as_wire(t) for t in b.build_wires()]
    seg = [
        float(np.linalg.norm(np.asarray(w.p1) - np.asarray(w.p0))) / max(1, w.n_seg)
        for w in ws
    ]
    net = _builder_network(b)
    port_wires = set()
    if net is not None:
        for port in net.ports.values():
            nm = getattr(port, "wire", None)
            if nm is not None:
                port_wires.add(nm)
    fed = [
        i
        for i, w in enumerate(ws)
        if w.ex is not None or (w.name is not None and w.name in port_wires)
    ]
    best = None
    for i in fed:
        ends = [np.asarray(ws[i].p0, float), np.asarray(ws[i].p1, float)]
        nb = [
            seg[j]
            for j, w in enumerate(ws)
            if j != i
            and any(
                np.allclose(e, np.asarray(q, float), atol=1e-9)
                for e in ends
                for q in (w.p0, w.p1)
            )
        ]
        if not nb:
            continue
        # Razor and NEC-5 both mesh the feed wire EVEN, so the source segment
        # is half the feed wire's own edge.
        r = statistics.median(nb) / (seg[i] / 2.0)
        best = r if best is None else max(best, r)
    return best


def solve(builder, engine, ground="free"):
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import BSplineSolver, RazorSolver

    if engine == "razor":
        eng = MomwireEngine(
            builder,
            solver=RazorSolver,
            solver_kwargs={"nec5_quadrature": True},
            ground=ground,
        )
    elif engine == "bs2":
        eng = MomwireEngine(
            builder,
            solver=BSplineSolver,
            solver_kwargs={"degree": 2},
            ground=ground,
        )
    else:
        from antennaknobs.engines.nec5 import NEC5Engine

        eng = NEC5Engine(builder, ground=ground)
    return eng.impedance()[0]


def fmt(z):
    return f"{z.real:.4f}{z.imag:+.4f}j"


def main():
    warnings.simplefilter("ignore")
    print("=== 0. does the segment-length step at the source predict the gap?\n")
    print(f"    {'design':32s} {'source step':>12s} {'|dX| razor-NEC-5':>18s}")
    for d in STEP_CASES:
        step = source_step(d)
        if step is None:
            print(f"    {d:32s} {'not measurable':>12s}")
            continue
        b = cvg.load_design(d)()
        b.nominal_nsegs = 21
        zr = solve(b, "razor")
        b = cvg.load_design(d)()
        b.nominal_nsegs = 21
        zn = solve(b, "nec5")
        print(f"    {d:32s} {step:9.2f} :1 {abs(zr.imag - zn.imag):17.4f}")
    print()

    print("=== 1. mesh ladder, free space: does the gap converge away?\n")
    for d in WORST:
        cls = cvg.load_design(d)
        print(f"--- {d}")
        print(
            f"{'nseg':>5s} {'segs':>5s} {'razor':>21s} {'nec5':>21s} {'bs2':>21s} "
            f"{'X(razor)-X(nec5)':>18s}"
        )
        for n in LADDER:
            z = {}
            for k in ("razor", "nec5", "bs2"):
                b = cls()
                b.nominal_nsegs = n
                z[k] = solve(b, k)
            print(
                f"{n:5d} {cvg.total_nominal_segs(cls, n):5d} {fmt(z['razor']):>21s} "
                f"{fmt(z['nec5']):>21s} {fmt(z['bs2']):>21s} "
                f"{z['razor'].imag - z['nec5'].imag:18.4f}"
            )
        print()

    print("=== 2. the catalog's insulated designs\n")
    from antennaknobs.cli import list_builtin_designs

    names = list_builtin_designs()
    ins = []
    for d in names:
        dp = cvg.load_design(d).default_params
        dp = dp() if callable(dp) else dp
        wt = dp.get("wire_type")
        if wt and "pvc" in str(wt):
            ins.append((d, wt))
    for d, wt in ins:
        print(f"    {d:36s} {wt}")
    print(f"    {len(ins)} of {len(names)} designs default to a jacketed wire\n")

    print("=== 3. same design, jacket removed, nothing else changed\n")
    cls = cvg.load_design("dipoles.pota_invvee")
    for wt in ("22-awg-pvc", "22-awg"):
        z = {}
        for k in ("razor", "nec5", "bs2"):
            b = cls()
            b.nominal_nsegs = 21
            b.wire_type = wt
            z[k] = solve(b, k)
        rel = abs(z["razor"] - z["nec5"]) / abs(z["nec5"])
        print(
            f"    wire_type={wt:12s} razor={fmt(z['razor']):>21s} "
            f"nec5={fmt(z['nec5']):>21s} bs2={fmt(z['bs2']):>21s} "
            f"dX={z['razor'].imag - z['nec5'].imag:+8.4f}  rel={100 * rel:8.4f}%"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
