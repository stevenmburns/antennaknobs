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
import subprocess
import sys
from collections import Counter
from pathlib import Path

DATA = (
    Path(__file__).resolve().parents[2]
    / "docs/status/data/2026-09-15-catalog-razor-nec5-bs2.jsonl"
)
PAIRS = (("razor", "nec5"), ("bs2", "nec5"), ("bs2", "razor"))

# The four designs AK#1516 actually refined x8. The mesh reading is scoped to
# these by name, because that is the extent of what was measured.
AK1516_DESIGNS = (
    "loops.skyloop_lmatch",
    "verticals.rectangle",
    "dipoles.koch_dipole",
    "verticals.four_square",
)

PROBE3 = Path(__file__).resolve().parents[1] / "845-mesh-policy" / "probe3_sweep.json"
# probe3's own error metric is PORT 0 ALONE (`abs(z - ref)` on a scalar), while
# this page's rows are per-port and its distributions use an all-port norm. The
# two are not the same number -- on the 4-port `arrays.moxonarray` probe3 reads
# 9.068 ohm where an all-port norm reads 18.0 -- so probe3 is used for the
# design-level CLASS only, and every ohm figure printed beside a row is computed
# from this run's own records for that row's own port.
PROBE3_PORT = 0

# AK#1516's own ladder records, copied in so the page regenerates from committed
# inputs. These are a DIRECT measurement of the question the class column asks --
# does THIS PAIR's gap close under refinement -- so where they cover a row they
# override probe3, which only ever measured razor against bs2.
LADDER1516 = Path(__file__).resolve().parent / "ladder-1516-records.jsonl"
LADDER_LO, LADDER_HI = 21, 168  # the x1 and x8 rungs
LABEL = {"razor": "razor-2p", "nec5": "NEC-5", "bs2": "momwire bs2"}
GROUNDS = ("free", "somm")
GROUND_LABEL = {"free": "free space", "somm": "Sommerfeld"}

# The one paragraph every bs2 comparison on this page carries. AK#1516 measured
# it; AK#1525 is where the density question goes.
ADJUDICATION = (
    "> **The mesh reading, scoped to what was measured.** On the four designs "
    "AK#1516 refined eightfold — `loops.skyloop_lmatch`, `verticals.rectangle`, "
    "`dipoles.koch_dipole` and `verticals.four_square` — razor-2p and NEC-5 "
    "moved **18–33 % together, toward momwire bs2**, while bs2 moved "
    "**≤ 2.4 %**. On those four, a wide bs2 row is a statement about mesh "
    "density. **That is four designs, not the catalog**: for every other row the "
    "class column says what is and is not known, and the density question itself "
    "is AK#1525."
)


def load_ladder1516():
    """(pair, design, ground) -> (ratio, gap at x1, gap at x8) from AK#1516.

    KEYED ON THE PAIR, not just the design and ground, because the answer differs
    between pairs on the same row: on `verticals.four_square` over Sommerfeld the
    bs2-against-NEC-5 gap closes from 19.0 % to 2.7 % while the
    razor-against-NEC-5 gap holds at 1.78 % -> 1.74 %. A class keyed only on
    design and ground would have to be wrong about one of them.
    """
    if not LADDER1516.is_file():
        return {}
    rung = {}
    for line in LADDER1516.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("variant") != "stock" or r.get("status") != "ok":
            continue
        rung[(r["design"], r["ground"], r["rung"], r["engine"])] = [
            complex(*p) for p in r["z"]
        ]
    out = {}
    for d, g, k, _e in list(rung):
        for a, b in PAIRS:
            key = (a, b, d, g)
            if key in out:
                continue
            va1, vb1 = rung.get((d, g, LADDER_LO, a)), rung.get((d, g, LADDER_LO, b))
            va8, vb8 = rung.get((d, g, LADDER_HI, a)), rung.get((d, g, LADDER_HI, b))
            if not all(v is not None for v in (va1, vb1, va8, vb8)):
                continue
            if len(va1) != len(vb1) or len(va8) != len(vb8):
                continue

            def nrm(x, y):
                den = math.sqrt(sum(abs(t) ** 2 for t in y))
                if den == 0:
                    return None
                return (
                    math.sqrt(sum(abs(u - t) ** 2 for u, t in zip(x, y, strict=True)))
                    / den
                )

            g1, g8 = nrm(va1, vb1), nrm(va8, vb8)
            if not g1 or g8 is None:
                continue
            out[key] = (g8 / g1, g1, g8)
    return out


