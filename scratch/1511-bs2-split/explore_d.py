"""Part D, EXPLORATORY and not registered: what drives PD2-PD4's misses.

  python scratch/1511-bs2-split/explore_d.py scratch/1511-bs2-split/rows_d.jsonl

For each sweep: the residual after `analyze_d.py`'s density trend, regressed on
(1, cos 2 pi xi, sin 2 pi xi) of each port in turn (the share of the residual
each port's xi explains), the residual against the feed's xi, and both of PD2's
bars. Also D1, and PD3's failing rows. Nothing here is a bar; misses stay misses.
Writes explore_d.json beside the records.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

SWEEPS = (
    ("k1_031", "free", (41, 81, 161)),
    ("k2", "free", (41, 81, 161)),
    ("k3", "free", (41, 81, 161)),
    ("k2", "somm13", (81,)),
)


def main():
    path = Path(sys.argv[1])
    rows = {}
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        if not rec.get("_meta"):
            rows[(rec["case"], rec["ground"], rec["n"], rec["path"])] = rec

    def z(*key):
        return complex(*rows[key]["z"])

    out = {"d1": [], "sweeps": [], "pd3_fails": []}
    for m in (10, 20, 40, 80):
        ze, zo, z4 = (
            z("centre", "free", n, "cont") for n in (2 * m, 2 * m + 1, 4 * m + 1)
        )
        out["d1"].append(
            {
                "m": m,
                "even_minus_odd": abs(ze - zo),
                "step_odd": abs(zo - z4),
                "abs_z": abs(zo),
            }
        )
    for case, ground, bases in SWEEPS:
        for base in bases:
            ns = list(range(base - 5, base + 6))
            zs = np.array([z(case, ground, n, "cont") for n in ns])
            x = 1.0 / np.array(ns, float) ** 2
            design = np.column_stack([np.ones_like(x), x])
            trend = design @ np.linalg.lstsq(design, zs.real, rcond=None)[0] + 1j * (
                design @ np.linalg.lstsq(design, zs.imag, rcond=None)[0]
            )
            res = zs - trend
            ptp = max(abs(a - b) for a in res for b in res)
            z_base = z(case, ground, base, "cont")
            step = abs(z_base - z(case, ground, 2 * base - 1, "cont"))
            names = [p["name"] for p in rows[(case, ground, ns[0], "cont")]["ports"]]
            xi = {
                nm: np.array(
                    [
                        next(
                            p["xi"]
                            for p in rows[(case, ground, n, "cont")]["ports"]
                            if p["name"] == nm
                        )
                        for n in ns
                    ]
                )
                for nm in names
            }
            explained = {}
            for nm, xv in xi.items():
                basis = np.column_stack(
                    [np.ones_like(xv), np.cos(2 * np.pi * xv), np.sin(2 * np.pi * xv)]
                )
                fit = basis @ np.linalg.lstsq(basis, res.real, rcond=None)[0] + 1j * (
                    basis @ np.linalg.lstsq(basis, res.imag, rcond=None)[0]
                )
                explained[nm] = float(
                    1 - np.sum(np.abs(res - fit) ** 2) / np.sum(np.abs(res) ** 2)
                )
            worst = int(np.argmax(np.abs(res)))
            out["sweeps"].append(
                {
                    "case": case,
                    "ground": ground,
                    "base": base,
                    "ptp": ptp,
                    "ptp_pct_of_z": 100 * ptp / abs(z_base),
                    "step": step,
                    "ptp_over_step": ptp / step,
                    "bar_quarter_step": 0.25 * step,
                    "bar_0p05pct_z": 0.0005 * abs(z_base),
                    "worst_n": ns[worst],
                    "worst_xi": {nm: float(v[worst]) for nm, v in xi.items()},
                    "share_explained_by_xi": explained,
                    "feed_xi_vs_residual": sorted(
                        (
                            [float(xi["feed"][i]), res[i].real, res[i].imag]
                            for i in range(len(ns))
                        ),
                        key=lambda t: t[0],
                    ),
                }
            )
    for base in (41, 81, 161):
        step = abs(
            z("k3", "free", base, "cont") - z("k3", "free", 2 * base - 1, "cont")
        )
        for n in range(base - 5, base + 6):
            old, cont = rows[("k3", "free", n, "old")], rows[("k3", "free", n, "cont")]
            d = abs(z("k3", "free", n, "old") - z("k3", "free", n, "cont"))
            if d > step:
                out["pd3_fails"].append(
                    {
                        "n": n,
                        "old_segments": old["segments"],
                        "cont_segments": cont["segments"],
                        "old_feed_xi": next(
                            p["xi"] for p in old["ports"] if p["name"] == "feed"
                        ),
                        "cont_feed_xi": next(
                            p["xi"] for p in cont["ports"] if p["name"] == "feed"
                        ),
                        "abs_old_minus_cont": d,
                        "step": step,
                    }
                )
    (path.parent / "explore_d.json").write_text(json.dumps(out, indent=1))
    for s in out["sweeps"]:
        print(
            f"{s['case']}/{s['ground']} N={s['base']}: ptp {s['ptp']:.4f} ({s['ptp_pct_of_z']:.3f} % of |Z|, "
            f"{s['ptp_over_step']:.2f} x step) | bars {s['bar_quarter_step']:.4f} / {s['bar_0p05pct_z']:.4f} | "
            f"share explained by xi: { {k: round(v, 2) for k, v in s['share_explained_by_xi'].items()} }"
        )
    for f in out["pd3_fails"]:
        print(
            f"PD3 k3 n={f['n']}: old {f['old_segments']} segs xi {f['old_feed_xi']:.2f} vs cont {f['cont_segments']} xi {f['cont_feed_xi']:.2f}: {f['abs_old_minus_cont']:.4f} > {f['step']:.4f}"
        )


if __name__ == "__main__":
    main()
