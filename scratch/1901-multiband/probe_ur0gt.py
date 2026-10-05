"""AK#1901: UR0GT's three-band vertical + capacitively coupled inverted L.

Dan's deck (QRZ), a third-party file: never copied into the repo. Opened
through the workbench (`POST /deck`) and optimised through `POST /optimize`
with a band list, so the free knobs are the deck's own SY constants reaching
the solver as the opened-deck knob path sets them (sy_w5hgt, sy_w6len,
sy_cap1, sy_cap2), never by editing the deck's text. momwire, the deck's own
ground (GE 1 + GD 13 / 0.005: the MININEC-type ground the workbench seeds).

    python scratch/1901-multiband/probe_ur0gt.py [/path/to/UR0GT_SY_vert_inv_L.nec]
"""

import sys
import time

import numpy as np
from fastapi.testclient import TestClient

from antennaknobs.web import server

PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/UR0GT_SY_vert_inv_L.nec"
which = sys.argv[2:] or ["start", "jacobian", "root3", "minimax", "sequential"]
MODE = {"root3": "root"}
F160, F80, F40 = 1.83, 3.7, 7.1
FREQS = (F160, F80, F40)
GROUND = {
    "ground": True,
    "ground_model": "mininec",
    "soil": {"eps_r": 13.0, "sigma": 0.005},
}
KNOBS = {
    "sy_w5hgt": (8.0, 16.0),
    "sy_w6len": (45.0, 75.0),
    "sy_cap1": (100.0, 1000.0),
    "sy_cap2": (10.0, 150.0),
}

c = TestClient(server.app)
with open(PATH) as fh:
    opened = c.post(
        "/deck", json={"name": "UR0GT_SY_vert_inv_L.nec", "text": fh.read()}
    )
key = opened.json()["key"]
ex = server.EXAMPLES[key]
base = {"geometry": key, **GROUND}
start = {"sy_w5hgt": 12.0, "sy_w6len": 61.22, "sy_cap1": 340.0, "sy_cap2": 41.0}


def show_bands(label, recs):
    print(
        f"  {label}: "
        + "  ".join(
            f"{r['freq_mhz']:g} MHz {r['z_re']:.1f}{r['z_im']:+.1f}j SWR {r['swr']:.2f}"
            for r in recs
        )
    )


def run(title, free_names, bands, mode="minimax", **opt):
    body = {
        **base,
        **start,
        "optimize": {
            "free": [
                {"name": k, "min": KNOBS[k][0], "max": KNOBS[k][1]} for k in free_names
            ],
            "bands": bands,
            "mode": mode,
            "max_evals": 400,
            **opt,
        },
    }
    t0 = time.perf_counter()
    out = c.post("/optimize", json=body).json()
    dt = time.perf_counter() - t0
    if "error" in out:
        print(f"[{title}] ERROR {out['error']}")
        return out
    print(
        f"[{title}] {out['method']} converged={out['converged']} "
        f"root_status={out['root_status']} "
        f"evals={out['n_evals']} builds={out['n_solves']} "
        f"band-solves={out['n_freq_solves']} passes={out['passes']} wall={dt:.1f}s "
        f"antiresonant={out['antiresonant_bands']} reason={out['root_reason']}"
    )
    show_bands("before", out["bands_before"])
    show_bands("after ", out["bands_after"])
    print(
        f"  J {out['objective_before']:.4g} -> {out['objective_after']:.4g} "
        f"(w={out['mean_weight']}; worst {out['objective_worst_before']:.4g} -> "
        f"{out['objective_worst_after']:.4g}, mean {out['objective_mean_before']:.4g}"
        f" -> {out['objective_mean_after']:.4g}); worst SWR "
        f"{out['worst_swr_before']:.3f} -> {out['worst_swr_after']:.3f} "
        f"(max of per-band read: {max(r['swr'] for r in out['bands_after']):.3f})"
    )
    print("  params", {k: round(v, 4) for k, v in out["params"].items()})
    return out


def res(f, **kn):
    return {"freq": f, "objective": "resonance", **kn}


if "start" in which:
    out = ex.momwire_bands({**base, **start}, list(FREQS))
    print(
        "start Z:", [f"{z:.1f}" for z in out["zs"][:, 0]], f"{out['solve_ms']:.0f} ms"
    )

if "jacobian" in which:
    z0 = ex.momwire_bands({**base, **start}, list(FREQS))["zs"][:, 0]
    print("dX (ohm) per +1 % of each knob, at the start:")
    print("            " + "".join(f"{f:>10g}" for f in FREQS))
    for k, v in start.items():
        z1 = ex.momwire_bands({**base, **start, k: v * 1.01}, list(FREQS))["zs"][:, 0]
        print(f"  {k:10s}" + "".join(f"{d:10.2f}" for d in np.imag(z1 - z0)))

if "root3" in which:
    # 3 resonances, 4 knobs: pin cap1 and solve the square 3 x 3.
    run(
        "root 3x3, cap1 pinned",
        ["sy_w5hgt", "sy_w6len", "sy_cap2"],
        [res(F160), res(F80), res(F40)],
        mode="root",
    )
    run(
        "minimax swr 3 knobs (cap1 pinned), default w",
        ["sy_w5hgt", "sy_w6len", "sy_cap2"],
        [{"freq": f} for f in FREQS],
    )

if "minimax" in which:
    for w in (0.0, 0.2, 0.5, 0.7):
        run(
            f"minimax swr, 4 knobs, w={w}",
            list(KNOBS),
            [{"freq": f, "objective": "swr"} for f in FREQS],
            mean_weight=w,
        )

if "sequential" in which:
    # The start's Jacobian (above) puts w6len first on BOTH 160 m (92 ohm per
    # 1 %) and 80 m (33), cap2 second on both (7.6, 2.4), w5hgt alone on 40 m.
    # So w5hgt -> 40 m, and the 160/80 pair is the question. w6len -> 160 m,
    # cap2 -> 80 m has an off-diagonal product over the diagonal's (7.6 * 33.4
    # against 91.9 * 2.35, ratio 1.18): block Gauss-Seidel diverges there.
    # The swap (w6len -> 80 m, cap2 -> 160 m) has ratio 0.85 and converges.
    for title, a160, a80 in (
        ("sequential, cap1 pinned, w6len->160 cap2->80", "sy_w6len", "sy_cap2"),
        ("sequential, cap1 pinned, w6len->80 cap2->160", "sy_cap2", "sy_w6len"),
    ):
        run(
            title,
            ["sy_w5hgt", "sy_w6len", "sy_cap2"],
            [
                res(F160, knobs=[a160]),
                res(F80, knobs=[a80]),
                res(F40, knobs=["sy_w5hgt"]),
            ],
            mode="sequential",
        )
    run(
        "sequential, cap1+cap2 on 160 m, w6len->80",
        list(KNOBS),
        [
            res(F160, knobs=["sy_cap1", "sy_cap2"]),
            res(F80, knobs=["sy_w6len"]),
            res(F40, knobs=["sy_w5hgt"]),
        ],
        mode="sequential",
    )
