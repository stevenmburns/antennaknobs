---
title: "Segmentation you never think about"
description: The same Moxon rectangle written with explicit segment counts and with automatic meshing — what changed, why, and what the new density rule means.
---

A method-of-moments solver chops every wire into segments, and the choice
of *how many* used to be part of authoring a design. It is now optional:
give a wire the segment count `None` and the framework meshes it at the
design density. This page shows the difference on a real catalog design —
the Moxon rectangle — because the Moxon is also the design where hand
segmentation last went wrong.

## The same builder, twice

Both versions build identical geometry: the two bent elements of a Moxon
rectangle, computed from `halfdriver`, `aspect_ratio`, and the tip
spacing, plus a short feed wire across the gap `T→S`. Everything up to
the wire list — the corner points `S, A, B, C, D…` — is the same code.
Only the meshing differs.

**Explicit segmentation** (how the catalog's Moxon was actually written,
until it was found wrong):

```python
def build_wires(self):
    # ... geometry: corner points S, A, B, C, D, E, F, G, H, T ...

    def build_path(lst, ns, ex):
        return ((a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:]))

    n_seg0 = self.nominal_nsegs
    # Feed gap T->S refines with the mesh; the driver arm S->A is the
    # reference-length wire that carries n_seg0.
    n_seg1 = self.segs_for(math.dist(T, S), math.dist(S, A))

    tups = []
    tups.extend(build_path([S, A, B], n_seg0, None))      # arm + tail
    tups.extend(build_path([C, D, E, F], n_seg0, None))   # reflector run
    tups.extend(build_path([G, H, T], n_seg0, None))      # tail + arm
    tups.append((T, S, n_seg1, 1 + 0j))                   # feed
    return tups
```

**Automatic meshing** (the catalog's Moxon today):

```python
def build_wires(self):
    # ... geometry: corner points S, A, B, C, D, E, F, G, H, T ...

    def path(lst):
        return [(a, b, None, None) for a, b in zip(lst[:-1], lst[1:])]

    tups = []
    tups.extend(path([S, A, B]))
    tups.extend(path([C, D, E, F]))
    tups.extend(path([G, H, T]))
    tups.append((T, S, None, 1 + 0j))
    return self.auto_mesh(tups)
```

Every count is `None`; the builder ends with `self.auto_mesh(tups)`; and
the design declares one new parameter:

```python
default_params = MappingProxyType({
    "freq": 28.57,
    "design_freq": 28.57,   # anchors the mesh density (see below)
    # ... the geometry knobs ...
})
```

That is the entire migration. No reference-wire choice, no `segs_for`
arithmetic, no per-wire decisions.

## What the explicit version got wrong

The explicit code above looks disciplined — it even refines the feed gap
properly. Its defect is one habit: **every wire got the full nominal
count**, long or short. The main elements are 3.8 m; the folded tails are
0.56 m. Same count on both means the tails ran at **6.7× the density** of
everything else, at every mesh — and the over-dense wires were exactly
the facing conductors across the Moxon's critical tip gap. At coarse
meshes nothing showed. Refined, the NEC-style basis walked off the
converged answer: 39.2−21.2j where the true value is 43.6−16.3j, a 14 %
error that hid because coarse meshes agreed fine.

The same habit produced every meshing failure in the catalog's history:
a folded inverted-V whose 10 cm link carried the full count until segment
length fell below the wire's *radius* (impedance exploded to −1188j
against a true −30j), fan-dipole feed links hard-coded at 5 segments
while the arms refined past them, hexbeam tip spacers likewise. Different
designs, one cause: a hand-assigned count that left one wire's segment
length out of step with its junction partners.

## The rule behind `None`

There is exactly one rule, applied per wire with no interactions:

> A `None` count meshes the wire at the **design density**:
> `nominal_nsegs` segments per quarter-wavelength at `design_freq`.
> An integer count is taken verbatim.

Three consequences worth knowing:

- **N is now a physical unit.** N=15 means a segment length of λ/60 — on
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
  the failure mode above becomes unwritable. A catalog-wide lint
  enforces the outcome (segment-length ratio bounded at fine mesh, and
  forbidden from growing up the ladder), so even a builder that keeps
  explicit counts can't silently reintroduce the bug class.

## When would you still write a count?

Explicit counts remain fully supported — a design written entirely with
integers behaves exactly as it always did, and `segs_for` is still there
for computing them. They are the right tool when the mesh itself is
*data*: a deck-faithful reproduction of an external NEC model, or the
few validated port models whose counts encode physics still under study.
For everything else, the recommendation is now simple: write `None`,
declare `design_freq`, finish with `auto_mesh`, and never think about
segmentation again.

For the measurement story behind this — the convergence ladders, the
basis comparisons, and the audit that found the defects — see
[How many segments?](/advanced/convergence/).
