# Notes for Ward: running momwire as SimNEC's NEC engine

**Date:** 2026-08-08 · **Issue:** antennaknobs #792 · **Against:** SimNEC 6p4d6
and its bundled `nec2c-ubuntu-x86` (`5b4az.ae6ty.1.23`; the corpus was captured
from an older 1.17 copy on the same machine and re-verified against 1.23 —
identical bar the banner, one signed zero and one denormal)

*Written to be sent nearly as-is. Everything below is measured or read out of
the shipped code; the questions at the end are genuinely open on our side.*

---

## What we built

We have momwire — our open-source method-of-moments solver — standing in for
`nec2c` behind SimNEC's NEC portal, as a **pure drop-in**: it is an executable
that answers `-version`, reads decks from stdin framed by `NX`, and writes the
NEC-2 printout back on stdout in the layout `nec2/Execute` parses. **No change
to SimNEC is needed today.** A user installs our package, pastes
`<venv>/bin/momwire-nec2c` into the NEC portal dialog, and SimNEC's Smith
chart, MNA solver, tuner and sweeps all work unmodified with a different
electromagnetics kernel underneath. We wrote it against the printout, not
against your internals, so nothing in it depends on a SimNEC version.

## What we validated

**Layout: 30 of 30.** We captured 30 deck/printout pairs from the oracle
`nec2c` your installation ships — the `NEC2Daemon` test deck raw and
daemon-framed, hand-written decks for every card class, ten real designs from
our catalog, and a two-decks-down-one-process residency case. Our engine
reproduces all 30 **section for section, column for column, token-arity for
token-arity**, including the details that bite: the `SENSE` column blanking
when both field components fall under the degenerate-field floor (which is what
makes a pattern row 11 tokens instead of 12, and would otherwise shift
`E(THETA)`/`E(PHI)` by one column on half the table); card numbering restarting
at 1 inside each deck; the frequency preamble printing only when the matrix is
rebuilt; the blanked zero cell in `STRUCTURE IMPEDANCE LOADING`.

**Numbers: agreement well inside engineering tolerance.** momwire is a B-spline
Galerkin solver and `nec2c` is pulse-basis point-matched, so they will never
agree digit for digit — and SimNEC does not need them to, since it reads two
numbers per `ANTENNA INPUT PARAMETERS` row and builds a Y matrix. Worst case
over every row of every table in all 30 fixtures, momwire 0.23.0 against
`nec2c 5b4az.ae6ty.1.17`:

| quantity | our bar | corpus worst | notes |
| --- | --- | --- | --- |
| `ANTENNA INPUT PARAMETERS` Z and I | 5 % | **2.83 %** | plus three explained outliers, below |
| `-YY` report-card currents | 5 % | **2.83 %** | 12.02 % on the `NEC2Daemon` deck's near-open port |
| current distribution (peak-normalised, complex) | 8 % | **6.00 %** | same distribution, segment for segment |
| `RADIATION PATTERNS` TOTAL gain | 0.5 dB | **0.12 dB** | |
| peak-gain direction | 1 step | **0 steps** | |
| near field, off the conductor | — | **0.7 % / 0.4°** | |

The three fixtures over 5 % are all one phenomenon — a small residual between
two large, nearly cancelling numbers — and each carries a test asserting the
identity that makes it benign: a 0.25 λ dipole with a +818 Ω loading coil at the
feed (`Re(Z)` agrees to 1.8 %, and the reactance gap is 1.0 % *of the coil*);
port 1 of your `NEC2Daemon` test deck, which is the centre gap of a full-wave
split dipole at |Z| ≈ 3.5 kΩ — a current null, and the known basis-sensitive
class — where the deck's other two ports agree to 0.4 %; and an `NT` deck where
the branch carries most of the current, so the *segment* current printed in
`STRUCTURE EXCITATION DATA` is a residual (12 %) while the *source* current
SimNEC actually reads agrees to 1.3 %.

One genuine bug fell out of that comparison, which is the argument for doing it
this way: two crossing wires share a segment midpoint exactly, and our
segment-to-element mapping had been position-only, so a crossed-dipole deck
printed one wire's port current on the other wire's segment — a 90° error
behind a perfectly plausible magnitude, invisible to every self-consistency
check.

**Live sessions: not yet.** Everything above is bench-tested against your
oracle's committed output, with a smoke script that runs decks through one
resident process exactly as `NEC2Daemon` does. Driving a real SimNEC session
end to end is the next step on our side, and we will report what breaks before
suggesting anyone else try it.

## Asks, smallest first

**1. Bless (or widen) the version-banner convention for third-party engines.**
`Execute.testCommand()` matches the first `-version` line against
`nec2c\.ae6ty\.(.*)` and feeds group(1) to `Double.valueOf`. The group is
greedy, so *any* non-numeric tail throws and is reported to the user as
"nec2c version too old" — the one message guaranteed to send them looking in
the wrong place. So we cannot say who we are in the probe. We currently answer:

```
nec2c.ae6ty.9.1
```

and carry our real identity in the printout banner, which no regex is anchored
to reach:

```
VERSION:nec2c.ae6ty.momwire.9.1
```

We picked `9.1` because `minimumNEC2CVersion` is currently `1.23` — which is
exactly the version of the `nec2c` 6p4d6 ships, so the floor evidently tracks
the bundled build and could rise. We would rather not squat on a number you may
want.

So: is there a form you would be willing to accept that lets a third-party
engine *name itself*? A tolerant parse that takes the leading numeric run and
ignores the rest would do it (`nec2c.ae6ty.9.1.momwire-0.23.0`), or a second
line in the probe output, or a separate vendor field. `setVersion()` already
stores and shows the whole trimmed line, so the display side is there — it is
only `Double.valueOf` on a greedy group that forces us to be anonymous. We are
happy to emit whatever you specify, and to gate it on a version so old builds
keep working.

