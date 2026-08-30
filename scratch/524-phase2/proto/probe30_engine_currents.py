#!/usr/bin/env python3
"""#524 phase 2 adjudicator 1: does the ENGINE's junction current satisfy
its own AGARD condition (I continuous, I'+/I'- = eps+/eps-)?

Parses the existing phase-0 crossing captures (anchor-crossing-x*) —
currents were already printed (PT default + PQ). No engine re-run.

Convention gate: e^{+jwt}, eps_t = eps_r - j sigma/(w eps0).
"""

import re
import json
import cmath
import math
from pathlib import Path

ORACLE = Path.home() / "antennas/antennaknobs/scratch/524-phase0/oracle"
EPS_R, SIGMA, F = 13.0, 0.005, 7.0e6
EPS0 = 8.8541878128e-12
W = 2 * math.pi * F
EPS_T = EPS_R - 1j * SIGMA / (W * EPS0)
K0 = W / 299792458.0
KM = K0 * cmath.sqrt(EPS_T)
assert abs(cmath.exp(-1j * KM * 1.0)) < 1.0, "e^{-jk-R} must decay"
AGARD_RATIO = 1.0 / EPS_T  # eps+/eps- ; slope jump I'+ / I'- expected

CUR_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+([-\d.E+]+)\s+([-\d.E+]+)\s+([-\d.E+]+)\s+"
    r"([-\d.E+]+)\s+([-\dE.+]+)\s+([-\dE.+]+)\s+([-\dE.+]+)\s+([-\d.]+)\s*$"
)


def parse_currents(path):
    """-> {tag: [(elem, I complex), ...]} from the Wire Currents table."""
    lines = path.read_text().splitlines()
    out = {}
    in_cur = False
    for ln in lines:
        if "- - - Wire Currents - - -" in ln:
            in_cur = True
            continue
        if in_cur and "Charge Densities" in ln:
            break
        if not in_cur:
            continue
        m = CUR_RE.match(ln)
        if m:
            elem, tag = int(m.group(1)), int(m.group(2))
            I = float(m.group(7)) + 1j * float(m.group(8))
            out.setdefault(tag, []).append((elem, I))
    return out


def parse_deck(path):
    segs = {}
    for ln in path.read_text().splitlines():
        if ln.startswith("GW"):
            p = ln[2:].replace(",", " ").split()
            segs[int(p[0])] = int(p[1])
    return segs  # tag -> nseg


def fit_end(zs, Is, order):
    """Polynomial fit I(z); return I(0), I'(0)."""
    import numpy as np

    c = np.polyfit(zs, Is, order)
    p = np.poly1d(c)
    return complex(p(0.0)), complex(p.deriv()(0.0))


def analyse(cap, out_name="out_stock.txt", npts=4, order=2):
    import numpy as np

    d = ORACLE / cap
    segs = parse_deck(d / "deck.nec")
    nb, na = segs[1], segs[2]
    cur = parse_currents(d / out_name)
    hb, ha = 2.0 / nb, 10.0 / na
    below = [(-2.0 + (i - 0.5) * hb, I) for i, I in cur[1]]
    above = [((j - 0.5) * ha, I) for j, I in cur[2]]
    nb_use = min(npts, len(below))
    zb = np.array([z for z, _ in below[-nb_use:]])
    Ib = np.array([I for _, I in below[-nb_use:]])
    za = np.array([z for z, _ in above[:npts]])
    Ia = np.array([I for _, I in above[:npts]])
    ob = min(order, len(zb) - 1)
    I0m, Ipm = fit_end(zb, Ib, ob)
    I0p, Ipp = fit_end(za, Ia, order)
    return dict(
        nb=nb,
        na=na,
        I_last_below=complex(Ib[-1]),
        I_first_above=complex(Ia[0]),
        I0_minus=I0m,
        I0_plus=I0p,
        dI_minus=Ipm,
        dI_plus=Ipp,
        cont_ratio=I0p / I0m,
        kcl_deficit=I0p - I0m,
        slope_ratio=Ipp / Ipm,
    )


def cfmt(z):
    return f"{z.real:+.4f}{z.imag:+.4f}j"


def main():
    print(
        f"eps_t = {EPS_T:.4f};  AGARD I'+/I'- = eps+/eps- = "
        f"{AGARD_RATIO:.6f} (|.|={abs(AGARD_RATIO):.5f})"
    )
    results = {}
    for cap in [
        "anchor-crossing-x1",
        "anchor-crossing-x2",
        "anchor-crossing-x3",
        "anchor-crossing-x4",
        "anchor-crossing-x5",
        "anchor-crossing-x8",
    ]:
        for out in ["out_stock.txt", "out_ezoff.txt"]:
            r = analyse(cap, out)
            key = f"{cap.split('-x')[1]}:{out.split('_')[1].split('.')[0]}"
            results[key] = r
            if out == "out_stock.txt":
                print(f"\n== x{cap.split('-x')[1]}  (nb={r['nb']}, na={r['na']}) ==")
                print(
                    f"  I(last below seg) = {cfmt(r['I_last_below'])}"
                    f"   I(first above seg) = {cfmt(r['I_first_above'])}"
                )
                print(
                    f"  I(0-) extrap = {cfmt(r['I0_minus'])}"
                    f"   I(0+) extrap = {cfmt(r['I0_plus'])}"
                )
                print(
                    f"  continuity I(0+)/I(0-) = {cfmt(r['cont_ratio'])}"
                    f"  |.| = {abs(r['cont_ratio']):.3f}"
                )
                print(
                    f"  KCL deficit I(0+)-I(0-) = {cfmt(r['kcl_deficit'])}"
                    f"  |.| = {abs(r['kcl_deficit']):.4f} A"
                )
                print(
                    f"  I'(0-) = {cfmt(r['dI_minus'])}  I'(0+) = {cfmt(r['dI_plus'])}"
                )
                sr = r["slope_ratio"]
                print(
                    f"  slope ratio I'+/I'- = {cfmt(sr)}  |.| = {abs(sr):.4f}"
                    f"   vs AGARD {abs(AGARD_RATIO):.4f}"
                )
    # stock vs ezoff spread check
    print("\nstock-vs-ezoff junction spread (|dI0+|):")
    for m in ["1", "2", "3", "4", "5", "8"]:
        a, b = results[f"{m}:stock"], results[f"{m}:ezoff"]
        print(f"  x{m}: {abs(a['I0_plus'] - b['I0_plus']):.2e} A")
    out = {
        k: {kk: (str(vv) if isinstance(vv, complex) else vv) for kk, vv in v.items()}
        for k, v in results.items()
    }
    res = (
        Path.home()
        / "antennas/antennaknobs/scratch/524-phase2/results/probe30-engine-currents.json"
    )
    res.write_text(json.dumps(out, indent=1))
    print(f"\nsaved -> {res}")


if __name__ == "__main__":
    main()
