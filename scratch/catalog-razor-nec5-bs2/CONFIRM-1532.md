# Confirmation run against AK PR #1532 (#1523's jacket fix)

**Predictions registered before the first solve.** Job assigned by Laptop-builder
2026-09-15; the three predictions C1–C3 are theirs, C4 is mine.

## What is being tested

The catalog study found that its whole >5 % razor-vs-NEC-5 tail was three
designs — the only three that default to a PVC-jacketed `wire_type` — and named
the cause: NEC-5 has no insulated-wire card, so `engines/nec5.py` emulated the
jacket as an `LD 2` King inductance alone while momwire's lane passes the jacket
into the solver. PR #1532 gives every NEC writer momwire's **coated-wire pair**:
the equivalent radius on `GW`, `LD 2` for the jacket inductance, and `LD 5`
rescaled for the larger radius (`engines/_nec_wire.py`).

## Setup

| axis | value |
|---|---|
| antennaknobs | PR #1532 head **`3b0d942a9`**, branch `fix/1523-nec5-equivalent-radius`, unmerged, base `main` |
| momwire | submodule pointer `1ca8725` — #1532 does not move it, verified |
| NEC-5 | `nec5cl-3b75639`, the same build as the catalog run at `b9bc3e2f0` |
| designs | `dipoles.pota_invvee`, `dipoles.invvee_catenary`, `wire.efhw_sloper` |
| grounds | `free` and `somm` = `("finite", 13.0, 0.005)` |
| harness | `run_catalog.py` from `b9bc3e2f0`, **unchanged** |

18 cells: 3 designs × 2 grounds × 3 engines.

## Predictions

* **C1.** `rel|ΔZ|(razor-2p, NEC-5)` ≤ **0.5 %** on all 6 design×ground rows.
* **C2.** Every `bs2` and `razor` row is **bit-identical** to the catalog records
  at `b9bc3e2f0` — same 17 significant figures, not merely the same to the
  printed precision.
* **C3.** **Only** the NEC-5 rows move.
* **C4 (mine).** The after values land within a factor of 3 of the catalog's own
  razor-vs-NEC-5 median of **0.0665 %**, i.e. in **0.022 %–0.20 %**. Laptop-builder
  measured 0.063–0.13 % on a *different* `nec5cl` build, so this bar asks whether
  the fix lands at the unjacketed background — not whether it reproduces their
  digits, which a different binary should not be expected to.

## Disclosure: the diff was read before these bars were written

C2 and C3 are registered having checked, not blind. #1532 touches 13 files.
`engines/momwire.py` is not among them. The two that could have moved momwire's
answer are **docstring-only**: `designs/dipoles/pota_invvee.py` (a paragraph about
how the engines spell the jacket) and `wire_catalog.py` (the `WireSpec` docstring).
So C2 is expected to hold for a reason that is visible in the diff, and a MISS on
it would mean the diff does something its file list does not suggest.

Nothing has been solved against `3b0d942a9` at the time of writing.
