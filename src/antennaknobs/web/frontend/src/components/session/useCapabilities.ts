import { useEffect, useState } from "react";
import type { BackendRoster } from "../../lib/backends";
import type { TerrainPresetSchema } from "../../lib/ground";

/** GET /capabilities, typed. `have_pynec` is still served for compatibility
 *  but is no longer read: PyNEC's availability is roster membership (#628). */
type CapabilitiesPayload = {
  backends?: BackendRoster;
  terrain_presets?: TerrainPresetSchema[];
};

export type CapabilitiesState = {
  /** null until the fetch resolves. There is deliberately no fallback roster:
   *  a hardcoded one is exactly the duplication issue #628 removes, so the
   *  backend-dependent UI waits instead of rendering a guess. */
  roster: BackendRoster | null;
  terrainPresets: TerrainPresetSchema[];
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

  return { roster, terrainPresets, error };
}
