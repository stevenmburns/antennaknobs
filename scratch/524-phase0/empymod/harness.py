#!/usr/bin/env python
"""empymod second-oracle harness for momwire#524 phase 0 (buried-wire risk burn-down).

Computes, for every (soil, frequency, source-type, depth) cell of the SPEC
matrix (scratch/524-phase0/SPEC.md), the complex E-field (Ex, Ey, Ez) of a
UNIT point electric dipole (1 A*m current moment) buried in the ground
half-space, on the SPEC observation grids.  empymod is RUN as a licence-free
second oracle; its kernel is never transcribed.

Conventions and coordinate mapping (verified empirically, see SUMMARY.md)
-------------------------------------------------------------------------
SPEC frame:    air z > 0, ground z < 0, e^{+j w t}, eta = sigma + j w eps.
empymod frame: z positive DOWN, interface at depth=[0]; layer 0 (z_emp < 0)
               = air, layer 1 (z_emp > 0) = ground.  empymod's frequency-
               domain output matched the e^{+j w t} analytic Hertzian dipole
               (outgoing e^{-jkr}) WITHOUT conjugation, so no conjugation is
               applied anywhere.

Mapping (improper reflection z -> -z; E from J transforms as a vector, so
mirror symmetry holds exactly for electric-electric):

    x_emp = x_spec,  y_emp = y_spec,  z_emp = -z_spec

    HED (unit dipole along +x_spec = +x_emp):
        Ex_spec = +E(ab=11), Ey_spec = +E(ab=21), Ez_spec = -E(ab=31)
    VED (unit dipole along +z_spec, i.e. UP; = -z_emp direction):
        Ex_spec = -E(ab=13), Ey_spec = -E(ab=23), Ez_spec = +E(ab=33)

(ab = <receiver dir><source dir>, 1=x 2=y 3=z, empymod frame.)

Numerical method (measured, see SUMMARY.md)
-------------------------------------------
The default DLF Hankel transform showed errors up to ~27% at the largest
k*r of this matrix (wave regime; the log-spaced CSEM filters sample poorly
through the air branch point).  ht='quad' with a wide lambda range converges:
ppd=300 vs ppd=600 agree to <= 6e-3 at the worst points of the real
air/soil configuration, and to ~1e-6 in damped in-medium cases.  Therefore:

    PRIMARY : ht='quad', htarg={a:1e-8, b:300, limit:4000, pts_per_dec:600},
              xdirect=True (analytic direct term when src/rec share a layer).
    XCHECK  : same but pts_per_dec=300/limit=2000, and default ht='dlf';
              per-grid spreads vs PRIMARY are recorded in results.json.

Usage:  .venv/bin/python harness.py   (writes results.json + SUMMARY.md here)
"""

import json
import time
import warnings
from pathlib import Path

import numpy as np
import empymod

HERE = Path(__file__).resolve().parent

EPS0 = 8.8541878128e-12
MU0 = 4e-7 * np.pi

RES_AIR = 2e14  # empymod's customary "air" resistivity (sigma ~ 5e-15)
INTERFACE = [0.0]  # empymod depth array: single interface at z_emp = 0

PRIMARY = dict(
    ht="quad", htarg={"a": 1e-8, "b": 300.0, "limit": 4000, "pts_per_dec": 600}
)
XCHECK_QUAD = dict(
    ht="quad", htarg={"a": 1e-8, "b": 300.0, "limit": 2000, "pts_per_dec": 300}
)
XCHECK_DLF = dict(ht="dlf", htarg={})  # empymod defaults (key_201_2009)

SOILS = {
    "A": {"eps_r": 13.0, "sigma": 0.005},
    "B": {"eps_r": 20.0, "sigma": 0.03},
    "C": {"eps_r": 5.0, "sigma": 0.001},
}

# Observation grids in SPEC coordinates (x, y, z_spec).
T_LINE = [(x, 0.0, 1.0) for x in np.arange(2.0, 30.0 + 1e-9, 2.0)]
T_VERT = [(10.0, 0.0, z) for z in (0.1, 0.3, 1.0, 3.0, 10.0)]
M_LINE = [(x, 0.0, -0.5) for x in np.arange(1.0, 10.0 + 1e-9, 1.0)]
GRIDS = {"T-line": T_LINE, "T-vert": T_VERT, "M-line": M_LINE}


