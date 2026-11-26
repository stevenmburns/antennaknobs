# Block builder: a Scratch-style way to write antenna designs

Status: proposal (2026-11-23). Nothing here is built yet. Two editors
share one design: **Blocks** for the antenna, and the **Station** rail for
everything between it and the rig.

## The problem

antennaknobs' designs are Python: an `AntennaBuilder` subclass with
`default_params` (the knobs) and a `build_wires()` that returns `Wire`s.
Experienced users write these well. Novices get stuck on four things, none of
which is the antenna:

1. **Coordinates.** Working out every endpoint by hand, in metres, in 3-D.
2. **Connectivity.** Two wires join only if their endpoints are *exactly*
   equal. A typo leaves a gap the solver treats as two separate wires.
3. **The builder contract.** Which class to subclass, how `default_params`
   becomes knobs, what `ui_params` does, where the feed goes (`ex=`), what
   `n_seg=None` means.
4. **Python itself.** For some users, the first time they have written any.

The block builder lets a user assemble a design from blocks, see it drawn
and solved live, and get, as its output, the same stylized Python a careful
author would have written. The blocks teach the code, and the code stays the
design's real form.

## Goals

- **G1. Blocks and code say the same thing.** Every block program has exactly
  one canonical Python rendering, shown side by side and updated live. A user
  who outgrows blocks keeps the `.py` and carries on in a text editor.
- **G2. TransformStack is the spine.** Blocks are nested transforms
  (translate, rotate, mirror, repeat) with wires inside them, which is how the
  good existing designs already think (`hentenna.py`, the arrays). The block
  tree *is* the transform stack.
- **G3. Connectivity is correct by construction.** Wires built from a path or
  from named points share endpoints exactly. A novice cannot leave a
  millimetre gap by accident.
- **G4. Live.** Every edit re-solves, the way a knob drag does now, and the
  Antenna, pattern and Sweep views follow.
- **G5. Safe on the hosted app.** A block program is data. The server
  interprets it, with no `exec` of generated text, so it needs neither the
  trust prompt nor the sandbox jail.
- **G6. Knobs come for free.** A "parameter" block becomes a slider with a
  range, exactly as `default_params` and `ui_params` do in hand-written
  designs, so a block design gets everything else antennaknobs offers:
  optimizer, analyses, sweeps, exports.

## Non-goals (first version)

- Reading arbitrary Python back into blocks. Only files the block builder
  wrote round-trip (see "Round trip").
- Traps and loads on the antenna's own wires in the block editor. Stations
  (coax, tuners, baluns) are the rail's job; see "Stations" below.
- Analyses (`build_analyses`). Block designs get the default analyses; a user
  who wants more edits the Python.
- Replacing hand-written designs. The catalog stays Python.

## What the user sees

