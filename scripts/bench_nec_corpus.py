"""Corpus benchmark: xnec2c `.nec` decks -> nec_import -> antennaknobs engines,
impedance vs. the canonical nec2c CLI run on the *original* deck.

For every deck in the xnec2c examples corpus this script:

  1. Parses the deck with ``antennaknobs.nec_import.parse_nec`` (per-wire specs).
  2. Runs the *original* deck through the ``nec2c`` CLI and reads the driving-
     point impedance from its first ANTENNA INPUT PARAMETERS block, at the
     frequency nec2c actually used (robust to sweep direction / FR start).
  3. Solves the translated geometry at that same frequency with the engines
     selected by --engines:
       pynec  — PyNECEngine
       sin    — MomwireEngine(SinusoidalSolver)
       bs1    — MomwireEngine(BSplineSolver, degree=1)   (tent basis)
       bs2    — MomwireEngine(BSplineSolver, degree=2)   (quadratic)
       nec5   — NEC5Engine (opt-in, #872 phase 0): needs $NEC5_EXE; decks
                asking for dialect the engine deliberately refuses (TL/NT,
                ql/qc loads, distributed ports, buried/in-plane wires,
                refl-coef ground) are counted OOS (out-of-scope), not as
                failures, and printouts are captured-and-cached by deck
                content hash under --nec5-capture-dir so re-analysis never
                re-solves.
  4. Scores each engine against nec2c by reflection-coefficient distance
     ΔΓ = |Γ_eng − Γ_nec2c| with Γ = (Z − 50)/(Z + 50), and records solve
     wall-time and peak RSS. ΔΓ is bounded on [0, 2], so decks whose |Z| passes
     near a zero/pole (near-open / near-short) stay comparable instead of
     blowing a relative-|Z| ratio up to 100s of % (issue #407). The raw complex
     impedances remain in the JSON, so relative-|Z| is still derivable.

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

Wild-corpus sweeps (issue #410) additionally want hard resource bounds and
restartability:
    python scripts/bench_nec_corpus.py --corpus ~/antennas/nec-wild \\
        --timeout 300 --mem-limit-gb 8 --out wild.jsonl
--mem-limit-gb applies RLIMIT_AS to every solve subprocess AND the nec2c
reference run, so one pathological deck can't OOM the machine. A ``.jsonl``
--out is written incrementally (one row per line as each deck finishes) and
is a resume point: re-running with the same --out skips decks already done.
Solve mode content-dedupes the corpus by md5 exactly like --parse-only.
"""

from __future__ import annotations

# --- concurrency policy: mirror web/server.py. libgomp reads these once at
#     load, before any Python runs, so they MUST be set before numpy/scipy/
#     PyNEC/momwire (which pull in libgomp) are imported. Fresh subprocesses
#     inherit this too, so worker solves get the same policy. ---
import os

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("GOMP_SPINCOUNT", "0")

import argparse
import json
import math
import re
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

XNEC2C_EXAMPLES = Path.home() / "antennas" / "xnec2c" / "examples"
Z0 = 50.0  # system impedance for the reflection-coefficient metric (issue #407)
# Every engine key the benchmark scripts can dispatch. "sing" (momwire#182)
# is the SAME three-term basis as "sin" tested variationally instead of
# point-matched, so the pair isolates the TESTING scheme with the basis held
# fixed — that is what it is here for. "nec5" (#872 phase 0) drives the
# licensed NEC-5 binary through NEC5Engine and needs $NEC5_EXE resolved.
ENGINE_KEYS = ("pynec", "sin", "sing", "bs1", "bs2", "nec5")
ENGINE_LABEL = {
    "pynec": "PyNEC",
    "sin": "Sinusoidal",
    "sing": "Sinusoidal-Gal",
    "bs1": "BSpline d=1",
    "bs2": "BSpline d=2",
    "nec5": "NEC-5",
}
# What `--engines` defaults to. Deliberately NOT all of ENGINE_KEYS: the
# corpus/catalog sweeps are long-running, and silently adding a fifth column
# to every historical benchmark would change what those runs cost and mean.
# Ask for "sing" or "nec5" explicitly.
DEFAULT_ENGINE_KEYS = ("pynec", "sin", "bs1", "bs2")


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


def _rlimit_preexec(mem_bytes: int):
    """preexec_fn capping a child's virtual address space (RLIMIT_AS — the
    same bound as ``ulimit -v``). Allocation past the cap raises MemoryError
    in Python workers / fails malloc in nec2c instead of OOMing the host."""

    def fn():
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

    return fn


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
    elif iperf == 3:
        # 4nec2/EZNEC "MiniNec-style" ground (70 wild decks): currents and
        # impedance are solved over a PERFECT ground; the eps/sig on the
        # card only shape the far field. For the impedance comparison the
        # faithful mapping is therefore pec — and nec2c happens to agree
        # bit-for-bit, landing type 3 in its perfect-ground branch
        # (verified on TopCap75: GN 3 and GN 1 give identical Z, while the
        # old "free" mapping made the deck a fake dG=1.59 outlier).
        spec = "pec"
    else:
        # Genuinely unknown type: solve free-space but FLAG it — silently
        # counting it as clean made mis-scored decks look like engine error.
        return ("free", False, f"unknown IPERF={iperf}")

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


def run_nec2c(
    deck_path: Path,
    timeout: float,
    mem_bytes: int | None = None,
    deck_text: str | None = None,
):
    """Run the original deck through nec2c; return the first-frequency result:
    ``{"freq": MHz, "z": [[re, im], ...], "runtime_s": s, "error": str|None}``.
    Short temp paths sidestep nec2c's fixed filename buffer. ``deck_text``
    substitutes prepared text (the resolved-reference retry, issue #439) for
    the file's own bytes."""
    if shutil.which("nec2c") is None:
        return {"error": "nec2c not on PATH"}
    with tempfile.TemporaryDirectory(prefix="nec_") as d:
        nec = Path(d) / "d.nec"
        out = Path(d) / "d.out"
        if deck_text is None:
            nec.write_bytes(deck_path.read_bytes())
        else:
            nec.write_text(deck_text)
        t0 = time.perf_counter()
        # nec2c returns non-zero (255) both on a faulty card AND after a NaN
        # solve, and it writes its real diagnostics into the output FILE, not
        # stderr. So don't gate on the exit code — read the output and classify.
        try:
            proc = subprocess.run(
                ["nec2c", "-i", str(nec), "-o", str(out)],
                capture_output=True,
                timeout=timeout,
                preexec_fn=_rlimit_preexec(mem_bytes) if mem_bytes else None,
            )
        except subprocess.TimeoutExpired:
            return {"error": f"nec2c timeout >{timeout:.0f}s"}
        runtime = time.perf_counter() - t0
        if not out.exists():
            tail = (proc.stderr or b"").decode(errors="replace").strip()[-120:]
            return {"error": f"nec2c produced no output (rc={proc.returncode}) {tail}"}
        # errors="replace": nec2c can emit raw non-UTF-8 bytes into its own
        # output on some wild decks (seen: 0xff mid-file) — a garbled char in
        # a diagnostic must not kill the sweep.
        text = out.read_text(errors="replace")
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
        from antennaknobs.engines.momwire import MomwireEngine
        from antennaknobs.network import as_wire
        from momwire import BSplineSolver, SinusoidalSolver

        ground = json.loads(ground_json)
        if isinstance(ground, list):
            ground = tuple(ground)

        deck, net, _ignored = load_deck(
            Path(deck_path).read_text(errors="replace"), Path(deck_path).name
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

        # Opt-in (issue #409): disable nec2++'s wire/segment intersection
        # validator so decks with closely-spaced / crossing wires that NEC-2
        # and momwire accept aren't rejected. Env-passed to keep the --worker
        # argv arity fixed at 4.
        allow_intersections = os.environ.get("PYNEC_ALLOW_INTERSECTIONS") == "1"

        t0 = time.perf_counter()
        if engine == "pynec":
            # Imported per-branch so the nec5 lane runs without PyNEC
            # installed (the nec5 study boxes need only the licensed binary).
            from antennaknobs.engines.pynec import PyNECEngine

            eng = PyNECEngine(
                builder,
                ground=ground,
                check_intersections=not allow_intersections,
                # Deck asked for NEC's extended thin-wire kernel (EK):
                # honour it so fat-wire decks compare kernel-for-kernel
                # against nec2c, which applies EK (#414).
                extended_thin_wire_kernel=deck.extended_kernel,
            )
        elif engine == "sin":
            eng = MomwireEngine(
                builder,
                solver=SinusoidalSolver,
                ground=ground,
                # Honour the deck's EK card kernel-for-kernel against nec2c
                # (#414 gave pynec this; momwire grew the opt-in in #849 and
                # serves it end to end — Sommerfeld included — since 0.27.0).
                extended_kernel=deck.extended_kernel,
            )
        elif engine == "sing":
            from momwire import SinusoidalGalerkinSolver

            eng = MomwireEngine(
                builder,
                solver=SinusoidalGalerkinSolver,
                ground=ground,
                extended_kernel=deck.extended_kernel,
            )
        elif engine == "bs1":
            eng = MomwireEngine(
                builder,
                solver=BSplineSolver,
                solver_kwargs={"degree": 1},
                ground=ground,
                extended_kernel=deck.extended_kernel,
            )
        elif engine == "bs2":
            eng = MomwireEngine(
                builder,
                solver=BSplineSolver,
                solver_kwargs={"degree": 2},
                ground=ground,
                extended_kernel=deck.extended_kernel,
            )
        elif engine == "nec5":
            from antennaknobs.engines.nec5 import NEC5Engine

            # Env-passed like PYNEC_ALLOW_INTERSECTIONS to keep the --worker
            # argv arity fixed at 4. The capture dir gives the sweep the
            # phase-0 printout cache (#872): a deck already captured is
            # served from disk, so re-analysis never re-solves.
            eng = NEC5Engine(
                builder,
                ground=ground,
                timeout=float(os.environ.get("NEC5_BENCH_TIMEOUT") or 120.0),
                capture_dir=os.environ.get("NEC5_CAPTURE_DIR") or None,
            )
        else:
            raise ValueError(f"unknown engine {engine!r}")
        zs = eng.impedance()
        solve_s = time.perf_counter() - t0
        if engine == "nec5":
            # Census-grade NEC-5 rows are Richardson (N, 2N) pairs (#872
            # phase 2: knot-source march, order ~1 — measured 0.54-1.74
            # across the stratified sample; phase 3a validated the same
            # recipe over Sommerfeld ground). Solve the deck again at
            # doubled mesh and report the pair extrapolation as the row's
            # z; the native and doubled reads stay in the JSON. Opt out
            # with NEC5_PAIR=0 (then z is the deck-native single read).
            if os.environ.get("NEC5_PAIR", "1") != "0":
                doubled = [w._replace(n_seg=2 * w.n_seg) for w in map(as_wire, tups)]

                class DoubledBuilder(DeckBuilder):
                    def build_wires(self):
                        return doubled

                eng2 = NEC5Engine(
                    DoubledBuilder(),
                    ground=ground,
                    timeout=float(os.environ.get("NEC5_BENCH_TIMEOUT") or 120.0),
                    capture_dir=os.environ.get("NEC5_CAPTURE_DIR") or None,
                )
                zs2 = eng2.impedance()
                solve_s = time.perf_counter() - t0
                result["nec5_z_native"] = [[z.real, z.imag] for z in zs]
                result["nec5_z_doubled"] = [[z.real, z.imag] for z in zs2]
                zs = [2 * z2 - z1 for z1, z2 in zip(zs, zs2)]
                result["nec5_pair"] = True
                eng.run_log.extend(eng2.run_log)
            result["nec5_runs"] = eng.run_log

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
        if engine == "nec5" and nec5_out_of_scope(e):
            result["out_of_scope"] = True
    print(json.dumps(result))


# NEC5Engine refusal messages that mean "the deck asks for something the
# stage-1..5 dialect deliberately does not serve" (#872 phase 0): the census
# counts these as out-of-scope, not engine failures. NotImplementedError is
# the engine's designed refusal channel (TL/NT branches, distributed or
# virtual ports, finite-fast ground, buried wires); the two ValueError
# messages are hard NEC-5 dialect rules the engine enforces at construction.
_NEC5_SCOPE_VALUEERROR_SNIPPETS = (
    "lies in the ground plane (z=0)",
    "too close to free space for NEC-5's Sommerfeld tables",
)


def nec5_out_of_scope(e: BaseException) -> bool:
    """True when a nec5-lane exception is a dialect-scope refusal rather
    than a solve failure."""
    if isinstance(e, NotImplementedError):
        return True
    return isinstance(e, ValueError) and any(
        s in str(e) for s in _NEC5_SCOPE_VALUEERROR_SNIPPETS
    )


def run_engine(
    engine,
    deck_path,
    freq,
    ground,
    timeout,
    allow_intersections=False,
    mem_bytes=None,
    nec5_capture_dir=None,
):
    """Dispatch a worker subprocess for one (deck, engine); parse its JSON."""
    env = dict(os.environ)
    if allow_intersections:
        env["PYNEC_ALLOW_INTERSECTIONS"] = "1"
    if engine == "nec5":
        # Env-passed to keep the --worker argv arity fixed at 4.
        if nec5_capture_dir:
            env["NEC5_CAPTURE_DIR"] = str(nec5_capture_dir)
        if timeout is not None:
            env["NEC5_BENCH_TIMEOUT"] = repr(float(timeout))
    try:
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
            env=env,
            preexec_fn=_rlimit_preexec(mem_bytes) if mem_bytes else None,
        )
    except subprocess.TimeoutExpired:
        # Wild decks WILL hit the wall-clock cap; that is a result, not a
        # sweep-stopper (the pre-#410 code let this propagate and killed
        # the whole run on the first slow deck).
        return {"error": f"solve timeout >{timeout:.0f}s"}
    if proc.returncode != 0 and not proc.stdout.strip():
        tail = (proc.stderr or "").strip()[-200:]
        note = (
            " (mem-limit set, likely OOM abort)"
            if mem_bytes and proc.returncode < 0
            else ""
        )
        return {"error": f"worker exited {proc.returncode}{note}: {tail}"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"error": f"unparseable worker output: {proc.stdout[-200:]!r}"}


