"""G4: empymod cross-check + the (A_m, s) sign selection.

PRIMARY oracle: ../empymod/results.json (the shared harness, empymod 2.6.0
with ht='quad', htarg pts_per_dec=600, limit=4000, xdirect=True).  Consumed,
not regenerated -- its SUMMARY.md records that empymod's DEFAULT DLF Hankel
filters are wrong by 0.13 median / 0.65 max on exactly these grids, so any
comparison run at empymod's defaults is meaningless here.  See the FIRST-CUT
note at the bottom of RESULTS.md.

Secondary, generated here by CALLING empymod directly (run, never
transcribed): a HOMOGENEOUS whole-space calibration that pins the time
convention and the coordinate/orientation mapping against our own complex-k
closed form.  That path uses empymod's analytic full-space branch, so the DLF
issue does not touch it.  Calls are cached in `empymod_cache.json`.

Coordinate mapping (ours -> empymod).  empymod's z axis points DOWN with the
interface at depth[0] = 0, so z_emp = -z_ours, x/y unchanged:

  HED (our +x-hat):   E_x = +Ex(ab=11),  E_y = +Ey(ab=21),  E_z = -Ez(ab=31)
  VED (our +z-hat = -z_emp):
                      E_x = -Ex(ab=13),  E_y = -Ey(ab=23),  E_z = +Ez(ab=33)
"""

from __future__ import annotations

import hashlib
import json
import os

import numpy as np

import buried_proto as bp

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE_PATH = os.path.join(_HERE, "empymod_cache.json")
_SHARED = os.path.normpath(os.path.join(_HERE, "..", "empymod", "results.json"))

_cache: dict | None = None


def _load_cache():
    global _cache
    if _cache is None:
        _cache = json.load(open(_CACHE_PATH)) if os.path.exists(_CACHE_PATH) else {}
    return _cache


def emp(src, rec, depth, res, freq, ab, epermH):
    """One empymod.dipole call (EMPYMOD coordinates, z down), memoized."""
    import empymod

    key = json.dumps(
        dict(
            src=src,
            rec=[list(np.atleast_1d(c)) for c in rec],
            depth=depth,
            res=res,
            freq=freq,
            ab=ab,
            epermH=epermH,
        ),
        sort_keys=True,
        default=float,
    )
    kh = hashlib.sha1(key.encode()).hexdigest()
    c = _load_cache()
    if kh in c:
        return np.array([complex(a, b) for a, b in c[kh]["v"]])
    out = empymod.dipole(
        src=src,
        rec=rec,
        depth=depth,
        res=res,
        freqtime=freq,
        ab=ab,
        epermH=epermH,
        epermV=epermH,
        verb=0,
    )
    out = np.atleast_1d(np.asarray(out, dtype=complex)).ravel()
    c[kh] = {"call": json.loads(key), "v": [[z.real, z.imag] for z in out]}
    with open(_CACHE_PATH, "w") as fh:
        json.dump(c, fh, indent=1)
    return out


def emp_fields_homog(kind, zsrc_ours, pts_ours, soil, freq):
    """Homogeneous whole space (both empymod layers = the soil)."""
    eps_r, sigma = soil
    res = [1.0 / sigma, 1.0 / sigma]
    eperm = [eps_r, eps_r]
    xs = [float(p[0]) for p in pts_ours]
    ys = [float(p[1]) for p in pts_ours]
    z_obs = float(pts_ours[0][2])
    src = [0.0, 0.0, -float(zsrc_ours)]
    rec = [xs, ys, -z_obs]
    if kind == "HED":
        ex = emp(src, rec, [0.0], res, freq, 11, eperm)
        ey = emp(src, rec, [0.0], res, freq, 21, eperm)
        ez = -emp(src, rec, [0.0], res, freq, 31, eperm)
    else:
        ex = -emp(src, rec, [0.0], res, freq, 13, eperm)
        ey = -emp(src, rec, [0.0], res, freq, 23, eperm)
        ez = emp(src, rec, [0.0], res, freq, 33, eperm)
    return np.stack([ex, ey, ez], axis=1)


