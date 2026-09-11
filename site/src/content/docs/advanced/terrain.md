---
title: "Antennas on a levee: modelling real terrain"
description: An advanced worked example — why every flat-ground model of a hillside QTH points at the wrong sky, and how the faceted-terrain ground fixes it.
---

Every ground model on the [workbench](/reference/web/#the-ground-plane) —
Sommerfeld, reflection-coefficient, PEC — shares one assumption so basic it's
easy to forget it's there: the ground is an **infinite flat plane** at the
antenna's feet. For a suburban backyard that's fine. But plenty of the best
antenna sites are good *precisely because* the ground is not flat — a
hilltop, a bluff over the sea, a ridge. This example works one real site end
to end and shows that no flat model, at *any* height, tells the truth about
it — then does it properly with the **faceted-terrain ground**.

## The site

A 20 ft (6.1 m) mast stands on a levee crest 10 ft (3 m) wide with ~20°
slopes. One side drops 35 ft (10.7 m) to fresh water; the other drops 25 ft
(7.6 m) to farmland. An inverted-V for 20 m through 10 m hangs from the mast.

The question every model must answer is: *how high is this antenna?* And the
honest answer is: **it depends which direction you ask.** Straight up, it's
6.1 m over soil. Toward the water at a low angle, the reflection happens off
the water surface far below — the antenna is effectively 16.8 m high over
water. Toward the land, 13.7 m over soil. One antenna, three heights, two
grounds.

Geometry says which surface governs at each elevation angle — the specular
reflection point walks outward from the mast as the angle drops:

| elevation of departure | reflecting surface | effective model |
|---|---|---|
| above ~76° | the crest itself | 6.1 m over soil |
| ~30–76° | the slopes | transition (tilted facets) |
| below ~30° | the water / the plain | 16.8 m over water / 13.7 m over soil |

The band that matters for working distant stations — the lowest one — never
touches the ground the mast stands on.

## Two flat models, both wrong

Model the site flat at mast height (6.1 m over soil) — what the workbench
does by default — and on 15 m the solver reports a broad lobe peaking
**5.9 dBi at 36° elevation**. Model it flat at the water-side effective
height instead (16.8 m over water) and you get the textbook low antenna-over-
water pattern: a fine 8.1 dBi lobe at 12°, then deep interference nulls at
25° and 60°.

The terrain model — same inverted-V, same mast — says the truth is neither:

| elevation | terrain (water side) | flat 6.1 m/soil | flat 16.8 m/water |
|---|---|---|---|
| 4° | **0.9** | −8.1 | 1.9 |
| 9° | **6.2** | −1.5 | 7.3 |
| 13° | **7.1** (peak) | 1.3 | 8.1 |
| 30° | **−0.2** | 5.7 | 0.6 |
| 36° | **−1.3** | 5.9 (peak) | ≈6 |
| 75° | **2.2** | 2.2 | 3.1 |

*(15 m, dBi along the elevation cut toward the water.)*

Read the two failure modes off the columns:

- The **flat-at-mast-height** model misses the entire DX story. At 9° — a
  workable one-hop angle on 15 m — it reports −1.5 dBi; the real site has
  **6.2 dBi** there, nearly 8 dB more. Worse, its confident 36° "main lobe"
  points at a part of the sky where the real pattern is 8 dB below its own
  peak. Aim your expectations by this model and you'll credit the wrong
  propagation for every contact.
- The **flat-at-effective-height** model gets the low angles nearly right
  (within ~1 dB below 15°) — that's why the effective-height rule of thumb
  survives — but its multipath structure above ~20° is fiction: the ±10 dB
  swings at 25°/45°/60° assume the same water plane extends *under the mast*,
  and it doesn't. The high-angle sky (short skip, NVIS-ish work) is governed
  by the crest at 6.1 m, which this model can't see.
- Above ~76°, all three columns agree — exactly where the validity table said
  the crest governs. The terrain model *contains* both flat models, each in
  the band where it's honest.

The levee's asymmetry survives too: at 4° the water side carries ~1.8 dB more
than the land side, and the first-lobe angles differ (water 18.5°→8.9°, land
22.9°→10.9° across 20→10 m) — none of which any single flat model can
express.

## What the terrain model actually does

The faceted terrain describes the surface *around* the site as a
piecewise-linear height profile per azimuth sector, each facet carrying its
own medium (εr, σ). It is deliberately **a far-field model**:

- **The current solve stays flat.** Soil and water can't be wire-gridded —
  only conductors can — so the impedance/current solution runs over a flat
  Sommerfeld ground with the *crest* facet's medium. That's physically
  defensible because near-field ground interaction is crest-local, and it's
  what keeps terrain solves exactly as fast as flat ones.
- **Each far-field ray reflects off its own facet.** Per direction, the
  model finds the facet the specular point lands on, tilts the incidence
  angle by the facet's slope, applies that facet's Fresnel coefficients, and
  adds the facet's height offset to the reflected path phase — which is how
  the antenna "gets taller" toward the drops.
- **What it doesn't do**: no surface roughness, no multiple bounces. Trust it
  for lobe positions and the first-order asymmetry.

**Diffraction: the second composer, and which one you are looking at.** Once a
profile has an edge in it, the three bullets above are not the whole story. A
second composer adds what the edge actually implies — shadowing, the source
imaged across each facet's own plane rather than a horizontal mirror, and UTD
wedge diffraction at the facet breaks. Where the two disagree it is the one to
believe, and the disagreement is not small. On the **hillside preset with a 45°
uphill slope**, the uphill band below that angle **collapses by 4 to 36 dB** —
because geometric optics was reporting a healthy +5.7 dBi *straight through 45
degrees of hillside*, having no concept of the hill being in the way, and the
diffracted composer is what puts it there. Just above the slope angle, where the
sky is clear, the same cut gets **up to 6 dB brighter** instead: a different
mechanism, the source imaged across the facet's own tilted plane rather than a
horizontal mirror, which puts a lobe where the specular formula had none. Peak
gain moves up, by +0.4 to +2.6 dB across the three presets at their defaults.
[A hillside, three ways](/advanced/hillside-three-models/) shows the two
composers and the tilted sloper side by side on one hill.

It costs about a second per pattern where the specular composer costs 17 ms,
and it is paid **per direction**, so no warm-up or cache turns it into a
drag-time field. So the workbench draws the specular field while a knob is
moving and composes the diffracted one a moment after it settles; the corner of
each polar chart says which one is on screen. In Python it is simply the
default — `Terrain(...)` and all three preset constructors carry
`diffraction=True`, and `diffraction=False` asks for the specular model.

**The impedance does not move.** Not approximately: `dZ = 0` on every preset.
The current solve is the flat crest-medium Sommerfeld one either way, which is
why the readout numbers stay put while the lobe changes shape.

Two limits of the diffracted composer are worth knowing, because both look like
bugs and neither is:

- **Near the zenith**, both composers are computing a number very close to zero
  for most antennas, and they get there by different arithmetic. A vertical's
  zenith null reads −319 dBi through one and −322 through the other; that is
  agreement about a null, not a 3 dB disagreement about a field. Read the dip,
  not its depth.
- **A mast standing right on a crest edge** puts its own structure inside that
  edge's near zone, where treating the edge as a diffracting wedge is the
  weakest assumption in the whole calculation. The model will answer; the answer
  is not worth much. Move the mast a metre back from the break and the question
  goes away — which is also what you would do on the actual hill.

It's cross-checked against an independent implementation: NEC-2's two-medium
cliff (`GD` card) agrees with the equivalent single-cliff terrain to within a
constant ~0.1 dB from 3° to 60° elevation. (If you try that comparison
yourself, mind the trap: NEC-2 silently ignores `GD` under the normal `RP 0`
pattern request — the cliff only reaches the pattern in `RP` modes 2/3/5/6.)
A degenerate single-flat-facet terrain reproduces the plain finite ground
bit-for-bit through the specular composer, and to within 1e-8 dB through the
diffracted one — a single unbroken facet has no wedge to diffract from — so
switching the feature on costs nothing when the ground really is flat.

## Driving it

**In the [simulator](/reference/web/#faceted-terrain)**: ground plane →
**terrain**, then pick the **levee** preset (crest width, slope, the two
drops, water bearing), **cliff** (edge, drop, bearing, arc), or **hillside**
(a bench on a slope — flat width, uphill slope, downhill slope; no bottom
reference exists or is needed, since the slope itself is the reflector). The elevation
cut's bearing dial uses the same azimuth convention as the water bearing, so
leaving both at 0° slices straight through the asymmetry; pin the pattern on
a flat ground first and the ghost overlay shows exactly what the facets
change. Both engine families run it — momwire natively, PyNEC as a hybrid
(NEC solves the currents over the crest-medium Sommerfeld ground, the server
applies the facet far field to those currents).

**In Python**, the same two presets plus arbitrary profiles:

```python
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.terrain import levee_terrain

terrain = levee_terrain(
    crest_width=3.0,
    slope_deg=20.0,
    drop_water=10.67,
    drop_land=7.62,
    water=(80.0, 0.005),
    land=(13.0, 0.005),
    water_azimuth=0.0,  # +x faces the water
)
eng = MomwireEngine(builder, ground=("terrain", terrain))
```

`cliff_terrain(...)` builds the single-drop case, `hillside_terrain(...)`
the bench-on-a-slope, and the underlying
`Terrain(sectors=(Sector(..., facets=(Facet(...), ...)),))` dataclasses
accept any piecewise profile per azimuth sector — a gully on one bearing, a
rising hill on another — as long as each sector's last facet extends to
infinity and all sectors agree on the crest medium (it's the impedance
ground).

## When to reach for it

Flat ground is still the right default — terrain adds information only when
the site has real relief within a few wavelengths of the mast. The strongest
signals that it's worth switching on: the ground falls away in the directions
you care about (the flat model is understating your low-angle gain), the
drop-off differs by direction (no single flat model can be right), or land
meets water (the media differ as much as the heights). And keep the model's scope in
mind: the specular composer sharpens *where the lobes point* and says nothing
trustworthy about what happens behind a hill; the diffracted one is the one to
reach for when behind-the-hill is the question you came with.