# --------------------------------------------------------------------------
# engine-error classification (issue #409)
# --------------------------------------------------------------------------
# nec2++ (the PyNEC kernel) runs a geometry validator in geometry_complete() /
# geo.wire() that the NEC-2 Fortran kernel and its faithful C port nec2c only
# *warn* about: it fatally rejects a deck whose wires pass within a
# radius-sum of each other, either crossing (WIRE #X INTERSECTS WIRE #Y) or
# meeting at a junction where a short segment's midpoint lands inside the
# connecting wire (FIRST SEGMENT MIDPOINT OF WIRE #X INTERSECTS WIRE #Y). The
# translated geometry is sound — nec2c and all three momwire solvers accept the
# same wires — so these are a genuine kernel-wrapper limitation, not a
# translation/wrapper bug. Classify them as `geo` so the report distinguishes
# "engine rejected the geometry" from an actual solve crash.
_GEO_REJECT_RE = re.compile(r"GEOMETRY DATA ERROR|INTERSECTS WIRE", re.IGNORECASE)
# RLIMIT_AS trips surface as MemoryError / numpy "Unable to allocate" in the
# worker, OpenBLAS's "Memory allocation still failed" (exits 1 before Python
# can catch anything), std::bad_alloc out of the C++ kernels, or (rarely) an
# abort/SIGSEGV when C code doesn't check malloc — a negative returncode with
# the limit on.
_MEM_RE = re.compile(
    r"MemoryError|bad_alloc|Unable to allocate|Cannot allocate|Out of memory"
    r"|Memory allocation|likely OOM abort",
    re.IGNORECASE,
)
_TIMEOUT_RE = re.compile(r"solve timeout")


def engine_error_kind(res):
    """Classify an engine result's error: ``None`` (no error), ``"geo"``
    (nec2++ geometry-intersection rejection — documented kernel limitation,
    issue #409), ``"scope"`` (outside the engine's served dialect — the
    nec5 lane's designed refusals, #872 phase 0), ``"mem"`` (hit the
    --mem-limit-gb cap), ``"timeout"`` (hit the --timeout wall-clock cap),
    or ``"err"`` (any other failure)."""
    if res is None:
        return "err"
    if res.get("out_of_scope"):
        return "scope"
    err = res.get("error")
    if not err:
        return None
    if _GEO_REJECT_RE.search(err):
        return "geo"
    if _TIMEOUT_RE.search(err):
        return "timeout"
    if _MEM_RE.search(err):
        return "mem"
    return "err"


# --------------------------------------------------------------------------
# comparison + reporting
# --------------------------------------------------------------------------
def _z(pair):
    return complex(pair[0], pair[1])


def _gamma(z):
    """Reflection coefficient Γ = (Z − Z₀)/(Z + Z₀) at the system impedance Z₀.
    For any passive antenna R ≥ 0 so Z + Z₀ has real part ≥ Z₀ > 0 — never
    singular — and |Γ| ≤ 1, so the |Γ_eng − Γ_ref| distance is bounded on
    [0, 2]. That is why it replaces relative-|Z| error (issue #407): a
    near-open/near-short deck lands both engines at |Γ| ≈ 1 and the distance
    measures only the (small) phase disagreement, instead of a tiny absolute
    shift near a zero/pole of Z blowing the ratio up to 100s of %."""
    return (z - Z0) / (z + Z0)


def compare(engine_z, ref_z):
    """Per-feed reflection-coefficient distance ``dgamma`` = |Γ_eng − Γ_ref|
    (Z₀ = 50 Ω) and the raw |ΔZ| ``abs``, aligned by index. The complex
    impedances stay in the JSON (``engine`` here, ``nec2c.z`` on the row), so
    the old relative-|Z| metric remains derivable."""
    out = []
    for i in range(min(len(engine_z), len(ref_z))):
        ze, zr = _z(engine_z[i]), _z(ref_z[i])
        out.append(
            {
                "engine": [ze.real, ze.imag],
                "abs": abs(ze - zr),
                "dgamma": abs(_gamma(ze) - _gamma(zr)),
            }
        )
    return out


# Series resistance for the EX 6 current-source emulation (issue #442):
# EX 6 becomes EX 0 with V = I·R_BIG behind an LD 4 series R_BIG, and the
# bench subtracts R_BIG back out of nec2c's reported impedance. The value
# balances the two error terms: forcing error ~ |Z_gap|/R_BIG against
# recovery error ~ R_BIG·1e-5 from nec2c's 5-significant-digit print.
EX6_R_BIG = 2.0e4


# Program-control cards that configure a NEC-2 run (as opposed to
# requesting execution). In batch NEC-2 these take effect at the NEXT
# XQ/RP execute request — so any that appear after the deck's LAST
# execute request are dead cards. Whole-deck GUI parsers (xnec2c, 4nec2,
# our importer) apply them regardless of position (issue #449).
#
# KH is deliberately NOT here: it's the one program-control card our
# evaluator ignores outright (NecDeck.ignored), so hoisting it can only
# make the reference diverge — and a trailing `KH 0` (xnec2c writes one)
# would set nec2c's interaction-approximation range to zero and wreck
# the solve (barry.nec: 2.81+71.9j → 0.0+43.5j). Left in place it stays
# dead on both sides.
_RUN_CONFIG_CARDS = frozenset(("LD", "TL", "NT", "GN", "GD", "EX", "FR", "EK"))


def dead_trailing_config(mnemonics) -> list[int]:
    """Indexes of run-config cards after the last XQ/RP execute request.

    ``mnemonics`` is the deck's card-mnemonic sequence (upper-case, one
    per card line). Nonempty result = the deck's batch-NEC-2 run differs
    from its whole-deck-parser intent (issue #449): nec2c executed before
    reading those cards, so its output silently lacks them — the zepp-80m
    'TL translation artifact' was exactly this, a reference that solved a
    disconnected feeder stub with no ground.
    """
    execs = [i for i, m in enumerate(mnemonics) if m in ("XQ", "RP")]
    if not execs:
        return []
    return [
        i
        for i in range(execs[-1] + 1, len(mnemonics))
        if mnemonics[i] in _RUN_CONFIG_CARDS
    ]