A new view, **Blocks**, in the view registry. It can sit in the desktop rail
or grid beside Antenna, and in the phone carousel. There is also a
**Pop out** button that opens the same editor in its own browser window, for
users who want it full-screen beside the main workbench (see "Where it
lives").

```
┌──────────── Blocks ──────────────────────────────┬──── Antenna ─────────┐
│ palette          │ workspace                      │  (live 3-D drawing,  │
│ ─ Parameters     │  ┌ design  "my hentenna" ────┐ │   currents, feed     │
│ ─ Points         │  │ freq 28.47 MHz            │ │   marked)            │
│ ─ Wires          │  │ param width = 0.138 λ ⇔   │ │                      │
│ ─ Transforms     │  │ with wire 14-awg          │ │                      │
│ ─ Repeat         │  │  ┌ move up by base ──────┐│ │                      │
│ ─ Feed & loads   │  │  │ loop A→C→E→F→A        ││ │                      │
│ ─ Templates      │  │  │ wire D→B  feed centre ││ │                      │
│                  │  │  └───────────────────────┘│ │                      │
│                  │  └───────────────────────────┘ │                      │
├──────────────────┴────────────────────────────────┤  Z = 52.1 − j3.4 Ω   │
│ Python ▾  (read-only, live)                       │  SWR 1.05            │
│   class Builder(AntennaBuilder): ...              │                      │
└───────────────────────────────────────────────────┴──────────────────────┘
```

- **Palette** on the left, grouped as below.
- **Workspace**, where blocks snap together. C-shaped blocks (transforms,
  "with wire", repeat) hold other blocks, Scratch-style.
- **Python panel** underneath: the generated code, read-only, highlighting
  the line for the selected block, and the reverse when a line is clicked.
- **Selection is shared with the Antenna view.** Selecting a block highlights
  its wires in 3-D, and clicking a wire there selects its block.
- **Errors sit on the block that caused them** (a red badge with the refusal
  text), not in a console.

## The block vocabulary

Each block maps to one stylized construct. Lengths may be in metres or in
wavelengths at the design frequency (λ). Novices think in λ fractions, and
the generated code spells `λ * 0.25` as `wavelength * 0.25`, as the catalog
does.

| group | block | generated Python (shape) |
|---|---|---|
| Design | **design** (name, design frequency, height `base`) | `class Builder(AntennaBuilder)` with `default_params` |
| Parameters | **param** name = value, unit (m, λ, °, plain), range min..max | an entry in `default_params`, and in `ui_params` for the range |
| Parameters | **let** name = expression | a local in `build_wires` |
| Points | **point** P = (x, y, z) | `P = (x, y, z)` |
| Points | **mirror point** Q = P across y | `Q = (P[0], -P[1], P[2])` |
| Wires | **wire** P → Q | `st.emit(Wire(P, Q))` |
| Wires | **path** P → Q → R … (open) | one `st.emit` per segment, shared endpoints |
| Wires | **loop** P → Q → R … → P (closed) | the same, closed |
| Wires | **arc** / **helix** | the existing `GA` / `GH` paths, once the builder exposes them |
| Transforms | **move** by (dx, dy, dz) | `with st.push_pop_tr(Transform.translate(dx, dy, dz)):` |
| Transforms | **rotate** about X / Y / Z by θ | `with st.push_pop_tr(Transform.rotZ(θ)):` |
| Transforms | **mirror** across a plane | `with st.push_pop_tr(Transform.scale(1, -1, 1)):` |
| Repeat | **repeat** n times, each moved / rotated by … | `for i in range(n): with st.push_pop_tr(...):` |
| Repeat | **both sides** (the body and its mirror image) | two passes, the second mirrored |
| Material | **with wire** *catalog name* (14-awg, 28-awg-pvc, …) | `with st.wire_spec(WIRES["14-awg"]):` (new, below) |
| Feed & loads | **feed here** on a wire (centre, end, %) | `ex=1 + 0j` on that wire, at the snapped position |
| Feed & loads | **load** R, L, C on a wire (phase 3) | the existing load and network constructs |
| Templates | dipole, inverted vee, hentenna, quad, yagi, vertical with radials | a ready-made block program |

Two rules keep the generated code close to the catalog's style:

- **Names carry through.** A point named `A` in blocks is `A` in Python, and
  a param named `width_factor` is `self.width_factor`. The generator never
  invents `p17`.
- **Each block is one readable statement or one `with` block.** No
  generator-only helper functions are inlined into the user's file.

## TransformStack additions

The block builder needs a few constructs that are worth having for
hand-written designs too. Each ships in `transform.py` with tests, and some
catalog designs adopt them, so the block output never uses an API no human
uses.

1. **`with st.wire_spec(spec):`** sets the default `WireSpec` for wires
   emitted inside the block, nested like transforms, innermost wins. An
   explicit `Wire(..., spec=...)` still wins over it, matching the existing
   precedence rule in `Wire`'s docstring. A spec is never scaled by a
   transform, as now.
2. **`st.path(points, *, closed=False, name=None, feed=None)`** emits
   consecutive wires that share endpoints. `feed=("D", "B", "centre")` puts
   `ex` on the named segment. This is `hentenna.py`'s `build_path` idiom,
   promoted.
3. **`with st.mirrored(axis="y"):`** is shorthand for the scale transform,
   but it also reverses each wire's direction, so a mirrored feed keeps its
   sign convention. Today's designs hand-roll `ry()` for this.
4. **Loops are plain.** `for i in range(n): with st.push_pop_tr(Transform.rotZ(360 * i / n)): ...`,
   one `with` per pass, so every push has its pop in view. There is no
   `st.repeat`: a generator that popped its pushes when the loop ended
   (tried, 2026-11-24) hid state. The block "repeat" generates this loop.
   `st.wire_x` / `wire_y` / `wire_z` and `Transform.mirrorYZ / XZ / XY` are
   built; `st.path` too.
5. **Named points**: `st.point("A", (x, y, z))` records the point under the
   current transform, so a later `st.wire("A", "B")` can join points made in
   different transform blocks and stay exactly coincident. This is what makes
   G3 hold across transform boundaries, and it is the one addition with real
   design weight (see open question Q2).

## How a block program is stored and run

**Stored as JSON**, not as Python. A block program is a tree:

```json
{"block": "design", "name": "my hentenna", "freq_mhz": 28.47,
 "params": [{"name": "width_factor", "value": 0.1378, "unit": "λ", "min": 0.10, "max": 0.18}],
 "body": [
   {"block": "with_wire", "spec": "14-awg", "body": [
     {"block": "move", "by": [0, 0, {"ref": "base"}], "body": [
       {"block": "loop", "points": ["A", "C", "E", "F"]},
       {"block": "wire", "from": "D", "to": "B", "feed": "centre"}]}]}]}
```

**Run by an interpreter, not by `exec`.** The server's `block_design` module
walks the tree and drives a real `TransformStack`. Expressions are a small
arithmetic grammar: numbers, param references, `λ`, + − × ÷, sqrt, sin, cos,
parsed with a tiny parser, never Python `eval`. The output is the same
`Wire` list a `build_wires()` would return, handed to the existing pipeline
(`auto_mesh`, the degenerate-wire refusals, the engines). The consequences:

- **The hosted app can accept block designs from anyone.** There's no code
  to trust, so this is the safe way for a visitor to build a design on
  app.antennaknobs.dev, where today a visitor's `.py` needs the jail.
- **Errors are structured.** The interpreter knows which block it was in, so
  a refusal comes back as `{block_id, message}` and lands on the block.
- **The Python is generated from the same tree** by `block_codegen`, purely
  for display and export. An equivalence test (below) keeps the two from
  drifting.

**Saved designs.** A block design saves as a `.py` file, so it lives where
user designs live and works everywhere a design works. Its last line embeds
the block JSON in a comment
(`# antennaknobs-blocks: v1 <base64>`). The file is ordinary Python: it runs
without the block builder, and a person can read it top to bottom.

## Round trip

- **Blocks → Python:** always, live.
- **Python → blocks:** only for a file carrying the `antennaknobs-blocks`
  trailer, *and* whose code still matches what the trailer generates. If the
  user edited the Python by hand, the builder says so and offers either
  "open the blocks as they were saved (your hand edits will be lost)" or
  "keep it as Python". It never guesses a parse of hand-written code.
- **Catalog designs as starting points:** templates are block programs
  written to generate code close to their catalog twins (dipole, inverted
  vee, hentenna), not imports of the catalog files.

## Stations: the rig on the left, the antenna on the right

The antenna is half of what a novice needs to build. The other half is
everything between it and the radio: coax, a tuner, a balun or unun, a
choke, open-wire line, a remote tuner at the feedpoint. antennaknobs already
models all of it, and most users never find out, because today a station
means writing a `build_network()`.

The engine side exists:

- **Lines:** `TL.from_cable` with the lossy cable catalog (`CABLES`: RG-58,
  RG-8X, LMR-400, the 450 Ω and 600 Ω lines). SWR-multiplied loss falls out
  of the circuit solve.
- **Matching:** `station.py`'s `l_network_tuner`, `t_network_tuner`,
  `balanced_l_tuner`, the stub tuners, and the self-tuning `LTuner` /
  `TTuner` (`auto_match.py`), which tune to the measurement frequency on
  their own.
- **Transformers:** `balun`, `unun`, `autotransformer`, `link_coupling`, the
  measured ferrite ununs (`ft240_43_unun_49_1` and kin), and `bypass()` for
  "with and without".
- **Finite Q** on every reactor, and the **power budget**: watts lost in each
  branch.

What's missing is a way to build a station without writing Python. The
existing Schematic view draws a design's network, but you can't edit it.

### The station rail: an aid to writing `build_network()`

The rail is not a station editor that happens to export code. Its job is to
teach and write the Python we already have (Steve, 2026-11-23): "if you put
this component here, you get this schematic; if you put it there, you get
that one." What a user takes away is a `.py` design in house style, and the
rail is the way to get there without knowing the syntax first.

Three panes, kept in step:

```
 ┌ rail ───────────────────────────────────────────────────────────┐
 │ RIG ── RG-8X 30 m ── [auto L] ── 600 Ω 20 m ── ANTENNA (doublet)  │
 └─────────────────────────────────────────────────────────────────┘
 ┌ Python ─────────────────────────┐ ┌ schematic ──────────────────┐
 │ def build_network(self):         │ │  (the existing Schematic     │
 │     return Network(              │ │   view, drawn from the same  │
 │       ports=[PortVirtual("rig"), │ │   Network, loss per box)     │
 │              PortOnWire("feed")],│ │                              │
 │ ▌     instances=[Instance(       │ │                              │
 │ ▌       "tuner", l_network_tuner │ │                              │
 │ ...                              │ │                              │
 └─────────────────────────────────┘ └──────────────────────────────┘
```

- **The Python is the main exhibit, not an export.** Every change rewrites
  `build_network()` and highlights the lines that changed: the new
  `Instance`, the renamed node, the line whose ends moved. Hovering a line
  lights its box on the rail and its part of the schematic, and the other
  way round.
- **The rig is pinned left and the antenna right.** The antenna box is any
  existing design (catalog, user `.py`, uploaded deck) and shows its feed
  ports.

### The placement gallery

Choosing a component does not ask the user to wire it. It lists **every
valid place it can go**, as a row of cards, and the user picks one:

```
 Add: shunt shorted stub
 ┌ at the feed ───────┐ ┌ at the shack ──────┐ ┌ after the tuner ───┐
 │ [mini schematic]   │ │ [mini schematic]   │ │ [mini schematic]   │
 │ + Instance("stub", │ │ + Instance("stub", │ │ + Instance("stub", │
 │   ..., at="feed")  │ │   ..., at="shack") │ │   ..., at="li")    │
 │ SWR 1.3  −0.4 dB   │ │ SWR 2.9  −1.8 dB   │ │ SWR 1.1  −0.6 dB   │
 └────────────────────┘ └────────────────────┘ └────────────────────┘
```

- Each card carries its **schematic**, its **code change** and **three
  numbers**: SWR at the rig, total loss, and power reaching the antenna.
- The tool enumerates the topologies and the user chooses between circuits
  that make sense. That is the break from SimNEC: you pick among valid
  circuits rather than draw one. It also covers part of what free schematics
  would give (a shunt at the feed against a shunt at the shack), with no free
  wiring.
- Invalid placements don't appear (a second self-tuning tuner; a series part
  across the rig). Placements that are valid but questionable appear with an
  advisory (coax straight onto a balanced feed: "feedline currents are not
  modelled").
- Moving an existing box opens the same gallery for that box.
- **Later: ghost placements.** Dragging a box along the rail previews each
  card's schematic and numbers at the drop point, the same data as the
  gallery in a gesture.

### How it differs from SimNEC

SimNEC's circuit side is a general schematic: place parts anywhere and wire
them, which makes a novice decide the topology before they know what a
station looks like. Here:

- **The code is the product.** The user ends with a design file they can
  read, keep and edit, in the same style as the catalog.
- **Placement is chosen, not drawn.** The gallery enumerates and compares.
- **The antenna is a solved box,** not an imported impedance table. Change
  the antenna and every card re-solves.
- **The numbers sit on the drawing,** per card and per box.

### Under the hood

- **Station model:** an ordered chain of component records between the rig
  and the antenna's feed port, with generated node names (`rig`, `shack`,
  `li`, `bal`, `feed`). Components are the `station.py` factories,
  `TL.from_cable` over `CABLES`, and the stubs.
