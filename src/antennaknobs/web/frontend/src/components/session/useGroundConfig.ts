import { useState } from "react";
import { type BackendEntry } from "../../lib/backends";
import {
  defaultSoil,
  groundSummaryLabel,
  resolveGroundModel,
  soilSummaryLabel,
  type FiniteGroundMethod,
  type GroundModel,
  type GroundType,
  type SoilParams,
  type SoilPresetSchema,
  type SoilRanges,
  type TerrainParams,
} from "../../lib/ground";

// The ground/terrain selection and everything derived from it: the wire
// `ground_model` value the server protocol takes, the terrain change-detector
// string the solve and norm-check effects depend on, and the one-line summary
// the tab hover shows (#642 seam 5b-3). No effects here — the cluster is state
// plus derivations, so the component's global effect order is untouched.
export function useGroundConfig({
  backend,
  soilRanges,
  soilPresets,
}: {
  backend: BackendEntry;
  /** Served bounds+defaults, null on a server predating #1173. */
  soilRanges?: SoilRanges | null;
  soilPresets?: SoilPresetSchema[];
}) {
  // Ground plane at z = 0 (model per backend; see groundType). ON by
  // default: this is an HF wire-antenna workbench, and the over-ground
  // picture (takeoff angle, ground-lobed elevation pattern, shifted Z)
  // is the decision-relevant one — free space is the idealization you
  // opt into. The whole catalog solves grounded (75/75 audit, all
  // designs above z=0) on the default B-spline refl-coef path.
  const [groundEnabled, setGroundEnabled] = useState(true);
  // Shared ground choice — one selector describing the GROUND (finite vs
  // PEC); every backend solves it as best it can (see the GroundType note).
  const [groundType, setGroundType] = useState<GroundType>("finite");
  // Finite-ground method; hidden (and inert) on backends with a single
  // finite model, but kept in state so it survives backend flips during
  // engine comparison. Defaults to "fast" — Sommerfeld is opt-in (it costs
  // seconds per solve on the B-spline backend).
  const [finiteGroundMethod, setFiniteGroundMethod] =
    useState<FiniteGroundMethod>("fast");
  // Terrain preset + knobs (groundType === "terrain"; momwire only). One
  // flat params object for both presets so values survive preset flips.
  const [terrainPreset, setTerrainPreset] = useState<string>("levee");
  const [terrainParams, setTerrainParams] = useState<TerrainParams>({});
  // Wire value derived for the server protocol (see GroundModel). A
  // terrain selection quietly degrades to the finite method on any future
  // backend without terrain support (all current ground-capable backends
  // have it — PyNEC via the #553 hybrid).
  const groundModel: GroundModel = resolveGroundModel(
    groundType,
    backend,
    finiteGroundMethod,
  );

  // Solve-effect dep for the terrain knobs: only bites while terrain is
  // the active model, so parked levee state never re-solves a flat-ground
  // setup (and vice versa).
  const terrainKey =
    groundModel === "terrain"
      ? JSON.stringify([terrainPreset, terrainParams])
      : "";

  // Soil constants for the finite models (issue #1173). Seeded from the
  // SERVED defaults once /capabilities resolves — never from a literal here,
  // which would be a second copy of a number the server already owns and
  // clamps. Null until then (and forever on a server predating #1173), and
  // the panel renders no soil controls while it is null.
  const [soil, setSoil] = useState<SoilParams | null>(null);
  const servedDefault = defaultSoil(soilRanges ?? null);
  // Seeded DURING RENDER, not in an effect — the same #768 idiom as
  // fields.tsx's useNumericDraft, and what react-hooks/set-state-in-effect
  // requires. The effect spelling would paint one frame with no soil
  // controls and correct it on a second pass; this re-renders before
  // committing to the DOM, so the un-seeded state is never shown.
  //
  // Seeds ONCE, on the null→value transition only: re-seeding whenever the
  // served default changed would stomp a soil the user had dialled.
  if (soil === null && servedDefault !== null) {
    setSoil(servedDefault);
  }

  // Whether the finite models are the active ones. pec and terrain carry no
  // soil: terrain media are fixed (the #1173 non-goal) and PEC has none.
  const soilApplies = groundModel === "fast" || groundModel === "sommerfeld";

  // What rides on the request, or undefined. Omitted when it equals the
  // served default so that a default-soil request is byte-identical to a
  // pre-#1173 one: same cache key, same curve, nothing shipped changes.
  const soilForRequest: SoilParams | undefined =
    soilApplies &&
    soil &&
    servedDefault &&
    (soil.eps_r !== servedDefault.eps_r || soil.sigma !== servedDefault.sigma)
      ? soil
      : undefined;

  // Solve-effect dep, same shape as terrainKey: only bites while a finite
  // model is active, so a parked soil never re-solves a PEC setup. Keyed off
  // what is SENT, so dialling back to the default settles on the same key
  // the session started with rather than a third distinct value.
  const soilKey = soilForRequest
    ? JSON.stringify([soilForRequest.eps_r, soilForRequest.sigma])
    : "";

  const soilSummary = soilApplies
    ? soilSummaryLabel(soil, soilPresets ?? [])
    : "";

  // One-line tab-hover summary: design · solver N=segs · ground model.
  // Every backend honours the selected method (momwire >= 0.8.0), so the
  // wording is uniform; "free space" when ground is off or unsupported.
  const groundSummary = groundSummaryLabel(
    groundEnabled,
    backend,
    groundModel,
    terrainPreset,
  );

  return {
    groundEnabled,
    setGroundEnabled,
    groundType,
    setGroundType,
    finiteGroundMethod,
    setFiniteGroundMethod,
    terrainPreset,
    setTerrainPreset,
    terrainParams,
    setTerrainParams,
    groundModel,
    terrainKey,
    groundSummary,
    soil,
    setSoil,
    soilApplies,
    soilForRequest,
    soilKey,
    soilSummary,
  };
}
