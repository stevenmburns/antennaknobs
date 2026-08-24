"""What the coaxial rule's declined cross-arm pairs cost — momwire#272.

momwire's B-spline extended kernel extends COAXIAL EQUAL-RADIUS pairs only
(`_ek_axis_groups`). NEC's per-END gating (IND1/IND2) additionally extends
some cross-arm pairs where two arms meet at a bend or a K>=3 junction.
`_bspline_kernels.py` calls the resulting gap "~1 % of Z at Delta/a = 2, and
O(h) in the refinement limit -- #249 4.3". That is an ESTIMATE from the
design. This script measures it.

## The quantity, and why it is not a plain Z difference

momwire's B-spline Galerkin and nec2c's sinusoidal collocation do not agree
on Z to anything like 1 % on their own, so |Z_mw - Z_nec| cannot answer the
question -- it is dominated by the basis difference.

What isolates the kernel is the EK SHIFT:

    delta = Z(EK on) - Z(EK off)

taken within each solver. The basis largely cancels: both solvers answer the
same geometry with the same mesh, and the shift is what turns the extended
kernel on. Then

    gap = |delta_nec - delta_mw| / |Z|

is the part of the shift nec2c applies and momwire does not. This is the
existing house method: tests/test_extended_kernel_bspline.py's G9/G10 gate
exactly this delta against nec2c on a straight wire.

## The control, and why the measurement needs one

On a STRAIGHT wire every pair is coaxial, so momwire declines nothing and the
true gap is zero by construction. Any nonzero `gap` measured there is the
basis noise floor in the shift -- and G9 already records that floor as large
(43.2 % of delta at Delta/a = 6.1). So the straight rung is run at every
radius as a control, and the bent / K=3 readings are only meaningful where
they EXCEED it.

Reporting `gap` for a bent deck without that control would attribute basis
noise to the coaxial rule.

## Geometries

    straight  one 0.5 lambda polyline               -- control, zero declined pairs
    bent      one 0.5 lambda polyline, 90 deg bend  -- IND=2 cross-arm pairs
    k3        three 1/6 lambda arms at 120 deg      -- IND=2 at a K=3 junction

All at lambda = 1 m, fed one segment away from the bend / junction, which is
where the declined pairs live and so where Z is most sensitive to them.

Run from the antennaknobs project root:

    .venv/bin/python scratch/272-coaxial-rule/measure_coaxial_rule.py

Writes readings.json beside this file and prints the table. Decks and nec2c
printouts for every rung are written to decks/ so the reading can be checked
without re-running anything.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from momwire.bspline import BSplineSolver

HERE = Path(__file__).resolve().parent
DECK_DIR = HERE / "decks"

LAM = 1.0  # metres; f = c / lambda below
FREQ_MHZ = 299.7924580  # c in Mm/s -> lambda exactly 1 m
HALF = 0.25 * LAM  # each arm of the 0.5 lambda dipoles
K3_ARM = LAM / 6.0  # three arms, same total wire as a 0.5 lambda dipole

N_PER_ARM = 11  # segments per arm; odd, so a bend never lands mid-segment

# Delta/a rungs across the window #272 names. Delta is fixed by the mesh, so
# the radius is what moves: a = Delta / (Delta/a).
DA_RUNGS = (2.0, 3.0, 4.0, 6.0, 10.0, 15.0, 25.0)


# The refinement leg. #249 4.3's estimate has TWO clauses -- "~1 % of Z at
# Delta/a = 2" and "O(h) in the refinement limit" -- and the Delta/a sweep
# above cannot test the second one: it moves Delta/a by changing the RADIUS at
# a fixed mesh, so a/lambda moves with it. Refinement is the other family:
# hold the radius fixed and shrink h. Delta/a still moves (it is h/a), but
# a/lambda does not, so this is the sweep the O(h) claim is about.
REFINE_RADIUS = 0.005681818  # Delta/a = 4 at N_PER_ARM = 11
REFINE_NS = (5, 7, 11, 15, 21)


def _radius_for(da: float, arm_len: float) -> float:
    return (arm_len / N_PER_ARM) / da


# ----------------------------------------------------------------------
# Geometry -- one definition, consumed by both solvers
# ----------------------------------------------------------------------


def geometry(kind: str, n: int = N_PER_ARM):
    """(polylines, junctions, feed_wire_index, feed_arclength, arm_len).

    `feed_arclength` is measured along the fed polyline and placed one full
    segment away from the bend / junction node: on the segment that owns the
    declined cross-arm pairs, without sitting exactly on the node (where a
    delta gap is ill-defined for the K=3 case).

    `junctions` is NOT optional and NOT inferred. BSplineSolver only builds
    KCL constraints for junctions it is handed (`bspline.py`: `self.junctions
    = []` unless the argument is given), so three arms sharing a coordinate
    with no junction list are three electrically DISCONNECTED wires. Measured
    that way the K=3 reading is meaningless -- momwire's EK shift came out 15x
    nec2c's, which is a disconnected-geometry artefact, not a kernel gap.
    """
    if kind == "straight":
        # Control: collinear, so every pair is coaxial and nothing is declined.
        pl = np.array([[-HALF, 0.0, 0.0], [0.0, 0.0, 0.0], [HALF, 0.0, 0.0]])
        seg = HALF / n
        return [pl], None, 0, HALF - 1.5 * seg, HALF
    if kind == "bent":
        # 90 degree bend at the origin -- the IND=2 cross-arm case. One
        # polyline with an interior vertex, so the bend needs no junction:
        # the two edges are a single wire's, and it is `_ek_axis_groups`
        # giving them different labels that declines the cross-edge pairs.
        pl = np.array([[-HALF, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, HALF, 0.0]])
        seg = HALF / n
        return [pl], None, 0, HALF - 1.5 * seg, HALF
    if kind == "k3":
        # Three arms at 120 degrees from a common node: a genuine K=3 junction.
        arms = []
        for deg in (90.0, 210.0, 330.0):
            th = np.radians(deg)
            arms.append(
                np.array(
                    [
                        [0.0, 0.0, 0.0],
                        [K3_ARM * np.cos(th), K3_ARM * np.sin(th), 0.0],
                    ]
                )
            )
        seg = K3_ARM / n
        # All three arms leave the node, so all three ends are "start".
        junctions = [[(0, "start"), (1, "start"), (2, "start")]]
        return arms, junctions, 0, 1.5 * seg, K3_ARM
    raise ValueError(kind)


# ----------------------------------------------------------------------
# nec2c
# ----------------------------------------------------------------------


def nec_deck(kind: str, radius: float, n: int = N_PER_ARM) -> str:
    """The NEC deck for one rung. GW tags follow the polyline edges so the
    bend / junction is a shared NEC node, which is what arms NEC's per-end
    gating in the first place."""
    polylines, _jn, _fw, _fa, _arm = geometry(kind, n)
    cards = ["CM momwire#272 coaxial-rule measurement", f"CM {kind} Delta/a rung", "CE"]
    tag = 0
    fed_tag = fed_seg = None
    for pl in polylines:
        for e in range(len(pl) - 1):
            tag += 1
            p, q = pl[e], pl[e + 1]
            cards.append(
                f"GW {tag} {n} {p[0]:.6f} {p[1]:.6f} {p[2]:.6f} "
                f"{q[0]:.6f} {q[1]:.6f} {q[2]:.6f} {radius:.8f}"
            )
            # Feed one segment in from the node shared with the next edge.
            if kind in ("straight", "bent") and e == 0:
                fed_tag, fed_seg = tag, n - 1
            elif kind == "k3" and tag == 1:
                fed_tag, fed_seg = tag, 2
    cards += [
        "GE 0",
        f"EX 0 {fed_tag} {fed_seg} 0 1. 0.",
        f"FR 0 1 0 0 {FREQ_MHZ:.7f} 0.",
        "XQ",
        "EN",
    ]
    return "\n".join(cards) + "\n"


def _parse_z(out_text: str) -> complex:
    lines = out_text.splitlines()
    for i, ln in enumerate(lines):
        if "ANTENNA INPUT PARAMETERS" in ln:
            j = i + 3
            while j < len(lines) and lines[j].strip():
                toks = lines[j].split()
                if len(toks) >= 8:
                    return complex(float(toks[6]), float(toks[7]))
                j += 1
    raise RuntimeError("no impedance in nec2c output")


def nec_z(
    kind: str, radius: float, ek: bool, keep_as: str | None = None, n: int = N_PER_ARM
) -> complex:
    """One nec2c solve. `EK` arms the extended kernel; its absence is the
    standard thin-wire kernel (`EK -1` is the explicit off, but a deck with no
    EK card has never armed it -- see momwire's deck spec #ek)."""
    deck = nec_deck(kind, radius, n)
    if ek:
        deck = deck.replace("GE 0\n", "GE 0\nEK\n")
    with tempfile.TemporaryDirectory() as d:
        nec = Path(d) / "deck.nec"
        out = Path(d) / "deck.out"
        nec.write_text(deck)
        subprocess.run(
            ["nec2c", "-i", str(nec), "-o", str(out)], check=True, capture_output=True
        )
        text = out.read_text()
    if keep_as:
        DECK_DIR.mkdir(parents=True, exist_ok=True)
        (DECK_DIR / f"{keep_as}.nec").write_text(deck)
        (DECK_DIR / f"{keep_as}.out").write_text(text)
    return _parse_z(text)


# ----------------------------------------------------------------------
# momwire
# ----------------------------------------------------------------------


def mw_z(kind: str, radius: float, ek: bool, n: int = N_PER_ARM) -> complex:
    polylines, junctions, feed_wire, feed_arc, _arm = geometry(kind, n)
    n_per_edge = [[n] * (len(pl) - 1) for pl in polylines]
    z, _ = BSplineSolver(
        wires=polylines,
        n_per_edge_per_wire=n_per_edge,
        junctions=junctions,
        degree=2,
        wavelength=LAM,
        wire_radius=radius,
        feed_wire_index=feed_wire,
        feed_arclength=feed_arc,
        feed_model="segment",
        extended_kernel=ek,
    ).compute_impedance()
    return complex(z)


# ----------------------------------------------------------------------


def main() -> int:
    if shutil.which("nec2c") is None:
        sys.exit("nec2c not on PATH -- required as the oracle")

    rows = []
    for kind in ("straight", "bent", "k3"):
        _pl, _jn, _fw, _fa, arm = geometry(kind)
        for da in DA_RUNGS:
            a = _radius_for(da, arm)
            stem = f"{kind}_da{da:g}"
            z_nec_off = nec_z(kind, a, False, keep_as=f"{stem}_ekoff")
            z_nec_on = nec_z(kind, a, True, keep_as=f"{stem}_ekon")
            z_mw_off = mw_z(kind, a, False)
            z_mw_on = mw_z(kind, a, True)
            d_nec = z_nec_on - z_nec_off
            d_mw = z_mw_on - z_mw_off
            # Normalise the residual on nec2c's own |Z| -- the oracle's scale,
            # not momwire's, so a basis-level offset in |Z| cannot move it.
            gap = abs(d_nec - d_mw) / abs(z_nec_on)
            rows.append(
                {
                    "geometry": kind,
                    "delta_over_a": da,
                    "radius_m": a,
                    "z_nec_ek_off": [z_nec_off.real, z_nec_off.imag],
                    "z_nec_ek_on": [z_nec_on.real, z_nec_on.imag],
                    "z_mw_ek_off": [z_mw_off.real, z_mw_off.imag],
                    "z_mw_ek_on": [z_mw_on.real, z_mw_on.imag],
                    "delta_nec": [d_nec.real, d_nec.imag],
                    "delta_mw": [d_mw.real, d_mw.imag],
                    "gap_frac_of_z": gap,
                }
            )
            print(
                f"{kind:9s} D/a={da:5.1f} a={a:9.6f}  "
                f"d_nec={d_nec.real:+8.3f}{d_nec.imag:+8.3f}j  "
                f"d_mw={d_mw.real:+8.3f}{d_mw.imag:+8.3f}j  "
                f"gap={100 * gap:6.3f}%"
            )

    # ---- refinement leg: hold the radius, shrink h -------------------
    print()
    refine = []
    for n in REFINE_NS:
        row = {"n_per_arm": n, "radius_m": REFINE_RADIUS}
        for kind in ("straight", "bent", "k3"):
            _pl, _jn, _fw, _fa, arm = geometry(kind, n)
            h = arm / n
            d_nec = nec_z(kind, REFINE_RADIUS, True, n=n) - nec_z(
                kind, REFINE_RADIUS, False, n=n
            )
            d_mw = mw_z(kind, REFINE_RADIUS, True, n=n) - mw_z(
                kind, REFINE_RADIUS, False, n=n
            )
            z_ref = nec_z(kind, REFINE_RADIUS, True, n=n)
            row[kind] = {
                "h_m": h,
                "delta_over_a": h / REFINE_RADIUS,
                "gap_frac_of_z": abs(d_nec - d_mw) / abs(z_ref),
            }
        # The declined pairs' own contribution is what the bent / K=3 deck
        # shows OVER the control at the same h -- the control has none.
        for kind in ("bent", "k3"):
            row[kind]["excess_over_control"] = (
                row[kind]["gap_frac_of_z"] - row["straight"]["gap_frac_of_z"]
            )
        refine.append(row)
        print(
            f"n={n:3d} h={row['straight']['h_m']:.5f} "
            f"D/a={row['straight']['delta_over_a']:5.2f}  "
            f"straight={100 * row['straight']['gap_frac_of_z']:6.3f}%  "
            f"bent={100 * row['bent']['gap_frac_of_z']:6.3f}% "
            f"(excess {100 * row['bent']['excess_over_control']:+6.3f}%)  "
            f"k3={100 * row['k3']['gap_frac_of_z']:6.3f}% "
            f"(excess {100 * row['k3']['excess_over_control']:+6.3f}%)"
        )

    out = HERE / "readings.json"
    out.write_text(
        json.dumps(
            {
                "issue": "momwire#272",
                "lambda_m": LAM,
                "freq_mhz": FREQ_MHZ,
                "n_per_arm": N_PER_ARM,
                "note": (
                    "gap = |delta_nec - delta_mw| / |Z_nec(EK on)|, where "
                    "delta = Z(EK on) - Z(EK off) within each solver. The "
                    "'straight' rows are the control: zero pairs are declined "
                    "there, so their gap is the basis noise floor in the "
                    "shift, and bent / k3 readings mean something only where "
                    "they exceed it. 'refinement' is the second leg: the "
                    "radius is held at REFINE_RADIUS and h shrinks, which is "
                    "the family the O(h) half of #249 4.3's estimate is "
                    "about; excess_over_control is the bent / k3 gap minus "
                    "the straight gap at the same h."
                ),
                "rows": rows,
                "refinement": refine,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\nwrote {out}")
    print(f"decks + nec2c printouts in {DECK_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