- **Codegen:** the model renders to house-style Python. The targets are the
  catalog designs that already hold stations, and generating their chains
  must reproduce their networks: `invvee_coax_station` (coax),
  `folded_invvee_balun` (coax then balun), `efhw_sloper` (coax then unun),
  `doublet_ladder_tuner` (tuner then 600 Ω line), `skyloop_lmatch` (L match).
- **Attaching to any design:** the server shadows the design's
  `build_network` with the compiled network, the hook `_apply_plane`
  (`web/adapter.py`) already uses for measurement planes. That works for
  sandboxed designs too, so a station never enters the sandbox. A design fed
  by a plain `ex` on a wire, with no network, needs its fed wire named and
  that source made a `PortOnWire` first.
- **Gallery solves:** one network solve per card. Only the circuit changes
  between cards, so the antenna's port admittance can be solved once and
  reused.
- **Reading code back:** a parser for the house style only, through `ast`,
  never `exec`. Code outside that style is shown, not edited on the rail.
  Generated code can run without the sandbox; once a person edits it, it
  goes through the user-design trust check like any `.py`.
- **Junction probes** (Z, SWR, forward and reflected power at each node)
  need the one piece of solve work: the reducer holds the full node vector
  but returns only port voltages. `AutoMatchReducer._load_impedance`
  (`auto_match.py`) already computes Z looking toward the antenna at an
  internal node, and is the template.

