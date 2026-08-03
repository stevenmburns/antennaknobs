// Backend selector, rendered entirely from the roster GET /capabilities
// serves (issue #628). There is deliberately NO roster literal in this file:
// the server's `_BACKENDS` in web/adapter.py is the single registry, and the
// duplication this replaces failed by *silent absence* — sinusoidal-galerkin
// landed server-side with both repos' CI green and no tab in the UI
// (#626/#627). Registering a solver there is now the whole change.
//
// Per-backend `model_options` are forwarded to the server's _make_momwire_sim;
// the served option keys ARE the snake_case constructor kwargs, so a generic
// knob cannot land under the wrong wire key.

/** One generic numeric solver knob, rendered by the options-schema loop in
 *  BackendConfigModal. `key` is both the client-side opts key and the wire
 *  kwarg. */
export type BackendOptionField = {
  key: string;
  label: string;
  min: number;
  max: number;
  step: number;
  default: number;
};

/** A served roster entry. Mirrors adapter.backend_roster(); snake_case
 *  because it is wire data, not a local shape. */
export type BackendEntry = {
  name: string;
  label: string;
  /** "pynec" rides the separate `solver: "pynec"` request field and never
   *  `momwire_model`; everything else is a momwire model name. */
  kind: "momwire" | "pynec";
  supports_ground: boolean;
  options_schema: BackendOptionField[];
  /** Bespoke panel hint — the knobs no numeric renderer can carry. Null for
   *  a backend whose whole surface is generic. */
  panel: string | null;
  default_n_per_wire: number;
  accelerator: boolean;
  dense_family: boolean;
};

export type BackendRoster = BackendEntry[];

// Panel hints, as served. Named constants so the bespoke components are
// selected by the server's hint rather than by backend name.
export const PANEL_BSPLINE = "bspline";
export const PANEL_SIN_GALERKIN = "sin-galerkin";
export const PANEL_PYNEC = "pynec";

export function hasBSplinePanel(b: BackendEntry): boolean {
  return b.panel === PANEL_BSPLINE;
}

export function backendSupportsGround(b: BackendEntry): boolean {
  return b.supports_ground;
}

// Every ground-capable backend supports terrain, so this is derived rather
// than a second served flag. Momwire applies the per-facet far field
// natively; PyNEC runs the hybrid (issue #553): NEC solves the currents over
// crest-medium Sommerfeld — exactly what the terrain recipe feeds the current
// solve anyway — and the server's cut physics applies the facet reflection to
// those currents.
export function backendSupportsTerrain(b: BackendEntry): boolean {
  return b.supports_ground;
}

// A design/solver combo is "inappropriate" when the solver is a poor fit: a
// dense solver (or PyNEC) on a large array is very slow, an accelerator
// (array-block / H-matrix) on a single-element design is pure overhead, and
// on a benchmark-class mesh (thousands of segments) every dense-family solver
// is minutes per solve where sinusoidal (or PyNEC) is seconds. `rec` is the
// server's recommended backend (array-block for grid arrays, a cheap dense-free
// momwire solver for huge meshes, else null) — read through its own roster
// flags so the policy follows the registry instead of a name list.
export function comboInappropriate(
  b: BackendEntry,
  rec: BackendEntry | null,
): boolean {
  if (rec?.accelerator) return !b.accelerator; // an array wants an accelerator
  // A cheap momwire reference solver was recommended: the mesh is
  // benchmark-class, so every dense-family solver is the wrong tool.
  if (rec && rec.kind === "momwire" && !rec.dense_family) return b.dense_family;
  return b.accelerator; // everything else doesn't need one
}

// Per-design backend allowlist (`requires_backends` on the descriptor —
// e.g. ["bspline"] for designs with PortAtEnd junction ports, which only
// the B-spline solver implements; NEC-2 has no equivalent card at all).
// null/undefined = no restriction. Unlike a solver the server doesn't offer
// at all (#429) this is per-design, and unlike comboInappropriate it is a
// HARD incompatibility: the disallowed solvers raise, so the gate offers
// "switch", never "solve anyway".
export function backendAllowed(
  b: BackendEntry,
  required: string[] | null | undefined,
): boolean {
  return !required || required.includes(b.name);
}

// One-line explanation for why a design is backend-restricted, used by the
// disabled tabs' tooltip and the hard withhold gate. Today the only
// restriction cause is junction ports, so the copy is specific; broaden it
// if _required_backends ever grows another cause.
export const RESTRICTED_BACKEND_REASON =
  "This design attaches network elements at conductor ends (junction-node " +
  "ports) — only the B-spline and sinusoidal-Galerkin solvers implement " +
  "them, and NEC-2 has no equivalent card.";

export function findBackend(
  roster: BackendRoster,
  name: string | null | undefined,
): BackendEntry | null {
  if (!name) return null;
  return roster.find((b) => b.name === name) ?? null;
}