def has_dead_trailing_config(text: str) -> bool:
    """Raw-text variant of ``dead_trailing_config`` for gating the
    original-deck reference run (tolerant of the 4nec2 dialect: only
    plausible two-letter mnemonics count, stops at EN)."""
    mnems = []
    for ln in text.splitlines():
        s = ln.strip()
        m = s[:2].upper()
        if len(s) >= 2 and m.isalpha():
            mnems.append(m)
            if m == "EN":
                break
    return bool(dead_trailing_config(mnems))


def reference_deck(text: str, name: str, ex6: str = "rbig") -> str:
    """Deck text prepared for the nec2c *reference* run (issue #439).

    ``resolve_sy`` materializes the 4nec2 dialect nec2c cannot read (SY
    symbols, ``'`` comments, ``#AWG`` gauges, fused mnemonics). On top of
    that, run-request and excitation quirks vanilla nec2c cannot handle:

    - an ``FR`` card with NFRQ = 0 gets the NEC-2 spec's "one assumed"
      default (``parse_nec`` applies the same normalization);
    - a deck with no ``XQ``/``RP`` execute request gets an ``XQ`` appended
      before ``EN``, otherwise nec2c parses everything and computes nothing
      ("no ANTENNA INPUT PARAMETERS block");
    - an ``EX 6`` current source (issue #442; nec2c misparses type 6 as a
      plane wave) becomes the classic emulation — ``EX 0`` with
      V = I·``EX6_R_BIG`` behind an ``LD 4`` series ``EX6_R_BIG`` on the
      driven segment. The caller must subtract ``EX6_R_BIG`` from nec2c's
      reported impedance at that feed (``bench_deck`` does);
    - an ``LD 6`` LC-trap (issue #444; 4nec2 dialect, nec2c aborts with
      IMPROPER LOAD TYPE) becomes the parallel RLC 4nec2 itself converts
      it to: ``LD 1 tag sf st R_p L C`` with R_p = Q·ωL at the initial
      FR card's frequency (F1 is the coil's unloaded Q, 0 → 100). Same
      conversion as ``nec_import``'s, so engines and reference agree on
      the physics;
    - an ``LD 7`` insulated-wire load (issue #447; 4nec2 dialect, nec2c
      aborts too — F1 = jacket εr, F2 = jacket outer radius in metres)
      becomes the ``LD 2`` distributed-series-L′ emulation PR #326
      validated against the WireSpec insulation model (~1% vf oracle):
      L′ = ``insulation_inductance(a, b, εr)`` per covered tag, with the
      conductor radius ``a`` taken from the parsed deck's wires (so GS
      scaling and geometry transforms are honoured). A whole-structure
      card expands to one ``LD 2`` per tag (radii differ per tag); a
      jacket that doesn't clear its conductor is dropped — the importer
      leaves that wire bare too;
    - run-config cards after the deck's LAST execute request (issue #449
      — dead in batch NEC-2, which executes at XQ/RP before reading
      them) are hoisted to just before the FIRST execute request, so the
      reference solves the configuration the deck's whole-deck-parser
      author intended (xnec2c saves TL/GN after RP; 31 wild decks carry
      a trailing GN alone — their unhoisted references silently ran
      free space).

    Raises ``ValueError`` like ``resolve_sy`` on undecipherable decks.
    """
    from antennaknobs.nec_import import parse_nec, resolve_sy
    from momwire import insulation_inductance

    lines = resolve_sy(text, name=name).splitlines()
    dead = dead_trailing_config([ln.split()[0] for ln in lines])
    if dead:
        hoisted = [lines[i] for i in dead]
        lines = [ln for i, ln in enumerate(lines) if i not in set(dead)]
        first = next(i for i, ln in enumerate(lines) if ln.split()[0] in ("XQ", "RP"))
        lines[first:first] = hoisted
    # 4nec2 evaluates LD 6 trap loss at the INITIAL FR card's F1 (issue
    # #444) — which may appear after the LD card, so pre-scan for it.
    fr_first_mhz = 299.8  # NEC's no-FR default
    for ln in lines:
        toks = ln.split()
        if toks[0] == "FR" and len(toks) > 5:
            try:
                fr_first_mhz = float(toks[5]) or fr_first_mhz
            except ValueError:
                pass
            break
    tag_radius: dict[int, float] | None = None

    def tag_radii() -> dict[int, float]:
        """NEC tag → conductor radius, computed lazily on the first LD 7.
        Preferred source is the fully parsed deck (post-GS/transform radii);
        a deck ``parse_nec`` refuses falls back to a raw GW-card scan."""
        nonlocal tag_radius
        if tag_radius is not None:
            return tag_radius
        tag_radius = {}
        try:
            # network=True so EX 6 current-source decks parse too (the
            # default mode refuses them; issue #442).
            wires = parse_nec(text, name=name, network=True).wires
            found = ((w.tag, w.radius) for w in wires)
        except Exception:  # noqa: BLE001 — fall back to the textual scan
            found = (
                (int(float(gtoks[1])), float(gtoks[9]))
                for gtoks in (gw.split() for gw in lines)
                if gtoks and gtoks[0] == "GW" and len(gtoks) > 9
            )
        for t, a in found:
            if a > 0.0:  # radius 0 = tapered-wire GC prelude — no emulation
                tag_radius.setdefault(t, a)
        return tag_radius

    out, has_exec, ex6_lds = [], False, []
    for ln in lines:
        toks = ln.split()
        if toks[0] == "FR" and len(toks) > 2 and float(toks[2]) == 0:
            toks[2] = "1"
            ln = " ".join(toks)
        if toks[0] == "LD" and len(toks) > 1 and int(float(toks[1])) == 6:
            tag = toks[2] if len(toks) > 2 else "0"
            sf = toks[3] if len(toks) > 3 else "0"
            st = toks[4] if len(toks) > 4 else "0"
            q = (float(toks[5]) if len(toks) > 5 else 0.0) or 100.0
            le = float(toks[6]) if len(toks) > 6 else 0.0
            c = float(toks[7]) if len(toks) > 7 else 0.0
            if le == 0.0:
                continue  # trap without inductance — the importer drops it too
            r_p = q * 2.0 * math.pi * fr_first_mhz * 1e6 * le
            out.append(f"LD 1 {tag} {sf} {st} {r_p!r} {le!r} {c!r}")
            continue
        if toks[0] == "LD" and len(toks) > 1 and int(float(toks[1])) == 7:
            tag = int(float(toks[2])) if len(toks) > 2 else 0
            sf = toks[3] if len(toks) > 3 else "0"
            st = toks[4] if len(toks) > 4 else "0"
            eps_r = float(toks[5]) if len(toks) > 5 else 0.0
            b = float(toks[6]) if len(toks) > 6 else 0.0
            if b <= 0.0 or eps_r <= 1.0:
                continue  # no jacket / vacuum jacket — the importer drops it too
            if tag == 0 and float(sf) == 0:
                targets, sf, st = sorted(tag_radii()), "0", "0"
            else:
                targets = [tag]
            if not all(t in tag_radii() for t in targets):
                # A tag with no known radius: keep the card verbatim so
                # nec2c aborts honestly instead of solving wrong physics.
                out.append(ln)
                continue
            for t in targets:
                a = tag_radii()[t]
                if b <= a:
                    continue  # jacket inside the conductor — importer leaves it bare
                l_ins = float(insulation_inductance(a, b, eps_r))
                out.append(f"LD 2 {t} {sf} {st} 0 {l_ins!r} 0")
            continue
        if toks[0] == "EX" and len(toks) > 1 and int(float(toks[1])) == 6:
            if ex6 == "drop":
                # The superposition reference (issue #463) supplies its own
                # voltage-drive excitation, so strip the deck's EX 6 cards and
                # emit no R_BIG emulation.
                continue
            tag, seg = toks[2], toks[3] if len(toks) > 3 else "0"
            i_re = float(toks[5]) if len(toks) > 5 else 0.0
            i_im = float(toks[6]) if len(toks) > 6 else 0.0
            out.append(f"EX 0 {tag} {seg} 0 {i_re * EX6_R_BIG!r} {i_im * EX6_R_BIG!r}")
            # The series R_BIG lands as an LD 4, but hoisted BEFORE the
            # first EX card (below): nec2c resets its voltage-source list
            # when a matrix-affecting card (LD) follows an EX, so an
            # interleaved EX/LD/EX/LD deck keeps only the last source.
            ex6_lds.append(f"LD 4 {tag} {seg} {seg} {EX6_R_BIG!r} 0")
            continue
        if toks[0] in ("XQ", "RP"):
            has_exec = True
        out.append(ln)
    if ex6_lds:
        first_ex = next(i for i, ln in enumerate(out) if ln.split()[0] == "EX")
        out[first_ex:first_ex] = ex6_lds
    if not has_exec:
        if out and out[-1] == "EN":
            out.insert(-1, "XQ")
        else:
            out += ["XQ", "EN"]
    return "\n".join(out) + "\n"


def _nec2c_source_currents(deck_text: str, timeout: float, mem_bytes=None):
    """Run nec2c on prepared text and return each source's complex current in
    EX-card order (the ANTENNA INPUT PARAMETERS ``CURRENT`` column), plus the
    frequency: ``{"freq": MHz, "currents": [complex, ...], "error": str|None}``.
    A sibling of ``run_nec2c`` that reads current instead of impedance — the
    superposition reference (issue #463) drives voltages and measures currents.
    """
    if shutil.which("nec2c") is None:
        return {"error": "nec2c not on PATH"}
    with tempfile.TemporaryDirectory(prefix="nec_") as d:
        nec = Path(d) / "d.nec"
        out = Path(d) / "d.out"
        nec.write_text(deck_text)
        try:
            subprocess.run(
                ["nec2c", "-i", str(nec), "-o", str(out)],
                capture_output=True,
                timeout=timeout,
                preexec_fn=_rlimit_preexec(mem_bytes) if mem_bytes else None,
            )
        except subprocess.TimeoutExpired:
            return {"error": f"nec2c timeout >{timeout:.0f}s"}
        if not out.exists():
            return {"error": "nec2c produced no output"}
        lines = out.read_text(errors="replace").splitlines()
    freq = None
    for i, ln in enumerate(lines):
        m = _FREQ_RE.search(ln)
        if m:
            freq = float(m.group(1))
        if "ANTENNA INPUT PARAMETERS" in ln:
            cur = []
            j = i + 3  # header + units row, then data rows
            while j < len(lines) and lines[j].strip():
                toks = lines[j].split()
                if len(toks) >= 6:
                    try:
                        cur.append(complex(float(toks[4]), float(toks[5])))
                    except ValueError:
                        return {"error": "nec2c current parse failed"}
                j += 1
            if cur:
                return {"freq": freq, "currents": cur, "error": None}
    return {"error": "no ANTENNA INPUT PARAMETERS block"}


