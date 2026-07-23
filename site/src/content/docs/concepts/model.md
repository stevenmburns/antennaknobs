---
title: The model
description: How antennaknobs represents an antenna — the AntennaBuilder framework, the knob system, and the build_wires() contract.
---

Everything in antennaknobs is built on one small idea: an antenna is a function
from **parameters** (the knobs) to a **list of wires**.

## `AntennaBuilder`

A design subclasses `AntennaBuilder` and declares its parameters:

```python
from antennaknobs import AntennaBuilder

class Builder(AntennaBuilder):
    default_params = {
        "design_freq": 28.47,
        "freq": 28.47,
        "length": 5.2,
        # ...
    }

    def build_wires(self):
        ...
```

Parameters are read and written as plain attributes (`ant.length = 5.2`); under
the hood that's backed by the parameter dict. Variant parameter sets (e.g. a
design retuned for a different height or band) live alongside `default_params`,
and a `ui_params` block carries hints for the web knobs (ranges, the default 3D
view, and so on).

## The `build_wires()` contract

`build_wires()` returns a flat list of edges, each a tuple:

```python
((x0, y0, z0), (x1, y1, z1), nsegs, excitation)
```

- the two endpoints are 3D coordinates (metres),
- `nsegs` is the wire's segment count — write **`None`** and the framework
  meshes the wire at the design density, `nominal_nsegs` segments per
  quarter-wavelength at the design's `design_freq` (see
  [Segmentation you never think about](/concepts/auto-meshing/)); an
  **integer** is honored verbatim. The rule is strictly per-wire: in a mixed
  list, `None` wires resolve at the design density and integer wires keep
  their counts, with no interaction between them,
- `excitation` is `None` for a structural wire, or a complex value for the
  **driven** segment carrying the source.

A tuple may carry an optional **fifth element, a name** (a string), tagging
the wire so the network layer can attach to it — a
[`PortOnWire("feed")`](/concepts/station-modelling/) port, a trap's load, a
transmission-line endpoint — at that wire's middle segment. Most wires are
anonymous; you name exactly the ones something attaches to.

For anything beyond the plain 4-tuple, the recommended spelling is the
`Wire` named tuple (`from antennaknobs.network import Wire`) — a drop-in
tuple superset whose fields after the endpoints all default, so keywords
replace positional `None` placeholders:

```python
Wire(a, b)                     # structural wire, design density
Wire(t, s, ex=1 + 0j)          # the feed
Wire(ti, to, name="trap_b0")   # a named attachment wire
```

(Plain tuples stay 4–6 fields — there is deliberately no 2/3-tuple form,
because a bare third element would be ambiguous between a segment count
and an excitation.)

That single list is the entire interface to the solver and every renderer —
nothing downstream cares *how* you produced it, which is what makes the
[geometry layer so flexible](/concepts/authoring/).

## House conventions

- **Angles are in degrees** throughout, with a `_deg` suffix on parameter names
  (the web UI shows a compact `°`-suffixed label and the full program name in a
  tooltip).
- Segment counts are derived from a wire's length relative to a reference
  (usually a quarter-wavelength) so meshing stays consistent across designs.

Ready to write one? [Write your first design](/concepts/first-builder/) builds a
tunable dipole from a single hardcoded wire, one change at a time.

<!-- TODO: link to a generated API reference for AntennaBuilder once it exists,
     and document FRAMEWORK_PARAMS / nominal_nsegs precisely. -->