# Matrix cells.  HED point-dipole depth = fed-segment center of bhd10/bhd1
# (= d).  VED point-dipole depth = fed-segment center of bvd1, whose axis
# runs z_spec in [-(d+1), -d] with 11 segments fed at segment 6, so the
# fed-segment center sits at z_spec = -(d + 0.5).
def matrix_cells():
    cells = []
    # Full matrix at soil A / 7 MHz.
    for d in (0.02, 0.05, 0.10, 0.15):
        cells.append(("A", 7e6, "HED", d, d))
    for d in (0.05, 0.10, 0.15):
        cells.append(("A", 7e6, "VED", d, d + 0.5))
    # Soils B, C and 21 MHz: d = 0.05 and 0.15 only, bhd10 + bhd1 (= HED).
    for soil, f in (("A", 21e6), ("B", 7e6), ("B", 21e6), ("C", 7e6), ("C", 21e6)):
        for d in (0.05, 0.15):
            cells.append((soil, f, "HED", d, d))
    return cells


# ab codes (empymod frame) and spec-frame sign per component, per source type.
COMPONENT_MAP = {
    "HED": {"Ex": (11, +1.0), "Ey": (21, +1.0), "Ez": (31, -1.0)},
    "VED": {"Ex": (13, -1.0), "Ey": (23, -1.0), "Ez": (33, +1.0)},
}


def soil_model(soil):
    s = SOILS[soil]
    return [RES_AIR, 1.0 / s["sigma"]], [1.0, s["eps_r"]]


def run_dipole(src_emp, xs, ys, z_emp, res, eperm, freq, ab, settings):
    """One empymod.dipole call; returns (complex array, warning strings, dt)."""
    t0 = time.time()
    with warnings.catch_warnings(record=True) as wl:
        warnings.simplefilter("always")
        out = empymod.dipole(
            src=src_emp,
            rec=[np.asarray(xs), np.asarray(ys), z_emp],
            depth=INTERFACE,
            res=res,
            freqtime=freq,
            ab=ab,
            epermH=eperm,
            xdirect=True,
            verb=0,
            **settings,
        )
    warns = sorted({f"{w.category.__name__}: {w.message}" for w in wl})
    return np.atleast_1d(np.asarray(out, dtype=complex)), warns, time.time() - t0


def fields_on_points(points_spec, src_depth, src_type, res, eperm, freq, settings):
    """E_spec (n,3) on SPEC points for a unit buried dipole, plus metadata."""
    pts = np.asarray(points_spec, dtype=float)
    src_emp = [0.0, 0.0, float(src_depth)]  # z_emp = +depth (ground)
    E = np.zeros((len(pts), 3), dtype=complex)
    calls, all_warns = [], []
    # group receivers by common z_spec (empymod wants a single rec depth)
    for z_spec in sorted(set(pts[:, 2])):
        idx = np.where(pts[:, 2] == z_spec)[0]
        z_emp = -z_spec
        for ci, comp in enumerate(("Ex", "Ey", "Ez")):
            ab, sign = COMPONENT_MAP[src_type][comp]
            vals, warns, dt = run_dipole(
                src_emp, pts[idx, 0], pts[idx, 1], z_emp, res, eperm, freq, ab, settings
            )
            E[idx, ci] = sign * vals
            calls.append(
                {
                    "function": "empymod.dipole",
                    "ab": ab,
                    "spec_component": comp,
                    "spec_sign": sign,
                    "src_emp_xyz": src_emp,
                    "rec_emp_z": z_emp,
                    "rec_emp_x": pts[idx, 0].tolist(),
                    "rec_emp_y": pts[idx, 1].tolist(),
                    "depth": INTERFACE,
                    "res_ohm_m": list(res),
                    "epermH": list(eperm),
                    "freq_hz": freq,
                    "xdirect": True,
                    "ht": settings["ht"],
                    "htarg": settings["htarg"],
                    "signal": None,
                    "elapsed_s": round(dt, 3),
                    "warnings": warns,
                }
            )
            all_warns.extend(warns)
    return E, calls, all_warns


