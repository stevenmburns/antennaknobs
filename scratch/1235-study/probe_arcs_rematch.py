"""#1235: today's cost against the #927 runtime-arcs ladder, matched exactly.

`scratch/runtime-arcs-ladders.jsonl` measured arrays.bowtiearray2x4 on momwire
0.29.0. Its `basis` column is `bench_converge.total_nominal_segs` and its
`n_per_wire` is `nominal_nsegs` -- verified: n=9 -> 304 and n=35 -> 1216, both
exactly the recorded basis. So the mesh axis matches and the ladders are
directly comparable at the same rungs, same geometry, same Sommerfeld ground,
same box.

One cell per subprocess so `ru_maxrss` is a real peak rather than a
high-water mark of everything before it. Warm timing clears the engine's
`_solved_cache` first, without which the second call is a dict lookup.
"""

import json
import resource
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

DESIGN = "arrays.bowtiearray2x4"
GROUND = ("finite", 13.0, 0.005)
RUNGS = (9, 35, 115, 241)


def worker(nseg, engine):
    import bench_converge as bnc

    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import BSplineSolver, SinusoidalSolver

    cls = bnc.load_design(DESIGN)
    b = cls()
    b.nominal_nsegs = int(nseg)
    kw = (
        {"solver": BSplineSolver, "solver_kwargs": {"degree": 2}}
        if engine == "bs2"
        else {"solver": SinusoidalSolver}
    )
    eng = MomwireEngine(b, ground=GROUND, **kw)
    eng.impedance()
    eng._solved_cache = None
    t = time.perf_counter()
    z = eng.impedance()[0]
    warm = time.perf_counter() - t
    print(
        json.dumps(
            {
                "nseg": int(nseg),
                "engine": engine,
                "basis": bnc.total_nominal_segs(cls, int(nseg)),
                "warm_s": warm,
                "rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                * 1024
                / 1e6,
                "z": [z.real, z.imag],
            }
        )
    )


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--worker":
        return worker(sys.argv[2], sys.argv[3])
    for engine in ("bs2", "sin"):
        for n in RUNGS:
            p = subprocess.run(
                [sys.executable, __file__, "--worker", str(n), engine],
                capture_output=True,
                text=True,
                timeout=1800,
            )
            line = (p.stdout or "").strip().splitlines()
            if line and line[-1].startswith("{"):
                print(line[-1], flush=True)
            else:
                print(
                    json.dumps(
                        {
                            "nseg": n,
                            "engine": engine,
                            "error": (p.stderr or "")[-160:],
                        }
                    ),
                    flush=True,
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
