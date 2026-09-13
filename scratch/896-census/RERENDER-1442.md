# Re-rendering the #896 census on corpus tool 1.11 — the record

The published page was rendered on corpus tool **1.9**. Three fixes have landed
since, all of them found by the previous re-render or by the review of it:

- **#1442** — `GN 2` passes through as `GN 2`. Under 1.9 it was rewritten to
  `GN 0` on 1,104 of 1,105 decks, and the two engines read `GN 0` differently:
  NEC-5 has no reflection-coefficient option so there it IS Sommerfeld, while
  momwire's portal honours the NEC-2 meaning. The census was comparing two ground
  MODELS on those decks.
- **#1435** — a `collision` status. `foo.inp` and `foo.nec` used to land on the
  same output path with the second write silently winning; the `.nec` source now
  wins by rule and the `.inp` is reported, so `written` equals the files on disk.
- **the tab-field tokenizer** (tool 1.11, PR #1463) — a number and its unit in
  one TAB field (`-68 ft`, `60.7 uh`) is one value, in both `nec_import` and the
  corpus tool.

**Every prediction below was registered in writing before the run that tested
it**, in `RERENDER-1442-PREDICTIONS.md`. One of them is wrong, and it is the one
that was flagged in advance as the sharp one.

## Scoreboard

| item | registered | measured | |
|---|---|---|---|
| 1. counts | `written` == on disk, one `collision` | 3,066 == 3,066, collision 1 | **hit** |
| 1b. `translated` | 3,060 | **3,059** | **MISS** |
| 2. determinism | trees byte-identical, reports equal bar `started` | both, and 0 of 3,066 census rows differ | **hit** |
| 3. GN A/B median | ≈ 0.091 from a 0.0994 base | 0.1161 → **0.0982** | hit in direction and size |
| 3. GN A/B > 10 % | 59 → ≈ 55 (−7 %) | 470 → **440** (−6.4 %) | **hit** |
| 3. reactance-sign count | **unchanged** | 198 → **203** | **MISS** |
| 4/7. Population B | 6 decks; no `GE -1`, no refl-coef; per-deck limits | exactly that | **hit** |
| 5. momwire v0.54.0 on changed rows | moves nothing | 0 statuses, 0 impedances of 873 | **hit** |
| 8. the five decks' geometry | exact card values | every digit | **hit** |
| 9. their class and status | not buried, momwire `ok` | 5/5 | **hit** |

### The two misses

**`translated` 3,059, not 3,060.** The collided `.inp` has to come *out* of
`translated` to become a `collision`. Obvious afterwards, which is the reason for
writing predictions down first.

**The reactance-sign count moved: 198 → 203 of 887.** This was registered as the
falsifier — "if the full population moves it, the sample was unrepresentative and
that is the finding" — so it is reported as a failure rather than folded in. The
honest reading is narrower than "unrepresentative": the true rate is 5 in 887,
**0.56 %**, so a 120-deck sample expects 0.68 flips and seeing zero is about as
likely as not. The sample was **underpowered**, not skewed, and a 120-deck sample
could never have resolved a half-percent effect. The direction is also worth
stating plainly: restoring the correct ground model made the sign group slightly
**worse**, by five decks.

## 1. Counts (1.9 → 1.11)

| | 1.9 | 1.10 | **1.11** |
|---|---:|---:|---:|
| source files seen | 3,168 | 3,168 | 3,168 |
| translated | 3,060 | 3,059 | **3,059** |
| refused | 75 | 75 | 75 |
| invalid | 24 | 24 | 24 |
| unreadable | 9 | 9 | 9 |
| **collision** | — | 1 | **1** |
| **`written`** | 3,067 | 3,066 | **3,066** |
| **deck files on disk** | 3,066 | 3,066 | **3,066** |
| **`written` == on disk** | no | yes | **yes** |

The collision row names its rule rather than acting silently:
`mox10-1al.inp` "translates to the same output path as … `mox10-1al.nec`, which
is kept (a `.nec` source over a same-named `.inp`; otherwise the first in sorted
order)".

### The 1.10 → 1.11 tripwires

Run before anything downstream, because the tokenizer fix should touch five decks
and nothing else:

- **status counts identical** to the 1.10 tree on every category.
- **exactly 5 decks differ**, ignoring the version comment: `2lsloper` in two
  collections, `G5RV.nec`, `g5rv.nec`, `Vehicle.nec`. No deck exists in one tree
  and not the other.
- **no translated `GW` carries a numeric width other than 9** anywhere in the
  corpus, except the 28 legal 8-field cards in `nec2c/YI20_40B.nec` and `…C.nec`,
  whose raw cards genuinely omit the radius ahead of a `GC`.

## 2. Determinism

Two 1.11 translate passes: trees byte-identical, reports equal once
`_meta.started` is dropped. Two momwire census passes over the same tree, 2,159 s
and 2,160 s: **0 of 3,066 rows** differ on anything but `wall_s`.

## 3. The ground spelling, on the whole population

1,104 decks had their ground rewritten `GN 2` → `GN 0` under 1.9; 887 of them are
comparable on both renders. On exactly that population:

| momwire ground model | median | p75 | p90 | > 1 % | > 10 % |
|---|---:|---:|---:|---:|---:|
| published — refl-coef (`GN 0`) | 0.1161 | 0.2797 | 0.7866 | 828 | 470 |
| this page — Sommerfeld (`GN 2`) | **0.0982** | 0.2480 | 0.7866 | 822 | **440** |

Sommerfeld is closer to NEC-5 on **437 of 887** decks — a coin flip, as the
120-deck sample also found (63 of 118). Reactance-sign disagreements **198 → 203**.

So the defect was real and the correction is real, and it is still not the
explanation for the census's headline disagreement: the median moves 15 %
relatively, half the decks get worse, and the sign group grows.

## 4 and 7. Population B

Re-selected on the 1.11 tree: **6 decks, all `crossing`.** Both `2lsloper` rows
are gone — they were never buried. The momwire column runs at momwire main
`553d671` (momwire#1052/U3, "serve `GE -1` at a crossing junction"), with
`ed51c31` (#1050/U5, the two-radius crossing node) below it.

| deck | momwire `23d81e5` | momwire `553d671` | NEC-5, deck's own `GE -1` |
|---|---|---|---|
| `cebik …/ch-1/1-3.nec` | `GE -1` | **mixed radius** | 47.1250+10.4880j |
| `cebik …/ch-3/3-2.nec` | `GE -1` | **mixed radius** | 47.1250+10.4880j |
| `cebik …/1r5-bc3elendfire-burrad.nec` | `GE -1` | **mixed radius** | 0.0167−0.0258j |
| `cebik …/1r8-4el-endfire-burrad.nec` | `GE -1` | **mixed radius** | 0.0035−0.0163j |
| `cebik …/lpma3r5-…-buriedradials.nec` | `GE -1` | **below/below range** | 53.0700−3.5386j |
| `cebik …/ch-11/11-4a-nec4.nec` | `GE -1` | **buried far field** | 50.2260+8.4939j |

**No deck refuses on `GE -1` or on refl-coef contact any more**, which was the
registered sharp claim: all six did at `23d81e5`, none does at `553d671`. Every
remaining refusal is a declared scope limit, and the mixed-radius sentence is now
specific about which side — "radii that differ within the below wires" on the two
tutorial decks, "within the above wires" on the two phased arrays — so #1050's
two-radius rule is reached and these decks sit past it.

The NEC-5 column is each deck's **own `GE -1`**, never a lifted variant. Where a
lifted print is quoted at all it gets its own labelled column (see
`BURIED-CENSUS.md`).

## 5. Attribution

The census's own momwire column runs at `23d81e5` — the published page's pointer
— so every row that moved belongs to tool 1.11 alone. Then, on the **873 decks
whose momwire row changed**, a separate column at momwire **v0.54.0** (`260bd91`,
the crossing kernel's W terms and the cross-block quadrature):

**0 statuses move. 0 impedances move.**

That is what PR #1441 predicted from its scope conclusion — #1004 was bit-identical
on every catalog buried design, and the W terms reach only decks with a crossing
junction, of which the corpus has none inside momwire's scope. The prediction was
registered before this column ran.

## 8 and 9. The five tokenizer decks

Predicted by hand from each raw card, before 1.11 was on this box:

| deck | predicted | 1.11 wrote |
|---|---|---|
| `2lsloper` ×2 | `GW 1 <ns> 0 -20.7264 41.148 19.5072 -20.7264 7.9248 0.001026262694` | exactly that, `<ns>` = 12 |
| `G5RV` / `g5rv` | `GW 1 <ns> 0 -15.5448 0 0 15.5448 0 0.001026262694` | exactly that, `<ns>` = 32 |
| `Vehicle` | `LD 1 4 1 <segT> 0 6.07e-05 0` | exactly that, `<segT>` = 2 |

And their rows:

| deck | momwire was | momwire now | NEC-5 now |
|---|---|---|---|
| `4nec2-models/HFActiveFeed/2lsloper.nec` | `error` (phantom refl-coef contact) | **ok** | 58.7920−42.2630j |
| `icecube-dbesson/2lsloper.nec` | `error` (same phantom) | **ok** | 58.7920−42.2630j |
| `4nec2-models/HFsimple/G5RV.nec` | `ok`, on a different antenna | **ok** | 97.6950−73.0460j |
| `icecube-dbesson/g5rv.nec` | `ok`, same | **ok** | 97.6950−73.0460j |
| `4nec2-models/Objects/Vehicle.nec` | `ok`, with a 60.7 **H** inductor | **ok** | 1.1045+1999.3000j |

`2lsloper` runs **z 7.9248 … 41.148 m**: an 80 m sloper above ground. `Vehicle`'s
geometry was never affected — all 36 `GW` cards were the legal 9 fields — so its
error was entirely in its loading, and its resistance is unchanged at 1.1045 Ω
while its reactance moves from −746.71 to +1999.3.

## Provenance

- **NEC-5**: `nec5cl-x13`, sha256 `2068ae67a7fb1225…`, the binary the published
  page's own metadata names.
- **momwire**: `23d81e5` (v0.53.0, the published pointer) for the census column;
  `260bd91` (v0.54.0) for the changed-rows column; `553d671` (momwire main, after
  #1052 and #1050) for Population B. Three checkouts, one set of compiled
  accelerators — `git diff` over `*.cpp *.hpp *.h setup.py` is empty from
  `23d81e5` to each.
- The antennaknobs submodule pointer is untouched.

## Reproducing

```
python scratch/896-census/rerender_1442.sh
```
