import type { SolveResponse } from "../../lib/api";

export type FarFieldCut = "xy" | "yz";

// Scalar far-field metrics from /pattern_metrics, shown in the compare table.
export type PatternMetrics = {
  peak_gain_dbi: number;
  takeoff_deg: number;
  azimuth_deg: number;
  front_to_back_db: number;
  az_beamwidth_deg: number;
  el_beamwidth_deg: number;
  measurement_freq_mhz?: number;
};

// A pinned far-field snapshot: the full solve response (so its cut traces
// recompute through the same math as the live one, in whatever cut the user is
// viewing) plus a label, and the metrics fetched for the table. Pins live in
// the shell and are shared across sessions (see PinsContext), so they survive
// design switches and tab closes — you can overlay one antenna's pattern on
// another's, including a design open in a different tab.
export type PinnedPattern = {
  id: string;
  label: string;
  result: SolveResponse;
  metrics: PatternMetrics | null;
  // Whether the ghost overlay is drawn. A disabled pin keeps its table row
  // (dimmed, metrics still readable) — that's the point of disable vs delete.
  enabled: boolean;
  // Fixed GHOST_COLORS slot, assigned at pin time. Stored — not the array
  // index — because the chart draws a filtered (enabled-only) list while the
  // table draws all pins; positional colors would desynchronize the two, and
  // already shifted every later pin's color on delete.
  colorIdx: number;
};
