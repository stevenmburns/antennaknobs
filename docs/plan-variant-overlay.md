# Plan: variants as an overlay on `default_params` (incl. per-variant `ui_params`)

Status: **COMPLETE.** Merge mechanism landed 2026-07-03 (Option A); the
remaining per-variant ui derivation landed 2026-07-08 (PR #266):
`_make_example` diffs each variant's merged `ui_params` against the
default's and emits `variant_ui` with per-variant `sweep_policy` and
explicit per-param presentation hints (`params`: slider min/max/step,
precision, unit, label, hidden), which the frontend overlays on
`param_schema` for the active variant. First users: triangular_skyloop's
band_locked sweep policy; dipoles.invvee's per-variant length_factor
ranges and the dipole variant's hidden angle_deg knob. Originally scoped
2026-07-03 out of the triangular-skyloop work, where we wanted a
"band-locked" *variant* of a design but found the sweep policy is pinned
per-design, not per-variant.

**Update (2026-07-03):** built as **Option A** — a single recursive merge over
the whole param tree — rather than the two-tier "shallow for regular params,
deep for `ui_params`" of the original Part 1/Part 2 split. `merge_params` /
`resolve_variant_params` live in `builder.py`; `_variant_params`
(`web/adapter.py`) and CLI `get_builder` both delegate to the resolver. Because
`ui_params` (a `MappingProxyType`) is the only Mapping-valued param in the
catalog, the recursion matches on `collections.abc.Mapping` and its only real
effect today is to deep-merge `ui_params` — so Part 1 and Part 2's *merge* are
now one mechanism. **What remains of Part 2 is derivation only:** making
`_make_example` read the merged per-variant `ui_params` and emitting a
`variant_ui` descriptor (see below). Coverage: `tests/test_variants.py`.

## Motivation

Two problems with the current variant model:

1. **Redundancy.** A named variant must re-list *every* parameter, even ones it
   doesn't change (see delta_loop's `z100_params`/`z200_params`, which repeat
   `design_freq`/`freq`/`base` verbatim). A variant should only need to state
   what it overrides.

2. **`ui_params` can't vary per variant.** UI hints — `sweep_policy`,
   `default_view`, `target_z0`, `meas_freq_range`, `bands`, `layout` — are
   derived once from `default_params.ui_params`. So there is no way to have,
   e.g., a band-locked *variant* (band-edge sweep) alongside a wide-window
   default variant of the same antenna.

## How it works today (baseline)

Variants are **full replacements**, in two independent code paths:

- **Web:** `adapter._variant_params(cls, variant)` (`adapter.py:719`) returns
  `dict(<variant>_params)` outright, falling back to `default_params`.
  `_build_builder` (`adapter.py:443`) then iterates **only the variant's keys**
  and overlays the live request (slider) values.
- **CLI:** `get_builder` (`cli.py`, `name:variant` spec) binds
  `partial(cls, params=<variant>_params)` directly.
- **Builder:** `AntennaBuilder.__init__` does `merged = dict(FRAMEWORK_PARAMS);
  merged.update(params)` and asserts every key is in `default_params` or
  `FRAMEWORK_PARAMS`. The passed dict is used as-is, so it must be complete for
  `build_wires`.

Consequence: a *partial* variant would drop the request values for its missing
keys in `_build_builder` and crash `build_wires` on a missing attribute. Variants
are complete today only by convention.

**The frontend already merges — but only values.** `selectVariant`
(`App.tsx:1985`) seeds `seedDefaults(schema)` then overlays
`variant_values[variant]` for present keys. So the frontend does default+variant
overlay; the backend does full replacement. They are inconsistent, and it only
works because variants are complete and the request re-sends every param.

**`ui_params` derivation is default-only:** `_make_example` (`adapter.py:874`)
reads `dict(cls.default_params)["ui_params"]` and derives the schema,
`sweep_policy` (`adapter.py:924`), `default_view`, `target_z0`,
`meas_freq_range`, `bands`, and `layout` from it. Variant `ui_params` is ignored.

## Proposed change

### Part 1 — variants overlay `default_params` (built as Option A: one recursive merge)