### Prototype (throwaway)

Before S1 proper, a prototype to see whether code + gallery reads well. It
may be thrown away, so it skips polish:

- a standalone page, not a carousel view, so no view registry or fixtures
  move;
- a chain model, codegen and placement enumeration in one backend module,
  with the codegen gate (catalog chains reproduce the catalog networks);
- one design's antenna to start, at one frequency;
- no probes, no ghost placements, no reading code back.

### The feedline as a wire (shield currents)

Steve, 2026-11-23: modelling the coax shield as a wire should be easy. This
is the place where the station and the antenna meet, so it is sketched
here, not settled.

**The physics, briefly.** Inside the coax, the signal travels between the
centre conductor and the inside of the shield. That part is a transmission
line, and the rail models it today. The *outside* of the shield is a
separate conductor. At the feedpoint it joins the side of the antenna the
shield is soldered to. From there it runs back to the station and ends at
whatever the rig's chassis is grounded to. Current on that outer surface
(common-mode current) radiates, detunes the antenna, and is what a choke is
for. NEC users model it by hand: a wire along the coax's route, joined to
the antenna at the feed, with an `LD` load where the choke sits.

**What the rail would do:**

1. A coax box gets an optional **route**, a path in 3-D from the feedpoint
   to the station: down the mast, along the ground, into the shack. With no
   route it stays a pure line, as today. With a route, it is also geometry.
