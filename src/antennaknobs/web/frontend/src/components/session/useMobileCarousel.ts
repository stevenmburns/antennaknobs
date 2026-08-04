import { useEffect, useRef, useState } from "react";
import { type View } from "../../lib/view";
import { useSlideSize } from "../hooks";

// Where the carousel must sit after the PINNED list changed under it — the one
// piece of index arithmetic worth having outside React, because every hard
// case of #700 unit 4 is a statement about this function. `prevPinned` is the
// list `index` was measured against; `pinned` is the new one (never empty —
// useViewPrefs enforces a floor of one pin).
//
// Pages are `pinned ++ [Info]`, so:
//   - Info is index `pinned.length` and MOVES with every pin/unpin;
//   - a chart page is `pinned[index]`, so `view` and `index` must agree or the
//     dots point at a page the user is not looking at.
export function reconcileCarousel(
  prevPinned: View[],
  pinned: View[],
  index: number,
  view: View,
): { index: number; view: View } {
  if (index >= prevPinned.length) {
    // Parked on Info (or past where Info used to be, after a shrink). Info
    // keeps the user: it is the page they chose. `view` stays parked on a
    // chart page and only needs rescuing if THAT page was just unpinned.
    return {
      index: pinned.length,
      view: pinned.includes(view) ? view : pinned[pinned.length - 1],
    };
  }
  const at = pinned.indexOf(view);
  // The page under the thumb survived. Follow it rather than the old index:
  // pinning appends, so this is a no-op for the common case (no visible jump),
  // and it stays correct if a future reorder lands.
  if (at >= 0) return { index: at, view };
  // The page under the thumb was just unpinned. Hold the SLOT and adopt
  // whatever slid into it — clamped, because unpinning the last chart page
  // leaves the old index one past the end of the new list.
  const i = Math.min(index, pinned.length - 1);
  return { index: i, view: pinned[i] };
}

// The mobile output carousel's state, refs and the effects that keep the DOM
// scroll position and `view` in agreement (#642 seam 5b-3). Lifted whole out of
// DesignSession so the cluster's internal hook order is preserved exactly; the
// caller keeps `view`/`setView` because the desktop tree and the arrow-key
// cycler share them.
//
// `compareCollapsed` deliberately stays behind in DesignSession: its
// `useState(isMobile)` initializer has to run after `useIsMobile()` there.
export function useMobileCarousel({
  isMobile,
  orientation,
  pinned,
  view,
  setView,
}: {
  isMobile: boolean;
  orientation: "portrait" | "landscape";
  // The pinned views (useViewPrefs) — the carousel's page list, in pin order.
  // Every index compare below is against THIS, not the registry: an unpinned
  // view has no page, so a VIEWS-based bound would map a swipe onto a view the
  // carousel never rendered (#700 unit 4).
  pinned: View[];
  view: View;
  setView: (v: View) => void;
}) {
  // Mobile output carousel (all hooks unconditional — desktop leaves them
  // inert). mobileIndex is which screen the snap carousel rests on — there are
  // `pinned.length + 1` of them; `view` stays the source of truth for the
  // chart screens and their data effects, kept in sync by the scroll handler /
  // reverse-sync effect below.
  const [mobileIndex, setMobileIndex] = useState(0);
  const mobileCarouselRef = useRef<HTMLDivElement>(null);
  const mobileScrollRafRef = useRef<number | null>(null);
  const { ref: mobRef, size: mobChartSize } = useSlideSize(720, isMobile);
  // The pinned list `mobileIndex` was last valid against. null while the
  // desktop tree is up, so entering mobile always re-reconciles: a desktop
  // peek leaves `view` unpinned, and an unpinned view has no page here.
  const prevPinnedRef = useRef<View[] | null>(null);

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
      if (i < pinned.length) setView(pinned[i]);
    });
  };

  // Dot tap: jump to a screen. Info (the last index) is reachable only here
  // and by swipe — it deliberately leaves `view` on the last chart screen.
  const goToMobileScreen = (i: number) => {
    setMobileIndex(i);
    if (i < pinned.length) setView(pinned[i]);
    const el = mobileCarouselRef.current;
    if (el) el.scrollTo({ left: i * el.clientWidth, behavior: "smooth" });
  };

  // The page list changed under us (the picker sheet pinned or unpinned
  // something), or we just arrived from a desktop tree holding an unpinned
  // view. Either way the (index, view) pair can name a page that no longer
  // exists; reconcileCarousel says where it goes. Declared BEFORE the
  // reverse-sync effect so that effect's stale `view` closure finds no target
  // and stands down for one commit rather than paging somewhere else first.
  useEffect(() => {
    if (!isMobile) {
      prevPinnedRef.current = null;
      return;
    }
    const prev = prevPinnedRef.current;
    prevPinnedRef.current = pinned;
    // Same list AND a view that has a page: nothing to fix here, and
    // re-deriving would fight whatever the swipe/arrow paths just did.
    if (prev === pinned && pinned.includes(view)) return;
    const next = reconcileCarousel(prev ?? pinned, pinned, mobileIndex, view);
    if (next.view !== view) setView(next.view);
    if (next.index !== mobileIndex) setMobileIndex(next.index);
    const el = mobileCarouselRef.current;
    if (!el || el.clientWidth === 0) return;
    // Only when the DOM actually sits elsewhere: pinning appends a page
    // without moving the current one, and a scrollTo there is a visible jump.
    if (Math.round(el.scrollLeft / el.clientWidth) !== next.index) {
      el.scrollTo({ left: next.index * el.clientWidth, behavior: "smooth" });
    }
  }, [isMobile, pinned, view, mobileIndex, setView]);

  // Reverse sync: anything else that sets `view` (the arrow-key cycler) pages
  // the carousel to match. The DOM scroll position is the ground truth for
  // "where are we" — comparing rounded indices means we never fight an
  // in-progress swipe, and parking on Info ignores view changes entirely.
  useEffect(() => {
    if (!isMobile) return;
    const el = mobileCarouselRef.current;
    if (!el || el.clientWidth === 0) return;
    const target = pinned.indexOf(view);
    const current = Math.round(el.scrollLeft / el.clientWidth);
    if (target < 0 || current >= pinned.length || current === target) return;
    setMobileIndex(target);
    el.scrollTo({ left: target * el.clientWidth, behavior: "smooth" });
  }, [view, isMobile, pinned]);

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
