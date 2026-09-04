"""Build the public validation page (#896 phase 0).

Consumes committed census artifacts and emits the site validation page plus
its figure — every number on the page is either computed here from a
committed artifact or a cited literal from a docs/status writeup:

  scratch/bydipole1-ladders.json      ByDipole1 four-engine ladders (computed)
  scratch/bydipole1-freespace-ladders.json  the free-space twin panel: bs1 /
                                      razor (momwire#311) / NEC-5 (computed)
  scratch/bydipole1-pulse-ladder.json  the pulse column: PulseSolver out to
                                      6401 segments vs the bs2 limit (computed)
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
FREE_LADDERS = ROOT / "scratch" / "bydipole1-freespace-ladders.json"
PULSE_LADDER = ROOT / "scratch" / "bydipole1-pulse-ladder.json"
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

# The pulse column's own ladder. Odd counts, because a pulse row IS a segment
# and the feed snaps to the nearest centroid — an odd count puts one segment
# centred on the wire's middle, the same parity nec2c and bs2 want. It runs
# to 6401 because this scheme's error is set by Δ/a rather than Δ/λ (see
# `pulse_section`), so the interesting part of its march is off the right-hand
# edge of the other two columns entirely.
PULSE_N = [13, 25, 51, 101, 201, 401, 801, 1601, 3201, 6401]
# The Harrington lane stops earlier, for two reasons that point the same way:
# it is flat to well under an ohm by 1601 (its error is O(1/N), not O(Δ/a)),
# and its fill is ~5x the nodal row's — the charge cells make the moment
# block (2n x 2n) — so the 6401 rung the nodal lane NEEDS to reach its limit
# would be a 12802-square moment matrix for a lane that stopped moving three
# rungs earlier.
HARRINGTON_N = PULSE_N[: PULSE_N.index(1601) + 1]
PULSE_REF_N = 401  # bs2 mesh for the converged free-space limit


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


# --------------------------------------------------------------------------
# ByDipole1 free-space companion: the formulation-twin panel. RazorSolver is
# free-space by design (its ground would be Michalski's, which carries its
# own limit offset and would muddy the twin comparison), so its lane lives
# on the same wire with the ground removed, next to the two lanes that give
# it meaning: bs1 (same tent basis, Galerkin testing) and NEC-5 (the
# formulation it twins). Recomputing the razor lane needs momwire >= the
# #311 RazorSolver branch; page rebuilds from the committed JSON do not.


def _free_wire_solver(n: int, cls, **kw):
    import numpy as np

    c0 = 299792458.0
    wires = [np.array([[0.0, 0.0, 0.0], [0.0, L, 0.0]])]
    solver = cls(
        wires=wires, nsegs=n, wire_radius=RAD, wavelength=c0 / (FREQ * 1e6), **kw
    )
    z, _ = solver.compute_impedance()
    return z


def _nec5_free_z(n: int, eng) -> complex:
    deck = (
        "CM tri-razor free-space ladder\nCE\n"
        f"GW 1 {n} 0.000000E+00 0.000000E+00 0.000000E+00 "
        f"0.000000E+00 {L:.6E} 0.000000E+00 {RAD:.6E}\n"
        "GE 0\n"
        f"EX 0 1 {n // 2} 2 1.000000E+00 0.000000E+00\n"
        f"FR 0 1 0 0 {FREQ:.6E} 0.000000E+00\nXQ 0\nEN\n"
    )
    return eng.run_deck(deck)[0][0][2]


def recompute_free_ladders() -> dict:
    from momwire import RazorSolver
    from momwire.bspline import BSplineSolver

    from antennaknobs.engines.nec5 import NEC5Engine
    from bench_nec5_walk_why import make_dipole

    eng5 = NEC5Engine(
        make_dipole(20),
        ground=None,
        capture_dir=Path.home() / ".antennaknobs" / "nec5-captures",
    )
    free = {}
    free["nec5"] = [[n, *_ri(_nec5_free_z(n, eng5))] for n in EVEN]
    print("nec5 free done", flush=True)
    free["bs1"] = [
        [n, *_ri(_free_wire_solver(n, BSplineSolver, degree=1))] for n in EVEN
    ]
    print("bs1 free done", flush=True)
    free["razor"] = [[n, *_ri(_free_wire_solver(n, RazorSolver))] for n in EVEN]
    print("razor done", flush=True)
    # The momwire#316 mode: NEC-5's identified centroid-trapezoid path rule.
    # This lane lands on the NEC-5 curve rung-for-rung (constant
    # ~0.004+0.037j residual) — the quadrature IS the coarse-mesh excess.
    free["razor_n5q"] = [
        [n, *_ri(_free_wire_solver(n, RazorSolver, nec5_quadrature=True))] for n in EVEN
    ]
    print("razor_n5q done", flush=True)
    FREE_LADDERS.write_text(json.dumps(free))
    return free


# --------------------------------------------------------------------------
# The pulse column: the oldest thin-wire scheme there is, on the same wire.
# Harrington's piecewise-constant expansion with point matching (momwire's
# `PulseSolver`, the momwire#416 architecture probe) reaches the SAME limit
# as every other lane — it just needs about 64× the mesh to get there, so it
# gets its own log-x column instead of a fourth line on the free-space axes.


def _require_solvers() -> dict:
    """Both pulse rows, or a sentence naming what is missing and why.

    `HarringtonSolver` arrived with momwire#557/#559. A submodule pinned
    before that imports fine and then fails on the attribute, so this asks
    the question once, up front, rather than letting an hour of solves
    discover it.
    """
    import momwire

    missing = [
        n for n in ("PulseSolver", "HarringtonSolver") if not hasattr(momwire, n)
    ]
    if missing:
        raise SystemExit(
            f"--recompute needs {', '.join(missing)}, which this momwire does "
            f"not export (momwire#557/#559). Update the submodule, or drop "
            f"--recompute to rebuild the page from the committed ladder JSON."
        )
    return {"pulse": momwire.PulseSolver, "harrington": momwire.HarringtonSolver}


def recompute_pulse_ladder() -> dict:
    """Both pulse rows on the same ladder: the charge-support instrument.

    `PulseSolver` and `HarringtonSolver` are the same basis, the same
    testing, the same kernel and the same feed — they differ in where the
    charge LIVES, and nothing else. Running both here is what turns the
    column from an anecdote about one bad row into a measurement of that
    one ingredient. Recomputing the harrington lane needs momwire >= the
    #557 branch; page rebuilds from the committed JSON do not.
    """
    from momwire.bspline import BSplineSolver

    # Probe both solvers BEFORE spending anything. `HarringtonSolver` is
    # momwire#557/#559 and a submodule older than that does not have it —
    # importing lazily further down meant a stock-pin recompute burned the
    # whole nodal ladder (~40 s and ~5 GB on the 6401 rung alone) and then
    # died with nothing written.
    solvers = _require_solvers()

    out = {
        "ref_n": PULSE_REF_N,
        "ref": _ri(_free_wire_solver(PULSE_REF_N, BSplineSolver, degree=2)),
    }
    # Harrington first, deliberately: it is the cheap ladder AND the one
    # whose availability is version-dependent, so if anything is going to
    # fail it fails before the expensive lane rather than after it. The JSON
    # is written after EACH lane for the same reason — a failure in lane two
    # used to discard lane one's solves.
    lanes = (
        ("harrington", solvers["harrington"], HARRINGTON_N),
        ("pulse", solvers["pulse"], PULSE_N),
    )
    for key, cls, ladder in lanes:
        rows = []
        for n in ladder:
            rows.append([n, *_ri(_free_wire_solver(n, cls))])
            print(f"{key} n={n} done", flush=True)
        out[key] = rows
        PULSE_LADDER.write_text(json.dumps(out))
    return out


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


def pulse_section(pulse: dict) -> tuple[str, float, float, int]:
    """Both charge models on one ladder, plus the numbers the prose quotes.

    Returns (table, the worst-case ratio between the two lanes' errors, the
    dual-cell lane's error at its last rung, the segment count where Δ/a
    reaches 1 on this wire).
    """
    ref = complex(*pulse["ref"])
    dual = {row[0]: _z(row) for row in pulse["harrington"]}
    rows = [
        "| Segments | Δ/a | charge at a point | error | Harrington's dual cell | error |",
        "|---|---|---|---|---|---|",
    ]
    ratios = []
    for row in pulse["pulse"]:
        n, z = row[0], _z(row)
        err = abs(z - ref)
        if n in dual:
            d_err = abs(dual[n] - ref)
            ratios.append(err / d_err)
            rows.append(
                f"| {n} | {L / (n * RAD):.4g} | {fmt_z(z)} | {err:,.1f} | "
                f"{fmt_z(dual[n])} | {d_err:,.2f} |"
            )
        else:
            rows.append(
                f"| {n} | {L / (n * RAD):.4g} | {fmt_z(z)} | {err:,.1f} | — | — |"
            )
    rows.append(f"| limit (bs2, N={pulse['ref_n']}) | — | {fmt_z(ref)} | — | — | — |")
    last_dual = abs(dual[max(dual)] - ref)
    return "\n".join(rows), max(ratios), last_dual, round(L / RAD)


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


def _style_axis(ax, grid: str, ink2: str) -> None:
    """The figure's axis furniture, in one place.

    Three panels' worth of columns had this block byte-for-byte, which is
    three chances for one of them to drift into looking subtly unlike the
    others.
    """
    ax.grid(True, color=grid, lw=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(ink2)
    ax.tick_params(colors=ink2, labelsize=9)


def render_figure(data: dict, free: dict, pulse: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    surface = "#fcfcfb"
    ink, ink2, grid = "#1a1a19", "#5f5e56", "#e8e8e6"
    # Column 0: the over-ground exhibit, unchanged. Column 1: the same wire
    # in free space — RazorSolver is free-space by design, so the twin
    # comparison lives on axes NEC-5's Michalski ground cannot contaminate.
    # bs1 and NEC-5 keep their colors across columns; razor gets its own.
    columns = [
        (
            data,
            {
                "bs2": ("#2a78d6", "momwire bs2"),
                "bs1": ("#eb6834", "momwire bs1"),
                "nec5": ("#1baf7a", "NEC-5"),
                "nec2c": ("#eda100", "nec2c (NEC-2)"),
            },
            "over Sommerfeld ground (εr 20, σ 0.0303 S/m)",
        ),
        (
            free,
            {
                "bs1": ("#eb6834", "momwire bs1"),
                "razor": ("#7a5bd6", "momwire razor"),
                "nec5": ("#1baf7a", "NEC-5"),
                # NEC-5's identified quadrature (momwire#316): drawn as a
                # marker-free dashed overlay so the green NEC-5 curve shows
                # through between the dashes — the two are one curve to
                # within a constant 0.04 Ω.
                "razor_n5q": ("#b2379b", "razor, NEC-5 quadrature"),
            },
            "free space — the formulation twin (momwire#309/#316)",
        ),
    ]
    dashed = {"razor_n5q"}
    pulse_color = "#c9314b"
    harrington_color = "#8c4a1f"

    # sharex="col", not True: the pulse column's ladder runs to 6401 segments
    # on a log axis and must not drag the other two columns' 8–118 window
    # with it.
    fig, axes = plt.subplots(
        3, 3, figsize=(18.6, 10.2), sharex="col", facecolor=surface
    )
    panels = [
        ("Source R (Ω)", lambda z: z.real),
        ("Source X (Ω)", lambda z: z.imag),
        ("SWR(50)", swr),
    ]
    for col, (col_data, series, col_title) in enumerate(columns):
        for ax, (ylabel, f) in zip(axes[:, col], panels, strict=True):
            ax.set_facecolor(surface)
            ends = []
            for key, (color, label) in series.items():
                pts = col_data[key]
                ns = [p[0] for p in pts]
                ys = [f(_z(p)) for p in pts]
                if key in dashed:
                    ax.plot(ns, ys, color=color, lw=1.6, ls=(0, (4, 3)), label=label)
                else:
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
            for (y, n, label, color), ly in zip(ends, placed, strict=True):
                ax.text(n + 2.5, ly, label, va="center", fontsize=9, color=color)
            if col == 0:
                ax.set_ylabel(ylabel, color=ink, fontsize=10)
            _style_axis(ax, grid, ink2)
            ax.set_xlim(8, 118)
        axes[0, col].legend(
            loc="lower right", frameon=False, fontsize=9, labelcolor=ink
        )
        axes[2, col].set_xlabel("Number of segments", color=ink, fontsize=10)
        axes[0, col].set_title(col_title, color=ink, fontsize=10, loc="left", pad=8)

    # Column 2: the same pulse basis under two charge models, on the same
    # free-space wire. Both lanes are Harrington's expansion with point
    # matching; they differ in where the CHARGE lives and in nothing else —
    # `PulseSolver` leaves it as two point charges at the segment ends,
    # `HarringtonSolver` spreads it over the half-shifted dual cell his 1967
    # paper specifies. So the gap between these two curves is the price of
    # one ingredient, which is what earns the column its place beside two
    # panels about basis and testing.
    #
    # Every row keeps its quantity and changes scale: the nodal lane's
    # capacitive excess spans four decades and its SWR three, so linear axes
    # would draw one visible point and a wall. The dashed horizontal is the
    # converged bs2 value both lanes walk toward; the dotted vertical is
    # Δ/a = 1, past which the NODAL lane's point-charge concentration error
    # reverses (momwire tests/test_pulse.py) — on a wire this thin that limit
    # is off the ladder, which is the whole reason the column needs its own
    # axes. The dual-cell lane has no such wall: its error is O(1/N).
    ref_z = complex(*pulse["ref"])
    pn = [p[0] for p in pulse["pulse"]]
    hn = [p[0] for p in pulse["harrington"]]
    reversal = L / RAD
    for row, (ax, (ylabel, f), scale) in enumerate(
        zip(axes[:, 2], panels, ("linear", "symlog", "log"), strict=True)
    ):
        ax.set_facecolor(surface)
        ax.axhline(f(ref_z), color=ink2, lw=1.2, ls=(0, (5, 3)))
        ax.axvline(reversal, color=ink2, lw=1.0, ls=(0, (1, 3)))
        for key, xs, color, label in (
            ("pulse", pn, pulse_color, "pulse — charge at a point"),
            ("harrington", hn, harrington_color, "pulse — Harrington's dual cell"),
        ):
            ax.plot(
                xs,
                [f(_z(p)) for p in pulse[key]],
                color=color,
                lw=2,
                marker="o",
                ms=3.5,
                mfc=color,
                mec=surface,
                mew=0.5,
                label=label,
            )
        ax.set_xscale("log")
        if scale == "symlog":
            ax.set_yscale("symlog", linthresh=100)
        elif scale == "log":
            ax.set_yscale("log")
        ax.set_xlim(11, 16000)
        ax.set_xticks([13, 51, 201, 801, 3201])
        ax.set_xticklabels(["13", "51", "201", "801", "3201"])
        ax.set_ylabel(ylabel, color=ink, fontsize=10)
        _style_axis(ax, grid, ink2)
    # The two reference marks are legend entries rather than in-axes text:
    # every x they could be written at has a curve running through it.
    handles, labels = axes[0, 2].get_legend_handles_labels()
    handles.append(Line2D([], [], color=ink2, lw=1.2, ls=(0, (5, 3))))
    labels.append("converged limit (bs2)")
    handles.append(Line2D([], [], color=ink2, lw=1.0, ls=(0, (1, 3))))
    labels.append("Δ/a = 1 — the point charge's wall")
    axes[0, 2].legend(
        handles, labels, loc="lower right", frameon=False, fontsize=9, labelcolor=ink
    )
    axes[2, 2].set_xlabel("Number of segments", color=ink, fontsize=10)
    axes[0, 2].set_title(
        "free space — one basis, two charge models (momwire#416/#557)",
        color=ink,
        fontsize=10,
        loc="left",
        pad=34,
    )

    # Δ/a is the axis this scheme actually converges on, and it is its own
    # inverse here: Δ/a = L/(N a) and N = L/((Δ/a) a).
    def _delta_over_a(x):
        import numpy as np

        return L / (np.clip(np.abs(x), 1e-9, None) * RAD)

    secax = axes[0, 2].secondary_xaxis("top", functions=(_delta_over_a, _delta_over_a))
    secax.set_xlabel("Δ / a  (segment length in wire radii)", color=ink2, fontsize=9)
    secax.tick_params(colors=ink2, labelsize=8)
    fig.suptitle(
        "ByDipole1 (EZNEC 7 sample) — feed-point convergence vs engine\n"
        "10.19 m dipole (#12 wire, 1.0262 mm radius), 14 MHz; left at 9.14 m "
        "over ground, centre "
        "and right the same wire in free space (right on its own log ladder)",
        color=ink,
        fontsize=11,
        x=0.02,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
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
    _style_axis(ax, grid, ink2)
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
    data: dict,
    free: dict,
    pulse: dict,
    phase2: dict,
    votes: list[dict],
    leeson: dict,
    anchors: dict,
) -> str:
    bd_table, bd_pairs = bydipole1_section(data)
    pulse_table, pulse_ratio, pulse_dual_err, pulse_reversal = pulse_section(pulse)
    pulse_dual_n = max(row[0] for row in pulse["harrington"])
    razor_diffs = [
        _z(free["razor"][EVEN.index(2 * n)]).imag
        - _z(free["razor"][EVEN.index(n)]).imag
        for n in (12, 24, 48)
    ]
    nec5f_diffs = [
        _z(free["nec5"][EVEN.index(2 * n)]).imag - _z(free["nec5"][EVEN.index(n)]).imag
        for n in (12, 24, 48)
    ]
    razor_pairs = " / ".join(f"{d:+.2f}" for d in razor_diffs)
    nec5f_pairs = " / ".join(f"{d:+.2f}" for d in nec5f_diffs)
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

ByDipole1 ships with EZNEC 7: a 10.19 m dipole at 9.144 m height, #12
wire (1.0262 mm radius), 14 MHz, over real Sommerfeld ground (εr 20, σ 0.0303 S/m). It is a
community-recognizable case — NEC-2 vs NEC-5 convergence plots for it were
independently published by AC6LA — and it sits squarely in NEC-2's good
regime (single radius, no junctions), which makes it a *convergence-rate*
exhibit: every engine here converges to the same answer, and the question
is how many segments each needs to get there.

![Three-column convergence plot: feed-point R, X and SWR versus segment
count on ByDipole1. Left, over ground: momwire bs2, momwire bs1, NEC-5 and
nec2c — the bs2 curve is flat from eleven segments while NEC-5 approaches
the common limit in a first-order march. Centre, the same wire in free
space: momwire's razor solver shares NEC-5's first-order march and lands
on the same limit, bs1 on the same tent basis with Galerkin testing
converges faster, and a dashed razor lane using NEC-5's identified
quadrature lies directly on the NEC-5 curve. Right, on log axes running to
6401 segments: the same pulse basis under two charge models — a point charge
at each segment end, which walks to the converged limit from kilohms of
capacitive excess and only closes as the segment length approaches the wire
radius, and Harrington's half-shifted dual cell, which converges first-order
with no such
wall.](../../../assets/validation/bydipole1-convergence.png)

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

The centre column is the same wire in free space, and it explains WHY
NEC-5 marches. NEC-5's public manual states its formulation — a triangular
(tent) current expansion tested by Rao-Wilton-Glisson path integrals
between element centroids ("razor-blade" testing) — and momwire now
implements that exact scheme as `RazorSolver`, the formulation twin
(momwire#309). On identical meshes the twin shares NEC-5's first-order
march — X-pair steps X(2N)−X(N) of {razor_pairs} Ω against NEC-5's
{nec5f_pairs} Ω at N=12/24/48, the same halving-per-doubling signature
(NEC-5 carries extra coarse-mesh excess on the first pair) — and the two
curves land together on a common limit, while bs1, the *same tent basis*
under Galerkin testing, converges visibly faster on its own trajectory. The march is the testing rule, reproduced
from the manual's description alone, with no NEC-5 code involved.

The dashed overlay closes the loop: NEC-5's remaining coarse-mesh excess
over the twin was identified (momwire#316) as its quadrature — the
∫A·dl testing integral evaluated by a two-point trapezoid at the element
centroids, the literal reading of "path integrals between centroids".
With that one rule adopted (`nec5_quadrature=True`), the razor lane lands
on NEC-5's curve at every rung, to a constant −0.004−0.037j Ω — an
N-independent kernel nuance and the entire remaining difference between
the two codes on this wire. (The twin panel is free-space by choice, not
necessity: `RazorSolver` serves the PEC and Sommerfeld grounds, and
`razor-2p` is the app's above-ground lane over both. NEC-5's Michalski
ground has its own small limit offset that would blur the formulation
comparison, so the twin is compared where the formulation is the only
difference.)

### What the charge model is worth: one basis, two ways to place it

The right-hand column holds the oldest thin-wire scheme there is —
Harrington's piecewise-constant current, point-matched, 1967 — twice. Both
lanes use the same basis, the same testing, the same kernel and the same
feed. They differ in one thing: **where the charge lives.**

A pulse current is discontinuous, so its charge is exactly two spikes at the
segment ends. You can take that literally and put a point charge there, which
is what momwire's `PulseSolver` does. Or you can do what Harrington's paper
actually specifies — spread each one over a half-shifted cell straddling the
node, his equations (95)/(96)/(100) — which is `HarringtonSolver`. Everything
else about the two rows is the same code.

{pulse_table}

That is a factor of **{pulse_ratio:.0f}×** between two solvers that differ by
one modelling decision, and it is the sharpest statement this page can make
about why formulations are worth arguing over. Neither lane is wrong about the
physics; both walk to the same limit. One of them just needs {pulse_ratio:.0f}
times the accuracy budget to get there.

**Why the point charge costs so much.** Its error is governed by **Δ/a —
segment length in wire radii — not Δ/λ**. A point charge's potential at its
own location is finite only because the thin-wire kernel floors the distance
at the conductor radius, so the mesh has to approach the *radius* before that
error retires. ByDipole1's wire is 1.0262 mm in radius — #12 AWG — which
puts Δ/a = 1 at about
{pulse_reversal:,} segments — the dotted vertical — and refining past it does
not merely stop helping, it reverses. The usable window is the sliver between
that wall and a mesh nobody would pay for.

Give the charge a cell of its own length and the wire radius stops setting the
scale. The dual-cell lane converges O(1/N) like any classical scheme, reaching
{pulse_dual_err:.2f} Ω at {pulse_dual_n:,} segments, with no wall anywhere on
the axis.

**What this column is not.** It is not a claim that the 1967 scheme is
obsolete — momwire ships it as `HarringtonSolver`, and it is a perfectly
reasonable base case. (`PulseSolver`, the point-charge lane beside it, is
momwire's own literal reading of the same basis, not Harrington's scheme;
neither is in the app's `--basis` roster.) It is a control: the two panels to its left vary the basis and the
testing, and this one varies neither. Whatever separates these two curves
cannot be blamed on either, which is what makes the number mean something.
Harrington's own advice, on page 145 of the same paper, is to move on anyway:
"faster convergence can be obtained by going from a step approximation to a
piecewise-linear approximation to the current" — the tent basis, which is the
`bs1` lane in the middle column.

Provenance: geometry translated from the EZNEC 7 distribution, with
EZNEC's current-source feed idiom replaced by a direct center voltage feed
(driving-point impedance is source-type independent; the equivalence is
pinned in the test suite). The NEC-2 curve is nec2c — the same lineage as
EZNEC's NEC-2D, independently implemented. The razor lane is momwire's
`RazorSolver` on the momwire#311 branch. The two pulse lanes are momwire's
`PulseSolver` and `HarringtonSolver` (momwire#557); the point-charge lane's
6401-segment rung is a 6401×6401 dense solve, about 40 s and 5 GB, and the
dual-cell lane stops at 1601 because its charge cells make the moment block
twice as wide in each direction, and by then it is inside an ohm of the
limit — still halving per rung, but far below anything the figure's axes
can show.

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
| Buried wires / below-ground conductors | **Served** on the momwire `bspline` lane over the Sommerfeld ground: impedance, currents and charges for wires strictly below the interface (buried radials and screens, buried fed elements, elevated feeds over buried counterpoises), and an above-ground wire joined at the surface to buried wires at a declared junction (the connected radial screen). **Refused by name:** a wire crossing the interface mid-span; ground-contact wires mixed with buried wires; a wire lying *in* the interface plane; a buried structure whose opposite tips are more than 4 in-medium wavelengths apart (the below/below remainder is tabulated to that range and grows with distance beyond it, so there is no honest clamp); and near fields / patterns of buried decks. A licensed local NEC-5 serves buried decks with its own detached-stake convention, which momwire refuses by name; on the buried-radial vertical's connected deck the two engines differ by the node model (NEC-5's point-electrode stake against momwire's crossing fill), 32.5 Ω apart on that design's defaults. On the elevated-detached class, which both serve as the same problem, they agree at the 0.2–2 Ω level converged ([the buried-radials study](/advanced/buried-radials/)). The PyNEC lane refuses buried decks outright. The validation stance below ground is its own paragraph under this table. |
| Electrically tiny, fat-conductor loops (magloop class) | Kernel-sensitive beyond any single-kernel read — reduced vs extended thin-wire kernels move results both ways by amounts that swamp formulation agreement. Census rows carry a kernel-sensitivity flag rather than a false-precision number. |
| `sin` basis on junction fans | A documented instability class on multi-wire junction geometries. bs2 is the default and census basis; `sin` remains available with the caveat attached. |
| Stepped-radius decks scored against NEC-2 references | The reference is the suspect (two independent formulations agree against it). Census rows carry the stepped-radius flag and score against NEC-5 mutually instead of pretending the nec2c number is truth. |
| `wire.sterba_bl` on the momwire `razor` lanes | Not served, at any mesh, with or without ground. The deck carries a junction PORT, and a junction basis is already a through-current unknown, so the razor formulation has nowhere to put one — it refuses by name with `junction_ports` rather than quietly dropping the port. `bspline` serves the deck normally, and is the lane the census uses for it. |

**Below the interface, validation is deliberately engine-independent.** The
NEC family's buried-conductor weakness is documented publicly
(LLNL-TR-490316) and corroborated in our licensed materials (details in
private notes), so no engine number is quoted for a fully buried fed
element — on this page or anywhere else. The gates are exact identities
instead: the lossless-limit collapse onto the free-space solve, the
deep-burial limit onto the infinite-medium solve, and a quasi-static
two-electrode cross-estimate — plus, on the buried radial and counterpoise
classes where the reference engine's convergence ladders are clean,
ladder-limit agreement at the half-percent class with the
with/without-radials coupling differential matching to about a milliohm.

## Underground: what the second reading is

Above ground, a number is checked against another engine. Underground that
option is deliberately closed, so the structure is different and worth stating
plainly. The **reference is a measurement** — Brown, Lewis and Epstein's 1937
buried-radial curves, gated. The **engine** is momwire's bspline at degree 2.
The **second reading** is bspline at degree 1: the same trunk, a different
basis (a tent under Galerkin testing rather than a quadratic B-spline). It is
not an independent engine and is not offered as one. `razor-2p` is the
above-ground twin of licensed NEC-5 and is **not gated below ground, by
decision**; the NEC family's buried-conductor weakness is the same reason no
engine number is quoted for a fully buried fed element anywhere on this page.

What the pair buys is a check that the answer is a property of the
formulation rather than of one basis. |bs1 − bs2| at each anchor's own mesh,
in ohms, against a 1.5 Ω bar:

| anchor (fed above ground) | \\|bs1 − bs2\\| |
| --- | --- |
| crossing deck | 0.96 |
| hub deck | 0.48 |
| graded fan (far mesh only) | 0.40 |
| BLE 45 ft, 2 radials | 0.08 |
| BLE 45 ft, 15 radials | 0.24 |
| BLE 45 ft, 30 radials | 0.24 |
| catalog `buried_radial_vertical` | 0.55 |

Gated in momwire as `tests/test_bspline_pair_g1b.py`, with degree 2 solved
rather than read from the bank, so an ignored `degree` argument fails the
distinct-bases check rather than passing quietly.

Three things this is **not**, each of which it would be easy to read into it:

- **Not an agreement with razor or NEC-5.** Neither is asked below ground, so
  no such claim is available from these numbers.
- **Not a convergence rate.** It is a separation at the anchor mesh. Degree 1
  oscillates in R as the mesh refines — the crossing deck reads 139.58, 138.19,
  138.56, 138.15 Ω at ×1/3/5/9 — so the pair agrees on a value, not on a
  shrinking sequence, and quoting it as the latter would overstate it.
- **Not a claim about decks fed *in* the soil.** Those are not impedance
  anchors at any reachable mesh: both degrees still move ohms per rung, and
  the movement is the fed segment's own length rather than the mesh around it
  (about 20 Ω along the gap axis against 4.5 Ω along the side-refinement axis
  on the same deck). The same relative movement appears in free space, so it
  is the delta-gap source region's capacitance rather than anything the soil
  does. Those decks are gated on shape — monotone and shrinking — which is
  what they can honestly carry.

## The buried radial vertical: what a user may claim

`verticals.buried_radial_vertical` is the design with the most anchors behind
it below ground, so this is what each of them actually holds — and, at the
end, what none of them do.

**The reference is a measurement, not an engine.** Brown, Lewis and Epstein's
1937 buried-radial curves, gated in momwire as `tests/test_ble_1937_838.py`:
3 MHz, a 21.4 m mast (77°), No. 8 copper throughout, σ = 2×10⁻³. **ε_r = 15 is
an ASSUMPTION** — the paper states conductivity only, and that single
assumption is worth about 3.6 Ω of what follows. Against Fig. 37 (45 ft
radials) the gate pins a *shape* rather than a number: steep fall, knee near
N = 15, plateau, with the plateau inside ±6 Ω of the figure's ~31 Ω. momwire
sits ~4 Ω low there. Against Fig. 36 (135 ft radials) agreement is markedly
better — within 1.4 Ω at every rung:

| N | 2 | 15 | 30 | 60 | 113 |
|---|---|---|---|---|---|
| momwire | 84.11 | 35.37 | 30.52 | 27.30 | 25.22 |
| Fig. 36 | ≥50 | 34 | 30 | 26 | 24.3 |

**The ±6 Ω envelope is falsifiable, and was falsified on purpose:** the same
deck at σ = 2×10⁻⁴ — a decade worse soil — reads R(30) = 24.76 Ω and is
rejected. Wide enough to carry the stated assumptions, narrow enough that
getting the ground wrong by a decade fails.

**One residual, recorded rather than smoothed.** The measurement's whole point
is that longer radials help. Fig. 36 and Fig. 37 separate by 6.7 Ω at N = 113;
momwire separates them by 1.75 Ω. It reproduces the ordering and the crossing,
and under-states the benefit. Not gated, because a gate on a 1.75-against-6.7
residual would be pinning a known disagreement.

**The second reading is the degree pair**, not a second engine — see
[Underground: what the second reading is](#underground-what-the-second-reading-is)
above; the catalog deck's row is there.

**The mesh is proven at the corners the app exposes, not just the default.**
Over the 11 solvable corners of the design's own knob ranges, refining each
axis independently moves the answer by at most: node grading ×3 **0.100 Ω**,
far mesh ×3 **0.126 Ω**, cross-edge quadrature at 64 **0.007 Ω**. The gate
holds each corner's banked answer to **0.10 Ω** — a tolerance measured rather
than chosen, and one whose limit is stated: it catches a 3× mesh coarsening and
**does not catch a 2×** one.

**Where the watts go has a physics gate and an outside reference.** The
hemispherical integral of linear gain is P_rad / P_in, so it must not exceed
one, and burying radials must raise it — which is the entire reason to bury
them. On the catalog deck at ε_r 13 / σ 0.005:

| radials | Z_in (Ω) | radiated fraction |
|---|---|---|
| 1 | 168.186 + 43.070j | 0.0766 |
| 2 | 107.964 + 43.057j | 0.1189 |
| 3 | 87.020 + 41.693j | 0.1479 |
| 4 | 75.850 + 40.451j | 0.1699 |

The same ordering holds on poor soil (5/0.001: 0.060 → 0.143) and good
(20/0.03: 0.223 → 0.349), with good > average > poor at every count.

The buried deck has no second engine to check the pattern code against, so the
cross-check runs on `verticals.raised_vertical`, which both engines serve, and
on the quantity that does not depend on whose input resistance you believe:
**radiated power for a fixed drive**, η·R_in. momwire against nec2++ reads
49.52 vs 49.57 over PEC, 14.88 vs 14.90 over 13/0.005, and 17.96 vs 17.98 over
20/0.03 — **0.10–0.13 %**, against a 1 % bar. The two engines differ by 9 % in
R_in on that deck; their far-field integrals agree to a tenth of a percent once
that is divided out.

**Two things are refused by name rather than approximated.** A wire lying *in*
the interface plane is not served (momwire#865) — that is the surface-radial
class, and it is being built. And a buried structure whose opposite radial tips
exceed 4 in-medium wavelengths apart is refused: the below/below remainder is
tabulated to that range, and unlike the reflected-wave remainder above the
interface it *grows* relative to the direct term with distance, so there is no
honest clamp beyond the table.

### What is not measured

- **Efficiency has no field-strength reference.** The radiated fraction above
  is a self-consistency bound plus a far-field cross-check on a *different*
  deck. Nothing here compares a computed efficiency against a measured one.
- **The surface class — radials lying on the ground — is refused**, not
  approximated (momwire#865). Its low-height limit is under study; a bare
  buried wire is not a model for an insulated one lying in grass, because the
  bare wire collects return current galvanically along its length.
- **nec2++'s own radiated fraction over PEC reads 1.057** — above unity —
  where momwire's reads 0.963. Grid clipping at the horizon, where a PEC
  vertical peaks. Recorded, not gated, and it is why the cross-check above is
  stated as η·R_in rather than as a fraction.

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
tables), community-submitted problem decks — the intake is
[antenna-problem-decks](https://github.com/stevenmburns/antenna-problem-decks),
where every submission gets a committed per-deck verdict (two published
so far: a 20:1 tapered dipole submitted by Ward Harriman, AE6TY, and
the hentenna — one NEC-2 defect class each — plus two hexbeam
verdicts requested via Reddit: the single-band broadband hexbeam,
the collection's first *agreement* entry (all three engines within
0.15 Ω, with the wire-gauge sensitivity measured rather than
assumed), and the 5-band stack (three-engine census on all five
bands plus the physical one-coax feed solved as a network — two
formulations within 1.2 Ω on every band; NEC-5 sits that one out,
having no TL stamping) — and measured-data anchors.
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
    if args.recompute or not FREE_LADDERS.exists():
        free = recompute_free_ladders()
    else:
        free = json.loads(FREE_LADDERS.read_text())
    if args.recompute or not PULSE_LADDER.exists():
        pulse = recompute_pulse_ladder()
    else:
        pulse = json.loads(PULSE_LADDER.read_text())
    if args.recompute or not ANCHORS.exists():
        anchors = recompute_anchors()
    else:
        anchors = json.loads(ANCHORS.read_text())
    phase2 = json.loads(PHASE2.read_text())
    votes = json.loads(VOTES.read_text())
    leeson = json.loads(LEESON.read_text())

    render_figure(data, free, pulse)
    render_leeson_figure(leeson)
    PAGE.write_text(build_page(data, free, pulse, phase2, votes, leeson, anchors))
    print(f"wrote {PAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
