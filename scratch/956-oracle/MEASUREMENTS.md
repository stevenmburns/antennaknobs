# momwire#956 Phase B — the rise deck's cross block against an empymod-warranted oracle

Scratch record, 2026-09-11. Nothing here touches package code.

Deck: antennaknobs `buried_radial_vertical`, connected spelling, 4 radials,
hub depth 0.15 m, soil A (13.0, 0.005), 7.1 MHz, shipped mesh — 248 segments,
26 above, 222 below, wire radius 0.5 mm. momwire reads
`Z = 75.8482072455881 + 40.45229390013113j`, which is the literal #956 carries.

## The instrument

`proj_oracle.py` is a drop-in for the `proj_fn` that `_field_galerkin_block`
already takes, so momwire's OWN moment weights, wing sums and chunking assemble
the block and **only the Green's function is replaced**. The kernel is the #524
phase-0 prototype (`scratch/524-phase0/proto/buried_proto.py`), whose warrant is
that suite's G4 against empymod 2.6.0 at ht='quad' ppd=600 — re-run 2026-09-11
in a scratch venv, live and cached, reproducing `RESULTS.md` to the digit.

Two gates before any reading:

- **conventions** (probe2): the two projectors agree to 3.3954e-05 worst over 12
  well-separated pairs, mean ratio 0.999992+0.000006j, std 1.2e-05. No moment
  or time-convention slip.
- **plumbing** (probe3 `gate2`): feeding momwire's own block back through the
  patch reproduces Z bit-for-bit, and zeroing the block moves Z by 326x. Neutral
  and not inert.

## Why the whole-block number is a DROP SPELLING and must not be quoted

Substituting the entire oracle block reads `dR = +5769 ohm` (Z -> 5844.6 -
8205.4j). **That is not a measurement of anything.** The rise and the radiator
are collinear and SHARE the node, so the block contains touching collinear
pairs, and the on-axis zero-radius field form over two segments with a common
endpoint has no finite value — it is the ln(a)-class content `_crossing_fill`'s
docstring names, the content its by-parts ends and corner exist to hold.

The quadrature ladder proves it rather than asserting it. On the on-axis
sub-block, worst-vs-momwire runs **1.72e-01 -> 3.27 -> 17.7** at q = 6 / 12 / 24,
with rung-to-rung self-convergence 4.15 and 3.38. A quantity that GROWS without
limit as the quadrature resolves it is a divergent integral, not an integral.
5844 ohm sits in the same family as #956's own fifth-surface table — 12270 ohm
with ends+corner dropped, 2629 ohm with the corner dropped.

## Where the oracle IS an instrument

Split by pair separation, the same rungs (probe10). "drift" is the worst
rung-to-rung movement on that population:

| separation | entries | q=6 | q=12 | q=24 | drift | verdict |
|---|---|---|---|---|---|---|
| >= 0        | 216 | 2.12e+04 | 1.09e+05 | 4.78e+05 | 8.1e-01 | divergent |
| >= 0.05 m   | 198 | 1.5054e+01 | 1.5054e+01 | 1.5054e+01 | 9.7e-08 | converged |
| >= 0.25 m   | 145 | 1.7418e+00 | 1.7418e+00 | 1.7418e+00 | 7.0e-07 | converged |
| >= 1.00 m   | 120 | 3.8319e-02 | 3.8319e-02 | 3.8319e-02 | 2.0e-09 | converged |

So the oracle is quadrature-converged for every pair 0.05 m apart or more.

**Converged is not the same as correct.** Substituting the 0.05-0.25 m band
moves R by +165 ohm, which no engine's answer is near (momwire 75.8, NEC-5
77.9). Those entries involve the crossing-node bases, which do not vanish at
z = 0: each free-end wing carries an end charge in a point-dipole superposition,
and those charges only cancel against each other once the full assembly makes
the current continuous through the node. Substituting the cross block ALONE
breaks that cancellation. So the near-node band is converged, wrong, and not an
instrument either — for a different reason than the touching pairs.

