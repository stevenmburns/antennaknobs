import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
} from "./VfoPanel";
import { apiFetch } from "../../lib/pin";

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
  },
): Record<string, unknown> {
  if (opts.bands && opts.bands.length > 0) {
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

// --- Reactive knob optimiser (POST /optimize) ---
//
// The reactive knob optimiser's whole behavior cluster (#642 seam 5b-3):
// state, the render-time optEnabledRef mirror, the design-load reset, the
// POST /optimize runner, the fixed-input signature that triggers a re-tune,
// the pause cue, the per-knob settings helpers and the knob-menu Escape
// listener. The cluster moves whole so its internal hook order and every
// literal dep array are unchanged.
//
// optAbortRef and optEnabledRef come back raw: selectVariant and
// handleUserParamChange stay in DesignSession and mutate them directly, which
// is exactly the "the human took over" path, so wrapping them in helpers would
// change what those call sites can express.
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
  const [optEnabled, setOptEnabled] = useState(false);
  const [optObjective, setOptObjective] = useState<OptObjective>("swr");
  // #1176. OFF by default: the seed is measured neutral-to-slightly-negative
  // from a TUNED start and decisive from a poor one, so it is the user's
  // statement about which they are in, not a default we can guess.
  const [optSeed, setOptSeed] = useState<boolean>(false);
  // AK#1901: optimise across several bands at once. null = off, and then the
  // request is exactly the single-frequency one; a list = each band's
  // frequency in MHz (SWR at each, minimax). Belongs to the design it was set
  // on, so the design-load reset clears it.
  const [optBands, setOptBands] = useState<number[] | null>(null);
  // The band run's balance w: J = (1 - w) * worst band + w * mean of bands.
  const [optMeanWeight, setOptMeanWeight] = useState<number>(DEFAULT_MEAN_WEIGHT);
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
  const [optRunning, setOptRunning] = useState(false);
  const [optResult, setOptResult] = useState<OptimizeResult | null>(null);
  // Latest `progress` frame of the in-flight run; reset to null at the start
  // of every runOptimize call so a stale frame never outlives its run.
  const [optProgress, setOptProgress] = useState<OptProgress | null>(null);
  // Frame-to-frame arrival interval (#1007). The interactive `rtt` is one
  // request/response pair on the /ws channel, which the optimiser never
  // touches, so it has no exact analogue mid-run — but the gap between
  // progress frames is what the user is actually waiting through, and it
  // carries the same network and queueing the interactive number does. It is a
  // DIFFERENT quantity and the readout labels it as one.
  const [optFrameMs, setOptFrameMs] = useState<number | null>(null);
  const lastFrameAtRef = useRef<number | null>(null);
  const [optError, setOptError] = useState<string | null>(null);
  // The run in flight replaced one that had not finished (AK#1912): a newer
  // input superseded it. Said on the readout ("restarted") rather than
  // dropping the old run silently.
  const [optRestarted, setOptRestarted] = useState(false);
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
  const optAbortRef = useRef<AbortController | null>(null);
  // Latest optEnabled mirrored into a ref so the design-load reset (effects keyed
  // on geometry, and selectVariant) can tell whether the optimizer was actually
  // running — to show the pause cue only then — without taking optEnabled as a
  // dep (which would re-run the reset on every toggle).
  const optEnabledRef = useRef(false);
  // optEnabled mirrored so the design-load reset can tell whether the
  // optimizer was actually running, without taking it as a dep (#768).
  // eslint-disable-next-line react-hooks/refs
  optEnabledRef.current = optEnabled; // mirror latest for the design-load reset
  // Per-knob settings persist per geometry (knobOpt is keyed by geometry); just
  // close any open menu / clear the last result / abort any in-flight run when
  // the antenna changes. The optimizer also *pauses* on a design switch — its
  // objective and marks belong to the design you left — but this design's marks
  // are kept (they're keyed by geometry), so returning restores them; only the
  // running toggle is switched off. Show the cue only if it was actually on.
  useEffect(() => {
    optAbortRef.current?.abort();
    // Design-load reset: clears the optimizer's result/menu and shows the
    // pause cue. A reset on input change, not a derivable value (#768).
    // (The knob menu needs no reset here: it is keyed to its design, above.)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOptResult(null);
    setOptProgress(null);
    setOptError(null);
    setOptBands(null);
    if (optEnabledRef.current) {
      setOptEnabled(false);
      setOptPausedBy({ kind: "load" });
    }
    // optEnabledRef is read (not a dep) on purpose — see its declaration.
  }, [geometry]);

  // Apply a settled /optimize outcome exactly as before: stash it for the
  // readout, and push every returned param through the normal onChange path
  // (which re-solves). Shared by the streaming `result` event and the
  // non-streaming JSON body.
  function applyOptimizeResult(data: OptimizeResult) {
    setOptResult(data);
    // A group leaf comes back under its dotted key (`bands.0.length_factor`,
    // AK#1901) and lands at its path; a flat name is the one-element path
    // it always was.
    for (const [name, val] of Object.entries(data.params)) {
      setParamAtPath(knobPath(name), val);
    }
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
  async function runOptimize() {
    const settings = knobOpt[geometry] ?? {};
    const free = Object.entries(settings)
      .filter(([, o]) => o.vary)
      .map(([name, o]) => ({ name, min: o.optMin, max: o.optMax }));
    if (free.length === 0) return;
    // A controller still set here is a run that has not settled: this one
    // supersedes it.
    setOptRestarted(optAbortRef.current !== null);
    optAbortRef.current?.abort();
    const ctrl = new AbortController();
    optAbortRef.current = ctrl;
    setOptRunning(true);
    setOptError(null);
    setOptProgress(null);
    setOptFrameMs(null);
    lastFrameAtRef.current = null;
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
              const prev = lastFrameAtRef.current;
              lastFrameAtRef.current = now;
              setOptFrameMs(prev == null ? null : now - prev);
              setOptProgress(JSON.parse(data) as OptProgress);
            }
          } else if (event === "result") {
            applyOptimizeResult(JSON.parse(data) as OptimizeResult);
          } else if (event === "error") {
            setOptError(String((JSON.parse(data) as { detail: string }).detail));
          }
        }
      } else {
        const data = await resp.json();
        if (ctrl.signal.aborted) return; // superseded while the body was read
        if (data.error) {
          setOptError(String(data.error));
        } else {
          applyOptimizeResult(data as OptimizeResult);
        }
      }
    } catch (e) {
      if (!ctrl.signal.aborted) setOptError(String(e));
    } finally {
      if (optAbortRef.current === ctrl) {
        optAbortRef.current = null;
        setOptRunning(false);
      }
    }
  }

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
    zoOverride,
    backend,
    designFreq,
    measFreq,
    currentValuesKey,
  ]);

  useEffect(() => {
    // Paused (Live off) holds the optimiser too — it drives engine solves, so it
    // must respect the same gate as the main solve. Resuming re-runs this effect
    // (autoSim is a dep) and re-tunes.
    if (!optFixedSig || !autoSim || !active) return;
    const t = setTimeout(() => {
      runOptimize();
    }, 400);
    return () => clearTimeout(t);
    // runOptimize captured here reflects the state at this signature; re-running
    // only when the signature changes is intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optFixedSig, autoSim, active]);

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
  // the schema (extents = slider bounds, step = schema step, not varying).
  function knobOptFor(name: string): KnobOpt {
    const existing = knobOpt[geometry]?.[name];
    if (existing) return existing;
    return defaultKnobOpt(currentSchema, name);
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
    optMeanWeight,
    setOptMeanWeight,
    knobOpt,
    setKnobOpt,
    knobMenu,
    setKnobMenu,
    optRunning,
    optResult,
    optProgress,
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
