// Shared roster fixtures (issue #628). The backend roster is server data now
// (GET /capabilities → adapter.backend_roster), so there is no module to
// import a roster from — these model the wire shape directly, the way
// GroundPanel.test.tsx models TerrainPresetSchema.
//
// SERVED_ROSTER mirrors what the real server sends today and is pinned
// Python-side by tests/test_backend_roster.py::test_backend_roster_served_shape;
// if the two ever disagree, one of them is the bug. Tests that care about a
// capability rather than a specific solver build their own entry with
// `backendEntry()` instead — including capabilities no real backend has yet
// (supports_ground: false) and backends that don't exist at all (the
// zero-frontend-change probe in newBackend.test.tsx).
import { defaultOptsFor, type BackendOpts } from "../lib/backends";
import { SERVED_CONSTRAINTS } from "./backendConstraintFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";
import type {
  BackendEntry,
  BackendOptionField,
  BackendRoster,
} from "../lib/backends";

export function backendOption(
  over: Partial<BackendOptionField> = {},
): BackendOptionField {
  return {
    key: "n_qp_const",
    label: "n_qp_const (GL pts)",
    min: 2,
    max: 32,
    step: 1,
    default: 8,
    ...over,
  };
}

export function backendEntry(over: Partial<BackendEntry> = {}): BackendEntry {
  return {
    name: "bspline",
    label: "B-spline",
    kind: "momwire",
    supports_ground: true,
    options_schema: [],
    panel: null,
    default_n_per_wire: 30,
    accelerator: false,
    dense_family: false,
    axes: null,
    bound: {},
    constraints: null,
    model_kwargs: [],
    ...over,
  };
}

// The axis payloads below are momwire's own, copied from a live
// `backend_roster(have_pynec=True, have_nec5=True)`. Only the axes each tab
// actually varies are interesting, but they are written out in full because a
// TRIMMED fixture would let `axisControls` pass here while returning something
// else against the real payload — the single-valued axes are precisely what
// the "multi-valued" clause has to see in order to reject them.
// Mirrors the server's shared tuples (`_SIN_FAMILY_KWARGS` etc.): the families
// genuinely share a constructor surface, so three literals here would be three
// things to drift. Pinned against the live payload by
// tests/test_frontend_option_spec_fixture.py.
const SIN_KWARGS = ["n_qp_const", "extended_kernel"];
const SIN_GALERKIN_KWARGS = ["n_qp_const", "feed_model", "extended_kernel"];
const BSPLINE_KWARGS = ["degree", "n_qp_pair", "n_qp_source", "feed_smoothing_factor", "use_singular_enrichment", "enrichment_variant", "tikhonov_lambda", "auto_tap_ratio_threshold", "n_qp_sing", "enrichment_min_k", "extended_kernel"];
const RAZOR_KWARGS = ["extended_kernel"];

const BSPLINE_AXES = {
  basis: ["bspline-1", "bspline-2"],
  testing: ["galerkin"],
  charge_support: ["spline"],
  kernel: ["extended", "reduced"],
  quadrature: ["converged"],
  solve_strategy: ["dense"],
  feed_model: ["segment-gap"],
  ground_model: ["free", "pec", "refl-coef", "sommerfeld"],
  wire_position: ["above", "buried", "contact"],
};

// Each entry's `constraints` come from the generated fixture, keyed by name,
// so the payload a test sees is the payload the server sends — prose included.
function withConstraints(b: BackendEntry): BackendEntry {
  return { ...b, constraints: SERVED_CONSTRAINTS[b.name] ?? null };
}

