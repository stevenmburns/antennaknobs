import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type SetStateAction,
} from "react";
import type { SolveRequest } from "../../lib/api";

import {
  defaultKnobOpt,
  knobPath,
  setValueAtPath,
  type KnobOpt,
  type ParamValueBag,
  type SchemaItem,
} from "../../lib/params";
import {
  type OptimizeResult,
  type OptObjective,
  type OptPause,
  type OptProgress,
  type OptStopped,
} from "./VfoPanel";
import { apiFetch } from "../../lib/pin";
import { nextBandMarks, type BandMarks } from "../../lib/optBands";
import { formFor, type BandForm } from "../../lib/keptRun";

// One decoded `event: X\ndata: Y` frame off an SSE byte stream.
type SseFrame = { event: string; data: string };

// Frames `event:`/`data:` lines separated by a blank line (issue #773 unit
// 4's pinned contract: progress/result/error, exactly one terminal event per
// stream). Multi-line `data:` fields join with `\n` per the SSE spec, though
// this contract only ever sends one JSON line per field.
//
// `signal`'s abort cancels the reader directly rather than relying on the
// fetch's own abort propagation: a stubbed test transport's stream has no
// such propagation, and canceling a reader with a read pending resolves that
// read as done (WHATWG streams), which is what unblocks the loop below.
async function* readSseFrames(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
): AsyncGenerator<SseFrame> {
  const reader = body.getReader();
  const onAbort = () => {
    reader.cancel().catch(() => {});
  };
  signal.addEventListener("abort", onAbort);
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let sep = buf.indexOf("\n\n");
      while (sep !== -1) {
        const block = buf.slice(0, sep);
        buf = buf.slice(sep + 2);
        let event = "message";
        const dataLines: string[] = [];
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (dataLines.length > 0) yield { event, data: dataLines.join("\n") };
        sep = buf.indexOf("\n\n");
      }
    }
  } finally {
    signal.removeEventListener("abort", onAbort);
    reader.releaseLock();
  }
}

// The value at a knob's path in a value bag (a flat name, or a group leaf).
function valueAtPath(bag: unknown, path: (string | number)[]): unknown {
  let v: unknown = bag;
  for (const k of path) {
    if (v === null || typeof v !== "object") return undefined;
    v = (v as Record<string | number, unknown>)[k];
  }
  return v;
}

// `bag` with a run's answer laid over it, each knob at its path.
function layParams(
  bag: ParamValueBag,
  params: Record<string, number | string | boolean>,
): ParamValueBag {
  let out = bag;
  for (const [name, val] of Object.entries(params)) {
    if (valueAtPath(out, knobPath(name)) !== val) {
      out = setValueAtPath(out, knobPath(name), val) as ParamValueBag;
    }
  }
  return out;
}

/** The band run's default balance (AK#1901), sent explicitly on every band
 *  run so the UI and the server cannot drift. 0.5: easy bands are not dragged
 *  up to the hardest band's SWR (0.2 equalised every band on a real deck). */
export const DEFAULT_MEAN_WEIGHT = 0.5;

export type OptFree = { name: string; min: number; max: number };

/** The `optimize` object of a POST /optimize body. With no bands it is the
 *  single-frequency spec exactly as it has always been sent (a test pins the
 *  body). With bands (AK#1901) it is the multi-band minimax: each band an SWR
 *  target at its own frequency, `mean_weight` the balance, and the budget
 *  left to the server, whose default scales with the knob count. The
 *  single-band `objective` and `seed_surrogate` are not read on that path and
 *  are not sent. */
export function optimizeSpec(
  free: OptFree[],
  opts: {
    objective: OptObjective;
    seed: boolean;
    bands: number[] | null;
    meanWeight: number;
    /** A kept run's form for these bands (#1921, `formFor`), else the
     *  SWR minimax. */
    form?: BandForm | null;
  },
): Record<string, unknown> {
  if (opts.bands && opts.bands.length > 0) {
    if (opts.form) {
      return {
        free,
        bands: opts.form.bands.map((b) => ({ ...b })),
        mode: opts.form.mode,
        mean_weight: opts.meanWeight,
      };
    }
    return {
      free,
      bands: opts.bands.map((freq) => ({ freq, objective: "swr" })),
      mode: "minimax",
      mean_weight: opts.meanWeight,
    };
  }
  return {
    free,
    objective: opts.objective,
    max_evals: 40,
    seed_surrogate: opts.seed,
  };
}

