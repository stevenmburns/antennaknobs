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
  /** Render only while this other option is TRUTHY — not "is true":
   *  `n_qp_source` shows while `feed_smoothing_factor` is a non-null number,
   *  so a gate naming a boolean is the common case and not the rule.
   *
   *  PURE UI GATING. A real refusal (the extended kernel against singular
   *  enrichment) is momwire's and arrives in `constraints`, never here. */
  shown_when: string | null;
  /** What the CONTROL offers. Not what the endpoint tolerates — see
   *  `accepts_min`/`accepts_max`, which are looser. `feed_smoothing_factor`
   *  differs by 10x between the two, and rendering the accepted pair would
   *  widen that knob and change its step. Gated server-side as a subset. */
  min?: number;
  max?: number;
  step?: number;
  /** What the hosted sanitiser will ACCEPT — always ⊇ [min, max]. Served so a
   *  client can tell "the server would take this" from "the control offers
   *  this"; the renderer wants the first pair, an API consumer the second. */
  accepts_min?: number;
  accepts_max?: number;
  allow_none?: boolean;
  values?: string[];
  /** Caption for the checkbox that switches a nullable knob on (or to auto).
   *  Not derivable from `label`: the gates read "n_qp_pair: auto" and "feed
   *  source smoothing" against labels of "n_qp_pair (GL pts/axis)" and
   *  "α (bump width / h_feed)".
   *
   *  POLARITY falls out rather than being stored: `auto_when_null` means
   *  checked-when-null, `allow_none` alone means checked-when-set. */
  gate_label?: string | null;
  /** The value the gate switches this knob ON to. Not the default — for an
   *  auto knob the default IS null, and unticking auto pins this instead. */
  gate_on_value?: number | null;
  /** When set, `shown_when` must EQUAL this rather than merely be truthy.
   *  Gates chain: these name `enrichment_variant`, which is itself gated on
   *  `use_singular_enrichment`, so resolving transitively reproduces the old
   *  panel's nesting with no chain syntax on the wire. */
  shown_when_value?: string | null;
};

export type ModelOptionSpecs = Record<string, ModelOptionSpec>;

/** One segment of a tab's composition line (#1006 G2-7). */
export type CompositionSegment = {
  axis: string;
  /** The phrase to render — served UI copy, never a raw momwire token. */
  text: string;
  /** The preset binds this axis, so it is not a control here and says so. */
  pinned: boolean;
  /** Single-valued on this backend: the tab's identity rather than a choice. */
  fixed: boolean;
};

/** The served vocabulary a composition line is written from. */
export type CompositionVocabulary = {
  axes: string[];
  labels: Record<string, Record<string, string>>;
};

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
  /** Bespoke panel hint, as served. Nothing in this client reads it since
   *  #1170 — every knob is drawn from the catalogue and the axes — and it is
   *  typed only because the wire carries it. */
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
  /** Axis -> the value this preset PINS it to (#1006 G2-7), resolved
   *  server-side from `bound`. Empty when the preset binds nothing. Separate
   *  from `bound` because that is keyed by constructor kwarg and a line needs
   *  the axis value. */
  bound_axes?: Record<string, string>;
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
  /** Does this backend serve BURIED geometry? Three states: true, false, and
   *  null for "cannot be asked" — a momwire predating the capability, or a
   *  non-momwire wrapper whose buried scope is its own business. Null must
   *  never be read as "cannot" (#1103).
   *
   *  SERVED SINCE #1108 AND UNTYPED HERE UNTIL NOW, which is a large part of
   *  why nothing gated on it: the fact was on the wire and invisible to the
   *  client. */
  buried?: boolean | null;
  /** momwire's sentence for why it cannot, or null. The boolean alone was not
   *  enough — with no prose, nothing could gate without inventing a reason,
   *  so nothing gated at all, and `razor-2p` on a buried design solved,
   *  raised, and showed a traceback instead of a refusal. */
  buried_refusal?: string | null;
  /** Which issue that refusal should cite (#1167). Served rather than fixed
   *  here: this was the literal `momwire#553` below, which was right while
   *  momwire was the only backend that could refuse a deck and became wrong
   *  the moment PyNEC could — a user reading a PyNEC limitation was sent to a
   *  momwire issue that does not mention PyNEC. */
  buried_issue?: string | null;
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

