# Designing antennas in this folder

This folder holds **your** antenna designs for the Antenna Designer app.
Each `.py` file here is one antenna. Drop a file in, refresh the web page,
and it shows up under **"Your designs"**.

If you're reading this as Claude Code: the user wants you to write or edit an
antenna design in this folder. Follow the contract below exactly, then tell
them to refresh the page (and to check the "failed to load" panel if their
design has an error).

## The contract

A design file must:

1. **Be named** `lowercase_with_underscores.py`. The file name becomes the
   antenna's name in the app (`my_dipole.py` → `user.my_dipole`). No spaces,
   no dots except the `.py` extension, one antenna per file.
2. **Define a class named exactly `Builder`** that subclasses `AntennaBuilder`.
3. **Import only** from `antennaknobs` and the Python standard library.
   Do **not** import other files in this folder — keep each one
   self-contained. (Importing an installed built-in as a base class is fine,
   e.g. `from antennaknobs.designs.dipoles.invvee import Builder as InvVee`.)
4. Provide a **`default_params`** mapping (use `MappingProxyType(...)`) and a
   **`build_wires(self)`** method.

Start from `TEMPLATE.py` in this folder — copy it, rename it, edit it.
Every built-in design follows this same contract, so copying a file out of
the installed package's `antennaknobs/designs/` folders into this one also
works verbatim as a starting point.

The same file also works from the command line: once `my_dipole.py` is in
this folder, run e.g. `antennaknobs draw --builder user.my_dipole` (or
`sweep`, `pattern`, …). Always address it with the `user.` prefix.
`antennaknobs list` shows every available design name (yours included).

## Safety: designs run only once you allow them

A design file is a full Python program that runs with your user privileges the
moment it loads — the whole language is available on purpose, because you need
it to describe an antenna. Nothing restricts what a design *can* do, so the
safety model is an explicit decision to allow it, like VS Code's "do you trust
the authors of this folder?" or Office's macro prompt: a user design in
`~/.antennaknobs/designs/` **does not run until you have allowed it.** In the
web app, designs awaiting your OK appear in a "designs need your OK to run"
panel where you can review and allow them; from the command line, use the
commands below.

The decision is remembered **per file, by its contents** — so a *new* file
someone gives you always asks first (it isn't covered by a design you allowed
earlier), and a previously-allowed file that later changes asks again.

- **A design you wrote:** allow it and your future edits so live-editing never
  re-prompts — `antennaknobs allow <name> --edits`.
- **A design someone sent you:** review it first — `antennaknobs screen path/to/file.py`
  shows what it does that's unusual (imports, file access, etc.) *without
  running it*. If you're satisfied, `antennaknobs allow <name>` allows that
  exact version; if the file ever changes, you'll be asked again.
- **Stop allowing one:** `antennaknobs disallow <name>`.
- The `screen` report is advisory, not a verdict — a flagged design isn't
  necessarily malicious, and a clean one isn't guaranteed safe (screening can't
  see through obfuscation or every corner of a big library like numpy). It's
  there to make your decision informed. **Only allow designs from sources you
  trust.** For a single-user machine you can allow everything up front with
  `ANTENNAKNOBS_TRUST_USER_DESIGNS=1`.
- The local web app has no login and no solve-size limits (those exist only on
  the shared public instance), so keep it on `localhost` — don't bind it to
  `0.0.0.0` or expose it to a network you don't fully control.

### Loading geometry from a data file

You may want to author geometry as **data** — a JSON or CSV wire list next to
your design. Prefer the confined helper on `AntennaBuilder` over raw
`open`/`pathlib`: it needs no extra imports and, unlike raw file access, can't
be pointed at your private files, so a data-driven design stays safe to share:

```python
from antennaknobs import AntennaBuilder, read_json

class Builder(AntennaBuilder):
    def build_wires(self):
        spec = read_json(self, "my_wires.json")   # file sits next to this .py
        ...
```

`read_data(self, name)` returns the file's text; `read_json(self, name)` parses
it. You pass `self` so the read is confined to *this* design's own folder. Both
are read-only, size-capped, and reject an absolute path, a `..` that climbs out,
or a symlink pointing elsewhere. A design shared as `my_design.py` +
`my_wires.json` is safe for someone to load: the data can only become antenna
geometry, never leave the machine.

### Loading a NEC card deck (`.nec`)

