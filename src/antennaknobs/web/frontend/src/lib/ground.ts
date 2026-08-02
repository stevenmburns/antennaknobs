import type { Backend } from "./backends";
import { backendSupportsGround, backendSupportsTerrain } from "./backends";

// The UI separates WHAT the ground is from HOW it's solved. GroundType is
// the shared, backend-agnostic choice: a finite ground (εr=10, σ=0.002), a
// perfectly conducting one, or a faceted terrain (levee/cliff presets).
// It never promises more than the physics — each backend
// solves it as best it can: PyNEC and the plain B-spline backend offer a
// method sub-choice (Sommerfeld-Norton vs the reflection-coefficient
// approximation) — since momwire 0.8.0 every momwire backend honours both,
// so the choice is uniform across solvers; either way the finite constants
// reach the far-field Fresnel cut. Terrain solves impedance on the crest
// medium (Sommerfeld) and applies per-direction specular-facet reflection
// in the far field (issue #534).
export type GroundType = "finite" | "pec" | "terrain";
// Finite-ground solve method, shown for every finite-ground backend:
// PyNEC (NEC ITYPE=2 vs ITYPE=0) and, since momwire 0.8.0, every momwire
// solver (true Sommerfeld on bspline dense, sinusoidal field-based, and
// the hmatrix/arrayblock fast paths). "fast" is the default everywhere;
// Sommerfeld is opt-in because it is more expensive: the first solve at a
// new frequency fills an interpolation grid (~0.2-0.5 s on a small box;
// the first sweep pays that per point), and repeat solves at seen
// frequencies reuse cached grids (tens of ms).
export type FiniteGroundMethod = "sommerfeld" | "fast";
// The wire value (`ground_model` on SolveRequest): derived from groundType
// (+ the method wherever finite ground is supported).
export type GroundModel = "sommerfeld" | "fast" | "pec" | "terrain";

// Terrain preset schema, served by GET /capabilities (issue #560). The
// frontend renders the whole terrain knob panel from this — the presets,
// their field ranges/labels/units, and the read-only media note all live
// server-side (adapter.terrain_presets_schema), so a Python-only preset needs
// no TypeScript. Media are fixed server-side (water 80/0.005, land + crest
// 13/0.005); each preset's media_note describes its own.
export type TerrainFieldSchema = {
  key: string;
  label: string; // omits the unit; the panel renders "{label} ({unit})"
  unit: string | null;
  default: number;
  min: number;
  max: number;
  step: number;
};
export type TerrainPresetSchema = {
  name: string;
  label: string; // radio label
  tooltip: string; // radio hover text
  media_note: string;
  fields: TerrainFieldSchema[];
};
// Terrain knob values keyed by field key, sent (spread) as the request's
// `terrain` object when ground_model === "terrain". One flat bag across all
// presets so edits survive preset flips; an unset key falls back to the
// schema default and the server clamps every number.
export type TerrainParams = Record<string, number>;

// The wire value (`ground_model` on SolveRequest), derived from groundType
// (+ the finite-ground method wherever the active backend supports it). A
// terrain selection quietly degrades to the finite method on any backend
// without terrain support (all current ground-capable backends have it —
// PyNEC via the #553 hybrid).
export function resolveGroundModel(
  groundType: GroundType,
  backend: Backend,
  finiteGroundMethod: FiniteGroundMethod,
): GroundModel {
  return groundType === "pec"
    ? "pec"
    : groundType === "terrain" && backendSupportsTerrain(backend)
      ? "terrain"
      : backendSupportsGround(backend)
        ? finiteGroundMethod
        : "fast";
}

// One-line tab-hover ground summary: "free space", "PEC ground", "terrain
// (<preset>)", "reflection-coef ground", or "Sommerfeld ground". Every
// backend honours the selected method (momwire >= 0.8.0), so the wording is
// uniform; "free space" when ground is off or unsupported.
export function groundSummaryLabel(
  groundEnabled: boolean,
  backend: Backend,
  groundModel: GroundModel,
  terrainPreset: string,
): string {
  const groundActiveForSummary = groundEnabled && backendSupportsGround(backend);
  return !groundActiveForSummary
    ? "free space"
    : groundModel === "pec"
      ? "PEC ground"
      : groundModel === "terrain"
        ? `terrain (${terrainPreset})`
        : groundModel === "fast"
          ? "reflection-coef ground"
          : "Sommerfeld ground";
}