// Panel hints are served but NOT read here. PANEL_BSPLINE and PANEL_PYNEC
// were deleted in #1006 G2-6 (their knobs come from the served catalogue);
// PANEL_SIN_GALERKIN outlived them as `feedModelChoices`' fallback for a
// momwire whose `axes` is null — the released momwire while the submodule
// pointer ran ahead of the PyPI pin — and went with the pin bump to momwire
// 0.48.0 (#1169, #1170). The grep test asserts no `PANEL_*` constant and no
// read of `.panel` survives in this file.

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
  // Same guard as `degreeChoices`: a backend that does not expose the kwarg
  // has no choice to offer, whatever its axes say or fail to say.
  if (!(b.model_kwargs ?? []).includes("feed_model")) return [];
  // A momwire that cannot describe itself (`axes` null) offers no choice:
  // the honest answer, now that the released momwire serves the vocabulary
  // (#1170). The hint-keyed fallback that used to sit here is gone.
  const vals = b.axes?.feed_model;
  if (!vals) return [];
  return FEED_MODEL_CHOICES.filter((c) => vals.includes(c.axisValue));
}

/** Does this backend give the user a feed-model CHOICE?
 *
 *  Replaces the four `panel === "sin-galerkin"` branches. Plain
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
  // EXPOSURE FIRST. The axes-null fallback below exists for a momwire that
  // cannot describe itself — not for a backend that has no degree at all.
  // Without this, `pynec` (axes: null, exposes nothing) fell through to the
  // fallback and grew a pair of degree tabs.
  if (!(b.model_kwargs ?? []).includes("degree")) return [];
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
    if (c.axis === "kernel" && c.value === "extended" && !opts.model.extended_kernel) {
      continue;
    }
    if (c.forbids_axis === "wire_position" && c.forbids_value === "buried") {
      if (design.buried) return c;
    }
  }
  return null;
}

/** The stepped-radius-junction note for this slot, or null.
 *
 *  Separate from `backendOptsAllowed` because the forbidden side is a
 *  property of the DECK (`junctions`) rather than an axis, so it has no
 *  cell in the product space and is served with `forbids_is_axis: false`.
 *  That marker is about RENDERING, not about whether momwire refuses — this
 *  one sits in the solver's `refusals` dict and raises like any other, which
 *  is why `designRefusal` gates on both shapes.
 *
 *  All three parts are required: the backend must carry the row, the user
 *  must have asked for the extended kernel, and the DESIGN must actually have
 *  a radius step at a junction. Uniform-radius junctions are the common case
 *  and are untouched — collapsing the condition would tell a user the
 *  extended kernel refuses junctions outright, which is false and sends them
 *  to the wrong workaround.
 */
export function steppedJunctionNote(
  b: BackendEntry,
  opts: BackendOpts,
  design: DesignConstraintInputs | null | undefined,
): BackendConstraint | null {
  if (!opts.model.extended_kernel || !design?.has_stepped_radius_junction) {
    return null;
  }
  return (
    (b.constraints ?? []).find(
      (c) =>
        c.axis === "kernel" &&
        c.value === "extended" &&
        c.forbids_axis === "junctions",
    ) ?? null
  );
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
  aliases: Record<string, string> = {},
): BackendEntry | null {
  if (!name) return null;
  // Retired names come from the server (#1006 G2-6). This used to be an
  // inline `name === "triangular" ? "bspline" : name`, which was the last
  // engine-name branch in this file; the server already tolerated the retired
  // name on the solve path, so it is now said once, there.
  return findBackend(roster, aliases[name] ?? name);
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
  /** Solver kwargs, keyed by the SERVER'S OWN kwarg name (#1006 G2-6).
   *
   *  One flat map, deliberately. This used to be `schema` (the generic
   *  numeric knobs) plus `bspline` (a bespoke panel's state) plus two loose
   *  fields, and `opts.bspline` is an engine name in the data model — so a
   *  renderer over that shape could never be generic, and a grep for engine
   *  names would have passed only because the name was a property rather
   *  than a string literal.
   *
   *  A key ABSENT means "not set"; for a spec with `auto_when_null` a null
   *  means "let the solver decide" and the key is dropped from the request
   *  rather than sent. Both are load-bearing — see `modelOptionsForRequest`.
   */
  model: Record<string, unknown>;
};

/** A backend's stock options, from the SERVED spec defaults.
 *
 *  Takes the catalogue rather than closing over a local table: the defaults
 *  are the server's (`_OPTION_SPECS`), and a copy here is the duplication
 *  #1006 G2-6 removes. An empty catalogue — a server predating it — yields no
 *  model options at all, which is the honest answer rather than a guess.
 */
