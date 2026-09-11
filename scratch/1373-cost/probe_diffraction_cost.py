"""#1373 cost gate: what `Terrain(diffraction=True)` costs, paired against False.

The rule this measures against is the 0.6.0 near-miss: an expensive model stays
opt-in. Sub-second and the default can flip; seconds and it needs a toggle with
the cost stated, or stays opt-in behind a prominent switch.

WHERE THE COST CAN FALL, which decides what is worth timing. The diffraction term
is in the far-field composition (`MomwireEngine._terrain_utd_power`), reached from
`far_field`. The impedance solve over terrain is a FLAT Sommerfeld solve at the
crest medium — the adapter says so and the engine does it — so the impedance path
cannot move, and a tracker tick, whose cost model is "one solve per tick", cannot
move either. Both are measured anyway rather than asserted, because "cannot move"
is a claim about code I did not write.

Three timings per case, paired and interleaved (False, True, False, True, ...) so
a drift in CPU clock state cannot land on one arm: this box is an i7-6700K on the
powersave governor with turbo on, so ratios and repeated minima are the readable
quantities, never a single absolute second.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time

# The server package first: importing the adapter directly at module scope trips
# the adapter <-> examples circular import, which is the order every web test uses.
from antennaknobs.web import server as _server  # noqa: F401 — import order

import antennaknobs.web.adapter as adapter  # noqa: E402 — must follow the server

from antennaknobs.designs.dipoles.invvee import Builder as InvVee
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.terrain import Terrain

# The app's pattern resolution -- 2 degrees in theta, 5 in phi -- expressed the
# way `far_field` asserts it: 90 == del_theta * n_theta and 360 == del_phi * n_phi.
# (The web response's 46 thetas are these 45 cells plus the pole row.)
PATTERN_GRID = dict(n_theta=45, n_phi=72, del_theta=2.0, del_phi=5.0)
REPS = 3


def presets():
    """Each hosted preset at the defaults the panel opens with."""
    out = []
    for p in adapter._TERRAIN_PRESETS:
        vals = {f.key: f.default for f in p.fields}
        out.append((p.name, vals, p.build))
    return out


def mikes_hillside():
    """M0AGP's hillside, the geometry probe10/probe12 publish: the 20 m hill."""
    from antennaknobs.terrain import hillside_terrain

    return hillside_terrain(
        flat_width=20.0,
        up_slope_deg=15.0,
        down_slope_deg=15.0,
        medium=adapter._TERRAIN_LAND,
        downhill_azimuth=0.0,
    )


def with_diffraction(t: Terrain, on: bool) -> Terrain:
    import dataclasses

    return dataclasses.replace(t, diffraction=on)


def time_far_field(terrain, reps=REPS):
    """Wall seconds for one far-field composition at the app's grid."""
    out = []
    for _ in range(reps):
        b = InvVee()
        eng = MomwireEngine(b, ground=("terrain", terrain))
        t0 = time.perf_counter()
        eng.far_field(**PATTERN_GRID)
        out.append(time.perf_counter() - t0)
    return out


def time_impedance(terrain, reps=REPS):
    """Wall seconds for the impedance solve — the tracker tick's unit of cost."""
    out = []
    for _ in range(reps):
        b = InvVee()
        eng = MomwireEngine(b, ground=("terrain", terrain))
        t0 = time.perf_counter()
        eng.impedance()
        out.append(time.perf_counter() - t0)
    return out


def time_web_solve(preset: str, on: bool, reps=REPS):
    """Wall seconds for the live web solve a knob drag triggers.

    This is the number a DRAG feels: the tick's display solve plus the two polar
    cuts the app redraws, through the same adapter path the WebSocket uses. The
    request carries no diffraction field (the flag is opt-in in code, #1373), so
    the harness wraps the adapter's terrain builder to turn it on.
    """
    import dataclasses

    from antennaknobs.web.examples import example_for

    real = adapter._terrain_from_request
    req = {
        "geometry": "dipoles.invvee",
        "ground": True,
        "ground_model": "terrain",
        "terrain_preset": preset,
    }

    def patched(r):
        return dataclasses.replace(real(r), diffraction=on)

    out = []
    ex = example_for("dipoles.invvee")
    adapter._terrain_from_request = patched if on else real
    try:
        for _ in range(reps):
            t0 = time.perf_counter()
            ex.momwire_solve(req)
            out.append(time.perf_counter() - t0)
    finally:
        adapter._terrain_from_request = real
    return out