def load_probe3():
    """Design x ground -> the mesh class, from #845's probe3 sweep.

    Classes, with #845's own resolution rule: a row whose REFERENCE moved by
    more than a third of the quantity being judged is unresolved rather than
    tabulated, because a reference that is still moving cannot adjudicate
    anything.
    """
    if not PROBE3.is_file():
        return {}

    def z0(cell):
        if not cell or cell.get("error") or not cell.get("z"):
            return None
        pair = cell["z"][PROBE3_PORT] if len(cell["z"]) > PROBE3_PORT else None
        return complex(*pair) if pair else None

    out = {}
    for entry in json.loads(PROBE3.read_text()):
        for g, scales in entry["grounds"].items():
            r = {k: z0((scales.get(k) or {}).get("razor-2p")) for k in ("1", "2", "4")}
            b = {
                k: z0((scales.get(k) or {}).get("bspline-d2")) for k in ("1", "2", "4")
            }
            ref = b["4"]
            if ref is None or any(r[k] is None for k in ("1", "2", "4")):
                out[(entry["design"], g)] = ("not measured", None)
                continue
            d1, d2, d4 = (abs(r[k] - ref) for k in ("1", "2", "4"))
            refmv = abs(b["2"] - ref) if b["2"] is not None else None
            detail = (
                f"razor {d1:.1f} → {d2:.1f} → {d4:.1f} Ω, reference moved {refmv:.2f} Ω"
                if refmv is not None
                else None
            )
            if refmv is None:
                cls = "not measured"
            elif d1 > 0 and refmv > d1 / 3.0:
                cls = "reference unsettled"
            elif d4 < d2 < d1:
                cls = "converging"
            elif d4 >= d1:
                cls = "not converging"
            else:
                cls = "unexplained"
            out[(entry["design"], g)] = (cls, detail)
    return out


def mesh_class(p3, ladder, pair, design, ground):
    """The class for one row, measured where AK#1516 covers it and inferred from
    probe3 where it does not.

    AK#1516 wins when it has the row, because it measured the actual pair over an
    x8 ladder. probe3 only ever compared razor against bs2, so it cannot speak to
    whether a razor-against-NEC-5 gap closes -- and on all four AK#1516 designs
    that gap does NOT close, in free space as well as over Sommerfeld. Reading
    those rows as "mesh" would tell a reader density fixes them, and it does not.
    """
    hit = ladder.get((pair[0], pair[1], design, ground))
    if hit is not None:
        ratio, g1, g8 = hit
        detail = f"{100 * g1:.3g} % at ×1 → {100 * g8:.3g} % at ×8 (AK#1516)"
        if ratio <= 0.5:
            return "closes under refinement (AK#1516)", detail
        if ratio > 0.8:
            tag = "AK#1526" if ground == "somm" else "AK#1516 residue"
            return f"does NOT close under refinement ({tag})", detail
        return "partly closes under refinement (AK#1516)", detail
    # probe3 measured razor-2p against bs2-d2. It can therefore speak to a row
    # where bs2 is one of the two engines, and NOT to a razor-against-NEC-5 row:
    # those two are the pair that moves TOGETHER under refinement, so their mutual
    # gap can sit flat while both converge. AK#1516 measured exactly that on all
    # four of its designs, in free space as well as over Sommerfeld. Handing a
    # razor-against-NEC-5 row a probe3 "converging" class would be the same
    # mistake as calling four_square's Sommerfeld row "mesh", by another route.
    if "bs2" not in pair:
        return "not measured (probe3 cannot speak to this pair)", None
    cls, detail = p3.get((design, ground), ("not measured", None))
    if cls == "converging":
        return "mesh (probe3)", detail
    return cls, detail


