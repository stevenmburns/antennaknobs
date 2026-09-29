import { useLayoutEffect, useRef } from "react";

// Keeps a position:fixed popover inside the part of the page the viewer can
// SEE (Steve, 2026-09-26: at 125 % browser zoom the Z-vs-parameter chart's
// right-axis popover opened mostly off screen, anchored at the click and
// growing rightward; 2026-09-29: on his phone the SWR axis's popover did not
// appear at all).
//
// `at` is the click, in viewport px. `side` is the way the box opens from
// it: "right" (its left edge at the click, the old placement) or "left" (its
// right edge at the click — toward the chart's interior from a right-hand
// axis). After layout the box is measured and clamped, with a margin, to the
// VISUAL viewport: on a phone that is pinch-zoomed (the chart is small there,
// so zooming in on it is natural) the visible region is a window at
// (offsetLeft, offsetTop) inside the layout viewport that position:fixed and
// clientX/Y are measured in, and clamping to window.innerWidth/innerHeight
// from the layout origin put the box above or left of what was on screen.
// A box bigger than the visible region is capped to it and scrolls. The
// position is written to the element directly: it is a measurement of the
// rendered box, not state the render depends on.

export const VIEWPORT_MARGIN = 8;

/** The visible region, in the layout-viewport px that position:fixed uses. */
export type VisibleRect = { left: number; top: number; width: number; height: number };

export function visibleRect(): VisibleRect {
  const vv = typeof window !== "undefined" ? window.visualViewport : null;
  if (vv && vv.width > 0 && vv.height > 0) {
    return { left: vv.offsetLeft, top: vv.offsetTop, width: vv.width, height: vv.height };
  }
  return { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight };
}

export function clampToViewport(
  at: { x: number; y: number },
  size: { width: number; height: number },
  viewport: { width: number; height: number; left?: number; top?: number },
  side: "left" | "right" = "right",
  margin = VIEWPORT_MARGIN,
): { left: number; top: number } {
  const vl = viewport.left ?? 0;
  const vt = viewport.top ?? 0;
  const wanted = side === "left" ? at.x - size.width : at.x;
  // min before max: a box wider (taller) than the region pins to its left
  // (top) margin rather than off the far edge.
  const left = Math.max(vl + margin, Math.min(wanted, vl + viewport.width - size.width - margin));
  const top = Math.max(vt + margin, Math.min(at.y, vt + viewport.height - size.height - margin));
  return { left, top };
}

export function useInViewport<T extends HTMLElement>(
  at: { x: number; y: number },
  side: "left" | "right" = "right",
) {
  const ref = useRef<T>(null);
  const { x, y } = at;
  useLayoutEffect(() => {
    const place = () => {
      const el = ref.current;
      if (!el) return;
      const view = visibleRect();
      // Never larger than what can be seen: the rest scrolls inside it.
      el.style.maxWidth = `${Math.max(0, view.width - 2 * VIEWPORT_MARGIN)}px`;
      el.style.maxHeight = `${Math.max(0, view.height - 2 * VIEWPORT_MARGIN)}px`;
      el.style.overflow = "auto";
      const r = el.getBoundingClientRect();
      const { left, top } = clampToViewport(
        { x, y },
        { width: r.width, height: r.height },
        view,
        side,
      );
      el.style.left = `${left}px`;
      el.style.top = `${top}px`;
    };
    place();
    window.addEventListener("resize", place);
    const vv = window.visualViewport;
    vv?.addEventListener("resize", place);
    vv?.addEventListener("scroll", place);
    return () => {
      window.removeEventListener("resize", place);
      vv?.removeEventListener("resize", place);
      vv?.removeEventListener("scroll", place);
    };
  }, [x, y, side]);
  return ref;
}
