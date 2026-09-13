# Registered BEFORE running — corpus tool 1.10 re-render (#1442 + #1435)

Written 2026-09-12, before any 1.10 translate or check has been run, so the
predictions cannot be fitted to the results. Source of each: where it comes from.

## 1. Counts (1.9 -> 1.10)

| | 1.9 (measured) | 1.10 (predicted) | why |
|---|---:|---:|---|
| translated | 3,060 | 3,060 | #1442 and #1435 change SPELLING and STATUS, not validity |
| refused | 75 | 75 | untouched |
| invalid | 24 | 24 | #1430's rule is unchanged |
| unreadable | 9 | 9 | untouched |
| collision | — | **1** | `mox10-1al.inp` vs `.nec`; #1435 says the `.nec` wins |
| `written` | 3,067 | **3,066** | the collided `.inp` no longer counts as written |
| deck files on disk | 3,066 | **3,066** | |
| **written == on disk** | no (3,067 vs 3,066) | **yes** | #1435's stated invariant |

## 2. Determinism

Two 1.10 passes byte-identical over all deck files; reports equal once
`_meta.started` is dropped. Basis: 1.9 was, twice, and neither fix introduces a
timestamp or an iteration order.

## 3. The ~930 GN-rewritten decks, now Sommerfeld on both sides

From PR #1441's seeded 120-deck A/B (the only measurement of this that exists):

| | refl-coef (1.9) | Sommerfeld (1.10) predicted |
|---|---:|---:|
| median \|ΔZ\|/max | 0.0994 | **≈ 0.091** |
| > 10 % count (of 118) | 59 | **≈ 55** |
| reactance-sign disagreements | 28 | **28 — unchanged** |

The sign-group prediction is the sharp one: the 120-deck sample moved it by
exactly zero, so if the full population moves it, the sample was unrepresentative
and that is the finding.

## 4. The 8 buried corpus decks

Contact-under-refl-coef should disappear as a refusal, since their ground is now
`GN 2`. Predicted per deck, from #1441's lifted-tree measurement:

- 6 decks: **`GE -1`** (momwire serves the interpolated GE 1 contact only) — that
  gate now fires FIRST, where before refl-coef hid behind it on some.
- with GE lifted, they land on: 4 mixed-radius corner, 3 below/below range,
  1 buried far field. Those are momwire's declared scope, not the ground model.

## 5. Attribution

The momwire column runs on the SAME momwire commit the published page used —
`23d81e5` (v0.53.0) — so every moved row belongs to tool 1.10 alone. Then, on the
CHANGED rows only, a separate labelled column at momwire **v0.54.0** (`260bd91`).

Prediction: **v0.54.0 moves no corpus row.** Basis: PR #1441 measured #1004 as
bit-identical on every catalog buried design and the #956 W terms as reaching only
decks with a crossing junction — and no corpus deck is inside momwire's crossing
scope (all 8 refused). If a row moves, the census's scope conclusion was wrong.

## 6. A correction to carry in, traced (not a prediction — a measured defect of mine)

**`BURIED-CENSUS.md`'s eight-deck table gives the NEC-5 column for the six
`GE -1` decks from decks I MODIFIED, under a heading that reads "NEC-5 Z".**
Reproduced on this box against the decks as translated:

| deck | as translated (`GE -1`) | what the table published (`GE 1`) | apart |
|---|---|---|---:|
| `cebik …/ch-1/1-3.nec` | 47.1250+10.4880j | 41.8150+4.6753j | 16 % |
| `cebik …/ch-3/3-2.nec` | 47.1250+10.4880j | 41.8150+4.6753j | 16 % |
| `cebik …/ch-11/11-4a-nec4.nec` | 50.2260+8.4939j | 37.4470−3.7412j | 35 % |
| `cebik …/lpma3r5-…-buriedradials.nec` | 53.0700−3.5386j | 50.5850−4.1415j | 4.8 % |
| `cebik …/1r5-bc3elendfire-burrad.nec` | 0.0167−0.0258j | 0.0209−0.0304j | ~21 % of a near-zero Z |
| `cebik …/1r8-4el-endfire-burrad.nec` | 0.0035−0.0163j | 0.0035−0.0172j | ~5 % of a near-zero Z |
| both `2lsloper.nec` | 24.3570−19.2450j | identical | — | 