2. The route becomes a **wire for the outer shield**, with the cable's outer
   radius and its jacket (the jacketed-wire machinery, momwire's insulated
   `WireSpec`), joined at the feed to the antenna side the shield connects
   to. The rail asks which side, or reads it from the balun box.
3. A **choke** box placed on a routed coax becomes a lumped impedance on that
   shield wire at its position along the route. Its impedance comes from the
   choke's own data (the ferrite models in `ferrite.py`, or a measured R + jX
   table).
4. The **station end** of the shield wire terminates in a "station ground"
   box: a ground rod (a wire into the soil), a lumped impedance, or the rig
   floating.
5. A **balun** at the feed changes what the shield wire joins. A current
   balun is a choke at distance zero; a voltage balun leaves the shield
   joined to one side.

So the rail and the 3-D view become two views of one object. The rail shows
the coax as a line with loss and SWR; the Antenna view draws the same coax
as a wire along its route, with its common-mode current shown in colour
like any other wire. This is also where the rail stops being like SimNEC:
there the feedline is only ever a circuit.

**What has to exist first:**

- A **port that splits**: the feed becomes a three-terminal junction (centre
  to one arm; shield inside to the other arm; shield outside to the shield
  wire). The network side has `PortOnWire` today. It needs a way to say "the
  line's return terminal is this junction, and a wire also leaves from it",
  without double-counting the shield inside and outside. This is the core
  modelling question, and it needs a measurement plan against a reference
  (a hand-built NEC deck of the same station) before any UI.
