---
title: NEC-5 as a third engine
description: Run your licensed NEC-5 binary as an antennaknobs engine — deck generation, grounds, patterns, ports and loads — and close the cross-validation triangle.
---

NEC-5 is LLNL's modern rewrite of the NEC lineage — a mixed-potential
formulation with basis functions in the RWG family, released in 2019 and
distributed under an individual license. antennaknobs can drive it as a
**third engine** beside momwire and PyNEC: it writes NEC-5-dialect decks,
runs your licensed executable, and parses the printout back into the same
impedance, current, pattern and power-budget readouts every other engine
serves.

Why bother, when two engines already cross-check each other? Because the
three implementations share almost nothing: momwire's sinusoidal and
B-spline families, NEC-2's reduced/extended thin-wire kernels, and NEC-5's
mixed-potential formulation are independently derived and independently
coded. When all three agree, the agreement means something — and when they
split, the split is a finding (see [the solver
page](/reference/solver/) for how antennaknobs treats cross-engine
differences as data, not noise).

## Licensing, and where the engine will not run

NEC-5 is licensed software. antennaknobs **never bundles, downloads, or
hosts it**: the engine activates only when you point it at a binary you
license yourself, and the hosted simulator can never offer it (the license
forbids service use, and the hosted machines simply have no binary). What
antennaknobs generates and parses — decks and printouts — are yours to keep;
captured printouts in the test suite carry the LLNL-CODE-746721 citation as
End-User Reports.

Point the engine at your executable with one environment variable:

```bash
export NEC5_EXE=~/nec5/nec5cl        # your licensed binary
```

Everything below lights up exactly when `NEC5_EXE` resolves — the CLI
engine name, the workbench slot entry — and disappears when it doesn't.
If you run a local web instance with the variable set, the NEC-5 slot is
available to anyone who can reach that instance; keeping it off the open
internet is your call to make, the same as for any local service.

## From the command line

`nec5` joins the `--engines` roster:

```bash
# The triangle: momwire vs PyNEC vs NEC-5 on one design
python -m antennaknobs compare_patterns \
  --builders beams.moxon beams.moxon beams.moxon \
  --engines momwire pynec nec5 --fn triangle.png
```

Every solve is one run of the binary in a scratch directory — deck in,
printout out, parsed and discarded. Sweeps batch uniformly-spaced
frequencies into a single run using NEC-5's linear `FR` stepping.

## What is served, what refuses

| capability | status |
| --- | --- |
| Impedance, currents, frequency sweeps | served |
| Grounds | free space, PEC, and NEC-5's **native Sommerfeld** (`("finite", eps_r, sigma)`) |
| Radiation patterns | served (`compare_patterns`, the web far-field views) |
| Feeds | plain `Wire.ex`, network `Driven`, and `DrivenCurrent` via NEC-5's **native current source** (`EX 4` — NEC-2 has no equivalent) |
| Loads | `Load` branches (fixed-Z and series/parallel RLC) at the port |
| Wire material | conductor loss natively; insulation via the same distributed-inductance emulation momwire uses — NEC-5 dropped NEC-4's insulated-wire card |
| Power budget | input/radiated/wire-loss/efficiency, plus hemisphere average gain (the ground-absorption readout) |
| Transmission lines, two-ports, `ql`/`qc` loads, distributed ports, buried wires | **refuse loudly**, each naming what is unsupported |

Refusals are the design: NEC-5 either solves exactly what you asked or
tells you precisely why not — never a silently simplified model.

Two conventions worth knowing, both pinned from the NEC-5 User's Manual
during development:

- **Sources sit at segment ends** (knots), not segment centers as in
  NEC-2. The deck writer meshes fed wires with even segment counts so the
  feed lands exactly at the wire's middle knot — the same physical point
  the other engines drive.
- **The "fast" ground model is served as full Sommerfeld.** NEC-5 has no
  reflection-coefficient approximation (its `IPERF 0` *is* the Sommerfeld
  solution), so asking for the fast model gets the accurate one, and the
  applied-model readout says so.

## In the workbench

With `NEC5_EXE` set on the machine serving the web UI, **NEC-5 appears in
the slot A/B/C solver picker** like any other backend. The natural use is
A/B: the same design and mesh in two slots, momwire against NEC-5, readouts
side by side. NEC-5 solves are one subprocess per request with no resident
state — fine for check-this-snapshot comparisons, heavier than momwire's
in-process solves for live knob-dragging.

## Honest numbers

Cross-engine agreement on reference designs runs a few ohms of impedance
(the different formulations' genuine spread) and ~0.01 dB RMS on far-field
patterns. One documented exception, found the day the engine landed: at
very low heights over lossy Sommerfeld ground (≈0.05 λ), NEC-5's reactance
sits ~7 Ω away from the mutually-agreeing NEC-2 lineage while resistances
match — a real formulation difference in the close-ground interaction,
pinned in the test suite as a measured gap rather than averaged into a
tolerance. That is the cross-validation triangle doing its job.

## Importing NEC-5 decks

`@file.nec` import recognises NEC-5's edge-source `EX` spellings (a
negative segment number, or the end-selector field NEC-2 never uses) and
refuses them with the dialect named rather than silently shifting the feed
half a segment to the NEC-2 reading — the [NEC deck
import](/reference/nec-import/) page has the details. Decks in the common
NEC-2 subset load normally, and NEC5Engine itself accepts them as-is.