**Where it came from.** Population B needed momwire to get past two of our own
gates, so I built a lifted tree (`GN 0`→`GN 2`, `GE -1`→`GE 1`) and ran NEC-5 on
it too, so both engines would read the same bytes. `popb_table.py` wrote BOTH
columns to `popb-rows.csv` — `R_nec5_published` (as translated) and
`R_nec5_lifted` — and they are both still there and correct. The markdown table
in the write-up collapsed them into one column headed "NEC-5 Z" and filled it
from the LIFTED run. The tool kept the distinction; the prose lost it.

**Why the lifted number is the wrong reference.** `GE -1` is NEC-5's card for a
deck with buried wires — our own `NEC5Engine` writes exactly that
(`ge = "GE -1 0" if self._has_buried_wires else "GE 1 0"`), and AK#1025 records
the other flag as unusable with them. So for these six the deck's own `GE -1` is
the reference, and a 4.8–35 % difference is not a rounding question.

**What this does NOT change.** Population B's conclusion was that momwire refuses
all eight decks at all three commits, and the refusal sentences are momwire's,
measured on the lifted tree deliberately and labelled as such in the prose. The
NEC-5 column was context, not the finding. The re-render carries the `GE -1`
numbers and states which card each column used.

## 7. Population B's momwire column at momwire main — registered before running

momwire main is `553d671` ("Serve GE -1 at a crossing junction; refuse only a free
end in the plane", momwire#1052/U3), with `ed51c31` (#1050/U5, the two-radius
crossing node) below it. Both land after v0.54.0. Registered now, before the
column is run:

Under tool **1.10** the decks carry `GN 2`, so momwire reads them as Sommerfeld and
the refl-coef contact refusal cannot fire. With `553d671` the `GE -1` refusal
cannot fire either. So per deck:

| deck | 1.9 tree + v0.53.0 (measured) | prediction at 1.10 + `553d671` |
|---|---|---|
| `…/ch-1/1-3.nec` | `GE -1` refusal | **mixed radius, or SOLVES** under #1050 |
| `…/ch-3/3-2.nec` | `GE -1` refusal | **mixed radius, or SOLVES** |
| `…/1r5-bc3elendfire-burrad.nec` | `GE -1` refusal | **mixed radius, or SOLVES** |
| `…/1r8-4el-endfire-burrad.nec` | `GE -1` refusal | **mixed radius, or SOLVES** |
| `…/lpma3r5-…-buriedradials.nec` | `GE -1` refusal | **below/below range** (74.7 m vs 63.9 m tabulated) |
| `…/ch-11/11-4a-nec4.nec` | `GE -1` refusal | **buried far field** (its `RP` over a buried deck) |
| `2lsloper.nec` ×2 | refl-coef contact | **below/below range** (135.6 m vs 60.7 m) |

The sharp part: **no deck should still refuse on `GE -1` or on refl-coef contact.**
If one does, either 1.10 did not restore its `GN 2` or #1052 does not reach that
shape, and which of the two is distinguishable from the deck's own cards.

The four mixed-radius decks are the open question — #1050 serves a two-radius
crossing, and these have more than two radii at the node in some cases, so
"solves" and "refuses with a radius-count sentence" are both live. Predicting
either would be a guess; what is registered is that the refusal, if any, names
radii and not the ground.

**Attribution stays as planned**: the census's own momwire column runs at
`23d81e5`, the published page's pointer, so tool 1.10 owns every moved row; the
v0.54.0 (`260bd91`) column on changed rows only answers whether #956/#1004 move
any corpus row; and this `553d671` column is Population B's alone, labelled as
momwire main rather than as the census's momwire.

## 8. The five tokenizer decks under tool 1.11 — registered before running

Derived by hand from each raw card, so every line below is checkable against
1.11's output exactly rather than approximately. `ft` = 0.3048, `uh` = 1e-6.

### `4nec2-models/HFActiveFeed/2lsloper.nec` and `icecube-dbesson/2lsloper.nec`

Raw: `GW<TAB>1<TAB>11<TAB>0<TAB>-68 ft <TAB>X<TAB>Y<TAB>-68 ft<TAB>Z<TAB>#12`
with `SY X=135 ft`, `Y=64 ft`, `Z=26 ft`. Fields are
x1=0, y1=−68 ft, z1=X, x2=Y, y2=−68 ft, z2=Z, rad=#12:

    GW 1 <ns> 0  -20.7264  41.148  19.5072  -20.7264  7.9248  0.001026262694
    GW 2 <ns> 0  +20.7264  41.148  19.5072  +20.7264  7.9248  0.001026262694

