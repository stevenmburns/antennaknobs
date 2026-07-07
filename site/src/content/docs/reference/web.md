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

## The hosted instance

A hosted simulator is running at
**[app.antennaknobs.dev](https://app.antennaknobs.dev/)** (a single
FastAPI process serving the API, the `/ws` live-solve channel, and the built
React SPA). It's deployed as a container on Fly.io; the repo's `docs/deploy.md`
is the runbook.

## Driving a knob

Each parameter in a design is a knob (the big one is the measurement-frequency
VFO dial; the rest are smaller). Three ways to change one:

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

## Live & paused solving

A **Live** toggle sits next to the frequency dial. It looks **depressed when on**
and raised when off:

- **On** — every knob turn triggers a solve; the plots track your hand.
- **Paused** — knob turns just move the values; nothing solves until you turn
  Live back on. Useful when you want to set several knobs before paying for a
  solve, or when a heavy design makes continuous solving sluggish.

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

Under the hood it's a derivative-free **Nelder–Mead** search (each evaluation is
a full MoM solve), bounded by your Optimize ranges, and it always runs on the
fast **momwire** engine — never PyNEC, which is too slow for an interactive loop.
It's a tuning aid, not a global optimizer: give it sensible ranges and a couple
of free knobs, not a dozen.

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
(**triangular**, **sinusoidal**, **bspline**), the accelerators (**hmatrix**,
**arrayblock**), and the optional **PyNEC** backend — see
[The solver & accuracy](/reference/solver/) for what each is good at.

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
This applies **only** to the shared hosted instance: a local install is
**unlocked** (solve as big as your own machine allows). See `docs/deploy.md`.
:::

## The ground plane

Real antennas hang over real ground, so the workbench starts there: the
**ground plane** checkbox is **on by default**, with free space one click away.
The over-ground picture — takeoff angle, the ground-lobed elevation pattern,
the shifted feed-point impedance — is usually the one your design decisions
actually depend on.

The selector describes what the ground **is**, independent of solver:

- **finite (εr=10, σ=0.002 S/m)** — "average" real earth, the default; or
- **PEC** — a perfect reflector, mainly for apples-to-apples engine
  comparisons.

Each solver then models that ground as well as it can, with a method
sub-choice on both engines — full **Sommerfeld/Norton** (most accurate,
the reference below ~0.1λ heights) vs. the **reflection-coefficient**
approximation (the default: much faster per solve, and fine above
~0.1λ; Sommerfeld is opt-in because its first solve at each frequency
builds an interpolation grid — so the first sweep takes a few seconds —
though repeat solves reuse cached grids and run in tens of milliseconds
since momwire 0.7.0). On momwire the plain
B-spline solver honours both (true Sommerfeld since momwire 0.6.0,
validated within ~2.4 Ω of an independent NEC-2 implementation down to
0.02λ); the accelerated B-spline solvers keep their fast
reflection-coefficient paths, the sinusoidal basis is
reflection-coefficient only (~0.1 Ω of NEC's gn 0 — it shares NEC's
basis), and the triangular basis folds the impedance solve to the PEC
image. The far-field pattern uses the real εr/σ on every basis. Whatever
runs, the solve readout's **ground** row reports the model that was
actually used, and over a finite ground the
[norm check](#norm-check--is-the-solve-trustworthy) Δ reads "incl. ground
loss" — a steady dB or so there is absorbed power, not error.

## Convergence sweep

To check that your chosen N is **converged** — i.e. adding more segments no
longer moves the impedance — run a **convergence sweep**. It re-solves the
current antenna across a range of N values and plots the resulting feed-point
impedance, so you can see where the curve flattens out. Details and how to read
it: [Segments & convergence](/reference/solver/#segments--convergence).

## Design sessions (tabs)

The sidebar is a **notebook**: the tabs across its top (**D1**, **D2**, …) are
independent design sessions, each with its own geometry, knob values, design and
measurement frequency, ground setting, solver slot, and results. Click **+** to
open a new session — it starts fresh and solves on its own — switch by clicking a
tab, and close one with the **✕** (the last remaining tab can't be closed).

- Sessions are **fully independent**: changing a knob, the solver, or the ground
  model in one leaves every other session exactly as you left it.
- **Hover a tab** for its summary — design, solver, segment count, and ground
  model — e.g. `dipoles.invvee · B-spline d=2 N=21 · reflection-coef ground`.
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

**Over a finite ground, Δ is not supposed to be zero.** The pattern integral
only counts power that leaves upward — what the lossy ground absorbs never
comes back — so a steady Δ of a dB or so *is the ground-loss reading* (the
readout says "incl. ground loss" to remind you), exactly like NEC's average-gain
value over real ground. It's still a mesh check: what should be small is how
much Δ *moves* as you add segments, and switching the ground to PEC (or off)
should send it back toward 0 dB.

## Copying params back to code

The **gear menu** (⚙, top of the sidebar) has **Copy params (Python)**, which
copies the current knob values to the clipboard as a paste-ready
`default_params = {...}` block (a `<variant>_params` block when you're on a
named variant). Drop it straight into a design file to bake in whatever you
dialed in — no more transcribing values off the screen by hand.

The same gear menu also has **Download .nec deck**, which exports the design as
a NEC-2 card deck for xnec2c / 4nec2 / EZNEC.

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
