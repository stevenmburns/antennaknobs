import {
  useCallback,
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { type TerrainPresetSchema } from "../../lib/ground";
import {
  seedDefaults,
  type ExampleDescriptor,
  type ParamValueBag,
} from "../../lib/params";
import { type DesignLoadError } from "../AwaitingTrustPanel";

// The design catalog: everything DesignSession learns from the server about
// which antennas exist and what this backend can run (#642 seam 5b-3). The
// cluster moves whole — the two mount fetches, the trust action that re-fetches
// the catalog, and the auto-select effect that keeps `geometry` pointing at a
// design that still exists — so its internal hook order and every literal dep
// array are unchanged.
//
// Schema-driven parameter controls. Each registered example bundles
// its parameter schema in web/examples/<name>.py; the backend serves
// them on GET /examples and we render generic sliders from the result.
export function useDesignCatalog({
  geometry,
  setGeometry,
  setParamValues,
}: {
  geometry: string;
  setGeometry: (name: string) => void;
  setParamValues: Dispatch<SetStateAction<Record<string, ParamValueBag>>>;
}) {
  const [examples, setExamples] = useState<ExampleDescriptor[]>([]);
  const [examplesError, setExamplesError] = useState<string | null>(null);
  // Whether the server has the optional pynec-accel package (#429). Reported
  // by /examples on mount; gates the PyNEC backend option. Defaults true so
  // the common (installed) case never flashes the option off before the fetch
  // resolves; a false reply then hides it and remaps any PyNEC slot.
  const [havePynec, setHavePynec] = useState<boolean>(true);
  // Terrain preset catalog (issue #560), reported by /capabilities on mount.
  // Empty until it resolves (and on any older server without the field), which
  // gates the terrain ground option off — the panel is rendered entirely from
  // this schema, so there is nothing to show without it.
  const [terrainPresets, setTerrainPresets] = useState<TerrainPresetSchema[]>(
    [],
  );
  // User designs that failed to load (bad Python, no Builder, geometry error).
  // Surfaced from /examples so the author / Claude can see and fix them.
  const [loadErrors, setLoadErrors] = useState<DesignLoadError[]>([]);

  // Load (or reload) the design catalog. Extracted so a trust action can
  // re-fetch it — trusting a design registers it server-side, and re-fetching
  // moves it out of the "awaiting trust" list into the selector.
  const loadExamples = useCallback(async () => {
    try {
      const j = await (await fetch("/examples")).json();
      const list: ExampleDescriptor[] = j.examples ?? [];
      setExamples(list);
      setExamplesError(null);
      setLoadErrors(Array.isArray(j.errors) ? j.errors : []);
      // Walk each example's schema and pre-seed defaults — including
      // pre-allocated group instance arrays — so the sliders have
      // something to render against on first show.
      setParamValues((prev) => {
        const next = { ...prev };
        for (const ex of list) {
          if (next[ex.name]) continue;
          next[ex.name] = seedDefaults(ex.param_schema);
        }
        return next;
      });
    } catch (e: unknown) {
      setExamplesError(String((e as Error)?.message ?? e));
    }
    // setParamValues is the caller's useState setter — stable for the life of
    // the component, so the empty dep array is unchanged from before the move.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadExamples();
  }, [loadExamples]);

  // Backend capabilities (#429), fetched once on mount — server-static, so
  // unlike the design catalog it is not re-fetched on trust actions. A failed
  // fetch or an older server without the route leaves havePynec at its `true`
  // default (prior behavior). Gates the PyNEC backend option.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const c = await (await fetch("/capabilities")).json();
        if (!cancelled) {
          setHavePynec(c.have_pynec !== false);
          setTerrainPresets(
            Array.isArray(c.terrain_presets) ? c.terrain_presets : [],
          );
        }
      } catch {
        /* keep the default; PyNEC stays offered */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Trust a user design from the UI (local-only; the backend refuses when
  // hosted). `stem` is the design name (e.g. "user.my_dipole"); `allowEdits`
  // trusts future edits too (path-level, for a design you author).
  const [trustBusy, setTrustBusy] = useState<string | null>(null);
  const trustDesign = useCallback(
    async (stem: string, allowEdits: boolean) => {
      setTrustBusy(stem);
      try {
        const r = await fetch("/trust", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ stem, allow_edits: allowEdits }),
        });
        if (!r.ok) {
          const j = await r.json().catch(() => ({}));
          setExamplesError(`Trust failed: ${j.detail ?? r.status}`);
          return;
        }
        await loadExamples();
      } finally {
        setTrustBusy(null);
      }
    },
    [loadExamples],
  );

  // Auto-select a sensible default once /examples resolves, and recover if
  // the current selection disappears (e.g. backend dropped an example).
  // dipoles.invvee is the canonical simple antenna (also the CLI default);
  // fall back to the first example if it isn't registered.
  useEffect(() => {
    if (examples.length === 0) return;
    if (!examples.some((e) => e.name === geometry)) {
      const preferred = examples.find((e) => e.name === "dipoles.invvee");
      setGeometry((preferred ?? examples[0]).name);
    }
    // setGeometry is a stable useState setter; the literal deps are unchanged
    // from the pre-extraction effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [examples, geometry]);

  return {
    examples,
    examplesError,
    havePynec,
    terrainPresets,
    loadErrors,
    trustBusy,
    trustDesign,
  };
}
