import type { Projection } from "./view";

// Schema served by `GET /examples`. The backend's web/examples/_base.py
// owns the source of truth; this type just mirrors the JSON shape.
export type SchemaEnumOption = {
  value: string;
  label: string;
  // Free-form metadata. Fan_dipole's band entries carry freq_min /
  // freq_max / freq_default for range_from_enum_option + on_change_set.
  [key: string]: unknown;
};

export type SchemaParamSpec = {
  name: string;
  label: string;
  default: number | string | boolean;
  kind: "float" | "int" | "bool" | "enum";
  min: number | null;
  max: number | null;
  step: number | null;
  precision: number;
  unit: string | null;
  visible_when: { name: string; op: string; value: number } | null;
  enum_options?: SchemaEnumOption[] | null;
  range_from_enum_option?: { param: string; min_key: string; max_key: string } | null;
  on_change_set?: { set: string; from_enum_key: string } | null;
  linked_to_design_freq?: boolean;
  // Flat-schema sibling of the group-level link: when this scalar
  // changes, push the current value of the named sibling param into
  // measFreq. Self-reference is allowed (and used by freq_NN params
  // in multi-band antennas).
  link_meas_freq_to_param?: string | null;
  // Optional explicit placement in the param grid (1-indexed CSS grid
  // lines). When present the field opts out of auto-flow and lands at the
  // given row/col, optionally spanning multiple tracks. null = auto-flow.
  layout?: KnobLayout | null;
};

// Per-knob grid placement. All fields optional; mapped onto inline
// grid-row / grid-column. Pairs with ExampleDescriptor.layout.columns.
export type KnobLayout = {
  row?: number | null;
  col?: number | null;
  row_span?: number | null;
  col_span?: number | null;
};

export type SchemaParamGroupSpec = {
  kind: "group";
  name: string;
  label_template: string;
  repeat_count: string;
  max_repeats: number;
  params: SchemaItem[];
  default_overrides: { [param: string]: unknown }[];
  // When set, names a sibling param inside this group's `params`
  // (typically "freq") whose per-instance value the frontend pushes
  // into the global measFreq state on every touch of any leaf inside
  // that instance. Gated by the linkMeas toggle.
  link_meas_freq_to_param?: string | null;
};

export type SchemaItem = SchemaParamSpec | SchemaParamGroupSpec;

export function isGroup(item: SchemaItem): item is SchemaParamGroupSpec {
  return (item as SchemaParamGroupSpec).kind === "group";
}

// State for a schema-driven antenna: nested map where scalars are
// numbers (float/int) or strings (enum), and groups are arrays of
// child bags (one per instance, pre-allocated to max_repeats).
export type ParamValueBag = {
  [key: string]: number | string | boolean | ParamValueBag[];
};

export type ResultFieldSpec = {
  field: string;
  label: string;
  precision: number;
  unit: string | null;
};

export type SweepPolicy = {
  anchor: "design_freq" | "meas_freq";
  lo_factor: number;
  hi_factor: number;
  band_locked?: boolean;
};

export type BandSpec = {
  key: string;
  label: string;
  freq_mhz: number;
  min_mhz: number;
  max_mhz: number;
};

export type ResultGroupItem = {
  kind: "group";
  name: string;
  label_template: string;
  fields: ResultFieldSpec[];
};
export type ResultSchemaItem = ResultFieldSpec | ResultGroupItem;

