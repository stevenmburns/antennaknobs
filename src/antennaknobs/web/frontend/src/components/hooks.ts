import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

// Shared between App.tsx (which owns the Provider and the theme-toggle
// control) and the chart components under components/charts/ (which read it
// via useContext to repaint on theme toggle). Lives here rather than in
// App.tsx so neither side has to take a runtime import on the other —
// App.tsx imports the charts, so a chart importing this value straight out
// of App.tsx would be a live import cycle (issue #642 seam 3).
export type Theme = "light" | "dark";
export const ThemeContext = createContext<Theme>("light");

// `reattachKey`: the measuring effect early-returns while the ref is detached,
// so a caller whose measured element mounts LATER (e.g. the layout branch flips
// between mobile and desktop at runtime) must pass a value that changes with
// the branch, re-running the effect once the element exists.
export function useSlideSize(maxSize = 720, reattachKey?: unknown) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState(maxSize);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const rect = el.getBoundingClientRect();
      const s = Math.min(rect.width, rect.height, maxSize);
      setSize(Math.max(160, Math.floor(s) - 16));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [maxSize, reattachKey]);
  return { ref, size };
}

// Grid mode's per-cell chart size (unit 3, docs/plan-view-rail-scaling.md):
// same "measure the box, hand charts a square that fits it" idiom as
// useSlideSize, but the box is the WHOLE grid (rows × cols of equal cells
// with a CSS gap) rather than one slide. `rows`/`cols` must be the same
// numbers the caller feeds `.view-grid`'s inline grid-template (ViewGrid and
// DesignSession both derive them from useViewPrefs' gridShape), or the
// divided-up size disagrees with the actual cell box.
const GRID_GAP = 8; // mirrors .view-grid's `gap: var(--space-4)` in styles.css
export function useGridCellSize(
  rows: number,
  cols: number,
  maxSize = 560,
  reattachKey?: unknown, // see useSlideSize
) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState(maxSize);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const rect = el.getBoundingClientRect();
      const cellW = (rect.width - GRID_GAP * (cols - 1)) / cols;
      const cellH = (rect.height - GRID_GAP * (rows - 1)) / rows;
      const s = Math.min(cellW, cellH, maxSize);
      // -16 is the cell's own padding (8px each side, .grid-cell in
      // styles.css) — same overhead subtraction useSlideSize does for the
      // slide's padding.
      setSize(Math.max(160, Math.floor(s) - 16));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [rows, cols, maxSize, reattachKey]);
  return { ref, size };
}

// Mirror of the stylesheet's phone breakpoint. The query string MUST stay
// identical to the mobile `@media` prelude in styles.css so the JS layout
// branch and the CSS rules can never disagree about which viewports are
// "mobile": max-width 700px catches portrait phones, and the short+coarse
// clause catches landscape phones that are wider than 700px.
const MOBILE_MEDIA_QUERY =
  "(max-width: 700px), (max-height: 500px) and (pointer: coarse)";
const PORTRAIT_MEDIA_QUERY = "(orientation: portrait)";

function useMediaQuery(query: string): boolean {
  // useSyncExternalStore is StrictMode-safe and avoids the subscribe/setState
  // races of a hand-rolled effect. The snapshot is a boolean primitive — an
  // object snapshot would be re-created every call, which React rejects
  // ("The result of getSnapshot should be cached").
  const [subscribe, getSnapshot] = useMemo(() => {
    const mql = window.matchMedia(query);
    const sub = (onChange: () => void) => {
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    };
    return [sub, () => mql.matches] as const;
  }, [query]);
  return useSyncExternalStore(subscribe, getSnapshot);
}

export function useIsMobile() {
  const isMobile = useMediaQuery(MOBILE_MEDIA_QUERY);
  const portrait = useMediaQuery(PORTRAIT_MEDIA_QUERY);
  return {
    isMobile,
    orientation: portrait ? ("portrait" as const) : ("landscape" as const),
  };
}

