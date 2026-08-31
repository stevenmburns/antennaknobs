"""Tune delta_looparray_with_tls geometry for broadside operation.

Strategy: ignore the TLs and central driver for tuning. Drive the two
loop ports directly with V_loop1 = V_loop2 = 1+0j (broadside) and tune
length_factor + angle_deg for Z_loop ≈ 100+0j at the design freq.

Once we have a clean broadside geometry, the TL design (a separate step)
sizes the two TL lengths so a central 100Ω-matched driver delivers the
desired phase shift (e.g. 60°) between the loops — that's beam steering
on top of a tuned-broadside antenna.

Usage:
    .venv/bin/python scripts/tune_delta_looparray_broadside.py
    .venv/bin/python scripts/tune_delta_looparray_broadside.py --phase-deg 60
"""

from __future__ import annotations

import itertools
import argparse
import math
from types import MappingProxyType

import numpy as np
from scipy.optimize import minimize

from antennaknobs import AntennaBuilder, Transform, TransformStack
from antennaknobs.engines.momwire import MomwireEngine


class BroadsideTuningBuilder(AntennaBuilder):
    """Same delta-loop pair as delta_looparray_with_tls, minus the central
    driver wire and the TLs. Loops are direct ports with caller-supplied
    voltages."""

    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            "length_factor": 1.0664,
            "angle_deg": 61.2377,
            "slant_deg": 0.0,
            "del_y": 4.0,
            "v_loop2": 1 + 0j,  # V at loop2; V_loop1 fixed to 1+0j
        }
    )

    def build_wires(self):
        eps = 0.05
        b = self.base
        wavelength = 299.792458 / self.design_freq
        driver = wavelength * self.length_factor
        angle = math.radians(self.angle_deg)
        cos_t = math.cos(angle)
        tan_t = math.tan(angle)

        def build_path(lst, ns, ex):
            return ((a, b, ns, ex) for a, b in itertools.pairwise(lst))

        def ry(p):
            return p[0], -p[1], p[2]

        n_seg0 = self.nominal_nsegs
        n_seg1 = max(3, self.nominal_nsegs // 7)

        d = driver
        h = (cos_t * (d - 2 * eps) + 2 * eps) / (2 * (cos_t + 1))
        S = (0, eps, b - (h - eps) * tan_t)
        A = (0, h, b)
        B, T = ry(A), ry(S)

        st = TransformStack()
        st.push(Transform.translate(0, 0, b))
        st.push(Transform.rotX(-self.slant_deg))
        st.push(Transform.translate(0, self.del_y, -b))
        SS, AA, BB, TT = st.hit(S), st.hit(A), st.hit(B), st.hit(T)
        SSS, AAA, BBB, TTT = ry(SS), ry(AA), ry(BB), ry(TT)

        tups = []
        tups.extend(build_path([SS, AA, BB, TT], n_seg0, None))
        tups.extend(build_path([TT, SS], n_seg1, 1 + 0j))
        tups.extend(build_path([SSS, AAA, BBB, TTT], n_seg0, None))
        tups.extend(build_path([SSS, TTT], n_seg1, complex(self.v_loop2)))
        return tups


def evaluate(b):
    """Return (Z_loop1, Z_loop2, peak_gain_dBi, peak_phi_deg, peak_theta_deg).

    Loops are stacked along y, so the array axis is y. NEC convention has
    phi=0 along +x; broadside (perpendicular to array axis) is therefore
    phi=0 or 180, and end-fire is phi=90 or 270.
    """
    e = MomwireEngine(b)
    zs = e.impedance()
    ff = e.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    rings = np.array(ff.rings)
    flat = rings.argmax()
    t_idx, p_idx = np.unravel_index(flat, rings.shape)
    return (
        zs[0],
        zs[1],
        float(ff.max_gain),
        float(ff.phis[p_idx]),
        float(ff.thetas[t_idx]),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase-deg",
        type=float,
        default=0.0,
        help="Phase of V_loop2 relative to V_loop1 (degrees).",
    )
    ap.add_argument(
        "--z0", type=float, default=100.0, help="Per-loop target impedance."
    )
    ap.add_argument(
        "--opt-gain", action="store_true", help="Add peak-gain reward to the objective."
    )
    args = ap.parse_args()

    v2 = complex(
        math.cos(math.radians(args.phase_deg)), math.sin(math.radians(args.phase_deg))
    )
    b = BroadsideTuningBuilder()
    b.v_loop2 = v2

    def report(tag):
        z1, z2, peak, p_phi, p_th = evaluate(b)
        print(f"{tag}:")
        print(f"  Z_loop1 = {z1.real:7.2f}{z1.imag:+7.2f}j")
        print(f"  Z_loop2 = {z2.real:7.2f}{z2.imag:+7.2f}j")
        print(f"  peak gain = {peak:6.2f} dBi at phi={p_phi:5.1f}°, theta={p_th:4.1f}°")

    report(f"baseline (phase={args.phase_deg}°, z0={args.z0})")

    knob_names = ["length_factor", "angle_deg", "del_y"]
    x0 = [getattr(b, n) for n in knob_names]
    bounds = [(x * 0.7, x * 1.3) for x in x0]

    def objective(xs):
        for n, x in zip(knob_names, xs, strict=True):
            setattr(b, n, x)
        try:
            z1, z2, peak, _, _ = evaluate(b)
        except Exception:  # noqa: BLE001 — probe harness — a failing case is recorded and the sweep continues
            return 1e9
        cost = abs(z1 - args.z0) + abs(z2 - args.z0)
        if args.opt_gain:
            cost -= 10.0 * peak
        return cost

    res = minimize(
        objective,
        x0=x0,
        method="Powell",
        options={"maxiter": 200, "disp": True, "xtol": 1e-4},
        bounds=bounds,
    )
    for n, x in zip(knob_names, res.x, strict=True):
        setattr(b, n, x)
    print()
    print("optimised:")
    for n in knob_names:
        print(f"  {n:18s} = {getattr(b, n):.6f}")
    report("final")


if __name__ == "__main__":
    main()
