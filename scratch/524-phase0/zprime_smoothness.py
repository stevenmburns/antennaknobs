"""momwire#524 phase 0, measurements (a)+(b).

(b) THE deciding experiment: smoothness of the below->above (transmitted)
scalars V_T/U_T in z' at fixed (rho, z) -- decides whether phase 1 tabulates
(rho, z, z') directly or (rho, z) surfaces over a z' ladder.  Method: dense
z' sweep; cubic interpolation in log|z'| from N log-spaced nodes; max rel
error vs direct evaluation; report N reaching 1e-3.  Two variants per
quantity: raw, and with the dominant in-medium factor e^{-j k_m |z'|}
divided out (NEC-4's sub-region trick).

(a) contour stress beyond SPEC: extreme soils, self-convergence + tail
health only (no oracle claims) -- verifying "benign", not assuming it.
"""

import sys
import numpy as np
from scipy.interpolate import CubicSpline

sys.path.insert(0, "/home/smburns/antennas/antennaknobs/scratch/524-phase0/proto")
import buried_proto as bp

RHO_Z = [(2.0, 0.5), (5.0, 0.1), (10.0, 1.0), (30.0, 1.0)]
LADDERS = (5, 7, 9, 13, 17, 25, 33)


def sweep_T(hs, rho, z, zps):
    V = np.empty(len(zps), complex)
    U = np.empty(len(zps), complex)
    for i, zp in enumerate(zps):
        val, _, _ = bp.integrals_T(hs, rho, z, zp, err=False)
        V[i], U[i] = val[0], val[1]
    return V, U


def run_smoothness(sid, eps_r, sigma, f, rho_z, zp_lo=0.02, zp_hi=8.0, n_dense=61):
    hs = bp.HalfSpace(f, eps_r, sigma)
    km = hs.km
    zps = -np.exp(np.linspace(np.log(zp_lo), np.log(zp_hi), n_dense))
    t = np.log(-zps)
    print(
        f"\n=== soil {sid} ({eps_r}/{sigma}) f={f / 1e6:g} MHz  "
        f"|k_m|={abs(km):.4f} /m  1/|k_m|={1 / abs(km):.2f} m  "
        f"z' in [{-zp_hi}, {-zp_lo}] m ==="
    )
    summary = {}
    for rho, z in rho_z:
        V, U = sweep_T(hs, rho, z, zps)
        for name, raw in (("V_T", V), ("U_T", U)):
            for mode in ("raw", "flat"):
                # zps < 0 so |z'| = -zps; dividing by e^{-j km |z'|} is
                # multiplying by e^{-j km zps}... careful: e^{-j km |z'|}
                # = e^{+j km zps}; divide => multiply by e^{-j km zps}.
                vals = raw * np.exp(-1j * km * zps) if mode == "flat" else raw
                scale = np.max(np.abs(vals))
                line, need = [], None
                for N in LADDERS:
                    idx = np.unique(
                        np.round(np.linspace(0, n_dense - 1, N)).astype(int)
                    )
                    approx = CubicSpline(t[idx], vals[idx].real)(t) + 1j * CubicSpline(
                        t[idx], vals[idx].imag
                    )(t)
                    err = np.max(np.abs(approx - vals)) / scale
                    line.append(f"N={N}:{err:.1e}")
                    if err < 1e-3:
                        need = N
                        break
                summary.setdefault((name, mode), []).append(need)
                print(
                    f"  rho={rho:5.1f} z={z:4.1f}  {name} {mode:4s}: "
                    f"{'  '.join(line)}   -> N(1e-3) = {need or '>33'}"
                )
    for (name, mode), needs in summary.items():
        ok = [n for n in needs if n]
        print(
            f"  {sid} {name} {mode}: worst N(1e-3) = "
            f"{max(ok) if len(ok) == len(needs) else '>33'}"
        )


def run_contour_stress():
    print("\n=== (a) contour stress, extreme soils (self-convergence only) ===")
    cases = [
        ("seawater-class", 81.0, 4.0, 7e6),
        ("wet-clay", 13.0, 0.05, 7e6),
        ("near-lossless", 13.0, 1e-4, 7e6),
        ("target-A-21MHz", 13.0, 0.005, 21e6),
    ]
    pts = [
        (2.0, 0.5, -0.05),
        (10.0, 1.0, -0.15),
        (30.0, 1.0, -0.02),
        (0.05, 0.02, -0.02),
    ]
    for name, er, sg, f in cases:
        hs = bp.HalfSpace(f, er, sg)
        lt = abs(hs.eps_t.imag) / hs.eps_t.real
        worst_rel, nonconv = 0.0, 0
        for rho, z, zp in pts:
            _, relT, qT = bp.integrals_T(hs, rho, z, zp, err=True)
            _, relR, qR = bp.integrals_R(hs, rho, -abs(z), zp, shared="m", err=True)
            for rel, q in ((relT, qT), (relR, qR)):
                if rel is not None:
                    worst_rel = max(worst_rel, rel)
                if q is not None and not q.tail_converged:
                    nonconv += 1
        print(
            f"  {name:16s} eps~={hs.eps_t:.4g}  losstan={lt:.3g}  "
            f"|k_m|/k_p={abs(hs.km) / hs.kp:.2f}:  worst selfconv "
            f"{worst_rel:.2e}  nonconvergent tails {nonconv}"
        )


if __name__ == "__main__":
    run_smoothness("A", 13.0, 0.005, 7e6, RHO_Z)
    run_smoothness("B", 20.0, 0.03, 7e6, RHO_Z)
    run_smoothness("A21", 13.0, 0.005, 21e6, RHO_Z[:3])
    run_contour_stress()
