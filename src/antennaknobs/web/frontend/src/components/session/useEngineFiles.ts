import { useEffect, useState } from "react";
import type { DesignSource, EngineIo, SolveRequest } from "../../lib/api";
import type { FilesViewData } from "../results/FilesPanel";

// The Files view's data (AK#1428): the file the design was written as, and the
// deck an external engine was given plus the report it printed.
//
// The source is fetched per DESIGN (POST /design_source, a file read). The
// engine texts are fetched per SOLVE, not per knob, and only for a solve whose
// response carries `engine_io_label`: the server stamps that on a solve that
// ran through a binary and keeps its runs under the solve_id, so the ask is a
// lookup. Which engines run a binary is the server's fact, not this file's
// (#1006 G2-6). Both fetches are gated on `active`, which the session sets
// only while Files is the view on the stage: opening the pane is the opt-in.
//
// Stale policy, the schematic's: a new solve keeps the previous texts up
// (flagged stale) until its own land; a design switch drops them at once,
// because another antenna's deck on screen is misinformation.
export function useEngineFiles({
  active,
  geometry,
  solveId,
  engineLabel,
  buildRequest,
}: {
  active: boolean;
  geometry: string;
  /** solve_id of the solve on screen when it is THIS design's; null while
   *  one is in flight. */
  solveId: string | null;
  /** That solve's `engine_io_label`: set only when it ran through an
   *  external engine's binary. */
  engineLabel: string | null;
  buildRequest: () => SolveRequest;
}): FilesViewData {
  const [source, setSource] = useState<DesignSource | null>(null);
  const [io, setIo] = useState<{
    geometry: string;
    solveId: string;
    data: EngineIo;
  } | null>(null);

  useEffect(() => {
    if (!active || !geometry) return;
    const controller = new AbortController();
    fetch("/design_source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ geometry }),
      signal: controller.signal,
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: DesignSource | null) => {
        if (!controller.signal.aborted && data) setSource(data);
      })
      .catch(() => {});
    return () => controller.abort();
  }, [active, geometry]);

  const have = io?.solveId ?? null;
  useEffect(() => {
    if (!active || !engineLabel || !solveId || have === solveId) return;
    const controller = new AbortController();
    // Debounced like the schematic: a drag lands a solve per tick, and only
    // the one the drag settles on is worth a printout.
    const t = setTimeout(() => {
      fetch("/engine_io", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...buildRequest(), solve_id: solveId }),
        signal: controller.signal,
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((data: EngineIo | null) => {
          // Only THIS solve's texts are taken. A superseded re-run carries
          // nothing. A reply naming another solve, or `moved` (this solve's
          // texts are gone and the request has changed since), would put a
          // different antenna's printout beside this readout. The newer solve
          // brings its own solve_id and asks again.
          if (
            controller.signal.aborted ||
            !data ||
            data.superseded ||
            data.moved ||
            data.solve_id !== solveId
          ) {
            return;
          }
          setIo({ geometry, solveId, data });
        })
        .catch(() => {});
    }, 250);
    return () => {
      clearTimeout(t);
      controller.abort();
    };
    // buildRequest is a plain closure over the session's live state (not
    // memoized); solveId is the real signature of what is on screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, engineLabel, solveId, have, geometry]);

  const shownIo = io && io.geometry === geometry ? io : null;
  return {
    geometry,
    // While a solve is in flight nothing on screen names an engine, so the
    // texts still showing (stale) name their own.
    engine: solveId !== null ? engineLabel : (shownIo?.data.label ?? null),
    solved: solveId !== null || shownIo !== null,
    source: source && source.geometry === geometry ? source : null,
    engineIo: shownIo?.data ?? null,
    stale: shownIo !== null && shownIo.solveId !== solveId,
  };
}
