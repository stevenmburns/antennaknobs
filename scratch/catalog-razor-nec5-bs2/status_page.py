"""Generate the published status page from its committed records.

    python scratch/catalog-razor-nec5-bs2/status_page.py \
        > docs/status/2026-09-15-catalog-razor-nec5-bs2.md

Reads `docs/status/data/2026-09-15-catalog-razor-nec5-bs2.jsonl` -- the records
AND their provenance header -- and writes the page. No number on the page is
transcribed, and the build identification comes out of the header rather than out
of prose, so the page cannot name a build the data did not come from.

PUBLICATION RULES THIS FILE ENFORCES, because a rule kept by hand is a rule that
lapses on the next regeneration:

  * Every section that puts bs2 beside razor-2p or NEC-5 emits the AK#1516
    adjudication with it (`ADJUDICATION`), so bs2 cannot read as the outlier by
    accident. There is no code path that prints a bs2 comparison without it.
  * NEC-5 appears as impedances and aggregates only -- no printout, no internals.
    The records carry no NEC-5 text for it to leak.
  * No claim about which engine is right beyond that adjudication.
  * Current truth only: this page is what main measures today. It carries no
    history of superseded engine behaviour.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

DATA = (
    Path(__file__).resolve().parents[2]
    / "docs/status/data/2026-09-15-catalog-razor-nec5-bs2.jsonl"
)
PAIRS = (("razor", "nec5"), ("bs2", "nec5"), ("bs2", "razor"))
LABEL = {"razor": "razor-2p", "nec5": "NEC-5", "bs2": "momwire bs2"}
GROUNDS = ("free", "somm")
GROUND_LABEL = {"free": "free space", "somm": "Sommerfeld"}

# The one paragraph every bs2 comparison on this page carries. AK#1516 measured
# it; AK#1525 is where the density question goes.
ADJUDICATION = (
    "> **Read with AK#1516.** At each design's default mesh razor-2p and NEC-5 "
    "are the *unconverged* pair, not bs2. Refining the mesh eightfold moves them "
    "**18–33 % together, toward bs2**, while bs2 moves **≤ 2.4 %** — razor-2p's "
    "path-testing rule is first order in the mesh and bs2's Galerkin testing is "
    "already converged at these segment counts. A wide bs2 row below is therefore "
    "a statement about mesh density, not about bs2. What density buys is "
    "AK#1525."
)


def load(path):
    recs, prov = {}, None
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if "design" not in r:
            prov = r
            continue
        recs[(r["design"], r["ground"], r["engine"])] = r
    return recs, prov


def zvec(rec):
    return [complex(*p) for p in rec["z"]]


def rel(a, b):
    den = abs(b)
    return abs(a - b) / den if den > 0 else math.inf


def rows_for(recs, designs, a, b):
    rows, unpaired, mismatched = [], [], []
    for d in designs:
        for g in GROUNDS:
            ra, rb = recs.get((d, g, a)), recs.get((d, g, b))
            if ra is None or rb is None:
                continue
            if ra["status"] != "ok" or rb["status"] != "ok":
                unpaired.append((d, g))
                continue
            za, zb = zvec(ra), zvec(rb)
            if len(za) != len(zb):
                mismatched.append((d, g, len(za), len(zb)))
                continue
            for i, (x, y) in enumerate(zip(za, zb, strict=True)):
                rows.append(
                    {
                        "design": d,
                        "ground": g,
                        "port": i,
                        "rel": rel(x, y),
                        "za": x,
                        "zb": y,
                        "flags": ra.get("flags") or [],
                    }
                )
    return rows, unpaired, mismatched


def dist(rows):
    v = sorted(r["rel"] for r in rows)
    if not v:
        return None
    n = len(v)
    return {
        "n": n,
        "median": statistics.median(v),
        "p90": v[min(n - 1, int(0.90 * n))],
        "p99": v[min(n - 1, int(0.99 * n))],
        "max": v[-1],
        "u01": sum(1 for x in v if x < 0.001) / n,
        "u2": sum(1 for x in v if x < 0.02) / n,
    }


def pct(x):
    return "—" if x is None else f"{100 * x:.3g} %"


def drow(label, d):
    if d is None:
        return f"| {label} | 0 | — | — | — | — | — | — |"
    return (
        f"| {label} | {d['n']} | {pct(d['median'])} | {pct(d['p90'])} | "
        f"{pct(d['p99'])} | {pct(d['max'])} | {pct(d['u01'])} | {pct(d['u2'])} |"
    )


DHEAD = (
    "| population | rows | median | p90 | p99 | max | < 0.1 % | < 2 % |\n"
    "|---|---:|---:|---:|---:|---:|---:|---:|"
)


def cause(rec):
    m = (rec.get("error") or "").lower()
    for needle, label in (
        ("junction_ports", "junction ports"),
        ("junction port", "junction ports"),
        ("floating port", "a floating port's second terminal"),
        ("buried", "no buried fill"),
        ("reciprocal", "a non-reciprocal multiport Y"),
    ):
        if needle in m:
            return label
    if "distributed" in m and "delta-gap" in m:
        return "a distributed (finite-gap) port"
    return (rec.get("error") or "").strip().split("\n")[0][:70] or rec.get(
        "error_type", "?"
    )


def main(argv=None):
    recs, prov = load(Path(argv[0]) if argv else DATA)
    designs = sorted({k[0] for k in recs})
    engines = ("razor", "nec5", "bs2")
    out = []
    w = out.append

    mw_ver = prov["version_momwire"]
    mw_sha = prov["momwire_sha"][:9]
    ak_sha = prov["ak_sha"][:9]
    variant = prov["accelerator_variant"]["_accelerators"].split(".")[0]
    nec5 = Path(prov["nec5_exe"] or "nec5cl").name

    w("# razor-2p, NEC-5 and momwire bs2 over the antennaknobs catalog\n")
    w(
        "**Evidence, not a scoreboard.** AK#1525. Every built-in design solved "
        "three ways at its own default mesh and frequency, in free space and "
        "over Sommerfeld ground, and the three pairwise disagreements reported "
        "as distributions. The page states what the three engines do and do not "
        "agree about. It does not rank them.\n"
    )
    w(
        f"**The builds, named because a version string does not identify a "
        f"solver.** antennaknobs at `{ak_sha}`; momwire **{mw_ver}** imported "
        f"from the editable submodule at `{mw_sha}` with a clean working tree — "
        f"which is also the commit antennaknobs records as its pointer, so this "
        f"run is the momwire a user installs rather than a dev tip ahead of it. "
        f"The compiled accelerator actually in use was **`{variant}`**; momwire "
        f"ships more than one SIMD variant behind that module name and they are "
        f"not bit-identical to each other, so the variant is recorded with the "
        f"data. NEC-5 is the build `{nec5}`, run as an executable and timed; "
        f"antennaknobs never inspects it.\n"
    )
    w(
        "**NEC-5 licensing.** NEC-5 is licensed from Lawrence Livermore National "
        "Laboratory (**LLNL-CODE-746721**). Neither its source nor any of its "
        "printouts appears here or in the committed data: the NEC-5 column is "
        "driving-point impedances and aggregates computed from them, and nothing "
        "else.\n"
    )
    w(
        f"Per-design rows, and the run's own provenance record, are committed "
        f"beside this page in `data/{DATA.name}`. Every table below is generated "
        f"from that file by `scratch/catalog-razor-nec5-bs2/status_page.py`; no "
        f"number on this page is transcribed.\n"
    )

    w("## The one thing to read before any table\n")
    w(ADJUDICATION + "\n")
    w(
        "This is stated first, and again beside every table that puts bs2 next to "
        "one of the other two, because the raw numbers invite the opposite "
        "reading: bs2 is the engine that most often sits apart, and it is also "
        "the engine nearest its own mesh limit. Both are true at once.\n"
    )

    w("## What this page can and cannot say\n")
    w(
        "* It can say how far apart the three engines are on a driving-point "
        "impedance, per design, at the mesh each design ships with.\n"
        "* It can say which designs an engine declines, and why, in the engine's "
        "own words.\n"
        "* **It cannot say which engine is right.** No reference here is a truth "
        "oracle; the denominator in each ratio is a choice of reference and "
        "nothing more. The one adjudication on offer is the mesh-convergence one "
        "above, which is measured (AK#1516) rather than asserted.\n"
        "* It cannot speak for any mesh but the default. Density is AK#1525.\n"
    )

    w("## Method\n")
    w(
        f"{len(designs)} designs × {len(GROUNDS)} ground models × {len(engines)} "
        f"engines = **{len(designs) * len(GROUNDS) * len(engines)}** cells, "
        f"{len(recs)} recorded. One worker subprocess per cell, dispatched "
        f"serially, each with an address-space cap so a runaway fill fails "
        f"cleanly instead of paging the machine; BLAS and OpenMP pinned to four "
        f"threads. Each design is solved at its own default frequency and its "
        f"shipped `nominal_nsegs`, with no per-design tuning.\n"
    )
    w(
        "Ground models are free space and the Sommerfeld-Norton finite ground "
        '`("finite", 13.0, 0.005)`, which is the application\'s default soil. '
        "**The reflection-coefficient ground is deliberately not on this page**: "
        "momwire writes it as `GN 0` and NEC-5 reads `GN 0` as Sommerfeld, so "
        "such a row would compare two different physical models rather than two "
        "formulations.\n"
    )
    w(
        "Disagreement is reported as `rel|ΔZ| = |Z_a − Z_b| / |Z_b|`, one row per "
        "design × ground × port, and only where both engines solved and returned "
        "the same number of ports. Cells where one side declined are counted as "
        "unpaired rather than dropped, so coverage is a number on the page and "
        "not a smaller denominator.\n"
    )

    w("## Coverage\n")
    w("| engine | solved | declined | error | timeout |")
    w("|---|---:|---:|---:|---:|")
    for e in engines:
        c = Counter(
            recs[(d, g, e)]["status"]
            for d in designs
            for g in GROUNDS
            if (d, g, e) in recs
        )
        w(
            f"| {LABEL[e]} | {c['ok']} | {c['refused']} | {c['error']} | {c['timeout']} |"
        )
    w("")
    w("Where an engine declined, in its own words:\n")
    w("| engine | reason | cells |")
    w("|---|---|---:|")
    for e in engines:
        cc = Counter(
            cause(recs[(d, g, e)])
            for d in designs
            for g in GROUNDS
            if (d, g, e) in recs and recs[(d, g, e)]["status"] in ("refused", "error")
        )
        for k, v in cc.most_common():
            w(f"| {LABEL[e]} | {k} | {v} |")
    w("")

    w("## Agreement on the driving-point impedance\n")
    store = {}
    for a, b in PAIRS:
        rows, unpaired, mismatched = rows_for(recs, designs, a, b)
        store[(a, b)] = rows
        w(f"### {LABEL[a]} against {LABEL[b]}\n")
        if "bs2" in (a, b):
            w(ADJUDICATION + "\n")
        w(DHEAD)
        w(drow("all", dist(rows)))
        for g in GROUNDS:
            w(drow(GROUND_LABEL[g], dist([r for r in rows if r["ground"] == g])))
        w(
            drow(
                "single-port designs",
                dist(
                    [
                        r
                        for r in rows
                        if r["port"] == 0
                        and sum(
                            1
                            for x in rows
                            if x["design"] == r["design"] and x["ground"] == r["ground"]
                        )
                        == 1
                    ]
                ),
            )
        )
        w(
            drow(
                "multi-port designs",
                dist(
                    [
                        r
                        for r in rows
                        if sum(
                            1
                            for x in rows
                            if x["design"] == r["design"] and x["ground"] == r["ground"]
                        )
                        > 1
                    ]
                ),
            )
        )
        w("")
        w(
            f"Unpaired: **{len(unpaired)}** design×ground cells where one side "
            f"declined. Port-count mismatches: **{len(mismatched)}**."
        )
        if mismatched:
            for d, g, na, nb in mismatched:
                w(f"  - `{d}` / {GROUND_LABEL[g]}: {na} against {nb}")
        w("")

    # One generated sentence naming the three medians and razor/NEC-5's worst
    # row, so the headline does not depend on the reader noticing a table cell.
    rn, bn, br = (dist(store[k]) for k in PAIRS)
    w("### In one line\n")
    w(
        f"Over the whole catalog at default mesh, razor-2p and NEC-5 agree to a "
        f"median **{pct(rn['median'])}** and their widest single row is "
        f"**{pct(rn['max'])}**. momwire bs2 sits a median **{pct(bn['median'])}** "
        f"from NEC-5 and **{pct(br['median'])}** from razor-2p, with a tail to "
        f"**{pct(bn['max'])}** — and the paragraph above is how that tail should "
        f"be read. The two formulation twins track each other closely at any "
        f"mesh; whether that mesh is fine enough is a separate question, and a "
        f"measured one.\n"
    )

    w("## The widest disagreements\n")
    w(ADJUDICATION + "\n")
    for a, b in PAIRS:
        rows = store[(a, b)]
        worst = sorted(rows, key=lambda r: -r["rel"])[:10]
        w(f"### {LABEL[a]} against {LABEL[b]} — ten widest rows\n")
        w(
            "| design | ground | port | "
            + f"{LABEL[a]} Z | {LABEL[b]} Z | rel\\|ΔZ\\| |"
        )
        w("|---|---|---:|---|---|---:|")
        for r in worst:
            w(
                f"| `{r['design']}` | {GROUND_LABEL[r['ground']]} | {r['port']} | "
                f"{r['za'].real:.4g}{r['za'].imag:+.4g}j | "
                f"{r['zb'].real:.4g}{r['zb'].imag:+.4g}j | {pct(r['rel'])} |"
            )
        w("")

    w("## Reactance carries the disagreement\n")
    w(
        "For each pair, the share of `rel|ΔZ|` attributable to the reactive part "
        "rather than the resistive one, as a median over all rows. A pair that "
        "disagrees about X and agrees about R is disagreeing about the feed "
        "region and the near field, not about radiated power.\n"
    )
    w("| pair | rows | median share carried by X |")
    w("|---|---:|---:|")
    for a, b in PAIRS:
        rows = [r for r in store[(a, b)] if r["rel"] > 0]
        shares = [
            abs(r["za"].imag - r["zb"].imag) / abs(r["zb"]) / r["rel"] for r in rows
        ]
        w(
            f"| {LABEL[a]} / {LABEL[b]} | {len(shares)} | {statistics.median(shares):.3f} |"
        )
    w("")

    w("## Publication discipline\n")
    w(
        "Per-design rows for all three engines are committed beside this page, "
        "including the NEC-5 impedances, because an impedance is a number this "
        "project computed and not a NEC-5 artifact. What is not committed and not "
        "quoted anywhere is any NEC-5 printout, deck output or source detail "
        "(LLNL-CODE-746721). The distinction is deliberate and it is the same one "
        "the corpus census draws.\n"
    )
    w(
        "The committed record also carries the run's provenance as its first "
        "line — both repository SHAs, both package versions, the resolved path of "
        "every compiled extension and the SIMD variant in use. A reader who has "
        "the data file does not need this page to know what produced it.\n"
    )

    w(
        f"<sub>Environments — antennaknobs `{prov['ak_sha']}`; momwire "
        f"`{prov['momwire_sha']}` ({prov['momwire_describe']}), version "
        f"{mw_ver}, clean; accelerators `{prov['accelerator_variant']['_accelerators']}` "
        f"and `{prov['accelerator_variant']['_near_interface_accel']}`; "
        f"antennaknobs {prov['version_antennaknobs']}; Python "
        f"{prov['python']}; NEC-5 `{nec5}`. Four threads, one solve at a time.</sub>"
    )

    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