// Document-fullscreen state + toggle for the gear menu's "full screen" check.
// This is the phone answer to browser chrome: on Android it hides BOTH the
// system status bar and the nav bar (the manifest's old standalone mode only
// hid the URL bar, and made Chrome nag to "install the app" besides).
// `supported` is false where element fullscreen doesn't exist (iPhone
// Safari), which hides the control. The subscribe pattern mirrors
// useMediaQuery: fullscreenchange fires on Esc / back-gesture exits too, so
// the checkbox can never disagree with the actual state.
export function useFullscreen() {
  const [subscribe, getSnapshot] = useMemo(() => {
    const sub = (onChange: () => void) => {
      document.addEventListener("fullscreenchange", onChange);
      return () => document.removeEventListener("fullscreenchange", onChange);
    };
    return [sub, () => document.fullscreenElement != null] as const;
  }, []);
  const active = useSyncExternalStore(subscribe, getSnapshot);
  const toggle = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      document.documentElement
        .requestFullscreen({ navigationUI: "hide" })
        .catch(() => {});
    }
  }, []);
  return {
    active,
    toggle,
    supported: typeof document.documentElement.requestFullscreen === "function",
  };
}

// Height the "All views" picker button occupies at the foot of the strip:
// its own fixed 28 px (see .view-picker-btn in styles.css) plus the one extra
// strip gap it adds. Changing either number here or there desyncs the model
// from the layout and the bottom thumb starts clipping.
const PICKER_SLOT = 28 + 8;

// The 3-thumb-era reference column's fixed overhead (see the width/height
// split comment below) — a yardstick, not a per-render measurement, so it
// lives at module scope: hoisted out of the hook body (rather than listed as
// a useEffect dep) because it is a literal constant that can never change
// between renders (react-hooks/exhaustive-deps, #736).
const WIDTH_OVERHEAD = 26 + 2 * 8 + 3 * 36;

export function useThumbColumnSize(
  stripRef: React.RefObject<HTMLDivElement>,
  nThumbs: number,
  maxThumb = 280,
  reattachKey?: unknown, // see useSlideSize
) {
  // Vertical thumbstrip: the rail views scaled so they ALWAYS fit (the strip
  // never scrolls — overflow:hidden in CSS). Fixed overhead per the CSS:
  //   strip padding (12+12) + (n-1) gaps of 8 + the picker slot +
  //   per-thumb (button padding 8+6 + label ~14 + gap 6 + border 2) ≈ 36 each,
  // biased slightly high (26 base) so they fit with a hair of slack rather
  // than clip; floor low so a short window shrinks them instead of
  // overflowing. n comes from the CALLER because the rail is now the user's
  // pinned set, not the registry: pinned−1 normally, pinned while peeking an
  // unpinned view. Zero thumbs still has to divide by something.
  //
  // Two dimensions since the schematic view made it 4 thumbs (issue #652):
  // `width` stays what the column measured in its 3-thumb era — chart text
  // is drawn at fixed pixel fonts, so squares small enough to stack 4 high
  // collide their left/right labels. Each thumb is a width × height
  // rectangle; the chart renders at width and scales down uniformly to
  // height (a true miniature — text shrinks with it instead of colliding).
  // That reference column is the 3-thumb era's, picker and all — it is a
  // fixed yardstick for text legibility, not a measurement of today's strip,
  // so the picker slot deliberately stays out of it.
  const n = Math.max(1, nThumbs);
  const overhead = 26 + (n - 1) * 8 + n * 36 + PICKER_SLOT;
  const [size, setSize] = useState({ width: 180, height: 180 });
  useEffect(() => {
    const el = stripRef.current;
    if (!el) return;
    const clamp = (v: number) => Math.max(40, Math.min(maxThumb, Math.floor(v)));
    const update = () => {
      const h = el.clientHeight;
      if (h <= 0) return;
      const width = clamp((h - WIDTH_OVERHEAD) / 3);
      const height = clamp((h - overhead) / n);
      setSize((s) =>
        s.width === width && s.height === height ? s : { width, height },
      );
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [stripRef, n, overhead, maxThumb, reattachKey]);
  return size;
}
