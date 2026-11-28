---
title: "Faster solves: the Fill view and two speed switches"
description: How to read the workbench's Fill view, and when "reuse repeated geometry" or "rotational symmetry (radial screens)" makes a fine-meshed design solve faster — with measured times on three catalog designs.
---

Most designs solve in a fraction of a second at the workbench's stock
segment counts, and nothing on this page is worth doing for them. It matters
when you mesh fine — a convergence ladder's top rungs, a long wire at a high
**N**, a radial screen with many radials — and each solve starts to take
seconds. The momwire engines have two switches for that, both off by default,
and the workbench's **Fill** view tells you which one can help.

## Fill and factor

A momwire solve has two expensive stages. The **fill** computes the
interaction matrix: one entry for every pair of basis functions, each an
integral over two pieces of wire, and over a finite ground each carries a
ground term as well. The **factor** then solves the linear system that matrix
defines. With *n* unknowns the fill does about *n²* integrals and the factor
about *n³* arithmetic, so the fill dominates a moderate mesh and the factor
takes over as the mesh grows. Where that crossover falls depends on the
engine and the ground: an integral over Sommerfeld ground costs far more than
one in free space. Measured on the 10-element Yagi below (same machine as the
worked examples), the fill and the factor take equal time at about 2,300
segments on Sinusoidal in free space, 3,200 on `razor2p` and 6,600 on `bs2`.
Over Sommerfeld ground the fill stays the larger stage much longer: to about
14,000 segments on Sinusoidal, and, extrapolating beyond the 9,300 measured,
past 25,000 on `razor2p` and `bs2`.

The two switches shorten different stages, and that decides which can help.
**Reuse repeated geometry** computes each repeated pair of wires once and
copies it, so it shortens only the fill; the factor takes as long as before.
**Rotational symmetry** solves a radial screen as one sector repeated N times.
It fills only that sector's rows and factors N small blocks in place of one
large matrix, so it shortens the fill **and** the factor.

## Where the switches are

Both are boxes in a momwire slot's gear menu, unticked by default.

- **reuse repeated geometry (faster fill)** is on the `bs2`, Sinusoidal and
  `razor2p` tabs. It is offered only where momwire certifies the reuse behind
  that tab, which is all three on the hosted app and on Linux, Windows and
  macOS installs. PyNEC's tab has its own box of the same name, which is
  PyNEC's fill reuse and is not covered here.
- **rotational symmetry (radial screens)** is on the `bs2` and Sinusoidal tabs
  only.

Neither is meant to change the answer. Reuse copies an entry instead of
computing it again; the sector route is another route through the same
matrix. In every measurement below the impedance agrees with the switch off
to all the digits the readout prints (two decimals), and the largest relative
change is 1 × 10⁻⁸.

## Reading the Fill view

Open **Fill** from **All views**; pin it to keep it in the rail. It describes
the solve on screen, as momwire reported it.

**Fill, factor and census times, and the fill share.** The share is the
fill's percentage of fill plus factor. It is the first number to read. A
share near 100 % means the fill is the solve, and either switch has room to
help. A low share means the factor dominates: reuse cannot help much there,
because it cannot shorten the factor, and only the sector route can.

**The route.** **dense** is the ordinary solve. **sector (rotational
symmetry)** means the sector route ran, and the view adds the number of
sectors, the wires on the axis, the blocks factored and how many matrix
entries were computed against the total.

**The reuse state.**

- **off** — the box is unticked.
- **served** — reuse ran over the whole fill.
- **partial** — reuse ran over part of it; the view names what it left out.
- **declined** — the box was ticked but reuse did not run, and the fill was
  the ordinary one. The view gives momwire's reason. The two you are most
  likely to see are a deck too small to repay the search, and *more than N
  classes for M pairs (the cap is 1.333x compression)*: a deck with so many
  distinct pairs of wires that reuse could not shrink the matrix by at least
  a third, so the table of repeats would cost more memory than it saves. A
  declined solve takes the same time as one with the box off, plus the
  search that found it would not pay.

