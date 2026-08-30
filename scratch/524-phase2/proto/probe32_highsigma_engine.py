"""A-2 session 6, probe 32 — adjudicator 2 (engine side): the high-sigma
limit. As sigma rises the buried stub becomes a perfect ground stake and
the contact fiction becomes exact, so engine crossing must approach
engine mono (Delta -> 0). Measures the engine's Delta and junction
currents along a sigma ladder.

Below-arm mesh per medium resolves the soil wavelength/decay length
(sigma=5: k- ~ 11.8-11.8j /m, decay ~8.5 cm -> 2 cm segments).

Run: NEC5_EXE=~/antennas/NEC5-downloads/nec5-linux/nec5cl \
       .venv/bin/python scratch/524-phase2/proto/probe32_highsigma_engine.py
"""

from __future__ import annotations

import cmath
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path.home() / "antennas/antennaknobs/scripts"))

EPS0 = 8.8541878128e-12
F = 7.0e6
W = 2 * math.pi * F
K0 = W / 299792458.0

# (eps_r, sigma, below_nseg). Soil A (13, 0.005) engine numbers already
# banked at x5: mono 72.8580-49.0230j, crossing 70.0380-50.7170j.
MEDIA = [
    (13.0, 0.05, 32),
    (13.0, 0.5, 50),
    (13.0, 5.0, 100),
    (81.0, 5.0, 100),
    (13.0, 5.0, 150),  # below-refinement control at the top rung
]

NA = 75  # above segments (x5 rung); feed = seg 33 (center 4.333 m)


def eps_t(eps_r, sigma):
    return eps_r - 1j * sigma / (W * EPS0)


def mono_deck(eps_r, sigma):
    return (
        "CM probe32 mono\nCE\n"
        f"GW 1,{NA},0.,0.,0.,0.,0.,10.,.001\n"
        "GE 1,-1\nFR 0,1,0,0,7.\n"
        f"GN 0,0,0,0,{eps_r},{sigma}\n"
        "EX 4,1,33,0,1.,0.\nPQ 0\nXQ 0\nEN\n"
    )


def crossing_deck(eps_r, sigma, nb):
    return (
        "CM probe32 crossing\nCE\n"
        f"GW 1,{nb},0.,0.,-2.,0.,0.,0.,.001\n"
        f"GW 2,{NA},0.,0.,0.,0.,0.,10.,.001\n"
        "GE 1,-1\nFR 0,1,0,0,7.\n"
        f"GN 0,0,0,0,{eps_r},{sigma}\n"
        "EX 4,2,33,0,1.,0.\nPQ 0\nXQ 0\nEN\n"
    )


def parse_currents_text(text):
    from probe30_engine_currents import CUR_RE

    out = {}
    in_cur = False
    for ln in text.splitlines():
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


def junction(text, nb, npts=4, order=2):
    from probe30_engine_currents import fit_end

    cur = parse_currents_text(text)
    hb, ha = 2.0 / nb, 10.0 / NA
    below = [(-2.0 + (i - 0.5) * hb, I) for i, I in cur[1]]
    above = [((j - 0.5) * ha, I) for j, I in cur[2]]
    zb = np.array([z for z, _ in below[-npts:]])
    Ib = np.array([I for _, I in below[-npts:]])
    za = np.array([z for z, _ in above[:npts]])
    Ia = np.array([I for _, I in above[:npts]])
    I0m, _ = fit_end(zb, Ib, order)
    I0p, _ = fit_end(za, Ia, order)
    return I0m, I0p


def cfmt(z):
    return f"{z.real:+.4f}{z.imag:+.4f}j"


def main():
    from antennaknobs.engines.nec5 import NEC5Engine
    from bench_nec5_walk_why import make_dipole

    cap = HERE.parent / "results" / "probe32-nec5-cap"
    eng = NEC5Engine(make_dipole(20), ground=None, capture_dir=cap)

    out = {}
    print(
        "sigma ladder (x5 above mesh; soil A reference: engine Delta "
        "x5 = -2.8200-1.6940j)\n"
    )
    for eps_r, sigma, nb in MEDIA:
        et = eps_t(eps_r, sigma)
        km = K0 * cmath.sqrt(et)
        tag = f"eps{eps_r:g}-sig{sigma:g}-nb{nb}"
        tm = eng._run(mono_deck(eps_r, sigma))
        zm = complex(NEC5Engine._parse_input_parameters(tm)[0][0][2])
        tc = eng._run(crossing_deck(eps_r, sigma, nb))
        zc = complex(NEC5Engine._parse_input_parameters(tc)[0][0][2])
        I0m, I0p = junction(tc, nb)
        d = zc - zm
        print(f"== {tag}: k- = {km:.3f}/m  decay {1 / abs(km.imag):.3f} m")
        print(f"   mono = {cfmt(zm)}   crossing = {cfmt(zc)}")
        print(f"   Delta = {cfmt(d)}   |Delta| = {abs(d):.4f}")
        print(
            f"   junction I(0-) = {cfmt(I0m)}  I(0+) = {cfmt(I0p)}  "
            f"KCL deficit |.| = {abs(I0p - I0m):.4f} A\n"
        )
        out[tag] = dict(
            mono=str(zm),
            crossing=str(zc),
            delta=str(d),
            I0_minus=str(I0m),
            I0_plus=str(I0p),
        )

    fp = HERE.parent / "results" / "probe32-highsigma-engine.json"
    fp.write_text(json.dumps(out, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
