import type { SolveResponse } from "../../lib/api";

export type FarFieldCut = "xy" | "yz";

export type PatternData = {
  theta_deg: number[];
  phi_deg: number[];
  gain_dbi: number[][];
  measurement_freq_mhz: number;
  /** The solve this pattern belongs to, when its engine ran a deck whose
   *  texts the Files view can show (AK#1506). */
  solve_id?: string;
};

// What a far-field chart would print in its corners. On the stage the chart
// hands these up instead of drawing them, and the overlay stacks show them:
// canvas text in a corner sits under whatever control the stage puts there,
// which a small or zoomed display makes coincide (AC6LA, QRZ #115).
export type FarFieldCaptions = {
  cut: FarFieldCut;
  /** Which cut this is: "elev @ 0° az (dBi)". */
  cutLabel: string;
  /** The live trace's maximum (the slice max) and where it is on this cut:
   *  the azimuth for the xy cut, the elevation for the yz cut (0-180, over
   *  the far side past 90; negative below the horizon). Null with no trace. */
  peakDbi: number | null;
  peakAngleDeg: number | null;
  /** Over faceted terrain, which field the trace is (issue #1373). */
  field: "with diffraction" | "specular while dragging" | null;
  /** Share of current moment below ground, percent (issue #1341). */
  belowGroundPct: number | null;
  /** NEC's rp_card pattern is drawn (the dashed cyan line). */
  necOverlay: boolean;
};

// Scalar far-field metrics from /pattern_metrics, shown in the compare table.
export type PatternMetrics = {
  peak_gain_dbi: number;
  takeoff_deg: number;
  azimuth_deg: number;
  front_to_back_db: number;
  az_beamwidth_deg: number;
  el_beamwidth_deg: number;
  /** Receiving directivity factor at the peak, dB (AK#1707): peak gain over
   * the pattern's average gain, normalised by the full sphere. Optional so a
   * pin fetched from an older server still renders ("—"). */
  rdf_db?: number;
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
