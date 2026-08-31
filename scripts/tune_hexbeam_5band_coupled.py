"""Coupled multi-band hexbeam_5band tuning script.

Unlike scripts/tune_hexbeam_5band_band.py — which slices `bands` down
to a single entry and tunes in isolation — this script keeps all five
bands active throughout and tunes one band's shape factors at a time,
sweeping band-by-band for several passes until each band's driving-
point Z lands close to z0 + 0j.

Algorithm:
  1. Start from opt_params (the single-band-tuned starting point).
  2. For each pass, walk bands 0..4 in order. For each band:
       - Set meas_freq to that band's freq.
       - Minimise |Z[band_idx] - z0| over (halfdriver_factor, t0_factor)
         of *that band only*, with the other four bands fixed at their
         current values. Z[band_idx] is the band's driving-point Z in
         the 5-port multi-feed solve, so the optimiser sees the actual
         inter-band coupling.
       - Update bands[band_idx] in place; the next band's tune sees
         the updated geometry.
  3. After each pass, log max|Z - z0|. Stop when it drops below tol or
     we hit max_passes.
  4. Print the final bands tuple as paste-ready Python.

Usage:
    .venv/bin/python scripts/tune_hexbeam_5band_coupled.py
    .venv/bin/python scripts/tune_hexbeam_5band_coupled.py --passes 8 --tol 0.3

Tune at PyNEC, free space. ~5 PyNEC solves per Powell step × ~40 steps
per band × 5 bands × N passes — expect ~1–3 minutes per pass.
"""

from __future__ import annotations

import argparse

from scipy.optimize import minimize

from antennaknobs.builder import resolve_variant_params
from antennaknobs.designs.multiband.hexbeam_5band import Builder
from antennaknobs.engines.pynec import PyNECEngine


def _solve_all(b: Builder) -> list[complex]:
    eng = PyNECEngine(b, ground=None)
    zs = eng.impedance()
    del eng
    return zs


def _max_distance_from_target(zs: list[complex], z0: float) -> float:
    return max(abs(z - z0) for z in zs)


def tune_band_in_place(
    b: Builder,
    band_idx: int,
    param_names: list[str],
    z0: float,
    verbose: bool,
) -> None:
    """Mutate b.bands[band_idx] toward Z[band_idx] = z0 + 0j with the
    other bands held at their current values. Uses Powell within a
    ±30% bound on each knob."""
    cur_bands = [dict(bd) for bd in b.bands]
    band = cur_bands[band_idx]
    x0 = [band[p] for p in param_names]
    bounds = [(x * 0.7, x * 1.3) for x in x0]
    b.freq = float(band["freq"])

    def objective(xs):
        for name, x in zip(param_names, xs, strict=True):
            band[name] = float(x)
        cur_bands[band_idx] = band
        b.bands = tuple(cur_bands)
        zs = _solve_all(b)
        z = zs[band_idx]
        loss = abs(z - z0)
        if verbose:
            kvs = ", ".join(
                f"{n}={x:.5f}" for n, x in zip(param_names, xs, strict=True)
            )
            print(
                f"    [band {band_idx}] {kvs} → "
                f"Z={z.real:7.3f}{z.imag:+7.3f}j  loss={loss:6.3f}"
            )
        return loss

    minimize(
        objective,
        x0=x0,
        method="Powell",
        bounds=bounds,
        options={"maxiter": 60, "xtol": 1e-4, "disp": False},
    )


def run(passes: int, tol: float, z0: float, param_names: list[str], verbose: bool):
    # params= replaces default_params wholesale, so overlay via
    # resolve_variant_params — a bare opt_params dict drops
    # n_bands/daisy_chain/etc. Multi-feed mode must be explicit now that
    # the design defaults to the one-coax feed: this script's objective
    # indexes zs[band_idx], the per-band tuning aid. Tuning the physical
    # coax is scripts/tune_hexbeam_5band_physical.py.
    params = dict(resolve_variant_params(Builder, "opt"))
    params["daisy_chain"] = False
    b = Builder(params=params)
    n_bands = int(b.n_bands)
    print(f"Starting from opt_params; tuning {n_bands} bands → Z = {z0:.1f} + 0j Ω")

    initial_zs = []
    for i in range(n_bands):
        b.freq = float(b.bands[i]["freq"])
        initial_zs.append(_solve_all(b)[i])
    print("Initial driving-point Z (all bands present, opt_params):")
    for i, z in enumerate(initial_zs):
        print(
            f"  band {i} @ {b.bands[i]['freq']:>7.3f} MHz: "
            f"Z = {z.real:6.2f}{z.imag:+6.2f}j Ω"
        )

    for pass_idx in range(passes):
        print(f"\n--- pass {pass_idx + 1}/{passes} ---")
        for band_idx in range(n_bands):
            tune_band_in_place(b, band_idx, param_names, z0, verbose)

        zs = []
        for i in range(n_bands):
            b.freq = float(b.bands[i]["freq"])
            zs.append(_solve_all(b)[i])
        print("After pass driving-point Z:")
        for i, z in enumerate(zs):
            print(
                f"  band {i} @ {b.bands[i]['freq']:>7.3f} MHz: "
                f"Z = {z.real:6.2f}{z.imag:+6.2f}j Ω"
            )
        worst = _max_distance_from_target(zs, z0)
        print(f"worst |Z - z0|: {worst:.3f} Ω")
        if worst < tol:
            print(f"converged: worst |Z - z0| < tol ({tol})")
            break

    print("\n# Paste into hexbeam_5band.py:")
    print("(")
    for bd in b.bands:
        print(
            "    {"
            f'"freq": {bd["freq"]}, '
            f'"halfdriver_factor": {bd["halfdriver_factor"]:.5f}, '
            f'"tipspacer_factor": {bd["tipspacer_factor"]}, '
            f'"t0_factor": {bd["t0_factor"]:.5f}'
            "},"
        )
    print(")")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--passes", type=int, default=4, help="Max band-cycle passes")
    ap.add_argument(
        "--tol", type=float, default=0.5, help="Stop when worst |Z-z0| < tol"
    )
    ap.add_argument("--z0", type=float, default=50.0)
    ap.add_argument(
        "--param",
        nargs="+",
        default=["halfdriver_factor", "t0_factor"],
        help="Per-band knobs to tune",
    )
    ap.add_argument("--quiet", action="store_true", help="Suppress per-step output")
    args = ap.parse_args()
    run(args.passes, args.tol, args.z0, args.param, not args.quiet)


if __name__ == "__main__":
    main()
