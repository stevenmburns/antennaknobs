// The Smith thumbnail draws the sweep the way the stage does. With adaptive
// resolution on (the default), the stage's Smith chart connects the sweep
// into a locus; the thumbnail drew a dot cloud until the chart was focused,
// because the thumbnail's ViewPanel never received `refineEnabled`
// (Steve, 2026-09-25, on the default invvee).
import { describe, it, expect } from "vitest";
import { waitFor } from "@testing-library/react";
import { mountDesignSession } from "./designSessionHarness";

describe("the Smith thumbnail connects the sweep like the stage", () => {
  it("draws a line, not dots, while another view has the stage", async () => {
    const { container } = mountDesignSession({
      layout: "rail",
      pinned: ["antenna", "smith", "vswr", "gamma"],
    });
    await waitFor(
      () =>
        expect(container.querySelector(".thumbstrip canvas.smith")).not.toBeNull(),
      { timeout: 5000 },
    );
    const thumb = container.querySelector(".thumbstrip canvas.smith") as HTMLElement;
    expect(thumb.dataset.connect).toBe("1");
  });
});
