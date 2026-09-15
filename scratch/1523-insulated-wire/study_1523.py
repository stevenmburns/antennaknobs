"""AK#1523: a centre-fed dipole in free space, bare and jacketed, under the two
insulated-wire treatments, on bs2, razor-2p and NEC-5 (measure only).

  PYTHONPATH=<momwire src>:src python scratch/1523-insulated-wire/study_1523.py --mesh
  NEC5_EXE=<nec5cl> PYTHONPATH=<momwire src>:src \\
      python scratch/1523-insulated-wire/study_1523.py --out scratch/1523-insulated-wire/rows.jsonl

The deck: a straight wire along y centred at (0, 0, 10), fed at its centre by a
PortOnWire delta gap, 14.2 MHz, free space, perfect conductor. Nominal counts
41 and 161; each engine meshes its own parity, and the meshed count is recorded.

Treatments (no engine is changed; the harness does the swapping):
  bare    no jacket.
  pair    momwire as it is: kernel radius a', L' at a. NEC-5 with the GW radius
          set to momwire's `equivalent_radius` after the engine has built its
          LD 2 card at a.
  lonly   momwire with `momwire._wire_loading.equivalent_radius` returning the
          conductor radius, so the kernel keeps a. NEC-5 as it is.

Every solved row reads back what the solve used: the kernel and conductor radii
of the solver the momwire engine made, and the GW radius and LD 2 value of the
deck NEC-5 ran.

Per row: the resonant length (secant on X from a start pair, stopping at
|X| <= 1e-4 ohm, at most 14 solves) and Z at L0, bs2's bare resonant length at
161 for that conductor. Bare rows run first, and bs2 bare at 161 first of all.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import MappingProxyType

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jackets import BARE, FREQ_MHZ, JACKETS, bare_of

NS = (41, 161)
FINE = 161
ENGINES = ("bs2", "razor", "nec5")
TREATMENTS = ("pair", "lonly")
LAMBDA = 299792458.0 / (FREQ_MHZ * 1e6)
X_TOL = 1e-4
MAX_SOLVES = 14
HEIGHT = 10.0


def builder(length, spec, n):
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Driven, Network, PortOnWire, Wire

    half = length / 2.0
    wires = [
        Wire((0.0, -half, HEIGHT), (0.0, half, HEIGHT), n_seg=n, name="w", spec=spec)
    ]
    network = Network(
        ports={"feed": PortOnWire("feed", wire="w")},
        branches=[],
        sources=[Driven(port="feed")],
    )

    class Deck(AntennaBuilder):
        default_params = MappingProxyType({"freq": FREQ_MHZ, "design_freq": FREQ_MHZ})

        def build_wires(self):
            return list(wires)

        def build_network(self):
            return network

    return Deck()


def spec_for(name, treatment):
    from antennaknobs.network import WireSpec

    if treatment == "bare":
        return WireSpec(radius=BARE[name])
    a, b, eps = JACKETS[name]
    return WireSpec(radius=a, insulation_radius=b, insulation_eps_r=eps)


@contextlib.contextmanager
def kernel_at_conductor(active):
    """momwire's a' swap suppressed: `equivalent_radius` returns a."""
    if not active:
        yield
        return
    import momwire._wire_loading as wl

    saved = wl.equivalent_radius
    wl.equivalent_radius = lambda radius, ins_radius, eps_r: float(radius)
    try:
        yield
    finally:
        wl.equivalent_radius = saved


def deck_fields(deck):
    if deck is None:
        return {"error": "no deck captured"}
    gw, segs, ld2 = [], [], []
    for line in deck.splitlines():
        f = line.split()
        if f[:1] == ["GW"]:
            gw.append(f[-1])
            segs.append(int(f[2]))
        elif f[:2] == ["LD", "2"]:
            ld2.append(f[6])
    return {"gw_radius": gw, "gw_segments": segs, "ld2_l": ld2}


def meshed_count(eng):
    if hasattr(eng, "_cards"):
        return int(sum(c[3] for c in eng._cards))
    return int(sum(sum(c) for c in eng._edge_segments))


class Probe:
    """One (conductor or jacket, treatment, engine, n): Z at a length, keeping
    the read-back of the last solve."""

    def __init__(self, name, treatment, engine, n, solve):
        self.name, self.treatment, self.engine, self.n = name, treatment, engine, n
        self.spec = spec_for(name, treatment)
        self.solve = solve
        self.readback = None
        self.meshed = None

    def build(self, length):
        from momwire import BSplineSolver, RazorSolver, equivalent_radius

        from antennaknobs.engines.momwire import MomwireEngine
        from antennaknobs.engines.nec5 import NEC5Engine

        b = builder(length, self.spec, self.n)
        if self.engine == "nec5":
            eng = NEC5Engine(b, ground=None, require_exe=self.solve)
            if self.treatment == "pair":
                a_eq = equivalent_radius(*JACKETS[self.name])
                eng._radii = [a_eq for _ in eng._radii]
            return eng
        if self.engine == "bs2":
            return MomwireEngine(b, solver=BSplineSolver, ground=None)
        return MomwireEngine(
            b,
            solver=RazorSolver,
            solver_kwargs={"nec5_quadrature": True},
            ground=None,
        )

    def z_at(self, length):
        made = []
        lonly_momwire = self.engine != "nec5" and self.treatment == "lonly"
        with kernel_at_conductor(lonly_momwire):
            eng = self.build(length)
            self.meshed = meshed_count(eng)
            if not self.solve:
                self.readback = (
                    deck_fields(eng.deck([FREQ_MHZ])) if self.engine == "nec5" else {}
                )
                return None
            if self.engine != "nec5":
                make = eng._make_solver

                def spy(*args, **kwargs):
                    solver = make(*args, **kwargs)
                    made.append(solver)
                    return solver

                eng._make_solver = spy
            z = complex(np.atleast_1d(eng.impedance())[0])
        if self.engine == "nec5":
            runs = getattr(eng, "io_runs", [])
            self.readback = deck_fields(runs[-1]["deck"] if runs else None)
        elif made:
            s = made[-1]
            self.readback = {
                "solvers_made": len(made),
                "kernel_radius": [float(r) for r in np.atleast_1d(s._radius_per_wire)],
                "conductor_radius": [
                    float(r)
                    for r in np.atleast_1d(getattr(s, "_conductor_radius_per_wire", []))
                ],
            }
        else:
            self.readback = {"error": "no solver was made through _make_solver"}
        return z


def resonance(probe, start):
    pts = [(length, probe.z_at(length)) for length in start]
    while len(pts) < MAX_SOLVES and abs(pts[-1][1].imag) > X_TOL:
        (l1, z1), (l2, z2) = pts[-2], pts[-1]
        if z2.imag == z1.imag:
            break
        l3 = l2 - z2.imag * (l2 - l1) / (z2.imag - z1.imag)
        pts.append((l3, probe.z_at(l3)))
    best = min(pts, key=lambda p: abs(p[1].imag))
    return best[0], abs(best[1].imag) <= X_TOL, [[ln, z.real, z.imag] for ln, z in pts]


def one(name, treatment, engine, n, L0, start, solve):
    """L0 is a length, None (not known), or "own" (this row's resonance)."""
    rec = {"jacket": name, "treatment": treatment, "engine": engine, "n": n}
    if treatment == "bare":
        rec["a"] = BARE[name]
    else:
        a, b, eps = JACKETS[name]
        rec.update(a=a, b=b, eps_r=eps)
    t0 = time.perf_counter()
    probe = Probe(name, treatment, engine, n, solve)
    try:
        if not solve:
            probe.z_at(start[0])
            rec.update(meshed=probe.meshed, readback=probe.readback)
        else:
            L_res, converged, search = resonance(probe, start)
            rec.update(L_res=L_res, converged=converged, search=search)
            rec["readback_res"] = probe.readback
            if L0 == "own":
                L0 = L_res if converged else None
            if L0 is not None:
                z = probe.z_at(L0)
                rec.update(L0=L0, z_L0=[z.real, z.imag], readback=probe.readback)
            rec["meshed"] = probe.meshed
        rec["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 - one refused run is a recorded row
        rec["status"] = "error"
        rec["error"] = f"{type(exc).__name__}: {exc}"[:400]
    rec["secs"] = round(time.perf_counter() - t0, 3)
    return rec


def _git_head(path):
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", action="store_true", help="mesh only, no solve")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--only", default="", help="comma list of jacket or bare names")
    args = ap.parse_args()
    import momwire

    from antennaknobs.wire_catalog import WIRES

    for cat in ("22-awg-pvc", "18-awg-pvc"):
        w = WIRES[cat]
        if (w.radius, w.insulation_radius, w.insulation_eps_r) != JACKETS[cat]:
            raise SystemExit(f"{cat}: jackets.py disagrees with the catalog")
    solve = not args.mesh
    exe = os.environ.get("NEC5_EXE", "")
    if solve and not exe:
        raise SystemExit("NEC5_EXE is unset")
    mw_dir = Path(momwire.__file__).resolve().parent
    meta = {
        "_meta": True,
        "momwire": str(mw_dir),
        "momwire_version": getattr(momwire, "__version__", "?"),
        "momwire_head": _git_head(mw_dir),
        "antennaknobs_head": _git_head(Path(__file__).resolve().parent),
        "nec5_exe": exe,
        "nec5_sha256": hashlib.sha256(Path(exe).read_bytes()).hexdigest()
        if exe
        else None,
        "numpy": np.__version__,
        "solve": solve,
        "x_tol_ohm": X_TOL,
    }
    out = open(args.out, "w") if args.out else None  # noqa: SIM115
    if out:
        out.write(json.dumps(meta) + "\n")
    only = set(filter(None, args.only.split(",")))

    def emit(rec):
        if out:
            out.write(json.dumps(rec) + "\n")
            out.flush()
        z = rec.get("z_L0")
        rb = rec.get("readback") or rec.get("readback_res") or {}
        print(
            f"{rec['jacket']} {rec['treatment']} {rec['engine']} n={rec['n']}: "
            f"{rec['status']} segs={rec.get('meshed')} "
            + (
                f"L_res={rec['L_res']:.5f} conv={rec['converged']} "
                f"solves={len(rec['search'])} "
                if "L_res" in rec
                else ""
            )
            + (f"Z(L0)={z[0]:.4f}{z[1]:+.4f}j " if z else "")
            + (
                f"gw={rb.get('gw_radius')} ld2={rb.get('ld2_l')} "
                if "gw_radius" in rb
                else ""
            )
            + (f"kernel={rb.get('kernel_radius')} " if "kernel_radius" in rb else "")
            + f"{rec['secs']}s "
            + (rec.get("error", "") if rec["status"] != "ok" else ""),
            flush=True,
        )

    L_bare, L0 = {}, {}
    guess = (0.475 * LAMBDA, 0.490 * LAMBDA)
    first = [(c, "bs2", FINE) for c in BARE]
    rest = [
        (c, e, n) for c in BARE for e in ENGINES for n in NS if (e, n) != ("bs2", FINE)
    ]
    for c, e, n in first + rest:
        if only and c not in only:
            continue
        own = (e, n) == ("bs2", FINE)
        rec = one(c, "bare", e, n, "own" if own else L0.get(c), guess, solve)
        if rec.get("converged"):
            L_bare[c, e, n] = rec["L_res"]
            if own:
                L0[c] = rec["L_res"]
        emit(rec)
    for name in JACKETS:
        if only and name not in only:
            continue
        c = bare_of(name)
        for t in TREATMENTS:
            for e in ENGINES:
                for n in NS:
                    lb = L_bare.get((c, e, n)) or L0.get(c) or 0.48 * LAMBDA
                    emit(one(name, t, e, n, L0.get(c), (lb, 0.97 * lb), solve))
    if out:
        out.close()


if __name__ == "__main__":
    main()