**The census** is the part of the fill spent finding what repeats. Each
engine searches the geometry itself, and pays the census once for each new
geometry: a frequency sweep pays it once, and so does solving the same design
again, but moving a knob that changes the geometry pays it again.

**Compression** is pairs ÷ (computed + near): how far the matrix shrank. It
is not the time saved. The long wire below compresses 108× on `bs2` and its
solve gets 3× faster, because the factor, and the copying itself, still take
time. Over a ground the counts come in two sections, the free-space term and
the ground terms; the ground terms depend on height as well as spacing, so
fewer pairs share them.

**The map** draws the matrix wire by wire, with each block's share of
computed, reused and near pairs. On a design that gains from reuse it is
mostly hatched (reused). On the sector route it marks the one computed
sector and the axis.

## Which designs gain

**Reuse** needs geometry that repeats: the same pair of wires, in the same
relative position, many times. The designs that have it are a long uniform
wire (every segment is like its neighbour), a Yagi's directors, a ground
screen or a set of radials, mirrored halves, and arrays of identical
elements. A design where every wire differs — a loaded multiband vertical
with a top hat, an irregular loop — has little to copy.

**Rotational symmetry** needs a radial screen: wires on one vertical axis,
and everything else in N identical copies spaced evenly around it, each
meshed the same way, made of the same wire, with the same loads, and fed so
that the drive is the same in every sector. Free space, perfect ground, the
reflection-coefficient ground and Sommerfeld ground qualify. In the catalog,
`verticals.vertical`, `verticals.buried_radial_vertical`,
`verticals.elevated_buried_counterpoise` at its stock settings and
`broadband.discone` are built that way.

When a design is not built that way, the solve refuses and the readout
shows momwire's sentence naming the first condition that failed, ending
*Untick 'rotational symmetry (radial screens)' to solve this design
densely.* Three that catalog designs give:

- *no wire lies on a single vertical line, so the deck has no axial group and
  no axis* — `verticals.inverted_l`, `dipoles.dipole_turnstile`, and
  `verticals.vertical` with one radial. A wire joined end to end with
  another at a joint where nothing else meets is solved as one wire, so a
  mast that runs straight into its only radial, or into a horizontal leg,
  is not a vertical wire any more.
- *sector 1 sits at 315.000 deg, where 2 sectors require 225.000 deg* —
  `verticals.raised_vertical`, whose two radials are not opposite each
  other.
- *sector 1's wire has 2 vertices against sector 0's 10* —
  `verticals.elevated_buried_counterpoise` with 3 elevated radials over its 4
  buried ones, which is no longer N copies of one sector.

## Worked examples

All three are catalog designs you can open by name. Each is meshed well past
the stock N so that a solve takes seconds; the **N** is the gear menu's
segments per λ/4. The ground is the workbench's default Sommerfeld ground.

Times are in seconds on one desktop, an Intel i7-6700K (4 cores, 8 threads)
with 46 GB, at default threads, with nothing else running. Each is the median of three solves after a first one, which
is how a running workbench sees a design it has already solved once. For the
engines that search for repeats, **first** is the time of the first solve of
that geometry, which includes the census. They are typical, not a promise:
your machine, and other work on it, will move them. **State** is the Fill
view's route and reuse state for that row, read from momwire's report of the
solve.

### A vertical with 16 radials

`verticals.vertical` at its maximum of 16 radials (the **n_radials** knob),
N = 150: 2,550 segments.

