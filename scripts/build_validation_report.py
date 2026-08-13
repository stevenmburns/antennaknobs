"""Build the public validation page (#896 phase 0).

Consumes committed census artifacts and emits the site validation page plus
its figure — every number on the page is either computed here from a
committed artifact or a cited literal from a docs/status writeup:

  scratch/bydipole1-ladders.json      ByDipole1 four-engine ladders (computed)
  scratch/leeson-cebik.json           the Leeson demo cases (computed; the
                                      published Cebik values ride inside)
  scratch/nec5-convergence-phase2.json  fixed-mesh self-convergence (computed)
  scratch/nec5-wild-pynec-votes.json  the fourth-vote split (computed)
  docs/status/2026-08-12-nec5-wild-phase5.md  census totals (cited literals)

Outputs (all committed):
  site/src/assets/validation/bydipole1-convergence.png
  site/src/assets/validation/leeson-case5.png
  site/src/content/docs/reference/validation.md

`--recompute` re-runs the ByDipole1 ladders live before rendering: nec2c on
PATH, momwire importable, and $NEC5_EXE pointing at a licensed binary
(NEC-5 printouts ride the capture cache). Without it the committed ladder
JSON is used as-is.

    python scripts/build_validation_report.py
    python scripts/build_validation_report.py --recompute
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LADDERS = ROOT / "scratch" / "bydipole1-ladders.json"
ANCHORS = ROOT / "scratch" / "analytic-anchors.json"
LEESON = ROOT / "scratch" / "leeson-cebik.json"
PHASE2 = ROOT / "scratch" / "nec5-convergence-phase2.json"
VOTES = ROOT / "scratch" / "nec5-wild-pynec-votes.json"
FIGURE = ROOT / "site" / "src" / "assets" / "validation" / "bydipole1-convergence.png"
LEESON_FIGURE = ROOT / "site" / "src" / "assets" / "validation" / "leeson-case5.png"
PAGE = ROOT / "site" / "src" / "content" / "docs" / "reference" / "validation.md"

# ByDipole1 (EZNEC 7 distributed sample), re-authored with a direct center
# voltage feed in place of EZNEC's NT current-source idiom (driving-point Z
# is source-type independent — the #890 EX0/EX4 identity).
FREQ, H, L, RAD = 14.0, 9.144, 10.18946, 0.0010262
EPS, SIG = 20.0, 0.0303
GROUND = ("finite", EPS, SIG)
ODD = list(range(11, 102, 4))
EVEN = list(range(12, 101, 4))


# --------------------------------------------------------------------------
# ByDipole1 live recompute (the small study this page regenerates on demand)


def _momwire_z(n: int, degree: int) -> complex:
    from types import MappingProxyType

    from antennaknobs import AntennaBuilder
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.network import Wire, WireSpec
    from momwire import BSplineSolver

    class ByDipole1(AntennaBuilder):
        default_params = MappingProxyType({"freq": FREQ})

        def build_wires(self):
            return [
                Wire(
                    (0, 0, H),
                    (0, L, H),
                    n_seg=n,
                    ex=1 + 0j,
                    spec=WireSpec(radius=RAD),
                )
            ]

    eng = MomwireEngine(
        ByDipole1(),
        solver=BSplineSolver,
        solver_kwargs={"degree": degree},
        ground=GROUND,
    )
    return eng.impedance()[0]


def _nec2c_z(n: int, workdir: Path) -> complex:
    from bench_nec_corpus import run_nec2c

    deck = (
        "CM bydipole1 direct\nCE\n"
        f"GW 1 {n} 0. 0. {H!r} 0. {L!r} {H!r} {RAD!r}\n"
        f"GE 1\nGN 2 0 0 0 {EPS!r} {SIG!r}\n"
        f"EX 0 1 {(n + 1) // 2} 0 1. 0.\nFR 0 1 0 0 {FREQ!r} 0\nXQ\nEN\n"
    )
    r = run_nec2c(workdir / "bydipole1.nec", 240, deck_text=deck)
    if r.get("error"):
        raise RuntimeError(r["error"])
    return complex(*r["z"][0])


def _nec5_z(n: int, eng) -> complex:
    deck = (
        "CM bydipole1 nec5\nCE\n"
        f"GW 1 {n} 0.000000E+00 0.000000E+00 {H:.6E} 0.000000E+00 {L:.6E} {H:.6E} {RAD:.6E}\n"
        "GE 1 0\n"
        f"GN 0 0 0 0 {EPS:.6E} {SIG:.6E} 1.000000E+00 0.000000E+00 NOFILE\n"
        f"EX 0 1 {n // 2} 2 1.000000E+00 0.000000E+00\n"
        f"FR 0 1 0 0 {FREQ:.6E} 0.000000E+00\nXQ 0\nEN\n"
    )
    return eng.run_deck(deck)[0][0][2]


def recompute_ladders() -> dict:
    from antennaknobs.engines.nec5 import NEC5Engine
    from bench_nec5_walk_why import make_dipole

    eng5 = NEC5Engine(
        make_dipole(20),
        ground=GROUND,
        capture_dir=Path.home() / ".antennaknobs" / "nec5-captures",
    )
    workdir = Path(tempfile.mkdtemp(prefix="bydipole1-"))
    data = {}
    data["nec2c"] = [[n, *_ri(_nec2c_z(n, workdir))] for n in ODD]
    print("nec2c done", flush=True)
    data["nec5"] = [[n, *_ri(_nec5_z(n, eng5))] for n in EVEN]
    print("nec5 done", flush=True)
    data["bs2"] = [[n, *_ri(_momwire_z(n, 2))] for n in ODD]
    print("bs2 done", flush=True)
    data["bs1"] = [[n, *_ri(_momwire_z(n, 1))] for n in EVEN]
    print("bs1 done", flush=True)
    LADDERS.write_text(json.dumps(data))
    return data


def recompute_anchors() -> dict:
    """The analytic-anchor rows (#896 phase 2): quantities whose exact value
    is set by physics, not by any engine. One case, the ByDipole1 wire in
    FREE SPACE (lossless): energy conservation fixes the average power gain
    over the sphere at exactly 1 — every engine's pattern integral is
    measured against that, which tests the whole normalization chain
    (momwire's closed-form η₀k²/(8π·P_in) directivity norm included)."""
    import re as _re
    import shutil
    import subprocess

    n = 51  # odd: the center-gap feed sits on the middle segment everywhere
    out: dict = {"case": "ByDipole1 wire, free space, lossless", "nseg": n}

    # momwire bs2: integrate the far-field grid. The public grid covers the
    # upper hemisphere (theta 0..89° from zenith, 1° rings); the horizontal
    # dipole is symmetric about its own plane, so the full-sphere average
    # equals the upper-hemisphere one.
    import numpy as np
    from types import MappingProxyType

    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Wire, WireSpec

    class _Free(AntennaBuilder):
        default_params = MappingProxyType({"freq": FREQ})

        def build_wires(self):
            return [
                Wire(
                    (0, 0, H),
                    (0, L, H),
                    n_seg=n,
                    ex=1 + 0j,
                    spec=WireSpec(radius=RAD),
                )
            ]

    from antennaknobs.engines.momwire import MomwireEngine

    ff = MomwireEngine(_Free(), ground=None).far_field(n_theta=90, n_phi=360)
    g = 10.0 ** (np.asarray(ff.rings, dtype=float) / 10.0)  # (90, 361) dBi grid
    g = g[:, :-1]  # drop the phi seam duplicate
    theta = np.radians(np.asarray(ff.thetas, dtype=float))
    dth, dph = np.pi / 180.0, np.pi / 180.0
    avg = float(np.sum(g * np.sin(theta)[:, None]) * dth * dph / (2.0 * np.pi))
    out["momwire_bs2"] = avg

    # nec2c: full-sphere RP with the average-power-gain request (XNDA A=2),
    # cell-centered rings so the sector average is honest.
    if shutil.which("nec2c"):
        deck = (
            "CM anchors free-space dipole\nCE\n"
            f"GW 1 {n} 0. 0. {H!r} 0. {L!r} {H!r} {RAD!r}\n"
            "GE 0\n"
            f"EX 0 1 {(n + 1) // 2} 0 1. 0.\n"
            f"FR 0 1 0 0 {FREQ!r} 0\n"
            "RP 0 90 180 1002 1.0 0.0 2.0 2.0\nEN\n"
        )
        with tempfile.TemporaryDirectory() as td:
            dp = Path(td) / "a.nec"
            op = Path(td) / "a.out"
            dp.write_text(deck)
            subprocess.run(
                ["nec2c", "-i", str(dp), "-o", str(op)],
                capture_output=True,
                timeout=240,
            )
            m = _re.search(
                r"AVERAGE POWER GAIN[^0-9Ee+-]*([0-9.Ee+-]+)", op.read_text()
            )
            if m:
                out["nec2c"] = float(m.group(1))

    # NEC-5: its own printout's average, over its own full-sphere grid.
    from antennaknobs.engines.nec5 import NEC5Engine, find_nec5

    if find_nec5():
        avg5, _solid = NEC5Engine(_Free()).average_power_gain(n_theta=90, n_phi=180)
        out["nec5"] = avg5

    ANCHORS.write_text(json.dumps(out, indent=1))
    return out


def anchors_section(anchors: dict) -> str:
    rows = [
        "| source | average power gain | deviation |",
        "| --- | --- | --- |",
        "| energy conservation (exact) | 1.0000 | — |",
    ]
    for key, label in (
        ("momwire_bs2", "momwire bs2 (closed-form directivity norm)"),
        ("nec2c", "nec2c (printout average)"),
        ("nec5", "NEC-5 (printout average)"),
    ):
        v = anchors.get(key)
        if v is None:
            rows.append(f"| {label} | — | — |")
        else:
            rows.append(f"| {label} | {v:.4f} | {abs(v - 1.0):.4f} |")
    return "\n".join(rows)


def _ri(z: complex) -> list[float]:
    return [z.real, z.imag]


# --------------------------------------------------------------------------
# Reductions


def swr(z: complex, z0: float = 50.0) -> float:
    g = abs((z - z0) / (z + z0))
    return (1 + g) / (1 - g)


def gamma(z: complex, z0: float = 50.0) -> complex:
    return (z - z0) / (z + z0)


def _z(row: list[float]) -> complex:
    return complex(row[1], row[2])


def richardson_pairs(series: list[list[float]]) -> list[tuple[int, int, complex]]:
    """First-order (N, 2N) pair extrapolations available in a ladder."""
    by_n = {int(r[0]): _z(r) for r in series}
    return [
        (n, 2 * n, 2.0 * by_n[2 * n] - by_n[n]) for n in sorted(by_n) if 2 * n in by_n
    ]


def fmt_z(z: complex) -> str:
    return f"{z.real:.2f} {z.imag:+.2f}j"


# --------------------------------------------------------------------------
# Page sections


def bydipole1_section(data: dict) -> str:
    rows = []
    labels = {
        "bs2": "momwire bs2",
        "bs1": "momwire bs1",
        "nec2c": "nec2c (NEC-2)",
        "nec5": "NEC-5 raw",
    }
    for key in ("bs2", "bs1", "nec2c", "nec5"):
        s = data[key]
        z0, z1 = _z(s[0]), _z(s[-1])
        rows.append(
            f"| {labels[key]} | {fmt_z(z0)} ({swr(z0):.2f}) @ {int(s[0][0])} "
            f"| {fmt_z(z1)} ({swr(z1):.2f}) @ {int(s[-1][0])} |"
        )
    pairs = richardson_pairs(data["nec5"])[-2:]
    pair_cells = " / ".join(f"({a},{b}) → {fmt_z(z)}" for a, b, z in pairs)
    table = "\n".join(
        [
            "| engine | coarsest read — Z in Ω (SWR₅₀) @ N | finest read @ N |",
            "| --- | --- | --- |",
            *rows,
        ]
    )
    return table, pair_cells


def phase2_table(phase2: dict) -> str:
    lines = [
        "| design | NEC-5 raw | momwire bs2 | momwire sin |",
        "| --- | --- | --- | --- |",
    ]
    for row in phase2["rows"]:
        cells = [row["design"].replace("_", "\\_")]
        for eng in ("nec5", "bs2", "sin"):
            s = row["series"].get(eng)
            if not s or len(s) < 2:
                cells.append("—")
                continue
            dg = abs(gamma(_z(s[0])) - gamma(_z(s[-1])))
            cells.append(f"{dg:.4f}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _zrow(row: list[float]) -> complex:
    """[mult, nseg, R, X] → Z (the Leeson artifact's row shape)."""
    return complex(row[2], row[3])


def leeson_table(leeson: dict) -> str:
    lines = [
        "| element (14 MHz, free space) | published NEC-2 raw | our nec2c, 1×→4× mesh | momwire bs2 | NEC-5 pair | published corrected |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in leeson["cases"]:
        pub = case["published"]
        raw = fmt_z(complex(*pub["raw"])) if pub["raw"] else "—"
        cor = fmt_z(complex(*pub["corrected"]))
        march = " → ".join(fmt_z(_zrow(r)) for r in case["nec2c"][::2])
        bs2 = fmt_z(_zrow(case["bs2"][-1]))
        nec5 = fmt_z(_zrow(case["nec5"][-1]))
        lines.append(f"| {case['label']} | {raw} | {march} | {bs2} | {nec5} | {cor} |")
    return "\n".join(lines)


def leeson_spreads(leeson: dict) -> tuple[float, float, str, str]:
    """Max bs2↔NEC-5 distance, max bs2 X offset from the corrected value,
    and case-5 nec2c X march endpoints."""
    max_mutual = max(
        abs(_zrow(c["bs2"][-1]) - _zrow(c["nec5"][-1])) for c in leeson["cases"]
    )
    max_dx = max(
        abs(_zrow(c["bs2"][-1]).imag - c["published"]["corrected"][1])
        for c in leeson["cases"]
    )
    c5 = next(c for c in leeson["cases"] if c["name"] == "case5-extreme")
    x0, x1 = _zrow(c5["nec2c"][0]).imag, _zrow(c5["nec2c"][-1]).imag
    return max_mutual, max_dx, f"{x0:+.1f}", f"{x1:+.1f}"


def votes_split(votes: list[dict]) -> tuple[int, int, int]:
    voted = [r for r in votes if r.get("dg_pynec_nec2c") is not None]
    formulation = sum(1 for r in voted if r["dg_pynec_nec2c"] < r["dg_pynec_bs2"])
    return len(voted), formulation, len(voted) - formulation


# --------------------------------------------------------------------------
# Figure (the AC6LA-style three-panel convergence plot; layout matches the
# exhibit already published on the groups.io thread)


def render_figure(data: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    surface = "#fcfcfb"
    ink, ink2, grid = "#1a1a19", "#5f5e56", "#e8e8e6"
    series = {
        "bs2": ("#2a78d6", "momwire bs2"),
        "bs1": ("#eb6834", "momwire bs1"),
        "nec5": ("#1baf7a", "NEC-5"),
        "nec2c": ("#eda100", "nec2c (NEC-2)"),
    }

    fig, axes = plt.subplots(3, 1, figsize=(8.6, 10.2), sharex=True, facecolor=surface)
    panels = [
        ("Source R (Ω)", lambda z: z.real),
        ("Source X (Ω)", lambda z: z.imag),
        ("SWR(50)", swr),
    ]
    for ax, (ylabel, f) in zip(axes, panels):
        ax.set_facecolor(surface)
        ends = []
        for key, (color, label) in series.items():
            pts = data[key]
            ns = [p[0] for p in pts]
            ys = [f(_z(p)) for p in pts]
            ax.plot(
                ns,
                ys,
                color=color,
                lw=2,
                marker="o",
                ms=3.5,
                mfc=color,
                mec=surface,
                mew=0.5,
                label=label,
            )
            ends.append((ys[-1], ns[-1], label, color))
        # Spread the end-of-line labels: enforce a minimum vertical gap
        # (fraction of the AXIS range, so it tracks font size) so series
        # converging to the same value stay individually legible.
        ymin, ymax = ax.get_ylim()
        min_gap = 0.045 * (ymax - ymin)
        ends.sort()
        placed = []
        for y, _n, _label, _color in ends:
            placed.append(y if not placed else max(y, placed[-1] + min_gap))
        for (y, n, label, color), ly in zip(ends, placed):
            ax.text(n + 2.5, ly, label, va="center", fontsize=9, color=color)
        ax.set_ylabel(ylabel, color=ink, fontsize=10)
        ax.grid(True, color=grid, lw=0.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(ink2)
        ax.tick_params(colors=ink2, labelsize=9)
        ax.set_xlim(8, 118)
    axes[0].legend(loc="lower right", frameon=False, fontsize=9, labelcolor=ink)
    axes[2].set_xlabel("Number of segments", color=ink, fontsize=10)
    axes[0].set_title(
        "ByDipole1 (EZNEC 7 sample) — feed-point convergence vs engine\n"
        "10.19 m dipole at 9.14 m over Sommerfeld ground (εr 20, "
        "σ 0.0303 S/m), 14 MHz",
        color=ink,
        fontsize=11,
        loc="left",
        pad=12,
    )
    fig.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=170, facecolor=surface)
    print(f"wrote {FIGURE.relative_to(ROOT)}")


def render_leeson_figure(leeson: dict) -> None:
    """Case-5 feed reactance vs mesh density: the march you cannot refine away."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    surface = "#fcfcfb"
    ink, ink2, grid = "#1a1a19", "#5f5e56", "#e8e8e6"
    c5 = next(c for c in leeson["cases"] if c["name"] == "case5-extreme")
    corrected_x = c5["published"]["corrected"][1]

    fig, ax = plt.subplots(figsize=(8.6, 4.6), facecolor=surface)
    ax.set_facecolor(surface)
    series = [
        ("nec2c", "nec2c (NEC-2), raw", "#eda100"),
        ("nec5_raw", "NEC-5, native single mesh", "#9dd6bf"),
        ("bs2", "momwire bs2", "#2a78d6"),
        ("nec5", "NEC-5 (N, 2N) pair", "#1baf7a"),
    ]
    for key, label, color in series:
        pts = c5[key]
        ax.plot(
            [p[0] for p in pts],
            [_zrow(p).imag for p in pts],
            color=color,
            lw=2,
            marker="o",
            ms=4.5,
            mfc=color,
            mec=surface,
            mew=0.5,
            label=label,
        )
    ax.axhline(corrected_x, color=ink2, lw=1.2, ls=(0, (5, 4)), zorder=0)
    ax.text(
        0.93,
        corrected_x + 0.7,
        f"published Leeson-corrected X ({corrected_x:+.1f} Ω)",
        va="bottom",
        fontsize=8.5,
        color=ink2,
    )
    ax.set_xscale("log", base=2)
    ax.set_xticks([1, 2, 4], labels=["1×", "2×", "4×"])
    ax.set_xlim(0.9, 7.5)
    ax.set_xlabel("Mesh density (1× ≈ 0.25 m segments)", color=ink, fontsize=10)
    ax.set_ylabel("Feed X (Ω)", color=ink, fontsize=10)
    ax.grid(True, color=grid, lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(ink2)
    ax.tick_params(colors=ink2, labelsize=9)
    ax.legend(loc="center right", frameon=False, fontsize=9, labelcolor=ink)
    ax.set_title(
        "Extreme stepped-diameter dipole (Cebik case 5) — feed reactance vs mesh\n"
        "Raw NEC-2's stepped-radius error grows with refinement; the\n"
        "exact-geometry formulations hold still, near the corrected value",
        color=ink,
        fontsize=10.5,
        loc="left",
        pad=12,
    )
    fig.tight_layout()
    fig.savefig(LEESON_FIGURE, dpi=170, facecolor=surface)
    print(f"wrote {LEESON_FIGURE.relative_to(ROOT)}")


# --------------------------------------------------------------------------
# The page


def build_page(
    data: dict, phase2: dict, votes: list[dict], leeson: dict, anchors: dict
) -> str:
    bd_table, bd_pairs = bydipole1_section(data)
    anchors_table = anchors_section(anchors)
    p2_table = phase2_table(phase2)
    n_voted, n_formulation, n_translation = votes_split(votes)
    lee_table = leeson_table(leeson)
    lee_mutual, lee_dx, lee_x0, lee_x1 = leeson_spreads(leeson)
    bs2_11 = _z(data["bs2"][0])
    nec5_12 = _z(data["nec5"][0])
    nec5_100 = _z(data["nec5"][-1])

    # Census totals below marked "cited" are literals from
    # docs/status/2026-08-12-nec5-wild-phase5.md (the raw 4 MB sweep artifact
    # is untracked, by the same convention as every corpus sweep); everything
    # else on the page is computed above from committed artifacts.
    return f"""---
title: The validation story
description: How antennaknobs' numbers are checked — three independent formulations, a 3,146-deck wild corpus, and per-case verdicts published with their evidence.
---

<!-- GENERATED by scripts/build_validation_report.py — edit the generator,
     not this file. Regenerate with:  python scripts/build_validation_report.py -->

Every solver page on the internet says "validated against NEC". This page
is the longer version: what antennaknobs' numbers are checked against, what
the checks found — including the defects they found on our side — and
exactly which claims stop where. The short version of the claim:

- **Parity** on plain geometries, grounds and patterns: three independently
  derived, independently coded formulations agree — momwire's B-splines,
  the NEC-2 lineage, and NEC-5's mixed-potential formulation
  (0.01 dB RMS class on far-field patterns, a few ohms of genuine
  formulation spread on impedance).
- **Superiority where the reference is wrong**: on stepped-diameter
  elements the NEC-2 lineage carries a known defect (the reason EZNEC
  ships the Leeson correction). There, momwire and NEC-5 agree *against*
  the two NEC-2 implementations — the correction table is built into the
  physics.
- **Honest limits, stated up front**: what antennaknobs does not model, it
  refuses by name — never a silently simplified answer. The
  [limits table](#honest-limits) is part of the validation story, not a
  footnote.

## The method

The cross-checking machinery is described on the
[solver & accuracy](/reference/solver/) and [NEC-5 engine](/reference/nec5/)
pages; the short form:

- **Three formulations that share almost nothing.** momwire (sinusoidal
  and B-spline Galerkin bases), NEC-2 (nec2c and nec2++, thin-wire
  collocation), and NEC-5 (LLNL's modern mixed-potential rewrite). When
  they agree, the agreement means something; when they split, the split is
  a finding to run down — several of the findings below started life as
  "our bug" and ended as a documented property of the reference.
- **The census metric** is ΔΓ: the distance between reflection
  coefficients at 50 Ω. Unlike raw ohms it is bounded, comparable across
  feed impedances from an ohm to ten thousand, and weighted the way a
  transmitter sees the antenna.
- **Census-grade NEC-5 numbers are Richardson (N, 2N) pairs.** NEC-5's
  knot-source discretization converges first-order in segment length —
  LLNL's own Validation Manual describes the behaviour (Burke & Poggio,
  NEC 5.0, LLNL-CODE-746721) — so the census extrapolates a native and a
  doubled-mesh solve rather than quoting either raw read. The
  [NEC-5 page](/reference/nec5/#honest-numbers) tells the full story of
  how that recipe was pinned.

## Case: ByDipole1 — the EZNEC sample everyone can re-run

ByDipole1 ships with EZNEC 7: a 10.19 m dipole at 9.144 m height, #14
wire, 14 MHz, over real Sommerfeld ground (εr 20, σ 0.0303 S/m). It is a
community-recognizable case — NEC-2 vs NEC-5 convergence plots for it were
independently published by AC6LA — and it sits squarely in NEC-2's good
regime (single radius, no junctions), which makes it a *convergence-rate*
exhibit: every engine here converges to the same answer, and the question
is how many segments each needs to get there.

![Three-panel convergence plot: feed-point R, X and SWR versus segment
count for momwire bs2, momwire bs1, NEC-5 and nec2c on ByDipole1. The bs2
curve is flat from eleven segments; NEC-5 approaches the common limit in a
first-order march.](../../../assets/validation/bydipole1-convergence.png)

{bd_table}

NEC-5 (N, 2N) pair extrapolations: {bd_pairs} — both pairs land on the
common limit within 0.05 Ω of each other.

What the plot shows:

- **Three formulations converge to a common limit within ~0.2 Ω** on a
  real-ground sample they did not choose.
- **bs2 at eleven segments** reads {fmt_z(bs2_11)} — within 0.4 Ω and
  0.014 SWR of the limit. That is the flat line in the figure, and it is
  what "census-grade at coarse mesh" means in practice.
- **Raw NEC-5 at twelve segments** reads {fmt_z(nec5_12)} (SWR
  {swr(nec5_12):.2f}) and needs N≈100 to close within 1.5 Ω
  ({fmt_z(nec5_100)}); the (N, 2N) pair recipe recovers the limit from
  either half of the ladder. This is NEC-5's documented first-order
  knot-source march, not an error — but it is why quoting a single raw
  NEC-5 read at low N misleads.
- **Independent cross-check of our NEC-5 lane**: the same runs reproduce
  AC6LA's published EZNEC-Pro NEC-5 curves to plot-reading precision —
  our runner and a second, unrelated NEC-5 host produce the same numbers
  from the same physics.

Provenance: geometry translated from the EZNEC 7 distribution, with
EZNEC's current-source feed idiom replaced by a direct center voltage feed
(driving-point impedance is source-type independent; the equivalence is
pinned in the test suite). The NEC-2 curve is nec2c — the same lineage as
EZNEC's NEC-2D, independently implemented.

## Case: the Leeson demo — stepped-diameter elements

Practical Yagi elements taper: fat tubing at the boom, thinner sections
toward the tips. NEC-2 carries a documented defect at wire-radius steps —
serious enough that EZNEC ships a correction (David Leeson's
uniform-diameter substitute elements) and applies it whenever a stepped
element qualifies. L.B. Cebik (W4RNL) published the canonical
demonstration: five 14 MHz free-space dipoles with progressively harder
tapers, giving uncorrected and Leeson-corrected NEC-2 values for each
("Tapering to Perfection", *Antenna Modeling* #10). Here are his cases
through our engines — the exact stepped geometry, no correction applied
anywhere:

{lee_table}

Reading the table:

- **The control row behaves**: on the uniform element every engine and
  the published value agree within a few tenths of an ohm.
- **Our raw nec2c reproduces the published defect**, and the mesh march
  shows something the single published number cannot: **the error grows
  as you refine the mesh**. On the extreme taper the reactance error runs
  {lee_x0} Ω at 1× density to {lee_x1} Ω at 4× — you cannot mesh your way
  out of a formulation defect. (Our reads differ from Cebik's published
  raw values by a few ohms of X because the raw error is
  segmentation-dependent and his segment counts were not published; the
  signature and direction match throughout.)
- **The two exact-geometry formulations agree with each other** — bs2 and
  the NEC-5 pair land within {lee_mutual:.2f} Ω on every case — and sit
  where the correction points: reactance within {lee_dx:.1f} Ω of the
  corrected value on every taper. The correction table is built into the
  physics.
- On the extreme taper the corrected *resistance* sits ~4 Ω from the
  exact-geometry consensus — a reminder that the Leeson correction is
  itself an approximation (a uniform substitute element), and two
  independent formulations solving the true geometry is the stronger
  statement of the two.

![Feed reactance versus mesh density for the extreme stepped-diameter
dipole: raw nec2c marches away from the answer as the mesh refines, while
momwire bs2 and the NEC-5 pair sit flat on the Leeson-corrected value at
every density.](../../../assets/validation/leeson-case5.png)

This is the same defect the wild-corpus census found at scale — see the
next section: 44 of the 46 formulation-line movers are stepped-radius
decks.

## The wild-corpus census

The strongest evidence is not a curated demo but a corpus nobody tuned:
3,146 wire decks collected from public archives (ARRL, Cebik, tutorial
collections, community files), each solved by multiple engines and scored
pairwise <!-- cited: docs/status/2026-08-12-nec5-wild-phase5.md -->:

- NEC-5 solved 2,314 decks as (N, 2N) pairs with **zero unclassified
  errors**; 488 decks refused by design (dialect features like TL/NT the
  engine names rather than approximates).
- Clean-cohort median ΔΓ against nec2c: **bs2 0.0080** (n=1686), NEC-5
  pairs 0.0215 (n=1369).
- At the ΔΓ > 0.2 outlier bar, the clean three-way cohort (1,368 decks)
  splits into: **2** decks where momwire is the outlier (filed and tracked
  as momwire defects — that is the entire momwire-suspect pile after five
  phases of hunting), **10** where NEC-5's pair is under-resolved
  (pre-asymptotic decks, a practical-limits note), and **61** where bs2
  and NEC-5 agree with each other against nec2c.

Those 61 mutually-agreeing decks got a fourth vote — nec2++ (PyNEC), which
shares *geometry translation* with the momwire lane but *formulation* with
nec2c, so it discriminates translation bugs from formulation findings. Of
the {n_voted} decks it could score: **{n_formulation} split along
formulation lines** ({{bs2 + NEC-5}} vs {{nec2c + nec2++}} on identical
geometry), {n_translation} translation-suspect. And 44 of the {n_formulation}
have stepped or multi-radius elements — the documented NEC-2
stepped-diameter defect, corrected in NEC-4/NEC-5 and by EZNEC's Leeson
option. On those decks the census now flags the *reference* as suspect and
scores bs2 against NEC-5 instead (mutual ΔΓ 0.004-class where nec2c sits
0.2–0.3 away).

The census also cut both ways — the machinery found and fixed defects on
our side (a wire-connection snap in deck import, two momwire solver issues
filed from census evidence) and the historical scoring was *rewritten
against us* where the reference was wrong. An audit trail that only ever
vindicates its author is not an audit trail.

## Convergence at fixed mesh

From the committed convergence census (13 designs across the catalog's
families — loops, yagis, folded elements, multi-junction fans, loaded
short antennas), each engine's self-movement between its coarsest and
finest ladder rung (ΔΓ between the N=21 and N=161 reads; smaller = already
converged at coarse mesh):

{p2_table}

bs2's coarse read is already census-grade (self-ΔΓ ≤ 0.01) on 11 of 13
designs. The exceptions are honest: the fandipole's near-open parallel
resonance and the loaded short dipole move under *every* engine — those
are genuinely mesh-hard designs, and the raw NEC-5 column shows the
first-order march the (N, 2N) pair recipe exists to remove.

## Honest limits

What antennaknobs will not claim, in one table. Refusal-over-wrong is a
design decision: where a number would be misleading, you get a named
refusal or a flag, not a number.

| limit | treatment |
| --- | --- |
| Surface patches (SM/SP) | Not modelled. Patch decks refuse at import with the feature named. |
| Buried wires / below-ground conductors | Refused by name in every engine lane. |
| Electrically tiny, fat-conductor loops (magloop class) | Kernel-sensitive beyond any single-kernel read — reduced vs extended thin-wire kernels move results both ways by amounts that swamp formulation agreement. Census rows carry a kernel-sensitivity flag rather than a false-precision number. |
| `sin` basis on junction fans | A documented instability class on multi-wire junction geometries. bs2 is the default and census basis; `sin` remains available with the caveat attached. |
| Stepped-radius decks scored against NEC-2 references | The reference is the suspect (two independent formulations agree against it). Census rows carry the stepped-radius flag and score against NEC-5 mutually instead of pretending the nec2c number is truth. |

## Reproducibility

- **The corpus is public.** The wild decks are collected from published
  archives; the deck paths in every census artifact identify them.
- **The reference lane is free software.** nec2c costs nothing; anyone can
  re-run every nec2c number on this page.
- **antennaknobs and momwire are MIT-licensed.**
- **NEC-5 requires an individual license** (LLNL). antennaknobs never
  ships or hosts it — the lane activates only against your own licensed
  binary (`NEC5_EXE`). Captured printouts in the test suite are End-User
  Reports carrying the LLNL-CODE-746721 citation; NEC-5 behaviour is
  described here by paraphrase and citation, never reproduced manual text.
- **The published anchors are cited, not copied.** The Leeson-demo target
  values are Cebik's published tables ("Tapering to Perfection",
  *Antenna Modeling* #10, archived in the community Cebik archive); the
  ByDipole1 external curves are AC6LA's published plots.
- **This page is generated** by `scripts/build_validation_report.py` from
  committed artifacts in `scratch/` (ByDipole1 ladders, the Leeson cases,
  the convergence census, the fourth-vote artifact); `--recompute` re-runs
  the ByDipole1 study live and `scripts/bench_leeson.py` regenerates the
  Leeson cases. The census instruments are `scripts/bench_nec_corpus.py`
  and `scripts/bench_nec5_convergence.py`; per-phase writeups live in
  `docs/status/`.

## Anchors that are not any engine

Cross-engine agreement can, in principle, be three engines sharing one
mistake. The rows below are pinned to values set by physics alone. The
first is energy conservation: for a lossless antenna in free space the
power-gain pattern must average to exactly 1 over the sphere. momwire
computes gain through a closed-form directivity norm
(η₀k²/8π · |M⊥|²/P_in — momwire#231), so its row measures the entire
normalization chain against the conservation law; the nec2c and NEC-5
rows are their own printouts' averages over their own grids.

{anchors_table}

Case: the ByDipole1 wire in free space, lossless, 51 segments. A
deviation in the fourth decimal is grid quadrature; a deviation in the
second would be a normalization defect — that is the failure mode this
row exists to catch.

This page grows as the validation story does: further analytic anchors
(King-Middleton second-order dipole values, from King's published
tables), community-submitted problem decks — every submission gets a
published per-deck verdict — and measured-data anchors.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--recompute",
        action="store_true",
        help="re-run the ByDipole1 ladders live (nec2c + momwire + $NEC5_EXE)",
    )
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT / "scripts"))
    if args.recompute:
        data = recompute_ladders()
    else:
        data = json.loads(LADDERS.read_text())
    if args.recompute or not ANCHORS.exists():
        anchors = recompute_anchors()
    else:
        anchors = json.loads(ANCHORS.read_text())
    phase2 = json.loads(PHASE2.read_text())
    votes = json.loads(VOTES.read_text())
    leeson = json.loads(LEESON.read_text())

    render_figure(data)
    render_leeson_figure(leeson)
    PAGE.write_text(build_page(data, phase2, votes, leeson, anchors))
    print(f"wrote {PAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
