# EZNEC → NEC-5: invocation, dialect, and the TL/NT verdict

Status doc for momwire#390. Black-box I/O observation only — the spy shim logs what
crosses the process boundary and delegates; nothing was decompiled. Same courtesy
stance as the SimNEC studies (`2026-08-08-ward-simnec-momwire-notes.md`).

Host: EZNEC Pro+ v7.0.4 (free since v7) driving the licensed NEC-5 build
`NEC5CL_x13.exe`, on the Windows box that hosted the 2026-08-08 SimNEC live session.
Harness and runbook: `scripts/eznec_spy/`. Captures: `scratch/eznec-capture/`.

## Verdict

**TL/NT ride the deck.** EZNEC emits transmission lines and networks as `TL`/`NT`
cards and lets NEC-5 solve them. It does not keep the line arithmetic in its own
code.

This is the outcome the issue flagged as the expensive one: a momwire drop-in at
this seam would have to **solve networks**, which contradicts the antenna-only
design and #388's deliberate refusals. The NEC-5 dialect front-end alone does not
buy an EZNEC drop-in.

Three independent legs support it:

1. **Two models, both emitting.** `4sqtl` ("4-square array w/feed system") emits
   `TL` ×6 and no `NT`; `Cardioid - L Network Feed` emits `TL` ×2 + `NT` ×1. One
   pure-TL feed system and one TL-plus-network feed system, both handed off whole.
2. **NEC-5 does the solving.** The printout carries a populated `NETWORK DATA`
   table listing all six lines, and a `STRUCTURE EXCITATION DATA AT NETWORK
   CONNECTION POINTS` section — the network solve, not a bare-wires solve.
3. **EZNEC does not post-process.** The issue's discriminator was to compare
   EZNEC's reported feedpoint Z against the printout. For `4sqtl` the printout's
   `ANTENNA INPUT PARAMETERS` gives 1.3949E+01 + j5.6027E+00; EZNEC's Src Dat
   reports the same to 4 figures (13.95 + j5.603). No hidden arithmetic on
   EZNEC's side — it reports what NEC-5 computed.

## Invocation protocol

EZNEC launches the engine once per calculation:

```
"C:\EZNEC 7.0\Docs\NEC5CL_x13.exe" "EZN5.NEC" "NEC5.OUT"
cwd = C:\EZNEC 7.0\Docs
stdin = 0 bytes (not redirected)   stderr = 0 bytes
stdout = "Fill complete, FMHZ=  7.1500E+00"
exit 0, 26 ms
```

- **Two quoted positional arguments** — input deck, then output file — resolved
  relative to a cwd of the engine's own directory. `LastRun.log` logs each launch
  as `Running ext engine C:\EZNEC 7.0\Docs\NEC5CL_x13.exe`.
- **stdin is unused.** With no arguments the engine falls back to prompting
  `Enter INPUT file name (or RETURN) >`, but it reads that from `CONIN$` — the
  console device, not stdin — so a piped answer is ignored and it dies
  `forrtl: severe (24): end-of-file`. EZNEC never takes that path. **A drop-in
  needs only the argv form.**
