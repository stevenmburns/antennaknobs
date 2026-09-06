---
title: "A vertical on a slope"
description: An advanced worked example — a ground-mounted vertical on a hillside, solved once on flat ground and read out through a tilted sky; what the slope does to the pattern, what "radials only downhill" buys, and why the interesting part is a script rather than a solve.
---

A question that comes up on the forums every season: *my vertical is on a
hillside — the mast is perpendicular to the ground, the radials follow the
slope, none of it is level. What does that do?* The instinct is that the
radials being "not flat" must matter. It does not, and seeing why turns the
whole problem into one ordinary solve plus a change of viewpoint.

Everything below is momwire on the workbench's catalog buried-radial
vertical — a quarter-wave over four radials buried 15 cm, soil εr 13 /
σ 0.005 S/m, 7.1 MHz — cut to resonance (0.953 of the nominal quarter-wave,
68 Ω resistive; the nominal cut reads 76+40j over this soil, electrically
long, which is what anyone trimming the antenna would remove). The scripts
that produced every number and both figures are in the repository under
`scratch/slope-study/`; each regenerates its table in about ten seconds.

## The frame is the ground's, not gravity's

Put the observer on the slope. In the ground's own frame the interface is a
flat plane, the mast stands normal to it, and the radials lie at constant
depth below it. That is exactly the level-ground antenna. The soil the
radials couple to is the soil under them, and relative to that soil they are
as flat as they ever were. The feed impedance is the level-ground value to
the digit, and so is the current distribution.

What changes is where the sky is. A slope of angle *s* tilts the ground
plane, so a direction at elevation ψ above the *ground* in the downhill
azimuth is at true elevation ψ − *s* above the horizon, and in the uphill
azimuth at ψ + *s*. Any direction that falls below the tilted plane is
inside the hill. One solve, then a rotation of the read-out.

## The elevation cut

![Two polar elevation cuts of the same solve. Left, on level ground: two
symmetric lobes peaking 27° above the horizon, −12.5 dBi at 3°. Right, the
mast normal to a 45° slope: the identical pattern with the ground line
rotated 45° through it — the downhill lobe points below the true horizon
into the valley, the uphill sky below 45° is inside the grey hill, and the
downhill skirt reads −4.7 dBi at 3° above the true
horizon.](../../../assets/advanced/slope45-elevation-cut.png)

The left panel is the familiar picture: a ground-mounted quarter-wave over
lossy soil, main lobe 27° up, −12.5 dBi at 3°. The right panel is the same
solve with a 45° ground line drawn through it. Three things happen at once:

- **The main lobe points into the valley.** Its 27° takeoff above the
  *ground* is 18° below the true horizon on the downhill side. What reaches
  the sky downhill is the upper skirt of that lobe, strongest right at the
  horizon and falling with elevation — −4.7 dBi at 3°, eight decibels better
  than level ground at the same true angle, and worse than level ground
  above about 20°.
- **The uphill sky is gone.** Everything below 45° true elevation on the
  uphill side is behind the hill. What is left uphill is the antenna's own
  overhead null.
- **Nothing else changes.** Peak gain, efficiency and feed impedance are the
  level-ground numbers, because the antenna has not noticed the slope.

A 10° slope does the same in miniature: downhill low angles gain about
8 dB at 3°, uphill loses everything below 10°, the peak is unchanged.

## The azimuth ring at a true elevation

An elevation cut shows two azimuths. The picture that answers "where does
this antenna work?" is an azimuth ring at a fixed *true* elevation, and it
is a curve through the level-ground pattern: for each true azimuth, rotate
the direction into the ground's frame, read the untilted far field there,
and mask whatever lands below the tilted plane.

![Polar azimuth plot at 3° true elevation for the mast normal to a 45°
slope, two series within a decibel of each other: a fan about 150° wide
centred downhill, with peaks of −2.8 dBi some 45° to 60° either side of
the fall line, −4.7 dBi straight downhill, a deep notch to −15 dBi
directly across the slope, and nothing from 105° round to 255° — behind
the hill.](../../../assets/advanced/slope45-azimuth-3deg.png)

Two things this figure says that the elevation cut cannot:

