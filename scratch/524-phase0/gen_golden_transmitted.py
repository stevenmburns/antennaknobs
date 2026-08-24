"""Generate momwire's `tests/golden_transmitted_524.py` (momwire#553 U3).

Three oracles, all consumed here and COMMITTED as numbers so the momwire
suite stays self-contained and never re-runs a library at test time:

1. the #524 phase-0 prototype's direct evaluation (`proto/buried_proto.py`,
   whose +-=+ anchor reproduces momwire's own four surfaces to 1.4e-10), for
   the five transmitted surfaces on an (R, theta, z') lattice;
2. the banked empymod run (`empymod/results.json`, empymod 2.6.0,
   ht='quad', pts_per_dec=600, limit=4000, xdirect=True) for the composed
   transmitted field on the SPEC T-line and T-vert grids, each grid carrying
   its own recorded quad(300)-vs-quad(600) spread as its uncertainty;
3. a FRESH empymod run in the CROSSED configuration — source in the air
   layer, receiver in the soil — which the phase-0 matrix never captured
   because phase 0 only ever buried the source. That is the only genuinely
   independent oracle for the above->below transpose: everything else about
   the transpose is true by construction, and an identity that is true by
   construction is not a test.

empymod at its LIBRARY DEFAULTS is not an oracle in this wave-regime
problem (phase 0 measured the default DLF filters at 0.13 median / 0.65 max
error on exactly these grids), so the crossed run pins the same quad
settings as the banked one and records its own quad(300)-vs-quad(600)
spread.

Usage:  python gen_golden_transmitted.py <path-to-momwire-checkout>
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
KEYS = ("TrhoV", "TzV", "TrhoH", "TphiH", "TzH")
EPS0 = 8.8541878128e-12

# The surface lattice, in the shipped grid's own coordinates: R is the
# OBSERVER's distance from the source's ground projection (R = sqrt(rho^2 +
# z^2)) in FREE-SPACE wavelengths, theta its elevation in degrees, and |z'|
# the source depth in metres. Both ends of every axis are represented, and
# theta = 0 (the observer ON the interface) is in the table because this
# family tabulates it — the source leg keeps the tail decaying there.
R_WL = (0.001, 0.01, 0.1, 0.5, 2.0)
THETA_DEG = (0.0, 0.2, 3.0, 30.0, 90.0)
ZP_M = (0.02, 0.15, 1.0)

# The prototype's own tail budget is 12,000 panels and the transmitted tail
# costs ~12*cot(theta_true) of them, so a lattice point at grazing and long
# range would come back TRUNCATED — and a truncated tail here does not
# degrade, it comes back wrong by decades (momwire#553 U3 measured 4.5e+3 at
# rho = 85.65 m, z = 0, z' = -0.02 m). Golden points are therefore taken only
# where the oracle can actually answer; the shipped grid's own grazing floor
# is a separate, tighter number derived from the same law.
MAX_COT_TRUE = 300.0


def proto_surfaces(hs, rho, z, zp):
    """The prototype's regime-1 integrals mapped into momwire's five
    T-surfaces with the two-leg divide-out.

    `buried_proto.stack_T` indices: 2 = d2V/drho2, 3 = d2V/drho dz,
    4 = (d2/dz2 + kp^2)V, 5 = (1/rho)dV/drho, 6 = d2V/drho dz', 7 = U_T.
    """
    J, _, _ = bp.integrals_T(hs, rho, z, zp, err=False)
    c1, kp, km = hs.C1, hs.kp, hs.km
    r = math.sqrt(rho * rho + (z + abs(zp)) ** 2)
    phase = r * np.exp(1j * (km * abs(zp) + kp * r))  # = 1/g
    return {
        "TrhoV": complex(c1 * phase * J[3]),
        "TzV": complex(c1 * phase * J[4]),
        "TrhoH": complex(c1 * phase * (J[2] + J[7])),
        "TphiH": complex(-c1 * phase * (J[5] + J[7])),
        "TzH": complex(-c1 * phase * J[6]),
    }


def _c(z):
    """A complex literal that round-trips exactly."""
    return f"complex({z.real!r}, {z.imag!r})"


def emit_surfaces(out):
    out.append("# (R/lambda_p, theta_deg, |z'| m, TrhoV, TzV, TrhoH, TphiH, TzH)")
    out.append("SURFACES: dict[str, tuple] = {")
    for s in SOILS:
        for f in FREQS:
            hs = bp.HalfSpace(f, *SOILS[s])
            hs.assert_decay()
            lam_p = 2.0 * math.pi / hs.kp
            lam_m = 2.0 * math.pi / abs(hs.km)
            cell = f"{s}/{f / 1e6:.0f}MHz"
            print(f"  surfaces {cell} (lambda_p = {lam_p:.3f} m)", flush=True)
            out.append(f'    "{cell}": (')
            for rw in R_WL:
                for td in THETA_DEG:
                    for zp in ZP_M:
                        if zp > 0.25 * lam_m:
                            continue  # past the ladder; the grid refuses it
                        th = math.radians(td)
                        rho = max(rw * lam_p * math.cos(th), 0.0)
                        z = max(rw * lam_p * math.sin(th), 0.0)
                        if rho > MAX_COT_TRUE * (z + zp):
                            continue  # past the oracle's own tail budget
                        v = proto_surfaces(hs, rho, z, -zp)
                        body = ", ".join(_c(v[k]) for k in KEYS)
                        out.append(f"        ({rw!r}, {td!r}, {zp!r}, {body}),")
            out.append("    ),")
    out.append("}")
    out.append("")


def emit_banked(out):
    """The SPEC T-line / T-vert grids from the banked phase-0 empymod run."""
    ora = json.load(open(os.path.join(_HERE, "empymod", "results.json")))
    out.append(
        "# The transmitted (below -> above) grids of the SPEC matrix: the\n"
        "# banked empymod quad field at each point plus that grid's own\n"
        "# recorded quad(300)-vs-quad(600) spread, which is the number a\n"
        "# tolerance here is named against."
    )
    out.append("TRANSMITTED: tuple = (")
    n = 0
    for cell in ora["cells"]:
        for gname in ("T-line", "T-vert"):
            g = cell["grids"].get(gname)
            if g is None:
                continue
            spread = g["xcheck"]["quad_ppd300_vs_primary"]["max_rel"]
            out.append("    {")
            out.append(f'        "id": {cell["id"] + "_" + gname!r},')
            out.append(f'        "grid": {gname!r},')
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
    print(f"  banked transmitted: {n} points", flush=True)


# --------------------------------------------------------------------------
# The crossed run: source ABOVE, receiver BELOW
# --------------------------------------------------------------------------

CROSSED_CELLS = (
    ("A", 7e6, "HED"),
    ("A", 7e6, "VED"),
    ("B", 7e6, "HED"),
    ("A", 21e6, "HED"),
)
# Source in the air at z = +1 m; receivers buried on a line and a ladder.
CROSSED_SRC_Z = 1.0
CROSSED_POINTS = tuple(
    [(x, 0.0, -0.15) for x in (2.0, 6.0, 10.0, 20.0, 30.0)]
    + [(10.0, 0.0, -d) for d in (0.05, 0.5, 1.0)]
)

_HTARG = {"a": 1e-8, "b": 300, "limit": 4000, "pts_per_dec": 600}
_HTARG_X = {"a": 1e-8, "b": 300, "limit": 2000, "pts_per_dec": 300}
# A THIRD setting, finer than the primary. quad(300)-vs-quad(600) is the
# banked run's uncertainty measure, and on the crossed geometry the two
# agree to 2e-5 while both still move by 1e-3 against quad(1200) — the two
# coarse settings share a common error there, so the recorded spread is the
# WORST of the two comparisons and not the convenient one.
_HTARG_F = {"a": 1e-8, "b": 300, "limit": 8000, "pts_per_dec": 1400}


# ab codes (empymod frame) and SPEC-frame sign per component, per source
# type — `empymod/SUMMARY.md`'s table verbatim. The z -> -z reflection is
# exact for E-from-J, so the map depends on the DIRECTIONS only and holds for
# a source above the interface exactly as it does for one below.
COMPONENT_MAP = {
    "HED": {"Ex": (11, +1.0), "Ey": (21, +1.0), "Ez": (31, -1.0)},
    "VED": {"Ex": (13, -1.0), "Ey": (23, -1.0), "Ez": (33, +1.0)},
}


def _empymod_crossed(eps_r, sigma, freq, kind, htarg):
    """empymod E at the buried receivers from a unit dipole in the AIR.

    empymod's z points DOWN, so z_emp = -z_spec: the source at SPEC
    z = +CROSSED_SRC_Z sits at empymod z = -CROSSED_SRC_Z, in layer 0 (air),
    and the receivers at SPEC z = -d sit at empymod z = +d, in layer 1.
    """
    import empymod

    pts = np.asarray(CROSSED_POINTS, dtype=float)
    out = np.zeros((len(pts), 3), dtype=complex)
    src_emp = [0.0, 0.0, -CROSSED_SRC_Z]
    for z_spec in sorted(set(pts[:, 2])):
        idx = np.where(pts[:, 2] == z_spec)[0]
        for ci, comp in enumerate(("Ex", "Ey", "Ez")):
            ab, sign = COMPONENT_MAP[kind][comp]
            val = empymod.dipole(
                src=src_emp,
                rec=[pts[idx, 0], pts[idx, 1], -z_spec],
                depth=[0.0],
                res=[2e14, 1.0 / sigma],
                freqtime=freq,
                ab=ab,
                epermH=[1.0, eps_r],
                xdirect=True,
                verb=0,
                ht="quad",
                htarg=htarg,
            )
            out[idx, ci] = sign * np.atleast_1d(np.asarray(val, dtype=complex))
    return {"Ex": out[:, 0], "Ey": out[:, 1], "Ez": out[:, 2]}


def emit_crossed(out):
    out.append(
        "# The CROSSED configuration the phase-0 matrix never captured:\n"
        "# source in the AIR, receivers in the soil. Run fresh by\n"
        "# `gen_golden_transmitted.py` with the banked run's quad settings\n"
        "# pinned, and carrying its own quad(300)-vs-quad(600) spread. This\n"
        "# is the only oracle for the above->below transpose that is not\n"
        "# true by construction."
    )
    out.append(f"CROSSED_SRC_Z = {CROSSED_SRC_Z!r}")
    out.append("CROSSED: tuple = (")
    for sname, freq, kind in CROSSED_CELLS:
        er, sg = SOILS[sname]
        print(f"  crossed {sname}/{freq / 1e6:.0f}MHz {kind}", flush=True)
        prim = _empymod_crossed(er, sg, freq, kind, _HTARG)
        # PER POINT, against that point's own scale -- the banked harness's
        # own `rel_spread` convention, and not a pooled of-scale norm. A
        # pooled one is wrong by 60x here: this grid's near point carries
        # |E| ~ 2.6 and its far point ~1e-2, so dividing the far point's
        # disagreement by the grid maximum reported 2.3e-5 for an oracle
        # whose quad is only converged to 4.2e-3 out there. That is U2's
        # second inversion, walked into inside the generator that is supposed
        # to measure the oracle's honesty.
        scale = np.maximum.reduce([np.abs(prim[k]) for k in ("Ex", "Ey", "Ez")])
        spread = 0.0
        for other in (_HTARG_X, _HTARG_F):
            xchk = _empymod_crossed(er, sg, freq, kind, other)
            for k in ("Ex", "Ey", "Ez"):
                spread = max(
                    spread,
                    float(
                        np.max(np.abs(prim[k] - xchk[k]) / np.maximum(scale, 1e-300))
                    ),
                )
        out.append("    {")
        out.append(f'        "id": {f"{sname}_{freq / 1e6:.0f}MHz_{kind}_air"!r},')
        out.append(f'        "eps_r": {er!r},')
        out.append(f'        "sigma": {sg!r},')
        out.append(f'        "freq_hz": {freq!r},')
        out.append(f'        "kind": {kind!r},')
        out.append(f'        "oracle_spread": {spread!r},')
        out.append('        "points": (')
        for p in CROSSED_POINTS:
            out.append(f"            {p!r},")
        out.append("        ),")
        out.append('        "E": (')
        for i in range(len(CROSSED_POINTS)):
            out.append(
                "            ("
                + ", ".join(_c(complex(prim[k][i])) for k in ("Ex", "Ey", "Ez"))
                + "),"
            )
        out.append("        ),")
        out.append("    },")
    out.append(")")
    out.append("")


HEADER = '''"""Committed goldens for the transmitted Sommerfeld family (momwire#553
unit 3, the momwire#524 phase-1 regime-1 arc). GENERATED — do not hand-edit.

Provenance
----------
#524 phase-0 prototype direct evaluation (`scratch/524-phase0/proto/
buried_proto.py` in the antennaknobs tree, whose +-=+ anchor reproduces
momwire's own four interpolation surfaces to 1.4e-10) for `SURFACES`;
empymod 2.6.0 at ht='quad' (pts_per_dec 600, limit 4000, xdirect=True) for
`TRANSMITTED` (the banked phase-0 run, `scratch/524-phase0/empymod/
results.json`) and for `CROSSED` (a fresh run in the source-above
configuration the phase-0 matrix never captured). Regenerated by
`scratch/524-phase0/gen_golden_transmitted.py` in the antennaknobs tree.

empymod at its LIBRARY DEFAULTS is not an oracle in this wave-regime
problem — phase 0 measured the default DLF filters at 0.13 median / 0.65 max
error on exactly these grids. Every field value here is a quad primary and
`oracle_spread` is that grid's own quad(300)-vs-quad(600) disagreement: the
number a tolerance is named against, never a number chosen to make a test
pass.

Conventions: SI, e^{+j omega t}, interface at z = 0, ground below, unit
current moment I*l = 1. eps_tilde = eps_r - j sigma/(omega eps0),
k_m = k_p sqrt(eps_tilde) on the Im <= 0 branch.

`SURFACES` is tabulated in the shipped grid's own coordinates: R/lambda_p
where R = sqrt(rho^2 + z^2) is the OBSERVER's distance from the source's
ground projection and lambda_p = 2 pi / k_p, theta = atan2(z, rho) in
DEGREES, and |z'| the source depth in METRES. The surfaces carry the
transmitted divide-out g = e^{-j(k_m |z'| + k_p R_true)} / R_true with
R_true = sqrt(rho^2 + (z + |z'|)^2), so surface * g is the field
combination.

Soils and frequencies are `scratch/524-phase0/SPEC.md`:
A = (13, 0.005), B = (20, 0.03), C = (5, 0.001) S/m, at 7 and 21 MHz.
"""
'''


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: gen_golden_transmitted.py <momwire-checkout>")
    dest = os.path.join(sys.argv[1], "tests", "golden_transmitted_524.py")
    out: list[str] = [HEADER]
    out.append("SOILS = {" + ", ".join(f'"{k}": {v!r}' for k, v in SOILS.items()) + "}")
    out.append(f"FREQS = {FREQS!r}")
    out.append('KEYS = ("TrhoV", "TzV", "TrhoH", "TphiH", "TzH")')
    out.append("")
    emit_surfaces(out)
    emit_banked(out)
    emit_crossed(out)
    with open(dest, "w") as fh:
        fh.write("\n".join(out))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
