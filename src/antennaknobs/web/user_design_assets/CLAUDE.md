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
  everywhere else. Exactly one segment in the whole antenna is the feed.

**Feed convention:** put the feed on a tiny segment between two points a
small `eps` (e.g. 0.01 m) apart, with the radiator arms running outward from
those two points. Wires connect where they share an endpoint, so the arms and
the feed segment must share their centre points exactly. See `TEMPLATE.py`.

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
3. Pick it in the selector and look at the geometry plot, the SWR curve, and
   the impedance. Adjust `default_params` and `build_wires` until the
   resonance and pattern look right.

## Good prompts to give Claude Code

- "Make me a 40-meter off-center-fed dipole fed 1/3 from one end."
- "Design a 2-element 20-meter quad loop, driven element plus a reflector."
- "Take my_dipole.py and add an adjustable height-above-ground slider."
- "My design loads but resonates at 32 MHz — shorten it to hit 28.5 MHz."
