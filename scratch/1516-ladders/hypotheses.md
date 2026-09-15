## Verdicts, and what they mean

### All four designs give the same answer, and it is not the one the framing suggests

Every one of the six cases reads **tent pair unconverged**. bs2 is the engine
sitting still: it moves 0.05–2.4 % of its own value from ×1 to ×8. razor and
NEC-5 move 18–33 %, together, toward bs2. So "bs2 differs from both by 16–50 %"
at the shipped mesh is not bs2 being wrong — it is **razor and NEC-5 both being
coarse, in the same direction, by the same amount**.

That is exactly what momwire's own `RazorFarMeshClass` advisory says: razor-2p is
*first order* in the far mesh because its path-testing rule is NEC-5's, "a median
3.3 % from converged, with a tail to 34 %", and "for a converged answer use
BSplineSolver (degree 2), which is already converged at these same segment
counts". The advisory fires on every razor cell in this study. These four designs
are the tail it warns about, and the binary is in the tail with it — which is the
point worth keeping: **the agreement between razor-2p and NEC-5 is agreement
about a coarse answer.** Both converge to bs2's.

The order table makes it quantitative. Local exponents on the bs2−NEC-5 gap
against the actual segment count:

| design | exponents ×1→×2→×4→×8 | reading |
|---|---|---|
| `verticals.rectangle` | 0.84, 1.03, 1.13 | first order |
| `dipoles.koch_dipole` | 0.93, 1.04, 1.23 | first order |
| `verticals.four_square` free | 0.91, 0.78, 0.71 | first order, slowest here |
| `verticals.four_square` somm | 1.06, 1.03, 1.20 | first order |
| `loops.skyloop_lmatch` | 2.34, 2.18, 1.96 | **second order** |
| `loops.skyloop_lmatch` bare | 1.94, 2.09, 1.94 | **second order**, so it is the loop, not the match |

And the first-order Richardson extrapolation from ×4 → ×8 puts the two sides in
the same place: razor and bs2 land 0.56 % apart on `rectangle` (against 4.86 % at
×8 itself), 1.59 % on `koch_dipole` (4.42 %), 1.03 % on `four_square` (3.34 %).
The gap at ×8 is residual razor mesh error, not a disagreement about the answer.

`skyloop_lmatch` is the exception and its own table says why: at exponent ≈ 2 a
*first-order* Richardson over-corrects, which is why its extrapolated separation
(1.22 %) is larger than its measured ×8 gap (0.473 %). The extrapolation is
reported for every case rather than only where it flatters the story.

### Step 1 found no deck difference anywhere

razor's and NEC-5's built meshes are **identical wire for wire at every rung of
every case** — 91/91, 174/174, 390/390, 1272/1272 and so on — and bs2 differs
only on the fed wires, one per feed, which is its odd parity taking a different
segment count there. Nothing else differs. The three named risks:

* **The L-match on `skyloop_lmatch` is not a deck difference.** `build_network()`
  returns one object; momwire keeps it on `_network` and `nec5.py:394` runs the
  same object through `_network_as_meshed`. It is applied to the antenna Y in
  Python, and the NEC-5 deck antennaknobs writes carries no `NT` and no `LD` for
  it — the generated card list above shows only `CM CE GW GE FR XQ EN`. Same for
  `rectangle`'s `TL` transmission line.
* **Δ/a never approaches the regime the peer flagged.** The minimum anywhere, at
  the ×8 rung, is **31.0**; `koch_dipole`'s short facets bottom out at 31.3, not
  near 1. Even at ×8 its shortest segment is 15.67 mm against a 0.5 mm radius; at
  ×1 it is 94.0 mm, for Δ/a = 188. P6 held with a lot of room.
* **`four_square`'s four phased feeds behave.** All four ports track: razor−NEC-5
  is 0.22–0.27 % at every port at every free rung, and the bs2 gap closes on all
  four together (17.9/22.1/22.1/21.7 % at ×1 → 3.56/4.32/4.32/4.16 % at ×8).
  Ports 1 and 2 agree to **1.7e-12** relative at worst across all 30 cells, which
  is the design's own symmetry recovered numerically and a free consistency check.
  (They are NOT bit-identical — the first version of this sentence said so on the
  strength of a table that rounds both to three figures. The measured worst case
  is 28.428352483663 + 2.689137561780j against ...664 + ...828j.)

