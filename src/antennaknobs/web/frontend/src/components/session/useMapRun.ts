import { useEffect, useRef, useState, type MutableRefObject } from "react";
import type { SolveRequest } from "../../lib/api";
import type { BackendEntry } from "../../lib/backends";
import type { MapRunAxis } from "../../lib/analysisChart";
import { emptyGrid, type MapGrid } from "../../lib/mapGrid";
import { apiFetch } from "../../lib/pin";
import { solveSignature } from "../../lib/solveSignature";

// One map runner (docs/design/sweep-framework-map.md, unit 3): a two-knob
// map's grid, streamed from POST /map one node per record, y outer and x
// inner (the CLI's order), painting as each node lands. The analysis chart's
// run contract, as its other runners keep it (useParamSweep, usePatternCell):
//
//   - with the dwell switch off (a map's default, decision 7) it runs only
//     when asked (Run, or a pick that runs); an input change after that
//     keeps the map drawn, dimmed as stale ("re-run?"), and runs nothing;
//     with the switch on, a change re-runs after the 500 ms dwell;
//   - the two swept knobs are not its inputs (`mapSignature` exempts them):
//     every node sets both, so dragging x or y moves the chart's marker and
//     leaves the map current (decision 8). z0 is not either: Z is z0-free,
//     so a new z0 re-colours what is drawn and re-solves nothing;
//   - Stop and the app's Cancel keep what landed, marked partial, and hold
//     there until the inputs change or Run;
//   - its points carry no generation, so the server's lane never drops them
//     for a live solve (dragging x or y); if the stream still ends without
//     its closing record (a dropped connection), it is asked again FROM THE
//     FIRST NODE NOT YET LANDED (`from`), a bounded number of times, rather
//     than from the start: on an 8-minute map that is the difference;
//   - the hosted wall-time budget's stop (`stopped: "time"`) keeps the
//     partial map and says so (`timeLimitS`).

/** What a map runner holds once asked. `grid` fills as nodes land (null
 *  where a node has not, or failed: `failed` counts those). */
export type MapRunData = {
  grid: MapGrid;
  /** The axes this grid is over, as asked. */
  x: MapRunAxis;
  y: MapRunAxis;
  /** Nodes landed (solved or failed), in stream order: the next one to ask
   *  for on a resume is this flat index. */
  received: number;
  failed: number;
  /** The first failed node's reason, for the chart to name. */
  firstError?: string;
  /** The closing record arrived: the run is complete (or time-limited). */
  done: boolean;
  /** The hosted time budget stopped it (seconds; null when the server named
   *  none). Absent otherwise. */
  timeLimitS?: number | null;
  /** Admission refused it (the hosted cap's 413, the poor-match 403, a
   *  422), in the server's words. */
  error?: string;
  errorStatus?: number;
  /** Stopped (Stop, Cancel, or dropped past the re-asks) before it was
   *  done: what landed is all there is until Run. */
  partial?: boolean;
  /** Drawn for inputs that have since changed. */
  stale?: boolean;
};

export type MapRunOptions = {
  /** The cell request's physics signature (`mapSignature`). */
  sig: string;
  /** The two axes the grid is over. */
  x: MapRunAxis;
  y: MapRunAxis;
  /** The chart shows this map on screen. */
  wanted: boolean;
  /** Re-run after the dwell by itself (the chart's dwell switch). */
  auto: boolean;
  autoSim: boolean;
  active: boolean;
  comboApproved: boolean;
  recommendedBackend: BackendEntry | null;
  buildRequest: () => SolveRequest;
  solveWithheld: () => boolean;
  approvedComboRef: MutableRefObject<boolean>;
};

export type MapRunHandle = {
  data: MapRunData | null;
  running: boolean;
  phase: "idle" | "queued" | "running";
  stop: () => void;
  runNow: () => void;
  arm: () => void;
  /** A pick that only selects (`[workbench.run_on_pick]`): the change the
   *  next render brings waits for Run. */
  hold: () => void;
  abort: () => void;
};

/** How many times a dropped map stream is asked for again (from where it
 *  stopped). */
export const MAP_REISSUES = 2;

const DISPLAY_EXEMPT = ["az_elev_deg", "elev_az_deg", "z0_ohms", "terrain"] as const;

/** A map's signature over one cell request: the request minus the
 *  display-only fields and the two swept knobs, which every node sets
 *  itself, plus the axes. */
export function mapSignature(req: SolveRequest, x: MapRunAxis, y: MapRunAxis): string {
  return (
    solveSignature(req, { exempt: [...DISPLAY_EXEMPT, x.param, y.param] }) +
    JSON.stringify([x.param, x.values, y.param, y.values])
  );
}

