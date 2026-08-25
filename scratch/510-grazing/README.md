# momwire#510 experiment 1 — the grazing-height floor, measured

2026-08-25. Probe: `momwire/scripts/probe_grazing_height_floor.py` (banked in
its own docstring too). Raw output in `RESULTS-height.txt` /
`RESULTS-segments.txt`, machine-readable in the two `.json`.

## The question

Captures 0033/0034 sit 1.778 cm over `GN 0` average soil at 1.832 MHz —
**h/λ = 1.09e-4** — and every basis answers 176–437 % away from the capture
with the reactance sign flipped, *served silently*. "Wrong at 1.09e-4 λ" is
not actionable. A refusal needs a threshold, a documented limit needs a
number, and a bug needs a signature. All three want the error as a function
of height.

## The instrument

0033 lifted **rigidly** — vertical length, radial length, radius, mesh and the
capture's own `EX 0,1,-1` drive card all bit-identical rung to rung, only the
structure's z translated — compared at every rung against the licensed binary
running the same deck text. Z is genuinely height dependent here, which is why
the reference is the binary at each rung and not the ladder's own flatness.

Two controls, both load-bearing: **`GN 1` perfect ground** at every rung (a
perfect image has no Sommerfeld integral in it), and **both shipped trunks**
(`bspline` degree 2, `razor-nec5`), because #593 ships two executables under a
"both serve or don't serve" ruling.

## Result 1 — the floor is between 1e-2 and 1e-3 λ, and it is in the ground

Error against the binary, per cent of |Z|:

| h/λ | 1e-1 | 3e-2 | 2e-2 | 1e-2 | 7e-3 | 5e-3 | 3e-3 | 2e-3 | 1e-3 | 5e-4 | 2e-4 | 1.09e-4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| razor-nec5, `GN 0` | 0.01 | 0.00 | 0.00 | 0.06 | 0.25 | 0.87 | 3.91 | 10.31 | 44.18 | 230.91 | 239.54 | 171.86 |
| razor-nec5, `GN 1` | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.01 | 0.00 |
| bspline, `GN 0` | 4.68 | 5.06 | 5.30 | 5.92 | 6.40 | 7.14 | 9.72 | 14.84 | 45.66 | 37.23 | 167.08 | 435.18 |
| bspline, `GN 1` | 4.72 | 5.17 | 5.39 | 5.86 | — | — | 6.87 | — | 8.23 | 10.13 | 15.78 | 24.17 |

**Over a perfect image razor-nec5 holds 0.00 % at every rung down to
1.09e-4 λ.** Same mesh, same five-wire junction of near-horizontal wires, same
drive card, same seam. Only the ground card changes. So the grazing failure is
**not** the mesh, **not** the junction, **not** the drive spelling and **not**
this seam's addressing — which is most of experiment 2 answered by a control
that is stronger than the single-wire version would have been, because it
holds the junction fixed instead of removing it.

Both trunks leave their own baseline at the same place — razor's baseline is
0.00 %, bspline's is the ~5 % basis difference it carries at *every* height,
over PEC too — so **one threshold serves both** and the parity ruling is
satisfiable:

> clean ≥ 1e-2 λ · ~1 % at 5e-3 · ~10 % at 2e-3 · broken ≤ 1e-3

bspline over PEC is its own smaller story: 4.7 % at 1e-1 λ rising to 24 % at
1.09e-4, and that one *does* converge out under refinement (24.23 → 1.75 % at
N=41). Ordinary basis convergence, not the finding.

## Result 2 — the controlling variable is h/λ, not h/Δ

Native height, mesh refined 5 → 41 segments a wire:

| N | 5 | 9 | 15 | 25 | 41 |
|---|---|---|---|---|---|
| h/Δ | 0.0022 | 0.0040 | 0.0067 | 0.0112 | 0.0184 |
| nec5cl | 38.79−49.58j | 40.69−42.16j | 41.30−39.80j | 41.54−38.81j | 41.63−38.36j |
| razor-nec5 err% | 175.88 | 158.64 | 358.73 | 703.13 | 276.32 |
| bspline err% | 437.23 | 189.29 | 47.42 | 68.22 | 217.04 |

