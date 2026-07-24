"""Levee-QTH bracketing recipe + nec2c GD-cliff cross-check (issue #535).

A raised-terrain QTH (antenna on a levee/ridge crest) has no honest flat-ground
model: the ground under the antenna is at one height, the ground the DX lobes
reflect off is 7-11 m lower and may be a different medium per side (land vs
water). Until the faceted-terrain far-field ground lands (#534), the honest
answer is a *bracket* — solve the same design on flat Sommerfeld ground at
several heights and read each result only inside its validity band:

  - h = h0 above the *crest* surface        -> believe psi >= psi_crest
    (the specular point d = h/tan(psi) is still on the crest facet)
  - h = effective height above the *plain*  -> believe psi <= psi_plain
    (specular point beyond the slope toe; one bracket per side, with that
    side's medium — this is where every DX lobe lives)
  - between the two: the slope band, where neither flat model is right;
    #534's facet machinery is the fix. Here we report both and the gap.

Validity-band geometry (per side)::

    psi_crest = atan(h0 / crest_half_width)
    x_toe     = crest_half_width + drop / tan(slope)
    psi_plain = atan((h0 + drop) / x_toe)

Cross-check: classic NEC-2 models exactly this scenario crudely — a two-media
ground with a straight boundary and a height offset (GN + GD cards, the
"cliff"). The cliff is pattern-only reflection-coefficient physics with no
slope facet (a vertical drop at the boundary), which makes it an independent
reference for the two flat brackets: its pattern should land between them,
approaching the raised-height bracket at low angles.

nec2c trap (cost us an afternoon; documented so it doesn't cost another):
the GD card parses fine but is COMPLETELY IGNORED by a normal ``RP 0``
pattern. The two-media cliff only enters the pattern for the dedicated RP
modes: I1=2 (linear cliff, the levee case), 3 (circular cliff), 5/6 (same +
radial screen). GD also takes the standard 4 leading integer fields like
every other card ("GD 0 0 0 0 eps2 sig2 clt cht") — float-first raises a
card error.

Outputs: per-band console table (validity bands, first-lobe angles, bracket
vs cliff gains at the DX angles), optional ``--json`` dump — the golden data
for #534's single-cliff acceptance gate — and optional ``--plot`` overlay.

Typical run (the motivating QTH, 20 m through 10 m)::

    python scripts/bench_levee_bracket.py --freqs 14.1,18.1,21.2,24.9,28.4
    python scripts/bench_levee_bracket.py --freqs 21.2 --json levee_goldens.json
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

# --------------------------------------------------------------------------
# terrain geometry -> validity bands
# --------------------------------------------------------------------------


def validity_bands(h0, crest_half_width, slope_deg, drop):
    """(psi_crest, psi_plain, x_toe, h_eff) for one side, degrees/metres.

    psi above psi_crest: specular point on the crest -> flat model at h0.
    psi below psi_plain: specular point past the slope toe -> flat model at
    h_eff = h0 + drop. Between: the slope band (#534 territory).
    """
    psi_crest = math.degrees(math.atan2(h0, crest_half_width))
    x_toe = crest_half_width + drop / math.tan(math.radians(slope_deg))
    h_eff = h0 + drop
    psi_plain = math.degrees(math.atan2(h_eff, x_toe))
    return psi_crest, psi_plain, x_toe, h_eff


# --------------------------------------------------------------------------
# momwire flat-Sommerfeld brackets
# --------------------------------------------------------------------------


def solve_bracket(design, freq, base, ground):
    """Solve one flat model; return (elevation_deg[], az_max_gain_dBi[], Z)."""
    from antennaknobs import merge_params
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import BSplineSolver

    mod = importlib.import_module(f"antennaknobs.designs.{design}")
    b = mod.Builder(
        merge_params(
            mod.Builder.default_params,
            {"design_freq": freq, "freq": freq, "base": base},
        )
    )
    eng = MomwireEngine(
        b, solver=BSplineSolver, solver_kwargs={"degree": 2}, ground=ground
    )
    z = complex(eng.impedance()[0])
    ff = eng.far_field(n_theta=90, n_phi=72, del_theta=1, del_phi=5)
    dBi = np.asarray(ff.rings)
    el = 90.0 - np.asarray(ff.thetas)
    return el, dBi.max(axis=1), z


def first_lobe(el, gain, lo=1.0, hi=45.0):
    """Elevation of the lowest local maximum in [lo, hi] deg."""
    m = (el >= lo) & (el <= hi)
    e, g = el[m], gain[m]
    order = np.argsort(e)
    e, g = e[order], g[order]
    for i in range(1, len(g) - 1):
        if g[i] >= g[i - 1] and g[i] >= g[i + 1]:
            return float(e[i]), float(g[i])
    j = int(np.argmax(g))
    return float(e[j]), float(g[j])


# --------------------------------------------------------------------------
# nec2c GD-cliff reference
# --------------------------------------------------------------------------


def author_cliff_deck(design, freq, base, ground, cliff, rp_mode):
    """Export the design to a NEC deck and swap in the cliff cards.

    cliff: None for the flat reference, else (eps2, sigma2, clt, cht).
    rp_mode: 0 flat reference / 2 linear cliff. The elevation cut is a
    full-circle pair (phi 0 and 180): with the linear-cliff boundary at
    x = clt, phi=0 looks out over medium 2, phi=180 back over medium 1.
    """
    from antennaknobs import merge_params
    from antennaknobs.nec_export import export_nec

    mod = importlib.import_module(f"antennaknobs.designs.{design}")
    b = mod.Builder(
        merge_params(
            mod.Builder.default_params,
            {"design_freq": freq, "freq": freq, "base": base},
        )
    )
    deck = export_nec(b, ground=ground, include_rp=False)
    lines = deck.splitlines()
    rp = f"RP {rp_mode} 89 2 1000 1 0 1 180"
    if cliff is not None:
        eps2, sig2, clt, cht = cliff
        lines.insert(-2, f"GD 0 0 0 0 {eps2} {sig2} {clt} {cht}")
    lines[-2] = rp
    return "\n".join(lines) + "\n"


def run_nec2c_pattern(deck_text, timeout=120.0):
    """Run nec2c; return {(theta_deg, phi_deg): total_gain_dBi} or None if
    nec2c is not on PATH."""
    if shutil.which("nec2c") is None:
        return None
    with tempfile.TemporaryDirectory(prefix="levee_") as d:
        nec = Path(d) / "d.nec"
        out = Path(d) / "d.out"
        nec.write_text(deck_text)
        subprocess.run(
            ["nec2c", "-i", str(nec), "-o", str(out)],
            capture_output=True,
            timeout=timeout,
        )
        if not out.exists():
            raise RuntimeError("nec2c produced no output")
        text = out.read_text(errors="replace")
    gains = {}
    on = False
    for ln in text.splitlines():
        if "RADIATION PATTERNS" in ln:
            on = True
            continue
        t = ln.split()
        if on and len(t) >= 5:
            try:
                th, ph, tot = float(t[0]), float(t[1]), float(t[4])
            except ValueError:
                continue
            gains[(th, ph)] = tot
    if on and not gains:
        raise RuntimeError("nec2c ran but the pattern did not parse")
    return gains


def cliff_elevation_cut(gains, phi=0.0):
    """(elevation_deg[], gain_dBi[]) for one azimuth from a nec2c gain map."""
    pts = sorted(
        (90.0 - th, g) for (th, ph), g in gains.items() if ph == phi and g > -900
    )
    el = np.array([p[0] for p in pts])
    g = np.array([p[1] for p in pts])
    return el, g


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

REPORT_ANGLES = (5, 10, 15, 20, 30, 45)


def gain_at(el, g, angle):
    return float(g[int(np.argmin(np.abs(el - angle)))])


def run_band(args, freq):
    soil = ("finite", args.soil_eps, args.soil_sigma)
    water = ("finite", args.water_eps, args.water_sigma)

    sides = {
        "land": (args.drop_land, soil, (args.soil_eps, args.soil_sigma)),
        "water": (args.drop_water, water, (args.water_eps, args.water_sigma)),
    }

    print(f"\n=== {args.design} @ {freq} MHz ===")
    out = {"freq": freq, "design": args.design, "sides": {}}

    el_c, g_c, z_c = solve_bracket(args.design, freq, args.h0, soil)
    print(
        f"crest bracket   h={args.h0:5.2f} m over soil   "
        f"Z={z_c.real:6.1f}{z_c.imag:+6.1f}j   (impedance to trust)"
    )
    out["crest"] = {
        "h": args.h0,
        "z": [z_c.real, z_c.imag],
        "gain": {a: gain_at(el_c, g_c, a) for a in REPORT_ANGLES},
    }

    for side, (drop, ground, (eps2, sig2)) in sides.items():
        psi_crest, psi_plain, x_toe, h_eff = validity_bands(
            args.h0, args.crest_half_width, args.slope_deg, drop
        )
        el_e, g_e, _ = solve_bracket(args.design, freq, h_eff, ground)
        lobe_el, lobe_g = first_lobe(el_e, g_e)

        rec = {
            "h_eff": h_eff,
            "psi_crest": psi_crest,
            "psi_plain": psi_plain,
            "x_toe": x_toe,
            "first_lobe": [lobe_el, lobe_g],
            "bracket_gain": {a: gain_at(el_e, g_e, a) for a in REPORT_ANGLES},
        }

        print(
            f"{side:5} bracket   h_eff={h_eff:5.2f} m  "
            f"valid psi<={psi_plain:4.1f} deg (toe {x_toe:.1f} m out); "
            f"crest model valid psi>={psi_crest:4.1f} deg; "
            f"first lobe {lobe_g:5.2f} dBi @ {lobe_el:.0f} deg"
        )

        if not args.no_nec2c:
            cliff = (eps2, sig2, args.crest_half_width, drop)
            deck = author_cliff_deck(args.design, freq, args.h0, soil, cliff, 2)
            gains = run_nec2c_pattern(deck)
            if gains is None:
                print("      nec2c not on PATH -- cliff cross-check skipped")
            else:
                el_n, g_n = cliff_elevation_cut(gains, phi=0.0)
                rec["cliff_gain"] = {a: gain_at(el_n, g_n, a) for a in REPORT_ANGLES}
                hdr = "      psi:      " + "".join(f"{a:>8}" for a in REPORT_ANGLES)
                print(hdr)
                print(
                    "      bracket:  "
                    + "".join(f"{rec['bracket_gain'][a]:8.2f}" for a in REPORT_ANGLES)
                )
                print(
                    "      gd-cliff: "
                    + "".join(f"{rec['cliff_gain'][a]:8.2f}" for a in REPORT_ANGLES)
                )
                print(
                    "      crest:    "
                    + "".join(f"{out['crest']['gain'][a]:8.2f}" for a in REPORT_ANGLES)
                )

        out["sides"][side] = rec

    return out, (el_c, g_c)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], epilog="See module docstring."
    )
    ap.add_argument("--design", default="dipoles.invvee")
    ap.add_argument(
        "--freqs",
        default="21.2",
        help="comma-separated design/measurement freqs in MHz",
    )
    ap.add_argument("--h0", type=float, default=6.1, help="pole height above crest, m")
    ap.add_argument("--crest-half-width", type=float, default=1.5)
    ap.add_argument("--slope-deg", type=float, default=20.0)
    ap.add_argument("--drop-land", type=float, default=7.62, help="crest-to-land, m")
    ap.add_argument("--drop-water", type=float, default=10.67, help="crest-to-water, m")
    ap.add_argument("--soil-eps", type=float, default=13.0)
    ap.add_argument("--soil-sigma", type=float, default=0.005)
    ap.add_argument("--water-eps", type=float, default=80.0, help="fresh water")
    ap.add_argument("--water-sigma", type=float, default=0.005, help="~5 if brackish")
    ap.add_argument("--no-nec2c", action="store_true", help="skip the cliff reference")
    ap.add_argument("--json", default=None, help="write goldens JSON here")
    ap.add_argument("--plot", default=None, help="write overlay PNG here")
    args = ap.parse_args()

    freqs = [float(f) for f in args.freqs.split(",")]
    results = []
    for f in freqs:
        band, _ = run_band(args, f)
        results.append(band)

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2) + "\n")
        print(f"\ngoldens -> {args.json}")

    if args.plot:
        plot_overlay(args, freqs[0], Path(args.plot))
        print(f"overlay -> {args.plot}")


def plot_overlay(args, freq, path):
    """One-band elevation overlay: crest + both effective-height brackets,
    validity bands shaded, nec2c cliff dashed."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    soil = ("finite", args.soil_eps, args.soil_sigma)
    water = ("finite", args.water_eps, args.water_sigma)
    fig, ax = plt.subplots(figsize=(9, 5.5))

    el, g, _ = solve_bracket(args.design, freq, args.h0, soil)
    ax.plot(el, g, label=f"crest h={args.h0} m (soil)", color="tab:brown")

    for side, drop, ground, color in (
        ("land", args.drop_land, soil, "tab:green"),
        ("water", args.drop_water, water, "tab:blue"),
    ):
        psi_crest, psi_plain, _, h_eff = validity_bands(
            args.h0, args.crest_half_width, args.slope_deg, drop
        )
        el2, g2, _ = solve_bracket(args.design, freq, h_eff, ground)
        ax.plot(el2, g2, label=f"{side} h_eff={h_eff:.1f} m", color=color)
        ax.axvline(psi_plain, color=color, ls=":", lw=1)
        if not args.no_nec2c:
            eps2, sig2 = ground[1], ground[2]
            deck = author_cliff_deck(
                args.design,
                freq,
                args.h0,
                soil,
                (eps2, sig2, args.crest_half_width, drop),
                2,
            )
            gains = run_nec2c_pattern(deck)
            if gains:
                eln, gn = cliff_elevation_cut(gains, phi=0.0)
                ax.plot(
                    eln, gn, ls="--", lw=1, color=color, label=f"{side} nec2c cliff"
                )
    ax.axvline(
        validity_bands(args.h0, args.crest_half_width, args.slope_deg, args.drop_land)[
            0
        ],
        color="tab:brown",
        ls=":",
        lw=1,
    )
    ax.set_xlim(0, 90)
    ax.set_xlabel("elevation (deg)")
    ax.set_ylabel("gain (dBi), azimuth max / cliff cut")
    ax.set_title(f"{args.design} @ {freq} MHz — levee brackets vs nec2c cliff")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)


if __name__ == "__main__":
    main()