export function useMapRun({
  sig,
  x,
  y,
  wanted,
  auto,
  autoSim,
  active,
  comboApproved,
  recommendedBackend,
  buildRequest,
  solveWithheld,
  approvedComboRef,
}: MapRunOptions): MapRunHandle {
  const [data, setData] = useState<MapRunData | null>(null);
  const [running, setRunning] = useState(false);
  const [queued, setQueued] = useState(false);
  const timerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // useParamSweep's refs, for the same reasons: where a Stop left it, what
  // the viewer asked for, whether the next change arms or only selects, and
  // the bounded re-asks of a dropped stream.
  const stoppedRef = useRef<string | null>(null);
  const armedRef = useRef<string | null>(null);
  const armNextRef = useRef(false);
  const holdNextRef = useRef(false);
  const reissuesRef = useRef(0);

  useEffect(() => {
    if (stoppedRef.current === sig) return;
    stoppedRef.current = null;
    const wasRunning = abortRef.current !== null || timerRef.current !== null;
    abortRef.current?.abort();
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setQueued(false);
    if (armNextRef.current && wanted) armedRef.current = sig;
    armNextRef.current = false;
    reissuesRef.current = 0;
    const held = holdNextRef.current && wanted;
    holdNextRef.current = false;
    if (!wanted || held) armedRef.current = null;
    if (held || (!auto && armedRef.current !== sig)) {
      // Nobody asked at these inputs: what is drawn stays, dimmed.
      // eslint-disable-next-line react-hooks/set-state-in-effect -- the runner's published state, as useParamSweep's
      setData((d) => (d ? { ...d, stale: true, ...(wasRunning ? { partial: true } : {}) } : null));
      setRunning(false);
      return;
    }
    setData(null);
    setRunning(false);
    // Held when Paused (issue #612), off screen, or before the design lands.
    if (!autoSim || !wanted || !active || x.values.length === 0 || y.values.length === 0) return;
    timerRef.current = window.setTimeout(() => void run(0, null), 500);
    setQueued(true);
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
    // run omitted: a plain closure, `sig` standing in for its inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig, wanted, auto, autoSim, active, comboApproved, recommendedBackend]);

  // Unmounting abandons the stream, as a Stop does.
  useEffect(
    () => () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
      abortRef.current?.abort();
    },
    [],
  );

  /** Stream the grid from flat node `from`, over `prior` (what landed
   *  before a dropped stream), or a fresh grid. */
  async function run(from: number, prior: MapRunData | null) {
    setQueued(false);
    // Only the poor-match gate holds it back; the server lane orders it.
    if (solveWithheld()) return;
    timerRef.current = null;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const nx = x.values.length;
    const grid = prior?.grid ?? emptyGrid(x.values, y.values);
    const re = grid.re.map((r) => r.slice());
    const im = grid.im.map((r) => r.slice());
    const acc: MapRunData = {
      x,
      y,
      grid: { xs: grid.xs, ys: grid.ys, re, im },
      received: from,
      failed: prior?.failed ?? 0,
      ...(prior?.firstError ? { firstError: prior.firstError } : {}),
      done: false,
    };
    const publish = () => {
      if (controller.signal.aborted) return;
      setData({
        ...acc,
        grid: { xs: acc.grid.xs, ys: acc.grid.ys, re: re.map((r) => r.slice()), im: im.map((r) => r.slice()) },
      });
    };
    setRunning(true);
    publish();
    let closed = false;
    try {
      const resp = await apiFetch("/map", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...buildRequest(),
          x,
          y,
          from,
          // No `_gen`: a map's points are never superseded by a live solve
          // (decision 8); the abort is how any other input stops it.
          _approved: approvedComboRef.current,
        }),
        signal: controller.signal,
      });
      if (!resp.ok) {
        let detail = `the server refused the map (${resp.status})`;
        try {
          const j = await resp.json();
          if (j && typeof j.detail === "string") detail = j.detail;
        } catch {
          /* no JSON body: the status line above */
        }
        acc.error = detail;
        acc.errorStatus = resp.status;
        closed = true;
        publish();
        return;
      }
      if (!resp.body) throw new Error(`map failed: ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      // Repaint at most every 50 ms: an 825-node map lands ~150 nodes a
      // second, and one canvas paint per node is wasted work.
      let last = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl;
        let landed = false;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          const pt = JSON.parse(line);
          if (pt.done) {
            closed = true;
            acc.done = true;
            if (pt.stopped === "time") {
              acc.timeLimitS = Number.isFinite(pt.time_budget_s) ? pt.time_budget_s : null;
            }
            landed = true;
            continue;
          }
          if (!Number.isInteger(pt.i) || !Number.isInteger(pt.j)) continue;
          acc.received = Math.max(acc.received, pt.j * nx + pt.i + 1);
          if (pt.error || !Number.isFinite(pt.z_re) || !Number.isFinite(pt.z_im)) {
            acc.failed += 1;
            acc.firstError ??= String(pt.error ?? "no impedance");
          } else {
            re[pt.j][pt.i] = pt.z_re;
            im[pt.j][pt.i] = pt.z_im;
          }
          landed = true;
        }
        const now = Date.now();
        if (landed && (now - last >= 50 || acc.done)) {
          last = now;
          publish();
        }
      }
      publish();
      if (closed) reissuesRef.current = 0;
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("map error", e);
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setRunning(false);
      }
    }
    // A dropped stream: ask again from the first node not yet landed, while
    // this is still the map on screen, a bounded number of times; past the
    // bound, what landed stays, partial.
    if (closed || controller.signal.aborted) return;
    if (abortRef.current !== null || timerRef.current !== null) return;
    if (stoppedRef.current === sig) return;
    if (reissuesRef.current < MAP_REISSUES) {
      reissuesRef.current += 1;
      await run(acc.received, acc);
      return;
    }
    acc.partial = true;
    publish();
  }

  function stop() {
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    setQueued(false);
    abortRef.current?.abort();
    stoppedRef.current = sig;
    setData((d) => (d && !d.done ? { ...d, partial: true } : d));
    setRunning(false);
  }

  function runNow() {
    stoppedRef.current = null;
    reissuesRef.current = 0;
    armedRef.current = sig;
    if (timerRef.current) window.clearTimeout(timerRef.current);
    setData(null);
    void run(0, null);
  }

  function arm() {
    armNextRef.current = true;
  }

  function hold() {
    holdNextRef.current = true;
  }

  function abort() {
    setQueued(false);
    if (abortRef.current || timerRef.current) {
      stoppedRef.current = sig;
      setData((d) => (d && !d.done ? { ...d, partial: true } : d));
    }
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
