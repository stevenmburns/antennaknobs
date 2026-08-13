# Notes for Ward: running momwire as SimNEC's NEC engine

**Date:** 2026-08-08 · **Against:** SimNEC 5.1a0 and its bundled `nec2c`
(`5b4az.ae6ty.1.23`)

> **Correction (2026-08-12):** every 2026-08 document in this repo
> originally recorded the validated SimNEC build as "6p4d6" — a
> mis-transcription that matches no SimNEC version format (upstream uses
> `5.1a0` / `5.0c3`-style strings) and that Ward himself did not
> recognize. The actual build is **5.1a0**, verified three ways on the
> Linux box that still has the installation: the Release Notes PDF inside
> the installed `SimNEC.jar` (dated 1/4/2026) tops out at 5.1a0; the
> app's preference layout is `$HOME/.SimNEC/<maj>/<min>/` and the active
> profile is `~/.SimNEC/5/1`; and the bundled `nec2c` version matches.
> The token has been corrected repo-wide in place.

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

**Layout: 40 of 40.** We captured 40 deck/printout pairs from your bundled
`nec2c` — its own `NEC2Daemon` test deck, hand-written decks for every card
class the portal emits, ten real designs, and a two-decks-one-process
residency case. Our engine reproduces all 36 section for section, column for
column, token for token — including the `SENSE` column blanking, per-deck
card renumbering, and the matrix-rebuild-only frequency preamble.

**Numbers: inside engineering tolerance.** momwire is a B-spline Galerkin
solver and `nec2c` uses NEC-2's sinusoidal basis with point matching, so they
will never agree digit for digit — and SimNEC doesn't need them to. Worst
case over every row of every table in all 40 fixtures:

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

**Live session: run on a Windows SimNEC installation, 2026-08-08.** The
engine drove a full session — load, knob tracking, sweeps, patterns,
multi-source — with these results:

- **Station impedance**: our validated ladder-tuner circuit read
  42.56 − j4.765 Ω at the rig side on momwire vs ~40 − j5.7 on your nec2c —
  a few percent through a high-Q tee match, i.e. tight agreement underneath.
- **Pattern**: the display's 2.431 dBi and 2.044 dB readouts straddle by
  0.387 dB — exactly the antenna's coil-loss efficiency (we compute
  −0.378 dB independently). Directivity, gain, and both engines' loss
  bookkeeping agree to a hundredth of a dB, which also answers our
  gain-vs-directivity question empirically: your display handles both,
  consistently.
- **Multi-source**: your own `lindenblad.ssn` example (4 phase-quadrature
  sources) read 27 − j4 per element on momwire vs 27 − j3 on nec2c.
- **One live failure, found and fixed same-day**: `NECSource`
  unconditionally emits a bare `EK` — a card absent from the portal
  documentation's card list — which our engine initially refused, and
  SimNEC then showed fabricated readouts with a NEC Failure Code. EK is
  now accepted and pinned against your engine's output (including the
  partial refill preamble a kernel change triggers, and the fact that NEC
  retains excitation across an execute card).

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
The live session showed the consequence: loading a patch antenna left the
session healthy but showed the user **nothing** — no data, no message. We
suspect an unsupported deck *should* trip your `NEC ERROR` warning frame so
the user sees why. Is that the convention you'd want?

**3. Gain or directivity?** Largely answered by the live session (above):
your display shows both, self-consistently. Remaining one-liner: confirm
which convention `FieldStore` holds internally, so we label our numbers to
match rather than infer it.

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
and `GN` radial-wire screens. The live session also showed user decks carry
cards the portal documentation's card list doesn't — `EK` (sent
unconditionally by `NECSource`) and `GD` (your EZNEC-derived examples all
carry one) are both supported now; each was about an hour's turnaround with
your engine on hand as the oracle. `RP 3` — where those examples' cliff
parameters actually land — is the remaining gap.

One more thing the launch mechanism makes possible: since the portal command
runs through the shell, a `--basis` flag on the command line picks the
solver's basis (`bspline`, `sinusoidal-galerkin`, or the
`sinusoidal-galerkin-converged` setting for near-open feeds). **Two portal
entries differing only in `--basis` give your users cross-basis validation
inside SimNEC** — an engine-side second opinion no single-basis NEC build
can offer, with your nec2c as the third.
