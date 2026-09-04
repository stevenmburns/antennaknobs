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

/** One solver knob, described by the server (#1006 G2-6).
 *
 *  Served once per session on `/capabilities` and keyed by kwarg, NOT repeated
 *  per roster row: the description of `degree` is the same fact for every
 *  backend that takes it, and copying it into each row would re-create the
 *  per-engine duplication this unit removes, one level down. A backend's
 *  `model_kwargs` names which of these apply to it.
 *
 *  Mirrors adapter.model_option_specs(); snake_case because it is wire data. */
export type ModelOptionSpec = {
  kind: "int" | "float" | "bool" | "enum";
  label: string;
  default: number | string | boolean | null;
  /** Null means "let the solver decide" and the key is OMITTED from the
   *  request rather than sent as null. antennaknobs#1064 is what happens when
   *  a caller substitutes a number instead: it silently overrides momwire's
   *  own per-deck default, which since momwire#863 depends on the geometry. */
  auto_when_null: boolean;
  /** Render only while this other option is truthy. PURE UI GATING — a real
   *  refusal (the extended kernel against singular enrichment) is momwire's
   *  and arrives in `constraints`, never here. */
  shown_when: string | null;
  min?: number;
  max?: number;
  step?: number;
  allow_none?: boolean;
  values?: string[];
};

export type ModelOptionSpecs = Record<string, ModelOptionSpec>;

/** A served roster entry. Mirrors adapter.backend_roster(); snake_case
 *  because it is wire data, not a local shape. */
export type BackendEntry = {
  name: string;
  label: string;
  /** Non-momwire kinds ("pynec", "nec5") ride the `solver` request field
   *  and never `momwire_model`; everything else is a momwire model name.
   *  "nec5" appears only when the serving machine resolves $NEC5_EXE — a
   *  licensed, user-supplied binary (issue #825), never the hosted box. */
  kind: "momwire" | "pynec" | "nec5";
  supports_ground: boolean;
  options_schema: BackendOptionField[];
  /** Bespoke panel hint — the knobs no numeric renderer can carry. Null for
   *  a backend whose whole surface is generic. */
  panel: string | null;
  default_n_per_wire: number;
  accelerator: boolean;
  dense_family: boolean;
  /** What the CLASS can be configured to: axis -> the values it accepts
   *  (antennaknobs#1006 G2-1). Null when the installed momwire cannot say
   *  — rendered as "not described", never as "no axes". */
  axes?: Record<string, string[]> | null;
  /** What this PRESET pins. `axes` and `bound` say different things and must
   *  stay separable: `razor-2p` binds `nec5_quadrature`, so its quadrature is
   *  fixed on a local install too — the preset is the reason, not host
   *  policy. This is #1006's "names are saved presets over a product space",
   *  in the payload. */
  bound?: Record<string, unknown>;
  /** Which axis values this backend cannot combine, with momwire's own
   *  refusal prose. Null when it cannot be asked; [] when there are none —
   *  different answers, rendered differently. */
  constraints?: BackendConstraint[] | null;
  /** Which solver kwargs this backend's constructor ACCEPTS (#1006 G2-6),
   *  measured server-side by construction. Names entries in the served
   *  `model_option_specs` catalogue.
   *
   *  This says what may be SENT, not what may be CHOSEN — see THE OFFERED-VS-
   *  SENT RULE beside `axisControls`. */
  model_kwargs?: string[];
};

/** One refused combination, as momwire measured it (momwire#885). */
export type BackendConstraint = {
  axis: string;
  value: string;
  forbids_axis: string;
  forbids_value: string;
  /** False when the forbidden side is a constructor keyword rather than an
   *  axis — the panel cannot draw it as a cell, so it skips it without
   *  needing a second list of exceptions. */
  forbids_is_axis: boolean;
  /** Null for a flat refusal; a short phrase when it applies only in a
   *  narrower case. "Refused" and "refused when X" are different sentences. */
  condition: string | null;
  reason: string;
  /** Null when the refusal's own prose cites no issue (momwire#888 made
   *  `Coupling.issue` optional for exactly one row). A plausible-looking
   *  number invented on either side would be followed, which is worse than
   *  none — so the absence travels rather than being papered over. */
  issue: string | null;
};

