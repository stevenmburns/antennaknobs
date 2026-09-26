import { useLayoutEffect, useRef } from "react";

// Keeps a position:fixed popover inside the viewport (Steve, 2026-09-26: at
// 125 % browser zoom the Z-vs-parameter chart's right-axis popover opened
// mostly off screen, anchored at the click and growing rightward).
//
// `at` is the click, in viewport px. `side` is the way the box opens from
// it: "right" (its left edge at the click, the old placement) or "left" (its
// right edge at the click — toward the chart's interior from a right-hand
// axis). After layout the box is measured and clamped to the viewport with a
// margin, so it stays on screen at any zoom or window width whichever side
// it opens to. The position is written to the element directly: it is a
// measurement of the rendered box, not state the render depends on.

export const VIEWPORT_MARGIN = 8;

export function clampToViewport(
  at: { x: number; y: number },
  size: { width: number; height: number },
  viewport: { width: number; height: number },
  side: "left" | "right" = "right",
  margin = VIEWPORT_MARGIN,
): { left: number; top: number } {
  const wanted = side === "left" ? at.x - size.width : at.x;
  const left = Math.max(margin, Math.min(wanted, viewport.width - size.width - margin));
  const top = Math.max(margin, Math.min(at.y, viewport.height - size.height - margin));
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
      const r = el.getBoundingClientRect();
      const { left, top } = clampToViewport(
        { x, y },
        { width: r.width, height: r.height },
        { width: window.innerWidth, height: window.innerHeight },
        side,
      );
      el.style.left = `${left}px`;
      el.style.top = `${top}px`;
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [x, y, side]);
  return ref;
}