| engine | switch | state | fill | factor | total | first | Z (Ω) |
|---|---|---|---|---|---|---|---|
| `bs2` | off | dense, off | 2.30 | 0.23 | 2.53 | | 30.20 + j7.18 |
| `bs2` | rotational symmetry | sector, 16 sectors | 0.43 | 0.00 | 0.44 | | 30.20 + j7.18 |
| `bs2` | reuse | dense, served (44×) | 0.84 | 0.23 | 1.14 | 2.06 | 30.20 + j7.18 |
| Sinusoidal | off | dense, off | 0.93 | 0.22 | 1.15 | | 30.14 + j7.15 |
| Sinusoidal | rotational symmetry | sector, 16 sectors | 0.15 | 0.00 | 0.16 | | 30.14 + j7.15 |
| Sinusoidal | reuse | dense, served (16.9×) | 0.23 | 0.22 | 0.47 | 1.25 | 30.14 + j7.15 |

This is the design the sector route is for: about 6× faster on `bs2` and
7× on Sinusoidal. The sector route computed 765,000 of the matrix's
6,502,500 entries, and its factor became too small to show. Reuse helps too,
but it leaves the factor as it was and, on Sinusoidal, pays a census of
about 0.6 s (`bs2`) or 0.7 s (Sinusoidal) the first time. On a radial screen, tick rotational symmetry.

### A long wire

`wire.longwire`, 3.5 wavelengths of wire at 7 m, N = 180: about 2,500
segments.

| engine | switch | state | fill | factor | total | first | Z (Ω) |
|---|---|---|---|---|---|---|---|
| `bs2` | off | dense, off | 2.96 | 0.22 | 3.19 | | 131.69 − j13.38 |
| `bs2` | reuse | dense, served (108×) | 0.69 | 0.21 | 0.97 | 1.70 | 131.69 − j13.38 |
| Sinusoidal | off | dense, off | 0.86 | 0.21 | 1.07 | | 131.69 − j13.38 |
| Sinusoidal | reuse | dense, served (499×) | 0.12 | 0.21 | 0.36 | 0.85 | 131.69 − j13.38 |
| `razor2p` | off | dense, off | 1.43 | 0.21 | 1.65 | | 131.59 − j14.07 |
| `razor2p` | reuse | dense, served (675×) | 0.33 | 0.21 | 0.57 | 1.08 | 131.59 − j14.07 |

A uniform wire is the best case for reuse: every segment pair at a given
spacing is the same pair, so almost nothing is computed. `bs2` goes from 3.2
to 1.0 s. Read the fill share as well: on Sinusoidal it falls from 80 % with
reuse off to 36 % with it on. What is left is mostly the factor, which reuse
cannot shorten, so a finer mesh than this would gain less and less.

### A 10-element Yagi, and designing for reuse

`beams.yagi` with 8 directors (the **n_directors** knob), N = 120: about
2,150 segments.

| engine | switch | state | fill | factor | total | first | Z (Ω) |
|---|---|---|---|---|---|---|---|
| `bs2` | off | dense, off | 1.63 | 0.15 | 1.78 | | 34.80 − j45.92 |
| `bs2` | reuse | dense, served (5.5×) | 0.99 | 0.14 | 1.18 | 2.08 | 34.80 − j45.92 |
| Sinusoidal | off | dense, off | 0.68 | 0.14 | 0.83 | | 34.80 − j45.99 |
| Sinusoidal | reuse | dense, served (5.5×) | 0.21 | 0.14 | 0.36 | 1.20 | 34.80 − j45.99 |
| `razor2p` | off | dense, off | 1.14 | 0.14 | 1.29 | | 34.68 − j46.71 |
| `razor2p` | reuse | dense, served (5.5×) | 0.38 | 0.14 | 0.57 | 1.40 | 34.68 − j46.71 |

The directors repeat, but the compression is modest: much of the matrix is
still computed. The reason is in how the Yagi is built. Its elements have
different lengths, so they mesh differently, and a segment on one element
seldom sits in the same position relative to a segment on another. Only
pairs that line up exactly can be copied.

