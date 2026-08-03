import { useState } from "react";
import { type BackendEntry } from "../../lib/backends";
import {
  groundSummaryLabel,
  resolveGroundModel,
  type FiniteGroundMethod,
  type GroundModel,
  type GroundType,
  type TerrainParams,
} from "../../lib/ground";

// The ground/terrain selection and everything derived from it: the wire
// `ground_model` value the server protocol takes, the terrain change-detector
// string the solve and norm-check effects depend on, and the one-line summary
// the tab hover shows (#642 seam 5b-3). No effects here — the cluster is state
// plus derivations, so the component's global effect order is untouched.
export function useGroundConfig({ backend }: { backend: BackendEntry }) {
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
  };
}
