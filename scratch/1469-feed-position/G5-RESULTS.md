# G5, momwire Z direction — Skylake, 2026-09-13

**HIT: 19 of 19 = 100 %**, against a bar of 80 %. No misses.

Registration, verbatim from `PLAN-slice2B.md`: *"On catalog-nec5 decks whose
momwire Z moves by more than 1e-3, the new spelling is closer to the catalog
design solved directly (`native_reference.py`) on at least 80 % of them. A miss is
reported, not re-gated."* Amendment 1 (#1483) rides on this branch; G5's bar is
unchanged.

## Setup

| | |
|---|---|
| baseline | `5363bbbe5` (main) |
| after | `bdeedfdd2` (part-B importer + the #1483 NEC-5 LD fix) |
| decks | `dist/nec5_corpus/catalog-nec5`, **476** files, `sha256sum *.nec \| sha256sum` = `8d568c566aa19540` |
| momwire | **495b6c9**, the pointer BOTH commits record, one build serving both runs |
| workers | 4 (4 × 3.5 GB cap against 46 GiB) |

`e7a01c122` differs from `bdeedfdd2` by nothing under `src/` or `tests/`, so the
branch head and the measured commit are the same code.

**On the momwire build.** `make build` after checking the submodule out to
`495b6c9` produced no compile lines and left the `.so` mtimes untouched — a no-op,
which is the shape the sync skill warns can hide a stale extension. It is benign
here and the check is one line: `git diff --stat 23d81e5 495b6c9` over
`*.cpp *.hpp *.h setup.py` is **empty**, so the extension already present is the
correct one for `495b6c9` and `build_ext` was right to relink nothing. `momwire`
imports from the submodule tree, the commit reads `495b6c9`, and
`from momwire import bspline` raises no stale-module error.

## Captures

| capture | wall | result |
|---|---:|---|
| baseline `5363bbbe5` | **83 s** | 476 decks, 468 ok, 8 refused or failed |
| after `bdeedfdd2` | **80 s** | 476 decks, **472 ok**, 4 refused or failed |
| `native_reference.py` | **75 s** | 300 decks, **0 errors** |

## Status changes: 4, all the same design

| deck | baseline | after |
|---|---|---|
| `dipoles.short_dipole_loaded.default.free.nec` | `error` | **`ok`** |
| `dipoles.short_dipole_loaded.default.somm13.nec` | `error` | **`ok`** |
| `dipoles.short_dipole_loaded.refined.free.nec` | `error` | **`ok`** |
| `dipoles.short_dipole_loaded.refined.somm13.nec` | `error` | **`ok`** |

Nothing served on the baseline stopped serving. These are the four refusals
Amendment 1 names.

## G5

468 decks served on both runs; **19 move by more than 1e-3** (`compare_z.py`'s
metric: the max over ports of |z_b − z_a| / |z_b|). All 19 have a
`native_reference.py` row and none carries an error, so all 19 are scored.

**All 19 land closer to the catalog design solved directly.** 100 %, no misses.

### The ten largest moves

| \|dZ\|/\|Z\| | deck | direction |
|---:|---|---|
| 1.030e+00 | `multiband.trap_fan_dipole.refined.somm13.nec` | closer |
| 1.030e+00 | `multiband.trap_fan_dipole.default.somm13.nec` | closer |
| 1.021e+00 | `multiband.trap_fan_dipole.refined.free.nec` | closer |
| 1.021e+00 | `multiband.trap_fan_dipole.default.free.nec` | closer |
| 4.743e-01 | `broadband.t2fd.default.free.nec` | closer |
| 4.742e-01 | `broadband.t2fd.refined.free.nec` | closer |
| 4.666e-01 | `broadband.t2fd.default.somm13.nec` | closer |
| 4.666e-01 | `broadband.t2fd.refined.somm13.nec` | closer |
| 3.731e-01 | `wire.rhombic.refined.free.nec` | closer |
| 3.731e-01 | `wire.rhombic.default.free.nec` | closer |

The remaining nine are `wire.rhombic` ×2, `wire.terminated_longwire` ×3 and
`multiband.trap_dipole` ×4, from 1.5e-01 down to 4.0e-03.

## What moved, and what did not — worth more than the pass mark

**Every one of the 19 movers carries a discrete `LD` card**, and so do the four
status changes. Checked per deck: `trap_fan_dipole` has four, `trap_dipole` two,
`t2fd` / `rhombic` / `terminated_longwire` one each. Not one deck without a
discrete load moved above 1e-3.

So on this corpus the movement is attributable to **#1483's LD fix alone**, and
part B's off-centre feed/load spelling moved no momwire Z above the bound. That is
consistent with how these decks are generated rather than surprising:
`export_catalog_nec5.py` coerces a fed wire to an even segment count so the feed
lands on a knot — `native_reference.py`'s own docstring says so — so a catalog deck
rarely presents the off-centre feed part B is about. It does mean **G5's 100 % is
evidence for #1483 and says little about part B's feed spelling**; the feed work's
evidence is in the other gates.

## Reproducing

```
PYTHONPATH=<base>/src python catalog_nec5_z.py <decks> baseline-5363bbbe5.json 4
PYTHONPATH=<after>/src python catalog_nec5_z.py <decks> after-bdeedfdd2.json 4
python compare_z.py baseline-5363bbbe5.json after-bdeedfdd2.json
PYTHONPATH=<after>/src python native_reference.py baseline-5363bbbe5.json after-bdeedfdd2.json native-momwire-partB.jsonl
```