- **Straight down the fall line is not the best direction.** That direction
  sits 48° above the tilted ground, up toward the vertical's overhead null.
  The best low-angle directions are 45° to 60° either side of the fall line,
  where the direction sits lower relative to the ground and nearer the main
  lobe: −2.8 dBi against −4.7 straight downhill.
- **Directly across the slope is dead.** At ±90° from the fall line the
  direction grazes along the tilted ground, where a vertical over real earth
  always dies: −15 dBi.

So the useful low-angle coverage is a fan of roughly 150° centred downhill
with two lobes off the fall line, not a pencil pointing down the hill.

## Radials only on the downhill side

A common suggestion: since the antenna works downhill, put all the radials
downhill. The same wire, moved from a full circle into a downhill sector,
resonant cut, 45° slope, gain 3° above the downhill horizon:

| radials | R | radiated fraction | downhill, 3° |
|---|---|---|---|
| 4, full circle | 68 Ω | 0.164 | −4.7 dBi |
| 4, downhill half | 74 Ω | 0.153 | −4.2 dBi |
| 4, downhill quarter | 83 Ω | 0.137 | −4.4 dBi |
| 8, full circle | 50 Ω | 0.222 | −3.4 dBi |
| 8, downhill half | 58 Ω | 0.193 | −3.1 dBi |

The suggestion has the right sign and is worth about half a decibel. The
mechanism is not the one it assumes. In the ground's frame the near field
and the soil loss are symmetric about the base, and the valley is outside
this model altogether. What bunching the radials does is unbalance the
horizontal currents in the screen, and the unbalanced part radiates: the
pattern skews 0.3 dB toward the radials and 1 to 1.4 dB away from them. It
also costs efficiency, since the same wire collects less of the return
current when it is not spread around the base. On a 45° slope those net to
+0.5 dB downhill, and the uphill penalty is free because that sky is behind
the hill anyway. Push the radials into a quarter and the efficiency loss
overtakes the skew.

More radials beats placing them: eight all round is 0.8 dB better downhill
than four packed downhill.

## A slope is not a hilltop

The planar model has no valley. Its downhill lobe goes below the true
horizon and never comes back, and on a real site that lobe hits ground
somewhere down the hill and some of it reflects. That is a different
problem with a different tool: the
[faceted-terrain ground](/advanced/terrain/) keeps the impedance solve on
flat ground and reflects each far-field ray off its own tilted facet. For a
mast at a *crest* with the ground falling away, it gives a different answer
from the planar slope — around −0.1 dBi at 3° downhill for a 10° drop,
because the specular point walks down the hill and the antenna effectively
gets taller. Its uphill numbers below the slope angle are a known artefact
of a specular model with no diffraction and should not be quoted.

Which model fits which site: a mast standing *on* a long uniform slope is
the rotated-sky case on this page; a mast at the top of a slope, or on a
bench, is the terrain page's. Neither is a substitute for the other.

## What each tool can do

- **The mast normal to the slope** is the level-ground deck in either
  engine. momwire and NEC-5 both solve it, and both give the same rotated
  sky.
- **A plumb mast on a slope** — vertical to gravity, so tilted off the
  ground's normal by the slope angle — is a tilted wire reaching the
  interface. NEC-5 takes a wire through the plane at any angle, so
  EZNEC Pro/5 and the app's NEC-5 lane spell that deck directly. momwire's
  buried family refuses a tilted conductor at the crossing node by name; the
  same antenna with its radials lying on the grass (the catalog's `surface`
  convention) has no crossing node and takes the tilted mast as ordinary
  geometry. Measured that way, a 10° tilt moves the feed impedance by about
  1 %, and a 45° tilt turns the antenna into a sloper: 46+50j Ω against
  61+61j level, with the peak gain unchanged.
- **The study itself** — the rotated read-out, the azimuth ring at a true
  elevation, the sector sweep, the resonance bisection, and the figures with
  their numbers in the titles — is a transformation of one solve plus a
  sweep of variants. That is what a scriptable engine with the far field in
  hand as an array buys: each script here is under a hundred lines and took
  its slope and elevation from the command line. The same figures can be
  built from any engine's exported pattern table with a spreadsheet and an
  afternoon per figure; the point is that they did not have to be.