def superposition_reference(text: str, name: str, timeout: float, mem_bytes=None):
    """EX 6 current-source reference via nec2c Y-matrix superposition (#463, #464).

    nec2c has no port current source, and the single-R_BIG emulation (issue
    #442) cannot force N simultaneous port currents at once — on phased
    active-feed decks (e.g. 3vertical.nec) the reported per-feed V/I comes out
    R_BIG-invariant and wrong, so the R_BIG subtraction manufactures a huge
    negative resistance. It also breaks for a *single* EX 6 source whose segment
    also anchors a TL/NT (issue #464): the network port bypasses the series
    ``LD 4 R_BIG`` (a 20 kΩ load carrying 200+ A), so the raw readout is a NEC
    LD-plus-network composition artifact, not the driving-point impedance — and
    #456's "trust the R_BIG-invariant readout" skip trusts the wrong number.

    Recover the physics with native voltage drives instead: for each of the N
    solves, excite every port with an all-nonzero, linearly independent set of
    gap voltages and read every port's current, giving the port admittance
    matrix ``Y = I_mat · V_mat⁻¹``; invert to the impedance matrix Z, then
    compose the driving-point impedances the deck's current excitation produces
    — ``V = Z·I``, ``Z_i = V_i / I_i``. All-nonzero voltages sidestep NEC's "an
    all-zero EX defaults to 1 V" quirk; the linear solve is exact for any
    invertible drive pattern. The N = 1 case degenerates to one 1 V solve whose
    ``Z = V/I`` is exactly the (source-type-independent) driving-point
    impedance — correct whether or not the segment carries a TL.

    Returns a ``run_nec2c``-shaped dict (``z`` per feed in EX-card order,
    ``superposition``/``resolved_deck`` flags set) or an error dict; ``None`` if
    the deck has no EX 6 sources (not this path's job).
    """
    from antennaknobs.nec_import import resolve_sy

    try:
        resolved = resolve_sy(text, name=name).splitlines()
    except ValueError as e:
        return {"error": f"superposition resolve_sy: {e}"}
    ports, currents = [], []
    for ln in resolved:
        toks = ln.split()
        if toks and toks[0] == "EX" and len(toks) > 1 and int(float(toks[1])) == 6:
            ports.append((toks[2], toks[3] if len(toks) > 3 else "0"))
            i_re = float(toks[5]) if len(toks) > 5 else 0.0
            i_im = float(toks[6]) if len(toks) > 6 else 0.0
            currents.append(complex(i_re, i_im))
    n = len(ports)
    if n < 1:
        return None
    i_exc = np.array(currents)
    if np.any(i_exc == 0):
        return {"error": "superposition: a feed has zero drive current"}
    try:
        base = reference_deck(text, name, ex6="drop").splitlines()
    except ValueError as e:
        return {"error": f"superposition reference_deck: {e}"}
    exec_i = next(
        (
            k
            for k, ln in enumerate(base)
            if ln.split()[:1] and ln.split()[0] in ("XQ", "RP")
        ),
        len(base),
    )
    # Drive matrix: 1 on the diagonal, 0.5 off — all nonzero (dodges the zero-EX
    # quirk) and well conditioned (det = (0.5n + 0.5)·0.5^(n-1) > 0) at any n.
    v_mat = np.full((n, n), 0.5) + np.eye(n) * 0.5
    i_mat = np.zeros((n, n), dtype=complex)
    freq = None
    for j in range(n):
        ex = [
            f"EX 0 {ports[k][0]} {ports[k][1]} 0 {float(v_mat[k, j])!r} 0"
            for k in range(n)
        ]
        deck_j = "\n".join(base[:exec_i] + ex + base[exec_i:]) + "\n"
        res = _nec2c_source_currents(deck_j, timeout, mem_bytes)
        if res.get("error"):
            return {"error": f"superposition solve {j}: {res['error']}"}
        cur = res["currents"]
        if len(cur) != n:
            return {"error": f"superposition solve {j}: {len(cur)} sources, want {n}"}
        i_mat[:, j] = cur
        freq = res["freq"]
    try:
        z = np.linalg.inv(i_mat @ np.linalg.inv(v_mat))
    except np.linalg.LinAlgError as e:
        return {"error": f"superposition: singular matrix ({e})"}
    z_dp = (z @ i_exc) / i_exc
    return {
        "freq": freq,
        "z": [[zz.real, zz.imag] for zz in z_dp],
        "error": None,
        "superposition": True,
        "resolved_deck": True,
    }


def _nec2c_network_tables(deck_text: str, timeout: float, mem_bytes=None):
    """Run nec2c on prepared text and return the first frequency's network
    readout: ``{"freq": MHz, "struct": {(tag, abs_seg): (V, I, Z)},
    "aip": {(tag, abs_seg): (V, I, Z)}, "error": str|None}``.

    ``struct`` is the STRUCTURE EXCITATION DATA AT NETWORK CONNECTION POINTS
    table (printed only when NT/TL cards are present), ``aip`` the ANTENNA
    INPUT PARAMETERS table. Both key on (tag number, ABSOLUTE segment number)
    — that is what nec2c prints in its SEG column, not the within-tag rank an
    EX card uses. Values are complex (voltage, current, impedance) columns.
    Parsing stops after the first ANTENNA INPUT PARAMETERS block with data so
    a multi-frequency FR sweep reads like ``run_nec2c``: first frequency only.
    """
    if shutil.which("nec2c") is None:
        return {"error": "nec2c not on PATH"}
    with tempfile.TemporaryDirectory(prefix="nec_") as d:
        nec = Path(d) / "d.nec"
        out = Path(d) / "d.out"
        nec.write_text(deck_text)
        try:
            subprocess.run(
                ["nec2c", "-i", str(nec), "-o", str(out)],
                capture_output=True,
                timeout=timeout,
                preexec_fn=_rlimit_preexec(mem_bytes) if mem_bytes else None,
            )
        except subprocess.TimeoutExpired:
            return {"error": f"nec2c timeout >{timeout:.0f}s"}
        if not out.exists():
            return {"error": "nec2c produced no output"}
        lines = out.read_text(errors="replace").splitlines()

    def read_rows(i, rows):
        j = i + 3  # header + units row, then data rows
        while j < len(lines) and lines[j].strip():
            toks = lines[j].split()
            if len(toks) >= 8:
                try:
                    tag, seg = int(toks[0]), int(toks[1])
                    vals = [float(t) for t in toks[2:8]]
                except ValueError:
                    j += 1
                    continue
                if not all(math.isfinite(v) for v in vals):
                    return False
                rows[(tag, seg)] = (
                    complex(vals[0], vals[1]),
                    complex(vals[2], vals[3]),
                    complex(vals[4], vals[5]),
                )
            j += 1
        return True

    freq, struct, aip = None, {}, {}
    for i, ln in enumerate(lines):
        m = _FREQ_RE.search(ln)
        if m:
            freq = float(m.group(1))
        if "STRUCTURE EXCITATION DATA AT NETWORK CONNECTION POINTS" in ln:
            if not read_rows(i, struct):
                return {"error": "nec2c network solve returned NaN"}
        elif "ANTENNA INPUT PARAMETERS" in ln:
            if not read_rows(i, aip):
                return {"error": "nec2c solve returned NaN"}
            if aip:
                return {"freq": freq, "struct": struct, "aip": aip, "error": None}
    return {"error": "no ANTENNA INPUT PARAMETERS block"}


