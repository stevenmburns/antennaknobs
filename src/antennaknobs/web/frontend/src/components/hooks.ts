import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { VIEWS } from "../lib/view";

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

export function useThumbColumnSize(
  stripRef: React.RefObject<HTMLDivElement>,
  maxThumb = 280,
  reattachKey?: unknown, // see useSlideSize
) {
  // Vertical thumbstrip: the non-active views scaled so they ALWAYS fit (the
  // strip never scrolls — overflow:hidden in CSS). Fixed overhead per the CSS:
  //   strip padding (12+12) + (n-1) gaps of 8 +
  //   per-thumb (button padding 8+6 + label ~14 + gap 6 + border 2) ≈ 36 each,
  // biased slightly high (26 base) so they fit with a hair of slack rather
  // than clip; floor low so a short window shrinks them instead of
  // overflowing. n tracks the view registry: every view but the active one.
  const nThumbs = VIEWS.length - 1;
  const overhead = 26 + (nThumbs - 1) * 8 + nThumbs * 36;
  const [size, setSize] = useState(180);
  useEffect(() => {
    const el = stripRef.current;
    if (!el) return;
    const update = () => {
      const h = el.clientHeight;
      if (h <= 0) return;
      const perThumb = (h - overhead) / nThumbs;
      setSize(Math.max(40, Math.min(maxThumb, Math.floor(perThumb))));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [stripRef, maxThumb, reattachKey]);
  return size;
}
