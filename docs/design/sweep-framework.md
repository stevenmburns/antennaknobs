# The workbench sweep framework: a deliberate design arc

Status: **step 1 (inventory) complete**, §1 and §2. Nothing in this document is decided yet.

This arc is about how the workbench's sweeps, the graphs that draw them, and
comparison ("pinning") fit together. It continues AK#1757 phase 2: the
frequency sweep and the convergence/knob sweep grew up separately, and they
should probably share a framework, above all a pinning framework.

Steve, 2026-09-27, on how to run it:

- It is a long, deliberate arc.
- Take it slowly, and make principled decisions only after weighing the
  options and existing designs.
- Pinning a sweep is attractive, but it is "not quite the same as pattern
  pinning".
- We seem stuck with one sweep graph. We might want one to begin with, and
  then want to split it into several.
- We may not want anything complicated in the workbench at all, and rely on
  the CLI or custom scripts for the fancy diagrams.
- Avoid a design that becomes unwieldy.

## How the arc runs

1. **Inventory.** No opinions: what exists here (§1), and how other interfaces
   handle the same problems (§2), well beyond antenna tools.
2. **Principles.** A short list agreed before any design. For example: what
   the workbench is for as opposed to the CLI, what a pin means for a sweep,
   and what must stay simple.
3. **Decision axes, one at a time.** Each axis gets options, trade-offs and
   precedents, and Steve decides it before the next is opened.
4. **Implementation.** Only then, in small steps that each ship on their own.

`scratch/sweep-unification-options.md` is an earlier analysis written for
#1757. It sketches a shared `Trace` type and recommends an option. Treat it
as input to step 3, not as a decision.

---

## §1. What exists (antennaknobs v0.90.0, main @ 201fa89e1)

Paths: `FE` = `src/antennaknobs/web/frontend/src`, `WEB` =
`src/antennaknobs/web`. Taken from the code with file and line citations
(the full cited inventory is `sweep-framework-inventory.md`, beside this file). Items marked
*(verified)* were re-checked by hand.

### 1.1 The sweeps the workbench runs

