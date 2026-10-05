// AK#1901's minimal band UI: the gear menu's band list + balance, the
// /optimize body it sends (and, with no bands, the body it has always sent,
// byte for byte), the per-band progress readout and the before/after table.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import { useState } from "react";
import {
  DEFAULT_MEAN_WEIGHT,
  optimizeSpec,
  useOptimizer,
} from "../components/session/useOptimizer";
import {
  BandsEditor,
  BandsReadout,
  type OptBandRecord,
  type OptBandsControl,
} from "../components/session/OptBands";
import { VfoPanel } from "../components/session/VfoPanel";
import type { OptimizeResult, OptProgress } from "../components/session/VfoPanel";
import { parseBandFreq } from "../lib/optBands";
import type { SolveRequest } from "../lib/api";

// ---------------------------------------------------------------- the body

function jsonResponse(body: unknown): Response {
  return {
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response;
}

const METRICS = { z_in_re: 48.2, z_in_im: -3.1, z0_ohms: 50.0, swr: 1.12 };

function rec(freq: number, swr: number): OptBandRecord {
  return {
    freq_mhz: freq,
    objective: "swr",
    feed: 0,
    z0_ohms: 50,
    z_re: 50,
    z_im: 0,
    swr,
    residual: null,
    value: swr,
  };
}

const BAND_RESULT: OptimizeResult = {
  objective: "bands",
  params: { length_factor: 0.99 },
  objective_before: 2.5,
  objective_after: 1.4,
  metrics_before: { ...METRICS, swr: 3.0 },
  metrics_after: { ...METRICS, swr: 1.5 },
  n_evals: 30,
  improved: true,
  bands_before: [rec(7.1, 3.0), rec(14.2, 1.8)],
  bands_after: [rec(7.1, 1.5), rec(14.2, 1.3)],
  objective_worst_before: 3.0,
  objective_worst_after: 1.5,
  objective_mean_before: 2.4,
  objective_mean_after: 1.4,
  mean_weight: 0.5,
  worst_swr_before: 3.0,
  worst_swr_after: 1.5,
  worst_band_before: 0,
  worst_band_after: 0,
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock = vi.fn(async () => jsonResponse(BAND_RESULT));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function mount() {
  return renderHook(() =>
    useOptimizer({
      geometry: "dipoles.probe",
      currentValues: { length_factor: 1.0 },
      currentValuesKey: "length_factor=1",
      currentSchema: [],
      backend: "momwire",
      designFreq: 14.1,
      measFreq: 14.1,
      autoSim: true,
      active: true,
      buildRequest: () => ({ geometry: "dipoles.probe" }) as SolveRequest,
      setParamAtPath: vi.fn(),
    }),
  );
}

async function settle() {
  await act(async () => {
    vi.advanceTimersByTime(400);
    await Promise.resolve();
    await Promise.resolve();
  });
}

const rawBodies = () =>
  fetchMock.mock.calls.map(([, init]) => String((init as RequestInit).body));

function arm(result: { current: ReturnType<typeof useOptimizer> }) {
  act(() => {
    result.current.setKnobOpt({
      "dipoles.probe": {
        length_factor: { vary: true, optMin: 0.8, optMax: 1.2, dispMin: 0.8, dispMax: 1.2, step: 0.001 },
      },
    });
  });
}

describe("the /optimize body (AK#1901)", () => {
  it("with no bands, is byte-identical to the single-frequency body", async () => {
    const { result } = mount();
    arm(result);
    act(() => result.current.setOptEnabled(true));
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(rawBodies()[0]).toBe(
      '{"geometry":"dipoles.probe","optimize":{"free":[{"name":"length_factor","min":0.8,"max":1.2}],' +
        '"objective":"swr","max_evals":40,"seed_surrogate":false}}',
    );
  });

  it("with bands, sends each band as an SWR target and the balance, explicitly", async () => {
    const { result } = mount();
    arm(result);
    expect(result.current.optMeanWeight).toBe(DEFAULT_MEAN_WEIGHT);
    expect(DEFAULT_MEAN_WEIGHT).toBe(0.5);
    act(() => result.current.setOptBands([7.1, 14.2]));
    act(() => result.current.setOptEnabled(true));
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = JSON.parse(rawBodies()[0]) as Record<string, unknown>;
    expect(body.optimize).toEqual({
      free: [{ name: "length_factor", min: 0.8, max: 1.2 }],
      bands: [
        { freq: 7.1, objective: "swr" },
        { freq: 14.2, objective: "swr" },
      ],
      mode: "minimax",
      mean_weight: 0.5,
    });
    // The settled band result reaches the hook's state for the table.
    expect(result.current.optResult?.objective).toBe("bands");
  });

  it("a balance or band-list edit re-tunes, with the new values on the wire", async () => {
    const { result } = mount();
    arm(result);
    act(() => result.current.setOptBands([7.1, 14.2]));
    act(() => result.current.setOptEnabled(true));
    await settle();
    act(() => result.current.setOptMeanWeight(0));
    await settle();
    act(() => result.current.setOptBands([7.1, 14.2, 21.2]));
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const specs = rawBodies().map(
      (b) => (JSON.parse(b) as { optimize: { mean_weight: number; bands: unknown[] } }).optimize,
    );
    expect(specs[1].mean_weight).toBe(0);
    expect(specs[2].bands).toHaveLength(3);
  });

  it("optimizeSpec: an empty list is no bands", () => {
    const free = [{ name: "a", min: 0, max: 1 }];
    expect(
      optimizeSpec(free, { objective: "resonance", seed: true, bands: [], meanWeight: 0.5 }),
    ).toEqual({ free, objective: "resonance", max_evals: 40, seed_surrogate: true });
  });
});

// ----------------------------------------------------------- the editor

function Harness({ initial = null }: { initial?: number[] | null }) {
  const [freqs, setFreqs] = useState<number[] | null>(initial);
  const [w, setW] = useState(DEFAULT_MEAN_WEIGHT);
  const bands: OptBandsControl = {
    freqs,
    setFreqs,
    meanWeight: w,
    setMeanWeight: setW,
    defaultFreq: 14.1,
  };
  return (
    <>
      <BandsEditor bands={bands} />
      <output data-testid="state">{JSON.stringify({ freqs, w })}</output>
    </>
  );
}

const state = () =>
  JSON.parse(screen.getByTestId("state").textContent ?? "{}") as {
    freqs: number[] | null;
    w: number;
  };

describe("the band list editor", () => {
  it("switching Bands on seeds one row at the measurement frequency; off clears it", () => {
    render(<Harness />);
    const toggle = screen.getByRole("menuitemcheckbox", { name: /several bands/i });
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    expect(screen.queryByLabelText("Band frequencies")).toBeNull();
    fireEvent.click(toggle);
    expect(state().freqs).toEqual([14.1]);
    expect(screen.getByText("14.1 MHz")).toBeTruthy();
    fireEvent.click(toggle);
    expect(state().freqs).toBeNull();
  });

  it("adds a typed band, refuses junk and duplicates by name, removes a row", () => {
    render(<Harness initial={[14.1]} />);
    const input = screen.getByLabelText("Add a band, MHz");
    fireEvent.change(input, { target: { value: "7.15" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(state().freqs).toEqual([14.1, 7.15]);

    fireEvent.change(input, { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "add" }));
    expect(screen.getByRole("alert").textContent).toMatch(/frequency in MHz/);
    expect(state().freqs).toEqual([14.1, 7.15]);

    fireEvent.change(input, { target: { value: "7.15" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByRole("alert").textContent).toMatch(/already a band/);

    fireEvent.click(screen.getByRole("button", { name: "Remove the 14.1 MHz band" }));
    expect(state().freqs).toEqual([7.15]);
    // The last row cannot be removed: switch Bands off instead.
    expect(
      (screen.getByRole("button", { name: "Remove the 7.15 MHz band" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("the balance slider defaults to 0.5 and sets mean_weight", () => {
    render(<Harness initial={[14.1]} />);
    const slider = screen.getByLabelText(
      "Balance between the worst band and the average",
    ) as HTMLInputElement;
    expect(Number(slider.value)).toBe(0.5);
    expect(screen.getByText(/0 = improve the worst band only/)).toBeTruthy();
    fireEvent.change(slider, { target: { value: "0.2" } });
    expect(state().w).toBe(0.2);
  });

  it("parseBandFreq caps the list at eight", () => {
    expect(parseBandFreq("30", [1, 2, 3, 4, 5, 6, 7, 8])).toEqual({ error: "at most 8 bands" });
    expect(parseBandFreq(" 3.5 ", [])).toEqual({ freq: 3.5 });
    expect("error" in parseBandFreq("-1", [])).toBe(true);
  });
});

// ---------------------------------------------------------- the readouts

const BAND_PROGRESS: OptProgress = {
  n_evals: 9,
  params: { length_factor: 0.97 },
  objective: 1.9,
  metrics: { ...METRICS, swr: 2.2 },
  bands: [
    { index: 0, ...rec(7.1, 2.2) },
    { index: 1, ...rec(14.2, 1.6) },
  ],
  objective_worst: 2.2,
  objective_mean: 1.9,
  worst_band: 0,
};

describe("the band readouts", () => {
  it("progress: each band's SWR and the worst", () => {
    render(<BandsReadout running progress={BAND_PROGRESS} result={null} error={null} />);
    const box = screen.getByLabelText("Band progress");
    expect(box.textContent).toContain("#9");
    expect(box.textContent).toContain("7.1: SWR 2.20");
    expect(box.textContent).toContain("14.2: SWR 1.60");
    expect(box.textContent).toContain("worst 2.20");
  });

  it("result: before -> after per band, then worst and mean", () => {
    render(<BandsReadout running={false} progress={null} result={BAND_RESULT} error={null} />);
    const table = screen.getByRole("table", { name: "Band results" });
    const rows = within(table)
      .getAllByRole("row")
      .map((r) =>
        [
          ...within(r).queryAllByRole("columnheader"),
          ...within(r).queryAllByRole("rowheader"),
          ...within(r).queryAllByRole("cell"),
        ].map((c) => c.textContent),
      );
    expect(rows).toEqual([
      ["MHz", "SWR before", "after"],
      ["7.1", "3.00", "1.50"],
      ["14.2", "1.80", "1.30"],
      ["worst", "3.00", "1.50"],
      ["mean", "2.40", "1.40"],
    ]);
  });

  it("a refusal shows its text", () => {
    render(
      <BandsReadout
        running={false}
        progress={null}
        result={null}
        error="band 1 repeats band 0: the same frequency read at the same feed is one equation, not two"
      />,
    );
    expect(screen.getByRole("alert").textContent).toMatch(/band 1 repeats band 0/);
  });

  it("a single-band result never renders the table", () => {
    const { container } = render(
      <BandsReadout
        running={false}
        progress={null}
        result={{ ...BAND_RESULT, objective: "swr" }}
        error={null}
      />,
    );
    expect(container.innerHTML).toBe("");
  });
});

// ------------------------------------------------- no reading, and index

describe("null readings and index matching (AK#1901)", () => {
  const unread = (freq: number, index?: number): OptBandRecord => ({
    ...rec(freq, 0),
    ...(index !== undefined ? { index } : {}),
    swr: null,
    z_re: null,
    z_im: null,
    value: null,
  });

  it("progress: a band with no reading, and a worst with none, say so", () => {
    const p: OptProgress = {
      ...BAND_PROGRESS,
      bands: [
        { ...unread(7.1), index: 0 },
        { index: 1, ...rec(14.2, 1.6) },
      ],
      objective_worst: null,
    };
    render(<BandsReadout running progress={p} result={null} error={null} />);
    const box = screen.getByLabelText("Band progress");
    expect(box.textContent).toContain("7.1: SWR no reading");
    expect(box.textContent).toContain("14.2: SWR 1.60");
    expect(box.textContent).toContain("worst no reading");
  });

  it("the panel survives a null worst band (narrow readout, tooltip, settled SWR)", () => {
    const nullMetrics = { z_in_re: null, z_in_im: null, z0_ohms: 50, swr: null } as unknown as OptProgress["metrics"];
    const p: OptProgress = {
      ...BAND_PROGRESS,
      objective: null as unknown as number,
      metrics: nullMetrics,
      bands: [{ ...unread(7.1), index: 0 }],
      objective_worst: null,
    };
    const { unmount } = render(
      <VfoPanel {...panelProps()} optRunning optProgress={p} optResult={null} bands={bandsOn([7.1])} />,
    );
    expect(screen.getByText("#9 worst SWR no reading")).toBeTruthy();
    unmount();
    render(
      <VfoPanel
        {...panelProps()}
        optRunning={false}
        optProgress={null}
        optResult={{ ...BAND_RESULT, metrics_after: nullMetrics }}
        bands={bandsOn([7.1, 14.2])}
      />,
    );
    expect(screen.getByText("worst SWR no reading")).toBeTruthy();
  });

  it("result rows match their start by index, not position; null reads as no reading", () => {
    const res: OptimizeResult = {
      ...BAND_RESULT,
      // The starts listed in the other order: a position match would swap them.
      bands_before: [{ ...rec(14.2, 1.8), index: 1 }, unread(7.1, 0)],
      bands_after: [{ ...rec(7.1, 1.5), index: 0 }, { ...rec(14.2, 1.3), index: 1 }],
      worst_swr_before: null,
      objective_mean_before: null,
    };
    render(<BandsReadout running={false} progress={null} result={res} error={null} />);
    const table = screen.getByRole("table", { name: "Band results" });
    const rows = within(table)
      .getAllByRole("row")
      .map((r) =>
        [
          ...within(r).queryAllByRole("columnheader"),
          ...within(r).queryAllByRole("rowheader"),
          ...within(r).queryAllByRole("cell"),
        ].map((c) => c.textContent),
      );
    expect(rows).toEqual([
      ["MHz", "SWR before", "after"],
      ["7.1", "no reading", "1.50"],
      ["14.2", "1.80", "1.30"],
      ["worst", "no reading", "1.50"],
      ["mean", "no reading", "1.40"],
    ]);
  });
});

// ------------------------------------------------------------ on the panel

function panelProps() {
  return {
    currentBands: [],
    measLocked: false,
    measFreq: 14.1,
    bandContaining: () => null,
    measBand: "",
    selectMeasBand: vi.fn(),
    sweepRange: { lo: 11.28, hi: 17.625, spacing: "log" as const },
    setMeasFreq: vi.fn(),
    measLockable: false,
    linkMeas: false,
    toggleLink: vi.fn(),
    autoSim: true,
    setAutoSim: vi.fn(),
    optEnabled: true,
    setOptEnabled: vi.fn(),
    setOptPausedBy: vi.fn(),
    optObjective: "swr" as const,
    optSeed: false,
    setOptSeed: vi.fn(),
    trackEnabled: false,
    setTrackEnabled: vi.fn(),
    trackRefusal: null,
    trackLatched: null,
    trackStatus: null,
    setOptObjective: vi.fn(),
    optError: null,
    optPausedBy: null,
  };
}

const bandsOn = (freqs: number[] | null): OptBandsControl => ({
  freqs,
  setFreqs: vi.fn(),
  meanWeight: 0.5,
  setMeanWeight: vi.fn(),
  defaultFreq: 14.1,
});

describe("VfoPanel with bands", () => {
  it("mid-run: the narrow readout names the worst band SWR, the block lists every band", () => {
    render(
      <VfoPanel
        {...panelProps()}
        optRunning
        optProgress={BAND_PROGRESS}
        optResult={null}
        bands={bandsOn([7.1, 14.2])}
      />,
    );
    expect(screen.getByText("#9 worst SWR 2.20")).toBeTruthy();
    expect(screen.getByLabelText("Band progress").textContent).toContain("14.2: SWR 1.60");
  });

  it("settled: the table renders and the narrow readout says worst SWR", () => {
    render(
      <VfoPanel
        {...panelProps()}
        optRunning={false}
        optProgress={null}
        optResult={BAND_RESULT}
        bands={bandsOn([7.1, 14.2])}
      />,
    );
    expect(screen.getByRole("table", { name: "Band results" })).toBeTruthy();
    expect(screen.getByText("worst SWR 1.50")).toBeTruthy();
  });

  it("bands off: no band block, and the single-band readout as before", () => {
    const single: OptimizeResult = { ...BAND_RESULT, objective: "swr" };
    render(
      <VfoPanel
        {...panelProps()}
        optRunning={false}
        optProgress={null}
        optResult={single}
        optError="some refusal"
        bands={bandsOn(null)}
      />,
    );
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByText("SWR 1.50")).toBeTruthy();
    // The error stays in its usual narrow readout when bands are off.
    expect(screen.getByText("some refusal").className).toContain("opt-readout-err");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