def c2pairs(arr):
    return [[float(v.real), float(v.imag)] for v in arr]


def rel_spread(E_alt, E_ref):
    """Max/median relative deviation, normalized per point by the largest
    component magnitude there (avoids blowups on symmetry-zero Ey)."""
    scale = np.max(np.abs(E_ref), axis=1, keepdims=True)
    d = np.abs(E_alt - E_ref) / scale
    return float(np.max(d)), float(np.median(d))


# --------------------------------------------------------------------------
# Independent closed form: unit (Il = 1 A*m) Hertzian dipole in a homogeneous
# medium, e^{+j w t}:
#   E = e^{-jkr}/(4 pi eta) [ k^2 ((rh x p) x rh)/r
#                             + (3 rh (rh.p) - p)(1/r^3 + jk/r^2) ],
#   eta = sigma + j w eps,  k^2 = -j w mu0 eta,  Im(k) <= 0.
# --------------------------------------------------------------------------
def analytic_fs_dipole(p_hat, r_vec, freq, eps_r=1.0, sigma=0.0):
    w = 2 * np.pi * freq
    eta = sigma + 1j * w * eps_r * EPS0
    k2 = -1j * w * MU0 * eta
    k = np.sqrt(k2)
    if k.imag > 0:
        k = -k
    r = np.linalg.norm(r_vec)
    rh = np.asarray(r_vec, dtype=float) / r
    p = np.asarray(p_hat, dtype=float)
    trans = np.cross(np.cross(rh, p), rh)
    longi = 3 * rh * np.dot(rh, p) - p
    return (
        np.exp(-1j * k * r)
        / (4 * np.pi * eta)
        * (k2 * trans / r + longi * (1.0 / r**3 + 1j * k / r**2))
    )


# --------------------------------------------------------------------------
# Self-checks
# --------------------------------------------------------------------------
def check_free_space():
    """Ground -> (eps_r 1, sigma ~0): buried-dipole field must recover the
    analytic free-space dipole.  Two variants:
      (a) ground identical to air: empymod detects the homogeneous fullspace
          and (with xdirect=True) uses its analytic path -> validates the
          sign/axis mapping and the time convention, essentially exactly.
      (b) ground different by 1 ppm: forces the true layered/Hankel code path
          -> bounds transform accuracy in the fully LOSSLESS corner (harder
          than any real cell, since real cells always have a lossy soil side).
    """
    d = 0.10
    pts = [
        (2.0, 0.0, 1.0),
        (10.0, 3.0, 2.0),
        (30.0, 0.0, 1.0),
        (3.0, -2.0, -0.5),
        (10.0, 0.0, 10.0),
    ]
    out = {}
    for variant, res, ep in (
        ("a_identical", [RES_AIR, RES_AIR], [1.0, 1.0]),
        ("b_forced_layered", [RES_AIR, RES_AIR * (1 + 1e-6)], [1.0, 1.0 + 1e-9]),
    ):
        rows = []
        for st, p_hat in (("HED", [1, 0, 0]), ("VED", [0, 0, 1])):
            for pt in pts:
                E, _, _ = fields_on_points([pt], d, st, res, ep, 7e6, PRIMARY)
                r_vec = np.array(pt) - np.array([0.0, 0.0, -d])
                E_an = analytic_fs_dipole(p_hat, r_vec, 7e6)
                err = float(np.max(np.abs(E[0] - E_an)) / np.max(np.abs(E_an)))
                rows.append({"source": st, "point_spec": list(pt), "rel_err": err})
        out[variant] = {"rows": rows, "max_rel_err": max(r["rel_err"] for r in rows)}
    return out