/** The design-side inputs a constraint needs. Read from the served design
 *  descriptor, so they are LIVE: they change when the design changes, which
 *  is what makes the warnings derived state rather than a one-time check. */
export type DesignConstraintInputs = {
  has_stepped_radius_junction?: boolean;
  /** Whether the design puts a wire below the interface (already served). */
  buried?: boolean | null;
};

export type BackendRoster = BackendEntry[];

// Panel hints, as served. Named constants so the bespoke components are
// selected by the server's hint rather than by backend name.
export const PANEL_BSPLINE = "bspline";
export const PANEL_SIN_GALERKIN = "sin-galerkin";
export const PANEL_PYNEC = "pynec";

// THE CONTROL RULE (antennaknobs#1006 G2-5), written down once:
//
//   an axis is a CONTROL iff it is multi-valued in `axes`
//                      AND it is not pinned by this preset's `bound`
//                      AND it is not a DERIVED axis (see below).
//
// The first clause is the class, the second the preset, and they are two
// different things. `razor-2p` binds `nec5_quadrature`, so quadrature is not a
// control on that tab even on a local install — the tab IS the two-point lane
// and letting a user flip it would make the name a lie.
//
// Host policy is a THIRD thing and it is deliberately NOT a clause here. The
// hosted sanitiser's allowlist (`_HOSTED_MODEL_OPTIONS` in web/adapter.py) is
// server-side knowledge and no hosted flag reaches this module, so a clause
// for it here could not be evaluated. It would also be vacuous today:
// `degree`, `extended_kernel` and `feed_model` are all allowlisted, and the
// one axis kwarg that is NOT (`nec5_quadrature`) is already dropped by the
// `bound` clause on the only tab that offers it. Rather than write a clause
// that cannot fire and cannot be checked, the invariant is pinned on the
// server, where hosted-ness is actually known:
// test_axis_controls_1006.py::test_every_axis_control_kwarg_is_hosted_allowed.
// If a future axis arrives whose kwarg is not allowlisted, that test fails and
// forces the decision — instead of this file silently rendering a control the
// hosted sanitiser will drop.
//
// The kwarg an axis maps to is not always its own name, so the mapping is
// explicit rather than guessed from the axis label.
// The DERIVED axes are never controls, and this is a fourth clause the rule
// needed rather than an exception to it. `ground_model` and `wire_position`
// describe the DECK a solver can be pointed at; the declared axes describe how
// the solver is BUILT. Ground is a user choice but it lives in its own panel,
// and wire position is not a user choice at all — it is the design's geometry.
// So they drive CONSTRAINTS (a buried deck forbids the extended kernel) and
// never controls. Caught by a test that expected two controls and got four.
export const DERIVED_AXES = ["ground_model", "wire_position"];

export const AXIS_KWARG: Record<string, string> = {
  basis: "degree",
  kernel: "extended_kernel",
  feed_model: "feed_model",
  quadrature: "nec5_quadrature",
};

// THE CHOICE LISTS, derived from the axis "wherever an axis exists".
//
// Each table below is UI copy — a label, a tooltip, and the opts value the tab
// sets — keyed by the axis value it presents. The AXIS decides which entries
// are offered; the table decides how they are named and in what ORDER. Order
// has to come from here rather than from the payload: momwire serves axis
// values sorted, which would put "Converged" before "NEC-compatible" and
// silently reorder a control users have muscle memory for.
//
// THE FALLBACK IS NOT VESTIGIAL. `axes` is null on any momwire predating the
// axis vocabulary, and that is the momwire USERS have — the submodule pointer
// runs ahead of the PyPI pin by design, so the released package answers null
// today. Dropping the fallback would delete the feed-model control for every
// installed user until the pin moves. So the `panel` hint stays as the answer
// for "cannot be asked", and the axis is the answer wherever it can.
const FEED_MODEL_CHOICES = [
  {
    axisValue: "segment-gap",
    value: "segment" as FeedModel,
    label: "NEC-compatible",
    title:
      "NEC's segment-wide gap: reproduces NEC/EZNEC behaviour, including " +
      "reactance drift with mesh density. Use when cross-checking against " +
      "NEC results.",
  },
  {
    axisValue: "point-gap",
    value: "point" as FeedModel,
    label: "Converged",
    title:
      "Zero-width (point) gap: converges to the B-spline answer and gives a " +
      "reciprocal Y. Recommended for near-open high-Q designs (momwire#213).",
  },
];

