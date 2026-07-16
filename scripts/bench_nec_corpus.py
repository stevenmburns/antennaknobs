"""Corpus benchmark: xnec2c `.nec` decks -> nec_import -> antennaknobs engines,
impedance vs. the canonical nec2c CLI run on the *original* deck.

For every deck in the xnec2c examples corpus this script:

  1. Parses the deck with ``antennaknobs.nec_import.parse_nec`` (per-wire specs).
  2. Runs the *original* deck through the ``nec2c`` CLI and reads the driving-
     point impedance from its first ANTENNA INPUT PARAMETERS block, at the
     frequency nec2c actually used (robust to sweep direction / FR start).
  3. Solves the translated geometry at that same frequency with four engines:
       pynec  — PyNECEngine
       sin    — MomwireEngine(SinusoidalSolver)
       bs1    — MomwireEngine(BSplineSolver, degree=1)   (tent basis)
       bs2    — MomwireEngine(BSplineSolver, degree=2)   (quadratic)
  4. Compares each engine's impedance to nec2c and records solve wall-time and
     peak RSS.

Ground matching (issue: nec_import discards GN -> only a bool). To keep the
comparison apples-to-apples, the GN/GD cards are parsed here and mapped to the
engine ``ground=`` spec both engines share:
    GN 1              -> "pec"
    GN 0 .. eps sig   -> ("finite-fast", eps, sig)   (NEC gn 0, refl-coef)
    GN 2 .. eps sig   -> ("finite", eps, sig)         (NEC gn 2, Sommerfeld)
    (no GN) / GN -1   -> "free"
A radial screen (nradl>0), a second medium (cliff), or a GD card can't be
represented by either engine; those decks still solve with the medium-1
ground (best effort) but are flagged ``unsupported-ground`` so their numbers
are read as not-apples-to-apples, not as engine error.

Concurrency mirrors the local web server (``web/server.py``): BLAS and OpenMP
thread pools are both pinned to the physical-core count via threadpoolctl at
runtime, with ``OMP_WAIT_POLICY=PASSIVE`` / ``GOMP_SPINCOUNT=0`` exported
before the numeric stack loads. Each solve runs in its own fresh subprocess so
peak RSS is clean and a solver crash on one deck can't take down the sweep;
subprocesses are dispatched serially (one solve at a time, all cores), exactly
as the server handles one request at a time.

Usage:
    python scripts/bench_nec_corpus.py                 # whole corpus
    python scripts/bench_nec_corpus.py --limit 5       # first 5 decks
    python scripts/bench_nec_corpus.py --decks 40m-moxon 20m_quad
    python scripts/bench_nec_corpus.py --engines pynec bs2
    python scripts/bench_nec_corpus.py --out results.json --timeout 300
"""

from __future__ import annotations

# --- concurrency policy: mirror web/server.py. libgomp reads these once at
#     load, before any Python runs, so they MUST be set before numpy/scipy/
#     PyNEC/momwire (which pull in libgomp) are imported. Fresh subprocesses
#     inherit this too, so worker solves get the same policy. ---
import os

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("GOMP_SPINCOUNT", "0")

import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import resource  # noqa: E402
import shutil  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

XNEC2C_EXAMPLES = Path.home() / "antennas" / "xnec2c" / "examples"
ENGINE_KEYS = ("pynec", "sin", "bs1", "bs2")
ENGINE_LABEL = {
    "pynec": "PyNEC",
    "sin": "Sinusoidal",
    "bs1": "BSpline d=1",
    "bs2": "BSpline d=2",
}


# --------------------------------------------------------------------------
# concurrency helpers (mirror web/server.py)
# --------------------------------------------------------------------------
def physical_cpu_count() -> int:
    """Physical cores (not HT siblings) — the server's thread-pool width."""
    try:
        import psutil

        n = psutil.cpu_count(logical=False)
        if n:
            return int(n)
    except Exception:
        pass
    return max(1, os.cpu_count() or 1)


def apply_server_thread_policy() -> int:
    """Pin BLAS + OpenMP pools to physical cores via threadpoolctl, exactly as
    web/server.py does at import time. Returns the core count used."""
    from threadpoolctl import threadpool_limits

    n = physical_cpu_count()
    # Persist for the process lifetime (not a context manager) — same as the
    # server, whose module-level call limits every subsequent solve.
    threadpool_limits(limits={"blas": n, "openmp": n})
    return n