export type ExampleDescriptor = {
  name: string;
  label: string;
  multi_feed: boolean;
  param_schema: SchemaItem[];
  result_schema: ResultSchemaItem[];
  bands: BandSpec[];
  meas_freq_range_mhz: [number, number] | null;
  /** Null for a deferred (user) design with no override — the real view is
   *  auto-detected and arrives with the first geometry/solve response. */
  default_view: Projection | null;
  /** The freq this antenna is naturally designed for. Used by the
   *  band-snap-on-example-change effect; null = no preferred freq. */
  default_freq: number | null;
  default_design_freq: number | null;
  /** Recommended solver backend for this design (e.g. "arrayblock" for grid
   *  arrays). The active slot's backend is seeded from this on selection
   *  unless the user has manually picked a backend. null = keep the UI
   *  default. Typed as a plain string because the server may name a backend
   *  this UI has retired (e.g. "triangular"); run it through
   *  normalizeBackend before use. */
  default_backend: string | null;
  /** Backend allowlist when the design is restricted to specific solvers,
   *  else null. Today: designs with PortAtEnd junction ports report
   *  ["bspline"] — only the dense B-spline solver implements junction
   *  ports (momwire#172), and NEC-2 has no equivalent card (issue #579).
   *  Derived server-side from the design's network spec. The UI disables
   *  the other backend tabs and withholds the solve with a hard (not
   *  "solve anyway") gate when the active backend is disallowed; the
   *  solvers' errors remain the enforcement. */
  requires_backends: string[] | null;
  /** Design-side inputs to the cross-axis constraints (#1006 G2-5). Optional
   *  so a server predating them reads as "not measured", which the gate
   *  treats as no claim — the same non-answer `requires_backends: null` makes. */
  has_stepped_radius_junction?: boolean;
  has_buried_wire?: boolean;
  /** Near-open high-Q feed (antennaknobs#478): the Sin-Galerkin solver's
   *  "Converged" (point-gap) feed model is recommended for this design —
   *  it collapses the cross-basis residual by 2-3 orders on this class
   *  (momwire#213). Drives the recommendation hint in the Sin-Galerkin
   *  feed-model control; declared statically in the design's ui_params.
   *  Absent/undefined on older servers → treat as false. */
  converged_feed_suggested?: boolean;
  /** Ground model this design REQUIRES to mean anything ("sommerfeld" for
   *  the buried-wire designs — conductors below z = 0 only exist under a
   *  Sommerfeld half-space; the refl-coef default refuses them by name).
   *  On selection the UI auto-selects finite ground + the Sommerfeld
   *  method and notes it in the ground panel. Absent/null = no
   *  requirement. Declared statically in the design's ui_params. */
  ground_requirement?: string | null;
  /** True when the Builder has a `design_freq` param that scales
   *  geometry (design_freq-sized designs). When false, the design-freq
   *  band-tab row is hidden because dragging it would be a no-op. */
  has_design_freq: boolean;
  /** Alternate seed dicts on the Builder, e.g. ["default", "opt"].
   *  The bare name is what the frontend sends back in `variant`.
   *  Single-entry lists ("default") hide the selector. */
  variants: string[];
  /** Per-variant param values, keyed by variant name. Lets the UI
   *  reset the schema sliders + design freq when the user switches
   *  variants. Complex-valued params arrive as {re, im}. */
  variant_values: { [variant: string]: { [key: string]: unknown } };
  sweep_policy: SweepPolicy;
  /** Informational note shown under the antenna selector — deck-backed
   *  designs list the NEC cards the import recorded but did not apply.
   *  null (the norm) renders nothing. */
  notes?: string | null | undefined;
  /** Per-variant UI-hint overrides, keyed by variant name. Only variants
   *  whose derived hints differ from the design-level values appear; look up
   *  the active variant and fall back to the top-level field (e.g.
   *  `sweep_policy`) for any variant not listed. */
  variant_ui?: {
    [variant: string]: {
      sweep_policy?: SweepPolicy;
      /** Explicit per-param presentation overrides for this variant
       *  (slider min/max/step, precision, unit, label), overlaid on
       *  param_schema entries by name. Values come from variant_values,
       *  never from here. */
      params?: {
        [name: string]: Partial<
          Pick<
            SchemaParamSpec,
            "min" | "max" | "step" | "precision" | "unit" | "label"
          >
        > & { hidden?: boolean };
      };
    };
  };
  /** Grid-level layout for the top-level knob rail. {columns: N} pins the
   *  grid to a fixed column count so per-knob `layout.col` positions are
   *  stable. null = responsive auto-flow packing. */
  layout?: { columns?: number | null } | null;
};

// Design names are `family.design` (e.g. "dipoles.invvee"). The selector
// groups by that family prefix; this fixes display order + labels and keeps
// any unknown family rendering last under its bare name.
export const FAMILY_ORDER = [
  "user", "dipoles", "loops", "verticals", "beams", "wire",
  "broadband", "multiband", "specialty", "arrays",
] as const;
export const FAMILY_LABELS: Record<string, string> = {
  user: "Your designs", dipoles: "Dipoles", loops: "Loops",
  verticals: "Verticals", beams: "Beams", wire: "Wire / traveling-wave",
  broadband: "Broadband", multiband: "Multiband", specialty: "Specialty",
  arrays: "Arrays",
};
// Extra search keywords so cryptic or historically-named designs are findable
// by something other than their terse name (the old pre-regroup names live
// here too, since names changed in the family reorg).
export const SEARCH_KEYWORDS: Record<string, string> = {
  "broadband.g5rv": "doublet ladder line multiband all band",
  "broadband.t2fd": "terminated tilted folded dipole all band",
  "broadband.lpda": "log periodic dipole array beam",
  "broadband.discone": "vhf uhf scanner wideband",
  "wire.zepp": "end fed zeppelin",
  "wire.rhombic": "traveling wave terminated",
  "wire.vbeam": "v beam traveling wave",
  "wire.lazy_h": "lazy-h collinear",
  "verticals.jpole": "j-pole slim jim",
  "verticals.bobtail": "bobtail curtain",
  "beams.yagi": "yagi-uda beam directional",
  "beams.moxon": "moxon rectangle beam",
  "loops.quad": "cubical quad loop",
};