The binary converges monotonically. Both trunks **diverge, and erratically**.
N=41 puts h/Δ at 0.0184 — the same h/Δ the height sweep reaches at h/λ = 1e-3,
where razor is 44 % out — yet here it is 276 %. Refining the mesh does not buy
the answer back; it costs more of it.

## Reading

This is a **breakdown signature, not a model gap**. A bounded formulation
error is monotone in the mesh and keeps its sign; this is neither — razor
walks −50j → +113j → −231j → +34j across four adjacent rungs, and the error
grows with the number of unknowns landing in the grazing regime. That is
conditioning, not approximation.

Which settles the standards question the handoff posed: **#510 is D3's
category, not D1's** — refuse, don't pin. And the threshold to refuse at is
now a measured number rather than a guess.

---

# Experiment 3 — is this #624's contact node? No.

Probe: `momwire/scripts/probe_grazing_orientation.py`. Raw output in
`RESULTS-tilt.txt` / `RESULTS-lone.txt`.

## The overlap is real, the identity is not

#624's stub ladder sweeps stub heights 0.1, 0.03, 0.01, 0.003, 0.001 m at
14 MHz (λ = 21.414 m), so its rungs sit at h/λ = 4.67e-3, 1.40e-3, 4.67e-4,
1.40e-4, 4.67e-5 — **the whole #624 ladder lives inside #510's broken zone.**
Yet #624 measured a contact node that is *bounded* there (0.21–0.55 Ω of
ladder spread, razor at bspline's accuracy on all four grounds) while #510 at
the same h/λ is hundreds of ohms out with the reactance sign flipped. Same
regime, two magnitudes apart. So something other than height separates them.

## The discriminator: orientation, not the feedpoint

**`--mode tilt`** — the feed junction pinned at 0033's own 1.778 cm
(1.09e-4 λ) the whole way, radials hinged up about it, radial *length* held at
39.624 m so the antenna keeps its electrical size:

| radial far end | 0.018 m | 0.05 | 0.164 | 0.5 | 1.64 | 5 | 16.4 |
|---|---|---|---|---|---|---|---|
| (/λ) | 1.1e-4 | 3.1e-4 | 1e-3 | 3.1e-3 | 1e-2 | 3.1e-2 | 1e-1 |
| razor-nec5 `GN 0` err% | 175.88 | 229.66 | 413.70 | 60.67 | 10.04 | 1.04 | **0.01** |
| razor-nec5 `GN 1` err% | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| bspline `GN 0` err% | 437.23 | 208.03 | 72.24 | 26.16 | 11.04 | 6.20 | 3.00 |

**`--mode lone`** — the vertical alone, no radials, no junction, bottom
segment grazing, base swept:

| base h/λ | 1.09e-4 | 5e-4 | 1e-3 | 3e-3 | 1e-2 | 3e-2 | 1e-1 |
|---|---|---|---|---|---|---|---|
| razor-nec5 `GN 0` err% | **0.00** | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.00 |
| bspline `GN 0` err% | 6.42 | 6.24 | 6.05 | 5.61 | 5.13 | 4.92 | 4.86 |

The grazing **feedpoint is innocent**: it never leaves 1.09e-4 λ across the
tilt sweep, and razor still lands at 0.01 % once the radials climb away. A
lone vertical whose bottom segment grazes the plane is exact at every height.
What breaks is the **horizontal wire lying in the grazing zone** — precisely
what #624's vertical stub does not have.

**#510 and #624 do not collapse into one investigation.** The plan's
hypothesis is refuted, which is worth as much as confirming it would have
been: it stops the two being conflated and it says where to look.

*(One confound, named: tilting the radials also changes the physics — the
binary's Z walks 38.79−49.58j → 7.16−142.2j across the sweep. The lone-vertical
control is what removes it, by holding a grazing node with no horizontal wire
and finding it exact.)*

## Mechanism: catastrophic cancellation in the *numerical* ground

