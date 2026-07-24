---
title: "Segmentation you never think about"
description: Wires mesh themselves at the design density — the rule behind the `None` default, why uniform density matters, and when an explicit count is still the right tool.
---

A method-of-moments solver chops every wire into segments, and the
trustworthiness of everything it computes rides on those segments being
short enough — and evenly sized. In antennaknobs that is the framework's
job, not the design's: a `Wire` that doesn't give a segment count (the
field defaults to `None`) is meshed at the **design density**
automatically. Here is a real catalog design, the Moxon rectangle — two
bent elements computed from `halfdriver`, `aspect_ratio`, and the tip
spacing, plus a short feed wire across the gap `T→S`:

```python
def build_wires(self):
    # ... geometry: corner points S, A, B, C, D, E, F, G, H, T ...

    def path(lst):
        return [Wire(a, b) for a, b in zip(lst[:-1], lst[1:])]

    tups = []
    tups.extend(path([S, A, B]))
    tups.extend(path([C, D, E, F]))
    tups.extend(path([G, H, T]))
    tups.append(Wire(T, S, ex=1 + 0j))
    return tups
```

No `Wire()` here mentions a count. The framework resolves `build_wires`
results before any consumer sees them, so there is no meshing call to
remember either. The builder's only meshing obligation is to declare the
frequency that anchors the density:

```python
default_params = MappingProxyType({
    "freq": 28.57,
    "design_freq": 28.57,   # anchors the mesh density (see below)
    # ... the geometry knobs ...
})
```

## The rule behind `None`

There is exactly one rule, applied per wire with no interactions:

> A `None` count meshes the wire at the **design density**:
> `nominal_nsegs` segments per quarter-wavelength at `design_freq`.
> An integer count is taken verbatim.

Three consequences worth knowing:

- **N is a physical unit.** N=15 means a segment length of λ/60 — on
  this design, on every design. Convergence ladders are comparable
  across the whole catalog, and the segments-per-wavelength intuition
  from the NEC world maps directly.
- **`design_freq`, never `freq`.** The mesh is anchored to the frequency
  the geometry is *designed* for, not the frequency being measured — so
  sweeping frequency can never remesh the antenna mid-sweep. A design
  whose geometry is sized in absolute metres (like the Moxon) declares a
  `design_freq` purely as its density anchor; wavelength-sized designs
  already have one. Using `None` without declaring it is a build-time
  error, not a silent guess.
- **Uniform density is the whole point.** Every `None` wire in a design
  gets the same segment length, so no junction ever sees a mesh step —
  the failure mode described below becomes unwritable. A catalog-wide
  lint enforces the outcome (segment-length ratio bounded at fine mesh,
  and forbidden from growing up the ladder), so even a builder that
  keeps explicit counts can't silently introduce a density mismatch.

## The bookkeeping this replaces

Meshing a multi-wire design by hand has one invariant: *every wire's
count must be proportional to its length, at one shared density*.
Maintaining it means picking a **reference wire** that carries
`nominal_nsegs`, deriving **every other wire's** count from its own
length at that density (`segs_for(length, ref)` — never reusing the
nominal count on a wire of a different length), and re-running that
arithmetic for every wire added later and every knob whose drag changes
a length ratio. For the Moxon it looks like this:

```python
def build_wires(self):
    # ... geometry: corner points S, A, B, C, D, E, F, G, H, T ...

    n_seg0 = self.nominal_nsegs
    ref = math.dist(S, A)          # the reference wire's length
    n_seg1 = self.segs_for(math.dist(T, S), ref)

    def path(lst):
        return [
            (a, b, self.segs_for(math.dist(a, b), ref), None)
            for a, b in zip(lst[:-1], lst[1:])
        ]

    tups = []
    tups.append((S, A, n_seg0, None))   # reference: carries nominal_nsegs
    tups.extend(path([A, B]))           # tail, at the arm's density
    tups.extend(path([C, D, E, F]))     # reflector run, same density
    tups.extend(path([G, H, T]))        # tail + arm, same density
    tups.append((T, S, n_seg1, 1 + 0j)) # feed, same density
    return tups
```

This is correct — and it is all bookkeeping, none of it Moxon-specific
insight. Every line that touches a count is a chance to slip into the
natural-looking shortcut: giving **every wire the full nominal count**,
long or short.

On the Moxon that shortcut is quietly disastrous. The main elements are
3.8 m and the folded tails are 0.56 m, so one shared count runs the
tails at **6.7× the density** of everything else — and the over-dense
wires are exactly the facing conductors across the Moxon's critical tip
gap. At coarse meshes nothing shows. Refined, the NEC-style basis walks
away from the converged answer: 39.2−21.2j where the true value is
43.6−16.3j, a 14 % error that coarse-mesh agreement never hints at. The
same mismatch bites wherever a short wire — a feed link, a tip spacer, a
folded element's connecting stub — meets long ones at a hand-assigned
count; in the worst case, a 10 cm link's segment length falls below the
wire's *radius* and the reported impedance explodes to −1188j against a
true −30j. Uniform density makes the entire class of mistakes
unwritable, which is why it is the default rather than a convention.

## When would you still write a count?

Explicit counts are fully supported — an integer count is honored
verbatim, and `segs_for` is still there for computing one. They are the
right tool when the mesh itself is *data*: a deck-faithful reproduction
of an external NEC model, or the few validated port models whose counts
encode physics still under study. For everything else the
recommendation is simple: write `None`, declare `design_freq`, and never
think about segmentation again.

For the measurement story behind the density rule — the convergence
ladders and the basis comparisons — see
[How many segments?](/advanced/convergence/).