def gyrator_reference(text: str, name: str, deck, timeout: float, mem_bytes=None):
    """EX 6 current-source reference via 4nec2's NT-gyrator emulation (#475).

    This is byte-for-byte how the authoring tool itself runs an ``EX 6`` deck
    on a stock NEC-2 kernel (verified against 4nec2/NEC-2D on the #463 decks,
    agreement <0.2%): per current source, append

    1. a phantom 1-segment wire parked far above the structure (4nec2 uses
       Z ≈ 9901+n m; here 10x the structure extent + 200 wavelengths);
    2. an ``NT`` gyrator tying phantom -> real feed segment with Y11=Y22=0,
       Y12=Y21=j, which forces current -j*V_phantom into the real segment
       independent of what it is loaded with;
    3. an ``EX 0`` voltage source V = j*I_req on the phantom, so the delivered
       current is exactly the requested phasor.

    Unlike the R_BIG emulation (#442) there is nothing to subtract, and unlike
    the Y-matrix superposition (#463) there is no N-solve linear recovery: the
    deck's own TL/NT cards compose natively with the gyrators in ONE nec2c
    solve, and mixed EX 0 + EX 6 decks work too (the voltage cards stay put).

    The readout gotcha: with a gyrator, ANTENNA INPUT PARAMETERS reports the
    phantom port (nonsense values), and at a feed segment shared with a TL the
    STRUCTURE EXCITATION DATA row's IMPEDANCE column is V/I_wire — the wire
    current EXCLUDES what the co-located network carries away, so that column
    is wrong exactly where it matters. The row's VOLTAGE column is the true
    port voltage though, and the gyrator forces the port current exactly, so
    the driving-point impedance is read as Z_i = V_row / I_req,i. Voltage
    (EX 0) feeds of a mixed deck read their ANTENNA INPUT PARAMETERS row
    verbatim (nec2c's impedance there already includes network current).

    Returns a ``run_nec2c``-shaped dict (``z`` per feed in EX-card order,
    ``gyrator``/``resolved_deck`` flags set) or an error dict; ``None`` if the
    deck has no EX 6 sources (not this path's job).
    """
    feeds = deck.feeds
    if not any(f.current for f in feeds):
        return None
    if any(f.current and f.voltage == 0 for f in feeds):
        return {"error": "gyrator: a feed has zero drive current"}
    try:
        base = reference_deck(text, name, ex6="drop").splitlines()
    except ValueError as e:
        return {"error": f"gyrator reference_deck: {e}"}

    # Wavelength from the first FR card (same pre-scan as reference_deck).
    fr_first_mhz = 299.8
    for ln in base:
        toks = ln.split()
        if toks[0] == "FR" and len(toks) > 5:
            try:
                fr_first_mhz = float(toks[5]) or fr_first_mhz
            except ValueError:
                pass
            break
    lam = 299.792458 / fr_first_mhz

    # nec2c numbers segments in wire-definition order; the EX card's
    # within-tag rank was already resolved to (wire, seg) by the importer,
    # so the absolute segment number is a cumulative count away.
    seg_base, acc = [], 0
    for w in deck.wires:
        seg_base.append(acc)
        acc += w.n_seg

    def abs_seg(f):
        return seg_base[f.wire] + f.seg

    maxtag = max(w.tag for w in deck.wires)
    maxc = max(abs(c) for w in deck.wires for p in (w.p1, w.p2) for c in p)
    # Far enough that phantom<->structure coupling is negligible (the phantom
    # carries ~|Y_phantom*V_port| ~ 1e-4 A per volt), high rather than lateral
    # so a Sommerfeld ground stays comfortable. Phantom wires only exist in
    # this nec2c deck — engines never see them (cf. the momwire #157 cap).
    zbase = 10.0 * maxc + 200.0 * lam
    plen = lam / 50.0
    prad = plen / 200.0

    ge_i = next((i for i, ln in enumerate(base) if ln.split()[0] == "GE"), None)
    if ge_i is None:
        return {"error": "gyrator: deck has no GE card"}
    exec_i = next(k for k, ln in enumerate(base) if ln.split()[0] in ("XQ", "RP"))

    gws, nts, exs = [], [], []
    cur_feeds = [f for f in feeds if f.current]
    for j, f in enumerate(cur_feeds):
        ptag = maxtag + 1 + j
        x0 = j * 10.0 * plen
        gws.append(f"GW {ptag} 1 {x0!r} 0 {zbase!r} {x0 + plen!r} 0 {zbase!r} {prad!r}")
        # Port 2 as tag 0 + absolute segment number (NEC's tag-0 convention)
        # — sidesteps recomputing the within-tag rank.
        nts.append(f"NT {ptag} 1 0 {abs_seg(f)} 0 0 0 1 0 0")
        v = 1j * f.voltage  # delivered current at port 2 is -j * V_src
        exs.append(f"EX 0 {ptag} 1 0 {v.real!r} {v.imag!r}")

    # NEC-2 requires all NT/TL cards of one network configuration to be
    # contiguous — a network card read after any non-network card DESTROYS
    # the previous network data (this silently dropped DipTL's TL until the
    # gyrator NTs were spliced adjacent to it). ALL EX cards go last, just
    # before the execute request: nec2c also drops voltage sources that
    # precede an FR or NT card (the same reset family as reference_deck's
    # LD-after-EX hoist), so a mixed deck's own EX 0 cards are re-emitted
    # there in original order rather than left in place.
    last_net = max(
        (k for k, ln in enumerate(base) if ln.split()[0] in ("TL", "NT")),
        default=None,
    )
    nt_at = last_net + 1 if last_net is not None else exec_i
    ex_deck = [ln for ln in base[:exec_i] if ln.split()[0] == "EX"]
    mid = [ln for ln in base[ge_i:nt_at] if ln.split()[0] != "EX"]
    tail = [ln for ln in base[nt_at:exec_i] if ln.split()[0] != "EX"]
    out = base[:ge_i] + gws + mid + nts + tail + ex_deck + exs + base[exec_i:]
    res = _nec2c_network_tables("\n".join(out) + "\n", timeout, mem_bytes)
    if res.get("error"):
        return {"error": f"gyrator: {res['error']}"}

    z_out = []
    for f in feeds:
        key = (deck.wires[f.wire].tag, abs_seg(f))
        if f.current:
            row = res["struct"].get(key)
            if row is None:
                return {
                    "error": f"gyrator: no network-connection row for "
                    f"tag {key[0]} seg {key[1]}"
                }
            z = row[0] / f.voltage  # V_port / I_forced
        else:
            row = res["aip"].get(key)
            if row is None:
                return {
                    "error": f"gyrator: no input-parameters row for "
                    f"tag {key[0]} seg {key[1]}"
                }
            z = row[2]
        z_out.append([z.real, z.imag])
    return {
        "freq": res["freq"],
        "z": z_out,
        "error": None,
        "gyrator": True,
        "resolved_deck": True,
    }


def feeds_sharing_tl_nt(deck) -> list[int]:
    """Indices of ``deck.feeds`` whose driven segment also anchors a ``TL``
    or ``NT`` endpoint (issue #456).

    The EX 6 current-source emulation (issue #442) drives ``V = I·R_BIG``
    behind an ``LD 4`` series ``R_BIG`` and the caller recovers the load by
    subtracting ``R_BIG`` from nec2c's reported feed impedance — valid only
    when that series R lands *inside* the readout. When a transmission line
    (or NT two-port) is anchored on the same segment, it carries the feed
    current and nec2c's reported V/I is already the true driving-point
    impedance (the R_BIG term does not appear — verified constant across
    R_BIG = 1e3…1e6 on DipTL/CardTL/4SQTL). Subtracting there manufactures
    a ~−R_BIG resistance; the caller must skip it on these feeds.
    """
    anchored = set()
    for c in (*deck.tls, *deck.nts):
        anchored.add((c.wire_a, c.seg_a))
        anchored.add((c.wire_b, c.seg_b))
    return [i for i, f in enumerate(deck.feeds) if (f.wire, f.seg) in anchored]


def _has_near_ground_ungrounded_wire(deck, freq_mhz: float) -> bool:
    """The geometry class where nec2++/PyNEC's gn 2 Sommerfeld is known-
    unreliable (issue #448): near-ground conductor that is not a plain
    grounded vertical. Delegates to the engine's own risk predicate
    (`engines.pynec._somm_low_wire_risk` — the same one behind the
    RuntimeWarning PyNECEngine emits at solve time) so the flag and the
    warning can never drift apart."""
    try:
        from antennaknobs.engines.pynec import _somm_low_wire_risk
    except ImportError:  # PyNEC absent: no pynec rows to annotate anyway
        return False
    try:
        tups = deck.wire_tuples(specs=True)
    except Exception:  # noqa: BLE001 — a flag, never a crash
        return False
    return bool(_somm_low_wire_risk(tups, 299.792458 / freq_mhz))


def _stepped_radius(deck) -> bool:
    """Stepped/multi-radius elements (issue #885): any two wires whose radii
    genuinely differ. On these decks the nec2c reference carries NEC-2's
    known stepped-diameter defect (the reason EZNEC ships the Leeson
    correction; fixed in NEC-4/NEC-5): the #872 phase-5 movers analysis put
    {bs2 + NEC-5} in mutual agreement against {nec2c + nec2++} on identical
    geometry for 44/46 formulation-class decks, all stepped-radius — the
    REFERENCE is the outlier there, so the flag marks the ΔΓ-vs-nec2c
    columns as reference-suspect rather than engine error. (GC tapers would
    belong here too, but ``parse_nec`` rejects GC decks before a row
    exists, so distinct GW radii are the whole served class.)"""
    radii = [w.radius for w in deck.wires]
    return bool(radii) and max(radii) > min(radii) * (1 + 1e-9)


