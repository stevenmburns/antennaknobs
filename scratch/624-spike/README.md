# 624-spike — §5.5's razor contact experiment, and its go/no-go

`momwire/docs/design/contact-over-finite-ground.md` §5.5 said: *"Until that
experiment runs, Stage 3 has no schedule."* It has now run. Harness:
`momwire/scripts/spike_contact_plane_reference.py`; raw output:
`RESULTS-spike.txt`.

Deck: the study's own contact monopole, 5.3535 m, r = 5 mm, 14 MHz,
base-fed, `ground_model="sommerfeld"`, against `nec5cl` on the same geometry.
Bar: difference-of-columns `δ = Z(soil) − Z(PEC)`, which cancels each
formulation's own discretization offset. Printed output only; no engine
internals read. Citation: NEC-5 (LLNL-CODE-746721).

## Verdict: GO — but the scope is not what §5.5 assumed

### 1. PEC bit-identity — PASS

Bit-for-bit at N = 11/21/41/61, term off vs on. Implemented as untouched
arithmetic (at PEC there is no `w_Φ` table and the branch never runs), not as
an added zero.

### 2. The parity gate — PASSES, and it does not need the term

**Every ladder is bounded**, term off and on, on all four grounds. razor at
contact over a finite ground does not diverge: it is on bspline's side of
§2.3(a), exactly as §4.3 predicted from the doublet argument, and not on the
direct-field trunk's (momwire#282).

So **razor can serve, and simply lifting the refusal is enough for parity.**
That is the answer momwire#624's release question turns on, and it is
independent of whether the restored term is right.

### 3. razor with the term OFF is already competitive with bspline

`|δ − δ_binary|` at N = 61:

| soil | razor OFF | bspline d=2 |
|---|---|---|
| sea | **0.005** | 0.201 |
| v.good | 0.405 | **0.116** |
| average | 1.397 | **1.236** |
| poor | 3.384 | **3.309** |

Comparable on the two lossy soils, forty times closer on sea, worse on very
good ground. Lifting the refusal costs no accuracy relative to the row that
already ships.

### 4. §4.3's term at full strength makes it WORSE

| soil (N=61) | OFF | ON (coeff 1.0) |
|---|---|---|
| v.good | 0.405 | 0.491 |
| average | 1.397 | 1.661 |
| poor | 3.384 | 3.906 |

The study flagged §4.3 as *"a reading of the code plus a physical argument,
not a measurement"* and listed *"whether §4.3's diagnosis of razor is right"*
under §8's known-unknowns. The measurement does not confirm it as stated.

### 5. But the term is not wrong-headed — the sign is confirmed and the shape holds

The coefficient sweep separates an implementation sign error from a wrong
hypothesis, which one coefficient cannot:

* **Sign is right.** −1.0 is far worse than +1.0 everywhere (poor N=41: 9.14
  against 4.10).
* **Shape is right.** One coefficient, ≈ **0.4**, is the argmin on *every*
  lossy ground at *every* mesh — v.good 0.404 → 0.223, average 1.392 → 0.939,
  poor 3.375 → 2.058. A term of the wrong shape helps one soil and hurts
  another; a term of the right shape at the wrong scale does exactly this.

**A fitted coefficient is not a derivation and nothing here should be read as
one.** What it establishes is that a term of this structure, entering at
somewhere near 40 % of the computed magnitude, removes about 40 % of a gap
that survived a full stage of investigation on the bspline side.

## What the overshoot points at

§5.5 asked for the row-halving assumption to be measured **separately**. The
result above suggests the two are *coupled*, which §5.5 did not anticipate:
razor's grounded row is the real half of the testing path only, halved by the
self-image invariance `E(M·r) = −M·E(r)` — a **PEC identity** that a weighted
image does not satisfy — and the restored term was added at full strength
into that halved row.

That predicts an overshoot of order 2×. The measured argmin is ≈ 0.4, not
0.5, so halving alone does not account for it.

A second candidate, not yet tested: over the **composing** (Sommerfeld)
ground the fold is `C₂·img + Q`, and the term as implemented reconstructs the
plane potential from the weighted exact-image half only — the remainder `Q`
also has a potential at the plane endpoint and is not in it. That would make
the implemented term an over-estimate of `Φ(plane)` by a soil-dependent
amount.

**Discriminating experiment:** the refl-coef ground is a pure weighted image
with no remainder. If the term's argmin moves to ≈ 1.0 there while it sits at
≈ 0.4 under Sommerfeld, the missing piece is `Q`; if it stays near 0.5 under
both, it is the row halving. (D3 refuses refl-coef at contact on every shipped
solver because the *model* is broken there — hundreds of ohms — so this is a
spike-only diagnostic and cannot be gated against the binary.)

