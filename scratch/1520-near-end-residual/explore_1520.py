"""AK#1520, EXPLORATORY and not registered: does Part D's feed-position ripple
account for the whole-wire vs split residual?

  python scratch/1520-near-end-residual/explore_1520.py scratch/1520-near-end-residual

(a) On AL (only the loads split) the long run holding the feed is re-gridded, so
    the feed's position within its segment, xi, changes. The shift |Z_AL - Z_A|
    is set against |cos 2 pi xi_AL - cos 2 pi xi_A|.
(b) Part D's k3 continuous-feed sweep (`partd_rows_d.jsonl`, copied from
    scratch/1511-bs2-split-study at 4bcf7b2; its Z(N) equals this study's A
    exactly) is fitted per base N with Z = a + b/n^2 + c cos 2 pi xi + s sin 2 pi
    xi. The fit predicts Z with the feed centred (xi = 0.5), which is compared
    with the split (B) and the feed-only split (AF).

Nothing here is a bar. Writes explore_1520.json beside the records.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np


def main():
    here = Path(sys.argv[1])
    rows = {}
    for name in ("rows.jsonl", "rows_e.jsonl"):
        for line in (here / name).read_text().splitlines():
            rec = json.loads(line)
            if not rec.get("_meta"):
                rows[(rec["engine"], rec["case"], rec["geometry"], rec["n"])] = rec

    def z(geom, n):
        return complex(*rows[("bs2", "base", geom, n)]["z"])

    out = {"al_feed_xi": [], "ripple_fit": []}
    for n in (41, 81, 161, 321):
        xi_a = (0.31 * n) % 1.0
        lo, hi, count, _i = next(
            p
            for p in rows[("bs2", "base", "AL", n)]["authored_pieces"]
            if p[0] <= 0.31 < p[1]
        )
        xi_al = ((0.31 - lo) / (hi - lo) * count) % 1.0
        out["al_feed_xi"].append(
            {
                "n": n,
                "xi_A": xi_a,
                "xi_AL": xi_al,
                "abs_dcos": abs(
                    math.cos(2 * math.pi * xi_al) - math.cos(2 * math.pi * xi_a)
                ),
                "abs_AL_minus_A": abs(z("AL", n) - z("A", n)),
            }
        )
    partd = {}
    for line in (here / "partd_rows_d.jsonl").read_text().splitlines():
        rec = json.loads(line)
        if (
            not rec.get("_meta")
            and rec["case"] == "k3"
            and rec["ground"] == "free"
            and rec["path"] == "cont"
            and rec.get("status") == "ok"
        ):
            partd[rec["n"]] = (
                complex(*rec["z"]),
                next(p["xi"] for p in rec["ports"] if p["name"] == "feed"),
            )
    for base in (41, 81, 161):
        ns = list(range(base - 5, base + 6))
        zs = np.array([partd[n][0] for n in ns])
        xs = np.array([partd[n][1] for n in ns])
        design = np.column_stack(
            [
                np.ones(len(ns)),
                1.0 / np.array(ns, float) ** 2,
                np.cos(2 * np.pi * xs),
                np.sin(2 * np.pi * xs),
            ]
        )
        coef = (
            np.linalg.lstsq(design, zs.real, rcond=None)[0]
            + 1j * np.linalg.lstsq(design, zs.imag, rcond=None)[0]
        )
        centred = coef[0] + coef[1] / base**2 - coef[2]
        out["ripple_fit"].append(
            {
                "base": base,
                "partd_equals_A": abs(partd[base][0] - z("A", base)),
                "fit_residual_max": float(np.max(np.abs(zs - design @ coef))),
                "amp_cos": abs(coef[2]),
                "amp_sin": abs(coef[3]),
                "predicted_centred": [centred.real, centred.imag],
                "abs_pred_minus_B": abs(centred - z("B", base)),
                "abs_pred_minus_AF": abs(centred - z("AF", base)),
                "r_B": abs(z("B", base) - z("A", base)),
            }
        )
    (here / "explore_1520.json").write_text(json.dumps(out, indent=1))
    for row in out["al_feed_xi"]:
        print(
            f"(a) n={row['n']}: xi_A {row['xi_A']:.2f} xi_AL {row['xi_AL']:.2f} "
            f"|dcos| {row['abs_dcos']:.2f} |AL-A| {row['abs_AL_minus_A']:.4f}"
        )
    for row in out["ripple_fit"]:
        print(
            f"(b) N={row['base']}: fit residual max {row['fit_residual_max']:.4f}, cos amplitude {row['amp_cos']:.4f}; "
            f"|pred - B| {row['abs_pred_minus_B']:.4f}, |pred - AF| {row['abs_pred_minus_AF']:.4f}, r_B {row['r_B']:.4f}"
        )


if __name__ == "__main__":
    main()
