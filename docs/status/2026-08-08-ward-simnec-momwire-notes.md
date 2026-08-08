# Notes for Ward: running momwire as SimNEC's NEC engine

**Date:** 2026-08-08 · **Against:** SimNEC 6p4d6 and its bundled `nec2c`
(`5b4az.ae6ty.1.23`)

---

## What we built

momwire — our open-source method-of-moments solver — standing in for `nec2c`
behind SimNEC's NEC portal, as a **pure drop-in**: an executable that answers
`-version`, reads `NX`-framed decks on stdin, and writes NEC-2 printout on
stdout in the layout `nec2/Execute` parses. **No change to SimNEC is needed.**
A user installs our package and pastes `momwire-nec2c`'s path into the NEC
portal dialog; the Smith chart, MNA, tuners and sweeps all work unmodified
with a different electromagnetics kernel underneath.

## What we validated

**Layout: 36 of 36.** We captured 36 deck/printout pairs from your bundled
`nec2c` — its own `NEC2Daemon` test deck, hand-written decks for every card
class the portal emits, ten real designs, and a two-decks-one-process
residency case. Our engine reproduces all 36 section for section, column for
column, token for token — including the `SENSE` column blanking, per-deck
card renumbering, and the matrix-rebuild-only frequency preamble.

**Numbers: inside engineering tolerance.** momwire is a B-spline Galerkin
solver and `nec2c` uses NEC-2's sinusoidal basis with point matching, so they
will never agree digit for digit — and SimNEC doesn't need them to. Worst
case over every row of every table in all 36 fixtures:

| quantity | corpus worst |
| --- | --- |
| `ANTENNA INPUT PARAMETERS` Z and I | 2.83 % |
| current distribution (peak-normalised, complex) | 6.00 % |
| `RADIATION PATTERNS` TOTAL gain | 0.12 dB |
| peak-gain direction | exact |
| near field, off the conductor | 0.7 % / 0.4° |

A handful of rows exceed 5 % — all the same phenomenon, a small residual
between two nearly cancelling numbers (a current null at a 3.5 kΩ gap, a
loading coil cancelling the feed reactance), each pinned by a test asserting
the identity that makes it benign. The comparison also caught one real bug in
our own mapping before it could ship, which is why we did it this way.

**Live sessions: not yet.** Everything above is bench-tested against your
engine's output; driving a real SimNEC session end to end is our next step,
and we'll report what breaks before suggesting anyone else try it.

## Asks, smallest first

**1. The version banner.** Your `-version` check feeds the regex group after
`nec2c.ae6ty.` to `Double.valueOf`, so any engine that *names itself* there is
rejected as "version too old". For now we mimic your convention — the probe
answers `nec2c.ae6ty.9.1` (above the current 1.23 floor) and our real identity
rides in the printout banner, which nothing parses. When you're ready to
recognise a third-party engine, tell us what to emit and we'll change to it.

**2. The error convention.** For anything we don't model we print
`ERROR-NEC2C: <card> is not supported by this engine` and **always** still
emit the `NX` data-card echo, since an engine that goes quiet hangs the UI.
Is that the shape you want, or should a third-party engine trip the
`NEC ERROR` warning frame so the user sees a dialog?

**3. Gain or directivity?** Our `RADIATION PATTERNS` block normalises to the
source's input power — *gain*, matching NEC-2's own `RP 0`. If whatever
consumes `FieldStore` assumes *directivity*, a lossy antenna plots off by
exactly its efficiency (2.2 dB at 60 %) with both engines self-consistent.
Which does SimNEC assume?

**4. Near fields.** We support `NE`/`NH` rectangular grids in free space and
over perfect ground, and refuse them over finite ground (a Sommerfeld
half-space is not an image field) and in spherical form. Both are real work:
is the near-field block used enough to justify it?

## Two bugs we found in the process (yours to keep)

These can freeze SimNEC with the *bundled* engine:

- **A negative `#Proc` on the MP card hangs nec2c forever** — `MP -1 32`
  never returns; no output, no exit.
- **`Execute.processResponse` has no read timeout.** An engine that dies or
  hangs mid-deck (the above, or the `GN 2` + radial-screen abort, which
  skips the NX echo) leaves SimNEC blocked in `readLine()` forever. A
  watchdog, or treating EOF as "engine gone", would turn these into an error
  dialog instead of a frozen session.

## What momwire offers your users

- **An independent second opinion**: different basis, different kernel,
  independently written — agreement means something. (It also ships its own
  sinusoidal-basis solver, close to NEC's formulation, as a built-in
  cross-check.)
- **One fill, N sources**: your multi-port probe sends N excitation groups
  and stock `nec2c` refills the matrix for each; we fill and factor once and
  answer every group by back-substitution.
- **Fast dense assembly**, and an **H-matrix solver at O(N log N)** where the
  dense matrix stops being reasonable.
- **Sommerfeld ground on every solver**; MIT-licensed, actively developed.

## If you want to try it

```bash
pip install antennaknobs
which momwire-nec2c            # paste this path into the NEC portal dialog
momwire-nec2c -version         # nec2c.ae6ty.9.1
```

Two caveats: the filename must keep `nec2c` in it (the portal decides the
dialect from the file name), and a momwire process is heavier than a 2 MB C
binary (~90 MB resident) but much faster per deck once warm — a NEC crew size
of 4 keeps up on a 16 GB machine. We refuse, with the sentinel intact, what
we don't model: surface patches (`SP`/`SM` — momwire is a wire solver), `IS`,
`RP` modes other than 0, spherical `NE`/`NH`, near fields over finite ground,
and `GN` radial-wire screens.