def check_skin_depth():
    """Soil-A fullspace at 7 MHz: broadside |E|*r slope vs -1/delta,
    delta = 1/alpha (general lossy formula) = 4.20 m."""
    er, sig = SOILS["A"]["eps_r"], SOILS["A"]["sigma"]
    w = 2 * np.pi * 7e6
    eps = er * EPS0
    alpha = (
        w
        * np.sqrt(MU0 * eps)
        * np.sqrt(0.5 * (np.sqrt(1 + (sig / (w * eps)) ** 2) - 1))
    )
    delta = 1.0 / alpha
    res = [1.0 / sig, (1.0 / sig) * (1 + 1e-6)]
    ep = [er, er + 1e-9]
    rs = np.arange(12.0, 26.0 + 1e-9, 2.0)
    vals = []
    for r in rs:  # broadside: HED along x, observe along y at same depth
        E, _, _ = run_dipole([0, 0, 0.1], [0.0], [r], 0.1, res, ep, 7e6, 11, PRIMARY)
        vals.append(abs(E[0]))
    logs = np.log(np.array(vals) * rs)
    slope = float(np.polyfit(rs, logs, 1)[0])
    return {
        "delta_m": float(delta),
        "expected_slope": float(-1 / delta),
        "fitted_slope": slope,
        "r_range_m": [float(rs[0]), float(rs[-1])],
        "rel_err": float(abs(slope + 1 / delta) / (1 / delta)),
    }


def check_reciprocity():
    """Below->above pair, soil A, 7 MHz, PRIMARY settings.
    G_zx(r2; r1) from a buried x-dipole vs G_xz(r1; r2) from an elevated
    z-dipole (empymod frame; ab 31 vs 13 with src/rec swapped)."""
    res, ep = soil_model("A")
    r1 = [0.0, 0.0, 0.1]  # emp: buried 0.1 m
    r2 = [10.0, 0.0, -1.0]  # emp: 1 m up in the air
    a, _, _ = run_dipole(r1, [r2[0]], [r2[1]], r2[2], res, ep, 7e6, 31, PRIMARY)
    b, _, _ = run_dipole(r2, [r1[0]], [r1[1]], r1[2], res, ep, 7e6, 13, PRIMARY)
    va, vb = complex(a[0]), complex(b[0])
    return {
        "G_zx_r2_r1": [va.real, va.imag],
        "G_xz_r1_r2": [vb.real, vb.imag],
        "rel_diff": float(abs(va - vb) / abs(va)),
    }


def check_depth_continuity():
    """Fixed observer (T-line x=10, z=+1), soil A, 7 MHz, HED; fine ladder
    0.02..0.15 step 0.01 must vary smoothly (no jumps)."""
    res, ep = soil_model("A")
    depths = np.round(np.arange(0.02, 0.15 + 1e-9, 0.01), 3)
    rows = []
    for d in depths:
        E, _, _ = fields_on_points([(10.0, 0.0, 1.0)], d, "HED", res, ep, 7e6, PRIMARY)
        rows.append(E[0])
    rows = np.array(rows)
    scale = np.max(np.abs(rows), axis=1)
    step = np.max(np.abs(np.diff(rows, axis=0)), axis=1) / scale[:-1]
    return {
        "depths_m": depths.tolist(),
        "Ex_abs": np.abs(rows[:, 0]).tolist(),
        "Ez_abs": np.abs(rows[:, 2]).tolist(),
        "max_adjacent_rel_step": float(np.max(step)),
        "adjacent_rel_steps": step.tolist(),
    }


