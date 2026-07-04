"""Profile the /ws solve pipeline to decide whether phases 3 + 4 of the
latest-wins refactor (docs/plan-ws-latest-wins.md) are worth building.

Phase 3 — skip stale post-processing: when a solve is already superseded, skip
`_attach_derived_em_fields` + `_compute_directivity_norm` between the core
impedance/currents solve and the send. Worth it only if post-processing is a
real fraction of a *slow* solve.

Phase 4 — serialization: `json.dumps` runs on the event loop once per response
and `solve()` pays a `deepcopy` per cache hit. Worth it only if either is a
measurable cost on a large payload (swap to orjson / cache the string).

Both are pure server-side CPU costs, so they profile on localhost — no fly.io
deploy needed (the RTT-dependent tail-latency win is phases 1+2, already
merged). Cases on the worst-case design `arrays.bowtiearray2x4` + N=21:
  - momwire / arrayblock (the interactive default; ~0.75 s warm/solve)
  - pynec (dense NEC; dozens of seconds — post-proc uses coarser KNOT arrays
    since PyNEC ships no segment-midpoint samples)

Ground is the usual interactive case, and the ground-on norm runs a *second*
exp/einsum (PEC image + Fresnel over the upper hemisphere), so it is ~2× the
free-space norm cost. We profile arrayblock both ground OFF and ON so the delta
is visible, and run the grid-convergence study under ground too — the adaptive
grid (move 3 of the directivity-norm rework) must be sized for the ground-on
integral, not the cheaper free-space one.

Run: python scripts/profile_ws_postproc_serialization.py
"""

from __future__ import annotations

import json
import statistics
import time
from copy import deepcopy

import orjson  # profiling-only dep; not in the app's runtime requirements

from antennaknobs.web import pynec_backend, server
from antennaknobs.web.examples import REGISTRY as EXAMPLES

BASE_REQ = {
    "geometry": "arrays.bowtiearray2x4",
    "variant": "default",
    "momwire_model": "arrayblock",
    "n_per_wire": 21,
    "measurement_freq_mhz": 28.47,
    "design_freq_mhz": 28.47,
    "wire_radius": 0.001,
    # Ground on is the usual interactive case; per-case overrides below still
    # exercise ground OFF for the delta.
    "ground": True,
    "ground_fast": False,
}

CHEAP_REPS = 50  # dumps/deepcopy are cheap → many reps


def med_ms(fn, reps):
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1e3)
    return statistics.median(times), min(times), max(times)


def core_only(req):
    """Core impedance/currents solve, mirroring server._solve_uncached but
    stopping before the shared post-processing step."""
    if req["solver"] == "pynec":
        return pynec_backend.solve(dict(req))
    ex = EXAMPLES[req["geometry"]]
    out = ex.momwire_solve(dict(req))
    out["solver"] = "momwire"
    return out


def profile_case(label, req, core_reps):
    print(f"\n{'=' * 68}\nCASE: {label}\n{'=' * 68}")

    # warm-up (JIT / caches / first-touch allocation)
    warm = core_only(req)
    server._attach_derived_em_fields(warm)
    server._compute_directivity_norm(warm)

    uses_samples = "sample_positions" in warm["wires"][0]
    nseg = sum(
        len(w.get("sample_positions", w["knot_positions"])) - 1 for w in warm["wires"]
    )

    core_med, core_lo, core_hi = med_ms(lambda: core_only(req), core_reps)

    # Post-processing measured on a fresh core result each rep (the functions
    # mutate in place, so re-running on the same dict would be a no-op/cheat).
    emf_times, dir_times = [], []
    for _ in range(core_reps):
        base = core_only(req)
        b1 = deepcopy(base)
        t0 = time.perf_counter()
        server._attach_derived_em_fields(b1)
        emf_times.append((time.perf_counter() - t0) * 1e3)
        t0 = time.perf_counter()
        server._compute_directivity_norm(b1)
        dir_times.append((time.perf_counter() - t0) * 1e3)
    emf_med = statistics.median(emf_times)
    dir_med = statistics.median(dir_times)
    post_med = emf_med + dir_med
    total_med = core_med + post_med

    # --- Full result for serialization / copy measurements ---
    full = core_only(req)
    server._attach_derived_em_fields(full)
    server._compute_directivity_norm(full)
    full["cache_hit"] = False
    full["_seq"] = 12345

    payload = json.dumps(full)
    payload_kb = len(payload.encode()) / 1024
    jd_med, _, _ = med_ms(lambda: json.dumps(full), CHEAP_REPS)
    oj_med, _, _ = med_ms(lambda: orjson.dumps(full), CHEAP_REPS)
    dc_med, _, _ = med_ms(lambda: deepcopy(full), CHEAP_REPS)
    assert json.loads(orjson.dumps(full)) == json.loads(payload)

    arr_kind = "sample (knot+midpoint)" if uses_samples else "KNOT-only (coarse)"
    print(
        f"  wires={len(full['wires'])}  far-field segments={nseg} [{arr_kind}]  "
        f"payload={payload_kb:.1f} KB  (core reps={core_reps}, median)"
    )
    print("\n  -- Phase 3: post-processing fraction --")
    print(
        f"    core (impedance/currents)   {core_med:9.1f} ms   [{core_lo:.1f}–{core_hi:.1f}]"
    )
    print(f"    _attach_derived_em_fields   {emf_med:9.2f} ms")
    print(f"    _compute_directivity_norm   {dir_med:9.2f} ms")
    print(f"    post-processing (sum)       {post_med:9.2f} ms")
    print(f"    total                       {total_med:9.1f} ms")
    print(f"    ==> post / total          = {100 * post_med / total_med:7.2f} %")
    print("\n  -- Phase 4: serialization + copy --")
    print(f"    json.dumps                  {jd_med:9.2f} ms")
    print(
        f"    orjson.dumps                {oj_med:9.2f} ms   ({jd_med / oj_med:.1f}x)"
    )
    print(f"    deepcopy (per cache hit)    {dc_med:9.2f} ms")


