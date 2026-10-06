// The workbench's two-knob map (docs/design/sweep-framework-map.md): the
// grid's colours, contours and best node, as `antennaknobs analyze` draws
// them (`analysis_run._map_figure`, `map_contours`, `best_cell_line`), so the
// two tools show one picture. Pure and React-free: MapChart draws from it and
// the tests check it against the CLI's own grid and contourpy's vertices.

/** A map's grid as it lands: node (i, j) is x = xs[i], y = ys[j], and its Z
 *  is `re[j][i]` + j`im[j][i]`, null until that node has solved (or where it
 *  failed). Rows are y, as the CLI's Z is (len(ys), len(xs)). */
export type MapGrid = {
  xs: readonly number[];
  ys: readonly number[];
  re: readonly (readonly (number | null)[])[];
  im: readonly (readonly (number | null)[])[];
};

/** An empty grid over `xs` × `ys`: every node unsolved. */
export function emptyGrid(xs: readonly number[], ys: readonly number[]): MapGrid {
  const row = () => xs.map(() => null as number | null);
  return { xs, ys, re: ys.map(row), im: ys.map(row) };
}

/** The map's reference lines as /analyses serves them (`Ref`): R = each r,
 *  X = each x (ohms), and the SWR threshold. */
export type MapRefs = { r: readonly number[]; x: readonly number[]; swr: number | null };

/** What the map is coloured by: |Γ| on z0 (the CLI's, and the Swr view's ρ
 *  scale), or 1 − 1/SWR (the Swr view's reciprocal scale). Both run 0..1. */
export type MapQuantity = "rho" | "reciprocal";

/** viridis_r as the CLI draws it (matplotlib's, 17 stops at t = k/16,
 *  linear between them): perceptually uniform, colour-blind safe, and the
 *  same in both themes. t = 0 (a match) is yellow, t = 1 dark violet. */
export const VIRIDIS_R: readonly (readonly [number, number, number])[] = [
  [253, 231, 37],
  [213, 226, 26],
  [170, 220, 50],
  [129, 211, 77],
  [92, 200, 99],
  [61, 188, 116],
  [39, 173, 129],
  [31, 159, 136],
  [33, 144, 141],
  [38, 129, 142],
  [44, 113, 142],
  [51, 98, 141],
  [59, 81, 139],
  [66, 63, 133],
  [71, 44, 122],
  [72, 23, 105],
  [68, 1, 84],
];

/** viridis_r at t (clamped to 0..1) as [r, g, b]. */
export function viridisR(t: number): [number, number, number] {
  const n = VIRIDIS_R.length - 1;
  const u = Math.min(1, Math.max(0, Number.isFinite(t) ? t : 1)) * n;
  const k = Math.min(n - 1, Math.floor(u));
  const f = u - k;
  const a = VIRIDIS_R[k];
  const b = VIRIDIS_R[k + 1];
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ];
}

export const viridisCss = (t: number): string => {
  const [r, g, b] = viridisR(t);
  return `rgb(${r},${g},${b})`;
};

/** |Γ| = |(Z − z0)/(Z + z0)|, the CLI's `np.abs((z - z0) / (z + z0))`. */
export function gammaOf(re: number, im: number, z0: number): number {
  const nr = re - z0;
  const dr = re + z0;
  // (a + jb)/(c + jd): |.| = |a + jb| / |c + jd|.
  return Math.hypot(nr, im) / Math.hypot(dr, im);
}

/** SWR at |Γ| g: (1 + g)/(1 − g), ∞ at g ≥ 1. */
export const swrOf = (g: number): number => (g < 1 ? (1 + g) / (1 - g) : Infinity);

/** |Γ| at SWR s, (s − 1)/(s + 1): the level a map contours `Ref.swr` at
 *  (`analysis_run.swr_gamma`). */
export const swrGamma = (s: number): number => (s - 1) / (s + 1);

/** A node's colour value on `q`'s 0..1 scale: |Γ| itself, or 1 − 1/SWR =
 *  2|Γ|/(1 + |Γ|). */
export function colourValue(g: number, q: MapQuantity): number {
  return q === "rho" ? g : (2 * g) / (1 + g);
}

/** The colour bar's title for `q`. */
export function quantityLabel(q: MapQuantity, z0: number): string {
  return q === "rho" ? `|Γ| on ${formatG(z0, 6)} Ω` : `1 − 1/SWR on ${formatG(z0, 6)} Ω`;
}

export type ContourQuantity = "X" | "R" | "SWR";

/** The map's contours, `analysis_run.map_contours`'s rule: X = each x and
 *  R = each r; with no R or X line, X = 0 and R = z0 (resonance and the
 *  match); and the SWR threshold, when there is one. */