export type FeedModelChoice = (typeof FEED_MODEL_CHOICES)[number];

/** The feed-model tabs this backend offers, in UI order. */
export function feedModelChoices(b: BackendEntry): FeedModelChoice[] {
  const vals = b.axes?.feed_model;
  if (!vals) return b.panel === PANEL_SIN_GALERKIN ? FEED_MODEL_CHOICES : [];
  return FEED_MODEL_CHOICES.filter((c) => vals.includes(c.axisValue));
}

/** Does this backend give the user a feed-model CHOICE?
 *
 *  Replaces the four `panel === PANEL_SIN_GALERKIN` branches. Plain
 *  `sinusoidal` declares `feed_model: ["segment-gap"]` — it can carry a feed
 *  model but not a choice of one (the point gap has no collocation RHS,
 *  momwire#212) — and that single-valued axis is exactly what the roster
 *  entry's absent panel hint used to say by omission.
 */
export function offersFeedModelChoice(b: BackendEntry): boolean {
  return feedModelChoices(b).length > 1;
}

const DEGREE_CHOICES = [
  { axisValue: "bspline-1", degree: 1 as const },
  { axisValue: "bspline-2", degree: 2 as const },
];

/** The B-spline degree tabs this backend offers, in UI order.
 *
 *  Was a hardcoded `[1, 2]`. It is the one control in the bspline panel that
 *  IS an axis; the other five (quadrature orders, the bump width, singular
 *  enrichment and its variant) are not, which is why that panel survives this
 *  change and the sin-Galerkin one does not.
 */
export function degreeChoices(b: BackendEntry): (1 | 2)[] {
  const vals = b.axes?.basis;
  const table = vals
    ? DEGREE_CHOICES.filter((d) => vals.includes(d.axisValue))
    : DEGREE_CHOICES;
  return table.map((d) => d.degree);
}

// THE OFFERED-VS-SENT RULE (#1006 G2-6), the three lines the generic
// renderer obeys:
//
//   1. `model_kwargs` says what may be SENT on the wire.
//   2. Where an AXIS exists for a kwarg, the axis decides whether a control is
//      OFFERED — multi-valued and unpinned, i.e. `axisControls`.
//   3. Where no axis exists, `model_kwargs` drives.
//
// Rule 2 is the one that is easy to drop, and dropping it is a behaviour
// change wearing a refactor's clothes. `bspline` ACCEPTS `feed_model` and has
// never offered a feed-model control — its `feed_model` axis holds the single
// value "segment-gap" — so a renderer driven by the kwarg list alone would
// grow one on bspline, hmatrix and arrayblock. The same rule is why `degree`
// never appears on `razor-2p`, whose basis axis is ("tent",) even though the
// constructor takes the keyword.
//
// Accepting a keyword and offering a choice are different questions. The
// server answers the first by construction (`_BackendSpec.model_kwargs`); the
// axes answer the second.
export function axisControls(b: BackendEntry): string[] {
  const axes = b.axes;
  if (!axes) return [];
  return Object.keys(axes)
    .filter((axis) => !DERIVED_AXES.includes(axis))
    .filter((axis) => (axes[axis]?.length ?? 0) > 1)
    .filter((axis) => {
      const kwarg = AXIS_KWARG[axis];
      return !kwarg || !(kwarg in (b.bound ?? {}));
    })
    .sort();
}

/** The constraint this slot violates on this design, or null.
 *
 *  The general form of `extendedKernelRefusal`, and the reason G2-5 extends
 *  the existing gate path rather than adding one beside it: the answer is
 *  DERIVED from the backend, the options and the CURRENT DESIGN, so it
 *  recomputes when any of the three changes. A one-time check when the engine
 *  is picked would go stale the moment the user switches design, which is the
 *  question this exists to answer.
 *
 *  Only constraints whose forbidden side is an axis are considered: the two
 *  keyword rows are served (so an API consumer sees the whole inventory) but
 *  cannot be rendered as a cell, and `near_correction` is not a user control
 *  at all — momwire defaults it True and the app never sets it, so no panel
 *  choice can reach that combination. */
