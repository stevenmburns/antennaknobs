# The EZNEC corpus against the licensed NEC-5, at a matched basis

What produced the numbers in momwire#1120 and AK#1622 (2026-09-21).

## Why it exists

Every routine gate here compares antennaknobs' `builder_from_file` route
against `momwire.eznec.serve`. That is a CONSISTENCY bar: it says "the same
computation", never "the right computation". By AK#1619 it had saturated: 23 of
28 networked decks sit at float noise, and the rest are inside the bspline basis
error, which is exactly where AK#1622 stopped. Three separate threads (the 0116
residual, AK#1622's premise, AK#1608 part 1) each reached "the instrument
cannot tell", and each re-derived it from scratch.

The instrument that HAS resolution is momwire's razor-2p with `nec5_quadrature`
and `extended_kernel`, NEC-5's own formulation, run against `nec5cl`. It reads
0.00 % where it agrees. It had never been run across the corpus; about ten
decks had been done by hand.

The extended kernel is part of the match. NEC-5 has no `EK` card and rejects
one, because its kernel is exact natively, so the momwire side runs with it
ON. It is not only about fat wires: 0067, at Delta/a = 40, moves 23x with it.

## Running it

```
python census.py --r 1  --out census_r1.jsonl
python census.py --r 11 --only 0021_vertical-over-real-ground,... --out ladder_r11.jsonl
python split_routes.py
```

Needs `nec5cl` at `~/antennas/NEC5-downloads/nec5-linux/nec5cl` (LAN only).
80 decks take about two minutes; the r = 11 ladder a few more.

## Results banked here

| file | what |
|---|---|
| `census_r1.jsonl` | all 80 decks at the authored mesh, against the licensed engine |
| `ladder_r{3,5,7,11}.jsonl` | the thirteen decks worth refining, at 3x to 11x the mesh |
| `split_routes.jsonl` | every deck, antennaknobs and serve side by side |

**Median 3.002e-05 over 80 decks; 64 of 80 at or under 0.01 %, 79 of 80 under
3 %.** The matched basis is essentially exact, which is what makes the outliers
worth reading.

## What it found

`split_routes.py` puts serve beside antennaknobs at the same basis, so every
deck splits by who carries the gap: a gap BOTH routes carry is momwire's model,
and a gap only one carries is that route's own defect.

| | decks |
|---|---:|
| both fine | 66 |
| SHARED (momwire's model) | 7 |
| AK-SIDE ONLY | 4 |
| unmeasured (serve refuses the deck's `NE` card) | 3 |

### The shared gap is two antennas near a finite ground

| antenna | lowest conductor | decks | r = 1 | r = 11 |
|---|---|---|---:|---:|
| ground-mounted vertical, contact-fed | 0 m (touching) | 0021, 0047, 0048, 0110, 0111 | 2.16e-02 | 2.12-2.13e-02 |
| elevated radial system | 0.0178 m | 0033 | 1.47e-02 | 7.80e-03 |
| | | 0034 | 7.81e-03 | 5.60e-03 |

0022 and 0112 are the same vertical and read 2.16e-02 from antennaknobs; serve
refuses their near-field card, which asks for the field at the contact itself.

Two controls make the vertical's gap an INTERACTION rather than "finite ground
is hard" or "contacts are hard":
- **Perfect ground:** the same verticals over a perfect ground (`GN 1`, or
  `GE 1` with no `GN`) agree to 2.9e-05.
- **Height:** conductors over the SAME finite medium at 1.52 m and above agree
  to 1.1e-04.

The vertical's gap is flat under an 11x mesh and the same on both routes to
1e-13, so it is momwire's model, not anything either caller does (see
momwire#1120). The radials' gap closes under refinement, so part of theirs is
mesh.

### The AK-side gap is AK#1608's four decks

| deck | antennaknobs | serve |
|---|---:|---:|
| 0028 17-10m log-periodic | 2.397e-01 | 2.47e-05 |
| 0029 dipole with coax feedline | 1.798e-02 | 1.67e-05 |
| 0011 / 0030 dipole with coax feedline | 1.723e-02 | 3.45e-05 |

0011 and 0030 hold 1.719-1.725e-02 from r = 1 to r = 11. So the gap is a
defect on the antennaknobs route, not a mesh or height effect, and serve being
essentially exact on all four is what AK#1608 part 1 needed.

## Method rules this obeys, each learned expensively

- **One configuration per comparison.** Both sides read the SAME deck text.
  Nothing is translated between dialects, which is what AK#1515 says poisons the
  older `scratch/896-census` harness.
- **Controls, every run.** 0012 and 0016 must read 114.4700 + 21.0960j or the
  run aborts. NEC-5 needs an `XQ` card or it reads the cards and stops with no
  results, so a malformed probe reads as a refusal rather than an error.
- **Check the model that ARRIVED, not the one requested.** A solver without the
  requested model falls back to its best available one. Both scripts record the
  kwargs that reach `RazorSolver.__init__` and abort unless `nec5_quadrature`
  and `extended_kernel` are both there. serve takes EK only from the deck's own
  card, which this dialect has none of, so `split_routes.py` widens the
  `razor-2p` roster entry to carry it.
- **The refinement is an instrument too.** Every address in this dialect is a
  KNOT: `EX` names end 2 of segment s exactly as `TL` and `NT` do (its fourth
  field 0 reads as 2, measured on the licensed binary). A knot at s/n refines
  to s·r. A negative field is an end selector and is never scaled. A tag is a
  phantom wire only if it carries an open-circuit `LD` pin, not merely a load;
  the cardioids and four-squares carry real 18-ohm loads on their radiators.
  Get any of these wrong and the ladder moves for a reason that is not physics.
- **Read the ladder before believing a single rung.** The r = 1 column mixes
  mesh error with model difference: under refinement 0033 closes by half and
  0034 by a quarter, while the contact vertical moves under 2 %.

Courtesy rule: never cite NEC-5 internals publicly, only "verified against our
licensed materials".