def _rel(a, b):
    a = np.asarray(a)
    b = np.asarray(b)
    den = max(float(np.max(np.abs(a))), float(np.max(np.abs(b))), 1e-300)
    return float(np.max(np.abs(a - b)) / den)


# ---------------------------------------------------------------------------


def calibrate(report=None):
    """empymod's time convention + our mapping, MEASURED on a homogeneous
    whole space against our own complex-k closed form."""
    soil = bp.SOILS["A"]
    freq = 7e6
    hs = bp.HalfSpace(freq, *soil)
    pts = [(2.0, 0.0, -0.5), (5.0, 2.0, -0.5), (10.0, 0.0, -0.5)]
    zsrc = -0.05
    verdict = {}
    for kind in ("HED", "VED"):
        p_hat = np.array([1.0, 0, 0]) if kind == "HED" else np.array([0, 0, 1.0])
        mine = np.stack(
            [
                bp.fs_field(hs.C1, hs.km, p_hat, np.array(p) - np.array([0, 0, zsrc]))
                for p in pts
            ]
        )
        raw = emp_fields_homog(kind, zsrc, pts, soil, freq)
        verdict[kind] = (_rel(mine, raw), _rel(mine, np.conj(raw)))
    best_conj = all(v[1] < v[0] for v in verdict.values())
    err = max(v[1] if best_conj else v[0] for v in verdict.values())
    if report:
        report(
            "G4a empymod calibration (homogeneous whole space, complex k_m)",
            err < 1e-6,
            f"conjugate empymod = {best_conj}; worst rel err {err:.3e} (tol 1e-6)",
        )
    for kind, (a, b) in verdict.items():
        print(f"    {kind}: rel(as-is)={a:.3e}  rel(conjugated)={b:.3e}")
    return best_conj, err


# ---------------------------------------------------------------------------


def _cplx(rows):
    """[[re, im], ...] -> complex array."""
    return np.array([complex(a, b) for a, b in rows])


def load_oracle():
    if not os.path.exists(_SHARED):
        return None
    return json.load(open(_SHARED))