### Two stable residues that mesh refinement does NOT remove

These are small, and they are the only formulation-level findings here.

1. **A free-space razor↔NEC-5 floor, per design, flat across the ladder**:
   0.09 % on `koch_dipole`, 0.12 % on `skyloop_lmatch`, 0.22 % on `four_square`,
   0.52 % on `rectangle`. Each is constant to within a few percent of itself over
   a 4–8× mesh change, so it is not discretisation. It is the residue between two
   implementations of the same testing rule, and at these sizes it is the
   background against which everything else in this study is measured.
2. **A Sommerfeld floor on `four_square` that is 8× the free-space one**:
   razor−NEC-5 reads **2.00 / 1.83 / 1.73 / 1.68 %** across ×1 → ×8 where free
   space reads 0.226 / 0.222 / 0.220 / 0.223 %. It shrinks by a tenth over a 7.6×
   mesh refinement, i.e. essentially not at all. Two engines that agree to 0.22 %
   in free space and 1.7 % over Sommerfeld disagree about the **ground model**,
   not the basis — momwire's Sommerfeld against NEC-5's. Not chased here; named
   so it is not mistaken for razor's mesh error, which is what it would look like
   from the ×1 row alone.

### The two misses

**P4 missed, and the mechanism was wrong, not just the number.** I predicted the
L-match would amplify the bs2 gap by more than 1.2× at every rung, on the
strength of the ×1 measurement (49.62 % through the match against 33.95 % bare,
a ratio of 1.46). Measured across the ladder the ratio is **1.462 at ×1, 1.109 at
×2, 1.044 at ×4, 1.030 at ×8** (and 1.119 at the served ×40) — the amplification
is itself a coarse-mesh artefact. The reading:
the match is tuned for the converged antenna impedance, so when the tent pair's
answer is far from it (265.7 − 190.3j at ×1 against a 258.6 − 76.4j limit) the
transformation is in a sensitive corner; once the antenna Z is near the design
point the match is close to a conjugate match and passes relative error through
at nearly unity. So the L-match is not an amplifier of a real difference — it is
an amplifier of a coarse-mesh error, and it stops amplifying as soon as the mesh
is adequate. The bare-variant ladder is what makes that visible and it is the
reason the variant was run.

**P5 missed, and this one is the actionable result.** I predicted razor at its
served mesh (`nominal_nsegs = 40`, which is `razor-2p`'s `default_n_per_wire`)
would keep at most 0.25 of its ×1 residual to ×8. Measured: **0.285× on
`skyloop_lmatch`, 0.467× on `four_square`, 0.545× on `rectangle`, 0.607× on
`koch_dipole`.** The bar was set as if 40 were a big step; first order in the
mesh says an error ∝ 1/N shrinks by 21/40 ≈ 0.53 going from ×1 to the served
rung, and three of the four land right on that. The prediction was wrong because
it did not apply the convergence order the rest of the study then measured.

What that means for the app, stated plainly and without proposing a fix: **at the
mesh the razor-2p tab actually serves, the bs2−NEC-5 gap on these four designs is
still 8–21 %** — 11.1 % on `skyloop_lmatch`, 20.1 % on `rectangle`, 20.8 % on
`koch_dipole`, 10.4 % on `four_square` free and 8.58 % over Sommerfeld. Since bs2
is within ~1–2 % of the extrapolated limit at any of these rungs, that gap is
very close to razor-2p's own error at the density it ships with. Doubling
`default_n_per_wire` would roughly halve it; that is a product call, and this
study does not make it.

## Reproducing

```
NEC5_EXE=<path to nec5cl-3b75639> \
  python scratch/1516-ladders/run_ladders.py --out scratch/1516-ladders/records.jsonl
python scratch/1516-ladders/report.py > scratch/1516-ladders/README.md
```

90 cells in 49 s on this box. The NEC-5 binary is licensed (LLNL-CODE-746721),
lives outside this repo, and is run and timed as an opaque executable; nothing
here carries its source or its printouts — impedances, meshes and timings only.
