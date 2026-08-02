import { createContext } from "react";
import type { SolveRequest, SolveResponse } from "../../lib/api";
import type { Theme } from "../hooks";
import type { PatternMetrics, PinnedPattern } from "../charts/types";

// Theme is global (owned by the shell) but the toggle button lives in each
// session's sidebar header; sessions reach the setter through this context so
// the single button drives the one shared theme.
export const ThemeControlContext = createContext<(next: Theme) => void>(() => {});

// The open design sessions and the controls to switch / add / close them. The
// shell provides this; each session renders a <TabStrip> off it, so all
// mounted sessions show the same tabs (only the active one is visible).
export type SessionMeta = { id: number };
export type SessionsCtx = {
  sessions: SessionMeta[];
  activeId: number;
  add: () => void;
  close: (id: number) => void;
  setActive: (id: number) => void;
  // Per-session one-line summary (design · solver · segs · ground) for the tab
  // hover, reported up from each session (which owns that state).
  summaries: Record<number, string>;
  reportSummary: (id: number, summary: string) => void;
};
export const SessionsContext = createContext<SessionsCtx>({
  sessions: [],
  activeId: 0,
  add: () => {},
  close: () => {},
  setActive: () => {},
  summaries: {},
  reportSummary: () => {},
});

// Pinned far-field patterns, shared across all design sessions: pin in one
// tab, compare against it in any other. Owned by the shell — a pin is a
// frozen snapshot (full solve response + fetched metrics) with no live tie to
// the session that made it, so it survives design switches and tab closes.
// A separate context from SessionsContext: pin churn (async metrics arrivals)
// shouldn't invalidate the memoized tab-strip context.
export type PinsCtx = {
  pins: PinnedPattern[];
  // Snapshot `result` under `label`; `req` is the request that produced it,
  // used to fetch the compare-table metrics.
  addPin: (label: string, result: SolveResponse, req: SolveRequest) => void;
  removePin: (id: string) => void;
  // Flip a pin's ghost overlay on/off without losing the snapshot.
  togglePin: (id: string) => void;
  clearPins: () => void;
};
export const PinsContext = createContext<PinsCtx>({
  pins: [],
  addPin: () => {},
  removePin: () => {},
  togglePin: () => {},
  clearPins: () => {},
});

// Fetch the scalar far-field metrics for a request (peak gain, takeoff, F/B,
// beamwidths). Returns null when the design can't be evaluated or on error.
export async function fetchMetrics(req: SolveRequest): Promise<PatternMetrics | null> {
  try {
    const resp = await fetch("/pattern_metrics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    const data = await resp.json();
    return data.available ? (data.metrics as PatternMetrics) : null;
  } catch {
    return null;
  }
}
