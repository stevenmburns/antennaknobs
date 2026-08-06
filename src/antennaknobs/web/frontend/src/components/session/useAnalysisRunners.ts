import {
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import type {
  ConvergeData,
  NormCheckData,
  SolveRequest,
  SweepData,
} from "../../lib/api";
import { type BackendEntry } from "../../lib/backends";
import { type GroundModel } from "../../lib/ground";
import { feedwiseRichardson, richardsonExtrap } from "../../lib/math";
import { type BandSpec, type ExampleDescriptor } from "../../lib/params";
import {
  ALL_SWEEP_PROJECTIONS,
  refineSweepFreqs,
  type SweepProjectionSet,
} from "../../lib/refine";
import { solveSignature } from "../../lib/solveSignature";
import {
  mergeSweepPoints,
  planSweepFreqs,
  SWEEP_REFINE_BUDGET,
  SWEEP_REFINE_ROUND_BUDGET,
} from "../../lib/sweep";
import type { PatternData } from "../charts/types";

// Log-spaced segments-per-wire ladder for the convergence sweep. Hentenna's
// 8N+2 total segments at N=68 puts the dense LU at a ~550-cell matrix —
// still snappy at this N range on all backends, but enough span to see
// O(1/N) trajectories clearly. Same ladder across backends so the curves
// are directly comparable when the user switches slots.
export const CONVERGE_N_VALUES: number[] = [8, 12, 17, 24, 34, 48, 68];

// Deliberate physics non-deps (issue #692), mirroring the server's
// _CACHE_KEY_BLOCKLIST (web/server.py) — the same idea at the other end of
// the wire. Cut angles are attached per-request AFTER the solve (POST /cuts,
// issue #547), so dragging a cut dial changes no analysis result: every
// analysis exempts them, exactly as the server cache does.
const CUT_ANGLE_EXEMPT = ["az_elev_deg", "elev_az_deg"] as const;

// The freq sweep and convergence sweep are impedance-only, and every terrain
// preset shares the crest medium the impedance solve uses — so the terrain
// knobs are additionally exempt for those two. NOT for the norm check, whose
// pattern integral runs over the facets.
const IMPEDANCE_ANALYSIS_EXEMPT = [...CUT_ANGLE_EXEMPT, "terrain"] as const;

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
 *  that. */
async function streamSweep(
  body: object,
  controller: AbortController,
  onPoint: (snapshot: SweepData) => void,
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
  if (!resp.ok || !resp.body) throw new Error(`sweep failed: ${resp.status}`);
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
      if (pt.done) continue;
      // A failed point/chunk ends the stream with {error} instead of
      // tearing the connection down (e.g. an approved poor-match combo
      // whose dense fill can't allocate). Keep whatever points landed.
      if (pt.error) {
        console.error("sweep error", pt.error);
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
  return snapshot();
}

// The four background analyses that shadow the live solve — the freq sweep,
// the segments-per-wire convergence sweep, the far-field norm check and the
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
  groundEnabled,
  groundModel,
  sweepEnabled,
  convergeEnabled,
  normCheckEnabled,
  necOverlayEnabled,
  sweepResident,
  convergeResident,
  patternResident,
  autoSim,
  active,
  comboApproved,
  recommendedBackend,
  z0 = 50,
  refineEnabled = true,
  residentSweepViews = ALL_SWEEP_PROJECTIONS,
  buildRequest,
  solveWithheld,
  seqRef,
  approvedComboRef,
}: {
  backend: BackendEntry;
  currentVariant: string;
  currentExample: ExampleDescriptor | undefined;
  currentBands: BandSpec[];
  freqWindowCeiling: number;
  designFreq: number;
  measFreq: number;
  measLocked: boolean;
  groundEnabled: boolean;
  groundModel: GroundModel;
  sweepEnabled: boolean;
  convergeEnabled: boolean;
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
  convergeResident: boolean;
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
  buildRequest: () => SolveRequest;
  solveWithheld: () => boolean;
  seqRef: MutableRefObject<number>;
  approvedComboRef: MutableRefObject<boolean>;
}) {
  // The physics dependency of each effect below (issue #692): a fresh
  // buildRequest() per render, hashed down to a stable string. Anything that
  // changes the request — a knob, the variant, the measurement plane, a
  // NEW field someone adds next month — invalidates by default; the
  // exemption lists at the top of this module are the only opt-outs.
  const req = buildRequest();
  const impedanceSig = solveSignature(req, { exempt: IMPEDANCE_ANALYSIS_EXEMPT });
  const solveSig = solveSignature(req, { exempt: CUT_ANGLE_EXEMPT });

  const [sweep, setSweep] = useState<SweepData | null>(null);
  const [sweepRunning, setSweepRunning] = useState(false);
  const [converge, setConverge] = useState<ConvergeData | null>(null);
  const [convergeRunning, setConvergeRunning] = useState(false);
  const [normCheck, setNormCheck] = useState<NormCheckData | null>(null);
  // NEC's rp_card pattern, fetched on a debounce so we don't fire one per
  // slider tick. Overlaid on the cuts as a comparison line.
  const [pattern, setPattern] = useState<PatternData | null>(null);

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
  refineEnabledRef.current = refineEnabled;
  const residentSweepViewsRef = useRef(residentSweepViews);
  residentSweepViewsRef.current = residentSweepViews;
  const patternTimerRef = useRef<number | null>(null);
  const patternAbortRef = useRef<AbortController | null>(null);
  const convergeTimerRef = useRef<number | null>(null);
  const convergeAbortRef = useRef<AbortController | null>(null);
  const normCheckTimerRef = useRef<number | null>(null);
  const normCheckAbortRef = useRef<AbortController | null>(null);

  // Debounced sweep across measurement freq. Re-runs whenever the solve
  // request changes (impedanceSig) or the freq planning inputs move.
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
    setSweep(null);
    setSweepRunning(false);
    // Paused (Live off) holds the engine (issue #612): an enabled sweep must
    // not keep solving while the user edits. Clearing above + returning here
    // blanks the overlay while paused; resuming Live re-runs this effect
    // (autoSim is a dep) and restarts the sweep from the current design.
    if (!autoSim || !sweepEnabled || !sweepResident || !active) {
      return;
    }
    // The 500 ms dwell only debounces network churn; ordering against the
    // live solve is the server lane's job now (live outranks sweeps).
    sweepTimerRef.current = window.setTimeout(runSweep, 500);
    return () => {
      if (sweepTimerRef.current) window.clearTimeout(sweepTimerRef.current);
      if (sweepRefineTimerRef.current) {
        window.clearTimeout(sweepRefineTimerRef.current);
      }
    };
    // runSweep is read but not listed: it's a plain, unmemoized closure
    // recreated every render, and impedanceSig is the deliberate stand-in
    // signature for everything it would otherwise pull in (same idiom as
    // currentValuesKey) — listing it would re-fire this effect on every
    // render regardless of whether anything it reads actually changed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    // Everything physics — knobs, freqs, ground, backend, variant, the
    // measurement plane (#652 c / #691) — arrives through the signature.
    impedanceSig,
    // Not a request field: measLocked steers planSweepFreqs' anchor policy
    // (band-locked sweeps stay put; unlocked re-anchor on measFreq), so a
    // lock toggle must re-plan the freqs even though the solve is unchanged.
    measLocked,
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
  sweepRef.current = sweep;
  useEffect(() => {
    if (!refineEnabled || !sweepRef.current || sweepRunning) return;
    if (sweepRefineTimerRef.current) {
      window.clearTimeout(sweepRefineTimerRef.current);
    }
    const settled = sweepRef.current;
    sweepRefineTimerRef.current = window.setTimeout(
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

  // Debounced convergence sweep over segments-per-wire. Independent of the
  // freq sweep above: re-runs on any antenna/backend change, gated by its
  // own overlay checkbox. The active slot's `nPerWire` is *overridden* by
  // the ladder values for the duration of the sweep — the per-slot opts
  // stay untouched, so the live /ws solve keeps using the user's setting.
  useEffect(() => {
    convergeAbortRef.current?.abort();
    if (convergeTimerRef.current) {
      window.clearTimeout(convergeTimerRef.current);
    }
    setConverge(null);
    setConvergeRunning(false);
    // Held when Paused (issue #612) — see the sweep effect. autoSim is a dep so
    // resuming Live restarts the convergence sweep.
    if (!autoSim || !convergeEnabled || !convergeResident || !active) {
      return;
    }
    // Debounce only; the server lane orders it behind the live solve.
    convergeTimerRef.current = window.setTimeout(runConverge, 500);
    return () => {
      if (convergeTimerRef.current) window.clearTimeout(convergeTimerRef.current);
    };
    // runConverge omitted — same reasoning as the sweep effect above: a
    // plain unmemoized closure, with impedanceSig standing in for its actual
    // inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    impedanceSig,
    convergeEnabled,
    convergeResident, // issue #715: the smith view is the only consumer
    autoSim,
    active,
    // Poor-match gate (see the sweep effect).
    comboApproved, recommendedBackend,
  ]);

  // Debounced far-field norm consistency check. Same shape as the converge
  // sweep: re-runs on any antenna/param change (which invalidates the norm),
  // gated by its own overlay checkbox. The server lane runs it after the
  // live solve (priority ordering), so it lands on that solve's cached
  // currents rather than forcing a re-solve.
  useEffect(() => {
    normCheckAbortRef.current?.abort();
    if (normCheckTimerRef.current) {
      window.clearTimeout(normCheckTimerRef.current);
    }
    setNormCheck(null);
    // Held when Paused (issue #612): the norm check re-solves, so it must not
    // run while the engine is held. autoSim is a dep — resuming Live re-runs it.
    if (!autoSim || !normCheckEnabled || !active) {
      return;
    }
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
    // impedance-only sweep/converge effects above).
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
    setPattern(null);
    if (
      !autoSim || // Paused holds the engine (issue #612) — no NEC re-solve.
      backend.name !== "pynec" ||
      !active ||
      !necOverlayEnabled ||
      !patternResident || // issue #715: gated on the azimuth/elevation cuts
      groundModel === "terrain"
    ) {
      return;
    }
    patternTimerRef.current = window.setTimeout(() => {
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

  async function runSweep() {
    // No competition with the live solve to time around anymore: the server's
    // per-session solve lane (issue #382) runs everything one-at-a-time with
    // the live solve first, so this just sends. While the poor-match gate is
    // withholding, don't issue batches of the very solves it's blocking — the
    // effect re-fires on approval (comboApproved is a dependency).
    if (solveWithheld()) return;
    sweepTimerRef.current = null;
    sweepAbortRef.current?.abort();
    const controller = new AbortController();
    sweepAbortRef.current = controller;

    // Sweep range, log-spaced — see planSweepFreqs for the resolution,
    // anchor, and band-lock policy this applies.
    const freqs = planSweepFreqs({
      backend,
      groundEnabled,
      groundModel,
      currentExample,
      currentVariant,
      measLocked,
      measFreq,
      designFreq,
      currentBands,
      freqWindowCeiling,
      // Lean base grid when refinement will polish it; the historical
      // dense grid when the toggle says the base IS the rendering.
      refineEnabled,
    });

    const body = {
      ...buildRequest(),
      freqs_mhz: freqs,
      // Lane metadata (issue #382): issued-at generation (a newer knob drag
      // supersedes this batch server-side) + the gate's approval, which the
      // server requires for a warned batch (poor-match combo backstop).
      _gen: seqRef.current,
      _approved: approvedComboRef.current,
    };
    setSweepRunning(true);
    let planned: SweepData | null = null;
    try {
      // New object per point so React re-renders the Smith chart as the
      // sweep fills in.
      planned = await streamSweep(body, controller, setSweep);
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("sweep error", e);
    } finally {
      if (sweepAbortRef.current === controller) {
        sweepAbortRef.current = null;
        setSweepRunning(false);
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
    if (!refineEnabledRef.current) return;
    if (solveWithheld()) return;
    sweepRefineAbortRef.current?.abort();
    const controller = new AbortController();
    sweepRefineAbortRef.current = controller;
    let acc = base;
    let spent = 0;
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
        );
        if (want.length === 0) break; // no visible kink left to remove
        spent += want.length;
        const settled = acc; // merge target for this round's snapshots
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
          (snapshot) => setSweep(mergeSweepPoints(settled, snapshot)),
        );
        acc = mergeSweepPoints(acc, extra);
        if (controller.signal.aborted) return;
        setSweep(acc);
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("sweep refine error", e);
    } finally {
      if (sweepRefineAbortRef.current === controller) {
        sweepRefineAbortRef.current = null;
      }
    }
  }

  async function runConverge() {
    // Same as runSweep: the server lane serializes and prioritizes; only the
    // poor-match gate holds this back (effect re-fires on approval).
    if (solveWithheld()) return;
    convergeTimerRef.current = null;
    convergeAbortRef.current?.abort();
    const controller = new AbortController();
    convergeAbortRef.current = controller;

    // The active slot's nPerWire is irrelevant during a converge sweep —
    // n_values overrides it on the server. We strip `n_per_wire` from the
    // request anyway to make that explicit.
    const body = {
      ...buildRequest(),
      n_values: CONVERGE_N_VALUES,
      _gen: seqRef.current,
      _approved: approvedComboRef.current,
    };
    setConvergeRunning(true);
    // feeds_* fields start OMITTED, same reasoning as runSweep's acc above.
    const acc: ConvergeData = {
      n_values: [],
      z_re: [],
      z_im: [],
      z_re_extrap: null,
      z_im_extrap: null,
    };
    try {
      const resp = await fetch("/converge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) throw new Error(`converge failed: ${resp.status}`);
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
          if (pt.done) continue;
          // A solver failure for one N (rare — degenerate small-N geometry)
          // is reported by the backend as {n_per_wire, error}; skip rather
          // than poisoning the trajectory.
          if (pt.error) continue;
          acc.n_values.push(pt.n_per_wire);
          acc.z_re.push(pt.z_re);
          acc.z_im.push(pt.z_im);
          // Multi-feed convergence records ship per-feed Z alongside the
          // primary; allocate the buffers lazily on first sight.
          if (Array.isArray(pt.feeds_z_re) && Array.isArray(pt.feeds_z_im)) {
            if (!acc.feeds_z_re) acc.feeds_z_re = [];
            if (!acc.feeds_z_im) acc.feeds_z_im = [];
            acc.feeds_z_re.push(pt.feeds_z_re);
            acc.feeds_z_im.push(pt.feeds_z_im);
          }
          const invN = acc.n_values.map((n) => 1 / n);
          acc.z_re_extrap = richardsonExtrap(invN, acc.z_re);
          acc.z_im_extrap = richardsonExtrap(invN, acc.z_im);
          // Per-feed Richardson Z* — see feedwiseRichardson.
          if (acc.feeds_z_re && acc.feeds_z_im) {
            const { feedsRe, feedsIm } = feedwiseRichardson(
              invN,
              acc.feeds_z_re,
              acc.feeds_z_im,
            );
            acc.feeds_z_re_extrap = feedsRe;
            acc.feeds_z_im_extrap = feedsIm;
          }
          if (!controller.signal.aborted) {
            setConverge({
              n_values: acc.n_values.slice(),
              z_re: acc.z_re.slice(),
              z_im: acc.z_im.slice(),
              z_re_extrap: acc.z_re_extrap,
              z_im_extrap: acc.z_im_extrap,
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
            });
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("converge error", e);
    } finally {
      if (convergeAbortRef.current === controller) {
        convergeAbortRef.current = null;
        setConvergeRunning(false);
      }
    }
  }

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

  return {
    sweep,
    sweepRunning,
    converge,
    convergeRunning,
    normCheck,
    pattern,
  };
}
