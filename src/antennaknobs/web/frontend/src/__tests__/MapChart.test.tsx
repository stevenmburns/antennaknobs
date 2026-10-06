// The map chart (components/charts/MapChart.tsx), drawn from the CLI's own
// grid of dipoles.invvee's tuning map (fixtures/invveeTuningMap.json, written
// by scripts/map_chart_fixture.py), read through its data-* attributes and
// DOM (jsdom has no 2-D context).
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import fixture from "./fixtures/invveeTuningMap.json";
import { MAP_MARGIN, MapChart, type MapLive } from "../components/charts/MapChart";
import { cellEdges, emptyGrid, type MapGrid, type MapQuantity, type MapRefs } from "../lib/mapGrid";

HTMLCanvasElement.prototype.getContext =
  (() => null) as unknown as HTMLCanvasElement["getContext"];

const FX = fixture as unknown as {
  x: { param: string; values: number[] };
  y: { param: string; values: number[] };
  re: number[][];
  im: number[][];
  best: { i: number; j: number; line: string };
};
const GRID: MapGrid = { xs: FX.x.values, ys: FX.y.values, re: FX.re, im: FX.im };
// The design's own Ref (no threshold): X = 0, R = 50, R = 75.
const REFS: MapRefs = { r: [50, 75], x: [0], swr: null };
const SIZE = 400;

function mount(p: {
  grid?: MapGrid;
  refs?: MapRefs;
  live?: MapLive | null;
  quantity?: MapQuantity;
  z0?: number;
  stale?: boolean;
  status?: string | null;
}) {
  const r = render(
    <MapChart
      grid={p.grid ?? GRID}
      xLabel="length_factor"
      yLabel="angle_deg"
      z0={p.z0 ?? 50}
      refs={p.refs ?? REFS}
      quantity={p.quantity ?? "rho"}
      live={p.live ?? null}
      size={SIZE}
      stale={p.stale ?? false}
      status={p.status ?? null}
    />,
  );
  const canvas = r.container.querySelector("canvas.map") as HTMLElement;
  return { ...r, canvas };
}

describe("the map from the CLI's grid", () => {
  it("every node, the three contours and the best node, as the CLI names them", () => {
    const { canvas } = mount({});
    expect(canvas.dataset.nodes).toBe("825");
    expect(canvas.dataset.total).toBe("825");
    expect(canvas.dataset.contours).toBe("X = 0 Ω|R = 50 Ω|R = 75 Ω");
    expect(canvas.dataset.best).toBe(`${FX.best.i},${FX.best.j}`);
    const items = within(screen.getByRole("list", { name: "Map legend" }))
      .getAllByRole("listitem")
      .map((li) => li.textContent?.trim());
    expect(items).toEqual(["X = 0 Ω", "R = 50 Ω", "R = 75 Ω", FX.best.line]);
  });

  it("Ref.swr draws as a |Γ| contour, and an unreached level is named, not dropped", () => {
    const { canvas } = mount({ refs: { r: [50, 5000], x: [0], swr: 2 } });
    expect(canvas.dataset.contours).toBe(
      "X = 0 Ω|R = 50 Ω|R = 5000 Ω (not reached)|SWR = 2 (|Γ| = 0.333)",
    );
    const segs = canvas.dataset.segments!.split(",").map(Number);
    expect(segs[2]).toBe(0);
    expect(segs[3]).toBeGreaterThan(0);
  });

  it("z0 re-colours, and with no Ref the contours are resonance and the match", () => {
    const { canvas } = mount({ refs: { r: [], x: [], swr: null }, z0: 75 });
    expect(canvas.dataset.z0).toBe("75");
    expect(canvas.dataset.contours).toBe("X = 0 Ω|R = 75 Ω");
  });

  it("the quantity: |Γ| by default, 1 − 1/SWR as the alternative", () => {
    expect(mount({}).canvas.dataset.quantity).toBe("rho");
    expect(mount({ quantity: "reciprocal" }).canvas.dataset.quantity).toBe("reciprocal");
  });
});

describe("a partial map", () => {
  it("counts what landed and names the best node so far", () => {
    const g = emptyGrid(GRID.xs, GRID.ys) as { xs: number[]; ys: number[]; re: (number | null)[][]; im: (number | null)[][] };
    g.re[0] = FX.re[0].slice();
    g.im[0] = FX.im[0].slice();
    const { canvas } = mount({ grid: g, status: "solving 33/825…" });
    expect(canvas.dataset.nodes).toBe("33");
    expect(canvas.dataset.status).toBe("solving 33/825…");
    expect(screen.getByText(/least \|Γ\| .* \(33\/825 nodes\)$/)).toBeTruthy();
  });

  it("before any node: says so", () => {
    mount({ grid: emptyGrid(GRID.xs, GRID.ys) });
    expect(screen.getByText("no node solved yet (0/825 nodes)")).toBeTruthy();
  });
});

describe("the live marker", () => {
  it("on the grid: a ring filled with the live solve's |Γ|", () => {
    const { canvas } = mount({ live: { x: 0.975, y: 30, re: 50, im: 0 } });
    expect(canvas.dataset.marker).toBe("in");
    expect(canvas.dataset.markerFill).toBe("0.0000");
  });
  it("off the grid: an arrow on the edge it is off", () => {
    expect(mount({ live: { x: 1.2, y: 30, re: null, im: null } }).canvas.dataset.marker).toBe("right");
    expect(mount({ live: { x: 1.0, y: -5, re: null, im: null } }).canvas.dataset.marker).toBe("below");
  });
});

describe("the hover readout", () => {
  it("reads the nearest node, with no interpolation", () => {
    const { canvas } = mount({});
    // The plot's centre, in canvas px.
    const pw = SIZE - MAP_MARGIN.l - MAP_MARGIN.r;
    const ph = SIZE - MAP_MARGIN.t - MAP_MARGIN.b;
    canvas.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: SIZE, height: SIZE }) as DOMRect;
    // jsdom has no PointerEvent: a MouseEvent of the pointer type carries
    // the coordinates React reads.
    fireEvent(
      canvas,
      new MouseEvent("pointermove", {
        clientX: MAP_MARGIN.l + pw / 2,
        clientY: MAP_MARGIN.t + ph / 2,
        bubbles: true,
      }),
    );
    const xe = cellEdges(GRID.xs);
    const ye = cellEdges(GRID.ys);
    const cx = (xe[0] + xe[xe.length - 1]) / 2;
    const cy = (ye[0] + ye[ye.length - 1]) / 2;
    const i = GRID.xs.reduce((b, v, k) => (Math.abs(v - cx) < Math.abs(GRID.xs[b] - cx) ? k : b), 0);
    const j = GRID.ys.reduce((b, v, k) => (Math.abs(v - cy) < Math.abs(GRID.ys[b] - cy) ? k : b), 0);
    expect(canvas.dataset.hover).toBe(`${i},${j}`);
    const text = screen.getByRole("status", { name: "Map node" }).textContent!;
    expect(text).toContain(`angle_deg ${GRID.ys[j]}: R `);
    expect(text).toMatch(/SWR \d+\.\d\d, \|Γ\| 0\.\d{3}$/);
    fireEvent.pointerLeave(canvas);
    expect(canvas.dataset.hover).toBe("");
  });
});