export function backendOptsAllowed(
  b: BackendEntry,
  opts: BackendOpts,
  design: DesignConstraintInputs | null | undefined,
): BackendConstraint | null {
  const constraints = b.constraints;
  if (!constraints || !design) return null;
  for (const c of constraints) {
    if (!c.forbids_is_axis) continue;
    if (c.axis === "kernel" && c.value === "extended" && !opts.extendedKernel) {
      continue;
    }
    if (c.forbids_axis === "wire_position" && c.forbids_value === "buried") {
      if (design.buried) return c;
    }
  }
  return null;
}

/** Whether this design trips the stepped-radius junction refusal under the
 *  extended kernel. Separate from `backendOptsAllowed` because the forbidden
 *  side is a keyword rather than an axis, so it is a NOTE on the kernel
 *  control rather than a greyed cell — but it is the same served data and the
 *  same live derivation. */
export function steppedJunctionNote(
  b: BackendEntry,
  opts: BackendOpts,
  design: DesignConstraintInputs | null | undefined,
): BackendConstraint | null {
  if (!opts.extendedKernel || !design?.has_stepped_radius_junction) return null;
  return (
    (b.constraints ?? []).find(
      (c) => c.axis === "kernel" && c.forbids_axis === "junction_ports",
    ) ?? null
  );
}

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
  nQpPair: number | null; // null = auto (let momwire choose)
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
  // Cross-edge Gauss order, or null for AUTO — the knob is then omitted from
  // the request entirely and momwire picks per deck (32 with wire below the
  // interface, 8 otherwise; momwire#863).
  //
  // Auto rather than a number because this value is sent only when non-null:
  // a literal here is sent UNCONDITIONALLY and silently overrides the library
  // for every hosted solve, which is antennaknobs#1064. That bit us exactly
  // once more — #1064 was raised when this pinned 4 against a library default
  // of 8, and pinning 8 then hid momwire#863's per-deck default the same way.
  // A fixed number here cannot track a default that depends on the GEOMETRY,
  // so the fix is to stop sending one rather than to update it again.
  nQpPair: null,
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
  // "point" = Converged (zero-width gap — converges to the B-spline answer,
  // exactly reciprocal Y; the solver's default since momwire#654, and
  // recommended for near-open high-Q designs, momwire#213); "segment" =
  // NEC-compatible (NEC's own segment-wide gap, including the reactance walk
  // with mesh density). "NEC-compatible" is a claim about the SOURCE and not
  // about the formulation — for a NEC cross-check the whole formulation is
  // the `sinusoidal` backend. Deliberately not offered on plain sinusoidal:
  // the point gap has no collocation RHS (momwire#212), so that solver's
  // roster entry names no panel.
  feedModel?: FeedModel;
  // NEC's extended thin-wire kernel — the `EK` card (issue #849, momwire >=
  // 0.26.0). Common to every momwire backend rather than panel-specific, so
  // it sits beside wire radius rather than inside a bespoke panel: it is the
  // knob that says how the on-axis Green's function treats that radius.
  // ABSENT = off, which is the EK card's own convention (a deck with no `EK`
  // card, and `EK -1`, both read as the reduced kernel) and what keeps a
  // kernel-off request byte-identical to what every release before #849 sent.
  extendedKernel?: boolean;
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
  // The solver's own default (momwire#654 made it the point gap), and the
  // one the gear menu recommends on near-open designs (#640). Sent
  // explicitly rather than left unset so the wire format says which source
  // ran regardless of which momwire the server is carrying.
  if (offersFeedModelChoice(b)) opts.feedModel = "point";
  return opts;
}

// ---------------------------------------------------------------------------
// The extended thin-wire kernel (issue #849)
// ---------------------------------------------------------------------------

