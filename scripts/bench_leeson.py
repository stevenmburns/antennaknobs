"""The Leeson demo: Cebik's tapered-diameter dipoles, three ways (#896 phase 1).

NEC-2 carries a documented defect at wire-radius steps — the reason EZNEC
ships the Leeson correction (uniform-diameter substitute elements) for
stepped-diameter Yagi elements. L.B. Cebik (W4RNL) published the canonical
demonstration: five 14 MHz free-space dipoles with progressively harder
diameter tapers, with uncorrected NEC-2 and Leeson-corrected values for
each ("Antenna Modeling #10: Tapering to Perfection", archived at
antenna2.github.io/cebik/content/amod/amod10.html; the published numbers
are recorded here as cited facts).

This bench re-solves the five cases on a mesh ladder per engine:

  nec2c    raw NEC-2 at 1x/2x/4x density — the defect GROWS with refinement
  bs2      momwire Galerkin B-splines on the exact stepped geometry
  nec5     the census (N, 2N) Richardson pair on the exact geometry

The demo claim: the two independent formulations agree with each other on
the exact geometry and land where the published correction points, while
raw NEC-2 misses by the documented amount — the correction table is built
into the physics. Writes the committed artifact consumed by
scripts/build_validation_report.py.

Requires $NEC5_EXE (printouts ride the capture cache).

    python scripts/bench_leeson.py --out scratch/leeson-cebik.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_nec_corpus import run_engine, run_nec2c

ROOT = Path(__file__).resolve().parent.parent
IN = 0.0254
FREQ = 14.0
SEG_PER_M = 4.0  # 1x density: ~0.25 m segments (~λ/86 at 14 MHz)

# The five amod10 cases. Half-element schedules in inches, mirrored about
# the feed; published values are Cebik's table (gain omitted — this bench
# is the impedance story).
CASES = [
    {
        "name": "case1-uniform",
        "label": "uniform 1.0″",
        "half": [(0, 201.25, 1.0)],
        "published": {"raw": None, "corrected": [71.8, -0.6]},
    },
    {
        "name": "case2-step-far",
        "label": "one step, far out",
        "half": [(0, 150, 1.0), (150, 204, 0.75)],
        "published": {"raw": [73.0, 4.4], "corrected": [72.0, 0.4]},
    },
    {
        "name": "case3-step-near",
        "label": "one step, near center",
        "half": [(0, 50, 1.0), (50, 204, 0.75)],
        "published": {"raw": [72.4, 5.2], "corrected": [71.8, -0.5]},
    },
    {
        "name": "case4-two-steps",
        "label": "two steps, modest taper",
        "half": [(0, 20, 1.25), (20, 100, 1.0), (100, 205.75, 0.75)],
        "published": {"raw": [72.5, 10.6], "corrected": [71.9, 0.1]},
    },
    {
        "name": "case5-extreme",
        "label": "two steps, extreme taper",
        "half": [(0, 20, 2.5), (20, 100, 1.0), (100, 208.5, 0.75)],
        "published": {"raw": [67.6, 17.1], "corrected": [72.1, 0.9]},
    },
]


def build_wires(half: list, mult: int) -> list:
    """Mirror a half-element schedule into full (x1, x2, dia, nseg) wires.

    The innermost section becomes one center wire spanning the feed with an
    odd segment count (feed at the exact center segment); outer sections
    mirror in pairs at ~equal segment length across the whole element.
    """
    wires = []
    x1, x2, dia = half[0]
    n = max(3, round(2 * x2 * IN * SEG_PER_M * mult))
    n += 1 - n % 2
    wires.append((-x2, x2, dia, n))
    for x1, x2, dia in half[1:]:
        n = max(2, round((x2 - x1) * IN * SEG_PER_M * mult))
        wires.append((x1, x2, dia, n))
        wires.append((-x2, -x1, dia, n))
    return wires


def deck_text(name: str, wires: list) -> str:
    lines = [f"CM {name}", "CE"]
    feed_tag = feed_seg = None
    for i, (x1, x2, dia, n) in enumerate(wires, 1):
        r = dia * IN / 2
        lines.append(f"GW {i} {n} {x1 * IN:.6f} 0 0 {x2 * IN:.6f} 0 0 {r:.6f}")
        if x1 == -x2:
            feed_tag, feed_seg = i, (n + 1) // 2
    lines += [
        "GE 0",
        f"EX 0 {feed_tag} {feed_seg} 0 1. 0.",
        f"FR 0 1 0 0 {FREQ} 0",
        "XQ",
        "EN",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "scratch" / "leeson-cebik.json"))
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args(argv)

    workdir = Path(tempfile.mkdtemp(prefix="leeson-"))
    results = []
    for case in CASES:
        row = {
            "name": case["name"],
            "label": case["label"],
            "half_inches": case["half"],
            "published": case["published"],
            "nec2c": [],
            "bs2": [],
            "nec5": [],
            "nec5_raw": [],
        }
        for mult in (1, 2, 4):
            wires = build_wires(case["half"], mult)
            nseg = sum(w[3] for w in wires)
            p = workdir / f"{case['name']}-x{mult}.nec"
            p.write_text(deck_text(f"{case['name']} x{mult}", wires))
            r2 = run_nec2c(p, args.timeout)
            if r2.get("error"):
                raise RuntimeError(f"nec2c {case['name']} x{mult}: {r2['error']}")
            row["nec2c"].append([mult, nseg, *r2["z"][0]])
            if mult == 4:
                continue  # bs2/nec5 are converged by 2x; 4x shows the march
            for eng in ("bs2", "nec5"):
                r = run_engine(eng, p, FREQ, None, args.timeout)
                if r.get("error"):
                    raise RuntimeError(f"{eng} {case['name']} x{mult}: {r['error']}")
                row[eng].append([mult, nseg, *r["z"][0]])
                if eng == "nec5" and r.get("nec5_z_native"):
                    row["nec5_raw"].append([mult, nseg, *r["nec5_z_native"][0]])
            print(f"{case['name']} x{mult} done", flush=True)
        results.append(row)

    out = Path(args.out)
    out.write_text(json.dumps({"freq_mhz": FREQ, "cases": results}, indent=1))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