export function defaultOptsFor(
  b: BackendEntry,
  specs: ModelOptionSpecs,
): BackendOpts {
  const model: Record<string, unknown> = {};
  for (const key of b.model_kwargs ?? []) {
    const spec = specs[key];
    if (spec === undefined) continue;
    model[key] = spec.default;
  }
  return {
    nPerWire: b.default_n_per_wire,
    wireRadius: DEFAULT_WIRE_RADIUS,
    model,
  };
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

// Every momwire basis serves the extended kernel since momwire 0.27.0 (the
// Galerkin family joined with momwire#246/#287/#299). The refusals that
// remain are COMBINATIONS, and they are momwire's to state: they arrive in
// the roster's `constraints` and are read by `designRefusal`. This file no
// longer carries a local rule about any of them — see momwire#888 for what
// the last local copy had drifted into.
/** The design-dependent refusal for this slot, or null.
 *
 *  The gate #1006 point 4 asks for, and it is DERIVED STATE: it takes the
 *  current design, so switching design re-answers it. A one-time check when
 *  the engine was picked would still be showing the first design's answer.
 *
 *  BOTH constraint shapes gate. `forbids_is_axis` says whether the panel can
 *  draw the row as a CELL in an axis matrix — `junctions` is a property
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
    capabilityRefusal(b, design) ??
    backendOptsAllowed(b, opts, design) ??
    steppedJunctionNote(b, opts, design)
  );
}

/** A refusal of the DECK ITSELF, independent of any option.
 *
 *  A THIRD SHAPE, and the gate missed it entirely until a review found
 *  `razor-2p` solving a buried design and showing the user a traceback.
 *  The other two ask "which COMBINATIONS are refused" — they are couplings,
 *  and `COUPLINGS` rightly does not name this, because a solver with no
 *  buried fill refuses the deck whatever else is set. Different question,
 *  and the gate needs both.
 *
 *  Checked FIRST: a backend that cannot take the deck at all should say so
 *  rather than report a narrower option-level reason that is also true.
 *
 *  `buried: null` is "cannot be asked" and must not be read as "cannot" —
 *  #1103's rule. `nec5` still answers null, because nobody has measured it.
 *
 *  `pynec` answered null on the same grounds until #1167 measured it, and the
 *  measurement inverted the docstring it replaced: PyNEC does not refuse a
 *  buried wire, it solves one as though it were in air and returns a
 *  plausible number. So this gate is the only thing standing between a user
 *  on a buried design and a wrong answer with no traceback to warn them —
 *  which is a stronger reason to render it than the `razor-2p` case that
 *  prompted the function, where at least the user saw a crash.
 */
export function capabilityRefusal(
  b: BackendEntry,
  design: DesignConstraintInputs | null | undefined,
): BackendConstraint | null {
  if (!design?.buried) return null;
  if (b.buried !== false) return null;
  const reason = b.buried_refusal;
  if (!reason) return null;
  return {
    axis: "wire_position",
    value: "buried",
    forbids_axis: "backend",
    forbids_value: b.name,
    // Not a cell in the product space: this is the solver declining the deck,
    // not one axis value excluding another.
    forbids_is_axis: false,
    condition: null,
    reason,
    // Served per backend (#1167). The fallback keeps every momwire row citing
    // what it cited before; a wrapper that serves its own issue overrides it.
    issue: b.buried_issue ?? "momwire#553",
  };
}

/** Is the extended kernel actually in force for this slot?
 *
 *  True only when the user asked for it AND this backend can serve it — a
 *  slot whose backend changed under a set flag solves reduced rather than
 *  erroring, so the chip and the request agree with the toggle on screen.
 *  PyNEC is excluded outright: it sends no `model_options` at all, and its
 *  own extended-kernel support (issue #414) is a separate, unexposed kwarg.
 *
 *  THE ENRICHMENT EXCLUSION NO LONGER LIVES HERE. `EK_ENRICHMENT_REASON` and
 *  `extendedKernelRefusal` were a hand-written copy of momwire's refusal,
 *  and a drifted one: they cited momwire#271 where momwire's own
 *  `_ENRICHMENT_EXTENDED_KERNEL_REFUSAL` cites momwire#249 follow-up C, and
 *  gave one reason where it gives three. There was no served row to
 *  reference until momwire#888 added it; now there is, so the copy is gone
 *  and the exclusion arrives through `constraints` like every other refusal.
 */
export function extendedKernelActive(b: BackendEntry, opts: BackendOpts): boolean {
  if (b.kind !== "momwire" || !opts.model.extended_kernel) return false;
  return true;
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
  // The degree affix, when this backend has a degree at all — read off the
  // served kwarg, not off a panel hint.
  const degree = opts.model.degree;
  if (degree !== undefined && degree !== null) return `${b.label} d=${degree}${ek}`;
  // Surface the non-default feed model on the slot chip: two Sin-Galerkin
  // slots differing only in feed model must be tellable apart at a glance.
  // Which value IS the deviation flipped with momwire#654 — the point gap is
  // the solver's default now, so a plain chip means converged and the chip
  // that carries a suffix is the one asking for NEC's source.
  if (offersFeedModelChoice(b) && opts.model.feed_model === "segment")
    return `${b.label} (NEC gap)${ek}`;
  return `${b.label}${ek}`;
}

/** Seed for one default slot: a backend NAME (resolved against the served
 *  roster, never assumed present) plus the deviations from that backend's
 *  stock options. */
export type SlotSeed = {
  backend: string;
  nPerWire?: number;
  /** Deviations from the backend's stock options, keyed by served kwarg. */
  model?: Record<string, unknown>;
};

/** The stock A/B/C seeds, SERVED (#1006 G2-6).
 *
 *  These were a literal here — `A: { backend: "bspline", nPerWire: 15 }` —
 *  which is three engine names and three product decisions in the client.
 *  They are decisions with measured reasons (a basis-convergence census), so
 *  they are a served TABLE rather than something derived from the roster:
 *  "the first dense backend" would be an accident, not a choice.
 *
 *  Empty from a server that predates this, which yields the roster's own
 *  first entry for every slot — the same fallback a seed naming an absent
 *  backend already got (#429).
 */
export type ServedSlotSeed = {
  slot: Slot;
  backend: string;
  n_per_wire: number | null;
  model: Record<string, unknown>;
};

// Resolve a seed against the served roster. A seed naming a backend this
// server doesn't offer (slot C on an install without pynec-accel, #429)
// falls back to the roster's first entry — the same tolerance the terrain
// panel applies to a parked preset name (#560). Falling back to the head of
// the served order rather than a hardcoded name is what keeps this file free
// of a second roster: the server puts its plainest solver first.
export function slotFromSeed(
  seed: SlotSeed,
  roster: BackendRoster,
  specs: ModelOptionSpecs,
): SlotConfig {
  const backend = findBackend(roster, seed.backend) ?? roster[0];
  const opts = defaultOptsFor(backend, specs);
  if (seed.nPerWire != null) opts.nPerWire = seed.nPerWire;
  // Only deviations the backend actually takes: a seed naming a kwarg this
  // solver does not accept would put it on the wire, where the hosted
  // sanitiser drops it and a local install raises TypeError.
  for (const [k, v] of Object.entries(seed.model ?? {})) {
    if (k in opts.model) opts.model[k] = v;
  }
  return { backend, opts };
}

export function defaultSlots(
  roster: BackendRoster,
  specs: ModelOptionSpecs,
  seeds: ServedSlotSeed[] = [],
): Record<Slot, SlotConfig> {
  // A slot the server said nothing about falls back to the roster's FIRST
  // entry — the server puts its plainest solver there, and falling back to
  // the head of the served order is what keeps this file free of a second
  // roster (#429/#560's precedent).
  const bySlot = new Map(seeds.map((s) => [s.slot, s]));
  const one = (slot: Slot): SlotConfig => {
    const seed = bySlot.get(slot);
    if (!seed) return { backend: roster[0]!, opts: defaultOptsFor(roster[0]!, specs) };
    return slotFromSeed(
      {
        backend: seed.backend,
        ...(seed.n_per_wire === null ? {} : { nPerWire: seed.n_per_wire }),
        model: seed.model,
      },
      roster,
      specs,
    );
  };
  return { A: one("A"), B: one("B"), C: one("C") };
}


// Translates the frontend options into the snake_case kwargs the server
// forwards to each Momwire model class constructor: the served generic knobs
// under their own keys, then whatever the bespoke panel contributes. PyNEC
// takes none — it isn't a momwire model.
export function modelOptionsForRequest(
  b: BackendEntry,
  opts: BackendOpts,
  specs: ModelOptionSpecs,
): Record<string, unknown> {
  if (b.kind !== "momwire") return {};
  const out: Record<string, unknown> = {};
  for (const key of b.model_kwargs ?? []) {
    const spec = specs[key];
    if (spec === undefined) continue;
    const v = opts.model[key];
    // NULL MEANS TWO DIFFERENT THINGS and the spec says which.
    //
    //   auto_when_null  -> "let the solver decide": DROP the key. Translating
    //                      auto into a literal here re-creates the override
    //                      antennaknobs#1064 is about, since momwire#863 made
    //                      that default depend on the geometry.
    //   allow_none      -> null IS the value (a sharp delta-gap, for
    //                      feed_smoothing_factor): SEND it.
    //
    // Collapsing the two would either drop a meaningful null or invent a
    // number for a knob whose default only momwire can compute.
    if (v === undefined) {
      if (spec.auto_when_null) continue;
      out[key] = spec.default;
      continue;
    }
    if (v === null && spec.auto_when_null) continue;
    out[key] = v;
  }
  // The extended thin-wire kernel is sent ONLY when in force: absence is the
  // reduced kernel — the EK card's own convention, and the spelling that
  // keeps a kernel-off request byte-identical to what every release before
  // #849 sent. So it is deleted rather than sent false.
  if (extendedKernelActive(b, opts)) out.extended_kernel = true;
  else delete out.extended_kernel;
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


/** A tab's composition line: what this engine is made of, in words (#1006
 *  point 2, G2-7).
 *
 *  Returns null when the backend cannot describe itself (`axes: null` — the
 *  released momwire, and pynec/nec5 always). The caller states that once, in
 *  words; it must never invent a line, because a line speaks with authority
 *  about the engine and a fabricated one is the worst answer this feature
 *  could give.
 *
 *  FREE segments read the CURRENT option value, so the line rewrites itself
 *  as a control moves. FIXED and PINNED segments never change, which is what
 *  makes the pin marker mean something.
 *
 *  It does NOT depend on the design. The line describes the engine; switching
 *  design changes which combinations are refused (the constraint notes), not
 *  what the engine is made of.
 */
export function compositionLine(
  b: BackendEntry,
  opts: BackendOpts,
  vocab: CompositionVocabulary,
): CompositionSegment[] | null {
  const axes = b.axes;
  if (!axes) return null;
  const bound = b.bound_axes ?? {};
  const out: CompositionSegment[] = [];
  for (const axis of vocab.axes) {
    const values = axes[axis];
    if (!values || values.length === 0) continue;
    // PINNED IFF THE SERVER RESOLVED THIS AXIS as bound — not "bound is
    // non-empty". `razor-2p` binds `nec5_quadrature` alone; its kernel is
    // free, and a segment reading "reduced kernel, pinned" there would assert
    // a constraint the engine does not have.
    //
    // The axis VALUE comes from the server too (`bound_axes`), because
    // translating `nec5_quadrature: true` into the axis value "nec5" is
    // engine vocabulary — and "nec5" is both a quadrature value and a backend
    // name, which is not an ambiguity a client should adjudicate.
    const pinnedValue = bound[axis];
    const pinned = pinnedValue !== undefined;
    const fixed = values.length === 1;

    let value: string | undefined;
    if (fixed) {
      value = values[0];
    } else if (pinned) {
      value = pinnedValue;
    } else {
      value = currentAxisValue(axis, opts) ?? values[0];
    }
    const text = vocab.labels[axis]?.[value!];
    // No phrase means the server described a value it has no words for.
    // Skipping is the honest failure: a raw momwire token in an English
    // sentence reads as a bug, and the Python side fails the build for it.
    if (!text) continue;
    out.push({ axis, text, pinned, fixed });
  }
  return out;
}

/** Which axis value the slot's options currently select. */
function currentAxisValue(axis: string, opts: BackendOpts): string | undefined {
  switch (axis) {
    case "basis": {
      const d = opts.model.degree;
      return typeof d === "number" ? `bspline-${d}` : undefined;
    }
    case "kernel":
      return opts.model.extended_kernel === true ? "extended" : "reduced";
    case "feed_model": {
      const f = opts.model.feed_model;
      return f === "point" ? "point-gap" : f === "segment" ? "segment-gap" : undefined;
    }
    default:
      return undefined;
  }
}

