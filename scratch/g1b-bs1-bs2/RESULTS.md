# G1-B: bspline degree 1 vs degree 2 on the buried anchors

Measured 2026-09-03 on the laptop, momwire main `53a15a6`, AK main `beb0233`,
accelerated kernels on. Scripts: `probe_bs1_bs2.py` (anchor rows, raw rows in
`results.jsonl`) and `ladder.py` (two-degree mesh ladders). The gate that came
out of it is momwire `tests/test_bspline_pair_g1b.py`.

Question: is degree 1 (tent basis, Galerkin) a usable same-trunk cross-check of
degree 2 underground, and what class does the pair agree within?

## Anchors fed ABOVE ground — the pair walks to one limit

|bs1 − bs2| in Ω. "×k" scales every per-edge count by k (odd, so the fed
segment's centre stays put); "far-only" scales only edges whose base segment is
≥ 0.2 m, leaving the node grading fixed.

| anchor (q) | ×1 | ×3 | ×5 | ×9 |
|---|---|---|---|---|
| crossing_deck(1) (64) | 0.9619 | 0.6141 | 0.2422 | 0.2842 |
| hub_deck(4) (32) | 0.4753 | 0.1537 | | |
| fan n2-graded, far-only (64) | 0.4046 | 0.5941 | 0.0949 | |
| BLE 45 ft N=2 (16) | 0.0751 | 0.0555 | | |
| BLE 45 ft N=15 (16) | 0.2414 | 0.093 | | |
| BLE 45 ft N=30 (16) | 0.2388 | | | |
| AK catalog `buried_radial_vertical` hub (32) | 0.5509 | | | |
| AK catalog `buried_radial_vertical` bundle (32) | 0.5511 | | | |

Degree 1 oscillates in R with mesh (crossing: 139.58 / 138.19 / 138.56 / 138.15
at ×1/3/5/9), so the class is stated as a separation at the anchor mesh, not a
shrink rate. Worst case 0.96 Ω; bar 1.5 Ω.

Degree 2's own far-mesh movement on the crossing deck: 0.36 Ω at ×3, 0.61 at
×9 (138.9619−102.6019j → 138.3477−102.3841j). `CROSSING_G1`'s quoted 0.021 Ω
envelope is the node axis only. The fan's degree-2 far-mesh movement is 0.06 Ω
at ×3, 0.10 at ×5, consistent with its docstring's 0.022 per doubling.

Catalog BRV prints (q=32, catalog mesh): hub bs2 75.8502+40.4507j, bs1
75.6774+39.9275j; bundle bs2 75.8525+40.7584j, bs1 75.6800+40.2351j. The
`detached` convention refuses on both degrees (contact + buried, momwire#567).

## Decks fed IN the soil — the anchor mesh is not an impedance anchor

Whole-mesh ladders, both degrees (Ω):

```
bvd1 (1 m vertical dipole, top 0.15 m down, a = 1 mm, soil A)
mult      bs1                    d bs1    bs2                    d bs2   |bs1-bs2|
   1   368.8318 -354.6694j              341.6400 -329.4541j             37.08
   3   339.9565 -327.9259j  39.36       329.1810 -317.9503j  16.96      14.68
   5   333.2376 -321.7097j   9.15       325.7351 -314.7593j   4.70      10.23
   9   327.9218 -316.7875j   7.24       322.6355 -311.8855j   4.23       7.21
  15   324.5338 -313.6468j   4.62       320.2998 -309.7181j   3.19       5.78
  27   321.3623 -310.7041j   4.33       317.5434 -307.1600j   3.76       5.21   (Δ/a = 3.4)

bhd10 (10 m horizontal dipole at 0.15 m)
   1   229.9049 +110.0571j              227.7501  +78.0240j             32.11
   3   227.8052  +76.7115j  33.41       225.4009  +64.2260j  14.00      12.71
   5   226.4783  +69.1361j   7.69       224.6190  +60.9431j   3.37       8.40
   9   225.2664  +63.5549j   5.71       223.9543  +58.4020j   2.63       5.32
  15   224.4854  +60.3945j   3.26       223.5266  +56.8639j   1.60       3.66

served_553 (elevated 10 m monopole, fed in air, over a detached buried radial)
   1    24.0578 -1137.4368j              22.0766 -1082.9735j            54.50
   3    22.0985 -1032.8620j 104.59       21.3876 -1014.8362j  68.14     18.04
   5    21.6990 -1014.9806j  17.89       21.2391 -1003.4142j  11.42     11.58
   9    21.4104 -1002.9942j  11.99       21.1251  -995.8212j   7.59      7.18
```

Both degrees move by ohms per rung and have not settled at any reachable mesh
(bvd1 at ×27 is at the thin-wire floor and degree 2 still moves 3.8 Ω per
rung). The separation shrinks (37 → 5.2, 32 → 3.7, 54 → 7.2), so the two
bases agree about the direction, but no fixed-mesh number on these decks is an
impedance anchor. The 553 gates on them are shape gates (monotone, shrinking)
and are right to be. What a buried-fed or short-elevated bare-wire number may
claim — and whether the drift is the delta-gap feed's known dependence on gap
width, which a lossy medium turns complex — is left for G1-C; nothing here
diagnoses it.

## What was gated, what was not

- Gated (momwire PR, `test_bspline_pair_g1b.py`): the five above-fed anchors,
  |bs1 − bs2| ≤ 1.5 Ω, degree 2 solved (not read from the bank) so an ignored
  `degree` kwarg fails the distinct-bases check. Mutation-checked both ways.
- Not gated: the AK catalog deck's pair (20 s per row at q=32 is past AK's
  per-test budget; the momwire hub_deck row is the same structure class). The
  buried-fed class, as above. Any agreement with razor or NEC-5 underground.