def bench_deck(
    deck_path: Path,
    engines,
    timeout,
    run_with_ground=True,
    allow_intersections=False,
    mem_bytes=None,
    rel_name=None,
    nec5_capture_dir=None,
):
    # rel_name (corpus-relative path) disambiguates wild trees where the same
    # stem appears under several sources.
    row = {"deck": rel_name or deck_path.stem, "error": None}
    text = deck_path.read_text(errors="replace")
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
        # Remote TL-anchor wires the importer replaced with PortVirtual
        # terminations (issue #427): the deck solves on momwire engines
        # instead of hanging (momwire#157), at a residual that matches nec2c
        # better than meshing the tiny remote wire would. Labeled, not hidden.
        virtualized_anchors=list(deck.virtual_anchor_tags()),
        stepped_radius=_stepped_radius(deck),
    )

    # EX 6 decks (issue #442) NEVER use the original-deck reference: nec2c
    # misparses type 6 as a plane wave, so a mixed EX 0 + EX 6 deck could
    # "succeed" with silently wrong physics. Same for decks with run-config
    # cards trailing the last execute request (issue #449): batch nec2c
    # executes BEFORE reading them, so the original run silently drops a
    # TL, ground, or load the deck intends. Both go straight to the
    # prepared (emulated / hoisted) reference.
    ex6_feeds = [f.current for f in deck.feeds]
    ref = None
    if not any(ex6_feeds) and not has_dead_trailing_config(text):
        ref = run_nec2c(deck_path, timeout, mem_bytes)
    # EX 6 decks route to the NT-gyrator emulation first (#475): 4nec2's own
    # way of running a current source on a NEC-2 kernel — one solve, composes
    # natively with the deck's TL/NT cards, handles mixed EX 0 + EX 6 decks,
    # and cross-validated against both 4nec2 itself and the superposition
    # reference (<0.2%). Falls through to superposition, then R_BIG, so
    # behaviour is never worse than before.
    if (ref is None or ref.get("error")) and any(ex6_feeds):
        gyr = gyrator_reference(text, deck_path.name, deck, timeout, mem_bytes)
        if gyr is not None and not gyr.get("error"):
            ref = gyr
    # All-current EX 6 decks (issues #463, #464): the R_BIG emulation can't
    # force the port current cleanly whenever a network shares the driven
    # segment — one solve can't hold N simultaneous currents (#463), and even a
    # single source's series R_BIG is bypassed by a co-located TL/NT so the raw
    # readout is a composition artifact (#464). Y-matrix superposition —
    # native voltage solves composing the true driving-point impedances,
    # correct for N ≥ 1 with or without a TL — remains the fallback when the
    # gyrator path can't run.
    if (ref is None or ref.get("error")) and sum(ex6_feeds) >= 1 and all(ex6_feeds):
        sup = superposition_reference(text, deck_path.name, timeout, mem_bytes)
        if sup is not None and not sup.get("error"):
            ref = sup
    if ref is None or ref.get("error"):
        # Resolved-reference retry (issue #439): the deck parses for *us*,
        # so a failed reference run may just be dialect (SY symbols, no
        # XQ/RP request, EX 6). Retry nec2c on the prepared text; a success
        # is labeled, never silently swapped in.
        try:
            prepared = reference_deck(text, deck_path.name)
        except ValueError:
            prepared = None
        if prepared is not None:
            retry = run_nec2c(deck_path, timeout, mem_bytes, deck_text=prepared)
            if not retry.get("error"):
                retry["resolved_deck"] = True
                if ref is not None:
                    retry["original_error"] = ref["error"]
                if any(ex6_feeds):
                    # Undo the current-source emulation: nec2c reported
                    # Z_gap + R_BIG at each EX 6 feed (row order follows
                    # EX-card order, same as deck.feeds) — EXCEPT on a feed
                    # whose segment also anchors a TL/NT, where the readout is
                    # already the true impedance and the subtraction must be
                    # skipped (issue #456).
                    retry["ex6_emulated"] = True
                    tl_shared = set(feeds_sharing_tl_nt(deck))
                    if tl_shared:
                        retry["ex6_tl_shared"] = sorted(tl_shared)
                    if len(retry.get("z") or []) >= len(ex6_feeds):
                        for i, is_cur in enumerate(ex6_feeds):
                            if is_cur and i not in tl_shared:
                                retry["z"][i][0] -= EX6_R_BIG
                ref = retry
            elif ref is None:
                ref = retry  # EX 6 path: report the prepared run's error
        if ref is None:
            ref = {"error": "EX 6 deck; reference preparation failed"}
    row["nec2c"] = ref
    if ref.get("error"):
        return row
    freq = ref["freq"]
    if freq is None:
        row["error"] = "nec2c gave impedance but no parseable FREQUENCY line"
        return row
    row["freq"] = freq

    # Before pynec-accel 1.7.6, nec2++/PyNEC's Sommerfeld (gn 2) was
    # unreliable when a conductor sits within 0.1 wavelength of the ground
    # plane without touching it (issue #448; calibrated on this corpus — all
    # 19 decks where PyNEC broke against an agreeing nec2c+momwire pair are
    # in this class; fixed by the INTRP cell-cache repair in
    # stevenmburns/necpp#5). The flag is kept for provenance when scoring
    # older PyNEC builds: a large pynec dgamma on a flagged deck under
    # pynec-accel < 1.7.6 is the known engine defect, not an
    # import/translation signal.
    row["pynec_somm_suspect"] = (
        isinstance(ground, tuple)
        and ground[0] == "finite"
        and _has_near_ground_ungrounded_wire(deck, freq)
    )

    eng_ground = ground if run_with_ground else "free"
    row["engines"] = {}
    for e in engines:
        res = run_engine(
            e,
            deck_path,
            freq,
            eng_ground,
            timeout,
            allow_intersections,
            mem_bytes,
            nec5_capture_dir=nec5_capture_dir,
        )
        if res.get("error") is None and "z" in res:
            res["cmp"] = compare(res["z"], ref["z"])
        else:
            # Persist the classification (geo-reject vs other) into the JSON so
            # a reader doesn't have to re-grep tracebacks (issue #409).
            res["error_kind"] = engine_error_kind(res)
        row["engines"][e] = res
    return row


def clean_deck(r) -> bool:
    """Deck-level membership in the clean baseline cohort — the decks whose
    ΔΓ measures the ENGINE rather than a labeled special case. Engine-level
    conditions (this engine errored, no comparison) are the caller's."""
    return (
        r.get("ground_supported", True)
        and not r.get("partial_net")
        and not r.get("virtualized_anchors")
        # r-flagged decks (reference from our own resolved text, #439)
        # are a labeled cohort, not the clean baseline: the resolution
        # and the engines share the SY evaluator, so its bugs cancel
        and not r["nec2c"].get("resolved_deck")
        # d-flagged decks measure the reference's stepped-diameter
        # defect, not the engine (#885) — they get their own section
        and not r.get("stepped_radius")
    )


# PyNEC is the IMPORT canary (issue #946). PyNEC/nec2++ and nec2c are near
# enough to the same physics that a large PyNEC ΔΓ does not mean "the solvers
# disagree" — it means the geometry we handed PyNEC is not the deck nec2c
# read, i.e. the importer diverged. Corpus evidence: PyNEC's median ΔΓ is
# 0.0002 with p90 0.0077 (2026-07-17 wild sweep, 1,875 decks), so anything
# near 0.05 is orders out of family.
#
# The floor dominates in practice (25 × a 0.0002 median is 0.005); the
# multiple only matters if a future corpus is far noisier, where an absolute
# 0.02 would flag half the run.
#
# The multiple is gated on sample size because on a short run the suspect
# inflates its OWN baseline and hides: a 3-deck run containing k9ay_orig
# (0.0848) medians at 0.0424, putting the threshold at 1.06 and flagging
# nothing. Below the gate the median carries no information about corpus
# noise, so the floor is the honest test.
_CANARY_FLOOR = 0.02
_CANARY_MULTIPLE = 25.0
_CANARY_MIN_BASELINE = 20

# Corroboration, not a gate: when every engine sits at the SAME distance from
# the reference, the fault is upstream of all of them. Spread within this
# fraction of the smallest ΔΓ counts as "clustered".
_CANARY_CLUSTER_FRAC = 0.5


def _feed0_dgamma(res):
    """Feed-0 ΔΓ for one engine result, or None if it did not produce one."""
    if not res or res.get("error") or engine_error_kind(res):
        return None
    cmp = res.get("cmp") or []
    return cmp[0]["dgamma"] if cmp else None


def import_canary(rows, engines):
    """Decks whose PyNEC ΔΓ is out of family — import-divergence suspects.

    Returns ``(median, threshold, suspects, n_baseline)``; ``suspects`` are
    ``(row, pynec_dgamma, clustered)`` sorted worst-first. ``clustered``
    marks the strong signature: every engine the same distance from nec2c,
    which no solver-physics story explains but a mistranslated deck does.
    ``n_baseline`` lets the caller say whether the median was trusted — below
    ``_CANARY_MIN_BASELINE`` it is reported but not used.

    The baseline median is taken over the clean cohort only, so labeled
    special cases (unsupported ground, partial networks, ...) cannot inflate
    the threshold and mask a real suspect.
    """
    if "pynec" not in engines:
        return None, None, [], 0
    ok = [r for r in rows if not r.get("error") and not r.get("nec2c", {}).get("error")]
    baseline = [
        dg
        for r in ok
        if clean_deck(r)
        and (dg := _feed0_dgamma(r["engines"].get("pynec"))) is not None
    ]
    if not baseline:
        return None, None, [], 0
    median = statistics.median(baseline)
    threshold = _CANARY_FLOOR
    if len(baseline) >= _CANARY_MIN_BASELINE:
        threshold = max(threshold, _CANARY_MULTIPLE * median)

    suspects = []
    for r in ok:
        dg = _feed0_dgamma(r["engines"].get("pynec"))
        if dg is None or dg < threshold:
            continue
        others = [
            v for e in engines if (v := _feed0_dgamma(r["engines"].get(e))) is not None
        ]
        clustered = (
            len(others) > 1
            and min(others) > 0
            and (max(others) - min(others)) <= _CANARY_CLUSTER_FRAC * min(others)
        )
        suspects.append((r, dg, clustered))
    suspects.sort(key=lambda t: -t[1])
    return median, threshold, suspects, len(baseline)


def fmt_dg(res):
    kind = engine_error_kind(res)
    if kind == "geo":
        return "GEO"  # nec2++ geometry-intersection rejection (issue #409)
    if kind == "scope":
        return "OOS"  # outside the engine's served dialect (#872 phase 0)
    if kind == "mem":
        return "MEM"  # hit --mem-limit-gb
    if kind == "timeout":
        return "TIME"  # hit --timeout
    if kind == "err":
        return "ERR"
    cmp = res.get("cmp") or []
    if not cmp:
        return "n/a"
    return f"{cmp[0]['dgamma']:.4f}"  # feed 0