- **File-based and one-shot**, not resident — the protocol delta vs the SimNEC
  portal, which is a long-lived server behind a thin forwarder (#379).
- **The error paths exit 0.** `NEC5CL_x13.exe deck.nec` alone prints
  `ERROR getting output file from command line` and exits 0; `-i`/`-o` flags print
  `GETIOF: ERROR - UNABLE TO OPEN FILE -i` and exit 0. The exit code is therefore
  not a refusal channel — a drop-in must signal refusals in the printout, the way
  the SimNEC portal emits `NEC ERROR` (antennaknobs#829). Confirmed from the other
  side by fault injection: EZNEC ignores a non-zero exit outright (next section).

## Error convention: EZNEC reads the printout, never the exit status

Established by fault injection, captures 0036-0042. The shim runs the real engine,
then damages what it left behind before returning to EZNEC; a one-shot marker file
(`fault.txt`) arms exactly one run, and the engine's real printout is kept beside
each capture as `printout-undamaged.txt`. Fixture: `Dipole1.ez`, free space, 11
segments, frequency nudged each run to defeat EZNEC's result cache. Dialog wording
below is transcribed from the screen; the ellipses are where the operator
abbreviated.

| what the engine left behind | exit | what EZNEC did |
| --- | --- | --- |
| valid printout, **exit code 1** | 1 | **nothing — normal results displayed** |
| printout deleted | 0 | "Unable to read calculating engine output file ... due to 'File not found'. No results available. This may be due to the location of the external NEC program. Try a different location. Suggestion: ..." |
| printout emptied to 0 bytes | 0 | "Unable to read calculating engine output file ... due to No results available." |
| one line, no header echo | 0 | "Calculating engine is malfunctioning or not present. Output file NEC.OUT is present, but was written earlier from another calculation." |
| header echo intact, results cut | 0 | "Unable to read NEC output file due to NEC program error. **Would you like to view the NEC calculating engine output file NEC5.OUT**" |
| header echo intact + `NEC ERROR` line | 0 | same dialog; **the refusal text is visible** in the viewer |

Three findings, in rising order of consequence.

**The exit status is not read at all.** A printout that was byte-for-byte correct,
returned with exit 1, produced normal results and no complaint. This confirms by
test what the invocation section infers from the engine's own error paths: the
exit code is not a refusal channel in either direction. A drop-in gains nothing by
exiting non-zero and loses nothing by exiting zero.

**A printout must prove it belongs to this run.** EZNEC stamps the launch time
into the deck as a comment card — `CM EZNEC Pro/2+ v. 7.0.4  2026-08-17 17:51:10`,
matching the capture's own start time — and NEC-5 echoes the comment block back at
the top of the printout. Replace the printout with content lacking that echo and
EZNEC reports the file as *"written earlier from another calculation"*, even though
it was written milliseconds ago: the check is on content, not the filesystem
timestamp. Keeping the first 1670 bytes (banner, echoed `CM` cards, geometry) and
cutting everything after clears the check and moves EZNEC to a different branch.
The experiment does not separate "checks the echoed timestamp" from "requires a
parseable header" — but the timestamp is the only field in that prefix that
distinguishes one run from another, so it is almost certainly the discriminator.

**Refusals can speak.** With the header echo intact and results missing, EZNEC
offers to display the printout, and text placed where the results would have been
reaches the user verbatim. Injecting

```
 ***** NEC ERROR - MOMWIRE REFUSES THIS DECK: NT CARD REQUIRES A NETWORK SOLVER
```

put that line in front of the operator as the last line of the viewer. So the
`NEC ERROR` frame the SimNEC portal already emits (antennaknobs#829) is the right
shape here too, and a refusal can name its own reason rather than surfacing as an
unexplained failure.

### What this obliges a drop-in to do

1. **Always write the output file**, even when refusing. Deleting it sends EZNEC
   down the "check where you installed the NEC program" path, which blames the
   user's configuration for what is actually a refusal.
2. **Always echo the deck's `CM` cards** at the top of the printout, the way NEC-5
   does. Without that echo every printout is rejected as stale and no message of
   any kind survives.
3. **Put the refusal after the echo**, as a `NEC ERROR` line. Exit 0 regardless.

Nothing in this convention is a barrier — it is three lines of formatting
discipline. The refusal path is the *easy* part of standing in at this seam; the
hard part remains physics scope.

## Sweep protocol: one process launch per frequency point

An SWR sweep on `4sqtl` (7.15–7.50 MHz, 0.05 steps) produced **eight separate
engine launches** in ~1 s — captures `0002`–`0009`, each a single-point
`FR 0,1,0,0,<f>` card, each exit 0 in 18–37 ms. EZNEC never uses NEC's
multi-frequency `FR` stepping (`FR 0,NFRQ,0,0,FMHZ,DELFRQ`).

**The whole deck is regenerated per point, not just the `FR` card.** Diffing
`0002` (7.15 MHz) against `0009` (7.50 MHz):

| quantity | 7.15 MHz | 7.50 MHz | in wavelengths |
| --- | --- | --- | --- |
| `TL` length (×3 lines) | 10.48225 | 9.993082 | **exactly 0.25 λ (90°)** |
| `TL` length | 31.44676 | 29.97925 | **exactly 0.75 λ (270°)** |
| `TL` length | 3.653648 / 20.22609 | 3.483144 / 19.28221 | 31.37° / 173.66° |
| virtual wire x, y | 4192.901 | 3997.233 | **exactly 100 λ** |
| virtual wire radius | .0041929 | .00399723 | **exactly λ/10000** |

Every length scales as 1/f. EZNEC's TL lengths in this model are specified in
**degrees**, and EZNEC converts them to a physical length at each frequency — the
90°/270° quarter- and three-quarter-wave lines of a 4-square feed system. The
virtual wire is likewise parked at a fixed 100 λ with a λ/10000 radius and moves
every point.

Consequences for a drop-in: **no sweep batching is available at this seam.** Each
frequency arrives as a fresh process with a fresh deck and a fresh geometry, so
momwire's swept machinery (`compute_impedance_swept`, k-batched fills, Sommerfeld
grid reuse across frequency) has nothing to amortize over. That is the sharpest
protocol delta vs the SimNEC portal, whose resident server exists precisely so
sweeps can be rebatched (#379, #385).

## The virtual wire is the feed system, not a passive anchor

Both decks drive the **virtual** wire, not the antenna: `EX 4,5,3,0,1.414214,0.`
in `4sqtl` (`EX 4,3,1,...` in the Cardioid deck) — a current source of √2 A on the
remote wire's segment 3, confirmed by the printout's `ANTENNA INPUT PARAMETERS`
row `5 27 1` at 1.4142 + j0 A. The real radiating wires are reached *only* through
`TL` cards. The virtual wire's nodes are pinned open with `LD 4,5,n,0,1.E+10,0.`
so they carry ~1e-9 A.

So EZNEC's idiom is: **park the entire feed network — source included — on a
non-radiating wire 100 λ away, and reach the antenna through transmission lines.**

### This breaks antennaknobs' own TL-anchor virtualization

`nec_import._anchor_wires` (issue #427) already recognizes remote TL-anchor wires
and replaces them with a `PortVirtual` circuit node — the mechanism that sidesteps
momwire#157's Sommerfeld hang on ~100 λ separations. **It would not fire on an
EZNEC deck.** The detector requires a wire that is 1-segment, undriven, unloaded,
and not an `NT` endpoint; EZNEC's virtual wire fails on all four counts:

| `_anchor_wires` requirement | EZNEC's virtual wire |
| --- | --- |
| `w[1] != 1 → continue` (strictly 1 segment) | **4 segments** |
| not in `excluded` via `feeds` | **driven by `EX`** |
| not in `excluded` via `LD` cards | **three `LD` 1e10 cards** |
| not in `excluded` via `NT` endpoints | **`NT` endpoint** (Cardioid deck) |

The corpus family #427 was written against parks anchors at 100–500 λ — and the
#157 repro deck (`GW 2,1,2114.9,…` at 14.175 MHz, radius .0021) is **99.998 λ with
radius λ/10071**, i.e. the same 100 λ / λ/10000 constants EZNEC emits. Those wild-corpus
decks look like EZNEC exports of *simpler* models, where the anchor happened to be
a bare 1-segment wire. Feed-system models produce the richer form, which the
detector misses — so an EZNEC-exported feed-system deck would take the unvirtualized
path straight into momwire#157's assembly hang. Worth its own issue.

## The bare-wires control

`Dipole1.ez` (capture `0010`), free space, 299.7925 MHz (λ = 1 m exactly):

```
GW 1,11,0.,-.25,0.,0.,.25,0.,.0005
GE 0,-1
FR 0,1,0,0,299.7925
GN -1
EX 4,1,6,0,1.414214,0.
PQ 0
RP 0,1,361,1000,90.,0.,0.,1.,0.
EN
```

**No virtual wire, no `LD` pins, no `! *Wire #N for virtual segments.` comment.**
The whole remote-anchor apparatus is `TL`/`NT`-specific, exactly as the feed-system
decks implied. This is the minimal deck shape a front-end must accept.

Two dialect facts it settles:

- **Free space is `GE 0,-1` + `GN -1`.** `GE`'s first parameter is the ground
  flag; its second is `-1` in every deck seen so far.
- **The source is always a current source.** `EX 4,…,1.414214,0.` appears in every
  deck — on the antenna wire here (segment 6, the exact center of 11), on the
  virtual wire in the feed-system decks. √2 A is a unit-power normalization
  (|I|²/2 = 1). No voltage-source `EX 0` has been observed yet, including on the
  simplest possible model, so `EX 4` may be EZNEC's universal drive.

## Ground: two cards carry the same payload

The family is complete. Captures `0019`–`0021` cycle one model (`Vert1`) through
every ground type with the geometry held fixed, so the mapping is direct
observation rather than inference:

| EZNEC ground type | cards emitted | printout says |
| --- | --- | --- |
| Free Space | `GE 0,-1` + `GN -1` | — |
| Perfect | `GE 1,-1` + `GN 1` (bare, one field) | `PERFECT GROUND` |
| **Real / MININEC type** | `GE 1,-1` + **`GD`** `0,0,0,0,ε,σ,1.,0.` | `FINITE GROUND.  SOMMERFELD SOLUTION` |
| **Real / High Accuracy** | `GE 1,-1` + **`GN 0`**`,0,0,0,ε,σ,1.,0.` | `FINITE GROUND.  SOMMERFELD SOLUTION` |

`GN`'s first field follows NEC-2's convention exactly — `-1` free space, `0`
finite, `1` perfect. `GD` is EZNEC's MININEC-type request, carrying the identical
8-field media payload on a different mnemonic. (This also explains the corpus
split: `Vert1`, `4sqtl` and `Cardioid` are old example files saved with
MININEC-type ground; `DipTL1` was saved with High Accuracy.)

**`GD` and `GN 0` are not synonyms — the banner lies.** Both print the same
`FINITE GROUND.  SOMMERFELD SOLUTION` header with the same ε/σ, but they solve
differently. Captures `0020` and `0021` are the same `Vert1` geometry at the same
frequency with the same media, and the *only* difference in the whole deck is the
mnemonic:

```
0020  ***** INPUT LINE  2  GD  0 0 0 0  1.30000E+01  5.00000E-03  1.0  0.0 ...
0021  ***** INPUT LINE  2  GN  0 0 0 0  1.30000E+01  5.00000E-03  1.0  0.0 ...
```

| | `GD` (MININEC type) | `GN 0` (High Accuracy) |
| --- | --- | --- |
| feedpoint Z | 35.571 − j1.4223 | **47.789 − j0.78525** |
| matrix FILL | 0.000 s | 0.078 s |
| segment currents | differ throughout | |

A **34 % difference in R** on an identical structure. The physics is the textbook
one: `Vert1` is a base-fed vertical whose base *touches ground*, and MININEC-type
ground famously under-counts near-field ground loss for exactly that case, giving
a near-ideal ~35.6 Ω, while the full Sommerfeld treatment adds the loss and lands
at ~47.8 Ω. The near-zero fill time on the `GD` path says it is not doing the same
work.

So a front-end **must** keep the two mnemonics distinct and implement two
ground-contact treatments. Mapping both onto one finite-ground model — which the
identical printout banner invites — would be wrong by tens of percent on any
ground-mounted vertical.

This is also a ready-made oracle pair for momwire's own ground-contact thread
(#151, #282, #291, #292): one geometry, two sanctioned answers, from the NEC-5
reference itself.

**EZNEC only warns.** Selecting High Accuracy on this model raises an EZNEC dialog
about a wire touching ground — advisory, not blocking; the deck is written and the
engine runs. A drop-in must therefore expect ground-contacting wires under
Sommerfeld ground and cannot treat them as a deck error.

Both real-ground forms carry the **same 8-field media payload** (ε, σ in fields
5–6) on two different mnemonics, and neither deck contains the other card. Note
form A's `GD` does *not* mean what NEC-2's `GD` means — NEC-2's is a radial-wire
ground screen whose fields are counts and radii, not ε/σ.

**The printout shows the two forms are equivalent.** `Vert1` (`GD`, capture `0015`)
and `DipTL1` (`GN`, capture `0011`) both produce the identical
`FINITE GROUND.  SOMMERFELD SOLUTION` environment, each echoing its own ε/σ. So
`GN` and `GD` are accepted as synonyms for the same media specification, and a
parser must treat them as such rather than looking for a semantic difference.
What makes EZNEC choose one mnemonic over the other is still unknown, and no
longer looks important.

**Still unsampled:** perfect ground and MININEC-type ground — `Vert1` was captured
only in its shipped Sommerfeld configuration.

### The engine is stateful across launches: `SOMMPD.NEX`

The environment section also reveals a **persistent Sommerfeld-table cache** in the
engine's own directory, keyed on the complex permittivity:

```
0002 (7.15 MHz)  Sommerfeld integral tables read:  E, H: 11 12 13 14 15 21 23
0003 (7.20 MHz)  GMPINO: EPSC from file = 1.30000E+01-1.25706E+01
                            should be   1.30000E+01-1.24833E+01
                 Will compute Sommerfeld-ground tables
0009 (7.50 MHz)  ... should be 1.30000E+01-1.19840E+01 -> Will compute
```

εc = ε − jσ/(ωε₀) is frequency-dependent, so **every sweep point after the first
misses the cache and recomputes the tables.** That sharpens the batching finding:
the one piece of cross-launch state that exists is invalidated by the very thing a
sweep varies. It is also the exact shape of momwire#164 (swept solves refilling the
Sommerfeld grid per rung).

`SOMMPD.NEX` was byte-identical (737,268 bytes, same SHA-256) across every captured
run, including those that recomputed — so during these captures it behaved as a
read-only cache, not one the engine writes back. A drop-in should expect the file
to exist in its working directory and must not depend on being able to update it.

## Request cards follow the display

The card that ends the deck depends on which EZNEC display triggered the launch:

| display | terminating card |
| --- | --- |
| FF Plot, 2-D slice | `RP 0,1,361,1000,<θ>,0.,0.,1.,0.` (or `0,181,1,1000,…`) |
| FF Plot, 3-D | `RP 0,37,73,1001,0.,0.,5.,5.,0.` — note **XNDA = 1001**, not 1000 |
| SWR sweep, Src Dat | **`XQ 0`** — execute only, no pattern requested |
| Near Field | **`NE 0,1,1,1,0.,0.,0.,0.,0.,0.`** (capture `0022`, at defaults — a single point at the origin) |

`PQ 0` precedes the request card in every deck. No `NH` (near magnetic field) card
has appeared — EZNEC's near-field display asked only for E at defaults.

**EZNEC decides when the engine runs, and it is not once per click.** Tracing
`LastRun.log`'s display codes against the launches:

| display code | launches? | emits |
| --- | --- | --- |
| `SD` (Src Dat) | when the model changed | `XQ 0` |
| `CR` (FF Plot) | when the pattern is stale | `RP` |
| `NF` (Near Field) | when near-field data is stale | `NE` |
| `TA` (far-field table) | **no** — consumes the pattern `CR` produced | — |
| `CU`, `LD`, `OP`, `AN`, `LO`, `VI`, `VA` | never | — |

`TA` was seen launching once in an earlier session only because no pattern had been
computed yet; with `CR` results current it never runs. So `TA` is not a distinct
request-card family.

Two consequences for a drop-in: it is invoked far less often than the user acts,
and an edit that returns a model to an already-computed state produces no launch at
all (observed when a ground-type change was undone). Caching lives entirely on
EZNEC's side — the engine is stateless apart from `SOMMPD.NEX`.

## Signed segment addressing is not limited to `TL`

`Network Connection Test` (capture `0012`) puts the sign on **`EX` and `NT` too**:

```
EX 4,2,-1,0,1.414214,0.
NT 3,-1,4,1,.01,0.,0.,0.,0.,0.
NT 3,-1,4,2,.005,0.,0.,0.,0.,0.
```

So the node-vs-node convention established for `TL` is a general addressing mode
across the dialect's connection cards — NEC-5's knot-addressed sources, the thing
`DeckModel.node_gaps` exists for. A front-end must carry the sign through `EX`,
`TL` and `NT` alike.

## Junction loads become `NT` cards, not `LD` cards

The same deck is the load case, and it is not expressed as loads at all. W7EL's
description is two parallel-connected loads at the wire-2/wire-3 junction, 100 Ω
and 200 Ω (his stated 66.67 Ω parallel equivalent). EZNEC emits them as **two `NT`
admittance cards** — `.01` and `.005` mhos — from the junction node (`3,-1`) to
segments 1 and 2 of a virtual wire, each pinned open with `LD 4,4,n,0,1.E+10,0.`

Consequence for scope: **a deck the user thinks contains only lumped loads can
still require an `NT` solve.** A drop-in that refuses `NT` would refuse ordinary
loaded models, not just network-feed models — this widens the network-solving
requirement well beyond the phased-array feed systems.

The virtual wire here is `GW 4,3,99.99998,…,1.0000E-4` at 299.7925 MHz, so λ = 1 m
and it sits at **100 λ with radius λ/10000** — the same two constants as the 7 MHz
and 14 MHz decks. It also carries a second comment form:
`CM ! Wire #4 for shorted/open trans. lines and/or parallel loads.` (vs
`CM ! *Wire #N for virtual segments.`), so the comment text is not a reliable
detection key — the geometry constants are.

## Dialect notes

**Negative segment numbers on `TL` are a flag, not an index.** The deck writes an
end as `tag,-1`; NEC-5 echoes it as a *global* segment index that keeps the sign:

| deck card | printout row | wire's segment 1 → global |
| --- | --- | --- |
| `TL 5,1,1,-1` | `5 25 1 -1` | wire 1 → 1 |
| `TL 5,2,2,-1` | `5 26 2 -7` | wire 2 → 7 |
| `TL 5,2,3,-1` | `5 26 3 -13` | wire 3 → 13 |
| `TL 5,1,4,-1` | `5 25 4 -19` | wire 4 → 19 |
| `TL 5,1,5,3` | `5 25 5 27` | wire 5 seg 3 — **positive** |

Six segments per vertical puts wires 1–4 at globals 1/7/13/19, so the magnitudes
are plain tag→global conversion; the sign survives it and therefore carries
meaning.

**Confirmed: the field is a NODE index, not a segment index.** Every connection
lands on a segment boundary, never a segment centre, and the encoding is:

> node **0** of a wire (its end 1) is written **`-1`**; node **k ≥ 1** is written
> **`+k`**, meaning the far boundary of segment *k*.

Node 0 needs the negative form only because `0` is not available — a zero segment
field means "all" elsewhere in NEC. Consistent with this, **every negative value
observed across the whole corpus is exactly `-1`**; no other negative appears.

This is knot addressing, and it is what momwire's `DeckModel.node_gaps` has to
match.

The decisive evidence is the `Network Connection Test` A/B pair, where W7EL has us
declare *the same physical point* two different ways and states that the answer
must not change:

| config | UI declaration | card emitted | node |
| --- | --- | --- | --- |
| A (shipped, `0012`) | Wire 3, **0%** from End 1 | `NT 3,-1,4,1` | wire 3 node 0 |
| B (`0016`) | Wire 2, **100%** from End 1 | `NT 2,3,4,1` | wire 3-segment wire 2's node 3 |

Wire 2 runs (0,0,0)→(0,.125,0) in 3 segments and wire 3 begins at (0,.125,0), so
wire 2's node 3 and wire 3's node 0 are **the same point** — and EZNEC reports the
same impedance for both, as W7EL says it must. `2,3` is 100% along wire 2 only
under the node reading; a segment-centre reading would put it at 83.3%.

### The oracle triple

Running W7EL's full three-configuration script gives a validated fixture set — his
published impedances, our captured decks, and NEC-5's printout all agreeing:

| config | UI declaration | cards emitted | Z from printout | W7EL's published |
| --- | --- | --- | --- | --- |
| A (`0012`, `0014`) | both loads Wire 3, 0% | `NT 3,-1,4,1` + `NT 3,-1,4,2` | 114.47 + j21.096 | 114.5 + j21.1 |
| B (`0016`) | both loads Wire 2, 100% | `NT 2,3,4,1` + `NT 2,3,4,2` | **114.47 + j21.096** | unchanged |
| C (`0017`) | one each | `NT 3,-1,4,1` + `NT 2,3,4,2` | 195.34 − j57.458 | 195.3 − j57.46 |

A and B agree to every digit printed: two different declarations of the same
geometric node are exactly equivalent, so the encoding is a true alias. C differs
by 70 Ω on a point that has not moved — the two admittances now sit on opposite
sides of the junction and combine in series rather than parallel.

**This is the fixture any front-end should be gated on.** It is the smallest model
that distinguishes correct favored-wire handling from a plausible-but-wrong
implementation, it has a published expected answer, and the wrong answer is not
subtly wrong — an implementation that canonicalizes `2,3` and `3,-1` to one node
returns 114.47 for config C and is off by 70 %.

Three further checks agree:

| deck | card | resolves to | matches |
| --- | --- | --- | --- |
| `Vhfgp` | `EX 4,5,-1` | (0,0,10.26687) — where all **five** wires meet | "the source is right at the junction of five wires" |
| `Vert1` | `EX 4,1,-1` | z = 0, the ground contact | "how to connect a source to ground" |
| `4sqtl` | `TL …,1,-1` | z = 0, base of a ground-mounted vertical | a base-fed vertical's feedpoint |

The printout corroborates it: the trailing index in `STRUCTURE EXCITATION DATA AT
NETWORK CONNECTION POINTS` **tracks the deck's sign exactly**, 9 of 9 rows —
positive → 1, negative → 2, i.e. it reports which end of the named segment the
node sits on:

| deck end | printout row | trailing index |
| --- | --- | --- |
| `5,1` `5,2` `5,3` (positive) | `5 25 1`, `5 26 1`, `5 27 1` | **1** |
| `1,-1` `2,-1` `3,-1` `4,-1` (negative) | `1 1 2`, `2 7 2`, `3 13 2`, `4 19 2` | **2** |
| `4,1` (positive) | `4 22 1` | **1** |
| `2,-1` (negative) | `2 11 2` | **2** |

It is not a port index: in `DipTL1` the negative end is the card's END ONE yet
reports 2, and in `4sqtl` `5,3` is an END TWO yet reports 1.

A front-end that drops the sign attaches the connection to the wrong place — on a
coax model like `DipTL1`, the difference between a feedline and a short; on a
ground plane, the difference between feeding the junction and feeding the whip.

**Non-node percentages snap, in the UI, before the deck is written** (capture
`0018`). Declaring a load at *Wire 2, 50% From E1* on a 3-segment wire — whose
nodes are at 0 / 33.33 / 66.67 / 100 % — makes EZNEC display an **Actual Pos. of
66.6667%** and emit `NT 2,2,…`, i.e. node 2. 50% is exactly equidistant between
nodes 1 and 2, so the tie rounds **up**.

Consequence: **the deck never carries a fractional position.** Every connection
point is node-exact by the time it reaches the engine, so a front-end needs no
snapping rule of its own — it only has to resolve node indices. Snapping is
EZNEC's business, and it tells the user what it did.

(The impedance moves to 225.39 − j60.593 here, as expected: the load is now a
genuine segment away from the junction rather than on it.)

This closes the addressing encoding. It is fully specified by: node index with the
`-1`/`+k` spelling, the tag as favored wire, and node-exact positions throughout.

**The virtual-wire idiom is systematic.** Both decks park a far-off wire whose
segments serve as the network's nodes — `GW 5,4,4192.901,4192.901,4234.831,...`
in `4sqtl`, wire 3 in the Cardioid deck — each node pinned open with
`LD 4,5,n,0,1.E+10,0.` so it carries ~1e-9 A and cannot radiate. The wire is cut
with more segments than nodes used (4 segments, 3 nodes) so no node lands on a
wire end. EZNEC announces it in a comment: `CM ! *Wire #3 for virtual segments.`

**`GE` takes a second parameter.** Both decks write `GE 1,-1`, where NEC-2's `GE`
takes one. Part of the NEC-5 dialect surface a front-end must parse.

**Junction-object semantics — the favored wire.** W7EL's bundled
`Network connection test` documents NEC-5's rule that an inserted source or load
is not *at* a junction but *on the wire right next to it*, with the favored wire
named by the object's position declaration; two nominally parallel loads at one
junction become series if declared on different wires.

The encoding is now visible: the favored wire is simply the **tag** in a
node-addressed (negative) card. `Vhfgp` is the clean case — five wires meet at
(0,0,10.26687) and `EX 4,5,-1` names wire 5, so the whip takes the full 1 A from
one source terminal while the other terminal's current splits among the four
radials. The same physical node could have been named through any of tags 1–4 and
the physics would differ. A front-end therefore **cannot canonicalize a
node-addressed card to a bare geometric node** — the tag carries physics, not just
addressing. (This is MININEC heritage: W7EL notes the vertical is wire 5 rather
than wire 1 because MININEC's convention favored the highest-numbered wire at a
junction, and the model dates to ELNEC.)

## Card vocabulary

**Fourteen mnemonics, across 31 captures spanning 19 models** — including every
transmission-line and network example in the bundle. The dialect is far narrower
than NEC-5's full surface:

| group | cards | notes |
| --- | --- | --- |
| geometry | `GW`, `GE` | `GE <ground-flag>,-1`; the second field is `-1` in every deck |
| environment | `GN`, `GD` | `GN -1` free space, `GN 1` perfect, `GN 0,…`/`GD …` finite — **not synonyms**, see above |
| excitation | `EX` | `EX 4` (current source) ×38 and `EX 0` (voltage source) ×2 — the model's source-type setting picks one |
| loading | `LD` | **`LD 4` only**, 67 of 67 — impedance (R+jX); segment-to field is **always 0**, so loads are single-point, never ranges |
| networks | `TL`, `NT` | see below |
| requests | `FR`, `PQ`, `RP`, `XQ`, `NE` | one per deck, chosen by display |
| terminator | `EN` | |

The narrowness is the useful part. **Loading is a single card type:** `LD 4` in 67
of 67 — no `LD 0/1/2` series/parallel RLC and no `LD 5` wire conductivity has ever
been emitted, because EZNEC reduces whatever the user entered to an impedance at
the frequency before writing the deck. **Excitation is two:** `EX 4` (elementary
current source) dominates at 38 of 40, with `EX 0` (voltage source) appearing in
the `Elevrad` pair — the model's source-type setting selects between them, so a
front-end must implement both.

### Multiple sources and phase

Phased arrays fed without a transmission-line network emit **one `EX` card per
source**, with relative phase carried as the complex drive in fields 5–6. The
40-metre four-square (capture `0031`) is the clean example:

```
EX 4,1,-1,0, 1.414214, 0.          0°
EX 4,2,-1,0, 0.,      -1.414214  -90°
EX 4,3,-1,0, 0.,      -1.414214  -90°
EX 4,4,-1,0,-1.414214, 0.         180°
```

— the textbook 0/−90/−90/−180 four-square phasing, and the `Cardioid` (`0032`)
gives the 0/−90 pair. Magnitude is always √2 (a 1 W normalisation, |I|²/2 = 1);
only the phase varies. Across the corpus just three drive values appear:
`1.414214,0.`, `0.,-1.414214`, `-1.414214,0.`

This matters for scope: **a phased array can be driven either way.** The same
physical antenna appears as multi-`EX` with phase (no network needed) or as
single-`EX` plus a `TL`/`NT` feed system, depending on which example file you
open. The multi-source form needs no network solve at all.

### Radials are wires

The `Elevrad` pair models an elevated radial system as ordinary `GW` wires over
`GN 0` ground. No radial-screen ground card, no radial count — NEC's radial-wire
ground screen is never used.

### `TL` variants in use

- **Crossed lines** — negative `Z0` (`TL 1,9,2,9,-490.0875,…` in the log-periodic,
  the classic LPDA phase-reversal feeder). NEC's convention; `nec_import.NecTL`
  already maps this to `transposed=True`.
- **Stubs via end shunt admittances** — `TL 1,9,6,1,490.0875,.1524,0.,0.,1.E+10,1.E+10`
  puts 10¹⁰ mhos on end two, i.e. a dead short: that is how a **shorted stub** is
  expressed. An **open stub** is the same construction with zero shunt, left open
  by the virtual node's `1.E+10` `LD` pin. This matches the two variants
  `nec_import.NecTL` already documents.
- Otherwise all four shunt fields are zero.

### `NT` variants in use

Fully complex, reciprocal Y matrices — e.g.
`NT 5,1,5,2,2.1151E-6,-4.599E-2,-2.115E-6,4.5991E-2,5.9009E-6,1.5538E-2`. Both
ends frequently land on the *virtual* wire, making the card a pure circuit element
with no antenna terminal at all. L-networks, transformers and series capacitors are
all expressed this way: capture `0025` ("4 Sq - L Ntwrk & Z Match", the transformer
+ series-C model) adds `NT`×3 and `LD`×8 rather than any new card.

### Signed node addressing spans four cards

`EX`, `LD`, `TL` and `NT` all take the node index described above. Across all 31
captures, **`-1` is the only negative value that appears anywhere** — exactly as
the node-0 encoding predicts.

### Not yet sampled

`NH` (near magnetic field); `LD 5` wire conductivity — no captured model used wire
loss, including a real-world five-element Yagi, so it may be that EZNEC folds wire
loss into `LD 4` as well; radial-wire ground screens (`Elevrad` shows EZNEC models
radials as wires instead).

Regenerate with:

```
python scripts/eznec_spy/index_captures.py --markdown <this file> --json scratch/eznec-capture/index.json
```

## Open work

- Run the remaining bundled examples (33 models; checklist in
  `scripts/eznec_spy/README.md`). The verdict is settled, but the **full card
  vocabulary** is the dialect study's raw material and prices the NEC-5 front-end
  for its other consumers — the twin/corpus studies that hand-translate NEC-5
  decks today.
- Confirm the negative-segment semantics with a both-ways deck.
- File the `_anchor_wires` gap above as its own issue — EZNEC-shaped decks defeat
  the #427 virtualization and land on momwire#157's hang.
- No bundled example is known to exercise a Y-parameter `NT` beyond the L-network
  case, or every ground type — hand-supplement where the corpus leaves gaps.

## Go / no-go

**No-go for a drop-in on the antenna-only line.** Standing in behind
`NEC5CL_x13.exe` is mechanically easy — one console executable, two positional
paths, a printout back, no resident protocol, no sentinel handshake, materially
simpler than the SimNEC portal. The blocker is physics scope, not plumbing:
EZNEC's own feed-system examples are transmission-line and network models, so the
decks a drop-in would be handed are exactly the ones momwire refuses.

The sweep behaviour compounds it: one process per frequency point means a drop-in
pays full setup on every point with nothing to batch, exactly the amortization the
SimNEC portal's resident server was built to get.

Three options, all scope decisions for a separate issue:

1. Take on network solving (`TL`/`NT`) in momwire — reverses #388's refusals.
2. Ship the NEC-5 dialect front-end for its other consumers and accept that the
   EZNEC seam serves only bare-wire models, refusing TL/NT decks in the printout.
3. **Put the seam in antennaknobs, not momwire.** antennaknobs already parses
   `TL`/`NT` (`nec_import.NecTL`/`NecNT`), already has the MNA network core, and
   already virtualizes remote TL anchors — the pieces momwire deliberately lacks.
   An EZNEC-facing `NEC5CL_x13.exe` stand-in could live there and call momwire for
   the antenna-only part, which is the layering the portal already uses. This
   keeps #388's refusals intact and is the option the capture makes look best —
   but it needs `_anchor_wires` extended to EZNEC's driven, loaded, multi-segment
   virtual wire first.
