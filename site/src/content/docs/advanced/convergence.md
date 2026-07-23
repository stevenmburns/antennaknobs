---
title: "How many segments? Convergence you can measure"
description: An advanced guide to choosing N and measuring accuracy with the convergence sweep — ladders, the mutual-limit test, and the four ways a curve refuses to settle.
---

The reference page covers the short version:
[more segments resolve the current better, cost grows as N²–N³, run the
convergence sweep and stop past the knee](/reference/solver/#segments--convergence).
That answer is right — and incomplete in one important way. A convergence
curve that has flattened is **not yet evidence that it flattened at the
right value**, and a curve that refuses to flatten can be telling you four
different things, only one of which is fixed by adding segments.

This page is the longer answer, built from a catalog-wide convergence
census (91 designs, every solver basis, meshes from N=7 to N=641). All
the numbers below are from those measurements.

## The ladder, not the pair

A single "coarse vs fine" comparison can mislead — curves overshoot. Run a
geometric **ladder**: solve at N = 21, 61, 161, 321 (each rung ≈3× the
last) and watch the whole trajectory. The workbench's
[convergence sweep](/reference/web/#convergence-sweep) does exactly this
and plots R and X against N per port.

Read it with a quantitative criterion, not by eye: call a rung
**converged** when its impedance is within 1–2 % of the finest rung's
(|ΔZ|/|Z|). Here is a real one — the catalog's `verticals.dominator` on
the sinusoidal basis:

| N | 21 | 61 | 161 | 321 | 641 |
|---|---|---|---|---|---|
| Z (sin) | 23.1−1.4j | 28.3+1.2j | 31.6+4.0j | 30.8+1.2j | 30.7−0.1j |

Two lessons in one table. First, the curve **overshoots** — at N=161 it is
past the answer and still moving, so a 21/161 pair would have estimated
the error with the wrong sign and the wrong size. Second, the plateau
only starts around N=321. If your ladder's last two rungs still differ by
more than your tolerance, the ladder is too short to conclude anything.

## Flat is not the same as right

The trap that motivates this whole page: **a curve can be flat at the
wrong value**. Flatness measures self-consistency, not accuracy.

The strong test is the **mutual limit**: solve the same ladder on a
*different basis* and require the two to converge to the *same* value.
That is what the workbench's solver slots are for — slot A (B-spline d=2)
and slot B (d=1) are different discretizations of the same physics, so
their agreement is evidence about the answer, while either one alone is
only evidence about itself. `dominator` again, slot A this time:

| N | 21 | 61 | 161 | 321 | 641 |
|---|---|---|---|---|---|
| Z (bs2) | 30.6+3.2j | 30.6+2.8j | 30.7+2.5j | 30.9+0.9j | 30.9−0.5j |

The d=2 basis is already at N=21 where the sinusoidal basis arrives at
N=321–641 — and they arrive at the **same** place. That pair of facts is
what "converged and correct" looks like. In the census, the two bases
reached a mutual limit (<2 % apart at the finest affordable mesh) on
66 of 91 designs; on those, bs2 was already within 2 % of the limit at
N=21 on 53 — the sinusoidal basis on 36 — with conv@N advantages up to
15×. That measurement is why the default solver slot now runs bs2 at
N=15: on the scorable catalog it is converged out of the box, at ~35 %
less cost per solve than N=21.

## The four ways a curve refuses to settle

When the sweep does *not* flatten, resist the reflex to just raise N.
The census decomposed every non-converging catalog design into four
classes, and they want four different responses.

**1. Slow basis convergence.** The value is creeping monotonically and
slot A (bs2) is flat at the value slot B is creeping *toward*. This is
the common case — port-fed and junction-heavy designs converge slowly on
the sinusoidal/pulse family. Response: trust the flat bs2 value, or
extend the ladder if you need the confirmation.

**2. Mesh-density mismatch in the geometry.** One part of the structure
refines while another is pinned coarse, and the graded junction between
them poisons the solve — the curve may *diverge* with refinement. (Two
catalog verticals did exactly this until their radials were made to
refine with the mesh; the tell was sin/PyNEC marching away from a flat
bs2 while the meshes decoupled.) Response: refine *uniformly* — in
your own builders, just return `None` segment counts; the framework
meshes every such wire at the design density, `nominal_nsegs`
segments per quarter-wavelength at your declared `design_freq` (so
N=15 means a segment length of λ/60, on every design). Integer counts
are still honored verbatim as the legacy path, but hand-assigned
counts are how every one of these defects was written.

**3. Physics-limited: the near-open feed.** A feed near a current null
(|Z| in the thousands of ohms — end-fed designs, some multi-element
arrays) is genuinely mesh-sensitive: the whole current distribution
contributes to a huge, delicately-balanced impedance. The tell: **both
bases crawl together**, in lockstep, at any port model. No basis and no
default fixes this class; expect a slow drift of a few percent, read the
admittance if you need a well-conditioned number, and treat the last
percent as physical uncertainty rather than solver error.

**4. A wire's segments approaching its own radius (Δ/a).** The oldest
rule in thin-wire MoM is also the one that produced the census's most
spectacular failure. The thin-wire kernel needs each segment to stay
long compared to the wire's *radius*: the NEC-2 guideline is Δ/a > 8
for ~1 % accuracy, "reasonable solutions" down to about 2 — and below
about 1 the discretized equation is genuinely ill-posed on the
point-matched sinusoidal/pulse family (sin, PyNEC, nec2c — errors here
are *correlated* across all three). In practice nobody violates this by
choosing N too large globally; it happens when a **builder gives a
short wire a long wire's segment count**. The census's folded
inverted-V read 223−30j identically on both bases at N=21…61, then the
sinusoidal basis went to 280−**1188**j at N=321 — and the cause was a
10 cm link wire silently carrying the full per-wire count, its segments
down to 0.6× the wire radius. With that one wire meshed proportionally
the sinusoidal ladder is dead flat at 223−30j through N=641. Two
amplifiers made the disguise convincing: the folded element's near-λ/4
shorted-stub mode sits at an antiresonance pole that turns a small
localized error into a wildly wrong reactance (with no visible
oscillation — the current stays smooth), and coarse meshes agree
beautifully because the coarse mesh itself keeps every wire above the
Δ/a floor. Response: when a ladder breaks at fine N, **check per-wire
Δ/a first** — in your own builders, let `auto_mesh` assign the counts
rather than reusing the nominal count on short wires (the catalog is
now linted for exactly this, both the ratio at fine mesh and its
growth up the ladder). The d=2 basis is immune — a Galerkin method
regularizes the reduced-kernel ill-posedness — which is also why a flat
bs2 next to an exploding sin curve is the tell.

One genuine residue survives the Δ/a accounting, and it is now pinned
([issue #484](https://github.com/stevenmburns/antennaknobs/issues/484)):
**multi-wire fan feeds** — several dipole pairs sharing one feed wire —
where the point-matched family drifts slowly and monotonically at fine
mesh while the Galerkin bases hold flat, with every wire comfortably
above the Δ/a floor. Three discriminating experiments settled what
drives it. Varying the element spacing over a 7× range moves the error
not at all — the traditional close-parallel-wire lore (the NEC-2
manual's aligned-segments requirement, Cebik's segment-length ≈
wire-spacing practice) does **not** explain this class. What does is
the **junction fan degree**: a one-element control converges cleanly,
and the fine-mesh error grows monotonically with each dipole pair
added to the shared feed junction (a five-band fan reads ~30 % low on
R at N=321). And it is a property of the *method family*, not one
implementation: our sinusoidal solver and PyNEC (nec2++) drift in
lockstep to a fraction of an ohm, while d=1 and d=2 B-splines — two
independent Galerkin bases — sit flat on the same value from N=21.
(That d=1 shares the immunity despite its merely-C⁰ junctions
identifies Galerkin's stationary impedance as the protective property:
collocation takes junction-charge error at first order in Z, and a
shared feed junction multiplies the error sites by the fan degree.)
Response: on fan-fed multiband geometry, read the fine-mesh answer on
the B-spline bases — and remember nec2c inherits the same family bias,
so it is not an independent referee here.

## Closed loops: room below the default

One geometry class earns a specific note because the payoff runs the
*other* way — not "raise N until it settles" but "you may lower it".
On single closed-loop designs the d=2 basis reaches the converged
impedance at a mesh ~2–3× coarser than the sinusoidal basis needs
([convergence anchor](https://github.com/stevenmburns/antennaknobs/blob/main/docs/status/2026-07-18-quad-convergence-anchor.md),
free space; "converged" = within 2 % of the finest rung):

| design | sinusoidal | B-spline d=2 |
|---|--:|--:|
| `loops.diamond_loop` (square loop) | N≥21 | N≥7 |
| `loops.delta_loop` (triangle) | N≥15 | N≥7 |

A dense solve scales as (basis count)², so 2–3× fewer segments is a
~4–9× cheaper solve at equal accuracy — on bs2 a single-loop design can
run *below* the N=15 default without losing the answer. Verify with the
convergence sweep as usual, and don't generalize the discount: it is
loop-specific. On open linear structures (`beams.yagi`) and the
two-element quad, every basis converges at the same N — which is why
the workbench applies no automatic basis-dependent coarsening. The
slider is yours.

## Feeds and ports deserve their own paragraph

The driving-point readout is the most mesh-sensitive number in the whole
solve, because the port *model* can change under refinement even when
the physics doesn't:

- A **delta-gap feed** narrows whenever the mesh subdivides its segment
  — on a short named port wire the readout can jump the first time the
  wire splits. Keep feed wires short (a dedicated ~1-segment stub at
  default mesh) so this happens far up the ladder, if ever.
- A port where a **transmission line or network attaches** can use a
  distributed port (`PortOnWire(name, distributed=True)`) — the port
  then spans the wire's fixed physical extent and is mesh-stable by
  construction. The catalog's Sterba-curtain TL variant runs its nine
  ports this way; they refine like every other wire and hold one
  basis-agreed value.
- A **lumped load** (termination resistor, trap) is genuinely a point
  element — keep it on a delta gap, on a short named wire that meshes at
  the design density like everything else. The load stays on the wire's
  *middle segment* as the mesh refines, so the point model survives
  refinement; pinning the wire's count instead (the old convention)
  turned out to bias the converged value itself — the catalog's trap
  study saw a pinned trap hold bs2 flat at the wrong reactance while the
  density-meshed model converged cleanly. What you should *not* do is
  spread the load's port current over a finite extent: gap-averaging a
  physical resistor under-counts its dissipation. Even the historically
  hardest case — a load at a **near-current-null (high-|Z|) attachment**,
  where the delta gap's parasitic susceptance competes with the tiny
  real admittance — turned out to be mesh-stable under this treatment:
  the catalog's terminated longwire kept pinned counts for years on
  evidence that refinement made its readout drift, but re-probing on the
  modern port machinery showed the density-meshed model reaching a clean
  mutual limit where the pinned one left the bases permanently apart
  (issue #526). The old drift was the port readout, not the physics.

## A working recipe

1. Solve at the defaults (bs2, N=15). For most of the catalog you are
   already converged — the census says 80 % of scorable designs are
   within 2 % at coarse mesh on this basis.
2. Run the **convergence sweep**. Flat within your tolerance across the
   top rungs → done.
3. Not flat? Turn on **slot B** and compare trajectories:
   - B creeping toward a flat A → class 1, trust A;
   - both marching away together as N grows → check your geometry for
     pinned-coarse wires meeting refined ones (class 2);
   - both crawling in lockstep at high |Z| → class 3, physics — accept
     the band, don't chase it;
   - agreement at coarse N that *breaks* or drifts at fine N while the
     other slot stays flat → class 4 — check per-wire Δ/a first (a
     short wire carrying a long wire's segment count is the classic
     cause; fix the density, don't just back N off), and on fan-feed
     geometry with healthy Δ/a, trust the flat d=2 value (#484).
4. Report the value both bases agree on, at the coarsest mesh past the
   plateau — that is the defensible number, and the cheapest one.
