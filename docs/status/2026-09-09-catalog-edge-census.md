# Edges per deck, segments per edge — the whole catalog

**2026-09-09.** Rows: `docs/status/data/catalog-edge-census.jsonl`, written by
`scripts/catalog_edge_census.py`. 103 designs, two rungs.

## Why

momwire#1024 measured `_seg_seg_reg_geometry` at **20.3%** of a solve on one
long finely-meshed wire and **0.4%** on a ten-wire catalog deck. Both serve the
**same-edge** path, and a single wire at N=1201 is *one edge with 1201
segments* — so the same-edge block is essentially the whole matrix. The open
question was whether any real catalog deck looks like that. It is the question
momwire#1006 also wanted answered and nobody had run.

## The metric

For edges holding n₁…n_E segments, the same-edge blocks cost `Σnₑ²` while the
whole fill costs `(Σnₑ)²`, so

    same_edge_fraction = Σnₑ² / (Σnₑ)²

is the share of the fill the same-edge path serves: **1.0** for a single edge,
**1/E** for E equal edges. Edge *count* alone does not predict it — one long
edge among nine short ones still dominates.

It is **invariant under uniform refinement**: `Σ(k·nₑ)² / (Σk·nₑ)²` cancels the
k². "Refined" in this codebase is exactly that — a uniform multiplier on the
counts (momwire's banked cells are the nominal mesh ×2 and ×4); there is no
engine-level density knob, the counts come from each design's own translation.
So the refined rung is measured for the **absolute** counts it reaches, not
because the ranking could move. It does not: both rungs give a median of 0.214
and the same ten decks above 0.5.

## What the catalog looks like

103 decks, app-default mesh:

| | |
|---|---|
| single-edge decks | **2** (`dipoles.short_dipole_loaded`, `wire.doublet_balanced_tuner`) |
| same-edge fraction ≥ 0.5 | **10** |
| median fraction | **0.214** |

The top of the distribution:

| design | wires | edges | segs | max/edge | fraction |
|---|---|---|---|---|---|
| `dipoles.short_dipole_loaded` | 1 | 1 | 21 | 21 | 1.000 |
| `wire.doublet_balanced_tuner` | 1 | 1 | 61 | 61 | 1.000 |
| `wire.zepp` | 1 | 2 | 41 | 40 | 0.952 |
| `wire.efhw_sloper` | 1 | 3 | 42 | 37 | 0.786 |
| **`wire.terminated_longwire`** | 1 | 5 | **1010** | **840** | 0.705 |
| `dipoles.ocf_dipole` | 1 | 3 | 41 | 33 | 0.678 |
| `verticals.challenger` | 1 | 3 | 42 | 31 | 0.602 |
| `verticals.dominator` | 1 | 3 | 69 | 41 | 0.506 |

At ×4 the same decks scale: `terminated_longwire` reaches **4040 segments with
3360 in a single edge**, larger than the N=1201 benchmark that started this.

## So: is the single-wire share an artefact?

**Partly — and the part that survives is smaller than it looks.** Measured
directly, not extrapolated:

| deck | segs | total | `_seg_seg_reg_geometry` | absolute |
|---|---|---|---|---|
| synthetic single wire, N=1201 | 1201 | 0.54 s | 20.3% | 0.11 s |
| `wire.terminated_longwire` ×1 | 1010 | 0.46 s | 12.0% | 0.05 s |
| `wire.terminated_longwire` ×4 | 4040 | 9.52 s | **9.3%** | **0.88 s** |
| `broadband.lpda` refined | 2456 | 6.26 s | 0.4% | 0.03 s |
| `beams.owa_yagi` | 158 | 0.02 s | 4.3% | 0.001 s |

Two things fall out that the single-wire benchmark could not show.

**One real deck is in that regime — one.** `wire.terminated_longwire` is
genuinely same-edge-dominated (0.705), and at a refined mesh it is the most
expensive same-edge case in the catalog.

**Its share FALLS with refinement, from 12.0% to 9.3%**, even as the absolute
cost rises to 0.88 s. The other fill costs grow faster. So refining does not
walk this toward the 20% the benchmark suggested; the benchmark's 20% is the
ceiling and no catalog deck reaches it.

**And the share is highest where the total is smallest.** The decks with a big
same-edge fraction are the cheap ones — 0.02 s for `owa_yagi`, 0.46 s for the
long wire. The deck a user actually waits on (`broadband.lpda` refined, 6.26 s)
has it at 0.4%. Optimising a share is only worth what the total is worth.

## Conclusion for momwire#1024

A C++ twin of `_seg_seg_reg_geometry` would save at most **~0.9 s, on one deck
of 103, at a mesh four times the shipped one**; ~0.05 s on that deck as
shipped; ~0.03 s on the expensive multi-wire decks. That is the measured
ceiling, and it does not justify C++ on three toolchains.

Recorded rather than acted on. If the catalog ever grows a family of long
finely-meshed single runs — beverages, long verticals — this census is the
thing to re-run, and the number to watch is the fraction, not the edge count.
