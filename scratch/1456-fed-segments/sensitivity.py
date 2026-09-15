"""AK#1456's size-sensitivity study (PLAN.md): each eligible catalog design's
driving-point impedance on momwire with its fed wires at 1 / 3 / 7 segments and
on NEC-5 at 2 / 6, far mesh untouched.

  NEC5_EXE=<nec5cl> PYTHONPATH=<momwire src>:src \\
      python scratch/1456-fed-segments/sensitivity.py --outdir DIR [--designs a,b] [--workers N]

A MARKED wire (a legacy `ex` or a port name, the parity coercion's own rule) is
re-counted in every variant. A design is eligible when every marked wire is an
authored 1-segment wire shorter than 0.01 lambda (so re-counting it cannot touch
the far mesh), none is graded, and no port carries an explicit position
(AK#1469). Anything else is recorded as excluded, with the reason.

Each design runs in its own child process with a wall timeout, so one slow or
hung design costs its own row and nothing else. Every engine reports the counts
it actually meshed the marked wires to (from its coerced wires), and a variant
whose meshed count is not the one asked for is recorded as a harness error, not
silently used.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

C = 299792458.0
COUNTS = {"mw": (1, 3, 7), "n5": (2, 6)}
MAX_GAP_LAM = 0.01
TIMEOUT_S = 1800


def _marked(w):
    return w.ex is not None or w.name is not None


def eligibility(b):
    from antennaknobs.engine import _port_positions
    from antennaknobs.network import GradedSegments, as_wire

    lam = C / (b.freq * 1e6)
    marked = []
    for i, t in enumerate(b.build_wires()):
        w = as_wire(t)
        if not _marked(w):
            continue
        if isinstance(w.n_seg, GradedSegments):
            return False, f"marked wire {i} is graded", marked
        length = math.dist(w.p0, w.p1)
        marked.append(
            dict(
                wire=i,
                name=w.name,
                ex=w.ex is not None,
                n=int(w.n_seg),
                length_m=length,
            )
        )
    if not marked:
        return False, "no marked wire", marked
    for m in marked:
        if m["n"] != 1:
            return (
                False,
                f"marked wire {m['wire']} is authored at {m['n']} segments",
                marked,
            )
        if m["length_m"] >= MAX_GAP_LAM * lam:
            return (
                False,
                f"marked wire {m['wire']} is {m['length_m'] / lam:.3g} lambda",
                marked,
            )
    if _port_positions(b):
        return False, "a port carries an explicit position (AK#1469)", marked
    return True, "", marked


def variant(cls, k):
    from antennaknobs.network import GradedSegments, as_wire

    def build_wires(self):
        out = []
        for t in cls.build_wires(self):
            w = as_wire(t)
            if _marked(w) and not isinstance(w.n_seg, GradedSegments):
                out.append(w._replace(n_seg=k))
            else:
                out.append(t)
        return out

    return type(f"{cls.__name__}Fed{k}", (cls,), {"build_wires": build_wires})


def meshed_counts(eng):
    """The counts the engine meshed its fed segments to: momwire's feed edges
    (it keeps no coerced wire list), or the marked wires of an engine that
    keeps its coerced wires as `tups` (NEC-5)."""
    from antennaknobs.network import as_wire

    if hasattr(eng, "_feed_edges"):
        return [int(eng._edge_segments[pl][e]) for pl, e in eng._feed_edges]
    tups = getattr(eng, "tups", None)
    if tups is None:
        return None
    return [int(as_wire(t).n_seg) for t in tups if _marked(as_wire(t))]


def one(name, out_path):
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.engines.nec5 import NEC5Engine

    cls = importlib.import_module(f"antennaknobs.designs.{name}").Builder
    b = cls()
    ok, reason, marked = eligibility(b)
    ui = dict(b.default_params.get("ui_params", {}) or {})
    ground = None
    if ui.get("ground_requirement") == "sommerfeld":
        ground = ("finite", b.design_eps_r, b.design_sigma)
    rec = dict(design=name, freq_mhz=b.freq, ground=ground, marked=marked)
    if not ok:
        rec.update(status="excluded", reason=reason)
        Path(out_path).write_text(json.dumps(rec, indent=1))
        return
    runs = {}
    for key, counts in COUNTS.items():
        for k in counts:
            tag = f"{key}{k}"
            t0 = time.perf_counter()
            try:
                bv = variant(cls, k)()
                eng = (
                    MomwireEngine(bv, ground=ground)
                    if key == "mw"
                    else NEC5Engine(bv, ground=ground)
                )
                got = meshed_counts(eng)
                if got is not None and any(n != k for n in got):
                    raise RuntimeError(f"meshed {got}, asked {k}")
                zs = [complex(z) for z in np.atleast_1d(eng.impedance())]
                runs[tag] = dict(
                    status="ok",
                    z=[[z.real, z.imag] for z in zs],
                    meshed=got,
                    fed_seg_mm=[1000 * m["length_m"] / k for m in marked],
                    secs=round(time.perf_counter() - t0, 2),
                )
            except Exception as exc:  # noqa: BLE001 - one variant's failure is a recorded row, not the run's end
                runs[tag] = dict(
                    status="error",
                    error=f"{type(exc).__name__}: {exc}"[:400],
                    secs=round(time.perf_counter() - t0, 2),
                )
    rec.update(status="ok", runs=runs)
    Path(out_path).write_text(json.dumps(rec, indent=1))


def drive(args):
    from antennaknobs.cli import list_builtin_designs

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    names = args.designs.split(",") if args.designs else sorted(list_builtin_designs())
    exe = os.environ.get("NEC5_EXE", "")
    import momwire

    meta = dict(
        nec5_exe=exe,
        nec5_sha256=hashlib.sha256(Path(exe).read_bytes()).hexdigest() if exe else None,
        momwire=str(Path(momwire.__file__).resolve().parent),
        antennaknobs_head=subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip(),
        workers=args.workers,
        omp_num_threads=os.environ.get("OMP_NUM_THREADS"),
        counts=COUNTS,
        max_gap_lambda=MAX_GAP_LAM,
        timeout_s=TIMEOUT_S,
        designs=len(names),
    )
    (outdir / "_meta.json").write_text(json.dumps(meta, indent=1))

    def child(name):
        path = outdir / f"{name}.json"
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [sys.executable, __file__, "--one", name, "--out", str(path)],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
                check=False,
            )
            if proc.returncode != 0 and not path.exists():
                path.write_text(
                    json.dumps(
                        dict(design=name, status="crashed", stderr=proc.stderr[-2000:]),
                        indent=1,
                    )
                )
        except subprocess.TimeoutExpired:
            path.write_text(json.dumps(dict(design=name, status="timeout"), indent=1))
        return name, round(time.perf_counter() - t0, 1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for name, secs in pool.map(child, names):
            status = json.loads((outdir / f"{name}.json").read_text()).get("status")
            print(f"{name}: {status} ({secs} s)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir")
    ap.add_argument("--designs", default="")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--one")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.one:
        one(args.one, args.out)
    else:
        drive(args)


if __name__ == "__main__":
    main()