export const SERVED_ROSTER: BackendRoster = ([
  backendEntry({
    name: "sinusoidal",
    label: "Sinusoidal",
    model_kwargs: SIN_KWARGS,
    options_schema: [backendOption()],
    axes: {
      ...BSPLINE_AXES,
      basis: ["sinusoidal-3term"],
      testing: ["point-matching"],
      charge_support: ["basis-implied"],
      wire_position: ["above", "contact"],
    },
  }),
  backendEntry({
    name: "sinusoidal-galerkin",
    label: "Sin-Galerkin",
    model_kwargs: SIN_GALERKIN_KWARGS,
    options_schema: [backendOption()],
    panel: "sin-galerkin",
    dense_family: true,
    axes: {
      ...BSPLINE_AXES,
      basis: ["sinusoidal-3term"],
      charge_support: ["basis-implied"],
      feed_model: ["point-gap", "segment-gap"],
      wire_position: ["above", "contact"],
    },
  }),
  backendEntry({
    name: "bspline",
    label: "B-spline",
    panel: "bspline",
    model_kwargs: BSPLINE_KWARGS,
    dense_family: true,
    axes: BSPLINE_AXES,
  }),
  backendEntry({
    name: "hmatrix",
    label: "H-matrix (ACA)",
    model_kwargs: BSPLINE_KWARGS,
    panel: "bspline",
    accelerator: true,
    dense_family: true,
    axes: {
      ...BSPLINE_AXES,
      solve_strategy: ["aca"],
      wire_position: ["above", "contact"],
    },
  }),
  backendEntry({
    name: "arrayblock",
    label: "Array-block",
    model_kwargs: BSPLINE_KWARGS,
    panel: "bspline",
    default_n_per_wire: 21,
    accelerator: true,
    dense_family: true,
    axes: {
      ...BSPLINE_AXES,
      solve_strategy: ["element-block"],
      wire_position: ["above", "contact"],
    },
  }),
  // Absent from this fixture until #1006 G2-5, though the server has served it
  // since the razor tab landed and the Python twin
  // (test_backend_roster_served_shape) has always named it. The two disagreed
  // and, as the header says, one of them was the bug — this one. Nothing here
  // asserted the roster LENGTH, so the missing row cost nothing until a test
  // needed the one tab whose preset pins an axis.
  backendEntry({
    name: "razor-2p",
    label: "Razor (2-point)",
    model_kwargs: RAZOR_KWARGS,
    dense_family: true,
    axes: {
      ...BSPLINE_AXES,
      basis: ["tent"],
      testing: ["path"],
      charge_support: ["basis-implied"],
      quadrature: ["converged", "nec5"],
      feed_model: ["node-port"],
      wire_position: ["above", "contact"],
    },
    bound: { nec5_quadrature: true },
  }),
  backendEntry({
    name: "pynec",
    label: "PyNEC",
    kind: "pynec",
    panel: "pynec",
    default_n_per_wire: 21,
  }),
] as BackendRoster).map(withConstraints);

/** The roster a server without pynec-accel serves (#429): the entry is
 *  absent, not flagged. */
export const ROSTER_NO_PYNEC: BackendRoster = SERVED_ROSTER.filter(
  (b) => b.kind !== "pynec",
);

/** The roster a machine with a licensed NEC-5 binary serves (issue #825):
 *  the nec5 entry appears only when the server resolves $NEC5_EXE, so the
 *  DEFAULT SERVED_ROSTER above deliberately omits it — absence is the
 *  hosted-simulator shape. Python twin pin: test_backend_roster.py. */
export const ROSTER_WITH_NEC5: BackendRoster = [
  ...SERVED_ROSTER,
  backendEntry({
    name: "nec5",
    label: "NEC-5",
    kind: "nec5",
    panel: "nec5",
    default_n_per_wire: 20,
  }),
];

export function entry(name: string, roster: BackendRoster = SERVED_ROSTER): BackendEntry {
  const found = roster.find((b) => b.name === name);
  if (!found) throw new Error(`no fixture backend named ${name}`);
  return found;
}


/** Stock options for a fixture backend, using the SERVED spec catalogue.
 *
 *  `defaultOptsFor` takes the catalogue since #1006 G2-6 — the defaults are
 *  the server's, and a copy in the frontend is the duplication that unit
 *  removes. Tests go through this helper so the catalogue is threaded in one
 *  place rather than at every call site.
 */
export function stockOpts(name: string, over: Partial<BackendOpts> = {}): BackendOpts {
  return { ...defaultOptsFor(entry(name), SERVED_OPTION_SPECS), ...over };
}

/** Stock options with specific solver kwargs overridden, by SERVED key. */
export function optsWithModel(
  name: string,
  model: Record<string, unknown>,
): BackendOpts {
  const base = defaultOptsFor(entry(name), SERVED_OPTION_SPECS);
  return { ...base, model: { ...base.model, ...model } };
}