The **uniform_cores** box in the Yagi's parameters builds every element on
the same core instead: a short centre wire and two arms out to the
director's half-length. The driver and the reflector reach their own,
longer, lengths through extension wires on each end. Equal wires mesh
equally, and the elements sit at equal spacing along the boom, so nearly
every pair between two elements repeats. The antenna is the same; only the
way its wires are divided has changed, and the impedance agrees with the
default layout to within 0.05 Ω on every engine. The same Yagi with
**uniform_cores** ticked (about 2,165 segments):

| engine | switch | state | fill | factor | total | first | Z (Ω) |
|---|---|---|---|---|---|---|---|
| `bs2` | off | dense, off | 1.69 | 0.14 | 1.83 | | 34.80 − j45.91 |
| `bs2` | reuse | dense, served (47×) | 0.55 | 0.15 | 0.75 | 1.32 | 34.80 − j45.91 |
| Sinusoidal | off | dense, off | 0.68 | 0.15 | 0.83 | | 34.80 − j45.97 |
| Sinusoidal | reuse | dense, served (51×) | 0.12 | 0.15 | 0.29 | 0.69 | 34.80 − j45.97 |
| `razor2p` | off | dense, off | 1.12 | 0.14 | 1.26 | | 34.68 − j46.66 |
| `razor2p` | reuse | dense, served (46×) | 0.25 | 0.14 | 0.42 | 0.88 | 34.68 − j46.66 |

On every engine the compression goes from 5.5× to between 46× and 51×,
and the fill becomes a small part of the solve. The first solve
benefits most, because the census also finds the repeats faster: on
Sinusoidal it now takes 0.69 s, which beats the 0.83 s with reuse off,
where on the default layout it lost (1.20 s). `razor2p`'s first solve
drops from 1.40 s to 0.88 s, and `bs2`'s from 2.08 s to 1.32 s.

Over ground `bs2` fills three terms for each pair of wires: the free-space
term, the ground image and the Sommerfeld remainder. It reuses all three, so
over Sommerfeld ground it compresses as far as in free space, 47× against
44× for the same layout.

With reuse off, the two layouts take about the same time, so ticking
**uniform_cores** costs nothing on its own. It is worth ticking whenever
you tick reuse on a long Yagi.

In free space, with no ground terms to compute, the fill is already cheap:
Sinusoidal fills the default layout in 0.13 s with reuse off. There the
census can cost more than it saves: the first solve with reuse on takes
0.63 s against 0.29 s off. Uniform cores narrows that to 0.41 s, but does
not close it.

The general lesson applies to any design you build: reuse rewards
geometry that is divided the same way. Wires of equal length, at equal
spacing, meshed with the same segment count, give the census repeats to
find. Where the antenna allows it, build the parts that differ as
extensions on a common core.

## When it won't help

- **A small deck.** At the stock `bs2` N of 15 the vertical with 16 radials
  has 256 segments and solves in 0.07 s; the sector route takes it to 0.01 s,
  and the 10-element Yagi (267 segments) takes 0.06 s with reuse off and 0.04 s
  with it on. Neither is
  something you will notice.
- **A factor-dominated deck.** When the Fill view's share is low, reuse can
  only shorten the small part. Only the sector route shortens the factor, and
  only on a radial screen.
- **A fill that is already cheap.** On Sinusoidal and `razor2p` in free
  space, the census on each new geometry can cost more than reuse saves.
  When you are dragging a knob that moves the geometry, every solve is a
  first solve.
- **A deck with many distinct wire pairs**, where reuse declines on its
  memory budget.
- **An engine without a fill report.** PyNEC, OpenNEC, NEC-2, NEC-4.2 and
  NEC-5 report no fill, and the Fill view says so.

## A default for a server

A server can tick the reuse box for every user with
`ANTENNAKNOBS_PAIR_REUSE=1` (and PyNEC's with
`ANTENNAKNOBS_PYNEC_FILL_REUSE=1`). The box is then served ticked, and a user
who unticks it still wins. The rotational-symmetry box has no server default:
it refuses a design that is not a radial screen, so it is a choice made per
design.
