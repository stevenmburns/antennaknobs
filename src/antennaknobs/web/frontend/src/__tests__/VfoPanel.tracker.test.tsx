// The "keep the target while I drag" switch and the third objective (#1220).
//
// Two rules are load-bearing here and both are about REFUSING rather than
// guessing:
//
//  - SWR is a minimisation, not a root, so there is no target to hold. It
//    stays in the picker (it is the only one of the three that works with any
//    knob count and any feed count) but the tracker refuses it.
//  - Resonance needs exactly ONE optimise-marked knob and Match Z₀ exactly
//    TWO. Any other count refuses WITH THE COUNT IN IT, because "the switch
//    did nothing" is the failure this exists to avoid.
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { VfoPanel } from "../components/session/VfoPanel";
import type { OptObjective } from "../components/session/VfoPanel";

const METRICS = { z_in_re: 48.2, z_in_im: -3.1, z0_ohms: 50.0, swr: 1.12 };

function baseProps() {
  return {
    currentBands: [],
    measLocked: false,
    measFreq: 14.1,
    bandContaining: () => null,
    measBand: "",
    selectMeasBand: vi.fn(),
    currentExample: undefined,
    measBandAnchor: 14.1,
    freqWindowCeiling: 30,
    setMeasFreq: vi.fn(),
    measLockable: false,
    linkMeas: false,
    toggleLink: vi.fn(),
    autoSim: true,
    setAutoSim: vi.fn(),
    optEnabled: true,
    setOptEnabled: vi.fn(),
    setOptPausedBy: vi.fn(),
    optObjective: "resonance" as OptObjective,
    optSeed: false,
    setOptSeed: vi.fn(),
    setOptObjective: vi.fn(),
    optError: null,
    optPausedBy: null,
    optRunning: false,
    optResult: null,
    optProgress: null,
    trackEnabled: false,
    setTrackEnabled: vi.fn(),
    trackRefusal: null as string | null,
    trackLatched: null as string | null,
    trackStatus: null as string | null,
  };
}

function openMenu(over: Partial<ReturnType<typeof baseProps>> = {}) {
  const props = { ...baseProps(), ...over };
  render(<VfoPanel {...props} />);
  fireEvent.click(screen.getByLabelText("Optimisation method"));
  return props;
}

describe("the objective picker offers all three (#1220)", () => {
  it("shows SWR, Resonance and Match Z₀, in that order", () => {
    openMenu();
    const items = screen
      .getAllByRole("menuitemradio")
      .map((n) => n.textContent ?? "");
    expect(items).toHaveLength(3);
    expect(items[0]).toContain("SWR");
    expect(items[1]).toContain("Resonance");
    expect(items[2]).toContain("Match Z₀");
  });

  it("says in one line what distinguishes them", () => {
    openMenu();
    const items = screen
      .getAllByRole("menuitemradio")
      .map((n) => n.textContent ?? "");
    expect(items[0]).toContain("any number of knobs");
    expect(items[2]).toContain("two knobs");
  });

  it("keeps SWR selectable — it is the any-count fallback, not replaced", () => {
    const props = openMenu();
    const swr = screen
      .getAllByRole("menuitemradio")
      .find((n) => (n.textContent ?? "").includes("SWR"))!;
    fireEvent.click(swr);
    expect(props.setOptObjective).toHaveBeenCalledWith("swr");
  });
});

describe("the tracker switch (#1220)", () => {
  function trackItem() {
    return screen
      .getAllByRole("menuitemcheckbox")
      .find((n) => (n.textContent ?? "").includes("Keep the target"))!;
  }

  it("turns the mode on when the knob count suits the objective", () => {
    const props = openMenu();
    fireEvent.click(trackItem());
    expect(props.setTrackEnabled).toHaveBeenCalledWith(true);
  });

  it("is disabled and states the count when the marks do not suit", () => {
    const props = openMenu({
      optObjective: "match_z0" as OptObjective,
      trackRefusal: "needs exactly 2 optimise-marked knobs; 1 marked",
    });
    const item = trackItem();
    expect((item as HTMLButtonElement).disabled).toBe(true);
    expect(item.textContent).toContain("needs exactly 2");
    expect(item.textContent).toContain("1 marked");
    fireEvent.click(item);
    expect(props.setTrackEnabled).not.toHaveBeenCalled();
  });

  it("refuses SWR as a minimisation rather than a root", () => {
    openMenu({
      optObjective: "swr" as OptObjective,
      trackRefusal: "SWR is a best compromise, not a target to hold",
    });
    expect(trackItem().textContent).toContain("best compromise");
  });
});

describe("the latched readout (#1220/#1216)", () => {
  const LOST = "the resonance you are holding disappears here";

  it("says the target disappeared, not that a knob hit a limit", () => {
    render(
      <VfoPanel {...baseProps()} trackEnabled trackLatched={LOST} />,
    );
    const el = screen.getByText(new RegExp(LOST));
    expect(el).toBeTruthy();
    // At the last good tick the held knob is usually nowhere near a bound, so
    // blaming a limit would be wrong as well as unhelpful.
    expect(el.textContent).not.toMatch(/limit/i);
    // And it is not permanent: dragging back the way you came re-acquires.
    expect(el.textContent).not.toMatch(/\bstop\b/i);
  });

  it("shows nothing while the mode is off", () => {
    render(
      <VfoPanel {...baseProps()} trackEnabled={false} trackLatched={LOST} />,
    );
    expect(screen.queryByText(new RegExp(LOST))).toBeNull();
  });

  it("mirrors the status onto the controls, wherever the message renders", () => {
    // A DOM probe that does not depend on where the wording lives, so a run in
    // the real app can confirm the state even if the text is somewhere a leaf
    // walk misses.
    const { container } = render(
      <VfoPanel {...baseProps()} trackEnabled trackLatched={LOST} trackStatus="latched" />,
    );
    expect(
      container.querySelector(".sim-controls")?.getAttribute("data-track-status"),
    ).toBe("latched");
  });

  it("shows nothing while tracking is healthy", () => {
    render(<VfoPanel {...baseProps()} trackEnabled trackLatched={null} />);
    expect(screen.queryByText(/disappears here/)).toBeNull();
  });
});

describe("the settled optimizer readout is unaffected", () => {
  it("still renders with the tracker off", () => {
    render(
      <VfoPanel
        {...baseProps()}
        optRunning
        optProgress={{
          n_evals: 3,
          params: {},
          objective: 1.1,
          metrics: METRICS,
        }}
      />,
    );
    expect(screen.getByText("#3 SWR 1.12")).toBeTruthy();
  });
});
