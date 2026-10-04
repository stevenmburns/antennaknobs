// The combined Az + El view's trace model (AK#1730), apart from its component
// so it can be tested without a canvas: which traces the plot draws, the one
// radial scale they share, and which legend focus it honours.
import type { PatternCuts } from "../../lib/api";
import { cutDbiTop } from "../../lib/refine";
import { traceFor } from "./cuts";
import type { FarFieldCut, PinnedPattern } from "./types";

/** The id the legend and the chart use for the live design's traces. */
export const LIVE_ENTITY = "live";

export type CombinedTrace = {
  /** LIVE_ENTITY, or the pin's id. */
  entity: string;
  cut: FarFieldCut;
  pinned: boolean;
  dbi: number[];
  anglesDeg?: number[];
  peakDbi: number;
};

/** Every trace the combined plot draws, pins first so the live pair draws on
 *  top. A cut with nothing above the floor is left out (it draws nothing and
 *  must not stretch the scale). `cuts[0]` is the live solve's, then one per
 *  enabled pin, in `pins` order — the order `useCutTraces` hands them back. */
export function combinedTraces(
  cuts: readonly (PatternCuts | null)[],
  pins: readonly Pick<PinnedPattern, "id">[],
): CombinedTrace[] {
  const out: CombinedTrace[] = [];
  const add = (c: PatternCuts | null, entity: string, pinned: boolean) => {
    for (const cut of ["xy", "yz"] as const) {
      const t = traceFor(c, cut);
      if (t) out.push({ entity, cut, pinned, ...t });
    }
  };
  pins.forEach((p, i) => add(cuts[i + 1] ?? null, p.id, true));
  add(cuts[0] ?? null, LIVE_ENTITY, false);
  return out;
}

/** The top of the shared radial scale: the peak over EVERY drawn trace, both
 *  cuts and the pins, through the same rule the one-cut charts use. */
export function combinedDbiTop(traces: readonly CombinedTrace[]): number {
  return cutDbiTop(traces.map((t) => t.peakDbi));
}

/** The highlight the chart honours (AK#1730): the stored ids that still name
 *  something drawn — the live design or a SHOWN pin. A pin since deleted or
 *  hidden drops out, so a stale id can never dim everything. Empty means no
 *  highlight: every trace at full strength. */
export function effectiveHighlight(
  stored: readonly string[],
  shownPins: readonly Pick<PinnedPattern, "id">[],
): string[] {
  return stored.filter(
    (id, i) =>
      stored.indexOf(id) === i &&
      (id === LIVE_ENTITY || shownPins.some((p) => p.id === id)),
  );
}

/** One row's highlight switched, independently of the others (not a radio):
 *  on if it was off, off if it was on. Works from the EFFECTIVE set, so stale
 *  ids are dropped on every toggle and un-highlighting every row always lands
 *  on the empty set, which draws everything at full strength. */
export function toggleHighlight(
  stored: readonly string[],
  id: string,
  shownPins: readonly Pick<PinnedPattern, "id">[],
): string[] {
  const eff = effectiveHighlight(stored, shownPins);
  return eff.includes(id) ? eff.filter((x) => x !== id) : [...eff, id];
}

/** How strongly a design's traces draw under a highlight: "full" with no
 *  highlight or when highlighted, "dim" when others are highlighted. */
export function highlightState(
  entity: string,
  effective: readonly string[],
): "normal" | "strong" | "dim" {
  if (effective.length === 0) return "normal";
  return effective.includes(entity) ? "strong" : "dim";
}

// The combined view's knob pair on a phone (AK#1732). At ~390 px the pair,
// side by side over the lower right, covered the plot's own lower right; on a
// phone it stacks into a column at the right edge (styles.css,
// .mobile-screen-combined) and the plot, left-aligned, gives up that column.
// The column is the ELEVATION label's width (9 uppercase 11 px letters,
// ~72 px, wider than the 54 px knob) + 2 × 8 px padding + 2 px border = 90,
// at 8 px from the edge, with 8 px between it and the plot and the plot's own
// 8 px inset: 114, rounded up.
export const CUT_PAIR_PHONE_COLUMN_PX = 116;

/** The combined view's plot size on a phone: the slide's square, narrowed so
 *  the knob column beside it has room. `paneWidth` is the carousel's. */
export function combinedPhoneChartSize(slide: number, paneWidth: number): number {
  return Math.max(160, Math.min(slide, paneWidth - CUT_PAIR_PHONE_COLUMN_PX));
}
