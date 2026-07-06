# Website content plan — antennaknobs.com & antennaknobs.dev

Status: draft for review. A page-by-page content plan for the two domains.
Anchored on the positioning in
[`market-research-antenna-simulators.md`](./market-research-antenna-simulators.md)
(note: that doc predates the rename — read `antenna_designer` → **antennaknobs**,
`pysim` → **momwire**).

## The one-sentence pitch

> An open-source, browser-based wire-antenna MoM simulator: grab a knob, watch
> the pattern, SWR, and impedance move in real time — paid-tier modeling quality
> (multi-basis MoM, H-matrix acceleration, NEC-2 cross-validation) for free, with
> no platform lock-in.

Everything below is in service of one idea: **nobody else leads with a live,
no-install "drag a knob, see the physics move" demo.** Both domains open with it.

## Audience tiering

| Domain | Primary audience | Voice |
|---|---|---|
| **antennaknobs.com** | hams + RF/EE students (broad) | plain-language, results-first, minimal jargon |
| **antennaknobs.dev** | Python devs + contributors | precise, code-shaped, canonical docs home |

Rule: anything code-shaped (API, authoring, contributing) lives **only** on `.dev`,
so there is one canonical URL per topic. `.com` links *into* `.dev` for depth.

---

## antennaknobs.com — the front door

```
/                     Hero: live simulator embed + one-line pitch + two CTAs
/gallery              Design catalog as cards → "open in the simulator"
/why                  Why antennaknobs (vs 4nec2 / EZNEC / PyNEC) — honest table
/learn                On-ramp: "design your first antenna in 5 minutes"
/about                Project, license (open source), credits, links to .dev
```

### `/` — Home

- **Above the fold:** an embedded live simulator instance (or, if cold-start is too
  heavy, a looping screen capture) showing a dipole/Yagi with a knob being
  dragged and the polar pattern + SWR responding. Caption: *"This is the whole
  tool. No install."*
- **One-line pitch** (above) + sub-line naming the audience: *"For ham operators,
  RF students, and anyone who'd rather turn a knob than hand-write a NEC deck."*
- **Two CTAs:** `Try it in your browser →` (the hosted app on .dev) and a copy box
  `pip install antennaknobs`.
- **Three proof tiles** drawn from the differentiators: *Multi-basis MoM* ·
  *H-matrix acceleration for big arrays* · *Cross-checked against NEC-2*.
- **Strip of gallery thumbnails** → `/gallery`.

### `/gallery` — Design catalog

- Card grid; each card = geometry thumbnail + name + one-line use ("40m full-wave
  loop", "2-element 10m Yagi") + **Open in the simulator** button (deep-links the
  hosted app with that design preloaded).
- Filter by band / type (dipole, Yagi, loop, vertical, bowtie, multiband).
- Each card's "details" links to the design's page on `.dev` (source + knobs).

### `/why` — Why antennaknobs

- The honest comparison table from the market research (Tier-2/Tier-3 row): method,
  interface, platform, price, license. Lead with the three real differentiators
  (multi-basis, H-matrix, web UI + cross-validation) and **state the gaps too**
  (no conductor loss yet, `.nec` import still pending) — honesty is itself a
  differentiator vs. the commercial pitches. Ground is a strength to state
  positively: finite ground solved two independent ways (momwire refl-coef +
  PyNEC Sommerfeld) that cross-check within ~2 Ω, and the UI reports the model
  each solve actually used.
- Positioning statement verbatim.

### `/learn` — First antenna in 5 minutes

- A guided, screenshot-driven walk: pick a dipole → tune length to resonance
  watching SWR → read the pattern → export the dimensions. No code.
- Ends with two doors: *"Want the physics?"* → `.dev` concepts; *"Want to script
  it?"* → `.dev` quickstart.

### `/about`

- What it is, who's behind it, MIT/OSS license, repo link, how to cite, contact.

---

## antennaknobs.dev — the workshop

Hosts **both** the live app and the canonical docs.

```
/app                  The hosted interactive simulator (the real product)
/docs/                Documentation root
  /docs/quickstart      pip install → first design in Python in 10 lines
  /docs/concepts        The model: AntennaBuilder, params/knobs, build_wires
  /docs/authoring       Three ways to describe geometry (coords / Transform / Drone)
  /docs/catalog         Every design rendered with its source + live knobs
  /docs/solver          The MoM engine: bases, H-matrix, accuracy & validation
  /docs/web             Running the web UI / adapter / ParamSpec
  /docs/cli             nec_export and command-line usage
  /docs/api             Generated API reference
/contributing         How to add a design, run tests, submit a PR
/changelog            Release notes
```

