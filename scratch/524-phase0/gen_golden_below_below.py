"""Generate momwire's `tests/golden_below_below_524.py` (momwire#553 U2).

Two oracles, both consumed here and COMMITTED as numbers so the momwire
suite stays self-contained:

1. the #524 phase-0 prototype's direct evaluation (`proto/buried_proto.py`,
   the generalized shared-medium form; its +-=+ anchor reproduces momwire's
   own four surfaces to 1.4e-10), for the surface lattice and the R1 -> 0
   probes;
2. the banked empymod run (`empymod/results.json`, empymod 2.6.0 with
   ht='quad', htarg pts_per_dec=600 / limit=4000, xdirect=True), for the
   composed in-medium field on the SPEC M-line, carried with each grid's
   own recorded quad(300)-vs-quad(600) spread as its uncertainty.

Usage:  python gen_golden_below_below.py <path-to-momwire-checkout>
"""

from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "proto"))

import buried_proto as bp  # noqa: E402

SOILS = {"A": (13.0, 0.005), "B": (20.0, 0.03), "C": (5.0, 0.001)}
FREQS = (7e6, 21e6)
KEYS = ("IrhoV", "IzV", "IrhoH", "IphiH")

# The surface lattice. Grazing is deliberately represented (theta = 2 deg)
# but not chased below it: the prototype's real-axis tail costs ~1/tan(theta)
# panels, and the momwire grid's own grazing story is measured separately.
R1_WL = (0.01, 0.05, 0.2, 0.8, 2.0, 3.5)
THETA_DEG = (2.0, 15.0, 45.0, 80.0)

# R1 -> 0 probes: the prototype's DIRECT evaluation at a radius small enough
# that the static limit is the answer.
LIMIT_R1_WL = 1.0e-4
LIMIT_THETA_DEG = (5.0, 20.0, 45.0, 70.0, 89.0)


def proto_surfaces(hs, r1, th):
    """The prototype's shared='m' remainder, mapped into momwire's
    I-surface convention with the below divide-out (the two-leg blend).

    The mapping is the one gate G6 measured at +-=+ (buried_proto.gate_G6),
    read at the other sign: prefactor k_o^2/k_s^2 on the V-source rows, none
    on the H rows, and the whole thing divided by the two-leg blend g.
    """
    rho = r1 * math.cos(th)
    zsum = -r1 * math.sin(th)  # both below => z + z' < 0
    z = zp = 0.5 * zsum
    J, _, _ = bp.integrals_R(hs, rho, z, zp, shared="m", err=False)
    C1, kp, km = hs.C1, hs.kp, hs.km
    ratio = (kp * kp) / (km * km)
    # The MEASURED below divide-out (momwire#553 U2): the two-leg blend
    # g = e^{-j(k_p rho + k_m h)} / R1, whose reciprocal is this phase.
    phase = r1 * np.exp(1j * (kp * rho + km * abs(zsum)))
    return {
        "IrhoV": complex(C1 * ratio * J[3] * phase),
        "IzV": complex(C1 * ratio * (J[4] + km * km * J[0]) * phase),
        "IrhoH": complex(C1 * (J[2] + J[6]) * phase),
        "IphiH": complex(-C1 * (J[5] + J[6]) * phase),
    }


def _c(z):
    """A complex literal that round-trips exactly."""
    return f"complex({z.real!r}, {z.imag!r})"


def emit_surfaces(out):
    out.append("# (R1/lambda_m, theta_deg, IrhoV, IzV, IrhoH, IphiH)")
    out.append("SURFACES: dict[str, tuple] = {")
    for s in SOILS:
        for f in FREQS:
            hs = bp.HalfSpace(f, *SOILS[s])
            hs.assert_decay()
            lam_m = 2.0 * math.pi / abs(hs.km)
            cell = f"{s}/{f / 1e6:.0f}MHz"
            print(f"  surfaces {cell} (lambda_m = {lam_m:.4f} m)", flush=True)
            out.append(f'    "{cell}": (')
            for rw in R1_WL:
                for td in THETA_DEG:
                    v = proto_surfaces(hs, rw * lam_m, math.radians(td))
                    body = ", ".join(_c(v[k]) for k in KEYS)
                    out.append(f"        ({rw!r}, {td!r}, {body}),")
            out.append("    ),")
    out.append("}")
    out.append("")


def emit_limits(out):
    out.append(
        "# (theta_deg, IrhoV, IzV, IrhoH, IphiH) — the prototype's DIRECT\n"
        f"# evaluation at R1 = {LIMIT_R1_WL!r} * lambda_m, which is what the\n"
        "# analytic R1 -> 0 limits must land on."
    )
    out.append(f"LIMIT_PROBE_R1_WL = {LIMIT_R1_WL!r}")
    out.append("LIMITS: dict[str, tuple] = {")
    for s in SOILS:
        for f in FREQS:
            hs = bp.HalfSpace(f, *SOILS[s])
            lam_m = 2.0 * math.pi / abs(hs.km)
            cell = f"{s}/{f / 1e6:.0f}MHz"
            print(f"  limits {cell}", flush=True)
            out.append(f'    "{cell}": (')
            for td in LIMIT_THETA_DEG:
                v = proto_surfaces(hs, LIMIT_R1_WL * lam_m, math.radians(td))
                body = ", ".join(_c(v[k]) for k in KEYS)
                out.append(f"        ({td!r}, {body}),")
            out.append("    ),")
    out.append("}")
    out.append("")