**The defensible window is separation >= 0.25 m.**

## The result

Substituting by population, at the finest rung (probe8, probe10):

| population | entries | dR |
|---|---|---|
| off-axis (radial x radiator), >= 0.25 m | 5832 | **-0.0001 ohm** |
| ON-AXIS (rise x radiator), >= 0.25 m | 145 | **+0.4561 ohm** |
| on-axis, >= 0.50 m | 136 | +0.5602 ohm |
| on-axis, >= 1.00 m | 120 | +0.5476 ohm |

and the on-axis figure is stable in quadrature to four digits:

| threshold | dR q=6 | dR q=12 | dR q=24 |
|---|---|---|---|
| 0.25 m | +0.4562 | +0.4561 | +0.4561 |
| 0.50 m | +0.5602 | +0.5602 | +0.5602 |
| 1.00 m | +0.5476 | +0.5476 | +0.5476 |

Two readings, and the second is the one to carry:

1. **The radial content is exact.** 5832 entries move R by a ten-thousandth of
   an ohm. The cross block's off-axis content is not where anything lives, which
   is consistent with #956's "flat in radial count, flat in radial length".
2. **The on-axis rise-to-radiator content disagrees, in NEC-5's direction, by
   about +0.46 ohm** — roughly 22 % of the +2.1 ohm residual, from 145 entries
   the oracle is entitled to price. The oracle sides with the ENGINE here, not
   with momwire. That is the opposite of the direction §4 of the withdrawn plan
   comment expected.

## What this does NOT establish

- It is a partial figure. +0.46 of +2.1, and the rest of the on-axis
  population — everything closer than 0.25 m, where the residual's per-entry
  weight is largest — cannot be priced by this instrument at all.
- A per-entry disagreement of 9-21 % on the far on-axis pairs is measured, but
  whether momwire or the field form is right there is NOT settled by agreement
  with NEC-5: three-way agreement between two of the three is what a third
  oracle is for, and here the third oracle is only entitled to 145 entries.
- The near-node band needs a different instrument: one that substitutes the
  cross block AND the compensating node content together, so the free-end
  charges still cancel.

## The next block to name

Not the cross block's distributed content — that is exonerated off-axis to 1e-4
ohm and converged on-axis. **The near-node cross content, separation < 0.25 m,
which is `_crossing_fill`'s by-parts ends and corner**, is where the unpriced
majority of the on-axis population sits. #956's own depth signature argues
against it (the corner is flat in depth to 0.08 % while the residual grows 11x),
but that argument was made against the corner's MAGNITUDE, not against the
by-parts ends, and the on-axis result above says the axis is where to look.

## Files

`proj_oracle.py` the projector; `probe1_geometry` the deck census;
`probe2_convention` the projector gate; `probe3_cross_block` gate2 + the whole-
block ladder; `probe4_cost` the measured cost model; `probe5_partition` the
separation split; `probe6_hub` the hub configuration and its off-axis ladder;
`probe7_census` every disagreeing entry with geometry; `probe8_substitute` the
population substitutions; `probe9_qladder` / `probe10_qconv` gate 1.
Blocks cached under `blocks/` so no rung is recomputed.

## Two traps this unit walked into, recorded because both nearly shipped

1. **`supp_seg` pads unused wings, and the padding is a real segment index.**
   26 of 765 wings here carry an all-zero polynomial; 9 repeat a real wing and
   17 are the literal index 0. Harmless in the assembly, poisonous to a
   geometric read of the same array: segment 0 on this deck is a radial AT THE
   HUB, so every padded basis looked like it had support 0.15 m from the plane.
   Mask on `polys`, never on `supp_seg` alone.
2. **A census sorted by relative difference must be read from the HEAD.** The
   first reading of probe7 was taken with `tail`, which showed its smallest
   disagreements and led to a conclusion the top of the same list contradicted.

## Rise-length control — predictions registered BEFORE the rungs landed