| | frequency | freq refinement (#744) | density (convergence) | knob (Z vs parameter) |
|---|---|---|---|---|
| endpoint | `POST /sweep` | `/sweep` with `_refine` | `POST /param_sweep` (`/converge` is an alias) | `/param_sweep` |
| server path | momwire: batched `momwire_sweep`, chunks aimed at 500 ms; externals: per point | same | one full `_solve_z_only` per point | same |
| lane kind | `sweep` | `sweep_refine` (not superseding, so a refinement cannot kill its base) | `converge` | `converge` |
| runs when | the freq-sweep switch is on and Smith, S11 or VSWR is resident | the tail of a completed base sweep, with refine on | automatically, when Z-vs-param is resident, or when the param-sweep switch is on and Smith is resident | only when asked (a header edit, "Sweep this knob…", or Run) |
| x grid | a five-level range precedence (session edit → file → design → band policy → ×0.8–×1.25), 17 points with refine on, else 41 (21 on Sommerfeld ground); at most 500 | a curvature planner in display space, over resident projections only; 48 in total, 12 per round | `DENSITY_LADDER` 8…68 | lin or log over the knob's range; 11 points by default, 2–201 allowed |
| extras | fixed-frequency advisories | — | Richardson Z* (client, per feed); gap-fed advisory | none |
| a failed point | ends the stream | same | the server skips it and goes on; the client drops it silently | same |
| Stop / Run | none; only the global Cancel | — | Stop keeps the partial points; Run | same, plus stale dimming |
| server cache | `(design, freq)` Z cache, 4096 entries | reads it | none | none |

Signatures:

- **Frequency sweep.** The signature exempts `measurement_freq_mhz` (#1755):
  moving the measurement frequency does not re-sweep. The server's own sweep
  cache key keeps it.
- **Parameter sweep.** The signature exempts the swept parameter itself, and
  includes the value list.

Supersession: `sweep` and `converge` are in `SAME_KIND_SUPERSEDES`, so a second
stream of the same kind from one session cancels the first
(`WEB/lane.py:59-61`).

Other background jobs:

- pattern-cut angle refinement (`/cuts`, no lane turn);
- the norm check;
- the NEC `rp` pattern;
- `/pattern_metrics`;
- the optimizer, whose per-evaluation Z is a single moving dot and keeps no
  trace;
- the tracker.

### 1.2 The graphs that draw sweep data

| view | plots | scale choices | controls | notes |
|---|---|---|---|---|
| VSWR vs freq (`SweepChart`) | SWR(f) per feed, and the live marker | 1−1/SWR (default), ρ (EZNEC), fixed presets, custom; no Auto | the y-axis popover; the freq-sweep switch (desktop) | threshold line, below-threshold shading, "2:1 BW" readout; dots until settled |
| S11 (dB) vs freq (`SweepChart`) | 20·log10\|Γ\| | Auto (default), floors, custom | same | |
| Smith (`SmithChart`) | freq locus; param-sweep trail with ring/disc/Z* diamond; measured overlay | zoom/pan on the stage | freq sweep, param sweep, measured .s1p, clear | the only chart that draws the measured overlay |
| Z vs parameter (`ZParamChart`) | R (left) and X (right) vs the param, with Z* lines, the current-value guide and R=Z0 / X=0 references | lin/log x; R and X ranges, each Auto or fixed | parameter, from/to/points, log, Stop/Run, reset | **port 0 only**; stale dimming |

**One of each.** A session holds at most one chart per view id (6 pins; the
grid shows the first 4), plus rail thumbnails of the same data. It holds one
frequency-sweep dataset and one parameter-sweep dataset. The Z-vs-param view
and the Smith trail share that one dataset.

**Phone.**

- Pinned views appear as a carousel.
- The Smith/VSWR/S11 overlay checkboxes live in the gear menu.
- The Z-vs-param header stacks above its chart.

### 1.3 Comparison and pinning today

| mechanism | captures | re-solves? | on a design switch | persistence |
|---|---|---|---|---|
| pattern pin (`PinnedPattern`, shell state in `App.tsx`) | DATA: the whole solve response and a label "{design} @ {f} MHz"; 4 colour slots; an `enabled` flag | no; its cuts are recomputed from the pinned solve | survives, and is shared across tabs | memory only; lost on reload |
| pattern compare table | the live row plus one row per pin: peak, takeoff, F/B, beamwidth, RDF | the live metrics refetch | — | — |
| measured VNA overlay | DATA: Z vs f from a .s1p | no; re-projected at the current z0 | kept (per session) | tab lifetime |
| A/B/C engine slots | a backend and options per slot | switching slots re-runs the sweeps on the new slot | — | seeded from settings.toml |

**Absent:** any sweep or trace pin, any hold or reference trace, and any
workbench comparison across slots. Sweeps run on the active slot only.

### 1.4 Settings and state

- **settings.toml `[switches]`:** `freq_sweep` ("freq sweep", on),
  `convergence_sweep` ("param sweep", off), `refine` ("adaptive resolution",
  on).
- **Browser view prefs (`akb.viewPrefs.v1`, global):** pins, layout, readout
  collapse, the VSWR/S11 axis choices and the SWR threshold.
- **Tuning keys:** sweep base N, refine budgets, refine tolerance.
- **Session-only:**
  - the sweep range edit;
  - the Z-vs-param parameter, range, log and axes, which reset on a design or
    variant switch;
  - the measured overlay.

### 1.5 The command line (`antennaknobs sweep`)

It sweeps any knob, frequency included, and takes several engines at once:

- `--panels`: one twin-axis R/X chart per engine;
- `--overlay`: every engine on one chart;
- `--only r|x`;
- `--log`, `--r-range` / `--x-range`, `--callouts`, `--markers`, `--set`;
- `--measured` on the SWR, Smith and R/X charts;
- the chart modes `--swr`, `--gain` and `--patterns`, and a Smith mode.

The `nominal_nsegs` density study prints a table (`N_ach`, R, X, |ΔΓ|, Z*).
Its charts are plotted against the achieved segment count.

| CLI only | workbench only |
|---|---|
| gain vs a parameter; pattern overlays per swept value | the live current-value guide; hover/tap readout |
| SWR/reflection vs any knob (the workbench's VSWR/S11 are vs frequency only) | adaptive refinement |
| R/X vs frequency (the workbench's parameter sweep excludes freq-linked knobs) | the range precedence and band anchoring; the dial is the range |
| several engines at once | the SWR threshold and bandwidth readout; the 1−1/SWR and ρ scales |
| `--markers`, `--callouts`, `--only`, `--set` | the gap-fed and fixed-frequency advisories |
| measured overlay on the SWR and R/X charts, interpolated onto the sweep grid | Stop/Run/partial/stale |
| a density table; x = achieved N; first-order Z* | x = nominal N; Z* by quadratic least squares in 1/N over the last ≤ 5 points |

### 1.6 Where the code, the docs and the earlier note disagree

These were found while taking the inventory. They are facts to fix or decide,
not design:

1. The options note says the measured overlay is on `SweepChart` too. It is
   on Smith only. *(verified)*
2. The note says a failed parameter-sweep point "is recorded". The client
   drops it; `ParamSweepData` has no error field. *(verified)*
3. The Smith chart draws the parameter-sweep trail whenever a parameter
   sweep exists, whatever the switch says. The docs say the switch draws it.
   *(verified)*
4. `measurement_freq_mhz` is exempt from the client's freq-sweep signature,
   but kept in the server's sweep-cache key.
5. `cli.md` says frequency sweeps use the vectorized sweep. Only
   `--swr --param freq` does.
6. A stale name, `CONVERGE_N_VALUES`, appears in `sweep.py` and `cli.md`.
7. `web.md` links the frequency sweep to `#convergence-sweep` in two places.
8. A comment in `useViewPrefs` says the axis choices are written "where they
   differ from Auto"; the VSWR default is the 1−1/SWR scale.
9. The CLI's `--swr` chart plots reflection as **10**·log10\|Γ\|. The
   workbench's S11 is 20·log10\|Γ\|. *(verified)*
10. The two tools compute Z* differently (§1.5).

---

## §2. How other interfaces do it

The cited survey is `sweep-framework-survey.md`, beside this file. It covers
five families:

- antenna and RF tools: EZNEC, AutoEZ, Zplots, 4nec2, MMANA, SimSmith,
  xnec2c, ADS, AWR, CST;
- lab instruments: VNA trace memory, spectrum-analyzer trace modes,
  oscilloscope references, NanoVNA-Saver;
- financial charting: TradingView, Bloomberg;
- exploratory data analysis and experiment tracking: JMP, Vega-Lite,
  Observable, Grafana, Spotfire, Dash, ipywidgets, MATLAB, W&B,
  TensorBoard;
- the visualization literature: Gleicher, Tufte, Wang Baldonado, Shneiderman,
  Heer, Bret Victor.

What each family tends to do:

- **Antenna tools** compare by overlaying data snapshots kept in files. The
  caps are small (4nec2 5, Zplots 4), and staleness is silent. ADS alone
  stores the recipe with the snapshot and can recall it. SimSmith's sweep is a
  live recipe, with a small size while editing and a large size on demand.
- **Instruments** keep the stimulus (the VNA "channel"), the displayed
  quantity (the trace) and the layout (window, sheet) as separate objects. A
  pin is a per-trace memory in a few fixed-colour slots. Explicit difference
  (Data−Mem, Data/Mem, delta markers) is first class. Staleness has stated
  rules: a VNA memory is invalidated, or interpolated, when the stimulus
  changes.
- **Financial charting** adds the comparand as a live recipe and normalizes to
  make it comparable, against an implicit baseline that moves with the view.
  Each series goes to the same pane and scale, a new scale, or a new pane. The
  x axis is shared; y is per pane. Links are per dimension, in named groups.
- **Data-analysis tools** compose charts with a small algebra: layer
  (superposition), facet (small multiples) and concat. Each operator defaults
  to shared or independent scales. The things compared vary: runs (W&B),
  remembered settings (JMP), time shifts (Grafana), marked subsets
  (Spotfire). JMP's Prediction Profiler is one-at-a-time sweeps around a
  movable current point, which is the closest analogue to a knob sweep.
- **The literature** gives the vocabulary. Gleicher: juxtaposition,
  superposition and explicit encoding, with superposition poor past 2 or 3,
  and a chosen reference vs reference-free designs. Wang Baldonado: parsimony,
  since a single view is a stable context and each coupling adds complexity.
  Shneiderman 1996 already names "save the items" vs "save the settings for
  the control widgets". Victor: a sweep as "abstracting over" a knob, where
  pointing at the curve steps back down to one value.

**The design axes the precedents reveal.** These are the raw material for §4,
not decisions:

1. What a pin stores: data, a recipe, or both (with recall).
2. What happens when it goes stale: invalidate, interpolate, freeze with a
   warning, silent, or lost.
3. Superposition, juxtaposition, or explicit difference, and whether one
   placement switch moves between them.
4. The baseline: explicit and user-chosen, implicit, or none.
5. Linked or independent axes and cursors; dual y axes (contested).
6. Where the sweep definition lives: a shared stimulus object, one dialog per
   sweep type, or one sweep over any parameter, frequency included.
7. A whole family of curves, or one selected member.
8. Capacity and colour: a few fixed slots, or many with a display cap; colour
   owned by the slot or by the run.
9. Recompute cadence, and keeping the view state across recomputes.
10. Scope and persistence: session, workspace, URL, file.
11. Simple and built in, or pushed out to scripts and files.
12. The same word naming different things: "pin", "hold", "memory",
    "reference". Our vocabulary will need definitions.

---

## §3. Principles *(step 2, not started)*

## §4. Decision axes *(step 3, not started)*
