"""AK#1456, EXPLORATORY and not registered: what the study's data collapses on,
after P2 missed. Nothing here is a prediction, a gate or a threshold; PLAN.md's
C_ref procedure stays abandoned whatever this prints.

  python scratch/1456-fed-segments/explore.py scratch/1456-fed-segments/study
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze import ports, spearman


def split(za, zb):
    return abs(za - zb) / max(abs(za), abs(zb))


def main():
    d = Path(sys.argv[1])
    recs = [
        json.loads(p.read_text())
        for p in sorted(d.glob("*.json"))
        if p.name != "_meta.json"
    ]
    rows = ports(recs)
    nports = {}
    for r in rows:
        nports[r["design"]] = nports.get(r["design"], 0) + 1
    mw = [r for r in rows if "dY_mw" in r]
    out = {}
    out["excluded"] = {
        r["design"]: r["reason"] for r in recs if r.get("status") == "excluded"
    }

    def stats(sel, label):
        s = [abs(r["mw3"] - r["mw1"]) / abs(r["mw1"]) for r in sel]
        zf = [abs(r["mw1"]) * r["f"] for r in sel]
        model = [abs(r["mw1"]) * 2 * math.pi * r["f"] * abs(r["dC_mw"]) for r in sel]
        ratio = np.array(s) / np.array(model)
        return {
            "label": label,
            "ports": len(sel),
            "designs": len({r["design"] for r in sel}),
            "rho_s_Zf": spearman(s, zf) if len(sel) > 2 else None,
            "shunt_model_s_over_ZwdC_median": float(np.median(ratio)),
            "shunt_model_p5_p95": [
                float(np.percentile(ratio, 5)),
                float(np.percentile(ratio, 95)),
            ],
        }

    single = [r for r in mw if nports[r["design"]] == 1]
    multi = [r for r in mw if nports[r["design"]] > 1]
    out["all"] = stats(mw, "all ports")
    out["single_port_designs"] = stats(single, "single-port designs")
    out["multi_port_designs"] = stats(multi, "multi-port designs")
    sR = [abs(r["mw3"].real - r["mw1"].real) / abs(r["mw1"].real) for r in single]
    xf = [abs(r["mw1"].imag) * r["f"] for r in single]
    out["single_rho_sR_Xf"] = spearman(sR, xf)

    movers = []
    for r in mw:
        sr = abs(r["mw3"].real - r["mw1"].real) / abs(r["mw1"].real)
        if sr > 0.01:
            movers.append(
                dict(
                    design=r["design"],
                    port=r["port"],
                    ports=nports[r["design"]],
                    f_mhz=r["f"] / 1e6,
                    z_mw1=[round(r["mw1"].real, 3), round(r["mw1"].imag, 3)],
                    absZ=round(abs(r["mw1"]), 1),
                    sR_pct=round(100 * sr, 2),
                    dC_fF=round(1e15 * r["dC_mw"], 1),
                )
            )
    out["P4_movers"] = movers

    xe = [
        r for r in rows if all(r[k] is not None for k in ("mw1", "n52", "mw7", "n56"))
    ]
    inh = np.array([split(r["mw1"], r["n52"]) for r in xe])
    near = np.array([split(r["mw7"], r["n56"]) for r in xe])
    out["cross_engine"] = {
        "ports": len(xe),
        "median_split_inherited_pct": 100 * float(np.median(inh)),
        "median_split_near_matched_pct": 100 * float(np.median(near)),
        "ports_inherited_over_1pct": int((inh > 0.01).sum()),
        "of_those_near_matched_halves_it": int(((inh > 0.01) & (near < inh / 2)).sum()),
        "worst_inherited": sorted(
            (
                dict(
                    design=r["design"],
                    port=r["port"],
                    inherited_pct=round(100 * a, 2),
                    near_matched_pct=round(100 * b, 2),
                    absZ=round(abs(r["mw1"]), 1),
                )
                for r, a, b in zip(xe, inh, near, strict=True)
            ),
            key=lambda x: -x["inherited_pct"],
        )[:12],
    }
    cp = next(
        r for r in rows if r["design"] == "verticals.elevated_buried_counterpoise"
    )
    out["counterpoise"] = {
        k: [cp[k].real, cp[k].imag] for k in ("mw1", "mw3", "mw7", "n52", "n56")
    }
    print(json.dumps(out, indent=1))
    (d.parent / "explore.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
