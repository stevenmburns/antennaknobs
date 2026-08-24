"""momwire#524 phase 0, measurement (c): momwire's _d12 at swapped arguments
reproduces the below/below (± = −) kernel pair.

The literature finding (BURIED-FORMULATION-SOURCES.local.md §3.2, verified
against the AGARD page images 2026-08-22): momwire's shipped d1/d2 are the
AGARD D₁/D₂ at ± = + (observer medium = air). The ± = − pair is

    D1m = 2/(γp + γm) − 2 k_m²/(γm (k_p² + k_m²))
    D2m = 2/(k_p² γm + k_m² γp) − 2/(γm (k_p² + k_m²))

which should equal _d12(lam, k1=k_air, k2=k_ground) — the same code with the
media swapped. If this holds to machine precision over the integration domain
(real axis + first-quadrant detour points, all SPEC soils, 7 and 21 MHz), the
whole SommerfeldGrid architecture reuses for buried radials with a sign flip.

Also checks that _gamma's vertical-cut realization agrees with the principal
root on that domain (they may differ only across the cuts, which the contour
never crosses).
"""

import numpy as np
import sys

sys.path.insert(0, "/home/smburns/antennas/antennaknobs/momwire/src")
from momwire._sommerfeld import _d12, _gamma

C = 299792458.0
EPS0 = 8.8541878128e-12

SOILS = {"A": (13.0, 0.005), "B": (20.0, 0.03), "C": (5.0, 0.001)}
FREQS = [7e6, 21e6]


def kpair(f, eps_r, sigma):
    w = 2 * np.pi * f
    kp = w / C
    eps_t = eps_r - 1j * sigma / (w * EPS0)
    km = kp * np.sqrt(eps_t)
    if km.imag > 0:
        km = -km
    return kp, km


def d12_minus_independent(lam, kp, km):
    gp = _gamma(lam, kp)
    gm = _gamma(lam, km)
    kps, kms = kp * kp, km * km
    d1 = 2.0 / (gp + gm) - 2.0 * kms / (gm * (kps + kms))
    d2 = 2.0 / (kps * gm + kms * gp) - 2.0 / (gm * (kps + kms))
    return d1, d2


def lam_domain(kp, km):
    """Real axis through/past both branch points + a first-quadrant detour."""
    kmax = max(kp, abs(km))
    real = np.linspace(1e-4 * kp, 8 * kmax, 4001)
    detour = np.linspace(1e-4 * kp, 1.4 * kmax, 800) + 0.35j * kmax * np.sin(
        np.linspace(0, np.pi, 800)
    )
    return np.concatenate([real, detour])


worst = 0.0
worst_where = None
gamma_worst = 0.0
for sid, (er, sg) in SOILS.items():
    for f in FREQS:
        kp, km = kpair(f, er, sg)
        lam = lam_domain(kp, km)
        # momwire's normal order is _d12(lam, k1=ground, k2=air); the claim is
        # that the SWAPPED call (k1=air, k2=ground) is the ± = − pair.
        d1_sw, d2_sw, _ = _d12(lam, kp, km)
        d1_ind, d2_ind = d12_minus_independent(lam, kp, km)
        r1 = np.max(np.abs(d1_sw - d1_ind) / np.max(np.abs(d1_ind)))
        r2 = np.max(np.abs(d2_sw - d2_ind) / np.max(np.abs(d2_ind)))
        m = max(r1, r2)
        if m > worst:
            worst, worst_where = m, (sid, f)
        # principal root vs vertical-cut realization on the domain
        for k in (kp, km):
            g_vc = _gamma(lam, k)
            g_pr = np.sqrt(lam * lam - k * k)
            g_pr = np.where(g_pr.real < 0, -g_pr, g_pr)
            gm_rel = np.max(np.abs(g_vc - g_pr) / np.maximum(np.abs(g_pr), 1e-300))
            gamma_worst = max(gamma_worst, gm_rel)

print(
    f"d12(swapped args) vs independent ±=− pair: worst rel {worst:.3e} at {worst_where}"
)
print(f"_gamma vertical-cut vs principal root on domain: worst rel {gamma_worst:.3e}")
print("PASS" if worst < 1e-13 and gamma_worst < 1e-12 else "FAIL")
