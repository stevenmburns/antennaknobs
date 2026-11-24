"""raw.jsonl -> the tables in faster-solves.md (summary.txt).

Per (case, switch): the median of reps 1-3 (rep 0, the cold solve, is shown
separately), the fill report's route and reuse state (which must be the same
in every rep, or the row is flagged), and Z to the readout's two decimals.
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

raw = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("raw.jsonl"))
rows = defaultdict(list)
for line in raw.read_text().splitlines():
    d = json.loads(line)
    rows[(d["case"], d["on"])].append(d)

hdr = (
    f"{'case':28} {'sw':3} {'segs':>5} {'fill':>6} {'factor':>6} {'census':>6} "
    f"{'total':>6} {'cold':>6}  {'route':6} {'reuse':9} {'Z (readout)':>18}  |dZ|/|Z| vs off"
)
print(hdr)
off_z = {}
for (case, on), rs in rows.items():
    timed = [r for r in rs if r["rep"] >= 1]
    cold = [r for r in rs if r["rep"] == 0]
    med = {
        k: statistics.median(r[k] for r in timed)
        for k in ("fill_s", "factor_s", "census_s", "wall_s")
    }
    states = {(r["route"], r["reuse_state"], json.dumps(r["sector"])) for r in rs}
    zs = {(round(r["z_re"], 9), round(r["z_im"], 9)) for r in rs}
    r0 = rs[0]
    z = complex(r0["z_re"], r0["z_im"])
    if not on:
        off_z[case] = z
    rel = abs(z - off_z[case]) / abs(off_z[case]) if on and case in off_z else None
    flag = "" if len(states) == 1 else "  !! state differs between reps"
    flag += "" if len(zs) == 1 else "  (Z varies between reps)"
    sign = "+" if z.imag >= 0 else "-"
    reuse = r0["reuse_state"] or ("off" if not r0["reuse_asked"] else "none")
    print(
        f"{case:28} {'on' if on else 'off':3} {r0['segments']:>5} "
        f"{med['fill_s']:6.2f} {med['factor_s']:6.2f} {med['census_s']:6.2f} "
        f"{med['wall_s']:6.2f} {cold[0]['wall_s'] if cold else float('nan'):6.2f}  "
        f"{r0['route']:6} {reuse:9} {z.real:8.2f} {sign} j{abs(z.imag):6.2f}  "
        f"{'' if rel is None else f'{rel:.1e}'}{flag}"
    )
    if cold:
        c = cold[0]
        print(
            f"{'':34}cold (rep 0, first solve of this geometry in the process): "
            f"fill {c['fill_s']:.2f}, census {c['census_s']:.2f}, "
            f"factor {c['factor_s']:.2f}, total {c['wall_s']:.2f}"
        )
    if r0["reuse_declined"]:
        print(f"{'':34}declined: {r0['reuse_declined']}")
    if r0["sector"]:
        s = r0["sector"]
        print(
            f"{'':34}sector: {s['n_sectors']} sectors, {s['axial']} axis wire(s), "
            f"{s['computed_pairs']:,} of {s['pairs']:,} entries computed"
        )
    if r0["reuse_state"] in ("served", "partial") and r0["pairs"]:
        paid = (r0["computed"] or 0) + (r0["near"] or 0)
        print(
            f"{'':34}reuse: {r0['pairs']:,} pairs, {r0['computed']:,} computed, "
            f"{r0['reused']:,} reused, {r0['near']:,} near; compression "
            f"{r0['pairs'] / paid:.1f}x"
        )

# The vertical's off rows were measured twice (once beside each switch); the
# page quotes the median of all six timed solves of each.
print("\npooled off rows, verticals.vertical 16 radials (6 timed solves each):")
for tag in ("bs2", "sin"):
    xs = [
        r
        for (case, on), rs in rows.items()
        if not on and case in (f"vertical16_sector_{tag}", f"vertical16_reuse_{tag}")
        for r in rs
        if r["rep"] >= 1
    ]
    if xs:
        print(
            f"  {tag}: fill {statistics.median(r['fill_s'] for r in xs):.2f}, "
            f"factor {statistics.median(r['factor_s'] for r in xs):.2f}, "
            f"total {statistics.median(r['wall_s'] for r in xs):.2f} "
            f"(range {min(r['wall_s'] for r in xs):.2f}-{max(r['wall_s'] for r in xs):.2f})"
        )