def grid_convergence(label, req, grids, ref_grid=(240, 480)):
    """Show how the directivity-norm scalar + its cost vary with grid
    resolution, vs a fine reference, for BOTH the uniform-midpoint and the
    Gauss–Legendre θ rules. Demonstrates (a) GL is far more accurate per
    θ-point above the resolution floor, (b) the floor scales with electrical
    size (a *fixed* coarse grid is not universally safe), and (c) the adaptive
    sizer lands above the floor for each design."""
    import math

    print(f"\n{'=' * 68}\nGRID CONVERGENCE: {label}\n{'=' * 68}")
    base = core_only(req)
    server._attach_derived_em_fields(base)

    def norm(nt, nph, rule):
        o = deepcopy(base)
        t0 = time.perf_counter()
        server._compute_directivity_norm(o, n_theta=nt, n_phi=nph, _theta_rule=rule)
        return o["directivity_norm"], (time.perf_counter() - t0) * 1e3

    ref, _ = norm(*ref_grid, "gl")
    print(f"  {'grid':>9} {'points':>7} {'uniform dB':>12} {'GL dB':>10} {'GL ms':>8}")
    for nt, nph in grids:
        du, _ = norm(nt, nph, "uniform")
        dg, ms = norm(nt, nph, "gl")
        eu = 10 * math.log10(du / ref) if du > 0 and ref > 0 else float("nan")
        eg = 10 * math.log10(dg / ref) if dg > 0 and ref > 0 else float("nan")
        print(f"  {f'{nt}x{nph}':>9} {nt * nph:>7} {eu:>+11.3f} {eg:>+9.3f} {ms:>8.1f}")

    # What the production adaptive sizer picks for this design, and its error.
    lo = base_bbox_lo_hi(base)
    ant, anp = server._adaptive_norm_grid(float(base["k_meas_m_inv"]), *lo)
    dn, ms = norm(ant, anp, "gl")
    db = 10 * math.log10(dn / ref) if dn > 0 and ref > 0 else float("nan")
    print(f"  ADAPTIVE → {ant}x{anp} ({ant * anp} pts)  err {db:+.4f} dB  {ms:.1f} ms")


def base_bbox_lo_hi(out):
    import numpy as np

    lo = np.array([np.inf, np.inf, np.inf])
    hi = -lo
    for w in out["wires"]:
        pts = np.asarray(w.get("sample_positions", w["knot_positions"]), float)
        lo = np.minimum(lo, pts.min(0))
        hi = np.maximum(hi, pts.max(0))
    return lo, hi


def main():
    # arrayblock both ground OFF and ON — the ground-on norm is ~2× (image +
    # Fresnel), and ground on is the usual interactive case.
    for ground in (False, True):
        tag = "ground ON" if ground else "ground OFF"
        profile_case(
            f"momwire / arrayblock — bowtiearray2x4 N=21 [{tag}]",
            {**BASE_REQ, "solver": "momwire", "ground": ground},
            core_reps=5,
        )
    if pynec_backend.HAVE_PYNEC:
        profile_case(
            "pynec (dense NEC) — bowtiearray2x4 N=21 [ground ON]",
            {**BASE_REQ, "solver": "pynec"},
            core_reps=2,  # dense solve is slow; keep rep count low
        )
    else:
        print("\n[pynec case SKIPPED — HAVE_PYNEC is False]")

    # Grid convergence: small design (bowtie) vs an electrically-large one
    # (80m skyloop run at harmonics). Shows required grid scales with size.
    # Run the bowtie both ground OFF and ON — the adaptive grid must be sized
    # for the ground-on integral (upper hemisphere + reflected term).
    grids = [(12, 24), (18, 36), (24, 48), (30, 60), (45, 90)]
    for ground in (False, True):
        tag = "ground ON" if ground else "ground OFF"
        grid_convergence(
            f"bowtiearray2x4 N=21 (moderate lobing) [{tag}]",
            {**BASE_REQ, "solver": "momwire", "ground": ground},
            grids,
        )
    sky = {
        "geometry": "loops.triangular_skyloop",
        "variant": "default",
        "solver": "momwire",
        "momwire_model": "triangular",
        "n_per_wire": 80,
        "design_freq_mhz": 3.8,  # sized for the 80m loop (~1λ)
        "wire_radius": 0.001,
        "ground": False,
        "ground_fast": False,
    }
    for fmhz, band in [(21.0, "15m ~5.8λ"), (50.0, "6m ~13.8λ")]:
        grid_convergence(
            f"triangular_skyloop @ {fmhz} MHz ({band})",
            {**sky, "measurement_freq_mhz": fmhz},
            grids,
        )
    print()


if __name__ == "__main__":
    main()