`read_nec(self, name)` loads a **NEC2 card deck** — the format xnec2c, 4nec2,
EZNEC, and antenna-handbook listings all speak — with the same folder
confinement as `read_json`.

**Set expectations with the user first: a NEC deck is frozen geometry, not a
parameterized design.** Coordinates are just numbers, so an imported deck
cannot offer the per-dimension knobs, `design_freq` band scaling, or
meaningful optimization that make native designs nice — the only knobs worth
adding to a deck stub are the measurement `freq`, a `height` lift (published
decks are usually drawn at z = 0, which would sit *in* the ground plane),
and a whole-geometry `scale` (a blunt uniform stretch, but enough to pull a
slightly-off deck onto frequency). Treat the import as a *viewer* for a
published deck; if the user wants to actually tune dimensions, port the
design to a native `AntennaBuilder`, using the deck as the source of
dimensions.

Import with `network=True` — it makes the deck's `.wire_tuples()` ready to
return from `build_wires` AND translates the deck's LD loading, TL
transmission lines, and (resistive) NT networks into the app's own
`build_network` branches, so the deck's matching/phasing actually acts:

```python
from antennaknobs import AntennaBuilder, read_nec

class Builder(AntennaBuilder):
    def build_wires(self):
        # specs=True: every wire keeps ITS OWN radius from the deck's GW
        # card (and its LD 5 conductivity), so a mixed-radius deck — a fat
        # driven element with thin radials — solves faithfully. No
        # build_wire_material() needed; each wire carries its spec.
        return read_nec(self, "my_yagi.nec", network=True).wire_tuples(specs=True)

    def build_network(self):
        # the deck's EX drive + its translated LD/TL/NT cards
        return read_nec(self, "my_yagi.nec", network=True).network()
```

