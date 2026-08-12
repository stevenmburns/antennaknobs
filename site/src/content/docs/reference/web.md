---
title: Web workbench
description: The browser-based simulator — driving the knobs, running several designs at once, optimizing, switching solvers, and how it's served.
---

The web workbench is the live, no-install face of antennaknobs: a panel of knobs
per design, with the radiation pattern, SWR, and impedance re-solving as you drag.

## Run it locally

```bash
pip install "antennaknobs[web]"
uvicorn antennaknobs.web.server:app      # http://127.0.0.1:8000
```

The `[web]` extra pulls in `uvicorn[standard]`, which provides the WebSocket
support the live-solve channel (`/ws`) needs — plain `uvicorn` fails that
handshake.

The server sizes its BLAS/OpenMP thread pools itself (physical-core count).
On multi-core boxes you can optionally prefix the command with
`OMP_WAIT_POLICY=PASSIVE GOMP_SPINCOUNT=0` to park idle solver threads
between solves — worth ~15% on live knob-drag latency. These two are read
once at process start, so they only take effect as launch environment.

A local instance has no login and none of the hosted instance's solve-size
limits, and it runs any design files you've allowed with your user privileges —
keep it on the default `127.0.0.1` bind rather than exposing it to a network
you don't fully control.

## The hosted instance

A hosted simulator is running at
**[app.antennaknobs.dev](https://app.antennaknobs.dev/)** (a single
FastAPI process serving the API, the `/ws` live-solve channel, and the built
React SPA). It's deployed as a container on Fly.io; the repo's `docs/deploy.md`
is the runbook.

## Driving a knob

Each parameter in a design is a knob (the big one is the measurement-frequency
VFO dial; the rest are smaller). The dial is normally locked to the design
frequency; **off-band designs** — an antenna cut for one band and worked on
another through a tuner (see
[Cut for one band, worked on another](/advanced/off-band/)) — open with the
lock open and the dial already parked on their operating band. Three ways to
change a knob:

- **Drag** — press on the knob and move the mouse **vertically** (up to
  increase, down to decrease). Horizontal motion is ignored, so a natural hand
  motion won't fight you.
- **Keyboard / physical dial** — click a knob (or tab to it) to focus it; it
  shows a highlight ring. While focused, **↑ / →** and **↓ / ←** step by one
  increment, **Page Up / Down** by ten, **Home / End** jump to the range ends,
  and **Enter** opens the value to type a number exactly. A physical USB dial
  that emits arrow keys drives the focused knob the same way — the knob keeps
  focus until you click elsewhere, so twisting the dial keeps adjusting it.
