# Plan: parked umbrella issues

Status: **written 2026-09-14.** This file parks three umbrella issues. Each
section below replaces a closed GitHub issue: what shipped under it, what it
left open, and how to resume. Open items are quoted as the issue wrote them,
with the date of the body or comment they come from.

## The validation story: public cross-engine report, Leeson demo, community problem decks, external anchors

[#896](https://github.com/stevenmburns/antennaknobs/issues/896), opened
2026-08-12.

**What shipped**

- The validation page and its generator, `scripts/build_validation_report.py`
  writing `site/src/content/docs/reference/validation.md`, with the ByDipole1
  case and the honest-limits table (PR #899, phase 0).
- The Leeson demo: Cebik's five tapered 14 MHz dipoles, re-solved on a mesh
  ladder per engine by `scripts/bench_leeson.py` (PR #900, phase 1). The
  2026-08-12 comments record acceptance item 1 as satisfied "modulo 'live'"
  and item 2 as satisfied.
- The first analytic anchor, energy conservation as a report row (PR #913,
  phase 2), and the page's link to the community-deck intake repo (PR #914,
  phase 3).
- The momwire bs2 × NEC-5 corpus census,
  `docs/status/2026-09-11-corpus-census-momwire-nec5.md` (PR #1415),
  re-rendered on corpus tool 1.11 (PR #1467).

**What stays open**

Acceptance boxes not covered by the list above (body, 2026-08-12):

- [ ] Analytic-anchor rows (King-Middleton + directivity norm)
- [ ] Community-deck intake running; every submitted deck gets a published verdict
- [ ] ≥ 1 external/measured anchor in the report
- [ ] ACES writeup draft (go/no-go decision recorded either way)

Partly done: PR #913's row checks the closed-form directivity norm against
energy conservation, and the page still lists King-Middleton values as to come.
The intake repo is linked (PR #914).

The phases those boxes belong to (body, 2026-08-12):

> **Phase 3 — community problem decks.** Ask the groups.io Antenna Research
> thread (and Ward's SimNEC channel) for antennas/decks people distrust or have
> seen solvers disagree on. Intake: NEC-2-dialect wire decks; patch/buried-wire
> models get an honest out-of-scope note. Every submission gets a per-deck
> three-way verdict in the report — the adversarial test set we did not curate
> ourselves. Launch the ask EARLY (replies accumulate over weeks, pipeline into
> the report as they arrive).

> **Phase 4 — external anchors.** At least one comparison against measured data
> or published non-NEC solver results (Cebik measured designs, ACES-published
> benchmarks). This is what graduates the story from self-consistent to
> validated, and the long pole.

> **Phase 5 — publication.** The site validation page as the durable artifact;
> an ACES newsletter/conference writeup of the census methodology ("outliers
> that move between oracles are findings") as the credibility vehicle — it is
> the venue the NEC-5 Validation Manual itself cites. SimNEC positioning rides
> the page: byte-contract dialect fidelity (315 fixtures), resident-daemon
> speed, IS served natively (#873), refusals instead of fabricated readouts.

The publication question from the census plan (comment, 2026-09-11):

> **A conflict for you to settle.** This issue's Phase 0 note records that
> *"NEC-5 captures are committable End-User Reports (LLNL-CODE-746721)"*. The
> standing instruction I am working under is stricter — conclusions and
> aggregates only, no per-deck NEC-5 printouts. **I am planning to the stricter
> rule.** If the End-User Report position holds, the mover cases get materially
> more legible and I would rather be told than assume.

The census doc's "Publication discipline" section still follows the stricter
reading and leaves this open. The same comment's other two pre-build questions
(translated or raw decks; fix the `LD` partial-range translate artifact before
or after the run) are answered in that doc's "Why the translated decks, and
what that costs".

The census's own open questions have issues, so they are linked rather than
copied: [#1417](https://github.com/stevenmburns/antennaknobs/issues/1417)
(455 corpus decks disagree on the sign of the reactance) and
[#1456](https://github.com/stevenmburns/antennaknobs/issues/1456)
(cross-engine comparisons inherit per-engine fed-wire parity).

**How to resume:** file one issue per open box when it is scheduled
(King-Middleton rows, an external anchor, the ACES go/no-go), or reopen #896 to
take the story up whole.

## Redesign the engine-choosing panel around what an engine is MADE OF, not what it is called

[#1006](https://github.com/stevenmburns/antennaknobs/issues/1006), opened
2026-08-27.

**What shipped**

- momwire declares what each solver is made of and which axis values cannot be
  combined (momwire#882, momwire#885); `/capabilities` serves both (PR #1147,
  G2-3; PR #1151, G2-4b).
- The feed-model and degree controls come from the axes, and the design refusal
  re-answers when the design changes (PR #1154, G2-5). The panel is drawn from
  the served schema, and the bespoke panels are deleted (PR #1163, G2-6).
- Each tab states what it is made of (PR #1164, G2-7). The axes-null feed-model
  fallback went once the pin served axes (PR #1172).
- Two follow-ons: a `pulse` tab (PR #1253, for #1148), and momwire's public
  capability and coated-wire names in place of the private reach-through
  (PR #1250, for momwire#884 and momwire#876).

**What stays open**

The made-of view itself. Owner's decision (comment, 2026-09-06):

> Owner's steer (2026-09-06): **deferred**, and when it is picked up the shape
> is an **alternative view rather than a replacement** — a button that switches
> the engine picker between the two input styles, the current by-name tabs and
> a made-of view over the capability axes, both fully usable, for users who
> think about engines in different ways. The two views serve the same roster
> row (the axes are already served since #1006's G2 work); only the
> presentation changes. Related: #1148 (the tab list is not a statement over
> the axes), momwire#884 / #876 (public names for the axes and the coated-wire
> pair).

The body's proposal items that need that view (body, 2026-08-27). Under the
decision above, item 2 is one of two views, not a replacement for the tabs:

> 2. Render the panel as the axes, with the preset names as shortcuts. A user
>    sees *B-spline · degree 2 · Galerkin · reduced kernel · dense* and can tell
>    at a glance what changes when they move one control.

> 4. \[...\] A composition the roster cannot build should grey out with that
>    sentence rather than not appear.

The criterion adopted for the work (comment, 2026-09-04):

> the criterion is now the count of reachable cells in the engine product
> space, and the unreachable-but-wanted cells are the refactor backlog, each
> with its cell as the gate.

On URLs and saved sessions (comment, 2026-09-04):

> What underwrites the same promise is **name → axes resolution stability**,
> gated in G2-4(c) \[...\] If a URL surface ever appears, that gate is the
> precondition for a round trip rather than something to tear out.

**How to resume:** file a new issue for the made-of view, switched by a toggle
against the by-name tabs, when it is scheduled.

## Frequency-dependent ground constants for the ground-mounted class (Messier model), follow-on to #1175

[#1188](https://github.com/stevenmburns/antennaknobs/issues/1188), opened
2026-09-05. No comments.

**What shipped**

Nothing frequency-dependent; the issue was filed as not scheduled. The
single-valued work it builds on:

- Soil constants (ε_r, σ) as knobs with named presets (PR #1174, for #1173).
- The single-valued-soil advisory on the buried class, the #1175 decision this
  issue follows (PR #1196).
- Presets re-checked against the ARRL Antenna Book's Table 3.1 (PR #1290), and
  the default soil set to its "average" row, εr 13 / σ 0.005 (PR #1314).
- Surrogate seeding for the optimizer, which design question 5 names (PR #1198,
  for #1176).

The error table and question 4's ratios below were measured by 2026-09-05,
before PRs #1290 and #1314 changed the presets. Re-measure before using them.

**What stays open**

The whole unit. What was measured (body, 2026-09-05):

> The served presets are single (ε_r, σ) pairs used at every frequency. Real
> soils disperse: in K6STI's GC 1.0 tables (Messier soil model fit to Hagn's
> 2–30 MHz generic curves) pastoral ε_r falls 33 → 15 and agricultural 111 → 42
> from 1.8 to 28.5 MHz, and σ roughly doubles. The effect splits by antenna
> class:
>
> | deck | 1.8 MHz | 7.1 | 14.2 | 28.5 |
> |---|---|---|---|---|
> | `buried_radial_vertical`, average soil, error vs K6STI | 5.9 % | 10.4 % | 17.7 % | 31.9 % |
> | same, poor | 8.5 % | 23.3 % | 21.6 % | 16.0 % |
> | `invvee` (elevated), average | 9.1 % | 2.6 % | 1.3 % | — |
>
> Height above ground in wavelengths is the variable: a ground-mounted screen
> never gets electrically further from the ground, an elevated wire does. And
> **correcting the table alone can regress**: for `poor`, the correct K6STI
> class frozen at its 1.8 MHz row leaves 10 m at 48.8 % against 16.0 % today.

The unit (body, 2026-09-05):

> Frequency-dependent ground constants for the ground-mounted / buried class
> only, from the Messier parameters (σ₀, ε∞ per soil class) rather than a
> table, so any frequency is served without interpolation. Elevated decks keep
> single values (≤ 3 % at the bands where it matters).

Design questions to settle first (body, 2026-09-05):

> Design questions to settle first, each a real change:
>
> 1. **A preset becomes a curve.** #1173's two knobs (ε_r, σ) must then mean
>    "override at this frequency", or the preset and the knobs silently
>    disagree.
> 2. **Sweeps.** A 1.8–30 MHz sweep under one soil is ill-defined; the solve
>    needs per-point constants, which touches the sweep path and its response
>    shape.
> 3. **Export.** The NEC `GN` card carries one soil; a deck exported at 7 MHz
>    and re-run at 28 MHz carries the 7 MHz soil silently. The exported deck
>    should say so in a comment card.
> 4. **Mapping.** Our σ values line up with K6STI's classes at 1.8 MHz
>    (average ↔ Pastoral 1.01×, very good ↔ Agricultural 0.95×, very poor ↔
>    Desert) but our ε_r is 2.5–5.5× low for the wetter classes; `poor` sits
>    between Mountains and Pastoral; fresh/salt water have no K6STI class.
>    Which classes carry a curve and which stay fixed is a decision, not a
>    lookup.
> 5. **The surrogate optimizer** (#1176) fits a surface at one frequency; a
>    frequency-dependent soil must be held fixed across a fit.

Sources (body, 2026-09-05): K6STI HF Ground Constants
(<https://k6sti.neocities.org/hfgc>), the Messier fit page
(<https://k6sti.neocities.org/messier>), and AC6LA's QRZ thread "Ground
Dielectric Constant is not ... Constant" (Aug 2026), which extrapolates the
ARRL 1 MHz ground types the same way in SimNEC/AutoEZ and records that K6STI
moved from the Moision exponential fit to the Messier model.

**How to resume:** reopen #1188 when the unit is scheduled, and settle the five
design questions before any code.
