import { useEffect, useRef, useState, type MutableRefObject } from "react";
import type { SolveRequest, SolveResponse } from "../../lib/api";
import type { BackendEntry } from "../../lib/backends";
import type { PatternMetrics } from "../charts/types";
import { apiFetch } from "../../lib/pin";

// One pattern cell runner (AK#1757, sweep-framework step 7 unit 3): a
// pattern analysis's cell is ONE solve, at its measurement frequency, and the
// pattern pins' compare-table metrics for it, both from POST /pattern_cell.
// The same run/dwell contract as the chart's other runners (useParamSweep):
// with the dwell switch on (`auto`) a change re-solves after 500 ms; off, a
// change marks the cell stale until Run or an arm asks for it; Stop and the
// app's Cancel hold it where it is until its inputs change.
//
// The response's `solve` is the live solve's own shape, cuts attached at the
// chart's angles, so the chart draws it through the same cut machinery as the
// live far-field views and the pinned ghosts (charts/cuts.ts useCutTraces),
// re-cutting through /cuts for any other angle without a second solve.

/** What a pattern cell holds once asked: its solve and metrics, or the
 *  server's refusal (`error`, with the HTTP status where admission said
 *  it). `stale`: its inputs changed since, and the dwell switch is off. */
export type PatternCellData = {
  result: SolveResponse | null;
  metrics: PatternMetrics | null;
  error?: string;
  errorStatus?: number;
  stale?: boolean;
};

export type PatternCellOptions = {
  /** The cell request's physics signature (the cut angles exempt, as for
   *  every analysis: a view change re-cuts, it never re-solves). */
  sig: string;
  /** The chart shows this cell's pattern on screen. */
  wanted: boolean;
  /** Re-solve after the dwell by itself (the chart's dwell switch). */
  auto: boolean;
  /** The cut angles the solve ships with. */
  elevAzDeg: number;
  azElevDeg: number;
  autoSim: boolean;
  active: boolean;
  comboApproved: boolean;
  recommendedBackend: BackendEntry | null;
  buildRequest: () => SolveRequest;
  solveWithheld: () => boolean;
  seqRef: MutableRefObject<number>;
  approvedComboRef: MutableRefObject<boolean>;
  /** What the curve is drawn as on its chart (useChartCells' `cellKey`):
   *  a result kept stale through a change is kept only while this is the
   *  same, so a pick that moves the chart's cells never draws one cell's
   *  old curve under another cell's legend row (AC6LA, QRZ, on v0.97.1: a
   *  Sommerfeld sweep drawn as "free space"). Absent: not tracked. */
  cell?: string | undefined;
};

export type PatternCellHandle = {
  data: PatternCellData | null;
  running: boolean;
  phase: "idle" | "queued" | "running";
  stop: () => void;
  runNow: () => void;
  arm: () => void;
  /** Hold the change the next render brings: it does not run by itself,
   *  whatever the dwell switch says, and waits (dimmed) for Run. A pick
   *  that only selects (`[workbench.run_on_pick]`, AC6LA #179). */
  hold: () => void;
  abort: () => void;
};