def print_report(rows, engines):
    ok = [r for r in rows if not r.get("error") and not r.get("nec2c", {}).get("error")]

    print("\n" + "=" * 104)
    print(
        "REFLECTION-COEFFICIENT ERROR vs nec2c  "
        "(feed 0; ΔΓ = |Γ_eng − Γ_nec2c|, Γ = (Z−50)/(Z+50))"
    )
    print(
        "  flags: g = unsupported ground (radials/cliff), n = inexpressible LD/TL/NT "
        "network, v = remote TL-anchor wire(s) virtualized (#427),"
        " r = reference from resolved deck (#439),"
        " t = mixed EX 6 feed shares a TL/NT segment; R_BIG subtraction skipped (#456),"
        " y = EX 6 current-source reference via NT-gyrator emulation (#475),"
        " s = EX 6 current-source reference via Y-matrix superposition (#463, #464),"
        " p = gn 2 + near-ground ungrounded wire: pynec known-unreliable (#448),"
        " d = stepped-radius wires: nec2c reference suspect "
        "(NEC-2 stepped-diameter defect, #885),"
        " i = PyNEC ΔΓ out of family: suspect the IMPORTER, not the solver (#946)"
    )
    print("=" * 104)
    hdr = (
        f"{'deck':<34} {'f/MHz':>8} {'grd':>5} {'fl':>4} {'Z_nec2c (feed0)':>19}  "
        + " ".join(f"{ENGINE_LABEL[e]:>11}" for e in engines)
    )
    print(hdr)
    print("-" * len(hdr))
    canary_median, canary_threshold, canary_suspects, canary_n = import_canary(
        rows, engines
    )
    canary_decks = {id(r) for r, _, _ in canary_suspects}
    for r in ok:
        z0 = _z(r["nec2c"]["z"][0])
        flags = (
            ("g" if not r.get("ground_supported", True) else "")
            + ("n" if r.get("partial_net") else "")
            + ("v" if r.get("virtualized_anchors") else "")
            + ("r" if r.get("nec2c", {}).get("resolved_deck") else "")
            + ("t" if r.get("nec2c", {}).get("ex6_tl_shared") else "")
            + ("y" if r.get("nec2c", {}).get("gyrator") else "")
            + ("s" if r.get("nec2c", {}).get("superposition") else "")
            + ("p" if r.get("pynec_somm_suspect") else "")
            + ("d" if r.get("stepped_radius") else "")
            + ("i" if id(r) in canary_decks else "")
        )
        cells = " ".join(f"{fmt_dg(r['engines'].get(e)):>11}" for e in engines)
        print(
            f"{r['deck']:<34} {r.get('freq', 0):>8.3f} {r.get('ground') or 'free':>5} "
            f"{flags:>4} {z0.real:>8.1f}{z0.imag:>+8.1f}j  {cells}"
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
        "AGREEMENT ROLLUP  (feed-0 ΔΓ; clean decks: supported ground, "
        "fully-expressed network, no virtualized anchors, verbatim reference,\n"
        "  single-radius geometry — d-flagged decks are excluded because the "
        "nec2c REFERENCE is the suspect there, #885)"
    )
    print("=" * 72)
    for e in engines:
        dgs = [
            r["engines"][e]["cmp"][0]["dgamma"]
            for r in ok
            if clean_deck(r)
            and not r["engines"].get(e, {}).get("error")
            and r["engines"][e].get("cmp")
        ]
        if not dgs:
            print(f"{ENGINE_LABEL[e]:<12} no data")
            continue
        dgs.sort()
        within = lambda t: sum(1 for x in dgs if x <= t)  # noqa: E731
        print(
            f"{ENGINE_LABEL[e]:<12} n={len(dgs):>3}  median={statistics.median(dgs):.4f}  "
            f"<0.01:{within(0.01):>3}  <0.05:{within(0.05):>3}  <0.2:{within(0.20):>3}"
        )

    # Import-divergence canary (#946). See import_canary for why PyNEC is the
    # instrument: it shares nec2c's physics closely enough that its distance
    # from the reference reads the TRANSLATION, not the solver.
    if canary_suspects:
        print("\n" + "=" * 72)
        trusted = canary_n >= _CANARY_MIN_BASELINE
        basis = (
            f"median {canary_median:.4f} over {canary_n} clean decks"
            if trusted
            else f"floor; {canary_n}-deck baseline is below the "
            f"{_CANARY_MIN_BASELINE}-deck gate"
        )
        print(
            f"IMPORT-DIVERGENCE SUSPECTS ({len(canary_suspects)}) — PyNEC ΔΓ "
            f"≥ {canary_threshold:.4f} ({basis}), #946"
        )
        print(
            "  PyNEC ≈ nec2c physics, so a large PyNEC ΔΓ means the geometry we\n"
            "  handed it is not the deck nec2c read. 'clustered' = every engine\n"
            "  the same distance from the reference: the strong signature, since\n"
            "  no solver-physics story puts them all out by one common offset."
        )
        print("=" * 72)
        print(f"{'deck':<34} {'pynec ΔΓ':>10} {'× median':>10}  signature")
        for r, dg, clustered in canary_suspects:
            # The ratio only means something against a trusted baseline; on a
            # short run the suspect is part of its own median.
            ratio = f"{dg / canary_median:.0f}x" if trusted and canary_median else "—"
            sig = (
                "clustered — import suspect"
                if clustered
                else "pynec-only — see #448/#885 first"
            )
            print(f"{r['deck']:<34} {dg:>10.4f} {ratio:>10}  {sig}")

    # Stepped-radius cohort (#885): on d-flagged decks the trustworthy signal
    # is the bs2↔nec5 MUTUAL distance — two independent formulations that both
    # model stepped diameters — not either engine's distance from nec2c.
    stepped = [r for r in ok if r.get("stepped_radius")]
    if stepped:
        both = "bs2" in engines and "nec5" in engines
        print("\n" + "=" * 72)
        print(
            f"STEPPED-RADIUS DECKS ({len(stepped)}) — nec2c reference suspect "
            "(#885)" + ("; quality signal = ΔΓ(bs2, nec5)" if both else "")
        )
        print("=" * 72)
        if both:
            print(
                f"{'deck':<34} {'bs2 vs ref':>11} {'nec5 vs ref':>12} {'bs2↔nec5':>10}"
            )
            for r in stepped:
                zs = {}
                for e in ("bs2", "nec5"):
                    res = r["engines"].get(e) or {}
                    if not res.get("error") and res.get("z"):
                        zs[e] = _z(res["z"][0])
                mutual = (
                    f"{abs(_gamma(zs['bs2']) - _gamma(zs['nec5'])):>10.4f}"
                    if len(zs) == 2
                    else f"{'n/a':>10}"
                )
                print(
                    f"{r['deck']:<34} {fmt_dg(r['engines'].get('bs2')):>11} "
                    f"{fmt_dg(r['engines'].get('nec5')):>12} {mutual}"
                )
        else:
            for r in stepped:
                print(f"  {r['deck']}")

    # failures
    errs = [r for r in rows if r.get("error") or r.get("nec2c", {}).get("error")]
    if errs:
        print("\n" + "=" * 72)
        print(f"SKIPPED / FAILED DECKS ({len(errs)})")
        print("=" * 72)
        for r in errs:
            why = r.get("error") or r["nec2c"].get("error")
            print(f"  {r['deck']:<40} {why}")

    # per-engine errors on decks that DID get a nec2c reference, split by kind:
    # GEO = nec2++ geometry-intersection rejection (documented limitation,
    # issue #409); ERR = any other engine failure worth investigating.
    eng_errs = [
        (r["deck"], e, kind, r["engines"][e].get("error"))
        for r in ok
        for e in engines
        if (kind := engine_error_kind(r["engines"].get(e)))
    ]
    if eng_errs:
        geo = [x for x in eng_errs if x[2] == "geo"]
        scope = [x for x in eng_errs if x[2] == "scope"]
        mem = [x for x in eng_errs if x[2] == "mem"]
        tmo = [x for x in eng_errs if x[2] == "timeout"]
        other = [x for x in eng_errs if x[2] == "err"]
        print("\n" + "=" * 72)
        print(f"ENGINE ERRORS ON REFERENCED DECKS ({len(eng_errs)})")
        print("=" * 72)
        if scope:
            print(
                f"OOS — outside the engine's served dialect ({len(scope)}); "
                "designed refusal (TL/NT, ql/qc loads, distributed ports, "
                "buried/in-plane wires, refl-coef ground), not a failure:"
            )
            for deck, e, _k, why in scope:
                print(f"  {deck:<28} {ENGINE_LABEL[e]:<12} {(why or '')[:70]}")
        if geo:
            print(
                f"GEO — nec2++ geometry-intersection rejection ({len(geo)}); "
                "genuine kernel limitation, nec2c & momwire accept the geometry:"
            )
            for deck, e, _k, why in geo:
                print(f"  {deck:<28} {ENGINE_LABEL[e]:<12} {(why or '')[:70]}")
        if mem:
            print(f"MEM — hit the memory cap ({len(mem)}):")
            for deck, e, _k, why in mem:
                print(f"  {deck:<28} {ENGINE_LABEL[e]:<12} {(why or '')[:70]}")
        if tmo:
            print(f"TIME — hit the wall-clock cap ({len(tmo)}):")
            for deck, e, _k, why in tmo:
                print(f"  {deck:<28} {ENGINE_LABEL[e]:<12} {(why or '')[:70]}")
        if other:
            print(f"ERR — other engine failures ({len(other)}):")
            for deck, e, _k, why in other:
                print(f"  {deck:<28} {ENGINE_LABEL[e]:<12} {(why or '')[:70]}")


# --------------------------------------------------------------------------
_NUM_RE = None


