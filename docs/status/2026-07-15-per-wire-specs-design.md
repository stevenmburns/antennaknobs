# Per-wire sizes and specs (#388): design decisions

Status note pinning the decisions for the per-wire `WireSpec` work before
code review. Companion momwire issue: per-wire radius arrays across all four
solver bases (filed separately; the kernels gate full #388 acceptance).

## The type: `NamedTuple`, not a model class

`Wire` is a `typing.NamedTuple` (`p0, p1, n_seg, ex=None, name=None,
spec=None`) living next to `WireSpec` in `network.py`. Rationale:

- A `Wire` **is** a tuple: indexing, unpacking, and the `t[4]`-style name
  access in existing consumers keep working, so plain 4/5-tuples and `Wire`
  entries mix freely in one `build_wires()` list — the issue's
  strictly-additive requirement.
- No new dependency; matches the codebase pattern (frozen dataclasses +
  tuples). A pydantic-style model was considered and rejected: it is not a
  sequence (every indexing consumer breaks), it validates on every
  construction in a hot path (~4k wires per knob drag on the whip
  benchmark), and its strengths (JSON parsing, schema) have no application —
  wires never cross a serialization boundary as wires.
- The one hazard — `len()` is always 6, so 4/5-arity checks misread it — is
  contained by a single normalizer choke point: `as_wire(entry) -> Wire`.
  Consumers call it instead of inspecting `len()`.

## Precedence (defined once)

explicit per-wire `spec` → web `wire_radius` override →
`build_wire_material()` → 0.5 mm PEC ideal.

The web override *moves the default* only; it never overrides an explicit
per-wire spec.

## Scaling semantics

Transforms, array placement, and scale knobs move geometry, never specs.
A `spec` describes the physical wire stock (gauge, jacket, weight); a
scaled antenna is still built from the same stock. Designs wanting scaled
radii construct their specs from their own scale knob.

## Spec changes split polylines

momwire consumes per-wire arrays (one value per polyline), so
`flat_wires_to_polylines` treats a spec change at a degree-2 node as a
polyline boundary and registers the node as a 2-entry KCL junction —
the same mechanism as a cycle cut. Every polyline therefore carries exactly
one spec (`polyline_specs` in the translate result). Mixed-spec loops are
opened by their spec boundaries before the pure-cycle handler runs.

## momwire mixed-radius kernel convention (to validate, not assume)

Proposed: self terms use the wire's own radius; mutual terms between
distinct wires use the source wire's radius for the surface offset
(observation on the axis) — the classic thin-wire reduced kernel. NEC
solves mixed-radius decks natively and is the parity oracle; the convention
freezes only when the oracle agrees on (a) a two-radius dipole, (b) a fat
monopole + thin radials, (c) the W8IO whip benchmark deck.

## Rollout

This PR lands phases 1, 2, and 4; the momwire kernels (phase 3) follow as
the companion-issue PR and then a version-bump hookup here.

1. **Phase 1**: `Wire` + `as_wire`, translate-layer specs, coercion/array
   passthrough — no engine behavior change; existing designs bit-identical.
2. **Phase 2**: PyNEC per-wire radius (native GW card) + per-tag LD 5
   conductivity/insulation cards; momwire per-polyline conductivity/
   insulation via the existing `_wire_loading` arrays; radius still scalar
   (uniform per-wire radii honored exactly, mixed collapse to the
   length-dominant with a warning).
3. **Phase 4**: `wire_tuples(specs=True)` imports decks with true per-wire
   radii (no `dominant_radius()` compromise; plain `wire_tuples()`
   unchanged), ranged whole-wire LD 5 becomes per-wire conductivity,
   per-wire length/weight readouts, docs, and the `elt_whip` upper whip
   carries its true 0.889 mm radius (PyNEC remeasured: bare 1.49+33.6j,
   matched 59.2+8.5j — inside the calibrated windows).
4. **Phase 3 (follow-up)**: momwire per-wire radius kernels across all four
   solver bases + C++ accelerators (companion issue momwire#147); the
   PyNEC-vs-momwire mixed-radius parity oracle lands with the kernels, and
   the momwire engine's dominant-radius collapse is then replaced by the
   real arrays. *Landed 2026-07-15 for SinusoidalSolver + the BSpline dense
   family (momwire PR #148): the engine passes per-wire radius arrays to
   those solvers; the H-matrix family keeps the collapse until its block
   fills are ported. Two validation findings: (a) the kernel convention is
   the OBSERVER wire's radius (necpp EFLD's `ai = segment_radius[i]`) — the
   source-radius convention this note originally proposed was refuted by
   the oracle; (b) NEC-2 is non-convergent at IN-LINE radius steps (the
   classic stepped-radius deficiency), so cross-engine parity there is
   asserted via SinusoidalSolver (which tracks NEC) and via mixed-radius
   junctions for the Galerkin family — see momwire
   docs/sinusoidal_basis_design.md "Per-wire radius".*
