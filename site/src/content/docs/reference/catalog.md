---
title: Design catalog
description: The built-in antenna designs, by family — each one a readable AntennaBuilder you can copy as a starting point.
---

Every built-in design is an [`AntennaBuilder`](/concepts/model/) whose source is
meant to be read and copied. Address them as `family.name` (the same names
`python -m antennaknobs list` prints), and open any in the [live
simulator](https://app.antennaknobs.dev/) to drag its knobs. Many are modelled
after L. B. Cebik (W4RNL)'s articles.

## Dipoles

| Design | Notes |
| --- | --- |
| `dipoles.invvee` | Inverted-vee dipole (the default quickstart example) |
| `dipoles.folded_invvee` | Folded inverted-vee |
| `dipoles.ocf_dipole` | Off-center-fed dipole (Windom) — a half-wave fed away from the middle |
| `dipoles.dipole_turnstile` | Crossed dipoles fed in phase quadrature |
| `dipoles.koch_dipole` | Koch fractal dipole |
| `dipoles.short_dipole_loaded` | Center-loaded shortened dipole (a Load-branch showcase) |

## Loops

The delta loop is the catalog's teaching showpiece — it exists **nine ways**, a
guided tour (in this order) from the most explicit build to the version shipped,
showing how flexibly geometry can be expressed (see [Many ways to express
geometry](/concepts/authoring/)):

| Design | Built by |
| --- | --- |
| `loops.delta_loop_sides` | side length written as direct coordinates (all the trig on the page) |
| `loops.delta_loop_drone` | `Drone` (3D turtle) flight; only the top edge is a computed length |
| `loops.delta_loop_flown` | `Drone`, top laid by `forward_through_plane` — no explicit trig, no reflection |
| `loops.delta_loop_marked` | `Drone` + labelled nodes (angle + side, trig-free) |
| `loops.delta_loop_reflected` | `Drone` point-finder + reflection + `build_path` |
| `loops.delta_loop_solved` | the reflected build, with the side solved by `brentq` |
| `loops.delta_loop_hoisted` | top-anchored by a second-pass z recalc (side solved for the perimeter) |
| `loops.delta_loop_plane` | top-down and solved: `forward_to_plane` lands the feed where the slant crosses `y = eps` |
| `loops.delta_loop` | the shipped version: coordinates from a closed-form apex height |

Other loops: `loops.delta_loop_slanted`, `loops.inv_delta_loop`,
`loops.horizontal_loop` (full-wave "loop skywire") and its `Drone` twin
`loops.horizontal_loop_drone`, `loops.diamond_loop` (+ `diamond_loop_turnstile`),
`loops.quad` (2-element cubical quad beam), and `loops.bisquare` (a two-wavelength
broadside curtain).

## Beams

| Design | Notes |
| --- | --- |
| `beams.yagi` | Yagi–Uda parasitic beam |
| `beams.moxon` | Moxon rectangle |
| `beams.hexbeam` | Hex beam |
| `beams.hb9cv` | ZL-Special / HB9CV — a 2-element all-driven phased beam |

## Verticals

| Design | Notes |
| --- | --- |
| `verticals.vertical` | Quarter-wave vertical |
| `verticals.raised_vertical` | Elevated vertical |
| `verticals.inverted_l` | Inverted-L, a bent top-loaded vertical |
| `verticals.jpole` | J-pole, end-fed half-wave with a quarter-wave matching stub |
| `verticals.half_square` | Half-square, a vertically-polarised wire antenna |
| `verticals.bobtail` | Bobtail curtain, a 3-element vertical broadside array |
| `verticals.bruce` | Bruce array, a series-fed vertical curtain |
| `verticals.phased_verticals` | Two-element phased verticals (the 90° cardioid) |
| `verticals.four_square` | Four-square phased array (diagonal-firing quadrature box) |

## Wire antennas & curtains

| Design | Notes |
| --- | --- |
| `wire.longwire` | Resonant multi-wavelength long-wire |
| `wire.rhombic` | Terminated rhombic, a traveling-wave directional long-wire |
| `wire.vbeam` | Resonant V-beam, two long wires splayed into a V |
| `wire.lazy_h` | Lazy-H, two stacked collinear elements fed in phase |
| `wire.w8jk` | W8JK flat-top beam, a 2-element all-driven array |
| `wire.zepp` | End-fed half-wave "Zepp" with a tuned-stub feeder |
| `wire.sterba` | Sterba curtain (broadside, bidirectional) — plus `sterba_tl`, `sterba_driven`, `sterba_center_driven`, `sterba_difftl` variants |

## Broadband

| Design | Notes |
| --- | --- |
| `broadband.discone` | Discone, a broadband vertical (disc + cone) as a wire cage |
| `broadband.g5rv` | G5RV doublet with a matched-line section |
| `broadband.t2fd` | T2FD — terminated tilted folded dipole |
| `broadband.lpda` | Log-periodic dipole array (LPDA) |

## Multiband

| Design | Notes |
| --- | --- |
| `multiband.fandipole` | Fan dipole (parallel dipoles for several bands) |
| `multiband.twoband_fan_dipole` | Two-band fan dipole |
| `multiband.trap_dipole` | Dual-band trap dipole |
| `multiband.trap_fan_dipole` | Four-band trapped fan dipole |
| `multiband.hexbeam_5band` | Stacked hexbeam — up to 5 concentric shapes |

## Arrays

Phased / stacked arrays of the elements above — the `arrayblock` solver's
showcase (see [the solver guide](/reference/solver/)):

`arrays.yagiarray`, `arrays.moxonarray`, `arrays.invveearray`,
`arrays.folded_invveearray`, `arrays.bowtiearray` (+ `1x2`, `2x4`),
`arrays.delta_looparray` (+ `1x4`, `1x4_grouped`, `2x2`, `network`, `with_tls`),
`arrays.hentenna_array`, `arrays.hourglass_array`.

## Specialty

| Design | Notes |
| --- | --- |
| `specialty.bowtie` | Bowtie dipole |
| `specialty.helix` | Normal-mode helical vertical |
| `specialty.hentenna` | Hentenna (+ `hentenna_slant`) |
| `specialty.hourglass` | Hourglass (+ `hourglass_slant`) |

:::note[Generated from source — coming soon]
This page will be generated from the package's design tree so it can't drift
from the code: each entry pulling its description, parameters, and rendered
geometry straight from the `Builder`.
:::
