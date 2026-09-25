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
`MiniNECGround`), `--seg-per-wl` (skip the per-wire mesh pin described below
and ask for SimNEC's own re-mesh at `NECOptions.segmentsPerWavelength`
instead — for a convergence comparison against SimNEC's own density),
`--sweep` (bare for ±10% around the frequency, or `LO,HI`), `--name`, and
`--out` (default stdout).

**Antenna-only designs** export as SimNEC's canonical three-element circuit —
LOAD / NETWORK / GENERATOR — with the geometry riding inside the NETWORK
element as a NEC-portal script (the same `GW`/`FR`/`EX`/lumped-`LD` cards
[`export`](/reference/cli/#exporting-to-nec) emits, plus daemon directives
for ground and mesh density).

SimNEC's NEC2 reader ignores everything in that block but `GW`/`GM`/`GS`/`EX`/`NT`, so three more things travel as daemon directives rather than cards:
the wire **conductivity** as one `NECOptions.mhosPerMeter` for the whole
block (refused by name when the design's wires do not all share one value);
each wire's **mesh**, as a `$GW_<tag>.JamSegments(N)` carrying the deck's own
segment count, so SimNEC solves the mesh you asked for instead of
re-meshing it away — unless `--seg-per-wl` is given, which skips these and
asks for SimNEC's own density instead; and an **insulation jacket**, as
`NECOptions.Insulation("W7EL", thickness, εr, 0)` — the EZNEC correction
model, set inside `if (NECOptions.Engine == 2)` since it applies on SimNEC's
NEC2 engine only, with an `errorOutln` for any other engine. A jacket is one
value for every wire, so a design whose wires carry different jackets is
refused by name.

**Station designs** — a `build_network()` ladder of feedline, tuner arms, and
transformers — additionally emit the chain as SimNEC circuit elements in
cascade order:

| antennaknobs branch | SimNEC element | carried values |
| --- | --- | --- |
| `TL` | `SERIES_TLINE` | Zo, VFnom, length (ft), k1/k2 matched-loss coefficients (dB/100 ft = k1·√f + k2·f — the same cable-table convention both sides), loss model pinned to `k0k1k2` |
| `TwoPort` L/C arm | `SERIES_IND` / `SERIES_CAP` | H / F, component Q quoted at the export frequency |
| `Shunt` L/C leg | `SHUNT_IND` / `SHUNT_CAP` | H / F, Q likewise |
| ideal `Transformer` | `TRANSFORMER2` (`Mdl ideal`) | turns ratio (SimNEC's N is the antenna:generator voltage ratio — handled internally, validated live) |
| `Load` off the fed segment (traps) | SimNEC's own `NECSource` load on the `$GW_<tag>` wire, at the load's segment centre | R/L/C, a fixed `z`, series or parallel |
| `Load` on the fed segment | `SERIES_IND` / `SERIES_CAP` between the antenna and the generator (SimNEC turns the `EX` card into its own source there, so the load has to be a series circuit element instead) | H / F |
| self-tuning `l_network_tuner(tune_to=…)`, `"low"` / `"high"` | `XMATCH` (the LC matching component, `mode auto`) | `pass`, `R` = the target (`X` 0), `Qc` / `Ql`, `MHz` = the tune frequency |

A self-tuning tuner exports as SimNEC's own element, not as numbers: SimNEC
tunes it against its antenna solve, as antennaknobs tunes it against its own,
and importing the file gives the same tuner back. What that element cannot
say is refused by name: a T network, `"ll"` / `"cc"` parts, component ranges,
and a tuner with a fixed shunt side that found no match (SimNEC's automatic
element picks its side, and would). For those, `--freeze-tuners`
(`freeze_tuners=True`) tunes the box first and writes the parts it chose as
ordinary `SERIES_*` / `SHUNT_*` elements, which import back as fixed values.

### What refuses to export — and why

SimNEC's cascade elements are **purely differential**: there is no
common-mode knob on its transmission line. A design whose physics lives in
the common mode — a `BalancedLine` with `zcomm`, a `FloatingBalun`, the
balanced tuners built from them — cannot be faithfully represented, and the
exporter raises a clear error naming the offending branch instead of
silently dropping the common mode and emitting a confidently-wrong circuit.
The same applies to non-ladder topologies, current sources, lossy
transformers, and distributed (finite-gap) feed ports. A **finite-Q** `Load`
is refused by name too: SimNEC's series elements take a fixed R/L/C, not a Q
that would need re-deriving per frequency. And a `Load` that lands on the fed
segment can only leave as a series L and/or C (the row above) — a resistor, a
fixed `z`, or a parallel pair there is refused by name, since SimNEC's own
source already owns that spot. About four in five catalog designs export; the
refusals tell you exactly what construct is in the way.

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
MHz** (in SimNEC the deck's `FR` card is advisory), the Generator's own sweep
expression is read (`14 : 14.35 : 0.025`, lin or log spacing honoured) and
becomes the design's measurement band, the daemon ground call surfaces as a
`--ground` hint (`PerfectGround`, `SommerfeldGround`, and `MiniNECGround` as
the [MININEC-type ground](/reference/web/#the-mininec-type-ground)), and wire conductivity applies to every wire alike, one value for the circuit. `NECUnits` is read
but not applied: in SimNEC it only sets the units wire dimensions are
displayed in, and the NEC cards are metres whatever it says. `NECOptions.fieldStep`
(SimNEC's far-field display step, in degrees) is likewise read and accepted
quietly rather than reported as skipped — it is a display resolution, and no
solved number depends on it — though a malformed value still refuses. Values
are read the way SimNEC writes them: component values with its SI suffixes (`37.52p`,
`731.9n`, `2K`; its `g` is a wire gauge and is not a multiplier), and a wire
material by name (`NECOptions.mhosPerMeter = Conductivities.aluminum;`, with
SimNEC's own values). An automatic `XMATCH` imports as a self-tuning
[`l_network_tuner`](/concepts/station-modelling/), which tunes for the solving
engine's own antenna impedance; SimNEC's `MHz 0` (retune at every frequency)
tunes once, at the Generator's frequency, and the import note says so.

A `$GW_<tag>.JamSegments(N)` is honoured **exactly**: the file's N replaces
that wire's `GW` count and pins it there, so no engine's even-count rule
moves it. An attachment that JamSegments leaves off a segment site — a feed
at the middle of an odd-count wire, say — is fed exactly where it is by
splitting the wire at that point, never snapped to a neighbouring site.
`JamSegments(0)` means "auto-segment as usual", so the `GW` count stands,
unpinned. Short of that, SimNEC still re-meshes every wire by its own rules
before it solves, so its numbers differ from an import's by the mesh alone;
for a same-mesh comparison, import `lastConstructedNEC.nec` from
`~/.SimNEC/<version>/` instead — the deck SimNEC actually solved.

Each SimNEC block is its own **measurement plane**: the Generator is `"rig"`
(the far end of the feed system, not the antenna), the deck's fed wire is
`"feed"` (the antenna's own terminals) — the same two names EZNEC's virtual-wire
idiom uses in the [NEC importer](/reference/nec-import/) — and every chain
block in between gets a node of its own, named after its label, so every
block SimNEC reports an impedance at is a measurement plane here too.

Chain elements
translate back branch-for-branch through the same table as export, plus one
import-only case: a `SERIES_Z` — SimNEC's fixed complex impedance — becomes a
frequency-independent 2-port `Admittance`. A `SERIES_TLINE`'s `Mdl simplified`
loss model (SimNEC's default: one dB/100-length figure at one frequency) is
read and kept as the matched-loss coefficient it implies, exact at that
frequency; any other line model is refused by name rather than approximated.
A chain element outside the translated set makes `network()` refuse rather
than build a station with a silently-missing tuner part.

**Which `.ssn` files import.** SimNEC lets a circuit hold its antenna two
ways, and antennaknobs reads one of them: **NEC cards between a `NEC2` line
and a `NECEND` line, inside a NETWORK element's script**. That is what
SimNEC's NEC portal accepts and what the export above writes, so every
round-tripped file qualifies. Either keyword line may carry a trailing `//`
comment (`NEC2  // ====`), and so may a card inside the block.

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

### dcl constants are knobs

SimNEC evaluates every field of a NEC card as an expression, so a block can
name constants the script declares above `NEC2` — which is how AC6LA's
examples convert a 4nec2 deck's `SY` cards ("replace all SY with dcl"):

```
dcl hgh = 50*0.3048 ; // Height (50 feet)
dcl len = 2.5601*2  ; // Driven element half-length
NEC2  // ====================
GW  2  19  -len  0  hgh  len  0  hgh  rad
...
NECEND  // ====================
```

Such a file keeps its parametrisation, the way a `.nec` deck's
[SY constants](/reference/nec-import/#sy-constants-are-knobs) do. Each
**constant** the cards read — a `dcl name = ...;` or `$name = ...;` statement
of its own, outside any `{ }` block, assigned nowhere else — whose expression
names no other constant becomes the knob `dcl_<name>` (`tmp_<name>` for a
`$name` temporary). Its label is the name as the script spells it (SimNEC
names are case-sensitive, so `Xc` stays `Xc`), and its tooltip is the line's
`//` comment. A constant that names another follows the knobs; one that
reaches only the `FR` card, or no card the design is built from, is not a
knob, and the import note says which and why. At its defaults the design is
the import, bit for bit, and moving a knob builds exactly what editing that
`dcl` line by hand would. As with a deck, the topology is frozen at the
file's own values: a value that makes wires meet or part, puts a wire end
into the ground plane, or collapses a wire is refused, naming the knob.

The expressions are evaluated with **SimNEC's own rules**, not 4nec2's —
measured by running probe circuits through SimNEC:

- trig (`Sin`, `Cos`, `Tan`, `Asin`, `Acos`, `Atan`) is in **radians**
  (4nec2's is in degrees);
- a trailing letter on a number is SimNEC's SI suffix, in any card field
  whether or not the block names a constant: `500m` is 0.5, `1.054u` is
  1.054e-6. 4nec2's unit suffixes (`mm`, `ft`, `in`) and SimNEC's wire gauge
  `g` are refused by name;
- unary minus binds tighter than `^`, so `-2^2` is 4, `2^-1` is 0.5, and
  `2^3^2` groups left, to 64; `**` is `^`, `%` takes the sign of the
  dividend (`-7%3` is −1), and `Int` truncates toward zero;
- in a card field, a `+` or `-` right after a **number** ends the field:
  SimNEC reads `12-dz` as the two fields `12` and `-dz`, and refuses the
  card when that overflows it. After a name the sign stays in the field
  (`hgh-sln` is one field). The import refuses such a field rather than
  read it differently from SimNEC; write `(12-dz)`, or move the sum into a
  `dcl`;
- names are case-sensitive, built-ins included: `Pi`, `mpf`, `fpm`, `Sqrt`,
  `Abs`, `Int` are read as spelled, and `sin(30)` is refused with "did you
  mean 'Sin'?", as SimNEC refuses it.

Anything else — complex values (`0+j50`), `|||`, `/_`, comparisons, member
access such as `G.MHz`, other functions — is refused by name. So is a card
that names something the script never sets as a constant: an undefined name
is an error, never a silent zero. The one exception is the `FR` card, which
SimNEC treats as advisory (the Generator's MHz drives the solve): an `FR` that
names an undefined constant — AC6LA's 3-el Yagi names a `freq` whose `dcl` is
commented out — is dropped, and the note says so.

Constants used only outside the NEC block, such as the `L`/`C` values of an
N-block trap (`R2 (L(L_23, Q_23) ||| C(C_23)) r2a r2b;`), are not read, and
the statements that use them are listed as not applied, as before.

### Element parameters are knobs

A bare name in the script — no `dcl`, no `$` — is a **parameter** of the
circuit element: SimNEC adds it to the element, lists it with the element's
other values, and saves its value in the file. AC6LA's variable-length
dipole is the whole idiom:

```
len;
segs;
NEC2
GW 1 11 0. 0. 9. 0. len 9. 0.001
...
NECEND
$GW_1.JamSegments(segs);
```

with `len` = 10.2 and `segs` = 30 saved on the element. Each such parameter
the cards read becomes the knob `par_<name>` at its saved value, published
exactly as a `dcl` constant is: labelled with its spelling, its bare
statement's `//` comment the tooltip, bit for bit the import at its
defaults, the topology frozen, a `dcl` constant that reads it following it.
The prefix is `par_`, not `dcl_`, because the value lives in a different
place in the file — on the element rather than in a `dcl` line — and a saved
setting names the one it sets.

A parameter may also set a **segment count**: `JamSegments` takes an
expression, so `JamSegments(segs)` makes `segs` a whole-number knob for that
wire's count, honoured exactly as a literal count is. A count below 1 or a
fraction is refused, naming the parameter — a literal `JamSegments(0)` still
means "auto-segment as usual", but a knob dragged to 0 does not silently
switch the wire back to its `GW` count.

Only an **input** is a knob. SimNEC saves a parameter's value whether the
user set it or the script computed it — AC6LA's trap dipole saves
`Trap23 = R2.z;` as a parameter too, and his Yagis save a `SegCnt` counted in
an `at(finalValue) { }` block — so a parameter the script assigns anywhere is
an output: never a knob, and a card that reads one is refused by name. So is
a name that is neither a constant nor a saved parameter. A
`NECOptions.segmentsPerWavelength` that names a parameter (`= segsWL`, in
AC6LA's Synth conversions) takes its saved value, which, like any
`segmentsPerWavelength`, only feeds the mesh note.

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
