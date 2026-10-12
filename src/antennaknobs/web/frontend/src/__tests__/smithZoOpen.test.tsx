// AK#1985: the Smith chart's "Z₀ = …" corner opens the reference impedance,
// where the session provides a way to; otherwise it stays plain canvas text.
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { SmithChart } from "../components/charts/SmithChart";
import { ZoOpenContext } from "../components/session/zoOpen";

const base: ComponentProps<typeof SmithChart> = {
  r: 70,
  x: 20,
  z0: 75,
  size: 300,
  sweep: null,
  paramSweep: null,
  measured: null,
  measFreqMhz: 14,
  running: false,
  paramSweepRunning: false,
  multiFeed: false,
  interactive: true,
};

describe("the Smith chart's Z₀ corner (AK#1985)", () => {
  it("opens the reference impedance when the session can", () => {
    const open = vi.fn();
    render(
      <ZoOpenContext.Provider value={open}>
        <SmithChart {...base} />
      </ZoOpenContext.Provider>,
    );
    fireEvent.click(screen.getByLabelText("Reference impedance 75 Ω: change it"));
    expect(open).toHaveBeenCalledTimes(1);
  });

  it("is plain text with no session, and on a thumbnail", () => {
    const { rerender } = render(<SmithChart {...base} />);
    expect(screen.queryByLabelText(/Reference impedance/)).toBeNull();
    rerender(
      <ZoOpenContext.Provider value={vi.fn()}>
        <SmithChart {...base} interactive={false} />
      </ZoOpenContext.Provider>,
    );
    expect(screen.queryByLabelText(/Reference impedance/)).toBeNull();
  });
});
