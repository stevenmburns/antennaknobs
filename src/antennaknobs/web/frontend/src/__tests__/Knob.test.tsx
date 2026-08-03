// Pins the rotary Knob's ARIA contract and keyboard behavior
// (src/components/params/Knob.tsx, issue #673): role="slider" attributes,
// the applyKey step/Page/Home/End arithmetic (in particular the 0-anchored
// step grid documented at Knob.tsx lines 66-74, and Home/End's deliberate
// bypass of that grid via roundP), clamping at the bounds, the Enter-to-edit
// numeric input round trip, and the disabled state.
//
// Scope cut: no wheel or pointer-drag tests. jsdom has no real layout or
// pointer-capture, so the drag math (which depends on getBoundingClientRect
// and setPointerCapture) can't be exercised meaningfully — those paths are
// left to manual/visual verification.
import type { ComponentProps } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, fireEvent, screen } from "@testing-library/react";
import { Knob } from "../components/params/Knob";

// --- render harness ---------------------------------------------------------
// onChange is always the spy (spread after overrides) so a test can't
// accidentally supply its own and end up asserting on a spy the component
// never received.
type KnobOverrides = Partial<Omit<ComponentProps<typeof Knob>, "onChange">>;

function renderKnob(overrides: KnobOverrides = {}) {
  const onChange = vi.fn();
  const view = render(
    <Knob
      knobId="test.knob"
      value={1.03}
      min={0.15}
      max={4.97}
      step={0.2}
      precision={2}
      unit={null}
      label="Test Knob"
      {...overrides}
      onChange={onChange}
    />,
  );
  return { ...view, onChange };
}

describe("Knob — ARIA contract", () => {
  it("exposes role, valuemin/max/now/text, label and data-knob-id", () => {
    renderKnob({
      knobId: "geom.length",
      value: 2.5,
      min: 0,
      max: 10,
      step: 0.5,
      precision: 1,
      unit: "m",
      label: "Length",
    });
    const slider = screen.getByRole("slider", { name: "Length" });
    expect(slider.getAttribute("aria-valuemin")).toBe("0");
    expect(slider.getAttribute("aria-valuemax")).toBe("10");
    expect(slider.getAttribute("aria-valuenow")).toBe("2.5");
    expect(slider.getAttribute("aria-valuetext")).toBe("2.5m");
    expect(slider.getAttribute("data-knob-id")).toBe("geom.length");
  });

  it("omits the unit suffix from aria-valuetext when unit is null", () => {
    renderKnob({ value: 3, precision: 0, unit: null });
    expect(screen.getByRole("slider").getAttribute("aria-valuetext")).toBe("3");
  });
});

