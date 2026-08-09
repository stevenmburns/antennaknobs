---
title: SimNEC round-trip
description: Export any design — antenna or whole station — as a SimNEC .ssn circuit, load .ssn files back as designs, or run momwire as the NEC engine behind SimNEC itself.
---

[SimNEC](https://ae6ty.com/smith_charts/) (AE6TY) is the successor to
SimSmith: a Smith-chart station tool with NEC2 embedded behind its own MNA
circuit solver. antennaknobs speaks its native `.ssn` circuit file in **both
directions** — export a design for SimNEC to solve, or load a SimNEC circuit
as a design — so the same antenna and matching chain can be checked by two
independently written solvers without hand-entering geometry or component
values in either direction.

The element mapping is validated against a real SimNEC installation (6p4d6):
generated stations load with correct values, reproduce the reference
impedance, and survive a SimNEC load/save round-trip without drift.

## Exporting: design → .ssn

```bash
# Antenna alone, free space
python -m antennaknobs.simnec_export dipoles.invvee --out invvee.ssn

# A whole station — feedline, tuner tee, and the antenna in one circuit
python -m antennaknobs.simnec_export wire.doublet_ladder_tuner --out station.ssn

# Over real ground, with an armed SimNEC frequency sweep
python -m antennaknobs.simnec_export loops.skyloop_lmatch \
    --ground finite:13,0.005 --sweep 6.9,7.3 --out skyloop.ssn

# A NEC card deck converted straight to a SimNEC circuit
python -m antennaknobs.simnec_export @measured/invvee.nec --out invvee.ssn
```

Flags: `--freq` (MHz, default the design's), `--ground free | pec | finite |
finite:<eps_r>,<sigma>`, `--seg-per-wl` (SimNEC re-meshes at its own
segments-per-wavelength — the deck's segment counts are advisory there),
`--sweep` (bare for ±10% around the frequency, or `LO,HI`), `--name`, and
`--out` (default stdout).

**Antenna-only designs** export as SimNEC's canonical three-element circuit —
LOAD / NETWORK / GENERATOR — with the geometry riding inside the NETWORK
element as a NEC-portal script (the same `GW`/`FR`/`EX`/lumped-`LD` cards
[`export`](/reference/cli/#exporting-to-nec) emits, plus daemon directives
for ground and mesh density).

**Station designs** — a `build_network()` ladder of feedline, tuner arms, and
transformers — additionally emit the chain as SimNEC circuit elements in
cascade order:

| antennaknobs branch | SimNEC element | carried values |
| --- | --- | --- |
| `TL` | `SERIES_TLINE` | Zo, VFnom, length (ft), k1/k2 matched-loss coefficients (dB/100 ft = k1·√f + k2·f — the same cable-table convention both sides), loss model pinned to `k0k1k2` |
| `TwoPort` L/C arm | `SERIES_IND` / `SERIES_CAP` | H / F, component Q quoted at the export frequency |
| `Shunt` L/C leg | `SHUNT_IND` / `SHUNT_CAP` | H / F, Q likewise |
| ideal `Transformer` | `TRANSFORMER2` (`Mdl ideal`) | turns ratio (SimNEC's N is the antenna:generator voltage ratio — handled internally, validated live) |
| `Load` on a real port (traps) | stays an `LD` card in the deck | R/L/C |

### What refuses to export — and why

SimNEC's cascade elements are **purely differential**: there is no
common-mode knob on its transmission line. A design whose physics lives in
the common mode — a `BalancedLine` with `zcomm`, a `FloatingBalun`, the
balanced tuners built from them — cannot be faithfully represented, and the
exporter raises a clear error naming the offending branch instead of
silently dropping the common mode and emitting a confidently-wrong circuit.
The same applies to non-ladder topologies, current sources, lossy
transformers, and distributed (finite-gap) feed ports. About four in five
catalog designs export; the refusals tell you exactly what construct is in
the way.

Component `Q` deserves one note: antennaknobs models `ql`/`qc` as
frequency-independent while SimNEC quotes Q at a frequency, so a lossy
component is exact at the export frequency and Q-model-approximate across a
SimNEC-side sweep. `Q = 0` means ideal (lossless) on both sides.

## Importing: .ssn → design

The reverse direction loads a SimNEC circuit — one you built in SimNEC, or
one that came back modified from a round-trip — as antenna geometry plus,
for station files, the matching chain as a real `build_network()`:

```bash
# Any subcommand takes an @file.ssn spec, like @file.nec
python -m antennaknobs draw    --builder @station.ssn
python -m antennaknobs sweep   --builder @station.ssn --swr
python -m antennaknobs compare_patterns --builders dipoles.invvee @station.ssn

# .ssn -> NEC deck conversion falls out of the pair
python -m antennaknobs export --builder @dip.ssn --out dip.nec
```

What the importer honours: the solve frequency comes from the **Generator's
MHz** (in SimNEC the deck's `FR` card is advisory), an armed Generator sweep
becomes the design's measurement band, the daemon ground call surfaces as a
`--ground` hint, wire conductivity applies per-wire, and `NECUnits` scales
geometry to metres with NEC's own scaling semantics. Chain elements
translate back branch-for-branch through the same table as export, and a
chain element outside that set makes `network()` refuse rather than build a
station with a silently-missing tuner part.

In Python the same machinery is `read_ssn(self, "circuit.ssn")` /
`parse_ssn(text)` — `read_ssn` ships a `.ssn` next to a
[user design](/reference/cli/#allowing-user-designs-to-run) in
`~/.antennaknobs/designs/`, with the same folder confinement as `read_nec`.

## The round-trip guarantee

Export → import is pinned by identity tests: a transformer's turns ratio and
every element value of the validated ladder-tuner cascade (line Zo/VF/length,
loss coefficients, both capacitors, coil and its Q) survive the full cycle
unchanged. If the two sides ever disagree about a convention, the suite
fails rather than the circuits quietly diverging.

## Using momwire as SimNEC's engine

The round-trip above hands SimNEC a file and lets SimNEC's own bundled NEC2
solve it. There is a second, tighter connection: **momwire can be the solver
SimNEC calls.**

SimNEC does not link NEC2 — it shells out to a `nec2c` executable, starts one
copy, and keeps it. Decks go down that process's stdin framed by an `NX` card,
printouts come back on stdout, and SimNEC's MNA circuit solver reads two
numbers per feedpoint out of each printout to build the antenna's Y matrix.
`antennaknobs.nec_portal` is a drop-in for that process, with momwire's
B-spline Galerkin solver behind it. Your Smith chart, tuner, and sweeps stay
SimNEC's; the electromagnetics become momwire's.

:::caution[Validated live — but unblessed upstream]
This has driven a real SimNEC session end to end (Windows, SimNEC 6p4d6):
knob tracking, sweeps, patterns, and multi-source phased-array examples, with
a validated station circuit reading within a few percent of the bundled
nec2c through a high-Q tuner, pattern levels agreeing to ~0.01 dB once the
gain/directivity conventions are lined up, and SimNEC's own 4-source
Lindenblad example matching to 1 Ω of reactance. Under the session sits a
bench corpus of 40 captured deck/printout pairs reproduced
layout-identically. It is still not something SimNEC's author has reviewed
or endorsed, and no part of SimNEC knows momwire exists — treat it as a
cross-check you can run yourself, not a supported configuration.
:::

### Pointing SimNEC at it

Install antennaknobs anywhere with a Python environment; the package ships a
console script:

```bash
pip install antennaknobs
which momwire-nec2c          # e.g. ~/.venvs/ak/bin/momwire-nec2c
momwire-nec2c -version       # NEC2momwire.<major>.<minor>
```

Then open SimNEC's NEC portal dialog and paste that path in as the NEC
command. Two rules decide whether SimNEC accepts it, and both are worth
knowing because the failure modes look nothing like their causes:

- **The filename must contain `nec2c`.** SimNEC picks the engine — the deck
  dialect, the daemon protocol, the printout parse offsets, all of it — off
  the command's file name, lowercased. A name with none of `nec2c` / `nec5` /
  `nec42` in it is refused outright with *NO NEC Command Available*, and the
  version probe cannot override the choice. That is why the script is called
  `momwire-nec2c` and not something tidier; if you wrap it in a shell script
  or a symlink, keep `nec2c` in the name (and keep the substring `out` out of
  the path — SimNEC refuses any command path containing it).
- **The version probe answers with our real name.** SimNEC runs
  `<command> -version` and reads the first line. The portal answers
  `NEC2momwire.<major>.<minor>` — SimNEC's own engine-family form, whose
  `NEC2` prefix declares the deck dialect while leaving the rest of the text
  free (sanctioned by SimNEC's author). SimNEC shows that string in the
  portal dialog's NECVersion row, stamps it as a `CM version` comment card on
  every deck it sends, and stores it in saved circuits — so a momwire session
  is identifiable as one everywhere the version travels. For a SimNEC build
  too old to know the `NEC2…` form, `--legacy-probe` on the portal command
  line restores the old `nec2c.ae6ty.9.1` masquerade; nothing else about the
  session changes either way.

Before a live session, run the built-in smoke — it needs no checkout, spawns
one resident copy of itself, runs embedded decks through it the way SimNEC
does, and prints PASS or FAIL:

```bash
momwire-nec2c --selftest
```

### Choosing the physics: `--basis`

SimNEC launches engines through the shell, so the command you paste into the
portal dialog can carry arguments. The portal accepts a `--basis` flag:

```text
momwire-nec2c --basis bspline                        # the default
momwire-nec2c --basis bspline-d1                     # degree 1 (tent basis) — d1-vs-d2 convergence check
momwire-nec2c --basis sinusoidal                     # closest to NEC-2's own formulation
momwire-nec2c --basis sinusoidal-galerkin            # the same basis, tested variationally
momwire-nec2c --basis sinusoidal-galerkin-converged  # recommended for near-open high-Q feeds
momwire-nec2c --basis hmatrix                        # same physics, hierarchical (ACA) solve
momwire-nec2c --basis arrayblock                     # same physics, element-block/FFT solve — large arrays
```

Four of those are a ladder: NEC-2 itself, then `sinusoidal` — the three-term
basis, point matched, with NEC's own delta-gap source, so it answers "does
this reproduce NEC-2's behaviour, mesh walk and all" — then the Galerkin
variants and the B-spline default, which answer "what does a better-converged
basis say". There is no `sinusoidal-converged`: a zero-width gap cannot be
expressed under point matching (momwire#212), and the flag does not offer a
name the solver would refuse. `bspline-d1` sits on a different axis — the
same B-spline physics at degree 1, so pairing it with the default is the
cheapest d1-vs-d2 convergence check a SimNEC user can run. `hmatrix` and
`arrayblock` are another axis again — not different physics but a different
*solve*: the same B-spline operator held compressed and solved iteratively, so
a large array answers without a dense fill. `arrayblock` is the one to reach
for on a repeated-element array (identical elements on a regular lattice
become an FFT convolution over the element grid); it degrades to `hmatrix`'s
hierarchical solve on a deck with no repeated structure, so it is safe to
leave on. Their answers should match `bspline`'s — if they do not, the deck is
telling you something about conditioning, not about basis choice.

How much it buys, measured on a 2017 quad-core laptop over a square lattice of
half-wave dipoles at 0.6 λ pitch: a 24×24 array (576 elements, 5184 unknowns)
takes 8.0 s and 5.3 GB with the dense fill and **0.77 s and 137 MB on
`arrayblock`**, and a 32×32 array will not solve at all inside an 8 GB budget
— it needs about 15 GB — while `arrayblock` answers it in 1.3 s and 173 MB. At
48×48 (2304 elements) `arrayblock` takes 3.0 s and 272 MB where `hmatrix`
needs 158 s and 2.0 GB. The crossover is around 8×8; below that the dense fill
is the cheaper tool. Agreement with the dense solve stays within a few parts
in 10⁶ relative everywhere dense can still be run. Full ladder, method and caveats:
[`docs/status/2026-08-09-arrayblock-lattice-benchmark.md`](https://github.com/stevenmburns/antennaknobs/blob/main/docs/status/2026-08-09-arrayblock-lattice-benchmark.md).

**Paste two portal entries that differ only in `--basis` and you have
cross-basis validation inside SimNEC itself** — switch engines from the
dialog and watch whether the answer holds. The printout banner records which
physics answered (`VERSION:...momwire.9.1+sgc`), a mistyped basis fails the
version probe loudly at configure time, and the `-converged` variant is the
documented setting for feeds near a current null — the one antenna class
where bases legitimately disagree at coarse segmentation.

### What works

Everything SimNEC's portal actually emits for wire antennas:

| | |
| --- | --- |
| Feedpoint impedance | `EX 0` voltage sources, one or many, and the `YY` report card SimNEC probes multi-port antennas with |
| Frequency sweeps | multi-point `FR`, the whole sweep in one deck |
| Geometry | `GW` wires with `GM` / `GX` / `GR` / `GS` / `GA` / `GH` transforms |
| Ground | free space, `GE ±1` perfect ground, `GN 0` reflection-coefficient and `GN 2` Sommerfeld finite ground |
| Loading | `LD 0` / `1` / `4` / `5` — series RLC traps, distributed loading, wire conductivity |
| Patterns | `RP 0` far-field grids, gain and polarisation, normalised to input power, at a range or in the gain-only `RFLD = 0` form |
| Cliffs | `RP 2` linear and `RP 3` circular cliffs — the second medium and edge geometry from a `GD` card (or from `GN`'s own `F3`–`F6`), selected per segment at its own reflection point |
| Near fields | `NE` / `NH` rectangular grids in free space or over perfect ground |
| Networks | `NT` two-port admittance branches and `TL` transmission lines between segments |
| Housekeeping | `EK` extended-kernel, `MP` multicore hints, `PT` print control — accepted and echoed exactly as nec2c does (advisory where momwire's own physics governs) |

One thing is faster than the engine it replaces, structurally. SimNEC probes an
N-port antenna by sending N excitation groups in one deck, and a stock nec2c
refills and refactors the whole moment matrix for each — N fills for one
matrix. The portal takes the union of every group's ports, fills and factors
**once** per geometry and frequency, and answers each group by back-substitution
on the cached factors. A three-port deck costs one fill, not three.

The deck is not the boundary either. The protocol is stateless — a sweep
arrives as N separate decks, each re-sending the whole geometry — but the
engine remembers: a solved structure is kept under a key built from everything
that decides its moment matrix (geometry after transforms, ground, loading,
port placement, network branches, kernel flag, basis), so a knob dragged back
to a value already probed, a restarted sweep, or the same antenna handed to
another engine in the crew is answered without parsing, meshing or filling
anything. The same structure at a *new* frequency reuses the mesh and pays only
the fill. The biggest bench deck (106 segments) takes ~150 ms cold and ~11 ms
on the repeat, and what is left in the repeat is the printout itself.

### What refuses — cleanly

A deck the engine cannot model is *reported and stepped over*, never guessed
at: the printout names the offending card and why, and still carries the `NX`
sentinel that SimNEC blocks in `readLine()` waiting for. (An engine that dies
or forgets the sentinel hangs SimNEC's UI with no timeout, which is strictly
worse than an error message.) The daemon survives it and runs the next deck.

The refusal leads with a line whose first word is exactly `ERROR:` — that is
what trips SimNEC's own `"NEC ERROR (1)"` warning frame, so a refused deck
shows up as a visible warning instead of a session that quietly loaded
nothing. (Earlier builds used a differently-shaped prefix specifically to
avoid tripping that frame; issue #829 reversed that on Ward's own say-so
after a live session hit it — a refused patch-antenna design left the user
staring at an empty result with no indication why.)

Refused today:

- **Surface patches** (`SP`, `SM`) — momwire is a wire solver.
- **`IS`** — NEC-4.2 wire insulation; momwire's insulation model is not
  wired through the portal.
- **`RP` mode 1** — the surface wave. It prints a different table altogether
  (`RADIATED FIELDS NEAR GROUND`, with an `E(RADIAL)` column) and needs a
  surface-wave kernel this engine does not have.
- **`RP` modes 4–6** — radial-wire ground screens, refused for the same
  reason `GN`'s radial count is. Modes 5 and 6 carry a cliff as well, but the
  screen is what stops them.
- **Spherical `NE` / `NH` grids** (`I1 = 1`) — rectangular only.
- **Near fields over finite ground** — the near field of a Sommerfeld
  half-space is not an image, and pretending otherwise would be quietly wrong.
  Far-field patterns over finite ground are fine.
- **`GN` radial-wire ground screens** (a non-zero radial count) — momwire has
  no screen model, and ignoring the field would silently change the answer.

### How many engines to run

SimNEC keeps a crew of engine processes and hands decks out among them. A
momwire process is not a 2 MB C binary: each one carries NumPy, SciPy and
momwire — about 90 MB resident before it solves anything — plus the dense
complex matrix and its factors, which grow as the square of the segment count.
It is also much quicker per deck once warm (a 106-segment design solves in
~130 ms, a small dipole in ~2 ms), so a smaller crew keeps up with a larger one
of the C engine.

Its memory of past structures is capped, per process, at a few hundred MB, and
a full cache costs a re-solve rather than a failure — so the worst case for a
crew of four stays well inside a 16 GB machine. In practice a bench-sized
design's entry measures tens of kilobytes, so the cap is a safety net for
array-scale work rather than something a session reaches.

**On a 16 GB machine, set the NEC crew size to 4.** Larger crews buy little,
because the win here is the single fill per geometry rather than parallelism
across decks, and they multiply the per-process floor by the segment count you
are least expecting.

## Licensing

SimNEC is proprietary freeware. antennaknobs emits and parses its *open file
format* for interoperability — like emitting a NEC deck or a Touchstone
file — and copies none of SimNEC's bundled assets. The engine portal is the
same kind of interoperability in the other direction: it reproduces the
printout *layout* SimNEC's reader expects, worked out from observed output,
and contains no nec2c code.