Written 2026-09-11 with the 0.075 m rung in hand and the 0.15 / 0.30 m rungs
still running, so these are predictions and not fits.

Rung 1 measured: rise 0.075 m, **ON-AXIS dR +0.2124 ohm** (144 entries),
off-axis -0.00024 ohm (5800 entries), R0 76.154.

The 0.15 m deck was priced at +0.4561 ohm by `probe8_substitute`. Against the
0.075 m rung that is a ratio of 2.147 over a 2x rise, i.e. an exponent of
**+1.10** — and the residual this issue measures runs 2.1 -> 23.6 ohm over
0.15 -> 1.2 m, which is **~d^1.1**. If that holds it is the same power law.

Two predictions:

1. **The 0.15 m rung reproduces +0.4561 ohm** to the digit shown. It is the same
   deck `probe8` priced, reached through a different script, so a disagreement
   is a harness defect rather than physics.
2. **The 0.30 m rung reads +0.978 ohm** (+0.4561 x 2^1.1). Tolerance for
   "the power law holds": an exponent in [1.0, 1.2] across both intervals.
   Outside that, the two-point exponent was a coincidence of two points and the
   term is not the residual's.

If instead the on-axis dR comes out FLAT in rise length, the +0.46 is a
different term, must not be netted against the residual, and the next unit is
worth less than its costing assumes.

### Outcome — prediction 1 held, prediction 2 FAILED, and the failure was the instrument

| rung | ON-AXIS dR | off-axis dR | verdict |
|---|---|---|---|
| 0.075 m | +0.2124 | -0.00024 | |
| 0.150 m | **+0.4562** | -0.00013 | prediction 1 HELD (probe8 read +0.4562 at q = 6) |
| 0.300 m | +77.5334 | **-88.25972** | prediction 2 FAILED (+0.978 predicted) |

Exponent +1.10 then **+7.41**. But the number that condemns the rung is not the
+77.5 — it is the **-88.26 beside it**. The off-axis population held at -2.4e-04
and -1.3e-04 on the first two rungs and has nothing to do with the rise. A
control that breaks when the measurement does says the instrument failed, not
that the term changed.

**Root cause: `separation >= 0.25 m` was a PROXY and it broke.** The real
criterion is the CROSSING-NODE bases — the ones that do not vanish at z = 0,
whose free-end charges cancel only across pair classes. On the 0.15 m deck those
bases sat within 0.25 m of everything, so an absolute threshold happened to
exclude them. But `depth` sets the RADIAL depth as well as the rise length, so
at 0.30 m the radials moved outside the threshold while still pairing with the
node bases, and the excluded population walked straight back in.

### The same three decks on a window that names what it excludes

No basis touching z = 0 (3 above, 3 below on every deck), and separation
>= 0.25 m. Re-analysis of the SAVED blocks, not a re-run:

| rise | ON-AXIS dR | entries | off-axis dR | entries |
|---|---|---|---|---|
| 0.075 m | +0.1682 | 90 | -0.00024 | 5200 |
| 0.150 m | +0.4119 | 91 | -0.00012 | 5220 |
| 0.300 m | +0.9785 | 139 | -0.00006 | 5280 |

| interval | ratio | exponent |
|---|---|---|
| 0.075 -> 0.150 m | 2.449 | **+1.29** |
| 0.150 -> 0.300 m | 2.376 | **+1.25** |

The off-axis control is restored and monotone. **The on-axis term is NOT flat in
rise length** — it scales cleanly, with a self-consistent exponent across both
intervals.

**But the registered tolerance was [1.0, 1.2] and it is MISSED.** 1.29 and 1.25
are consistent with each other and NOT with the residual's ~d^1.1 as that
exponent was measured. By the criterion set before the rungs ran, "this is a
piece of the same term" is **not** established — what is established is that it
is rise-scaling, self-consistent, and a candidate. The two exponents are close
enough that the difference may be span (0.075-0.30 m here against 0.15-1.2 m
there) or the difference between a partial term and a driving-point R, but
saying so would be fitting an explanation to a missed prediction.