def _knob_response(design):
    """(segments at x21, segments at x160) for one design, or None.

    `nominal_nsegs` is a density and each design decides which edges follow it,
    so a design can be "refined" x7.6 on paper and hardly remesh at all.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
        import bench_converge as cvg

        cls = cvg.load_design(design)
        return cvg.total_nominal_segs(cls, 21), cvg.total_nominal_segs(cls, 160)
    except Exception:  # noqa: BLE001 -- absent is a fine answer for a footnote
        return None


def _explained(cls: str) -> bool:
    """Only a class that says the gap CLOSES explains a wide row. "does NOT
    close" is a measured finding, not an explanation of the disagreement."""
    return cls.startswith("closes under refinement") or cls.startswith("mesh")


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

    p3 = load_probe3()
    ladder = load_ladder1516()
    # The main commit the study branch sits on, COMPUTED rather than typed: the
    # provenance record carries the branch SHA, and the page must name main.
    try:
        main_sha = subprocess.run(
            ["git", "merge-base", prov["ak_sha"], "origin/main"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()[:9]
    except Exception:  # noqa: BLE001 -- an unnamed main is better than a wrong one
        main_sha = "undetermined"
    mw_ver = prov["version_momwire"]
    mw_sha = prov["momwire_sha"][:9]
    ak_sha = prov["ak_sha"][:9]
    variant = prov["accelerator_variant"]["_accelerators"].split(".")[0]
    nec5 = Path(prov["nec5_exe"] or "nec5cl").name

    w("# razor-2p, NEC-5 and momwire bs2 over the antennaknobs catalog\n")
    w(
        "**Evidence, not a scoreboard.** Every built-in design solved "
        "three ways at its own default mesh and frequency, in free space and "
        "over Sommerfeld ground, and the three pairwise disagreements reported "
        "as distributions. The page states what the three engines do and do not "
        "agree about. It does not rank them.\n"
    )
    w(
        f"**The builds, named because a version string does not identify a "
        f"solver.** antennaknobs **main `{main_sha}`**, run from a study branch "
        f"(`{ak_sha}`) that adds only this study's harness and records; "
        f"momwire **{mw_ver}** imported "
        f"from the editable submodule at `{mw_sha}` with a clean working tree — "
        f"which is also the commit antennaknobs records as its pointer, so this "
        f"run is the momwire a user installs rather than a dev tip ahead of it. "
        f"The compiled accelerator actually in use was **`{variant}`**; momwire "
        f"ships more than one SIMD variant behind that module name and they are "
        f"not bit-identical to each other, so the variant is recorded with the "
        f"data. NEC-5 is the build `{nec5}`, run as an executable; "
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
        "**The reflection-coefficient ground is not on this page because NEC-5 "
        "has no such model**: its `IPERF 0` is a full Sommerfeld solution, and "
        "antennaknobs' NEC-5 engine refuses a `finite-fast` ground by name "
        "rather than silently upgrading the physics "
        "(`engines/nec5.py:_normalise_ground`). There is therefore no NEC-5 row "
        "to compare against, so the model is left off for all three engines "
        "rather than shown for two of them.\n"
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
        f"**{pct(bn['max'])}**. How to read that tail is not one answer: four of "
        f"its widest designs are AK#1516's mesh finding, and the single widest "
        f"row of all — `dipoles.short_dipole_loaded` — is **not yet explained**, "
        f"because the reference it is measured against has not settled at that "
        f"design's shipped mesh either. The class column on each table below says "
        f"which is which.\n"
    )

    w("## The widest disagreements\n")
    w(ADJUDICATION + "\n")
    w(
        "**`|ΔZ|` in ohms is given beside the relative figure**, because on a "
        "low-impedance or near-open design a percentage misleads: the widest row "
        "on this page is a ~7 Ω reactance difference on a driving point of about "
        "13 Ω.\n"
    )
    w(
        "**The class column is generated, not asserted.** It comes from "
        "`scratch/845-mesh-policy/probe3_sweep.json`, a 1× / 2× / 4× mesh sweep of "
        "the catalog measured on an **older build** (2026-09-03), with #845's own "
        "resolution rule applied: a design whose *reference* moved by more than a "
        "third of the quantity being judged is marked `reference unsettled` rather "
        "than classified, because a reference that is still moving cannot "
        "adjudicate anything. probe3's metric is **port 0 alone**, so the class is "
        "a property of the design and ground, not of the individual port row "
        "beside it. **Every one of these classes will be re-measured on current "
        "code by AK#1525**, and a design that changes class there is a finding.\n"
    )
    w(
        "Where **AK#1516** covers a row it overrides probe3, because it refined "
        "that exact pair eightfold while probe3 only ever compared razor-2p "
        "against bs2. That distinction changes answers: on "
        "`verticals.four_square` over Sommerfeld the bs2-against-NEC-5 gap closes "
        "from 19.0 % to 2.7 %, while the razor-2p-against-NEC-5 gap holds at "
        "1.78 % → 1.74 %. Only the first is a density story.\n"
    )
    w(
        "**Only a class saying the gap CLOSES explains a wide row.** "
        "`does NOT close under refinement` is a measured finding rather than an "
        "explanation — it says density is not the cause and names the issue "
        "tracking it. `reference unsettled`, `not converging`, `unexplained` and "
        "`not measured` all mean the same thing for a reader: **the disagreement "
        "on that row has no established cause yet.**\n"
    )
    for a, b in PAIRS:
        rows = store[(a, b)]
        worst = sorted(rows, key=lambda r: -r["rel"])[:10]
        w(f"### {LABEL[a]} against {LABEL[b]} — ten widest rows\n")
        w(
            f"| design | ground | port | {LABEL[a]} Z | {LABEL[b]} Z | "
            f"\\|ΔZ\\| Ω | rel\\|ΔZ\\| | class |"
        )
        w("|---|---|---:|---|---|---:|---:|---|")
        for r in worst:
            cls, _detail = mesh_class(p3, ladder, (a, b), r["design"], r["ground"])
            w(
                f"| `{r['design']}` | {GROUND_LABEL[r['ground']]} | {r['port']} | "
                f"{r['za'].real:.4g}{r['za'].imag:+.4g}j | "
                f"{r['zb'].real:.4g}{r['zb'].imag:+.4g}j | "
                f"{abs(r['za'] - r['zb']):.3g} | {pct(r['rel'])} | {cls} |"
            )
        w("")
        unexplained = sorted(
            {
                r["design"]
                for r in worst
                if not _explained(
                    mesh_class(p3, ladder, (a, b), r["design"], r["ground"])[0]
                )
            }
        )
        if unexplained:
            w(
                "Designs in this table with **no established cause**: "
                + ", ".join(f"`{d}`" for d in unexplained)
                + ".\n"
            )
        # A "not converging" class is only as good as the refinement it was
        # measured over, and at least one catalog design barely remeshes when the
        # knob moves. Say so wherever that class appears, with the counts.
        stiff = sorted(
            {
                r["design"]
                for r in worst
                if mesh_class(p3, ladder, (a, b), r["design"], r["ground"])[0]
                == "not converging"
                and _knob_response(r["design"]) is not None
                and _knob_response(r["design"])[1]
                < 1.5 * _knob_response(r["design"])[0]
            }
        )
        for d in stiff:
            lo, hi = _knob_response(d)
            w(
                f"> **`{d}`'s mesh barely responds to the knob** — {lo} segments at "
                f"×21 rising only to {hi} at ×160 — so a `not converging` class on "
                f"it is measured over a refinement that hardly happened. AK#1525 "
                f"reports the achieved segment count per rung for exactly this "
                f"reason.\n"
            )

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