export const familyOf = (name: string): string => name.split(".")[0];

export function familyRank(fam: string): number {
  const i = (FAMILY_ORDER as readonly string[]).indexOf(fam);
  return i === -1 ? FAMILY_ORDER.length : i;
}

export function matchesQuery(ex: ExampleDescriptor, q: string): boolean {
  if (!q) return true;
  const hay = `${ex.name} ${ex.label} ${familyOf(ex.name)} ${
    SEARCH_KEYWORDS[ex.name] ?? ""
  }`.toLowerCase();
  // Case-insensitive on both sides (issue #674): callers used to have to
  // pre-lowercase the query, which was a silent-miss footgun for any new
  // call site.
  return hay.includes(q.toLowerCase());
}

export function applyVisibility(spec: SchemaParamSpec, values: ParamValueBag): boolean {
  const v = spec.visible_when;
  if (!v) return true;
  const cur = values[v.name];
  if (cur == null) return true;
  // Visibility comparisons only make sense for numeric controls today
  // (e.g. yagi's `n_directors > 0`). Enum-valued conditions would need
  // a different comparator — flag in v1 but punt on implementation.
  if (typeof cur !== "number") return true;
  switch (v.op) {
    case "eq": return cur === v.value;
    case "ne": return cur !== v.value;
    case "gt": return cur > v.value;
    case "ge": return cur >= v.value;
    case "lt": return cur < v.value;
    case "le": return cur <= v.value;
    default: return true;
  }
}

// Seed defaults for one ParamValueBag from a flat list of schema items.
// `overrides` (optional) overlays per-instance defaults from a group's
// default_overrides[i] entry — used when seeding a group instance.
export function seedDefaults(
  schema: SchemaItem[],
  overrides?: { [k: string]: unknown },
): ParamValueBag {
  const out: ParamValueBag = {};
  for (const item of schema) {
    if (isGroup(item)) {
      // CONTRACT (issue #674): a nested group always self-seeds from its own
      // default_overrides; a parent override bag never reaches it. Overrides
      // are per-scalar-leaf by design, and the adapter cannot emit nested
      // groups at all today (audited: 0 across all 100 designs) — this
      // branch exists only so a future nested schema fails soft, not wrong.
      const arr: ParamValueBag[] = [];
      for (let i = 0; i < item.max_repeats; i++) {
        arr.push(seedDefaults(item.params, item.default_overrides[i]));
      }
      out[item.name] = arr;
    } else {
      // An override wins over the leaf default, but both go through the same
      // per-kind coercion (issue #674): the server builds default_overrides
      // from the Builder's own instance dicts, so types agree by
      // construction today — coercing here keeps a heterogeneously-typed
      // instance (e.g. an int where instance 0 had a float, or a stringified
      // number) from leaking a wrong-typed value into the ParamValueBag.
      const ov = overrides?.[item.name];
      const raw = ov !== undefined ? ov : item.default;
      if (item.kind === "enum") {
        out[item.name] = String(raw);
      } else if (item.kind === "bool") {
        out[item.name] = Boolean(raw);
      } else {
        out[item.name] = Number(raw);
      }
    }
  }
  return out;
}

// Overlay freshly seeded defaults UNDER an existing bag (issue #867): tuned
// values always win; only keys the bag lacks — a param the design's author
// just added, seen when reloading an edited user design — take the seeded
// default. Group instance arrays merge per index, so a new scalar inside an
// existing group instance lands too; a shrunk max_repeats drops the surplus
// instances with it. Returns `existing` by identity when nothing merged, so
// unchanged bags don't churn state identity on every /examples fetch.
export function mergeSeededDefaults(
  seeded: ParamValueBag,
  existing: ParamValueBag,
): ParamValueBag {
  let changed = false;
  const out: ParamValueBag = { ...existing };
  for (const [key, seedVal] of Object.entries(seeded)) {
    const cur = existing[key];
    if (cur === undefined) {
      out[key] = seedVal;
      changed = true;
    } else if (Array.isArray(seedVal) && Array.isArray(cur)) {
      const merged = seedVal.map((inst, i) =>
        cur[i] !== undefined ? mergeSeededDefaults(inst, cur[i]) : inst,
      );
      if (
        merged.length !== cur.length ||
        merged.some((m, i) => m !== cur[i])
      ) {
        out[key] = merged;
        changed = true;
      }
    }
  }
  return changed ? out : existing;
}