# --------------------------------------------------------------------------
# ground parsing (GN/GD cards -> engine ground= spec)
# --------------------------------------------------------------------------
def load_deck(text: str, name: str):
    """Parse a deck with network translation on, so LD/TL/NT cards antennaknobs
    can express become ``Load``/``TL``/``TwoPort`` branches instead of being
    silently dropped (nec2c applies them, so ignoring them wrecks the impedance
    comparison — e.g. a TL-phased array or a network-matched feed).

    Returns ``(deck, network, ignored_net)`` where ``ignored_net`` is the list
    of LD/TL/NT cards that *couldn't* be expressed exactly (frequency-dependent
    reactance, complex-Y networks, distributed RLC): if non-empty the deck is
    only partially modelled and its comparison to nec2c is best-effort, not a
    clean engine-accuracy number. Falls back to geometry-only parsing if network
    translation itself raises."""
    from antennaknobs.nec_import import parse_nec

    try:
        deck = parse_nec(text, name=name, network=True)
        net = deck.network()
    except ValueError:
        deck = parse_nec(text, name=name, network=False)  # may re-raise -> caller
        net = None
    ignored_net = [
        (c, r) for c, r in deck.ignored_detail if c[:2] in ("LD", "TL", "NT")
    ]
    return deck, net, ignored_net


def parse_ground(deck_text: str):
    """Return ``(spec, supported, note)`` for the deck's ground.

    ``spec`` is the engine ground argument ("free" | "pec" |
    ("finite", eps, sig) | ("finite-fast", eps, sig)); ``supported`` is False
    when the true ground has a radial screen / second medium / GD card that
    neither engine can represent (spec is then the best-effort medium-1
    homogeneous ground); ``note`` explains a False.
    """
    gn = None
    has_gd = False
    for raw in deck_text.splitlines():
        toks = raw.replace(",", " ").split()
        if not toks:
            continue
        tag = toks[0].upper()
        if tag == "GN":
            gn = toks[1:]  # last GN wins
        elif tag == "GD":
            has_gd = True

    if gn is None:
        return ("free", True, "")

    def as_int(v):
        try:
            return int(float(v))
        except (ValueError, IndexError):
            return 0

    def as_float(i):
        try:
            return float(gn[i])
        except (ValueError, IndexError):
            return 0.0

    iperf = as_int(gn[0]) if gn else 0
    nradl = as_int(gn[1]) if len(gn) > 1 else 0
    eps = as_float(4)
    sig = as_float(5)
    # Fields past sig (second-medium dielectric/conductivity, cliff distance/
    # height) being non-zero means a two-medium ground.
    second_medium = any(abs(as_float(i)) > 0.0 for i in range(6, len(gn)))

    if iperf == -1:
        return ("free", True, "")
    if iperf == 1:
        spec = "pec"
    elif iperf == 0:
        spec = ("finite-fast", eps, sig)
    elif iperf == 2:
        spec = ("finite", eps, sig)
    else:
        return ("free", True, f"unknown IPERF={iperf}")

    reasons = []
    if nradl > 0:
        reasons.append(f"radial screen ({nradl})")
    if second_medium or has_gd:
        reasons.append("second medium / cliff")
    if reasons:
        return (spec, False, "; ".join(reasons))
    return (spec, True, "")


# --------------------------------------------------------------------------
# nec2c reference (run the ORIGINAL deck)
# --------------------------------------------------------------------------
_FREQ_RE = re.compile(r"FREQUENCY\s*:\s*([0-9.Ee+-]+)\s*MHz", re.IGNORECASE)


