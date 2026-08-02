// Backend selector — Momwire model variants + PyNEC. Per-backend
// `model_options` are forwarded to server.py's _make_momwire_sim.
// "triangular" is retired from the UI (the server still accepts it);
// see normalizeBackend for how a stale recommendation is mapped.
export type Backend =
  | "sinusoidal"
  | "sinusoidal-galerkin"
  | "bspline"
  | "hmatrix"
  | "arrayblock"
  | "pynec";

export const BACKEND_LABEL: Record<Backend, string> = {
  sinusoidal: "Sinusoidal",
  "sinusoidal-galerkin": "Sin-Galerkin",
  bspline: "B-spline",
  hmatrix: "H-matrix (ACA)",
  arrayblock: "Array-block",
  pynec: "PyNEC",
};

// A design/solver combo is "inappropriate" when the solver is a poor fit: a
// dense solver (or PyNEC) on a large array is very slow, an accelerator
// (array-block / H-matrix) on a single-element design is pure overhead, and
// on a benchmark-class mesh (thousands of segments) every b-spline-family
// solver is minutes per solve where sinusoidal (or PyNEC) is seconds. `rec`
// is the server's recommended backend ("arrayblock" for grid arrays,
// "sinusoidal" for huge meshes, else null).
export function comboInappropriate(b: Backend, rec: Backend | null): boolean {
  const accel = b === "arrayblock" || b === "hmatrix";
  if (rec === "arrayblock") return !accel; // an array wants an accelerator
  if (rec === "sinusoidal") return b !== "sinusoidal" && b !== "pynec";
  return accel; // everything else doesn't need one
}

export const BACKEND_ORDER: Backend[] = [
  "sinusoidal",
  "sinusoidal-galerkin",
  "bspline",
  "hmatrix",
  "arrayblock",
  "pynec",
];

// PyNEC needs the optional pynec-accel package, so the server reports whether
// it is installed (`have_pynec` in /examples). When it is not, the UI must not
// offer it — otherwise the /ws solve silently falls back to momwire (#429).
// `sinusoidal` is the fallback: it is the momwire basis closest to NEC (the
// same sinusoidal current expansion), so a default panel or a coerced saved
// slot still solves the same physics without PyNEC.
export const PYNEC_FALLBACK_BACKEND: Backend = "sinusoidal";

// Backends selectable given the server's capabilities: drops PyNEC when
// pynec-accel is absent.
export function selectableBackends(havePynec: boolean): Backend[] {
  return havePynec ? BACKEND_ORDER : BACKEND_ORDER.filter((b) => b !== "pynec");
}

// Map an unavailable PyNEC selection to the fallback; leave everything else
// untouched. Applied wherever a backend can arrive from outside the gated
// picker — default slots, a saved/URL slot, a server recommendation.
export function resolveBackend(b: Backend, havePynec: boolean): Backend {
  return b === "pynec" && !havePynec ? PYNEC_FALLBACK_BACKEND : b;
}

// Per-design backend allowlist (`requires_backends` on the descriptor —
// e.g. ["bspline"] for designs with PortAtEnd junction ports, which only
// the B-spline solver implements; NEC-2 has no equivalent card at all).
// null/undefined = no restriction. Unlike the missing-pynec-accel case
// (#429) this is per-design, and unlike comboInappropriate it is a HARD
// incompatibility: the disallowed solvers raise, so the gate offers
// "switch", never "solve anyway".
export function backendAllowed(
  b: Backend,
  required: string[] | null | undefined,
): boolean {
  return !required || required.includes(b);
}

// One-line explanation for why a design is backend-restricted, used by the
// disabled tabs' tooltip and the hard withhold gate. Today the only
// restriction cause is junction ports, so the copy is specific; broaden it
// if _required_backends ever grows another cause.
export const RESTRICTED_BACKEND_REASON =
  "This design attaches network elements at conductor ends (junction-node " +
  "ports) — only the B-spline and sinusoidal-Galerkin solvers implement " +
  "them, and NEC-2 has no equivalent card.";

// hmatrix (hierarchical H-matrix / ACA) and arrayblock (element-aware block
// solver for arrays) are accelerators built on the same B-spline basis as
// bspline; they share its options and request shape, and fall back to the
// dense bspline path for ground/enrichment.
export const BSPLINE_FAMILY: Backend[] = ["bspline", "hmatrix", "arrayblock"];
export function isBSplineFamily(b: Backend): boolean {
  return BSPLINE_FAMILY.includes(b);
}