// One-line "why you'd want this", used as the toggle's tooltip.
export const EK_HINT =
  "NEC's extended thin-wire kernel (the EK card): the on-axis Green's " +
  "function uses NEC's O(a²) tube expansion instead of the filament " +
  "approximation. It matters where the wire is FAT relative to its segments " +
  "— a fraction of a percent at Δ/a > 10, several percent below Δ/a ≈ 3 — " +
  "and costs about 1.0–1.3× the reduced-kernel solve.";

// The one basis that cannot serve the kernel. Named here rather than read off
// Since momwire 0.27.0 every momwire basis serves the extended kernel — the
// Galerkin family joined with momwire#246/#287/#299 — so the one refusal left
// is the enrichment combination below. This is the frontend twin of
// engines/momwire.py::_extended_kernel_refusal, which raises the same refusal
// server-side — a stale rule here costs a clear error dialog, not a wrong
// answer. If a second refusal ever appears, that is the moment to serve the
// capability as a roster field instead of another local rule.
export const EK_ENRICHMENT_REASON =
  "The extended kernel and K≥3 junction singular enrichment cannot be used " +
  "together (momwire#271): the enrichment DOFs bypass the moment kernels the " +
  "extended kernel corrects. Turn one of the two off.";

/** Why this slot cannot run the extended kernel, or null if it can. Mirrors
 *  the engine-side refusals so the gear menu can grey the toggle out and say
 *  why, instead of letting the solve come back as an error dialog. */
export function extendedKernelRefusal(
  _b: BackendEntry,
  opts: BackendOpts,
): string | null {
  if (opts.bspline?.useSingularEnrichment) return EK_ENRICHMENT_REASON;
  return null;
}

/** The design-dependent refusal for this slot, or null.
 *
 *  The gate #1006 point 4 asks for, and it is DERIVED STATE: it takes the
 *  current design, so switching design re-answers it. A one-time check when
 *  the engine was picked would still be showing the first design's answer.
 *
 *  BOTH constraint shapes gate. `forbids_is_axis` says whether the panel can
 *  draw the row as a CELL in an axis matrix — `junction_ports` is a property
 *  of the deck, not an axis, so it has no cell. That is a rendering question
 *  and NOT a question about whether momwire refuses: both of these sit in a
 *  solver's `refusals` dict and both raise. Gating only the axis-shaped one
 *  would let the stepped-radius deck through to an error dialog, which is the
 *  outcome this whole path exists to prevent.
 */
export function designRefusal(
  b: BackendEntry,
  opts: BackendOpts,
  design: DesignConstraintInputs,
): BackendConstraint | null {
  return (
    backendOptsAllowed(b, opts, design) ?? steppedJunctionNote(b, opts, design)
  );
}

/** Is the extended kernel actually in force for this slot? True only when the
 *  user asked for it AND this backend can serve it — a slot whose backend
 *  changed under a set flag solves reduced rather than erroring, and the chip
 *  and the request agree with the toggle the gear menu is showing. PyNEC is
 *  excluded outright: it sends no `model_options` at all, and its own
 *  extended-kernel support (issue #414) is a separate, unexposed kwarg. */