def run_nec2c(deck_path: Path, timeout: float):
    """Run the original deck through nec2c; return the first-frequency result:
    ``{"freq": MHz, "z": [[re, im], ...], "runtime_s": s, "error": str|None}``.
    Short temp paths sidestep nec2c's fixed filename buffer."""
    if shutil.which("nec2c") is None:
        return {"error": "nec2c not on PATH"}
    with tempfile.TemporaryDirectory(prefix="nec_") as d:
        nec = Path(d) / "d.nec"
        out = Path(d) / "d.out"
        nec.write_text(deck_path.read_text())
        t0 = time.perf_counter()
        # nec2c returns non-zero (255) both on a faulty card AND after a NaN
        # solve, and it writes its real diagnostics into the output FILE, not
        # stderr. So don't gate on the exit code — read the output and classify.
        try:
            subprocess.run(
                ["nec2c", "-i", str(nec), "-o", str(out)],
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"error": f"nec2c timeout >{timeout:.0f}s"}
        runtime = time.perf_counter() - t0
        if not out.exists():
            return {"error": "nec2c produced no output"}
        text = out.read_text()
        lines = text.splitlines()

    freq = None
    for i, ln in enumerate(lines):
        m = _FREQ_RE.search(ln)
        if m:
            freq = float(m.group(1))
        if "ANTENNA INPUT PARAMETERS" in ln:
            zs = []
            saw_nan = False
            j = i + 3  # header + units row, then data rows
            while j < len(lines) and lines[j].strip():
                toks = lines[j].split()
                if len(toks) >= 8:
                    try:
                        zre, zim = float(toks[6]), float(toks[7])
                    except ValueError:
                        zre = zim = float("nan")
                    # NB: float("-NAN") parses fine in Python, so an exception
                    # never fires for nec2c's diverged rows — test explicitly.
                    if math.isnan(zre) or math.isnan(zim) or math.isinf(zre):
                        saw_nan = True
                    else:
                        zs.append([zre, zim])
                j += 1
            if zs:
                return {"freq": freq, "z": zs, "runtime_s": runtime, "error": None}
            if saw_nan:
                return {"error": "nec2c solve returned NaN", "runtime_s": runtime}

    # No usable impedance block: surface nec2c's own diagnostic if it printed one.
    for key in ("FAULTY DATA CARD", "GEOMETRY DATA ERROR", "RUN ABORTED"):
        hit = next((ln.strip() for ln in lines if key in ln), None)
        if hit:
            return {"error": f"nec2c: {hit[:90]}", "runtime_s": runtime}
    return {"error": "no ANTENNA INPUT PARAMETERS block", "runtime_s": runtime}


# --------------------------------------------------------------------------
# worker: solve one (deck, engine) in a fresh subprocess, report JSON
# --------------------------------------------------------------------------
def worker_main(engine: str, deck_path: str, freq: float, ground_json: str):
    """Runs in a fresh interpreter. Prints one JSON line to stdout."""
    result = {"error": None}
    try:
        import psutil
        from types import MappingProxyType

        cores = apply_server_thread_policy()

        from antennaknobs import AntennaBuilder, WireSpec
        from antennaknobs.engines.pynec import PyNECEngine
        from antennaknobs.engines.momwire import MomwireEngine
        from momwire import BSplineSolver, SinusoidalSolver

        ground = json.loads(ground_json)
        if isinstance(ground, list):
            ground = tuple(ground)

        deck, net, _ignored = load_deck(
            Path(deck_path).read_text(), Path(deck_path).name
        )
        tups = deck.wire_tuples(specs=True)

        class DeckBuilder(AntennaBuilder):
            default_params = MappingProxyType({"freq": float(freq)})

            def build_wires(self):
                return tups

            def build_network(self):
                return net

            def build_wire_material(self):
                # Per-wire specs (specs=True) carry radius/conductivity; this is
                # only the fallback for any spec-less wire.
                return WireSpec(radius=deck.dominant_radius())

        builder = DeckBuilder()

        # Baseline resident memory after imports + parse, before the solve.
        base_rss = psutil.Process().memory_info().rss

        t0 = time.perf_counter()
        if engine == "pynec":
            eng = PyNECEngine(builder, ground=ground)
        elif engine == "sin":
            eng = MomwireEngine(builder, solver=SinusoidalSolver, ground=ground)
        elif engine == "bs1":
            eng = MomwireEngine(
                builder,
                solver=BSplineSolver,
                solver_kwargs={"degree": 1},
                ground=ground,
            )
        elif engine == "bs2":
            eng = MomwireEngine(
                builder,
                solver=BSplineSolver,
                solver_kwargs={"degree": 2},
                ground=ground,
            )
        else:
            raise ValueError(f"unknown engine {engine!r}")
        zs = eng.impedance()
        solve_s = time.perf_counter() - t0

        # ru_maxrss is the process-lifetime peak (KiB on Linux).
        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024

        result.update(
            z=[[float(z.real), float(z.imag)] for z in zs],
            solve_s=solve_s,
            base_rss_mb=base_rss / 1e6,
            peak_rss_mb=peak_rss / 1e6,
            cores=cores,
            n_wires=len(tups),
        )
    except Exception as e:  # noqa: BLE001 — report, never crash the sweep
        import traceback

        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()[-800:]
    print(json.dumps(result))


