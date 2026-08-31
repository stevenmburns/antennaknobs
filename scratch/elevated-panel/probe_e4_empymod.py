"""Elevated-panel probe E4 — the empymod adjudication of the buried
coupling (three instruments, one geometry).

Question: whose below-ground illumination is right on THIS deck? The E1
depth ladder measured the engines' radial-coupling deltas diverging
(|nec5/momwire| 2.9 -> 4.7 over depth 0.15 -> 2.0 m). Here the
illumination itself is measured at the radial's location:

  (a) momwire: <f, E> Galerkin functionals harvested through the
      PRODUCTION cross fill (tiny detached probe wires at the
      observation points; entries contracted with the vertical's solved
      current) — zero convention risk, it IS the machinery the solves
      use.
  (b) empymod: the same <f, E> functionals from the independent
      layered-earth code, house conventions copied verbatim from
      scratch/524-phase0/empymod/harness.py (z_emp = -z_spec, VED
      Ex_spec = -E(ab=13), ht='quad' ppd 600, no conjugation), driven
      by the SAME solved current (per-segment sub-dipoles).
  (c) the engine: printed NE table values at the same points (its own
      current — a few-% normalization difference, irrelevant to decay
      shapes).

Adjudication is on DECAY SHAPES over the depth ladder (kills every
constant convention) plus residuals after one fitted global complex
constant per instrument pair.

Observation points: probe tents centered at x in {1.0, 2.5} m,
depth in {0.15, 0.5, 1.0, 2.0} m, on the y = 0 line (the radial's
locus). Source: the E1 ref vertical (h = 0.5, 10 m, 30 segs).

Run stages:
  .venv/bin/python scratch/elevated-panel/probe_e4_empymod.py momwire
  .venv/bin/python scratch/elevated-panel/probe_e4_empymod.py empymod
  NEC5_EXE=... .venv/bin/python scratch/elevated-panel/probe_e4_empymod.py engine
  .venv/bin/python scratch/elevated-panel/probe_e4_empymod.py verdict
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
from numpy.polynomial.legendre import leggauss

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = HERE / "results" / "probe-e4.json"
sys.path.insert(0, str(ROOT / "scratch" / "524-phase2" / "proto"))
sys.path.insert(0, str(ROOT / "momwire" / "tests"))

WL7 = 42.827494
H = 0.5
XS = (1.0, 2.5)
DEPTHS = (0.15, 0.5, 1.0, 2.0)
PROBE_LEN = 0.3
PROBE_SEGS = 3

EPS0 = 8.8541878128e-12
RES_AIR = 2e14
PRIMARY = dict(
    ht="quad", htarg={"a": 1e-8, "b": 300.0, "limit": 4000, "pts_per_dec": 600}
)


def vertical_build(dens=2):
    return dict(
        wires=[np.array([(0.0, 0.0, 10.0 + H), (0.0, 0.0, H)])],
        n_per_edge_per_wire=[[15 * dens]],
        feeds=[(0, 4.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=(13.0, 0.005),
        ground_model="sommerfeld",
    )


def probe_points():
    return [(x, d) for x in XS for d in DEPTHS]


def probe_build(dens=2):
    b = vertical_build(dens)
    wires = list(b["wires"])
    npe = list(b["n_per_edge_per_wire"])
    for x, d in probe_points():
        wires.append(
            np.array([(x - PROBE_LEN / 2, 0.0, -d), (x + PROBE_LEN / 2, 0.0, -d)])
        )
        npe.append([PROBE_SEGS])
    b.update(wires=wires, n_per_edge_per_wire=npe)
    return b


def wire_bases(s, geom, wire_idx):
    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    off = geom["seg_offsets"]
    segs = set(range(int(off[wire_idx]), int(off[wire_idx + 1])))
    out = []
    for m in range(polys.shape[0]):
        live = [
            int(supp_seg[m, a])
            for a in range(supp_seg.shape[1])
            if np.any(polys[m, a] != 0.0)
        ]
        if live and all(g in segs for g in live):
            out.append(m)
    return out


def tent_samples(s, geom, m, segs):
    """(points, weights, f-values) of basis m over its live support —
    the <f, E> quadrature both instruments share."""
    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    d = s.degree
    xg, wg = leggauss(6)
    tq = 0.5 * (xg + 1.0)
    pts, wts, fv = [], [], []
    for g in segs:
        a_slot = [
            a
            for a in range(supp_seg.shape[1])
            if supp_seg[m, a] == g and np.any(polys[m, a] != 0.0)
        ]
        if not a_slot:
            continue
        sl, sr = geom["seg_l"][g], geom["seg_r"][g]
        h = float(geom["h_per_seg"][g])
        u = h * tq
        f = np.zeros(len(u))
        for a in a_slot:
            for p in range(d + 1):
                c = polys[m, a, p]
                if c != 0.0:
                    f += c * u**p
        pts.append(sl[None, :] + (u / h)[:, None] * (sr - sl)[None, :])
        wts.append(0.5 * h * wg)
        fv.append(f)
    return np.vstack(pts), np.concatenate(wts), np.concatenate(fv)


def load():
    return json.loads(RESULTS.read_text()) if RESULTS.exists() else {}


def save(out):
    RESULTS.parent.mkdir(exist_ok=True)
    old = load()
    old.update(out)
    RESULTS.write_text(json.dumps(old, indent=1))
    print(f"saved {RESULTS}")


def solved_current():
    """Solve the vertical ALONE; return (solver, geom, coeffs, per-seg
    current, seg midpoints, seg h)."""
    from momwire.bspline import BSplineSolver
    from probe9_sense import capture
    from test_buried_serve_553 import element_currents

    s = BSplineSolver(**vertical_build())
    st = capture(s)
    kcl = st["kcl"]
    if kcl is None or kcl.shape[0] == 0:
        coeffs = np.linalg.solve(st["Z"], st["v"])
    else:
        coeffs = BSplineSolver._solve_with_kcl(s, st["Z"], st["v"], kcl)
    i_seg = element_currents(s, coeffs)
    geom = s._build_geometry()
    mid = 0.5 * (geom["seg_l"] + geom["seg_r"])
    h = geom["h_per_seg"]
    print(f"vertical solved: Z = {st['z_in']:.4f}, {len(i_seg)} segments")
    return s, geom, coeffs, i_seg, mid, h


def run_momwire():
    from momwire.bspline import BSplineSolver
    from probe9_sense import capture

    s_v, geom_v, coeffs_v, i_seg, mid, h = solved_current()

    s = BSplineSolver(**probe_build())
    geom = s._build_geometry()
    above = wire_bases(s, geom, 0)
    assert len(above) == len(coeffs_v), (len(above), len(coeffs_v))
    st = capture(s)
    Z = st["Z"]
    off = geom["seg_offsets"]

    out = {}
    for wi, (x, d) in enumerate(probe_points(), start=1):
        pb = wire_bases(s, geom, wi)
        m = pb[len(pb) // 2]  # the center tent
        emf = complex(Z[m, above] @ coeffs_v[above])
        pts, wts, fv = tent_samples(s, geom, m, range(int(off[wi]), int(off[wi + 1])))
        out[f"mw x={x} d={d}"] = dict(
            emf=f"{emf:.6e}",
            tent_center=[x, 0.0, -d],
            tent_pts=pts.tolist(),
            tent_wts=wts.tolist(),
            tent_f=fv.tolist(),
        )
        print(f"  mw x={x} d={d}: <f,E>-entry = {emf:.4e}")
    # Segment currents for the empymod stage (same solve).
    out["vertical current"] = dict(
        i_seg=[f"{c:.6e}" for c in i_seg],
        mid_z=[float(z) for z in mid[:, 2]],
        h=[float(v) for v in h],
    )
    save(out)


def run_empymod():
    import empymod

    r = load()
    cur = r["vertical current"]
    i_seg = np.array([complex(c) for c in cur["i_seg"]])
    mid_z = np.array(cur["mid_z"])
    h_seg = np.array(cur["h"])
    # Wire spelled top->bottom: tangents point -z; flip to +z (UP) moment.
    i_up = -i_seg

    res = [RES_AIR, 1.0 / 0.005]
    eperm = [1.0, 13.0]
    freq = 299792458.0 / WL7 / 1e6 * 1e6  # Hz — c/WL7
    nsub = 3

    out = {}
    t0 = time.time()
    for x, d in probe_points():
        key = f"mw x={x} d={d}"
        pts = np.asarray(r[key]["tent_pts"])
        wts = np.asarray(r[key]["tent_wts"])
        fv = np.asarray(r[key]["tent_f"])
        Ex = np.zeros(len(pts), dtype=complex)
        for zc, hh, ii in zip(mid_z, h_seg, i_up, strict=True):
            for k in range(nsub):
                zs = zc + hh * ((k + 0.5) / nsub - 0.5)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    e = empymod.dipole(
                        src=[0.0, 0.0, -zs],
                        rec=[pts[:, 0], pts[:, 1], float(-pts[0, 2])],
                        depth=[0.0],
                        res=res,
                        freqtime=freq,
                        ab=13,
                        epermH=eperm,
                        xdirect=True,
                        verb=0,
                        **PRIMARY,
                    )
                # VED along +z_spec: Ex_spec = -E(ab=13); moment I*dl.
                Ex += -np.atleast_1d(np.asarray(e, complex)) * ii * (hh / nsub)
        emf = complex(np.sum(wts * fv * Ex))
        ex_c = complex(Ex[len(Ex) // 2])
        out[f"emp x={x} d={d}"] = dict(emf=f"{emf:.6e}", ex_center=f"{ex_c:.6e}")
        print(
            f"  emp x={x} d={d}: <f,E> = {emf:.4e}  Ex(center) = {ex_c:.4e}"
            f"  ({time.time() - t0:.0f}s)",
            flush=True,
        )
    save(out)


def run_engine():
    from antennaknobs.engines.nec5 import NEC5Engine

    sys.path.insert(0, str(ROOT / "scripts"))
    from bench_nec5_walk_why import make_dipole

    captures = HERE / "results" / "nec5-cap-e4"
    captures.mkdir(parents=True, exist_ok=True)
    eng = NEC5Engine(make_dipole(20), ground=None, capture_dir=captures)

    ne_rows = "".join(f"NE 0,2,1,1,{1.0},0.,{-d},1.5,0.,0.\n" for d in DEPTHS)
    deck = (
        "CM e4 illumination probe\nCE\n"
        "GW 1,45,0.,0.,10.5,0.,0.,0.5,.001\n"
        "GE 1,-1\nFR 0,1,0,0,7.\nGN 0,0,0,0,13.,.005\n"
        "EX 4,1,20,0,1.,0.\n" + ne_rows + "PQ 0\nXQ 0\nEN\n"
    )
    eng.run_deck(deck)
    # Parse the newest captured printout for the near-field table.
    files = sorted(captures.rglob("*"), key=lambda p: p.stat().st_mtime)
    text = ""
    for f in reversed(files):
        if f.is_file():
            try:
                t = f.read_text(errors="ignore")
            except Exception:  # noqa: BLE001 — kept: a probe surveying an optional oracle must not die on its absence
                continue
            if "NEAR ELECTRIC FIELDS" in t:
                text = t
                break
    assert text, "no printout with a near-field table found"
    out = {}
    in_tbl = False
    for line in text.splitlines():
        if "NEAR ELECTRIC FIELDS" in line:
            in_tbl = True
            continue
        if in_tbl:
            parts = line.split()
            if len(parts) >= 9:
                try:
                    x, y, z = (float(parts[0]), float(parts[1]), float(parts[2]))  # noqa: F841 — kept: names the quantity the probe computed, read when inspecting
                    exm, exp_ = float(parts[3]), float(parts[4])
                except ValueError:
                    continue
                ex = exm * np.exp(1j * np.radians(exp_))
                out[f"eng x={x} d={-z}"] = f"{ex:.6e}"
                print(f"  eng x={x} z={z}: Ex = {ex:.4e}")
    save(out)


def verdict():
    r = load()
    pts = probe_points()

    mw = np.array([complex(r[f"mw x={x} d={d}"]["emf"]) for x, d in pts])
    emp = np.array([complex(r[f"emp x={x} d={d}"]["emf"]) for x, d in pts])
    alpha = (np.vdot(mw, emp)) / np.vdot(mw, mw)
    resid = np.abs(alpha * mw - emp) / np.abs(emp)
    print(f"momwire vs empymod: one global alpha = {alpha:.4e}")
    for (x, d), rr in zip(pts, resid, strict=True):
        print(f"  x={x} d={d}: relative residual {rr:.3f}")
    print(f"  worst {resid.max():.3f}, median {np.median(resid):.3f}\n")

    print("depth-decay profiles |E(d)|/|E(0.15)| at each x:")
    for x in XS:
        for name, vec in (
            ("empymod ", emp),
            ("momwire ", mw),
        ):
            prof = [
                abs(vec[pts.index((x, d))]) / abs(vec[pts.index((x, 0.15))])
                for d in DEPTHS
            ]
            print(f"  x={x} {name}: " + "  ".join(f"{p:.3f}" for p in prof))
        eng_keys = [f"eng x={x} d={d}" for d in DEPTHS]
        if all(k in r for k in eng_keys):
            ev = [complex(r[k]) for k in eng_keys]
            prof = [abs(v) / abs(ev[0]) for v in ev]
            print(f"  x={x} engine  : " + "  ".join(f"{p:.3f}" for p in prof))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "verdict"
    {
        "momwire": run_momwire,
        "empymod": run_empymod,
        "engine": run_engine,
        "verdict": verdict,
    }[mode]()
