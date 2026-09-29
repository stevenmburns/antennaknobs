---
title: NEC-4.2 as an external engine
description: Point antennaknobs at your own licensed NEC-4.2 console binary and get a NEC-4.2 tab — NEC-2's cards, plus buried wires over the Sommerfeld ground.
---

NEC-4.2 is the Lawrence Livermore National Laboratory code that followed NEC-2
and preceded NEC-5. It is **licensed software**: every user holds their own
licence from LLNL and builds or receives their own binary. antennaknobs
therefore ships none of it — not in the pip install, the frozen Windows
workbench, the Docker image or the hosted simulator — and drives the binary
**you** supply, the same way it drives [NEC-5](/reference/nec5/) and
[NEC-2](/reference/nec2/): a deck written to a temporary directory, your
executable run over it, its printout parsed back into the impedance, current,
power-budget and pattern readouts every other engine serves.

Because the licence covers your own use, the NEC-4.2 slot appears only where
the machine running the server can find your binary. The hosted simulator
never can, so it never shows the tab.

## Pointing at it

One environment variable, naming a console binary that takes the deck and the
printout as its two arguments (`nec42cl deck.nec deck.out`):

```bash
export NEC42_EXE=$HOME/nec42/nec42cl
antennaknobs sweep --builder specialty.buried_dipole --engine nec42 --ground finite
```

or `nec42_exe` under `[engines]` in
[`settings.toml`](/reference/web/#where-the-workbench-starts-settingstoml),
which the workbench and the command line both read. The variable wins over
the file.

`nec42` joins the engine roster only when the binary **runs**: antennaknobs
writes a one-wire deck, runs it once, and requires a parseable printout, so a
variable pointing at the wrong program is an absent tab rather than a tab that
fails at the first solve.

## What is different from the NEC-2 tab

NEC-4.2 reads NEC-2's cards and prints NEC-2's blocks, so the NEC-4.2 engine
is the NEC-2 engine with four differences:

- **Buried wires are served.** A design with wires below the ground plane,
  which the NEC-2 tab refuses, runs here over the Sommerfeld ground: the deck
  carries `GE -1`, NEC-4's flag for a ground with wires below it.
- **No table files.** NEC-4.2's Sommerfeld ground caches its tables to files in
  the working directory unless told otherwise, so every `GN 2` card is written
  with `NOFILE` — and each run happens in a fresh temporary directory that is
  removed afterwards, never the directory you started antennaknobs in.
- **A newer Sommerfeld evaluation** (`GN 3`) is available from Python as
  `NEC42Engine(builder, ground=..., sommerfeld=3)`; the tab and the command
  line use `GN 2`.
- **The MININEC-type ground is refused.** NEC-4.2 accepts the NEC-2 spelling
  (`GN 1` plus a `GD` card) but prints the perfect-ground pattern to the
  digit, so the soil the pattern should reflect off is never read. Use the
  NEC-2 or NEC-5 tab for that ground.

## What is refused, and why

Each refusal names itself rather than letting the binary answer:

- a wire that crosses the ground plane **mid-span** — split it at z = 0. With
  a segment end on the interface the binary gives the same answer as the split
  wire; with a segment straddling it, a very different number and no warning;
- a wire lying **in** the plane;
- buried wires over the perfect or the reflection-coefficient ground, neither
  of which has anything below the plane;
- a conductor that **ends on** the plane in a design that also has buried
  wires. The flag buried wires need gives that end no current there, so the
  conductor would read as open-circuited. A conductor that continues below the
  plane — a rise from a buried hub — is served;
- a graded mesh, a junction-node port and a series apex feed, for the NEC-2
  tab's reasons.

## Not yet

NEC-4.2's native current source (`EX 6`), graded meshes, a writer of its own
and a "Download NEC-4.2 deck" button are
[antennaknobs#1803](https://github.com/stevenmburns/antennaknobs/issues/1803).
Until then a current source is written as NEC-2's gyrator, which NEC-4.2 runs
unchanged.

## Citing it

Numbers produced with NEC-4.2 should cite the code: G. J. Burke and A. J.
Poggio, *Numerical Electromagnetics Code (NEC-4.2), Method of Moments*,
Lawrence Livermore National Laboratory, 2011, LLNL-CODE-491368.
