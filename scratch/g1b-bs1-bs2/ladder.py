"""Two-degree mesh ladders: do bs1 and bs2 walk to ONE limit on each deck?"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import probe_bs1_bs2 as P  # noqa: E402

LADDERS = {
    "bvd1": (
        lambda m: P.buried_dipole_build(11 * m, 1.0, True),
        None,
        (1, 3, 5, 9, 15, 27),
    ),
    "bhd10": (
        lambda m: P.buried_dipole_build(21 * m, 10.0, False),
        None,
        (1, 3, 5, 9, 15),
    ),
    "served_553": (P.served_build, None, (1, 3, 5, 9)),
    "crossing_g1": (
        lambda m: P.scale(P.t524.crossing_deck(1), m),
        P.t524.CROSSING_G1_QP,
        (1, 3, 5, 9),
    ),
}
for name in sys.argv[1:] or list(LADDERS):
    build, nqp, mults = LADDERS[name]
    prev = {1: None, 2: None}
    print(f"\n== {name} ==")
    print(
        f"{'mult':>4} {'bs1':>24} {'d bs1':>8} {'bs2':>24} {'d bs2':>8} {'|bs1-bs2|':>9}"
    )
    for m in mults:
        z = {}
        for d in (1, 2):
            z[d], _ = P.solve(build(m), d, nqp)
        row = f"{m:>4}"
        for d in (1, 2):
            dd = "" if prev[d] is None else f"{abs(z[d] - prev[d]):8.4f}"
            row += f" {z[d].real:12.4f}{z[d].imag:+12.4f}j {dd:>8}"
            prev[d] = z[d]
        row += f" {abs(z[1] - z[2]):9.4f}"
        print(row, flush=True)