Implemented in `builder.py` and delegated to from both call sites
(`_variant_params` in `web/adapter.py`, CLI `get_builder`):

```python
def merge_params(base, over):
    out = dict(base)
    for k, v in over.items():
        # Match Mapping, not dict: ui_params is a MappingProxyType, which is
        # a Mapping but not a dict subclass.
        if isinstance(out.get(k), Mapping) and isinstance(v, Mapping):
            out[k] = merge_params(out[k], v)   # recurse into dicts / proxies
        else:
            out[k] = v                          # scalars, tuples: replace
    return out

def resolve_variant_params(cls, variant):
    base = dict(cls.default_params)
    if variant and variant != "default":
        v = getattr(cls, f"{variant}_params", None)
        if v is not None and hasattr(v, "keys"):
            return merge_params(base, v)
    return base
```

A single recursive rule covers the whole param tree, so the original
"shallow-for-regular, deep-for-`ui_params`" two-tier split collapses into one
mechanism. Since `ui_params` is the only Mapping-valued key in the catalog, this
is behaviorally identical to that split — it just isn't special-cased.

- **Backward-compatible:** overlaying a *complete* variant dict == that dict, so
  every existing variant keeps working unchanged. Verified: `test_variants.py`
  (complete variants reproduce themselves).
- **Fixes the latent crash:** `_build_builder`'s `base` is now always the full
  key set, so a partial variant is safe.
- **Invariant preserved:** the Builder's `assert all(k in default_params …)`
  still forbids a variant introducing a *new* param.
- **One CLI-side behavior change:** a variant that omits `ui_params` (e.g.
  `twoband_fan_dipole.s07_params`) now inherits `default_params["ui_params"]`
  when built via the CLI, matching how the default (`params=None`) path already
  builds. `test_renamed_twoband_variant` was updated to expect `default ⊕ s07`;
  geometry is unaffected (`build_wires` ignores `ui_params`).

