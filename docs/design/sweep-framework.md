# The workbench sweep framework: a deliberate design arc

Status:

- **Step 1 (inventory) is complete** (§1, §2).
- **One principle is decided**, 2026-09-28: an analysis is Python (§3.1).
- The rest of §3 is still *candidate* principles for step 2.
- §4 opens the first decision axes that §3.1 creates. None of them is decided.

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

*Addendum, 2026-09-28.* Three of these were fixed after the inventory:

- **Item 3** (the Smith trail ignored its switch): #1784.
- **Item 9** (the CLI's 10·log10\|Γ\|): #1775.
- **Item 10** (two Z* estimators): #1782. Z* is now Z∞, one estimator in
  both tools, against the achieved segment count.

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

## §3. Principles

### §3.1 Decided: an analysis is Python (Steve, 2026-09-28, #1757)

> A lot of work can go into setting up a plot, and with our UI there is no
> good way to save that work so that it can be repeated later or reused to
> generate the same chart on other antennas. SimNEC has a way to store this in
> their data model. We don't really have one, and probably don't really want
> one. I think we need to go back to our Python first principle and describe
> the sweeps using Python commands. We can have the UI suggest the right
> sequence of commands, but that is how it should be stored. This is a bit of
> a departure from our work with Dan, but that is okay. We need a
> build_analyses() method in our Builder class to set up the analyses we want,
> and we can choose from them in the UI. The .nec and .ssn input paths should
> create a stub that inputs the file, but allows us to add plot specs through
> this new method.

What follows from it:

- **The recipe lives in Python.** A design's analyses come from
  `Builder.build_analyses()`, in the design's own file. Designs, knobs and
  variants are already Python, so analyses become diffable, reviewable and
  shareable, with no stored data model to version.
- **The UI chooses, runs and suggests; it does not store.** It lists a
  design's analyses and runs the one picked. It can turn what the user set up
  into code to paste, as the Tools menu's "copy the current knob values as a
  paste-ready Python default_params block" already does for knobs.
- **A deck gets a stub.** A `.nec` or `.ssn` input becomes a small Python
  design that loads the file and adds `build_analyses()`.
- **It retires two of §2's axes.** What a pin's recipe is (axis 1) is Python,
  and where recipes persist (axis 10) is a file.
- **Accepted cost:** users who do not write Python, Dan's side of the
  workbench, depend on the UI generating the code for them.

Consequences for the candidates below:

- Principle 3 (a pin says what it is) now splits cleanly: the *analysis* is
  the recipe, in Python, and a *pin* is data captured from one run of it,
  under a recorded context.
- Principle 7 (nothing runs unasked) constrains §3.1's shape: an analysis must
  be a declarative spec that can be listed without solving (§4, axis A1).
- Principle 8 (the same numbers in both tools) becomes structural if the CLI
  can run the same named analysis.

### §3.2 Candidates *(step 2: not agreed)*

A starting list for Steve to accept, reject or rewrite. None of these is
decided, and each names the tension it would settle. They are drawn from §1
and §2; the order is not a ranking.

1. **The workbench answers "what does turning this knob do?", and the CLI
   answers "show everyone."** Keep the workbench's sweep surface to what an
   interactive session needs. Leave publication charts (panels, overlays of
   many engines, callouts) to the CLI and scripts, which already do them.
   *Tension:* Dan asked for engine overlays in the workbench (#166).
2. **One sweep concept, and several ways to draw it.** A sweep is (the
   swept variable, its grid, a solve context). Frequency, density and a knob
   differ only in the variable. VSWR, S11, R/X and the Smith trail are
   projections of the same trace. (The VNA's channel/trace/window split;
   SimSmith's one sweep menu.) *Tension:* frequency has refinement, band
   anchoring and the dial; the parameter sweeps have Richardson and Stop/Run.
3. **A pin says what it is.** A pinned sweep is a snapshot of data, taken
   under a recorded context: design, knobs, engine, ground, z0. It is shown
   with that context, and it is never silently recomputed. (VNA memory, ADS
   Store, Shneiderman's "save the items" vs "save the settings".)
   *Tension:* a recipe that recomputes stays comparable after an engine fix.
4. **Stale is visible, never silent.** When the live context departs from a
   pin's, the pin says so, like the VNA's invalidate-or-interpolate rule and
   the Z-vs-param view's dimming. *Tension:* too many warnings become noise.
5. **Superposition first, with a hard cap.** Comparison overlays on the same
   axes, in a few fixed-colour slots (instruments 4; Gleicher: poor past 2
   or 3), with an explicit-difference readout rather than more curves. The
   pattern pins' 4 slots are the precedent. *Tension:* a family sweep
   (knob × frequency) wants more than 4 curves.
6. **One graph by default; more only when the axes differ.** A second graph
   earns its place when its x or y cannot be shared (Wang Baldonado's
   parsimony; TradingView's per-pane y over a shared x). *Tension:* your "one
   to begin with, then split".
7. **Nothing the user did not ask for runs.** Residency and switches start
   sweeps today, and the knob sweep runs only when asked (#1759). Pins never
   start solves. *Tension:* the density sweep runs automatically when its
   view is resident.
8. **The same numbers in both tools.** The workbench and the CLI compute S11,
   Z* and the ladders one way (§1.6 items 9 and 10), so a number quoted from
   either is the same measurement.
9. **Words mean one thing.** Define "sweep", "trace", "pin", "reference" and
   "stale" once, in this document, and use them in the UI and the docs
   (§2 axis 12).


## §4. Decision axes *(step 3)*

§3.1 opens these first. Each lists options and what they trade. None is
decided; they are taken one at a time, in this order, because each depends
on the one before.

### A1. What `build_analyses()` returns

- **(a) Declarative specs.** Small frozen dataclasses, e.g.
  `Sweep(param="length_factor", lo=0.9, hi=1.1, points=11, views=("zparam",
  "smith"))`, or `Sweep.density()` for the convergence ladder. The UI lists
  them without solving, the CLI and the workbench read the same object, and a
  spec prints back as the code that made it, which is what the UI's
  "suggest the commands" needs.
- **(b) Imperative calls** that run the sweeps when invoked. This is the most
  flexible, but nothing can be listed or shown without executing it, which
  breaks §3.2 principle 7 and makes the UI's picker a runner.
- **(c) Specs plus an escape hatch.** Like (a), with an optional
  `custom=callable` for what the spec language cannot say, which the
  workbench shows only as "runs in the CLI".

### A2. Reuse across antennas

The comment asks for "the same chart on other antennas". A method on one
design only reaches that design.

- **(a) A shared library of named factories** (`analyses.convergence()`,
  `analyses.band_swr("20m")`, `analyses.knob(name, span=0.2)`) that any
  `build_analyses()` composes. The workbench can also offer the library's
  generic analyses on any design, with no code.
- **(b) Inheritance only.** A family base class defines the analyses and its
  designs inherit them. This works within a family, not across them.
- **(c) Both,** with (a) as the unit of reuse and (b) for family defaults.

### A3. Where a user's analyses live for a design they cannot edit

The catalog is installed read-only, and a deck is not Python.

- **(a) A user design that subclasses the catalog one** (`user.<name>`) and
  adds `build_analyses()`. It uses the existing user-design mechanism and
  its trust gate.
- **(b) A sidecar file per design** in the user config directory, beside
  settings.toml, holding only a `build_analyses()`, merged with the design's
  own.
- **(c) The UI writes (a) or (b) for the user** ("save these analyses"), so
  the Python is generated rather than typed.

### A4. The deck stub

- **(a) A generated `.py` next to the deck**: a `Builder` that loads the
  deck through the existing importer (`builder_from_file`) and adds
  `build_analyses()`.
- **(b) An in-memory stub** with analyses from a sidecar (A3 b), so nothing
  is written next to the user's deck.

Later axes, not opened yet: pins as data captured from an analysis run (§2
axes 2 and 3), engines and ground in a spec, and how many graphs an analysis
may ask for (§3.2 principle 6).