# Grids whose direction counts span two decades, all satisfying `far_field`'s
# assertions (90 == del_theta * n_theta, 360 == del_phi * n_phi). Timed on the
# PUBLIC path rather than by calling the composer with hand-made arrays, and used
# to separate the two terms the per-cut question turns on: cost = setup + N x
# per-direction. If the setup dominates, a cut's cost is nothing like the grid's
# divided by its directions.
DIRECTION_SWEEP = (
    dict(n_theta=9, n_phi=12, del_theta=10.0, del_phi=30.0),
    dict(n_theta=18, n_phi=24, del_theta=5.0, del_phi=15.0),
    dict(n_theta=45, n_phi=72, del_theta=2.0, del_phi=5.0),
    dict(n_theta=90, n_phi=180, del_theta=1.0, del_phi=2.0),
)

# The app's polar cuts: two circles of 180 samples each (server._CUT_N_DIR).
CUT_DIRECTIONS = 2 * 180


def time_far_field_grid(terrain, grid, reps=REPS):
    """Minimum wall seconds over `reps`, first call discarded as warm-up: the
    first `far_field` in a process costs ~10x the steady state."""
    b = InvVee()
    eng = MomwireEngine(b, ground=("terrain", terrain))
    eng.far_field(**DIRECTION_SWEEP[0])  # warm-up, not timed
    out = []
    for _ in range(reps):
        t0 = time.perf_counter()
        eng.far_field(**grid)
        out.append(time.perf_counter() - t0)
    return min(out), out


def fit_setup_and_per_direction(points):
    """(setup_s, per_direction_s) from least squares on cost = a + b*N."""
    n = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    den = n * sxx - sx * sx
    if den == 0:
        return points[0][1], 0.0
    b = (n * sxy - sx * sy) / den
    a = (sy - b * sx) / n
    return a, b


