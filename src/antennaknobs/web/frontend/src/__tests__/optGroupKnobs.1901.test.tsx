// AK#1901: a knob inside a group (the fan dipole's per-band length_factor)
// can be marked "Optimize this knob". Its optimiser key is its dotted path,
// `bands.0.length_factor` — the spelling /optimize reads — and the result
// lands back at ["bands", 0, "length_factor"]. A flat knob keeps its plain
// name everywhere.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { ParamForm } from "../components/params/ParamForm";
import { useOptimizer } from "../components/session/useOptimizer";
import type { OptimizeResult } from "../components/session/VfoPanel";
import {
  defaultKnobOpt,
  findKnobSpec,
  knobKey,
  knobPath,
  type KnobOpt,
  type ParamValueBag,
  type SchemaItem,
  type SchemaParamSpec,
} from "../lib/params";
import type { SolveRequest } from "../lib/api";

function leaf(o: Partial<SchemaParamSpec>): SchemaParamSpec {
  return {
    name: "p",
    label: "P",
    default: 0,
    kind: "float",
    min: 0,
    max: 10,
    step: 0.1,
    precision: 2,
    unit: null,
    visible_when: null,
    ...o,
  };
}

// The fan dipole's shape: a flat knob, a count, and a `bands` group.
const SCHEMA: SchemaItem[] = [
  leaf({ name: "sy_w5hgt", label: "W5 height", min: 8, max: 16 }),
  leaf({ name: "n_bands", label: "Bands", kind: "int", min: 1, max: 5, step: 1 }),
  {
    kind: "group",
    name: "bands",
    label_template: "band {i}",
    repeat_count: "n_bands",
    max_repeats: 5,
    default_overrides: [{}, {}],
    params: [
      leaf({ name: "freq", label: "Freq", min: 13.5, max: 30.2, step: 0.001 }),
      leaf({ name: "length_factor", label: "Length factor", min: 0.4, max: 0.55, step: 0.0001 }),
    ],
  },
];

const VALUES: ParamValueBag = {
  sy_w5hgt: 12,
  n_bands: 2,
  bands: [
    { freq: 18.1575, length_factor: 0.4994 },
    { freq: 21.383, length_factor: 0.4984 },
  ],
};

describe("dotted knob keys", () => {
  it("knobKey / knobPath round-trip, and a flat name stays flat", () => {
    expect(knobKey(["bands", 0, "length_factor"])).toBe("bands.0.length_factor");
    expect(knobPath("bands.0.length_factor")).toEqual(["bands", 0, "length_factor"]);
    expect(knobKey(["sy_w5hgt"])).toBe("sy_w5hgt");
    expect(knobPath("sy_w5hgt")).toEqual(["sy_w5hgt"]);
  });

  it("defaultKnobOpt resolves a group leaf's spec through the group", () => {
    expect(findKnobSpec(SCHEMA, "bands.1.length_factor")?.label).toBe("Length factor");
    expect(defaultKnobOpt(SCHEMA, "bands.1.length_factor")).toMatchObject({
      vary: false,
      optMin: 0.4,
      optMax: 0.55,
      step: 0.0001,
    });
    expect(defaultKnobOpt(SCHEMA, "sy_w5hgt")).toMatchObject({ optMin: 8, optMax: 16 });
    // A group itself, or a name that is not there, is no knob.
    expect(findKnobSpec(SCHEMA, "bands")).toBeUndefined();
    expect(findKnobSpec(SCHEMA, "bands.0.nope")).toBeUndefined();
  });
});

describe("marking a knob inside a group", () => {
  it("right-click and 'o' name the nested knob by its dotted key; the flat one by its name", () => {
    const opt = { settings: {}, onContext: vi.fn(), onToggleVary: vi.fn() };
    render(<ParamForm schema={SCHEMA} values={VALUES} onChange={vi.fn()} opt={opt} />);
    const lfs = screen.getAllByRole("slider", { name: "Length factor" });
    expect(lfs).toHaveLength(2);
    fireEvent.contextMenu(lfs[1]);
    expect(opt.onContext.mock.calls[0][0]).toBe("bands.1.length_factor");
    fireEvent.keyDown(lfs[0], { key: "o" });
    expect(opt.onToggleVary).toHaveBeenCalledWith("bands.0.length_factor");
    fireEvent.contextMenu(screen.getByRole("slider", { name: "W5 height" }));
    expect(opt.onContext.mock.calls[1][0]).toBe("sy_w5hgt");
  });

  it("a nested knob reads its settings under its dotted key, and only its own instance", () => {
    const ko: KnobOpt = { vary: true, optMin: 0.45, optMax: 0.52, dispMin: 0.45, dispMax: 0.52, step: 0.001 };
    const opt = { settings: { "bands.0.length_factor": ko }, onContext: vi.fn(), onToggleVary: vi.fn() };
    render(<ParamForm schema={SCHEMA} values={VALUES} onChange={vi.fn()} opt={opt} />);
    const [lf0, lf1] = screen.getAllByRole("slider", { name: "Length factor" });
    expect(lf0.getAttribute("aria-valuemin")).toBe("0.45");
    expect(lf1.getAttribute("aria-valuemin")).toBe("0.4");
  });
});

