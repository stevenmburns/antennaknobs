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
    ...over,
  };
}

export const SERVED_ROSTER: BackendRoster = [
  backendEntry({
    name: "sinusoidal",
    label: "Sinusoidal",
    options_schema: [backendOption()],
  }),
  backendEntry({
    name: "sinusoidal-galerkin",
    label: "Sin-Galerkin",
    options_schema: [backendOption()],
    panel: "sin-galerkin",
    dense_family: true,
  }),
  backendEntry({ name: "bspline", label: "B-spline", panel: "bspline", dense_family: true }),
  backendEntry({
    name: "hmatrix",
    label: "H-matrix (ACA)",
    panel: "bspline",
    accelerator: true,
    dense_family: true,
  }),
  backendEntry({
    name: "arrayblock",
    label: "Array-block",
    panel: "bspline",
    default_n_per_wire: 21,
    accelerator: true,
    dense_family: true,
  }),
  backendEntry({
    name: "pynec",
    label: "PyNEC",
    kind: "pynec",
    panel: "pynec",
    default_n_per_wire: 21,
  }),
];

/** The roster a server without pynec-accel serves (#429): the entry is
 *  absent, not flagged. */
export const ROSTER_NO_PYNEC: BackendRoster = SERVED_ROSTER.filter(
  (b) => b.kind !== "pynec",
);

export function entry(name: string, roster: BackendRoster = SERVED_ROSTER): BackendEntry {
  const found = roster.find((b) => b.name === name);
  if (!found) throw new Error(`no fixture backend named ${name}`);
  return found;
}
