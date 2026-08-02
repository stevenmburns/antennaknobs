import { useEffect, useRef, useState } from "react";
import { VIEWS, type View } from "../../lib/view";
import { useSlideSize } from "../hooks";

// The mobile output carousel's state, refs and the two effects that keep the
// DOM scroll position and `view` in agreement (#642 seam 5b-3). Lifted whole
// out of DesignSession so the cluster's internal hook order is preserved
// exactly; the caller keeps `view`/`setView` because the desktop tree and the
// arrow-key cycler share them.
//
// `compareCollapsed` deliberately stays behind in DesignSession: its
// `useState(isMobile)` initializer has to run after `useIsMobile()` there.
export function useMobileCarousel({
  isMobile,
  orientation,
  view,
  setView,
}: {
  isMobile: boolean;
  orientation: "portrait" | "landscape";
  view: View;
  setView: (v: View) => void;
}) {
  // Mobile output carousel (all hooks unconditional — desktop leaves them
  // inert). mobileIndex is which of the 5 screens the snap carousel rests on;
  // `view` stays the source of truth for the 4 chart screens and their data
  // effects, kept in sync by the scroll handler / reverse-sync effect below.
  const [mobileIndex, setMobileIndex] = useState(0);
  const mobileCarouselRef = useRef<HTMLDivElement>(null);
  const mobileScrollRafRef = useRef<number | null>(null);
  const { ref: mobRef, size: mobChartSize } = useSlideSize(720, isMobile);

  // Track where a swipe/fling snaps and mirror it into state. rAF-throttled:
  // scroll events arrive per frame during a fling, one rounding per frame is
  // plenty. The rounded-index compare inside the setters keeps this from
  // fighting the programmatic scrolls below.
  const onMobileCarouselScroll = () => {
    if (mobileScrollRafRef.current !== null) return;
    mobileScrollRafRef.current = requestAnimationFrame(() => {
      mobileScrollRafRef.current = null;
      const el = mobileCarouselRef.current;
      if (!el || el.clientWidth === 0) return;
      const i = Math.round(el.scrollLeft / el.clientWidth);
      setMobileIndex((prev) => (prev === i ? prev : i));
      if (i < VIEWS.length) setView(VIEWS[i].id);
    });
  };

  // Dot tap: jump to a screen. Info (the last index) is reachable only here
  // and by swipe — it deliberately leaves `view` on the last chart screen.
  const goToMobileScreen = (i: number) => {
    setMobileIndex(i);
    if (i < VIEWS.length) setView(VIEWS[i].id);
    const el = mobileCarouselRef.current;
    if (el) el.scrollTo({ left: i * el.clientWidth, behavior: "smooth" });
  };

  // Reverse sync: anything else that sets `view` (the arrow-key cycler) pages
  // the carousel to match. The DOM scroll position is the ground truth for
  // "where are we" — comparing rounded indices means we never fight an
  // in-progress swipe, and parking on Info ignores view changes entirely.
  useEffect(() => {
    if (!isMobile) return;
    const el = mobileCarouselRef.current;
    if (!el || el.clientWidth === 0) return;
    const target = VIEWS.findIndex((v) => v.id === view);
    const current = Math.round(el.scrollLeft / el.clientWidth);
    if (target < 0 || current >= VIEWS.length || current === target) return;
    setMobileIndex(target);
    el.scrollTo({ left: target * el.clientWidth, behavior: "smooth" });
  }, [view, isMobile]);

  // An orientation flip (or any pane resize) changes the screen width, so
  // scrollLeft no longer sits on a snap point; re-center the active screen
  // once the new layout lands (hence the rAF). Skipped when the rounded
  // position already matches — never fights a drag.
  useEffect(() => {
    if (!isMobile) return;
    const raf = requestAnimationFrame(() => {
      const el = mobileCarouselRef.current;
      if (!el || el.clientWidth === 0) return;
      const i = Math.round(el.scrollLeft / el.clientWidth);
      if (i !== mobileIndex) el.scrollTo({ left: mobileIndex * el.clientWidth });
    });
    return () => cancelAnimationFrame(raf);
  }, [isMobile, orientation, mobChartSize, mobileIndex]);

  return {
    mobileIndex,
    mobileCarouselRef,
    mobRef,
    mobChartSize,
    onMobileCarouselScroll,
    goToMobileScreen,
  };
}