export function extendedKernelActive(b: BackendEntry, opts: BackendOpts): boolean {
  if (b.kind !== "momwire" || !opts.extendedKernel) return false;
  return extendedKernelRefusal(b, opts) === null;
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
  // "+EK" affixes the extended thin-wire kernel (issue #849) to whatever the
  // slot is already called. The whole point of the toggle is A-vs-B — one slot
  // with the kernel, one without — so the chips have to say which is which.
  // Affixed only when the kernel is actually IN FORCE, never when a backend
  // that refuses it is carrying a set flag.
  const ek = extendedKernelActive(b, opts) ? " +EK" : "";
  if (b.panel === PANEL_BSPLINE)
    return `${b.label} d=${opts.bspline?.degree ?? BSPLINE_DEFAULT_OPTS.degree}${ek}`;
  // Surface the non-default feed model on the slot chip: two Sin-Galerkin
  // slots differing only in feed model must be tellable apart at a glance.
  // Which value IS the deviation flipped with momwire#654 — the point gap is
  // the solver's default now, so a plain chip means converged and the chip
  // that carries a suffix is the one asking for NEC's source.
  if (offersFeedModelChoice(b) && opts.feedModel === "segment")
    return `${b.label} (NEC gap)${ek}`;
  return `${b.label}${ek}`;
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
  if (b.kind !== "momwire") return {};
  const out: Record<string, unknown> = {};
  for (const f of b.options_schema) out[f.key] = opts.schema[f.key] ?? f.default;
  if (b.panel === PANEL_BSPLINE) {
    // bspline, hmatrix, and arrayblock all take the B-spline kwargs; the
    // accelerators read additional aca_tol/solve_tol from their own defaults.
    const o = opts.bspline ?? BSPLINE_DEFAULT_OPTS;
    out.degree = o.degree;
    // Omitted when auto, so momwire's own per-deck default decides. Never
    // substitute a literal here: translating auto into 8 or 32 on this side
    // re-creates the override #1064 is about, and AK does not know the
    // geometry rule.
    if (o.nQpPair != null) out.n_qp_pair = o.nQpPair;
    out.n_qp_source = o.nQpSource;
    out.feed_smoothing_factor = o.feedSmoothingFactor;
    out.use_singular_enrichment = o.useSingularEnrichment;
    out.enrichment_variant = o.enrichmentVariant;
    out.tikhonov_lambda = o.tikhonovLambda;
    out.auto_tap_ratio_threshold = o.autoTapRatioThreshold;
    out.n_qp_sing = o.nQpSing;
    out.enrichment_min_k = o.enrichmentMinK;
  }
  if (offersFeedModelChoice(b)) {
    // feed_model only here: plain sinusoidal cannot carry the point gap
    // (momwire#212) and must not receive the key at all. The fallback is the
    // solver's own default (momwire#654); a design saved before that default
    // moved carries its own explicit value and is unaffected.
    out.feed_model = opts.feedModel ?? "point";
  }
  // The extended thin-wire kernel travels as a model option (the server pulls
  // it back out of model_options and passes it as the named `extended_kernel=`
  // constructor kwarg). Sent ONLY when in force: absence is the reduced
  // kernel — the EK card's own convention, and the spelling that keeps a
  // kernel-off request byte-identical to what every release before #849 sent.
  // The `extendedKernelActive` gate is also what keeps a refused combination
  // off the wire; the UI disables the toggle on those, so this is the second
  // of the two locks, not the only one.
  if (extendedKernelActive(b, opts)) out.extended_kernel = true;
  return out;
}


/** The knobs to RENDER for this backend, in order — the offered-vs-sent rule
 *  above, as a function.
 *
 *  Returns kwarg names; the caller looks each up in the served
 *  `ModelOptionSpecs`. `shown_when` is NOT applied here: it depends on the
 *  live option values, so it is the renderer's business and is applied per
 *  draw (`specShown`).
 */
export function renderableOptions(
  b: BackendEntry,
  specs: ModelOptionSpecs,
): string[] {
  const kwargs = b.model_kwargs ?? [];
  const axisFor: Record<string, string> = {};
  for (const [axis, kwarg] of Object.entries(AXIS_KWARG)) axisFor[kwarg] = axis;
  const offeredAxes = new Set(axisControls(b));
  return kwargs
    .filter((k) => k in specs)
    .filter((k) => {
      const axis = axisFor[k];
      // Rule 3: no axis governs this kwarg, so the kwarg list decides.
      if (axis === undefined) return true;
      // Rule 2: an axis governs it, so the axis decides. When the backend
      // cannot describe its axes at all (`axes: null`, the released momwire),
      // `axisControls` is empty and this would hide EVERY axis-governed knob
      // — including `degree`, which that momwire has always shown. So fall
      // back to the kwarg list, which is the pre-axes behaviour.
      if (!b.axes) return true;
      return offeredAxes.has(axis);
    })
    .sort((x, y) => kwargs.indexOf(x) - kwargs.indexOf(y));
}

/** Is this spec's `shown_when` gate satisfied by the current values? */
export function specShown(
  spec: ModelOptionSpec,
  values: Record<string, unknown>,
): boolean {
  return spec.shown_when === null || Boolean(values[spec.shown_when]);
}
