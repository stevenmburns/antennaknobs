// The far-field chart's corner captions live in the stage's overlay stacks,
// where no control can cover them (AC6LA's zoomed display, QRZ #115), and the
// peak readout says WHERE the maximum is (AK#1632): the slice max's angle for
// free, the whole pattern's max on one click, and a second click aims both
// cuts through it.
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { slicePeakAngleDeg } from "../components/charts/cuts";
import {
  CompareOverlay,
  FarFieldOverlayControls,
} from "../components/results/StageOverlays";
import type {
  FarFieldCaptions,
  PatternMetrics,
} from "../components/charts/types";

describe("slicePeakAngleDeg", () => {
  // 8 uniform samples: sample i sits at 45·i degrees.
  const at = (i: number) =>
    Array.from({ length: 8 }, (_, k) => (k === i ? 5 : -3));

  it("reads an azimuth cut's peak as its bearing, 0-360", () => {
    expect(slicePeakAngleDeg({ dbi: at(2) }, "xy")).toBe(90);
    expect(slicePeakAngleDeg({ dbi: at(7) }, "xy")).toBe(315);
  });

  it("reads an elevation cut up and over, negative below the horizon", () => {
    expect(slicePeakAngleDeg({ dbi: at(1) }, "yz")).toBe(45);
    // Past the zenith: the far side's elevation, as EZNEC reads 122°.
    expect(slicePeakAngleDeg({ dbi: at(3) }, "yz")).toBe(135);
    expect(slicePeakAngleDeg({ dbi: at(7) }, "yz")).toBe(-45);
  });

  it("uses a refined trace's own angles", () => {
    const t = { dbi: [1, 4, 2], anglesDeg: [0, 12.5, 30] };
    expect(slicePeakAngleDeg(t, "yz")).toBe(12.5);
  });
});

const CAPTIONS: FarFieldCaptions = {
  cut: "yz",
  cutLabel: "elev @ 0° az (dBi)",
  peakDbi: 6.78,
  peakAngleDeg: 0,
  field: null,
  belowGroundPct: null,
  necOverlay: true,
};

const METRICS: PatternMetrics = {
  peak_gain_dbi: 6.8,
  takeoff_deg: 12.2,
  azimuth_deg: 359.6,
  front_to_back_db: 20,
  az_beamwidth_deg: 180,
  el_beamwidth_deg: 40,
};

function controls(
  over: Partial<Parameters<typeof FarFieldOverlayControls>[0]>,
) {
  return render(
    <FarFieldOverlayControls
      isMobile={false}
      normCheckEnabled={false}
      setNormCheckEnabled={() => {}}
      normCheck={null}
      backend="nec5"
      groundModel="sommerfeld"
      necOverlayEnabled
      setNecOverlayEnabled={() => {}}
      captions={CAPTIONS}
      maxMetrics={null}
      maxPending={false}
      canFindMax
      onFindMax={() => {}}
      onAimAtMax={() => {}}
      onDismissMax={() => {}}
      {...over}
    />,
  );
}

describe("the peak readout", () => {
  it("says where the slice max is", () => {
    controls({});
    expect(screen.getByText("peak +6.8 dBi @ el 0°")).toBeTruthy();
  });

  it("fetches the 3-D max only when asked", () => {
    const onFindMax = vi.fn();
    controls({ onFindMax });
    fireEvent.click(screen.getByRole("button", { name: "find 3-D max" }));
    expect(onFindMax).toHaveBeenCalledOnce();
  });

  it("says it is finding, and cannot be asked twice", () => {
    controls({ maxPending: true });
    const b = screen.getByRole("button", { name: "finding 3-D max…" });
    expect((b as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows the 3-D max and aims through it on a click", () => {
    const onAimAtMax = vi.fn();
    controls({ maxMetrics: METRICS, onAimAtMax });
    const b = screen.getByRole("button", {
      // 359.6° rounds to 360, which is the 0° bearing the aim goes to.
      name: "3-D max +6.8 dBi @ az 0°, el 12°",
    });
    fireEvent.click(b);
    expect(onAimAtMax).toHaveBeenCalledWith(METRICS);
  });

  it("dismisses the 3-D max with its ×", () => {
    const onDismissMax = vi.fn();
    const onAimAtMax = vi.fn();
    controls({ maxMetrics: METRICS, onDismissMax, onAimAtMax });
    fireEvent.click(
      screen.getByRole("button", { name: "Dismiss the 3-D max" }),
    );
    expect(onDismissMax).toHaveBeenCalledOnce();
    expect(onAimAtMax).not.toHaveBeenCalled();
  });

  it("cannot be asked while a solve is in flight", () => {
    controls({ canFindMax: false });
    const b = screen.getByRole("button", { name: "find 3-D max" });
    expect((b as HTMLButtonElement).disabled).toBe(true);
  });

  it("carries the NEC legend on its own switch", () => {
    controls({});
    expect(screen.getByLabelText("dashed cyan line")).toBeTruthy();
    controls({ captions: { ...CAPTIONS, necOverlay: false } });
    expect(screen.getAllByLabelText("dashed cyan line")).toHaveLength(1);
  });
});

describe("the cut label", () => {
  it("sits in the compare stack, above the Pin button", () => {
    render(
      <CompareOverlay
        pinCurrentPattern={() => {}}
        setCompareCollapsed={() => {}}
        result={null}
        pinnedPatterns={[]}
        compareCollapsed
        clearPins={() => {}}
        liveMetrics={null}
        currentExample={undefined}
        geometry="dipole"
        measFreq={14}
        removePin={() => {}}
        togglePin={() => {}}
        cutLabel="elev @ 0° az (dBi)"
      />,
    );
    const label = screen.getByText("elev @ 0° az (dBi)");
    const pin = screen.getByRole("button", { name: /Pin pattern/ });
    expect(
      label.compareDocumentPosition(pin) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});
