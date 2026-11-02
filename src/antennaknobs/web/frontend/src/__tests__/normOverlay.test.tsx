import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { necCutSamples } from "../components/charts/polar";
import { FarFieldOverlayControls } from "../components/results/StageOverlays";
import { cutDbiTop } from "../lib/refine";

// The norm check and its dotted overlay are two switches now: the check feeds
// the readouts' radiated %, and the overlay, off by default, is drawn only on
// request. Over real ground the dotted pattern sits above the gain lobe by the
// ground loss (1.37 dB on the Koch dipole over average ground), and on the
// ARRL scale the highest trace drawn sets the outer ring.

type Props = Parameters<typeof FarFieldOverlayControls>[0];

function controls(over: Partial<Props> = {}) {
  const props = {
    isMobile: false,
    normCheckEnabled: false,
    setNormCheckEnabled: vi.fn(),
    normOverlayEnabled: false,
    setNormOverlayEnabled: vi.fn(),
    normCheck: null,
    backend: "bspline",
    groundModel: "sommerfeld" as const,
    necOverlayEnabled: true,
    setNecOverlayEnabled: vi.fn(),
    captions: null,
    maxMetrics: null,
    maxPending: false,
    canFindMax: false,
    onFindMax: vi.fn(),
    onAimAtMax: vi.fn(),
    onDismissMax: vi.fn(),
    ...over,
  } as Props & {
    setNormCheckEnabled: ReturnType<typeof vi.fn>;
    setNormOverlayEnabled: ReturnType<typeof vi.fn>;
  };
  render(<FarFieldOverlayControls {...props} />);
  return props;
}

describe("the chart's norm overlay box", () => {
  it("shows the overlay switch, not the check's, and starts unchecked", () => {
    controls({ normCheckEnabled: true });
    const box = screen.getByLabelText("norm overlay") as HTMLInputElement;
    expect(box.checked).toBe(false);
  });

  it("turning the overlay on also turns the check on when it was off", () => {
    const p = controls({ normCheckEnabled: false });
    fireEvent.click(screen.getByLabelText("norm overlay"));
    expect(p.setNormOverlayEnabled).toHaveBeenCalledWith(true);
    expect(p.setNormCheckEnabled).toHaveBeenCalledWith(true);
  });

  it("turning it off leaves the check (and the readouts) alone", () => {
    const p = controls({ normCheckEnabled: true, normOverlayEnabled: true });
    fireEvent.click(screen.getByLabelText("norm overlay"));
    expect(p.setNormOverlayEnabled).toHaveBeenCalledWith(false);
    expect(p.setNormCheckEnabled).not.toHaveBeenCalled();
  });
});

describe("the NEC overlay's peak counts toward the outer ring", () => {
  // A 3 x 3 (theta 0/45/90, phi 0/180/360) pattern peaking at 4 dBi on the
  // horizon at phi 0, the elevation cut's t = 0.
  const pattern = {
    theta_deg: [0, 45, 90],
    phi_deg: [0, 180, 360],
    gain_dbi: [
      [-10, -10, -10],
      [0, -3, 0],
      [4, 1, 4],
    ],
  };

  it("samples the cut, null below the horizon", () => {
    const smp = necCutSamples(pattern, "yz", 0, 0, 8);
    expect(smp[0]?.dbi).toBeCloseTo(4, 12); // t = 0: horizon, phi 0
    expect(smp[2]?.dbi).toBeCloseTo(-10, 12); // t = pi/2: zenith
    expect(smp[6]).toBeNull(); // t = 3pi/2: nadir, below the horizon
  });

  it("an NEC lobe above the live one sets the ARRL rim", () => {
    const smp = necCutSamples(pattern, "yz", 0, 0, 8);
    const necPeak = Math.max(...smp.flatMap((s) => (s ? [s.dbi] : [])));
    expect(cutDbiTop([3.8, necPeak], "arrl")).toBeCloseTo(4, 12);
  });
});
