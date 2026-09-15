"""AK#1456's analysis: P1-P5 and C_ref from `sensitivity.py`'s records.

  python scratch/1456-fed-segments/analyze.py DIR [--out analysis.json]

Fixed before the data exists (committed with the harness, ahead of the full
run). The readings of PLAN.md it commits to:

  * A PORT is one entry of an engine's impedance list, matched by index across
    the variants of one design. A variant that errored drops that design's
    ports from every statistic needing it.
  * Y = 1 / Z. Under momwire 1->3, dY = Y(mw3) - Y(mw1). Under NEC-5 2->6,
    dY = Y(n56) - Y(n52). dC = Im(dY) / omega, omega = 2 pi f.
  * P1: the median over ports of |Re dY| / |Im dY| under momwire 1->3. A port
    whose dY is exactly 0 has no defined fraction and is left out.
  * P2: s = |Z(mw3) - Z(mw1)| / |Z(mw1)|, Spearman-correlated (average ranks
    for ties) over ports with |Z(mw1)| * f and with |X(mw1)| / |R(mw1)|.
  * P3: p90 / p10 of |dC| under momwire 1->3 over ports with dC != 0.
  * P4: designs with any port where |R(mw3) - R(mw1)| / |R(mw1)| > 0.01.
  * P5: `verticals.elevated_buried_counterpoise`'s B split,
    |B_mw - B_n5| / max(|B_mw|, |B_n5|): inherited (mw1 against n52) and
    near-matched (mw7 against n56).
  * C_ref: over ports where BOTH engines' refinements are available, the
    larger |dC| of the two per port, then the 90th percentile
    (numpy's default linear interpolation). The flag threshold is
    |Z| >= 0.01 / (2 pi f C_ref).
  * If P2 fails, C_ref is still computed and printed, marked ABANDONED, and
    no flag threshold is proposed from it.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

COUNTERPOISE = "verticals.elevated_buried_counterpoise"


def rank(a):
    a = np.asarray(a, dtype=float)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a))
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
            j += 1
        ranks[order[i : j + 1]] = 0.5 * (i + j)
        i = j + 1
    return ranks


def spearman(x, y):
    rx, ry = rank(x), rank(y)
    rx -= rx.mean()
    ry -= ry.mean()
    return float((rx @ ry) / math.sqrt((rx @ rx) * (ry @ ry)))


def zlist(run):
    if not run or run.get("status") != "ok":
        return None
    return [complex(r, x) for r, x in run["z"]]


def ports(recs):
    out = []
    for rec in recs:
        if rec.get("status") != "ok":
            continue
        runs = rec["runs"]
        z = {k: zlist(runs.get(k)) for k in ("mw1", "mw3", "mw7", "n52", "n56")}
        n = len(z["mw1"]) if z["mw1"] else 0
        f = rec["freq_mhz"] * 1e6
        omega = 2 * math.pi * f
        for p in range(n):
            row = dict(design=rec["design"], port=p, f=f)
            for k, zz in z.items():
                row[k] = zz[p] if zz is not None and len(zz) > p else None
            if row["mw1"] is not None and row["mw3"] is not None:
                dy = 1 / row["mw3"] - 1 / row["mw1"]
                row["dY_mw"] = dy
                row["dC_mw"] = dy.imag / omega
            if row["n52"] is not None and row["n56"] is not None:
                dy = 1 / row["n56"] - 1 / row["n52"]
                row["dY_n5"] = dy
                row["dC_n5"] = dy.imag / omega
            out.append(row)
    return out


def bsplit(za, zb):
    ba, bb = (1 / za).imag, (1 / zb).imag
    return abs(ba - bb) / max(abs(ba), abs(bb))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    d = Path(args.dir)
    recs = [
        json.loads(p.read_text())
        for p in sorted(d.glob("*.json"))
        if p.name != "_meta.json"
    ]
    status = {}
    for r in recs:
        status.setdefault(r.get("status"), []).append(r["design"])
    rows = ports(recs)
    mw = [r for r in rows if "dY_mw" in r]
    res = dict(
        status_counts={k: len(v) for k, v in status.items()},
        ports=len(rows),
        ports_mw=len(mw),
    )

    fr = [
        abs(r["dY_mw"].real) / abs(r["dY_mw"].imag) for r in mw if r["dY_mw"].imag != 0
    ]
    res["P1_shunt_fraction_median"] = float(np.median(fr)) if fr else None
    res["P1_pass"] = (
        res["P1_shunt_fraction_median"] is not None
        and res["P1_shunt_fraction_median"] <= 0.1
    )

    s = [abs(r["mw3"] - r["mw1"]) / abs(r["mw1"]) for r in mw]
    zf = [abs(r["mw1"]) * r["f"] for r in mw]
    xr = [
        abs(r["mw1"].imag) / abs(r["mw1"].real) if r["mw1"].real != 0 else float("inf")
        for r in mw
    ]
    res["P2_rho_Zf"] = spearman(s, zf) if len(mw) > 2 else None
    res["P2_rho_XR"] = spearman(s, xr) if len(mw) > 2 else None
    res["P2_pass"] = (
        res["P2_rho_Zf"] is not None
        and res["P2_rho_Zf"] >= 0.9
        and res["P2_rho_Zf"] > res["P2_rho_XR"]
    )

    dc = np.array([abs(r["dC_mw"]) for r in mw if r["dC_mw"] != 0])
    if len(dc):
        p10, p90 = np.percentile(dc, 10), np.percentile(dc, 90)
        res["P3_dC_mw_p10_fF"], res["P3_dC_mw_p90_fF"] = 1e15 * p10, 1e15 * p90
        res["P3_ratio"] = float(p90 / p10) if p10 > 0 else None
        res["P3_pass"] = res["P3_ratio"] is not None and res["P3_ratio"] <= 10

    moved = sorted(
        {
            r["design"]
            for r in mw
            if r["mw1"].real != 0
            and abs(r["mw3"].real - r["mw1"].real) / abs(r["mw1"].real) > 0.01
        }
    )
    res["P4_designs"] = moved
    res["P4_pass"] = len(moved) <= 5 and COUNTERPOISE in moved

    cp = [r for r in rows if r["design"] == COUNTERPOISE]
    if cp and all(cp[0][k] is not None for k in ("mw1", "n52", "mw7", "n56")):
        inh, near = (
            bsplit(cp[0]["mw1"], cp[0]["n52"]),
            bsplit(cp[0]["mw7"], cp[0]["n56"]),
        )
        res["P5_B_split_inherited_pct"], res["P5_B_split_near_pct"] = (
            100 * inh,
            100 * near,
        )
        res["P5_pass"] = inh > 0.10 and near <= 0.02
    else:
        res["P5_pass"] = None

    both = [r for r in rows if "dC_mw" in r and "dC_n5" in r]
    if both:
        cref = float(
            np.percentile([max(abs(r["dC_mw"]), abs(r["dC_n5"])) for r in both], 90)
        )
        res["C_ref_fF"] = 1e15 * cref
        res["C_ref_ports"] = len(both)
        res["C_ref_status"] = "proposed" if res["P2_pass"] else "ABANDONED (P2 failed)"
        flagged = []
        for r in rows:
            if r["mw1"] is None:
                continue
            if abs(r["mw1"]) * 2 * math.pi * r["f"] * cref >= 0.01:
                flagged.append(
                    dict(
                        design=r["design"],
                        port=r["port"],
                        absZ=abs(r["mw1"]),
                        f_mhz=r["f"] / 1e6,
                    )
                )
        res["flagged_at_defaults"] = flagged
        res["Z_flag_ohm_at_7MHz"] = 0.01 / (2 * math.pi * 7.0e6 * cref)
        res["Z_flag_ohm_at_14MHz"] = 0.01 / (2 * math.pi * 14.0e6 * cref)

    per_port = []
    for r in rows:
        per_port.append(
            {
                k: ([v.real, v.imag] if isinstance(v, complex) else v)
                for k, v in r.items()
            }
        )
    res["excluded"] = {
        r["design"]: r.get("reason") for r in recs if r.get("status") == "excluded"
    }
    res["errors"] = {
        r["design"]: {
            k: v.get("error")
            for k, v in r.get("runs", {}).items()
            if v.get("status") != "ok"
        }
        for r in recs
        if r.get("status") == "ok"
        and any(v.get("status") != "ok" for v in r["runs"].values())
    }
    res["failed_designs"] = {
        k: v for k, v in status.items() if k not in ("ok", "excluded")
    }
    print(
        json.dumps(
            {
                k: v
                for k, v in res.items()
                if k not in ("flagged_at_defaults", "excluded", "errors")
            },
            indent=1,
        )
    )
    print(
        "flagged at defaults:",
        json.dumps(res.get("flagged_at_defaults"), indent=None)[:2000],
    )
    if args.out:
        Path(args.out).write_text(
            json.dumps(dict(summary=res, ports=per_port), indent=1)
        )


if __name__ == "__main__":
    main()