export function backendSupportsGround(b: Backend): boolean {
  // sinusoidal-galerkin: all three grounds since momwire#182 M4. (Junction-
  // port designs OVER a ground refuse server-side — a per-design error the
  // solve surfaces cleanly, not a backend capability gap.)
  return (
    b === "sinusoidal" ||
    b === "sinusoidal-galerkin" ||
    isBSplineFamily(b) ||
    b === "pynec"
  );
}

// Every ground-capable backend supports terrain. Momwire applies the
// per-facet far field natively; PyNEC runs the hybrid (issue #553): NEC
// solves the currents over crest-medium Sommerfeld — exactly what the
// terrain recipe feeds the current solve anyway — and the server's cut
// physics applies the facet reflection to those currents.
export function backendSupportsTerrain(b: Backend): boolean {
  return backendSupportsGround(b);
}

// Coerce a server-supplied backend name into something this UI knows.
// "triangular" was retired from the frontend (the server still accepts
// it and may still recommend it, e.g. from an older adapter or a saved
// design hint): map it to "bspline", the default working solver on the
// same dense path. Anything else unrecognised falls back to null ("no
// recommendation") so a stale value never reaches state or the wire.
export function normalizeBackend(b: string | null | undefined): Backend | null {
  if (!b) return null;
  if (b === "triangular") return "bspline";
  return (BACKEND_ORDER as string[]).includes(b) ? (b as Backend) : null;
}

export type CommonOpts = { nPerWire: number; wireRadius: number };

