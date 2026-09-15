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

## Results

| design | ground | razor−NEC-5 before | after | NEC-5 Z before → after |
|---|---|---:|---:|---|
| `dipoles.pota_invvee` | free | 14.380 % | **0.1025 %** | 53.1480-16.1530j → 53.5990-8.2337j |
| `dipoles.pota_invvee` | somm | 12.131 % | **0.0877 %** | 65.0150-10.6390j → 65.6060-2.7267j |
| `dipoles.invvee_catenary` | free | 10.658 % | **0.1177 %** | 50.5180-6.2344j → 50.9310-0.8854j |
| `dipoles.invvee_catenary` | somm | 12.084 % | **0.1337 %** | 44.8490-5.0933j → 45.2160+0.2881j |
| `wire.efhw_sloper` | free | 11.939 % | **0.0752 %** | 42.9233-6.6700j → 47.8816-5.2208j |
| `wire.efhw_sloper` | somm | 11.071 % | **0.0629 %** | 48.9251-7.0788j → 54.3374-6.4035j |

### C1–C4

| prediction | bar | measured | verdict |
|---|---|---|---|
| **C1** | razor−NEC-5 ≤ 0.5 % on all 6 rows | worst 0.1337 % | **HIT** |
| **C2** | every bs2 and razor row bit-identical to `b9bc3e2f0` | 12 of 18 rows unchanged, byte for byte | **HIT** |
| **C3** | only the NEC-5 rows move | 6 rows changed, all `nec5` | **HIT** |
| **C4** | after values within ×3 of the catalog median 0.0665 % (i.e. 0.022–0.20 %) | range 0.0629–0.1337 % | **HIT** |

Hit 4 of 4.

The six rows carried the catalog study's entire >5 % razor-vs-NEC-5 tail. They now sit at 0.0629–0.1337 %, against a catalog-wide median of 0.0665 % over the other 100 designs — at the unjacketed background, not below it, which is the strongest claim the data supports.

### Cross-build agreement, unasked for and worth recording

Laptop-builder measured `wire.efhw_sloper` at **0.075 %** free and **0.063 %** over
the default ground on the *laptop's* `nec5cl`. This run, on `nec5cl-3b75639`, reads
**0.0752 %** and **0.0629 %**. Two different NEC-5 builds, four-figure agreement.
C4 was deliberately written as a band rather than a reproduction of their digits,
because a different binary need not match; it matched anyway, which says the
coated-wire pair is being read the same way by both builds.

### What this does and does not settle

It settles the jacket: the two engines now spell a coated wire the same way, and
the catalog study's worst rows are gone. `CONFIRM-1532.md`'s own framing above is
the limit of the claim — **nothing here is about convergence.** All six rows are
at each design's default mesh, and the #1516 ladders showed razor-2p and NEC-5 are
the *unconverged* pair there, moving 18–33 % together under refinement while bs2
moves under 2.4 %. So these figures say the two engines agree about the jacket;
they do not say either is near its own mesh limit. That is job 2's question.

### Reproducing

```
git checkout 3b0d942a9                    # AK PR #1532, unmerged
NEC5_EXE=<path to nec5cl-3b75639> \
  python <this dir>/run_catalog.py \
    --designs dipoles.pota_invvee dipoles.invvee_catenary wire.efhw_sloper \
    --out records-1532.jsonl
python <this dir>/confirm_1532_report.py
```

18 cells in 9.0 s. The harness is `run_catalog.py` at `b9bc3e2f0`, unchanged —
it was read out of git rather than edited, and the copy used had sha256 prefix
`1f373187981bb2b3`.
