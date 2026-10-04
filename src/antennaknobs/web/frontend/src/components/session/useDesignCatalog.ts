import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type Dispatch,
  type SetStateAction,
} from "react";
import { openedDecks, subscribeDecks } from "../../lib/decks";
import {
  mergeSeededDefaults,
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
  preferred,
}: {
  geometry: string;
  setGeometry: (name: string) => void;
  setParamValues: Dispatch<SetStateAction<Record<string, ParamValueBag>>>;
  /** The design the session opens on, when it names one the catalog holds
   *  (a deep link's, AK#1838); null or absent, dipoles.invvee. Asked only
   *  for the first pick, never to recover a vanished selection. */
  preferred?: (examples: ExampleDescriptor[]) => string | null;
}) {
  // The server's catalog, and (below) it with the decks this page opened.
  const [served, setExamples] = useState<ExampleDescriptor[]>([]);
  const [examplesError, setExamplesError] = useState<string | null>(null);
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
      // something to render against on first show. Designs already seen
      // merge-seed instead (issue #867): tuned values survive, but params
      // an edited user design just grew get their defaults filled in.
      setParamValues((prev) => {
        const next = { ...prev };
        for (const ex of list) {
          const seeded = seedDefaults(ex.param_schema);
          next[ex.name] = next[ex.name]
            ? mergeSeededDefaults(seeded, next[ex.name])
            : seeded;
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
    // Fetch-on-mount; the setState happens in the async result, not as a
    // render-derivable value (#768).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadExamples();
  }, [loadExamples]);

  // (Server capabilities — the solver roster and the terrain presets — are
  // fetched by useCapabilities, above this component: the session tree only
  // mounts once they land, so nothing here has to cope with their absence.)

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

  // Opened decks (lib/decks.ts) join the catalog in every tab of the page:
  // the server never lists them (they are the opening browser's), so they
  // ride after the served designs, each under its `deck.<hash>` key.
  const opened = useSyncExternalStore(subscribeDecks, openedDecks);
  const examples = useMemo(() => {
    if (opened.length === 0) return served;
    const have = new Set(served.map((e) => e.name));
    return [...served, ...opened.filter((d) => !have.has(d.key)).map((d) => d.example)];
  }, [served, opened]);
  useEffect(() => {
    // An opened deck's knobs start at its own values, as a served design's.
    setParamValues((prev) => {
      let next = prev;
      for (const d of opened) {
        if (next[d.key]) continue;
        if (next === prev) next = { ...prev };
        next[d.key] = seedDefaults(d.example.param_schema);
      }
      return next;
    });
    // setParamValues is the caller's stable useState setter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened]);

  // Auto-select a sensible default once /examples resolves, and recover if
  // the current selection disappears (e.g. backend dropped an example).
  // dipoles.invvee is the canonical simple antenna (also the CLI default);
  // fall back to the first example if it isn't registered. A deep link's
  // design (`preferred`) wins on the first pick, so the session never opens
  // on invvee first and then switches.
  useEffect(() => {
    // Waits for the server's catalog: an opened deck alone is no reason to
    // pick (the default design is a served one).
    if (served.length === 0) return;
    if (!examples.some((e) => e.name === geometry)) {
      const linked = geometry === "" ? (preferred?.(examples) ?? null) : null;
      const fallback = examples.find((e) => e.name === "dipoles.invvee");
      setGeometry(linked ?? (fallback ?? examples[0]).name);
    }
    // setGeometry is a stable useState setter; the literal deps are unchanged
    // from the pre-extraction effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [examples, served, geometry]);

  return {
    examples,
    examplesError,
    loadErrors,
    trustBusy,
    trustDesign,
    // For the user-design reload button (issue #867): the server re-registers
    // user designs on every GET /examples, so a bare re-fetch IS the reload.
    reloadCatalog: loadExamples,
  };
}
