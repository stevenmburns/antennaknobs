# Plan: catalog architecture for 1k–10k designs

Status: **future / not started.** Scoped 2026-07-08 during the per-variant
ui_params work (PR #266), when "does /examples ship the whole catalog?"
turned into "what would 10,000 designs need?". Nothing here is worth
building at today's ~75 designs — see the trigger conditions at the end.

## Where today's architecture is O(catalog)

Three costs scale linearly with the number of registered designs:

1. **Boot.** `register_all()` imports every design module and runs every
   builder's `build_wires()` once to prime the derived hints
   (`default_view`, `target_z0`, `multi_feed`, recommended backend). At
   ~75 designs this is unnoticeable; at 10k it is minutes of imports and
   geometry builds before the server can answer anything.
2. **`GET /examples`.** One monolithic payload carrying every design's
   full descriptor (param_schema, variants, variant_values, variant_ui,
   bands, sweep_policy). Measured 2026-07-08: 240 kB uncompressed for 75
   designs (~3.2 kB/design mean; group-heavy multiband designs 6–7 kB).
   Linear extrapolation: ~3 MB at 1k, ~32 MB at 10k.
3. **Discovery UX.** A flat family-grouped picker; unusable at 1k
   regardless of payload size.

What already does NOT scale with the catalog: solves, sweeps, geometry —
all per-selected-design. And user designs already have the lazy pattern
(`defer_hints=True`, rescan on request) that built-ins lack.

## Target architecture

### 1. Split the wire contract: index vs descriptor

- `GET /catalog` — lightweight index entries only: name, label, family,
  tags, one-line blurb, optional thumbnail URL. ~150–200 B/entry, so
  even 10k ≈ 2 MB uncompressed — and with server-side search, facets,
  and pagination the client never fetches it all anyway.
- `GET /designs/{name}` — the full per-design descriptor, exactly the
  shape one element of today's `/examples` array has. Fetched lazily on
  selection, cached client-side keyed by (name, catalog version).

The important property: **the existing descriptor shape becomes the
lazy-loading unit unchanged.** ParamForm, variant_values overlay,
variant_ui presentation hints — no downstream consumer changes.

### 2. Build-time manifest for built-ins

Derive every built-in design's descriptor at *package build time*: CI
runs the same `_make_example` derivation and emits a static JSON
manifest shipped in the wheel. At runtime the server serves index and
descriptors straight from the manifest without importing a single
design module. A design's module imports on its first *solve* — where
the builder has to run anyway.

This also kills the eager hint priming: hints are baked into the
manifest for built-ins. `defer_hints=True` (today's user-design path)
becomes the universal runtime rule rather than the exception.

Skew guard: a manifest is derived output, so CI must assert
manifest == live derivation for every design (one parametrized test),
or the wheel build simply regenerates it unconditionally.

### 3. Discovery as a server capability

At 1k+ the picker is a search box, not a list: full-text over
name/blurb/tags, facets (family, band coverage, polarization, feed
impedance class), typeahead endpoint. Because descriptors are static
per release, CI can also precompute *derived performance metrics* —
gain, F/B, SWR bandwidth at design frequency — enabling sort/filter by
performance. These must never be computed at request time; they are
exactly the kind of thing the golden-capture scripts already know how
to batch.

### 4. Caching

Built-in descriptors are immutable per release → ETag / long-lived
immutable cache headers, CDN-friendly (the SPA is already static).
User designs stay dynamic in their own namespace with the same
descriptor contract — they are the only part that cannot be baked.

## Migration path (each step independently valuable)

1. Generalize `defer_hints` to all designs; stop running builders at
   boot. (Smallest step, removes the boot-time O(catalog) term.)
2. Split `/catalog` from `/designs/{name}`; frontend grows a small
   descriptor cache. Comfortably carries ~1k designs.
3. Build-time manifest for built-ins. Carries 10k.
4. Search/facets/typeahead + precomputed performance metrics, when the
   catalog is actually big enough that discovery is the bottleneck.

## Trigger conditions (when to start)

Do NOT build this at ~75 designs — the monolith is simpler to keep
correct (one derivation path, no manifest/runtime skew class). Start
step 1–2 when any of:

- server boot time becomes noticeable in deploys or dev iteration,
- `/examples` exceeds ~1 MB uncompressed (~300 designs at current
  per-design size),
- the design picker needs search to be usable.

Step 3 only when import cost at boot is the residual problem after
steps 1–2.
