"""A-2 session 8, probe 38 — the fan widening's adjudicator + bank.

Three measurements on the 4-rise fan (the connected radial screen,
rise-spelled: contact_deck's monopole junction-joined at the node to 4
radials that run at 15 cm depth and rise to the surface — the N rise
segments coincident on (0,0,-0.15) -> (0,0,0)):

  eps1   - THE ADJUDICATOR for the N-tent corner bookkeeping: at
           eps_t = 1 the interface vanishes and the fan deck IS a
           free-space 5-wire junction deck, solved independently by the
           native junction machinery (KCL row, shipped free-space fill).
           This is what validates (or indicts) the below x below tent
           corners and N^2 bnd cross-terms the self completion now emits.
  soil   - the soil-A 4-rise fan number, NEW bank (compared to the
           engine's detached-stake four-radial print 90.051-70.731j only
           as a documented convention difference, never a gate).
  grade  - the node-grading pair: the monopole's node edge and each
           rise split once more (probe18's grading direction) for a
           mesh-stability envelope on the fan answer.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe38_fan_widening.py [eps1|soil|grade ...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from test_crossing_serve_524 import fan_rise_deck, hub_deck  # noqa: E402

ANCHOR_FOUR_RADIAL = 90.051 - 70.731j  # engine detached-stake print, record only

# Convention gate (house rule): e^{+jwt}, eps_t = eps_r - j sigma/(w eps0)
# so Im(k_m) < 0 and e^{-j k_m R}/R decays with R.
from momwire._sommerfeld_below import k_medium  # noqa: E402
from test_buried_serve_553 import SOIL_A, WL7  # noqa: E402

_w = 2 * np.pi * 299792458.0 / WL7
_eps_t = SOIL_A[0] - 1j * SOIL_A[1] / (_w * 8.8541878128e-12)
assert _eps_t.imag < 0.0
_km = k_medium(_eps_t, 2 * np.pi / WL7)
assert abs(np.exp(-1j * _km * 10.0)) < abs(np.exp(-1j * _km * 1.0)) < 1.0


def _solve(build, tag):
    s = BSplineSolver(**build)
    if "ground_z" in build:
        print(
            f"[{tag}] media = {s._wire_media()}  crossing = {s._crossing_junctions()}",
            flush=True,
        )
    t0 = time.time()
    z, _ = s.compute_impedance()
    dt = time.time() - t0
    print(f"[{tag}] Z = {z:.4f}   ({dt:.0f}s)", flush=True)
    return z, dt


def free_space_truth(build):
    """The SAME wires/junctions/feed with no ground at all — the native
    free-space junction machinery is the independent truth."""
    truth = {
        k: v
        for k, v in build.items()
        if k not in ("ground_z", "ground_eps", "ground_model")
    }
    return truth


def run_eps1(out):
    build = fan_rise_deck(ground_eps=(1.0, 0.0))
    z_truth, dt_t = _solve(free_space_truth(build), "eps1-truth")
    z, dt = _solve(build, "eps1-fan")
    diff = abs(z - z_truth)
    print(
        f"[eps1] |fan - truth| = {diff:.4f} ohm "
        f"({'PASS' if diff <= 0.05 else 'FAIL'} at the 0.05 class)",
        flush=True,
    )
    out["eps1"] = dict(
        z=f"{z:.4f}",
        truth=f"{z_truth:.4f}",
        diff_ohm=round(float(diff), 4),
        secs=round(dt + dt_t, 1),
    )


def run_soil(out):
    z, dt = _solve(fan_rise_deck(), "soil-A")
    print(
        f"[soil] engine detached-stake print = {ANCHOR_FOUR_RADIAL:.4f} "
        f"(convention record, |diff| = {abs(z - ANCHOR_FOUR_RADIAL):.3f} ohm)",
        flush=True,
    )
    out["soil-A-fan"] = dict(
        z=f"{z:.4f}",
        engine_print=f"{ANCHOR_FOUR_RADIAL:.4f}",
        diff_vs_print_ohm=round(float(abs(z - ANCHOR_FOUR_RADIAL)), 3),
        secs=round(dt, 1),
    )


def run_grade(out):
    build = fan_rise_deck()
    build["n_per_edge_per_wire"] = [[15, 3] for _ in range(4)] + [[22]]
    z, dt = _solve(build, "grade-up")
    out["soil-A-fan-graded"] = dict(z=f"{z:.4f}", secs=round(dt, 1))
    if "soil-A-fan" in out:
        move = abs(z - complex(out["soil-A-fan"]["z"]))
        out["grade_move_ohm"] = round(float(move), 4)
        print(f"[grade] move vs base mesh = {out['grade_move_ohm']} ohm", flush=True)


def run_scale(out):
    """N-scaling of the eps1 residual: N = 1 must reproduce probe37's
    0.0019-ohm class (same deck class); the N = 2 step says whether the
    N = 4 residual grows with the coincident-rise pair count (quadrature
    class) or jumps discontinuously (bookkeeping class)."""
    for n in (1, 2):
        build = fan_rise_deck(n_radials=n, ground_eps=(1.0, 0.0))
        z_truth, dt_t = _solve(free_space_truth(build), f"scale{n}-truth")
        z, dt = _solve(build, f"scale{n}-fan")
        diff = abs(z - z_truth)
        print(f"[scale] N={n}: |fan - truth| = {diff:.4f} ohm", flush=True)
        out[f"eps1-n{n}"] = dict(
            z=f"{z:.4f}",
            truth=f"{z_truth:.4f}",
            diff_ohm=round(float(diff), 4),
            secs=round(dt + dt_t, 1),
        )


def run_eps1_grade(out):
    """Node-grades the N = 4 eps1 residual: if 0.23 ohm is a convergence
    class (the emergent-KCL error at a K = 5 node, or under-integrated
    touching-pair content) it shrinks as the node mesh refines; if it is
    bookkeeping it plateaus. Truth and fan refine TOGETHER — the diff is
    the quantity under test."""
    for tag, npe_r, npe_m in (("g2", [20, 6], 30),):
        build = fan_rise_deck(ground_eps=(1.0, 0.0))
        build["n_per_edge_per_wire"] = [list(npe_r) for _ in range(4)] + [[npe_m]]
        z_truth, dt_t = _solve(free_space_truth(build), f"eps1-{tag}-truth")
        z, dt = _solve(build, f"eps1-{tag}-fan")
        diff = abs(z - z_truth)
        print(f"[eps1-grade] {tag}: |fan - truth| = {diff:.4f} ohm", flush=True)
        out[f"eps1-grade-{tag}"] = dict(
            z=f"{z:.4f}",
            truth=f"{z_truth:.4f}",
            diff_ohm=round(float(diff), 4),
            secs=round(dt + dt_t, 1),
        )


def run_hub_eps1(out):
    """The hub spelling through the same eps1 adjudicator: at eps_t = 1
    the hub deck IS a free-space 6-wire deck with two native junctions —
    validates the hub ends' by-parts/KCL cancellation on the crossing
    axes."""
    build = hub_deck(ground_eps=(1.0, 0.0))
    z_truth, dt_t = _solve(free_space_truth(build), "hub-eps1-truth")
    z, dt = _solve(build, "hub-eps1")
    diff = abs(z - z_truth)
    print(
        f"[hub-eps1] |hub - truth| = {diff:.4f} ohm "
        f"({'PASS' if diff <= 0.05 else 'FAIL'} at the 0.05 class)",
        flush=True,
    )
    out["hub-eps1"] = dict(
        z=f"{z:.4f}",
        truth=f"{z_truth:.4f}",
        diff_ohm=round(float(diff), 4),
        secs=round(dt + dt_t, 1),
    )


def run_hub_soil(out):
    """hub-spelling vs N-rises-spelling on the SAME soil-A screen — the
    two spellings of one physical structure must agree."""
    z, dt = _solve(hub_deck(), "hub-soil-A")
    out["soil-A-hub"] = dict(z=f"{z:.4f}", secs=round(dt, 1))
    if "soil-A-fan" in out:
        gap = abs(z - complex(out["soil-A-fan"]["z"]))
        out["hub_vs_rises_ohm"] = round(float(gap), 4)
        print(f"[hub-soil] |hub - N-rises| = {gap:.4f} ohm", flush=True)


def main():
    fp = HERE.parent / "results" / "probe38-fan-widening.json"
    out = json.loads(fp.read_text()) if fp.exists() else {}
    runners = {
        "eps1": run_eps1,
        "scale": run_scale,
        "eps1-grade": run_eps1_grade,
        "soil": run_soil,
        "grade": run_grade,
        "hub-eps1": run_hub_eps1,
        "hub-soil": run_hub_soil,
    }
    for name in sys.argv[1:] or ["eps1", "soil", "grade", "hub-eps1", "hub-soil"]:
        runners[name](out)
        fp.write_text(json.dumps(out, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
