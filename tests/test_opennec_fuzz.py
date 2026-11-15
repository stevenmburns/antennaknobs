"""Crash-fuzz the optional OpenNEC engine (pyopennec's porty interface).

Condition for putting OpenNEC on the hosted app: no input AK accepts may kill
the process (abort, segfault, exit, hang). A Python exception is a PASS (the
request is refused); a returned NaN/inf is reported apart (a wrong answer, not
a crash). This is the dynamic half of a static review of every assert/exit
site in the C.

Two entry paths, seeded and deterministic:

* ``porty``: ``pyopennec.porty.Structure(...).solve(freqs)`` (+ ``far_field``);
* ``ak``: ``OpenNECEngine`` on a builder made from generated NEC deck text via
  ``file_designs.builder_from_text``; ``impedance()`` and sometimes
  ``far_field()`` / ``current_distribution()`` / ``impedance_sweep()``.

Every case runs in its OWN forked process (the imports are paid once, in the
parent, which never solves), under an address-space limit and a SIGALRM that
kills a hang. The parent classifies the exit status:

    finite | exception | nan   -> the child reported, exit 0
    CRASH                      -> killed by a signal / exit without a report
    HANG                       -> SIGALRM

The CI slice (~50 cases) runs by default. The large mode is manual:

    AK_FUZZ_CASES=5000 AK_FUZZ_SEED=1 AK_FUZZ_OUT=/some/dir \
        .venv/bin/python tests/test_opennec_fuzz.py

and prints a summary (counts by path / mutation class / outcome, top exception
messages, reproducers for every CRASH/HANG saved under AK_FUZZ_OUT).
"""

from __future__ import annotations

import collections
import dataclasses
import json
import math
import os
import random
import resource
import signal
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

import numpy as np
import pytest

from antennaknobs.engines import opennec as opennec_mod

needs_opennec = pytest.mark.skipif(
    opennec_mod.porty is None, reason="pyopennec (porty) not installed"
)

AS_LIMIT = 2 * 1024**3
TIMEOUT_S = 60
NAN, INF = float("nan"), float("inf")

# ---------------------------------------------------------------- generator

_SPECIAL = [NAN, INF, -INF, 0.0, -0.0, -1.0, 5e-324, 1e-300, 1e300]


def _scale(rng):
    """A length scale across the whole float range, weighted to usable."""
    return rng.choice(
        [1e-12, 1e-9, 1e-6, 1e-3, 1e-2, 0.1, 1.0, 1.0, 5.0, 10.0, 100.0, 1e3, 1e6, 1e9]
    )


def _vec(rng, s):
    return [rng.uniform(-1, 1) * s for _ in range(3)]


def _ulps(x, k):
    for _ in range(k):
        x = math.nextafter(x, INF)
    return x