// Coerce a server-supplied backend name into an entry of the served roster.
// "triangular" was retired from the registry (the server still accepts it and
// may still recommend it, e.g. from an older adapter or a saved design hint):
// map it to "bspline", the default working solver on the same dense path.
// Anything the roster doesn't carry — including PyNEC on a server without
// pynec-accel — falls back to null ("no recommendation") so a name this
// server can't honour never reaches state or the wire.
export function normalizeBackend(
  name: string | null | undefined,
  roster: BackendRoster,
): BackendEntry | null {
  if (!name) return null;
  return findBackend(roster, name === "triangular" ? "bspline" : name);
}

export type FeedModel = "segment" | "point";

// Bespoke B-spline panel state (PANEL_BSPLINE). Not derivable from a numeric
// options_schema: degree is a tab pair, smoothing and enrichment are
// checkbox-gated sub-forms, and the variant is an enum select that gates two
// further knobs.
export type BSplineOpts = {
  degree: 1 | 2;
  nQpPair: number;
  feedSmoothingFactor: number | null; // null = sharp delta-gap
  useSingularEnrichment: boolean;
  // "raw"      → Φ_sing(t) = t·log(t), PR #45/#47 original shape.
  // "stable"   → Φ_sing − bubble-subspace L²-projection: faster large-N
  //              convergence on dominant-pair K=3 junctions; larger
  //              small-N transient; loses Y-fixture cusp benefit. d=1
  //              collapses to raw bit-exact.
  // "tikhonov" → raw basis + λ·s·I penalty on Z_ee at solve time.
  //              λ→0 is raw; λ→∞ kills enrichment. λ=0.1 preserves
  //              Y-fixture cusp; λ=1.0 fully suppresses the small-N
  //              transient on dominant-pair K=3 junctions but loses Y cusp.
  // "auto"     → two-pass: solve once without enrichment, measure
  //              tap_ratio at each K≥3 junction, apply raw enrichment
  //              only where tap_ratio > autoTapRatioThreshold. Cleanly
  //              separates dominant-pair K=3 (tap_ratio ≈ 0.16) from
  //              balanced 3-way (Y ≈ 0.50). The selectivity that
  //              raw/stable/tikhonov can't deliver algebraically.
  enrichmentVariant: "raw" | "stable" | "tikhonov" | "auto";
  tikhonovLambda: number;
  autoTapRatioThreshold: number;
  nQpSing: number;
  enrichmentMinK: number;
  nQpSource: number;
};

export const BSPLINE_DEFAULT_OPTS: BSplineOpts = {
  degree: 2,
  nQpPair: 4,
  feedSmoothingFactor: null,
  useSingularEnrichment: false,
  enrichmentVariant: "raw",
  tikhonovLambda: 0.1,
  autoTapRatioThreshold: 0.3,
  nQpSing: 32,
  enrichmentMinK: 3,
  nQpSource: 16,
};

// The one common wire radius; every backend's gear menu offers it next to
// segments/wire, whose per-backend default the roster carries.
export const DEFAULT_WIRE_RADIUS = 0.0005;

// One slot's solver settings. `schema` holds the served generic knobs keyed
// by wire key; the two optional members are the bespoke panels' state,
// present exactly when the entry names that panel.
export type BackendOpts = {
  nPerWire: number;
  wireRadius: number;
  schema: Record<string, number>;
  bspline?: BSplineOpts;
  // Sin-Galerkin only (PANEL_SIN_GALERKIN, issue #640, momwire#192).
  // "segment" = NEC-compatible (NEC's segment-wide gap — reproduces
  // NEC/EZNEC behaviour, including the reactance walk with mesh density);
  // "point" = Converged (zero-width gap — converges to the B-spline answer;
  // recommended for near-open high-Q designs, momwire#213). Deliberately not
  // offered on plain sinusoidal: the point gap has no collocation RHS
  // (momwire#212), so that solver's roster entry names no panel.
  feedModel?: FeedModel;
};

/** A backend's stock options: served numeric defaults plus the bespoke
 *  panel's own defaults. */
export function defaultOptsFor(b: BackendEntry): BackendOpts {
  const opts: BackendOpts = {
    nPerWire: b.default_n_per_wire,
    wireRadius: DEFAULT_WIRE_RADIUS,
    schema: Object.fromEntries(b.options_schema.map((f) => [f.key, f.default])),
  };
  if (b.panel === PANEL_BSPLINE) opts.bspline = { ...BSPLINE_DEFAULT_OPTS };
  // The solver's own default; the gear menu recommends "point" (Converged)
  // on near-open designs (#640).
  if (b.panel === PANEL_SIN_GALERKIN) opts.feedModel = "segment";
  return opts;
}

// Three abstract solver slots. Each holds one backend choice and its
// options; the user picks A/B/C with the row of buttons, configures the
// inhabitants from the per-slot gear menu. Lets the same UI compare
// e.g. "B-spline d=2 @ N=15" against "B-spline d=1 @ N=20" without
// losing either setup.
export type Slot = "A" | "B" | "C";
export const SLOT_ORDER: Slot[] = ["A", "B", "C"];

export type SlotConfig = {
  backend: BackendEntry;
  opts: BackendOpts;
};