### `/app` — The hosted simulator

The live FastAPI + React app. Deep-linkable per design (so `.com/gallery` cards
and `/docs/catalog` can point at it). This *is* the product; docs orbit it.

### `/docs/quickstart`

`pip install antennaknobs`, then ~10 lines: import a `Builder`, set a couple of
params, `build_wires()`, solve, print SWR/impedance. The "it's real Python"
moment.

### `/docs/concepts` — The model

- `AntennaBuilder`: `default_params` / variant params, `ui_params`, the knob model
  (`__getattr__`/`__setattr__` over `_params`), `FRAMEWORK_PARAMS`.
- `build_wires()` contract: the edge list
  `((x0,y0,z0),(x1,y1,z1), nsegs, excitation)`.
- House conventions: **angles in degrees**, `_deg` suffix, the display-label /
  tooltip story (why the knob says `slant°` but the param is `slant_deg`).

### `/docs/authoring` — Many ways to express geometry  ⭐ centerpiece

The teaching page that sells the design philosophy. Same delta loop, built every
way, rendering identically:

1. **Coordinates + a formula** (`delta_loop`) — apex-height closed form.
2. **The Drone / 3D turtle** (`delta_loop_drone`) — fly, turn, pay out wire; the
   pen-up/pen-down (`cut`/`pay_out`/`feed`), `yaw`/`pitch`/`roll`, `face`, `close`.
3. **Drone + labelled nodes** (`delta_loop_marked`) — `mark`/`line_to`, trig-free.
4. **Point-finder + reflection + `build_path`** (`delta_loop_reflected`) — Drone
   reads off one corner, `ry` mirrors the rest.
5. **Numeric solve** (`delta_loop_solved`) — `brentq` inverts a build-and-measure
   model from a `length_factor`.

Show the five scripts side by side with the identical rendered geometry under
each. Message: *pick the expression that fits how you think; the framework
doesn't care.* Cross-link `Drone` and `Transform` API.

### `/docs/catalog` — Designs with source

Every design: rendered geometry, the live knobs, and the actual `Builder` source
(these are meant to be **starting points for new designs**, so the source is the
point). Grouped by family (dipoles, Yagis, loops, verticals, bowties, multiband).

### `/docs/solver` — The engine & accuracy

- The MoM core (momwire): triangular / sinusoidal / B-spline bases; H-matrix/ACA +
  GMRES; `ArrayBlock`/`HMatrix` for large arrays.
- **The benchmark** (the 10-design engine comparison already in the repo) →
  accuracy & performance plots. This is the credibility page for skeptics.
- The two-engine cross-validation (momwire vs. PyNEC reference).
- Honest caveats from `NEXT_STEPS.md` (PEC wires — no conductor loss;
  triangular/sinusoidal impedance folds finite ground to the PEC image;
  strict `tl_card` agreement open on near-decoupled geometries).

### `/docs/web`, `/docs/cli`, `/docs/api`, `/contributing`, `/changelog`

Reference + process pages: the web adapter & `_auto_paramspec`/ParamSpec model,
`nec_export` CLI, generated API ref, how to add a design and run the test suite,
release notes.

---

## Build order (suggested)

1. **`.dev/app` live + deep-linkable** — without the live simulator nothing else
   lands. Everything points here.
2. **`.com/` home** wrapping that app in the pitch + CTAs.
3. **`/docs/authoring` (five-ways)** + **`/docs/catalog`** — the highest-leverage
   teaching content, and it's already written in code.
4. **`.com/gallery`** + **`/docs/solver` benchmark** — depth and credibility.
5. **`/why`, `/learn`, quickstart, contributing** — fill in the on-ramps.

## Open questions

- **Hosting the live app:** is `.dev/app` a persistently-running instance, or do we
  ship a WASM/static build so the demo can't cold-start? (Decides whether `.com`
  embeds live or a captured loop.)
- **Docs tooling:** MkDocs Material, Docusaurus, or Astro Starlight? (Astro pairs
  well if we want the marketing `.com` and docs `.dev` to share components.)
- **Domain redirect policy:** does bare `antennaknobs.dev` redirect to `/app`,
  `/docs`, or a thin landing? (I'd send it to `/app`.)
