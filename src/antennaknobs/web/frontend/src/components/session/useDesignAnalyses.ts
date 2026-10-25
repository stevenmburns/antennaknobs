import { useEffect, useState } from "react";
import { type AnalysisEntry, parseAnalyses } from "../../lib/analyses";
import { apiFetch } from "../../lib/pin";

const NONE: AnalysisEntry[] = [];
const NO_REFUSALS: Refusals = { link: null, built: null };

/** Why /analyses did not read a catalog design's link analyses or a built
 *  one (AK#2045), in its words; null for none. */
export type Refusals = { link: string | null; built: string | null };

const said = (v: unknown): string | null => (typeof v === "string" && v ? v : null);

// The design's analyses for the Z-vs-parameter view's picker (AK#1757,
// sweep-framework step 3), fetched from POST /analyses once per design (a
// design, variant or reload key), and only while the view is on screen:
// listing a design's analyses builds it on the server, so a session that
// never opens the view never asks. A failure is no analyses, not an error:
// the picker is simply absent.
export function useDesignAnalyses({
  designKey,
  enabled,
  request,
}: {
  /** Changes when the design does: geometry, variant, reload generation. */
  designKey: string;
  /** The view is resident. */
  enabled: boolean;
  /** The solve request the builder is made from (read when fetching). */
  request: () => object;
}): { entries: AnalysisEntry[]; loaded: boolean; refusals: Refusals } {
  const [got, setGot] = useState<{ key: string; entries: AnalysisEntry[]; refusals: Refusals } | null>(null);
  const have = got?.key === designKey;
  useEffect(() => {
    if (!enabled || have) return;
    const controller = new AbortController();
    // Inside a promise, so a fetch that throws synchronously (a test's stub)
    // lands in the catch like any other failure.
    Promise.resolve()
      .then(() =>
        apiFetch("/analyses", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request()),
          signal: controller.signal,
        }),
      )
      .then((r) => (r.ok ? r.json() : null))
      .then((body: unknown) => {
        if (controller.signal.aborted) return;
        const o = (body ?? {}) as Record<string, unknown>;
        setGot({
          key: designKey,
          entries: parseAnalyses(body),
          refusals: { link: said(o.analyses_refusal), built: said(o.built_refusal) },
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) setGot({ key: designKey, entries: [], refusals: NO_REFUSALS });
      });
    return () => controller.abort();
    // `request` is read when the fetch starts, not a trigger: the list is
    // the design's, and a knob drag must not re-fetch it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [designKey, enabled, have]);
  // `loaded`: /analyses has answered for this design (a deep link waits on
  // it, AK#1838, since an empty list is also what a pending fetch shows).
  return have
    ? { entries: got.entries, loaded: true, refusals: got.refusals }
    : { entries: NONE, loaded: false, refusals: NO_REFUSALS };
}