// The empty band lists, shared so a design with none keeps one identity
// across renders (the memos and effects below take them as deps).
const NO_BANDS: number[] = [];

/** State kept per design (AK#2292): the value for `geometry`, a setter for
 *  it, and a setter for any design by key. A run writes its own design's
 *  slot from its stream whichever design is shown. */
function useByGeometry<T>(
  geometry: string,
  initial: T,
): [T, (action: SetStateAction<T>) => void, (g: string, action: SetStateAction<T>) => void] {
  const [byGeom, setByGeom] = useState<Record<string, T>>({});
  const setFor = useCallback(
    (g: string, action: SetStateAction<T>) =>
      setByGeom((prev) => {
        const old = g in prev ? prev[g] : initial;
        const next =
          typeof action === "function" ? (action as (p: T) => T)(old) : action;
        return Object.is(next, old) ? prev : { ...prev, [g]: next };
      }),
    // `initial` is a constant at every call site.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  const set = useCallback((action: SetStateAction<T>) => setFor(geometry, action), [geometry, setFor]);
  return [geometry in byGeom ? byGeom[geometry] : initial, set, setFor];
}

// --- Reactive knob optimiser (POST /optimize) ---
//
// The reactive knob optimiser's whole behavior cluster (#642 seam 5b-3):
// state, the render-time optEnabledRef mirror, the POST /optimize runner,
// the fixed-input signature that triggers a re-tune, the pause cue, the
// per-knob settings helpers and the knob-menu Escape listener.
//
// A RUN BELONGS TO ITS DESIGN (AK#2292). Its toggle, band list, progress,
// result and abort controller are kept per design key, and a design switch
// neither cancels nor forgets it: the run keeps streaming into its own
// design's slot while another is shown, and switching back shows its live
// progress, or its result. A result that lands while another design is
// shown waits, and is written back to its own knobs when its design is
// shown again, so it can never land on the wrong design's knobs. A design
// switch used to abort the run and clear all of it, which lost a long band
// run the user had come back for.
//
// optAbortRef and optEnabledRef come back raw: selectVariant and
// handleUserParamChange stay in DesignSession and mutate them directly, which
// is exactly the "the human took over" path, so wrapping them in helpers would
// change what those call sites can express. Both read the SHOWN design's.
export function useOptimizer({
  geometry,
  currentValues,
  currentValuesKey,
  currentSchema,
  backend,
  designFreq,
  measFreq,
  autoSim,
  active,
  buildRequest,
  setParamAtPath,
  zoOverride = null,
}: {
  geometry: string;
  currentValues: ParamValueBag;
  currentValuesKey: string;
  currentSchema: SchemaItem[];
  /** Backend NAME — a dep-array/signature member, not a capability read. */
  backend: string;
  designFreq: number;
  measFreq: number;
  autoSim: boolean;
  active: boolean;
  buildRequest: () => SolveRequest;
  setParamAtPath: (
    path: (string | number)[],
    value: number | string | boolean,
  ) => void;
  /** The gear menu's Zo override (AK#1735), null = the design's own. It
   *  reaches the request through `buildRequest`; it is here only so a new
   *  reference re-tunes, the way a new objective does. */
  zoOverride?: number | null;
}) {
  // Master enable + objective live in the compact control by meas-freq; per-knob
  // "vary" + extents + step live in each knob's right-click menu (knobOpt).
  const [optEnabled, setOptEnabled] = useByGeometry(geometry, false);
  const [optObjective, setOptObjective] = useState<OptObjective>("swr");
  // #1176. OFF by default: the seed is measured neutral-to-slightly-negative
  // from a TUNED start and decisive from a poor one, so it is the user's
  // statement about which they are in, not a default we can guess.
  const [optSeed, setOptSeed] = useState<boolean>(false);
  // AK#1901: optimise across several bands at once. null = off, and then the
  // request is exactly the single-frequency one; a list = each band's
  // frequency in MHz (SWR at each, minimax). Belongs to the design it was set
  // on, and is kept per design.
  const [optBands, setOptBands] = useByGeometry<number[] | null>(geometry, null);
  // The bands ticked to show on the Smith chart while a knob turns: each a
  // live solve of its own per knob change, so none is shown until asked.
  // Only the ticked bands still in the list count (`optBandsLive`).
  const [optBandsShown, setOptBandsShown] = useByGeometry<number[]>(geometry, NO_BANDS);
  const optBandsLive = useMemo(
    () => (optBands ? optBands.filter((f) => optBandsShown.includes(f)) : []),
    [optBands, optBandsShown],
  );
  // The band run's balance w: J = (1 - w) * worst band + w * mean of bands.
  const [optMeanWeight, setOptMeanWeight] = useState<number>(DEFAULT_MEAN_WEIGHT);
  // A kept run's form (#1921): read only while the band list is still its
  // frequencies (`formFor`), so an edit to Bands drops it by itself.
  const [optBandForm, setOptBandForm] = useByGeometry<BandForm | null>(geometry, null);
  const optForm = formFor(optBandForm, optBands);
  const [knobOpt, setKnobOpt] = useState<Record<string, Record<string, KnobOpt>>>({});
  // Open knob context menu: which param + anchor position, and the design it
  // was opened on. A menu belongs to its design: one left open across a
  // design switch reads as closed (derived below), which is what the
  // design-load reset used to do in an effect — and an effect runs AFTER the
  // commit that shows the new design's knobs, so a right-click landing in
  // that gap was opened and then wiped by the late reset (the zparamView
  // session-test flake, reproduced 2026-09-26). Keyed state has no gap.
  const [knobMenuAt, setKnobMenuAt] = useState<
    { name: string; x: number; y: number; geometry: string } | null
  >(null);
  const knobMenu = useMemo(
    () =>
      knobMenuAt && knobMenuAt.geometry === geometry
        ? { name: knobMenuAt.name, x: knobMenuAt.x, y: knobMenuAt.y }
        : null,
    [knobMenuAt, geometry],
  );
  const setKnobMenu = useCallback(
    (m: { name: string; x: number; y: number } | null) =>
      setKnobMenuAt(m ? { ...m, geometry } : null),
    [geometry],
  );
  // The run's own state, per design (AK#2292): each `...For` setter writes
  // the slot of the design a run belongs to, whichever is shown.
  const [optRunning, , setOptRunningFor] = useByGeometry(geometry, false);
  const [optResult, setOptResult, setOptResultFor] = useByGeometry<OptimizeResult | null>(
    geometry,
    null,
  );
  // A result that landed while another design was shown, written back when
  // its own design is shown again.
  const [optPendingResult, setOptPendingResult, setOptPendingResultFor] =
    useByGeometry<OptimizeResult | null>(geometry, null);
  // Latest `progress` frame of the in-flight run; reset to null at the start
  // of every runOptimize call so a stale frame never outlives its run.
  const [optProgress, , setOptProgressFor] = useByGeometry<OptProgress | null>(geometry, null);
  // A run the user stopped early (Optimize off mid-run) that had found a
  // better point than it started from: the "keep best so far" prompt.
  const [optStopped, setOptStopped, setOptStoppedFor] = useByGeometry<OptStopped | null>(
    geometry,
    null,
  );
  // The shown design, for a run's stream to tell whether its design is the
  // one on screen when its result lands.
  const geometryRef = useRef(geometry);
  // eslint-disable-next-line react-hooks/refs
  geometryRef.current = geometry; // mirror latest for the runs in flight
  // Each design's run starting objective: its first frame's, the warm
  // start's solve.
  const startObjectiveByGeom = useRef(new Map<string, number | null>());
  // Frame-to-frame arrival interval (#1007). The interactive `rtt` is one
  // request/response pair on the /ws channel, which the optimiser never
  // touches, so it has no exact analogue mid-run — but the gap between
  // progress frames is what the user is actually waiting through, and it
  // carries the same network and queueing the interactive number does. It is a
  // DIFFERENT quantity and the readout labels it as one.
  const [optFrameMs, , setOptFrameMsFor] = useByGeometry<number | null>(geometry, null);
  const [optError, , setOptErrorFor] = useByGeometry<string | null>(geometry, null);
  // A band run's live markers on the Smith chart (AK 0.97.1): each band's
  // last few impedances, from every progress frame. They outlive the run —
  // the final positions stay until the next edit — and the next run starts
  // them afresh.
  const [optBandMarks, setOptBandMarks, setOptBandMarksFor] = useByGeometry<BandMarks | null>(
    geometry,
    null,
  );
  // The last run's answer, the values it replaces and the bag it leaves. A
  // bag on the way there — every answered knob at its old value or its new
  // one, nothing else moved — is the run's own write-back (whole or knob by
  // knob), not an edit, so it must not clear the markers. Once the write-back
  // has landed (`done`), only that exact bag is.
  // Kept for the shown design only: a write-back happens only while its
  // design is shown, and it names that design, so another never reads it.
  const writtenBackRef = useRef<{
    params: Record<string, number | string | boolean>;
    before: Record<string, unknown>;
    key: string;
    done: boolean;
    geometry: string;
  } | null>(null);
  // The run's pace (AK 0.97.1): wall time since it started over the points
  // it has solved (`n_solves`; a memo hit costs nothing and is not counted).
  // Read off the frames' arrival, not their `solve_ms`: a memo hit's frame
  // repeats the last solve's `solve_ms`, and the wall time also carries the
  // lane and network a hosted run waits through. No ETA: how many points a
  // run needs is decided by when it converges, not known up front.
  const [optPaceMs, , setOptPaceMsFor] = useByGeometry<number | null>(geometry, null);
  // The run in flight replaced one that had not finished (AK#1912): a newer
  // input superseded it. Said on the readout ("restarted") rather than
  // dropping the old run silently.
  const [optRestarted, , setOptRestartedFor] = useByGeometry(geometry, false);
  // The Optimize gear menu is open (AK 0.97.1). Optimize is OFF while its
  // settings are edited: each edit in the menu (a band, the balance, Zo, the
  // objective) is a new input, and re-tuning on each started a run per edit,
  // each superseding the last — UR0GT's three bands were three POST /optimize
  // a second apart. Opening the menu stops the run in flight and switches
  // Optimize off; closing it switches Optimize back on only if it was on when
  // the menu opened, which starts ONE run with the new settings.
  const [optMenuOpen, setOptMenuOpenState] = useState(false);
  // Optimize was on when the menu opened: the menu paused it, and closing the
  // menu resumes it.
  const [optMenuPaused, setOptMenuPaused] = useState(false);
  // When something auto-pauses the optimizer, this holds *why*: grabbing a
  // knob marked for optimization by hand (said until Optimize is turned back
  // on), or loading a new design/variant (a brief cue, cleared after a few
  // seconds).
  const [optPausedBy, setOptPausedBy] = useState<OptPause | null>(null);
  // Each design's run in flight (AK#2292). `optAbortRef` is the SHOWN
  // design's, which is what every caller of it means: the human took over
  // the knobs on screen.
  const abortByGeom = useRef(new Map<string, AbortController | null>());
  const optAbortRef = useMemo<{ current: AbortController | null }>(
    () => ({
      get current() {
        return abortByGeom.current.get(geometryRef.current) ?? null;
      },
      set current(c: AbortController | null) {
        abortByGeom.current.set(geometryRef.current, c);
      },
    }),
    [],
  );
  // A closed tab stops its runs: nothing is left to read them.
  useEffect(() => {
    const runs = abortByGeom.current;
    return () => {
      for (const c of runs.values()) c?.abort();
    };
  }, []);
  // The signature each design's last run started at (`optFixedSig`): a
  // return to the design, or to its tab, with the same inputs re-runs
  // nothing, so the run in flight or the result on screen stays.
  const lastRunSig = useRef(new Map<string, string>());
  // Latest optEnabled mirrored into a ref so a variant load (selectVariant)
  // can tell whether the optimizer was actually running — to show the pause
  // cue only then — without taking optEnabled as a dep (#768).
  const optEnabledRef = useRef(false);
  // eslint-disable-next-line react-hooks/refs
  optEnabledRef.current = optEnabled; // mirror latest for a variant load
  // A design switch keeps every design's run, marks and toggle (all keyed
  // by design, AK#2292): nothing here is reset or aborted. Optimize stays on
  // in the design it was turned on in and off in one never turned on, so a
  // run never starts on a design the user did not ask it of.

  // Apply a settled /optimize outcome exactly as before: stash it for the
  // readout, and push every returned param through the normal onChange path
  // (which re-solves). Shared by the streaming `result` event and the
  // non-streaming JSON body. Only ever for the shown design: a result for
  // another is held (`landed`) until that design is shown.
  function applyOptimizeResult(data: OptimizeResult) {
    setOptResult(data);
    writtenBackRef.current = {
      params: data.params,
      before: Object.fromEntries(
        Object.keys(data.params).map((name) => [name, valueAtPath(currentValues, knobPath(name))]),
      ),
      key: JSON.stringify(layParams(currentValues, data.params)),
      done: false,
      geometry,
    };
    // A group leaf comes back under its dotted key (`bands.0.length_factor`,
    // AK#1901) and lands at its path; a flat name is the one-element path
    // it always was.
    for (const [name, val] of Object.entries(data.params)) {
      setParamAtPath(knobPath(name), val);
    }
  }

  // Write a set of knob values back the way a settled run's are, so the
  // same markers and the same "edit after the run clears them" rule apply.
  function writeBack(params: Record<string, number>) {
    writtenBackRef.current = {
      params,
      before: Object.fromEntries(
        Object.keys(params).map((name) => [name, valueAtPath(currentValues, knobPath(name))]),
      ),
      key: JSON.stringify(layParams(currentValues, params)),
      done: false,
      geometry,
    };
    for (const [name, val] of Object.entries(params)) {
      setParamAtPath(knobPath(name), val);
    }
  }

  // Optimize switched off while a run is in flight: stop it now (the server
  // stops when its client goes), leave the knobs where they started, and,
  // if the run had found a better point, offer it.
  function stopOptimize() {
    const frame = optProgress;
    optAbortRef.current?.abort();
    setOptEnabled(false);
    // Always say what happened: the prompt when the run found something
    // better than where it started, a plain "nothing better" otherwise
    // (a warm-started run's first trials are often worse than its start).
    // The start comes off the frame (the server's, so a dropped first frame
    // cannot lose it), else the first frame this page saw.
    const best = frame?.best;
    const start = frame?.objective_start ?? startObjectiveByGeom.current.get(geometry) ?? null;
    if (frame && best && start != null) {
      setOptStopped({
        params: best.params,
        objectiveStart: start,
        objectiveBest: best.objective,
        nEvals: frame.n_evals,
        improved: best.objective < start,
      });
    }
  }
  function keepBest() {
    if (optStopped?.improved) writeBack(optStopped.params);
    setOptStopped(null);
  }
  function discardBest() {
    setOptStopped(null);
  }

  // Run the optimiser once: POST the current solve request + the free knobs
  // (from each knob's menu) and objective, then apply the returned params to the
  // knobs (re-solving via the normal onChange path). Warm-started from the
  // current values; a newer run aborts the previous so stale results are
  // dropped. Optimises on the slot's own engine server-side (AK#1741).
  //
  // Requests `text/event-stream` (issue #773's pinned contract) to get live
  // `progress` frames; a server that doesn't stream yet ignores the header
  // and answers with today's plain JSON, which the content-type check below
  // routes to the unchanged single-shot path.
  //
  // The run is its design's (AK#2292): everything it writes goes to that
  // design's slot (`g`), so a design switch mid-run leaves it streaming
  // there, and its result is written back only to its own knobs.
  async function runOptimize() {
    const g = geometry;
    const settings = knobOpt[g] ?? {};
    const free = Object.entries(settings)
      .filter(([, o]) => o.vary)
      .map(([name, o]) => ({ name, min: o.optMin, max: o.optMax }));
    if (free.length === 0) return;
    const runs = abortByGeom.current;
    // A controller still set here is a run that has not settled: this one
    // supersedes it.
    setOptRestartedFor(g, (runs.get(g) ?? null) !== null);
    runs.get(g)?.abort();
    const ctrl = new AbortController();
    runs.set(g, ctrl);
    setOptRunningFor(g, true);
    setOptErrorFor(g, null);
    setOptProgressFor(g, null);
    setOptStoppedFor(g, null);
    setOptPendingResultFor(g, null);
    startObjectiveByGeom.current.set(g, null);
    setOptBandMarksFor(g, null);
    setOptPaceMsFor(g, null);
    const startedAt = performance.now();
    setOptFrameMsFor(g, null);
    let lastFrameAt: number | null = null;
    // The run's answer: written back now when its design is shown, else held
    // until it is (`optPendingResult`).
    const landed = (data: OptimizeResult) => {
      if (geometryRef.current === g) applyOptimizeResult(data);
      else {
        setOptResultFor(g, data);
        setOptPendingResultFor(g, data);
      }
    };
    try {
      const resp = await apiFetch("/optimize", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        signal: ctrl.signal,
        body: JSON.stringify({
          ...buildRequest(),
          // Reactive runs are warm-started, so a modest eval cap keeps them snappy.
          optimize: optimizeSpec(free, {
            objective: optObjective,
            seed: optSeed,
            bands: optBands,
            meanWeight: optMeanWeight,
            form: optForm,
          }),
        }),
      });
      if (ctrl.signal.aborted) return; // superseded by a newer run
      const streaming = (resp.headers.get("content-type") ?? "").includes(
        "text/event-stream",
      );
      if (streaming && resp.body) {
        for await (const { event, data } of readSseFrames(resp.body, ctrl.signal)) {
          if (ctrl.signal.aborted) break; // superseded mid-stream
          if (event === "progress") {
            {
              const now = performance.now();
              const prev = lastFrameAt;
              lastFrameAt = now;
              setOptFrameMsFor(g, prev == null ? null : now - prev);
              const frame = JSON.parse(data) as OptProgress;
              if (startObjectiveByGeom.current.get(g) == null && frame.n_evals === 1)
                startObjectiveByGeom.current.set(g, frame.objective);
              setOptProgressFor(g, frame);
              setOptBandMarksFor(g, (prev) => nextBandMarks(prev, frame));
              const solved = frame.n_solves ?? frame.n_evals;
              if (solved > 0) setOptPaceMsFor(g, (now - startedAt) / solved);
            }
          } else if (event === "result") {
            landed(JSON.parse(data) as OptimizeResult);
          } else if (event === "error") {
            setOptErrorFor(g, String((JSON.parse(data) as { detail: string }).detail));
          }
        }
      } else {
        const data = await resp.json();
        if (ctrl.signal.aborted) return; // superseded while the body was read
        if (data.error) {
          setOptErrorFor(g, String(data.error));
        } else {
          landed(data as OptimizeResult);
        }
      }
    } catch (e) {
      if (!ctrl.signal.aborted) setOptErrorFor(g, String(e));
    } finally {
      if (runs.get(g) === ctrl) {
        runs.set(g, null);
        setOptRunningFor(g, false);
      }
    }
  }

  // A result that landed while another design was shown is written back
  // when its design is shown again (AK#2292), through the same path a run's
  // answer always takes, so its knobs, markers and readout follow.
  useEffect(() => {
    if (!optPendingResult) return;
    // Applying the held result is the write-back the run would have made.
    setOptPendingResult(null);
    applyOptimizeResult(optPendingResult);
    // applyOptimizeResult is this render's, for the design now shown.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optPendingResult]);

  // Reactive optimisation. When enabled with >=1 free knob, re-tune shortly
  // after the user pauses on any *fixed* input. The trigger is a signature of
  // everything the optimiser depends on EXCEPT the free knobs' values — the
  // optimiser writes those, so including them would loop. Turning it on produces
  // a fresh signature, so it also tunes immediately on enable.
  const optFixedSig = useMemo(() => {
    if (!optEnabled) return "";
    const settings = knobOpt[geometry] ?? {};
    const free = Object.entries(settings).filter(([, o]) => o.vary);
    if (free.length === 0) return "";
    const freeSet = new Set(free.map(([n]) => n));
    let fixedBag: ParamValueBag = {};
    for (const [k, v] of Object.entries(currentValues)) {
      if (!freeSet.has(k)) fixedBag[k] = v;
    }
    // A free group leaf (AK#1901) sits inside a group the bag carries whole;
    // blank it there too, or the run's own write-back would change the
    // signature and re-tune forever.
    for (const name of freeSet) {
      const path = knobPath(name);
      if (path.length > 1 && path[0] in fixedBag) {
        fixedBag = setValueAtPath(fixedBag, path, "") as ParamValueBag;
      }
    }
    const fixed: Record<string, unknown> = fixedBag;
    return JSON.stringify({
      geometry,
      objective: optObjective,
      zo: zoOverride,
      backend,
      designFreq,
      // A band run reads its own frequencies, never the dial's — and a group
      // leaf's write-back can move the dial (link_meas_freq_to_param), which
      // must not read as a new input.
      ...(optBands ? {} : { measFreq }),
      bounds: free.map(([n, o]) => [n, o.optMin, o.optMax]),
      fixed,
      // Only when set, so a single-band signature is the string it always was.
      ...(optBands ? { bands: optBands, meanWeight: optMeanWeight } : {}),
      ...(optForm ? { form: optForm } : {}),
    });
    // currentValuesKey stands in for currentValues' contents in the deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    optEnabled,
    knobOpt,
    geometry,
    optObjective,
    optSeed,
    optBands,
    optMeanWeight,
    optForm,
    zoOverride,
    backend,
    designFreq,
    measFreq,
    currentValuesKey,
  ]);

  useEffect(() => {
    // Paused (Live off) holds the optimiser too — it drives engine solves, so it
    // must respect the same gate as the main solve. Resuming re-runs this effect
    // (autoSim is a dep) and re-tunes; so does turning Optimize back on.
    if (!optFixedSig || !autoSim) {
      lastRunSig.current.delete(geometry);
      return;
    }
    if (!active) return;
    // Back on a design (or its tab) whose inputs are the ones its run
    // started at: that run, in flight or finished, is the answer (AK#2292).
    if (lastRunSig.current.get(geometry) === optFixedSig) return;
    const t = setTimeout(() => {
      lastRunSig.current.set(geometry, optFixedSig);
      runOptimize();
    }, 400);
    return () => clearTimeout(t);
    // runOptimize captured here reflects the state at this signature; re-running
    // only when the signature changes is intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optFixedSig, autoSim, active]);

  // An edit after the run (a knob, the band list) leaves the markers
  // describing an antenna that is no longer there: they go. The run's own
  // write-back is the exception — it is where the markers already are. A
  // design switch is no edit: each design keeps its own markers (AK#2292).
  const valuesSeenFor = useRef(geometry);
  useEffect(() => {
    if (valuesSeenFor.current !== geometry) {
      valuesSeenFor.current = geometry;
      return;
    }
    const written = writtenBackRef.current;
    if (written && written.geometry === geometry) {
      if (currentValuesKey === written.key) {
        written.done = true;
        return;
      }
      const onTheWay =
        !written.done &&
        Object.entries(written.params).every(([name, val]) => {
          const now = valueAtPath(currentValues, knobPath(name));
          return now === val || now === written.before[name];
        }) &&
        JSON.stringify(layParams(currentValues, written.params)) === written.key;
      if (onTheWay) return;
    }
    writtenBackRef.current = null;
    // A reset on input change, not a derivable value (#768).
    setOptBandMarks(null);
    // currentValuesKey stands in for currentValues' contents in the deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentValuesKey, geometry]);
  const bandsSeenFor = useRef(geometry);
  useEffect(() => {
    if (bandsSeenFor.current !== geometry) {
      bandsSeenFor.current = geometry;
      return;
    }
    writtenBackRef.current = null;
    // A reset on input change, not a derivable value (#768).
    setOptBandMarks(null);
    // setOptBandMarks follows geometry, which is already a dep.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optBands, geometry]);

  // The "loaded a new design" cue is a brief flash: clear it a few seconds
  // after it appears so it doesn't linger while Optimize stays off. A hand
  // move's pause stays said until Optimize is turned back on (AK#1912): it is
  // the optimizer's state, not a passing event.
  useEffect(() => {
    if (!optPausedBy || optPausedBy.kind === "knob") return;
    const t = setTimeout(() => setOptPausedBy(null), 5000);
    return () => clearTimeout(t);
  }, [optPausedBy]);

  // The effective per-knob optimiser settings: the stored entry, or seeded from
  // the schema and the knob's value now (`defaultKnobOpt`). Marking a knob
  // stores it, so its range is fixed from then on, round the value it had.
  function knobOptFor(name: string): KnobOpt {
    const existing = knobOpt[geometry]?.[name];
    if (existing) return existing;
    const v = valueAtPath(currentValues, knobPath(name));
    return defaultKnobOpt(currentSchema, name, typeof v === "number" ? v : undefined);
  }
  function updateKnobOpt(name: string, patch: Partial<KnobOpt>) {
    const base = knobOptFor(name);
    setKnobOpt((prev) => ({
      ...prev,
      [geometry]: { ...(prev[geometry] ?? {}), [name]: { ...base, ...patch } },
    }));
  }

  // Close the knob menu on Escape.
  useEffect(() => {
    if (!knobMenu || !active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setKnobMenu(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [knobMenu, active, setKnobMenu]);

  function setOptMenuOpen(open: boolean) {
    if (open === optMenuOpen) return;
    setOptMenuOpenState(open);
    if (open) {
      // The same stop as a hand move of a marked knob: the abort cancels the
      // request, and the server stops the run when its client goes.
      setOptMenuPaused(optEnabled);
      if (optEnabled) {
        optAbortRef.current?.abort();
        setOptEnabled(false);
      }
    } else {
      if (optMenuPaused) setOptEnabled(true);
      setOptMenuPaused(false);
    }
  }

  // How many knobs this design has marked (AK#1912): none means Optimize
  // has nothing to do, and the readout says so.
  const optMarked = Object.values(knobOpt[geometry] ?? {}).filter((o) => o.vary).length;

  return {
    optEnabled,
    optMarked,
    optRestarted,
    optBandMarks,
    optPaceMs,
    optMenuOpen,
    optMenuPaused,
    setOptMenuOpen,
    setOptEnabled,
    optObjective,
    setOptObjective,
    optSeed,
    setOptSeed,
    optBands,
    setOptBands,
    optBandsShown,
    setOptBandsShown,
    optBandsLive,
    optMeanWeight,
    setOptMeanWeight,
    optForm,
    setOptBandForm,
    knobOpt,
    setKnobOpt,
    knobMenu,
    setKnobMenu,
    optRunning,
    optResult,
    optProgress,
    optStopped,
    stopOptimize,
    keepBest,
    discardBest,
    optFrameMs,
    optError,
    optPausedBy,
    setOptPausedBy,
    optAbortRef,
    optEnabledRef,
    knobOptFor,
    updateKnobOpt,
  };
}
