import { useEffect, useMemo, useRef, useState } from "react";
import type { SolveRequest } from "../../lib/api";
import { type Backend } from "../../lib/backends";
import {
  defaultKnobOpt,
  type KnobOpt,
  type ParamValueBag,
  type SchemaItem,
} from "../../lib/params";
import {
  type OptimizeResult,
  type OptObjective,
  type OptPause,
} from "./VfoPanel";

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
}: {
  geometry: string;
  currentValues: ParamValueBag;
  currentValuesKey: string;
  currentSchema: SchemaItem[];
  backend: Backend;
  designFreq: number;
  measFreq: number;
  autoSim: boolean;
  active: boolean;
  buildRequest: () => SolveRequest;
  setParamAtPath: (
    path: (string | number)[],
    value: number | string | boolean,
  ) => void;
}) {
  // Master enable + objective live in the compact control by meas-freq; per-knob
  // "vary" + extents + step live in each knob's right-click menu (knobOpt).
  const [optEnabled, setOptEnabled] = useState(false);
  const [optObjective, setOptObjective] = useState<OptObjective>("swr");
  const [knobOpt, setKnobOpt] = useState<Record<string, Record<string, KnobOpt>>>({});
  // Open knob context menu: which param + anchor position.
  const [knobMenu, setKnobMenu] = useState<{ name: string; x: number; y: number } | null>(
    null,
  );
  const [optRunning, setOptRunning] = useState(false);
  const [optResult, setOptResult] = useState<OptimizeResult | null>(null);
  const [optError, setOptError] = useState<string | null>(null);
  // When something auto-pauses the optimizer, this holds *why* for a brief cue
  // (cleared on re-enable / after a few seconds): grabbing a knob marked for
  // optimization by hand ("changing X by hand"), or loading a new design/variant
  // ("loaded a new design").
  const [optPausedBy, setOptPausedBy] = useState<OptPause | null>(null);
  const optAbortRef = useRef<AbortController | null>(null);
  // Latest optEnabled mirrored into a ref so the design-load reset (effects keyed
  // on geometry, and selectVariant) can tell whether the optimizer was actually
  // running — to show the pause cue only then — without taking optEnabled as a
  // dep (which would re-run the reset on every toggle).
  const optEnabledRef = useRef(false);
  optEnabledRef.current = optEnabled; // mirror latest for the design-load reset
  // Per-knob settings persist per geometry (knobOpt is keyed by geometry); just
  // close any open menu / clear the last result / abort any in-flight run when
  // the antenna changes. The optimizer also *pauses* on a design switch — its
  // objective and marks belong to the design you left — but this design's marks
  // are kept (they're keyed by geometry), so returning restores them; only the
  // running toggle is switched off. Show the cue only if it was actually on.
  useEffect(() => {
    optAbortRef.current?.abort();
    setKnobMenu(null);
    setOptResult(null);
    setOptError(null);
    if (optEnabledRef.current) {
      setOptEnabled(false);
      setOptPausedBy({ kind: "load" });
    }
    // optEnabledRef is read (not a dep) on purpose — see its declaration.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry]);

  // Run the optimiser once: POST the current solve request + the free knobs
  // (from each knob's menu) and objective, then apply the returned params to the
  // knobs (re-solving via the normal onChange path). Warm-started from the
  // current values; a newer run aborts the previous so stale results are
  // dropped. Always uses the momwire engine server-side.
  async function runOptimize() {
    const settings = knobOpt[geometry] ?? {};
    const free = Object.entries(settings)
      .filter(([, o]) => o.vary)
      .map(([name, o]) => ({ name, min: o.optMin, max: o.optMax }));
    if (free.length === 0) return;
    optAbortRef.current?.abort();
    const ctrl = new AbortController();
    optAbortRef.current = ctrl;
    setOptRunning(true);
    setOptError(null);
    try {
      const resp = await fetch("/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({
          ...buildRequest(),
          // Reactive runs are warm-started, so a modest eval cap keeps them snappy.
          optimize: { free, objective: optObjective, max_evals: 40 },
        }),
      });
      const data = await resp.json();
      if (ctrl.signal.aborted) return; // superseded by a newer run
      if (data.error) {
        setOptError(String(data.error));
      } else {
        setOptResult(data as OptimizeResult);
        for (const [name, val] of Object.entries((data as OptimizeResult).params)) {
          setParamAtPath([name], val);
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
    const fixed: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(currentValues)) {
      if (!freeSet.has(k)) fixed[k] = v;
    }
    return JSON.stringify({
      geometry,
      objective: optObjective,
      backend,
      designFreq,
      measFreq,
      bounds: free.map(([n, o]) => [n, o.optMin, o.optMax]),
      fixed,
    });
    // currentValuesKey stands in for currentValues' contents in the deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    optEnabled,
    knobOpt,
    geometry,
    optObjective,
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

  // The "paused — changing X by hand" cue is a brief flash: clear it a few
  // seconds after it appears so it doesn't linger while Optimize stays off.
  useEffect(() => {
    if (!optPausedBy) return;
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
  }, [knobMenu, active]);

  return {
    optEnabled,
    setOptEnabled,
    optObjective,
    setOptObjective,
    knobOpt,
    setKnobOpt,
    knobMenu,
    setKnobMenu,
    optRunning,
    optResult,
    optError,
    optPausedBy,
    setOptPausedBy,
    optAbortRef,
    optEnabledRef,
    knobOptFor,
    updateKnobOpt,
  };
}
