// The Z-vs-parameter header's number boxes (Steve, 2026-09-26): typing 101
// into "points" jumped to 20, then 40, because every keystroke was committed
// and clamped. They now edit as free text and commit on blur / Enter.
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ZParamControls } from "../components/results/ZParamControls";
import { DEFAULT_DENSITY_SPEC, paramValues, type ParamSweepSpec } from "../lib/paramSweep";

function Harness({
  initial = DEFAULT_DENSITY_SPEC,
  onSpec,
}: {
  initial?: ParamSweepSpec;
  onSpec: (s: ParamSweepSpec) => void;
}) {
  const [spec, setSpec] = useState(initial);
  return (
    <ZParamControls
      spec={spec}
      knobs={[]}
      densityLabel="density"
      onSpec={(s) => {
        onSpec(s);
        setSpec(s);
      }}
      onParam={() => {}}
      onReset={() => {}}
      isDefault={false}
      values={paramValues(spec, true)}
    />
  );
}

// By label, so the same query finds the box in the old and new controls.
const box = (name: string) => screen.getByLabelText(name) as HTMLInputElement;

describe("the points box", () => {
  it("typing 101 character by character ends as 101", async () => {
    const user = userEvent.setup();
    const onSpec = vi.fn();
    render(<Harness onSpec={onSpec} />);
    await user.clear(box("points"));
    await user.type(box("points"), "101");
    // Nothing rewrote it mid-entry, and nothing committed yet.
    expect(box("points").value).toBe("101");
    expect(onSpec).not.toHaveBeenCalled();
    await user.tab();
    expect(onSpec).toHaveBeenLastCalledWith(expect.objectContaining({ points: 101 }));
    expect(box("points").value).toBe("101");
  });

  it("a lone 1 stays 1 until blur, and then reverts with the range as a hint", async () => {
    const user = userEvent.setup();
    const onSpec = vi.fn();
    render(<Harness onSpec={onSpec} />);
    await user.clear(box("points"));
    await user.type(box("points"), "1");
    expect(box("points").value).toBe("1");
    expect(onSpec).not.toHaveBeenCalled();
    await user.tab();
    expect(onSpec).not.toHaveBeenCalled();
    expect(box("points").value).toBe("7");
    expect(screen.getByRole("status").textContent).toBe("2–201");
  });

  it("an out-of-range count on Enter reverts with the hint", async () => {
    const user = userEvent.setup();
    const onSpec = vi.fn();
    render(<Harness onSpec={onSpec} />);
    await user.clear(box("points"));
    await user.type(box("points"), "5000{Enter}");
    expect(onSpec).not.toHaveBeenCalled();
    expect(box("points").value).toBe("7");
    expect(screen.getByRole("status").textContent).toBe("2–201");
  });

  it("a big count on a narrow integer range shows the rungs actually solved", async () => {
    const user = userEvent.setup();
    render(<Harness onSpec={() => {}} />);
    await user.clear(box("points"));
    await user.type(box("points"), "101{Enter}");
    // 101 geometric steps over 8…68, rounded, repeat at the coarse end:
    // 57 distinct segment counts are solved.
    expect(screen.getByText(/→\s*57\s*rungs/)).toBeTruthy();
  });

  it("arrow keys step and commit", async () => {
    const user = userEvent.setup();
    const onSpec = vi.fn();
    render(<Harness onSpec={onSpec} />);
    await user.click(box("points"));
    await user.keyboard("{ArrowUp}");
    expect(onSpec).toHaveBeenLastCalledWith(expect.objectContaining({ points: 8 }));
  });
});

describe("the from / to boxes", () => {
  it("accept 0.8 and 500 typed character by character, committing once on blur", async () => {
    const user = userEvent.setup();
    const onSpec = vi.fn();
    render(<Harness onSpec={onSpec} />);
    await user.clear(box("from"));
    await user.type(box("from"), "0.8");
    expect(box("from").value).toBe("0.8");
    await user.clear(box("to"));
    await user.type(box("to"), "500");
    expect(box("to").value).toBe("500");
    // The blur of "from" (tabbing on to "to") committed it, once.
    expect(onSpec).toHaveBeenCalledTimes(1);
    expect(onSpec).toHaveBeenLastCalledWith(expect.objectContaining({ lo: 0.8 }));
    await user.tab();
    expect(onSpec).toHaveBeenLastCalledWith(expect.objectContaining({ lo: 0.8, hi: 500 }));
  });
});
