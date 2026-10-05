# The replay sitting — 20 decks EZNEC accepted from momwire's NEC-4.2 slot

momwire#1295 phase 3, run 2026-10-03 on the Windows box with **EZNEC Pro/2+
v7.0.4 driving every run**. The capture corpus in `scratch/eznec-capture/`
records what EZNEC *writes*; this records what EZNEC *accepts back*, which is a
different and previously untested thing.

Every deck here was written by EZNEC's External NEC-4.2 slot with the engine
path pointed at momwire, and **every printout in `printouts-momwire/` was
displayed by EZNEC without complaint** — Src Dat, currents, patterns, near
field, or (for 020) a refusal shown in its own window. That is what makes this
set usable as a smoke oracle: it is not merely well-formed, it is known-read.

## Provenance

| | |
|---|---|
| host | EZNEC Pro/2+ v7.0.4, `C:\EZNEC 7.0\Docs` |
| slot | External NEC-4.2, engine path `momwire-nec4.exe` |
| writer | momwire 0.70.0, branch `feat/1295-nec4-printout` (PR #1305), `7330d92a10c7a3cbbcea6c9fabefc825e8e5a7f0`, bspline basis, AVX2 accelerators |
| reference | NEC-4.2, LLNL distributed `NEC42W64CL.exe`, run on this box on the identical decks |

**NEC-4.2 printouts are included with attribution**, per the licensee
(Steve Burns, 2026-10-03): *"You are allowed to add nec42 printout with
attribution in the repository. We already do this for nec5 printouts."* The
NEC-4.2 **sources and binaries** remain licence-restricted and are not here.

Note the contrast with `.gitignore`'s `scratch/eznec-capture/**/*.OUT` rule,
which is deliberately left in place. That rule exists to keep *licensed NEC-5*
printouts out of a public repo. Neither reason applies here: the
`printouts-momwire/` files are our own engine's output, and the
`printouts-nec42/` files are covered by the permission above.

## Layout

- `decks/` — the `EZ.NEC` EZNEC wrote, byte for byte, CRLF included.
- `printouts-momwire/` — what momwire answered, and what EZNEC then displayed.
- `printouts-nec42/` — NEC-4.2's answer to the identical deck, as a reference.
- `index.tsv` — line counts both sides, NEC-4.2's exit code, served vs refused.

## What the line counts say

**18 of the 20 match NEC-4.2 exactly.** The two that do not are both expected:

- **016 (`GN 2`)** — ours 179, NEC-4.2 185. The six lines are NEC-4.2's
  Sommerfeld ground-table cache messages, which we do not write. This is the
  one shape where our printout is measurably *short*, and EZNEC read it
  without objecting.
- **020** — ours 30, NEC-4.2 435. Deliberate **at the version measured**: in
  momwire 0.70.0/0.71.0 `NE` over a finite ground was a shape the NEC-4.2 slot
  refused by name, while NEC-4.2 itself solves it. The 30-line file is that
  refusal, and EZNEC popped it up in its own window.

  **This is no longer current behaviour.** momwire#1352 (PR #1355) serves `NE 0`
  and `NE 1` over free space, PEC, `GN 2` and `GN 3`, so from 0.72.0 this deck is
  expected to SOLVE. The file stays as the record of what 0.71.0 did and as the
  proof that EZNEC surfaces a refusal to the user — which is what it was captured
  for — but do not read it as a statement about what momwire refuses today.

## Pairs and negative controls

- 001/002 and 007/008 are repeats, kept because a repeat is evidence the result
  was stable rather than a one-off.
- **010 vs 011** are two different shipped 4-square models that carry the *same*
  EZNEC title, "4-square array w/feed system" — `4sqtl.ez` and
  `4Square TL ARRL Example.ez`. They give 10.547 + 3.828j and 13.657 + 4.479j.
  Kept because the title does not identify the model, which cost a wrong turn
  during the sitting.
- **012 vs 013** are the same `LD 4` load at two positions; only 013 (segment 3)
  reproduces capture 0225.
- **018 vs 019** are a one-point `NE` and a 242-point grid. EZNEC's near-field
  dialog defaults to the single point.