def _normalize_reason(msg: str) -> str:
    """Collapse per-deck specifics (numbers, quoted names) so one cause
    groups into one census line: 'line 42: GW card: tag 17 ...' and
    'line 7: GW card: tag 3 ...' are the same bug."""
    global _NUM_RE
    import re

    if _NUM_RE is None:
        _NUM_RE = (
            re.compile(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?"),
            re.compile(r"'[^']*'"),
        )
    num_re, quote_re = _NUM_RE
    # Drop the "<deckname>, line N:" prefix — the grouping key is the cause,
    # not which deck tripped it.
    if ": " in msg:
        head, tail = msg.split(": ", 1)
        if "line" in head or head.endswith((".nec", ".NEC", ".inp")):
            msg = tail
    out = quote_re.sub("'…'", msg)
    out = num_re.sub("#", out)
    return out[:160]


def parse_census(decks, corpus, out_path):
    """Importer acceptance census (issue #410): parse every content-unique
    deck with network=True (the app's path), falling back to network=False
    exactly like load_deck does. No solves. A ValueError is a *designed*
    rejection (the importer said why); any other exception is a parser
    crash — a bug by definition on wild input."""
    import hashlib
    from collections import Counter, defaultdict

    from antennaknobs.nec_import import parse_nec

    seen: dict[str, Path] = {}
    dup_count = 0
    results = []
    skipped_hist: Counter = Counter()
    reject_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    crash_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    n_clean = n_skipcards = n_fallback = 0
    slowest = (0.0, None)

    for p in decks:
        raw = p.read_bytes()
        h = hashlib.md5(raw).hexdigest()
        if h in seen:
            dup_count += 1
            continue
        seen[h] = p
        rel = str(p.relative_to(corpus))
        text = raw.decode("utf-8", errors="replace")
        rec = {"deck": rel}
        t0 = time.perf_counter()
        try:
            deck = parse_nec(text, name=p.name, network=True)
            rec["status"] = "ok"
            rec["ignored"] = list(deck.ignored)
            if deck.ignored:
                n_skipcards += 1
                skipped_hist.update(set(deck.ignored))
            else:
                n_clean += 1
        except ValueError as first:
            try:
                deck = parse_nec(text, name=p.name, network=False)
                rec["status"] = "net-fallback"
                rec["reason"] = str(first)
                n_fallback += 1
                skipped_hist.update(set(deck.ignored))
            except ValueError as e:
                rec["status"] = "rejected"
                rec["reason"] = str(e)
                reject_groups[("ValueError", _normalize_reason(str(e)))].append(rel)
            except Exception as e:  # noqa: BLE001 — census must survive anything
                rec["status"] = "crash"
                rec["reason"] = f"{type(e).__name__}: {e}"
                crash_groups[(type(e).__name__, _normalize_reason(str(e)))].append(rel)
        except Exception as e:  # noqa: BLE001
            rec["status"] = "crash"
            rec["reason"] = f"{type(e).__name__}: {e}"
            crash_groups[(type(e).__name__, _normalize_reason(str(e)))].append(rel)
        dt = time.perf_counter() - t0
        if dt > slowest[0]:
            slowest = (dt, rel)
        rec["parse_s"] = round(dt, 4)
        results.append(rec)

    n = len(results)
    n_rej = sum(len(v) for v in reject_groups.values())
    n_crash = sum(len(v) for v in crash_groups.values())
    print(f"\ncorpus: {corpus}")
    print(f"files: {len(decks)}  unique: {n}  (content dups skipped: {dup_count})")
    print(
        f"parsed clean: {n_clean}   with skipped cards: {n_skipcards}   "
        f"network-mode fallback: {n_fallback}   rejected: {n_rej}   "
        f"CRASHES: {n_crash}"
    )
    print(f"slowest parse: {slowest[0]:.2f}s  {slowest[1]}")

    if skipped_hist:
        print("\nSKIPPED-CARD HISTOGRAM (decks containing the card)")
        for card, cnt in skipped_hist.most_common():
            print(f"  {card:4s} {cnt:5d}")

    def _show(title, groups):
        if not groups:
            return
        print(f"\n{title} ({sum(len(v) for v in groups.values())} decks)")
        for (cls, reason), files in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            print(f"  {len(files):5d}  {cls}: {reason}")
            print(f"         e.g. {files[0]}")

    _show("DESIGNED REJECTIONS (grouped)", reject_groups)
    _show("PARSER CRASHES — bugs by definition (grouped)", crash_groups)

    if out_path:
        out_path.write_text(
            json.dumps(
                {"corpus": str(corpus), "n_files": len(decks), "decks": results},
                indent=1,
            )
        )
        print(f"\nfull census -> {out_path}")


def nec2c_fingerprint():
    """Identify the nec2c build the sweep scores against (census caveat:
    vanilla 1.3.1 and the KJ7LNW fork disagree on some decks — results are
    only comparable against the same binary)."""
    import hashlib

    path = shutil.which("nec2c")
    if not path:
        return {"path": None}
    ver = subprocess.run(["nec2c", "-v"], capture_output=True, text=True).stdout.strip()
    md5 = hashlib.md5(Path(path).read_bytes()).hexdigest()
    return {"path": path, "version": ver, "md5": md5}


def dedupe_decks(decks):
    """Content-dedupe (md5, first path wins) — same rule as --parse-only;
    the wild corpus has ~860 exact duplicates across source mirrors."""
    import hashlib

    seen: set[str] = set()
    unique = []
    for p in decks:
        h = hashlib.md5(p.read_bytes()).hexdigest()
        if h not in seen:
            seen.add(h)
            unique.append(p)
    return unique, len(decks) - len(unique)


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
        "--engines",
        nargs="+",
        default=list(DEFAULT_ENGINE_KEYS),
        choices=ENGINE_KEYS,
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
        "--mem-limit-gb",
        type=float,
        default=None,
        help="RLIMIT_AS cap (GB) applied to every solve subprocess and the "
        "nec2c reference run — one pathological wild deck can't OOM the host "
        "(issue #410)",
    )
    ap.add_argument(
        "--free-space",
        action="store_true",
        help="run engines free-space regardless of the deck's GN",
    )
    ap.add_argument(
        "--allow-wire-intersections",
        action="store_true",
        help="disable nec2++'s wire/segment intersection validator so PyNEC "
        "accepts closely-spaced / crossing wires NEC-2 and momwire solve "
        "(issue #409; needs pynec-accel >=1.7.5)",
    )
    ap.add_argument(
        "--nec5-capture-dir",
        type=Path,
        default=Path.home() / ".antennaknobs" / "nec5-captures",
        help="printout capture-and-cache for the nec5 lane (#872 phase 0): "
        "each solve's deck and printout are stored keyed by deck content "
        "hash, and an already-captured deck is served from disk without "
        "re-running the binary. Captured printouts are End-User Reports "
        "under the NEC-5 license (LLNL-CODE-746721)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write full results here. A .json path is written once at the "
        "end; a .jsonl path is written incrementally (one row per deck as it "
        "finishes) and doubles as a resume point — re-running with the same "
        "--out skips decks already recorded",
    )
    ap.add_argument(
        "--parse-only",
        action="store_true",
        help="importer acceptance census (issue #410): run nec_import over "
        "every deck in the corpus (recursive, content-deduped) with NO "
        "solves — classify parsed-clean / cards-skipped / designed "
        "rejection / parser crash, and print the histograms",
    )
    args = ap.parse_args(argv)

    if args.worker:
        engine, deck, freq, ground = args.worker
        worker_main(engine, deck, float(freq), ground)
        return

    corpus = args.corpus
    if not corpus.is_dir():
        sys.exit(f"corpus not found: {corpus}")
    # Recursive + .inp so wild corpora (nec-wild trees) work; flat corpora
    # like the xnec2c examples dir see identical behaviour.
    decks = sorted(
        p
        for p in corpus.rglob("*")
        if p.is_file() and p.suffix.lower() in (".nec", ".inp")
    )
    if args.decks:
        want = {d.replace(".nec", "") for d in args.decks}
        decks = [p for p in decks if p.stem in want or p.name in args.decks]
    if args.limit:
        decks = decks[: args.limit]
    if not decks:
        sys.exit("no decks selected")

    if args.parse_only:
        parse_census(decks, corpus, args.out)
        return

    decks, n_dups = dedupe_decks(decks)
    mem_bytes = int(args.mem_limit_gb * 2**30) if args.mem_limit_gb else None

    cores = physical_cpu_count()
    nec2c_id = nec2c_fingerprint()
    print(f"corpus: {corpus}")
    print(
        f"decks: {len(decks)} (content dups skipped: {n_dups})   "
        f"engines: {', '.join(args.engines)}"
    )
    print(
        f"bounds: timeout={args.timeout:.0f}s/solve   "
        f"mem={args.mem_limit_gb or 'unlimited'}"
        + ("GB (RLIMIT_AS)" if args.mem_limit_gb else "")
    )
    print(
        f"nec2c reference: {nec2c_id.get('version')} at {nec2c_id.get('path')} "
        f"md5={nec2c_id.get('md5')}"
    )
    print(
        f"concurrency (mirrors web/server.py): BLAS={cores} OpenMP={cores} "
        f"OMP_WAIT_POLICY={os.environ['OMP_WAIT_POLICY']} "
        f"GOMP_SPINCOUNT={os.environ['GOMP_SPINCOUNT']}   (serial dispatch)"
    )
    if nec2c_id.get("path") is None:
        sys.exit("nec2c not on PATH — build it and symlink into ~/.local/bin")
    if "nec5" in args.engines:
        from antennaknobs.engines.nec5 import find_nec5

        nec5_exe = find_nec5()
        if nec5_exe is None:
            sys.exit(
                "nec5 lane requested but $NEC5_EXE does not resolve to an "
                "executable — point it at your licensed nec5cl binary"
            )
        print(f"nec5 lane: {nec5_exe}   captures: {args.nec5_capture_dir}")

    # Incremental JSONL mode: resume by skipping decks already recorded.
    jsonl = args.out if args.out and args.out.suffix == ".jsonl" else None
    done: dict[str, dict] = {}
    if jsonl and jsonl.exists():
        for line in jsonl.read_text().splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # torn final line from a killed run
            if "_meta" not in rec:
                done[rec["deck"]] = rec
        print(f"resume: {len(done)} decks already in {jsonl}, skipping those")
    elif jsonl:
        meta = {
            "_meta": {
                "corpus": str(corpus),
                "engines": list(args.engines),
                "timeout_s": args.timeout,
                "mem_limit_gb": args.mem_limit_gb,
                "nec2c": nec2c_id,
                "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        }
        jsonl.write_text(json.dumps(meta) + "\n")

    rows = list(done.values())
    for i, deck in enumerate(decks, 1):
        rel = str(deck.relative_to(corpus))
        if rel in done:
            continue
        print(f"[{i}/{len(decks)}] {rel} ...", flush=True)
        try:
            row = bench_deck(
                deck,
                args.engines,
                args.timeout,
                run_with_ground=not args.free_space,
                allow_intersections=args.allow_wire_intersections,
                mem_bytes=mem_bytes,
                rel_name=rel,
                nec5_capture_dir=(
                    args.nec5_capture_dir if "nec5" in args.engines else None
                ),
            )
        except Exception as e:  # noqa: BLE001 — a 20 h sweep must survive any
            # single deck (first bite: nec2c emitting raw 0xff into its output)
            row = {"deck": rel, "error": f"sweep-level: {type(e).__name__}: {e}"}
        rows.append(row)
        if jsonl:
            with jsonl.open("a") as f:
                f.write(json.dumps(row) + "\n")

    print_report(rows, args.engines)

    if args.out and not jsonl:
        args.out.write_text(json.dumps(rows, indent=2))
        print(f"\nfull results -> {args.out}")


if __name__ == "__main__":
    main()
