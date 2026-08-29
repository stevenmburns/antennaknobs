"""Dense convergence ladder on Roy's coupled-loop model: EVERY k = 1..16.

Engines and spellings (all post-#518, geometry verified):
  sin-nec2   : SinusoidalSolver, 6-wire deck geometry, NEC-2 segment source
               at arc 280 - 10/k (the segment ending at the z=20 gap knot)
  bs1 / bs2  : BSplineSolver d1/d2, split-at-gap node-gap drive (the seam's
               normal form), junction list CORRECT (wire 6 present)
  razor-nec5 : RazorSolver nec5_quadrature, 6-wire, knot feed at arc 280
               (refuses k=1: wire 6's single segment)
  nec5cl     : the licensed binary if found ($NEC5CL or the default path),
               skipped gracefully otherwise

Writes results-dense.json next to this script, same schema as results.json:
  {engine: {str(k): [Re I_src, Im I_src, max loop element |I|]}}
Run from any machine with the momwire venv:  python ladder_dense.py
"""

import json
import os
import subprocess
from pathlib import Path

import numpy as np
from momwire.bspline import BSplineSolver
from momwire.razor import RazorSolver
from momwire.sinusoidal import SinusoidalSolver

MHZ = 0.0005
WL = 299.8 / MHZ
V = -404675.9j
RADIUS = 0.005
HERE = Path(__file__).parent
KS = list(range(1, 17))

W = [
    ((20, -40, 300), (20, -40, 0), 15),
    ((40, -40, 0), (40, 40, 0), 4),
    ((40, 40, 0), (-40, 40, 0), 4),
    ((-40, 40, 0), (-40, -40, 0), 4),
    ((-40, -40, 0), (20, -40, 0), 3),
    ((20, -40, 0), (40, -40, 0), 1),
]
J6 = [
    [(0, "end"), (4, "end"), (5, "start")],
    [(5, "end"), (1, "start")],
    [(1, "end"), (2, "start")],
    [(2, "end"), (3, "start")],
    [(3, "end"), (4, "start")],
]
J7 = [
    [(0, "end"), (1, "start")],
    [(1, "end"), (6, "start"), (5, "end")],
    [(6, "end"), (2, "start")],
    [(2, "end"), (3, "start")],
    [(3, "end"), (4, "start")],
    [(4, "end"), (5, "start")],
]


def wires6(k):
    return ([np.array([a, b], float) for a, b, _ in W], [[n * k] for _, _, n in W])


def loop_max(solver, coeffs, skip):
    knots = solver.currents_at_knots(coeffs)
    return max(
        float(np.max(np.abs(0.5 * (np.asarray(c)[:-1] + np.asarray(c)[1:]))))
        for c in knots[skip:]
    )


def run_sin(k):
    ws, npe = wires6(k)
    s = SinusoidalSolver(
        wires=ws,
        n_per_edge_per_wire=npe,
        feeds=[(0, 280.0 - 10.0 / k, 0j)],
        junctions=J6,
        wire_radius=RADIUS,
        wavelength=WL,
    )
    sol = s.compute_port_solution()
    i = complex(sol.y[0, 0]) * V
    return i, loop_max(s, sol.coeffs @ np.array([V]), 1)


def run_bs(k, degree):
    ws = [
        np.array([(20, -40, 300), (20, -40, 20)], float),
        np.array([(20, -40, 20), (20, -40, 0)], float),
    ]
    npe = [[14 * k], [1 * k]]
    for a, b, n in W[1:]:
        ws.append(np.array([a, b], float))
        npe.append([n * k])
    s = BSplineSolver(
        wires=ws,
        n_per_edge_per_wire=npe,
        feeds=[],
        node_gaps=[(0, "end", 0j)],
        junctions=J7,
        degree=degree,
        wire_radius=RADIUS,
        wavelength=WL,
    )
    sol = s.compute_port_solution()
    i = complex(sol.y[0, 0]) * V
    return i, loop_max(s, sol.coeffs @ np.array([V]), 2)


def run_razor(k):
    ws, npe = wires6(k)
    s = RazorSolver(
        wires=ws,
        n_per_edge_per_wire=npe,
        feeds=[(0, 280.0, 0j)],
        wire_radius=RADIUS,
        wavelength=WL,
        nec5_quadrature=True,
    )
    sol = s.compute_port_solution()
    i = complex(sol.y[0, 0]) * V
    return i, loop_max(s, sol.coeffs @ np.array([V]), 1)


def nec5cl_path():
    p = Path(
        os.environ.get(
            "NEC5CL", Path.home() / "antennas/NEC5-downloads/nec5-linux/nec5cl"
        )
    )
    return p if p.exists() else None


def run_nec5cl(k, binary, room):
    lines = ["CM dense ladder", "CE"]
    for t, (a, b, n) in enumerate(W, start=1):
        lines.append(
            f"GW {t},{n * k},{a[0]}.,{a[1]}.,{a[2]}.,{b[0]}.,{b[1]}.,{b[2]}.,{RADIUS}"
        )
    lines += [
        "GE 0,-1",
        f"FR 0,1,0,0,{MHZ}",
        "GN -1",
        f"EX 0,1,{14 * k},0,0.,-404675.9",
        "PQ 0",
        "XQ 0",
        "EN",
    ]
    d = room / f"k{k}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "deck.nec").write_text("\n".join(lines) + "\n")
    subprocess.run(
        [str(binary), "deck.nec", "out.txt"], cwd=d, capture_output=True, timeout=600
    )
    i_src = lm = None
    in_table = False
    for line in (d / "out.txt").read_text(encoding="latin-1").splitlines():
        p = line.split()
        if len(p) >= 9 and p[0] == "1" and p[1] == str(14 * k) and i_src is None:
            i_src = complex(float(p[5]), float(p[6]))
        if "Wire Currents" in line:
            in_table = True
            continue
        if "Charge Dens" in line:
            in_table = False
        if in_table and len(p) >= 10 and p[0].isdigit() and int(p[1]) >= 2:
            lm = float(p[8]) if lm is None else max(lm, float(p[8]))
    return i_src, lm


def main():
    out_path = HERE / "results-dense.json"
    out = json.loads(out_path.read_text()) if out_path.exists() else {}
    binary = nec5cl_path()
    room = HERE / "dense-nec5-room"
    engines = [
        ("sin-nec2", run_sin),
        ("bs1", lambda k: run_bs(k, 1)),
        ("bs2", lambda k: run_bs(k, 2)),
        ("razor-nec5", run_razor),
    ]
    if binary:
        engines.append(("nec5cl", lambda k: run_nec5cl(k, binary, room)))
    else:
        print("nec5cl binary not found - skipping that engine")
    for name, fn in engines:
        out.setdefault(name, {})
        for k in KS:
            if str(k) in out[name]:
                continue
            try:
                i, lm = fn(k)
            except Exception as e:  # noqa: BLE001 — probe harness — a failing case is recorded and the sweep continues
                print(f"{name} k={k}: {type(e).__name__}: {str(e)[:80]}", flush=True)
                continue
            out[name][str(k)] = [i.real, i.imag, lm]
            print(
                f"{name} k={k:2d}: X = {(V / i).imag / 1e3:9.3f} kOhm  loop {lm:.4f} A",
                flush=True,
            )
            out_path.write_text(json.dumps(out, indent=1))
    print("written", out_path)


if __name__ == "__main__":
    main()