export function mapContourLevels(
  refs: MapRefs,
  z0: number,
): { quantity: ContourQuantity; level: number }[] {
  const out: { quantity: ContourQuantity; level: number }[] =
    refs.r.length === 0 && refs.x.length === 0
      ? [
          { quantity: "X", level: 0 },
          { quantity: "R", level: z0 },
        ]
      : [
          ...refs.x.map((level) => ({ quantity: "X" as const, level })),
          ...refs.r.map((level) => ({ quantity: "R" as const, level })),
        ];
  if (refs.swr !== null) out.push({ quantity: "SWR", level: refs.swr });
  return out;
}

/** The grid a contour of `quantity` is traced on (`map_contour_field`):
 *  X and R in ohms, SWR as |Γ| on z0. Null where the node has not solved. */
export function contourField(
  grid: MapGrid,
  quantity: ContourQuantity,
  z0: number,
): (number | null)[][] {
  return grid.re.map((row, j) =>
    row.map((re, i) => {
      const im = grid.im[j][i];
      if (re === null || im === null) return null;
      if (quantity === "X") return im;
      if (quantity === "R") return re;
      return gammaOf(re, im, z0);
    }),
  );
}

/** Whether the grid crosses `level`: strictly between its finite least and
 *  greatest values (`map_contour_reached`). One it does not is named
 *  "(not reached)" in the legend, never dropped. */