- **Routes as geometry** from the station side: a TransformStack path that
  belongs to a rail box, not to `build_wires()`. Block programs and catalog
  designs then both get the shield wire without being edited.
- **Ground contact** for the station end (a rod or radials at the shack).
  momwire already serves wires into the Sommerfeld ground.

Open: whether the shield wire should exist only when a route is set, or
whether every coax gets a default route (straight down from the feed, then
along the ground to a default shack position), so common-mode currents show
up without the user asking. The second is more honest and more surprising.

### Station templates

- **Dipole on coax:** rig, RG-8X 30 m, antenna.
- **Doublet with ladder line and a tuner:** rig, short coax, auto tuner, 1:1
  current balun, 450 Ω 20 m, antenna.
- **EFHW with 49:1:** rig, coax, choke, 49:1 unun, wire.
- **Remote tuner at the feedpoint:** rig, long coax, auto tuner, antenna.
- **Vertical with a choke at the feedpoint:** rig, coax, choke, antenna.

## Help for novices

- **Templates first.** "New design" opens a gallery: dipole, inverted vee,
  hentenna, quad loop, 2-element yagi, vertical with radials. Each opens
  already solving.
- **λ by default.** Lengths default to wavelength fractions at the design
  frequency, with metres shown beside them. Changing the frequency rescales
  the antenna, which is what a novice expects.
- **Snapping.** In the Antenna view, dragging a point snaps to grid,
  existing points and axes, and writes the numbers back into the block.
  Exact coincidence is the default (G3).
- **Plain refusals.** The existing refusal text, attached to the block:
  "these two wires cross without a junction", "the feed is on a wire that
  isn't connected to anything", "this wire is shorter than its radius".
- **A "why" hint per block**, one sentence of physics where it matters:
  "Mirroring the arm makes the antenna symmetric, so the feed sees a balanced
  load."
- **First solve on the first block.** A lone wire block with a feed already
  shows an impedance, so there's something to look at from the start.

## Where it lives

- **A view first.** "Blocks" joins `VIEWS` in `lib/view.ts` (one metadata
  entry and one render entry in `viewRegistry.tsx`, as every view does). It
  is unpinned by default, and not stale while optimizing, since it describes
  the current knobs, as the Schematic view does. The phone carousel picks it
  up from the same registry; on a phone it is usable for templates and
  parameter edits, while building from scratch wants a desktop.
- **Pop-out window second.** `/blocks?session=…` opens the editor alone,
  kept in step with the main window over a `BroadcastChannel`. Edits there
  re-solve in the main window. This suits a wide second screen.
- **Library: Blockly** (Google, Apache-2.0), the engine behind most
  Scratch-style editors. It is mature on touch and keyboard, has
  accessibility work behind it, and ships a code-generator framework. The
  alternative is a hand-built React editor, which gives full control of the
  look at the price of drag-and-drop, undo and touch handling we'd have to
  build ourselves. My recommendation is Blockly with a custom theme from our
  tokens; it's open question Q1.

## Testing

- **Interpreter ≡ generated Python.** For every template and a fuzzed set of
  block programs, the wires from the interpreter must equal, bit for bit, the
  wires from `exec`-ing the generated `.py` in a test. This is the gate that
  keeps G1 true; a disabled-path probe (codegen that drops a transform) must
  fail it.
- **Templates against their catalog twins.** The block dipole's impedance
  matches `dipoles.invvee`'s dipole variant at the same knobs, and likewise
  for the others.
- **Round trip.** generate → save → reopen gives the same tree; a hand-edited
  file is detected, never silently reparsed.
- **Safety.** The expression parser rejects everything outside its grammar
  (attribute access, calls other than the listed functions, names other than
  params and λ), with a fuzz test on it.
- **Frontend.** Vitest for the block → JSON serialisation and the
  selection link to the Antenna view; one Playwright run that builds a dipole
  from an empty workspace and reads the impedance.

## Phases

The station rail goes first (Steve, 2026-11-23):

- **S0. Prototype** (throwaway): the code pane, the rail and the placement
   gallery on a standalone page, one design, one frequency. See
   "Prototype (throwaway)" above.
- **S1. Station rail.** The three panes and the placement gallery over the
   existing `station.py` components, on any design, with junction probes and
   A/B rails. Reading house-style code back onto the rail. The only engine
   work is returning per-junction probes.
