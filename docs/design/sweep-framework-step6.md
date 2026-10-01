# Sweep framework, step 6: hold (design note)

Status: **built, 2026-10-01**, on `feat/sweep-step6-hold` (AK#1757 step 6).
This page records the decisions step 6 was built to. The spec's "Addendum:
`hold`" and examples E8 and E9 are in `sweep-framework-spec.md`.

## What it does

An `an.Hold(objective, adjust=..., z0=None, warm_start=True)` on an analysis
re-solves the `adjust` knobs at every sweep point, and the analysis's views
are drawn at the optimised point. `an.Knobs()` draws the held knobs against
x.

- **Shared core.** `antennaknobs.hold.hold_line` is the same function in the
  CLI (`analyze`, called per crossed cell) and in the workbench
  (`/param_sweep` with a `hold`).
- **No second optimizer.** Each point is one call of the workbench's
  `web.optimize.optimize`: its secant / bracket for `resonance` on one knob,
  and its two-component Newton for `match_z0` on two.
- **Two switches were added to `optimize`.** Both are off by default, so
  `/optimize` is unchanged:
  - `warm=True`: Newton starts from the previous point's root before the
    seed samples the box. This is the spec's "skipping the optimizer's seed
    after the first point".
  - `fallback=False`: no Nelder-Mead polish after a failed root search.
- **Its own verdict.** `optimize` now reports `converged` and `root_reason`.
- **Crosses.** Each cell is held on its own: its design, state, family step,
  engine and ground, from its own defaults. A state may not set a held knob,
  which was already refused.

## Decisions

1. **A point that does not converge is a gap.**
   - **What counts as a gap:**
     - the optimizer's root search did not converge;
     - its solved residual is over 1 Ω (the tracker's user-facing
       `TRACK_TOL`);
     - a solve the search asked for failed (a candidate the engine refuses).
   - **How a gap is shown, never as a value:**
     - the CLI prints it with its reason, the curve gets a NaN there, and the
       CSV leaves its cells empty;
     - the workbench sends a `gap` record, draws a break in the line with an
       × on the x axis, puts the reason in the hover, and the Table prints a
       "gap" row with the reason.
   - **Recovery.** The next point warm-starts from the last CONVERGED point.
     After 3 failures in a row, each remaining point cold-starts from the
     defaults once:
     - a point that converges resumes the warm chain;
     - a point that fails is given up on.

   A bound is named in the reason ("length_factor at its ui_params max
   0.99"). A root found exactly on a bound is still a root, so it is not a
   gap.
2. **Bounds are the knobs' `ui_params` min/max.** The workbench optimizer's
   knob menu defaults its range to the same values. A held knob without both
   is refused by name.
3. **Cost.**
   - A held chart runs on **Run**, or on a pick. Its dwell switch starts off
     whatever `settings.toml` says, and the per-chart switch from step 5
     still turns it on.
   - It streams one record per point, so the chart shows `k/N` progress.
   - Stop, or a new pick, cancels it. The stream's own token trips on
     disconnect, as `/optimize`'s does.
   - It takes no lane turn, again as `/optimize`. A point is several solves,
     and a turn per point would hold the live solve behind a whole
     optimisation.
   - **Start values.** The held knobs start from the design's defaults
     (its variant's), never their sliders. So dragging a held knob does not
     stale the curve, a kept study reproduces it bit for bit, and the CLI
     (which takes no `--set`) agrees.
4. **Refusals by name** cover:
   - `swr`: a minimisation, with no root to call converged;
   - the square-system count mismatch (already checked);
   - a held knob with no range;
   - a multi-feed design: the root paths are single-feed;
   - a hold on a frequency sweep, a density ladder, or a map.

   A per-point engine refusal is a gap. It refuses the whole cell only when
   every point fails.
5. **Frequency sweeps with hold: refused in v1.** The optimizer itself could
   serve one (`freq` is a request field), but the frequency path does not fit
   a hold:
   - it is one build solved across the band;
   - its range can be the band policy, which the frontend places;
   - its views (SWR bands, refinement) belong to the frequency chart.

   A held line rebuilds and re-solves per point. Density ladders and maps are
   refused for the same reason: they are other code paths.

## Keeping

- **A held chart.** "Keep as study" writes `hold=` from the served spec, so
  the kept study re-runs held.
- **A held curve's pin** carries the hold in its request. A study made from
  pins keeps it, and leaves the held knobs out of the state, since the hold
  moves them. Pins under different holds are refused by name.

## Measured (Haswell, momwire at the submodule pointer)

- **E9 in the CLI, free space:** all 25 points held. Worst |X| is 0.00075 Ω.
  `length_factor` rises monotonically from 0.9704 to 1.0057, using 98
  solves.
- **E8 in the CLI over `finite-fast`:** 36 of 37 held. Worst |Z − 50| is
  0.00094 Ω.
  - The gap is base = 2 m. The first point's cold seed samples the knob box,
    and at a 2 m apex the box includes droops that put wire ends in the
    ground plane, which the reflection-coefficient ground refuses. The point
    is drawn as a gap with the engine's words.
  - Over `finite` (Sommerfeld, contact-capable) all 37 points hold, worst
    0.00091 Ω, in 208 solves and 37 s.
- **The seam.** A recorded held point is bit-equal to `optimize` called
  standalone at that x from the same start, for both E9 and E8. Branches
  reached:
  - E9: 1 cold and 24 warm, all on the secant;
  - E8: 1 seeded Newton (cold) and 35 warm Newton.
- **Forced non-convergence.** With `length_factor` capped at 0.99, E9 gives
  6 gaps from 47.5°. The first three warm-start from the last converged
  point, and the last three cold-start from the defaults and are given up on.
