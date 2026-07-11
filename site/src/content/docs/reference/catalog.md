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
| `dipoles.invvee_coax_station` | The inv-vee fed through 100 ft of real coax (cable preset dropdown), referenced to the rig — line loss and the SWR penalty in the power budget |

## Loops

The delta loop is the catalog's teaching showpiece — one loop laid out **four
ways**, all exposing the same knobs (`base`, `length_factor`, `angle_deg`) and
producing byte-identical wires. They differ only in *how you specify the
geometry*, from writing every corner as coordinates to flying the whole shape
with a `Drone` (see [Many ways to express geometry](/concepts/authoring/)):

| Design | Built by |
| --- | --- |
| `loops.delta_loop` | the shipped version: corner coordinates from a closed-form expression for the top corner |
| `loops.delta_loop_flyby` | full `Drone` (3D turtle) flyby; top laid by `forward_through_plane`, feed-anchored with a z-offset pass |
| `loops.delta_loop_reflected` | `Drone` point-finder + `ry` reflection + `build_path` (side solved for the perimeter) |
| `loops.delta_loop_topdown` | top-down flight: starts at the top, `forward_to_plane` lands the feed where the slant crosses `y = eps` |

Other loops: `loops.delta_loop_slanted`, `loops.inv_delta_loop`,
`loops.horizontal_loop` (full-wave "loop skywire") and its `Drone` twin
`loops.horizontal_loop_drone`, `loops.diamond_loop` (+ `diamond_loop_turnstile`),
`loops.quad` (2-element cubical quad beam), `loops.bisquare` (a two-wavelength
broadside curtain), `loops.triangular_skyloop` (corner-fed full-wave triangle),
and `loops.skyloop_lmatch` (the 80 m skyloop worked on 17 m through an
L-network — series L, shunt C — matched to 50 Ω).

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
| `verticals.inverted_l_tmatch` | The 10 m inverted-L worked on 12 m through a T-network tuner (series C, shunt L, series C) |
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
| `wire.sterba` | Sterba curtain (broadside, bidirectional) — plus the `sterba_tl` transmission-line-phased variant |
| `wire.doublet_ladder_tuner` | 88 ft doublet + 100 ft of 600 Ω open-wire line + lossy T-network tuner, referenced to the rig — the classic multiband station, with the tuner-coil cost in the power budget |

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
`arrays.hentenna_array`, `arrays.hourglass_array`, and
`arrays.lumped_coupled_pair` (a dipole pair steered through a lumped series
R+jωL bridge between the two feeds — the `TwoPort` network element's
showcase).

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