def emit_mline(out):
    path = os.path.join(_HERE, "empymod", "results.json")
    ora = json.load(open(path))
    out.append(
        "# One entry per SPEC matrix cell that has an M-line grid: the\n"
        "# empymod in-medium field at each point, plus that grid's own\n"
        "# recorded quad(300)-vs-quad(600) spread — the oracle's numerical\n"
        "# uncertainty, which is what a tolerance here must be named against."
    )
    out.append("MLINE: tuple = (")
    n = 0
    for cell in ora["cells"]:
        g = cell["grids"].get("M-line")
        if g is None:
            continue
        spread = g["xcheck"]["quad_ppd300_vs_primary"]["max_rel"]
        out.append("    {")
        out.append(f'        "id": {cell["id"]!r},')
        out.append(f'        "eps_r": {cell["soil"]["eps_r"]!r},')
        out.append(f'        "sigma": {cell["soil"]["sigma"]!r},')
        out.append(f'        "freq_hz": {cell["freq_hz"]!r},')
        out.append(f'        "kind": {cell["source"]["type"]!r},')
        out.append(f'        "src_xyz": {tuple(cell["source"]["src_spec_xyz"])!r},')
        out.append(f'        "oracle_spread": {spread!r},')
        out.append('        "points": (')
        for p in g["points_spec_xyz"]:
            out.append(f"            {tuple(p)!r},")
        out.append("        ),")
        out.append('        "E": (')
        for i in range(len(g["points_spec_xyz"])):
            ex = complex(*g["Ex"][i])
            ey = complex(*g["Ey"][i])
            ez = complex(*g["Ez"][i])
            out.append(f"            ({_c(ex)}, {_c(ey)}, {_c(ez)}),")
            n += 1
        out.append("        ),")
        out.append("    },")
    out.append(")")
    out.append("")
    print(f"  M-line: {n} points", flush=True)


HEADER = '''"""Committed goldens for the below/below Sommerfeld remainder (momwire#553
unit 2, the momwire#524 phase-1 regime-2 arc). GENERATED — do not hand-edit.

Provenance
----------
#524 phase-0 prototype direct evaluation (`scratch/524-phase0/proto/
buried_proto.py` in the antennaknobs tree, the generalized shared-medium
evaluator whose +-=+ anchor reproduces momwire's own four interpolation
surfaces to 1.4e-10) + empymod ht='quad' (pts_per_dec 600, limit 4000,
xdirect=True; empymod 2.6.0, `scratch/524-phase0/empymod/results.json`).
Regenerated by `scratch/524-phase0/gen_golden_below_below.py` in the
antennaknobs tree.

empymod at its LIBRARY DEFAULTS is not an oracle in this wave-regime
problem — phase 0 measured the default DLF filters at 0.13 median / 0.65 max
error on exactly these grids. Every `MLINE` value is the quad primary, and
`oracle_spread` is that grid's own quad(300)-vs-quad(600) disagreement: the
number a tolerance here has to be named against, never a number chosen to
make a test pass.

Conventions: SI, e^{+j omega t}, interface at z = 0, ground below, unit
current moment I*l = 1. eps_tilde = eps_r - j sigma/(omega eps0),
k_m = k_p sqrt(eps_tilde) on the Im <= 0 branch. Surfaces are tabulated
against R1/lambda_m with lambda_m = 2 pi / |k_m| and theta in DEGREES, and
carry the below divide-out g = e^{-j(k_p rho + k_m h)}/R1, the two-leg
blend momwire#553 U2 measured (so surface * g is the field combination).

Soils and frequencies are `scratch/524-phase0/SPEC.md`:
A = (13, 0.005), B = (20, 0.03), C = (5, 0.001) S/m, at 7 and 21 MHz.
"""
'''


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: gen_golden_below_below.py <momwire-checkout>")
    dest = os.path.join(sys.argv[1], "tests", "golden_below_below_524.py")
    out: list[str] = [HEADER]
    out.append("SOILS = {" + ", ".join(f'"{k}": {v!r}' for k, v in SOILS.items()) + "}")
    out.append(f"FREQS = {FREQS!r}")
    out.append('KEYS = ("IrhoV", "IzV", "IrhoH", "IphiH")')
    out.append("")
    emit_surfaces(out)
    emit_limits(out)
    emit_mline(out)
    with open(dest, "w") as fh:
        fh.write("\n".join(out))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
