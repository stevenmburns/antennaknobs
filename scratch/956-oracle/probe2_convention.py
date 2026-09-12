"""#956 Phase B gate 0: does the prototype's projector MEAN the same thing as
momwire's?

Before any block is assembled, the two `proj_fn`s must agree entry for entry
on a configuration where momwire's own grid is accurate — a well-separated
below source and above observer, which is the regime the #524 goldens already
pin. A convention slip (moment normalization, e^{+jwt}, the ground-projection
origin, the tangent contraction) shows up here as O(1), not as a subtle block
difference later.

This is a projector check, not a block check: no basis, no quadrature weights.
"""

import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from momwire import _sommerfeld_transmitted as trans  # noqa: E402

import proj_oracle as PO  # noqa: E402

C0 = 299792458.0
FREQ = 7.1e6
SOIL_A = (13.0, 0.005)
EPS0 = 8.8541878128e-12
GZ = 0.0


def medium():
    w = 2.0 * np.pi * FREQ
    eps_t = complex(SOIL_A[0]) - 1j * SOIL_A[1] / (w * EPS0)
    k_p = w / C0
    k_m = k_p * np.sqrt(eps_t)
    if k_m.imag > 0:
        k_m = np.conj(k_m)
    return eps_t, k_p, complex(k_m), w


def main():
    eps_t, k_p, k_m, w = medium()
    # A well-separated pair set: buried sources 0.05-0.15 m down under the
    # origin, observers 1-8 m up and 1-12 m out. Nothing near-singular.
    src = np.array([[0.0, 0.0, -0.05], [0.3, 0.0, -0.10], [0.0, 0.4, -0.15]])
    t_src = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    obs = np.array([[1.0, 0.0, 1.0], [5.0, 0.0, 2.0], [0.0, 7.0, 3.0], [3.0, 4.0, 8.0]])
    t_obs = np.array(
        [[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]]
    )

    r_max = float(
        np.max(
            np.hypot(
                np.hypot(
                    obs[:, 0][:, None] - src[:, 0][None, :],
                    obs[:, 1][:, None] - src[:, 1][None, :],
                ),
                obs[:, 2][:, None],
            )
        )
    )
    zp = GZ - src[:, 2]
    grid = trans.get_grid_below_above(
        eps_t,
        k_p,
        r_max * 1.05,
        float(zp.min()),
        float(zp.max()),
        w,
        mu=4.0e-7 * np.pi,
        r_min=0.5,
    )
    mw = trans.transmitted_field_proj_below_to_above(
        obs, t_obs, src, t_src, GZ, k_p, k_m, grid
    )
    proto = PO.make_proj(FREQ, *SOIL_A, workers=1)(obs, t_obs, src, t_src)

    print(f"k_p {k_p:.6e}   k_m {k_m:.6e}")
    print(f"{'obs':>4} {'src':>4} {'momwire':>28} {'prototype':>28} {'rel':>10}")
    worst = 0.0
    for i in range(len(obs)):
        for j in range(len(src)):
            a, b = mw[i, j], proto[i, j]
            rel = abs(a - b) / max(abs(b), 1e-300)
            worst = max(worst, rel)
            print(
                f"{i:>4} {j:>4} {a.real:13.6e}{a.imag:+13.6e}j "
                f"{b.real:13.6e}{b.imag:+13.6e}j {rel:10.3e}"
            )
    print(f"\nworst relative difference: {worst:.4e}")
    ratio = mw / proto
    print(
        f"ratio spread: mean {np.mean(ratio):.6f}  "
        f"std {np.std(ratio):.3e}  (a constant ratio = a normalization slip)"
    )


if __name__ == "__main__":
    main()