def _base(rng):
    """A small ordinary structure: 1-3 wires around a few metres."""
    wires = []
    for tag in range(1, rng.randint(1, 3) + 1):
        p1 = [rng.uniform(-3, 3), rng.uniform(-3, 3), rng.uniform(1, 8)]
        p2 = [a + rng.uniform(-6, 6) for a in p1]
        p2[2] = abs(p2[2]) + 0.5
        wires.append([tag, rng.randint(1, 15), p1, p2, rng.choice([1e-3, 2e-3, 5e-3])])
    return {
        "wires": wires,
        "ports": [[1, 1 + wires[0][1] // 2]],
        "loads": [],
        "ground": None,
        "ek": False,
        "freqs": [rng.choice([3.5, 7.1, 14.2, 28.5, 146.0])],
        "far": False,
        "ak_ground": None,
    }


def _m_len_extreme(c, rng):
    s = _scale(rng)
    for w in c["wires"]:
        d = [rng.uniform(-1, 1) for _ in range(3)]
        w[2] = [rng.uniform(-1, 1) * s * 0.1 for _ in range(3)]
        w[3] = [a + b * s for a, b in zip(w[2], d, strict=True)]


def _m_ulp(c, rng):
    w = rng.choice(c["wires"])
    k = rng.randint(1, 4)
    w[3] = [_ulps(a, k) if rng.random() < 0.7 else a for a in w[2]]


def _m_short_vs_radius(c, rng):
    w = rng.choice(c["wires"])
    ln = math.dist(w[2], w[3]) or 1.0
    w[4] = ln * rng.choice([0.01, 0.5, 1.0, 2.0, 100.0]) / max(w[1], 1)


def _m_bad_numeric(c, rng):
    w = rng.choice(c["wires"])
    which = rng.choice(["p1", "p2", "r", "nseg", "freq", "ld", "port"])
    v = rng.choice(_SPECIAL)
    if which == "p1":
        w[2][rng.randrange(3)] = v
    elif which == "p2":
        w[3][rng.randrange(3)] = v
    elif which == "r":
        w[4] = v
    elif which == "nseg":
        w[1] = rng.choice([0, -1, 2**31, 2**31 - 1, 10**6])
    elif which == "freq":
        c["freqs"] = [v]
    elif which == "ld":
        c["loads"].append([rng.randint(0, 5), w[0], 0, 0, v, v, v])
    else:
        c["ports"] = [[rng.choice([w[0], 0, -1, 9999]), rng.choice([0, -1, 2**31])]]


def _m_touching(c, rng):
    a = c["wires"][0]
    n = len(c["wires"]) + 1
    kind = rng.choice(["coincident", "overlap", "endpoint", "cross", "tee"])
    if kind == "coincident":
        w = [n, a[1], list(a[2]), list(a[3]), a[4]]
    elif kind == "overlap":
        mid = [(p + q) / 2 for p, q in zip(a[2], a[3], strict=True)]
        w = [n, a[1], mid, list(a[3]), a[4]]
    elif kind == "endpoint":
        w = [n, a[1], list(a[3]), [a[3][0] + 1, a[3][1], a[3][2] + 1], a[4]]
    elif kind == "cross":
        mid = [(p + q) / 2 for p, q in zip(a[2], a[3], strict=True)]
        w = [n, a[1], [mid[0] - 1, mid[1], mid[2]], [mid[0] + 1, mid[1], mid[2]], a[4]]
    else:  # tee at an odd angle, 1 deg off
        mid = [(p + q) / 2 for p, q in zip(a[2], a[3], strict=True)]
        w = [n, a[1], mid, [mid[0] + 2, mid[1] + 0.03, mid[2]], a[4]]
    c["wires"].append(w)


def _m_ground_z(c, rng):
    c["ground"] = rng.choice(
        ["perfect", ["reflection", 13.0, 0.005], ["sommerfeld", 13.0, 0.005]]
    )
    zt = rng.choice([0.0, 1e-15, 1e-9, 1e-3, -1e-9, -1e-3, -0.5, -50.0, 1e-6])
    for w in c["wires"]:
        shift = zt - min(w[2][2], w[3][2])
        if rng.random() < 0.5:  # the lowest end at zt
            w[2][2] += shift
            w[3][2] += shift
    if rng.random() < 0.3:
        c["wires"][0][2][2] = zt


def _m_ground_params(c, rng):
    kind = rng.choice(["reflection", "sommerfeld", "perfect"])
    eps = rng.choice([1.0, 1.0001, 2.0, 13.0, 81.0, 1e3, 1e6, 0.0, -5.0, NAN, INF])
    sig = rng.choice([0.0, 1e-9, 0.005, 1.0, 1e3, 1e6, -1.0, NAN, INF])
    c["ground"] = "perfect" if kind == "perfect" else [kind, eps, sig]


def _m_big(c, rng):
    n = rng.choice([200, 500, 1000, 2000, 3000])
    c["wires"][0][1] = n
    c["ports"] = [[c["wires"][0][0], rng.choice([1, n // 2, n])]]
    if rng.random() < 0.4:
        c["wires"] = c["wires"][:1]


def _m_freq(c, rng):
    c["freqs"] = [
        rng.choice(
            [1e-9, 1e-6, 1e-3, 0.01, 0.1, 300.0, 1e3, 1e5, 1e7, 1e12, 1e300, 5e-324]
        )
    ]
    if rng.random() < 0.3:
        c["freqs"] = sorted(rng.choice([0.5, 14.0, 14.0, 150.0, 1e4]) for _ in range(3))


def _m_loads(c, rng):
    w = rng.choice(c["wires"])
    typ = rng.randint(0, 5)
    vals = [
        rng.choice([0.0, 1.0, 50.0, -50.0, 1e-12, 1e12, 1e300, NAN, INF, -INF, 1e-300])
        for _ in range(3)
    ]
    sf = rng.choice([0, 1, 1, w[1], w[1] + 5, -1, 2])
    st = rng.choice([0, sf, sf + 1, w[1], 0, 1 << 20])
    c["loads"].append([typ, rng.choice([w[0], 0, 99]), sf, st, *vals])


def _m_ports(c, rng):
    w = rng.choice(c["wires"])
    n = w[1]
    c["ports"] = [
        [w[0], rng.choice([1, n, max(n // 2, 1), n + 1, 0, -1])]
        for _ in range(rng.randint(1, 3))
    ]
    if rng.random() < 0.2:
        c["ports"] = []


def _m_kernel(c, rng):
    c["ek"] = True


def _m_far(c, rng):
    c["far"] = True


_MUT = {
    "len_extreme": _m_len_extreme,
    "ulp": _m_ulp,
    "short_vs_radius": _m_short_vs_radius,
    "bad_numeric": _m_bad_numeric,
    "touching": _m_touching,
    "ground_z": _m_ground_z,
    "ground_params": _m_ground_params,
    "big": _m_big,
    "freq": _m_freq,
    "loads": _m_loads,
    "ports": _m_ports,
    "kernel": _m_kernel,
    "far_field": _m_far,
}
_WEIGHTS = {"big": 0.4, "far_field": 2.0, "kernel": 2.0}


def make_case(seed, i, allow_big=True):
    rng = random.Random(f"{seed}:{i}")
    c = _base(rng)
    names = list(_MUT)
    w = [_WEIGHTS.get(n, 1.0) for n in names]
    classes = []
    for _ in range(rng.choice([1, 1, 2, 2, 3])):
        n = rng.choices(names, w)[0]
        if n == "big" and not allow_big:
            continue
        if n not in classes:
            classes.append(n)
            _MUT[n](c, rng)
    c["path"] = rng.choice(["porty", "ak"])
    c["classes"] = classes
    c["id"] = f"{seed}:{i}"
    c["sweep"] = rng.random() < 0.15
    c["cd"] = rng.random() < 0.3
    if c["path"] == "ak":
        c["ak_ground"] = _ak_ground(c, rng)
        c["deck"] = deck_text(c)
    return c


def _ak_ground(c, rng):
    g = c["ground"]
    if g is None:
        return rng.choice([None, "free"])
    if g == "perfect":
        return "pec"
    kind, e, s = g
    if kind == "sommerfeld":
        return ["finite", e, s]
    return [rng.choice(["finite-fast", "mininec"]), e, s]


def _n(x):
    if isinstance(x, float):
        return (
            repr(x)
            if math.isfinite(x)
            else ("nan" if x != x else ("inf" if x > 0 else "-inf"))
        )
    return str(x)


def deck_text(c):
    L = ["CM fuzz", "CE"]
    for tag, nseg, p, q, r in c["wires"]:
        L.append("GW " + " ".join(_n(v) for v in [tag, nseg, *p, *q, r]))
    g = c["ground"]
    L.append("GE 1" if g else "GE 0")
    if g == "perfect":
        L.append("GN 1")
    elif g:
        L.append(f"GN {2 if g[0] == 'sommerfeld' else 0} 0 0 0 {_n(g[1])} {_n(g[2])}")
    for ld in c["loads"]:
        L.append("LD " + " ".join(_n(v) for v in ld))
    if c["ek"]:
        L.append("EK")
    L.append("FR 0 1 0 0 " + _n(c["freqs"][0]) + " 0")
    for tag, seg in c["ports"]:
        L.append(f"EX 0 {tag} {seg} 0 1 0")
    L += ["RP 0 19 37 1000 0 0 5 10", "EN"]
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ the case


def _all_finite(x):
    if x is None or isinstance(x, (str, bool)):
        return True
    if isinstance(x, np.ndarray):
        return x.dtype.kind not in "fc" or bool(np.isfinite(x).all())
    if isinstance(x, (int, np.integer)):
        return True
    if isinstance(x, (float, complex, np.floating, np.complexfloating)):
        return bool(np.isfinite(x))
    if isinstance(x, dict):
        return all(_all_finite(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return all(_all_finite(v) for v in x)
    if dataclasses.is_dataclass(x):
        return all(_all_finite(getattr(x, f.name)) for f in dataclasses.fields(x))
    if hasattr(x, "__dict__"):
        return all(_all_finite(v) for v in vars(x).values())
    return True


def _ground_porty(g):
    return tuple(g) if isinstance(g, list) else g


def run_case(c):
    """Run one case in THIS process. Returns the list of results to be
    checked for finiteness (an exception propagates)."""
    out = []
    if c["path"] == "porty":
        from pyopennec import porty

        wires = [(t, n, tuple(p), tuple(q), r) for t, n, p, q, r in c["wires"]]
        s = porty.Structure(
            wires,
            ports=[tuple(p) for p in c["ports"]],
            ground=_ground_porty(c["ground"]),
            loads=[tuple(x) for x in c["loads"]],
            extended_kernel=c["ek"],
        )
        sol = s.solve(c["freqs"])
        out += [sol.y, sol.currents]
        if c["far"] and sol.nports:
            ff = porty.far_field(
                sol,
                0,
                np.ones(sol.nports, complex),
                [0.0, 45.0, 90.0, 179.0],
                [0.0, 90.0, 0.0, 180.0],
            )
            out.append(ff)
    else:
        from antennaknobs.engines.opennec import OpenNECEngine
        from antennaknobs.file_designs import builder_from_text

        b = builder_from_text("fuzz.nec", c["deck"])()
        g = c["ak_ground"]
        eng = OpenNECEngine(b, ground=tuple(g) if isinstance(g, list) else g)
        out.append(eng.impedance())
        if c["sweep"]:
            out.append(
                eng.impedance_sweep([c["freqs"][0] * f for f in (0.9, 1.0, 1.1)])
            )
        if c["cd"]:
            out.append(eng.current_distribution())
        if c["far"]:
            out.append(eng.far_field())
    return out


def _child(c, wfd, errpath):
    try:
        resource.setrlimit(resource.RLIMIT_AS, (AS_LIMIT, AS_LIMIT))
        fd = os.open(errpath, os.O_WRONLY | os.O_TRUNC)
        os.dup2(fd, 2)
        os.dup2(fd, 1)
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.alarm(TIMEOUT_S)
        try:
            res = run_case(c)
            r = {"o": "finite" if _all_finite(res) else "nan"}
        except SystemExit as e:
            r = {"o": "sysexit", "e": f"SystemExit({e.code})"}
        except BaseException as e:  # noqa: BLE001 — the point: any Python exception is a refusal
            r = {"o": "exception", "e": f"{type(e).__name__}: {str(e)[:200]}"}
        os.write(wfd, json.dumps(r).encode())
    finally:
        os._exit(0)


def run_forked(c):
    """One case in its own forked process. Returns (outcome, detail)."""
    rfd, wfd = os.pipe()
    with tempfile.NamedTemporaryFile(delete=False) as t:
        errpath = t.name
    pid = os.fork()
    if pid == 0:
        os.close(rfd)
        _child(c, wfd, errpath)
    os.close(wfd)
    _, status = os.waitpid(pid, 0)
    raw = os.read(rfd, 1 << 16)
    os.close(rfd)
    tail = Path(errpath).read_text(errors="replace")[-300:].strip()
    os.unlink(errpath)
    if os.WIFSIGNALED(status):
        sig = os.WTERMSIG(status)
        if sig == signal.SIGALRM:
            return "HANG", f"no result in {TIMEOUT_S}s"
        return "CRASH", f"signal {signal.Signals(sig).name}: {tail}"
    if not raw:
        return "CRASH", f"exit {os.WEXITSTATUS(status)} without a report: {tail}"
    r = json.loads(raw)
    return r["o"], r.get("e", "")


def run_cases(cases):
    """``run_forked`` over `cases`, from a COLD helper process.

    Forking from a process that has already run a solve deadlocks the child:
    libgomp / OpenBLAS have started their thread pools in the parent, and a
    forked child inherits the locks but not the threads. Inside pytest that is
    the usual state (an earlier test solved), so every in-process fork there
    hangs, even on an ordinary 14 MHz dipole. The helper imports the engine
    but never solves, so each of its forks starts with no pool at all.
    """
    p = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--zygote"],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        timeout=len(cases) * (TIMEOUT_S + 5) + 120,
        check=False,
    )
    assert p.returncode == 0, (p.returncode, p.stderr[-500:])
    return [tuple(x) for x in json.loads(p.stdout.splitlines()[-1])]


# ----------------------------------------------------------------- CI + CLI

SLICE_SEED = 20261114


@needs_opennec
@pytest.mark.antenna_computation_check  # ~10 s of forked solves: main-only lane
@pytest.mark.skipif(not hasattr(os, "fork"), reason="forks one process per case")
def test_fuzz_slice_nothing_kills_the_process():
    bad = []
    seen = collections.Counter()
    cases = [make_case(SLICE_SEED, i, allow_big=False) for i in range(50)]
    for c, (o, d) in zip(cases, run_cases(cases), strict=True):
        seen[o] += 1
        if o in ("CRASH", "HANG", "sysexit"):
            bad.append((c["id"], o, d, c.get("deck") or c))
    assert not bad, bad
    # A NaN/inf answer is refused by name, never returned (the engine's
    # non-finite check), so the slice sees none.
    assert seen["nan"] == 0, seen
    assert seen["finite"] + seen["exception"] == 50


def _dipole_case(path, freq, **over):
    c = {
        "wires": [[1, 11, [0.0, 0.0, 5.0], [0.0, 0.0, 15.0], 0.001]],
        "ports": [[1, 6]],
        "loads": [],
        "ground": None,
        "ek": False,
        "freqs": [freq],
        "far": False,
        "ak_ground": None,
        "path": path,
        "classes": ["nan_regression"],
        "id": f"nan:{path}:{freq}",
        "sweep": False,
        "cd": False,
    }
    c.update(over)
    if path == "ak":
        c["deck"] = deck_text(c)
    return c


@needs_opennec
@pytest.mark.skipif(not hasattr(os, "fork"), reason="forks one process per case")
def test_an_absurd_frequency_is_refused_up_front_through_ak():
    """The fuzz's NaN answers came from absurd frequencies. Through AK the
    engine refuses the frequency by name before any porty work (one process,
    no solve); porty itself is free to return NaN or to raise, and the direct
    path is only required not to die (the fuzz slice holds that)."""
    cases = [_dipole_case("ak", f) for f in (1e300, 5e-324, 1e-6, 1e9, 0.001)]
    for c, (o, d) in zip(cases, run_cases(cases), strict=True):
        assert o == "exception" and "MHz is outside the" in d, (c["freqs"], o, d)


@needs_opennec
@pytest.mark.skipif(not hasattr(os, "fork"), reason="forks one process per case")
def test_an_absurd_electrical_size_is_refused_up_front():
    # 10 m of wire at 100 GHz is ~3300 wavelengths: inside the frequency range,
    # outside the size range.
    c = _dipole_case("ak", 1.0e5)
    o, d = run_cases([c])[0]
    assert o == "exception" and "wavelengths across" in d, (o, d)


@needs_opennec
def test_the_engine_names_a_non_finite_reading(monkeypatch):
    """A NaN admittance from porty (as the fuzz found for NaN geometry that
    got past an older importer) is refused by name, not turned into a Z."""
    from antennaknobs.engines.opennec import OpenNECEngine
    from antennaknobs.file_designs import builder_from_text

    real = opennec_mod.porty.Structure.solve

    def nan_solve(self, freqs, *a, **k):
        sol = real(self, freqs, *a, **k)
        return types.SimpleNamespace(
            y=np.full_like(sol.y, np.nan), segments=sol.segments, currents=sol.currents
        )

    monkeypatch.setattr(opennec_mod.porty.Structure, "solve", nan_solve)
    eng = OpenNECEngine(builder_from_text("f.nec", _dipole_case("ak", 14.0)["deck"])())
    with pytest.raises(ValueError, match=r"non-finite port admittance Y.* at 14 MHz"):
        eng.impedance()


def test_generator_is_deterministic():
    assert json.dumps(make_case(7, 3), default=str) == json.dumps(
        make_case(7, 3), default=str
    )


@needs_opennec
def test_large_mode_is_opt_in():
    # The large mode is the __main__ below, gated by AK_FUZZ_CASES.
    assert (
        os.environ.get("AK_FUZZ_CASES") is None or int(os.environ["AK_FUZZ_CASES"]) > 0
    )


def main():
    n = int(os.environ.get("AK_FUZZ_CASES", "5000"))
    seed = os.environ.get("AK_FUZZ_SEED", "1")
    budget = float(os.environ.get("AK_FUZZ_BUDGET_S", "2400"))
    out = Path(os.environ.get("AK_FUZZ_OUT", "fuzz-out"))
    out.mkdir(parents=True, exist_ok=True)
    print(f"seed={seed} cases<={n} budget={budget}s pyopennec={opennec_mod.porty}")
    by_path = collections.Counter()
    by_class = collections.defaultdict(collections.Counter)
    by_outcome = collections.Counter()
    msgs = collections.Counter()
    bad = []
    t0 = time.time()
    done = 0
    for i in range(n):
        if time.time() - t0 > budget:
            break
        c = make_case(seed, i)
        o, d = run_forked(c)
        done += 1
        by_path[(c["path"], o)] += 1
        by_outcome[o] += 1
        for k in c["classes"]:
            by_class[k][o] += 1
        if o == "exception":
            msgs[(c["path"], d)] += 1
        if o in ("CRASH", "HANG", "sysexit"):
            bad.append((c["id"], o, d))
            (out / f"repro-{seed}-{i}.json").write_text(
                json.dumps({**c, "outcome": o, "detail": d}, default=str, indent=1)
            )
            if "deck" in c:
                (out / f"repro-{seed}-{i}.nec").write_text(c["deck"])
        if done % 250 == 0:
            print(
                f"  {done} cases, {time.time() - t0:.0f}s, {dict(by_outcome)}",
                flush=True,
            )
    print(f"\nran {done} cases in {time.time() - t0:.0f}s")
    print("outcomes:", dict(by_outcome))
    print("by path:")
    for (p, o), v in sorted(by_path.items()):
        print(f"  {p:6} {o:10} {v}")
    print("by mutation class (cases touching it):")
    for k, cnt in sorted(by_class.items()):
        print(f"  {k:16} total={sum(cnt.values()):5} {dict(cnt)}")
    print("top exception messages:")
    for (p, m), v in msgs.most_common(20):
        print(f"  {v:5} [{p}] {m}")
    print(f"CRASH/HANG/sysexit: {len(bad)}")
    for b in bad:
        print("  ", b)


def zygote():
    cases = json.loads(sys.stdin.read())
    print(json.dumps([run_forked(c) for c in cases]))


if __name__ == "__main__":
    sys.exit(zygote() if "--zygote" in sys.argv else main())
