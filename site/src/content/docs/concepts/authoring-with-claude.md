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
`ANTENNAKNOBS_USER_DIR` environment variable) and seeds two reference files into
it:

- **`TEMPLATE.py`** — a complete, working example dipole. Copy it, rename it, edit
  it.
- **`CLAUDE.md`** — the authoring contract, written *for Claude Code*. It's the
  context that lets Claude write a correct design on the first try.

Both are refreshed from the package on every startup (they're documentation, not
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
4. **Tune it** with the knobs, the SWR curve, and the impedance readout until the
   resonance and pattern look right.

## The contract (what Claude follows)

The seeded `CLAUDE.md` is authoritative; in brief, a design file must:

- Be named `lowercase_with_underscores.py` — the name becomes the antenna's name
  (`my_dipole.py` → `user.my_dipole`).
- Define a class **`Builder`** subclassing `AntennaBuilder`.
- Provide a **`default_params`** mapping (every key becomes a knob, read as
  `self.<key>` in the build) and a **`build_wires(self)`** method returning
  `(start, end, n_segments, feed)` tuples — exactly **one** segment carries the
  feed `1 + 0j`, the rest `None`.
- Import only from `antennaknobs` and the standard library.

```python
from antennaknobs import AntennaBuilder


class Builder(AntennaBuilder):
    default_params = {
        "design_freq": 14.1,   # MHz — the band this is cut for
        "freq": 14.1,          # MHz — measurement frequency
        "length_factor": 0.96,
        "height": 10.0,        # metres
        "ui_params": {"default_view": "xz"},
    }

    def build_wires(self):
        wavelength = 299.792458 / self.design_freq
        h = (wavelength / 4.0) * self.length_factor
        z, eps = self.height, 0.01
        arm = self.nominal_nsegs
        return [
            ((0.0, -h, z), (0.0, -eps, z), arm, None),       # left arm
            ((0.0, eps, z), (0.0, h, z), arm, None),         # right arm
            ((0.0, -eps, z), (0.0, eps, z), 1, 1 + 0j),      # driven feed gap
        ]
```

:::tip[The `design_freq` rule — resonate across bands]
To put an antenna on a band *and keep it tunable there*, size every dimension as
a fraction of `wavelength = 299.792458 / self.design_freq` (times a
`length_factor` near 1.0). That scales the geometry with the band selector, so
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
