import { useEffect, useRef, useState, type MutableRefObject } from "react";
import type { SolveRequest } from "../../lib/api";
import type { BackendEntry } from "../../lib/backends";
import { closingAdvisories } from "../../lib/sweep";
import {
  paramFeedZinf,
  paramZinf,
  paramZinfReason,
  refinementX,
  type ParamSweepData,
  type ParamSweepRequest,
} from "../../lib/paramSweep";
import { apiFetch } from "../../lib/pin";

// One parameter sweep runner (docs/design/z-vs-param-view.md): Z against the
// density or one design knob, streamed from /param_sweep, with Stop, Run and
// the knob sweep's "only when asked" arming. Extracted from
// useAnalysisRunners (AK#1757 step 5 unit 2) so that every analysis chart can
// hold one of its own.

export type ParamSweepOptions = {
  /** What it sweeps. `auto: false` runs only when asked (armed or Run). */
  req: ParamSweepRequest;
  /** The request signature minus the swept parameter, plus the ladder
   *  (useAnalysisRunners' paramSweepSignature). */
  sig: string;
  /** Something that draws it is on screen (issue #715). */
  wanted: boolean;
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

/** What a parameter sweep runner publishes, and its controls. */
export type ParamSweepHandle = {
  data: ParamSweepData | null;
  running: boolean;
  phase: "idle" | "queued" | "running";
  stop: () => void;
  runNow: () => void;
  arm: () => void;
  /** Hold the change the next render brings: it does not run by itself,
   *  whatever the dwell switch says, and waits (dimmed) for Run. A pick
   *  that only selects (`[workbench.run_on_pick]`, AC6LA #179). */
  hold: () => void;
  /** The app's Cancel: stops it the way its own Stop does. */
  abort: () => void;
};

/** How many times one request is asked for again after the server dropped
 *  its stream (runParamSweep). */
export const PARAM_SWEEP_REISSUES = 2;

export function useParamSweep({
  req: paramSweepReq,
  sig: paramSweepSig,
  wanted: paramSweepWanted,
  autoSim,
  active,
  comboApproved,
  recommendedBackend,
  buildRequest,
  solveWithheld,
  seqRef,
  approvedComboRef,
  cell,
}: ParamSweepOptions): ParamSweepHandle {

  const [paramSweep, setParamSweep] = useState<ParamSweepData | null>(null);
  const [paramSweepRunning, setParamSweepRunning] = useState(false);
  // A sweep is waiting out its dwell (its timer is set). With `running`, the
  // runner's phase as the view publishes it (idle / queued / running): a
  // test that must show NO sweep follows a change waits for the decision
  // (idle) instead of sleeping past the dwell.
  const [paramSweepQueued, setParamSweepQueued] = useState(false);
  const paramSweepTimerRef = useRef<number | null>(null);
  const paramSweepAbortRef = useRef<AbortController | null>(null);
  // The signature a Stop (or the app's Cancel) left the parameter sweep
  // stopped at: the effect below neither blanks nor restarts for it, so the
  // partial points stay and nothing re-solves until a parameter changes (a
  // new signature) or the user presses Run.
  const paramSweepStoppedRef = useRef<string | null>(null);
  // A knob sweep runs only when asked (ParamSweepRequest.auto). The request
  // it was asked for — its signature — is "armed", and only an armed knob
  // sweep runs; `armNext` arms whatever request the next effect run sees
  // (a header edit or "Sweep this knob…" changes the spec, so its signature
  // is not known until the next render).
  const paramSweepArmedRef = useRef<string | null>(null);
  const paramSweepArmNextRef = useRef(false);
  // A pick that only selects (`hold`): the next request the effect sees runs
  // nothing by itself, even with the dwell switch on; Run runs it.
  const paramSweepHoldNextRef = useRef(false);
  // Re-issues of the current request after the server dropped its stream
  // (see runParamSweep's end): bounded, so a server that keeps dropping it
  // cannot loop the runner.
  const paramSweepReissuesRef = useRef(0);
  // The cell (`cell`) what is drawn was solved for.
  const drawnCellRef = useRef(cell);
  // Debounced parameter sweep: Z against the density or one design knob, on
  // the active slot's engine, whenever something that draws it (`wanted`) is
  // on screen. The swept field is overridden per point on the server; the
  // slot's own value stays what the live /ws solve uses.
  useEffect(() => {
    // Stopped at exactly this request: keep the partial sweep, run nothing.
    if (paramSweepStoppedRef.current === paramSweepSig) return;
    paramSweepStoppedRef.current = null;
    const wasRunning = paramSweepAbortRef.current !== null || paramSweepTimerRef.current !== null;
    paramSweepAbortRef.current?.abort();
    if (paramSweepTimerRef.current) {
      window.clearTimeout(paramSweepTimerRef.current);
      paramSweepTimerRef.current = null;
    }
    setParamSweepQueued(false);
    // Arming (a knob sweep only): the user's ask arms this request; leaving
    // everything that draws the sweep disarms, so coming back to the view
    // does not start it again.
    if (paramSweepArmNextRef.current && paramSweepWanted) {
      paramSweepArmedRef.current = paramSweepSig;
    }
    paramSweepArmNextRef.current = false;
    paramSweepReissuesRef.current = 0;
    const held = paramSweepHoldNextRef.current && paramSweepWanted;
    paramSweepHoldNextRef.current = false;
    if (!paramSweepWanted || held) paramSweepArmedRef.current = null;
    if (held || (paramSweepReq.auto === false && paramSweepArmedRef.current !== paramSweepSig)) {
      // A knob sweep nobody asked for at these inputs: run nothing. One
      // already drawn for this knob stays, dimmed as stale ("re-run?");
      // any other is cleared.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      const sameCell = drawnCellRef.current === cell;
      setParamSweep((d) =>
        d && d.param === paramSweepReq.param && sameCell
          ? { ...d, stale: true, ...(wasRunning ? { partial: true } : {}) }
          : null,
      );
      drawnCellRef.current = cell;
      setParamSweepRunning(false);
      return;
    }
    // Cancel-then-blank is the contract (#692/#715): the overlay must go blank
    // the instant its inputs change, or a stale curve reads as current while
    // the new one dwells. Synchronous blanking is what makes 'stale'
    // unrepresentable.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setParamSweep(null);
    drawnCellRef.current = cell;
    setParamSweepRunning(false);
    // Held when Paused (issue #612) — see the sweep effect. autoSim is a dep so
    // resuming Live restarts the parameter sweep.
    if (!autoSim || !paramSweepWanted || !active || paramSweepReq.values.length === 0) {
      return;
    }
    // Debounce only; the server lane orders it behind the live solve.
    // `runParamSweep` is an async function DECLARATION, so the binding is live
    // before this effect runs; the compiler cannot see hoisting (#768).
    // eslint-disable-next-line react-hooks/immutability
    paramSweepTimerRef.current = window.setTimeout(runParamSweep, 500);
    setParamSweepQueued(true);
    return () => {
      if (paramSweepTimerRef.current) window.clearTimeout(paramSweepTimerRef.current);
    };
    // runParamSweep omitted — same reasoning as the sweep effect above: a
    // plain unmemoized closure, with paramSweepSig standing in for its
    // actual inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    paramSweepSig,
    paramSweepWanted, // issue #715: the Smith trail or the view consumes it
    autoSim,
    active,
    // Poor-match gate (see the sweep effect).
    comboApproved, recommendedBackend,
  ]);

  // The cell's key changing with no change to what it solves (a chart of
  // one curve gaining a second, which names the first) leaves what is drawn
  // valid: it is that cell's. Declared after the effect above, so a change
  // of both is judged there first, against the old cell.
  useEffect(() => {
    drawnCellRef.current = cell;
  }, [cell]);

  // Unmounting (a closed tab or chart, a torn-down session) abandons the
  // sweep in flight: it is aborted, as a Stop aborts it, so its end never
  // reads as a dropped stream and asks again from a runner nothing draws.
  useEffect(
    () => () => {
      if (paramSweepTimerRef.current) window.clearTimeout(paramSweepTimerRef.current);
      paramSweepTimerRef.current = null;
      paramSweepAbortRef.current?.abort();
    },
    [],
  );

  async function runParamSweep() {
    setParamSweepQueued(false);
    // Same as runSweep: the server lane serializes and prioritizes; only the
    // poor-match gate holds this back (effect re-fires on approval).
    if (solveWithheld()) return;
    paramSweepTimerRef.current = null;
    paramSweepAbortRef.current?.abort();
    const controller = new AbortController();
    paramSweepAbortRef.current = controller;

    const { param, values, label, metric } = paramSweepReq;
    const hold = paramSweepReq.hold ?? null;
    const body = {
      ...buildRequest(),
      param,
      values,
      ...(metric !== undefined ? { metric } : {}),
      // A held sweep (AK#1757 step 6): the server re-solves the hold's knobs
      // at every point, resolving the hold on this curve's own design.
      ...(hold ? { hold: hold.spec } : {}),
      _gen: seqRef.current,
      _approved: approvedComboRef.current,
    };
    setParamSweepRunning(true);
    // feeds_* fields start OMITTED, same reasoning as runSweep's acc above.
    const acc: ParamSweepData = {
      param,
      label,
      values: [],
      z_re: [],
      z_im: [],
      z_re_extrap: null,
      z_im_extrap: null,
      ...(metric !== undefined ? { metric: [] } : {}),
      ...(hold ? { held: Object.fromEntries(hold.knobs.map((k) => [k, [] as number[]])), gaps: [] } : {}),
    };
    const publish = () => {
      if (controller.signal.aborted) return;
      setParamSweep({
        ...acc,
        values: acc.values.slice(),
        ...(acc.metric ? { metric: acc.metric.slice() } : {}),
        ...(acc.n_seg ? { n_seg: acc.n_seg.slice() } : {}),
        ...(acc.fed_seg_m ? { fed_seg_m: acc.fed_seg_m.slice() } : {}),
        z_re: acc.z_re.slice(),
        z_im: acc.z_im.slice(),
        // Spread-conditional, not `: undefined` — see runSweep's setSweep.
        ...(acc.feeds_z_re
          ? { feeds_z_re: acc.feeds_z_re.map((row) => row.slice()) }
          : {}),
        ...(acc.feeds_z_im
          ? { feeds_z_im: acc.feeds_z_im.map((row) => row.slice()) }
          : {}),
        ...(acc.feeds_z_re_extrap
          ? { feeds_z_re_extrap: acc.feeds_z_re_extrap.slice() }
          : {}),
        ...(acc.feeds_z_im_extrap
          ? { feeds_z_im_extrap: acc.feeds_z_im_extrap.slice() }
          : {}),
        ...(acc.feeds_z_extrap_p
          ? { feeds_z_extrap_p: acc.feeds_z_extrap_p.slice() }
          : {}),
        ...(acc.feeds_z_extrap_status
          ? { feeds_z_extrap_status: acc.feeds_z_extrap_status.slice() }
          : {}),
        ...(acc.advisories ? { advisories: acc.advisories.slice() } : {}),
        ...(acc.held
          ? { held: Object.fromEntries(Object.entries(acc.held).map(([k, v]) => [k, v.slice()])) }
          : {}),
        ...(acc.gaps ? { gaps: acc.gaps.slice() } : {}),
        ...(acc.error ? { error: acc.error } : {}),
        ...(acc.errorStatus ? { errorStatus: acc.errorStatus } : {}),
        ...(acc.partial ? { partial: true } : {}),
        ...(acc.timeLimitS !== undefined ? { timeLimitS: acc.timeLimitS } : {}),
      });
    };
    let dropped = false;
    try {
      const resp = await apiFetch("/param_sweep", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!resp.ok) {
        // Admission speaks for itself (the hosted point cap's 413, the
        // poor-match 403, a refused parameter's 422): show its detail.
        let detail = `the server refused the sweep (${resp.status})`;
        try {
          const j = await resp.json();
          if (j && typeof j.detail === "string") detail = j.detail;
        } catch {
          /* no JSON body: the status line above */
        }
        acc.error = detail;
        acc.errorStatus = resp.status;
        publish();
        return;
      }
      if (!resp.body) throw new Error(`param sweep failed: ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      // The first failed point's reason: when no point lands at all, it is
      // the engine refusing the design, which a chart names as that curve's
      // refused cell (AK#1757 step 5 unit 4b).
      let firstError: string | null = null;
      // The closing `{done}` record. The server ends a stream without it
      // when its lane drops the job (a newer generation superseded it, or
      // the solve was aborted): what landed is then not the sweep.
      let closed = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          const pt = JSON.parse(line);
          if (pt.done) {
            closed = true;
            // The closing record's advisories: the gap-fed density warning,
            // and the hosted time limit's stop, which also marks what landed
            // partial (the curve ended at its next point, not its last).
            const notes = closingAdvisories(pt);
            if (pt.stopped === "time") {
              acc.partial = true;
              acc.timeLimitS = Number.isFinite(pt.time_budget_s) ? pt.time_budget_s : null;
            }
            if (notes.length > 0) acc.advisories = notes;
            if (notes.length > 0 || acc.partial) publish();
            continue;
          }
          // A solver failure at one value (rare — a degenerate small-N
          // geometry) is reported by the backend as {value, error}; skip
          // rather than poisoning the trajectory.
          if (pt.error) {
            firstError ??= String(pt.error);
            // A held sweep's refusal at a solve (a multi-feed design) ends
            // its stream: say so on the chart, whatever already landed.
            if (hold && pt.value === undefined) {
              acc.error = String(pt.error);
              publish();
            }
            continue;
          }
          // A held point the optimizer did not converge at (step 6): a gap
          // at its x with its reason, never a value on the curve.
          if (acc.gaps && typeof pt.gap === "string" && Number.isFinite(pt.value)) {
            acc.gaps.push({ value: pt.value, reason: pt.gap });
            publish();
            continue;
          }
          // A record without a finite Z (never expected; JSON carries a
          // non-finite float as null) would poison every axis: skip it.
          if (!Number.isFinite(pt.z_re) || !Number.isFinite(pt.z_im)) continue;
          acc.values.push(pt.value);
          // The achieved segment count (AK#1781): Z∞'s x, as in the CLI.
          // One point without it and the whole sweep falls back to the
          // swept values, so x is never a mix of the two.
          if (Number.isFinite(pt.n_seg) && (acc.n_seg || acc.values.length === 1)) {
            (acc.n_seg ??= []).push(pt.n_seg);
          } else {
            delete acc.n_seg;
          }
          // The fed segment's length, on the same all-or-nothing rule: the
          // reason a rough Z∞ gives (feedMeshStep).
          if (
            Number.isFinite(pt.fed_seg_m) &&
            (acc.fed_seg_m || acc.values.length === 1)
          ) {
            (acc.fed_seg_m ??= []).push(pt.fed_seg_m);
          } else {
            delete acc.fed_seg_m;
          }
          acc.z_re.push(pt.z_re);
          acc.z_im.push(pt.z_im);
          // The metric read off this point's solve (AK#1828), or why not; a
          // held point's, off the solve at its optimum (AK#1757 step 6).
          if (acc.metric) {
            acc.metric.push(Number.isFinite(pt.metric) ? pt.metric : null);
            if (typeof pt.metric_error === "string") acc.metric_error ??= pt.metric_error;
          }
          // A held point's knobs, aligned with `values`.
          if (acc.held) {
            const h = (pt.held ?? {}) as Record<string, unknown>;
            for (const k of Object.keys(acc.held)) {
              const v = h[k];
              acc.held[k].push(typeof v === "number" ? v : Number.NaN);
            }
          }
          // Multi-feed records ship per-feed Z alongside the primary;
          // allocate the buffers lazily on first sight.
          if (Array.isArray(pt.feeds_z_re) && Array.isArray(pt.feeds_z_im)) {
            if (!acc.feeds_z_re) acc.feeds_z_re = [];
            if (!acc.feeds_z_im) acc.feeds_z_im = [];
            acc.feeds_z_re.push(pt.feeds_z_re);
            acc.feeds_z_im.push(pt.feeds_z_im);
          }
          // Z∞ — density only (paramZinf is null for a knob), per feed too,
          // one estimator with the CLI (lib/zinf.ts, AK#1781).
          const x = refinementX(acc.values, acc.n_seg);
          const z = paramZinf(param, x, acc.z_re, acc.z_im);
          acc.z_re_extrap = z?.re ?? null;
          acc.z_im_extrap = z?.im ?? null;
          acc.z_extrap_p = z?.p ?? null;
          acc.z_extrap_status = z?.status ?? null;
          acc.z_extrap_reason = paramZinfReason(z, acc.n_seg, acc.fed_seg_m);
          if (acc.feeds_z_re && acc.feeds_z_im) {
            const f = paramFeedZinf(param, x, acc.feeds_z_re, acc.feeds_z_im);
            if (f) {
              acc.feeds_z_re_extrap = f.map((e) => e.re);
              acc.feeds_z_im_extrap = f.map((e) => e.im);
              acc.feeds_z_extrap_p = f.map((e) => e.p);
              acc.feeds_z_extrap_status = f.map((e) => e.status);
            }
          }
          publish();
        }
      }
      if (firstError !== null && acc.values.length === 0 && !controller.signal.aborted) {
        acc.error = firstError;
        publish();
      }
      dropped = !closed && firstError === null && !acc.error && !controller.signal.aborted;
      if (closed) paramSweepReissuesRef.current = 0;
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("param sweep error", e);
    } finally {
      if (paramSweepAbortRef.current === controller) {
        paramSweepAbortRef.current = null;
        setParamSweepRunning(false);
      }
    }
    // A dropped stream (AK#1876). The server's lane supersedes a queued or
    // running point by generation (any newer live solve, such as the
    // session's first, which can follow a deep link's run), but this runner
    // re-issues only when its own signature changes, and a curve whose
    // request does not follow the live knobs (a state or design cell, the
    // swept knob itself) keeps its signature: dropped, it would end as a
    // curve with nothing in it, never asked for again. Still the request on
    // screen (a newer one or a Stop aborts this controller): ask again, at
    // the generation current now. Past the bound, what landed stays, partial.
    if (!dropped || controller.signal.aborted) return;
    if (paramSweepAbortRef.current !== null || paramSweepTimerRef.current !== null) return;
    if (paramSweepStoppedRef.current === paramSweepSig) return;
    if (paramSweepReissuesRef.current < PARAM_SWEEP_REISSUES) {
      paramSweepReissuesRef.current += 1;
      await runParamSweep();
      return;
    }
    acc.partial = true;
    publish();
  }

  // The header's Stop: abort the stream (the server sees the disconnect and
  // stops solving), keep what landed, marked partial, and hold here until a
  // parameter changes or Run.
  function stopParamSweep() {
    if (paramSweepTimerRef.current) window.clearTimeout(paramSweepTimerRef.current);
    paramSweepTimerRef.current = null;
    setParamSweepQueued(false);
    paramSweepAbortRef.current?.abort();
    paramSweepStoppedRef.current = paramSweepSig;
    setParamSweep((d) => (d ? { ...d, partial: true } : d));
    setParamSweepRunning(false);
  }

  // The header's Run: the same sweep again, now (no dwell), whatever stopped
  // it. Still behind the poor-match gate (runParamSweep checks it).
  function runParamSweepNow() {
    paramSweepStoppedRef.current = null;
    paramSweepReissuesRef.current = 0;
    paramSweepArmedRef.current = paramSweepSig;
    if (paramSweepTimerRef.current) window.clearTimeout(paramSweepTimerRef.current);
    setParamSweep(null);
    drawnCellRef.current = cell;
    void runParamSweep();
  }

  // Arm the next request the effect sees (a header edit, "Sweep this
  // knob…"): the user asked for that sweep, so it runs even as a knob sweep.
  function armParamSweep() {
    paramSweepArmNextRef.current = true;
  }

  // A pick that only selects: the next request waits for Run.
  function holdParamSweep() {
    paramSweepHoldNextRef.current = true;
  }

  // The app's Cancel stops the parameter sweep the way its own Stop does.
  function abort() {
    setParamSweepQueued(false);
    if (paramSweepAbortRef.current || paramSweepTimerRef.current) {
      paramSweepStoppedRef.current = paramSweepSig;
      setParamSweep((d) => (d ? { ...d, partial: true } : d));
    }
    if (paramSweepTimerRef.current) window.clearTimeout(paramSweepTimerRef.current);
    paramSweepTimerRef.current = null;
    paramSweepAbortRef.current?.abort();
  }

  return {
    data: paramSweep,
    running: paramSweepRunning,
    phase: paramSweepRunning ? "running" : paramSweepQueued ? "queued" : "idle",
    stop: stopParamSweep,
    runNow: runParamSweepNow,
    arm: armParamSweep,
    hold: holdParamSweep,
    abort,
  };
}
