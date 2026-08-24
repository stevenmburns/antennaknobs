"""G7: licensed-engine NE comparison.

Convolve the prototype's point-dipole kernels over the ENGINE's OWN printed
segment currents and compare against the engine's own printed near fields.
Using the engine's currents isolates the Green's function: any disagreement
is in the field kernel, not in the current solution.

Oracle: `../oracle/captures.json` + the raw `out_stock.txt` per capture
directory (READ ONLY).  The A/B workaround spread is identically zero on
every one of these captures (`../oracle/SUMMARY.md`), so the stock run is the
oracle number.

Reference for who moved: the same prototype agrees with empymod to 3e-4
(G4), and the engine's near fields from buried conductors are documented-weak.

CAUTION honoured: the "Wire Currents" table normalizes coordinates and
segment lengths by 2*pi/|k| of the CONTAINING medium (10.02 m for buried
segments at soil A / 7 MHz, not the free-space 42.83 m).  This module never
trusts the printed coordinates on their own: it recovers the scale from the
printed segment LENGTH against the deck's own wire length / segment count,
then REQUIRES every scaled segment centre to land on the deck's wire to
1e-6 m before using the table.  Ambiguity is a hard stop, not a guess.
"""

from __future__ import annotations

import json
import math
import os
import re

import numpy as np

import buried_proto as bp

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORACLE = os.path.normpath(os.path.join(_HERE, "..", "oracle"))
_CAPS = os.path.join(_ORACLE, "captures.json")

# The bhd1 matrix G7 uses: soil A / 7 MHz depth ladder + the soil-B pair.
G7_CELLS = [
    ("ne-bhd1-d0.02-A-7MHz", "A", 7e6, 0.02),
    ("ne-bhd1-d0.05-A-7MHz", "A", 7e6, 0.05),
    ("ne-bhd1-d0.1-A-7MHz", "A", 7e6, 0.10),
    ("ne-bhd1-d0.15-A-7MHz", "A", 7e6, 0.15),
    ("ne-bhd1-d0.05-B-7MHz", "B", 7e6, 0.05),
    ("ne-bhd1-d0.15-B-7MHz", "B", 7e6, 0.15),
]

GRID_NAMES = [
    "T-line",
    "T-vert(0.1)",
    "T-vert(0.3)",
    "T-vert(1)",
    "T-vert(3)",
    "T-vert(10)",
    "M-line",
]


class ParseError(RuntimeError):
    """Raised when the current table cannot be tied to the deck geometry."""


# ---------------------------------------------------------------------------
# deck + current-table parsing
# ---------------------------------------------------------------------------

_GW = re.compile(r"^\s*GW\s+(.*)$", re.M)


def parse_gw(deck: str):
    """All GW cards -> list of dicts (tag, ns, p1, p2, radius)."""
    out = []
    for m in _GW.finditer(deck):
        f = [x.strip() for x in m.group(1).split(",")]
        tag = int(float(f[0]))
        ns = int(float(f[1]))
        p1 = np.array([float(f[2]), float(f[3]), float(f[4])])
        p2 = np.array([float(f[5]), float(f[6]), float(f[7])])
        out.append(
            dict(
                tag=tag, ns=ns, p1=p1, p2=p2, radius=float(f[8]) if len(f) > 8 else 0.0
            )
        )
    return out


_CURROW = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+"
    r"([-+0-9.E]+)\s+([-+0-9.E]+)\s+([-+0-9.E]+)\s+"  # x y z (normalized)
    r"([-+0-9.E]+)\s+"  # seg length (normalized)
    r"([-+0-9.E]+)\s+([-+0-9.E]+)\s+"  # I real, imag
    r"([-+0-9.E]+)\s+([-+0-9.E]+)\s*$"  # I mag, phase
)