describe("Knob — keyboard step/page/home/end", () => {
  // Shared fixture: min=0.15 and step=0.2 put min deliberately off the
  // 0-anchored step grid, so Home (below) can distinguish roundP from snap.
  it.each(["ArrowUp", "ArrowRight"])(
    "%s adds one step, snapped to the 0-anchored grid (not min-anchored)",
    (key) => {
      const { onChange } = renderKnob();
      fireEvent.keyDown(screen.getByRole("slider"), { key });
      // Doc'd exact case (Knob.tsx 66-74): 1.03 + 0.2 -> 1.2, not 1.23
      // (1.23 is what a min-anchored or unsnapped grid would produce).
      expect(onChange).toHaveBeenCalledWith(1.2);
      expect(onChange).toHaveBeenCalledTimes(1);
    },
  );

  it.each(["ArrowDown", "ArrowLeft"])("%s subtracts one step, grid-snapped", (key) => {
    const { onChange } = renderKnob();
    fireEvent.keyDown(screen.getByRole("slider"), { key });
    expect(onChange).toHaveBeenCalledWith(0.8);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("PageUp adds ten steps, grid-snapped", () => {
    const { onChange } = renderKnob();
    fireEvent.keyDown(screen.getByRole("slider"), { key: "PageUp" });
    expect(onChange).toHaveBeenCalledWith(3);
  });

  it("PageDown subtracts ten steps, clamped at min", () => {
    const { onChange } = renderKnob();
    fireEvent.keyDown(screen.getByRole("slider"), { key: "PageDown" });
    expect(onChange).toHaveBeenCalledWith(0.15);
  });

  it("Home jumps to exactly min with no grid snap (regression guard)", () => {
    // min=0.15 is off the 0.2 grid: snap(0.15) would land on 0.2, not 0.15.
    // Home must go through roundP alone to hit the bound exactly.
    const { onChange } = renderKnob();
    fireEvent.keyDown(screen.getByRole("slider"), { key: "Home" });
    expect(onChange).toHaveBeenCalledWith(0.15);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("End jumps to exactly max", () => {
    const { onChange } = renderKnob();
    fireEvent.keyDown(screen.getByRole("slider"), { key: "End" });
    expect(onChange).toHaveBeenCalledWith(4.97);
  });
});

describe("Knob — clamping", () => {
  it("ArrowUp at max stays at max", () => {
    const { onChange } = renderKnob({ value: 1, min: 0, max: 1, step: 0.2, precision: 2 });
    fireEvent.keyDown(screen.getByRole("slider"), { key: "ArrowUp" });
    expect(onChange).toHaveBeenCalledWith(1);
  });

  it("ArrowDown at min stays at min", () => {
    const { onChange } = renderKnob({ value: 0, min: 0, max: 1, step: 0.2, precision: 2 });
    fireEvent.keyDown(screen.getByRole("slider"), { key: "ArrowDown" });
    expect(onChange).toHaveBeenCalledWith(0);
  });
});

describe("Knob — precision rounding", () => {
  it("emits the clean toFixed value even when the grid math produces fp noise", () => {
    // 0.2 + 0.1 = 0.30000000000000004 in raw fp; the step-grid multiply
    // reintroduces noise (Math.round(...)*0.1), so only the final toFixed
    // in roundP cleans it up.
    const { onChange } = renderKnob({ value: 0.2, step: 0.1, precision: 1, min: 0, max: 10 });
    fireEvent.keyDown(screen.getByRole("slider"), { key: "ArrowUp" });
    expect(onChange).toHaveBeenCalledWith(0.3);
  });
});

describe("Knob — Enter-to-edit", () => {
  it("Enter opens the numeric edit input", () => {
    renderKnob();
    expect(screen.queryByRole("spinbutton")).toBeNull();
    fireEvent.keyDown(screen.getByRole("slider"), { key: "Enter" });
    expect(screen.getByRole("spinbutton")).toBeTruthy();
  });

  it("committing a typed number on Enter fires onChange(snapped) and closes the editor", () => {
    const { onChange } = renderKnob();
    fireEvent.keyDown(screen.getByRole("slider"), { key: "Enter" });
    const input = screen.getByRole("spinbutton");
    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith(2);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });

  it("Escape cancels the edit with no onChange", () => {
    const { onChange } = renderKnob();
    fireEvent.keyDown(screen.getByRole("slider"), { key: "Enter" });
    const input = screen.getByRole("spinbutton");
    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });

  it("a non-finite committed value fires no onChange but still closes the editor", () => {
    // A real <input type="number"> sanitizes any non-numeric text back to ""
    // before it's ever stored (verified empirically: fireEvent.change with
    // "abc" leaves input.value === ""), so a literal non-numeric keystroke
    // never reaches commit()'s Number() check in jsdom. Override the value
    // accessor directly to exercise that guard the way a NaN/Infinity from
    // some other input path would.
    const { onChange } = renderKnob();
    fireEvent.keyDown(screen.getByRole("slider"), { key: "Enter" });
    const input = screen.getByRole("spinbutton") as HTMLInputElement;
    Object.defineProperty(input, "value", { get: () => "abc", configurable: true });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });
});

describe("Knob — disabled", () => {
  it("ignores keys, and reports tabIndex -1 / aria-disabled true", () => {
    const { onChange } = renderKnob({ disabled: true });
    const slider = screen.getByRole("slider");
    expect(slider.getAttribute("tabindex")).toBe("-1");
    expect(slider.getAttribute("aria-disabled")).toBe("true");
    fireEvent.keyDown(slider, { key: "ArrowUp" });
    fireEvent.keyDown(slider, { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });

  it("an enabled knob has tabIndex 0 and no aria-disabled", () => {
    renderKnob();
    const slider = screen.getByRole("slider");
    expect(slider.getAttribute("tabindex")).toBe("0");
    expect(slider.getAttribute("aria-disabled")).toBeNull();
  });
});
