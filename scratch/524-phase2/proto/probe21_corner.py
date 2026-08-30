"""A-2 session 5, probe 21: validate the designed near-interface tables.

Ledger (DERIVATION-NEAR-INTERFACE.md §6):
  21a  designed == shipped contour tables where the latter converges
  21b  Lambda / ray-panel independence at corner-adjacent points
  21c  singular structure: s*U -> 1, s*kp^2 V -> 2/(1+eps), s*dzW -> -(e-1)/(e+1),
       dW/d ln s -> -(eps-1)/(eps+1)
  21d  eps = 1: U = kp^2 V = e^{-jkR}/R exact, W = dzW = 0
  21e  auxiliary surfaces are the derivatives they claim (FD check)

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe21_corner.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "567-phase0" / "proto"))

import corner_tables as ct  # noqa: E402
from mp_cross import mp_tables  # noqa: E402  (the shipped-path contour tables)
from momwire._sommerfeld_transmitted import k_medium  # noqa: E402

WL7 = 42.83100850350743  # 299792458/7e6
K_P = 2.0 * np.pi / WL7
OMEGA = 2.0 * np.pi * 7.0e6
EPS0 = 8.8541878128e-12
EPS_T = 13.0 - 1j * 0.005 / (OMEGA * EPS0)  # soil A at 7 MHz
A_WIRE = 1e-3

out = {}


def rel(a, b):
    sc = max(abs(a), abs(b), 1e-300)
    return abs(a - b) / sc


def report(name, val):
    out[name] = val
    print(f"{name}: {val}")


def main():
    print(f"eps_t = {EPS_T:.4f}, k_p = {K_P:.6f}, k_m = {k_medium(EPS_T, K_P):.6f}")

    # --- 21a: overlap vs the shipped contour tables ----------------------
    pts = [
        (0.0, 1.0, -0.5),
        (0.0, 0.30, -0.15),
        (0.0, 0.05, -0.02),
        (0.5, 0.20, -0.30),
        (2.0, 1.00, -0.15),
        (0.05, 0.02, -0.15),
    ]
    worst = {k: 0.0 for k in ("U", "V", "W", "dzW")}
    t0 = time.time()
    for rho, z, zp in pts:
        old = mp_tables(EPS_T, K_P, rho, z, zp, rtol=1e-11)
        new = ct.designed_tables(EPS_T, K_P, rho, z, zp, rtol=1e-11)
        for k in worst:
            worst[k] = max(worst[k], rel(complex(old[k]), complex(new[k])))
    report("21a_overlap_max_rel", {k: f"{v:.3e}" for k, v in worst.items()})
    print(f"  ({time.time() - t0:.1f}s for {len(pts)} pts x 2 paths)")

    # --- 21b: Lambda / panel independence at corner-adjacent points ------
    cpts = [
        (A_WIRE, 0.0, 0.0),  # the corner value, R = a
        (0.0, A_WIRE, 0.0),  # on-axis, z = a, z' = 0 exact
        (0.0, 0.0, -A_WIRE),  # on-axis, z = 0 exact
        (0.0, 2e-4, -1e-4),  # deep inside the old dead zone
        (5e-4, 1e-3, 0.0),
    ]
    worst_b = 0.0
    t0 = time.time()
    for rho, z, zp in cpts:
        v8 = ct.six_point(EPS_T, K_P, rho, z, zp, rtol=1e-11, lam_mult=8.0)
        v12 = ct.six_point(EPS_T, K_P, rho, z, zp, rtol=1e-11, lam_mult=12.0)
        m = float(np.max(np.abs(v8 - v12) / np.maximum(np.abs(v8), 1e-300)))
        worst_b = max(worst_b, m)
    report("21b_lambda_independence_max_rel", f"{worst_b:.3e}")
    print(f"  ({time.time() - t0:.1f}s for {len(cpts)} pts x 2 Lambdas)")

    # --- 21c: singular structure at rho = 0, s -> 0 ----------------------
    e = EPS_T
    stat_V = 2.0 / (1.0 + e)
    stat_dzW = -(e - 1.0) / (e + 1.0)
    rows = {}
    svals = (1e-3, 1e-4, 1e-5)
    tabs = {
        s: ct.six_point(EPS_T, K_P, 0.0, s / 2.0, -s / 2.0, rtol=1e-11) for s in svals
    }
    for s in svals:
        t = tabs[s]
        rows[s] = dict(
            sU=complex(s * t[0]),
            sV=complex(s * K_P * K_P * t[1]),
            sdzW=complex(s * t[3]),
        )
    s1, s2 = 1e-4, 1e-5
    dlog = np.log(s2 / s1)
    wslope = (complex(tabs[s2][2]) - complex(tabs[s1][2])) / dlog
    report("21c_sU_at_1e-5", f"{rows[1e-5]['sU']:.8f}  (target 1)")
    report("21c_sKp2V_at_1e-5", f"{rows[1e-5]['sV']:.8f}  (target {stat_V:.8f})")
    report("21c_sdzW_at_1e-5", f"{rows[1e-5]['sdzW']:.8f}  (target {stat_dzW:.8f})")
    report("21c_dW_dlns", f"{wslope:.8f}  (target {stat_dzW:.8f})")
    out["21c_rel"] = {
        "sU": f"{rel(rows[1e-5]['sU'], 1.0):.3e}",
        "sV": f"{rel(rows[1e-5]['sV'], complex(stat_V)):.3e}",
        "sdzW": f"{rel(rows[1e-5]['sdzW'], complex(stat_dzW)):.3e}",
        "dWdlns": f"{rel(wslope, complex(stat_dzW)):.3e}",
    }
    print(f"21c rel: {out['21c_rel']}")

    # --- 21d: eps = 1 closed form ---------------------------------------
    worst_d = 0.0
    worst_w = 0.0
    for rho, z, zp in [
        (0.0, 0.3, -0.2),
        (A_WIRE, 0.0, 0.0),
        (0.0, 1e-4, 0.0),
        (0.7, 0.4, -0.9),
    ]:
        t = ct.six_point(1.0, K_P, rho, z, zp, rtol=1e-11)
        R = np.hypot(rho, z - zp)
        g = np.exp(-1j * K_P * R) / R
        worst_d = max(
            worst_d,
            rel(complex(t[0]), complex(g)),
            rel(complex(K_P * K_P * t[1]), complex(g)),
        )
        worst_w = max(worst_w, abs(t[2]) / abs(g), abs(t[3]) / abs(g))
    report("21d_eps1_UV_vs_greens_max_rel", f"{worst_d:.3e}")
    report("21d_eps1_W_dzW_over_G", f"{worst_w:.3e}")

    # --- 21e: auxiliary surfaces are the claimed derivatives -------------
    rho0, z0, zp0 = 0.3, 0.25, -0.35
    h = 1e-5
    v_pp = ct.six_point(EPS_T, K_P, rho0, z0 + h, zp0 + h, rtol=1e-12)
    v_pm = ct.six_point(EPS_T, K_P, rho0, z0 + h, zp0 - h, rtol=1e-12)
    v_mp = ct.six_point(EPS_T, K_P, rho0, z0 - h, zp0 + h, rtol=1e-12)
    v_mm = ct.six_point(EPS_T, K_P, rho0, z0 - h, zp0 - h, rtol=1e-12)
    base = ct.six_point(EPS_T, K_P, rho0, z0, zp0, rtol=1e-12)
    fd_dzpv = (
        complex(v_pp[1]) - complex(v_pm[1]) - complex(v_mp[1]) + complex(v_mm[1])
    ) / (4.0 * h * h)
    fd_dzpw = (complex(v_pp[2] + v_mp[2]) - complex(v_pm[2] + v_mm[2])) / (4.0 * h)
    fd_dzw = (complex(v_pp[2] + v_pm[2]) - complex(v_mp[2] + v_mm[2])) / (4.0 * h)
    report("21e_dzpV_fd_rel", f"{rel(fd_dzpv, complex(base[4])):.3e}")
    report("21e_dzpW_fd_rel", f"{rel(fd_dzpw, complex(base[5])):.3e}")
    report("21e_dzW_fd_rel", f"{rel(fd_dzw, complex(base[3])):.3e}")

    res = HERE.parent / "results"
    res.mkdir(exist_ok=True)
    (res / "probe21-corner.json").write_text(json.dumps(out, indent=1))
    print("saved results/probe21-corner.json")


if __name__ == "__main__":
    main()
