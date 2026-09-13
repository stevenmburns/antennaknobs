# AK#1443: `elevated_buried_counterpoise`'s 31 % in R against NEC-5

Haswell (i7-4770K). Scratch only; no `src/` change in either repo until the
term is named. Plan unit U6 (`docs/plan-buried-scope-closure.md`). Measure-first:
every prediction below is committed before the run that tests it, and every
miss is reported.

## Setup

- antennaknobs `eab1c4ac8` (origin/main). momwire `1dbd384`: origin/main, whose
  `src/` is the v0.54.0 tag `260bd91` that antennaknobs pins, and a superset of
  the census's `ad3cb9f`. Accelerators rebuilt with `make build`.
- NEC-5 reference: `~/nec5-timing/nec5cl-x13-static`, sha256
  `7ebf343d7d01283b83fae8192cd9c6ca434b5befb232065fc12b4d729f06a9f3` — the
  original x13 statically linked. The census used dynamic x13 `2068ae67…`. On
  momwire#1048 the static build printed every one of #1027's 15 banked NEC-5 rows
  identically.
- Decks from `NEC5Engine.deck()`, default variant, soil (13, 0.005), 7.1 MHz.

## Two facts from the decks, checked before anything is registered

**The decks are the census's.** Rebuilt at `eab1c4ac8`: nominal_nsegs 21 gives
sha256 `14239f58d8073ceb…` (239 NEC-5 segments), 42 gives `5c08c0eee924e8fe…`
(472), both equal to AK#1443's.

**The fed segment is not refined by nominal_nsegs, and the two engines are fed
at different ports** — the pattern momwire#1048 found on #1027's rod:

| nominal_nsegs | NEC-5 fed wire (0.50 → 0.55 m) | NEC-5 source | momwire fed wire | momwire source |
|---|---|---|---|---|
| 21 | 2 × 25 mm | `EX 0 1 1 2`, the knot | 1 × 50 mm | gap at arclength 0.025 m, mid-segment |
| 42 | 2 × 25 mm | the knot | 1 × 50 mm | mid-segment |

Doubling nominal_nsegs refines the radiator (21 → 42 segments) and the radials,
not the 50 mm source region. So AK#1443's "not mesh error, or not mostly"
(ΔR/R 31.2 → 31.3 % under ×2) is untested on the source axis. On #1027 that
axis, together with a/Δ, carried the whole disagreement. It is a hypothesis
here, not a finding. And this deck is near-open (|X| ≈ 70 kΩ), which is where a
source region's capacitance is the largest part of |Z|.

**Resolution floor.** NEC-5 prints five significant figures, so its X is
quantised to ±0.5 Ω at 61604 and R to ±0.0005 Ω at 30.643.

## Step 1 — reproduce AK#1443's rows (registered before the run)

The census's own per-cell worker (`scratch/956-census/popa_worker.py`) with its
thread pinning (`OMP/OPENBLAS/MKL_NUM_THREADS=1`), so "bit-identical" means what
the census meant by it.

| id | prediction | verdict |
|---|---|---|
| P1.1 | momwire Z bit-identical to the census at both meshes: 44.5602−73719.3196j (21), 42.7896−72708.6105j (42) — `1dbd384` adds nothing on this deck's path beyond `ad3cb9f` | pending |
| P1.2 | NEC-5 (x13-static) prints the census's Z at both meshes: 30.6430−61604.0000j and 29.4170−61557.0000j | pending |
| P1.3 | ΔR / max\|R\| = 31.2 % and 31.3 %; \|ΔZ\| / max\|Z\| = 16.4 % and 15.3 % | pending |

A miss on P1.1 or P1.2 stops the unit and is reported before anything else.
