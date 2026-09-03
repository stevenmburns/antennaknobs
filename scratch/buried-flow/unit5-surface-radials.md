# Buried-flow unit 5 (scoping): radials ON the ground are the low-height limit of the ELEVATED family

Measured 2026-09-03 on the laptop, momwire v0.47.0 (main 84211f8). Probe:
`surface_radials.py`. Reference: Severns N6LF, QEX Mar/Apr 2009 part 3,
Table 1 — 7.2 MHz, 33.5 ft tubular mast, 33 ft No. 18 INSULATED radials lying
on grass, soil measured at the site (ε_r 30, σ 0.020 in part 4; part 3's own
segment reads 0.015 — see momwire#838/#865 for the soil caveat). Measured Zi:

| N | 4 | 8 | 16 | 32 | 64 |
|---|---|---|---|---|---|
| Zi (Ω) | 137+14.9j | 85.5+8.0j | 56.1+6.2j | 42.9+2.1j | 39.7−1.2j |

momwire refuses a wire IN the plane (momwire#865). The question was which
served family the surface class is the limit of. Deck: shared radius 0.51 mm
(No. 18), mast graded to the node, feed on a vertex 5 cm below the top,
n_rad 10, n_far 19, auto quadrature, soil (30, 0.020).

## Buried spelling (bare radials at −z, hub, one rise)

| N | z = −5 cm | −2 cm | −1 cm | −3 mm |
|---|---|---|---|---|
| 4 | 58.88+15.56j | 59.07+14.98j | refused (θ floor) | refused |
| 16 | 45.13+10.54j | 45.09+9.59j | refused | refused |

Flat in depth and FAR below the measurement at low N (59 vs 137). A bare
buried wire collects the return current galvanically along its length; an
insulated wire in grass does not. The buried fill also refuses shallower than
~2 cm on this screen (below/below pair elevation under the 1° floor).

## Elevated spelling (radials and mast base at +h, no ground contact)

| N | h = 15 cm | 5 cm | 2 cm | 1 cm | 5 mm | 3 mm | 2 mm | 1.5 mm | 1.0 mm | 0.7 mm | measured |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4 | 39.44+2.41j | 41.06+16.55j | 42.77+31.08j | 45.47+45.42j | 53.29+66.46j | 73.54+90.22j | 125.96+101.72j | 175.28+51.63j | 123.66−21.44j | 83.99−11.58j | 137+14.9j |
| 8 | | | | | | 46.85+37.99j | 63.41+45.30j | 82.30+36.32j | 79.97+7.71j | | 85.5+8.0j |
| 16 | 36.73−2.32j | 36.88+0.77j | 36.76+3.90j | 36.69+6.88j | | 39.07+14.91j | 43.19+17.75j | 47.65+17.70j | 51.85+13.40j | | 56.1+6.2j |
| 64 | | | | | | 36.28+3.24j | | | | | 39.7−1.2j |

Mesh check at N = 4 (n_rad 10 → 30): 5 mm 53.29 → 53.24; 3 mm 73.54 → 73.44;
2 mm 125.96 → 124.14; 1.5 mm 175.28 → 171.14; 1.0 mm 123.66 → 128.88;
0.7 mm 83.99 → 88.31. Stable to ~1 % down to 2 mm, ~4 % at 1 mm (h/a = 2),
i.e. the fill is answering, not diverging, until the thin-wire floor.

## Reading

1. **The surface class is the elevated family taken to h ≈ conductor height,
   not the buried family.** At 15 cm the elevated deck reads 39–41 Ω at every
   N, the "few elevated radials suffice" result Severns also measured
   (his 6/12/48 in rows, reproduced by Haswell on momwire#838). As h falls
   toward the wire radius the low-N impedance swings through a RESONANCE
   (N = 4: 53 → 74 → 126 → 175 → 124 Ω from 5 mm to 1 mm, X +66 → +102 → +52
   → −21): a wire lying on a lossy dielectric is a slow-wave line, the 33 ft
   radial becomes electrically longer than λ/4, and a 4-radial system detunes.
   That is the mechanism behind "surface radials should be cut long", and the
   engine produces it unprompted.
2. **At h = 1.0 mm — where the centre of an insulated No. 18 conductor lying
   on soil actually sits (0.5 mm radius + ~0.4 mm insulation) — momwire reads
   the measurement to within a few ohms at N = 8 and 16** (80.0+7.7j vs
   85.5+8.0j; 51.9+13.4j vs 56.1+6.2j), within 4 Ω at N = 64 (h = 3 mm run),
   and within 13 Ω in R at N = 4 with X 35 Ω off. Nothing was tuned: h was
   set from the wire.
3. **The class is physically ill-conditioned at low N.** dR/dh at N = 4 is
   ~50 Ω per mm around 1.5 mm. A real installation's Zi depends on how the
   wire lies in the grass, and any serve must say so; at N ≥ 16 the
   sensitivity is a few ohms and the class is quotable.
4. **The insulation is part of the answer** and is not modelled (momwire has
   no dielectric coating); the 1 mm height stands in for it. Grass raises h
   further and lowers R at low N.

## What the serve should be (proposal for momwire#865)

- Keep refusing a wire IN the plane by name — z = 0 is not a physical
  configuration for a real wire and the kernel has no answer there.
- Serve "on the surface" as the ELEVATED family at an explicit small height
  (default: wire radius plus insulation, user-visible), with an advisory that
  states the low-N sensitivity in ohms per millimetre from the deck's own
  local slope. No new kernel; the above-ground fill answers today.
- Validity floor: h/a ≥ 2 (mesh-stable to ~4 % there); refuse below by name.
- Gate: Severns part 3 Table 1 at h = 1.0 mm as a SHAPE anchor with our own
  bar (the soil, insulation and grass terms are ours to state), the way
  Haswell's elevated-row anchor is being built.

Not done: convergence in n_rad at 1 mm for N = 8/16/64 (only N = 4 checked);
N = 32; the 160 m series (part 5); the insulation as a coating model.
