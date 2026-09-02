"""antennaknobs#1068, second half — is the PANEL section a q=4 print too?

`probe1` settled the drop-in table, which is the EZNEC-dialect seam. The same
page carries a second set of momwire numbers in "Converged-vs-converged, the
full panel" (no-radial decks agree to 0.19-0.22 Ω, one radial 0.29-0.44 Ω, four
radials 1.13-1.53 Ω), and those come from a DIFFERENT instrument: momwire's
native builder (`probe_e5_matched.e2_build`, its own d1/d2/d3 ladder and its own
point feed), not the seam. Whether the seam moves says nothing about it.

Measured here: it does not move. `n_qp_pair` is live on this build — q=2 differs
from q=4 — but q=4 is ALREADY converged, agreeing with q=128 to ~1e-4 Ω on all
nine (geometry, height) combinations. The banked August values reproduce
exactly.

So the panel section needs no restatement, and the reason is not that quadrature
is harmless in general: it is that these two front ends discretise the same
physical deck differently enough to have different cross-edge sensitivity. The
seam moves 0.1 Ω between q=4 and converged where the native builder moves 1e-4.
The two also disagree with each other by ~0.3 Ω on the same deck (different feed
spelling: the seam takes the deck's `EX 4` node drive, the native build a point
feed at the centre), so they are separate instruments and always were.

That asymmetry is not explained here, only measured. It is worth a look before
anyone assumes a quadrature result from one momwire front end transfers to the
other.

Run:
  .venv/bin/python scratch/1068-quadrature/probe2_panel_quadrature_check.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "elevated-panel"))

from momwire.bspline import BSplineSolver
from probe_e5_matched import e2_build

HERE = Path(__file__).resolve().parent
BANKED = HERE.parents[1] / "scratch" / "elevated-panel" / "results" / "probe-e5.json"
RESULTS = HERE / "results" / "probe2-panel-check.json"

GEOMS = ("ref", "lone", "fan")
HEIGHTS = (0.25, 0.5, 1.0)
LADDER = (2, 4, 32, 128)


def main() -> None:
    banked = json.loads(BANKED.read_text())
    out: dict[str, str] = {}
    worst_vs_banked = 0.0
    worst_shift = 0.0

    print(
        f"{'geom':>5} {'h':>5}  {'q=4':>22} {'q=128':>22}  {'|128-4|':>9}  {'vs banked':>9}"
    )
    for geom in GEOMS:
        for h in HEIGHTS:
            zs = {}
            for q in LADDER:
                z, _ = BSplineSolver(
                    **e2_build(geom, h, 3), n_qp_pair=q
                ).compute_impedance()
                zs[q] = z
                out[f"mw-e2 {geom} h={h} d3 q={q}"] = f"{z:.6f}"
            b = complex(banked[f"mw-e2 {geom} h={h} d3"])
            shift = abs(zs[128] - zs[4])
            drift = abs(zs[4] - b)
            worst_shift = max(worst_shift, shift)
            worst_vs_banked = max(worst_vs_banked, drift)
            print(
                f"{geom:>5} {h:>5}  {zs[4]:22.6f} {zs[128]:22.6f}"
                f"  {shift:9.6f}  {drift:9.6f}",
                flush=True,
            )

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(out, indent=1))
    print(f"\nsaved {RESULTS}")
    print(f"worst q=4 -> q=128 shift : {worst_shift:.6f} Ω")
    print(f"worst drift vs banked    : {worst_vs_banked:.6f} Ω")
    print(
        "\nThe knob is live, not ignored: q=2 is a control, and it differs.\n"
        "q=2 vs q=4 on fan h=0.25 d3:"
    )
    z2 = complex(out["mw-e2 fan h=0.25 d3 q=2"])
    z4 = complex(out["mw-e2 fan h=0.25 d3 q=4"])
    print(f"  {z2:.6f} vs {z4:.6f}  ->  {abs(z4 - z2):.6f} Ω")


if __name__ == "__main__":
    main()
