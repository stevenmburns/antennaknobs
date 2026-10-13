---
title: Writing designs with Claude Code
description: Drop your own antenna into the workbench — and let Claude Code write the Python for you from the seeded contract.
---

The workbench loads **your** designs alongside the built-ins. Each `.py` file in
your designs folder becomes one antenna under **"Your designs"** (the `user.*`
namespace) — drop a file in, refresh the page, and it shows up. Because each
design is just a small Python class, [Claude Code](https://claude.com/claude-code)
can write or edit one for you from a contract that's seeded right into the folder.

## Your designs folder

On first run the app creates **`~/.antennaknobs/designs/`** (override with the
`ANTENNAKNOBS_USER_DIR` environment variable) and seeds three reference files
into it:

- **`TEMPLATE.py`** — a complete, working example dipole. Copy it, rename it, edit
  it.
- **`TERRAIN_TEMPLATE.py`** — a complete, working example terrain (a bluff
  over a lake). See [A terrain of your own](#a-terrain-of-your-own) below.
- **`CLAUDE.md`** — the authoring contract, written *for Claude Code*. It's the
  context that lets Claude write a correct design on the first try.

All three are refreshed from the package on every startup (they're documentation, not
your content), so an upgrade brings the latest authoring guidance. Your own
`*.py` files are never touched.

A design is also a first-class CLI antenna: once `my_dipole.py` is in the folder,
`antennaknobs draw --builder user.my_dipole` (or `sweep`, `pattern`, …) works,
and `antennaknobs list` shows it.

## The workflow

1. **Open Claude Code in the folder:**
   ```bash
   cd ~/.antennaknobs/designs
   claude
   ```
   Claude reads the seeded `CLAUDE.md` as context automatically.
2. **Ask for an antenna in plain language** — for example:
   - *"Make me a 40-meter off-center-fed dipole fed 1/3 from one end."*
   - *"Design a 2-element 20-meter quad loop — driven element plus a reflector."*
   - *"Take my_dipole.py and add an adjustable height-above-ground slider."*
   - *"My design loads but resonates at 32 MHz — shorten it to hit 28.5 MHz."*
3. **Refresh the web page.** A design file is a Python program that runs on your
   computer, so the first time it appears under **"designs need your OK to
   run"** — click it to see what it does, then **Allow it to run** (choose
   **Allow + my edits** for a design you'll keep editing, so it won't ask again
   each time you save). It then shows under "Your designs." From the command
   line the same gate is `antennaknobs allow user.my_dipole`. If instead it
   lands in the **"designs that failed to load"** panel, that's a real error —
   the panel shows the file, error, and line number; paste that back to Claude
   and iterate.
4. **Adjust it** with the knobs, watching the pattern plots and the impedance
   readout, until the resonance and pattern look right.

## A terrain of your own

The same folder holds a second kind of file: a **terrain**, the shape of the
ground around your mast. The workbench has three built in (levee, cliff and
hillside, see [Faceted terrain](/reference/web/#faceted-terrain)). A terrain
file adds one of your own to that list, for every antenna, built-in ones
included.

The rules are the design rules with one name changed:

- **One terrain per file, and the file's name is the terrain's name.**
  `lake_bluff.py` is listed as "lake_bluff". The name cannot be `levee`,
  `cliff` or `hillside`.
- The file binds one `TerrainPreset` to the name **`TERRAIN`** and leaves its
  `name` and `label` out.
- The file defines **no `Builder`**. A file is one antenna or one terrain.
- It imports only from `antennaknobs` and the Python standard library.

A terrain is a few sliders and a function from their values to a `Terrain`:

```python
from antennaknobs.terrain import Facet, Sector, Terrain, TerrainField, TerrainPreset

SOIL = (13.0, 0.005)  # relative permittivity, conductivity in S/m
LAKE = (80.0, 0.001)


def build(v):  # v: each slider's value by key, already inside its min..max
    return Terrain(
        (
            Sector(
                0.0,
                360.0,
                (
                    Facet(v["edge_m"], 0.0, *SOIL),  # flat out to the edge
                    Facet(v["edge_m"] + 2 * v["drop_m"], -v["drop_m"], *SOIL),
                    Facet(None, -v["drop_m"], *LAKE),  # the lake, to the horizon
                ),
            ),
        )
    )


TERRAIN = TerrainPreset(
    tooltip="Flat ground out to a bluff, a bank falling 1 in 2, then lake.",
    media_note="media: lake εr=80 σ=0.001 · soil εr=13 σ=0.005",
    fields=(  # key, label, default, min, max, step, unit
        TerrainField("edge_m", "edge of the bluff", 15.0, 1.0, 500.0, 1.0, "m"),
        TerrainField("drop_m", "drop to the lake", 6.0, 0.5, 100.0, 0.5, "m"),
    ),
    build=build,
)
```

Each `Facet` is a straight piece of ground along one bearing: how far from the
mast it ends, how high the ground is there (negative is below the mast's
ground), and what it is made of. The last one has `x1=None` and runs to the
horizon. A `Sector` applies one chain of facets to a range of bearings; the
sectors together cover the full circle. `TERRAIN_TEMPLATE.py` in the folder is
a longer example with a lake on one side only.

Unlike the built-in terrains, the ground and water are yours to choose: put
them in the facets, and say what you chose in `media_note`, which is the line
shown under the sliders.

To use it, save the file and **reload the page**. A terrain file is a Python
program too, so it asks for the same OK to run as a design. Then set the ground
type to **terrain** and pick it from the list. The list is read when the page
loads, so a new or renamed terrain needs a reload; if it is not listed yet,
reload once more. A file with a mistake in it appears in the **"designs that
failed to load"** panel with the error and line number, like a broken design.

## The contract (what Claude follows)

The seeded `CLAUDE.md` is authoritative; in brief, a design file must:

- Be named `lowercase_with_underscores.py` — the name becomes the antenna's name
  (`my_dipole.py` → `user.my_dipole`).
- Define a class **`Builder`** subclassing `AntennaBuilder`.
- Provide a **`default_params`** mapping (every key becomes a knob, read as
  `self.<key>` in the build) and a **`build_wires(self)`** method returning
  `(start, end, n_segments, feed)` tuples — write `None` for `n_segments`
  (the framework meshes at the design density; never hand-assign counts) and
  declare a `design_freq` param. Exactly **one** wire carries the feed
  `1 + 0j`, the rest `None`.
- Import only from `antennaknobs` and the standard library.

```python
from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire


class Builder(AntennaBuilder):
    default_params = {
        "design_freq": 14.1,  # MHz — the band this is cut for
        "freq": 14.1,  # MHz — measurement frequency
        "length_factor": 0.96,
        "height": 10.0,  # metres
        "ui_params": {"default_view": "xz"},
    }

    def build_wires(self):
        wavelength = self.design_wavelength  # = C_LIGHT_MHZ_M / design_freq, in metres
        h = (wavelength / 4.0) * self.length_factor
        z, eps = self.height, 0.01
        return [
            Wire((0.0, -h, z), (0.0, -eps, z)),  # left arm
            Wire((0.0, eps, z), (0.0, h, z)),  # right arm
            Wire((0.0, -eps, z), (0.0, eps, z), ex=1 + 0j),  # driven feed gap
        ]
```

:::tip[The `design_freq` rule — resonate across bands]
To put an antenna on a band *and keep it tunable there*, size every dimension as
a fraction of `self.design_wavelength` (the free-space wavelength at
`design_freq`, in metres — an `AntennaBuilder` property, so you never write the
bare `299.792458` constant), times a `length_factor` near 1.0. That scales the
geometry with the band selector, so
one design resonates anywhere you point it. Skip it — freeze the dimensions in
metres — and changing the band no longer resizes the antenna: the meas-freq
slider still reaches any band you select, but a fixed-metre wire only *resonates*
on the one band its dimensions happen to suit.
:::

:::note[Alternate knob-sets: variants are overlays]
Ship alternate tunings as `<variant>_params` class attributes alongside
`default_params` (`opt_params`, `z100_params`, …); a user selects one with
`name:variant`. A variant lists **only the keys it changes** — the rest inherit
from `default_params` — so keep them to the deltas. See
[Variants are overlays](/reference/cli/#variants-are-overlays).
:::

For path-shaped geometry (loops, vees, rhombics), `build_wires` can fly a
[`Drone`](/reference/drone-transform/) instead of computing corners by hand —
return `drone.wires()`. Arrays of identical elements have dedicated builders
(`Array1x2Builder`, `Array2x2Builder`, …); reach for those only once a single
element works.
