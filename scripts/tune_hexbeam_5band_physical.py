"""Physical-feed hexbeam_5band tuning script (issue #921).

scripts/tune_hexbeam_5band_coupled.py tunes each band's driving-point Z
in the multi-feed solve (daisy_chain=False) — the tuning aid. The deck
validation showed that tune does not transfer: the same parameters
present -j17..-j21 on four of five bands through the physical one-coax
feed (daisy_chain=True), because the TL jumpers and the four passive
band feeds transform the drive point.

This script tunes the same per-band shape knobs, but the objective is
the *physical* drive point: at each band's frequency the engine solves
the full 5-port Y and the NetworkReducer reduces the jumper chain +
Driven source to the one-coax Z. Band i's knobs are tuned against the
one-coax Z at band i's freq (cyclic coordinate descent, several passes,
so inter-band coupling through the chain is absorbed pass over pass).

momwire is the tuning engine (~0.1 s per one-coax solve at the base
mesh, ~100x cheaper than PyNEC here); cross-check the result with
scripts-free evaluation on PyNEC before shipping.

Usage:
    .venv/bin/python scripts/tune_hexbeam_5band_physical.py
    .venv/bin/python scripts/tune_hexbeam_5band_physical.py --passes 8 --tol 3.0

Note the Builder(params=...) trap: params *replaces* default_params
(builder.py), so always start from resolve_variant_params — passing a
bare variant overlay dict silently drops n_bands/daisy_chain/etc.
"""

from __future__ import annotations

import argparse

from scipy.optimize import minimize

from antennaknobs.builder import resolve_variant_params
from antennaknobs.designs.multiband.hexbeam_5band import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network_reduce import SingularNetworkError

_PENALTY = 1e6


def swr50(z, z0=50.0):
    gamma = abs((z - z0) / (z + z0))
    gamma = min(gamma, 1 - 1e-9)
    return (1 + gamma) / (1 - gamma)


def one_coax_z(b: Builder, freq: float) -> complex:
    """Physical drive-point Z at freq: full multiport Y + jumper-chain
    reduction, one Driven port. Raises on singular network stamps."""
    b.freq = freq
    zs = MomwireEngine(b, ground=None).impedance()
    assert len(zs) == 1, "expected the single reduced coax port"
    return zs[0]


def _loss_at(b: Builder, freq: float, z0: float) -> tuple[float, complex]:
    try:
        z = one_coax_z(b, freq)
    except SingularNetworkError:
        return _PENALTY, complex("nan")
    if not (abs(z.real) < 1e6 and abs(z.imag) < 1e6):
        # open-port sentinel (inf) or a blowup — steer the optimiser away
        return _PENALTY, z
    return abs(z - z0), z


def tune_band_in_place(
    b: Builder,
    band_idx: int,
    param_names: list[str],
    z0: float,
    verbose: bool,
) -> None:
    """Mutate b.bands[band_idx] toward one-coax Z(freq_i) = z0 + 0j with
    the other bands held at their current values. Powell within a +-30%
    bound on each knob."""
    cur_bands = [dict(bd) for bd in b.bands]
    band = cur_bands[band_idx]
    x0 = [band[p] for p in param_names]
    bounds = [(x * 0.7, x * 1.3) for x in x0]
    freq = float(band["freq"])

    def objective(xs):
        for name, x in zip(param_names, xs, strict=True):
            band[name] = float(x)
        cur_bands[band_idx] = band
        b.bands = tuple(cur_bands)
        loss, z = _loss_at(b, freq, z0)
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


def eval_all(b: Builder, z0: float) -> list[complex]:
    zs = []
    for i in range(int(b.n_bands)):
        _, z = _loss_at(b, float(b.bands[i]["freq"]), z0)
        zs.append(z)
    return zs


def report(b: Builder, zs: list[complex], z0: float) -> float:
    worst = 0.0
    for i, z in enumerate(zs):
        print(
            f"  band {i} @ {b.bands[i]['freq']:>7.3f} MHz: "
            f"Z = {z.real:6.2f}{z.imag:+6.2f}j Ω  SWR50 = {swr50(z):5.2f}"
        )
        worst = max(worst, abs(z - z0))
    return worst


def run(passes: int, tol: float, z0: float, param_names: list[str], verbose: bool):
    b = Builder(params=resolve_variant_params(Builder, "opt_coupled"))
    assert b.daisy_chain, "physical tune requires the one-coax (daisy_chain) mode"
    n_bands = int(b.n_bands)
    print(
        f"Starting from opt_coupled; tuning {n_bands} bands' one-coax "
        f"drive point → Z = {z0:.1f} + 0j Ω"
    )

    print("Initial physical (one-coax) drive point:")
    report(b, eval_all(b, z0), z0)

    for pass_idx in range(passes):
        print(f"\n--- pass {pass_idx + 1}/{passes} ---")
        for band_idx in range(n_bands):
            tune_band_in_place(b, band_idx, param_names, z0, verbose)

        print("After pass one-coax drive point:")
        worst = report(b, eval_all(b, z0), z0)
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
    ap.add_argument("--passes", type=int, default=6, help="Max band-cycle passes")
    ap.add_argument(
        "--tol", type=float, default=1.0, help="Stop when worst |Z-z0| < tol"
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
