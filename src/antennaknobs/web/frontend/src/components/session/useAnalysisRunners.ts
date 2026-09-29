import {
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import type { NormCheckData, SolveRequest } from "../../lib/api";
import { type BackendEntry } from "../../lib/backends";
import { type GroundModel } from "../../lib/ground";
import {
  DENSITY,
  DENSITY_LADDER,
  type ParamSweepRequest,
} from "../../lib/paramSweep";
import { type BandSpec, type ExampleDescriptor } from "../../lib/params";
import { ALL_SWEEP_PROJECTIONS, type SweepProjectionSet } from "../../lib/refine";
import { solveSignature } from "../../lib/solveSignature";
import {
  DEFAULT_AXES,
  DEFAULT_SWR_THRESHOLD,
  type SweepAxes,
} from "../../lib/sweepAxis";
import { resolveSweepRange, type SweepRange } from "../../lib/sweep";
import type { PatternData } from "../charts/types";
import { type SweepPhase, useFreqSweep } from "./useFreqSweep";
import { useParamSweep } from "./useParamSweep";

// Deliberate physics non-deps (issue #692), mirroring the server's
// _CACHE_KEY_BLOCKLIST (web/server.py) — the same idea at the other end of
// the wire. Cut angles are attached per-request AFTER the solve (POST /cuts,
// issue #547), so dragging a cut dial changes no analysis result: every
// analysis exempts them, exactly as the server cache does.
//
// The reference impedance (AK#1735) is exempt from every analysis for the
// same reason: it moves the SWR, the Smith centre and the |Γ| a chart draws,
// never an impedance a sweep computes, so a Zo edit re-draws rather than
// re-solves (the charts take the reference as a prop, below).
const DISPLAY_ONLY_EXEMPT = ["az_elev_deg", "elev_az_deg", "z0_ohms"] as const;

// The freq sweep and the parameter sweep are impedance-only, and every terrain
// preset shares the crest medium the impedance solve uses — so the terrain
// knobs are additionally exempt for those two. NOT for the norm check, whose
// pattern integral runs over the facets.
const IMPEDANCE_ANALYSIS_EXEMPT = [...DISPLAY_ONLY_EXEMPT, "terrain"] as const;

// The freq sweep alone is also exempt from the measurement frequency (Steve,
// 2026-09-26: moving the dial redrew the whole VSWR curve). A sweep solves at
// ITS OWN frequencies: every engine's sweep overrides measurement_freq_mhz
// per point (adapter.momwire_sweep, the pynec/nec2/nec5 _sweep_at), and the
// geometry is built at the design frequency, never the measurement one. So
// the dial slides the marker along the curve already drawn. Where the BAND
// follows the dial (a sweep_policy anchored on meas_freq), the band's own
// edges arrive through sweepRangeKey and re-sweep as before; a design that
// links a knob to the dial (link_meas_freq_to_param) changes that knob, which
// the signature sees. The parameter sweep solves AT the measurement
// frequency, so it keeps the field.
const FREQ_SWEEP_EXEMPT = [...IMPEDANCE_ANALYSIS_EXEMPT, "measurement_freq_mhz"] as const;


/** The freq sweep's physics signature over one request (FREQ_SWEEP_EXEMPT):
 *  what every frequency sweep runner keys on, the session's and a chart's. */
export function freqSweepSignature(req: SolveRequest): string {
  return solveSignature(req, { exempt: FREQ_SWEEP_EXEMPT });
}

/** A parameter sweep's signature. The sweep overrides its own parameter at
 *  every point, so the request's value of it changes no point: dragging the
 *  swept knob (or the slot's density, for a density sweep) moves the chart's
 *  current-value guide and re-solves nothing (the #1755 lesson). The ladder
 *  itself is part of the key: a new range is a new sweep. */
export function paramSweepSignature(
  req: SolveRequest,
  sweep: Pick<ParamSweepRequest, "param" | "values">,
): string {
  return (
    solveSignature(req, { exempt: [...IMPEDANCE_ANALYSIS_EXEMPT, sweep.param] }) +
    JSON.stringify([sweep.param, sweep.values])
  );
}

// The parameter sweep a caller that names none runs: the density ladder of
// the old convergence sweep (lib/paramSweep.ts DENSITY_LADDER).
const DENSITY_SWEEP: ParamSweepRequest = {
  param: DENSITY,
  values: [...DENSITY_LADDER],
  label: "N",
};


export type { SweepPhase };

/** One analysis chart curve's solve inputs (AK#1757 step 5 unit 4): its
 *  cell's solver slot and ground slot (lib/chartCells.ts) and the lane
 *  stream its batches run on (null: none, the first chart's first curve),
 *  which the session's `buildCellRequest` turns into a request; the engine
 *  and ground its frequency grid is planned for (defaultSweepPoints); and
 *  whether it is on the active solver slot, whose "Solve anyway" approval
 *  its batches then carry (any other slot's carry none). Plain data, so the
 *  session derives it during render. */
export type ChartCellRequest = {
  slot: string;
  ground: string;
  stream: string | null;
  backend: BackendEntry;
  groundEnabled: boolean;
  groundModel: GroundModel;
  onActiveSlot: boolean;
};

/** The approval a curve on another slot than the active one carries: none.
 *  The session's "Solve anyway" is for the active slot's engine; a poor
 *  match on another slot is a refused cell instead (DesignSession). */
export const NOT_APPROVED: MutableRefObject<boolean> = { current: false };


// The four background analyses that shadow the live solve — the freq sweep,
// the parameter sweep (density or a knob), the far-field norm check and the
// NEC rp_card pattern — with their debounce effects, timer/abort refs and
// streaming runners (#642 seam 5b-3).
//
// Each effect's physics invalidation is one request-signature dependency
// (issue #692): solveSignature(buildRequest()) minus the exemption lists
// above. Only gating/UI state that is not a request field stays hand-listed.
//
// Every dep-array member arrives as a plain per-render value, and buildRequest
// / solveWithheld as plain per-render functions: memoizing either would change
// which closure a pending debounce timeout fires. The signatures are fresh
// strings per render for the same reason — the string VALUE is what the dep
// arrays compare, so an unchanged request still skips the effect.
export function useAnalysisRunners({
  backend,
  currentVariant,
  currentExample,
  currentBands,
  freqWindowCeiling,
  designFreq,
  measFreq,
  measLocked,
  sweepRange,
  groundEnabled,
  groundModel,
  sweepEnabled,
  sweepAuto = true,
  normCheckEnabled,
  necOverlayEnabled,
  sweepResident,
  paramViewResident = false,
  paramSweep: paramSweepReq = DENSITY_SWEEP,
  patternResident,
  autoSim,
  active,
  comboApproved,
  recommendedBackend,
  z0 = 50,
  refineEnabled = true,
  residentSweepViews = ALL_SWEEP_PROJECTIONS,
  sweepAxes = DEFAULT_AXES,
  swrThreshold = DEFAULT_SWR_THRESHOLD,
  buildRequest,
  solveWithheld,
  seqRef,
  approvedComboRef,
  chartCell,
  buildCellRequest,
}: {
  backend: BackendEntry;
  currentVariant: string;
  currentExample: ExampleDescriptor | undefined;
  currentBands: BandSpec[];
  freqWindowCeiling: number;
  designFreq: number;
  measFreq: number;
  measLocked: boolean;
  /** AK#1682: the one range the measurement dial travels — DesignSession
   *  resolves it once and hands the SAME object to the dial and here, so
   *  the sweep's [lo, hi] is the dial's travel by construction. Omitted,
   *  the range is resolved from the fields above with no session edit
   *  (the design's own range, levels 2–5 of lib/sweep.ts). */
  sweepRange?: SweepRange;
  groundEnabled: boolean;
  groundModel: GroundModel;
  /** The freq sweep runs at all: the analysis chart shows a frequency sweep
   *  (AK#1757 step 5 unit 3; until then, the freq-sweep checkbox). */
  sweepEnabled: boolean;
  /** Re-sweep after the dwell by itself: the chart's dwell switch (the
   *  freq-sweep checkbox's meaning, moved onto the chart). Off, a change
   *  marks the sweep stale and it waits for `armSweep` / `runSweepNow`
   *  (useFreqSweep's run-on-request mode). Optional: omitted, it is on. */
  sweepAuto?: boolean;
  normCheckEnabled: boolean;
  necOverlayEnabled: boolean;
  /** View residency (issue #715): true when any view that RENDERS the
   *  analysis is pinned or active. DesignSession derives these from the
   *  view-rail state so this hook stays layout-agnostic — they are pure
   *  gating deps, exactly like the enable checkboxes, and join the gating
   *  half of each dep array (never the physics/signature half). The norm
   *  check has no residency prop on purpose: its consumer is the HUD
   *  readout, resident in every layout (see docs/plan-view-residency-
   *  gating.md). */
  sweepResident: boolean;
  /** The analysis chart shows a knob or density sweep, on its R/X or Smith
   *  view, and is on screen: the one thing the parameter sweep runs for now
   *  that the Smith view's "param sweep" switch is gone (AK#1757 step 5 unit
   *  3). Optional: omitted, the parameter sweep never runs. */
  paramViewResident?: boolean;
  /** What the parameter sweep sweeps: the parameter, its values and its
   *  display name. Omitted, it is the density ladder the old convergence
   *  sweep ran. */
  paramSweep?: ParamSweepRequest;
  patternResident: boolean;
  autoSim: boolean;
  active: boolean;
  comboApproved: boolean;
  recommendedBackend: BackendEntry | null;
  /** Reference impedance the sweep charts plot against — the only thing
   *  refinement (issue #744) needs beyond the sweep itself, since VSWR /
   *  S11 / Smith are all functions of Γ(Z, z0). Optional with the charts'
   *  own `result?.z0_ohms ?? 50` fallback: a caller that doesn't pass it
   *  gets refinement against the 50 Ω reference, which is right for every
   *  design that doesn't declare otherwise. Deliberately NOT a dep of any
   *  effect — z0 is a display reference, not physics, and re-planning the
   *  whole sweep when it changes would re-solve for nothing. */
  z0?: number;
  /** Master switch for adaptive refinement (sweep side; the cuts side reads
   *  the module flag in charts/cuts.ts — same setting, two consumers). Off
   *  means the base sweep is the final word: no second-dwell rounds, no
   *  extra solves — the escape hatch for large designs where even
   *  cache-warmed refinement rounds are real work. */
  refineEnabled?: boolean;
  /** Which sweep-consuming charts are on screen (finer than the boolean
   *  sweepResident above, which gates the BASE sweep): refinement plans
   *  against only these projections, so a VSWR-only session stops spending
   *  solves flattening a Smith locus nobody can see. Read per refinement
   *  ROUND via a ref, so mid-chain pin changes take effect immediately. */
  residentSweepViews?: SweepProjectionSet;
  /** The sweep charts' vertical ranges (AK#1738), so refinement judges
   *  curvature on the axes actually drawn. Read per ROUND via a ref, like
   *  the projection set: a range change mid-chain applies at the next round.
   *  Not an effect dep — a range is display, not physics, and changing it
   *  re-plans nothing already done. */
  sweepAxes?: SweepAxes;
  /** The SWR threshold (AK#1738), which Auto keeps on screen and so moves
   *  the drawn range; read per ROUND like sweepAxes. */
  swrThreshold?: number;
  buildRequest: () => SolveRequest;
  solveWithheld: () => boolean;
  seqRef: MutableRefObject<number>;
  approvedComboRef: MutableRefObject<boolean>;
  /** The engine and ground the analysis chart's first curve solves on
   *  (AK#1757 step 5 unit 4): its cell's request, the cell engine and
   *  ground the sweep grid is planned for, and the approval that request
   *  carries. The chart's frequency and parameter sweeps run on it; the
   *  norm check and the NEC pattern stay on the session's own request.
   *  Omitted, the chart's curve is the session's (the active slot and
   *  ground), as before crosses. */
  chartCell?: ChartCellRequest;
  /** A cell's request (DesignSession's buildCellRequest); given with
   *  `chartCell`. */
  buildCellRequest?: (cell: ChartCellRequest) => SolveRequest;
}) {
  // The range the sweep grids (AK#1682): the caller's, or the design's own.
  const effectiveSweepRange =
    sweepRange ??
    resolveSweepRange({
      currentExample,
      currentVariant,
      measLocked,
      measFreq,
      designFreq,
      currentBands,
      freqWindowCeiling,
    }).range;

  // The physics dependency of each effect below (issue #692): a fresh
  // buildRequest() per render, hashed down to a stable string. Anything that
  // changes the request — a knob, the variant, the measurement plane, a
  // NEW field someone adds next month — invalidates by default; the
  // exemption lists at the top of this module are the only opt-outs.
  const req = buildRequest();
  // The chart's first curve: its cell's request, else the session's.
  const cellBuild =
    chartCell && buildCellRequest ? () => buildCellRequest(chartCell) : buildRequest;
  const cellBackend = chartCell?.backend ?? backend;
  const cellGroundEnabled = chartCell?.groundEnabled ?? groundEnabled;
  const cellGroundModel = chartCell?.groundModel ?? groundModel;
  const cellApprovedRef = chartCell && !chartCell.onActiveSlot ? NOT_APPROVED : approvedComboRef;
  const cellReq = cellBuild === buildRequest ? req : cellBuild();
  // The parameter sweep overrides its own parameter at every point, so the
  // request's value of it changes no point: dragging the swept knob (or the
  // slot's density, for a density sweep) moves the chart's current-value
  // guide and re-solves nothing (the #1755 lesson). The ladder itself is
  // part of the key: a new range is a new sweep.
  const paramSweepSig = paramSweepSignature(cellReq, paramSweepReq);
  const freqSweepSig = freqSweepSignature(cellReq);
  const solveSig = solveSignature(req, { exempt: DISPLAY_ONLY_EXEMPT });

  // The freq sweep: the analysis chart's, when it shows a frequency sweep
  // (AK#1757 step 5 unit 3, which folded the standalone Smith / VSWR / S11
  // views and their freq-sweep switch into the chart), over the chart's
  // range and under its dwell switch. One runner, so one /sweep per change,
  // exactly the traffic the standalone views made (useFreqSweep).
  const freq = useFreqSweep({
    range: effectiveSweepRange,
    sig: freqSweepSig,
    enabled: sweepEnabled,
    resident: sweepResident,
    auto: sweepAuto,
    backend: cellBackend,
    groundEnabled: cellGroundEnabled,
    groundModel: cellGroundModel,
    refineEnabled,
    z0,
    residentSweepViews,
    sweepAxes,
    swrThreshold,
    autoSim,
    active,
    comboApproved,
    recommendedBackend,
    buildRequest: cellBuild,
    solveWithheld,
    seqRef,
    approvedComboRef: cellApprovedRef,
  });

  // The parameter sweep: the analysis chart's knob or density sweep, drawn
  // as R/X against the knob or as its trail on the Smith chart
  // (useParamSweep).
  const param = useParamSweep({
    req: paramSweepReq,
    sig: paramSweepSig,
    wanted: paramViewResident,
    autoSim,
    active,
    comboApproved,
    recommendedBackend,
    buildRequest: cellBuild,
    solveWithheld,
    seqRef,
    approvedComboRef: cellApprovedRef,
  });

  const [normCheck, setNormCheck] = useState<NormCheckData | null>(null);
  // NEC's rp_card pattern, fetched on a debounce so we don't fire one per
  // slider tick. Overlaid on the cuts as a comparison line.
  const [pattern, setPattern] = useState<PatternData | null>(null);

  const patternTimerRef = useRef<number | null>(null);
  const patternAbortRef = useRef<AbortController | null>(null);
  const normCheckTimerRef = useRef<number | null>(null);
  const normCheckAbortRef = useRef<AbortController | null>(null);

  // Debounced far-field norm consistency check. Same shape as the parameter
  // sweep: re-runs on any antenna/param change (which invalidates the norm),
  // gated by its own overlay checkbox. The server lane runs it after the
  // live solve (priority ordering), so it lands on that solve's cached
  // currents rather than forcing a re-solve.
  useEffect(() => {
    normCheckAbortRef.current?.abort();
    if (normCheckTimerRef.current) {
      window.clearTimeout(normCheckTimerRef.current);
    }
    // Cancel-then-blank is the contract (#692/#715): the overlay must go blank
    // the instant its inputs change, or a stale curve reads as current while
    // the new one dwells. Synchronous blanking is what makes 'stale'
    // unrepresentable.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setNormCheck(null);
    // Held when Paused (issue #612): the norm check re-solves, so it must not
    // run while the engine is held. autoSim is a dep — resuming Live re-runs it.
    if (!autoSim || !normCheckEnabled || !active) {
      return;
    }
    // `runNormCheck` is an async function DECLARATION, so the binding is live
    // before this effect runs; the compiler cannot see hoisting (#768).
    // eslint-disable-next-line react-hooks/immutability
    normCheckTimerRef.current = window.setTimeout(runNormCheck, 500);
    return () => {
      if (normCheckTimerRef.current) window.clearTimeout(normCheckTimerRef.current);
    };
    // runNormCheck omitted — same reasoning as the sweep effect above; note
    // this one stands in on solveSig, not impedanceSig (see below).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    // solveSig, not impedanceSig: the pattern integral runs over the facets,
    // so terrain knob changes invalidate the norm check (unlike the
    // impedance-only sweep/parameter-sweep effects above).
    solveSig,
    normCheckEnabled,
    autoSim,
    active,
    // Poor-match gate (see the sweep effect).
    comboApproved, recommendedBackend,
  ]);

  // Debounced NEC pattern fetch. PyNEC only — for momwire there's no rp_card
  // equivalent. Tracks measurement freq too (unlike the impedance sweep).
  // Held off entirely over terrain (the rp pattern is flat-ground only) and
  // when the user switches the overlay off.
  useEffect(() => {
    if (patternTimerRef.current) window.clearTimeout(patternTimerRef.current);
    // Cancel-then-blank is the contract (#692/#715): the overlay must go blank
    // the instant its inputs change, or a stale curve reads as current while
    // the new one dwells. Synchronous blanking is what makes 'stale'
    // unrepresentable.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPattern(null);
    if (
      !autoSim || // Paused holds the engine (issue #612) — no NEC re-solve.
      (backend.name !== "pynec" && backend.name !== "nec5") ||
      !active ||
      !necOverlayEnabled ||
      !patternResident || // issue #715: gated on the azimuth/elevation cuts
      groundModel === "terrain"
    ) {
      return;
    }
    patternTimerRef.current = window.setTimeout(() => {
      // `runPattern` is an async function DECLARATION, so the binding is live
      // before this effect runs; the compiler cannot see hoisting (#768).
      // eslint-disable-next-line react-hooks/immutability
      runPattern();
      patternTimerRef.current = null;
    }, 500);
    return () => {
      if (patternTimerRef.current) window.clearTimeout(patternTimerRef.current);
    };
    // runPattern omitted — same reasoning as the sweep effect above.
    // backend.name/groundModel are read only in the guard above; solveSig
    // (a request field for both) already re-fires this effect when either
    // changes, so listing them too would be redundant.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    // The backend/terrain gates above re-evaluate on the signature too:
    // solver, momwire_model and ground_model are all request fields.
    solveSig,
    necOverlayEnabled,
    patternResident,
    autoSim,
    active,
  ]);

  async function runNormCheck() {
    // The pattern norm reuses the settled live solve (a server cache hit):
    // the lane's live-first priority guarantees that ordering now, no
    // client-side timing needed. Only the poor-match gate holds this back.
    if (solveWithheld()) return;
    normCheckTimerRef.current = null;
    normCheckAbortRef.current?.abort();
    const controller = new AbortController();
    normCheckAbortRef.current = controller;
    try {
      const resp = await fetch("/norm_check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...buildRequest(),
          _gen: seqRef.current,
          _approved: approvedComboRef.current,
        }),
        signal: controller.signal,
      });
      if (!resp.ok) throw new Error(`norm check failed: ${resp.status}`);
      const data = await resp.json();
      if (controller.signal.aborted) return;
      if (!data.available) {
        setNormCheck(null);
        return;
      }
      const delta = 10 * Math.log10(data.pattern_norm / data.directivity_norm);
      setNormCheck({
        directivity_norm: data.directivity_norm,
        pattern_norm: data.pattern_norm,
        method: data.method,
        delta_db: delta,
        radiated_fraction: data.radiated_fraction ?? 0,
        radiation_efficiency: data.radiation_efficiency ?? 1,
      });
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("norm check error", e);
    } finally {
      if (normCheckAbortRef.current === controller) {
        normCheckAbortRef.current = null;
      }
    }
  }

  async function runPattern() {
    patternAbortRef.current?.abort();
    const controller = new AbortController();
    patternAbortRef.current = controller;
    try {
      const resp = await fetch("/pattern", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...buildRequest(), _gen: seqRef.current }),
        signal: controller.signal,
      });
      if (!resp.ok) throw new Error(`pattern failed: ${resp.status}`);
      const data = await resp.json();
      if (!data.available) {
        setPattern(null);
        return;
      }
      if (!controller.signal.aborted) setPattern(data as PatternData);
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("pattern error", e);
    } finally {
      if (patternAbortRef.current === controller) patternAbortRef.current = null;
    }
  }

  // The user's "Cancel solve" (AK#1712): stop every batch this session has in

  // The user's "Cancel solve" (AK#1712): stop every batch this session has in
  // flight or waiting on its dwell. The server's session cancel already trips
  // each one's lane token; aborting here as well closes the streams now rather
  // than when the server gets round to ending them, and clearing the dwell
  // timers stops a batch the user never saw start from starting a moment
  // after the cancel. What is already drawn stays drawn: the next knob change
  // re-runs everything through the effects above, as before.
  function abortInFlight() {
    param.abort();
    freq.abort();
    for (const timer of [normCheckTimerRef, patternTimerRef]) {
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = null;
    }
    for (const ctrl of [normCheckAbortRef, patternAbortRef]) {
      ctrl.current?.abort();
    }
  }

  return {
    sweep: freq.sweep,
    sweepRunning: freq.running,
    sweepPhase: freq.phase,
    sweepSettled: freq.settled,
    sweepProgress: freq.progress,
    sweepAdvisories: freq.advisories,
    sweepStale: freq.stale,
    armSweep: freq.arm,
    runSweepNow: freq.runNow,
    stopSweep: freq.abort,
    paramSweep: param.data,
    paramSweepRunning: param.running,
    paramSweepPhase: param.phase,
    stopParamSweep: param.stop,
    runParamSweepNow: param.runNow,
    armParamSweep: param.arm,
    normCheck,
    pattern,
    abortInFlight,
    /** This render's frequency sweep signature (the chart's first curve's
     *  request). */
    freqSweepSig,
    /** The two runners themselves, as the analysis chart's first curve
     *  (AK#1757 step 5 unit 4 treats every curve as a runner pair). */
    freq,
    param,
  };
}
