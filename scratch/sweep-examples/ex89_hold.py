"""Driving examples E8 and E9 for the sweep framework (AK#1757, Steve
2026-09-28): a sweep with an optimisation HELD at every point, warm-started
from the previous point (continuation), through the workbench's own
optimizer (`web.optimize.optimize`), over average ground.

E8: sweep the inverted vee's height, hold match_z0 = 50 with length_factor
    AND angle_deg free (two equations, two unknowns: a root).
E9: sweep the apex angle, hold resonance (X = 0) with length_factor free
    (one equation, one unknown); R then shows where 50 is reachable.

    .venv-pypi/bin/python scratch/sweep-examples/ex89_hold.py
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from antennaknobs.web.examples import example_for
from antennaknobs.web.optimize import optimize

ex = example_for("dipoles.invvee")
BASE = {
    "geometry": "dipoles.invvee",
    "design_freq_mhz": 28.47,
    "measurement_freq_mhz": 28.47,
    "ground": True,
    "ground_model": "finite",
    "ground_eps_r": 13.0,
    "ground_sigma": 0.005,
    "z0_ohms": 50.0,
    "base": 7.0,
    "length_factor": 0.9719,
    "angle_deg": 31.6846,
}
LF = {"name": "length_factor", "min": 0.8, "max": 1.25}
ANG = {"name": "angle_deg", "min": 0.0, "max": 60.0}
TOL = 1e-3  # |residual| in ohms that counts as held


def held_sweep(knob, xs, free, objective):
    req = dict(BASE)
    rows = []
    for x in xs:
        req[knob] = float(x)
        r = optimize(req, free, objective, solve_fn=ex.momwire_solve)
        ok = r["residual_after"] is not None and r["residual_after"] < TOL
        m = r["metrics_after"]
        rows.append(
            dict(
                x=float(x),
                ok=bool(ok),
                params=r["params"],
                re=m["z_in_re"],
                im=m["z_in_im"],
                swr=m["swr"],
                solves=r["n_solves"],
                residual=r["residual_after"],
                method=r["method"],
            )
        )
        if ok:
            req.update(r["params"])  # warm start the next point
    return rows


e8 = held_sweep("base", np.linspace(2, 20, 37), [LF, ANG], "match_z0")
e9 = held_sweep("angle_deg", np.linspace(0, 60, 25), [LF], "resonance")
with open("scratch/sweep-examples/ex89_hold.json", "w") as f:
    json.dump({"e8": e8, "e9": e9}, f, indent=1)

fig, axs = plt.subplots(1, 2, figsize=(13, 5))
a = axs[0]
x = [r["x"] for r in e8]
ok = [r["ok"] for r in e8]
a.plot(
    x,
    [r["params"]["angle_deg"] if o else np.nan for r, o in zip(e8, ok, strict=True)],
    "o-",
    ms=3,
    color="tab:purple",
    label="angle_deg (held)",
)
a.set_xlabel("apex height, base (m)")
a.set_ylabel("apex angle for a 50 Ω match (°)", color="tab:purple")
a2 = a.twinx()
a2.plot(
    x,
    [
        r["params"]["length_factor"] if o else np.nan
        for r, o in zip(e8, ok, strict=True)
    ],
    "s-",
    ms=3,
    color="tab:green",
    label="length_factor (held)",
)
a2.set_ylabel("length_factor for a 50 Ω match", color="tab:green")
for xi, o in zip(x, ok, strict=True):
    if not o:
        a.axvspan(xi - 0.25, xi + 0.25, color="tab:red", alpha=0.15)
a.set_title("E8: sweep height, hold Z = 50 + j0 (length_factor, angle)")
a.grid(alpha=0.3)

b = axs[1]
x9 = [r["x"] for r in e9]
b.plot(x9, [r["re"] for r in e9], "o-", ms=3, color="tab:red", label="R at resonance")
b.axhline(50, color="0.4", ls=":", lw=0.8)
b.set_xlabel("apex angle (°)")
b.set_ylabel("R at resonance (Ω)", color="tab:red")
b2 = b.twinx()
b2.plot(x9, [r["params"]["length_factor"] for r in e9], "s-", ms=3, color="tab:green")
b2.set_ylabel("length_factor for resonance", color="tab:green")
b.set_title("E9: sweep angle, hold X = 0 (length_factor)")
b.grid(alpha=0.3)
fig.suptitle(
    "dipoles.invvee, 28.47 MHz, average ground; the workbench optimizer at each point, warm-started"
)
fig.tight_layout()
fig.savefig("scratch/sweep-examples/ex89_hold.png", dpi=110)

for name, rows in (("E8", e8), ("E9", e9)):
    good = [r for r in rows if r["ok"]]
    print(
        f"{name}: {len(good)}/{len(rows)} points held; solves per point "
        f"median {int(np.median([r['solves'] for r in rows]))}, max {max(r['solves'] for r in rows)}; "
        f"methods {sorted({r['method'] for r in rows})}"
    )
    bad = [r["x"] for r in rows if not r["ok"]]
    if bad:
        print(f"  not held at x = {bad}")
