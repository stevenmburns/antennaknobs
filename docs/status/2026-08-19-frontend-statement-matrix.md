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

> **Superseded in part — see the [2026-08-19 evening
> addendum](#addendum-2026-08-19-evening-workstream-2-phase-c-landed--re-baselined).**
> Workstream 2 phase C and the hygiene wave landed the same day this was
> written. Today's measured serve is **358 (78.3 %)** with the silent column
> at **zero**; rows falsified by those waves are corrected in place below and
> marked *(re-baselined)*.

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
| **missing terminator** (EOF, no `EN`/`NX`) | 5 (1.1 %) | serve *(re-baselined)* | was silently-wrong: the dialect discarded an unterminated body. The hygiene wave matched NEC, which synthesizes `EN` at EOF (the `gs_8d_bb` capture) |
| `NX` | 2 (0.4 %) | serve | frame terminator serves; its only bundle use is the `WG`/`GF` handoff, which doesn't (below) |
| `XQ`, incl. injected | 6 source + every run | serve | |

### Geometry

| statement | models | score | notes |
| --- | --- | --- | --- |
| `GW` | 454 (99.3 %) | serve | |
| `GE` — bare (32), `0` (237), `1` (167), `-1` (16), two-field `0 1` (6) | 457 (100 %) | serve | flag recorded; ground physics comes from `GN`; extra fields ignored |
| `GM` | 41 (9.0 %) | serve | |
| `GS`, incl. ranged | 150 (32.8 %) | serve | a third of the corpus — already served |
| `GX` reflection | 18 (3.9 %) | serve *(re-baselined)* | momwire#415 landed; the out-of-cell `LD` drop refuses by name (costs `1MHz_tower`) |
| `GR` cylindrical | 5 (1.1 %) | serve *(re-baselined)* | #415 |
| `GH` helix | 4 (0.9 %) | refuse-loudly | #415 |
| `GC` taper continuation | 3 (0.7 %) | refuse-loudly | #415 — and taper is pillar 1 of the pitch; the `GW` non-positive-radius announcement already refuses by name |
| `GA` arc | 0 | refuse-loudly | documented in 4nec2's card table, unsampled in the bundle; assume required (#413 open work) |
| `SP` / `SM` patches | 10 / 9 (2.2 / 2.0 %) | refuse-loudly | deliberate exclusion per #456 — stays, documented |
| `SC` patch continuation | 15 (3.3 %) | refuse-loudly, **by name** *(re-baselined)* | was the generic `unrecognised NEC card 'SC'`; the hygiene wave gave it a named refusal, so the deliberate patch exclusion now speaks |

### Ground

| statement | models | score | notes |
| --- | --- | --- | --- |
| `GN -1` free space | 92 (20.1 %) | serve | |
| `GN 1` perfect | 62 emitted (13.6 %) | serve | 21 written + 41 manufactured from `GN 3` |
| `GN 2` Sommerfeld | 158 (34.6 %) | serve | **the single most common ground in the bundle is the one momwire gates against the licensed binary** — contact included |
| `GN 0` refl-coef, clear of ground | 18 (3.9 %) | serve | |
| `GN 0` refl-coef, geometry touching z = 0 | 9 (2.0 %) | refuse-loudly, **by design** | momwire#282: NEC-2 itself is wildly wrong here; the message names the fix (`GN 2`). The one refusal that stays at the bottom of the ladder |
| `GN 0`/`GN 2` with `NRADL` radial screen | 2 (0.4 %) | refuse-loudly | #388 priority 4; workstream-2 decision (no oracle on the NEC-5 dialect either — #444's landmine) |
| **`GN 3` → `GN 1` + `GD` (manufactured), and hand-written `GD` + `GN 1`** | 45 (9.8 %) | refuse-loudly *(re-baselined)* | was the flagship silent row (mechanism below). The hygiene wave refuses the idiom by name, narrowed exactly as wide as the silence: an all-zero `EPSR2`/`SIG2` pair is no medium and does not trip it, and an `RP 2`/`RP 3` cliff request *reads* the record and is answered |
| `GD` as a genuine NEC-2 cliff | 0 | serve | momwire reads it, `RP 2`/`3` use it; the bundle never does |

### Excitation

| statement | models | score | notes |
| --- | --- | --- | --- |
| `EX 0` voltage | 447 emitted (97.8 %) | serve | 395 written + 52 manufactured |
| `EX 6` current → `EX 0` + `NT` + phantom wire | 52 (11.4 %) | serve *(re-baselined)* | phase C serves `NT`; the manufactured form is pinned end-to-end by momwire's `dipole_ex6_gyrator` fixture and by this census's verbatim constants. The phantom 1-segment wire parked at z = its own tag, driven and an `NT` endpoint, still fails `_anchor_wires`' guards (antennaknobs#427, #944) — an antennaknobs item, not a dialect one |
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
| `TL`, incl. negative-Z₀ crossed lines | 45 (9.8 %) | **serve** *(re-baselined)* | momwire#482 phase C. Crossed lines keep sign and magnitude apart; `F2 = 0` is the segment-midpoint distance, not a zero-length line; a zero `Z0` refuses (NEC aborts while reading) |
| `NT` | 53 emitted (11.6 %) | **serve** *(re-baselined)* | momwire#482 phase C. 1 hand-written (with the `1.E10` open-pin idiom EZNEC also uses) + 52 manufactured from `EX 6`. An all-zero `NT` is **not** a no-op — it open-circuits both addressed segments, and antennaknobs' importer skipping it is a divergence to fix |
| network **contiguity** — a non-transparent card between two network cards | 11 (2.4 %) *(modelled)* | refuse-loudly, **by design** | new row: NEC silently destroys every earlier `TL`/`NT`. All 11 pair a hand-written `TL` with an `NT` manufactured from `EX 6`; the emission order this rests on is captured once and the pairing is uncaptured — see the addendum |
| network addressing — segment below 1, or `TL` `Z0 = 0` | 0 | refuse-loudly | measured zero corpus-wide, matching phase C's own scan |

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
| `PQ`, emitted as `PQ -1` | 3 (0.7 %) | serve *(re-baselined)* | the hygiene wave made `PQ` a by-value gate: `PQ -1` *suppresses* the charge report and serves, `PQ >= 0` *requests* one and refuses. All three bundle cards are `PQ -1`, so `PQ` costs nothing |
| `EK` | 105 (23.0 %) | serve | per-group, NEC-exact `I1 == -1` test, honoured not advisory |
| `KH` / `PL` / `ZO` / `MP` / `IS` | 0 | refuse (`KH`/`PL`/`ZO`) / serve (`MP`/`IS`) | absent from the bundle |
| **no `EX` card anywhere** | 8 (1.8 %) | refuse-loudly, **by design** | new row: `Objects/`-family display models and the two NGF writers. Nothing drives the structure and NEC solves nothing either — `deck has no EX card` |

### The frequency-weighted ladder

Model-level classification (a deck scores by its worst statement), with each
work cluster added in the order the weights argue for. **The first three rungs
have since landed — see the [re-baselined
ladder](#the-re-baselined-ladder-measured-457-models) in the addendum for
today's numbers; this table is the morning snapshot that argued for the
order.**

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

### The two silent mechanisms — both retired the same day

**Both were fixed by the hygiene wave; the silent column is now zero at every
rung of the ladder.** The analysis is kept because it is what argued for the
order, and because mechanism 1's substitution is still an open *physics*
decision (implement MININEC-type ground, or keep the loud refusal) rather than
a silence.

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

1. ~~**Hygiene, immediately** (silent → 0): EOF-as-`EN`; a named refusal for
   `GD`-with-`GN 1` (no false positives corpus-wide); a named refusal for
   `SC`; serve `PQ -1`/`PQ 0` as print control.~~ **DONE** — all four landed;
   silent is 0.
2. ~~**The `NT`/`TL` decision** (+64 decks, and the EZNEC seam's blocking
   issue).~~ **DONE** — momwire#482 phase C serves both, in momwire.
3. **Geometry transforms** — `GX`/`GR` **DONE** (momwire#415, +23 decks);
   `GH`/`GC`/`GA` remain, 6 decks between them.
4. **MININEC-type ground** (+45 decks, both frontends, two-host oracle in
   hand) — decide implement vs permanent loud refusal, alongside the
   `NRADL` radial-screen decision (#388 P4).
5. **Long tail** as listed; patches stay excluded and documented; `GN 0`
   contact stays refused by design.

Regenerate the numbers with:

```
python scripts/census_4nec2_bundle.py [--root <bundle>] [--json out.json]
```

## Addendum, 2026-08-19 (evening): workstream 2 phase C landed — re-baselined

Everything above was written against the dialect as it stood that morning.
Three waves have landed since, and the census that backs this document has
been re-baselined against the live one (`scripts/census_4nec2_bundle.py`,
momwire#456 ws2 phase C). **The rows and the ladder in the body of this
document are corrected in place where the phase falsified them; this section
carries the new numbers and what they rest on.**

### What landed

**Phase C — `TL` and `NT` serve (momwire#482, sub-PRs #478/#481).** The
largest and second-largest rungs of the ladder above, retired together. Four
semantics were measured on the oracle rather than reasoned about, and each is
now normative in `deck-grammar-nec2.md`:

- **Networks are exempt from the symmetric-cell rule**
  ([`#networks-under-a-symmetric-cell`]). A `GX`/`GR` cell replicates what
  enters the *matrix*, and NEC's network solve is a composition on top of the
  solved matrix — the same argument that already exempts `EX`. The probe
  triple under `tests/fixtures/nec2_symmetry/` puts an `NT` under a live
  `GX 2 100`: the oracle's answer is byte-identical to the hand-expanded deck
  carrying **one** card as written, and differs from the deck carrying one
  card per copy. Endpoints resolve against the fully generated structure,
  image tags and all, and the card attaches exactly once.
- **The contiguity destroy pattern is refused by name**
  ([`#network-contiguity`]). NEC resets its network list on reading a network
  card whose predecessor was not one, so an interposed card of any other kind
  makes every earlier `TL`/`NT` **vanish with no diagnostic** while still
  being echoed in the `DATA CARD` list as read. The transparent set is the
  measured, closed one — `PT`, `PQ`, `MP`, the cards that change what a run
  reports and not what it computes; everything else destroys.
- **Nonpositive addressing is refused** ([`#segment-numbers-must-be-positive`]).
  NEC halts the whole run on an endpoint segment below 1, and does so whether
  or not the paired tag is zero. Without the guard, `locate` would read a
  nonpositive segment as 1 and quietly attach to the wrong segment.
- **An all-zero `NT` is not a no-op** ([`#an-all-zero-nt-is-not-a-no-op`]).
  It attaches a network of zero admittance, which **open-circuits both
  addressed segments**. Measured: a probe whose control answers
  0.10161 + j514.86 answers 0.68923 − j4651.8 with the all-zero card, both
  connection-point currents at ~1e-20. Note that antennaknobs' own importer
  *skips* an all-zero `NT` as unmodellable — a divergence this document's
  successor owns.
- A `TL` with a zero characteristic impedance is refused; NEC aborts while
  *reading* the deck ([`#tl--transmission-line`]).

**The hygiene wave**, all four items of the handoff list below: EOF is read
as `EN`; `GD`-with-`GN 1` refuses by name; `SC` refuses by name; and `PQ` is
a by-**value** gate — `PQ -1` suppresses the charge report and serves,
`PQ >= 0` requests one and refuses. All three bundle `PQ` cards are `PQ -1`,
so `PQ` now costs nothing.

**`GX`/`GR` structure symmetry** (momwire#415), served, with the out-of-cell
`LD` drop refused by name.

### The re-baselined ladder (measured, 457 models)

| step | serve | refuse | silent |
| --- | --- | --- | --- |
| **today (live dialect)** | **358 (78.3 %)** | 99 | **0** |
| + remaining geometry (`GA` `GH` `GC`) | 364 (79.6 %) | 93 | 0 |
| + MININEC-type ground (the `GN 3`/`GD` decision) | 406 (88.8 %) | 51 | 0 |
| + long tail (`PQ` req, `CP`, `WG`/`GF`, `LD 2`/`7`, `RP 1`, `EX 1`/`5`, `NRADL`) | 414 (90.6 %) | 43 | 0 |
| (+ patches — excluded by #456) | 430 (94.1 %) | 27 | 0 |

**The silent column is zero at every rung, including today.** That was the
bar, and it is met: no bundled model now reaches the engine meaning something
the frontend didn't. Today's 78.3 % clears the old `+ NT/TL` projection of
78.1 %; the three waves together moved serve by 70 models.

The 27 at the bottom are refused **by design**, each because NEC-2 itself is
wrong or silent there and the dialect says so out loud: 11 network-contiguity,
9 `GN 0` ground-contact (momwire#282), 8 decks with no `EX` card at all
(`Objects/`-family display models and the two NGF writers — nothing drives
the structure, and NEC would solve nothing either).

### Re-baselined again 2026-08-20 — the MININEC rung lands (momwire#487)

Workstream 2 took the `GN 3`/`GD` decision the ladder above priced: C0
measurements (oracle + 4nec2's own manual and bundled engine) showed the
idiom is **letter-faithful NEC-2 already** — perfect-ground physics under
`RP 0`/request-less execution, the second medium behind `RP 2`/`RP 3`, which
is 4nec2's own "circular cliff … distance zero" manufacturing — so the
refusal came out and the pair serves byte-faithfully (decision record:
momwire `docs/design/mininec-ground-idiom.md`; arc momwire#487, sub-PRs
#488/#493/#494). This script's hand-modelled idiom gate went with it, and
the ladder loses that rung the way it lost hygiene, `GX`/`GR` and `NT`/`TL`:

| step | serve | refuse | silent |
| --- | --- | --- | --- |
| **today (live dialect)** | **400 (87.5 %)** | 57 | **0** |
| + remaining geometry (`GA` `GH` `GC`) | 406 (88.8 %) | 51 | 0 |
| + long tail (`PQ` req, `CP`, `WG`/`GF`, `LD 2`/`7`, `RP 1`, `EX 1`/`5`, `NRADL`) | 414 (90.6 %) | 43 | 0 |
| (+ patches — excluded by #456) | 430 (94.1 %) | 27 | 0 |

Today moved 358 → 400 (+42, exactly the rung's price) and the silent column
stays zero everywhere. The `GD`+`GN 1` rows earlier in this document
(refuse-loudly) describe the pre-#487 state and stay as written — this
section is their successor. The arc also filed two divergences its probes
turned up, neither reachable by a bundle deck: momwire#489 (`GE`'s sign is
unread by the solve) and momwire#490 (an all-zero second medium under a
cliff request reflects off vacuum instead of medium 1).

### The same evening: the Windows captures land (antennaknobs#963)

The batched capture session closed both of this page's remaining
observations in one sitting, and both landed on the side the analysis
predicted:

**`RP 3`, observed.** 4nec2's far-field runs of the `GN 3` model emit mode
digit **3** — `RP 3 19 73 1503` for the pattern, `RP 3 37 1 1500` for the
sweep (captures 0039/0040) — over the manufactured `GN 1` + `GD`. The
MININEC decision record's one inference is now capture fact: the finite
far field is asked for as the circular cliff, exactly as 4nec2's manual
says, and the served `RP 0`/request-less forms are the impedance runs.

**The `NT` placement, observed — and the contiguity refusals dissolve.**
Capture 0041 (`Coax.nec`, the deck whose whole point is a hand-written `TL`
feedline): the manufactured `NT` block is emitted immediately BEFORE the
first hand-written network card — adjacent, one block — with `EX`/`GN`/`FR`
after it, and the engine's own printout solves the network. The census's
old at-the-execute-card model (from capture 0036, a deck with no network
cards of its own) invented destroy patterns 4nec2 never emits; `emit` now
implements the observed rule, the sensitivity line is retired, and its
number becomes the measurement:

| step | serve | refuse | silent |
| --- | --- | --- | --- |
| **today (live dialect)** | **411 (89.9 %)** | 46 | **0** |
| + remaining geometry (`GA` `GH` `GC`) | 417 (91.2 %) | 40 | 0 |
| + long tail | 425 (93.0 %) | 32 | 0 |
| (+ patches — excluded by #456) | 441 (96.5 %) | 16 | 0 |

`net-contiguity` is gone from the refusal reasons: the bottom of the ladder
is now purely by-design — 9 `GN 0` ground-contact (momwire#282) and 8
no-`EX` display decks. The EZNEC half of the session pinned the ground menu
byte-for-byte (Perfect → `GN 1`; MININEC type → a bare `GD` with **no `GN`
at all**; High Accuracy → `GN 0,…`), which is workstream 3's inheritance:
the NEC-5 dialect must read a bare `GD` as MININEC-type ground, where this
dialect measured it free-space-inert.

### Two corrections the re-baseline forced

**1. The census's `EX 6` emission order was wrong, and only phase C could
show it.** The manufactured cards were expanded *in place*, all three at the
`EX 6`'s own site. 4nec2 emits them **grouped**: the phantom `GW` at the end
of the geometry section, the `EX 0` where the `EX 6` was, and the `NT` block
deferred to just before the execute card. Capture 0036's `out__QFH1280.inp`
settles it — its source writes both `EX 6` cards *before* its `FR`, and the
emitted deck writes both `NT` cards *after* it. While `NT` was refused by
name the order was unobservable; the moment it served, the inline expansion
invented 87 contiguity destroy patterns that 4nec2 never emits.

With the order corrected, **zero** bundle decks trip the nonpositive-segment
or zero-`Z0` guards — matching phase C's own corpus scan.

**2. Eleven decks trip contiguity, and that number is a prediction.** Every
one pairs a hand-written `TL` with an `NT` manufactured from `EX 6`:
`HFsimple/Coax.nec`, `HFsimple/EDZ_TL.nec`, `HFvertical/4SQTL.NEC`,
`HFvertical/CardTL.nec`, the three `HFActiveFeed/` Z-match models, and four
`zz_EZnec/v3.0/` models. Under the captured emission order, `LD`/`EX`/`GN`/
`FR` sit between the hand-written `TL` and the manufactured `NT`, so NEC
silently destroys the `TL` — in `Coax.nec`, a model whose entire purpose is
demonstrating a coaxial feedline as a `TL`.

**No capture holds both card kinds at once**, so the manufactured block's
placement relative to a hand-written one is unobserved. The census prints
this as its own sensitivity line: if 4nec2 instead emits the `NT` block
adjacent to the hand-written network cards, today's serve is 366 (80.1 %)
rather than 358. **A single capture of `Coax.nec` settles it**, and it is the
highest-value remaining item on the #413 capture list — either 4nec2 has a
long-standing silent defect in its own bundled demo, or the census loses a
refusal class.

### The census now reads the live refusal table

The by-name half of the scoring was a hand-embedded static set, and it went
stale **twice in three weeks** — it still listed `GX`/`GR` long after #415
served them, and `TL`/`NT` after phase C did, each time overstating the
refusal column. It is now imported from
`momwire.deck._nec2._REFUSED_BY_NAME`, alongside the network-transparent set
and the card-class sets. A private import across the repo boundary is
acceptable for a dev-side measurement script that runs against the submodule
in the same tree and has no runtime contract; it fails **loudly** — an
`ImportError` before a single number is printed — if momwire renames the
table, which is the point. A census that cannot read the live table must not
print a stale one instead.

The by-**value** half cannot come from any table and is still modelled by
hand, but every gate is now audited against the grammar at re-baseline time
and the audit is recorded in `score`'s docstring.

### The `EX 6` manufactured form is pinned end-to-end

The census emits the capture's verbatim constants — `-1.1945e-4` /
`1.19452e-4` / `5.97258e-6`, the phantom wire parked at `z` = its own tag —
rather than the rounded ones it used to. momwire's
`tests/fixtures/nec_portal/dipole_ex6_gyrator.deck` pins the same bytes, so
the form the census models and the form the engine is tested against are one
form. `EX 6` is now a **serve** row: 52 decks arrive as `EX 0` + `NT` +
phantom wire and the dialect runs all three cards. The phantom wire still
fails `_anchor_wires`' guards exactly as EZNEC's does (antennaknobs#427,
#944) — an antennaknobs-side item, not a dialect one.

One unmodelled variant is worth recording: capture 0036's
`out__SLOPE1.inp` emits `EX 0 29901 1` and `NT 29901 1 1 51` with **no
phantom `GW` at all** and a tag of 29901 rather than 9901 — a dangling
network address. Whether that is a second translation form or a stale file in
4nec2's output directory is unresolved; the census models the QFH form only.

[`#networks-under-a-symmetric-cell`]: https://momwire.dev/reference/deck-grammar-nec2/#networks-under-a-symmetric-cell
[`#network-contiguity`]: https://momwire.dev/reference/deck-grammar-nec2/#network-contiguity
[`#segment-numbers-must-be-positive`]: https://momwire.dev/reference/deck-grammar-nec2/#segment-numbers-must-be-positive
[`#an-all-zero-nt-is-not-a-no-op`]: https://momwire.dev/reference/deck-grammar-nec2/#an-all-zero-nt-is-not-a-no-op
[`#tl--transmission-line`]: https://momwire.dev/reference/deck-grammar-nec2/#tl--transmission-line