## The discriminator, run — and it kills the term outright

*(`RESULTS-stub-ladder.txt`, harness
`momwire/scripts/spike_contact_stub_ladder.py`. Added after the above.)*

**The discriminator proposed above could not be run as written.** It needed
the licensed binary as the reference under refl-coef, and refl-coef at
contact sits **26 Ω** from it (52.006+21.505j against 26.643+10.767j,
average soil, N=21). That is the model error D3 withdrew refl-coef at contact
for, and it dwarfs the ~3 Ω the term is worth: fitting a 5 Ω knob to close a
26 Ω model gap measures the gap. The reference had to go.

### Half the question needed no experiment

Read from `razor.py`: T2's `M0c` is the reduced-kernel static moments times
`w_Φ` and nothing else. `rem_fn` — the Sommerfeld remainder — is built at
:2558 and used only at :2653/:2661, in the Q FIELD term, after T2 is already
assembled. So the folded scalar potential at the plane is

| ground | Φ(plane) | the term |
|---|---|---|
| refl-coef | `(1 − w_Φ)·M0(plane)` | complete, by construction |
| sommerfeld | `(1 − w_Φ)·M0(plane) + Φ_Q(plane)` | missing the remainder |

by construction, not by measurement. But that predicts a **soil-dependent**
deficit, and the measured argmin did not vary with soil — ≈0.4 on very good,
average and poor alike. A single coefficient across grounds with very
different remainders looks like a model-independent factor, not the
remainder's.

### The instrument that does work: the stubbed ladder

Momwire against momwire, no binary: the same antenna with its contacting
element replaced by a vanishing grounded stub, over a 100× range of stub
heights. Two corrections from the stage-2 record are built in — the feed goes
on the **radiator**, not the stub's base, and the mesh above the stub is held
**fixed** (spelling the radiator on a fixed segment COUNT re-meshes the whole
antenna every rung and drifts the PEC control 2.5 Ω, which is a mesh artefact
with no contact node in it).

**PEC control: flat to 2.15e-3 Ω** across the ladder, certifying the harness
before any finite-ground row is read.

Ladder spread, worst rung against the smallest stub:

| ground | coeff 0.0 | 0.25 | 0.40 | 0.50 | 0.75 | 1.00 |
|---|---|---|---|---|---|---|
| average, refl-coef | **0.285** | 5.58 | 9.20 | 11.63 | 17.16 | 5.67 |
| average, sommerfeld | **0.551** | 2.63 | 3.80 | 4.55 | 5.83 | 2.43 |
| poor, refl-coef | **0.410** | 7.56 | 12.68 | 16.23 | 24.91 | 8.21 |
| poor, sommerfeld | **0.209** | 5.20 | 8.26 | 10.27 | 14.75 | 5.23 |

**Coefficient 0 is flattest on every row.** The term at any nonzero
coefficient makes razor's contact node LESS self-consistent, and by an order
of magnitude. At coefficient 0.4 the ladder slides 42.18+25.82j → 33.58+16.50j
as the stub shrinks — converging back onto the coefficient-0 answer, i.e. the
term's whole contribution evaporates with the contacting element.

### What that settles, and what it does not

**Settled: §4.3's term is not the missing physics.** Not mis-scaled — *no*
scale makes it self-consistent. The accuracy sweep's ≈0.4 preference was a fit
at one fixed mesh that does not survive an instrument needing no reference,
which is exactly why the study insists on such instruments.

**Also settled: the deficit is not the remainder Q.** refl-coef (no remainder)
and sommerfeld behave the same, both preferring 0.

**Not settled, and the honest limit of this:** it tests §4.3's term *as
implemented here* — `(1 − w_Φ)·M0(plane)` reconstructed from the T2 moment
table. A structurally different reading of §4.3 is not excluded by it.

### The finding worth keeping

At coefficient 0 the finite-ground ladders spread **0.21–0.55 Ω** where PEC
holds **0.002 Ω** — two orders worse. So razor's contact node IS internally
inconsistent over a finite ground; it just is not §4.3's term.

That is a **new instrument with a target**: a self-consistency residual, no
binary required, that a correct contact-node fix must drive toward the PEC
control's 1e-3. Stage 3 gets a gate it did not have.

## What this changes about Stage 3

Stage 3 was scoped as "restore the term". The term is now measured and does
not survive. Rescope to **"find what makes the grounded row inconsistent over
a finite ground, gated on the stubbed ladder"** — with §4.3 recorded as
tested and rejected, and the row-halving still untested and now the leading
suspect, since it is exactly the kind of model-independent factor the
soil-independent behaviour points at.

Parity does not have to wait for any of it. §2 stands on its own: razor
serves, bounded, at bspline's accuracy, today, with the term off.
