"""Part D of the split study: bs2's continuous feed against the old placement,
at fixed mesh density (#1519).

  PYTHONPATH=<momwire src>:src python scratch/1511-bs2-split/study_d.py --mesh
  PYTHONPATH=<momwire src>:src \\
      python scratch/1511-bs2-split/study_d.py --out rows_d.jsonl

The same 10.5 m dipole and builders as `study.py` (geometry A, the whole wire),
on momwire bs2 (BSplineSolver degree 2) only. Two placement paths:

  cont  #1519's continuous feed: the AUTHORED mesh exactly, with neither
        antennaknobs' positioned-port re-count (AK#1469) nor its odd-parity
        bump, and each port at its exact arclength. `study.py`'s A0 suppressed
        only the re-count, so an even authored count still became odd there;
        this path suppresses both, and every row records the engine's actual
        count to show it.
  old   antennaknobs' placement as it stands (the parity bump and the
        re-count), i.e. `study.py`'s A.

Runs (PLAN.md, Part D, registers what is compared):

  D1  the feed at 0.5, cont, n = 20, 40, 80, 160 (on a knot) and 21, 41, 81,
      161, 321 (at a segment centre).
  D2  k1: the feed at 0.31, no loads. For base N in 41, 81, 161: n = N-5 ... N+5
      on both paths, plus cont at 2N-1 for the refinement step at N.
  D3  D2 for k2 (+ a 50 ohm load at 0.77) and k3 (+ loads at 0.77 and 0.04).
  D4  D2 for k2 over finite ground 13 / 0.005, base N = 81 only.

Each distinct (case, ground, n, path) is solved once; the analysis groups rows
into the parts.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import study

study.CASES.setdefault("centre", (("feed", 0.5),))
study.CASES.setdefault("k1_031", (("feed", 0.31),))

BASES = (41, 81, 161)
D1_EVEN = (20, 40, 80, 160)
D1_ODD = (21, 41, 81, 161, 321)


@contextlib.contextmanager
def continuous():
    """#1519's placement for bs2: the authored count exactly (no parity bump,
    no positioned-port re-count), each port at its exact arclength."""
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


def configs():
    """Every distinct (case, ground, n, path) the parts need."""
    seen = []

    def add(*cfg):
        if cfg not in seen:
            seen.append(cfg)

    for n in D1_EVEN + D1_ODD:
        add("centre", "free", n, "cont")
    for case, ground, bases in (
        ("k1_031", "free", BASES),
        ("k2", "free", BASES),
        ("k3", "free", BASES),
        ("k2", "somm13", (81,)),
    ):
        for base in bases:
            for n in range(base - 5, base + 6):
                add(case, ground, n, "cont")
                add(case, ground, n, "old")
            add(case, ground, 2 * base - 1, "cont")
    return seen


def one(case, ground, n, path, solve):
    gnd = study.GROUND if ground == "somm13" else None
    b, _pieces = study.builder(case, "A", n)
    ctx = continuous() if path == "cont" else contextlib.nullcontext()
    rec = dict(case=case, ground=ground, n=n, path=path)
    t0 = time.perf_counter()
    try:
        with ctx:
            eng = study.make_engine("bs2", b, gnd, solve)
            segs = study.meshed_segments(eng)
            m = sum(c for _ln, c in segs)
            rec["meshed"] = [[ln, c] for ln, c in segs]
            rec["segments"] = m
            rec["ports"] = [
                {"name": name, "at": u, "xi": (u * m) % 1.0}
                for name, u in study.CASES[case]
            ]
            if solve:
                z = complex(np.atleast_1d(eng.impedance())[0])
                rec["z"] = [z.real, z.imag]
                rec["placements"] = study.offsets_mm(eng)
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
    args = ap.parse_args()
    import momwire

    meta = dict(
        _meta=True,
        momwire=str(Path(momwire.__file__).resolve().parent),
        solve=not args.mesh,
        study_py_sha256=hashlib.sha256(
            (Path(__file__).resolve().parent / "study.py").read_bytes()
        ).hexdigest(),
    )
    out = open(args.out, "w") if args.out else None  # noqa: SIM115
    if out:
        out.write(json.dumps(meta) + "\n")
    for case, ground, n, path in configs():
        rec = one(case, ground, n, path, solve=not args.mesh)
        if out:
            out.write(json.dumps(rec) + "\n")
            out.flush()
        z = rec.get("z")
        xis = [round(p["xi"], 3) for p in rec.get("ports", [])]
        print(
            f"{case} {ground} n={n} {path}: {rec['status']} segs={rec.get('segments')} "
            f"xi={xis} "
            + (f"Z={z[0]:.4f}{z[1]:+.4f}j" if z else "")
            + rec.get("error", ""),
            flush=True,
        )
    if out:
        out.close()


if __name__ == "__main__":
    main()