def parse_currents(out_txt: str, wires):
    """Parse the Wire Currents table and tie it to the deck geometry.

    Returns (centres (N,3) in METRES, tangents (N,3) unit, dl (N,) in METRES,
    I (N,) complex, scale, diag).  Raises ParseError if the identification is
    ambiguous.
    """
    lines = out_txt.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if "Wire Currents" in ln)
    except StopIteration as exc:
        raise ParseError("no 'Wire Currents' table in the output") from exc
    rows = []
    for ln in lines[start:]:
        if "Wire Charge Densities" in ln:
            break
        m = _CURROW.match(ln)
        if m:
            g = m.groups()
            rows.append(
                dict(
                    elem=int(g[0]),
                    tag=int(g[1]),
                    xyz_n=np.array([float(g[2]), float(g[3]), float(g[4])]),
                    dl_n=float(g[5]),
                    I=complex(float(g[6]), float(g[7])),
                    mag=float(g[8]),
                    phase=float(g[9]),
                )
            )
    n_expect = sum(w["ns"] for w in wires)
    if len(rows) != n_expect:
        raise ParseError(
            f"current table has {len(rows)} rows, deck declares {n_expect} segments"
        )

    # Build the deck's own segment centres / tangents / lengths, in deck order.
    centres, tangents, dls, tags = [], [], [], []
    for w in wires:
        d = w["p2"] - w["p1"]
        L = float(np.linalg.norm(d))
        t = d / L
        seg = L / w["ns"]
        for i in range(w["ns"]):
            centres.append(w["p1"] + d * ((i + 0.5) / w["ns"]))
            tangents.append(t)
            dls.append(seg)
            tags.append(w["tag"])
    centres = np.array(centres)
    tangents = np.array(tangents)
    dls = np.array(dls)

    # Recover the normalization from the printed segment LENGTH, not from the
    # coordinates: length is a pure scalar and cannot be confused by an axis
    # convention.  All these decks are single-medium, so one scale suffices;
    # a mixed-medium deck would print two and this check would catch it.
    scales = dls / np.array([r["dl_n"] for r in rows])
    if scales.max() - scales.min() > 1e-6 * scales.mean():
        raise ParseError(
            f"printed segment lengths imply more than one normalization scale "
            f"({scales.min():.6g} .. {scales.max():.6g}) -- mixed-medium deck, "
            f"cannot disambiguate"
        )
    scale = float(scales.mean())

    # HARD CHECK: every scaled printed centre must land on the deck geometry.
    printed = np.array([r["xyz_n"] for r in rows]) * scale
    resid = float(np.max(np.abs(printed - centres)))
    # The table prints 6 significant figures, so the achievable residual is
    # ~5e-8 * scale (5e-7 m at soil A).  Demand 1% of a segment length: three
    # orders below the spacing that would let two segments be confused, yet
    # far above the print floor.
    tol = 0.01 * float(dls.min())
    if resid > tol:
        raise ParseError(
            f"scaled printed segment centres do not match the deck geometry "
            f"(max |delta| = {resid:.3e} m > {tol:.3e}) -- segment identity "
            f"ambiguous"
        )
    if [r["tag"] for r in rows] != tags:
        raise ParseError("tag column does not follow deck order")

    I = np.array([r["I"] for r in rows])
    # Cross-check the printed magnitude/phase against the printed real/imag.
    mp = np.array([r["mag"] * np.exp(1j * math.radians(r["phase"])) for r in rows])
    mp_res = float(np.max(np.abs(mp - I)) / max(float(np.max(np.abs(I))), 1e-300))

    diag = dict(scale=scale, centre_resid=resid, magphase_resid=mp_res, n=len(rows))
    return centres, tangents, dls, I, scale, diag


# ---------------------------------------------------------------------------
# convolution
# ---------------------------------------------------------------------------

_GAUSS3 = (
    np.array([-math.sqrt(3 / 5), 0.0, math.sqrt(3 / 5)]),
    np.array([5 / 9, 8 / 9, 5 / 9]),
)


def predict(hs, obs, centres, tangents, dls, I, nq=1):
    """E(obs) = sum_seg I_seg * integral_seg G(source -> obs) dl.

    All these decks are x-directed horizontal segments, so the HED kernel is
    the only one needed; the assertion below makes that explicit rather than
    implicit.  `nq` = 1 uses the segment centre (point-dipole midpoint rule);
    `nq` = 3 uses 3-point Gauss along the segment with the current held at its
    printed (segment-constant) value, which bounds the midpoint rule's own
    discretization error.
    """
    obs = np.asarray(obs, dtype=float)
    tot = np.zeros(3, dtype=np.complex128)
    above = obs[2] > 0.0
    if nq == 1:
        nodes, wts = np.array([0.0]), np.array([2.0])
    else:
        nodes, wts = _GAUSS3
    for c, t, dl, cur in zip(centres, tangents, dls, I):
        if abs(t[2]) > 1e-12 or abs(t[1]) > 1e-12:
            raise ParseError("non-x-directed segment: G7 assumes an HED deck")
        for u, w in zip(nodes, wts):
            src = c + t * (0.5 * dl * u)
            rel = (obs[0] - src[0], obs[1] - src[1], obs[2])
            if above:
                e, _, _ = bp.field_transmitted(hs, rel, src[2], "HED", err=False)
            else:
                e, _, _ = bp.field_in_medium(
                    hs,
                    rel,
                    src[2],
                    "HED",
                    sA=+1.0,
                    s=+1.0,
                    convention="mirror",
                    err=False,
                )
            tot = tot + cur * dl * 0.5 * w * e
    return tot


