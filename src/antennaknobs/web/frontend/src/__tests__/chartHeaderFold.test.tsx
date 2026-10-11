// A chart header folded to one line (Steve's phone, 2026-10-11): the sweep
// controls took half a phone's page above the chart, and as much on a
// desktop at 175 %. Folded, a header keeps its toggle with a summary and
// Run / Stop; the choice is one for every chart header, and is remembered.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ZParamControls } from "../components/results/ZParamControls";
import {
  FOLD_STORAGE_KEY,
  resetHeaderFoldForTests,
} from "../components/results/ControlsFold";
import { paramValues, type ParamSweepSpec } from "../lib/paramSweep";

const SPEC: ParamSweepSpec = {
  param: "tuner_c_pF",
  lo: 10,
  hi: 100,
  points: 50,
  log: false,
};
const KNOBS = [{ name: "tuner_c_pF", label: "C (pF)", type: "float" }] as never;

function mount(running = false) {
  const onStop = vi.fn();
  const onRun = vi.fn();
  render(
    <ZParamControls
      spec={SPEC}
      knobs={KNOBS}
      densityLabel="density"
      onSpec={() => {}}
      onParam={() => {}}
      onReset={() => {}}
      isDefault={false}
      values={paramValues(SPEC, false)}
      run={{
        running,
        received: 7,
        partial: false,
        stale: false,
        done: false,
        onStop,
        onRun,
      }}
    />,
  );
  return { onStop, onRun };
}

function stubWidth(narrow: boolean) {
  vi.stubGlobal("matchMedia", () => ({
    matches: narrow,
    addEventListener() {},
    removeEventListener() {},
  }));
}

beforeEach(() => {
  localStorage.clear();
  resetHeaderFoldForTests();
});
afterEach(() => vi.unstubAllGlobals());

describe("the chart header's fold", () => {
  it("is open on a wide window: every control, and the toggle to fold them", () => {
    stubWidth(false);
    mount();
    expect(screen.getByLabelText("from")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Fold the chart's controls" }),
    ).toBeTruthy();
  });

  it("starts folded on a narrow window: the summary and Run, no range boxes", () => {
    stubWidth(true);
    const { onRun } = mount();
    expect(screen.queryByLabelText("from")).toBeNull();
    const toggle = screen.getByRole("button", {
      name: "Show the chart's controls",
    });
    expect(toggle.textContent).toContain("C (pF) 10–100 · 50 pts");
    fireEvent.click(screen.getByRole("button", { name: "run" }));
    expect(onRun).toHaveBeenCalled();
  });

  it("keeps Stop and the progress count while folded", () => {
    stubWidth(true);
    const { onStop } = mount(true);
    fireEvent.click(screen.getByRole("button", { name: /7\/50 · stop/ }));
    expect(onStop).toHaveBeenCalled();
  });

  it("unfolds on a tap, and the pick is remembered over the window's width", () => {
    stubWidth(true);
    mount();
    fireEvent.click(
      screen.getByRole("button", { name: "Show the chart's controls" }),
    );
    expect(screen.getByLabelText("from")).toBeTruthy();
    expect(localStorage.getItem(FOLD_STORAGE_KEY)).toBe("0");
  });

  it("reads a stored pick back over the window's width", () => {
    stubWidth(false);
    localStorage.setItem(FOLD_STORAGE_KEY, "1");
    mount();
    expect(screen.queryByLabelText("from")).toBeNull();
  });

  it("treats a garbage stored value as no pick", () => {
    stubWidth(false);
    localStorage.setItem(FOLD_STORAGE_KEY, "yes please");
    mount();
    expect(screen.getByLabelText("from")).toBeTruthy();
  });
});