**zmin = 7.9248 m.** The deck is an 80 m sloper wholly ABOVE ground, so it is not
a buried deck, not a Population B member, and has no "split" class. 1.10 wrote
z2 = −68 for both wires, which is where the phantom came from.

### `4nec2-models/HFsimple/G5RV.nec` and `icecube-dbesson/g5rv.nec`

Raw: `GW<TAB>1<TAB>31<TAB>0<TAB>-51 ft<TAB>0<TAB>0<TAB>51 ft<TAB>0<TAB>#12`,
i.e. x1=0, y1=−51 ft, z1=0, x2=0, y2=51 ft, z2=0:

    GW 1 <ns> 0  -15.5448  0  0  +15.5448  0  0.001026262694

A 102 ft (31.09 m) horizontal dipole lying in the z = 0 plane, in free space
(`GE 0`, `GN -1`) at 14.2 MHz — which is what a G5RV is. 1.10 wrote a wire from
(0, −51, 0.3048) to (0, 0, 51): a different antenna, and the census's
**88.0900−124.3800j** is that antenna's answer, not this one's.

### `4nec2-models/Objects/Vehicle.nec`

Raw: `LD<TAB>1<TAB>4<TAB>1<TAB>0<TAB>0<TAB>60.7 uh<TAB>0` — an `LD 1` series RLC
on tag 4, so F1 = R, F2 = L, F3 = C:

    LD 1 4 1 <segT> 0  6.07e-05  0

**60.7 µH.** 1.10 wrote `LD 1 4 1 2 0 60.7 1e-06`: a **60.7 henry** inductor and a
1 µF capacitor that is not in the deck at all. Geometry is untouched here (all 36
`GW` cards are the legal 9 fields), so this deck's error is entirely in its
loading, and the census's `1.1045−746.7100j` follows from it.

### What does NOT change

The corpus counts: these five decks still translate, so `translated` 3,059,
`collision` 1, `written` = on disk = 3,066 and `invalid` 24 should all hold at
1.11. If any of them moves, the tokenizer fix changed more than the tokenizer.

### The impedances

Not predicted. The corrected decks are different antennas from the ones the
published census solved, and guessing four impedances would be a guess dressed as
a prediction. What is predicted is the geometry and the loading above, exactly,
and that all five rows differ from the published ones.

## 9. The five decks' CENSUS rows under 1.11 — registered before any census runs

Item 8's geometry predictions are already confirmed against the 1.11 tree (every
number exact). These are the remaining questions — class, buried, and momwire's
status — registered before the momwire column is run:

| deck | buried? | Population B member? | momwire status | was, published |
|---|---|---|---|---|
| `4nec2-models/HFActiveFeed/2lsloper.nec` | **no**, z 7.9248…41.148 | **no** | **ok** | `error` (phantom refl-coef contact) |
| `icecube-dbesson/2lsloper.nec` | **no**, same | **no** | **ok** | `error` (same phantom) |
| `4nec2-models/HFsimple/G5RV.nec` | **no** — z ≡ 0 in FREE SPACE (`GE 0`, `GN -1`), so the plane is not an interface | **no** | **ok** | `ok`, but on a different antenna |
| `icecube-dbesson/g5rv.nec` | **no**, same | **no** | **ok** | same |
| `4nec2-models/Objects/Vehicle.nec` | **no** — geometry was never affected; `GS 0 0 0.0254`, z 16…100 in | **no** | **ok** | `ok`, but with a 60.7 H inductor |

Reasoning, so a wrong one is diagnosable rather than just wrong: `2lsloper` carries
`GN 2` (Sommerfeld, restored by #1442) with every conductor 7.9 m or higher and
nothing at z = 0, so neither the contact gate nor the buried gate can fire, and
its two `EX 0` sources are a shape the census already solves elsewhere. `G5RV` is
one wire, one source, free space. `Vehicle` was scored `ok` by momwire with the
CORRUPTED `LD` (60.7 H and a 1 µF capacitor that is not in the deck), so `LD 1`
is in momwire's dialect and the corrected 60.7 µH cannot take it out of scope.

**Population B therefore drops to 6 decks**, the crossing class, with both
`2lsloper` rows gone — which is the correction #1441's table needs.

One more falsifier, from the symptom side: **no translated `GW` card should now
carry a numeric width other than 9**, except the 28 legal 8-field cards in
`nec2c/YI20_40B.nec` and `…C.nec`, whose raw cards genuinely omit the radius
ahead of a `GC`.
