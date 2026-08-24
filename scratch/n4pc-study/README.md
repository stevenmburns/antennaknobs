# N4PC Loop (captures 0081-0084): the deviation resolved — 2026-08-21

The 122-corpus sweep's sharpest impedance deviation (3.8–4.3 kΩ on a 7–9 kΩ
anti-resonance at 14.1 MHz) is **the capture's mesh, not a seam defect**.

The model: 15.5 m square loop (2.9 λ perimeter) at 15.24 m, two `EX 4`
current sources, 16 segs/side. Four captures: GN 0 / GD × XQ / RP.

Findings (all from `sweep.py` → `sweep.json`, figure in
`n4pc-anti-resonance.png`):

1. **Ground-independent**: the deviation is the same over GN 0 (capture
   6948+j3810 vs seam 8976+j646) and GD (7298+j4230 vs 9682+j641). GD's
   currents solve over a perfect image → the Sommerfeld machinery is
   exonerated; the cause is the loop solve itself.
2. **Mesh ladder at 14.1 MHz (GD)**: the seam is converged at the deck's own
   mesh (9682+j641 at ×1 → 9723−j104 at ×8, ~0.5 % total motion). The
   licensed engine **marches onto the seam's answer**: 7298+j4230 →
   9154+j2276 → 9560+j1229 → 9673+j677 (×8 ≈ the seam's ×1).
3. **Mechanism**: at 16 segs/side NEC-5's anti-resonance sits ≈ 0.14 MHz
   (~1 %) high (f_res ≈ 14.26 vs the converged ≈ 14.12 MHz); the resonance
   slope (~1.8 kΩ per 50 kHz) magnifies that into the corpus number. Both
   engines trace the same ≈ 9.7 kΩ peak.

Consequences: the corpus matrix's N4PC row should be annotated
"capture under-converged, seam-side value is the converged one" (same class
as the coupled-loop finding: bs2 better-converged than the licensed engine
at the deck's own mesh — a pitch exhibit, not a defect). No momwire issue
needed; nothing to fix.