export function usePatternCell({
  sig,
  wanted,
  auto,
  elevAzDeg,
  azElevDeg,
  autoSim,
  active,
  comboApproved,
  recommendedBackend,
  buildRequest,
  solveWithheld,
  seqRef,
  approvedComboRef,
  cell,
}: PatternCellOptions): PatternCellHandle {
  const [data, setData] = useState<PatternCellData | null>(null);
  const [running, setRunning] = useState(false);
  const [queued, setQueued] = useState(false);
  const timerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // The signature a Stop / Cancel left it at, the one the viewer asked for
  // (Run or an arm), and whether the next effect run arms: useParamSweep's
  // three refs, for the same three reasons.
  const stoppedRef = useRef<string | null>(null);
  const armedRef = useRef<string | null>(null);
  const armNextRef = useRef(false);
  // A pick that only selects (useParamSweep's `hold`).
  const holdNextRef = useRef(false);
  // The cell (`cell`) what is drawn was solved for.
  const drawnCellRef = useRef(cell);

  useEffect(() => {
    if (stoppedRef.current === sig) return;
    stoppedRef.current = null;
    abortRef.current?.abort();
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setQueued(false);
    if (armNextRef.current && wanted) armedRef.current = sig;
    armNextRef.current = false;
    const held = holdNextRef.current && wanted;
    holdNextRef.current = false;
    if (!wanted || held) armedRef.current = null;
    if (held || (!auto && armedRef.current !== sig)) {
      // Nobody asked at these inputs: what is drawn stays, dimmed as stale.
      // One solved for another cell is not this one's (PatternCellOptions.cell).
      if (drawnCellRef.current === cell) setData((d) => (d ? { ...d, stale: true } : null));
      else setData(null);
      drawnCellRef.current = cell;
      setRunning(false);
      return;
    }
    setData(null);
    setRunning(false);
    drawnCellRef.current = cell;
    // Held when Paused (issue #612), off screen, or before the design lands.
    if (!autoSim || !wanted || !active) return;
    timerRef.current = window.setTimeout(run, 500);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the dwell's own phase, as useParamSweep publishes it
    setQueued(true);
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
    // run omitted: a plain closure, `sig` standing in for its inputs (the
    // angles are display, exempt from `sig` like the live cut dials).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig, wanted, auto, autoSim, active, comboApproved, recommendedBackend]);

  // The cell's key changing with no change to what it solves (a chart of
  // one curve gaining a second, which names the first) leaves what is drawn
  // valid: it is that cell's. Declared after the effect above, so a change
  // of both is judged there first, against the old cell.
  useEffect(() => {
    drawnCellRef.current = cell;
  }, [cell]);

  async function run() {
    setQueued(false);
    // Only the poor-match gate holds it back; the server lane orders it.
    if (solveWithheld()) return;
    timerRef.current = null;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    try {
      const resp = await apiFetch("/pattern_cell", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...buildRequest(),
          elev_az_deg: elevAzDeg,
          az_elev_deg: azElevDeg,
          _gen: seqRef.current,
          _approved: approvedComboRef.current,
        }),
        signal: controller.signal,
      });
      if (!resp.ok) {
        // Admission speaks for itself (the poor-match 403, a hosted 413).
        let detail = `the server refused the pattern (${resp.status})`;
        try {
          const j = await resp.json();
          if (j && typeof j.detail === "string") detail = j.detail;
        } catch {
          /* no JSON body: the status line above */
        }
        if (!controller.signal.aborted) {
          setData({ result: null, metrics: null, error: detail, errorStatus: resp.status });
        }
        return;
      }
      const body = (await resp.json()) as {
        available?: boolean;
        solve?: SolveResponse;
        metrics?: PatternMetrics | null;
        error?: string;
      };
      if (controller.signal.aborted) return;
      if (body.available && body.solve) {
        setData({ result: body.solve, metrics: body.metrics ?? null });
      } else if (typeof body.error === "string") {
        setData({ result: null, metrics: null, error: body.error });
      }
      // Neither: superseded on the lane by a newer ask, which draws instead.
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("pattern cell error", e);
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setRunning(false);
      }
    }
  }

  function stop() {
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    setQueued(false);
    abortRef.current?.abort();
    stoppedRef.current = sig;
    setRunning(false);
  }

  function runNow() {
    stoppedRef.current = null;
    armedRef.current = sig;
    if (timerRef.current) window.clearTimeout(timerRef.current);
    setData(null);
    drawnCellRef.current = cell;
    void run();
  }

  function arm() {
    armNextRef.current = true;
  }

  function hold() {
    holdNextRef.current = true;
  }

  function abort() {
    setQueued(false);
    if (abortRef.current || timerRef.current) stoppedRef.current = sig;
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    abortRef.current?.abort();
  }

  return {
    data,
    running,
    phase: running ? "running" : queued ? "queued" : "idle",
    stop,
    runNow,
    arm,
    hold,
    abort,
  };
}
