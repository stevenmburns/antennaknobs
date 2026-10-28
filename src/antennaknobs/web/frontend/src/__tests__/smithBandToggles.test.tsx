// The band list's toggles on the Smith chart (Steve, 2026-10-28): the bands
// read-only, one click to show or hide each one's Z as a knob turns, none on
// to start with. Only the stage chart carries them.
import { describe, it, expect } from "vitest";
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { SmithBandToggles } from "../components/charts/SmithBandToggles";

function Harness({ freqs }: { freqs: number[] }) {
  const [shown, setShown] = useState<number[]>([]);
  return (
    <>
      <SmithBandToggles picker={{ freqs, shown, setShown }} />
      <output data-testid="shown">{JSON.stringify(shown)}</output>
    </>
  );
}

const shown = () => JSON.parse(screen.getByTestId("shown").textContent ?? "[]") as number[];

describe("SmithBandToggles", () => {
  it("lists every band, none shown, and toggles each with a click", () => {
    render(<Harness freqs={[24.97, 28.47]} />);
    const b12 = screen.getByRole("button", { name: "24.97" });
    const b10 = screen.getByRole("button", { name: "28.47" });
    expect(b12.getAttribute("aria-pressed")).toBe("false");
    expect(shown()).toEqual([]);
    fireEvent.click(b10);
    expect(shown()).toEqual([28.47]);
    expect(b10.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(b12);
    expect(shown()).toEqual([28.47, 24.97]);
    fireEvent.click(b10);
    expect(shown()).toEqual([24.97]);
  });

  it("names a band the design declares, the frequency otherwise (AK#2108)", () => {
    render(
      <SmithBandToggles
        picker={{
          freqs: [7.15, 14.175],
          shown: [],
          setShown: () => {},
          labels: new Map([[7.15, "40 m"]]),
        }}
      />,
    );
    expect(screen.getByRole("button", { name: "40 m" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "14.175" })).toBeTruthy();
  });

  it("draws nothing with an empty band list", () => {
    render(<Harness freqs={[]} />);
    expect(screen.queryByRole("group", { name: "Bands on the Smith chart" })).toBeNull();
  });
});
