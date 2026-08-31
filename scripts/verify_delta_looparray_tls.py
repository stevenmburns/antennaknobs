"""Verify that a TL-driven array reproduces the direct phase-drive pattern.

Step 1 (scripts/tune_delta_looparray_broadside.py) tuned the loop geometry
so each loop is 100+0j when driven directly with equal voltages. Sweeping
the V_loop2 phase steers the beam in azimuth (0° → broadside, 60° → ~9°
off broadside).

This script then substitutes in two 100Ω transmission lines from a single
central driver. With matched loads, a TL of length L delivers a voltage
phase delay of βL = 2πL/λ to the loop. The phase difference between the
two loops is 2π(L₁−L₂)/λ. For a 60° (=π/3) shift at 28.47 MHz (λ ≈ 10.53 m):
    L₁ − L₂ = λ/6 ≈ 1.755 m

We pick L₁ = del_y − 0.5·λ/6 and L₂ = del_y + 0.5·λ/6 (symmetric around
del_y), then compare the TL-driven impedance and pattern against the
direct phase-drive case.
"""

from __future__ import annotations

import itertools
import math
from types import MappingProxyType

import numpy as np

from antennaknobs import AntennaBuilder, Transform, TransformStack
from antennaknobs.engines.momwire import MomwireEngine

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from tune_delta_looparray_broadside import (
    BroadsideTuningBuilder,
    evaluate as evaluate_direct,
)


# Tuned at broadside (V_loop1 = V_loop2 = 1+0j) for Z = 100+0j.
TUNED = {
    "length_factor": 1.068115,
    "angle_deg": 62.4141,
    "del_y": 4.068715,
}


class TLArrayBuilder(AntennaBuilder):
    """Tuned delta-loop pair with a central driver and two TLs. TL lengths
    are parameters so we can sweep them; default values target a 60° phase
    shift between loops (matched-load approximation)."""

    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            "length_factor": TUNED["length_factor"],
            "angle_deg": TUNED["angle_deg"],
            "slant_deg": 0.0,
            "del_y": TUNED["del_y"],
            "tl_z0": 100.0,
            "tl_len_1": TUNED["del_y"] - 0.5 * (299.792458 / 28.47) / 6.0,
            "tl_len_2": TUNED["del_y"] + 0.5 * (299.792458 / 28.47) / 6.0,
        }
    )

    def build_tls(self):
        return self.tls

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
        tups.extend(build_path([TT, SS], n_seg1, 1 + 0j))  # loop1 feed (gets nullified)
        tups.extend(build_path([SSS, AAA, BBB, TTT], n_seg0, None))
        tups.extend(
            build_path([SSS, TTT], n_seg1, 1 + 0j)
        )  # loop2 feed (gets nullified)

        WW = (SS[0], eps, SS[1])
        WWW = ry(WW)
        self.tls = []
        tups.extend(
            build_path([WWW, WW], n_seg1, 1 + 0j)
        )  # central driver (the real source)

        # Same TL wiring as delta_looparray_with_tls, but lengths are explicit
        feedpoints = [(i, x) for i, x in enumerate(tups, start=1) if x[3] is not None]
        assert len(feedpoints) == 3
        tl_lengths = (self.tl_len_1, self.tl_len_2)
        for (idx, (p0, p1, nsegs, _ev)), tl_length in zip(
            feedpoints[:2], tl_lengths, strict=True
        ):
            self.tls.append(
                (
                    idx,
                    (n_seg1 + 1) // 2,
                    len(tups),
                    (n_seg1 + 1) // 2,
                    self.tl_z0,
                    tl_length,
                )
            )
            tups[idx - 1] = (p0, p1, nsegs, None)

        return tups


def evaluate_tl(b):
    e = MomwireEngine(b)
    z = e.impedance()
    ff = e.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    rings = np.array(ff.rings)
    flat = rings.argmax()
    t_idx, p_idx = np.unravel_index(flat, rings.shape)
    return z[0], float(ff.max_gain), float(ff.phis[p_idx]), float(ff.thetas[t_idx])


def main():
    wavelength = 299.792458 / 28.47
    delta_l = wavelength / 6.0  # λ/6 for 60° phase

    # Direct phase-drive reference at 60°
    bd = BroadsideTuningBuilder()
    for k, v in TUNED.items():
        setattr(bd, k, v)
    bd.v_loop2 = complex(math.cos(math.radians(60.0)), math.sin(math.radians(60.0)))
    z1, z2, peak, phi, theta = evaluate_direct(bd)
    print("DIRECT PHASE DRIVE (V_loop1=1, V_loop2=1∠60°):")
    print(f"  Z_loop1 = {z1.real:7.2f}{z1.imag:+7.2f}j")
    print(f"  Z_loop2 = {z2.real:7.2f}{z2.imag:+7.2f}j")
    print(f"  peak gain = {peak:6.2f} dBi at phi={phi:5.1f}°, theta={theta:4.1f}°")
    print()

    # TL-driven version: V_loop2 should lead V_loop1 by 60°, so V_loop2 needs
    # LESS TL delay → L2 < L1. (For a matched TL, V_load = V_in · e^(-jβL).)
    btl = TLArrayBuilder()
    btl.tl_len_1 = TUNED["del_y"] + 0.5 * delta_l
    btl.tl_len_2 = TUNED["del_y"] - 0.5 * delta_l
    print(f"TL-DRIVEN (Z0=100, L1={btl.tl_len_1:.4f} m, L2={btl.tl_len_2:.4f} m,")
    print(f"          ΔL = {delta_l:.4f} m = λ/6):")
    zd, peak, phi, theta = evaluate_tl(btl)
    print(
        f"  Z_driver = {zd.real:7.2f}{zd.imag:+7.2f}j  (expect ~50Ω: 100Ω matched TLs in parallel)"
    )
    print(f"  peak gain = {peak:6.2f} dBi at phi={phi:5.1f}°, theta={theta:4.1f}°")


if __name__ == "__main__":
    main()
