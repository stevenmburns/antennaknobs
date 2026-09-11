"""#956 near-node unit, gate: the in-medium kernel against momwire's own.

G4c (3.160e-04 against empymod) is the prototype's WARRANT for regime 2, not a
gate on this geometry — it was taken on the #524 SPEC grids, which are not the
near-node configurations this unit queries. So the same check gate 0 did for the
transmitted family, on the pairs that matter: shallow below observers on the
wire surface against below sources from the rise and the hub.

Like for like: momwire's `remainder_field_proj_below` returns the REMAINDER, and
its below/below block is direct at k_m plus image MINUS that. The prototype's
twin is `field_remainder(shared="m")`, not `field_in_medium`, which composes all
three. Pairing the total against the remainder is a silent decade of error and
the docstring in `_sommerfeld_below` says so.
"""

import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from momwire import _sommerfeld_below as below  # noqa: E402

import proj_oracle as PO  # noqa: E402

C0 = 299792458.0
FREQ = 7.1e6
SOIL_A = (13.0, 0.005)
EPS0 = 8.8541878128e-12
MU0 = 4.0e-7 * np.pi
GZ = 0.0
A_WIRE = 5e-4


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
    # observers ON THE WIRE SURFACE at rho = a, shallow (the node-touching
    # bases live from z = 0 down); sources on the rise axis and at the hub.
    obs = np.array(
        [
            [A_WIRE, 0.0, -0.003],
            [A_WIRE, 0.0, -0.02],
            [A_WIRE, 0.0, -0.075],
            [2 * A_WIRE, 0.0, -0.003],
            [4 * A_WIRE, 0.0, -0.003],
        ]
    )
    t_obs = np.array([[0.0, 0.0, 1.0]] * 5)
    src = np.array(
        [
            [0.0, 0.0, -0.02],
            [0.0, 0.0, -0.075],
            [0.0, 0.0, -0.15],
            [0.05, 0.0, -0.15],
            [0.5, 0.0, -0.15],
        ]
    )
    t_src = np.array(
        [
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
        ]
    )

    d_o = GZ - obs[:, 2]
    d_s = GZ - src[:, 2]
    rho = np.hypot(
        obs[:, 0][:, None] - src[:, 0][None, :],
        obs[:, 1][:, None] - src[:, 1][None, :],
    )
    hh = d_o[:, None] + d_s[None, :]
    r1_max = float(np.hypot(rho, hh).max())
    grid = below.get_grid_below(eps_t, k_p, r1_max * 1.05, w, mu=MU0)
    mw = below.remainder_field_proj_below(obs, t_obs, src, t_src, GZ, k_p, k_m, grid)
    proto = PO.make_proj_below(FREQ, *SOIL_A, workers=1)(obs, t_obs, src, t_src)

    print(f"k_p {k_p:.6e}   k_m {k_m:.6e}   r1_max {r1_max:.4f}")
    print(
        f"{'obs':>4} {'src':>4} {'rho':>9} {'h':>8} "
        f"{'momwire':>26} {'prototype':>26} {'rel':>10}"
    )
    worst = 0.0
    for i in range(len(obs)):
        for j in range(len(src)):
            a, b = mw[i, j], proto[i, j]
            rel = abs(a - b) / max(abs(b), 1e-300)
            worst = max(worst, rel)
            print(
                f"{i:>4} {j:>4} {rho[i, j]:9.5f} {hh[i, j]:8.4f} "
                f"{a.real:12.5e}{a.imag:+12.5e}j "
                f"{b.real:12.5e}{b.imag:+12.5e}j {rel:10.3e}"
            )
            sys.stdout.flush()
    ratio = mw / proto
    print(f"\nworst relative difference: {worst:.4e}")
    print(f"ratio spread: mean {np.mean(ratio):.6f}  std {np.std(ratio):.3e}")
    print("(a constant ratio would be a normalization or sign-convention slip)")


if __name__ == "__main__":
    main()
