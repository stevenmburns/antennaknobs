// AK#1737: the Antenna view's orientation setting, through useViewState.
// The issue's gates, one describe each:
//   - "auto" reproduces today's per-design views exactly;
//   - "iso" gives Iso on a design whose guess is xy, and again after a switch;
//   - a hand change in the session is not reverted until the next load.
// Plus the two seams the hook owns beyond the switch effect: the deferred
// design's guess arriving later (snapToDesignView, called where the /geometry
// preview lands) and a change of the setting mid-session.
import { describe, it, expect } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { type View } from "../lib/view";
import { type Orientation } from "../lib/settings";
import type { ExampleDescriptor } from "../lib/params";
import { useViewState } from "../components/session/useViewState";
import { HARNESS_EXAMPLE } from "./designSessionHarness";

const PINNED: View[] = ["antenna", "azimuth", "elevation", "smith"];

function design(
  name: string,
  default_view: ExampleDescriptor["default_view"],
): ExampleDescriptor {
  return { ...HARNESS_EXAMPLE, name, default_view };
}

const FLAT = design("flat.xy", "xy"); // a horizontal loop: guessed Top
const TALL = design("tall.yz", "yz"); // a vertical in y: guessed Side
const BEAM = design("beam.xz", "xz"); // guessed Front
const USER = design("user.deferred", null); // guess arrives with the preview

function mount(orientation: Orientation | undefined, first: ExampleDescriptor) {
  return renderHook(
    ({ ex }: { ex: ExampleDescriptor }) =>
      useViewState({
        currentExample: ex,
        active: true,
        pinned: PINNED,
        ...(orientation ? { orientation } : {}),
      }),
    { initialProps: { ex: first } },
  );
}

describe("auto: the per-design guess, as before the setting", () => {
  it("is the default, and follows each design's guess across switches", () => {
    const { result, rerender } = mount(undefined, FLAT);
    expect(result.current.orientation).toBe("auto");
    expect(result.current.cameraProjection).toBe("xy");
    rerender({ ex: TALL });
    expect(result.current.cameraProjection).toBe("yz");
    rerender({ ex: BEAM });
    expect(result.current.cameraProjection).toBe("xz");
    rerender({ ex: FLAT });
    expect(result.current.cameraProjection).toBe("xy");
  });

  it("holds the camera for a deferred design until its preview reports a guess", () => {
    const { result, rerender } = mount("auto", TALL);
    rerender({ ex: USER });
    expect(result.current.cameraProjection).toBe("yz");
    act(() => result.current.snapToDesignView("xy"));
    expect(result.current.cameraProjection).toBe("xy");
    // A preview with no guess changes nothing.
    act(() => result.current.snapToDesignView(undefined));
    expect(result.current.cameraProjection).toBe("xy");
  });
});

describe("a fixed orientation wins over the guess at every load", () => {
  it("iso on a design guessed xy, and again after switching designs", () => {
    const { result, rerender } = mount("iso", FLAT);
    expect(result.current.cameraProjection).toBe("iso");
    rerender({ ex: TALL });
    expect(result.current.cameraProjection).toBe("iso");
    rerender({ ex: FLAT });
    expect(result.current.cameraProjection).toBe("iso");
  });

  it("maps top / front / side to the view switch's own projections", () => {
    const want: [Orientation, string][] = [
      ["top", "xy"],
      ["front", "xz"],
      ["side", "yz"],
    ];
    for (const [o, p] of want) {
      // A design whose guess is none of the three, so the setting shows.
      const { result } = mount(o, design(`d.${o}`, o === "top" ? "yz" : "xy"));
      expect(result.current.cameraProjection).toBe(p);
    }
  });

  it("applies to a deferred design at once, and its late guess does not undo it", () => {
    const { result, rerender } = mount("iso", FLAT);
    act(() => result.current.setCameraProjection("xz"));
    rerender({ ex: USER });
    expect(result.current.cameraProjection).toBe("iso");
    act(() => result.current.snapToDesignView("yz"));
    expect(result.current.cameraProjection).toBe("iso");
  });
});

describe("a hand change lasts until the next design load", () => {
  it("survives re-renders of the same design, then the setting comes back", () => {
    const { result, rerender } = mount("iso", FLAT);
    act(() => result.current.setCameraProjection("xz"));
    // Same design, fresh descriptor object (a catalog refresh): no reset.
    rerender({ ex: { ...FLAT } });
    rerender({ ex: { ...FLAT, default_view: "yz" } });
    expect(result.current.cameraProjection).toBe("xz");
    rerender({ ex: TALL });
    expect(result.current.cameraProjection).toBe("iso");
  });

  it("under auto too: the hand pick holds until a switch brings the guess back", () => {
    const { result, rerender } = mount("auto", FLAT);
    act(() => result.current.setCameraProjection("iso"));
    rerender({ ex: { ...FLAT } });
    expect(result.current.cameraProjection).toBe("iso");
    rerender({ ex: TALL });
    expect(result.current.cameraProjection).toBe("yz");
  });
});

describe("changing the setting in the session", () => {
  it("applies at once, sticks for later loads, and auto returns to the guess", () => {
    const { result, rerender } = mount("auto", FLAT);
    act(() => result.current.setOrientation("iso"));
    expect(result.current.orientation).toBe("iso");
    expect(result.current.cameraProjection).toBe("iso");
    rerender({ ex: TALL });
    expect(result.current.cameraProjection).toBe("iso");
    act(() => result.current.setOrientation("auto"));
    // TALL's own guess, not the first design's.
    expect(result.current.cameraProjection).toBe("yz");
    rerender({ ex: BEAM });
    expect(result.current.cameraProjection).toBe("xz");
  });

  it("back to auto on a deferred design returns to its preview's guess", () => {
    const { result, rerender } = mount("iso", FLAT);
    rerender({ ex: USER });
    act(() => result.current.snapToDesignView("yz"));
    expect(result.current.cameraProjection).toBe("iso");
    act(() => result.current.setOrientation("auto"));
    expect(result.current.cameraProjection).toBe("yz");
  });
});
