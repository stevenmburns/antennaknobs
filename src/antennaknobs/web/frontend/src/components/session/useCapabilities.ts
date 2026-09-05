import { useEffect, useState } from "react";
import type {
  BackendRoster,
  ModelOptionSpecs,
  ServedSlotSeed,
  CompositionVocabulary,
} from "../../lib/backends";
import type {
  SoilPresetSchema,
  SoilRanges,
  TerrainPresetSchema,
} from "../../lib/ground";

/** GET /capabilities, typed. `have_pynec` is still served for compatibility
 *  but is no longer read: PyNEC's availability is roster membership (#628). */
type CapabilitiesPayload = {
  backends?: BackendRoster;
  terrain_presets?: TerrainPresetSchema[];
  soil_presets?: SoilPresetSchema[];
  soil_ranges?: SoilRanges;
  model_option_specs?: ModelOptionSpecs;
  backend_aliases?: Record<string, string>;
  default_slots?: ServedSlotSeed[];
  composition_axes?: string[];
  axis_value_labels?: Record<string, Record<string, string>>;
};

export type CapabilitiesState = {
  /** null until the fetch resolves. There is deliberately no fallback roster:
   *  a hardcoded one is exactly the duplication issue #628 removes, so the
   *  backend-dependent UI waits instead of rendering a guess. */
  roster: BackendRoster | null;
  terrainPresets: TerrainPresetSchema[];
  /** Named soils and the two knobs' bounds (#1173). Empty/null from a server
   *  predating it, and the ground panel then renders no soil controls —
   *  absence means "the server does not describe this", the same rule the
   *  terrain panel follows. Never a hardcoded fallback: the bounds here must
   *  be the same fact as the server-side clamp. */
  soilPresets: SoilPresetSchema[];
  soilRanges: SoilRanges | null;
  /** The solver-knob catalogue (#1006 G2-6), keyed by kwarg. Empty from a
   *  server predating it — "describes nothing", which yields a slot with no
   *  model options rather than a guess at some. Not an error path: the roster
   *  is what a session cannot start without. */
  modelOptionSpecs: ModelOptionSpecs;
  /** Retired backend names -> what supersedes each (#1006 G2-6). Empty from a
   *  server predating it, which simply means no name is rewritten. */
  backendAliases: Record<string, string>;
  /** The stock A/B/C seeds. Empty falls back to the roster's first entry for
   *  every slot — the same tolerance an absent seeded backend already got. */
  defaultSlotSeeds: ServedSlotSeed[];
  /** The composition line's vocabulary (#1006 G2-7). Empty axes from a server
   *  predating it, which renders no line rather than a guessed one. */
  compositionVocab: CompositionVocabulary;
  error: string | null;
};

// Server capabilities, fetched once per session mount — server-static, so
// unlike the design catalog it is never re-fetched. The solver roster (#628)
// and the terrain preset catalog (#560) both arrive here; the frontend renders
// both panels entirely from them, so a Python-only solver or preset needs no
// TypeScript.
export function useCapabilities(): CapabilitiesState {
  const [roster, setRoster] = useState<BackendRoster | null>(null);
  const [terrainPresets, setTerrainPresets] = useState<TerrainPresetSchema[]>(
    [],
  );
  const [soilPresets, setSoilPresets] = useState<SoilPresetSchema[]>([]);
  const [soilRanges, setSoilRanges] = useState<SoilRanges | null>(null);
  const [modelOptionSpecs, setModelOptionSpecs] = useState<ModelOptionSpecs>({});
  const [backendAliases, setBackendAliases] = useState<Record<string, string>>({});
  const [defaultSlotSeeds, setDefaultSlotSeeds] = useState<ServedSlotSeed[]>([]);
  const [compositionVocab, setCompositionVocab] = useState<CompositionVocabulary>({
    axes: [],
    labels: {},
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/capabilities");
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const c: CapabilitiesPayload = await r.json();
        if (cancelled) return;
        setTerrainPresets(
          Array.isArray(c.terrain_presets) ? c.terrain_presets : [],
        );
        setSoilPresets(Array.isArray(c.soil_presets) ? c.soil_presets : []);
        // Both knobs must be described or neither is: a half-served range
        // would otherwise render one slider with server bounds and one with
        // guessed ones.
        setSoilRanges(
          c.soil_ranges &&
            typeof c.soil_ranges === "object" &&
            c.soil_ranges.eps_r &&
            c.soil_ranges.sigma
            ? c.soil_ranges
            : null,
        );
        setModelOptionSpecs(
          c.model_option_specs && typeof c.model_option_specs === "object"
            ? c.model_option_specs
            : {},
        );
        setBackendAliases(
          c.backend_aliases && typeof c.backend_aliases === "object"
            ? c.backend_aliases
            : {},
        );
        setDefaultSlotSeeds(
          Array.isArray(c.default_slots) ? c.default_slots : [],
        );
        setCompositionVocab({
          axes: Array.isArray(c.composition_axes) ? c.composition_axes : [],
          labels:
            c.axis_value_labels && typeof c.axis_value_labels === "object"
              ? c.axis_value_labels
              : {},
        });
        // An empty roster is as unusable as a failed fetch — there would be
        // no solver to pick — so it takes the error path rather than
        // stranding the session on the loading note.
        if (Array.isArray(c.backends) && c.backends.length > 0) {
          setRoster(c.backends);
        } else {
          setError("the server reported no solver backends");
        }
      } catch (e: unknown) {
        if (!cancelled) setError(String((e as Error)?.message ?? e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return {
    roster,
    terrainPresets,
    soilPresets,
    soilRanges,
    modelOptionSpecs,
    backendAliases,
    defaultSlotSeeds,
    compositionVocab,
    error,
  };
}
