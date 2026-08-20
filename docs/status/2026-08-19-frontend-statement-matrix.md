# The frontend statement matrix: everything EZNEC and 4nec2 emit, scored

Workstream-1 deliverable for momwire#456, closing its last open box: the matrix
document, jointly over both dialects, versus momwire#388's refusal-vs-oracle
inventory. Sources: the two emission censuses
(`2026-08-16-eznec-nec5-dialect-capture.md`, momwire#390/#414;
`2026-08-18-4nec2-subengine-capture.md`, momwire#413), momwire's normative
dialect contract (`deck-grammar-nec2.md`), and a static census of the 4nec2
bundled model corpus (`scripts/census_4nec2_bundle.py`, 457 models read
locally).

Every row is one statement — a card, or a variant of a card where variants
score differently — weighted by how much of the 4nec2 bundle emits it, and
scored against what momwire does with it **today**:

| score | meaning |
| --- | --- |
| **serve** | runs, with the physics the frontend meant |
| **refuse-loudly** | refused with a named message; both frontends' error channels are captured and carry refusal text verbatim (momwire#414; the #413 fault-injection table), so a loud refusal reaches the operator with its reason |
| **silently-wrong** | accepted (or discarded) while meaning something the frontend didn't — the zero-tolerance column |
| **resolved** | never reaches the engine; the frontend resolves it before the process boundary, so the refusal can stand |

The bar, restated from #456: every statement either frontend generates is
served or refused loudly in that frontend's own error grammar, with the
deliberate exclusions documented rather than silent.

## Verdict

**4nec2 half: 63.0 % of the 457-model bundle serves today, 28.9 % refuses
loudly, and 8.1 % is silently wrong — from exactly two mechanisms, both cheap
to retire.** The silent set is the MININEC ground idiom (`GD` alongside
`GN 1`, 45 decks — 41 manufactured from `GN 3`, 4 hand-written) and the
missing deck terminator (5 decks). Two hygiene changes take the silent column
to zero immediately; four work clusters then take serve from 64 % to 94 %,
and the only refusal left standing at the bottom of the ladder is the `GN 0`
ground-contact refusal — which is by design (momwire#282), and speaks its own
fix.

**EZNEC half: the seam is unbuilt (workstream 3), so nothing serves today —
but the dialect is only fourteen mnemonics, and the matrix shows most of them
land on physics momwire already has.** The build risk is concentrated in
three identified traps, each of which would be silently wrong (or a hang) if
missed, and each of which has a ready-made gate.

## Census method, and its limits

The corpus is the local mirror of 4nec2's bundled models (457 `.nec` files;
the capture doc's Windows install reads 467 — the delta includes at least
`models/Nec4`, absent here). Each model is translated into the dialect the
engine sees using the resolutions the #413 capture established — `SY`,
comments, gauges and units resolve away; `LD 6` arrives as `LD 1`; `GN 3`
arrives as `GN 1` + `GD`; `EX 6` arrives as `EX 0` + `NT` + a phantom wire —
then scored card-by-card against `deck-grammar-nec2.md`'s refusal tables.
Weights are **models containing the statement**, out of 457.

Three caveats. Classification precedence is refuse-first: `parse()` raises on
the first refused card, so a deck is scored silent only when it otherwise
parses clean — which means serving refusals can *expose* silent decks behind
them (the ladder orders the hygiene gate first for exactly this reason).
Request cards (`FR`/`XQ`/`RP`) are also injected by 4nec2 at run time, so
bundle counts for them are lower bounds on what a drop-in sees. And
statically undecidable refusals (`LD` ranges over 8 segments, doubled loads,
partial-wire `LD 5`) are not counted.

Cross-check against the #413 capture's own tallies: fifteen cards match
exactly (`TL` 45, `GX` 18, `SP` 10, `SM` 9, `GR` 5, `GH` 4, `GC` 3, `PQ` 3,
`WG` 3, `GF` 2, `NT` 1, `CP` 1, `GM` 41, `SC` 15, `NX` 2). Four differ (`SY`
227 vs 174, `EK` 105 vs 82, `GN 3` 41 vs 33, `GS` 150 vs 152) — a corpus-copy
and counting-rule delta, immaterial to any score: `SY` resolves away and `EK`
serves at either count.

## The 4nec2 matrix (nec2 dialect, engine-facing)

### Resolved before the engine — refusals can stand

| statement | source models | note |
| --- | --- | --- |
| `SY` symbols and arithmetic | 227 (49.7 %) | expanded to literals, including inside `FR`/`GH` fields |
| `'` comment lines | 247 (54.0 %) | dropped (momwire's parser would read `'` as a mnemonic error — it never sees one) |
| `LD 6` LC trap | 23 (5.0 %) | recomputed into a standard `LD 1` |
| `#nn` AWG gauges | 25 (5.5 %) | SI radii |
| imperial units (`ft`, `in`) | ~45 (rough regex) | SI floats |
| commas / tabs | all | single spaces |

Half the corpus's scariest surface evaporates at the frontend. What follows
is what actually crosses the process boundary.

### Framing

| statement | models | score | notes |
| --- | --- | --- | --- |
| `CM` | 441 (96.5 %) | serve | printout must echo every card as `***** DATA CARD NO. n …` — renderer obligation, not parse |
| `CE`, incl. trailing text | 457 (100 %) | serve | 4nec2 folds the last `CM` into `CE <text>`; the parser carries the text |
| `EN` | 447 (97.8 %) | serve | |
| **missing terminator** (EOF, no `EN`/`NX`) | 5 (1.1 %) | **silently-wrong** | the dialect discards an unterminated body; NEC's own reader synthesizes `EN` at EOF (the `gs_8d_bb` capture). Fix: match NEC |
| `NX` | 2 (0.4 %) | serve | frame terminator serves; its only bundle use is the `WG`/`GF` handoff, which doesn't (below) |
| `XQ`, incl. injected | 6 source + every run | serve | |

### Geometry

| statement | models | score | notes |
| --- | --- | --- | --- |
| `GW` | 454 (99.3 %) | serve | |
| `GE` — bare (32), `0` (237), `1` (167), `-1` (16), two-field `0 1` (6) | 457 (100 %) | serve | flag recorded; ground physics comes from `GN`; extra fields ignored |
| `GM` | 41 (9.0 %) | serve | |
| `GS`, incl. ranged | 150 (32.8 %) | serve | a third of the corpus — already served |
| `GX` reflection | 18 (3.9 %) | refuse-loudly | **work: momwire#415** — the largest geometry rung |
| `GR` cylindrical | 5 (1.1 %) | refuse-loudly | #415 |
| `GH` helix | 4 (0.9 %) | refuse-loudly | #415 |
| `GC` taper continuation | 3 (0.7 %) | refuse-loudly | #415 — and taper is pillar 1 of the pitch; the `GW` non-positive-radius announcement already refuses by name |
| `GA` arc | 0 | refuse-loudly | documented in 4nec2's card table, unsampled in the bundle; assume required (#413 open work) |
| `SP` / `SM` patches | 10 / 9 (2.2 / 2.0 %) | refuse-loudly | deliberate exclusion per #456 — stays, documented |
| `SC` patch continuation | 15 (3.3 %) | refuse-loudly, **generic** | not on the by-name list — falls to `unrecognised NEC card 'SC'`. Needs a named refusal: it accompanies every `SP`/`SM` deck, and the exclusion should speak |

### Ground

| statement | models | score | notes |
| --- | --- | --- | --- |
| `GN -1` free space | 92 (20.1 %) | serve | |
| `GN 1` perfect | 62 emitted (13.6 %) | serve | 21 written + 41 manufactured from `GN 3` |
| `GN 2` Sommerfeld | 158 (34.6 %) | serve | **the single most common ground in the bundle is the one momwire gates against the licensed binary** — contact included |
| `GN 0` refl-coef, clear of ground | 18 (3.9 %) | serve | |
| `GN 0` refl-coef, geometry touching z = 0 | 9 (2.0 %) | refuse-loudly, **by design** | momwire#282: NEC-2 itself is wildly wrong here; the message names the fix (`GN 2`). The one refusal that stays at the bottom of the ladder |
| `GN 0`/`GN 2` with `NRADL` radial screen | 2 (0.4 %) | refuse-loudly | #388 priority 4; workstream-2 decision (no oracle on the NEC-5 dialect either — #444's landmine) |
| **`GN 3` → `GN 1` + `GD` (manufactured), and hand-written `GD` + `GN 1`** | 45 (9.8 %) | **silently-wrong** | the flagship silent row — mechanism below |
| `GD` as a genuine NEC-2 cliff | 0 | serve | momwire reads it, `RP 2`/`3` use it; the bundle never does |

### Excitation

| statement | models | score | notes |
| --- | --- | --- | --- |
| `EX 0` voltage | 447 emitted (97.8 %) | serve | 395 written + 52 manufactured |
| `EX 6` current → `EX 0` + `NT` + phantom wire | 52 (11.4 %) | refuse-loudly (via `NT`) | serving `NT` covers it, but the gates must pin the **manufactured form** (#456): phantom 1-segment wire parked at z = its own tag, driven and an `NT` endpoint — fails `_anchor_wires`' guards (antennaknobs#427, #944) |
| `EX 1` plane wave | 1 (0.2 %) | refuse-loudly | #388 priority 1 (`EX 1–3`) |
| `EX 5` current-slope | 1 (0.2 %) | refuse-loudly | #388 row |
| `EX 2/3/4` | 0 | refuse-loudly | #388 rows; `EX 4` is NEC-5-native (the twin uses it) |

### Loads

| statement | models | score | notes |
| --- | --- | --- | --- |
| `LD 5` conductivity | 157 (34.4 %) | serve | whole-wire rule; partial ranges refuse (not statically counted) |
| `LD 0` series RLC | 46 (10.1 %) | serve | ≤ 8-segment range rule applies |
| `LD 1` parallel RLC | 33 emitted (7.2 %) | serve | 10 written + 23 from `LD 6` |
| `LD 4` fixed Z | 24 (5.3 %) | serve | |
| `LD 2` per-metre | 1 (0.2 %) | refuse-loudly | #388 row |
| `LD 7` wire coating | 3 (0.7 %) | refuse-loudly *if it arrives* | 4nec2 extension; translation unsampled (#413 open work). If resolved like `LD 6`, it becomes a non-row; if passed through, the named refusal already exists |

### Networks

| statement | models | score | notes |
| --- | --- | --- | --- |
| `TL`, incl. negative-Z₀ crossed lines | 45 (9.8 %) | refuse-loudly | **required** — the #390 verdict, now weighted: second-largest single rung |
| `NT` | 53 emitted (11.6 %) | refuse-loudly | 1 hand-written (with the `1.E10` open-pin idiom EZNEC also uses) + 52 manufactured from `EX 6` — the **largest** rung. momwire's NT oracle exists (#65's reducer); the SimNEC dialect refuses networks by spec, so this is the workstream-2 serve-path decision |

### Frequency and requests

| statement | models | score | notes |
| --- | --- | --- | --- |
| `FR` single | 432 (94.5 %) | serve | |
| `FR` multi (`NFRQ` > 1) | 20 source + every UI sweep | serve | **the batching prize**: a 30-point sweep is one launch, and the dialect's frequency groups run the whole list natively — the two-phase sweep deck (single-point + `XQ`, then 30-point `FR` + `RP`) is exactly the execute-group state machine |
| `RP 0` | 52 (11.4 %) | serve | `XNDA` ignored by parse; the printout renderer must reproduce the format it selects |
| `RP 1` surface wave | 1 (0.2 %) | refuse-loudly | #388 priority 3 |
| `RP 2`/`3` cliff | 0 | serve | |
| `RP 4–6` screens | 0 | refuse-loudly | #388 row |
| `NE` / `NH` | 5 / 1 (1.1 / 0.2 %) | serve* | rectangular, free-space/PEC; over finite ground refuses — #388's near-field row |
| `PT`, incl. `PT -1` | 12 (2.6 %) | serve | |
| `PQ`, emitted as `PQ -1` | 3 (0.7 %) | refuse-loudly | **wrongly so**: `PQ -1` *suppresses* the charge print, and momwire prints no charge report — refusing a suppression card kills runnable decks. Cheap serve: accept `PQ -1`/`PQ 0` as print control, refuse only a positive charge-print *request* if ever seen |
| `EK` | 105 (23.0 %) | serve | per-group, NEC-exact `I1 == -1` test, honoured not advisory |
| `KH` / `PL` / `ZO` / `MP` / `IS` | 0 | refuse (`KH`/`PL`/`ZO`) / serve (`MP`/`IS`) | absent from the bundle |

### The frequency-weighted ladder

Model-level classification (a deck scores by its worst statement), with each
work cluster added in the order the weights argue for:

| step | serve | refuse | silent |
| --- | --- | --- | --- |
| today | 288 (63.0 %) | 132 | 37 |
| hygiene: EOF-as-`EN` + the `GD`-with-`GN 1` gate | 293 (64.1 %) | 164 | **0** |
| + serve `NT`/`TL` | 357 (78.1 %) | 100 | 0 |
| + geometry transforms (`GX` `GR` `GH` `GC` `GA`) | 373 (81.6 %) | 84 | 0 |
| + MININEC-type ground (the `GN 3`/`GD` decision) | 418 (91.5 %) | 39 | 0 |
| + long tail (`PQ`, `CP`, `WG`/`GF`, `LD 2`/`7`, `RP 1`, `EX 1`/`5`, `NRADL`) | 431 (94.3 %) | 26 | 0 |
| (+ patches — excluded by #456) | 448 (98.0 %) | 9 | 0 |

The 9 at the bottom are the `GN 0` contact decks: refused by design, loudly,
with the fix in the message. The hygiene step must come **first**: serving
`NT`/`TL` before the `GD` gate would *grow* the silent column from 32 to 44
decks, because a dozen MININEC-ground decks currently hide behind their own
network refusals.

### The two silent mechanisms

**1. The MININEC ground idiom — `GD` alongside `GN 1` (45 decks, 9.8 %).**
4nec2 rewrites its `GN 3` "MiniNec ground" into `GN 1` + `GD ... ε σ`, and
four bundled models hand-write the same pair. momwire parses both cards —
`GD` is not on any refusal list — and answers **perfect-ground physics**: the
`GD` record is read as a cliff that only `RP 2`/`3` ever consult, and the
bundle emits `RP 0`. The wrongness is bounded by the EZNEC study's twin
measurement of the same substitution: 34 % in R on a ground-contacting
vertical. The corpus makes the gate signature clean: **zero** bundled decks
pair `GD` with `GN 1` as a genuine cliff, so "`GD` in a `GN 1` deck" can
refuse loudly, by name, with no false positives — until workstream 2 decides
whether to implement a MININEC-type ground (for which the two captures supply
a ready-made two-host oracle; #151/#282/#291/#292).

**2. The missing terminator (5 decks, 1.1 %).** The dialect discards a deck
body left unterminated at end of input; NEC's own reader synthesizes `EN` at
EOF and runs it. Five bundled models end at their last request card. The host
would get an empty printout and blame the engine ("Nec error ? Check output")
with nothing naming the cause. Fix: match NEC — treat EOF as `EN`.

## The EZNEC matrix (NEC-5 dialect — workstream 3, seam unbuilt)

No drop-in exists at this seam, so "today" is uniformly *nothing runs*; the
score column here is the **planned disposition** — what the front-end being
priced in #456 workstream 3 does with each statement, given what momwire and
antennaknobs already have. Weights are the capture study's own counts (31
captures over 19 of the 52 bundled models; the other 33 are the study's named
open work).

| statement | evidence | planned score | notes |
| --- | --- | --- | --- |
| `GW` | every deck | serve | |
| `GE g,-1` (two-field) | every deck | serve | second field `-1` throughout |
| `GN -1` free space | bare-wires decks | serve | |
| `GN 1` perfect (bare) | ground cycle 0019–0021 | serve | capture leftover: sparsely sampled |
| `GN 0,…,ε,σ` — High Accuracy (Sommerfeld) | `DipTL1`, `Vert1` cycle | serve | **pillar 2**: contact gated two-bar against the licensed binary; the 1.2–4.4 Ω lossy-soil envelope is named, not hidden |
| `GD …,ε,σ` — MININEC type | `Vert1`, `4sqtl`, `Cardioid` | **refuse-loudly until built** | the same 8-field payload as `GN 0` under the same printout banner, **34 % apart in R** — not NEC-2's `GD`, and never to be aliased onto one finite-ground model. Same workstream-2 decision as 4nec2's `GN 3`, same oracle pair |
| `EX 4` current source | 38 of 40 `EX` cards | work, tractable | the portal drives voltage only, but `NEC5Engine` already drives native `EX 4`; single-source current drive is a readout transform, multi-source phased drive (four-square: 0/−90/−90/−180 at √2 A) is a constrained port solve — no network needed |
| `EX 0` voltage | 2 of 40 | serve | |
| signed node addressing on `EX`/`LD`/`TL`/`NT` (`-1`/`+k`, favored-wire tag) | every connection card | **silent-trap** — gate required | the tag carries physics, not just addressing: canonicalizing `2,3` ≡ `3,-1` to one node answers 114.47 Ω where W7EL publishes 195.3 Ω (config C). `DeckModel.node_gaps` + `PortAtVertex` are the seam; **the W7EL oracle triple is the gate fixture** |
| `LD 4` fixed Z | 67 of 67 `LD` cards | serve | the only load type EZNEC emits; always single-point |
| `LD 4` `1.E10` pins | every virtual wire | serve | mechanically ordinary loads |
| `TL` — lengths pre-resolved to metres; crossed (−Z₀); stubs via `1.E10` shunt | `4sqtl` ×6, Cardioid ×2, LPDA | work: network path | antennaknobs already maps all three forms (`nec_import.NecTL`); the #456 layering decision (option 3: seam in antennaknobs, momwire stays antenna-only) |
| `NT` — reciprocal Y-triples; junction loads; L-networks/transformers/series C | Cardioid, connection test, L-network deck | work: network path | **junction loads emit `NT`**, so ordinary loaded models need the network solve, not just phased arrays |
| virtual-wire feed idiom (100 λ out, λ/10000 radius, 4-segment, driven + pinned + `NT` endpoint) | every `TL`/`NT` deck | **silent-trap → hang** | *the feed system itself*; defeats `_anchor_wires` on all four guards (#427) and lands on momwire#157's assembly hang — not a wrong answer, a hang. antennaknobs#157 |
| `FR` single point | every launch | serve | one process per frequency point, deck regenerated per point — nothing batches; the warm-server / cross-deck-cache pattern is workstream 3's economics item |
| `PQ 0` | every deck | serve (accept) | |
| `RP 0` 2-D / 3-D | pattern displays | serve | `XNDA` 1000 vs **1001** select printout formats the renderer must reproduce |
| `XQ 0` | Src Dat | serve | |
| `NE` at defaults | capture 0022 | serve* | rectangular E-field; over finite ground is #388's near-field row — refuse-loudly until served |
| `EN` | every deck | serve | |
| `CM` launch-stamp echo | every printout | **obligation** | echo the deck's `CM` block or every printout is rejected as stale and no message survives (#414's error convention — done as design, three lines of formatting discipline) |

Not emitted, per the capture: radial-screen grounds (**EZNEC models radials
as `GW` wires** — `Elevrad` — so #388's priority-4 pressure is 4nec2-side and
real-world-deck-side only), `LD 0/1/2/5`, `NH`, `EX 1–3`. Unsampled: the
remaining 33 bundled models, perfect/MININEC ground variants beyond the one
cycle, `SOMMPD.NEX` statefulness semantics (#456 leftovers).

## Cross-cutting rows

**Error grammar — done on both sides.** Both frontends ignore the exit
status entirely and read only the printout. EZNEC requires the `CM` echo,
then surfaces a `NEC ERROR` line in a viewer; 4nec2 surfaces a single
`NEC ERROR` line verbatim in a popup with no framing ritual at all, and never
redisplays stale results. Refusals can speak at both seams, so every
"refuse-loudly" score in this matrix is *deliverable*, not aspirational.

**Sweep economics — opposite ends.** 4nec2 batches (30 points, one launch:
momwire's swept machinery finally amortizes — the strongest performance
argument of any seam) and carries ~400 ms/iteration of its own optimiser
overhead, so drop-in startup cost is immaterial. EZNEC launches once per
point with the whole deck regenerated and its only cross-launch state
(`SOMMPD.NEX`) invalidated by the very thing a sweep varies — the
warm-server pattern is what makes that seam usable.

**The NEC-4 slot** (`CW` `IS` `JN` `LE` `LH` `PS` `UM` `VC`, `GD 2`,
`GE 0 1`) is deliberately out of this matrix: same protocol, different
physics claim, separate go/no-go per #413/#456.

## What workstream 1 hands workstream 2

In order, by weight and by what each unlocks:

1. **Hygiene, immediately** (silent → 0): EOF-as-`EN`; a named refusal for
   `GD`-with-`GN 1` (no false positives corpus-wide); a named refusal for
   `SC`; serve `PQ -1`/`PQ 0` as print control. All four are small dialect
   PRs against `deck-grammar-nec2.md` + parser.
2. **The `NT`/`TL` decision** (+64 decks, and the EZNEC seam's blocking
   issue): the workstream-2 scope call the capture already framed — momwire's
   #65 reducer vs the antennaknobs-layering option 3.
3. **Geometry transforms** (momwire#415: `GX` first at 18 decks, then
   `GR`/`GH`/`GC`/`GA`) — honest NEC surface, pre-expandable to `GW`+`GM`/`GS`.
4. **MININEC-type ground** (+45 decks, both frontends, two-host oracle in
   hand) — decide implement vs permanent loud refusal, alongside the
   `NRADL` radial-screen decision (#388 P4).
5. **Long tail** as listed; patches stay excluded and documented; `GN 0`
   contact stays refused by design.

Regenerate the numbers with:

```
python scripts/census_4nec2_bundle.py [--root <bundle>] [--json out.json]
```
