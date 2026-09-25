"""Compare two pre-tag sweep arms, or summarise one.

  python analyze.py results-v0.62.0.jsonl                      # one arm
  python analyze.py results-v0.62.0.jsonl results-cand.jsonl   # base vs cand

Flags (candidate vs baseline, per case id):
  * TIME   wall grew > 10 % AND > 0.5 s
  * MEM    peak RSS (ru_maxrss) grew > 10 % AND > 30 MB
  * OUTCOME ok -> anything else (and any other outcome change, listed apart)
  * Z      any port impedance moved > 1e-6 relative (|dZ| / |Z_base|)

--cross-machine (baseline and candidate on DIFFERENT boxes, e.g. Skylake vs
Haswell): TIME flags only when the candidate's wall exceeds 2x the baseline's
(and 0.5 s), since the boxes differ in speed; MEM / OUTCOME / Z are unchanged.
Z moves in (1e-9, 1e-6] are listed as information (momwire#1189's ~1e-7 on
near-ground decks lands here, as does cross-box BLAS rounding). The flagged
TIME / MEM cases are printed as a driver `--only` list for a same-box re-time.
Exit status 1 when any TIME / MEM / OUTCOME(ok->non-ok) / Z flag fires.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

WALL_REL, WALL_ABS = 0.10, 0.5
RSS_REL, RSS_ABS = 0.10, 30.0
Z_REL = 1e-6


# Geometry-by-name refusals that sweep.py's first-pass regex files as "error".
# Applied to BOTH arms at load, so an arm run before a regex change still
# compares like for like.
_REFUSAL_EXTRA = re.compile(
    r"degenerate over a conducting ground|lying in the ground plane|carries no basis",
    re.I,
)


def load(p: str) -> dict:
    rows = {}
    for line in Path(p).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if r["outcome"] == "error" and _REFUSAL_EXTRA.search(
                r.get("message") or ""
            ):
                r["outcome"] = "refused"
            rows[r["id"]] = r  # a re-run of a case supersedes the earlier row
    return rows


def _arm_label(rows: dict) -> str:
    for r in rows.values():
        if r.get("momwire_version"):
            return (
                f"momwire {r['momwire_version']} ({(r.get('momwire_sha') or '?')[:9]})"
            )
    return "?"


def summarise(rows: dict, name: str, top: int = 10) -> None:
    c = Counter(r["outcome"] for r in rows.values())
    print(
        f"== {name}: {_arm_label(rows)}, {len(rows)} cases: {dict(sorted(c.items()))}"
    )
    ok = [r for r in rows.values() if r["outcome"] == "ok"]
    print(f"-- slowest {top} (solve wall):")
    for r in sorted(ok, key=lambda r: -r["wall_s"])[:top]:
        print(f"   {r['wall_s']:8.2f} s  {r['ru_maxrss_mb']:8.0f} MB  {r['id']}")
    print(f"-- largest {top} (peak RSS):")
    for r in sorted(rows.values(), key=lambda r: -(r.get("ru_maxrss_mb") or 0))[:top]:
        w = r.get("wall_s")
        ws = f"{w:8.2f} s" if w is not None else f"{'-':>8}  "
        print(
            f"   {r.get('ru_maxrss_mb') or 0:8.0f} MB {ws}  {r['outcome']:8} {r['id']}"
        )
    bad = [r for r in rows.values() if r["outcome"] not in ("ok", "refused")]
    if bad:
        print("-- not ok / not refused:")
        for r in sorted(bad, key=lambda r: r["id"]):
            print(f"   {r['outcome']:8} {r['id']}: {(r.get('message') or '')[:160]}")


def _zrel(zb, zc) -> float:
    if zb is None or zc is None or len(zb) != len(zc):
        return float("inf")
    worst = 0.0
    for (br, bi), (cr, ci) in zip(zb, zc, strict=True):
        b, c = complex(br, bi), complex(cr, ci)
        worst = max(worst, abs(c - b) / max(abs(b), 1e-300))
    return worst


def _mode(r: dict) -> str:
    # Rows from before `driver.py fast` are serial, 4 threads and idle-gated:
    # the conditions of today's "timed" rows.
    return r.get("mode", "timed")


def compare(base: dict, cand: dict, cross: bool = False) -> int:
    flags = []
    small_z = []
    other = []
    mode_skips = 0
    common = sorted(set(base) & set(cand))
    for cid in common:
        b, c = base[cid], cand[cid]
        if b["outcome"] == "ok" and c["outcome"] != "ok":
            flags.append(
                (
                    "OUTCOME",
                    cid,
                    f"ok -> {c['outcome']}: {(c.get('message') or '')[:160]}",
                )
            )
            continue
        if b["outcome"] != c["outcome"]:
            other.append(
                (
                    cid,
                    f"{b['outcome']} -> {c['outcome']}: {(c.get('message') or '')[:120]}",
                )
            )
        if b["outcome"] != "ok" or c["outcome"] != "ok":
            continue
        # Wall is compared only between serial, idle-gated rows, and peak RSS
        # only between rows of one mode: a process's RSS depends on its thread
        # count (per-thread BLAS buffers), and a parallel row's wall on its
        # neighbours. Z and outcome are compared whatever the mode.
        same_mode = _mode(b) == _mode(c)
        if not same_mode:
            mode_skips += 1
        bw, cw = b["wall_s"], c["wall_s"]
        slow = cw > 2.0 * bw if cross else cw > bw * (1 + WALL_REL)
        if same_mode and _mode(c) == "timed" and slow and cw - bw > WALL_ABS:
            flags.append(("TIME", cid, f"{bw:.2f} -> {cw:.2f} s (x{cw / bw:.2f})"))
        bm, cm = b["ru_maxrss_mb"], c["ru_maxrss_mb"]
        if same_mode and cm > bm * (1 + RSS_REL) and cm - bm > RSS_ABS:
            flags.append(("MEM", cid, f"{bm:.0f} -> {cm:.0f} MB (x{cm / bm:.2f})"))
        zr = _zrel(b.get("z"), c.get("z"))
        if zr > Z_REL:
            flags.append(("Z", cid, f"rel {zr:.2e}: {b.get('z')} -> {c.get('z')}"))
        elif zr > 1e-9:
            small_z.append((cid, zr))
    print(
        f"\n== compare: {len(common)} common cases; only-in-base {len(set(base) - set(cand))}, "
        f"only-in-cand {len(set(cand) - set(base))}"
    )
    if mode_skips:
        print(
            f"-- {mode_skips} both-ok cases ran in different modes: memory and "
            "wall NOT compared for them (re-run the baseline with `fast`)"
        )
    for kind in ("OUTCOME", "MEM", "TIME", "Z"):
        rows = [f for f in flags if f[0] == kind]
        print(f"-- {kind}: {len(rows)}")
        for _, cid, msg in rows:
            print(f"   {cid}: {msg}")
    print(f"-- Z moved in (1e-9, 1e-6] (info, not flagged): {len(small_z)}")
    for cid, zr in sorted(small_z, key=lambda t: -t[1]):
        print(f"   {zr:.2e}  {cid}")
    retime = sorted({cid for k, cid, _ in flags if k in ("TIME", "MEM")})
    if retime:
        print(f"-- re-time on the baseline box ({len(retime)} cases), driver args:")
        print("   --only " + " ".join(f"'{c}'" for c in retime))
    if other:
        print(f"-- other outcome changes (not ok->non-ok): {len(other)}")
        for cid, msg in other:
            print(f"   {cid}: {msg}")
    # Largest improvements too, so a fix's effect is visible at a glance.
    both_ok = [
        cid for cid in common if base[cid]["outcome"] == cand[cid]["outcome"] == "ok"
    ]
    if both_ok:
        tb = sum(base[c]["wall_s"] for c in both_ok)
        tc = sum(cand[c]["wall_s"] for c in both_ok)
        print(
            f"-- total solve wall over {len(both_ok)} both-ok cases: {tb:.1f} -> {tc:.1f} s"
        )
    return 1 if flags else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("cand", nargs="?")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument(
        "--cross-machine", action="store_true", help="wall flagged only above 2x"
    )
    a = ap.parse_args()
    base = load(a.base)
    summarise(base, a.base, a.top)
    if a.cand:
        cand = load(a.cand)
        summarise(cand, a.cand, a.top)
        sys.exit(compare(base, cand, a.cross_machine))


if __name__ == "__main__":
    main()