def gate_G4(report, cells_filter=None, verbose=True):
    ora = load_oracle()
    if ora is None:
        report(
            "G4 empymod cross-check", False, "SKIPPED: ../empymod/results.json absent"
        )
        return None
    print(
        f"    oracle: {_SHARED} (empymod {ora['meta']['empymod_version']}, "
        f"{ora['meta']['primary_settings']['ht']} ht)"
    )
    calibrate(report)

    combos = [(sa, s) for sa in (+1.0, -1.0) for s in (+1.0, -1.0)]
    conventions = ("mirror", "literal")
    scan = {(cv, sa, s): 0.0 for cv in conventions for sa, s in combos}
    scan_wc = dict(scan)  # restricted to well-conditioned grids

    rowsT: list[tuple] = []
    rowsM: list[tuple] = []
    worst_T = 0.0
    worst_T_wc = 0.0

    for cell in ora["cells"]:
        cid = cell["id"]
        if cells_filter and cid not in cells_filter:
            continue
        soil = (cell["soil"]["eps_r"], cell["soil"]["sigma"])
        freq = cell["freq_hz"]
        kind = cell["source"]["type"]
        zp = cell["source"]["src_spec_xyz"][2]
        hs = bp.HalfSpace(freq, *soil)
        hs.assert_decay()
        print(f"      ... {cid}", flush=True)
        for gname, g in cell["grids"].items():
            spread = g["xcheck"]["quad_ppd300_vs_primary"]["max_rel"]
            wc = spread <= 1e-3  # oracle's own numerical uncertainty
            pts = g["points_spec_xyz"]
            ref = np.stack([_cplx(g["Ex"]), _cplx(g["Ey"]), _cplx(g["Ez"])], axis=1)
            if gname == "M-line":
                for i, p in enumerate(pts):
                    _t, rel, q, parts = bp.field_in_medium(
                        hs, p, zp, kind, parts=True, err=True
                    )
                    errs = {}
                    for cv in conventions:
                        p_hat = (
                            np.array([1.0, 0, 0])
                            if kind == "HED"
                            else np.array([0, 0, 1.0])
                        )
                        img = bp.image_field(hs.C1, hs.km, p_hat, p, zp, convention=cv)
                        for sa, s in combos:
                            tot = (
                                parts["direct"]
                                + sa * parts["A_m"] * img
                                + s * parts["rem"]
                            )
                            e = _rel(tot, ref[i])
                            errs[(cv, sa, s)] = e
                            if e > scan[(cv, sa, s)]:
                                scan[(cv, sa, s)] = e
                            if wc and e > scan_wc[(cv, sa, s)]:
                                scan_wc[(cv, sa, s)] = e
                    frac = float(np.max(np.abs(parts["rem"]))) / max(
                        float(np.max(np.abs(parts["direct"]))), 1e-300
                    )
                    rowsM.append((cid, gname, tuple(p), rel, spread, wc, errs, frac))
            else:
                for i, p in enumerate(pts):
                    e_mine, rel, q = bp.field_transmitted(hs, p, zp, kind)
                    e = _rel(e_mine, ref[i])
                    worst_T = max(worst_T, e)
                    if wc:
                        worst_T_wc = max(worst_T_wc, e)
                    rowsT.append((cid, gname, tuple(p), e, rel, spread, wc))

    # ---- report regime 1 ----
    report(
        "G4b empymod vs regime-1 transmitted field (below -> above)",
        worst_T_wc < 1e-3,
        f"worst rel err {worst_T:.3e} over ALL grids; {worst_T_wc:.3e} over "
        f"well-conditioned grids (oracle spread <= 1e-3); tol 1e-3",
    )
    if verbose:
        by_cell: dict = {}
        for cid, gname, p, e, rel, spread, wc in rowsT:
            k = (cid, gname)
            by_cell.setdefault(k, []).append((e, rel, spread, wc, p))
        for (cid, gname), v in by_cell.items():
            wr = max(x[0] for x in v)
            print(
                f"    {cid:<22s} {gname:<7s} worst rel {wr:.3e}  "
                f"(oracle spread {v[0][2]:.1e}{'' if v[0][3] else '  [ill-cond]'}; "
                f"selfconv <= {max(x[1] for x in v):.1e})"
            )
        print("    per-point (worst 12):")
        for cid, gname, p, e, rel, spread, wc in sorted(rowsT, key=lambda r: -r[3])[
            :12
        ]:
            print(
                f"      {cid} {gname} p={p}: rel {e:.3e} (oracle spread {spread:.1e})"
            )

    # ---- report the sign scan ----
    print(
        "\n    (A_m, s) sign scan -- worst rel err vs the oracle over every "
        "regime-2 point:"
    )
    rows = sorted(scan.items(), key=lambda kv: kv[1])
    for (cv, sa, s), v in rows:
        print(
            f"      dyad={cv:<8s} sign(A_m)={sa:+.0f} s={s:+.0f}: "
            f"worst rel {v:.3e}   (well-conditioned only: {scan_wc[(cv, sa, s)]:.3e})"
        )
    best = rows[0][0]
    worst_M = rows[0][1]
    worst_M_wc = scan_wc[best]
    report(
        "G4c empymod vs regime-2 in-medium field / (A_m, s) selection",
        worst_M_wc < 1e-3,
        f"winner dyad={best[0]} sign(A_m)={best[1]:+.0f} s={best[2]:+.0f} -> "
        f"worst rel {worst_M:.3e} (all), {worst_M_wc:.3e} (well-conditioned); "
        f"runner-up {rows[1][1]:.3e}; tol 1e-3",
    )
    if verbose:
        print("\n    per-point detail, winning combo:")
        for cid, gname, p, rel, spread, wc, errs, frac in rowsM:
            print(
                f"      {cid} {gname} p={p}: rel {errs[best]:.3e} "
                f"|rem|/|dir| {frac:.2e} selfconv {rel:.1e} "
                f"(oracle spread {spread:.1e}{'' if wc else ' [ill-cond]'})"
            )
    return dict(
        worst_T=worst_T,
        worst_T_wc=worst_T_wc,
        scan=scan,
        scan_wc=scan_wc,
        best=best,
        rowsT=rowsT,
        rowsM=rowsM,
    )