(Without `specs=True` you get plain tuples and one whole-antenna wire
material: pair `wire_tuples()` with a `build_wire_material()` returning
`WireSpec(radius=deck.dominant_radius(), conductivity=deck.conductivity)` —
the pre-#388 recipe, still fully supported.)

Wires (GW/GA arcs/GH helices) and the geometry transforms (GM, GX, GR, GS —
including xnec2c's tag-range GS) are honoured, the deck's EX voltage sources
drive the exact segments the deck drives, and wires that cross other wires
at segment boundaries are split there so the crossing conducts (NEC connects
segment ends regardless of wire grouping). Lumped LD 0/1 loads, pure-R LD 4,
whole-structure LD 5 conductivity, TL cards (crossed lines, zero-length =
port separation, conductance end shunts), and all-real-Y NT cards translate
exactly; what can't be expressed (frequency-independent reactance, LD 2/3
distributed loading) is listed in `deck.ignored` with a per-card reason in
`deck.ignored_detail`. Ground (GN/GE) and output requests (RP/NE/...) are
always the app's own settings — expect readouts to differ from published
results that relied on those. Tell the user about it in the UI:
`deck.skipped_note()` renders the not-applied record (plus the deck's ground
request) as one informational sentence — put it under `ui_params["notes"]`
and the app shows it beneath the antenna selector.
Patch antennas (SP/SM) and tapered wires (GC) raise a clear error. The deck's
FR card is exposed as `deck.freq_mhz = (lo, hi)` — use it to seed `freq` and
`ui_params["meas_freq_range"]` so the design tunes on the deck's own band.
Do the seeding once at import time in a module-level helper, not per build
(see `nec_2m_yagi.py` in this folder if present for a worked example):

```python
def _seed_defaults_from_deck(cls):
    deck = read_nec(cls(), WIRES_FILE, network=True)
    params = dict(cls.default_params)
    ui = dict(params.get("ui_params", ()))
    if deck.freq_mhz:
        lo, hi = deck.freq_mhz
        params["freq"] = round(0.5 * (lo + hi), 3)
        ui["meas_freq_range"] = (lo, hi)
    note = deck.skipped_note()
    if note:
        ui["notes"] = note
    params["ui_params"] = MappingProxyType(ui)
    cls.default_params = MappingProxyType(params)
```

## `default_params`

Every key becomes a slider in the UI, accessed in `build_wires` as
`self.<key>`. Conventions:

- `freq` — measurement frequency in **MHz** (seeds the meas-freq slider).
  Always include it, and set it to your target band (e.g. `7.1` for 40m). See
  the tuning note under `build_wires` about pairing this with `design_freq`.
- Lengths/positions are in **metres**.
- Add a nested `"ui_params": MappingProxyType({...})` for UI hints. The most
  useful is `"default_view"`: `"xy"` (top-down), `"xz"`, or `"yz"` (side).
- A class-level `label = "Pretty Name"` sets the display name (optional).

Slider bounds and step are auto-derived (±50% around the default, fine
resolution). You usually don't need to specify them.

### Arranging the knobs (optional)

By default knobs auto-flow into the panel. To place them deliberately, add
a `"layout"` to a param's override dict — `{row, col, row_span, col_span}`,
1-indexed, all optional — and pin the grid width with a panel-level
`"layout": {"columns": N}` so the columns don't shift with the panel size:

```python
"ui_params": MappingProxyType({
    "layout": {"columns": 2},                 # 2-column knob grid
    "length": {"layout": {"row": 1, "col": 1}},
    "height": {"layout": {"row": 1, "col": 2}},
    "feed_z": {"layout": {"row": 2, "col": 1, "col_span": 2}},  # full-width
}),
```

## `build_wires(self)`

Return a list of straight wire segments. Each entry is:

```python
(start, end, n_segments, feed)
```

- `start`, `end` — `(x, y, z)` tuples in metres.
- `n_segments` — how finely to subdivide that wire. Use `self.nominal_nsegs`
  for the main radiator; fewer for short stubs (`max(1, self.nominal_nsegs // 7)`).
- `feed` — `1 + 0j` on the **single** segment the transmitter drives, `None`
  everywhere else. Exactly one segment in the whole antenna is the feed —
  unless the design models its feed system with `build_network` (see that
  section below), in which case the drive moves into the network and the
  feed wire is *named* instead.

**Feed convention:** put the feed on a tiny segment between two points a
small `eps` (e.g. 0.01 m) apart, with the radiator arms running outward from
those two points. Wires connect where they share an endpoint, so the arms and
the feed segment must share their centre points exactly. See `TEMPLATE.py`.

**Per-wire sizes (optional).** A design that mixes conductors — a fat
aluminium element with thin wire radials — can give any entry its own
`WireSpec` by returning a `Wire` named tuple instead of a plain tuple; the
two mix freely in one list:

```python
from antennaknobs import AntennaBuilder, Wire, WireSpec

TUBE = WireSpec(radius=6e-3)                       # 12 mm boom element
WIRE = WireSpec(radius=1e-3, conductivity=5.8e7)   # copper radial

(start, end, n_segments, feed)                     # plain tuple: design default
Wire(start, end, n_segments, feed, spec=TUBE)      # this wire is the fat tube
```

A wire without a `spec` uses `build_wire_material()` (or the 0.5 mm ideal).
PyNEC honors per-wire radius and loss exactly; momwire honors per-wire
loss/insulation and — on its default (BSpline) and sinusoidal solvers —
per-wire radius too (momwire#147). Specs describe physical wire stock —
scale knobs and transforms move geometry, never specs.

**Tuning on a band — use `design_freq` (strongly recommended).** To place an
antenna on a band *and be able to tune it there*, add a `design_freq` param
(MHz) plus a `length_factor` (a multiplier near 1.0), compute
`wavelength = 299.792458 / self.design_freq`, and build every dimension as a
fraction of `wavelength * self.length_factor`. This does two things at once:
it scales the geometry to the chosen frequency, **and** it makes the app's band
selector and the measurement-frequency slider follow `design_freq`. So a design
with `design_freq = 7.1` lands on 40m and tunes on 40m. This is how the built-in
designs work.

**Why this matters (the 40m trap):** without a `design_freq`, the geometry is
fixed metres and the measurement-frequency window stays parked near 14 MHz
(20m). A fixed-metre 40m antenna therefore *cannot be tuned on 40m* — the meas
slider won't reach 7 MHz. So if the user asks for any band other than 20–10m,
prefer `design_freq`. If you must keep fixed dimensions, instead widen the
measurement slider to the target band by adding
`"meas_freq_range": (low_mhz, high_mhz)` to `ui_params` (e.g. `(6.5, 8.0)` for
40m).

## `build_network(self)` — feedline, transformer, tuner (optional)

Without this method, the design is driven directly at its `build_wires`
feed segment. Adding `build_network` models the rest of the station — a
coax or ladder-line run, a balun/unun, a matchbox — as a circuit solved
*together with* the antenna, and re-references every readout (impedance,
SWR, gain, the power budget) to wherever the source sits. The concepts
are explained on the docs site under **Station modelling**.

Two changes, always together:

1. In `build_wires`, the driven segment **loses its inline drive** and
   instead *names* its wire with a 5-element tuple:
   `(start, end, n_segments, None, "feed")`. The name declares a port;
   which port is driven is now the network's business (so the "exactly
   one feed segment" rule above applies only to network-less designs).
2. Add `build_network` returning a `Network` — three fields, always:

```python
from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL

    def build_network(self):
        return Network(
            ports={
                "feed": PortOnWire("feed"),  # the named wire from build_wires
                "rig": PortVirtual("rig"),   # circuit-only node: the rig end
            },
            branches=[
                TL.from_cable("RG-8X", "rig", "feed", 20.0),  # 20 m of coax
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
```

- `ports` declares **every** name a branch or source references.
  `PortOnWire` must match a named wire (the port is a gap at that wire's
  middle segment — give the feed its own short wire, as in
  `TEMPLATE.py`); `PortVirtual` is a node with no geometry. Driving a
  virtual `rig` node is what makes the readouts rig-referenced.
- `branches` come from `antennaknobs.network`: `TL` / `TL.from_cable`
  (the `CABLES` catalog: `"RG-58"`, `"RG-8X"`, `"window-450"`,
  `"openwire-600"`, …), `Load` (series R/L/C in a wire — a trap, a
  terminating resistor), `TwoPort`, `Shunt`, `Transformer`. Reactive
  elements take a finite Q (`ql`, `qc`, `qlmag`) — that is where real
  boxes burn power, and the app itemizes it in the power budget.
- `sources` is usually one `Driven`.

**Prefer the pre-built boxes** in `antennaknobs.station` over raw
branches for the common cases — a tuner or transformer is one
`Instance`, parameterized in radio units (pF / µH), with keyword
arguments mapping the box's formal ports to your port names:

```python
from antennaknobs.network import Driven, Instance, Network, PortOnWire, PortVirtual, TL
from antennaknobs.station import unun

    def build_network(self):
        return Network(
            ports={
                "ant": PortOnWire("ant"),
                "pri": PortVirtual("pri"),   # unun's line-side terminals
                "rig": PortVirtual("rig"),
            },
            branches=[
                Instance(
                    "unun",
                    unun(turns=7.0, lmag_uH=8.0, qlmag=10.0),  # a 49:1
                    line="pri",  # formal → actual port map
                    ant="ant",
                ),
                TL.from_cable("RG-58", "rig", "pri", 5.0),
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
```

The stdlib: `t_network_tuner(c1_pF, c2_pF, l_uH, ql)`,
`l_network_tuner(series_l_uH, shunt_c_pF, ql)`, `unun(turns, lmag_uH,
qlmag, comp_c_pF)`, `balun(n, lmag_uH, qlmag)`, and `bypass()` — a
pass-through with a box's two-port interface, so swapping a tuner for
`bypass()` answers "what is this box buying me?" in a one-line change.
A box's internals are private (the T-network's midpoint is `tuner.m`,
auto-declared), and its loss rows group under the instance name in the
power budget.

Built-in designs to copy from: `dipoles.invvee_coax_station` (just
coax — the minimal case), `wire.efhw_sloper` (unun + comp cap + coax),
`wire.doublet_ladder_tuner` (ladder line + T-network tuner).

## Arrays of identical elements (advanced)

For a phased array of N copies of one element, `antennaknobs` exposes
`Array1x2Builder`, `Array1x4Builder`, `Array2x2Builder`, `Array2x4Builder`.
These wrap an element `Builder`. For a first design, stick to a single
`build_wires`; reach for arrays only once a single element works.

## How to check your work

1. Save the file. **Refresh the web page** (no server restart needed).
2. The antenna appears under "Your designs". If it doesn't, look at the
   **"designs that failed to load"** panel — it shows the file, the error
   type, and the line number. Fix and refresh again.
3. Pick it in the selector and look at the geometry plot, the Smith chart, and
   the impedance readout. Adjust `default_params` and `build_wires` until the
   resonance and pattern look right.

## Good prompts to give Claude Code

- "Make me a 40-meter off-center-fed dipole fed 1/3 from one end."
- "Design a 2-element 20-meter quad loop, driven element plus a reflector."
- "Take my_dipole.py and add an adjustable height-above-ground slider."
- "My design loads but resonates at 32 MHz — shorten it to hit 28.5 MHz."