// ------------------------------------------------- the run, end to end

function jsonResponse(body: unknown): Response {
  return { headers: { get: () => "application/json" }, json: async () => body } as unknown as Response;
}

const METRICS = { z_in_re: 50, z_in_im: 0, z0_ohms: 50, swr: 1.2 };
const RESULT: OptimizeResult = {
  objective: "bands",
  params: { "bands.0.length_factor": 0.4878, "bands.1.length_factor": 0.4941, sy_w5hgt: 12.5 },
  objective_before: 1.9,
  objective_after: 1.2,
  metrics_before: METRICS,
  metrics_after: METRICS,
  n_evals: 60,
  improved: true,
};

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  vi.useFakeTimers();
  fetchMock = vi.fn(async () => jsonResponse(RESULT));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function settle() {
  await act(async () => {
    vi.advanceTimersByTime(400);
    await Promise.resolve();
    await Promise.resolve();
  });
}

function mount(setParamAtPath: (p: (string | number)[], v: number | string | boolean) => void) {
  return renderHook(
    ({ values }: { values: ParamValueBag }) =>
      useOptimizer({
        geometry: "multiband.fandipole",
        currentValues: values,
        currentValuesKey: JSON.stringify(values),
        currentSchema: SCHEMA,
        backend: "momwire",
        designFreq: 21.383,
        measFreq: 21.383,
        autoSim: true,
        active: true,
        buildRequest: () => ({ geometry: "multiband.fandipole", ...values }) as unknown as SolveRequest,
        setParamAtPath,
      }),
    { initialProps: { values: VALUES } },
  );
}

describe("a run with group leaves marked", () => {
  it("sends the dotted names, and applies the result at their nested paths (flat too)", async () => {
    const setParamAtPath = vi.fn();
    const { result } = mount(setParamAtPath);
    act(() => {
      result.current.updateKnobOpt("bands.0.length_factor", { vary: true });
    });
    act(() => {
      result.current.updateKnobOpt("bands.1.length_factor", { vary: true });
    });
    act(() => {
      result.current.updateKnobOpt("sy_w5hgt", { vary: true });
    });
    act(() => result.current.setOptBands([18.1575, 21.383]));
    act(() => result.current.setOptEnabled(true));
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body)) as {
      optimize: { free: { name: string; min: number; max: number }[] };
    };
    expect(body.optimize.free).toEqual([
      { name: "bands.0.length_factor", min: 0.4, max: 0.55 },
      { name: "bands.1.length_factor", min: 0.4, max: 0.55 },
      { name: "sy_w5hgt", min: 8, max: 16 },
    ]);
    expect(setParamAtPath).toHaveBeenCalledWith(["bands", 0, "length_factor"], 0.4878);
    expect(setParamAtPath).toHaveBeenCalledWith(["bands", 1, "length_factor"], 0.4941);
    expect(setParamAtPath).toHaveBeenCalledWith(["sy_w5hgt"], 12.5);
  });

  it("the run's own write-back to a group leaf does not re-tune; a fixed leaf in the same group does", async () => {
    const { result, rerender } = mount(vi.fn());
    act(() => {
      result.current.updateKnobOpt("bands.0.length_factor", { vary: true });
    });
    act(() => result.current.setOptEnabled(true));
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const written: ParamValueBag = {
      ...VALUES,
      bands: [
        { freq: 18.1575, length_factor: 0.4878 },
        { freq: 21.383, length_factor: 0.4984 },
      ],
    };
    rerender({ values: written });
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    rerender({
      values: {
        ...written,
        bands: [
          { freq: 18.1575, length_factor: 0.4878 },
          { freq: 21.383, length_factor: 0.5 },
        ],
      },
    });
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