A horizontal wire's image current is antiparallel, so as h → 0 every coupling
through the plane becomes the small difference of two nearly equal large
quantities. Over `GN 1` that difference is a closed-form image and razor holds
0.00 % at 1.09e-4 λ **with the radials flat** — the same cancellation, exactly
computed. Over `GN 0` the image is an integral evaluated numerically, its
absolute error does not shrink with h, and the relative error in the
difference blows up.

That predicts everything experiment 1 saw: error growing as refinement puts
more unknowns in the regime, sign non-monotone rung to rung, and a hard onset
where the cancellation gets deep enough to eat the integrator's accuracy.

## What this changes

The outlook. A formulation limit would be refuse-only; **an accuracy floor in
the Sommerfeld evaluation near the interface is a fixable target.** And the
refusal predicate, if it is still wanted, cannot be bare height — a lone
vertical at 1.09e-4 λ is exact and a height-keyed refusal would refuse it.
It needs an orientation/extent term.

---

# Which part of the finite-ground path? Not the evaluation — the scaling.

Probe: `momwire/scripts/probe_grazing_ground_path.py`, three modes. Raw output
in `RESULTS-theta.txt` / `RESULTS-direct.txt` / `RESULTS-reflcoef.txt`.

## A clean-looking hypothesis, measured and killed

The grid's own layout comment names the premise 0033 breaks:

> *The grazing band (region 0) keeps the 0.01-lambda spacing: there the layer
> variable h = R1 sin(theta) stretches it out in R1, **no physical deck queries
> small R1 at grazing (two points at grazing-small R1 means both are ON the
> plane — radial screens, which are refused)***

0033 **is** an elevated radial screen and it is **not** refused. And the
mechanism behind the premise fails for it: h = R₁·sinθ "stretches out in R₁"
for a general pair, but for two points both at a fixed grazing height it is
pinned at z_s + z_o however large R₁ grows.

`--mode theta` confirms the geometry exactly:

| h/λ | 1.09e-4 | 1e-3 | 3e-3 | 1e-2 | 3e-2 | 1e-1 |
|---|---|---|---|---|---|---|
| median queried θ | 0.115° | 1.058° | 3.171° | 10.46° | 23.66° | 54° |
| pairs in first θ cell | 64.6 % | 64.6 % | 64.6 % | 43.1 % | 0 % | 0 % |
| razor-nec5 err% | 171.86 | 44.18 | 3.91 | 0.06 | 0.00 | 0.01 |

The grazing band's θ cell is **10°** and at the native height the median query
sits at **0.115°** — 87× inside the first cell — with the error tracking how
deep into that cell the queries fall. A textbook interpolation-resolution
story.

**And it is wrong.** `--mode direct` removes the lattice entirely and
evaluates the surfaces directly at rtol 1e-11:

| h/λ | grid err% | direct err% | |
|---|---|---|---|
| 1.09e-4 | 435.18 | 435.23 | bspline |
| 1.09e-4 | 171.86 | 172.08 | razor-nec5 |
| 1e-3 | 44.18 | 44.19 | razor-nec5 |
| 3e-3 | 3.91 | 3.91 | razor-nec5 |
| 1e-2 | 0.06 | 0.06 | razor-nec5 |

Identical to three figures. **The interpolation lattice is exonerated, and so
is the integration tolerance** — direct evaluation *is* the grid's own fill
function, swept two decades past production. The surfaces are evidently smooth
enough in θ near zero that a cubic across 10° carries them.

## Where it actually is

`--mode reflcoef` forces the seam's ground kwargs to refl-coef with the deck,
drive, mesh and route all held. refl-coef **does not track** sommerfeld here —
which is where this parts company with #624's contact finding — and the gap
grows exactly as the error does (razor-nec5, |Z_somm − Z_refl|): 10.0 Ω at
1e-2 λ, 22.9 at 3e-3, 71.9 at 1e-3, **176.3 at 1.09e-4**. The two differ only
by the remainder Q, so that gap *is* Q's contribution.

The sharpest form — the **ground correction**, Z(`GN 0`) − Z(`GN 1`), which is
what the finite ground is worth on top of a perfect image. razor over `GN 1`
reproduces the binary to 0.00 % at every height, so the binary's PEC answer is
a baseline both sides share exactly:

| h/λ | true (binary) | momwire (razor) | overshoot |
|---|---|---|---|
| 1e-2 | 1.577 + 0.670j | 1.582 + 0.739j | **1.02×** |
| 3e-3 | 3.084 + 8.700j | 3.391 + 13.009j | **1.46×** |
| 1e-3 | 4.473 + 20.397j | 9.065 + 63.307j | **3.06×** |
| 1.09e-4 | 13.900 + 61.346j | 82.971 + 144.743j | **2.65×** |

**momwire over-computes the finite-ground correction by up to ~3× at grazing,
and is exact at 1e-2 λ.** Backing refl-coef's undershoot out, Q is worth 176 Ω
at the native height where it should be worth 71 Ω.

So the defect is in **how Q is scaled or folded into the system, not in
computing it**: its evaluation is verified correct by `--mode direct`, and its
contribution is 2.5× too large regardless. That is a bounded, well-localized
target rather than a formulation dead end.

It also rhymes with #624's row-halving suspicion — a model-independent scale
factor on a near-plane row — without contradicting experiment 3. Different
geometric trigger, different symptom, possibly one defect family.

*(bspline's overshoot column is not readable the same way: its own ~5 % basis
error rides on a correction that is only 1.7 Ω at 1e-2 λ, which is what makes
that row 4.77×. razor's is the clean column, and it is clean precisely because
razor over PEC is exact.)*

---

# The soil sweep — row-halving is out, the lossless dielectric is in

`--mode soil`. Raw output in `RESULTS-soil.txt`. razor-nec5 only: bspline's
~5 % basis error rides on the same correction and contaminates the ratio,
while razor is exact over `GN 1` at every height, which is what makes the PEC
baseline genuinely shared.

The **complex** ratio Δ_momwire / Δ_true is what is read, not its magnitude. A
model-independent scale factor is *real* and *constant in soil*; a
mis-weighted physics term tracks ε̃ and wanders in phase.

|Δ_mw/Δ_true| across the five golden half-spaces:

| h/λ | sea | vgood | avg | poor | diel | arg spread |
|---|---|---|---|---|---|---|
| 1e-2 | 1.066 | 1.025 | 1.019 | 0.978 | 0.997 | 0.0 … 2.0° |
| 3e-3 | 2.048 | 1.482 | 1.456 | 1.661 | 0.889 | −8.8 … 7.8° |
| 1e-3 | 5.455 | 3.183 | 3.063 | 3.261 | 1.946 | −77.7 … 12.3° |
| 1.09e-4 | 4.436 | 3.033 | 2.652 | 3.232 | **61.188** | −45.8 … 1.9° |

**The control first:** at 1e-2 λ the correction is right on all five
half-spaces (0.98–1.07, phase ≤ 2°). The floor is a property of **height**,
not of any one soil.

**Row-halving is ruled out.** Below the floor the overshoot is
soil-*dependent* — 2.65× to 4.44× across the four conducting soils at the
native height, phase wandering −16° to −57°. No single real constant describes
that, so the model-independent-scale-factor lead inherited by analogy from
#624 does not carry. It was worth testing and it is dead.

**What replaces it: the lossless dielectric is catastrophic.** 61× at the
native height against 2.6–4.4× for soils that conduct. It is also the one
half-space whose *true* correction has a negative real part (−5.288 + 7.670j —
a lossless dielectric lowers the resistance relative to a perfect image).
momwire answers 110.7 + 559.2j to that.

That is momwire#282 stage 2's signature seen from the other side: its
half-space sweep found the contact discrepancy **peaking over a lossless
dielectric** (4.36 Ω at ε_r ≈ 2.5) and falling monotonically as the ground
became conductive — the measurement that killed "the missing resistance is a
loss term". Same qualitative shape here, two decades larger.

*Suggestive, not proven:* the two were measured on different geometries at
different heights, and nothing here has walked the σ axis.

---

# The orthogonal axes — two defects, not one

