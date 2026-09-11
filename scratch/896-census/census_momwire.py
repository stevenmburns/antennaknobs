"""AK#896: run momwire over the public NEC corpus, in the corpus tool's own
report format so its `compare` can join the two engines.

    python scratch/896-census/census_momwire.py --src ~/nec5-timing/nec5 \
        --report ~/nec5-timing/check-momwire.jsonl

ONE DECK PER SUBPROCESS, and that is not ceremony. The first version of this
script called `run_deck` in-process, bounded only by a segment cap, on the
reasoning that a dense 4,000^2 complex matrix is about 256 MB. Run for real, it
reached **8.9 GB RSS** two minutes in and was still climbing when it was killed,
on a stretch of the corpus whose decks are all under the cap.

Whether that was one deck or an accumulation across many was never established
— and that is the point. In one process the two are indistinguishable from the
outside, so there is no bound to be had: the segment count is not the number of
unknowns, an `FR` sweep multiplies the work behind it, and a shared heap hides
which deck is responsible. A cap on deck SIZE bounds neither solve TIME nor
MEMORY. (Measured separately afterwards, `Bowtie.nec` — 5,328 segments across 29
frequencies — runs past 200 s at 1.9 GB on its own, so the slow tail is real
whatever the 8.9 GB was.)

So each deck now runs in a child process with a real wall timeout and an
address-space rlimit, exactly as the NEC-5 side runs its binary. A runaway deck
dies as a `crash` row with its exit code, and the census keeps going. The cost
is a 0.49 s interpreter start per deck (measured) — about 25 minutes over the
corpus, which is the price of being unable to bound an in-process solve.

Then, with the NEC-5 side's report from the same tree:

    python scripts/nec5_corpus/nec5_corpus.py compare \
        ~/nec5-timing/check-base.jsonl ~/nec5-timing/check-momwire.jsonl \
        --ignore-env --tol 1e-4

WHY THIS IS A SEPARATE SCRIPT. `nec5_corpus.py` is a single-file, stdlib-only,
frozen-and-signed release artifact (#1376); importing momwire into it would end
that. So this writes the SAME JSONL schema instead — a `{"_meta": ...}` header
line then one `{file, status, exit_code, wall_s, error, z}` object per deck —
and `compare` joins the two sides unmodified.

WHICH DECKS. The TRANSLATED tree (`nec5/`), not the raw one, and that is the
opposite of the obvious choice. momwire speaks NEC-2 and the translated decks
are NEC-5 dialect, yet measured on one 150-deck sample momwire answers 122/150
(81 %) after translation against 88/150 (59 %) before. The cause is `SY`: 680
raw decks carry 4nec2 symbolic variables and none of the translated ones do,
because `translate` expands them. Running raw would drop the corpus's most
heavily parameterised models and report that as a momwire limitation. Running
translated also makes the join exact by construction — the same bytes go into
both engines.

The cost, which the census states as its instrument's caveat rather than hiding:
roughly 11 decks in 150 answer BEFORE translation and not after, almost all
`LD <n> conductivity on a partial-wire segment range` on Cebik files. That is a
defect in our translator, not in momwire.

WHY NOT `nec5_corpus._aip`. It wants an ANTENNA INPUT PARAMETERS row of exactly
12 tokens with the impedance at 7/8, which is NEC-5's layout. momwire's portal
writes a NEC-2 printout: 11 tokens, impedance at 6/7. Measured: `_aip` reads
zero of 134 momwire printouts. So the parser here is
`antennaknobs.engines.nec2.NEC2Engine._parse_input_parameters`, which is the
already-tested reader for exactly that layout, rather than a third scraper.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import platform
import re
import subprocess
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "nec5_corpus"))

# Segment cap, from the distribution: over the 3,076 translated decks the median
# is 89 segments, p99 is 1,428 and the maximum is 39,020 (Patch.nec). 4,000
# leaves 6 decks out, recorded as `over-cap` — which is NOT a momwire failure and
# must never be counted as one.
#
# It is a cheap PRE-FILTER and nothing more. It is decidable from the text before
# an engine is handed the deck, which is its only virtue; it does not bound
# memory (a sub-cap deck reached 8.9 GB) and it does not bound time. The rlimit
# and the timeout below are what actually bound a deck.
SEG_CAP = 4000

# Matches the NEC-5 side's `check --timeout` so the two columns are comparable.
TIMEOUT_S = 300.0

# Address-space ceiling per child. Generous enough that no deck is refused for
# being merely large, small enough that one runaway cannot take the box: this
# corpus ran against 46 GB of RAM, and a census that OOMs the machine loses every
# result it had not yet flushed.
MEM_GB = 6.0

_GW_RE = re.compile(r"^\s*GW\b", re.I)


def deck_segments(body: str) -> int:
    """Total GW segments, for the cap. Deliberately a text scan and not a parse:
    the cap has to be decidable BEFORE handing the deck to an engine that might
    spend a minute on it, and a deck too big to solve is often too odd to parse.
    """
    n = 0
    for line in body.splitlines():
        if not _GW_RE.match(line):
            continue
        toks = line.split()
        if len(toks) > 2:
            try:
                n += int(float(toks[2]))
            except ValueError:
                pass
    return n


def run_one_in_process(body: str) -> dict:
    """One deck through momwire's portal, scored in the corpus tool's status
    vocabulary so the two engines' reports are joinable. CHILD-SIDE: this runs
    inside the subprocess `run_one` spawns, which is what bounds it.

    `ok-no-source` is a real answer, not a failure: a plane-wave or
    geometry-only deck has nothing to print, and the NEC-5 side scores it the
    same way. Conflating it with `error` would invent disagreements out of decks
    on which both engines correctly said nothing.
    """
    from momwire.portal import run_deck

    from antennaknobs.engines.nec2 import NEC2Engine

    rec: dict = {"status": "error", "exit_code": 0, "error": None, "z": []}
    t0 = time.perf_counter()
    # Advisories are census OUTPUT, not noise. momwire raises real ones on
    # corpus decks ("treat its impedance as indicative rather than predictive"),
    # and an engine that says so and is then scored as if it had said nothing is
    # being misreported. `record=True` is the only reading that works: an outer
    # catch_warnings without it records zero by construction.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            out, err = run_deck(body)
        except BaseException as exc:  # noqa: BLE001 — a census survives any deck
            rec["status"] = "crash"
            rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
            rec["wall_s"] = round(time.perf_counter() - t0, 4)
            rec["advisories"] = _advisories(caught)
            return rec
    rec["wall_s"] = round(time.perf_counter() - t0, 4)
    rec["advisories"] = _advisories(caught)

    blob = out + ("\n" + err if err else "")
    if "ANTENNA INPUT PARAMETERS" in out:
        try:
            freqs = NEC2Engine._parse_input_parameters(out)
        except Exception as exc:  # noqa: BLE001 — an unreadable section is a status
            rec["status"] = "no-impedance"
            rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
            return rec
        rec["status"] = "ok"
        # The corpus tool's row shape: [tag, seg, Zre, Zim], first frequency
        # only — `_first_z` reads row 0, and a multi-point FR sweep prints one
        # section per frequency.
        rec["z"] = [[t, s_, z.real, z.imag] for t, s_, z in freqs[0]]
        return rec

    m = re.search(r"ERROR:?\s*(.+)", blob)
    if m:
        rec["status"] = "error"
        rec["error"] = m.group(1).strip()[:300]
    elif "no EX card" in blob or "EX" not in body.upper():
        rec["status"] = "ok-no-source"
    else:
        rec["status"] = "no-impedance"
        rec["error"] = "no ANTENNA INPUT PARAMETERS and no ERROR line"
    return rec


def run_one(path: Path, timeout: float, mem_gb: float) -> dict:
    """PARENT-SIDE: one deck in its own bounded child.

    Returns a record whatever happens. A child that is killed by the wall clock
    is `timeout`; one killed by the address-space rlimit, by the OOM killer, or
    by a segfault is `crash` with its exit code — all of which are answers about
    the deck, and none of which may take the census down with them.
    """
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--one",
                str(path),
                "--mem-gb",
                str(mem_gb),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "exit_code": 0,
            "error": f"no answer in {timeout:g} s",
            "z": [],
            "wall_s": round(time.perf_counter() - t0, 4),
            "advisories": [],
        }
    wall = round(time.perf_counter() - t0, 4)
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            rec = json.loads(proc.stdout.strip().splitlines()[-1])
            rec["wall_s"] = wall  # the parent's clock includes interpreter start
            return rec
        except (ValueError, IndexError):
            pass
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return {
        "status": "crash",
        "exit_code": proc.returncode,
        "error": (tail[-1][:300] if tail else f"exit {proc.returncode}, no output"),
        "z": [],
        "wall_s": wall,
        "advisories": [],
    }


def _advisories(caught) -> list:
    """Advisory class names with counts — the class is the fact, the prose is
    long and identical every time."""
    out: dict[str, int] = {}
    for w in caught:
        name = getattr(w.category, "__name__", str(w.category))
        out[name] = out.get(name, 0) + 1
    return [[k, v] for k, v in sorted(out.items())]


def environment_meta(jobs: int) -> dict:
    import momwire

    return {
        "engine": "momwire",
        "momwire_version": getattr(momwire, "__version__", "?"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "jobs": jobs,
        "thread_env": {
            k: os.environ.get(k)
            for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
        "seg_cap": SEG_CAP,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", default=str(Path.home() / "nec5-timing" / "nec5"))
    ap.add_argument("--report", default="check-momwire.jsonl")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=TIMEOUT_S)
    ap.add_argument("--cap", type=int, default=SEG_CAP)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default=None)
    ap.add_argument("--mem-gb", type=float, default=MEM_GB)
    ap.add_argument(
        "--one",
        default=None,
        help="CHILD MODE: solve this one deck, print its record as JSON, exit",
    )
    a = ap.parse_args(argv)

    if a.one:
        # The bound that the segment cap could not provide. RLIMIT_AS makes an
        # over-large allocation raise MemoryError inside the child instead of
        # the kernel choosing a victim process on a loaded box.
        try:
            import resource

            cap = int(a.mem_gb * (1 << 30))
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        except (ImportError, ValueError, OSError):
            pass  # not POSIX, or the limit is already lower — the timeout still holds
        body = Path(a.one).read_text(encoding="latin-1", errors="replace")
        print(json.dumps(run_one_in_process(body)))
        return 0

    from nec5_corpus import _is_deck_name

    src = Path(a.src).expanduser()
    decks = [
        p
        for p in sorted(src.rglob("*"))
        if p.is_file() and _is_deck_name(p.name) and p.name != "LICENSES.md"
    ]
    if a.only:
        decks = [p for p in decks if a.only in p.as_posix()]
    if a.limit:
        decks = decks[: a.limit]

    # Pin the engine to one thread per worker, or the per-deck wall times are
    # uninterpretable — the same discipline `check` carries as `timing_valid`.
    pinned = {}
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        if k not in os.environ:
            os.environ[k] = "1"
            pinned[k] = "1"
    timing_valid = a.jobs * 1 <= (os.cpu_count() or 1)

    out = open(a.report, "w", encoding="utf-8")
    out.write(
        json.dumps(
            {
                "_meta": {
                    "tool": "census_momwire.py",
                    "version": "1.0",
                    "step": "check",
                    "exe": "momwire.portal.run_deck",
                    "platform": sys.platform,
                    "timeout_s": a.timeout,
                    "timing_valid": timing_valid,
                    "src": str(src),
                    "pinned": pinned,
                    "environment": environment_meta(a.jobs),
                    "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            }
        )
        + "\n"
    )

    counts: dict[str, int] = {}
    errors: dict[str, int] = {}
    advis: dict[str, int] = {}
    t0 = time.perf_counter()

    def one(p: Path) -> dict:
        segs = deck_segments(p.read_text(encoding="latin-1", errors="replace"))
        if segs > a.cap:
            rec = {
                "status": "over-cap",
                "exit_code": 0,
                "error": f"{segs} segments over the {a.cap} cap",
                "z": [],
                "wall_s": 0.0,
                "advisories": [],
            }
        else:
            rec = run_one(p, a.timeout, a.mem_gb)
        rec["file"] = p.relative_to(src).as_posix()
        rec["segments"] = segs
        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        for i, rec in enumerate(pool.map(one, decks), 1):
            counts[rec["status"]] = counts.get(rec["status"], 0) + 1
            if rec.get("error"):
                key = re.sub(r"[-+]?\d+(\.\d+)?", "N", rec["error"])[:80]
                errors[key] = errors.get(key, 0) + 1
            for name, n in rec.get("advisories", []):
                advis[name] = advis.get(name, 0) + n
            out.write(json.dumps(rec) + "\n")
            # Flush every row. `pool.map` yields IN ORDER, so one slow deck
            # holds the writer while later workers race ahead — `Parab50.nec`
            # blocked it for two and a half minutes on the first real run, and
            # a fifteen-minute census that dies at minute fourteen with a
            # buffered file has written nothing at all.
            out.flush()
            if i % 200 == 0:
                print(f"  {i}/{len(decks)}  {counts}", flush=True)
    out.close()

    print(f"\n{len(decks)} decks in {time.perf_counter() - t0:.0f} s: {counts}")
    if advis:
        print("\nadvisories, by class:")
        for k, v in sorted(advis.items(), key=lambda kv: -kv[1]):
            print(f"  {v:5d}  {k}")
    if errors:
        print("\nrefusals and errors, by message:")
        for k, v in sorted(errors.items(), key=lambda kv: -kv[1])[:25]:
            print(f"  {v:5d}  {k}")
    print(f"\nreport: {a.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