export type SinusoidalOpts = CommonOpts & { nQpConst: number };
// Sin-Galerkin only: the feed-model axis (issue #640, momwire#192).
// "segment" = NEC-compatible (NEC's segment-wide gap — reproduces NEC/EZNEC
// behaviour, including the reactance walk with mesh density); "point" =
// Converged (zero-width gap — converges to the B-spline answer; recommended
// for near-open high-Q designs, momwire#213). Deliberately NOT on plain
// sinusoidal: the point gap has no collocation RHS (momwire#212), so that
// solver offers no choice to present.
export type SinGalerkinOpts = SinusoidalOpts & { feedModel: "segment" | "point" };
export type BSplineOpts = CommonOpts & {
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
export type PyNECOpts = CommonOpts;

// hmatrix and arrayblock share BSplineOpts (same basis + knobs); the ACA
// tolerances use the solver defaults.
export type BackendOptsMap = {
  sinusoidal: SinusoidalOpts;
  // Same constructor surface as sinusoidal (momwire#182: same basis, Galerkin
  // testing) plus the feed-model choice only the Galerkin testing can carry;
  // the test-quadrature knobs keep their solver defaults.
  "sinusoidal-galerkin": SinGalerkinOpts;
  bspline: BSplineOpts;
  hmatrix: BSplineOpts;
  arrayblock: BSplineOpts;
  pynec: PyNECOpts;
};

export const BSPLINE_DEFAULT_OPTS: BSplineOpts = {
  nPerWire: 30,
  wireRadius: 0.0005,
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

export const DEFAULT_BACKEND_OPTS: BackendOptsMap = {
  sinusoidal: { nPerWire: 30, wireRadius: 0.0005, nQpConst: 8 },
  // feedModel "segment" (NEC-compatible) is the solver's own default; the
  // gear menu recommends "point" (Converged) on near-open designs (#640).
  "sinusoidal-galerkin": {
    nPerWire: 30,
    wireRadius: 0.0005,
    nQpConst: 8,
    feedModel: "segment",
  },
  bspline: { ...BSPLINE_DEFAULT_OPTS },
  hmatrix: { ...BSPLINE_DEFAULT_OPTS },
  // Arrays auto-select this; 21 segs/wire is the converged, correct-parity
  // choice for B-spline d=2 (odd → interior knot at the feed). The old
  // inherited 40 was both too many and the wrong (even) parity.
  arrayblock: { ...BSPLINE_DEFAULT_OPTS, nPerWire: 21 },
  pynec: { nPerWire: 21, wireRadius: 0.0005 },
};

// Three abstract solver slots. Each holds one backend choice and its
// options; the user picks A/B/C with the row of buttons, configures the
// inhabitants from the per-slot gear menu. Lets the same UI compare
// e.g. "B-spline d=2 @ N=15" against "B-spline d=1 @ N=20" without
// losing either setup.
export type Slot = "A" | "B" | "C";
export const SLOT_ORDER: Slot[] = ["A", "B", "C"];

export type SlotConfig = {
  backend: Backend;
  opts: BackendOptsMap[Backend];
};

// Display label for a configured backend: B-spline-family entries carry
// their spline degree so two b-spline slots (the default A d=2 / B d=1
// pair) stay distinguishable at a glance.
export function backendDisplayLabel(b: Backend, opts: BackendOptsMap[Backend]): string {
  if (isBSplineFamily(b))
    return `${BACKEND_LABEL[b]} d=${(opts as BSplineOpts).degree}`;
  // Surface the non-default feed model on the slot chip: two Sin-Galerkin
  // slots differing only in feed model must be tellable apart at a glance.
  if (b === "sinusoidal-galerkin" && (opts as SinGalerkinOpts).feedModel === "point")
    return `${BACKEND_LABEL[b]} (converged)`;
  return BACKEND_LABEL[b];
}

export const DEFAULT_SLOTS: Record<Slot, SlotConfig> = {
  // A is the default working solver: B-spline d=2 — most accurate per
  // unknown, converged at a small odd N (interior knot at the feed), and
  // its impedance solve honours finite grounds (Triangular, the old,
  // now-retired default, folded them to the PEC image). N=15 per the
  // basis-convergence census (docs/status/2026-07-20): within 2% of the
  // basis-agreed limit on 50/66 scorable designs (N=21 buys only 3 more,
  // all within 2.3%), patterns within 0.05 dB of the fine-mesh reference,
  // ~35% faster ticks. Odd parity keeps the feed's interior knot.
  A: {
    backend: "bspline",
    opts: { ...DEFAULT_BACKEND_OPTS.bspline, nPerWire: 15 },
  },
  // B is the cross-check basis: B-spline d=1 needs a larger N to reach
  // the same answer (slower), which is what makes agreement with A a
  // meaningful second opinion rather than the same solve twice. N=20
  // trades cross-check tightness for speed (within 2% of the limit on
  // 45/66 vs 55/66 at the old N=40 — disagreement with A beyond a couple
  // of percent warrants raising N before suspecting the design).
  B: {
    backend: "bspline",
    opts: { ...DEFAULT_BACKEND_OPTS.bspline, degree: 1, nPerWire: 20 },
  },
  C: {
    backend: "pynec",
    opts: { ...DEFAULT_BACKEND_OPTS.pynec },
  },
};

// Resolve a slot config against server capabilities (#429): if it names PyNEC
// and pynec-accel is absent, swap to the fallback backend with that backend's
// default kwargs, preserving the geometry-sizing (segments/wire, radius) the
// same way a manual backend swap does. Slot C defaults to PyNEC, so this is
// what keeps the default panel sensible on a server without it.
export function resolveSlotConfig(cfg: SlotConfig, havePynec: boolean): SlotConfig {
  const backend = resolveBackend(cfg.backend, havePynec);
  if (backend === cfg.backend) return cfg;
  return {
    backend,
    opts: {
      ...DEFAULT_BACKEND_OPTS[backend],
      nPerWire: cfg.opts.nPerWire,
      wireRadius: cfg.opts.wireRadius,
    } as BackendOptsMap[Backend],
  };
}

// Translates the camelCase frontend options into the snake_case kwargs the
// server forwards to each Momwire model class constructor.
export function modelOptionsForRequest(
  backend: Backend,
  opts: BackendOptsMap[Backend],
): Record<string, unknown> {
  if (backend === "sinusoidal-galerkin") {
    const o = opts as SinGalerkinOpts;
    // feed_model only here: plain sinusoidal cannot carry the point gap
    // (momwire#212) and must not receive the key at all.
    return { n_qp_const: o.nQpConst, feed_model: o.feedModel };
  }
  if (backend === "sinusoidal") {
    const o = opts as SinusoidalOpts;
    return { n_qp_const: o.nQpConst };
  }
  if (isBSplineFamily(backend)) {
    // bspline, hmatrix, and arrayblock all take the B-spline kwargs; the
    // accelerators read additional aca_tol/solve_tol from their own defaults.
    const o = opts as BSplineOpts;
    return {
      degree: o.degree,
      n_qp_pair: o.nQpPair,
      n_qp_source: o.nQpSource,
      feed_smoothing_factor: o.feedSmoothingFactor,
      use_singular_enrichment: o.useSingularEnrichment,
      enrichment_variant: o.enrichmentVariant,
      tikhonov_lambda: o.tikhonovLambda,
      auto_tap_ratio_threshold: o.autoTapRatioThreshold,
      n_qp_sing: o.nQpSing,
      enrichment_min_k: o.enrichmentMinK,
    };
  }
  return {};
}
