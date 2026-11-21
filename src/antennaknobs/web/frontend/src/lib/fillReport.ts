// What a momwire fill did (AK#2327): the served payload's types and the
// wording the Fill view reads it through. The server packs the payload
// (`antennaknobs/fill_report.py`); nothing here derives a number momwire did
// not report, beyond the ratios the view labels as ratios.

export type FillCounts = {
  pairs: number;
  computed: number;
  reused: number;
  near: number;
  kernel_evals: number;
};

export type FillReuse = {
  state: "served" | "partial" | "declined";
  declined: string | null;
  pairs: number | null;
  computed: number | null;
  reused: number | null;
  near: number | null;
  kernel_evals: number | null;
  /** Open-ended: a family this file has never heard of still draws. */
  families: Record<string, FillCounts>;
  /** Families this fill has but cannot count. Never read these as zero. */
  uncounted: string[];
  plan_bytes: number | null;
  census_peak_bytes: number | null;
};

export type FillSector = {
  n_sectors: number | null;
  axial: number | null;
  blocks: { size: number; count: number }[];
  computed_pairs: number | null;
  pairs: number | null;
  declined: string | null;
};

export type FillMapRow = {
  label: string;
  first: number;
  last: number;
  wires: number;
  segments: number;
  sector_first?: number;
  sector_last?: number;
  role?: "computed" | "rotation";
};

export type FillReuseMap = {
  kind: "reuse";
  rows: FillMapRow[];
  computed: number[][];
  reused: number[][];
  near: number[][];
};
export type FillSectorMap = { kind: "sector"; rows: FillMapRow[] };
export type FillMapGone = { kind: "unavailable"; reason: string };
export type FillMap = FillReuseMap | FillSectorMap | FillMapGone;

export type FillReport = {
  version: number;
  scope: "solve" | "sweep";
  source: "fresh" | "cached" | "refused";
  solved_at: number;
  solver: string | null;
  fills: number;
  frequencies: number;
  times: { fill_s: number; factor_s: number; census_s: number };
  no_fill: boolean;
  points_cached: number;
  route: string | null;
  reuse_asked: boolean;
  reuse: FillReuse | null;
  sector: FillSector | null;
  map: FillMap | null;
};

export function formatSeconds(s: number): string {
  if (!Number.isFinite(s)) return "—";
  if (s === 0) return "0 ms";
  if (s >= 10) return `${s.toFixed(1)} s`;
  if (s >= 1) return `${s.toFixed(2)} s`;
  return `${(s * 1e3).toPrecision(3)} ms`;
}

export function formatCount(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n.toLocaleString("en-US");
}

/** pairs ÷ (computed + near): how far the matrix compressed. Not time saved. */
export function compression(reuse: Pick<FillReuse, "pairs" | "computed" | "near"> | null): number | null {
  if (!reuse || reuse.pairs === null) return null;
  const paid = (reuse.computed ?? 0) + (reuse.near ?? 0);
  return paid > 0 ? reuse.pairs / paid : null;
}

/** The fill's share of fill + factor time, 0..1; null with nothing timed. */
export function fillShare(report: FillReport): number | null {
  const { fill_s, factor_s } = report.times;
  const total = fill_s + factor_s;
  return total > 0 ? fill_s / total : null;
}

const ROUTE_LABEL: Record<string, string> = {
  dense: "dense",
  sector: "sector (rotational symmetry)",
  hmatrix: "H-matrix",
  "array-block": "array block",
  cxx: "dense (C++ route)",
};

export function routeLabel(route: string | null): string {
  if (route === null) return "—";
  return ROUTE_LABEL[route] ?? route;
}

/** Which solve the numbers describe, or null for the solve on screen. */
export function provenanceNote(report: FillReport): string | null {
  if (report.source === "cached") {
    const at = new Date(report.solved_at * 1000).toLocaleTimeString();
    return `This answer came from the solve cache. The numbers describe the earlier solve at ${at} that produced it; nothing was filled just now.`;
  }
  if (report.no_fill) {
    return "The matrix for this solve was already in memory, so no fill ran. There are no times or counts to show for it.";
  }
  return null;
}

