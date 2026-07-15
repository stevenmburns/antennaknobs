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

1. **Phase 1 (this PR)**: `Wire` + `as_wire`, translate-layer specs,
   coercion/array passthrough — no engine behavior change; existing designs
   bit-identical.
2. **Phase 2**: PyNEC per-wire radius (native GW card) + per-tag LD 5
   conductivity; momwire per-polyline conductivity/insulation via the
   existing `_wire_loading` arrays; radius still scalar.
3. **Phase 3**: momwire per-wire radius kernels (companion issue), oracle
   tests land with the kernels.
4. **Phase 4**: `nec_import` uses true per-wire radii (no more
   `dominant_radius()` compromise) and translates ranged LD 5; per-wire
   length/weight readouts; docs + `elt_whip` showcase.
