# ΔΓ re-cut of the three density records

Registered 2026-09-16 **before any re-cut was computed**. **No re-solving**: every
cell of all three records stores Z per port, so this is arithmetic on
`records.jsonl`, not a new measurement.

Branched from `scratch/1552-bspline-tail` because **AK PR #1551 is still open**;
it rebases onto main when #1551 and #1552's record land.

## Why

`docs/status/2026-07-16-nec2c-corpus-benchmark.md` scores engines by
**ΔΓ = |Γ_eng − Γ_ref|**, `Γ = (Z − Z₀)/(Z + Z₀)`, `Z₀ = 50 Ω`. For a passive
antenna `R ≥ 0`, so `Z + Z₀` has real part ≥ 50 and **Γ is never singular**;
`|Γ| ≤ 1` makes ΔΓ bounded on **[0, 2]**. The July note adopted it precisely
because relative-Z errors near a cancellation "read as 100s of % but were
artifacts", and Γ is the quantity SWR and match actually depend on.

The AK#1525 ladder used `|ΔZ|` over all ports relative to `|Z_ref|` and both of
today's runs inherited it. **My own AK#1552 finding is that metric's artefact
showing through**: `short_dipole_loaded`'s 240 % is a ~1.3 Ω wander in X on a
`13 + j13` residual, and `zepp`'s 31 % is a fixed feed-mesh offset on a
transformed high impedance. Neither is 240 % or 31 % of anything a user
experiences.

Relative-Z columns are **kept beside** the new ones. Nothing is deleted.

## Method

* Per cell, per port: `Γ = (Z − 50)/(Z + 50)`; `ΔΓ` against the same reference the
  record already uses.
* **Multi-port rows report both**: the max over ports *and* the vector norm, so
  the new column is comparable with the old `|ΔZ|` norm. Every table says which.
* The admissibility rule is re-stated **on ΔΓ**: bs2's own ×80→×160 move in Γ
  under a third of the ΔΓ being judged.
* Fitted order and class split recomputed on ΔΓ for the #1525 ladder.

## Predictions — one line per record

* **J1 — AK#1525 ladder: the class split moves, and specifically the unresolved
  count FALLS.** Rows tripped the one-third rule partly because their relative-Z
  error was inflated by a small denominator; ΔΓ has no such denominator. Bar:
  *reference unsettled* drops below **25** (from 30) and *converging* rises above
  **155**.
* **J2 — AK#1543 served rungs: the ranking does NOT change.** On relative Z the
  medians are d=2@15 0.964 %, d=3@12 1.11 %, d=1@20 1.53 %. Bar: the same
  ordering — d=2, then d=3, then d=1 — on median ΔΓ.
* **J3 — AK#1552 tail: all three verdicts stand, and both conditioning rows
  collapse.** The verdicts are about *why*, not how big. Bar:
  `short_dipole_loaded`'s worst tail row and `wire.zepp`'s both come in at
  **ΔΓ ≤ 0.05**, while `continuous_helix` — the one genuine density row — stays
  the largest of the three at its served rung.

If J3's collapse does **not** happen, the relative-Z figures were not a
conditioning artefact after all and my AK#1552 reading was wrong; that is the
result this re-cut is most able to falsify.

## Deliverable

One dated **"ΔΓ re-cut"** section appended to each of the three studies'
`hypotheses.md`, so each README regenerates with it in place; plus **the one
number per degree on ΔΓ that `density.py`'s docstring should cite**. Nothing is
posted to any issue.
