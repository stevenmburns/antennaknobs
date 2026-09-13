# AK#1469 slice 2 part B: results against PLAN-slice2B.md

- **Commits:** baseline main 5363bbbe5; part B 09f752465; amendment 1 fix (AK#1483) bdeedfdd2.
- **Corpora:** 476 catalog-nec5 decks (`dist/nec5_corpus/catalog-nec5`) and 65 momwire `nec_portal` decks.

## Part B gates (09f752465 against 5363bbbe5)

| gate | result | numbers |
|---|---|---|
| G1 structure | **HIT** | 0 segment totals changed; every `at` is (k − ½)/n or k/n on its piece; 0 PortAtVertex counts changed. The 10 named 1-segment pieces left are authored 1-segment GW wires in the source deck (same count on baseline), not cuts. |
| G2 PyNEC Z | **HIT** | 527 decks solve on both runs; worst relative difference 3.6e-11 (bar 1e-9). The 4 `short_dipole_loaded` decks go from refused to importing (see amendment 1). |
| G3 NEC-2 export | **HIT** | GW counts of the export equal the source deck's on 54/54 portal decks (baseline 44/54). |
| G4 NEC-5 deck | **HIT (advisories); round-trip miss explained** | 0 FeedPlacement advisories on NEC-5 or PyNEC across all decks. The NEC-5 round trip of attachment points missed on 43 decks, the SAME decks on the baseline tree: 35 carry a discrete LD (AK#1483, found here), 8 are TL/NT/pattern portal decks. The count rule was not tallied separately; the point round trip covers placement. |
| G5 momwire Z direction | **HIT, but scoped to #1483** | Skylake, `G5-RESULTS.md`: 19/19 = 100 % closer to the native design (bar 80 %); 4 status changes, all `short_dipole_loaded` error → ok. Every mover carries a discrete LD, so G5 measures #1483, not part B's positioned spelling. Amendment 2 (G9) was registered to measure part B on momwire. |
| G6 AC6LA | **HIT** | `dan2.nec` imports as one 20-segment wire, port at 19/40. PyNEC keeps 20 segments. NEC-5 writes `GW 1 40` with `EX 0 1 19 2`. No advisory. |
| G7 regression | **HIT** at 09f752465 | Fast lane 5092 passed, 125 skipped; ruff check/format clean on src and tests. |

## Amendment 1 gates (bdeedfdd2 against 09f752465)

| gate | result | numbers |
|---|---|---|
| G2' PyNEC Z | **HIT** | 24 decks moved beyond 1e-9, all among the 28 discrete-LD decks. The other 4 are `elt_whip`, skipped as over 3000 segments on both runs. 0 status changes. |
| G4' round trip | **MISS by one** | NEC-5 round-trip misses 43 → **9** (registered 8). The extra one is `dipole_ld_nt_colocated.deck`: it carries an NT as well as the LD. Like the other TL/NT decks, NEC-5 solves it by the multiport-Y route (#1280), so the gate's plain `deck()` call writes a template with no EX card and the re-import finds no source. That is an artefact of the gate, not a defect. The registration counted it with the LD decks. NEC-2 round-trip misses stay at the same 2. |
| G1, G6 | **HIT** | Unchanged from part B. |
| G7 regression | **HIT** at bdeedfdd2 | Fast lane 5100 passed, 125 skipped. |
| G8 direction | **MISS** | Closer to the native design's PyNEC Z on **15/20 = 75 %** (bar 80 %). |

### G8 in detail
- **Identity where the meshes coincide.** After the fix, 8 decks reproduce the catalog design to ≤ 1e-6 relative: t2fd refined ×2, rhombic refined ×2, terminated_longwire default ×2, and short_dipole_loaded refined ×2 (1.2e-5). Before the fix they were off by 0.4 %–60 %.
- **The misses are mesh differences at the loaded wire, not placement.**
  - **multiband.trap_dipole ×4: 4.1 % → 5.3 %.**
    - The design authors each trap on a 1-segment wire, so native PyNEC counts are `[10, 1, 43, 1, 10]`.
    - The NEC-5 export makes that wire 2 segments, to put a knot at the trap.
    - Imported, it is a 2-segment wire with its port at the middle, which PyNEC's centre rule makes 3: `[10, 3, 43, 3, 10]`.
    - Before the fix, the misread gave two 1-segment trap pieces, a spelling that happened to land nearer.
  - **terminated_longwire refined somm13: 21.2 % → 22.3 %.**
    - Native end wires have 5 segments; the import has 7, by the same export-then-centre route.
    - Its free-space twin moved closer: 2.17 % → 2.15 %.
- Reported, not re-gated, as registered.

## Amendment 2 gates: G9, part B on momwire (5363bbbe5 against 9951ee368)

Unregistered context, captured before G9 was registered (`partB-portal-momwire-*.json`, default momwire engine):
- On the 65 nec_portal decks, 52 are identical, 0 change status, and exactly the 10 decks with off-centre attachments move, by 5.9e-5 to 3.6e-3 relative.

| gate | result | numbers |
|---|---|---|
| G9a the spellings converge | **HIT 5/5** | \|Z_before(9) − Z_after(9)\| against \|Z_before(1) − Z_after(1)\|: apex_pq 2.3e-4 vs 2.0e-1 Ω; dipole_load_ld0 9.0e-3 vs 5.8e-1; ld4 7.7e-3 vs 4.6e-1; gp80_seam 1.2e-6 vs 3.0e-3; mininec vertical 1.3e-3 vs 8.2e-2. The cut and the positioned spelling are the same physics in the limit. |
| G9b direction at the authored mesh | **MISS 3/5 = 60 %** (bar 80 %) | Closer to the r = 9 midpoint: ld0 (10.62 vs 10.95 Ω), gp80_seam (2.337 vs 2.338), mininec vertical (0.412 vs 0.490). Further: apex_pq (24.35 vs 24.15), ld4 (0.962 vs 0.670). |

### G9 read
- **The spelling difference is small next to each deck's own mesh error.** At r = 1 it is 0.8 % of the distance to the limit on apex_pq, 5 % on ld0, 0.1 % on gp80_seam, 17 % on the vertical and 68 % on ld4. So the direction test was poorly conditioned on 3 of the 5 geometries, which the registration did not anticipate.
- **On the two geometries where the spelling matters relative to mesh error,** it splits one each way: the vertical is closer, ld4 further.
- **Conclusion.** On momwire, part B's positioned spelling converges to the same answer as the cut, and at the deck's own mesh it is neither better nor worse beyond that mesh's error. Part B is justified by the interface decision (never cut a wire at an attachment) and AC6LA's deck, not by accuracy on this corpus.

## Open
- Found during gating, and the same on main:
  - not a defect: the 7 TL/NT portal decks miss the NEC-5 round trip only because NEC-5 drives such a network one port at a time (#1280), and `deck()` with no source override is that template, with no EX card. The NEC-2 export refuses them by name.
  - the NEC-2 export of `dipole_load_ld4.deck` has no LD card: its reactive `LD 4` load (100 − j75 Ω) is missing (filed #1485). `dipole_nt_all_zero.deck`'s NT is all zero, so its absence from the export is correct.