def time_pattern_cuts(preset: str, reps=REPS):
    """What a cut-dial drag tick costs TODAY: `server._pattern_cuts` over the
    two 180-sample circles, from a live solve response. This is the specular
    (#534) composer -- the one that has no diffraction term at all -- so there
    is no on/off pair to report, only the budget the UTD term would have to fit
    inside at ~60 msg/s."""
    # Through the SERVER's solve path, not `momwire_solve` directly: the cuts
    # composer needs `directivity_norm` and `k_meas_m_inv`, which the server's
    # path adds and the adapter's does not, and it returns None without them.
    # Timing that None reads as 0.00 ms and looks like a free cut -- it is the
    # empty-result trap, and it is what the first version of this function measured.
    out = _server._solve_uncached(
        {
            "geometry": "dipoles.invvee",
            "ground": True,
            "ground_model": "terrain",
            "terrain_preset": preset,
        }
    )
    assert _server._pattern_cuts(out, 5.0, 0.0) is not None, (
        "the response does not support cuts; timing it would measure an early return"
    )
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        _server._pattern_cuts(out, 5.0, 0.0)
        times.append(time.perf_counter() - t0)
    return min(times), times


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=None, help="write the rows as JSON here")
    ap.add_argument("--reps", type=int, default=REPS)
    args = ap.parse_args(argv)

    cases = [(name, build(vals)) for name, vals, build in presets()]
    cases.append(("mike-hillside-20m", mikes_hillside()))

    rows = []
    print(
        f"{'case':22s} {'what':10s} {'off_s':>8s} {'on_s':>8s} {'ratio':>7s}  {'spread':>7s}"
    )
    for name, base in cases:
        off_t, on_t = with_diffraction(base, False), with_diffraction(base, True)
        jobs = [("far_field", time_far_field), ("impedance", time_impedance)]
        if name != "mike-hillside-20m":  # a preset the panel can actually select
            jobs.append(
                (
                    "web_solve",
                    lambda t, reps=1, _n=name: time_web_solve(
                        _n, t.diffraction, reps=reps
                    ),
                )
            )
        for what, fn in jobs:
            off, on = [], []
            for _ in range(args.reps):  # interleaved, one rep of each at a time
                off += fn(off_t, reps=1)
                on += fn(on_t, reps=1)
            o, n = min(off), min(on)
            spread = max((max(off) - o) / o if o else 0, (max(on) - n) / n if n else 0)
            print(
                f"{name:22s} {what:10s} {o:8.3f} {n:8.3f} {n / o if o else 0:7.2f}x "
                f"{spread * 100:6.0f}%"
            )
            rows.append(
                {
                    "case": name,
                    "what": what,
                    "off_min_s": o,
                    "on_min_s": n,
                    "ratio": n / o if o else None,
                    "off_all_s": off,
                    "on_all_s": on,
                    "median_off_s": statistics.median(off),
                    "median_on_s": statistics.median(on),
                }
            )
    # --- the per-cut question: setup vs per-direction, and today's cut budget --
    print("\n=== direction-count sweep (minima, warm-up discarded) ===")
    print(f"{'case':22s} {'dirs':>6s} {'off_s':>8s} {'on_s':>8s} {'ratio':>7s}")
    fits = {}
    for name, base in cases:
        pts_off, pts_on = [], []
        for grid in DIRECTION_SWEEP:
            dirs = grid["n_theta"] * grid["n_phi"]
            o, _ = time_far_field_grid(with_diffraction(base, False), grid, args.reps)
            n_, _ = time_far_field_grid(with_diffraction(base, True), grid, args.reps)
            pts_off.append((dirs, o))
            pts_on.append((dirs, n_))
            print(f"{name:22s} {dirs:6d} {o:8.4f} {n_:8.4f} {n_ / o if o else 0:7.1f}x")
            rows.append(
                {
                    "case": name,
                    "what": "far_field_grid",
                    "directions": dirs,
                    "off_min_s": o,
                    "on_min_s": n_,
                }
            )
        a_on, b_on = fit_setup_and_per_direction(pts_on)
        a_off, b_off = fit_setup_and_per_direction(pts_off)
        fits[name] = (a_on, b_on, a_off, b_off)
        print(
            f"{name:22s}   fit ON : setup {a_on * 1e3:7.1f} ms + "
            f"{b_on * 1e6:6.1f} us/direction   -> {CUT_DIRECTIONS} dirs = "
            f"{(a_on + b_on * CUT_DIRECTIONS) * 1e3:6.1f} ms"
        )
        print(
            f"{name:22s}   fit OFF: setup {a_off * 1e3:7.1f} ms + "
            f"{b_off * 1e6:6.1f} us/direction   -> {CUT_DIRECTIONS} dirs = "
            f"{(a_off + b_off * CUT_DIRECTIONS) * 1e3:6.1f} ms"
        )
        rows.append(
            {
                "case": name,
                "what": "fit",
                "setup_on_s": a_on,
                "per_direction_on_s": b_on,
                "setup_off_s": a_off,
                "per_direction_off_s": b_off,
                "predicted_cut_pair_on_s": a_on + b_on * CUT_DIRECTIONS,
                "predicted_cut_pair_off_s": a_off + b_off * CUT_DIRECTIONS,
            }
        )

    print("\n=== today's cut-dial budget: server._pattern_cuts, specular only ===")
    for name, _vals, _b in presets():
        m, all_t = time_pattern_cuts(name, args.reps)
        print(
            f"{name:22s} two 180-sample cuts: {m * 1e3:7.2f} ms  (min of {len(all_t)})"
        )
        rows.append({"case": name, "what": "pattern_cuts_today", "min_s": m})

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