On the named window the 0.15 m figure is **+0.4119 ohm**, i.e. about **20 %** of
the +2.1 ohm residual, not the 22 % quoted from the proxy window.

## Spike: why regime 2 costs what it does

The 1376 ms/eval that set the next unit's price was ONE configuration, and it is
neither wrong nor representative. The cost is a clean function of rho/h, where
h = |z + z'| is the in-medium image distance: the tail is partitioned at the
J0(lam*rho) zeros and truncated where e^{-lam h} dies, so the panel count — and
the time — scale with how many oscillations fit before the damping.

Measured on the unit's OWN query set (node-touching observers, which are shallow,
against every below source, which reach 6 m):

| rho | z_obs | h | tail panels | ms |
|---|---|---|---|---|
| 0.05 | -0.150 | 0.300 | 21 | 62 |
| 0.25 | -0.003 | 0.153 | 28 | 343 |
| 1.00 | -0.003 | 0.153 | 54 | 624 |
| 3.00 | -0.003 | 0.153 | 149 | 1449 |
| 6.00 | -0.003 | 0.153 | 288 | **2620** |
| 6.00 | -0.150 | 0.300 | 150 | 236 |

Mean over that grid **513 ms**, median 245, max 2620 — a 42x internal span. The
transmitted reference is ~29 ms, so the ratio is 18x on the mean and 90x at the
corner, not a flat 50x.

Three things the tally settles, none of them a quick win:

- **The head is free**: 16 sub-intervals on every single call, flat in geometry.
- **Nothing is failing**: zero non-convergent tails and zero Wynn-epsilon
  activations across every configuration — the plain tail sum goes quiet on its
  own, so the acceleration path is not being leaned on and there is no
  robustness problem hiding in the cost.
- **`err=False` buys 10-20 %, not 50 %.** It skips the COARSE companion
  integration, but the FINE run dominates. Not worth surrendering the
  per-call self-convergence estimate for.

**Revised cost.** ~144k in-medium evaluations at 513 ms mean = 20.5 h
single-core, **~2.9 h on 7 workers**, plus the above/above and cross parts and
the build/gate/analyse time: **8-10 h wall clock**, against the 12-16 h costed
before the spike. Most of it unattended.

A further 2-4x is available in principle by screening out the shallow-observer x
far-radial pairs, which are both the most expensive and the most weakly coupled
— but a screening threshold has to be gated against the unscreened answer on a
small deck before it can be trusted, and that gate is itself a chunk of the
saving. Not recommended as part of the first pass.

## The near-node unit

### Gate: the in-medium kernel at THIS geometry

G4c's 3.160e-04 against empymod is the prototype's warrant for regime 2, but it
was taken on the #524 SPEC grids, not on near-node configurations. Same check as
gate 0, on the pairs this unit queries — shallow below observers ON THE WIRE
SURFACE (rho = a, 2a, 4a) against below sources on the rise and out a radial:

**worst relative difference 9.6275e-05** over 25 pairs, mean ratio
0.999987+0.000012j, std 3.97e-05. No normalization or sign-convention slip.

Like for like: momwire's `remainder_field_proj_below` returns the REMAINDER, and
its below/below block is direct at k_m plus image minus that. The prototype's
twin is `field_remainder(shared="m")`, NOT `field_in_medium`, which composes all
three. Pairing the total against the remainder would be a silent decade.

### Prediction for Phase 1, registered before the run

Phase 1 substitutes the field form for the node-touching rows against the rise
and radiator columns, in the pair classes where plain Gauss is an instrument
(cross, and non-self non-adjacent same-medium), leaving momwire's own self and
nearest-neighbour entries in place. Partial by construction: radial columns are
Phase 2.

The reasoning: the residual is +2.1 ohm; the far on-axis content priced at
**+0.4119 ohm**, about 20 %. If the residual is an on-axis term, the near-node
remainder of it is the other ~80 %, and the near-node entries are the largest in
the block by three orders of magnitude.