// Walk the schema collecting (param, value) pairs for every leaf marked
// `linked_to_design_freq`. Fan_dipole's first band's freq is the
// canonical example: when it changes, the global design frequency
// should follow.
// The design-switch band snap, as a pure function of the example descriptor:
// the band containing the design's native freq (else the first band — which
// the adapter's synthetic-band rule keeps from being a wrong-by-decades 160 m
// fallback, issue #390) and the frequency to park designFreq on. Shared by
// the snap effect on currentExample AND the antenna-switch preview fetch,
// which fires in the same commit and would otherwise race the snapped state
// by one render, fetching its preview with the PREVIOUS design's freqs.
export function snapForExample(
  ex: ExampleDescriptor | undefined,
): {
  bandKey: string;
  freq: number;
  measBandKey: string;
  measFreq: number;
  offBand: boolean;
} | null {
  if (!ex || ex.bands.length === 0) return null;
  // The measurement dial parks on the design's native operating freq;
  // designFreq parks on its STOCK design_freq. They're almost always the
  // same value, but off-band designs (a 10 m antenna deliberately worked
  // on 12 m through a tuner, e.g. inverted_l_tmatch) differ — snapping
  // designFreq to the operating freq would silently RESIZE the geometry
  // and destroy the design's premise.
  const m = ex.default_freq;
  const d = ex.default_design_freq ?? m;
  const findBand = (f: number | null) =>
    f != null ? ex.bands.find((b) => f >= b.min_mhz && f <= b.max_mhz) : null;
  // Use the exact freq when a band contains it; otherwise the band's own
  // default. This avoids the small designFreq drift that would happen if
  // we always snapped to band.freq_mhz (e.g. dipole's 28.57 → 10m band's
  // 28.470).
  const dBand = findBand(d);
  const dTarget = dBand ?? ex.bands[0];
  const designFreq = dBand && d != null ? d : dTarget.freq_mhz;
  const mBand = findBand(m);
  const mTarget = mBand ?? dTarget;
  const measFreq = mBand && m != null ? m : mTarget.freq_mhz;
  return {
    bandKey: dTarget.key,
    freq: designFreq,
    measBandKey: mTarget.key,
    measFreq,
    offBand: measFreq !== designFreq,
  };
}

// Per-knob optimisation settings (per geometry, per param name). `vary` marks
// the knob as a free variable the optimiser may change; opt extents bound the
// search; display extents are the knob's own slider range; step is the manual
// turn granularity (the optimiser itself is continuous). Absent for a knob =
// schema defaults.
export type KnobOpt = {
  vary: boolean;
  optMin: number;
  optMax: number;
  dispMin: number;
  dispMax: number;
  step: number;
};

export function findLinkedDesignFreq(
  schema: SchemaItem[],
  values: ParamValueBag,
): number | null {
  for (const item of schema) {
    if (isGroup(item)) {
      const instances = values[item.name];
      if (!Array.isArray(instances) || instances.length === 0) continue;
      // Only the first instance's linked param drives design freq.
      // Extending to "any instance" needs a tie-break policy; not
      // worth designing until a second antenna asks for it.
      const found = findLinkedDesignFreq(item.params, instances[0]);
      if (found != null) return found;
    } else if (item.linked_to_design_freq) {
      const v = values[item.name];
      if (typeof v === "number") return v;
    }
  }
  return null;
}

// Deep-immutable path setter. ParamForm calls with paths like
// ["bands", 2, "freq"] for nested groups, or ["angle_deg"] for
// scalars. Recursive clone along the path so React sees a new
// reference at every level it watches.
export function setValueAtPath(
  node: unknown,
  path: (string | number)[],
  value: number | string | boolean,
): unknown {
  if (path.length === 0) return value;
  const [head, ...rest] = path;
  if (typeof head === "number") {
    const arr = ((node as unknown[]) ?? []).slice();
    arr[head] = setValueAtPath(arr[head], rest, value);
    return arr;
  }
  const obj = { ...((node as Record<string, unknown>) ?? {}) };
  obj[head] = setValueAtPath(obj[head], rest, value);
  return obj;
}

