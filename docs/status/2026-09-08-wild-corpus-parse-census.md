# 2026-09-08 — wild-corpus parse census (3,146 decks, importer acceptance)

## Goal

Re-run the 2026-07-16 parse-only census against today's importer and rank what
it still cannot read, by deck count and by family, each rejection keyed on the
sentence it produced. Closes #943.

Parse-only: no solve, no reference. 7.8 s for the whole corpus.

## Headline

**4,009 files → 3,146 content-unique decks → zero parser crashes**, and
rejections fall from 1,082 to **188**.

| outcome | 2026-09-08 | 2026-07-16 |
|---|--:|--:|
| parsed, no cards skipped | **338** | 73 |
| parsed, run-config cards skipped | **2,615** | 1,984 |
| parsed via network=False fallback | 5 | 7 |
| rejected with a designed message | **188** | 1,082 |
| **crashed** | **0** | **0** |

**94 % of the wild web now parses into solvable geometry, against 65 % in
July.** The acceptance bar — wild input must never produce an unhandled
exception — still holds with zero crashes, and every rejection is a
`ValueError` carrying a specific sentence. The July census's two named unlocks
both landed: SY symbolic variables (642 decks) and the tolerant tokenizer
(~242).

Slowest single parse 0.45 s (`arrl/cebik-models/VHF-UHF/432-tri-cornerrefl.nec`).

## Skipped-card histogram (decks containing ≥1 of the card)

RP 1898 · GN 1367 · PT 175 · NE 110 · PQ 99 · XQ 98 · NH 98 · LD 61 · GD 24 ·
WG 14 · KH 13 · IS 10 · PL 7 · CP 5 · NT 1

All run-config or report cards the app decides itself. `TL` and `NT` have
almost vanished from this list since July (72 → 0 and 47 → 1): they now
translate on the network path rather than being skipped.

## The 188 rejections split in half

| | decks |
|---|--:|
| **correct rejections** — not a driven wire antenna at all | **99** |
| **importer gaps** — the deck is in scope and we cannot read it | **89** |

### Correct rejections (99) — no action

| decks | sentence |
|--:|---|
| 46 | `EX card asks for plane-wave excitation, which is a scattering run, not a driven antenna` |
| 22 | `this deck uses a surface patch (SP), which antennaknobs cannot model` |
| 16 | `this deck uses a numerical Green's function file (GF), which antennaknobs cannot model` |
| 15 | `this deck uses a multiple-patch surface (SM), which antennaknobs cannot model` |

These are scattering runs and patch/NGF models. Nothing here is a defect.

## The five importer gaps, ranked

### 1. Tapered wires — 30 decks

| decks | sentence |
|--:|---|
| 20 | `GW card: zero wire radius announces a tapered wire (GW with zero radius + GC continuation), which antennaknobs cannot model` |
| 10 | `GH card: wire radius must be > 0` |

The largest single gap, and the only one that is modelling rather than
parsing. Per-segment radius has existed since #388, so the representation is
there; what is missing is the GC continuation card and GH's zero-radius
spelling of the same idea. Families: `arrl/RHOM.NEC`, the Cebik NEC-4 tutorial
series, `opensource/4nec2` Yagis (`YI20_40B/C`), helix decks.

**Not filed** — this is a feature with real design questions (how a tapered
wire meets the per-wire material model), not a bug with obvious scope.

### 2. SY-family evaluator failures — 20 decks, and they are THREE bugs

Grouped by the card on the failing line, not by the message:

| decks | card | what is actually there |
|--:|---|---|
| 7 | `GM` | `GM 0 0 0 0 0 (dHelix/2 - dCplLoop/2 - clSep)/1000 0 clZ/1000 1` |
| 10 | `SY` | `SY D = #12/in`, `SY R-2=18`, `SY Len=#.4` |
| 3 | `GN` | `GN 2 0 0 0 10. 0.01 SOMEX10.NEC` |

- The **GM** cases are a field-splitting bug: the expression contains spaces
  *inside parentheses*, so whitespace tokenisation truncates it at
  `(dHelix/2` and the evaluator reports an unbalanced parenthesis. Filed as
  **#1273**.
- The **GN** cases are a NEC-4 Sommerfeld ground-file name being evaluated as
  an expression — the same shape as the closed **#1067** (`NL` mesh filename
  evaluated as an SY expression), on a different card. Filed as **#1274**.
