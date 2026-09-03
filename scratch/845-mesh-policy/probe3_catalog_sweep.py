"""momwire#845 part 1b — razor-2p against bspline-d2 on every razor-2p-served
catalog deck, at the shipped mesh and at 2x and 4x.

This is the per-deck table the #845 advisory quotes: for each deck, how far
razor-2p's driving-point impedance sits from the converged answer AT THE MESH
THE DECK ACTUALLY SHIPS WITH, and how much of that a 2x or 4x refinement buys.
probe2 established the scale a per-solver mesh policy would need (6.8-7.8x on
a base-fed quarter-wave, 15.8-16.1x on a free dipole) and probe1 established
that the catalog cannot absorb it; this probe says which decks are affected
and by how much, which is what an advisory has to be able to state.

Reference. Per deck and per ground, the converged answer is taken as
**bspline-d2 at 4x**, and the report prints bspline's own 2x -> 4x move
alongside every row. That second number is not decoration: a |dZ| is only
meaningful to the extent its reference has settled, and the rule this probe
inherited from probe2 is that **a tolerance row whose reference moved by more
than a third of the tolerance is an artifact of the reference, not a
measurement** — in probe2 an unconverged reference produced a tidy "4.0x"
that matched #845's headline figure for entirely the wrong reason. Rows whose
reference has not settled are marked rather than quietly tabulated.

Ground, per the coordinating session: free space plus Sommerfeld (the shipped
finite ground, eps_r 10 / sigma 0.002) for decks under 2000 total segments,
free space only above, since razor's first-order class shows under Sommerfeld
contact and pec adds nothing. The threshold is on Sigma-seg at the mesh being
solved, so a deck can qualify at 1x and drop out at 4x; the report says which.

Each solve runs in a fresh subprocess with an address-space cap, so one
runaway finite-ground fill fails cleanly with its row marked instead of taking
the sweep down or swapping the box — the same isolation `scripts/bench_catalog.py`
uses, for the same reason.

The seven decks with no `design_freq` are included deliberately even though
their mesh does not move with `nominal_nsegs`: their 1x/2x/4x columns coming
back IDENTICAL is the direct demonstration of probe1's finding that a scale in
`auto_mesh` cannot reach them.

RESULTS, 2026-09-03, AK main fc0e5c68c + momwire 9eda56f. 100 decks solved;
88 free / 83 Sommerfeld carry a reportable razor 1x number (the rest are
guard-skipped, refused, or have no bounded reference).

**razor-2p at the SHIPPED mesh is a median 2.29 ohm from converged**, mean
4.01, range 0.17-32.19. 77 of 88 decks are over 1 ohm, 48 over 2, 36 over 3.
Refining halves it as the class predicts: median 2.29 -> 1.27 at 2x -> 0.70 at
4x. **The ground barely matters** -- 2.29 free against 2.24 Sommerfeld, medians
within 2 % -- which independently confirms #845's own comment 2 ("it is not the
ground") across the whole catalog rather than on four decks.

**THE ABSOLUTE-OHM FRAMING IS MISLEADING, and this issue uses it throughout.**
corr(|Z|, |dZ|) = +0.69, so most of the 189x spread in ohms is a spread in
impedance magnitude, not in accuracy. `wire.lazy_h` is the catalog's worst deck
at 32.19 ohm and its |Z| is 5092 ohm, i.e. **0.63 %** -- while
`loops.skyloop_lmatch` (16.11 ohm at |Z| 48) is **33.6 %**. Ranked in ohms the
0.6 % deck comes first and the 33 % decks are invisible. In relative terms the
median is 3.34 % and the tail is skyloop_lmatch 33.6 %, verticals.rectangle
32.9 %, dipoles.koch_dipole 32.6 % -- all at ordinary ~48 ohm feedpoints, which
is where a third of the answer being wrong actually matters.

**NO SOLVE-FREE PROPERTY PREDICTS THE ERROR.** This is the finding that decides
the advisory's design, and it is negative:

    corr(lambda/delta , |dZ|)      = +0.021        corr(lambda/delta, rel) = +0.092
    corr(delta/a      , |dZ|)      = +0.135        corr(n_wires,      rel) = -0.066
    corr(n_wires      , |dZ|)      = -0.087        corr(|Z|,          rel) = -0.170
    corr(Sigma-seg    , |dZ|)      = -0.056

74 decks share lambda/delta in 80-90 while their |dZ| runs 0.17 to 32.19 ohm.
So an advisory that fires on FAR SEGMENT LENGTH keys on a quantity carrying
essentially zero information about the error it warns about: at the shipped
density it would fire on all 74 identically, or on none, while their true
errors differ by 190x. Family medians do not separate either (loops 1.23 %
median against a 33.58 % max).

What an honest advisory CAN say, given that: because probe1 found
lambda/delta is constant at ~83 across the catalog, "the default mesh" is a
well-defined class, and the advisory can state what that class COSTS -- median
3.3 % relative, tail to 34 %, halving per mesh doubling -- and name bspline as
the converged engine. What it cannot do is discriminate between decks, so it
should be unconditional on the razor-2p path rather than threshold-triggered.
A threshold on segment length would be a trigger that looks principled and
fires at random with respect to the thing it guards.

Timing caveat: `t_r1x`/`t_b1x` are wall seconds, and the workers spawn 15
OpenMP threads onto 8 cores because this probe does not call
`bench_converge.apply_server_thread_policy()` the way `scripts/bench_catalog.py`
does. Oversubscription is uniform across decks so within-table comparison
holds, but the absolute numbers are not quotable. Part 3 was cut, so this was
not worth a re-run; add that call first if a timing number is ever wanted.

Run: .venv/bin/python scratch/845-mesh-policy/probe3_catalog_sweep.py --json out.json
     .venv/bin/python scratch/845-mesh-policy/probe3_catalog_sweep.py --design loops.quad
     .venv/bin/python scratch/845-mesh-policy/probe3_catalog_sweep.py --report-only out.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

_spec = importlib.util.spec_from_file_location(
    "bench_converge", ROOT / "scripts" / "bench_converge.py"
)
cvg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cvg)

BURIED = (
    "specialty.buried_dipole",
    "verticals.buried_radial_vertical",
    "verticals.elevated_buried_counterpoise",
)

GROUNDS = {"free": "free", "somm": ("finite", 10.0, 0.002)}
MULTS = (1, 2, 4)
ENGINES = ("razor-2p", "bspline-d2")

# Finite ground is the expensive fill; above this many segments a deck is
# solved in free space only.
MAX_SEG_FINITE = 2000
DEFAULT_MEM_GB = 20.0
DEFAULT_TIMEOUT = 900.0


def solve_one(design, nseg, engine, ground):
    """One impedance through the antennaknobs momwire engine. razor-2p is not
    in `bench_converge.solve_design`'s engine roster (it predates the razor
    lane), so the two engines are bound here from the same pairs
    `antennaknobs.cli.MOMWIRE_BASIS_VARIANTS` uses."""
    from momwire import BSplineSolver, RazorSolver

    from antennaknobs.engines.momwire import MomwireEngine

    binding = {
        "razor-2p": (RazorSolver, {"nec5_quadrature": True}),
        "bspline-d2": (BSplineSolver, {"degree": 2}),
    }[engine]

    cls = cvg.load_design(design)
    b = cls()
    b.nominal_nsegs = nseg

    t0 = time.perf_counter()
    eng = MomwireEngine(b, solver=binding[0], solver_kwargs=binding[1], ground=ground)
    zs = eng.impedance()
    secs = time.perf_counter() - t0
    return {
        "error": None,
        "z": [[float(z.real), float(z.imag)] for z in zs],
        "solve_s": secs,
        "total_nominal_segs": cvg.total_nominal_segs(cls, nseg),
    }


def worker_main(design, nseg, engine, ground_json, mem_gb):
    result = {"error": None}
    try:
        # argv values arrive as strings; coerce before comparing.
        mem_gb = float(mem_gb) if mem_gb else 0.0
        if mem_gb > 0:
            cap = int(mem_gb * 1024**3)
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        ground = json.loads(ground_json)
        if isinstance(ground, list):
            ground = tuple(ground)
        result = solve_one(design, int(nseg), engine, ground)
        result["peak_rss_mb"] = (
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 / 1e6
        )
    except MemoryError:
        result = {"error": f"MemoryError: exceeded {mem_gb} GB", "error_kind": "mem"}
    except Exception as e:  # noqa: BLE001 — report, never crash the sweep
        result = {"error": f"{type(e).__name__}: {e}", "error_kind": "err"}
    print(json.dumps(result))


def run_one(design, nseg, engine, ground, timeout, mem_gb):
    try:
        proc = subprocess.run(
            [
                sys.executable,
                __file__,
                "--worker",
                design,
                str(nseg),
                engine,
                json.dumps(ground),
                str(mem_gb),
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 15,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timeout > {timeout:g}s", "error_kind": "timeout"}
    if proc.returncode != 0 and not proc.stdout.strip():
        kind = "mem" if proc.returncode in (-9, 137) else "err"
        tail = (proc.stderr or "").strip()[-160:]
        return {"error": f"worker exited {proc.returncode}: {tail}", "error_kind": kind}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"error": f"unparseable: {proc.stdout[-160:]!r}", "error_kind": "err"}


def _z0(res):
    """Driving-point impedance of the first port, or None on any failure."""
    if res.get("error") or not res.get("z"):
        return None
    r, x = res["z"][0]
    return complex(r, x)


def sweep_design(design, *, timeout, mem_gb):
    try:
        base = cvg.load_design(design)().nominal_nsegs
    except Exception as e:  # noqa: BLE001 — a design that will not construct
        return {"design": design, "load_error": f"{type(e).__name__}: {e}"}

    row = {"design": design, "base_nseg": base, "grounds": {}}
    for gname, gspec in GROUNDS.items():
        cells = {}
        for mult in MULTS:
            nseg = base * mult
            try:
                seg = cvg.total_nominal_segs(cvg.load_design(design), nseg)
            except Exception:  # noqa: BLE001 — fall back to solving and see
                seg = None
            if gname == "somm" and seg and seg > MAX_SEG_FINITE:
                cells[mult] = {
                    e: {
                        "error": f"skipped: seg {seg} > {MAX_SEG_FINITE}",
                        "error_kind": "skip",
                    }
                    for e in ENGINES
                }
                continue
            cells[mult] = {
                e: run_one(design, nseg, e, gspec, timeout, mem_gb) for e in ENGINES
            }
        row["grounds"][gname] = cells

        # Per-ground reference: the FINEST bspline-d2 mesh that actually
        # solved, not unconditionally 4x. A deck can qualify for the finite
        # ground at 1x and be guard-skipped at 4x (Sigma-seg grows with the
        # mesh), and scoring against a missing 4x threw away rows whose
        # coarser meshes were perfectly good. `ref_mult` is reported so a
        # reader knows how much headroom the reference has, and `self_move`
        # is its step from the next-coarser mesh -- the resolution bound on
        # every |dZ| scored against it.
        avail = [m for m in MULTS if _z0(cells.get(m, {}).get("bspline-d2", {}))]
        ref_mult = avail[-1] if avail else None
        ref = None if ref_mult is None else _z0(cells[ref_mult]["bspline-d2"])
        prev = [m for m in avail if m < ref_mult] if ref_mult else []
        ref_prev = _z0(cells[prev[-1]]["bspline-d2"]) if prev else None
        row.setdefault("ref", {})[gname] = {
            "z": None if ref is None else [ref.real, ref.imag],
            "mult": ref_mult,
            "self_move": None
            if (ref is None or ref_prev is None)
            else abs(ref - ref_prev),
        }
    return row


def _dz(cell, ref):
    z = _z0(cell)
    if z is None or ref is None:
        return None
    return abs(z - ref)


def _reference(cells):
    """Finest bspline-d2 mesh that actually solved, its step from the
    next-coarser one, and which mult it is. Derived here rather than read from
    the run's stored field so re-rendering a saved JSON uses the CURRENT rule."""
    avail = [m for m in MULTS if _z0(cells.get(m, {}).get("bspline-d2", {}))]
    ref_mult = avail[-1] if avail else None
    ref = None if ref_mult is None else _z0(cells[ref_mult]["bspline-d2"])
    prev = [m for m in avail if m < ref_mult] if ref_mult else []
    ref_prev = _z0(cells[prev[-1]]["bspline-d2"]) if prev else None
    return {
        "z": None if ref is None else [ref.real, ref.imag],
        "mult": ref_mult,
        "self_move": None if (ref is None or ref_prev is None) else abs(ref - ref_prev),
    }