// Display label for a configured backend: B-spline-panel entries carry their
// spline degree so two b-spline slots (the default A d=2 / B d=1 pair) stay
// distinguishable at a glance.
export function backendDisplayLabel(b: BackendEntry, opts: BackendOpts): string {
  if (b.panel === PANEL_BSPLINE)
    return `${b.label} d=${opts.bspline?.degree ?? BSPLINE_DEFAULT_OPTS.degree}`;
  // Surface the non-default feed model on the slot chip: two Sin-Galerkin
  // slots differing only in feed model must be tellable apart at a glance.
  if (b.panel === PANEL_SIN_GALERKIN && opts.feedModel === "point")
    return `${b.label} (converged)`;
  return b.label;
}

/** Seed for one default slot: a backend NAME (resolved against the served
 *  roster, never assumed present) plus the deviations from that backend's
 *  stock options. */
export type SlotSeed = {
  backend: string;
  nPerWire?: number;
  bspline?: Partial<BSplineOpts>;
};

export const DEFAULT_SLOT_SEEDS: Record<Slot, SlotSeed> = {
  // A is the default working solver: B-spline d=2 — most accurate per
  // unknown, converged at a small odd N (interior knot at the feed), and
  // its impedance solve honours finite grounds (Triangular, the old,
  // now-retired default, folded them to the PEC image). N=15 per the
  // basis-convergence census (docs/status/2026-07-20): within 2% of the
  // basis-agreed limit on 50/66 scorable designs (N=21 buys only 3 more,
  // all within 2.3%), patterns within 0.05 dB of the fine-mesh reference,
  // ~35% faster ticks. Odd parity keeps the feed's interior knot.
  A: { backend: "bspline", nPerWire: 15 },
  // B is the cross-check basis: B-spline d=1 needs a larger N to reach
  // the same answer (slower), which is what makes agreement with A a
  // meaningful second opinion rather than the same solve twice. N=20
  // trades cross-check tightness for speed (within 2% of the limit on
  // 45/66 vs 55/66 at the old N=40 — disagreement with A beyond a couple
  // of percent warrants raising N before suspecting the design).
  B: { backend: "bspline", nPerWire: 20, bspline: { degree: 1 } },
  C: { backend: "pynec" },
};

// Resolve a seed against the served roster. A seed naming a backend this
// server doesn't offer (slot C on an install without pynec-accel, #429)
// falls back to the roster's first entry — the same tolerance the terrain
// panel applies to a parked preset name (#560). Falling back to the head of
// the served order rather than a hardcoded name is what keeps this file free
// of a second roster: the server puts its plainest solver first.
export function slotFromSeed(seed: SlotSeed, roster: BackendRoster): SlotConfig {
  const backend = findBackend(roster, seed.backend) ?? roster[0];
  const opts = defaultOptsFor(backend);
  if (seed.nPerWire != null) opts.nPerWire = seed.nPerWire;
  if (seed.bspline && opts.bspline)
    opts.bspline = { ...opts.bspline, ...seed.bspline };
  return { backend, opts };
}

export function defaultSlots(roster: BackendRoster): Record<Slot, SlotConfig> {
  return {
    A: slotFromSeed(DEFAULT_SLOT_SEEDS.A, roster),
    B: slotFromSeed(DEFAULT_SLOT_SEEDS.B, roster),
    C: slotFromSeed(DEFAULT_SLOT_SEEDS.C, roster),
  };
}


// Translates the frontend options into the snake_case kwargs the server
// forwards to each Momwire model class constructor: the served generic knobs
// under their own keys, then whatever the bespoke panel contributes. PyNEC
// takes none — it isn't a momwire model.
export function modelOptionsForRequest(
  b: BackendEntry,
  opts: BackendOpts,
): Record<string, unknown> {
  if (b.kind === "pynec") return {};
  const out: Record<string, unknown> = {};
  for (const f of b.options_schema) out[f.key] = opts.schema[f.key] ?? f.default;
  if (b.panel === PANEL_BSPLINE) {
    // bspline, hmatrix, and arrayblock all take the B-spline kwargs; the
    // accelerators read additional aca_tol/solve_tol from their own defaults.
    const o = opts.bspline ?? BSPLINE_DEFAULT_OPTS;
    out.degree = o.degree;
    out.n_qp_pair = o.nQpPair;
    out.n_qp_source = o.nQpSource;
    out.feed_smoothing_factor = o.feedSmoothingFactor;
    out.use_singular_enrichment = o.useSingularEnrichment;
    out.enrichment_variant = o.enrichmentVariant;
    out.tikhonov_lambda = o.tikhonovLambda;
    out.auto_tap_ratio_threshold = o.autoTapRatioThreshold;
    out.n_qp_sing = o.nQpSing;
    out.enrichment_min_k = o.enrichmentMinK;
  }
  if (b.panel === PANEL_SIN_GALERKIN) {
    // feed_model only here: plain sinusoidal cannot carry the point gap
    // (momwire#212) and must not receive the key at all.
    out.feed_model = opts.feedModel ?? "segment";
  }
  return out;
}
