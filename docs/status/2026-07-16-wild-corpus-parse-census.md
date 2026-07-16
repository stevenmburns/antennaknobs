# 2026-07-16 — wild-corpus parse census (3,146 decks, importer acceptance)

## Goal

Issue #410: run `nec_import` across the wild `.nec` corpus collected from the
web (`~/antennas/nec-wild/` — ARRL/Cebik course sets, the on5au Cebik archive,
4nec2's bundled models, G1OJS, nec2c/nec2++ distributions, w8io, community
sites; per-source `MANIFEST.md` provenance) and classify every outcome. This
is the *parser* acceptance axis — the xnec2c examples corpus is one program's
dialect; this corpus spans at least four authoring tools.

Tooling: `scripts/bench_nec_corpus.py --parse-only --corpus DIR [--out x.json]`
— recursive, content-hash deduped, no solves. Parses with `network=True` (the
app's path) and falls back to `network=False` exactly like the bench's
`load_deck`.

## Headline

**4,009 files → 3,146 content-unique decks → zero parser crashes.**
Every non-parse is a `ValueError` with a designed, specific message. The
acceptance bar — wild input must never produce an unhandled exception — is
met with no code changes. (Total census wall time ~20 s; slowest single
parse 0.26 s.)

| outcome | decks | share |
|---|--:|--:|
| parsed, no cards skipped | 73 | 2% |
| parsed, run-config cards skipped (RP/GN/…) | 1,984 | 63% |
| parsed via network=False fallback | 7 | 0.2% |
| rejected with a designed message | 1,082 | 34% |
| **crashed** | **0** | **0%** |

65% of the wild web parses into solvable geometry today.

## Skipped-card histogram (decks containing ≥1 of the card)

RP 1782 · GN 1340 · LD 138 · NE 106 · NH 99 · XQ 87 · TL 72 · NT 47 · PT 25 ·
GD 22 · PQ 14 · WG 12 · PL 7 · KH 7 · CP 5 — all run-config/report cards the
app deliberately decides itself (GN becomes the app's ground setting; LD/TL/NT
translate on the network path where expressible). EK no longer appears here:
it is honored since #414.

## Rejection census (1,082 decks, grouped by cause)

| decks | cause | class |
|--:|---|---|
| **642** | SY symbolic variables (4nec2 extension) | **the big unlock** |
| ~242 | tokenizer: `'` inline comments / quoted junk — "expected a NEC card mnemonic, got `'`/`'GW`" (115), "expected mnemonic" other (89), "bad number `'…'`" (38) | **second unlock — one tolerant-tokenizer fix** |
| 44 | EX plane-wave excitation (scattering run) | correct rejection |
| 26 | genuinely unrecognised cards | long tail |
| 19+10 | SP / SM surface patches | out of scope (no patch solver) |
| 15 | GF numerical Green's function | correct rejection |
| 13 | GC tapered wire | modelable someday (per-segment radius exists since #388) |
| 12 | EX non-voltage source types | correct rejection |
| 10 | CM card after CE | trivial tolerance fix |
| 9 | GH with zero wire radius | related to GC class |
| rest | singles/small groups | see JSON |

## Priorities this data sets (filed as issues)

1. **SY symbolic variables — 642 decks (59% of all rejections).** Evaluating
   `SY name=expr` (arithmetic, `*MM`-style unit suffixes, references to other
   symbols) plus substitution into card fields would raise the parse rate
   from 65% → ~86%. 4nec2's own corpus and G1OJS (399 decks) are almost
   entirely SY-based.
2. **`'`-comment / junk-line tolerance — ~242 decks.** 4nec2 writes `'` 
   end-of-line and full-line comments; some exports quote fields. A
   tokenizer that strips `'`-to-EOL before parsing (plus tolerating the
   10 CM-after-CE decks) is a small change unlocking ~8% of the corpus,
   including ARRL's own DIP.NEC.
3. GC/GH tapered-radius support (22 decks) — natural extension of the
   per-wire WireSpec machinery; lower value per effort.

## Caveats

- Parse ≠ solve: this census says the geometry translates, not that engines
  agree on it. The solve/impedance axis stays with the (smaller) xnec2c
  corpus where a nec2c reference exists per deck; running engines across
  2,000 wild decks without references is a separate (deliberate) decision.
- nec2c-reference footnote from the same day: vanilla nec2c 1.3.1 and the
  KJ7LNW 1.3 fork disagree wildly on some decks (`1MHz_tower`,
  near-resonance verticals) — any future wild-solve pass must pin WHICH
  nec2c build it scores against.
- The corpus has 863 exact-content duplicates across sources (the Cebik
  classroom set arrived via two mirrors; icecube mirrors 4nec2) — the census
  dedupes by md5, first path wins.