def _cell_tag(cell, ref_mult, mult):
    """Why a cell has no number: a guard skip, a hard refusal, or a reference
    that is not finer than the mesh being scored. Printing one word for all
    three (it was "skip") hid a razor refusal behind a cost guard."""
    kind = cell.get("error_kind")
    if kind == "skip":
        return "  guard"
    if kind in ("err", "mem", "timeout"):
        return " REFUSE" if kind == "err" else f"  {kind[:5]}"
    if ref_mult is None or mult > ref_mult:
        return "  noref"
    return "unbound"  # reference solved, but its own residual is unbounded
    return "      -"


def print_report(rows):
    hdr = (
        f"{'design':40} {'grd':>4} {'seg1x':>6} "
        f"{'razor1x':>8} {'razor2x':>8} {'razor4x':>8} "
        f"{'bspl1x':>7} {'ref@':>4} {'refmv':>6} {'t_r1x':>7} {'t_b1x':>7}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        if r.get("load_error"):
            print(f"{r['design']:40} LOAD ERROR: {r['load_error']}")
            continue
        for gname, cells in r["grounds"].items():
            cells = {int(k): v for k, v in cells.items()}
            ref_i = _reference(cells)
            ref = None if ref_i["z"] is None else complex(*ref_i["z"])
            seg1 = cells[1]["bspline-d2"].get("total_nominal_segs") or cells[1][
                "razor-2p"
            ].get("total_nominal_segs")
            # Equal-mesh comparison against bspline-d2 is the RIGHT instrument
            # here and is what #845 uses: bspline is higher order, so at a mesh
            # where it has converged it stands in for the exact answer, and
            # razor@4x vs bspline@4x is a real measure of razor's error. What
            # makes a row unreportable is therefore not "the reference is not
            # finer" but "the reference's own residual is not small compared to
            # the number being quoted" -- bounded by `refmv`, its step from the
            # next-coarser mesh. With only ONE bspline mesh solved there is no
            # such bound at all, and those rows are marked rather than quoted.
            rm = ref_i.get("mult")
            mv = ref_i.get("self_move")
            vals, vals_raw = [], []
            for mult in MULTS:
                usable = rm is not None and mult <= rm and mv is not None
                d = _dz(cells[mult]["razor-2p"], ref) if usable else None
                vals_raw.append(d)
                vals.append(
                    _cell_tag(cells[mult]["razor-2p"], rm, mult)
                    if d is None
                    else f"{d:8.3f}"
                )
            b1 = _dz(cells[1]["bspline-d2"], ref) if (rm and rm > 1) else None
            mv = ref_i["self_move"]
            tr = cells[1]["razor-2p"].get("solve_s")
            tb = cells[1]["bspline-d2"].get("solve_s")
            # Guard the quantity this table exists to report: razor's |dZ| at
            # the shipped mesh. bspline's own 1x column is reference-limited BY
            # CONSTRUCTION -- bspline at 1x is already near bspline at 4x, so
            # its |dZ| is the same size as the reference's own residual -- and
            # flagging that would flag every row while saying nothing about
            # razor. It is printed for scale, not as a measurement.
            flag = ""
            r1 = vals_raw[0]
            if mv is not None and r1 is not None and r1 > 0 and mv > r1 / 3.0:
                flag = "  <-- ref cannot resolve razor1x"
            print(
                f"{r['design']:40} {gname:>4} {seg1 if seg1 else -1:>6} "
                f"{vals[0]:>8} {vals[1]:>8} {vals[2]:>8} "
                f"{'  n/a' if b1 is None else f'{b1:7.3f}'} "
                f"{('  n/a' if ref_i.get('mult') is None else str(ref_i['mult']) + 'x'):>4} "
                f"{'   n/a' if mv is None else f'{mv:6.3f}'} "
                f"{'    n/a' if tr is None else f'{tr:7.2f}'} "
                f"{'    n/a' if tb is None else f'{tb:7.2f}'}{flag}"
            )


def main(argv=None):
    if argv is None and len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker_main(*sys.argv[2:])
        return

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--design", action="append")
    ap.add_argument("--json", type=Path)
    ap.add_argument(
        "--report-only",
        type=Path,
        help="re-render the table from a saved --json run without solving",
    )
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ap.add_argument("--mem-gb", type=float, default=DEFAULT_MEM_GB)
    args = ap.parse_args(argv)

    if args.report_only:
        print_report(json.loads(args.report_only.read_text()))
        return

    from antennaknobs.cli import list_builtin_designs

    designs = args.design or [d for d in list_builtin_designs() if d not in BURIED]
    print(f"# {len(designs)} design(s); grounds {list(GROUNDS)}; mults {MULTS}")

    rows = []
    t0 = time.perf_counter()
    for i, d in enumerate(designs, 1):
        r = sweep_design(d, timeout=args.timeout, mem_gb=args.mem_gb)
        rows.append(r)
        print(
            f"[{i}/{len(designs)}] {d} done ({time.perf_counter() - t0:.0f}s)",
            flush=True,
        )
        if args.json:
            args.json.write_text(json.dumps(rows, indent=2))

    print()
    print_report(rows)
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