- **Right-click menu** — right-click a knob for its settings:
  - **Turn step** — how much one drag-notch / arrow press moves the value.
  - **Display range** — the min/max the knob sweeps between.
  - **Optimize this knob** + **Optimize range** — mark it as a free variable for
    the optimizer and bound its search (see [Optimizing](#optimizing) below).

Every turn re-solves and redraws live (when **Live** is on — see below).

## The output stage — views, pins, and layout

The right-hand stage shows one **primary view** at full size with your other
views as thumbnails beside it. The roster is:

| View | What it draws |
| --- | --- |
| **Antenna** | the wires, current heat-map, standing-wave envelope |
| **Azimuth (xy)** | far-field polar cut in azimuth |
| **Elevation (yz)** | far-field polar cut in elevation |
| **Smith** | feedpoint impedance, plus the sweep locus and any [measured overlay](#measured-overlay--your-vna-on-the-smith-chart) |
| **Schematic** | the [feed network as a chain](#the-schematic-view) |
| **S11 (dB) vs freq** | return loss against frequency, the log-magnitude form a VNA shows |
| **VSWR vs freq** | SWR against frequency |

Click a thumbnail to promote it to primary. The last two read the **same
frequency sweep** the Smith chart plots — run a [sweep](#convergence-sweep)
and all three fill in together; the marker on each rides the measurement
frequency.

- **Pin the views you watch.** The stage carries a *pinned set*, not the whole
  roster — **Antenna, Azimuth, Elevation, Smith** to start, up to **six**
  pins. Six is a hard cap: more thumbnails than that and none of them is
  legible.
- **The rest live in the picker.** **All views ⌄ +N** at the foot of the
  thumbnail strip opens every view in the roster; the ⊕ / ⊖ beside each row
  pins or unpins it, and a view added to the roster since you last looked
  wears a **NEW** badge. At the cap, pinning is blocked with *"Unpin a view
  first"* rather than silently dropping someone else's pin.
- **Rail or grid.** The **▤ / ⊞** toggle on the stage switches between the
  rail (one primary + thumbnails) and a **2×2 grid** of equal cells over your
  first four pins, for watching several live at once. Each grid cell has a
  maximize button back to the rail. Grid is desktop-only.
- **On a phone** the output pages are the pinned set — swipe between them,
  with a trailing **Info** page for the solve readout — and the **⋯** button
  opens the same roster as a sheet, so pinning a view gives it a page and
  unpinning takes it away.
- **Pins are yours, not the design's**: the set (and the layout mode) is
  stored in the browser and shared by every design session, since which views
  you care about is a habit, not a property of the antenna. Since v0.43.0
  the picker's **▲/▼ buttons reorder** the pinned set — pin order IS rail
  order, grid-cell order, and phone-page order, so one reorder serves all
  three — and a second browser **window** picks up pin/order/layout changes
  live instead of on reload.
- **Analyses follow the views** (v0.43.0): the freq sweep, convergence
  sweep, and NEC pattern overlay only run while a view that renders them is
  pinned or open — an enabled sweep with no Smith/S11/VSWR view on screen
  costs nothing, and pinning one starts it. The norm check is the deliberate
  exception (its number lives in the always-present solve readout).

## The antenna viewer

The Antenna view draws the wires (with the current heat-map and standing-wave
envelope overlays) in one of four projections — **Top (xy)**, **Front (xz)**,
**Side (yz)**, and an isometric **Iso** (the classic corner view: x and y
recede left and right, z stays up) — switched by the buttons in the top-right
overlay. The ground reference line appears on the two elevation views.

The view auto-fits the whole antenna, and you can navigate from there,
map-style:

- **Zoom** — scroll wheel (desktop) or pinch (touch), anchored at the cursor
  or pinch centre, up to 10 000×. Fine construction detail — a cage of wires
  millimetres apart on an antenna metres across, typical of imported NEC
  decks — is inspectable without touching any knob.
- **Pan** — drag, once zoomed in. At fit zoom a touch drag stays with the
  page (on a phone that's the swipe between output screens); after a pinch
  the canvas owns the gesture until you re-fit.
- **Re-fit** — double-click / double-tap, the **Fit** button in the
  bottom-right HUD (next to the live zoom readout), or just zoom all the way
  back out. Switching design also re-fits — the old viewport means nothing
  for a new geometry.
- **Turning the view keeps your place** — switching projection carries the
  zoomed viewport over: the world point at the centre of the canvas stays
  centred (its depth along the old camera ray taken from the geometry's
  midpoint), at the same on-screen magnification. Zoom into a feed region in
  Front view and flip to Side or Iso to see the same region from the other
  angle. Fit is one double-click away whenever the carried view isn't what
  you wanted.

The scale bar under the antenna reads **λ/4** at fit zoom; once zoomed it
switches to a round metric length (1/2/5 × 10ᵏ m — like a map's) sized to
about a quarter of the canvas, so it stays readable and true at any
magnification. Zooming magnifies geometry only: wire strokes, labels, the
feed dot, and the envelope amplitude keep their size.

## Live & paused solving

A **Live** toggle sits next to the frequency dial. It looks **depressed when on**
and raised when off:

- **On** — every knob turn triggers a solve; the plots track your hand.
- **Paused** — knob turns just move the values; nothing solves until you turn
  Live back on. Useful when you want to set several knobs before paying for a
  solve, or when a heavy design makes continuous solving sluggish.

## Adaptive resolution

The frequency sweep and the far-field cuts sample **where the curve actually
bends**, not just on a fixed grid. Hold the design still for a moment after a
sweep settles and the workbench quietly buys extra samples where the drawn
polyline still misses the true curve — a sharp SWR notch that a uniform grid
would step right over resolves down to sub-pixel, and a pattern lobe's edge
gets angles a uniform circle wouldn't spend there.

What you'll notice:

- **Sweeps start faster.** With refinement on, the base grid's job is only to
  *detect* features, so it opens at 17 log-spaced points instead of 41 and the
  S11/VSWR/Smith views fill in sooner; the refinement rounds then sharpen
  whatever the base grid straddled.
- **The Smith locus is a connected curve — once it has earned it.** While
  refinement is still landing points, the Smith, VSWR and |Γ| views draw
  **unconnected dots**: a polyline through a half-refined set shows kinks
  that are artifacts of sampling, not physics. When the refinement pass
  settles, the views switch to the connected stroke. (Toggling refinement
  off mid-run deliberately keeps the dots — the accumulated set is uneven,
  and the charts keep saying so.)
- **Only what's on screen refines.** Like the sweeps themselves
  (view-residency gating, above), refinement spends solves only on the
  projections and cuts whose views are pinned or open.
- **It's a setting.** The gear menu's **adaptive resolution** toggle (default
  on, stored per browser like the theme) turns the whole machinery off, and
  the base grids revert to their historical sizes (41-point sweeps) and become
  final. For unusually difficult designs the budgets can be nudged via
  `localStorage` overrides (`antennaknobs.sweepBaseN`,
  `antennaknobs.sweepRefineBudget`, `antennaknobs.cutRefineBudget`,
  `antennaknobs.refineTolerance`) — deliberately not knobs in the menu.

Relatedly, the **S11 chart no longer clamps at 0 dB**: a driven-array port's
*active* reflection is not bounded by |Γ| ≤ 1 (mutual coupling can push more
power into a detuned element than its own generator supplies), so when any
drawn value crosses zero the axis top rises to show it, with the 0 dB line
kept as the tick a healthy passive port never crosses.

## Optimizing

Next to Live is an **Optimize** toggle (same depressed-when-on look), with a
**gear menu** beside it for the objective. The optimizer continuously tunes the
knobs you've marked to hit a target:

1. **Pick an objective** in the gear menu:
   - **Resonance** — drive the feed-point reactance to zero (X → 0).
   - **SWR** — minimize SWR against the design's reference impedance (Z₀, 50 Ω
     by default).
2. **Mark the knobs to vary** — right-click each knob you'll let the optimizer
   move, check **Optimize this knob**, and set its **Optimize range** (the search
   bounds). A marked knob is visually flagged. To flip the flag from the keyboard,
   focus a knob (click or tab to it) and press **`o`** — the same toggle as the
   menu checkbox, without leaving the home row.
3. **Turn on Optimize.** While Live is also on, the optimizer runs reactively: any
   time you change a *fixed* knob, it re-tunes the *marked* knobs (a short
   debounce, then a few dozen solves) and writes the best values back, so the
   antenna stays on target as you explore.

**A run shows its work.** Progress streams back per evaluation: the VFO
panel's readout ticks through each candidate's eval count, impedance, and SWR
as the search moves, and the **Smith chart follows the run live** — its dot
walks the Γ-plane with every trial. Every other view keeps describing the
design you started from (the knobs aren't touched until the run finishes), so
those views **dim** for the duration — the same stale-fade a mid-solve view
wears — and light up when the result lands. The schematic stays bright: it's
drawn from the current knob values and stays right throughout.

Under the hood it's a derivative-free **Nelder–Mead** search (each evaluation is
a full MoM solve), bounded by your Optimize ranges, and it always runs on the
fast **momwire** engine — never PyNEC, which is too slow for an interactive loop.
It's a tuning aid, not a global optimizer: give it sensible ranges and a couple
of free knobs, not a dozen.

**Multi-feed designs score their worst feed.** On a design with several
independently driven ports (a bowtie array, a pair of phased verticals), the
objective is evaluated per feed and the optimizer minimizes the *worst* one —
so "SWR 1.4" after a run means *no* element sits worse than 1.4, and one bad
feed can't hide behind several good ones. The SWR shown while optimizing is
that worst feed's. A design that feeds its elements from a single source
through a network is different: there the match that matters is the network's
input, so the optimizer scores the driven plane — the same impedance the
readout shows. The CLI's `optimize` aggregates feeds the same way (it differs
only in scoring |Z − Z₀| distance rather than SWR).

**Loading a design pauses Optimize.** Switching antenna or picking a variant
turns Optimize off — its objective and marks belong to the design you left —
and briefly says so. Switching antenna *keeps* that design's marks (they're
remembered per design, so coming back restores them); loading a **variant**
instead *clears* its marks, because their ranges were scaled to the values the
variant just replaced. Re-mark the knobs and turn Optimize back on to resume.

## Choosing a solver & segment count

A **solver selector** offers a few preset slots so you can flip between engines
without re-entering options — e.g. a fast dense basis, an accelerated array
engine, and the PyNEC reference. The available engines are the momwire bases
(**Sinusoidal**, **Sin-Galerkin**, **B-spline**), the accelerators
(**H-matrix (ACA)**, **Array-block**), the optional **PyNEC** backend — see
[The solver & accuracy](/reference/solver/) for what each is good at — and,
on a machine with a licensed binary, **NEC-5**
([setup and terms](/reference/nec5/)): the slot appears exactly when the
server resolves `NEC5_EXE`, which is why the hosted simulator never shows
it while your own local instance can. The list is **served by the backend
you're pointed at**, so a server without an optional engine simply doesn't
offer it, rather than offering a slot that fails on the first solve. NEC-5
solves are one external run per request — right for A/B snapshot checks
against momwire in the next slot, heavier than the in-process engines for
live dragging.

The solver's gear menu also exposes **segments / wire (N)** — how finely each
wire is discretized. More segments = more accurate (up to convergence) but a
larger, slower solve. See
[Segments & convergence](/reference/solver/#segments--convergence) for what N
means and how to find "enough."

:::caution[The live instance limits very large solves]
A solve builds a matrix whose size grows with the total segment count, so the
hosted instance **rejects** solves that would be too large for the shared box
(you'll see a message in the error banner telling you to reduce N or pick a
smaller design — or switch to the array-block / H-matrix engine for big arrays).
The same instance also caps sweep lengths and optimizer eval budgets, well
above anything the UI sends. This applies **only** to the shared hosted
instance: a local install is **unlocked** (solve as big as your own machine
allows, sweep as long as you like). See `docs/deploy.md`.
:::

### The extended kernel (EK)

Beside **wire radius**, every momwire slot's gear menu carries an **extended
kernel (EK)** check — NEC's extended thin-wire kernel, the `EK` card. It
changes how the solve treats the wire's radius on-axis: instead of collapsing
the current to a filament, it integrates NEC's O(a²) expansion over the tube.
That only matters when a wire is **fat relative to its own segments** — the
Δ/a ratio. Above Δ/a ≈ 10 it moves the impedance a fraction of a percent;
below Δ/a ≈ 3 it moves it several percent, in NEC's direction. It costs about
1.0–1.3× the ordinary solve.

Turn it on when you're modelling thick elements (tubing, cages, a fat-wire
imported deck) or cross-checking a NEC model whose deck carries an `EK`
card — the flag is per slot, so the natural use is **A against B: the same
basis and mesh, one slot with the kernel and one without**, and the readouts
side by side. A slot running it is labelled **+EK** on its chip
(e.g. `B-spline d=2 +EK`), so the pair stays tellable apart.

Every momwire basis serves it — the Galerkin family joined with momwire
0.27.0 (momwire#246/#287/#299: every ground model, bent and stepped
geometry included). One combination is unavailable, and the check greys out
and says which:

- **K≥3 junction singular enrichment** (the validation-only B-spline knob)
  cannot run alongside it: the enrichment degrees of freedom bypass the very
  kernels the extended kernel corrects (momwire#271). The two grey each other
  out, so you can always back out of either.

**PyNEC** has no such check — the toggle drives momwire's kernel. Changing a
slot's solver resets the check along with that solver's other options, so an
armed kernel never rides silently onto a basis you just switched to.

### The feed model (Sin-Galerkin only)

Pick **Sin-Galerkin** and its gear menu grows one more control, **feed
model** — how the source gap itself is modelled:

- **NEC-compatible** (the default) — NEC's segment-wide gap. The readout
  reproduces NEC/EZNEC behaviour, including the familiar reactance drift as
  the mesh refines. Use it when you're cross-checking against NEC results.
- **Converged** — a zero-width (point) gap instead: the impedance converges
  to the B-spline answer, and the port admittance is exactly reciprocal.

On **near-open, high-Q feeds** the choice is worth a lot, and the gear menu
says so: those designs (`wire.lazy_h`, `wire.vbeam` and their class) show a
hint recommending *Converged*, which removes two to three orders of magnitude
of the apparent disagreement between solver bases (momwire#213). What it does
**not** do is reduce the mesh such a design needs — budget fine segments
either way; see
[the near-open feed](/advanced/convergence/#the-four-ways-a-curve-refuses-to-settle).
A slot running the non-default setting is labelled **Sin-Galerkin
(converged)**, so two Sin-Galerkin slots stay tellable apart at a glance.

No other engine carries the control: the plain **Sinusoidal** solver cannot
express a zero-width gap under point matching (momwire#212), and the B-spline
family already uses the point gap.

### One solve at a time

Everything a workbench tab computes — the live solve, the frequency sweep,
the convergence ladder, the norm check, the NEC pattern — runs through a
single **per-session solve lane** on the server, one computation at a time,
with the live solve always first in line. You'll notice it as steadiness on
heavy designs: background sweeps never compete with the solve that's drawing
the heatmap, and a knob turn preempts stale background work at the solver's
next internal checkpoint (milliseconds to one sweep point, not the rest of
the batch). Abandoning the tab mid-sweep stops the computation the same way.

When the selected solver is a **poor match** for the design (a dense engine
on a benchmark-class mesh), the workbench warns and withholds the solve; the
server holds background batches to the same answer, so a sweep of
minutes-per-point solves only runs once you've clicked **Solve anyway**.

## The ground plane

Real antennas hang over real ground, so the workbench starts there: the
**ground plane** checkbox is **on by default**, with free space one click away.
The over-ground picture — takeoff angle, the ground-lobed elevation pattern,
the shifted feed-point impedance — is usually the one your design decisions
actually depend on.

The selector describes what the ground **is**, independent of solver:

- **finite (εr=10, σ=0.002 S/m)** — "average" real earth, the default;
- **PEC** — a perfect reflector, mainly for apples-to-apples engine
  comparisons; or
- **terrain** — a faceted height profile around the site (levee/cliff
  presets), for antennas where the ground is not flat. See
  [Faceted terrain](#faceted-terrain) below.

Every solver then offers the same method sub-choice — full
**Sommerfeld/Norton** (most accurate, the reference below ~0.1λ heights)
vs. the **reflection-coefficient** approximation (the default: much
faster per solve, and fine above ~0.1λ; Sommerfeld's first solve of a
session builds an interpolation grid, but since momwire 0.15.0 that grid
is reused across a band's frequencies — a sweep pays a few fills on its
first pass, then every repeat sweep and knob-drag tick runs warm in tens
of milliseconds). Since momwire 0.8.0 the choice
is uniform: every momwire solver honours both models (Sommerfeld
validated against an independent NEC-2 implementation down to 0.02λ —
within ~2.4 Ω on the B-spline bases, ~0.1 Ω on the sinusoidal basis, and
the accelerators solve it on their fast paths), and PyNEC honours both
natively — with one caveat: PyNEC's (nec2++'s) Sommerfeld solve is
known-unreliable for conductors within 0.1λ of the ground that don't
touch it (low radials, half-squares, slopers — the engine warns; use a
momwire engine as the reference in that configuration). The far-field
pattern uses the real εr/σ on every basis.
Whatever runs, the solve readout's **ground** row reports the model that
was actually used, and over a finite ground the
[norm check](#norm-check--is-the-solve-trustworthy) readout becomes a
**radiated** percentage — the share of your input power that actually
leaves as sky wave. The rest is absorbed power, not error.

### Faceted terrain

The **terrain** ground type models a site whose ground is *not* an infinite
flat plane: a piecewise-linear height profile per azimuth sector, each facet
carrying its own medium. Three presets cover the common cases, with every
number a live knob:

- **levee** — a raised crest with two sloped sides: *crest width*, *slope*,
  *drop to water* on the *water bearing* side, *drop to land* opposite.
  Crest and slopes are earth; the water medium starts at the water-side toe.
- **cliff** — flat earth out to the *cliff edge*, then a sheer *drop* to
  water; *arc* < 360° restricts the cliff to a sector facing the *bearing*.
- **hillside** — a flat bench on a slope: the ground rises at the *uphill
  slope* on one side and falls at the *downhill slope* on the other (facing
  the *downhill bearing*), all earth. There is no bottom to reference and
  none is needed — the slope itself is the reflector, so the effective
  height grows continuously as the elevation drops. One honest limit:
  below the uphill slope angle the real sky is shadowed by the hill, which
  a specular model cannot express.

Media are fixed in this version (water εr=80 σ=0.005, land and crest εr=13
σ=0.005 — shown read-only in the panel); arbitrary facet profiles and custom
media are available from Python via `antennaknobs.terrain`.

How it solves: the **impedance/current solution runs over a flat Sommerfeld
ground with the crest medium** (near-field ground interaction is
crest-local; soil and water cannot be wire-gridded), and the **far field
reflects each ray off the facet its specular point lands on** — tilted
incidence, that facet's Fresnel coefficients, and the facet's height folded
into the reflected-path phase, which is what lets a modest mast act
electrically tall toward a drop-off. A single flat facet reproduces the
plain finite ground exactly, and the solve readout's ground row reports
**terrain (crest Somm.)**. It is a specular model: lobe positions and
direction-dependent asymmetry are its business; diffraction behind a crest
is not. The worked example —
[Antennas on a levee](/advanced/terrain/) — shows what it changes on a real
site and where each flat model fails.

Engine notes: momwire applies the facet far field natively. **PyNEC runs a
hybrid** — NEC-2 has no facet model, so NEC solves the currents over the
crest-medium Sommerfeld ground (exactly what the terrain recipe feeds the
current solve anyway) and the server applies the facet reflection to those
currents; the two engines agree to engine tolerance. The **NEC rp** overlay
switch (PyNEC only) is greyed out over terrain, because NEC's own `rp_card`
pattern is flat-ground-only and would silently disagree with the facet
traces. **Download .nec** exports the crest medium as a flat `GN` card —
a NEC deck cannot carry the facets.

A wire that ends at exactly z = 0 **connects to the ground plane** — the
return path a design like `wire.terminated_longwire` (fed and terminated
against ground through its vertical legs) depends on. NEC-2 makes that
connection physical over **PEC** ground only (finite-ground contact is a
NEC-4 feature), so solve ground-connected designs with PEC selected;
elevated designs are unaffected.

Designs can add their own rows to the solve readout (v0.43.0): a builder
that computes physical diagnostics — the catenary inverted vee reports its
**rigging tension in N and lbf**, sag, and derived rope cut length — sends
them as self-describing rows the readout renders generically, so a new
design idea (including a user design in `~/.antennaknobs/designs/`) gets its
numbers on screen with no frontend change.

When the design you're iterating **is** a user design — editor in one
window, workbench in the other — a **reload button** next to the design
picker re-reads the file and re-solves in place. Your tuned knob values
always survive the reload; a parameter the edited file just *grew* appears
with the file's default. One click instead of a page reload per edit
cycle.

## Power budget

Designs with a lossy feed network — a real coax or ladder-line run, a
matching network with a finite-Q coil, a lossy balun, a terminating
resistor — get a
**power budget** table in the solve readout: one row per network branch
with the fraction of the source's input power it dissipates, plus an
**antenna (accepted)** row for what actually reaches the wires. The rows
come straight from the MNA network solve (each branch current is an
explicit unknown, so the watts are read off the solution, not modelled
separately — see [Station modelling](/concepts/station-modelling/) for
the network vocabulary). Rows from a station *box* are grouped under a
header naming its instance and indented beneath it — one indent step per
nesting level — and a design may retitle rows for display via
`ui_params["budget_labels"]`. The same accounting drives
the reported radiation
efficiency: **every** dissipative branch counts, including resistive
coupling and matching elements, not just explicit `Load`s. Gain is
normalised by input power, so network loss already shows up in dBi;
the budget tells you *where* it went. Lossless networks hide the
branch rows.

Below the budget sits the honest bottom line: a **radiated (incl.
ground)** row — the fraction of input power that leaves as far-field
radiation *after* the ground has taken its share, the third of the
[three efficiency ledgers](/advanced/pota-performer/#the-efficiency-claim-true-in-its-ledger).
It comes from the dwell-triggered
[norm check](#norm-check--is-the-solve-trustworthy) pattern integral, so
it greys to **—** the moment any knob moves and fills in once you settle
— never costing the live drag path anything. Expect a shock the first
time: a "95% efficient" portable vertical over average ground radiates
~30%; a 7 m-high inverted vee on 20 m about 70%. Over PEC ground or free
space (nothing to absorb) it collapses back onto the structural
efficiency.

Designs that declare a real wire material (a `wire_type` knob over the
`WIRES` catalog, e.g. [`dipoles.pota_invvee`](/advanced/wire-gauge/))
additionally get a **wire loss (I²R)** row: the skin-effect power burned
in the antenna conductor itself, read from the solve's current
distribution. It counts toward the reported efficiency the same way the
network rows do, and the Info pane shows the matching **wire length**
and **wire weight** rows.

## The schematic view

The **Schematic** view draws the design's feed network — feedline, tuner,
balun, and the port the source sits on — as a circuit chain, the same drawing
the CLI writes with
[`schematic`](/reference/cli/#drawing-the-feed-network). The server renders it
to themed SVG on every knob change; no solve is involved, so component labels
(lengths, C and L values, turns ratios) always match the knobs on screen.

- **The power budget is folded into the picture.** Each box carries the
  fraction of input power it burns, drawn where the loss happens, so the
  [budget rows](#power-budget) and the circuit are one artifact rather than
  two. Elements that dissipate *nothing* — an ideal `TL`, a `bypass()` —
  appear here and nowhere else.
- **Balanced sections are drawn as two conductors.** Past a floating balun's
  secondary or along a balanced line the return rides the partner wire, so
  there is a second rail, the isolation barrier crosses the balun, and no
  ground symbol appears beyond it.
- **What isn't a chain isn't faked.** A trap in a dipole leg or a curtain's
  risers draw beneath the antenna labelled with the nodes they bridge; a
  parallel second antenna is noted rather than drawn in series; a 16-source
  array summarizes its feeds instead of drawing sixteen identical branches.
- Roughly two-thirds of the catalog is a bare antenna with no feed circuit at
  all. Those say so — *"No feed circuit — this design is the bare antenna"* —
  instead of showing an empty box.

A local install needs the optional extra for this view:
`pip install 'antennaknobs[schematic]'`.

## The measurement plane

Every number in the readout and every impedance chart is referenced to **one
port**. For a bare antenna that's the feedpoint; for a
[station design](/concepts/station-modelling/) whose chain runs from the rig
through a tuner and feedline, it's the rig end — what a sweep taken in the
shack sees.

When a design's chain has more than one named port, the readout grows a
**plane** selector, and the picked plane is marked on the schematic with the
disconnected part of the chain dimmed. Picking a plane re-solves the design
**as a VNA clipped on at that port would see it**: the chain upstream of the
pick is *unscrewed*, not merely re-driven — leaving a length of open-ended
coax dangling in parallel with the antenna would be neither what you asked for
nor anything you could measure. Attachments that hang off the structure
(traps, stubs wired into the antenna) are upstream of nothing, so they always
stay.

The frequency sweep, convergence ladder, and chart titles all follow the pick,
so a measurement overlay is compared at the plane you actually calibrated at.
The CLI has the same control on `fit` via `--plane`.

## Convergence sweep

To check that your chosen N is **converged** — i.e. adding more segments no
longer moves the impedance — run a **convergence sweep**. It re-solves the
current antenna across a range of N values and plots the resulting feed-point
impedance, so you can see where the curve flattens out. (Like the freq
sweep, it runs only while the Smith view that draws it is on screen —
v0.43.0's view-residency gating.) Basics:
[Segments & convergence](/reference/solver/#segments--convergence); the full
method (ladders, cross-basis validation with a second solver slot, and what a
non-settling curve is telling you): [How many segments?](/advanced/convergence/).

## Measured overlay — your VNA on the Smith chart

Under the Smith chart, **measured .s1p…** loads a one-port Touchstone file — a
NanoVNA export, or any VNA's — and draws the antenna you actually measured as a
dashed violet locus against the modeled one. It is the "did my model match
reality?" view, and the same overlay the CLI draws with
[`--measured`](/reference/cli/#overlaying-a-vna-measurement).

- **Capture is a local CLI step.** `python -m antennaknobs capture --out
  bench.s1p --start 27 --stop 30` sweeps an attached NanoVNA into a file you
  then load here. The server never opens a serial port — its ports are not
  yours when the backend runs elsewhere.
- **Your file stays on your machine.** The browser reads it and posts the text
  to be parsed; nothing is stored server-side. That also means it works
  unchanged when the backend runs somewhere else while the VNA is plugged in
  here.
- **Reference impedance is handled.** The measurement travels as impedance and
  is converted at the chart's own reference, so a 75 Ω calibration lands
  correctly on a 50 Ω chart.
- **Bands are clipped to the frequency sweep** so both loci cover the same
  frequencies; the label under the chart reports the span actually drawn, and
  says `(clipped)` when the measurement reaches past the swept band. A
  measurement with no overlap at all says so rather than silently drawing
  nothing — turn the [freq sweep](#convergence-sweep) onto that band, or move
  the measurement frequency there.
- **Calibrate at the plane you're comparing.** The chart shows the feedpoint,
  so a measurement taken at the feedpoint is the like-for-like one; a
  shack-end sweep includes feedline the model may not have.

Expect some irreducible disagreement — common-mode current on a real feedline
perturbs a measurement in ways a differential model doesn't reproduce. A
*structured* gap (the same offset across the band) usually points at something
physical: line length, ground, a connector.

## Design sessions (tabs)

The sidebar is a **notebook**: the tabs across its top (**D1**, **D2**, …) are
independent design sessions, each with its own geometry, knob values, design and
measurement frequency, ground setting, solver slot, and results. Click **+** to
open a new session — it starts fresh and solves on its own — switch by clicking a
tab, and close one with the **✕** (the last remaining tab can't be closed).

- Sessions are **fully independent**: changing a knob, the solver, or the ground
  model in one leaves every other session exactly as you left it.
- **Hover a tab** for its summary — design, solver, segment count, and ground
  model — e.g. `dipoles.invvee · B-spline d=2 N=15 · reflection-coef ground`.
- Switching to a session **re-solves** it, which is near-instant because the
  server caches recent solves (see [How a knob turn works](#how-a-knob-turn-works)).
- The light/dark theme and [pinned patterns](#comparing-patterns) are shared
  across all sessions; everything else is per-session.

Open the same design in two tabs to compare tunings, or load two different
antennas — then pair it with [pattern pinning](#comparing-patterns) to overlay
one session's radiation pattern on another's.

## Comparing patterns

The far-field views are calibrated **azimuth and elevation polar cuts** — the
numbers-first presentation you read gain, takeoff angle, and beamwidth straight
off. (The solver computes the full sphere on every basis; the cuts are how the
workbench chooses to show it.)

On the **azimuth** and **elevation** pattern views a **📌 Pin pattern** button
(top-left of the plot) freezes the current radiation pattern as a dimmed,
dashed **ghost** overlaid on the live one. Pin it, then change knobs — or switch
to a completely different design, or another [session tab](#design-sessions-tabs)
— and the live lobe redraws over the pinned ghost so you can see the effect
directly.

- **Pins are shared across every design session**: pin in one tab and the
  ghost (and its table row) is there in all the others, so you can overlay one
  antenna's pattern on another's — a Yagi's beam against a dipole's figure-8,
  say — not just two tunings of the same design. A pin is a frozen snapshot:
  it survives switching designs and even closing the tab that made it.
- Each pinned trace recomputes for whichever cut (azimuth or elevation) and
  cut-angle you're viewing, so it always shares the live plot's geometry.
- A **compare table** appears alongside with a row per pattern — peak gain
  (dBi), takeoff angle, front-to-back, and −3 dB azimuth beamwidth — so the
  overlaid shapes come with the numbers that matter.
- **Show or hide a pin without losing it**: click a pinned row's colored
  swatch-and-name in the compare table. The ghost disappears from the plot and
  the row dims, but its metrics stay readable for the side-by-side numbers;
  click the name again to bring the ghost back in the same color. Handy when
  several pins crowd the plot and you want to declutter one at a time.
- **Removing pins**: the **✕** on a row deletes that pin (everywhere — pins
  are shared); **clear** above the table removes them all. The **–** button
  minimizes the table to a compact *n pinned* chip — ghosts stay on the plot —
  and clicking the chip reopens it.

## Norm check — is the solve trustworthy?

On the **azimuth** and **elevation** pattern views a **norm check** checkbox
(top-right of the plot) draws a second, dotted radiation curve over the solid
live one — a built-in "should I trust this pattern?" gauge.

The two curves are the *same pattern normalised two different ways*. The solid
line scales it by the **input power** the feed delivers (the circuit side — what
the impedance solve says went in). The dotted line renormalises by the pattern's
**own integrated radiated power** (the field side — what the far-field integral
says came back out). For a lossless PEC antenna those two must be equal, so:

- **The curves overlap** ⇒ the solve conserves power: the mesh is fine enough
  that the currents and the radiated field agree.
- **A visible gap** ⇒ discretisation error — too few segments (or too stiff a
  basis) for this geometry. Add segments and the gap closes.

Beside the checkbox a **Δ** readout gives that gap as one number in decibels —
**0 dB is perfect power balance**. A few tenths of a dB is typical and harmless;
a large value means the pattern and its gain figures should not be trusted until
you refine the mesh. This is exactly NEC's classic **"average gain"** sanity
check, which most tools make you compute by hand. It's cheap (a closed-form
integral for free space and PEC ground, a small reference-grid quadrature over
finite ground, either way evaluated once the knob settles), so it's **on by
default** — uncheck it to hide the overlay and the readout.

**Over a finite ground the gap is not supposed to be zero — it's physics**,
so the readout switches to its honest form: **radiated NN%**, the fraction
of input power that actually leaves as far-field radiation. The pattern
integral only counts power that leaves upward — what the lossy ground
absorbs never comes back — so the shortfall from 100% is structural loss
plus real ground absorption, exactly like NEC's average-gain value over
real ground (hover the readout for the raw Δ dB). The same number fills
the [power budget](#power-budget)'s **radiated (incl. ground)** row, so
it follows you to every view. It's still a mesh check: what should be
small is how much the reading *moves* as you add segments, and switching
the ground to PEC (or off) should send it back toward ~100% (Δ 0 dB).

## Copying params back to code

The **gear menu** (⚙, top of the sidebar) has **Copy params (Python)**, which
copies the current knob values to the clipboard as a paste-ready
`default_params = {...}` block (a `<variant>_params` block when you're on a
named variant). Drop it straight into a design file to bake in whatever you
dialed in — no more transcribing values off the screen by hand.

The same gear menu also has **Download .nec deck**, which exports the design as
a NEC-2 card deck for xnec2c / 4nec2 / EZNEC. The reverse — bringing a `.nec`
deck someone published *into* the workbench — is
[Loading NEC decks](/reference/nec-import/).

On phones, the gear menu also has a **full screen** check (under *display*):
it hides the system status and navigation bars so the whole screen is
workbench — uncheck it or use the back gesture to exit. The control appears
only in the mobile layout (desktop already has F11), and only on browsers
with full-screen support (so not iPhone Safari).

## How a knob turn works

A knob change sends one message over the `/ws` WebSocket; the server re-solves in
a worker thread and sends the result back. Perceived latency is dominated by the
**solve time** (free-space dipole-class solves are tens of milliseconds), not the
network — so a regional server feels responsive for live tuning. Repeated solves
of the same request hit a server-side cache, so flicking a knob back to a prior
value is instant.
