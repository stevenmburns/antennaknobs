// AK#1738 through the real <DesignSession>, in grid layout so the Smith,
// VSWR and S11 charts are all on the stage at once:
//   - the three charts' freq-sweep switches are ONE switch (and the Tools
//     menu's is the same one);
//   - a range picked on a chart's axis persists in the view prefs and is
//     what that chart then draws; the other chart stays on Auto.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mountDesignSession } from "./designSessionHarness";
import { VIEW_PREFS_KEY } from "../components/session/useViewPrefs";

afterEach(() => {
  vi.unstubAllGlobals();
});

const sweepBoxes = () =>
  screen
    .getAllByRole("checkbox", { name: "freq sweep" })
    .map((c) => (c as HTMLInputElement).checked);

describe("the sweep charts share one freq-sweep switch (AK#1738)", () => {
  it("unchecking it on the VSWR chart unchecks it on Smith, S11 and the Tools menu", async () => {
    const user = userEvent.setup();
    const { container } = mountDesignSession({
      layout: "grid",
      pinned: ["smith", "vswr", "gamma", "antenna"],
    });
    await waitFor(
      () => expect(container.querySelector('canvas.sweep[data-mode="vswr"]')).not.toBeNull(),
      { timeout: 5000 },
    );
    // Smith, VSWR and S11 each carry the switch.
    expect(sweepBoxes()).toEqual([true, true, true]);
    const vswrCell = container
      .querySelector('canvas.sweep[data-mode="vswr"]')!
      .closest(".grid-cell") as HTMLElement;
    const vswrBox = screen
      .getAllByRole("checkbox", { name: "freq sweep" })
      .find((b) => vswrCell.contains(b))!;
    expect(vswrBox).toBeTruthy();
    await user.click(vswrBox);
    expect(sweepBoxes()).toEqual([false, false, false]);
    await user.click(await screen.findByRole("button", { name: "Tools menu" }));
    expect(sweepBoxes()).toEqual([false, false, false, false]);
  });
});

describe("a chart's range persists in the view prefs", () => {
  it("a VSWR preset is stored sparsely and drawn; S11 stays on Auto", async () => {
    const user = userEvent.setup();
    const { container } = mountDesignSession({
      layout: "grid",
      pinned: ["smith", "vswr", "gamma", "antenna"],
    });
    await waitFor(
      () => expect(container.querySelector('canvas.sweep[data-mode="vswr"]')).not.toBeNull(),
      { timeout: 5000 },
    );
    await user.click(
      screen.getByRole("button", { name: "VSWR range and SWR threshold" }),
    );
    await user.click(screen.getByRole("button", { name: "1–2" }));
    const vswr = container.querySelector('canvas.sweep[data-mode="vswr"]') as HTMLElement;
    expect(vswr.dataset.yHi).toBe("2");
    expect(vswr.dataset.axis).toBe("fixed");
    const gamma = container.querySelector('canvas.sweep[data-mode="gamma"]') as HTMLElement;
    expect(gamma.dataset.axis).toBe("auto");
    const stored = JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "{}");
    expect(stored.sweepAxes).toEqual({ vswr: { kind: "fixed", lo: 1, hi: 2 } });
    expect(stored.swrThreshold).toBeUndefined();
  });
});
