import { useEffect, useRef, useState, type MutableRefObject } from "react";
import type { SolveRequest } from "../../lib/api";
import type { BackendEntry } from "../../lib/backends";
import {
  paramFeedZinf,
  paramZinf,
  paramZinfReason,
  refinementX,
  type ParamSweepData,
  type ParamSweepRequest,
} from "../../lib/paramSweep";

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
};

/** What a parameter sweep runner publishes, and its controls. */
export type ParamSweepHandle = {
  data: ParamSweepData | null;
  running: boolean;
  phase: "idle" | "queued" | "running";
  stop: () => void;
  runNow: () => void;
  arm: () => void;
  /** The app's Cancel: stops it the way its own Stop does. */
  abort: () => void;
};

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
    if (!paramSweepWanted) paramSweepArmedRef.current = null;
    if (paramSweepReq.auto === false && paramSweepArmedRef.current !== paramSweepSig) {
      // A knob sweep nobody asked for at these inputs: run nothing. One
      // already drawn for this knob stays, dimmed as stale ("re-run?");
      // any other is cleared.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setParamSweep((d) =>
        d && d.param === paramSweepReq.param
          ? { ...d, stale: true, ...(wasRunning ? { partial: true } : {}) }
          : null,
      );
      setParamSweepRunning(false);
      return;
    }
    // Cancel-then-blank is the contract (#692/#715): the overlay must go blank
    // the instant its inputs change, or a stale curve reads as current while
    // the new one dwells. Synchronous blanking is what makes 'stale'
    // unrepresentable.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setParamSweep(null);
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

  async function runParamSweep() {
    setParamSweepQueued(false);
    // Same as runSweep: the server lane serializes and prioritizes; only the
    // poor-match gate holds this back (effect re-fires on approval).
    if (solveWithheld()) return;
    paramSweepTimerRef.current = null;
    paramSweepAbortRef.current?.abort();
    const controller = new AbortController();
    paramSweepAbortRef.current = controller;

    const { param, values, label } = paramSweepReq;
    const body = {
      ...buildRequest(),
      param,
      values,
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
    };
    const publish = () => {
      if (controller.signal.aborted) return;
      setParamSweep({
        ...acc,
        values: acc.values.slice(),
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
        ...(acc.error ? { error: acc.error } : {}),
        ...(acc.errorStatus ? { errorStatus: acc.errorStatus } : {}),
      });
    };
    try {
      const resp = await fetch("/param_sweep", {
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
            // The closing record's advisories: the gap-fed density warning.
            if (Array.isArray(pt.advisories) && pt.advisories.length > 0) {
              acc.advisories = pt.advisories;
              publish();
            }
            continue;
          }
          // A solver failure at one value (rare — a degenerate small-N
          // geometry) is reported by the backend as {value, error}; skip
          // rather than poisoning the trajectory.
          if (pt.error) continue;
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
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("param sweep error", e);
    } finally {
      if (paramSweepAbortRef.current === controller) {
        paramSweepAbortRef.current = null;
        setParamSweepRunning(false);
      }
    }
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
    paramSweepArmedRef.current = paramSweepSig;
    if (paramSweepTimerRef.current) window.clearTimeout(paramSweepTimerRef.current);
    setParamSweep(null);
    void runParamSweep();
  }

  // Arm the next request the effect sees (a header edit, "Sweep this
  // knob…"): the user asked for that sweep, so it runs even as a knob sweep.
  function armParamSweep() {
    paramSweepArmNextRef.current = true;
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
    abort,
  };
}
