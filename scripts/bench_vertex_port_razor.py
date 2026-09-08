"""Does razor-2p's node-gap path earn a tab on vertex-port designs? (AK#1267 follow-up)

`_VERTEX_PORT_WITHHELD = ("razor-2p",)` records that `RazorSolver` SERVES
momwire's series node gap (momwire#603) and solves the one catalog design that
uses one, but is not offered as a tab because nobody had driven that path.
This is that drive. It changes no code and no tab list -- it produces the
numbers the decision needs.

THE CATALOG HAS EXACTLY ONE VERTEX-PORT DESIGN. Enumerated from the registry
(`bench_catalog.all_designs`, every network built and its ports typed):
103 designs, 1 with a `PortAtVertex` -- `dipoles.invvee_apex`. A tab decision
resting on one geometry is thin, so this sweeps that design's OWN declared
`ui_params` ranges (`angle_deg` 0-60, `base` 1-16, `length_factor` 0.8-1.25)
one knob at a time around the default, plus three corners. Those are the knobs
a user can actually move behind the tab, so the sample is the space the
decision is about -- not decks invented for the occasion.

Against `bs2` and `sinusoidal-galerkin` at matched mesh: two INDEPENDENT
converged formulations, whose spread is the yardstick razor is measured
against. Comparing razor to one of them would measure the pair's
disagreement as if it were razor's error.

FOUR rungs, not two. The question "does its step shrink with refinement"
needs at least two steps to have a ratio at all; four rungs give three steps
and two ratios, which is what separates "first order" (ratio ~0.5 per
doubling) from "not converging".

    python scripts/bench_vertex_port_razor.py --out docs/status/<date>-....jsonl

One cell per subprocess, for the same reason the catalog ladder does it:
`ru_maxrss` is a high-water mark, so a shared interpreter reports the peak of
everything that ran before. Warm timing with `_solved_cache` cleared, the same
cache trap #1235 documents. BLAS pin from `bench_nec_corpus`, so these numbers
are comparable with that ladder's.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

DESIGN = "dipoles.invvee_apex"
ENGINES = ("bs2", "sing", "razor-2p")
RUNGS = (21, 42, 84, 168)
GROUNDS = {
    # The design's docstring states its A/B in free space, and the catalog
    # cost ladder (#1235) runs everything at ("finite", 13.0, 0.005). Both are
    # measured: a node gap rides the ordinary span with no node-charge
    # machinery, so the ground should not interact with it -- which is a claim
    # worth checking rather than assuming.
    "free": None,
    "finite-13-0.005": ("finite", 13.0, 0.005),
}


def param_points():
    """The design's own knobs, one at a time around the default, plus corners.

    Ranges are read from `ui_params` rather than written here, so this cannot
    sweep somewhere the app would not let a user go.
    """
    from antennaknobs.designs.dipoles.invvee_apex import Builder

    d = dict(Builder.default_params)
    ui = d["ui_params"]
    pts = [("default", {})]
    for knob in ("angle_deg", "base", "length_factor"):
        lo, hi = ui[knob]["min"], ui[knob]["max"]
        base = float(d[knob])
        # Interior points, not the endpoints: `angle_deg` min is 0.0, which
        # collapses the vee into a straight horizontal dipole and stops being
        # the geometry under test.
        for frac, tag in ((0.12, "lo"), (0.88, "hi")):
            v = lo + frac * (hi - lo)
            if abs(v - base) < 1e-9:
                continue
            pts.append((f"{knob}={v:g}", {knob: v}))
    corners = [
        {"angle_deg": 12.0, "base": 2.5},
        {"angle_deg": 52.0, "base": 14.0},
        {"angle_deg": 52.0, "base": 2.5, "length_factor": 1.2},
    ]
    for c in corners:
        pts.append(("+".join(f"{k}={v:g}" for k, v in c.items()), c))
    return pts


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _build(b, engine, ground):
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import BSplineSolver, RazorSolver, SinusoidalGalerkinSolver

    kw = {} if ground is None else {"ground": ground}
    if engine == "bs2":
        return MomwireEngine(b, solver=BSplineSolver, solver_kwargs={"degree": 2}, **kw)
    if engine == "sing":
        return MomwireEngine(b, solver=SinusoidalGalerkinSolver, **kw)
    if engine == "razor-2p":
        # The TAB's preset, not a bare RazorSolver: `razor-2p` binds the
        # identified two-point quadrature, and measuring the unbound class
        # would answer about a configuration no tab offers.
        return MomwireEngine(
            b,
            solver=RazorSolver,
            solver_kwargs={"nec5_quadrature": True},
            **kw,
        )
    raise SystemExit(f"unknown engine {engine!r}")


def worker_main(engine, nseg, ground_key, params_json):
    out = {"error": None, "advisories": []}
    try:
        bnc = _load("bench_converge")
        cores = _load("bench_nec_corpus").apply_server_thread_policy()
        cls = bnc.load_design(DESIGN)
        b = cls()
        # SET, do not pass: `AntennaBuilder.__init__` takes no design knobs
        # (measured — `Builder(angle_deg=52.0)` raises TypeError), they are
        # attributes seeded from `default_params`. Each name is checked
        # against the instance first, so a typo'd knob fails loudly instead
        # of silently measuring the default geometry N times.
        for k, v in json.loads(params_json).items():
            if not hasattr(b, k):
                raise SystemExit(f"{DESIGN} has no knob {k!r}")
            setattr(b, k, v)
        b.nominal_nsegs = int(nseg)
        ground = GROUNDS[ground_key]

        eng = _build(b, engine, ground)
        t0 = time.perf_counter()
        eng.impedance()
        cold = time.perf_counter() - t0
        # The #1235 cache trap: a second impedance() on an unchanged engine is
        # a dict lookup, not a solve.
        eng._solved_cache = None
        t1 = time.perf_counter()
        zs = eng.impedance()
        warm = time.perf_counter() - t1
        # READ THE ENGINE'S CHANNEL, not a `catch_warnings` around the call.
        # The first spelling of this wrapped `eng.impedance()` in
        # `catch_warnings(record=True)` and recorded ZERO advisories for every
        # razor cell -- because `@_captures_advisories` already catches them
        # inside the engine and absorbs them into `_advisory_recorder`, so
        # nothing propagates out to an outer recorder. It would have reported
        # "razor raises no advisory on this design", which is the opposite of
        # true: razor-2p raises `RazorFarMeshClass` on every deck.
        out["advisories"] = [
            f"{a['category']}: {a['text'][:240]}" for a in eng.advisories
        ]
        out.update(
            z=[[float(z.real), float(z.imag)] for z in zs],
            cold_s=cold,
            warm_s=warm,
            peak_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 / 1e6,
            cores=cores,
            nominal_segs=bnc.total_nominal_segs(cls, int(nseg)),
        )
    except Exception as e:  # noqa: BLE001 — a refusal is a RESULT here, not a crash
        out["error"] = f"{type(e).__name__}: {e}"
    print(json.dumps(out))


def _meta():
    def sha(path):
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout.strip()

    root = _HERE.parent
    import numpy as np

    return {
        "_meta": True,
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "box": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "antennaknobs_sha": sha(root),
        "momwire_sha": sha(root / "momwire"),
        "blas_pin": "bench_nec_corpus.apply_server_thread_policy",
        "design": DESIGN,
        "engines": list(ENGINES),
        "rungs": list(RUNGS),
        "grounds": {k: list(v) if v else None for k, v in GROUNDS.items()},
    }


FINE_RUNGS = (168, 336, 672, 1344)


def fine_ladder(out):
    """The default geometry, free space, every engine, out to n=1344.

    The 4-rung grid answers "is razor inside the spread at a mesh anyone would
    run". This answers the follow-up the grid cannot: razor is FIRST ORDER, so
    where does it land if you simply pay for mesh — does it converge to the
    same number, or to a different one? Those are a cost question and a
    correctness question, and only the second would be a reason to refuse the
    tab outright.

    Appended to the same file rather than written beside it: it is the same
    measurement at more rungs, and two files would invite reading one without
    the other.
    """
    with out.open("a") as fh:
        for engine in ENGINES:
            for nseg in FINE_RUNGS:
                cp = subprocess.run(
                    [
                        sys.executable,
                        __file__,
                        "--worker",
                        engine,
                        str(nseg),
                        "free",
                        "{}",
                    ],
                    capture_output=True,
                    text=True,
                )
                rec = json.loads(cp.stdout.strip().splitlines()[-1])
                rec.update(
                    design=DESIGN,
                    params_tag="default",
                    params={},
                    ground="free",
                    engine=engine,
                    nseg=nseg,
                    series="fine_ladder",
                )
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                print(f"  fine {engine} n={nseg}", flush=True)
    print(f"appended fine ladder to {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--fine",
        action="store_true",
        help="the DEFAULT geometry only, out to 1344 — the ladder that answers "
        "'what does first order cost here', appended to --out",
    )
    args = ap.parse_args()
    if args.fine:
        return fine_ladder(Path(args.out))
    pts = param_points()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_total = len(pts) * len(ENGINES) * len(RUNGS) * len(GROUNDS)
    done = 0
    with out.open("w") as fh:
        fh.write(json.dumps(_meta()) + "\n")
        for tag, params in pts:
            for gkey in GROUNDS:
                for engine in ENGINES:
                    for nseg in RUNGS:
                        cp = subprocess.run(
                            [
                                sys.executable,
                                __file__,
                                "--worker",
                                engine,
                                str(nseg),
                                gkey,
                                json.dumps(params),
                            ],
                            capture_output=True,
                            text=True,
                        )
                        try:
                            rec = json.loads(cp.stdout.strip().splitlines()[-1])
                        except Exception:  # noqa: BLE001 — a dead worker is a cell
                            rec = {
                                "error": f"worker exit {cp.returncode}: "
                                f"{cp.stderr.strip()[-300:]}"
                            }
                        rec.update(
                            design=DESIGN,
                            params_tag=tag,
                            params=params,
                            ground=gkey,
                            engine=engine,
                            nseg=nseg,
                        )
                        fh.write(json.dumps(rec) + "\n")
                        fh.flush()
                        done += 1
            print(f"  {tag}: {done}/{n_total}", flush=True)
    print(f"wrote {out} ({done} cells)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker_main(*sys.argv[2:])
    else:
        main()