/** What a sweep's numbers cover. */
export function sweepNote(report: FillReport): string {
  const cached =
    report.points_cached > 0
      ? ` ${report.points_cached} more came from the sweep cache and ran no solver.`
      : "";
  return `Times are totals over ${report.frequencies} solved frequencies. Route and reuse describe the last fill.${cached}`;
}

/** The sentence for the reuse state: why there are, or are not, counts. */
export function reuseNote(report: FillReport): string | null {
  const reuse = report.reuse;
  if (reuse === null) {
    if (report.no_fill) return null;
    return report.reuse_asked
      ? "Fill reuse was on, but this fill read no reuse plan."
      : `Fill reuse is off for this ${report.scope === "sweep" ? "sweep" : "solve"}.`;
  }
  if (reuse.state === "declined") {
    return `Fill reuse declined: ${reuse.declined ?? "no reason given"}.`;
  }
  if (reuse.state === "partial") {
    return `Fill reuse served part of this fill. Left out: ${reuse.declined ?? "not stated"}.`;
  }
  return null;
}

/** Which saving applies: the two shorten different stages. */
export function savingNote(report: FillReport): string | null {
  if (report.route === "sector") {
    return "The sector route shortens the fill and the factor: it fills one sector's rows and factors one block per harmonic.";
  }
  if (report.reuse && report.reuse.state !== "declined") {
    return "Pair reuse shortens the fill only. The factor takes the same time with or without it.";
  }
  return null;
}

/** One map cell's counts. */
export function cellCounts(map: FillReuseMap, row: number, col: number) {
  const computed = map.computed[row][col];
  const reused = map.reused[row][col];
  const near = map.near[row][col];
  return { computed, reused, near, pairs: computed + reused + near };
}

/** A sector-map row's axis label: its wires, then the sector they are in. */
export function sectorRowLabel(row: FillMapRow): string {
  const where = sectorSpan(row);
  return row.label === where ? where : `${row.label} · ${where}`;
}

/** Whether a sector begins at this row, for the map's boundary lines. */
export function startsSector(rows: FillMapRow[], i: number): boolean {
  return i > 0 && rows[i].sector_first !== rows[i - 1].sector_first;
}

export function sectorName(sector: number | undefined): string {
  if (sector === undefined) return "—";
  return sector < 0 ? "axis" : `sector ${sector + 1}`;
}

function sectorSpan(row: FillMapRow): string {
  if (row.sector_first === row.sector_last) return sectorName(row.sector_first);
  return `sectors ${(row.sector_first ?? 0) + 1} – ${(row.sector_last ?? 0) + 1}`;
}

function percent(part: number, whole: number): string {
  return whole > 0 ? `${((part / whole) * 100).toFixed(0)}%` : "0%";
}

/** The hover and keyboard detail of one reuse-map cell. */
export function reuseCellText(map: FillReuseMap, row: number, col: number): string {
  const c = cellCounts(map, row, col);
  const pair = `${map.rows[row].label} × ${map.rows[col].label}`;
  return `${pair}: ${formatCount(c.pairs)} pairs. Computed ${formatCount(c.computed)} (${percent(c.computed, c.pairs)}), reused ${formatCount(c.reused)} (${percent(c.reused, c.pairs)}), near ${formatCount(c.near)} (${percent(c.near, c.pairs)}).`;
}

/** The hover and keyboard detail of one sector-map row. */
export function sectorRowText(row: FillMapRow): string {
  const where = sectorSpan(row);
  const size = `${formatCount(row.wires)} ${row.wires === 1 ? "wire" : "wires"}, ${formatCount(row.segments)} segments`;
  return row.role === "computed"
    ? `${row.label} (${where}, ${size}): these rows were computed.`
    : `${row.label} (${where}, ${size}): these rows follow from sector 1 by rotation.`;
}