**2. Confirm the error-reporting convention.** When a deck asks for something we
do not model, we report it in the printout and **always** still emit the `NX`
data-card echo, because `processResponse` blocks in `readLine()` with no
timeout and an engine that stays quiet hangs the UI rather than showing a
message. We copy the oracle's own prefix:

```
ERROR-NEC2C: <card> is not supported by this engine
```

deliberately *not* leading with the bare token `ERROR:`, which trips your
`NEC ERROR (1)` warning frame. Is that the shape you want, or would you rather
a third-party engine trip that frame so the user sees a dialog? Related: is
there anything on the Java side that notices a *stalled* engine, or is the
sentinel genuinely the only thing standing between a bad engine and a hung UI?

**3. The gain-vs-directivity question for `FieldStore`.** This one could make
plots differ without any number being wrong. `PROCESSINGPATTERN` and
`PROCESSINGNEARFIELD` fill `FieldStore`, but we cannot see who consumes it or
with what convention. Our `RADIATION PATTERNS` block normalises to the
**source's input power** — i.e. the `POWER GAINS` columns are *gain*, including
antenna losses. If whatever reads `FieldStore` assumes **directivity**
(normalised to radiated power), then for a lossless antenna the two are
identical and nothing shows, but a lossy one — ground losses, a loading coil,
resistive wire — plots systematically low or high by exactly its efficiency:
a 60 %-efficient antenna is 2.2 dB apart on the two conventions, with both
engines self-consistent and neither obviously wrong. NEC-2's own `RP 0` prints
power gain relative to input power, so we believe we match the oracle here;
what we want to know is what SimNEC *assumes* it is being handed, and whether
you would want an engine to be able to say which one it sent.

**4. How much do users touch `_NECBLOCK.Nearfield`?** We support `NE`/`NH`
rectangular grids in free space and over a perfect ground. We deliberately
refuse them over finite ground — the near field of a Sommerfeld half-space is
not an image field, and approximating it would be quietly wrong at exactly the
distances people care about. We also refuse the spherical form (`I1 = 1`),
although `WAITINGFORMETERSMETERSMETERS` accepts a `METERS DEGREES DEGREES`
header, which suggests something in SimNEC expects to see it. Both are real
work for us, and we would rather spend it where your users actually are: is the
near-field block a corner feature, or does it get used enough that lossy-ground
near fields matter?

## Two bugs we found in the process (yours to keep)

Reporting these regardless of where the engine conversation goes, since they
can freeze SimNEC with the *bundled* engine:

**A negative `#Proc` on the MP card hangs nec2c forever.** `MP -1 32` (and
`MP -3 -9`) never return — no output, no exit; we killed them at 12 s and
25 s. The advisory's own printing test is unsigned (`{0,1}` silent,
everything else printed, including negatives), so nothing catches the value
on the way in. Combined with the second item, this is a UI freeze.

**`Execute.processResponse` has no read timeout.** The Java side blocks in
`readLine()` until the NX data-card echo arrives; an engine that dies
mid-deck (or hangs, as above — or the `GN 2` + radial-screen refusal, where
nec2c aborts *without* the NX echo) leaves SimNEC waiting forever with no
recovery path we could find. A watchdog around the daemon read — or accepting
EOF as "engine gone, restart it" — would turn all of these into an error
dialog instead of a frozen session.

## What momwire would offer your users

- **A genuinely independent second opinion.** Different basis (B-spline
  Galerkin), different kernel, independently written — so agreement means
  something. momwire also ships a sinusoidal-basis solver as a built-in
  cross-check, which is much closer to NEC's own formulation.
- **One fill, N sources.** `NECSource.sensorLines` probes an N-port antenna
  with N excitation groups in a single deck, and stock `nec2c` refills and
  refactors the whole moment matrix for each — N fills for one matrix. We take
  the union of every group's ports, fill and factor **once** per geometry and
  frequency, and answer each group by back-substitution on the cached factors.
  A three-port deck costs one fill. This is where the multi-port probe gets its
  time back.
- **Speed on the dense assembly**, which is where MoM time actually goes, and
  an **H-matrix solver at O(N log N)** for structures where the dense matrix
  stops being reasonable — large arrays, long wires, dense meshes.
- **Sommerfeld ground on every solver**, not as a special path.
- **Active development**, MIT-licensed, with a public issue tracker; if you
  want something changed on our side, it is a conversation rather than a fork.

## If you want to try it

```bash
pip install antennaknobs
which momwire-nec2c            # paste this path into the NEC portal dialog
momwire-nec2c -version         # nec2c.ae6ty.9.1
```

Two caveats worth stating up front. The filename must keep `nec2c` in it —
`NEC2PortalDialog` decides the engine dialect on the lowercased file name, so a
tidier name is refused outright. And a momwire process is not a 2 MB C binary:
each carries NumPy/SciPy/momwire, ~90 MB resident before it solves anything,
plus the dense matrix and its factors. It is much quicker per deck once warm
(~2 ms for a small dipole, ~130 ms for a 106-segment design), so a smaller crew
keeps up with a larger one of the C engine — we suggest a NEC crew size of 4 on
a 16 GB machine.

We refuse, clearly and with the sentinel intact, anything we do not model:
surface patches (`SP`/`SM` — momwire is a wire solver), `PT`/`MP`/`IS`, `TL`
(we model the network fine; it is the `NETWORK DATA` layout for `TL` we have
never observed), `RP` modes other than 0, spherical `NE`/`NH`, near fields over
finite ground, and `GN` radial-wire ground screens.
