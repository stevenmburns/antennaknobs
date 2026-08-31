"""Tune one band's shape factors to Z = z0 + 0j on PyNEC.

Default target is 50+0j and the default knobs are halfdriver_factor +
t0_factor — two degrees of freedom for a 2-D target (resistance and
reactance). Add --resonance to fall back to |Im(Z)|-only (one knob is
enough for that).

Usage:
    .venv/bin/python scripts/tune_hexbeam_5band_band.py --band 0
    .venv/bin/python scripts/tune_hexbeam_5band_band.py --band 2 \\
        --param halfdriver_factor tipspacer_factor --z0 50

Sets n_bands=1 and slices `bands` to the single requested band so the
solver computes one impedance per call. Prints the optimised factor(s)
so you can paste them back into _BAND_xx in the design file.
"""

from __future__ import annotations

import argparse

from scipy.optimize import minimize

from antennaknobs.designs.multiband.hexbeam_5band import Builder
from antennaknobs.engines.pynec import PyNECEngine


def tune(
    band_idx: int,
    param_names: list[str],
    freq_mhz: float | None,
    z0: float,
    resonance_only: bool,
) -> dict:
    b = Builder()
    full_bands = tuple(b.bands)
    band = dict(full_bands[band_idx])
    if freq_mhz is not None:
        band["freq"] = freq_mhz

    # Strip the multi-band setup down to just the band we're tuning.
    b.n_bands = 1
    b.bands = (band,)
    b.freq = band["freq"]
    b.design_freq = band["freq"]

    x0 = [band[p] for p in param_names]
    bounds = [(x * 0.7, x * 1.3) for x in x0]

    def objective(xs):
        new_band = dict(band)
        for name, x in zip(param_names, xs, strict=True):
            new_band[name] = float(x)
        b.bands = (new_band,)
        eng = PyNECEngine(b, ground=None)
        (z,) = eng.impedance()
        del eng
        # Resonance mode targets just |Im(Z)| (one DOF is enough).
        # Default targets Z = z0 + 0j — two DOFs needed; |z - z0|
        # naturally weights resistance and reactance equally in Ω.
        loss = abs(z.imag) if resonance_only else abs(z - z0)
        print(
            f"  {dict(zip(param_names, xs, strict=True))} → "
            f"Z=({z.real:.2f} {z.imag:+.2f}j) Ω  loss={loss:.3f}"
        )
        return loss

    target = f"Z = {z0:.1f} + 0j Ω" if not resonance_only else "Im(Z) = 0"
    print(
        f"Tuning band {band_idx} at {band['freq']:.3f} MHz on knobs {param_names} → {target}"
    )
    if not resonance_only and len(param_names) < 2:
        print(
            "  WARNING: hitting both R and X needs two DOFs — "
            "consider --param halfdriver_factor t0_factor"
        )
    result = minimize(
        objective,
        x0=x0,
        method="Powell",
        bounds=bounds,
        options={"maxiter": 100, "xtol": 1e-4, "disp": True},
    )
    final = {name: float(x) for name, x in zip(param_names, result.x, strict=True)}
    print(f"\nOptimised: {final}")
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--band", type=int, required=True, help="Band index 0..4")
    ap.add_argument(
        "--param",
        nargs="+",
        default=["halfdriver_factor", "t0_factor"],
        help="Per-band knobs to tune (default: halfdriver_factor t0_factor — "
        "two DOFs for matching Z = z0 + 0j)",
    )
    ap.add_argument(
        "--freq",
        type=float,
        default=None,
        help="Override the band's freq (MHz) before tuning",
    )
    ap.add_argument(
        "--z0",
        type=float,
        default=50.0,
        help="Target resistance in Ω (default: 50)",
    )
    ap.add_argument(
        "--resonance",
        action="store_true",
        help="Optimise |Im(Z)| only, ignore resistance — one knob is enough",
    )
    args = ap.parse_args()
    tune(args.band, args.param, args.freq, args.z0, args.resonance)


if __name__ == "__main__":
    main()
