import { useEffect, useRef, useState, type MutableRefObject } from "react";
import type { SolveRequest, SweepData } from "../../lib/api";
import type { BackendEntry } from "../../lib/backends";
import type { GroundModel } from "../../lib/ground";
import { refineSweepFreqs, type SweepProjectionSet } from "../../lib/refine";
import {
  defaultSweepPoints,
  mergeSweepPoints,
  sweepGrid,
  type SweepProgress,
  type SweepRange,
  SWEEP_REFINE_BUDGET,
  SWEEP_REFINE_ROUND_BUDGET,
} from "../../lib/sweep";
import type { SweepAxes } from "../../lib/sweepAxis";
import type { Advisory } from "../results/SolverAdvisories";

// One frequency sweep runner: the debounced base sweep over a range, its
// adaptive refinement rounds (issue #744) and their phase, progress and
// advisories. Extracted from useAnalysisRunners (AK#1757 step 5 unit 2) so
// that it can be instantiated once per analysis chart: the session's one
// instance is the chart's since unit 3 folded the standalone Smith / VSWR /
// S11 views and their freq-sweep switch into it, over the chart's range and
// gated by its dwell switch; a second chart (unit 4) holds another.
//
// Two modes, by `auto`:
//   - auto (the session's sweep, and a chart with its dwell switch on): any
//     change to the inputs cancels, blanks and re-sweeps after the 500 ms
//     dwell, exactly as the freq sweep always has;
//   - not auto (a chart with its dwell switch off): the sweep runs only for
//     inputs it was ASKED for (`arm` before the change, or `runNow`). A later
//     change keeps the curve drawn, marked `stale`, and runs nothing, the way
//     a knob sweep waits for Run.
// Extra dwell between a completed base sweep and the first refinement round
// (issue #744). The base sweep is already post-dwell — the 500 ms debounce
// below gates it and a knob change aborts it — so this is a second settling
// window, not the first: it buys the stretch where the user has stopped
// dragging but is still deciding, during which the *next* knob move should
// find the lane empty. Same 500 ms as every other dwell in this module.
const SWEEP_REFINE_DWELL_MS = 500;

/** Accumulate a /sweep NDJSON stream into a SweepData, publishing a fresh
 *  snapshot per point so the charts fill in as they land. Shared by the
 *  base sweep and its refinement rounds — they differ only in which freqs
 *  they ask for and what the caller does with the snapshots. Throws
 *  AbortError (via fetch) when the controller is tripped; the callers own
 *  that. `onDone` sees the closing record, which carries the sweep's
 *  `advisories` when the server has any (AK#1681/#1682). */