export function contourReached(field: readonly (readonly (number | null)[])[], level: number): boolean {
  let lo = Infinity;
  let hi = -Infinity;
  for (const row of field) {
    for (const v of row) {
      if (v === null || !Number.isFinite(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  return lo < level && level < hi;
}

/** One straight piece of a contour, in data coordinates: [x1, y1, x2, y2]. */
export type Segment = [number, number, number, number];

/** The contour of `field` at `level` over the grid's nodes, by marching
 *  squares with linear interpolation along each cell edge: the vertices are
 *  where contourpy (matplotlib's contour) puts them. A node counts as above
 *  the level when its value is greater than it, as contourpy's does. A cell
 *  with an unsolved corner draws nothing, so a partial grid draws the
 *  contours of what has landed. A saddle (all four edges crossed) is split
 *  by the cell's mean. Each edge's crossing is computed one way only (lower
 *  node first), so neighbouring cells meet exactly. */
export function contourSegments(
  xs: readonly number[],
  ys: readonly number[],
  field: readonly (readonly (number | null)[])[],
  level: number,
): Segment[] {
  const out: Segment[] = [];
  const crossX = (j: number, i: number): [number, number] | null => {
    // The edge (i, j)–(i+1, j).
    const a = field[j][i];
    const b = field[j][i + 1];
    if (a === null || b === null || a > level === b > level) return null;
    const f = (level - a) / (b - a);
    return [xs[i] + f * (xs[i + 1] - xs[i]), ys[j]];
  };
  const crossY = (j: number, i: number): [number, number] | null => {
    // The edge (i, j)–(i, j+1).
    const a = field[j][i];
    const b = field[j + 1][i];
    if (a === null || b === null || a > level === b > level) return null;
    const f = (level - a) / (b - a);
    return [xs[i], ys[j] + f * (ys[j + 1] - ys[j])];
  };
  for (let j = 0; j + 1 < ys.length; j++) {
    for (let i = 0; i + 1 < xs.length; i++) {
      const c = [field[j][i], field[j][i + 1], field[j + 1][i + 1], field[j + 1][i]];
      if (c.some((v) => v === null || !Number.isFinite(v))) continue;
      // Edges in order round the cell: bottom, right, top, left.
      const pts = [crossX(j, i), crossY(j, i + 1), crossX(j + 1, i), crossY(j, i)];
      const hit = pts.filter((p): p is [number, number] => p !== null);
      if (hit.length === 2) {
        out.push([hit[0][0], hit[0][1], hit[1][0], hit[1][1]]);
      } else if (hit.length === 4) {
        const [bot, right, top, left] = pts as [number, number][];
        const mean = ((c[0] as number) + (c[1] as number) + (c[2] as number) + (c[3] as number)) / 4;
        // Corner 0 (bottom-left) above the level with the mean above: the
        // above region joins diagonally through the middle, so the lines
        // cut off the two below corners (bottom-right, top-left).
        const joined = (c[0] as number) > level === mean > level;
        if (joined) {
          out.push([bot[0], bot[1], right[0], right[1]]);
          out.push([top[0], top[1], left[0], left[1]]);
        } else {
          out.push([bot[0], bot[1], left[0], left[1]]);
          out.push([top[0], top[1], right[0], right[1]]);
        }
      }
    }
  }
  return out;
}

/** A contour as the chart draws and names it. */
export type MapContour = {
  quantity: ContourQuantity;
  /** The level as the legend says it: ohms, or the SWR. */
  level: number;
  /** The level on its field (`contourField`): ohms, or |Γ|. */
  at: number;
  label: string;
  reached: boolean;
  segments: Segment[];
};

/** Every contour of `refs` on the grid as landed so far. */
export function mapContours(grid: MapGrid, refs: MapRefs, z0: number): MapContour[] {
  return mapContourLevels(refs, z0).map(({ quantity, level }) => {
    const field = contourField(grid, quantity, z0);
    const at = quantity === "SWR" ? swrGamma(level) : level;
    const reached = contourReached(field, at);
    const base =
      quantity === "SWR"
        ? `SWR = ${formatG(level, 6)} (|Γ| = ${formatG(at, 3)})`
        : `${quantity} = ${formatG(level, 6)} Ω`;
    return {
      quantity,
      level,
      at,
      label: reached ? base : `${base} (not reached)`,
      reached,
      segments: reached ? contourSegments(grid.xs, grid.ys, field, at) : [],
    };
  });
}

/** The grid's least-|Γ| node so far (`best_cell_line`'s rule: the best
 *  node, not an optimum between nodes; the first in row order on a tie, as
 *  numpy's nanargmin), or null before any has landed. */
export type BestNode = { i: number; j: number; gamma: number; swr: number; re: number; im: number };

export function bestNode(grid: MapGrid, z0: number): BestNode | null {
  let best: BestNode | null = null;
  grid.re.forEach((row, j) =>
    row.forEach((re, i) => {
      const im = grid.im[j][i];
      if (re === null || im === null) return;
      const g = gammaOf(re, im, z0);
      if (Number.isNaN(g)) return;
      if (best === null || g < best.gamma) best = { i, j, gamma: g, swr: swrOf(g), re, im };
    }),
  );
  return best;
}

/** The legend's line for the best node, worded as `best_cell_line` prints
 *  it: "least |Γ| 0.0235 (SWR 1.05) at length_factor 0.975, angle_deg 30:
 *  Z 50.96 -2.17j". */
export function bestNodeLine(
  b: BestNode,
  grid: MapGrid,
  kx: string,
  ky: string,
): string {
  const swr = Number.isFinite(b.swr) ? formatG(b.swr, 3) : "inf";
  const im = `${b.im < 0 || Object.is(b.im, -0) ? "-" : "+"}${Math.abs(b.im).toFixed(2)}`;
  return (
    `least |Γ| ${formatG(b.gamma, 3)} (SWR ${swr}) at ${kx} ${formatG(grid.xs[b.i], 6)}, ` +
    `${ky} ${formatG(grid.ys[b.j], 6)}: Z ${b.re.toFixed(2)} ${im}j`
  );
}

/** Python's `format(x, ".{p}g")`: p significant digits, trailing zeros
 *  dropped, exponent form below 1e-4 or at 10^p and above. */
export function formatG(x: number, p: number): string {
  if (!Number.isFinite(x)) return Number.isNaN(x) ? "nan" : x > 0 ? "inf" : "-inf";
  if (x === 0) return Object.is(x, -0) ? "-0" : "0";
  const [mant, expStr] = x.toExponential(p - 1).split("e");
  const e = Number(expStr);
  const strip = (s: string) => (s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s);
  if (e < -4 || e >= p) {
    const sign = e < 0 ? "-" : "+";
    return `${strip(mant)}e${sign}${String(Math.abs(e)).padStart(2, "0")}`;
  }
  return strip(x.toFixed(Math.max(0, p - 1 - e)));
}

/** The node nearest a point in data coordinates, by the cell (the CLI's
 *  "nearest" shading: a node's cell runs to the midpoints of its
 *  neighbours), or null off the grid. */
export function nodeAt(
  xs: readonly number[],
  ys: readonly number[],
  x: number,
  y: number,
): { i: number; j: number } | null {
  const near = (v: readonly number[], t: number): number => {
    const e = cellEdges(v);
    const lo = Math.min(e[0], e[e.length - 1]);
    const hi = Math.max(e[0], e[e.length - 1]);
    if (!(t >= lo && t <= hi)) return -1;
    let best = 0;
    for (let k = 1; k < v.length; k++) if (Math.abs(v[k] - t) < Math.abs(v[best] - t)) best = k;
    return best;
  };
  const i = near(xs, x);
  const j = near(ys, y);
  return i < 0 || j < 0 ? null : { i, j };
}

/** The cell edges of nodes `v` (matplotlib's "nearest" shading): midpoints
 *  between neighbours, and half a neighbour gap past each end. One node
 *  gets ±0.5. */
export function cellEdges(v: readonly number[]): number[] {
  if (v.length === 0) return [];
  if (v.length === 1) return [v[0] - 0.5, v[0] + 0.5];
  const mids = v.slice(1).map((b, k) => (v[k] + b) / 2);
  return [v[0] - (v[1] - v[0]) / 2, ...mids, v[v.length - 1] + (v[v.length - 1] - v[v.length - 2]) / 2];
}

/** How many nodes of the grid have landed. */
export function landed(grid: MapGrid): number {
  let n = 0;
  for (const row of grid.re) for (const v of row) if (v !== null) n++;
  return n;
}
