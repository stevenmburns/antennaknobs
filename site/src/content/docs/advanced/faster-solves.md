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
  that tab: on the hosted app all three; on a local install the `razor2p` box
  everywhere, and the `bs2` and Sinusoidal boxes on Linux and Windows, not on
  macOS. PyNEC's tab has its own box of the same name, which is PyNEC's fill
  reuse and is not covered here.
- **rotational symmetry (radial screens)** is on the `bs2` and Sinusoidal tabs
  only.

Neither is meant to change the answer. Reuse copies an entry instead of
computing it again; the sector route is another route through the same
matrix. In every measurement below the impedance agrees with the switch off
to all the digits the readout prints (two decimals), and the largest relative
change is 3 × 10⁻¹⁰.

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
  likely to see are a deck too small to repay the search, and *the plan and
  its census would exceed the 256 MB budget*: a deck with many distinct
  pairs of wires, where the table of repeats would grow past the memory
  reuse is allowed. A declined solve takes the same time as one with the box
  off, plus the search that found it would not fit.

**The census** is the part of the fill spent finding what repeats. The
Sinusoidal and `razor2p` engines search the geometry themselves, and pay the
census once for each new geometry: a frequency sweep pays it once, and so
does solving the same design again, but moving a knob that changes the
geometry pays it again. `bs2` is told what repeats by the workbench, from the
design's wires, and its census is close to zero.

**Compression** is pairs ÷ (computed + near): how far the matrix shrank. It
is not the time saved. The long wire below compresses 1254× on `bs2` and its
solve gets 4× faster, because the factor, and the copying itself, still take
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
| `bs2` | off | dense, off | 2.30 | 0.24 | 2.54 | | 30.20 + j7.18 |
| `bs2` | rotational symmetry | sector, 16 sectors | 0.42 | 0.00 | 0.43 | | 30.20 + j7.18 |
| `bs2` | reuse | dense, served (2.8×) | 1.39 | 0.23 | 1.62 | | 30.20 + j7.18 |
| Sinusoidal | off | dense, off | 0.93 | 0.22 | 1.16 | | 30.14 + j7.15 |
| Sinusoidal | rotational symmetry | sector, 16 sectors | 0.14 | 0.00 | 0.15 | | 30.14 + j7.15 |
| Sinusoidal | reuse | dense, served (16.9×) | 0.22 | 0.24 | 0.49 | 1.20 | 30.14 + j7.15 |

This is the design the sector route is for: about 6× faster on `bs2` and
8× on Sinusoidal. The sector route computed 765,000 of the matrix's
6,502,500 entries, and its factor became too small to show. Reuse helps too,
but it leaves the factor as it was and, on Sinusoidal, pays a census of
about 0.7 s the first time. On a radial screen, tick rotational symmetry.

### A long wire

`wire.longwire`, 3.5 wavelengths of wire at 7 m, N = 180: about 2,500
segments.

| engine | switch | state | fill | factor | total | first | Z (Ω) |
|---|---|---|---|---|---|---|---|
| `bs2` | off | dense, off | 2.96 | 0.21 | 3.17 | | 131.69 − j13.38 |
| `bs2` | reuse | dense, served (1254×) | 0.56 | 0.21 | 0.77 | | 131.69 − j13.38 |
| Sinusoidal | off | dense, off | 0.86 | 0.22 | 1.08 | | 131.69 − j13.38 |
| Sinusoidal | reuse | dense, served (499×) | 0.12 | 0.21 | 0.35 | 0.79 | 131.69 − j13.38 |
| `razor2p` | off | dense, off | 1.42 | 0.21 | 1.64 | | 131.59 − j14.07 |
| `razor2p` | reuse | dense, served (675×) | 0.39 | 0.21 | 0.65 | 1.15 | 131.59 − j14.07 |

A uniform wire is the best case for reuse: every segment pair at a given
spacing is the same pair, so almost nothing is computed. `bs2` goes from 3.2
to 0.8 s. Read the fill share as well: on Sinusoidal it falls from 80 % with
reuse off to 36 % with it on. What is left is mostly the factor, which reuse
cannot shorten, so a finer mesh than this would gain less and less.

### A 10-element Yagi

`beams.yagi` with 8 directors (the **n_directors** knob), N = 120: about
2,150 segments.

| engine | switch | state | fill | factor | total | first | Z (Ω) |
|---|---|---|---|---|---|---|---|
| `bs2` | off | dense, off | 1.62 | 0.14 | 1.77 | | 34.80 − j45.92 |
| `bs2` | reuse | dense, served (1.6×) | 1.27 | 0.15 | 1.42 | | 34.80 − j45.92 |
| Sinusoidal | off | dense, off | 0.67 | 0.14 | 0.81 | | 34.80 − j45.99 |
| Sinusoidal | reuse | dense, served (5.5×) | 0.22 | 0.14 | 0.38 | 1.15 | 34.80 − j45.99 |
| `razor2p` | off | dense, off | 1.12 | 0.14 | 1.26 | | 34.68 − j46.71 |
| `razor2p` | reuse | dense, **declined** | 1.08 | 0.14 | 1.22 | 1.46 | 34.68 − j46.71 |

The directors repeat, but the compression is modest (1.6× on `bs2`, 5.5× on
Sinusoidal): much of the matrix is still computed. `bs2` saves 0.35 s. Sinusoidal is 2× faster on a
repeat solve, and slower on the first (1.15 s against 0.81 s), because the
census costs more than one solve saves. `razor2p` declined: *the plan and its census would
exceed the 256 MB budget*. Its row is the ordinary solve plus the search
that found the plan would not fit, and the Fill view says so rather than
showing an "on" solve that did nothing.

The same Yagi in free space, with no ground terms to compute, has a much
cheaper fill: Sinusoidal fills it in 0.13 s with reuse off, and its first
solve with reuse on takes 0.60 s against 0.27 s off. Where the fill is
already quick, the census can cost more than it saves.

## When it won't help

- **A small deck.** At the stock `bs2` N of 15 the vertical with 16 radials
  has 256 segments and solves in 0.07 s; the sector route takes it to 0.01 s,
  and the 10-element Yagi (267 segments) takes 0.07 s with reuse off and 0.08 s
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
