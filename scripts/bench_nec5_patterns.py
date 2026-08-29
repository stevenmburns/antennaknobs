"""Pattern census: NEC-5 vs bs2 across the catalog (#872 phase 4).

Per built-in design (free space), solve the far field on NEC5Engine and
MomwireEngine(bs2) over the shared 1-degree upper-hemisphere grid and
compare `pattern_metrics` (peak dBi, takeoff, azimuth, F/B, az/el
beamwidths) plus the RMS dB difference over the co-illuminated grid
(both engines within 30 dB of their peak — nulls and floor values carry
no shape information).

Flags per the issue: |Δpeak| > 0.5 dB or |Δtakeoff| > 2°. Designs whose
dialect NEC-5 deliberately refuses (TL/NT, distributed ports, ...) are
counted out-of-scope, exactly like the impedance census.

Patterns are far less mesh-sensitive than feed impedance (the knot-source
march is a feed-region effect; gain is a global functional), so this
census runs single-mesh: nominal_nsegs = 81 when the design stays under
--seg-cap, else its as-shipped default (recorded per row).

    python scripts/bench_nec5_patterns.py --out patterns.json
    python scripts/bench_nec5_patterns.py --only dipoles.invvee beams.yagi
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_converge as bc  # sibling: design loading

PREFERRED_NSEG = 81
DEFAULT_SEG_CAP = 3000
PEAK_FLAG_DB = 0.5
TAKEOFF_FLAG_DEG = 2.0
COILLUM_DB = 30.0  # compare shape where both patterns are within this of peak


def far_field_metrics(engine):
    from antennaknobs.far_field import pattern_metrics

    ff = engine.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    return pattern_metrics(ff), np.asarray(ff.rings, float)


def rms_db(rings_a: np.ndarray, rings_b: np.ndarray) -> float:
    mask = (rings_a > rings_a.max() - COILLUM_DB) & (
        rings_b > rings_b.max() - COILLUM_DB
    )
    if not mask.any():
        return float("nan")
    d = rings_a[mask] - rings_b[mask]
    return float(np.sqrt(np.mean(d * d)))


def census_row(design: str, seg_cap: int, capture_dir) -> dict:
    from antennaknobs.engines import MomwireEngine, NEC5Engine
    from momwire import BSplineSolver

    row = {"design": design, "error": None, "out_of_scope": None}
    try:
        cls = bc.load_design(design)
        nseg = PREFERRED_NSEG
        if bc.total_nominal_segs(cls, nseg) > seg_cap:
            nseg = cls().nominal_nsegs
        row["nseg"] = nseg

        def build(kind):
            b = cls()
            b.nominal_nsegs = nseg
            if kind == "nec5":
                return NEC5Engine(b, capture_dir=capture_dir)
            return MomwireEngine(b, solver=BSplineSolver, solver_kwargs={"degree": 2})

        t0 = time.time()
        m5, r5 = far_field_metrics(build("nec5"))
        row["t_nec5"] = time.time() - t0
        t0 = time.time()
        mb, rb = far_field_metrics(build("bs2"))
        row["t_bs2"] = time.time() - t0
    except NotImplementedError as e:
        row["out_of_scope"] = str(e)[:100]
        return row
    except Exception as e:  # noqa: BLE001 — record, keep sweeping
        row["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return row

    def ang_diff(a, b):
        return abs((a - b + 180.0) % 360.0 - 180.0)

    row["nec5"] = m5
    row["bs2"] = mb
    row["rms_db"] = rms_db(r5, rb)
    row["d_peak_db"] = m5["peak_gain_dbi"] - mb["peak_gain_dbi"]
    row["d_takeoff_deg"] = m5["takeoff_deg"] - mb["takeoff_deg"]
    row["d_azimuth_deg"] = ang_diff(m5["azimuth_deg"], mb["azimuth_deg"])
    row["d_fb_db"] = m5["front_to_back_db"] - mb["front_to_back_db"]
    # A takeoff delta only means something when the gain surfaces actually
    # differ: on a broad flat lobe (free-space dipoles) the argmax twitches
    # degrees between engines whose patterns match to milli-dB. Gate the
    # takeoff flag on RMS shape difference.
    row["flagged"] = abs(row["d_peak_db"]) > PEAK_FLAG_DB or (
        abs(row["d_takeoff_deg"]) > TAKEOFF_FLAG_DEG and row["rms_db"] > 0.1
    )
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="+", default=None)
    ap.add_argument("--seg-cap", type=int, default=DEFAULT_SEG_CAP)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--nec5-capture-dir",
        type=Path,
        default=Path.home() / ".antennaknobs" / "nec5-captures",
    )
    args = ap.parse_args(argv)

    from antennaknobs.cli import list_builtin_designs
    from antennaknobs.engines.nec5 import find_nec5

    if find_nec5() is None:
        sys.exit("$NEC5_EXE does not resolve to an executable")

    designs = args.only or list_builtin_designs()
    rows = []
    for i, d in enumerate(designs, 1):
        print(f"[{i}/{len(designs)}] {d} ...", flush=True)
        rows.append(census_row(d, args.seg_cap, args.nec5_capture_dir))

    ok = [r for r in rows if not r.get("error") and not r.get("out_of_scope")]
    oos = [r for r in rows if r.get("out_of_scope")]
    errs = [r for r in rows if r.get("error")]
    flagged = [r for r in ok if r["flagged"]]

    print("\n" + "=" * 100)
    print(
        f"PATTERN CENSUS nec5 vs bs2 — {len(ok)} compared, {len(oos)} OOS, "
        f"{len(errs)} errors; flags: |dpeak| > {PEAK_FLAG_DB} dB or "
        f"|dtakeoff| > {TAKEOFF_FLAG_DEG} deg"
    )
    print("=" * 100)
    print(
        f"{'design':<34} {'peak5':>7} {'dpeak':>7} {'dtake':>7} {'daz':>6}"
        f" {'dF/B':>7} {'rmsdB':>7}  flag"
    )
    for r in sorted(ok, key=lambda r: -abs(r["d_peak_db"])):
        print(
            f"{r['design']:<34} {r['nec5']['peak_gain_dbi']:>7.2f}"
            f" {r['d_peak_db']:>+7.2f} {r['d_takeoff_deg']:>+7.1f}"
            f" {r['d_azimuth_deg']:>6.1f} {r['d_fb_db']:>+7.2f}"
            f" {r['rms_db']:>7.3f}  {'FLAG' if r['flagged'] else ''}"
        )
    if ok:
        dps = [abs(r["d_peak_db"]) for r in ok]
        rms = [r["rms_db"] for r in ok if not math.isnan(r["rms_db"])]
        print(
            f"\n|dpeak| median {sorted(dps)[len(dps) // 2]:.3f} dB, max {max(dps):.3f};"
            f" rms dB median {sorted(rms)[len(rms) // 2]:.3f}"
            f"   flagged: {len(flagged)}/{len(ok)}"
        )
    if oos:
        print(f"\nOOS ({len(oos)}):")
        for r in oos:
            print(f"  {r['design']:<34} {r['out_of_scope'][:60]}")
    if errs:
        print(f"\nERRORS ({len(errs)}):")
        for r in errs:
            print(f"  {r['design']:<34} {r['error'][:60]}")

    if args.out:
        args.out.write_text(json.dumps(rows, indent=1))
        print(f"\nfull results -> {args.out}")


if __name__ == "__main__":
    main()