**Prediction: Phase 1's partial dR is POSITIVE and between +1.0 and +3.0 ohm.**

Falsifiers, stated now:

- **|dR| < 0.1 ohm** — the near-node content is exonerated, the residual is not
  an on-axis near-node term, and the +0.41 far figure stands alone as something
  else. This would be the most informative outcome and I would report it as
  killing my own hypothesis.
- **dR negative, or |dR| > 10 ohm** — the instrument has failed again, the way
  the proxy window did. The plumbing control (momwire's own rows substituted
  must return momwire's own R) and the radius ladder are what would catch it,
  and I would not report a number until they do.

### TRAP: `field_transmitted` does not refuse a reversed pair — it answers a different question

The prototype's `field_transmitted` is written for a **buried source and an
elevated observer**. Phase 1's second cross block hands it the reverse — an
ABOVE source and a BELOW observer — because the two directions are assembled by
the same projector. It does not raise, it does not clamp, and it is not slow. It
returns a plausible number **quickly**, and the number is wrong. On one physical
pair (observer z = -0.02 m, source z = +5.0 m, VED, soil A, 7.1 MHz):

| route | E_z |
|---|---|
| reversed arguments into `field_transmitted` | **-4.172081e-01 - 2.808804e-01j** |
| the same pair via reciprocity (z and z' exchanged) | **+2.312433e-01 - 3.584108e-01j** |

Different in magnitude AND in sign structure. Nothing downstream would have
flagged it: the block assembles, the matrix is finite, the solve converges, and
a dR comes out.

The right route is reciprocity — `V_T(b->a)(rho, z, z') = V_T(a->b)(rho, z', z)`
— which is the prototype's own **G1**, reading 0.000e+00 over 18 (soil,
frequency, point) combinations. `proj_oracle._one` now detects the reversed
orientation and exchanges the roles, projecting on the OTHER tangent to match.

momwire does not have this trap because it carries two named projectors,
`transmitted_field_proj_below_to_above` and `..._above_to_below`, rather than one
used twice. Worth copying if a third consumer ever appears.

**How it was found, which is the part worth keeping.** Not by a test — by
chasing an unrelated stall. Three hypotheses for the stall were wrong and cheap
to falsify, and hypothesis 2 was wrong about the stall while being right about
correctness. A silent wrong answer surfaced because something else was broken
loudly enough to make me look. The earlier cross-block work (`probe3`,
`probe11`, and the +0.4119 ohm) assembles only the a x b direction and compares
against momwire's own a x b block, so it never took this route and is unaffected
-- checked, not assumed.

**Also cleared while chasing it:** "rho = 0 exactly breaks the J0-zero tail
partition" is FALSE. Measured at rho = 0 against rho = a and 2a, on three
near-plane configurations: 21-25 ms, tail panels 24-25, `nonconv` 0, self-
convergence 1e-11 to 1e-12, and the values agree across rho to the digits that
matter. This matters because every one of the 145 on-axis entries behind the
posted +0.4119 ohm sits at rho = 0 exactly.

### Phase 1 — prediction MISSED, falsifier triggered, no number reported

Registered 17:49:19Z: dR positive, +1.0 to +3.0 ohm; falsifier "negative, or
|dR| > 10 — the instrument has failed again".

| run | exclusions | dR |
|---|---|---|
| first | 24 self/adjacent | **+5858.52** |
| second | 24 self/adjacent + 24 touching-support | **+164.69** |

Both are falsifier territory. **No physical number is reported from either.**

The plumbing control PASSES in both: momwire's own entries substituted through
the same patch return `75.84820724558877+40.452293900130144j` bit for bit. So
the harness is neutral and the premise is what failed.

**The first run's +5858 was one missing exclusion.** "Shares a segment" cannot
catch a touching CROSS pair — an above basis and a below basis never share one —
so the pair meeting at z = 0 went through, and a single entry (|-Q - Z| =
4.3861e+03, the same entry `probe5` ranked first on the whole block) carried
+5858 of the +5859. Excluding touching supports fixed that.

**The second run's +164.69 is ALSO one entry**, and it is not a new one:

| |-Q - Z| | sep | m x n | class | \|Z\| | \|-Q\|/\|Z\| | dR alone |
|---|---|---|---|---|---|---|
| 1.4278e+02 | 0.1000 m | 228 x 220 | above x below | 1.4649e+02 | **2.53e-02** | **+164.33** |
| 5.89e-01 | 0.0063 | 228 x 224 | above x below | 4.23e+02 | 1.0013 | -0.35 |
| 4.15e-01 | 0.0062 | 229 x 233 | above x above | 1.22e+03 | 1.0003 | +0.00 |
| ... | | | | | 1.0001-1.0087 | |

**Every other entry agrees to between 0.01 % and 0.9 %.** One pair carries
+164.33 of +164.69. It is basis 228 — the crossing-node ABOVE basis, support
segment 222, [0,0,0] -> [0,0,0.05] — against basis 220, the hub-end rise basis,
support segment 216, [0,0,-0.15] -> [0,0,-0.100]. On the axis, 0.1 m apart, no
shared segment, no touching support, no singularity, and quadrature-converged.
momwire reads 1.4649e+02 there; the field form reads 2.5 % of it.

**And it is the same entry that has been anomalous throughout.** `probe7`'s
census ranked "228 x 220, sep 1.0000e-01, |o|/|m| 2.5313e-02" fifth back when I
was calling it one of the "hub four".

**So the unit's premise is falsified.** "Include all three pair classes among
the node-touching set and the free-end charges cancel as they do in the real
assembly" predicted this would resolve. It did not. That diagnosis is therefore
probably wrong too, and I am withdrawing it rather than repairing it.

### What the failure actually localises to, which is worth more than the number

Gate 2 (`probe15`) verified "an assembled entry IS -<f_m, E(f_n)>" to 3.0e-06 /
1.0e-06 — **on well-separated pairs, none of them involving a crossing-node
basis.** The one entry that fails involves exactly such a basis. So the open
question is sharp:

> Is momwire's assembled Z entry for a CROSSING-NODE basis the field-form
> Galerkin integral at all, or does the node wing carry structure that
> `supp_seg`/`polys` do not express?

The second is entirely plausible — the crossing serve appends the node's own
dofs after the stitch (D3's "one node wing per member"), and `_field_galerkin_
block` reconstructs a basis purely from `supp_seg` and `polys`. If a node wing
is not fully described by those two arrays, then MY Q for that entry is wrong
and momwire is right, and every field-form comparison touching a node basis is
void — including this whole unit.

That is one afternoon's check against a day of assembling, and it must come
first. Until it is answered, no near-node figure from this instrument means
anything.

### The node-basis check — and it removes MY instrument from the question

Same `_field_galerkin_block` contraction, same `supp_seg`/`polys` basis, driven
by MOMWIRE'S OWN transmitted projector instead of the prototype's:

| entry | (a) momwire kernel | (b) prototype kernel | (c) assembled Z | \|a-b\|/\|c\| | \|a-c\|/\|c\| |
|---|---|---|---|---|---|
| 228 x 220 (the failure) | -2.48301e+00+2.75406e+00j | -2.48294e+00+2.75396e+00j | -9.40695e+01+1.12292e+02j | **7.87e-07** | **9.75e-01** |
| 239 x 222 (control, far) | -9.02580e-02+1.08228e-01j | -9.02589e-02+1.08230e-01j | -9.48051e-02+6.73435e-02j | **1.87e-05** | **3.54e-01** |

**(a) equals (b).** momwire's own Green's function and the prototype's give the
same field-form answer to 7.9e-07 and 1.9e-05. So the disagreement is not the
kernel, and it is not my oracle: swapping in momwire's own kernel changes
nothing. The prototype, empymod, G4, the gates — none of them are the question
any more.

**Both differ from the ASSEMBLED entry**, by 97 % on the failing pair and 35 %
on the control.

**And the control involves NO node basis.** 239 is a radiator basis well up the
element and 222 a rise basis; neither touches z = 0. So "the node wing carries
structure `supp_seg`/`polys` do not express" cannot be the whole story — the
departure is not confined to node bases. What the two entries share is that both
are ON-AXIS cross pairs: the rise against the radiator.

So the sharp question is no longer about the oracle:

> On a crossing deck, momwire's assembled cross entries for ON-AXIS pairs differ
> from the field-form Galerkin integral of the same pair — computed with
> momwire's own kernel, momwire's own contraction and momwire's own basis
> arrays — by 35 % to 97 %. Off-axis cross entries agree to a median of 1.05e-08.

Two readings, and I cannot yet choose between them:

1. `_crossing_fill`'s complete mixed-potential spelling genuinely differs from
   the field form on these pairs — the by-parts ends and corner being O(1) where
   they should vanish. That would be a finding about the crossing serve.
2. `_field_galerkin_block` over `supp_seg`/`polys` is not the right contraction
   for a crossing deck's basis set at all, because the crossing serve appends
   node dofs after the stitch and `axis_data` may build its own representation.
   Then (a) and (b) are both computing something that is not the entry, and
   agreeing with each other proves only that they share a contraction.

Reading 2 is not ruled out by the control: if the contraction is wrong for the
deck's basis set it can be wrong for non-node bases too. Distinguishing them
needs momwire's own crossing-fill machinery interrogated directly — `axis_data`
and `cross_complete_block_split` against `_field_galerkin_block` on a deck where
they should agree by construction, e.g. a NON-crossing mixed deck, where the
cross block goes through the transmitted grid and the field form and the fill
are the same object. **That is the next check and it needs no oracle at all.**

### Is the contraction the fill's own assembly? YES — reading 1 confirmed

On a NON-CROSSING mixed deck the cross block goes through the transmitted grid
and `compute_Z_operator_buried` does `Z -= f.field_galerkin_block(...)` with
nothing else writing the above x below quadrant. So the assembled entry there IS
minus that contraction's output, and driving MY contraction with MOMWIRE's
projector must reproduce it.

| deck / pair | entry | (a) my contraction | (c) assembled Z | rel |
|---|---|---|---|---|
| non-crossing, ON-AXIS cross | 4x13 | -1.28246e-01+1.66911e-01j | -1.28246e-01+1.66911e-01j | **3.51e-10** |
| non-crossing, off-axis cross | 4x22 | 1.01589e-02+2.06186e-03j | 1.01589e-02+2.06186e-03j | **1.92e-10** |
| CROSSING, off-axis, sep 2.20 m | 240x0 | 3.76000e-04-2.30850e-04j | 3.75999e-04-2.30854e-04j | **8.77e-06** |
| CROSSING, on-axis, sep 0.10 m | 228x220 | -2.48301e+00+2.75406e+00j | -9.40695e+01+1.12292e+02j | **9.75e-01** |
| CROSSING, on-axis, sep 0.86 m | 239x222 | -9.02580e-02+1.08228e-01j | -9.48051e-02+6.73435e-02j | **3.54e-01** |

**`_field_galerkin_block` over `supp_seg`/`polys` IS the fill's own assembly.**
It reproduces the assembled entry to 1e-10 on a non-crossing deck in BOTH
orientations — on-axis included, so "on-axis" is not inherently hard for it —
and to 8.8e-06 on the crossing deck off-axis. Reading 2 is dead.

Consequences:

- **The +0.4119 ohm stands**, measured through a contraction now shown correct.
- **The finding is `_crossing_fill`'s ON-AXIS cross spelling.** It departs from
  the field-form Galerkin integral of the same pair — momwire's own kernel,
  momwire's own contraction, momwire's own basis arrays — by 35 % at 0.86 m and
  97 % at 0.10 m, while the same machinery agrees to 1e-10 wherever the crossing
  fill is not the thing being asked.

One scoping trap worth keeping: `basis_support` silently TRUNCATES a support to
the segments it is handed, so a basis reaching outside a restricted set yields a
PARTIAL entry. The crossing control row first read 9.4e-01 for exactly that
reason — a number about my scoping, not about momwire. Requiring every live wing
inside the restriction took it to 8.8e-06.

Also noted while doing it: **`serve_plan` REFUSES to size a transmitted grid for
this deck at all** — shallowest buried node 2.1e-04 m, observer elevation
0.0153 deg against a 0.1519 deg floor, and the refusal says a truncated tail
there was measured 4.5e+3 relative wrong. That is why a crossing deck never
builds one, and it is worth remembering that any hand-built grid for this
geometry is outside the band momwire will pay for. The rows above are inside it.

## The per-term decomposition — the O(1) term is NAMED

`_crossing_fill` exposes every seam from outside, so nothing in `src/momwire`
was touched:

    full   = cross_complete_block_split(ctx, a, b, A, B, corner=True)
    bnd    = _ends_and_corner(..., corner=False)
    corner = _ends_and_corner(..., corner=True) - bnd
    main   = full - _ends_and_corner(..., corner=True)     # `_main_split`
    self   = self_completions(ctx, ax_b, ax_a)

### Gates, run before any row was read

| gate | result |
|---|---|
| (ii) `corner=False` MOVES the block | 1.6716e+00 — **PASS**, the knob is connected |
| (i)a `main + bnd + corner == full` | **0.0000e+00** |
| (i)b `-(full + full.T) + self == Z` on the cross quadrant | **0.0000e+00** |
| (iv) non-crossing deck, field form vs assembled | 3.5e-10 / 1.9e-10 (probe20) |

Both sum gates are EXACT, not merely tight. The decomposition reconstitutes the
assembled entry, so the five terms below are the entry and not an approximation
of it.

### The table

| entry | sep | kind | \|main\| | \|bnd\| | \|corner\| | \|self\| | \|Z\| | \|field form\| | \|ff\|/\|Z\| |
|---|---|---|---|---|---|---|---|---|---|
| 228x220 | 0.100 m | on-axis | 1.4472e+02 | **2.9120e+02** | **0** | **0** | 1.4649e+02 | 3.7081e+00 | **0.0253** |
| 239x222 | 0.881 m | on-axis | 1.1629e-01 | **0** | **0** | **0** | 1.1629e-01 | 1.4092e-01 | **1.2118** |
| 240x4 | 2.212 m | off-axis | 1.7835e-02 | **0** | **0** | **0** | 1.7835e-02 | — | 8.8e-06 (probe20) |

### What it names

**The corner is exactly zero on every entry examined**, and so is
`self_completions`. Neither can carry the departure. That is worth stating
plainly because this issue has circled the corner for two units — the depth
signature argued against it (flat to 0.08 % while the residual grows 11x) and
the decomposition now says it is not merely small on these pairs, it is ABSENT.

**On two of the three entries `main` is the ONLY term**: Z = -main exactly. And
that same single term agrees with the field form to **8.8e-06 off-axis** and
departs by **21 %** on-axis, at comparable separations (2.2 m against 0.9 m).
Same code path, same kernel, same contraction; the only thing that changes is
whether the pair lies on the axis.

**So the named term is `_main_split`** — the designed mixed-potential sandwich,
M + SW + SQ — on ON-AXIS cross pairs. The by-parts end term is additionally
large on the node-adjacent entry (2.9e+02 against an assembled 1.4649e+02, the
two partially cancelling), but it is exactly zero on both other entries, so it
cannot be the general mechanism.

### What this does NOT say

It names which term, not whether it should be what it is. The field form is the
EFIE definition and `_main_split` is the designed spelling; deciding which is
right on an on-axis pair is a derivation against EQUATIONS.md and the AGARD
source, not a measurement. I am not making that call here, and after two
withdrawn mechanisms on this issue I am not offering a third.