`--mode sigma` / `--mode epsr`. The five golden soils confound σ with ε_r
(`diel` is the least conductive *and* the least dense; `sea` is both the most),
so neither can be read off them. These are #282 stage 2's own two sweeps,
asked at grazing. Absolute error in the ground correction, |Δ_mw − Δ_true| in
Ω, razor-nec5 at the native height:

| σ | 0 | 1e-6 | 1e-5 | 1e-4 | 3e-4 | 1e-3 | 3e-3 | 1e-2 | 1e-1 |
|---|---|---|---|---|---|---|---|---|---|
| ε_r = 5 | 300.2 | 300.3 | 300.7 | 279.8 | 205.8 | 136.3 | 120.4 | 117.1 | 116.3 |
| ε_r = 20 | 26.6 | 26.6 | 26.9 | 29.3 | 35.0 | 54.1 | 86.7 | 111.2 | 116.2 |

| ε_r | 1.05 | 1.5 | 2.5 | 3.0 | 3.10 | 3.6 | 5 | 13 | 20 | 81 |
|---|---|---|---|---|---|---|---|---|---|---|
| \|err\| | 18.95 | 96.71 | 563.58 | 2480.3 | **3343.9** | 939.6 | 300.7 | 63.92 | 26.85 | 67.53 |

**There are two separate things here, and the controls separate them.**

### One: a shared, soil-independent, *additive* grazing defect

Both σ sweeps converge on the **same ~116 Ω plateau** once the ground conducts
(tan δ ≳ 5) — from opposite directions. Across the four lossy golden soils the
*absolute* error is 82–136 Ω while the true correction varies 23–63 Ω.

So it is an **additive** error that barely depends on the half-space, not a
multiplicative one. That is sharper than the soil mode's ratio column supports
on its own (the ratio varied mostly because Δ_true varied), and it is a second
and better reason row-halving is the wrong suspect: **a mis-scaled row would
give error ∝ Δ_true, and this does not.**

At 1.832 MHz every real soil is lossy (tan δ 2–600), so every real deck sits on
this plateau. This is #510 proper.

### Two: a razor-specific pole in ε_r at ≈ 3.1

Resolved finely at the native height, and it is a pole, not a bump:

| ε_r | 2.60 | 2.80 | 2.90 | 3.00 | 3.05 | **3.10** | 3.20 | 3.40 | 3.60 |
|---|---|---|---|---|---|---|---|---|---|
| razor \|err\| | 695.7 | 1171.9 | 1650.9 | 2480.3 | 3002.4 | **3343.9** | 2797.1 | 1442.3 | 939.6 |
| arg | −44.1° | −46.5° | −53.2° | −69.3° | −84.1° | −104.1° | −142.2° | −170.5° | −177.6° |
| bspline \|err\| | 99.3 | 109.6 | 114.3 | 118.7 | 120.7 | 122.8 | 126.7 | 133.8 | 140.3 |

A magnitude peak with a **~135° phase sweep** through it, **in razor alone** —
bspline walks smoothly 99 → 140 Ω across the same window with no feature at
all. That reads as a **spurious pole in razor's assembly**.

And `--mode direct --eps-r 3.0` confirms it is not the Sommerfeld evaluation:
grid 2466.91 % against direct 2470.40 %. **The one-soil exoneration survives
its worst corner.**

ε_r ≈ 3 is outside real ground (5–81), so no captured deck meets this pole. It
is a diagnostic pointer, not a user symptom — but it is the sharpest handle in
the whole arc on where razor's ground assembly goes wrong.

### Correcting an earlier reading in this same record

The soil-sweep section above proposed that the lossless-dielectric behaviour
resembled #282 stage 2's σ story ("a loss term must vanish with σ"). **It does
not.** ε_r = 5 sits on the resonance's shoulder, and what σ damps there is the
pole. Clear of it at ε_r = 20 the trend *reverses* (26.6 → 116 Ω). The
resemblance was an artifact of holding ε_r at 5, and the orthogonal sweep is
what caught it.

---

# The pole moves, conditioning is innocent, one wire reproduces it

## The pole is not a coefficient singularity — it moves with geometry

`--radial-lens`. |err| in Ω at the native height, razor-nec5:

| ε_r | 1.8 | 2.2 | 2.6 | 3.0 | 3.4 | 4.0 | 5.0 | 6.5 | 8.0 |
|---|---|---|---|---|---|---|---|---|---|
| L = 20 m | 21.5 | 29.4 | 36.1 | 41.9 | 46.9 | 53.4 | 62.1 | 72.0 | 79.5 |
| L = 30 m | 61.5 | 89.4 | 117.2 | 145.5 | 175.2 | 223.7 | 322.8 | 557.7 | 1087.4 |
| L = 39.6 m | 171.8 | 330.0 | 695.7 | **2480.3** | 1442.3 | 565.6 | 300.7 | 184.2 | 133.5 |
| L = 60 m | 332.5 | 209.0 | 139.0 | 76.4 | 15.2 | 208.2 | **4217.2** | 948.2 | 640.5 |

L = 39.6 peaks near ε_r 3.0, L = 60 near 5.0, and L = 20/30 show no peak below
8 at all. **A coefficient singularity would sit at one ε̃ whatever the antenna
is.** At L = 60, ε_r = 5 the solved impedance reaches 3600 + 2678j — an
anti-resonance, an open circuit where the antenna has no business having one.

## Conditioning is innocent — and inversely so

`--mode cond`, wrapping `scipy.linalg.solve` (the per-class `_assemble_Z` hook
was wrong twice: razor reaches its solve by more than one assembly path so it
never fired, and bspline's returns a partial block whose cond came out
identical at every ε_r — the tell that it wasn't the inverted matrix):

| ε_r | 1.8 | 2.6 | 3.0 | **3.1** | 3.6 | 5.0 | 8.0 | 13.0 |
|---|---|---|---|---|---|---|---|---|
| razor cond | 442.2 | 109.3 | 78.33 | **73.26** | 60.23 | 82.95 | 126.2 | 1410 |
| razor \|err\| | 171.8 | 695.7 | 2480.3 | **3343.9** | 939.6 | 300.7 | 133.5 | 63.9 |
| bspline cond | 113.8 | 119.6 | 120.0 | 120.1 | 128.6 | 172.4 | 221.4 | 256.4 |

The correlation is **inverse**. razor's operator is at its *best* conditioned
(cond 73, σ_min 136) exactly where the error is *worst*, and at its worst
(cond 1410) where the error is smallest. bspline's is smooth and featureless.

**So the matrix is fine and its entries are wrong.** The anti-resonance is not
rank loss. Ill-conditioning joins the interpolation lattice, the integration
tolerance and row-halving on the list of things this is not.

## One horizontal wire reproduces it — the reproducer is now 6 unknowns

`--mode wire`. One 39.624 m horizontal wire, five segments, driven at node 2.
No junction, no screen, no vertical.

| h/λ | ε_r 2.5 | 3.0 | 3.1 | 5.0 | 13.0 |
|---|---|---|---|---|---|
| 1e-2 | 0.23 | 0.20 | 0.22 | 0.26 | 0.27 |
| 1e-3 | 33.0 | 39.7 | 40.9 | 57.1 | 79.7 |
| 1.09e-4 | 599.6 | 753.7 | 783.0 | 1283.9 | 3281.7 |

(razor-nec5 |err| in Ω; ratio at 1e-2 is 0.996–1.005.)

Clean at 1e-2 λ, broken below. **The reproducer drops from 24 unknowns to 6** —
entry-by-entry diagnosis becomes tractable and a fix gets a millisecond unit
test. It also confirms experiment 3 from the smallest possible model: **the
horizontal wire alone is sufficient**; the screen and the junction are not part
of the mechanism.

Two cautions, banked with it:

- The wire is far more sensitive than 0033 — Z over `GN 1` at the clean rung is
  0.0395 − 1035.2j, a real part of 0.04 Ω — so the ground correction dwarfs the
  PEC answer and bspline's own basis error is amplified with it. bspline is
  35–39 Ω out even at the clean rung here, and its column is **not** readable
  as basis-independent evidence.
- razor **undershoots** here at 1e-3 (ratio 0.73–0.83) where on 0033 it
  overshot 3.06×. The error's *sign* is geometry-dependent — a third reason no
  single scale factor describes it.

## Where the elimination stands

Ruled out, each by measurement: the mesh · the junction · the drive spelling ·
the seam's addressing · the interpolation lattice · the integration tolerance ·
a model-independent scale factor (row-halving) · ill-conditioning /
rank loss · a coefficient singularity at a fixed ε̃.

What is left: **the assembled ground-correction entries themselves are wrong
for grazing horizontal pairs**, additively and soil-independently on lossy
ground, with a sign and a resonant structure that both depend on geometry.

---

# Named: razor's near-diagonal ground entries, ~4× too big

`--mode matrix`, on the six-unknown reproducer. **This one needs no binary at
all.** Raw output in `RESULTS-matrix.txt`.

## Reciprocity is clean

‖Z − Zᵀ‖/‖Z‖ sits at 1e-15 to 1e-17 for both trunks, at every height, over PEC
and over `GN 0` alike. No asymmetry bug.

## The correction lives entirely in the near-diagonal band

|ΔZ| averaged by |i−j|, razor-nec5:

| \|i−j\| | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| h/λ = 1e-2 | 13.2 | 5.4 | 1.03 | 0.145 |
| h/λ = 1e-3 | 62.8 | 34.5 | 0.915 | 0.0958 |
| h/λ = 1.09e-4 | **439** | **235** | 0.873 | 0.11 |

33× on the diagonal, 43× on the first off-diagonal — and **every entry at
|i−j| ≥ 2 is height-independent.** Whatever is wrong is in the self and
nearest-neighbour terms, the ones where a source and its own image nearly
coincide (R₁ → 2h).

## The limit that settles it — computable from momwire's own machinery

The growth is not by itself an error: a horizontal wire close to a dielectric
genuinely couples hard to it. What settles it is the **limit**.

As h → 0 the near-diagonal correction is the incomplete cancellation of an
antiparallel image — PEC images a horizontal current at exactly −1, a
half-space at −Γ — so

> |ΔZ| / |PEC image term| → |1 − Γ| = |2/(ε̃ + 1)|

and the PEC image term is measurable with no reference at all, as
Z(`GN 1`) − Z(`GN -1`). For average soil at 1.832 MHz, ε̃ = 13 − 49.06j and the
limit is **0.0392**.

|ΔZ| / |PEC image|, bands 0 / 1 / 2:

| h/λ | bspline | razor-nec5 |
|---|---|---|
| 1e-2 | 0.0603 0.0785 0.0411 | 0.0656 0.0813 0.0292 |
| 1e-3 | 0.0498 0.0728 0.0399 | 0.0620 0.0716 0.0201 |
| 1.09e-4 | 0.0484 0.0740 0.0408 | **0.2357 0.2537** 0.0192 |

**bspline is height-stable and razor is not.** bspline holds ~0.05 / 0.074 /
0.041 at all three heights — converging to a constant, as the physics
requires. razor tracks it down to 1e-3 and then **jumps 4× at the last
height**, to 0.236 and 0.254, exactly where the quasi-static limit is most
valid.

The finding does **not** rest on absolute agreement with 0.0392 (bspline sits
within a factor ~2, which is what a leading-order estimate is worth). It rests
on razor's own ratio *moving* 0.062 → 0.236 between two heights where it
should be settling to a constant, on a band whose neighbours are
height-independent, in a basis whose sibling does settle.

## The finding

> **razor's self and nearest-neighbour finite-ground entries carry about 4×
> too much of the perfect-image term at deep grazing.**

The surfaces are right, the medium is right, the matrix is symmetric and well
conditioned, and bspline's identical band converges.

## The acceptance test this hands a fix

On the one-wire reproducer: **|ΔZ|/|PEC image| in the near-diagonal band must
tend to a constant as h → 0, and that constant must be |2/(ε̃+1)|.** No binary,
no captured deck, six unknowns, milliseconds. That is a gate the fix can be
written against directly, and it is the first thing in this arc that is one.

---

# SOLVED: `n_qp_sommerfeld = 3` under-resolves Q's source quadrature

`--mode nqp`. Raw output in `RESULTS-nqp.txt`.

## The mechanism

With the band named, razor's assembly reads straight to it. The remainder Q
rides the T1 window and is integrated **over each source segment with
`n_qp_sommerfeld` Gauss points, default 3** (`razor.py`, the
`n_qp_sommerfeld=3` constructor default).

For a grazing horizontal pair the Q integrand has a **spike of width ~2h**
where the observer sits over the source's image — 1.78 cm inside a 7.92 m
segment, a relative width of 0.0022. Three Gauss points cannot see a feature
that narrow, and the spike **sharpens as h → 0**. That is exactly the band,
and exactly the height dependence, that `--mode matrix` measured.

It is consistent with every earlier elimination, which is what made it worth
testing rather than merely plausible:

- The direct-grid bypass changed how each quadrature point's *surface* is
  evaluated, **not how many points there are** — so exonerating the surfaces
  said nothing about the order.
- momwire#282 raised n_qp 3 → 12 at **contact** and moved 0.03 Ω. Not a
  counterexample: contact is a *vertical* wire, its image is collinear, and
  there is no spike to miss. That is also why this wasn't tried sooner.

## The band collapses at n_qp = 6

|ΔZ|/|PEC image| against the 0.0392 quasi-static limit:

| n_qp | 3 | 6 | 12 | 24 | 48 | 96 |
|---|---|---|---|---|---|---|
| h/λ = 1e-3 | 0.0620 | 0.0457 | 0.0469 | 0.0474 | 0.0475 | 0.0475 |
| h/λ = 1.09e-4 | **0.2357** | 0.0416 | 0.0419 | 0.0425 | 0.0433 | 0.0440 |

The 4× excess is gone at n_qp = 6, landing on bspline's value.

## End to end against the binary — 171.86 % → 1.44 %

razor-nec5 on 0033, error as % of |Z|:

| h/λ | n_qp=3 | 12 | 24 | 48 | 96 | 192 |
|---|---|---|---|---|---|---|
| 1.09e-4 | **171.86** | 61.02 | 44.15 | 26.05 | 9.87 | **1.44** |
| 2e-4 | 239.54 | 31.86 | 19.18 | 7.74 | 1.32 | 0.08 |
| 5e-4 | 230.91 | 10.02 | 3.24 | 0.37 | 0.05 | 0.05 |
| 1e-3 | 44.18 | 2.52 | 0.28 | | | |
| 3e-3 | 3.91 | 0.02 | 0.01 | | | |
| 1e-2 | 0.06 | 0.01 | 0.01 | | | |

**0033 and 0034 have been "divergent" for want of Gauss points.** #510 is a
quadrature-**order** defect, entirely fixable, and nothing else in the
elimination list has to be revisited.

## The fix is a keying rule, not a global raise

The order needed scales as the spike is narrow: h/Δ = 0.0103 wants ~48,
h/Δ = 0.00225 wants ~192 — roughly

> **n_qp ≈ 0.4 · Δ/h**

the same shape momwire#443 already applied to the grid's boundary layer.
**Keying is the design point.** 192 points on every pair would be ruinous, and
the spike exists only where an observer sits over a source segment's
near-coincident image — a per-pair or per-source-segment condition, not a
global one.

## What is left for the fix

- Design and implement the keying (per-pair predicate + order rule), and pin
  the cost. The reference-free acceptance test from the previous round is the
  gate: |ΔZ|/|PEC image| → |2/(ε̃+1)| on the one-wire reproducer.
- Whether bspline needs the same treatment. Its band is stable and its
  near-diagonal ratio is right, so its own grazing error (the ~5 % basis floor
  and the 82–136 Ω plateau) is probably a different and smaller story — but it
  has not been measured with n_qp raised.
- Whether the keying also removes the razor-only ε_r ≈ 3.1 pole. That pole was
  measured at n_qp = 3 throughout and may simply be the same defect seen at a
  half-space where it is worst.
- The ~116 Ω conductive-ground plateau: same question.
- The option-E *Honest limits* row, which was always independent of all of it —
  and which may no longer be needed if the fix lands.