async function streamSweep(
  body: object,
  controller: AbortController,
  onPoint: (snapshot: SweepData) => void,
  onDone?: (closing: { advisories?: Advisory[] }) => void,
): Promise<SweepData> {
  // feeds_z_re/feeds_z_im start OMITTED (not set to undefined): the type's
  // doc comment says single-feed geometries omit them entirely, and
  // exactOptionalPropertyTypes now enforces that distinction — `acc.feeds_z_re`
  // still reads as undefined either way, so this is a no-op for behavior.
  const acc: SweepData = { freqs_mhz: [], z_re: [], z_im: [] };
  const snapshot = (): SweepData => ({
    freqs_mhz: acc.freqs_mhz.slice(),
    z_re: acc.z_re.slice(),
    z_im: acc.z_im.slice(),
    // Spread-conditional, not `: undefined`, so a single-feed sweep OMITS
    // the key (matching SweepData's documented contract).
    ...(acc.feeds_z_re
      ? { feeds_z_re: acc.feeds_z_re.map((row) => row.slice()) }
      : {}),
    ...(acc.feeds_z_im
      ? { feeds_z_im: acc.feeds_z_im.map((row) => row.slice()) }
      : {}),
  });
  const resp = await fetch("/sweep", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: controller.signal,
  });
  if (!resp.ok || !resp.body) {
    // The server's refusal in its own words (the poor-match gate's 403, the
    // hosted cap's 413), for a chart to name: a cell on another slot's
    // engine has no "Solve anyway" of its own (AK#1757 step 5 unit 4).
    let detail = "";
    try {
      const body = (await resp.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* no JSON body */
    }
    throw new Error(detail || `sweep failed: ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  // The first failed point's reason: when no point lands at all, it is the
  // engine refusing the design (NEC-2 and a vertex feed), which a chart
  // names as that curve's refused cell (AK#1757 step 5 unit 4b).
  let firstError: string | null = null;
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
        if (!controller.signal.aborted) onDone?.(pt);
        continue;
      }
      // A failed point/chunk ends the stream with {error} instead of
      // tearing the connection down (e.g. an approved poor-match combo
      // whose dense fill can't allocate). Keep whatever points landed.
      if (pt.error) {
        console.error("sweep error", pt.error);
        firstError ??= String(pt.error);
        continue;
      }
      acc.freqs_mhz.push(pt.freq_mhz);
      acc.z_re.push(pt.z_re);
      acc.z_im.push(pt.z_im);
      // Multi-feed sweep records (bowtie) ship per-feed Z alongside the
      // primary. Allocate the per-feed buffers lazily on first sight so
      // single-feed sweeps stay on the original code path.
      if (Array.isArray(pt.feeds_z_re) && Array.isArray(pt.feeds_z_im)) {
        if (!acc.feeds_z_re) acc.feeds_z_re = [];
        if (!acc.feeds_z_im) acc.feeds_z_im = [];
        acc.feeds_z_re.push(pt.feeds_z_re);
        acc.feeds_z_im.push(pt.feeds_z_im);
      }
      if (!controller.signal.aborted) onPoint(snapshot());
    }
  }
  if (firstError !== null && acc.freqs_mhz.length === 0) throw new Error(firstError);
  return snapshot();
}

/** The freq sweep runner's phase, as the sweep charts publish it. */
export type SweepPhase = "idle" | "queued" | "running" | "refining";

export type FreqSweepOptions = {
  /** The range the sweep grids (lib/sweep.ts). */
  range: SweepRange;
  /** The sweep's physics signature (useAnalysisRunners' FREQ_SWEEP_EXEMPT
   *  over this render's request): any change is a new sweep. */
  sig: string;
  /** It runs at all: the chart shows a frequency sweep (the chart's dwell
   *  switch is `auto`). */
  enabled: boolean;
  /** Something that draws it is on screen (issue #715). */
  resident: boolean;
  /** Re-sweep by itself after the dwell (see the module comment). Read when
   *  the inputs change, not a trigger: flipping it re-runs nothing. */
  auto?: boolean;
  backend: BackendEntry;
  groundEnabled: boolean;
  groundModel: GroundModel;
  refineEnabled: boolean;
  z0: number;
  residentSweepViews: SweepProjectionSet;
  sweepAxes: SweepAxes;
  swrThreshold: number;
  autoSim: boolean;
  active: boolean;
  comboApproved: boolean;
  recommendedBackend: BackendEntry | null;
  buildRequest: () => SolveRequest;
  solveWithheld: () => boolean;
  seqRef: MutableRefObject<number>;
  approvedComboRef: MutableRefObject<boolean>;
};

/** What a frequency sweep runner publishes, and its controls. */
export type FreqSweepHandle = {
  sweep: SweepData | null;
  running: boolean;
  phase: SweepPhase;
  settled: boolean;
  progress: SweepProgress | null;
  advisories: Advisory[];
  /** Drawn for inputs that have since changed (not-auto mode only). */
  stale: boolean;
  /** Why the last sweep failed (the server's refusal), until the next one
   *  starts; null otherwise. */
  error: string | null;
  /** The same sweep again, now, with no dwell. */
  runNow: () => void;
  /** Ask for whatever inputs the next render brings (a pick): with `auto`
   *  off, that sweep runs after the dwell as if `auto` were on. */
  arm: () => void;
  /** The app's Cancel: stop the stream and any pending round; what is drawn
   *  stays drawn. */
  abort: () => void;
};

export function useFreqSweep({
  range: effectiveSweepRange,
  sig: freqSweepSig,
  enabled: sweepEnabled,
  resident: sweepResident,
  auto = true,
  backend,
  groundEnabled,
  groundModel,
  refineEnabled: refineSetting,
  z0,
  residentSweepViews,
  sweepAxes,
  swrThreshold,
  autoSim,
  active,
  comboApproved,
  recommendedBackend,
  buildRequest,
  solveWithheld,
  seqRef,
  approvedComboRef,
}: FreqSweepOptions): FreqSweepHandle {
  // An analysis's explicit frequency list is swept exactly (AK#1757 step 5
  // unit 5): no refinement adds points between its points, as `antennaknobs
  // analyze` adds none, so its curve is settled once the list lands.
  const refineEnabled = refineSetting && !effectiveSweepRange.exact;
  const sweepRangeKey = JSON.stringify(effectiveSweepRange);
  const [sweep, setSweep] = useState<SweepData | null>(null);
  const [sweepRunning, setSweepRunning] = useState(false);
  // The freq sweep's phase, published on the sweep charts (AK#1762): the base
  // sweep waiting out its dwell (`queued`), streaming (`running`), a
  // refinement pass waiting or streaming (`refining`), or none of those
  // (`idle`). A test that must show NO sweep follows a change asserts the
  // runner's decision (still idle) instead of sleeping past the dwell.
  const [sweepQueued, setSweepQueued] = useState(false);
  const [sweepRefining, setSweepRefining] = useState(false);
  // Whether the current sweep's shape is final (issue #866). False from the
  // moment a base sweep starts under refinement (its lean grid is destined
  // to be densified — a polyline through it would draw the transient kinks
  // refinement exists to remove) until a refinement pass concludes on its
  // own terms (plan empty or budget spent). Toggling refinement off mid-run
  // deliberately does NOT settle: the accumulated set is uneven, so the
  // charts keep rendering dots rather than faking a finished curve. A sweep
  // run with refinement disabled settles immediately — its uniform grid is
  // the rendering, unchanged from the pre-#744 behavior.
  const [sweepSettled, setSweepSettled] = useState(true);
  // Points received so far by the sweep in flight (AK#1682): the base grid
  // as k/N, then any refinement pass as its own count. Null when nothing is
  // streaming — including the dwell between the base sweep and refinement,
  // when no request is out and a counter would claim work that isn't.
  const [sweepProgress, setSweepProgress] = useState<SweepProgress | null>(null);
  // The base sweep's closing-record advisories (AK#1682) — today #1681's
  // FixedFrequencyNT, raised when a deck's fixed-frequency NT cards do not
  // hold across the swept range. Taken from the BASE sweep only: its record
  // names the whole range, and a refinement round only ever inserts points
  // inside it. Cleared with the sweep, so a stale note never outlives the
  // curve it was about.
  const [sweepAdvisories, setSweepAdvisories] = useState<Advisory[]>([]);
  const [sweepError, setSweepError] = useState<string | null>(null);
  const sweepTimerRef = useRef<number | null>(null);
  const sweepAbortRef = useRef<AbortController | null>(null);
  // Refinement gets its own timer/abort pair rather than sharing the base
  // sweep's: the base sweep's finally-block clears its own ref, and a
  // refinement scheduled from inside that block would immediately lose the
  // handle the next knob change has to abort through.
  const sweepRefineTimerRef = useRef<number | null>(null);
  const sweepRefineAbortRef = useRef<AbortController | null>(null);
  // Live mirrors of the refinement props, read per refinement ROUND rather
  // than captured at chain start — a mid-chain toggle-off or pin change
  // must not run a stale plan to the end of its budget.
  const refineEnabledRef = useRef(refineEnabled);
  // Mirrored every render so each refinement ROUND reads the current value;
  // capturing at chain start would let a mid-chain toggle-off run a stale plan
  // to the end of its budget (#768).
  // eslint-disable-next-line react-hooks/refs
  refineEnabledRef.current = refineEnabled;
  const residentSweepViewsRef = useRef(residentSweepViews);
  // Mirrored every render so each refinement ROUND reads the current value;
  // capturing at chain start would let a mid-chain toggle-off run a stale plan
  // to the end of its budget (#768).
  // eslint-disable-next-line react-hooks/refs
  residentSweepViewsRef.current = residentSweepViews;
  const sweepAxesRef = useRef(sweepAxes);
  // Per ROUND, as above.
  // eslint-disable-next-line react-hooks/refs
  sweepAxesRef.current = sweepAxes;
  const swrThresholdRef = useRef(swrThreshold);
  // eslint-disable-next-line react-hooks/refs
  swrThresholdRef.current = swrThreshold;
  // Not-auto mode (a chart with its dwell switch off): the inputs the sweep
  // was asked for ("armed"), and whether the next inputs are asked for (a
  // pick changes the range, so its key is not known until the next render).
  // The same bookkeeping as the knob sweep's (useParamSweep).
  const armedRef = useRef<string | null>(null);
  const armNextRef = useRef(false);
  const [sweepStale, setSweepStale] = useState(false);
  const armKey = freqSweepSig + sweepRangeKey;

  // Debounced sweep across measurement freq. Re-runs whenever the solve
  // request changes (freqSweepSig) or the freq planning inputs move.
  useEffect(() => {
    // Cancel any in-flight sweep fetch immediately. Without this the
    // previous sweep keeps streaming for hundreds of ms (PyNEC ground at
    // 100 ms/point × 41 points = ~4 s) and starves the live /ws solve of
    // CPU — the user moves a slider but the next impedance update is
    // delayed behind the now-stale sweep finishing.
    sweepAbortRef.current?.abort();
    if (sweepTimerRef.current) {
      window.clearTimeout(sweepTimerRef.current);
    }
    // Refinement points live in the same `sweep` state, so the clear below
    // drops them with everything else — signature invalidation (issue #692)
    // covers refined points for free, and must keep doing so. Killing the
    // pending round and its in-flight stream here is what stops a
    // superseded refinement from re-publishing them a moment later.
    sweepRefineAbortRef.current?.abort();
    if (sweepRefineTimerRef.current) {
      window.clearTimeout(sweepRefineTimerRef.current);
    }
    // Arming (not-auto mode): an ask arms these inputs; nothing on screen to
    // draw them disarms, so coming back does not start a sweep by itself.
    const wanted = sweepEnabled && sweepResident;
    if (armNextRef.current && wanted) armedRef.current = armKey;
    armNextRef.current = false;
    if (!wanted) armedRef.current = null;
    if (!auto && armedRef.current !== armKey) {
      // Inputs nobody asked to sweep: run nothing. What is drawn stays,
      // dimmed as stale, until Run (a knob sweep's rule, AK#1757).
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSweepStale(true);
      setSweepRunning(false);
      setSweepQueued(false);
      setSweepRefining(false);
      setSweepProgress(null);
      return;
    }
    // Cancel-then-blank is the contract (#692/#715): the overlay must go blank
    // the instant its inputs change, or a stale curve reads as current while
    // the new one dwells. Synchronous blanking is what makes 'stale'
    // unrepresentable.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSweep(null);
    setSweepStale(false);
    setSweepRunning(false);
    setSweepQueued(false);
    setSweepRefining(false);
    setSweepProgress(null);
    setSweepAdvisories([]);
    setSweepError(null);
    // Paused (Live off) holds the engine (issue #612): an enabled sweep must
    // not keep solving while the user edits. Clearing above + returning here
    // blanks the overlay while paused; resuming Live re-runs this effect
    // (autoSim is a dep) and restarts the sweep from the current design.
    if (!autoSim || !sweepEnabled || !sweepResident || !active) {
      return;
    }
    // The 500 ms dwell only debounces network churn; ordering against the
    // live solve is the server lane's job now (live outranks sweeps).
    // `runSweep` is an async function DECLARATION, so the binding is live
    // before this effect runs; the compiler cannot see hoisting (#768).
    // eslint-disable-next-line react-hooks/immutability
    sweepTimerRef.current = window.setTimeout(runSweep, 500);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSweepQueued(true);
    return () => {
      if (sweepTimerRef.current) window.clearTimeout(sweepTimerRef.current);
      if (sweepRefineTimerRef.current) {
        window.clearTimeout(sweepRefineTimerRef.current);
      }
    };
    // runSweep is read but not listed: it's a plain, unmemoized closure
    // recreated every render, and freqSweepSig is the deliberate stand-in
    // signature for everything it would otherwise pull in (same idiom as
    // currentValuesKey) — listing it would re-fire this effect on every
    // render regardless of whether anything it reads actually changed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    // Everything physics — knobs, the design freq, ground, backend, variant,
    // the measurement plane (#652 c / #691) — arrives through the signature.
    // Not the measurement frequency: see FREQ_SWEEP_EXEMPT.
    freqSweepSig,
    // measLocked is no longer listed: it steers the range's anchor policy
    // (lib/sweep.ts), and the range it steers IS sweepRangeKey, so a lock
    // toggle that moves the band re-sweeps and one that does not (the band
    // already at the design frequency) no longer blanks the curve for
    // nothing — which the real app showed on invvee.
    // Not a request field: the range itself (AK#1682) — a menu edit,
    // "↺ design range" or a band pick re-plans the grid.
    sweepRangeKey,
    sweepEnabled,
    // Residency (issue #715): no smith/gamma/vswr view on screen means
    // nobody can see the sweep — clear it and free the server lane.
    sweepResident,
    autoSim,
    active,
    // The poor-match gate: while it withholds, runSweep declines to issue the
    // batch; approving ("Solve anyway") or a new recommendation re-fires this
    // effect (issue #382 — replaces the old 200 ms re-poll loop).
    comboApproved, recommendedBackend,
  ]);

  // A sweep chart pinned AFTER the sweep settled (or refinement switched
  // back on) still deserves its refinement pass — the base flow's trigger
  // (the tail of runSweep) has already come and gone. This effect fills
  // that gap: on a growth of the resident-projection set, re-enter the
  // refinement dwell against the CURRENT accumulated sweep. No base
  // re-sweep (the data is fine, only the polish is missing), and already-
  // refined projections converge immediately (their plan comes back empty
  // or tiny, and the server's per-freq cache answers any overlap), so the
  // marginal cost is the new projection's points alone.
  const residentSweepKey = `${residentSweepViews.vswr},${residentSweepViews.gamma},${residentSweepViews.smith}`;
  const sweepRef = useRef<SweepData | null>(null);
  // Mirrored every render so each refinement ROUND reads the current value;
  // capturing at chain start would let a mid-chain toggle-off run a stale plan
  // to the end of its budget (#768).
  // eslint-disable-next-line react-hooks/refs
  sweepRef.current = sweep;
  useEffect(() => {
    if (!refineEnabled || !sweepRef.current || sweepRunning) {
      // A pending round this effect's last run set (and its cleanup
      // cleared) is gone; an in-flight one reports for itself.
      if (!sweepRefineAbortRef.current) setSweepRefining(false);
      return;
    }
    if (sweepRefineTimerRef.current) {
      window.clearTimeout(sweepRefineTimerRef.current);
    }
    setSweepRefining(true);
    const settled = sweepRef.current;
    sweepRefineTimerRef.current = window.setTimeout(
      // `runSweepRefine` is an async function DECLARATION, so the binding is
      // live before this effect runs; the compiler cannot see hoisting (#768).
      // eslint-disable-next-line react-hooks/immutability
      () => runSweepRefine(settled),
      SWEEP_REFINE_DWELL_MS,
    );
    return () => {
      if (sweepRefineTimerRef.current) {
        window.clearTimeout(sweepRefineTimerRef.current);
      }
    };
    // sweep/sweepRunning are read via ref/guard, deliberately not deps: a
    // COMPLETING sweep must not re-fire this effect (the runSweep tail owns
    // that trigger); only the projection set growing or the toggle flipping
    // on re-arms it. runSweepRefine: same unmemoized-closure idiom as
    // runSweep above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [residentSweepKey, refineEnabled]);

  async function runSweep() {
    // No competition with the live solve to time around anymore: the server's
    // per-session solve lane (issue #382) runs everything one-at-a-time with
    // the live solve first, so this just sends. While the poor-match gate is
    // withholding, don't issue batches of the very solves it's blocking — the
    // effect re-fires on approval (comboApproved is a dependency).
    setSweepQueued(false);
    if (solveWithheld()) return;
    sweepTimerRef.current = null;
    sweepAbortRef.current?.abort();
    const controller = new AbortController();
    sweepAbortRef.current = controller;

    // The range's grid — see lib/sweep.ts for the precedence, anchor and
    // band-lock policy. A range with its own density is solved exactly
    // (refinement adds points between its points); one without gets the
    // lean base grid when refinement will polish it, the historical dense
    // grid when the toggle says the base IS the rendering.
    const freqs = sweepGrid(
      effectiveSweepRange,
      defaultSweepPoints({ backend, groundEnabled, groundModel, refineEnabled }),
    ).freqs;

    const base = buildRequest();
    const body = {
      ...base,
      freqs_mhz: freqs,
      // Opt-in cache read-through (issue #763): a knob scrub back to an
      // already-swept state may reuse the per-freq Z this session itself
      // wrote. User designs are excluded — their file can change on disk
      // under an unchanged request key (the server enforces both gates
      // again regardless).
      reuse_cached_z:
        !String(base.geometry ?? "").startsWith("user.") &&
        !String(base.geometry ?? "").startsWith("@"),
      // Lane metadata (issue #382): issued-at generation (a newer knob drag
      // supersedes this batch server-side) + the gate's approval, which the
      // server requires for a warned batch (poor-match combo backstop).
      _gen: seqRef.current,
      _approved: approvedComboRef.current,
    };
    setSweepRunning(true);
    // Settledness for this sweep (issue #866): with refinement on, the lean
    // base grid is provisional until the refine pass lands; with it off, the
    // dense grid IS the final shape.
    setSweepSettled(!refineEnabledRef.current);
    setSweepProgress({ phase: "base", received: 0, planned: freqs.length });
    let planned: SweepData | null = null;
    try {
      // New object per point so React re-renders the Smith chart as the
      // sweep fills in. The counter reads the snapshot's own length, so it
      // is the number of points that actually landed (AK#1682).
      planned = await streamSweep(body, controller, (snapshot) => {
        setSweep(snapshot);
        setSweepProgress({
          phase: "base",
          received: snapshot.freqs_mhz.length,
          planned: freqs.length,
        });
      }, (closing) => setSweepAdvisories(closing.advisories ?? []));
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("sweep error", e);
      if (!controller.signal.aborted) setSweepError(e instanceof Error ? e.message : String(e));
    } finally {
      if (sweepAbortRef.current === controller) {
        sweepAbortRef.current = null;
        setSweepRunning(false);
        setSweepProgress(null);
        // Adaptive refinement (issue #744) rides the tail of the base
        // sweep rather than its own effect: reaching here IS the dwell
        // signal — the design settled long enough for a whole sweep to
        // stream without a knob aborting it. `planned` is null exactly
        // when the stream threw (abort, transport failure), which is the
        // case that must not refine; a stream that ended on a per-chunk
        // {error} line still leaves a real curve worth polishing.
        //
        // sweepRunning stays false throughout: refinement adds points to a
        // curve that is already drawn, and flickering the chart's busy
        // indicator back on would read as "this result is provisional".
        const settled = planned;
        if (settled && !controller.signal.aborted && refineEnabledRef.current) {
          sweepRefineTimerRef.current = window.setTimeout(
            () => runSweepRefine(settled),
            SWEEP_REFINE_DWELL_MS,
          );
          setSweepRefining(true);
        }
      }
    }
  }

  // Densify the settled sweep where the rendered curve corners (issue
  // #744). Iterative: each round asks the pure planner for the worst
  // intervals, streams those freqs, merges them in, and re-plans against
  // the densified curve — the planner cannot evaluate its own insertions,
  // so re-evaluation only exists across rounds.
  //
  // Every round is optional. Running out of budget, an abort, or a plan
  // that comes back empty all just stop, leaving the best-so-far merge on
  // screen; nothing here is load-bearing for correctness of the curve.
  async function runSweepRefine(base: SweepData) {
    sweepRefineTimerRef.current = null;
    if (!refineEnabledRef.current || solveWithheld()) {
      setSweepRefining(false);
      return;
    }
    sweepRefineAbortRef.current?.abort();
    const controller = new AbortController();
    sweepRefineAbortRef.current = controller;
    let acc = base;
    let spent = 0;
    let refined = 0; // points RECEIVED across rounds, for the counter
    // Unsettle here too, not just in runSweep (issue #866): a pass triggered
    // by a chart becoming resident refines a sweep whose base flow settled
    // long ago (or ran refine-disabled), and its insertions are about to
    // reshape the curve.
    setSweepSettled(false);
    // Set exactly when the pass concludes on its own terms — the budget runs
    // out or the planner finds nothing left to fix. A mid-run toggle-off
    // (the break below) leaves it false: the accumulated set is uneven and
    // the charts should keep saying so (dots, not a polyline).
    let concluded = false;
    try {
      while (spent < SWEEP_REFINE_BUDGET && !controller.signal.aborted) {
        // The toggle and the resident-projection set are read per ROUND:
        // switching refinement off (or unpinning the last chart that wanted
        // a projection) takes effect at the next round boundary instead of
        // finishing the whole budget.
        if (!refineEnabledRef.current) break;
        const want = refineSweepFreqs(
          acc,
          z0,
          Math.min(SWEEP_REFINE_ROUND_BUDGET, SWEEP_REFINE_BUDGET - spent),
          residentSweepViewsRef.current,
          sweepAxesRef.current,
          swrThresholdRef.current,
        );
        if (want.length === 0) {
          concluded = true; // no visible kink left to remove
          break;
        }
        spent += want.length;
        const settled = acc; // merge target for this round's snapshots
        // Cumulative across rounds, counted per point received (AK#1682).
        const before = refined;
        setSweepProgress({
          phase: "refine",
          received: before,
          budget: SWEEP_REFINE_BUDGET,
        });
        const extra = await streamSweep(
          {
            ...buildRequest(),
            freqs_mhz: want,
            // Lane metadata (issue #382) + the refinement marker the server
            // reads for its lane kind (issue #744). `_refine` is pure
            // scheduling — it is on the server's cache-key blocklist, so a
            // refinement request hits the same per-freq entries a base
            // sweep would.
            _gen: seqRef.current,
            _approved: approvedComboRef.current,
            _refine: true,
          },
          controller,
          (snapshot) => {
            setSweep(mergeSweepPoints(settled, snapshot));
            setSweepProgress({
              phase: "refine",
              received: before + snapshot.freqs_mhz.length,
              budget: SWEEP_REFINE_BUDGET,
            });
          },
        );
        refined = before + extra.freqs_mhz.length;
        acc = mergeSweepPoints(acc, extra);
        if (controller.signal.aborted) return;
        setSweep(acc);
      }
      // Exiting because the budget ran dry is as final as an empty plan —
      // best-so-far is the shape we will render from here on. An abort
      // (superseded by a new sweep) is not: that sweep resets settledness
      // itself.
      if (spent >= SWEEP_REFINE_BUDGET && !controller.signal.aborted) {
        concluded = true;
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("sweep refine error", e);
    } finally {
      if (concluded) setSweepSettled(true);
      if (sweepRefineAbortRef.current === controller) {
        sweepRefineAbortRef.current = null;
        setSweepProgress(null);
        // Done, unless a new round is already waiting (a resident chart's
        // re-entry set a timer while this one streamed).
        if (!sweepRefineTimerRef.current) setSweepRefining(false);
      }
    }
  }

  // Run: this sweep again, now (no dwell), whatever the switch says. Behind
  // the poor-match gate like any other (runSweep checks it).
  function runNow() {
    armedRef.current = armKey;
    sweepAbortRef.current?.abort();
    sweepRefineAbortRef.current?.abort();
    for (const t of [sweepTimerRef, sweepRefineTimerRef]) {
      if (t.current) window.clearTimeout(t.current);
      t.current = null;
    }
    setSweep(null);
    setSweepStale(false);
    setSweepQueued(false);
    setSweepRefining(false);
    setSweepProgress(null);
    setSweepAdvisories([]);
    setSweepError(null);
    void runSweep();
  }

  function arm() {
    armNextRef.current = true;
  }

  function abort() {
    setSweepQueued(false);
    setSweepRefining(false);
    for (const t of [sweepTimerRef, sweepRefineTimerRef]) {
      if (t.current) window.clearTimeout(t.current);
      t.current = null;
    }
    sweepAbortRef.current?.abort();
    sweepRefineAbortRef.current?.abort();
  }

  const phase: SweepPhase = sweepRunning
    ? "running"
    : sweepQueued
      ? "queued"
      : sweepRefining
        ? "refining"
        : "idle";

  return {
    sweep,
    running: sweepRunning,
    phase,
    settled: sweepSettled,
    progress: sweepProgress,
    advisories: sweepAdvisories,
    stale: sweepStale && sweep !== null,
    error: sweepError,
    runNow,
    arm,
    abort,
  };
}