def run_engine(engine, deck_path, freq, ground, timeout):
    """Dispatch a worker subprocess for one (deck, engine); parse its JSON."""
    proc = subprocess.run(
        [
            sys.executable,
            __file__,
            "--worker",
            engine,
            str(deck_path),
            repr(float(freq)),
            json.dumps(ground),
        ],
        capture_output=True,
        text=True,
        timeout=None if timeout is None else timeout + 15,
    )
    if proc.returncode != 0 and not proc.stdout.strip():
        tail = (proc.stderr or "").strip()[-200:]
        return {"error": f"worker exited {proc.returncode}: {tail}"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"error": f"unparseable worker output: {proc.stdout[-200:]!r}"}


# --------------------------------------------------------------------------
# comparison + reporting
# --------------------------------------------------------------------------
def _z(pair):
    return complex(pair[0], pair[1])


def compare(engine_z, ref_z):
    """Per-feed |Δ| and rel-% between engine and nec2c, aligned by index."""
    out = []
    for i in range(min(len(engine_z), len(ref_z))):
        ze, zr = _z(engine_z[i]), _z(ref_z[i])
        dabs = abs(ze - zr)
        drel = dabs / abs(zr) if abs(zr) > 0 else float("inf")
        out.append({"engine": [ze.real, ze.imag], "abs": dabs, "rel": drel})
    return out


def bench_deck(deck_path: Path, engines, timeout, run_with_ground=True):
    name = deck_path.stem
    row = {"deck": name, "error": None}
    text = deck_path.read_text()
    try:
        deck, _net, ignored_net = load_deck(text, deck_path.name)
    except Exception as e:  # noqa: BLE001
        row["error"] = f"parse: {type(e).__name__}: {e}"
        return row

    ground, supported, note = parse_ground(text)
    row.update(
        n_feeds=len(deck.feeds),
        ground=(
            "free"
            if ground == "free"
            else ground
            if isinstance(ground, str)
            else ground[0]
        ),
        ground_supported=supported,
        ground_note=note,
        partial_net=bool(ignored_net),
        partial_net_detail=[c for c, _ in ignored_net][:4],
    )

    ref = run_nec2c(deck_path, timeout)
    row["nec2c"] = ref
    if ref.get("error"):
        return row
    freq = ref["freq"]
    row["freq"] = freq

    eng_ground = ground if run_with_ground else "free"
    row["engines"] = {}
    for e in engines:
        res = run_engine(e, deck_path, freq, eng_ground, timeout)
        if res.get("error") is None and "z" in res:
            res["cmp"] = compare(res["z"], ref["z"])
        row["engines"][e] = res
    return row


def fmt_rel(res):
    if res is None or res.get("error"):
        return "ERR"
    cmp = res.get("cmp") or []
    if not cmp:
        return "n/a"
    r = cmp[0]["rel"]  # feed 0
    return f"{100 * r:6.1f}%" if r != float("inf") else "  inf"


