// The map in a real <DesignSession> (docs/design/sweep-framework-map.md,
// unit 3):
//   - picking a map shows it on the chart, waiting for Run by default
//     ([workbench.run_on_pick] map = false, decision 7), and sends nothing;
//   - Run streams /map for the served axes and the grid fills;
//   - with run_on_pick map = true, the pick alone draws it (no Run, no
//     switch flipped by the test: the past miss);
//   - dragging x or y leaves the map current; another knob dims it stale;
//   - the solver and ground are radios, and the cost line counts solves.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { HARNESS_EXAMPLE, mountReady, untilDom } from "./designSessionHarness";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";

vi.setConfig({ testTimeout: 20_000 });

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
  name: "length_factor",
  label: "length factor",
  default: 1,
  kind: "float",
  min: 0.8,
  max: 1.25,
  step: 0.005,
  precision: 3,
  unit: null,
  visible_when: null,
  ...over,
});

const EXAMPLE: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  param_schema: [
    knob({}),
    knob({ name: "angle_deg", label: "angle", default: 30, min: 0, max: 60, step: 1, precision: 0 }),
    knob({ name: "base", label: "Height", default: 7, min: 1, max: 16, step: 0.5, precision: 1 }),
  ],
};

const LF = [0.9, 0.95, 1.0, 1.05];
const ANG = [0, 30, 60];
const axis = (param: string, values: number[]) => ({
  param,
  values,
  log: false,
  lo: values[0],
  hi: values[values.length - 1],
  points: values.length,
  spacing: "lin",
});
const ANALYSES = {
  geometry: EXAMPLE.name,
  analyses: [
    {
      name: "tuning map",
      summary: "length_factor x angle_deg; views Map",
      code: 'an.Analysis("tuning map", (lf, ang), views=(an.Map(),))',
      problems: [],
      workbench: {
        runs: true,
        kind: "map",
        x: axis("length_factor", LF),
        y: axis("angle_deg", ANG),
        refs: { r: [50], x: [0], swr: null },
        views: ["Map"],
        limit: null,
        engines: null,
        grounds: null,
        note: null,
      },
    },
  ],
};

type MapBody = Record<string, unknown> & {
  x: { param: string; values: number[] };
  y: { param: string; values: number[] };
  from: number;
};

function mapRoute(bodies: MapBody[]) {
  return (_url: string, init?: RequestInit) => {
    const b = JSON.parse(String(init?.body ?? "{}")) as MapBody;
    bodies.push(b);
    const lines: string[] = [];
    b.y.values.forEach((y, j) =>
      b.x.values.forEach((x, i) =>
        lines.push(JSON.stringify({ i, j, z_re: 50 * x, z_im: y - 30, solver: "momwire" })),
      ),
    );
    lines.push(JSON.stringify({ done: true, solver: "momwire", points: lines.length }));
    const chunks = [new TextEncoder().encode(lines.join("\n") + "\n")];
    return {
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: async () =>
            chunks.length > 0 ? { done: false, value: chunks.shift() } : { done: true, value: undefined },
        }),
      },
    } as unknown as Response;
  };
}

afterEach(() => vi.unstubAllGlobals());

async function open(opts: { runOnPickMap: boolean }) {
  const bodies: MapBody[] = [];
  const r = await mountReady({
    examples: [EXAMPLE],
    pinned: ["antenna", "zparam"],
    ...(opts.runOnPickMap ? { uiDefaults: { workbench: { run_on_pick: { map: true } } } } : {}),
    routes: {
      "/map": mapRoute(bodies),
      "/analyses": () => ({ ok: true, status: 200, json: async () => ANALYSES }) as unknown as Response,
    },
  });
  fireEvent.click(r.container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
  const select = await untilDom(
    () => screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null,
  );
  const map = () =>
    [...r.container.querySelectorAll("canvas.map")].find((c) => !c.closest(".thumbstrip")) as
      | HTMLElement
      | undefined;
  return { ...r, bodies, select, map };
}

describe("the map chart", () => {
  it("a pick shows it waiting for Run; Run fills the served grid", async () => {
    const { bodies, select, map } = await open({ runOnPickMap: false });
    fireEvent.change(select, { target: { value: "tuning map" } });
    const head = await untilDom(() => {
      const h = screen.queryByRole("group", { name: "Analysis chart" });
      return h?.dataset.chartKind === "map" ? h : null;
    });
    expect(head.dataset.dwell).toBe("0");
    await untilDom(() => map());
    expect(map()!.dataset.nodes).toBe("0");
    expect(map()!.dataset.total).toBe("12");
    expect(bodies).toHaveLength(0);
    // The cost line counts the grid's solves.
    expect(screen.getByLabelText("Map cost").textContent).toMatch(/^12 solves/);
    fireEvent.click(screen.getByRole("button", { name: "run" }));
    await untilDom(() => map()?.dataset.nodes === "12");
    expect(bodies).toHaveLength(1);
    expect(bodies[0].x).toEqual({ param: "length_factor", values: LF });
    expect(bodies[0].y).toEqual({ param: "angle_deg", values: ANG });
    expect(bodies[0].from).toBe(0);
    expect(bodies[0]._gen).toBeUndefined();
    expect(map()!.dataset.contours).toBe("X = 0 Ω|R = 50 Ω");
  });

  it("with run_on_pick map on, the pick alone draws it", async () => {
    const { bodies, select, map } = await open({ runOnPickMap: true });
    fireEvent.change(select, { target: { value: "tuning map" } });
    await untilDom(() => map()?.dataset.nodes === "12");
    expect(bodies).toHaveLength(1);
  });

  it("an x or y drag leaves it current; another knob dims it stale", async () => {
    const { bodies, select, map } = await open({ runOnPickMap: true });
    fireEvent.change(select, { target: { value: "tuning map" } });
    await untilDom(() => map()?.dataset.nodes === "12");
    const nudge = (label: string) =>
      fireEvent.keyDown(screen.getByRole("slider", { name: label }), { key: "ArrowUp" });
    const live0 = map()!.dataset.live;
    expect(live0).toBe("1,30");
    nudge("angle");
    nudge("length factor");
    // The marker moved with both knobs: the drags landed.
    await untilDom(() => map()?.dataset.live !== live0 && !map()!.dataset.live!.startsWith("1,"));
    await new Promise((r) => setTimeout(r, 700));
    expect(map()!.dataset.stale).toBe("0");
    expect(bodies).toHaveLength(1);
    nudge("Height");
    await untilDom(() => map()?.dataset.stale === "1");
    expect(bodies).toHaveLength(1);
    expect(screen.getByRole("button", { name: "run · re-run?" })).toBeTruthy();
  });

  it("one solver slot and one ground slot, as radios; a pick keeps one of each", async () => {
    const { select, bodies, map } = await open({ runOnPickMap: false });
    fireEvent.change(select, { target: { value: "tuning map" } });
    const solver = await untilDom(() => screen.queryByRole("radiogroup", { name: "solver" }));
    const radios = [...solver.querySelectorAll("input[type=radio]")] as HTMLInputElement[];
    expect(radios.length).toBeGreaterThanOrEqual(2);
    expect(radios.filter((r) => r.checked)).toHaveLength(1);
    // Another slot: the map is of that slot's engine, one grid.
    const other = radios.find((r) => !r.checked)!;
    fireEvent.click(other);
    await untilDom(() => (other.checked ? true : null));
    expect(radios.filter((r) => r.checked)).toEqual([other]);
    fireEvent.click(screen.getByRole("button", { name: "run" }));
    await untilDom(() => map()?.dataset.nodes === "12");
    expect(bodies).toHaveLength(1);
  });
});
