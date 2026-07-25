# Singular-enrichment probe over the #521 junction-residue cluster (issue #565)

**Date:** 2026-07-25
**Tool:** `scripts/bench_enrichment_probe.py` (ladder N = 21/41/81/161,
free space + PEC + Sommerfeld, `enrichment_variant=raw`, seg-cap 6000,
RLIMIT 8 GB). Runs on an **editable momwire install** (momwire `main`,
0.16.0, issue #167 complete) — no release/pin bump, by the #565 decision.
Finite-ground medium: NEC "average" (εr 13, σ 0.005 S/m), lowest wire
placed 0.1 λ above the plane.

## Question

momwire #167 unblocked the K≥3 singular-enrichment bases over *every* ground
(PRs #169 PEC / #170 refl-coef / #171 Sommerfeld), so #521's grounded
junction cluster — **hentenna, hentenna_array, hentenna_slant, hourglass,
hourglass_slant, hourglass_array, discone** — can finally be probed with the
correction that targets exactly its suspected defect. #521 named
junction-collocation as the prime suspect for the cluster's sin↔bs2
**reactance** disagreement but called it "not yet demonstrated." Singular
enrichment is the direct test: it is a Galerkin correction at the K≥3
junctions, and on the *bare-momwire* hentenna it flips R/X convergence from
O(1/N) to ~O(1/N³) (`test_bspline_d2_hentenna_singular_enrichment`).

The discriminator (#565): does enrichment collapse the sin↔bs2 reactance gap
toward the Galerkin value, the way it does on that free-space hentenna?

## Method — three bases up a ladder, gap before/after

Per design the driving-point reactance (feed 0) is solved up the ladder on
**sin**, **bs2** (BSpline d=2, Galerkin), and **bs2+enrichment**. The report
scores, at the finest common rung:

- **gapB** = |X_sin − X_bs2| — the #521 disagreement *before* enrichment;
- **gapA** = |X_sin − X_bs2enr| — *after*. gapA ≪ gapB would mean enrichment
  moved the Galerkin basis toward sin (junction collocation corrupts bs2 too);
- **enr↦** = |X_bs2enr − X_bs2| — how far the K≥3 correction moved the
  Galerkin driving-point reactance at all;
- **stepSin / stepBs2** = |ΔX| across the last mesh doubling — who is still
  moving, with no asymptotic assumption.

### Two confounds respected (#565 step 4)

1. **`enrichment_variant="auto"` suppresses enrichment** on several of these
   catalog designs — the auto tap-ratio gate decides the junction is already
   resolved and returns the plain-bs2 matrix *bit-for-bit*. A naive `auto`
   probe would report "no effect" everywhere for the wrong reason. The probe
   defaults to **`raw`** (enrichment always on at K≥3); `raw` is verified
   distinct from bs2 (hentenna N=21: X 38.590 → 38.703), so a null result here
   means "enrichment did nothing", never "auto turned it off".
2. **Feed placement gates the correction's reach.** The catalog hentenna feeds
   *mid-wire*, electrically removed from its two K=3 rails, so `raw` moves X by
   ~0.1 Ω at N=21 — versus ~5.6 Ω in the bare-momwire test whose feed stub
   attaches *at* the junction. Same basis correction, 50× smaller footprint on
   the driving point, purely from where the feed sits. Real geometry, not a bug.

## Result — the gap persists; enrichment is a driving-point no-op

Free space (PEC and Sommerfeld are identical to within ground's own shift —
see below):

| design | Nf | X_sin | X_bs2 | gapB | gapA | enr↦ | stepSin | stepBs2 |
|---|---|---|---|---|---|---|---|---|
| hentenna         | 161 |  30.57 |  38.89 |  8.32 |  8.32 | 0.001 | 0.93 | 0.049 |
| hentenna_array   | 161 |  30.40 |  41.26 | 10.86 | 10.87 | 0.003 | 1.07 | 0.010 |
| hentenna_slant   | 161 |  24.78 |  24.83 |  0.05 |  0.05 | 0.001 | 0.26 | 0.094 |
| hourglass        | 161 |  23.39 |  28.81 |  5.41 |  5.41 | 0.001 | 0.41 | 0.032 |
| hourglass_slant  | 161 |  24.85 |  34.50 |  9.65 |  9.65 | 0.001 | 0.80 | 0.075 |
| hourglass_array  | 161 |  16.22 |  25.80 |  9.58 |  9.59 | 0.003 | 0.82 | 0.017 |
| discone          | 161 | −26.32 | −31.02 |  4.70 |  4.70 | 0.000 | 2.63 | 0.045 |

Three findings, uniform across the cluster and identical in shape on PEC and
Sommerfeld ground:

1. **Enrichment does not collapse the gap.** gapA = gapB to two decimals
   everywhere; enr↦ ≤ 0.003 Ω on X and 0.000 Ω on R (checked separately). The
   K≥3 junction correction moves the driving-point impedance by essentially
   nothing — on *every* ground.
2. **bs2 is already settled; sin is the laggard.** stepBs2 = 0.01–0.09 Ω
   (Galerkin flat by N=81), while stepSin = 0.4–2.6 Ω — sin is still climbing
   ~1 Ω per mesh doubling at N=161. The "no mutual limit" #521 flagged is
   *sin's slow reactance convergence against an already-converged Galerkin
   value*, not a collocation defect in the Galerkin basis.
3. **Ground doesn't change the mechanism.** #167's ground-capable enrichment
   path is reachable and consistent (step 1 confirmed: no `NotImplementedError`
   on PEC / refl-coef / Sommerfeld), but the gap and the enrichment no-op are
   the same over ground as in free space — ground shifts every basis's X by a
   few Ω together and leaves the sin↔bs2 split untouched.

### sin is genuinely non-asymptotic (why extrapolation is refused)

A longer free-space ladder on the hentenna shows sin's per-doubling steps
**growing**, not shrinking — it is not in an asymptotic regime, so any
three-point fit of *where sin lands* is a mirage the true sequence blows
through. bs2 is flat from N=81:

| N | sin X | bs2 X |
|---|---|---|
|  21 | 29.23 | 38.59 |
|  41 | 28.35 | 38.79 |
|  81 | 29.64 | 38.84 |
| 161 | 30.57 | 38.89 |
| 321 | 31.43 | 38.91 |
| 641 | 32.63 | 38.92 |

The tool's Aitken column is guarded to refuse non-contracting series for
exactly this reason; it extrapolates only the (genuinely convergent) enriched
Galerkin basis.

### Outlier: hentenna_slant is not in the cluster

hentenna_slant shows gapB ≈ 0.05–0.13 Ω — sin and bs2 **agree**. Its geometry
puts both bases on the same limit; it should not be counted among the
no-mutual-limit residue. discone is the opposite extreme: sin wildly
unconverged (stepSin ~2.6–2.9 Ω) and capacitive (X ≈ −30 Ω), the largest
laggard, with the largest R gap (2.5–3.2 Ω) as well.

## Verdict — #565 outcome 2: the gap persists → different class

This is the issue's second outcome: **the X-dominated cluster is a different
class from #484's R-dominated fan-feed drift, and singular enrichment is the
wrong remedy for it.** The junction-collocation mechanism, *as probed by
singular enrichment at the driving point*, is not demonstrated for this
cluster — because the Galerkin basis already resolves the junctions well
enough that the correction has nowhere to act, and the catalog feeds sit too
far from the junctions for a junction correction to reach the port anyway.

What actually drives the cluster's sin↔bs2 reactance gap is the **sinusoidal
basis's slow reactance convergence**; bs2 already holds the trustworthy limit
from a coarse mesh. That reframes #521's remedy hunt:

- Don't pursue singular enrichment as the fix for this cluster's gap — it is a
  no-op at the driving point on every ground.
- Treat bs2 as the reference limit for these designs (it is flat by N=81); the
  open work is characterising *why sin converges so slowly* here, not
  correcting bs2.
- A residual caveat: a driving-point no-op does not prove the junction basis is
  perfect in the *current/field* solution — only that the reactance *seen at
  the feed* is insensitive to the correction, for these feed placements. A
  probe closer to a junction feed (or on the current distribution near the
  junction) would test the mechanism where it could still bite.

## Reproduce

```
python scripts/bench_enrichment_probe.py --ladder 21 41 81 161 \
    --grounds free pec sommerfeld --out probe.jsonl
python scripts/bench_enrichment_probe.py --only specialty.hentenna \
    --variant auto      # demonstrates auto suppressing enrichment (enr↦ = 0)
```

Related: #521 (the cluster), #484 (closed — the R-dominated fan-feed drift
this cluster is *not*), #478 (near-open convergence class), momwire #167
(the ground-capable enrichment this consumes).
