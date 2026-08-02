import { useCallback, useMemo, useRef, useState } from "react";
import type { SolveRequest, SolveResponse } from "./lib/api";
import { GHOST_COLOR_COUNT } from "./components/charts/palette";
import type { PinnedPattern } from "./components/charts/types";
import { ThemeContext, type Theme } from "./components/hooks";
import {
  fetchMetrics,
  type PinsCtx,
  PinsContext,
  type SessionMeta,
  type SessionsCtx,
  SessionsContext,
  ThemeControlContext,
} from "./components/session/contexts";
import { DesignSession } from "./components/session/DesignSession";

// App shell. Owns the two pieces of truly global state — the light/dark theme
// and the list of open design sessions — and nothing else. Every session is a
// mounted <DesignSession>; only the active one is shown (the rest are hidden
// with CSS so their inputs survive). Switching flips `active`, which suspends
// the outgoing session's socket/listeners/solves and resumes the incoming
// one's (see the `active` gates in DesignSession).
export function App() {
  // Theme is seeded from the <html data-theme> the no-flash script in
  // index.html set (localStorage || prefers-color-scheme). The 3 canvases read
  // their colors from CSS vars via getComputedStyle, so they consume
  // ThemeContext to repaint on toggle (see FarFieldChart/SmithChart/
  // CurrentCanvas). The toggle button itself lives in each session's sidebar
  // and writes back through ThemeControlContext.
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );
  // Apply the attribute SYNCHRONOUSLY here, not in a post-render effect: React
  // runs child effects before parent effects, so the canvases' draw effects
  // would re-read getComputedStyle while the attribute still held the previous
  // theme — lagging one toggle behind the (pure-CSS) chrome. Setting it eagerly
  // means the attribute is already current when those effects re-run.
  const applyTheme = useCallback((next: Theme) => {
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* storage disabled — in-memory toggle still works */
    }
    setTheme(next);
  }, []);

  // Open sessions. Ids are stable and monotonic (never reused), so React keys
  // each session to a fixed mount for its whole lifetime — the whole point:
  // a session's inputs live in its component instance, so it must never be
  // reconciled onto a different session's tree.
  const [sessions, setSessions] = useState<SessionMeta[]>([{ id: 1 }]);
  const [activeId, setActiveId] = useState(1);
  const nextIdRef = useRef(2);
  // Per-session tab-hover summaries, reported up from each session.
  const [summaries, setSummaries] = useState<Record<number, string>>({});

  const add = useCallback(() => {
    const id = nextIdRef.current++;
    setSessions((prev) => [...prev, { id }]);
    setActiveId(id);
  }, []);

  const close = useCallback((id: number) => {
    setSessions((prev) => {
      if (prev.length <= 1) return prev; // always keep one session open
      const idx = prev.findIndex((s) => s.id === id);
      const next = prev.filter((s) => s.id !== id);
      // If the closed session was active, activate its neighbour (prefer the
      // one to the left, matching browser-tab behaviour).
      setActiveId((cur) =>
        cur === id ? next[Math.max(0, idx - 1)].id : cur,
      );
      return next;
    });
    setSummaries((prev) => {
      if (!(id in prev)) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  const setActive = useCallback((id: number) => setActiveId(id), []);

  // Identity-guarded so a session re-reporting the same summary is a no-op
  // (avoids a render loop from the reporting effect).
  const reportSummary = useCallback((id: number, summary: string) => {
    setSummaries((prev) => (prev[id] === summary ? prev : { ...prev, [id]: summary }));
  }, []);

  const sessionsCtx = useMemo<SessionsCtx>(
    () => ({ sessions, activeId, add, close, setActive, summaries, reportSummary }),
    [sessions, activeId, add, close, setActive, summaries, reportSummary],
  );

  // Pinned patterns, shared across sessions. The counter is shell-level so
  // pin ids stay unique no matter which session mints them; a pin is a frozen
  // snapshot, so it deliberately outlives the session that created it.
  const [pins, setPins] = useState<PinnedPattern[]>([]);
  const pinSeq = useRef(0);

  // Append the snapshot immediately (the ghost overlay needs no metrics),
  // then patch the table metrics in when /pattern_metrics answers. The color
  // slot is the smallest one no current pin holds, so a freed color is reused
  // before the palette wraps — and never shifts an existing pin's color.
  const addPin = useCallback(
    (label: string, result: SolveResponse, req: SolveRequest) => {
      const id = `pin-${pinSeq.current++}`;
      setPins((ps) => {
        const used = new Set(ps.map((p) => p.colorIdx));
        let colorIdx = 0;
        while (used.has(colorIdx) && colorIdx < GHOST_COLOR_COUNT) colorIdx++;
        if (colorIdx >= GHOST_COLOR_COUNT) colorIdx = ps.length % GHOST_COLOR_COUNT;
        return [...ps, { id, label, result, metrics: null, enabled: true, colorIdx }];
      });
      fetchMetrics(req).then((m) =>
        setPins((ps) => ps.map((p) => (p.id === id ? { ...p, metrics: m } : p))),
      );
    },
    [],
  );

  const removePin = useCallback((id: string) => {
    setPins((ps) => ps.filter((p) => p.id !== id));
  }, []);

  const togglePin = useCallback((id: string) => {
    setPins((ps) =>
      ps.map((p) => (p.id === id ? { ...p, enabled: !p.enabled } : p)),
    );
  }, []);

  const clearPins = useCallback(() => setPins([]), []);

  const pinsCtx = useMemo<PinsCtx>(
    () => ({ pins, addPin, removePin, togglePin, clearPins }),
    [pins, addPin, removePin, togglePin, clearPins],
  );

  return (
    <ThemeContext.Provider value={theme}>
      <ThemeControlContext.Provider value={applyTheme}>
        <SessionsContext.Provider value={sessionsCtx}>
          <PinsContext.Provider value={pinsCtx}>
            <div className="sessions">
              {sessions.map((s) => (
                <div
                  key={s.id}
                  className="session-mount"
                  // Hidden — not unmounted — so an inactive session keeps its
                  // inputs. `hidden` also removes it from the a11y tree and stops
                  // its canvases painting.
                  hidden={s.id !== activeId}
                >
                  <DesignSession id={s.id} active={s.id === activeId} />
                </div>
              ))}
            </div>
          </PinsContext.Provider>
        </SessionsContext.Provider>
      </ThemeControlContext.Provider>
    </ThemeContext.Provider>
  );
}
