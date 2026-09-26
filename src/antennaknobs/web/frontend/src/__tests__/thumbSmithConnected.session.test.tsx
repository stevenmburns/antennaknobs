// The Smith thumbnail draws the sweep the way the stage does. With adaptive
// resolution on (the default), the stage's Smith chart connects the sweep
// into a locus; the thumbnail drew a dot cloud until the chart was focused,
// because the thumbnail's ViewPanel never received `refineEnabled`
// (Steve, 2026-09-25, on the default invvee).
import { describe, it, expect, afterEach, vi } from "vitest";
import { mountReady } from "./designSessionHarness";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the Smith thumbnail connects the sweep like the stage", () => {
  it("draws a line, not dots, while another view has the stage", async () => {
    const { container } = await mountReady({
      layout: "rail",
      pinned: ["antenna", "smith", "vswr", "gamma"],
    });
    const thumb = container.querySelector(".thumbstrip canvas.smith") as HTMLElement;
    expect(thumb.dataset.connect).toBe("1");
  });
});