**The recursive-merge floor (tuples are replaced, not merged).**
The merge recurses into Mappings only; every non-Mapping value — scalars and
the multiband `bands` **tuple of dicts** — replaces wholesale. The limit is the
tuple representation, *not* the merge algorithm (see Option C in "Removing the
floor" below). The multiband designs store bands as a tuple:

```python
"bands": (_BAND_17_12, _BAND_15_10),   # multiband/trap_fan_dipole
"bands": (_BAND_20M, _BAND_17M, ...),  # multiband/hexbeam_5band
```

- ✅ Overriding a **top-level scalar** (`freq`, `base`, `angle_deg`) is safe and
  partial — that is all the multiband variants do today.
- ❌ You **cannot** express "override just `bands[1].trap_freq`" as a partial. A
  variant that touches one sub-band must restate the entire `bands` tuple.

The recursive merge does **not** rescue this: it recurses into Mappings, and
`bands` is a *tuple*, not a Mapping. Positional merge-by-index into a tuple is
ill-defined (length/`n_bands` changes, reordering, no key identity), so the
merge deliberately replaces tuples wholesale. The trim in Part 1b therefore
applies to top-level scalar keys; nested `bands` tuples stay whole by design.
Covered by `test_bands_tuple_replaced_wholesale`. Acceptable (no current variant
needs a sub-band partial), but documented so nobody assumes "variants are
overlays now" means they can partially override inside `bands` and get a
silently whole-tuple-replaced result. See "Removing the floor" for the escape
hatch (convert `bands` tuple → dict keyed by band).

Consumers of `_variant_params` (all verified working under merge — full
`tests/` suite green): `_build_builder`, `_design_freq_default`, params-source
export, `variant_values` serialization (all in `web/adapter.py`).

Keep serializing `variant_values` as the full merged values (frontend overlays
them onto `seedDefaults`, so full or overrides both work; full is the smaller
diff).

### Part 1b — trim redundant variants to their overrides

Once Part 1 lands, walk the catalog and trim each `<variant>_params` down to the
keys it actually changes. This is the redundancy the Motivation calls out, and
the trimmed variants become the real-world proof that partial overlay works —
i.e. the regression the new `tests/test_variants.py` case is meant to guard.

**Sequence it as its own commit, after Part 1 — not bundled in.** Part 1's whole
safety argument is "overlaying a *complete* variant == that variant, so
`test_variants.py` passes unchanged." That invariant is what makes the mechanism
change auditable. Trimming in the same commit exercises a new merge path *and*
newly-partial data at once, so a failure can't be localized. Land the mechanism
first (variants still complete, tests prove overlay ≡ replacement), then trim.

Flat targets (top-level scalar overrides — all safe under the recursive merge):

- `loops/delta_loop.py` — `z100_params` is **byte-for-byte identical** to
  `default_params` → trims to `{}`. `z200_params` → `{length_factor, angle_deg}`.
- `multiband/trap_fan_dipole.py` — all four variants are `{**default_params,
  "freq": X}` by construction → each trims to a single `{"freq": X}`.
- `dipoles/invvee.py`, `specialty/hentenna_slant.py`, `arrays/delta_looparray.py`
  — flat scalar variants; trim to their deltas.

Do **not** attempt to trim inside `bands` tuples (see the shallow-overlay floor
under Part 1) — those stay whole.

**Landed (2026-07-03):** 254 stated keys → 130 across all 40 variants; every
variant's fully-resolved params verified byte-identical (numeric equality)
before/after via a snapshot of `resolve_variant_params` over all 113 (design,
variant) pairs. See Part 1c for a latent-crash class this surfaced.

### Part 1c — make `AntennaBuilder.__init__` overlay-aware (follow-up, not yet built)

Trimming surfaced a latent crash on a path Part 1 did **not** cover. Part 1 made
the *resolvers* (`resolve_variant_params`, `_variant_params`, CLI `get_builder`)
overlay-aware, but **direct construction** — `cls(cls.<variant>_params)` — passes
the raw dict straight to `AntennaBuilder.__init__`, which replaces rather than
overlays. While variants were complete this worked by accident; once trimmed to
partial dicts, `build_wires` crashes on the missing keys (`self.base`, etc.).

Part 1b fixed the *consumers* (all in tests — `src/` already routes through the
resolvers): `test_nec_export`, `test_momwire_engine`, `test_drone` constructed
Builders directly from a variant dict as a convenient "complete preset", now
resolve the variant first.

The deeper fix is to make `__init__` itself overlay a partial `params` on
`default_params` (reusing `merge_params`), so `cls(partial_dict)` is safe
everywhere and this whole bug class disappears:

```python
def __init__(self, params=None):
    merged = dict(self.FRAMEWORK_PARAMS)
    if params is None:
        merged.update(self.__class__.default_params)
    else:
        merged.update(merge_params(self.__class__.default_params, params))
    ...
```

**Why it's a separate PR, not folded into Part 1b:** it's a Builder-semantics
change with a real interaction to settle first — the web adapter's `_build_builder`
calls `_strip_ui(...)` to drop `ui_params` before `cls(params=base)`; if
`__init__` then overlays on `default_params` (which *has* `ui_params`), the
Builder would silently re-inherit `ui_params`. Harmless in principle (build_wires
ignores it) but it needs verifying against the web path before landing. Backward
-compat otherwise holds: a complete dict overlaid on default equals itself, and a
partial dict was already a latent crash, so nothing depends on the old behavior.

### Part 2 — per-variant `ui_params` (per-field override)

**The merge half is done** (Option A above): a variant's `ui_params` already
deep-merges over the default's — `test_ui_params_deep_merge` proves a variant
carrying only `{"ui_params": {"sweep_policy": {"band_locked": True}}}` inherits
the default `anchor`/`lo_factor`/`hi_factor` and flips only `band_locked`. **What
remains is derivation:** the ui-derived hints must be recomputed *per variant*
and exposed to the frontend. Today `_make_example` still derives them from the
default only.

- **Merge depth (settled):** recursive Mapping-merge for the `ui_params`
  subtree. Tradeoff: you can add/override nested fields but cannot *replace* a
  whole nested dict wholesale — acceptable; documented. A `band_locked_params`
  variant carries *only* `ui_params`, so all regular params come from default.

- **Adapter:** `_make_example` computes `sweep_policy` (and optionally
  `default_view`, etc.) **per variant** by merging each variant's `ui_params`
  over the default's. Emit a new descriptor field:

  ```
  variant_ui: { <variant>: { sweep_policy: SweepPolicy, ... }, ... }
  ```

  Keep the existing top-level fields as the **default** variant's values for
  backward compat. Design `variant_ui` as an extensible per-variant map so more
  hints can move per-variant later without another `/examples` contract change.

- **Server:** serialize `variant_ui` in the `/examples` payload.

- **Frontend:** look up by active variant, falling back to the design-level value:

  ```ts
  const policy =
    currentExample.variant_ui?.[currentVariant]?.sweep_policy
    ?? currentExample.sweep_policy;
  ```

  Add the `variant_ui` type. (`App.tsx:3037` is the sweep-policy read site.)

## Scope decision to settle before building Part 2

Keep the per-variant override to `sweep_policy` (+ maybe `default_view`) only,
or make *all* ui hints variant-aware? Recommendation: start narrow
(`sweep_policy`) behind the extensible `variant_ui` map; generalize when a second
real use case appears. The schema itself stays derived from `default_params`
(one rendered form); variants override values + ui hints, not structure.

## Removing the floor (only if a sub-band partial is ever needed)

The floor is imposed by the `bands` *tuple* representation, not the merge. Three
options were weighed:

- **A (built):** one recursive Mapping-merge. Uniform semantics, but tuples still
  replace wholesale — the floor stays.
- **B (rejected):** teach the merge to descend into tuples positionally. Removes
  the floor but fakes key-identity the data doesn't have — `n_bands`/length
  changes become ambiguous, reordering silently corrupts, needs a no-op sentinel
  per slot. Not worth it.
- **C (deferred escape hatch):** change the data shape — `bands` tuple → dict
  keyed by band (`{"17_12": {...}, "15_10": {...}}`). Then A's recursive merge
  works at every depth with explicit identity. Cost is a data-model migration
  through the machinery that assumes positional bands: multiband `build_wires`
  iteration, the schema adapter's `ParamGroupSpec`/`repeat_count`/`max_repeats`,
  the frontend's preallocated group instances, and serialization. Do this only
  when a real sub-band-partial use case appears.

## Effort / risk / sequencing

| Part | Scope | Risk | Effort | Status |
|------|-------|------|--------|--------|
| 1 | `merge_params`/`resolve_variant_params` in `builder.py`; `_variant_params` + CLI delegate; `tests/test_variants.py` | Low — backward-compatible, and fixes the partial-variant crash | ~1–2h | **done** |
| 1b | trim redundant variants to their overrides | Low | ~1h | not started |
| 2 | per-variant ui *derivation* + `variant_ui` descriptor field + serialize + frontend lookup + types (merge already done) | Medium — changes the `/examples` contract | ~½ day | not started |

**Sequence:** Part 1 landed. Part 1b (trim) and Part 2 (derivation) both build on
it and are independent of each other. The **band-locked skyloop variant** lands
as a 3-line `band_locked_params` on `loops.triangular_skyloop` once Part 2's
derivation is in.

## Test impact

- `tests/test_variants.py` — primary coverage. Extended with overlay-semantics
  tests: partial overlay, partial ≡ full equivalent, complete-reproduces-self,
  `ui_params` deep-merge, and `bands`-tuple-replaced-wholesale (the floor).
  `test_renamed_twoband_variant` updated for the `ui_params`-inheritance change.
- Web: `tests/test_web_server.py` / `test_design_schemas.py` for the `/examples`
  descriptor shape after Part 2 (`variant_ui`).

## Interim option (if the band-locked skyloop is wanted before this lands)

A separate sibling design `loops.triangular_skyloop_banded` that subclasses the
base Builder and overrides only `default_params.ui_params` to add
`sweep_policy: {band_locked: True}`. Works today with no architecture change, but
shows as its own antenna in the catalog rather than a variant of the existing one.
