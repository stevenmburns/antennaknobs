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
