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
bs2 while the meshes decoupled.) Response: refine *uniformly* — in your
own builders, scale every wire's count with `segs_for`.

**3. Physics-limited: the near-open feed.** A feed near a current null
(|Z| in the thousands of ohms — end-fed designs, some multi-element
arrays) is genuinely mesh-sensitive: the whole current distribution
contributes to a huge, delicately-balanced impedance. The tell: **both
bases crawl together**, in lockstep, at any port model. No basis and no
default fixes this class; expect a slow drift of a few percent, read the
admittance if you need a well-conditioned number, and treat the last
percent as physical uncertainty rather than solver error.

**4. Refinement past the geometry's own scale.** On closely-spaced
parallel wires — folded elements, fan dipoles, meander rails — the
thin-wire method breaks when the segment length drops **below the wire
spacing**. This one is vicious because coarse meshes agree beautifully
and then refinement makes the answer *worse*: a folded inverted-V in the
census read 223−30j identically on both bases at N=21…61, then the
sinusoidal basis went to 280−**1188**j at N=321 while bs2 never moved.
Response: don't refine such geometry past segment ≈ spacing; prefer the
d=2 basis, which was immune in every measured case.

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
  element — keep it on a delta gap, and pin that wire's segment count if
  refinement disturbs it. Spreading a physical resistor over a finite
  gap under-counts its dissipation.

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
   - agreement at coarse N that *breaks* at fine N on parallel-wire
     geometry → class 4 — back N off to segment ≈ spacing and stay
     there.
4. Report the value both bases agree on, at the coarsest mesh past the
   plateau — that is the defensible number, and the cheapest one.
