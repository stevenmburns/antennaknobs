import { useEffect, useRef, useState } from "react";
import type { SolveRequest } from "../../lib/api";

// The feed-network schematic (issue #652): server-rendered SVG from
// POST /schematic. No solve happens server-side — build_network() plus the
// schemdraw render is milliseconds — so this refetches on every knob/freq
// change like the geometry preview, debounced so a knob drag coalesces.
// The SVG is drawn in "currentColor", so the inlined markup follows the
// app theme with no refetch on theme flips.
export function useSchematic({
  active,
  geometry,
  requestKey,
  buildRequest,
  budget,
  inputPowerW,
}: {
  active: boolean;
  geometry: string;
  // Everything that can change the drawing (param values, variant, freqs),
  // pre-stringified by the caller. Solver/backend knobs are deliberately
  // absent: the network is the design's, not the solver's.
  requestKey: string;
  buildRequest: () => SolveRequest;
  // The latest solve's power budget (issue #652): structural (key, watts)
  // pairs plus that solve's input power, echoed in the POST so each block
  // draws its burn as the same percent the budget table shows. Null before
  // a solve lands — the drawing then simply carries no watts. This IS
  // solver output on a design-only endpoint, deliberately: /schematic never
  // solves, so the watts ride along from the solve the session already ran.
  budget?: [string, number][] | null;
  inputPowerW?: number | null;
}) {
  const [svg, setSvg] = useState<string | null>(null);
  // True once the server answered "no feed circuit" — the panel's empty
  // state. Distinct from svg === null alone, which is also the loading gap.
  const [unavailable, setUnavailable] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const forGeometryRef = useRef<string | null>(null);

  useEffect(() => {
    if (!active || !geometry) return;
    // A knob tweak keeps the previous drawing up while the refetch is in
    // flight (labels update when it lands, no flash). A design switch must
    // not: another antenna's feed chain on screen is misinformation.
    if (forGeometryRef.current !== geometry) {
      forGeometryRef.current = geometry;
      setSvg(null);
      setUnavailable(false);
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const t = setTimeout(() => {
      const body: SolveRequest & {
        budget?: [string, number][];
        input_power_w?: number;
      } = { ...buildRequest() };
      if (budget && budget.length) {
        body.budget = budget;
        if (inputPowerW) body.input_power_w = inputPowerW;
      }
      fetch("/schematic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (controller.signal.aborted || !data) return;
          if (data.available) {
            setSvg(data.svg as string);
            setUnavailable(false);
          } else {
            setSvg(null);
            setUnavailable(true);
          }
        })
        .catch(() => {});
    }, 250);
    return () => {
      clearTimeout(t);
      controller.abort();
    };
    // buildRequest is a plain closure over the session's live state (not
    // memoized); requestKey is the real dependency signature. The budget is
    // a dependency of its own: a knob change refetches immediately (labels
    // update, watts briefly stale), then the solve lands and this refetches
    // once more with the fresh watts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, geometry, requestKey, JSON.stringify([budget, inputPowerW])]);

  return { schematicSvg: svg, schematicUnavailable: unavailable };
}
