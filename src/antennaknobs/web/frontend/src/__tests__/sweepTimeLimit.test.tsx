// The hosted wall-time budget for every sweep: past ANTENNAKNOBS_MAX_SWEEP_SECONDS
// the server stops a sweep at its next point and closes the stream with
// `{done, stopped: "time", time_budget_s}`. The workbench says so: "stopped at
// the time limit (120 s): partial", as an advisory over the view and in the
// knob chart's status, and keeps what landed.
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, renderHook, waitFor } from "@testing-library/react";
import { useRef } from "react";
import { closingAdvisories, SWEEP_TIME_LIMIT, sweepTimeLimitNote } from "../lib/sweep";
import { useParamSweep } from "../components/session/useParamSweep";
import { ZParamChart } from "../components/charts/ZParamChart";
import type { ParamSweepData } from "../lib/paramSweep";

HTMLCanvasElement.prototype.getContext =
  (() => null) as unknown as HTMLCanvasElement["getContext"];

describe("the time-limit note", () => {
  it("names the budget", () => {
    expect(sweepTimeLimitNote({ stopped: "time", time_budget_s: 120 })).toBe(
      "stopped at the time limit (120 s): partial",
    );
  });
  it("without a budget it still says why", () => {
    expect(sweepTimeLimitNote({ stopped: "time" })).toBe("stopped at the time limit: partial");
  });
  it("a run that was not stopped says nothing", () => {
    expect(sweepTimeLimitNote({})).toBeNull();
    expect(sweepTimeLimitNote(null)).toBeNull();
    expect(closingAdvisories({ advisories: [{ category: "X", text: "y" }] })).toEqual([
      { category: "X", text: "y" },
    ]);
  });
  it("leads the closing record's advisories", () => {
    expect(
      closingAdvisories({
        stopped: "time",
        time_budget_s: 120,
        advisories: [{ category: "GapFed", text: "g" }],
      }),
    ).toEqual([
      { category: SWEEP_TIME_LIMIT, text: "stopped at the time limit (120 s): partial" },
      { category: "GapFed", text: "g" },
    ]);
  });
});

describe("the knob chart's status", () => {
  const STOPPED: ParamSweepData = {
    param: "length_factor",
    label: "length factor",
    values: [0.9, 1.0],
    z_re: [55, 70],
    z_im: [-40, 0],
    z_re_extrap: null,
    z_im_extrap: null,
    partial: true,
    timeLimitS: 120,
  };
  const mount = (data: ParamSweepData) =>
    render(
      <ZParamChart
        data={data}
        param="length_factor"
        label="length factor"
        total={5}
        currentValue={1}
        liveR={70}
        liveX={0}
        size={400}
        running={false}
        xLog={false}
      />,
    ).container.querySelector("canvas.zparam") as HTMLElement;

  it("a time-limited sweep says so, with what landed", () => {
    expect(mount(STOPPED).dataset.status).toBe(
      "stopped at the time limit (120 s): partial — 2/5",
    );
  });
  it("a sweep the user stopped keeps its own words", () => {
    const stopped: ParamSweepData = { ...STOPPED };
    delete stopped.timeLimitS;
    expect(mount(stopped).dataset.status).toBe("stopped at 2/5 — partial");
  });
});

describe("the parameter sweep runner reads the stop", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("keeps the landed points, marks them partial, and carries the note", async () => {
    const lines = [
      { param: "length_factor", value: 0.9, z_re: 55, z_im: -40, solver: "momwire" },
      { done: true, solver: "momwire", stopped: "time", time_budget_s: 120 },
    ];
    const text = lines.map((l) => JSON.stringify(l)).join("\n") + "\n";
    const fetchMock = vi.fn(async () => new Response(text, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => {
      const seqRef = useRef(1);
      const approvedComboRef = useRef(false);
      return useParamSweep({
        req: { param: "length_factor", values: [0.9, 1.0, 1.1], label: "length factor" },
        sig: "s",
        wanted: true,
        autoSim: true,
        active: true,
        comboApproved: false,
        recommendedBackend: null,
        buildRequest: () => ({ geometry: "dipoles.invvee" }) as never,
        solveWithheld: () => false,
        seqRef,
        approvedComboRef,
      });
    });
    result.current.runNow();
    await waitFor(() => expect(result.current.data?.timeLimitS).toBe(120));
    const d = result.current.data!;
    expect(d.values).toEqual([0.9]);
    expect(d.partial).toBe(true);
    expect(d.advisories?.[0]).toEqual({
      category: SWEEP_TIME_LIMIT,
      text: "stopped at the time limit (120 s): partial",
    });
    // A closed stream is not a dropped one: it is not asked for again.
    await waitFor(() => expect(result.current.running).toBe(false));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