- The **SY** cases are mostly gauge tokens, which is gap 4 below (**#1272**).

### 3. Unrecognised cards — 16 decks

`NX` 7 · `LE` 2 · `UM` 2 · `JN` · `VC` · `PS` · `CW` · `MP`

`NX` is the only one with volume and the only one with a clear reading: it
terminates one structure and begins the next in a multi-run file, always after
an `RP`/`WG`. Filed as **#1275**. The rest are singles across NEC-4 and
vendor extensions and are a genuine long tail.

### 4. AWG-per-unit gauge tokens — 12 decks

`#12/ft` 6 · `#18/ft` 2 · `#8/ft` 2 · `#12/in` · `#14/in`

4nec2 writes the wire radius slot as an AWG gauge with a unit suffix:

```
GW  1  5  0  0  0  0  0  31.915  #12/ft
```

The bare `#12` spelling is already understood; the `/ft` and `/in` suffix is
not. The same token also appears inside `SY` assignments (`SY D = #12/in`), so
a fix here reaches part of gap 2 as well. Filed as **#1272**.

### 5. Tokeniser: `CE` with no separating space — 9 decks

7 of the 9 are `expected a NEC card mnemonic, got 'CEEXAMPLE'` and friends:

```
CMTHE PATCH MODEL MAY BE USED FOR KA LESS THAN ABOUT 3.   <- accepted
CEFOR THIS RUN  *** KA=2.9 ***                            <- rejected
```

**`CM` immediately followed by comment text is already tolerated; `CE` is
not** — the two lines above are adjacent in the same file. That asymmetry is
the whole bug. Filed as **#1272** alongside the gauge fix as a tokeniser pair.
The remaining 2 are `bad number '…'` singles.

## What the ranking says

Of the 89 gap decks, **59 are parser-level** (SY-family 20, unrecognised 16,
gauge 12, tokeniser 9, plus 2 singles) and **30 are the one modelling gap**.
The parser-level ones are individually small and collectively the cheaper
half: the four filed issues cover 36 decks between them (#1272 nineteen, #1273 seven, #1275 seven, #1274 three), and none requires a
change to the geometry model.

The July census's framing — "one tolerant-tokeniser fix" as the second unlock
— still applies at a smaller scale. There is no third 642-deck unlock left;
what remains is a long tail plus one feature.

## Addendum (2026-09-09): GC tapered wires — 157 → 147

`nec_import` now translates the canonical NEC-2 tapered wire (a `GW` with zero
radius followed by `GC 0 0 RDEL RAD1 RAD2`) into a run of one-segment `GW`
wires carrying the GW's tag, so `(tag, segment)` addressing on EX / LD / TL
still resolves. **Rejections fall 157 → 147, ten decks, with zero
regressions** (a full before/after diff of the census: 10 decks move from
`rejected`, none moves the other way).

Both progressions are geometric, and both were **derived from nec2c's own
segmentation table** rather than assumed — nec2c reads GC natively:

- **radii** geometric from `RAD1` to `RAD2`. On `YI20_40B.NEC` (16 segments,
  .006 → .011) the ratio is (11/6)^(1/15) = 1.041237, and all sixteen of
  nec2c's printed radii match.
- **lengths** `L[i+1] = L[i] · RDEL`, scaled to the wire's own span. On
  `ch-3/3-1a-nec2.nec` (9 segments over 0.232 m, RDEL 0.8163265) that predicts
  L₁ = 0.050785 and nec2c prints 0.0508.

The length taper is **honoured, not refused**. The original issue expected it
to be rare; it is a third of the canonical set, and `3-1a-nec2.nec` carries two
different RDEL values in one deck.

Solve gate against nec2c, same decks:

| deck | AK | nec2c | ΔΓ |
|---|--:|--:|--:|
| `YI20_40B.NEC` (radius taper) | 25.4685 − 9.8620j | 25.4010 − 9.9794j | 0.00234 |
| `3-1a-nec2.nec` (length taper) | 70.9267 − 3.1119j | 70.9230 − 3.1248j | **0.00009** |

### What the taper class still holds, and why it is not 30

The issue estimated ~30 decks from the two refusal messages. Classifying all
30 shows the GC translation was never going to reach most of them:

| decks | class | status |
|--:|---|---|
| 10 | **unlocked here** | canonical NEC-2 GC |
| 10 | `GH` zero radius, **no GC anywhere in the file** | separate issue |
| 7 | GC in a NEC-4 spelling (6, 7 and 9 fields) | separate issue; refused by name |
| 3 | no GC — incl. `arrl/RHOM.NEC` | separate issue |

`RHOM.NEC` deserves its own note because it was the issue's headline gate: it
has **no GC card**, its radius sits on a wrapped continuation line, and
**nec2c rejects the deck outright** (`GEOMETRY DATA CARD ERROR`), so it could
never have been the reference it was named as. It needs continuation-line
support, which is a different fix.

Every remaining case now refuses **by name** — "only the plain continuation
form … is translated", or "zero radius and no GC continuation followed it" —
rather than under the old blanket message, which claimed a taper on 13 decks
that have none.

## Caveats

- Parse-only. A deck that parses is not necessarily one that solves, and this
  census says nothing about accuracy.
- Content-deduped by md5 (863 duplicate files collapsed), same rule as the
  solve sweep.
- Rejection counts are per deck, keyed on the FIRST sentence the importer
  produced; a deck with two unreadable features is counted once.

> **Addendum, 2026-09-08 evening.** The four census items filed from this run
> (#1272 gauge-per-unit tokens and glued `CE`, #1273 spaced expressions in
> parentheses and tab fields, #1274 the GN ground-file sentence, #1275 `NX`)
> were fixed together, ported from the NEC-5 corpus translator
> (`scripts/nec5_corpus/`) where they were first worked out against the same
> decks. Re-run on the same 3,146 unique decks: **rejected 188 → 157**; the
> three `GN … SOMEX10.NEC` decks now carry the tabulated-ground sentence rather
> than "unexpected character '.'". The head of the remaining list is the
> designed refusals (plane-wave EX 46, SP 27, GC taper 20, GF 16, SM 15).
