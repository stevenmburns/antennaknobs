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

The element mapping is validated against a real SimNEC installation (5.1a0):
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

**From the workbench**, with no terminal: open the **Files** view and pick the
**SimNEC** tab. It holds the same circuit for the design on screen — its knobs,
its frequency, its ground — with **Copy** and **Download** beside it, the way
the Source and engine-deck tabs work. That is the whole export step on Windows,
where the packaged workbench is the only interface there is. The tab is offered
for every design and needs no engine installed; a design SimNEC cannot carry
shows the same refusal the command prints, naming the construct in the way. The
Generator's frequency is the solve frequency and no sweep is armed — arming one
is `--sweep` below, on the command line.

Flags: `--freq` (MHz, default the design's), `--ground free | pec | finite |
finite:<eps_r>,<sigma> | mininec:<eps_r>,<sigma>` (the last as SimNEC's own
`MiniNECGround`), `--seg-per-wl` (SimNEC re-meshes at its own
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
for station files, the matching chain as a real `build_network()`. A
re-imported `.ssn` is a file deck like a `.nec`: its segment counts are what
the file says, so export → import → export is a fixed point — the export's
one-time re-mesh of a fed wire, which puts the feed exactly at its stated
position, does not repeat on every hop.

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
`--ground` hint (`PerfectGround`, `SommerfeldGround`, and `MiniNECGround` as
the [MININEC-type ground](/reference/web/#the-mininec-type-ground)), and wire conductivity applies per-wire. `NECUnits` is read
but not applied: in SimNEC it only sets the units wire dimensions are
displayed in, and the NEC cards are metres whatever it says. Values are read
the way SimNEC writes them: component values with its SI suffixes (`37.52p`,
`731.9n`, `2K`; its `g` is a wire gauge and is not a multiplier), and a wire
material by name (`NECOptions.mhosPerMeter = Conductivities.aluminum;`, with
SimNEC's own values). SimNEC re-meshes a deck's wires by its own rules before
solving, and antennaknobs solves the segments the deck gives, so the two can
differ by the mesh alone. Chain elements
translate back branch-for-branch through the same table as export, and a
chain element outside that set makes `network()` refuse rather than build a
station with a silently-missing tuner part.

**Which `.ssn` files import.** SimNEC lets a circuit hold its antenna two
ways, and antennaknobs reads one of them: **NEC cards between a `NEC2` line
and a `NECEND` line, inside a NETWORK element's script**. That is what
SimNEC's NEC portal accepts and what the export above writes, so every
round-tripped file qualifies.

The other way is a **script** — `NECWire` and `NECSource` calls against
declared variables, which SimNEC evaluates itself, leaving no cards in the
saved file. antennaknobs does not evaluate SimNEC's scripting language, and
says so by name rather than reporting a missing block. To bring such an
antenna in, either write its cards into a `NEC2 … NECEND` block in the NETWORK
script, or export a design from antennaknobs to `.ssn` and edit that.

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

momwire is the solver SimNEC calls — `pip install momwire` provides the
`momwire-nec2c` drop-in engine, and the portal lives in momwire itself.
Install, wrapper-script recipe, `--basis` selection, the probe/version
contract, and the dialect it serves are documented on momwire's own site:

- [Portal usage](https://momwire.dev/reference/portal-usage/)
- [The nec2 deck dialect](https://momwire.dev/reference/deck-grammar-nec2/)

The `.ssn` export/import above is antennaknobs' side of the pairing: build
or import the antenna here, hand SimNEC the circuit, and point SimNEC's
engine at momwire.

## Licensing

SimNEC is proprietary freeware. antennaknobs emits and parses its *open file
format* for interoperability — like emitting a NEC deck or a Touchstone
file — and copies none of SimNEC's bundled assets. The engine portal
(now part of momwire) is the same kind of interoperability in the other
direction: it reproduces the printout *layout* SimNEC's reader expects,
worked out from observed output, and contains no nec2c code.