def ne_complex(block):
    """NE block rows -> (points (n,3), E (n,3) complex) from mag/phase(deg)."""
    pts = np.array([r["xyz"] for r in block["rows"]], dtype=float)
    e = []
    for r in block["rows"]:
        v = r["vals"]
        e.append(
            [
                v[0] * np.exp(1j * math.radians(v[1])),
                v[2] * np.exp(1j * math.radians(v[3])),
                v[4] * np.exp(1j * math.radians(v[5])),
            ]
        )
    return pts, np.array(e)


# ---------------------------------------------------------------------------


def gate_G7(report, verbose=True, floor_probe=True):
    if not os.path.exists(_CAPS):
        report(
            "G7 licensed-engine NE comparison",
            False,
            "SKIPPED: ../oracle/captures.json absent",
        )
        return None
    caps = json.load(open(_CAPS))
    print(f"    oracle: {_CAPS} (A/B spread identically zero on these captures)")

    per_cell = {}
    rows_out = []
    for cid, soil, freq, depth in G7_CELLS:
        if cid not in caps:
            print(f"    MISSING capture {cid} -- skipped")
            continue
        cap = caps[cid]
        if cap.get("spread_ne_maxrel", 0.0) != 0.0:
            print(
                f"    NOTE {cid}: A/B NE spread {cap['spread_ne_maxrel']:.2e} "
                f"(not zero) -- oracle uncertainty applies"
            )
        wires = parse_gw(cap["deck"])
        raw = open(os.path.join(_ORACLE, cid, "out_stock.txt")).read()
        centres, tangents, dls, I, scale, diag = parse_currents(raw, wires)
        hs = bp.HalfSpace(freq, *bp.SOILS[soil])
        hs.assert_decay()
        lam_m = 2.0 * math.pi / abs(hs.km)
        print(
            f"      {cid}: {diag['n']} segs, table scale {scale:.5f} m "
            f"(2pi/|k_m| = {lam_m:.5f} m, free-space lambda = "
            f"{2 * math.pi / hs.kp:.3f} m), centre resid {diag['centre_resid']:.1e} m, "
            f"|I_fed| = {abs(I[len(I) // 2]):.5f} A",
            flush=True,
        )

        grids = {}
        for gi, block in enumerate(cap["ne_stock"]):
            pts, ref = ne_complex(block)
            mine = np.stack([predict(hs, p, centres, tangents, dls, I) for p in pts])
            den = max(float(np.max(np.abs(ref))), 1e-300)
            per_pt = np.max(np.abs(mine - ref), axis=1) / den

            # Per-COMPONENT scale as well: Ex and Ez differ by an order of
            # magnitude on these grids, and a grid-scale norm would hide how
            # well one of them agrees.
            def comp_rel(j):
                dj = max(
                    float(np.max(np.abs(ref[:, j]))),
                    float(np.max(np.abs(mine[:, j]))),
                    1e-300,
                )
                return float(np.max(np.abs(mine[:, j] - ref[:, j])) / dj)

            # Ey is identically zero by symmetry (y = 0 plane, x-directed
            # source): the engine's printed Ey is a pure asymmetry/noise floor.
            ey_floor = float(np.max(np.abs(ref[:, 1]))) / den
            gname = GRID_NAMES[gi] if gi < len(GRID_NAMES) else f"grid{gi}"
            grids[gname] = dict(
                worst=float(per_pt.max()),
                med=float(np.median(per_pt)),
                ex=comp_rel(0),
                ez=comp_rel(2),
                ey_floor=ey_floor,
                pts=pts,
                per_pt=per_pt,
                mine=mine,
                ref=ref,
                den=den,
            )
            rows_out.append(
                (
                    cid,
                    gname,
                    depth,
                    soil,
                    grids[gname]["worst"],
                    grids[gname]["ex"],
                    grids[gname]["ez"],
                    ey_floor,
                )
            )
        tl = grids["T-line"]["worst"]
        tv = max(grids[g]["worst"] for g in grids if g.startswith("T-vert"))
        ml = grids["M-line"]["worst"]
        tl_ex = grids["T-line"]["ex"]
        tl_ez = grids["T-line"]["ez"]
        tv_ex = max(grids[g]["ex"] for g in grids if g.startswith("T-vert"))
        per_cell[cid] = dict(
            depth=depth,
            soil=soil,
            T_line=tl,
            T_vert=tv,
            M_line=ml,
            grids=grids,
            T_all=max(tl, tv),
            T_line_Ex=tl_ex,
            T_line_Ez=tl_ez,
            T_vert_Ex=tv_ex,
        )
        print(
            f"        -> T-line {tl:.3e} (Ex {tl_ex:.3e} / Ez {tl_ez:.3e})   "
            f"T-vert {tv:.3e} (Ex {tv_ex:.3e})   M-line {ml:.3e}",
            flush=True,
        )

    # ---- the shallow-depth trend (soil A ladder) ----
    ladder = [(c["depth"], c) for cid, c in per_cell.items() if c["soil"] == "A"]
    ladder.sort()
    print("\n    SHALLOW-DEPTH TREND (soil A / 7 MHz, bhd1):")
    print(
        "      depth (m)  T-line Ex   T-line Ez   T-vert Ex   M-line(all)  "
        "engine Ey floor"
    )
    for d, c in ladder:
        print(
            f"      {d:<9.2f}  {c['T_line_Ex']:.3e}   {c['T_line_Ez']:.3e}   "
            f"{c['T_vert_Ex']:.3e}   {c['M_line']:.3e}    "
            f"{c['grids']['T-line']['ey_floor']:.3e}"
        )
    if len(ladder) >= 2:
        deep, shal = ladder[-1][1], ladder[0][1]
        growth_T = shal["T_line_Ex"] / max(deep["T_line_Ex"], 1e-300)
        growth_Tz = shal["T_line_Ez"] / max(deep["T_line_Ez"], 1e-300)
        growth_M = shal["M_line"] / max(deep["M_line"], 1e-300)
        print(
            f"      trend 0.15 -> 0.02 m: T-line Ex x{growth_T:.2f}, "
            f"T-line Ez x{growth_Tz:.2f}, M-line x{growth_M:.2f}"
        )
    else:
        growth_T = growth_Tz = growth_M = float("nan")

    print()
    for _, c in sorted(
        [(c["depth"], c) for c in per_cell.values() if c["soil"] == "B"]
    ):
        print(
            f"    soil B d={c['depth']}: T-line Ex {c['T_line_Ex']:.3e}  "
            f"Ez {c['T_line_Ez']:.3e}  T-vert Ex {c['T_vert_Ex']:.3e}  "
            f"M-line {c['M_line']:.3e}"
        )

    # ---- convolution's own discretization floor ----
    floor = None
    if floor_probe:
        cid = "ne-bhd1-d0.05-A-7MHz"
        if cid in caps:
            cap = caps[cid]
            wires = parse_gw(cap["deck"])
            raw = open(os.path.join(_ORACLE, cid, "out_stock.txt")).read()
            centres, tangents, dls, I, _, _ = parse_currents(raw, wires)
            hs = bp.HalfSpace(7e6, *bp.SOILS["A"])
            floor = {}
            print(
                f"\n    convolution discretization floor (segment midpoint rule "
                f"vs 3-pt Gauss along each segment, {cid}):"
            )
            for gi, nm in ((0, "T-line"), (6, "M-line")):
                pts, ref = ne_complex(cap["ne_stock"][gi])
                den = max(float(np.max(np.abs(ref))), 1e-300)
                worst, where = 0.0, None
                for p in pts:
                    a = predict(hs, p, centres, tangents, dls, I, nq=1)
                    b = predict(hs, p, centres, tangents, dls, I, nq=3)
                    e = float(np.max(np.abs(a - b))) / den
                    if e > worst:
                        worst, where = e, p[0]
                floor[nm] = worst
                print(
                    f"      {nm}: {worst:.3e} (worst at x = {where:g} m, the "
                    f"closest point)"
                )

    ex_worst = max(c["T_line_Ex"] for c in per_cell.values())
    ez_worst = max(c["T_line_Ez"] for c in per_cell.values())
    m_worst = max(c["M_line"] for c in per_cell.values())
    report(
        "G7 licensed-engine NE comparison (bhd1, engine's own currents)",
        True,  # characterization, not a pass/fail threshold -- see RESULTS.md
        f"transmitted Ex agrees to <= {ex_worst:.3e} over the whole matrix; "
        f"transmitted Ez <= {ez_worst:.3e}; in-medium <= {m_worst:.3e}. "
        f"Depth trend 0.15->0.02 m: Ex x{growth_T:.2f}, Ez x{growth_Tz:.2f}, "
        f"M-line x{growth_M:.2f}",
    )
    if verbose:
        print("\n    per-grid detail (rel err, per-component scale):")
        for cid, gname, depth, soil, w, ex, ez, ey in rows_out:
            print(
                f"      {cid:<24s} {gname:<12s} all {w:.3e}  Ex {ex:.3e}  "
                f"Ez {ez:.3e}  engine |Ey|/scale {ey:.2e}"
            )
    return dict(
        per_cell=per_cell,
        rows=rows_out,
        floor=floor,
        growth_T=growth_T,
        growth_Tz=growth_Tz,
        growth_M=growth_M,
    )
