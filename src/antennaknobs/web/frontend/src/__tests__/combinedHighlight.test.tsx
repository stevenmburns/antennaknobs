// The combined view's row highlight (AK#1730), in the compare table: each row
// toggles on its own (not a radio), any number at once; with none highlighted
// every trace draws at full strength, and that state is always reachable —
// by un-highlighting each row, or by "all".
import { useState } from "react";
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import {
  effectiveHighlight,
  highlightState,
  LIVE_ENTITY,
  toggleHighlight,
} from "../components/charts/combined";
import type { PinnedPattern } from "../components/charts/types";
import { PatternCompareTable } from "../components/results/PatternCompareTable";
import { CompareOverlay } from "../components/results/StageOverlays";
import type { SolveResponse } from "../lib/api";

const pin = (id: string, label: string, enabled = true, colorIdx = 0): PinnedPattern => ({
  id,
  label,
  result: {} as SolveResponse,
  metrics: null,
  enabled,
  colorIdx,
});
const PINS = [pin("a", "pin A"), pin("b", "pin B", true, 1), pin("h", "pin H", false, 2)];
const shown = PINS.filter((p) => p.enabled);
const ENTITIES = [LIVE_ENTITY, "a", "b"];
const states = (hl: readonly string[]) =>
  ENTITIES.map((e) => highlightState(e, effectiveHighlight(hl, shown)));

describe("the highlight model", () => {
  it("draws everything normally with nothing highlighted", () => {
    expect(states([])).toEqual(["normal", "normal", "normal"]);
  });

  it("toggles rows independently: highlight A, highlight B, un-highlight both", () => {
    let hl: string[] = [];
    hl = toggleHighlight(hl, "a", shown);
    expect(states(hl)).toEqual(["dim", "strong", "dim"]);
    hl = toggleHighlight(hl, "b", shown);
    expect(states(hl)).toEqual(["dim", "strong", "strong"]); // both, not a radio
    hl = toggleHighlight(hl, "a", shown);
    expect(states(hl)).toEqual(["dim", "dim", "strong"]);
    hl = toggleHighlight(hl, "b", shown);
    expect(hl).toEqual([]);
    expect(states(hl)).toEqual(["normal", "normal", "normal"]);
  });

  it("drops a pin that is hidden or gone, so it can never dim everything", () => {
    expect(effectiveHighlight(["h", "gone"], shown)).toEqual([]);
    expect(states(["h", "gone"])).toEqual(["normal", "normal", "normal"]);
    // A toggle works from the effective set, so the stale ids go with it.
    expect(toggleHighlight(["gone", "a"], "a", shown)).toEqual([]);
  });
});

// The table and overlay wired to real state, as DesignSession wires them.
function Harness({ onClearPins = () => {} }: { onClearPins?: () => void }) {
  const [hl, setHl] = useState<string[]>([]);
  const eff = effectiveHighlight(hl, shown);
  return (
    <>
      <CompareOverlay
        pinCurrentPattern={() => {}}
        setCompareCollapsed={() => {}}
        result={null}
        pinnedPatterns={PINS}
        compareCollapsed={false}
        clearPins={onClearPins}
        liveMetrics={null}
        currentExample={undefined}
        geometry="g"
        measFreq={14.2}
        removePin={() => {}}
        togglePin={() => {}}
        cutLabel={null}
        highlight={eff}
        onToggleHighlight={(id) => setHl((cur) => toggleHighlight(cur, id, shown))}
        onClearHighlight={() => setHl([])}
      />
      <output data-testid="states">{ENTITIES.map((e) => highlightState(e, eff)).join(",")}</output>
    </>
  );
}
const drawn = () => screen.getByTestId("states").textContent;
const sw = (label: string) => screen.getByRole("button", { name: `Highlight ${label}` });

describe("the compare table's highlight", () => {
  it("highlights A, then B, and un-highlighting both returns to all full strength", () => {
    render(<Harness />);
    expect(drawn()).toBe("normal,normal,normal");
    fireEvent.click(sw("pin A"));
    fireEvent.click(sw("pin B"));
    expect(drawn()).toBe("dim,strong,strong");
    expect(sw("pin A").getAttribute("aria-pressed")).toBe("true");
    expect(sw("pin B").getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(sw("pin A"));
    fireEvent.click(sw("pin B"));
    expect(drawn()).toBe("normal,normal,normal");
  });

  it("toggles from a click anywhere on the row", () => {
    render(<Harness />);
    const row = sw("pin B").closest("tr")!;
    fireEvent.click(row.querySelectorAll("td")[2]); // a metrics cell
    expect(drawn()).toBe("dim,dim,strong");
    fireEvent.click(row.querySelectorAll("td")[2]);
    expect(drawn()).toBe("normal,normal,normal");
  });

  it("'all' resets to none highlighted, and shows only while something is", () => {
    const clearPins = vi.fn();
    render(<Harness onClearPins={clearPins} />);
    expect(screen.queryByRole("button", { name: "all" })).toBeNull();
    fireEvent.click(sw("g @ 14.20 MHz")); // the live row
    fireEvent.click(sw("pin A"));
    fireEvent.click(screen.getByRole("button", { name: "all" }));
    expect(drawn()).toBe("normal,normal,normal");
    expect(screen.queryByRole("button", { name: "all" })).toBeNull();
    expect(clearPins).not.toHaveBeenCalled(); // "clear" still means remove pins
  });

  it("cannot highlight a hidden pin", () => {
    render(<Harness />);
    expect((sw("pin H") as HTMLButtonElement).disabled).toBe(true);
  });

  it("keeps show/hide on the name and leaves the one-cut views' table unchanged", () => {
    const onToggle = vi.fn();
    const onToggleHighlight = vi.fn();
    const { unmount } = render(
      <PatternCompareTable
        live={null}
        liveLabel="live"
        pinned={PINS}
        onRemove={() => {}}
        onToggle={onToggle}
        highlight={[]}
        onToggleHighlight={onToggleHighlight}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^pin A$/ }));
    expect(onToggle).toHaveBeenCalledWith("a");
    expect(onToggleHighlight).not.toHaveBeenCalled();
    unmount();
    render(
      <PatternCompareTable
        live={null}
        liveLabel="live"
        pinned={PINS}
        onRemove={() => {}}
        onToggle={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /^Highlight/ })).toBeNull();
  });
});
