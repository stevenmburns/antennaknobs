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

<!-- catalog:begin dipoles -->
| Design | Notes |
| --- | --- |
| `dipoles.dipole_turnstile` | Crossed dipoles fed in phase quadrature (turnstile) |
| `dipoles.folded_invvee` | Folded inverted-vee — the folded dipole's impedance step-up, with drooped arms |
| `dipoles.folded_invvee_balun` | Folded inverted-V fed through a 4:1 balun and real coax — the `Transformer` showcase (issue #301) |
| `dipoles.invvee` | Inverted-vee dipole — the default quickstart example · variants: `classic_edz`, `dipole`, `three_halves` |
| `dipoles.invvee_coax_station` | Inverted-V fed through real coax — the classic "resonant antenna on 50 Ω line" station, modelled from the rig (issue #300) · variants: `classic_edz`, `dipole`, `three_halves` |
| `dipoles.koch_dipole` | Koch fractal dipole (L. B. Cebik, W4RNL -- "fractal antennas") |
| `dipoles.ocf_dipole` | Off-Center-Fed dipole (Windom): a half-wave fed away from the middle (L. B. Cebik, W4RNL) |
| `dipoles.pota_invvee` | POTA wire-gauge tradeoff: a 20 m inverted-V where the wire is a knob · variants: `classic_edz`, `dipole`, `three_halves` |
| `dipoles.short_dipole_loaded` | Center-loaded shortened dipole — the Load-branch showcase for issue #65 |
<!-- catalog:end dipoles -->

## Loops

The delta loop is the catalog's teaching showpiece — one loop laid out **four
ways** (`delta_loop`, `delta_loop_flyby`, `delta_loop_reflected`,
`delta_loop_topdown`), all exposing the same knobs (`base`, `length_factor`,
`angle_deg`) and producing byte-identical wires. They differ only in *how you
specify the geometry*, from writing every corner as coordinates to flying the
whole shape with a `Drone` — see
[Many ways to express geometry](/concepts/authoring/).

<!-- catalog:begin loops -->
| Design | Notes |
| --- | --- |
| `loops.bisquare` | Bi-square: a two-wavelength loop worked as a vertical broadside curtain (L. B. Cebik, W4RNL) |
| `loops.delta_loop` | Corner-fed full-wave delta loop; corner coordinates from a closed-form expression for the top corner · variants: `z100`, `z200` |
| `loops.delta_loop_flyby` | The shipped delta loop, laid down as a full **drone flyby** — fly the whole perimeter and let the flight do the work, no coordinates written |
| `loops.delta_loop_reflected` | The shipped delta loop, built as a **reflection hybrid**: the drone is a trig-free *point finder*, an ``ry`` mirror gives the left half for free, and ``build_path`` stitches the corners |
| `loops.delta_loop_slanted` | Delta loop tilted out of the vertical plane by a slant_deg knob · variants: `slant0`, `slant30` |
| `loops.delta_loop_topdown` | The shipped delta loop, built as a **top-down reflection flight**: the same reflection hybrid as ``delta_loop_reflected``, but the flight starts *at the top* — so the top height is right from move one and there is **no z-offset pass** |
| `loops.diamond_loop` | Full-wave diamond (square) loop fed at the bottom corner · variants: `z100`, `z200` |
| `loops.diamond_loop_turnstile` | Two diamond loops crossed and fed in phase quadrature (turnstile) |
| `loops.horizontal_loop` | Horizontal full-wave loop / "loop skywire" (L. B. Cebik, W4RNL) |
| `loops.horizontal_loop_drone` | A horizontal square loop, vertex-fed, authored with the 3D-turtle Drone |
| `loops.inv_delta_loop` | Inverted delta loop — the triangle flipped so the feed edge sits at the top · variants: `z100`, `z200` |
| `loops.quad` | Two-element cubical quad beam (L. B. Cebik, W4RNL) |
| `loops.skyloop_lmatch` | 80 m triangular skyloop run on 17 m, matched to 50 Ω with an L-network — the `Shunt`-branch showcase for issue #65 (Q2, shunt-to-common) · variants: `band_locked` |
| `loops.triangular_skyloop` | Triangular horizontal full-wave loop ("skyloop"), fed at a corner · variants: `band_locked` |
<!-- catalog:end loops -->

## Beams

<!-- catalog:begin beams -->
| Design | Notes |
| --- | --- |
| `beams.hb9cv` | ZL-Special / HB9CV: a 2-element all-driven phased beam (L. B. Cebik, W4RNL) |
| `beams.hexbeam` | Hex beam — a W-folded 2-element beam on a hexagonal spreader footprint · variants: `opt` |
| `beams.moxon` | Moxon rectangle — a 2-element beam with folded-back element tips · variants: `opt`, `original` |
| `beams.moxon_turnstile` | Moxon turnstile: two up-firing Moxons in real quadrature (L. B. Cebik, W4RNL, QST Aug 2001 pp |
| `beams.owa_yagi` | OWA Yagi: 4 elements, whole-band flat 50-ohm feed (NW3Z/WA3FET concept, systematized by L. B. Cebik, W4RNL) |
| `beams.yagi` | Yagi-Uda parasitic beam (driven element + reflector + directors) |
<!-- catalog:end beams -->

## Verticals

<!-- catalog:begin verticals -->
| Design | Notes |
| --- | --- |
| `verticals.bobtail` | Bobtail curtain: a 3-element vertically-polarised broadside array (L. B. Cebik, W4RNL) |
| `verticals.bruce` | Bruce array: a series-fed vertically-polarised curtain (L. B. Cebik, W4RNL) |
| `verticals.challenger` | KJ6ER's "Challenger" — off-center-fed halfwave vertical with 4:1 unun · variants: `band10`, `band12`, `band17`, `band20`, `band6`, `plus` |
| `verticals.dominator` | KJ6ER's "Dominator" — end-fed halfwave vertical with 49:1 transformer · variants: `band10`, `band12`, `band17`, `plus` |
| `verticals.four_square` | Four-square phased vertical array -- the diagonal-firing quadrature box (L. B. Cebik, W4RNL) |
| `verticals.half_square` | Half-square: a vertically-polarised wire antenna (L. B. Cebik, W4RNL) |
| `verticals.inverted_l` | Inverted-L: a bent, top-loaded vertical (L. B. Cebik, W4RNL) |
| `verticals.inverted_l_tmatch` | 10 m inverted-L worked on the 12 m band through a T-network tuner — the first design with a pure interior circuit node (series C, shunt L, series C), exercising the MNA network core on the classic "wire antenna + T-match" situation |
| `verticals.jpole` | J-pole: an end-fed half-wave matched by a quarter-wave stub (L. B. Cebik, W4RNL) |
| `verticals.phased_verticals` | Two-element phased vertical array -- the 90-degree cardioid (L. B. Cebik, W4RNL) |
| `verticals.pota_performer` | KJ6ER's "POTA PERformer" — elevated quarter-wave with tuned radials · variants: `band10`, `band12`, `band17`, `band20`, `band6`, `omni`, `single_radial` |
| `verticals.raised_vertical` | Elevated quarter-wave vertical, fed above ground |
| `verticals.rectangle` | Rectangle "magnetic slot" SCV: a flattened 1 wl loop (L. B. Cebik, W4RNL) |
| `verticals.right_angle_delta` | Right-Angle Delta: the coax-friendly SCV delta (L. B. Cebik, W4RNL) |
| `verticals.vertical` | Quarter-wave vertical over ground |
<!-- catalog:end verticals -->

## Wire antennas & curtains

<!-- catalog:begin wire -->
| Design | Notes |
| --- | --- |
| `wire.doublet_ladder_tuner` | 88 ft doublet + 100 ft of 600 Ω open-wire line + lossy T-network tuner — the "non-resonant wire and a matchbox" station, modelled from the rig (issue #300) · variants: `classic_edz`, `dipole`, `three_halves` |
| `wire.edz` | Extended Double Zepp: 1.25 wl centre-fed doublet + series match (L. B. Cebik, W4RNL) |
| `wire.efhw_sloper` | End-fed half-wave sloper with a real 49:1 unun — "the POTA antenna, complete" (issue #329) · variants: `band40` |
| `wire.expanded_lazy_h` | Expanded Lazy-H: two stacked EDZs fed through a real phasing harness (L. B. Cebik, W4RNL) |
| `wire.lazy_h` | Lazy-H: two stacked collinear elements fed in phase (L. B. Cebik, W4RNL) |
| `wire.longwire` | Resonant multi-wavelength long-wire (L. B. Cebik, W4RNL) |
| `wire.rhombic` | Terminated rhombic: a traveling-wave directional long-wire (L. B. Cebik, W4RNL, "Long-Wire Antennas" / "The Terminated Vee-Beam and Rhombic") |
| `wire.sterba` | Sterba curtain: a broadside, bidirectional, horizontally-polarised curtain array (E. J. Sterba, Bell Labs, 1930s) |
| `wire.sterba_tl` | Sterba curtain, transmission-line sister design of `sterba.py` |
| `wire.terminated_longwire` | Terminated end-fed long-wire: the directional single wire (L. B. Cebik, W4RNL, "Long-Wire Antennas", Part 2) |
| `wire.vbeam` | Resonant V-beam: two long wires splayed into a V (L. B. Cebik, W4RNL) |
| `wire.w8jk` | W8JK flat-top beam: a 2-element all-driven 180-degree array (L. B. Cebik, W4RNL, after John Kraus W8JK) |
| `wire.zepp` | End-fed half-wave "Zepp" with a tuned-stub feeder (L. B. Cebik, W4RNL) |
<!-- catalog:end wire -->

## Broadband

<!-- catalog:begin broadband -->
| Design | Notes |
| --- | --- |
| `broadband.discone` | Discone: a broadband vertical (disc + cone), modelled as a wire cage (L. B. Cebik, W4RNL) |
| `broadband.g5rv` | G5RV doublet with a matched-line section (analysed at length by L. B. Cebik, W4RNL, "The G5RV Antenna") |
| `broadband.lpda` | Log-periodic dipole array (LPDA) (L. B. Cebik, W4RNL; ARRL Antenna Book LPDA chapter) |
| `broadband.t2fd` | T2FD -- Terminated Tilted Folded Dipole (G2BCX; modeled per L. B. Cebik, W4RNL, "broadband wire antennas") |
<!-- catalog:end broadband -->

## Multiband

<!-- catalog:begin multiband -->
| Design | Notes |
| --- | --- |
| `multiband.fandipole` | Fan dipole — parallel dipoles off one feed for several bands · variants: `five_band`, `pair_12_10`, `pair_17_15` |
| `multiband.hexbeam_5band` | Stacked hexbeam: up to 5 concentric hexbeam shapes stacked along z, each sized to its own band's wavelength and driven by its own feed · variants: `opt`, `opt_coupled` |
| `multiband.trap_dipole` | Dual-band trap dipole — Load(parallel=True) showcase for issue #65 |
| `multiband.trap_fan_dipole` | Four-band trapped fan dipole — combines `fandipole` geometry with the `trap_dipole` Load(parallel=True) idiom · variants: `band0_full`, `band0_inner`, `band1_full`, `band1_inner` |
| `multiband.twoband_fan_dipole` | Two-band fan (parallel) dipole — two dipoles bonded at a common feed · variants: `current_physical`, `s01`, `s015`, `s01_eps001`, `s02`, `s025`, `s03`, `s05`, `s07` |
<!-- catalog:end multiband -->

## Arrays

Phased / stacked arrays of the elements above — the `arrayblock` solver's
showcase (see [the solver guide](/reference/solver/)):

<!-- catalog:begin arrays -->
| Design | Notes |
| --- | --- |
| `arrays.bowtiearray` | 2x2 phased stack of bowtie dipoles |
| `arrays.bowtiearray1x2` | Side-by-side bowtie pair (1x2) |
| `arrays.bowtiearray2x4` | 2x4 phased bowtie curtain — the catalog's largest stack |
| `arrays.delta_looparray` | Side-by-side delta-loop pair (1x2) · variants: `dy3`, `dy35`, `dy45` |
| `arrays.delta_looparray_1x4` | Four delta loops in a broadside row (1x4) |
| `arrays.delta_looparray_1x4_grouped` | 1x4 delta-loop row with per-group knobs (inner/outer pairs tuned separately) |
| `arrays.delta_looparray_2x2` | 2x2 phased stack of delta loops |
| `arrays.delta_looparray_network` | delta_looparray driven by two TLs from a central virtual driver |
| `arrays.delta_looparray_with_tls` | Delta-loop pair phased through explicit transmission lines (legacy build_tls path) |
| `arrays.folded_invveearray` | 2x2 phased stack of folded inverted-vees |
| `arrays.hentenna_array` | Side-by-side hentenna pair (1x2) |
| `arrays.hourglass_array` | Side-by-side hourglass pair (1x2) |
| `arrays.invveearray` | 2x2 phased stack of inverted-vee dipoles · variants: `old` |
| `arrays.lumped_coupled_pair` | Lumped-coupled dipole pair — the TwoPort-branch showcase for issue #65 |
| `arrays.moxonarray` | 2x2 phased stack of Moxon rectangles |
| `arrays.yagiarray` | 2x2 phased stack of Yagi beams |
<!-- catalog:end arrays -->

## Specialty

<!-- catalog:begin specialty -->
| Design | Notes |
| --- | --- |
| `specialty.bowtie` | Bowtie dipole — triangular fan arms for broadened bandwidth |
| `specialty.helix` | Normal-mode helical vertical (L. B. Cebik, W4RNL) |
| `specialty.hentenna` | Hentenna — the Japanese rectangular loop, fed off-center for vertical polarization · variants: `z100`, `z50` |
| `specialty.hentenna_slant` | Slanted hentenna parameterised by top-rectangle perimeter + two aspect ratios · variants: `z100`, `z50` |
| `specialty.hourglass` | Hourglass loop — a crossed (bowtie-folded) rectangular loop |
| `specialty.hourglass_slant` | Hourglass loop tilted out of the vertical plane |
<!-- catalog:end specialty -->

:::note[Generated from source]
The listings on this page are generated by `scripts/generate_catalog.py` from
the package's design tree — each entry's description is the first sentence of
the design module's docstring, and its variants come from the `*_params`
convention. Do not edit the tables by hand; edit the docstrings and
regenerate. The test suite fails if this page drifts from the code.
:::
