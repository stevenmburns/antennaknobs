// The Z-vs-parameter view's analysis picker through a real <DesignSession>
// (AK#1757, sweep-framework step 3):
//   - the view on screen asks /analyses for the design's analyses, on the
//     slot's own request;
//   - picking "height" sends /param_sweep for base, 2…20 in 37 points (the
//     values `antennaknobs analyze` sweeps), and the chart draws 37 points,
//     with the analysis's note under the header;
//   - an analysis the view cannot draw is listed disabled with its reason,
//     and choosing it sends nothing;
//   - every analysis shows its Python, with a Copy button.
import { describe, it, expect, afterEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { HARNESS_EXAMPLE, mountReady, untilDom } from "./designSessionHarness";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";

vi.setConfig({ testTimeout: 15_000 });

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
  name: "base",
  label: "Height",
  default: 7,
  kind: "float",
  min: 1,
  max: 16,
  step: 0.5,
  precision: 1,
  unit: "m",
  visible_when: null,
  ...over,
});

const EXAMPLE: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  param_schema: [knob({})],
};

const E3_VALUES = Array.from({ length: 37 }, (_, i) => 2 + 0.5 * i);
const GROUNDS_NOTE =
  "crossed over grounds: the workbench draws this session's ground; `antennaknobs analyze` draws all 3";
const HOLD_WHY = "hold (optimise at each point): not in the workbench yet (sweep-framework step 6)";

// The invvee's entries as POST /analyses serves them (trimmed to three).
const ANALYSES = {
  geometry: EXAMPLE.name,
  analyses: [
    {
      name: "convergence",
      summary: "density (nominal_nsegs); 3 curves (3 engines); views Rx, Table, Smith",
      code: 'an.convergence(\n    cross=an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec5")),\n)',
      problems: [],
      workbench: {
        runs: true,
        param: "n_per_wire",
        values: [8, 12, 17, 24, 34, 48, 68],
        log: true,
        note: "crossed over engines: the workbench draws this session's engine",
      },
    },
    {
      name: "height",
      summary: "height (base) 2..20, 37 points; 3 curves (3 grounds); views Rx",
      code: 'an.Analysis(\n    "height",\n    an.Sweep(an.HEIGHT, 2, 20, points=37),\n)',
      problems: [],
      workbench: { runs: true, param: "base", values: E3_VALUES, log: false, note: GROUNDS_NOTE },
    },
    {
      name: "match vs height",
      summary: "height (base) 2..20, 37 points; 1 curve; hold match_z0",
      code: 'an.Analysis(\n    "match vs height",\n)',
      problems: [],
      workbench: { runs: false, why: HOLD_WHY },
    },
  ],
};

type Body = Record<string, unknown> & { param: string; values: number[] };

function paramSweepRoute(bodies: Body[]) {
  return (_url: string, init?: RequestInit) => {
    const b = JSON.parse(String(init?.body ?? "{}")) as Body;
    bodies.push(b);
    const lines = b.values.map((v) =>
      JSON.stringify({ param: b.param, value: v, z_re: 60 + v, z_im: -30 + v, solver: "momwire" }),
    );
    lines.push(JSON.stringify({ done: true, solver: "momwire" }));
    const chunks = [new TextEncoder().encode(lines.join("\n") + "\n")];
    return {
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: async () =>
            chunks.length > 0
              ? { done: false, value: chunks.shift() }
              : { done: true, value: undefined },
        }),
      },
    } as unknown as Response;
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the analysis picker", () => {
  it("picking height sweeps base 2…20 in 37 points; a hold sends nothing", async () => {
    const bodies: Body[] = [];
    const asked: Record<string, unknown>[] = [];
    const { container } = await mountReady({
      // A pick starts its analysis, as before [workbench.run_on_pick] (AC6LA #179).
      pickRuns: true,
      examples: [EXAMPLE],
      pinned: ["antenna", "zparam"],
      routes: {
        "/param_sweep": paramSweepRoute(bodies),
        "/analyses": (_url: string, init?: RequestInit) => {
          asked.push(JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>);
          return { ok: true, status: 200, json: async () => ANALYSES } as unknown as Response;
        },
      },
    });
    const chart = () =>
      [...container.querySelectorAll("canvas.zparam")].find(
        (c) => !c.closest(".thumbstrip"),
      ) as HTMLElement | undefined;
    // The chart's thumb: the Smith chart a new chart opens on (unit 3).
    fireEvent.click(container.querySelector(".thumbstrip canvas.smith") as HTMLElement);
    const select = await untilDom(
      () => screen.queryByRole("combobox", { name: "Analysis" }) as HTMLSelectElement | null,
    );
    // Asked once, on the slot's own request.
    expect(asked).toHaveLength(1);
    expect(asked[0].geometry).toBe(EXAMPLE.name);
    // The chart opens on the design's own frequency sweep, so nothing has
    // gone to /param_sweep yet.
    const before = bodies.length;
    expect(before).toBe(0);
    const head = () => screen.getByRole("group", { name: "Analysis chart" });

    // The hold is listed, disabled, with its reason as the tooltip.
    const hold = [...select.options].find((o) => o.value === "match vs height")!;
    expect(hold.disabled).toBe(true);
    expect(hold.title).toBe(HOLD_WHY);
    fireEvent.change(select, { target: { value: "match vs height" } });
    expect(head().dataset.chartKind).toBe("frequency");
    expect(chart()).toBeUndefined();
    expect(bodies.length).toBe(before);

    // Height: base, 2…20, 37 points, as `antennaknobs analyze` sweeps it.
    fireEvent.change(select, { target: { value: "height" } });
    await untilDom(() => bodies.length > before);
    const sent = bodies.slice(before);
    expect(sent).toHaveLength(1);
    expect(sent[0].param).toBe("base");
    expect(sent[0].values).toEqual(E3_VALUES);
    await untilDom(() => chart()?.dataset.points === "37" && chart()?.dataset.param === "base");
    expect(select.value).toBe("height");
    expect((screen.getByRole("combobox", { name: "Parameter" }) as HTMLSelectElement).value).toBe(
      "base",
    );
    expect(screen.getByText(GROUNDS_NOTE)).toBeTruthy();

    // Every analysis as Python, read-only, with Copy.
    expect(screen.getByLabelText("height as Python").textContent).toContain(
      "an.Sweep(an.HEIGHT, 2, 20, points=37)",
    );
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    fireEvent.click(screen.getByRole("button", { name: "Copy height as Python" }));
    expect(writeText).toHaveBeenCalledWith(ANALYSES.analyses[1].code);
    // Nothing else was sent along the way.
    expect(bodies.length).toBe(before + 1);
  });
});