- **S2. The feedline as a wire.** The split feed port and its measurement
   against a hand-built NEC deck first, then routes, chokes on the shield,
   and the station ground.

Then the block editor:

1. **Spine (backend only).** `wire_spec`, `path`, `mirrored` and
   named points in `transform.py`, adopted by two or three catalog designs;
   the JSON schema, the interpreter, codegen and the equivalence test. A CLI
   flag runs a block JSON file, so the whole pipeline is testable before any
   UI exists.
2. **Editor.** The Blocks view with Blockly, the palette above minus loads,
   the live Python panel, templates, errors on blocks, and save as `.py` with
   the trailer. Local install first, then hosted, where block designs need no
   jail.
3. **Loads and traps on the antenna's wires** as blocks.
4. **Direct manipulation.** Dragging points in the Antenna view writes back
   to blocks; the pop-out window.

## Open questions for Steve

- **Q1. Blockly or our own editor?** Blockly gets a working editor far sooner
  and handles touch and accessibility; our own matches the app's look
  exactly. I'd start with Blockly.
- **Q2. Named points across transforms.** They make connectivity exact
  anywhere (G3), but a point's meaning then depends on where it was
  declared. Alternative: allow joins only inside one transform block, and
  have "both sides" and "repeat" share their seam points automatically.
  Simpler to explain, less general.
- **Q3. Where block designs show up.** In the user-designs list beside
  hand-written ones, or as their own group?
- **Q4. Hosted sharing.** A block program is safe data, so a shared link
  could carry a whole design, as an uploaded deck's link does today. Do we
  want that in phase 2, or later?
- **Q5. Naming.** "Blocks", "Builder", "Design with blocks"?
## Decisions (Steve, 2026-11-23)

- **The station rail comes first** (was Q6). It sits on components that
  already exist and helps every existing design.
- **A chain to begin with, free schematics not ruled out** (was Q7). The
  worry is that a plain chain is too much like SimNEC. What makes it
  different is that the antenna is a solved box and the coax can be routed
  in space (the shield as a wire), so the rail and the 3-D view describe
  one station. A free-schematic mode can come later, for phasing networks
  and multi-feed designs, over the same component records.
- **The coax shield as a wire should be easy** (was Q8), but how is still
  open. See "The feedline as a wire" above; the split feed port is the
  first thing to design and measure.
- **Q2: joins stay inside one transform stack** (Steve, 2026-11-24). A point's
  name means a position in the frame of the block it was made in, so nothing
  about it is hidden. One stack of nested transforms is the whole model, as in
  1980s solid modelling. Where that would be awkward, `both sides` and
  `repeat` share their seam points automatically. Named points that cross
  blocks (the `st.point` / `st.wire` pair above) are not in the first version.

## Ideas (Steve, 2026-11-24)

- **Axis wires.** `st.wire_x(x0, x1)`, `st.wire_y(y0, y1)`, `st.wire_z(z0, z1)`
  lay a wire along the current frame's own axis, so a design does not spell
  the zero coordinates (built in the spine, with `st.path`). The block for
  it is the same: "wire along X from .. to ..".
- **Show the frame.** Clicking a statement in the code (or a block) draws the
  coordinate system that statement runs in, in the Antenna view: the origin
  and the three axes under every transform above it. The stack can record the
  matrix at each `emit`, so the editor needs nothing more than that and a
  small axes glyph. It teaches transforms better than any description.

## Hosted, eventually (Steve, 2026-11-24)

The authoring tools should run on the hosted app one day, which means no
arbitrary Python there. The way in is a stylized subset, not a sandbox for the
full language: the statements the tools write and read back (`st.path`,
`st.wire_x/y/z`, `with st.push_pop_tr(...)`, `Transform.*`, `st.hit`, numbers
and names) and a bounded `for i in range(n)` with a fixed cap on `n` and on
nesting, so a design cannot loop forever. No `while`, no imports, no
attribute access beyond that vocabulary. The explicit `for` + `with` loops
(no `st.repeat`) are already that shape. Postponed: the local prototype runs
plain Python until the subset is written down.