# --------------------------------------------------------------------------
def main():
    t_start = time.time()
    print("== self-checks ==", flush=True)
    checks = {}
    checks["free_space"] = check_free_space()
    print(
        f"  free-space (a) mapped-exact max err: "
        f"{checks['free_space']['a_identical']['max_rel_err']:.2e}",
        flush=True,
    )
    print(
        f"  free-space (b) forced-layered max err: "
        f"{checks['free_space']['b_forced_layered']['max_rel_err']:.2e}",
        flush=True,
    )
    checks["skin_depth"] = check_skin_depth()
    print(
        f"  skin-depth slope {checks['skin_depth']['fitted_slope']:.4f} "
        f"vs {checks['skin_depth']['expected_slope']:.4f} "
        f"(rel err {checks['skin_depth']['rel_err']:.1%})",
        flush=True,
    )
    checks["reciprocity"] = check_reciprocity()
    print(
        f"  reciprocity rel diff: {checks['reciprocity']['rel_diff']:.2e}", flush=True
    )
    checks["depth_continuity"] = check_depth_continuity()
    print(
        f"  depth-continuity max adjacent step: "
        f"{checks['depth_continuity']['max_adjacent_rel_step']:.3f}",
        flush=True,
    )

    print("== matrix ==", flush=True)
    cells = []
    for soil, freq, st, d_spec, src_depth in matrix_cells():
        cid = f"{soil}_{freq / 1e6:g}MHz_{st}_d{d_spec:g}"
        res, ep = soil_model(soil)
        cell = {
            "id": cid,
            "soil": dict(id=soil, **SOILS[soil]),
            "freq_hz": freq,
            "source": {
                "type": st,
                "orientation_spec": "+x" if st == "HED" else "+z (up)",
                "moment": "unit point electric dipole, Il = 1 A*m",
                "spec_depth_param_d_m": d_spec,
                "src_depth_m": src_depth,
                "src_spec_xyz": [0.0, 0.0, -src_depth],
                "note": (
                    "point-dipole stand-in for bhd10/bhd1 fed-segment center"
                    if st == "HED"
                    else "point-dipole stand-in for bvd1; fed-segment center "
                    "is at z = -(d+0.5)"
                ),
            },
            "grids": {},
        }
        t0 = time.time()
        for gname, pts in GRIDS.items():
            E, calls, warns = fields_on_points(
                pts, src_depth, st, res, ep, freq, PRIMARY
            )
            E_q, _, w_q = fields_on_points(
                pts, src_depth, st, res, ep, freq, XCHECK_QUAD
            )
            E_d, _, w_d = fields_on_points(
                pts, src_depth, st, res, ep, freq, XCHECK_DLF
            )
            mq, medq = rel_spread(E_q, E)
            md, medd = rel_spread(E_d, E)
            cell["grids"][gname] = {
                "points_spec_xyz": [list(map(float, p)) for p in pts],
                "Ex": c2pairs(E[:, 0]),
                "Ey": c2pairs(E[:, 1]),
                "Ez": c2pairs(E[:, 2]),
                "units": "V/m per (A*m)",
                "calls": calls,
                "xcheck": {
                    "quad_ppd300_vs_primary": {"max_rel": mq, "med_rel": medq},
                    "dlf_default_vs_primary": {"max_rel": md, "med_rel": medd},
                    "xcheck_warnings": sorted(set(w_q + w_d)),
                },
            }
        print(
            f"  {cid}: done in {time.time() - t0:.0f}s "
            f"(worst quad-xcheck {max(cell['grids'][g]['xcheck']['quad_ppd300_vs_primary']['max_rel'] for g in GRIDS):.1e}, "
            f"worst dlf-xcheck {max(cell['grids'][g]['xcheck']['dlf_default_vs_primary']['max_rel'] for g in GRIDS):.1e})",
            flush=True,
        )
        cells.append(cell)

    results = {
        "meta": {
            "purpose": "momwire#524 phase 0 empymod second oracle",
            "spec": "scratch/524-phase0/SPEC.md",
            "empymod_version": empymod.__version__,
            "time_convention": "e^{+j w t} (matched analytic without conjugation)",
            "coordinate_mapping": (
                "x_emp=x_spec, y_emp=y_spec, "
                "z_emp=-z_spec; depth=[0]; layer0(z_emp<0)"
                "=air res 2e14/eps_r 1, layer1(z_emp>0)="
                "soil; HED: Ex=+E11,Ey=+E21,Ez=-E31; "
                "VED(+z_spec up): Ex=-E13,Ey=-E23,"
                "Ez=+E33"
            ),
            "primary_settings": {
                "ht": PRIMARY["ht"],
                "htarg": PRIMARY["htarg"],
                "xdirect": True,
            },
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_s": None,
        },
        "self_checks": checks,
        "cells": cells,
    }
    results["meta"]["elapsed_s"] = round(time.time() - t_start, 1)

    with open(HERE / "results.json", "w") as fh:
        json.dump(results, fh, indent=1)
    print(
        f"wrote results.json ({(HERE / 'results.json').stat().st_size / 1e6:.1f} MB) "
        f"in {results['meta']['elapsed_s']:.0f}s total",
        flush=True,
    )
    return results


if __name__ == "__main__":
    main()
