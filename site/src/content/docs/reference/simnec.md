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

A design with a wire **in the soil** (an end below z = 0 over real ground)
exports too. The `NEC2` block is still NEC-2 card syntax, which SimNEC's
NEC-5 and NEC-4.2 engines read with the soil around the buried wire; its NEC-2
engine cannot model a buried wire, so the script stops there with an
`errorOutln` naming the wire. For the same reason such a design's jackets go
per wire, as `$GW_<tag>.Insulation(thickness, εr, loss tangent)` after the
block, the form SimNEC's NEC-5 engine applies, rather than the W7EL directive.

**Station designs** — a `build_network()` ladder of feedline, tuner arms, and
transformers — additionally emit the chain as SimNEC circuit elements in
cascade order:

| antennaknobs branch | SimNEC element | carried values |
| --- | --- | --- |
| `TL` | `SERIES_TLINE` | Zo, VFnom, length (ft), k0/k1/k2 matched-loss coefficients (dB/100 ft = k0 + k1·√f + k2·f — the same cable-table convention both sides), loss model pinned to `k0k1k2` |
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

A **feed or load at a junction knot** (a `PortAtVertex`, such as an apex feed,
or a source at the end of a feed wire where the next wire starts) exports as
SimNEC writes one itself: `$feed = NECSource({w2, gnd}, $GW_<tag>, 100)` at
that wire's end, with no `EX` card, and a knot load as a `NECSource` load at
the same place. The script stops SimNEC's NEC-2 engine by name, because NEC-2
has no source at a knot. A station chain on such a design, and a
junction-node port (`PortAtEnd`, a shunt attachment at a node), are still
refused by name.

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
becomes the design's measurement band (a sweep saved as `(y)`, which SimNEC
shows suspended when a file reopens, is the same sweep as `y`; only `n` is
off), the daemon ground call surfaces as a
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
`~/.SimNEC/<version>/` instead — the deck SimNEC actually solved. In a file
with `NECSource` loads, though, that deck carries each load as one more
source, which SimNEC then terminates in its own circuit, so the deck on its own
is not the loaded antenna.

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
frequency. A `k0k1k2` line, or a named cable from SimNEC's database (an AC6LA
table entry such as Belden 8259 RG-58A/U), is read from the Zo, velocity
factor and k0/k1/k2 that SimNEC saves on the element. It is solved as AC6LA's
Johnson line, the model SimNEC, TLDetails, Zplots and AutoEZ all use; see
[a station on any antenna](#a-simnec-station-on-any-antenna). A named cable
saved without its coefficients is refused by name rather than approximated.
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

**Feeds, loads and jackets written in the script.** Around the block, the
importer also reads SimNEC's own statements for them:

- a feed as a `NECSource` on a declared port's nodes
  (`$src = NECSource({w2, gnd}, $GW_2, 100);`), when the block has no `EX`;
- a load as N-block element lines on two nodes (`R1 (1000 ||| L(2u)) a b;`,
  or `Ra 4150 a b;`, `La 26.3u a b;`, `Ca 4.91p a b;`, which on the same two
  nodes are in parallel) plus the `NECSource` attaching them, or written
  inline as `NECSource(R(4150) ||| L(26.3u) ||| C(4.91p), $GW_3, 100)`;
- a jacket per wire, `$GW_<tag>.Insulation(thickness, εr, loss tangent)`,
  over the circuit-wide `NECOptions.Insulation(...)`.

The script is read as SimNEC reads it, statement by statement: a statement
may run over several lines, and `//` and `/* … */` comments may sit anywhere.
Values are evaluated, not matched. A value, a place along the wire, or the
wire itself may come from a constant the script sets once (`$r = 4150;` then
`R($r)`; `$w = $GW_3;` then `NECSource(…, $w, 100)`), and may be arithmetic
(`R(4000+150)`, `100*5.5/21`), with SimNEC's suffixes and `j` prefix. One
thing is refused as ambiguous: a product beside `|||` without parentheses
(`2*R(500) ||| L(2u)`), since SimNEC's own notes give `|||` two different
precedences against `*`.

**Conditions, loops and functions.** The script's control flow is evaluated
where it can be, and never guessed at where it cannot:

- An `if (…) … else …` whose condition is a constant reads only the branch it
  takes, and a constant set in that branch counts as set once — a knob, if
  the cards read it. A condition may use numbers, arithmetic, comparisons,
  `&&` / `||` / `!`, the script's own functions and names the whole script
  sets once, before the `if`. A knob in a condition is read at the knob's
  value, so moving the knob can move the branch.
- `NECOptions.Engine` reads as `2`: where a script branches on SimNEC's
  engine, the import follows SimNEC's NEC-2 engine, the one the `NEC2` block's
  cards are written for. That is why the export's W7EL insulation, written
  under `if (NECOptions.Engine == 2)`, is applied on the way back in, and its
  NEC-5-only `JamSegments` for a one-segment fed wire is not.
- A condition that is not a constant — the frequency (`G.MHz`), an element
  parameter, a name set twice — applies neither branch. A statement there
  that changes the model refuses the file by name; one that only computes a
  read-out or prints a line does not.
- A loop (`for`, `while`, `do`) is not run. A model statement in its body
  refuses by name — geometry built in a loop is `NECWire` territory, which
  is not read — and a loop that only adds up a read-out, such as the segment
  count in SimNEC's bundled examples, is harmless. The same holds inside an
  `at(…)` phase block, a `switch`, and `finalize { … }`.
- A function declared as `dcl f(a, b) { return <expression>; }` is evaluated
  where a value calls it, its arguments in place of its parameters, so
  `dcl trap(r, l, c) { return R(r) ||| L(l) ||| C(c); }` then
  `NECSource(trap(4150, 26.3u, 4.91p), $GW_3, 100)` reads as the inline load.
  A call to a function with any other body refuses by name, and a function
  whose body builds the antenna is never taken for a read-out.

A place along a wire is taken exactly: a percentage that lands on a segment
centre is that centre, and one on a knot (between two segments, or a wire's
end, as `100` is) sits at that knot, as a NEC-5 deck's end field puts it.
A percentage written to a few decimals counts within half its last digit, and
so does one given by name (`dcl P = 66.4;` or a slider saved at `66.4`, then
`NECSource(…, $GW_1, P)`), read to the decimals it is written with; a whole
number, or a place the script computes, is exact. Anywhere else, the
percentage itself is the place, never moved to the nearest site: the feed or
load is carried at that fraction of the wire, as a 4nec2 `LD … 71.89%` card
is, and the wire is split so the port sits exactly there (the placement note
says so). Two loads at one place add in series, as two `LD` cards on one
segment do in NEC.

A value or a place may also name a **slider**: a bare `Cap_F;` in the script
whose value SimNEC saves on the element (`<numericParam>Cap_F</numericParam>`).
It is read at its saved value and offered as a knob, like a slider the cards
read; a `Button` that tunes it does not change that, since SimNEC runs a
button only when it is clicked.

The Generator's `MHz` may list several frequencies (`3.55 14.05 21.1 28.3`):
SimNEC solves at the last and marks every one on its charts, so the design
opens at the last and offers each as a band.

**What is not read is refused, not dropped.** A statement the importer cannot
read refuses the file, naming the statement and the line it starts on (and,
where it is known, why — `line 17: $ld = NECSource(R($r), $GW_1, 50) ($r has
no one constant value)`), instead of solving the antenna without it: a name
with no one value (set twice, or only under a condition that is not a
constant), a wire no `GW` card declares, an element nothing attaches, an L or
C with a Q, elements in series through an inner node, a model statement in a
loop or an unevaluated branch, or any call or setting it does not know. Only statements known to leave the model alone may go unread, and are
listed in the import note: block structure, declarations, assignments that
read results back (`$g = _NECBLOCK.field.APG;`), display calls such as
`BodyGraphic(…)` and `pl` print lines, and a `Button Name() { … }`, whose
body SimNEC runs only when the button is clicked (a tune, a report); what a
click changed is already saved in the file's values.

**A file that carries its own files opens alone.** SimNEC stores a copy of
each file the circuit names (an S block's `.s2p`) inside the `.ssn`. A file
of that name beside the `.ssn` is read first; otherwise the stored copy is,
and the import note says which. So a full-station `.ssn` opens by itself
through Open… and on the hosted app, with no folder of sidecars. When every
wire's count is held by `JamSegments`, SimNEC solves the file's own mesh, and
the two agree: a real full-station file (an inverted L with its insulation
and traps, a measured 49:1 unun and choke as S blocks, and two RG-58 runs)
reads SimNEC's own Generator impedance within 0.06 % at 3.55 and 28.45 MHz on
`momwire:razor-2p`.

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
`$name` temporary). A `prm name = ...;` statement, or a plain
`name = ...;` with no `dcl`, `$` or `prm` (`hgt = 9.144;`), is a constant by
the same rule and becomes the knob `prm_<name>`: it is an element parameter
(below) whose value the script sets. Its label is the name as the script spells it (SimNEC
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

`prm` is the explicit form of the same declaration (Anvil's "passive
declaration", SimNEC 2.6 and later): `prm len;` is `len;`, and
`prm len,hei,fp;` declares three parameters, each a `par_` knob when the
cards read it. A `prm file[];` file parameter, and the
`prm num; prm runs; prm logLvl;` lines many scripts carry, are declarations
with nothing to apply, and change nothing.

A parameter the script **assigns** a constant — `prm len = 10.2;`, or the
plain `len = 10.2;`, at top level, once — is the knob `prm_<name>`. SimNEC
saves its value on the element too, but the script sets it again on every
run before the cards read it, so the script line is the value used, and
moving the knob builds exactly what editing that line would. When the saved
value disagrees with the script's, the import note says so. A `prm` or plain
assignment from other constants (`prm wl = 300/f;`) follows them, as a
`dcl` does.

A parameter may also set a **segment count**: `JamSegments` takes an
expression, so `JamSegments(segs)` makes `segs` a whole-number knob for that
wire's count, honoured exactly as a literal count is. A count below 1 or a
fraction is refused, naming the parameter — a literal `JamSegments(0)` still
means "auto-segment as usual", but a knob dragged to 0 does not silently
switch the wire back to its `GW` count.

Only an **input** is a knob. SimNEC saves a parameter's value whether the
user set it or the script computed it — AC6LA's trap dipole saves
`Trap23 = R2.z;` as a parameter too, and his Yagis save a `SegCnt` counted in
an `at(finalValue) { }` block — so a parameter the script assigns from
something other than a constant (a member such as `R2.z` or `G.MHz`, a
string), more than once, or inside any `{ }` block or the brace-less body
of an `if`, `else`, `while` or `for` is an output: never a
knob, and a card that reads one is refused by name. So is
a name that is neither a constant nor a saved parameter. A
`NECOptions.segmentsPerWavelength` that names a parameter (`= segsWL`, in
AC6LA's Synth conversions) takes its saved value, which, like any
`segmentsPerWavelength`, only feeds the mesh note.

### The station's component values are knobs

A full station opened by itself — the antenna block plus the chain between
it and the Generator — also offers the chain's component values as knobs,
beside its `dcl` and parameter knobs:

| Element | Knob | Unit |
|---|---|---|
| `SERIES_TLINE` | its length, `stn_<label>_mtrs` or `stn_<label>_ft` | as saved: m or ft |
| `SERIES_IND`, `SHUNT_IND` | `stn_<label>_H` | µH |
| `SERIES_CAP`, `SHUNT_CAP` | `stn_<label>_F` | pF |
| `TRANSFORMER2` | `stn_<label>_N` | turns ratio |

Moving one builds exactly what the file builds when SimNEC saves that value.
A line's cable model (Zo, VF, the loss coefficients), a component's Q and a
fixed `SERIES_Z` load stay as saved; a design that wants them as knobs sets
them with `with_values` (see *Knobs on both halves* below). An element needs its own label to
have a knob: one with no label, or one sharing its label with another
element, keeps its saved value. A value of 0 (an unused component) is not
offered.

## A SimNEC station on any antenna

A common workflow models the antenna in EZNEC, AutoEZ or NEC and the feed
system in SimNEC: coax runs, measured choke and unun S-parameters, a tuner.
The SimNEC circuit holds the antenna as a `LOAD` reading a table of its
feed-point impedance. `parse_ssn_station` reads just that station chain, the
elements between the Generator and the antenna end, and
`SsnStation.network(antenna)` hangs it on any antenna's network: a native
builder's, a `.nec` deck's, or the table itself.

```python
from types import MappingProxyType

from antennaknobs.builder import AntennaBuilder
from antennaknobs.nec_import import read_nec  # or parse_nec(text, network=True)
from antennaknobs.simnec_import import read_ssn_station


class Station(AntennaBuilder):
    """My antenna from a .nec, my feed system from a .ssn, in one design."""

    default_params = MappingProxyType({"freq": 7.0})

    def _deck(self):
        return read_nec(self, "antenna.nec", network=True)

    def build_wires(self):
        # specs=True keeps each wire's own radius, insulation and material;
        # plain wire_tuples() gives every wire one stock radius.
        return self._deck().wire_tuples(specs=True)

    def build_network(self):
        station = read_ssn_station(self, "station.ssn")  # .s2p files beside it
        return station.network(self._deck().network())
```

The chain sits between a new `rig` port, which is SimNEC's Generator, and the
antenna's own fed port, which keeps its name and reads the antenna alone.
Every chain block gets a node named after its SimNEC label, so each block's
generator side is a measurement plane, as in SimNEC.

What the chain reads:

- **`SERIES_TLINE`**: length in feet or metres, with its Zo, velocity factor
  and k0/k1/k2, solved as **AC6LA's Johnson line** (momwire's
  `TL(k0=..., skin=True)`). Each coefficient becomes a per-length element:
  R_dc from k0, R_hf from k1, G from k2, and L and C from Zo and velocity
  factor. The conductors' internal impedance is √(R_dc² + [R_hf·(1 + j)]²),
  so the skin effect's internal inductance slows the line as 1/√f. On 12 m of
  RG-58 at 3.55 MHz that is 2.7 % more electrical length than the velocity
  factor alone gives.
- **`SCATTERING`** (an S block): its S-parameters from the `.s2p` named
  beside the `.ssn`, else from the copy SimNEC stores inside the `.ssn` (the
  import note says so), or as written on the element, at its `Zref`. `2 <> 1`
  puts port 1 on the generator side; `1 <> 2` reverses it. The de-embedding
  modes are refused by name.
- The lumped blocks (series and shunt R, L, C with their Q, transformers, the
  `XMATCH` tuner) as in a full station import above.
- The antenna `LOAD`'s table (SimSmith Generic format):
  `station.antenna_table()` returns it as a one-port, to check a solved
  antenna against what the station was built on, or to terminate the chain
  with it (`N.TouchstoneLoad(port, table)`).

### Knobs on both halves

Either half can carry knobs. On the antenna side, a constant the `.nec`
defines with an `SY` card becomes a knob through `parse_nec`'s
`sy_overrides`. On the station side, `station.values()` lists the chain's
adjustable numbers, keyed `"<label>.<param>"` by each element's SimNEC
label, and `station.with_values()` sets them:

```python
from types import MappingProxyType

from antennaknobs.builder import AntennaBuilder
from antennaknobs.design_data import read_data
from antennaknobs.nec_import import parse_nec
from antennaknobs.simnec_import import read_ssn_station


class Station(AntennaBuilder):
    """The top wire's length and the coax run as knobs."""

    # antenna.nec carries `SY H_len=30.45` and uses H_len in its GW card.
    default_params = MappingProxyType({"freq": 3.55, "H_len": 30.45, "coax_m": 12.0})

    def _deck(self):
        return parse_nec(
            read_data(self, "antenna.nec"),
            name="antenna.nec",
            network=True,
            sy_overrides={"H_len": float(self.H_len)},
        )

    def build_wires(self):
        return self._deck().wire_tuples(specs=True)

    def build_network(self):
        station = read_ssn_station(self, "station.ssn")
        station = station.with_values({"T2.mtrs": float(self.coax_m)})
        return station.network(self._deck().network())
```

The values are the ones the chain reads, in SimNEC's own units: a line's
length (`mtrs` or `ft`, whichever it was saved with), `Zo`, `VFnom` and
`k0`/`k1`/`k2`; a component's `H` or `F` and `Q`; a `SERIES_Z`'s `ohms`
and `johms`; a transformer's `N`; an `XMATCH`'s `R`, `MHz`, `Qc` and `Ql`.
A value set this way builds exactly the network the `.ssn` saved with it
would. A label no element carries, or more than one does, a parameter the
element does not carry, a display-only field such as a line's `~deg`, and a
value that is not a finite number are refused by name.

On the hosted app a design cannot read files beside it, so paste the two
files into the design as strings and read them with `parse_nec(text, ...)`
and `parse_ssn_station(text, name=...)`. The `.s2p` files then come from the
copies SimNEC stores inside the `.ssn`.

How exact it is: on a real EFHW station (an inverted L with a measured 49:1
unun and a common-mode choke as S blocks, and 12 m + 4 m of RG-58), the chain
on SimNEC's own antenna table reproduces SimNEC's generator-side trace to
3e-15. What it does not model is the same as in SimNEC: the coax is a
lumped two-port, so a feed line that radiates, or carries common-mode current
through the antenna's field, is not in it. Model that as wires.

### The station as one NEC-5 deck

`nec5_station.export_nec5_station(builder)` writes the antenna and its
whole station as ONE NEC-5 deck, so the station runs on licensed NEC-5 (or
momwire's `momwire-nec5-bspline` drop-in) with no antennaknobs installed:

```python
from antennaknobs.nec5_station import station_deck

deck = station_deck(Station(), freq=3.55, ground=("finite", 13.0, 0.005))
open("station-3.55MHz.nec", "w").write(deck.text)
```

`ground` is the deck's ground, as in the plain NEC-5 download, and it
defaults to free space whatever the `.nec` says, so name it.

| part of the station | NEC-5 card |
| --- | --- |
| antenna wires, ground, wire material, loads on wires | `GW` / `GE` / `GN` / `LD`, as the plain NEC-5 download writes them |
| a virtual node (`rig`, each block's node) | a knot of one phantom wire parked 200 λ away, pinned open by `LD 4 … 1e10` |
| a lossless line | `TL` |
| the Johnson line, an S block, a series R/L/C | `NT`: the two-port's Y at the deck's frequency |
| a shunt R/L/C | folded into the `NT` (or `TL`) at its node |
| an ideal transformer | two λ/4 `TL` cards through a phantom knot, the second transposed: an exact impedance inverter twice is an exact transformer |
| the bare wire between blocks | the two nodes become one knot |
| the Generator | `EX 0` on the `rig` knot |

**One frequency per deck.** `NT` values and the λ/4 lines hold only at the
frequency they were computed for; the deck's `CM` header says so, and a
sweep is one deck per frequency. A list of frequencies is refused.

**Why the phantom knots are pinned.** A phantom knot is real wire to NEC-5,
and bare it sits in parallel with the network there: about j2.6e-5 S per
knot measured on the licensed binary, which put this page's test station
1 % off. Pinned by `LD 4` of 10¹⁰ Ω, as EZNEC pins its own virtual
segments, a knot reads 10⁻¹⁰ S and the source and network cards on it are
untouched. The writer measures what that residual does at every knot (it
solves the design once, on momwire by default) and lists it in the `CM`
header; a knot whose pin would move the impedance by more than 10⁻⁶,
below anything a five-figure printout can show, is refused by name. That
is a node near 10 kΩ, which belongs on a real antenna segment.

How exact it is (a 7 MHz dipole and an inverted V fed at its vertex, each
behind an ideal transformer, a shunt C, a series L, a lossless line, an S
block and 12 m of RG-58; `scratch/2209-station-deck/`):

| run | against | agreement |
| --- | --- | --- |
| licensed NEC-5 | the station on NEC-5's own antenna | 1.3e-6 / 8.7e-6, inside the printout's rounding |
| `momwire-nec5-bspline` | the station on the drop-in's own antenna | 1.5e-6 / 9.6e-6 |
| AK's importer → momwire | the station on momwire | 3.7e-8 / 5.4e-8, the pins' measured 4e-8 / 6e-8 |

On a real full-station model (an EFHW inverted L fed at a wire junction,
a 49:1 unun and a choke as S blocks, two runs of RG-58 as Johnson lines),
the one deck run on licensed NEC-5 reads 34.78 + j7.85 Ω at 3.55 MHz and
29.02 + j33.95 Ω at 28.45 MHz, SimNEC's own Generator readout to the
printout's digits.

An antenna fed at a knot where two wires meet (`PortAtVertex`) is written:
NEC-5 attaches `NT` and `TL` cards to a segment end exactly as it attaches
`EX`. Refused by name: a self-tuning tuner (tune it, then write its parts),
a current source, a floating or distributed port, a load behind a source
that also drives the network.

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