// Schema-driven meas-freq follow, as a pure resolution over the just-set
// value tree. Two variants:
//   * group leaf: `path = [groupName, instanceIdx, leafName]` and the
//     group declares `link_meas_freq_to_param` — resolve to that
//     instance's value of the named sibling.
//   * flat scalar: `path = [paramName]` and the ParamSpec declares
//     `link_meas_freq_to_param` — resolve to the current value of the
//     named sibling (possibly itself). Used by multi-band antennas with
//     parallel length_NN / freq_NN flat sliders (antennaknobs's
//     fandipole).
// Returns null when nothing should follow (no link declared, or the
// linked value isn't numeric); the caller decides whether/how to apply it
// (e.g. gating on the linkMeas toggle and calling setMeasFreq).
export function linkedMeasFreqFor(
  ex: ExampleDescriptor | undefined,
  path: (string | number)[],
  newRoot: ParamValueBag,
): number | null {
  if (!ex) return null;
  if (path.length === 1 && typeof path[0] === "string") {
    const paramName = path[0];
    const spec = ex.param_schema.find(
      (s) => !isGroup(s) && s.name === paramName,
    ) as SchemaParamSpec | undefined;
    const linked = spec?.link_meas_freq_to_param;
    if (!linked) return null;
    const freqValue = newRoot[linked];
    return typeof freqValue === "number" ? freqValue : null;
  }
  if (path.length < 3) return null;
  const groupName = path[0];
  const instanceIdx = path[1];
  if (typeof groupName !== "string" || typeof instanceIdx !== "number") return null;
  const group = ex.param_schema.find(
    (s) => isGroup(s) && s.name === groupName,
  ) as SchemaParamGroupSpec | undefined;
  if (!group || !group.link_meas_freq_to_param) return null;
  const instances = newRoot[groupName];
  if (!Array.isArray(instances)) return null;
  const inst = instances[instanceIdx];
  if (!inst) return null;
  const freqValue = inst[group.link_meas_freq_to_param];
  return typeof freqValue === "number" ? freqValue : null;
}

// param_schema with a variant's explicit presentation overrides
// (variant_ui[variant].params) overlaid per param — e.g. invvee's
// long-wire variants carry their own length_factor slider range. Feeds
// the knob rail and the per-knob optimiser menu so both see
// variant-correct bounds; value seeding stays on the raw schema
// (defaults/values are variant_values' job).
export function overlaySchemaForVariant(
  example: ExampleDescriptor | undefined,
  variant: string,
): SchemaItem[] {
  if (!example) return [];
  const over = example.variant_ui?.[variant]?.params;
  if (!over) return example.param_schema;
  return example.param_schema
    .map((item) =>
      !isGroup(item) && over[item.name]
        ? { ...item, ...over[item.name] }
        : item,
    )
    .filter(
      // A variant can hide a base-visible knob (e.g. invvee:dipole's
      // angle_deg — flat by definition, value pinned at 0 by the
      // variant). Display-only: the value still rides variant_values.
      (item) => isGroup(item) || !(item as { hidden?: boolean }).hidden,
    );
}

// Picker contents: filter `examples` by `query` (always keeping `selected`
// visible so the <select> value stays valid), then group by family in
// FAMILY_ORDER.
export type ExampleGroup = {
  fam: string;
  label: string;
  items: ExampleDescriptor[];
};

export function groupExamplesForPicker(
  examples: ExampleDescriptor[],
  selected: string,
  query: string,
): ExampleGroup[] {
  const visible = examples.filter(
    (ex) => ex.name === selected || matchesQuery(ex, query),
  );
  const byFam = new Map<string, ExampleDescriptor[]>();
  for (const ex of visible) {
    const fam = familyOf(ex.name);
    (byFam.get(fam) ?? byFam.set(fam, []).get(fam)!).push(ex);
  }
  return [...byFam.entries()]
    .map(([fam, items]) => ({
      fam,
      label: FAMILY_LABELS[fam] ?? fam,
      items: items.sort((a, b) => a.label.localeCompare(b.label)),
    }))
    .sort((a, b) => familyRank(a.fam) - familyRank(b.fam));
}

// The effective per-knob optimiser settings, seeded from the schema: opt
// extents = slider bounds, step = schema step, not varying. The caller
// overlays any explicitly stored KnobOpt entry on top of this default.
export function defaultKnobOpt(schema: SchemaItem[], name: string): KnobOpt {
  const s = schema.find(
    (x): x is SchemaParamSpec => !isGroup(x) && x.name === name,
  );
  const min = s?.min ?? 0;
  const max = s?.max ?? 1;
  return {
    vary: false,
    optMin: min,
    optMax: max,
    dispMin: min,
    dispMax: max,
    step: s?.step ?? 0.001,
  };
}
