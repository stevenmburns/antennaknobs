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
import { SERVED_CONSTRAINTS } from "./backendConstraintFixtures";
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
    ...over,
  };
}

// The axis payloads below are momwire's own, copied from a live
// `backend_roster(have_pynec=True, have_nec5=True)`. Only the axes each tab
// actually varies are interesting, but they are written out in full because a
// TRIMMED fixture would let `axisControls` pass here while returning something
// else against the real payload — the single-valued axes are precisely what
// the "multi-valued" clause has to see in order to reject them.
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
    dense_family: true,
    axes: BSPLINE_AXES,
  }),
  backendEntry({
    name: "hmatrix",
    label: "H-matrix (ACA)",
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
