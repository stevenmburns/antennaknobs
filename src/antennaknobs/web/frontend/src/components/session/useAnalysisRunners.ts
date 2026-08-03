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
import { planSweepFreqs } from "../../lib/sweep";
import type { PatternData } from "../charts/types";

// Log-spaced segments-per-wire ladder for the convergence sweep. Hentenna's
// 8N+2 total segments at N=68 puts the dense LU at a ~550-cell matrix —
// still snappy at this N range on all backends, but enough span to see
// O(1/N) trajectories clearly. Same ladder across backends so the curves
// are directly comparable when the user switches slots.
export const CONVERGE_N_VALUES: number[] = [8, 12, 17, 24, 34, 48, 68];

// The four background analyses that shadow the live solve — the freq sweep,
// the segments-per-wire convergence sweep, the far-field norm check and the
// NEC rp_card pattern — with their debounce effects, timer/abort refs and
// streaming runners (#642 seam 5b-3). The cluster moves whole, so the four
// literal dep arrays and the runners' fresh-per-render closures are unchanged.
//
// Every dep-array member arrives as a plain per-render value, and buildRequest
// / solveWithheld as plain per-render functions: memoizing either would change
// which closure a pending debounce timeout fires.
export function useAnalysisRunners({
  geometry,
  backend,
  backendOptsKey,
  currentValuesKey,
  currentVariant,
  currentExample,
  currentBands,
  freqWindowCeiling,
  designFreq,
  measFreq,
  measLocked,
  groundEnabled,
  groundModel,
  terrainKey,
  sweepEnabled,
  convergeEnabled,
  normCheckEnabled,
  necOverlayEnabled,
  autoSim,
  active,
  comboApproved,
  recommendedBackend,
  buildRequest,
  solveWithheld,
  seqRef,
  approvedComboRef,
}: {
  geometry: string;
  backend: BackendEntry;
  backendOptsKey: string;
  currentValuesKey: string;
  currentVariant: string;
  currentExample: ExampleDescriptor | undefined;
  currentBands: BandSpec[];
  freqWindowCeiling: number;
  designFreq: number;
  measFreq: number;
  measLocked: boolean;
  groundEnabled: boolean;
  groundModel: GroundModel;
  terrainKey: string;
  sweepEnabled: boolean;
  convergeEnabled: boolean;
  normCheckEnabled: boolean;
  necOverlayEnabled: boolean;
  autoSim: boolean;
  active: boolean;
  comboApproved: boolean;
  recommendedBackend: BackendEntry | null;
  buildRequest: () => SolveRequest;
  solveWithheld: () => boolean;
  seqRef: MutableRefObject<number>;
  approvedComboRef: MutableRefObject<boolean>;
}) {
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
  const patternTimerRef = useRef<number | null>(null);
  const patternAbortRef = useRef<AbortController | null>(null);
  const convergeTimerRef = useRef<number | null>(null);
  const convergeAbortRef = useRef<AbortController | null>(null);
  const normCheckTimerRef = useRef<number | null>(null);
  const normCheckAbortRef = useRef<AbortController | null>(null);

  // Debounced sweep across measurement freq. Re-runs whenever any antenna
  // parameter changes. Single-band geometries sweep around designFreq, so
  // moving the measFreq slider doesn't re-sweep (the existing data already
  // covers the new slider position). Fan dipole sweeps around measFreq,
  // so measFreq is part of the deps there to re-anchor.
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
    setSweep(null);
    setSweepRunning(false);
    // Paused (Live off) holds the engine (issue #612): an enabled sweep must
    // not keep solving while the user edits. Clearing above + returning here
    // blanks the overlay while paused; resuming Live re-runs this effect
    // (autoSim is a dep) and restarts the sweep from the current design.
    if (!autoSim || !sweepEnabled || !active) {
      return;
    }
    // The 500 ms dwell only debounces network churn; ordering against the
    // live solve is the server lane's job now (live outranks sweeps).
    sweepTimerRef.current = window.setTimeout(runSweep, 500);
    return () => {
      if (sweepTimerRef.current) window.clearTimeout(sweepTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    geometry, backend.name, backendOptsKey,
    currentValuesKey,
    designFreq,
    groundEnabled, groundModel,
    sweepEnabled,
    autoSim,
    active,
    // measFreq/measLocked drive the anchor now (meas_freq policy, or any
    // unlocked design — incl. fixed-geometry designs whose lock is inert),
    // so a meas-band change or dial turn re-runs the sweep.
    measFreq, measLocked,
    // A variant can override sweep_policy (variant_ui) without changing any
    // param — e.g. a band-locked variant. currentValuesKey wouldn't move then,
    // so depend on currentVariant directly to re-run the sweep on switch.
    currentVariant,
    // The poor-match gate: while it withholds, runSweep declines to issue the
    // batch; approving ("Solve anyway") or a new recommendation re-fires this
    // effect (issue #382 — replaces the old 200 ms re-poll loop).
    comboApproved, recommendedBackend,
  ]);

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
    if (!autoSim || !convergeEnabled || !active) {
      return;
    }
    // Debounce only; the server lane orders it behind the live solve.
    convergeTimerRef.current = window.setTimeout(runConverge, 500);
    return () => {
      if (convergeTimerRef.current) window.clearTimeout(convergeTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    geometry, backend.name, backendOptsKey,
    currentValuesKey,
    designFreq, measFreq,
    groundEnabled, groundModel,
    convergeEnabled,
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    geometry, backend.name, backendOptsKey,
    currentValuesKey,
    designFreq, measFreq,
    groundEnabled, groundModel,
    // The pattern integral runs over the facets, so terrain knob changes
    // invalidate it (unlike the impedance-only sweep/converge effects,
    // which are legitimately terrain-param-independent — every preset
    // shares the crest medium the impedance solve uses).
    terrainKey,
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    geometry, backend.name, backendOptsKey,
    currentValuesKey,
    designFreq, measFreq,
    groundEnabled, groundModel,
    necOverlayEnabled,
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
    const acc: SweepData = {
      freqs_mhz: [],
      z_re: [],
      z_im: [],
      feeds_z_re: undefined,
      feeds_z_im: undefined,
    };
    try {
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
          // Multi-feed sweep records (bowtie) ship per-feed Z alongside
          // the primary. Allocate the per-feed buffers lazily on first
          // sight so single-feed sweeps stay on the original code path.
          if (Array.isArray(pt.feeds_z_re) && Array.isArray(pt.feeds_z_im)) {
            if (!acc.feeds_z_re) acc.feeds_z_re = [];
            if (!acc.feeds_z_im) acc.feeds_z_im = [];
            acc.feeds_z_re.push(pt.feeds_z_re);
            acc.feeds_z_im.push(pt.feeds_z_im);
          }
          if (!controller.signal.aborted) {
            // New object so React re-renders the Smith chart per point.
            setSweep({
              freqs_mhz: acc.freqs_mhz.slice(),
              z_re: acc.z_re.slice(),
              z_im: acc.z_im.slice(),
              feeds_z_re: acc.feeds_z_re
                ? acc.feeds_z_re.map((row) => row.slice())
                : undefined,
              feeds_z_im: acc.feeds_z_im
                ? acc.feeds_z_im.map((row) => row.slice())
                : undefined,
            });
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("sweep error", e);
    } finally {
      if (sweepAbortRef.current === controller) {
        sweepAbortRef.current = null;
        setSweepRunning(false);
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
    const acc: ConvergeData = {
      n_values: [],
      z_re: [],
      z_im: [],
      z_re_extrap: null,
      z_im_extrap: null,
      feeds_z_re: undefined,
      feeds_z_im: undefined,
      feeds_z_re_extrap: undefined,
      feeds_z_im_extrap: undefined,
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
              feeds_z_re: acc.feeds_z_re
                ? acc.feeds_z_re.map((row) => row.slice())
                : undefined,
              feeds_z_im: acc.feeds_z_im
                ? acc.feeds_z_im.map((row) => row.slice())
                : undefined,
              feeds_z_re_extrap: acc.feeds_z_re_extrap
                ? acc.feeds_z_re_extrap.slice()
                : undefined,
              feeds_z_im_extrap: acc.feeds_z_im_extrap
                ? acc.feeds_z_im_extrap.slice()
                : undefined,
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
