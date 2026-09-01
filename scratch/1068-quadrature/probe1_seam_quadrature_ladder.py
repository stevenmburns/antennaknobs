"""antennaknobs#1068 — is the buried-radials residual physics, or our quadrature?

`advanced/buried-radials` publishes a residual that GROWS with radial count:

    no radials 0.17 Ω,  1 radial 0.83 Ω,  4 radials 1.94 Ω

read as "the one genuine disagreement this study found". Those momwire columns
were computed in August 2026 at the then-default cross-edge quadrature
`n_qp_pair = 4`. momwire#760 later measured cross-edge error at a lossy-soil
interface falling only as C/q — on momwire's side only, concentrated on buried
wire, growing with the number of buried members at a junction. Same side, same
direction, same ordering as the residual. So the published claim is currently
unfalsifiable from the page: the one axis that could manufacture exactly this
ordering was held fixed at its least-converged value.

This probe re-runs the momwire columns across a quadrature ladder and asks
whether the ordering survives. The engine columns cannot move — they are a
different code — so the banked Richardson limits below are used as-is.

METHOD. The published columns are the EZNEC-dialect seam (momwire reading the
same NEC-5 deck text), not momwire's native builder, so this stays on the seam
path: `serve()` resolves a basis name to (solver_class, kwargs) through
`basis_entry`, and patching that in the seam's own namespace changes the
quadrature and nothing else. Decks come from `probe_e5_matched.e2_engine_deck`,
the same generator that produced the published table.

REPRODUCTION CAVEAT, measured before anything here was believed: at q=4 this
harness prints 100.5345+19.3766j for `ref x1` where August banked
100.5300+19.3770j — 4.5 mΩ apart, not bit-identical. momwire moved through two
releases in between (#758's quadrature split, #762, #769, #778, #781), and #778
and #781 are both documented round-off movers. 4.5 mΩ is three orders of
magnitude below the 1.94 Ω effect under test, so it does not touch the question;
it is recorded because "reproduced the published number" would be false.

Run:
  .venv/bin/python scratch/1068-quadrature/probe1_seam_quadrature_ladder.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "elevated-panel"))

import momwire.eznec._serve as serve_mod
from momwire.bspline import BSplineSolver
from momwire.deck import parse_nec5
from probe_e5_matched import e2_engine_deck

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results" / "probe1-seam-ladder.json"

H = 0.25
GEOMS = ("ref", "lone", "fan")
MULTS = (1, 3)
LADDER = (4, 8, 16, 32, 64, 128)

# Banked engine columns from the published table: its own x1/x3/x8 refinement
# ladder Richardson-extrapolated. A different code — nothing here moves them.
ENGINE_LIMIT = {
    "ref": 100.64 + 20.08j,
    "lone": 100.76 + 20.95j,
    "fan": 100.70 + 22.49j,
}

# What the page prints today, for the delta column.
PUBLISHED_X3 = {
    "ref": 100.62 + 19.91j,
    "lone": 100.55 + 20.15j,
    "fan": 100.17 + 20.64j,
}


def seam(text: str, q: int) -> complex:
    """One deck through the seam with cross-edge quadrature forced to `q`."""
    original = serve_mod.basis_entry
    serve_mod.basis_entry = lambda basis: (BSplineSolver, {"n_qp_pair": q})
    try:
        return serve_mod.serve(parse_nec5(text)).sources[0].impedance
    finally:
        serve_mod.basis_entry = original


def main() -> None:
    out: dict[str, str] = {}
    for geom in GEOMS:
        for mult in MULTS:
            deck = e2_engine_deck(geom, H, mult)
            for q in LADDER:
                t0 = time.time()
                z = seam(deck, q)
                key = f"seam-e2 {geom} h={H} x{mult} q={q}"
                out[key] = f"{z:.6f}"
                print(f"  {key}: {z:12.6f}  ({time.time() - t0:.1f}s)", flush=True)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(out, indent=1))
    print(f"saved {RESULTS}")

    print("\n=== |seam x3 - engine limit| across the quadrature ladder ===")
    print(f"{'q':>5} " + " ".join(f"{g:>12}" for g in GEOMS) + "   ordering")
    published = " ".join(
        f"{abs(PUBLISHED_X3[g] - ENGINE_LIMIT[g]):12.3f}" for g in GEOMS
    )
    print(f"{'pub':>5} {published}   (the published row, q=4, August)")
    for q in LADDER:
        vals = [
            abs(complex(out[f"seam-e2 {g} h={H} x3 q={q}"]) - ENGINE_LIMIT[g])
            for g in GEOMS
        ]
        grows = "grows" if vals[0] < vals[1] < vals[2] else "BROKEN"
        print(f"{q:>5} " + " ".join(f"{v:12.3f}" for v in vals) + f"   {grows}")


if __name__ == "__main__":
    main()