def print_report(rows, engines):
    ok = [r for r in rows if not r.get("error") and not r.get("nec2c", {}).get("error")]

    print("\n" + "=" * 104)
    print("IMPEDANCE vs nec2c  (feed 0; rel = |Z_eng - Z_nec2c| / |Z_nec2c|)")
    print(
        "  flags: g = unsupported ground (radials/cliff), n = inexpressible LD/TL/NT network"
    )
    print("=" * 104)
    hdr = (
        f"{'deck':<34} {'f/MHz':>8} {'grd':>5} {'fl':>3} {'Z_nec2c (feed0)':>19}  "
        + " ".join(f"{ENGINE_LABEL[e]:>11}" for e in engines)
    )
    print(hdr)
    print("-" * len(hdr))
    for r in ok:
        z0 = _z(r["nec2c"]["z"][0])
        flags = ("g" if not r.get("ground_supported", True) else "") + (
            "n" if r.get("partial_net") else ""
        )
        cells = " ".join(f"{fmt_rel(r['engines'].get(e)):>11}" for e in engines)
        print(
            f"{r['deck']:<34} {r.get('freq', 0):>8.3f} {r.get('ground') or 'free':>5} "
            f"{flags:>3} {z0.real:>8.1f}{z0.imag:>+8.1f}j  {cells}"
        )

    # runtime + RSS summary per engine (over solves that succeeded)
    print("\n" + "=" * 72)
    print("RUNTIME & PEAK RSS per engine  (successful solves only)")
    print("=" * 72)
    print(
        f"{'engine':<12} {'n':>4} {'solve_s median':>15} {'max':>8} "
        f"{'peakRSS med':>12} {'max':>8}"
    )
    print("-" * 72)
    for e in engines:
        st = [r["engines"][e] for r in ok if not r["engines"].get(e, {}).get("error")]
        n = len(st)
        if not n:
            print(f"{ENGINE_LABEL[e]:<12} {0:>4}   (all failed)")
            continue
        solves = [s["solve_s"] for s in st]
        rss = [s["peak_rss_mb"] for s in st]
        print(
            f"{ENGINE_LABEL[e]:<12} {n:>4} {statistics.median(solves):>13.3f}s "
            f"{max(solves):>7.2f}s {statistics.median(rss):>10.0f}MB {max(rss):>6.0f}MB"
        )

    # rollups
    print("\n" + "=" * 72)
    print(
        "AGREEMENT ROLLUP  (feed-0 rel error; clean decks: supported ground, "
        "fully-expressed network)"
    )
    print("=" * 72)
    for e in engines:
        rels = [
            r["engines"][e]["cmp"][0]["rel"]
            for r in ok
            if r.get("ground_supported", True)
            and not r.get("partial_net")
            and not r["engines"].get(e, {}).get("error")
            and (r["engines"][e].get("cmp"))
            and r["engines"][e]["cmp"][0]["rel"] != float("inf")
        ]
        if not rels:
            print(f"{ENGINE_LABEL[e]:<12} no data")
            continue
        rels.sort()
        within = lambda t: sum(1 for x in rels if x <= t)  # noqa: E731
        print(
            f"{ENGINE_LABEL[e]:<12} n={len(rels):>3}  median={100 * statistics.median(rels):5.1f}%  "
            f"<1%:{within(0.01):>3}  <5%:{within(0.05):>3}  <20%:{within(0.20):>3}"
        )

    # failures
    errs = [r for r in rows if r.get("error") or r.get("nec2c", {}).get("error")]
    if errs:
        print("\n" + "=" * 72)
        print(f"SKIPPED / FAILED DECKS ({len(errs)})")
        print("=" * 72)
        for r in errs:
            why = r.get("error") or r["nec2c"].get("error")
            print(f"  {r['deck']:<40} {why}")


# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--worker",
        nargs=4,
        metavar=("ENGINE", "DECK", "FREQ", "GROUND"),
        help=argparse.SUPPRESS,
    )
    ap.add_argument("--corpus", type=Path, default=XNEC2C_EXAMPLES)
    ap.add_argument(
        "--engines", nargs="+", default=list(ENGINE_KEYS), choices=ENGINE_KEYS
    )
    ap.add_argument(
        "--decks",
        nargs="+",
        default=None,
        help="deck stem(s) or filename(s) to restrict to",
    )
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--timeout",
        type=float,
        default=240.0,
        help="per-solve / per-nec2c wall-clock cap (s)",
    )
    ap.add_argument(
        "--free-space",
        action="store_true",
        help="run engines free-space regardless of the deck's GN",
    )
    ap.add_argument(
        "--out", type=Path, default=None, help="write full results JSON here"
    )
    args = ap.parse_args(argv)

    if args.worker:
        engine, deck, freq, ground = args.worker
        worker_main(engine, deck, float(freq), ground)
        return

    corpus = args.corpus
    if not corpus.is_dir():
        sys.exit(f"corpus not found: {corpus}")
    decks = sorted(corpus.glob("*.nec"))
    if args.decks:
        want = {d.replace(".nec", "") for d in args.decks}
        decks = [p for p in decks if p.stem in want or p.name in args.decks]
    if args.limit:
        decks = decks[: args.limit]
    if not decks:
        sys.exit("no decks selected")

    cores = physical_cpu_count()
    print(f"corpus: {corpus}")
    print(f"decks: {len(decks)}   engines: {', '.join(args.engines)}")
    print(
        f"concurrency (mirrors web/server.py): BLAS={cores} OpenMP={cores} "
        f"OMP_WAIT_POLICY={os.environ['OMP_WAIT_POLICY']} "
        f"GOMP_SPINCOUNT={os.environ['GOMP_SPINCOUNT']}   (serial dispatch)"
    )
    if shutil.which("nec2c") is None:
        sys.exit("nec2c not on PATH — build it and symlink into ~/.local/bin")

    rows = []
    for i, deck in enumerate(decks, 1):
        print(f"[{i}/{len(decks)}] {deck.stem} ...", flush=True)
        rows.append(
            bench_deck(
                deck, args.engines, args.timeout, run_with_ground=not args.free_space
            )
        )

    print_report(rows, args.engines)

    if args.out:
        args.out.write_text(json.dumps(rows, indent=2))
        print(f"\nfull results -> {args.out}")


if __name__ == "__main__":
    main()
