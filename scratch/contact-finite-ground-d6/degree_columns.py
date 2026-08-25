"""Is the contact gap a property of the BASIS or of the trunk?

momwire#603 U5 / D6. §3.5 measured the ground-induced shift
`delta = Z(soil) - Z(PEC)` for `BSplineSolver(degree=2)` against the licensed
binary and found the poor-soil row OPENING with mesh to 3.3 ohm. razor is
refused at contact over finite ground, and the question on the table is
whether it would land in the same place.

razor's basis is the TENT basis, which is exactly `BSplineSolver(degree=1)`.
Both degrees are Galerkin, so running d=1 beside d=2 isolates the basis: if
the gap is the same, the basis is exonerated and the gap belongs to the
trunk's ground handling, which razor shares. What razor does NOT share is the
testing scheme, and §4.3 locates its missing term there.

Deck: the stage-2 contact monopole, 5.3535 m, r = 5 mm, 14 MHz, base-fed,
against nec5cl on the same geometry. Difference-of-columns cancels each
formulation's own discretization offset at PEC.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

FREQ_MHZ = 14.0
WL = 299792458.0 / (FREQ_MHZ * 1e6)
RAD = 0.005
MONO_H = 5.3535
EXE = Path(os.path.expanduser(os.environ.get("NEC5_EXE", "")))

SOILS = {"poor": (5.0, 0.001), "average": (13.0, 0.005)}
LADDER = (11, 21, 41)


def _num(x):
    return f"{float(x):.6E}"


def deck(n, soil):
    gn = (
        "GN 1 0 0 0\n"
        if soil is None
        else f"GN 0 0 0 0 {_num(soil[0])} {_num(soil[1])} {_num(1.0)} {_num(0.0)} NOFILE\n"
    )
    return (
        "CM contact monopole — basis-vs-trunk columns\nCE\n"
        f"GW 1 {n} 0.0 0.0 0.0 0.0 0.0 {_num(MONO_H)} {_num(RAD)}\n"
        "GE 1 0\n" + gn + f"EX 0 1 1 1 {_num(1.0)} {_num(0.0)}\n"
        f"FR 0 1 0 0 {_num(FREQ_MHZ)} {_num(0.0)}\n"
        "XQ 0\nEN\n"
    )


def momwire_z(n, soil, degree):
    from momwire import BSplineSolver

    kw = dict(
        wires=[np.array([[0.0, 0.0, 0.0], [0.0, 0.0, MONO_H]])],
        n_per_edge_per_wire=[[n]],
        wire_radius=RAD,
        wavelength=WL,
        degree=degree,
        feed_model="segment",
        feed_wire_index=0,
        feed_arclength=0.0,
        ground_z=0.0,
    )
    if soil is not None:
        kw.update(ground_eps=soil, ground_model="sommerfeld")
    z, _ = BSplineSolver(**kw).compute_impedance()
    return complex(z)


def binary_z(n, soil):
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "m.nec").write_text(deck(n, soil))
        subprocess.run(
            [str(EXE)],
            input="m.nec\nm.out\n\n",
            capture_output=True,
            text=True,
            cwd=td,
            timeout=600,
        )
        out = (Path(td) / "m.out").read_text(errors="replace")
    row = [
        ln for ln in out.splitlines() if re.match(r"\s*1\s+\d+ \d+\s+1\.0000E\+00", ln)
    ]
    nums = re.findall(r"[-+]?\d\.\d+E[-+]\d+", row[0])
    return complex(float(nums[4]), float(nums[5]))


def _z(z):
    return f"{z.real:9.3f}{z.imag:+9.3f}j"


def main():
    print(f"contact monopole {MONO_H} m, r={RAD} m, {FREQ_MHZ} MHz, base-fed\n")
    print("delta = Z(soil) - Z(PEC); |diff| = |delta_momwire - delta_binary|\n")
    print(
        f"{'soil':<9s}{'N':>4s} | {'|diff| d=1 (tent)':>18s} {'|diff| d=2':>12s} "
        f"| {'delta d=1':>22s} {'delta binary':>22s}"
    )
    for name, soil in SOILS.items():
        for n in LADDER:
            pec_b = binary_z(n, None)
            pec_1 = momwire_z(n, None, 1)
            pec_2 = momwire_z(n, None, 2)
            d_b = binary_z(n, soil) - pec_b
            d_1 = momwire_z(n, soil, 1) - pec_1
            d_2 = momwire_z(n, soil, 2) - pec_2
            print(
                f"{name:<9s}{n:>4d} | {abs(d_1 - d_b):>18.3f} {abs(d_2 - d_b):>12.3f} "
                f"| {_z(d_1):>22s} {_z(d_b):>22s}"
            )
        print()


if __name__ == "__main__":
    main()
