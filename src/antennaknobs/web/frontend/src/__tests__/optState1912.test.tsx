// AK#1912: "I don't think the optimize button does anything. How can I
// tell?" The readout under Live / Optimize always says the optimizer's state:
// nothing marked, needs Live, paused while its settings are edited, paused
// by a hand move, running (or restarted), and the progress after that.
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VfoPanel, type OptProgress, type OptStateControl } from "../components/session/VfoPanel";

function state(over: Partial<OptStateControl> = {}): OptStateControl {
  return { marked: 2, restarted: false, menuOpen: false, menuPaused: false, setMenuOpen: vi.fn(), ...over };
}

const PROGRESS: OptProgress = {
  n_evals: 7,
  params: { a: 1 },
  objective: 1.34,
  metrics: { z_in_re: 48.2, z_in_im: -3.1, z0_ohms: 50.0, swr: 1.12 },
};

function props(over: Record<string, unknown> = {}) {
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
    optRunning: false,
    optObjective: "swr" as const,
    setOptObjective: vi.fn(),
    optSeed: false,
    setOptSeed: vi.fn(),
    trackEnabled: false,
    setTrackEnabled: vi.fn(),
    trackRefusal: null,
    trackLatched: null,
    trackStatus: null,
    optResult: null,
    optProgress: null,
    optError: null,
    optPausedBy: null,
    optState: state(),
    ...over,
  };
}

const status = () => screen.queryByRole("status");

describe("the Optimize readout states the optimizer's state (AK#1912)", () => {
  it("nothing marked: says how to mark a knob", () => {
    render(<VfoPanel {...props({ optState: state({ marked: 0 }) })} />);
    expect(status()?.textContent).toBe("mark a knob to optimize (right-click → Optimize this knob)");
  });

  it("Live off: needs Live", () => {
    render(<VfoPanel {...props({ autoSim: false })} />);
    expect(status()?.textContent).toBe("needs Live");
  });

  it("nothing marked wins over Live off: marking is the first thing to do", () => {
    render(<VfoPanel {...props({ autoSim: false, optState: state({ marked: 0 }) })} />);
    expect(status()?.textContent).toMatch(/^mark a knob/);
  });

  it("menu open over a running Optimize: paused while editing its settings", () => {
    render(
      <VfoPanel {...props({ optEnabled: false, optState: state({ menuOpen: true, menuPaused: true }) })} />,
    );
    expect(status()?.textContent).toBe("paused while editing optimize settings");
    // The menu itself is open: the session holds its state.
    expect(screen.getByRole("menu")).toBeTruthy();
  });

  it("menu open with Optimize already off: nothing paused, nothing said", () => {
    render(<VfoPanel {...props({ optEnabled: false, optState: state({ menuOpen: true }) })} />);
    expect(status()).toBeNull();
  });

  it("the gear button asks the session to open and close the menu", () => {
    const setMenuOpen = vi.fn();
    render(<VfoPanel {...props({ optState: state({ setMenuOpen }) })} />);
    screen.getByRole("button", { name: "Optimisation method" }).click();
    expect(setMenuOpen).toHaveBeenCalledWith(true);
  });

  it("a hand move of a marked knob: paused, and it stays said", () => {
    render(
      <VfoPanel {...props({ optEnabled: false, optPausedBy: { kind: "knob", name: "sy_cap1" } })} />,
    );
    const el = screen.getByText("paused: you moved a marked knob");
    expect(el.getAttribute("title")).toMatch(/sy_cap1/);
  });

  it("started, before the first frame: bands, knobs, running…", () => {
    render(
      <VfoPanel
        {...props({
          optRunning: true,
          bands: {
            freqs: [7.2, 3.6, 1.8],
            setFreqs: vi.fn(),
            meanWeight: 0.5,
            setMeanWeight: vi.fn(),
            defaultFreq: 7.2,
          },
          optState: state({ marked: 4 }),
        })}
      />,
    );
    expect(status()?.textContent).toBe("bands: 3, knobs: 4, running…");
  });

  it("single band started: knobs, running…", () => {
    render(<VfoPanel {...props({ optRunning: true })} />);
    expect(status()?.textContent).toBe("knobs: 2, running…");
  });

  it("a superseding run says restarted, before and after its first frame", () => {
    const { rerender } = render(
      <VfoPanel {...props({ optRunning: true, optState: state({ restarted: true }) })} />,
    );
    expect(status()?.textContent).toBe("knobs: 2, restarted…");
    rerender(
      <VfoPanel
        {...props({ optRunning: true, optProgress: PROGRESS, optState: state({ restarted: true }) })}
      />,
    );
    expect(screen.getByText("restarted")).toBeTruthy();
    // The eval count line is the progress readout, unchanged.
    expect(screen.getByText("#7 SWR 1.12")).toBeTruthy();
    expect(status()).toBeNull();
  });

  it("running with progress and not superseded: no restarted chip", () => {
    render(<VfoPanel {...props({ optRunning: true, optProgress: PROGRESS })} />);
    expect(screen.getByText("#7 SWR 1.12")).toBeTruthy();
    expect(screen.queryByText("restarted")).toBeNull();
  });

  it("the Optimize button's tooltip counts the marked knobs", () => {
    render(<VfoPanel {...props({ optState: state({ marked: 3 }) })} />);
    expect(screen.getByRole("button", { name: /^Optimize/ }).getAttribute("title")).toMatch(
      /Marked: 3 knobs\.$/,
    );
  });

  it("Optimize off and nothing paused: no state line", () => {
    render(<VfoPanel {...props({ optEnabled: false, optState: state({ marked: 0 }) })} />);
    expect(status()).toBeNull();
  });
});

describe("useOptimizer's state for the readout (AK#1912)", () => {
  it("a hand move's pause stays until re-enabled; a design load's cue clears", async () => {
    const { renderHook, act } = await import("@testing-library/react");
    const { useOptimizer } = await import("../components/session/useOptimizer");
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() =>
        useOptimizer({
          geometry: "deck.x",
          currentValues: { a: 1 },
          currentValuesKey: "a=1",
          currentSchema: [],
          backend: "momwire",
          designFreq: 7.2,
          measFreq: 7.2,
          autoSim: true,
          active: true,
          buildRequest: () => ({ geometry: "deck.x" }) as never,
          setParamAtPath: vi.fn(),
        }),
      );
      expect(result.current.optMarked).toBe(0);
      act(() => result.current.setOptPausedBy({ kind: "knob", name: "a" }));
      act(() => {
        vi.advanceTimersByTime(10_000);
      });
      expect(result.current.optPausedBy).toEqual({ kind: "knob", name: "a" });
      act(() => result.current.setOptPausedBy({ kind: "load" }));
      act(() => {
        vi.advanceTimersByTime(6000);
      });
      expect(result.current.optPausedBy).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
