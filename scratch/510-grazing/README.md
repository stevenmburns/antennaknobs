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

## What this does not yet say

- Whether the onset moves with the integrator's own accuracy setting — the
  rtol / interpolation-grid axis `probe_contact_direct_remainder.py` found
  *saturated at contact*. That is a different regime, so it has to be asked
  again here. This is the next lever and the one that decides fix vs refuse.
- Whether `refl-coef` breaks in the same place. #624 found refl-coef and
  Sommerfeld behaving alike at contact; if they agree here too the remainder
  is exonerated again and the shared machinery is the suspect. The deck route
  cannot ask for refl-coef, so that needs a direct-solver lane.
- Whether the onset moves with soil. Average only, so far.
- Exactly where the refusal predicate should sit, if refusal survives the
  rtol test. These rungs bound it; they do not design it.
