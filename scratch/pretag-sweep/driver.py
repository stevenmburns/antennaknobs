"""Pre-tag performance sweep driver (runs ON the bench box, stdlib only).

Plan once (enumerates the catalog through the given tree, writes cases.json):

  python3 driver.py plan --python PY --tree MW_TREE --ak-src AK_SRC --out cases.json

Run one arm (one fresh process per case, strictly sequential, resumable —
cases already present in --out are skipped):

  python3 driver.py run --python PY --tree MW_TREE --ak-src AK_SRC \\
      --cases cases.json --out results-<arm>.jsonl [--budget-min 60]

Every case runs as
  prlimit --as=<24 GiB> PY sweep.py --expect-tree MW_TREE --case JSON
with OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=4 and a per-run timeout; a timeout,
an address-space kill or a MemoryError is recorded as the case's result.

Before each case the box must be idle: 1-min load < 1, OR (because the 1-min
average still carries OUR previous 4-thread run for a minute or more) fewer
than 0.3 cores busy over a 2 s /proc/stat window, sampled twice. Both numbers
are recorded on the row.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GIB = 1024**3

DECKS = [
    "decks/3el-inverted-V.nec",
    "decks/3elYagiGain.nec",
    "decks/GndScreen.nec",
    "decks/moxon435_optimised.nec",
    "decks/ground_rod_efhw_wa7ark.nec",
]
GROUNDS = ("sommerfeld", "free", "fast")


def _env(tree: str, ak_src: str, threads: int = 4) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{Path(tree).resolve()}/src:{Path(ak_src).resolve()}"
    env["OMP_NUM_THREADS"] = str(threads)
    env["OPENBLAS_NUM_THREADS"] = str(threads)
    env["PYTHONWARNINGS"] = "ignore"
    return env


# --------------------------------------------------------------------- plan
def plan(a) -> None:
    out = subprocess.run(
        [a.python, str(HERE / "sweep.py"), "--expect-tree", a.tree, "--enumerate"],
        env=_env(a.tree, a.ak_src),
        capture_output=True,
        text=True,
        check=True,
    )
    census = json.loads(out.stdout.strip().splitlines()[-1])
    designs = census["designs"]

    def case(kind, design, ground, engine, tier, **extra):
        cid = f"{engine}|{ground}|{design}"
        if extra.get("params"):
            cid += "|" + ",".join(
                f"{k}={v}" for k, v in sorted(extra["params"].items())
            )
        return {
            "id": cid,
            "kind": kind,
            "design": design,
            "ground": ground,
            "engine": engine,
            "tier": tier,
            **extra,
        }

    cases = []
    near_ground = []
    for d in designs:
        grounds = ("sommerfeld",) if d.get("ground_requirement") else GROUNDS
        ng = bool(d.get("has_buried_wire")) or (d.get("zmin", 1.0) <= 1e-3)
        if ng:
            near_ground.append(d["design"])
        for g in grounds:
            tier = {"sommerfeld": 1, "free": 2, "fast": 4}[g]
            cases.append(case("catalog", d["design"], g, "default", tier))
            cases.append(case("catalog", d["design"], g, "razor-2p", 3 if ng else 5))
    # Named decks through the file-design path: every ground, both engines.
    for deck in DECKS:
        name = Path(deck).stem
        for g in GROUNDS:
            tier = {"sommerfeld": 1, "free": 2, "fast": 4}[g]
            cases.append(case("file", name, g, "default", tier, deck=deck))
            cases.append(case("file", name, g, "razor-2p", 3, deck=deck))
    # The momwire#1189 shape: 48 surface radials over Sommerfeld, twice —
    # through the catalog (BRV surface variant) and in plain momwire (#1131).
    p48 = {"variant": "surface", "n_radials": 48}
    for eng, tier in (("default", 1), ("razor-2p", 3)):
        cases.append(
            case(
                "catalog",
                "verticals.buried_radial_vertical",
                "sommerfeld",
                eng,
                tier,
                params=p48,
            )
        )
    for g, tier in (("sommerfeld", 1), ("fast", 4), ("free", 2)):
        cases.append(
            case("raw", "screen1131", g, "default", tier, params={"radials": 48})
        )
    # Stable order: tier, then the order above (sommerfeld first inside a tier).
    cases.sort(key=lambda c: c["tier"])
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    Path(a.out).write_text(
        json.dumps(
            {"census": census, "near_ground": near_ground, "cases": cases}, indent=1
        )
    )
    by_tier = {}
    for c in cases:
        by_tier[c["tier"]] = by_tier.get(c["tier"], 0) + 1
    print(
        f"{len(designs)} designs, {len(cases)} cases, by tier {dict(sorted(by_tier.items()))}"
    )
    print("near-ground:", near_ground)


# ---------------------------------------------------------------------- run
def _cpu_times():
    with open("/proc/stat") as f:
        parts = f.readline().split()[1:]
    v = [int(x) for x in parts]
    idle = v[3] + v[4]
    return sum(v), idle


def _busy_cores(dt: float = 2.0) -> float:
    t0, i0 = _cpu_times()
    time.sleep(dt)
    t1, i1 = _cpu_times()
    frac = 1.0 - (i1 - i0) / max(1, t1 - t0)
    return frac * (os.cpu_count() or 1)


def _load1() -> float:
    with open("/proc/loadavg") as f:
        return float(f.read().split()[0])


def wait_idle(max_wait: float = 1800.0) -> dict:
    t0 = time.time()
    while True:
        load = _load1()
        if load < 1.0:
            return {"load1": load, "busy_cores": None, "idle_wait_s": time.time() - t0}
        b1 = _busy_cores()
        if b1 < 0.3:
            b2 = _busy_cores()
            if b2 < 0.3:
                return {
                    "load1": load,
                    "busy_cores": max(b1, b2),
                    "idle_wait_s": time.time() - t0,
                }
        if time.time() - t0 > max_wait:
            return {
                "load1": load,
                "busy_cores": b1,
                "idle_wait_s": time.time() - t0,
                "idle_gave_up": True,
            }
        time.sleep(3)


def _classify_dead(rc: int, stderr: str, timed_out: bool) -> tuple[str, str]:
    tail = stderr.strip()[-800:]
    if timed_out:
        return "timeout", tail
    low = stderr.lower()
    if any(
        s in low
        for s in (
            "memoryerror",
            "bad_alloc",
            "cannot allocate",
            "unable to allocate",
            "memory allocation",
        )
    ):
        return "oom", tail
    if rc < 0:
        return "killed", f"signal {-rc}: {tail}"
    return "error", f"rc={rc}: {tail}"


def run_one(a, case: dict, threads: int = 4) -> dict:
    cmd = [
        "prlimit",
        f"--as={int(a.as_gb * GIB)}",
        a.python,
        str(HERE / "sweep.py"),
        "--expect-tree",
        a.tree,
        "--case",
        json.dumps(case),
    ]
    t0 = time.perf_counter()
    p = subprocess.Popen(
        cmd,
        env=_env(a.tree, a.ak_src, threads),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    timed_out = False
    try:
        out, err = p.communicate(timeout=a.timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(p.pid, signal.SIGKILL)  # our own session only, by PID
        out, err = p.communicate()
    proc_wall = time.perf_counter() - t0
    rec = None
    for line in (out or "").splitlines():
        if line.startswith("SWEEP_RESULT "):
            rec = json.loads(line[len("SWEEP_RESULT ") :])
    if rec is None:
        outcome, msg = _classify_dead(p.returncode, err or "", timed_out)
        rec = {"id": case["id"], "case": case, "outcome": outcome, "message": msg}
    rec["proc_wall_s"] = proc_wall
    rec["rc"] = p.returncode
    rec["timeout_s"] = a.timeout
    return rec


def run(a) -> None:
    doc = json.loads(Path(a.cases).read_text())
    cases = doc["cases"]
    if a.only:
        cases = [c for c in cases if any(s in c["id"] for s in a.only)]
    if a.max_tier:
        cases = [c for c in cases if c["tier"] <= a.max_tier]
    out = Path(a.out)
    done = set()
    if out.is_file():
        for line in out.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["id"])
    todo = [c for c in cases if c["id"] not in done]
    print(f"{len(cases)} cases, {len(done)} done, {len(todo)} to run", flush=True)
    t_start = time.time()
    for i, c in enumerate(todo):
        if a.budget_min and (time.time() - t_start) > a.budget_min * 60:
            print(f"budget reached; {len(todo) - i} cases not started", flush=True)
            break
        idle = wait_idle()
        rec = run_one(a, c)
        rec.update(idle)
        rec["arm"] = a.arm
        rec["host"] = os.uname().nodename
        rec["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with out.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        w = rec.get("wall_s")
        print(
            f"[{i + 1}/{len(todo)}] {c['id']}: {rec['outcome']}"
            f" wall={w if w is None else round(w, 2)} rss={round(rec.get('ru_maxrss_mb') or 0)}MB"
            f" proc={rec['proc_wall_s']:.1f}s",
            flush=True,
        )


# --------------------------------------------------------------------- fast
# The release-path sweep (2026-09-24). The serial run above spent more time
# proving the box idle than solving: 0.63.0's 643 cases were 18 min of
# processes, but ~26 min of load-average waits plus ~43 min of the gate's
# own 2 s CPU samples. Only a couple of dozen cases are long enough for a
# wall time to mean anything.
#
# So: every case NOT in timed.txt runs in parallel (--jobs workers, one
# BLAS/OpenMP thread each, one idle check before the batch), recording
# outcome, peak RSS and Z; then the timed.txt cases run one at a time, 4
# threads, idle-gated, as `run` does. Rows carry `mode` ("par1" / "timed"),
# and analyze.py compares memory and wall only between rows of the same mode:
# a process's peak RSS depends on its thread count (per-thread BLAS buffers).
def _timed_ids() -> list[str]:
    lines = (HERE / "timed.txt").read_text().splitlines()
    return [ln.split("#", 1)[0].strip() for ln in lines if ln.split("#", 1)[0].strip()]


def fast(a) -> None:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from threading import Lock

    cases = json.loads(Path(a.cases).read_text())["cases"]
    by_id = {c["id"]: c for c in cases}
    timed = _timed_ids()
    missing = [t for t in timed if t not in by_id]
    if missing:
        raise SystemExit(f"timed.txt names cases not in {a.cases}: {missing}")
    out = Path(a.out)
    done = set()
    if out.is_file():
        done = {json.loads(ln)["id"] for ln in out.read_text().splitlines() if ln}
    tset = set(timed)
    par = [c for c in cases if c["id"] not in tset and c["id"] not in done]
    ser = [by_id[t] for t in timed if t not in done]
    # Longest-first shortens the batch's tail; the order is a hint only.
    hint = {}
    if a.order_by and Path(a.order_by).is_file():
        for ln in Path(a.order_by).read_text().splitlines():
            if ln:
                r = json.loads(ln)
                hint[r["id"]] = r.get("proc_wall_s") or 0.0
    par.sort(key=lambda c: -hint.get(c["id"], 0.0))
    print(
        f"{len(cases)} cases: {len(par)} parallel (x{a.jobs}), {len(ser)} timed, "
        f"{len(done)} already done",
        flush=True,
    )
    lock = Lock()
    t0 = time.time()

    def record(rec, mode, extra=None):
        rec.update(extra or {})
        rec.update(
            mode=mode,
            arm=a.arm,
            host=os.uname().nodename,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        with lock, out.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    idle = wait_idle()
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futs = {pool.submit(run_one, a, c, 1): c for c in par}
        for n, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            record(rec, "par1", {"batch_idle": idle})
            if rec["outcome"] != "ok" or n % 50 == 0 or n == len(par):
                print(
                    f"[par {n}/{len(par)} {time.time() - t0:.0f}s] "
                    f"{rec['id']}: {rec['outcome']}",
                    flush=True,
                )
    t_par = time.time() - t0
    for n, c in enumerate(ser, 1):
        idle = wait_idle()
        rec = run_one(a, c, 4)
        record(rec, "timed", idle)
        w = rec.get("wall_s")
        print(
            f"[timed {n}/{len(ser)}] {c['id']}: {rec['outcome']}"
            f" wall={w if w is None else round(w, 2)}"
            f" rss={round(rec.get('ru_maxrss_mb') or 0)}MB",
            flush=True,
        )
    print(
        f"done: parallel {t_par / 60:.1f} min, timed "
        f"{(time.time() - t0 - t_par) / 60:.1f} min, total "
        f"{(time.time() - t0) / 60:.1f} min",
        flush=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "fast"):
        s = sub.add_parser(name)
        s.add_argument("--python", required=True)
        s.add_argument(
            "--tree", required=True, help="momwire tree (its src/ is imported)"
        )
        s.add_argument("--ak-src", required=True, help="antennaknobs src/ directory")
        s.add_argument("--out", required=True)
        if name in ("run", "fast"):
            s.add_argument("--cases", required=True)
            s.add_argument("--arm", required=True, help="label, e.g. v0.62.0")
            s.add_argument("--timeout", type=float, default=600.0)
            s.add_argument("--as-gb", type=float, default=24.0)
        if name == "run":
            s.add_argument("--budget-min", type=float, default=0.0)
            s.add_argument("--max-tier", type=int, default=0)
            s.add_argument(
                "--only", nargs="*", default=None, help="substring filter on case id"
            )
        if name == "fast":
            s.add_argument("--jobs", type=int, default=8)
            s.add_argument(
                "--order-by",
                default=None,
                help="an earlier results .jsonl: run its slowest cases first",
            )
    a = ap.parse_args()
    a.tree = str(Path(a.tree).resolve())
    {"plan": plan, "run": run, "fast": fast}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
