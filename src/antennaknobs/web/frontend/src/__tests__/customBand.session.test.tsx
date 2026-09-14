/**
 * A custom band through a real <DesignSession> (#1487).
 *
 * Before this, a design could not be set to 300 MHz from the UI at all. The
 * design slider stopped at its band's edges. The measurement dial clamped a
 * typed 300 to 0.8–1.25× of the selected band's centre: 182.5 on 2 m, 348 on
 * 70 cm. This test drives both pickers' "Custom…" and reads back the controls
 * the user sees.
 */
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { BandSpec, ExampleDescriptor } from "../lib/params";
import { HARNESS_EXAMPLE, mountDesignSession } from "./designSessionHarness";

const BANDS: BandSpec[] = [
  { key: "2m", label: "2m", freq_mhz: 146, min_mhz: 144, max_mhz: 148 },
  { key: "70cm", label: "70cm", freq_mhz: 435, min_mhz: 420, max_mhz: 450 },
];

const VHF: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: BANDS,
  default_freq: 146,
  default_design_freq: 146,
};

// A deck with no FR card: the importer seeds 14 MHz and no dial range, and
// the served table is the amateur set.
const NO_FR_DECK: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  bands: [
    { key: "20m", label: "20m", freq_mhz: 14.175, min_mhz: 14, max_mhz: 14.35 },
    ...BANDS,
  ],
  default_freq: 14,
  default_design_freq: 14,
};

// A deck-like design: the FR card seeded a dial range, which a custom
// measurement band must be able to leave.
const DECK: ExampleDescriptor = {
  ...VHF,
  meas_freq_range_mhz: [144, 148],
  has_design_freq: false,
};

function lcd(container: HTMLElement) {
  return container.querySelector(".freq-lcd .lcd-live")?.textContent;
}

function dial() {
  const k = screen.getByRole("slider", { name: "measurement frequency" });
  return [Number(k.getAttribute("aria-valuemin")), Number(k.getAttribute("aria-valuemax"))];
}

async function applyCustom(
  user: ReturnType<typeof userEvent.setup>,
  picker: string,
  centre: string,
  span?: string,
) {
  await user.click(screen.getByRole("button", { name: picker }));
  await user.click(screen.getByRole("option", { name: "Custom…" }));
  const c = screen.getByRole("spinbutton", { name: "centre (MHz)" });
  await user.clear(c);
  await user.type(c, centre);
  if (span != null) {
    const s = screen.getByRole("spinbutton", { name: "span (MHz)" });
    await user.clear(s);
    await user.type(s, span);
  }
  await user.click(screen.getByRole("button", { name: "Apply" }));
}

describe("custom band in the session (#1487)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("puts the design and the locked dial on 300 MHz, and the unlocked dial on its window", async () => {
    const user = userEvent.setup();
    const { container } = mountDesignSession({ examples: [VHF] });
    await waitFor(() => expect(lcd(container)).toBe("146.000"));

    await applyCustom(user, "band", "300");

    await waitFor(() => expect(lcd(container)).toBe("300.000"));
    expect(screen.getByText("300.000 MHz")).toBeTruthy();
    expect(screen.getByRole("button", { name: "band" }).textContent).toContain(
      "custom 300 MHz",
    );
    const slider = screen.getByRole("slider", {
      name: "design frequency",
    }) as HTMLInputElement;
    expect(Number(slider.min)).toBeCloseTo(295.5);
    expect(Number(slider.max)).toBeCloseTo(304.5);

    await user.click(
      screen.getByRole("button", {
        name: "Lock measurement frequency to the design frequency",
      }),
    );
    await waitFor(() => {
      const [lo, hi] = dial();
      expect(lo).toBeCloseTo(240);
      expect(hi).toBeCloseTo(375);
    });

    // A second custom band on the measurement picker leaves the design alone,
    // and the dial's ceiling grows with it past the served 70 cm table.
    await applyCustom(user, "measurement band", "900", "20");
    await waitFor(() => expect(lcd(container)).toBe("900.000"));
    expect(screen.getByText("300.000 MHz")).toBeTruthy();
    const [lo, hi] = dial();
    expect(lo).toBeCloseTo(720);
    expect(hi).toBeCloseTo(1125);
    await user.click(screen.getByRole("button", { name: "measurement band" }));
    const labels = screen.getAllByRole("option").map((o) => o.textContent);
    expect(labels).toEqual([
      "2m",
      "70cm",
      "custom 300 MHz",
      "custom 900 MHz",
      "Custom…",
    ]);
  });

  it("re-locks an unlocked measurement dial to a custom design band", async () => {
    const user = userEvent.setup();
    const { container } = mountDesignSession({ examples: [VHF] });
    await waitFor(() => expect(lcd(container)).toBe("146.000"));
    const lock = screen.getByRole("button", {
      name: "Lock measurement frequency to the design frequency",
    });
    await user.click(lock);
    await waitFor(() => expect(lock.getAttribute("aria-pressed")).toBe("false"));
    await user.click(screen.getByRole("button", { name: "measurement band" }));
    await user.click(screen.getByRole("option", { name: "70cm" }));
    await waitFor(() => expect(lcd(container)).toBe("435.000"));

    await applyCustom(user, "band", "300");

    await waitFor(() => expect(lcd(container)).toBe("300.000"));
    expect(lock.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "measurement band" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("sets 300 MHz on a deck with no FR card, from its 14 MHz default", async () => {
    const user = userEvent.setup();
    const { container } = mountDesignSession({ examples: [NO_FR_DECK] });
    await waitFor(() => expect(lcd(container)).toBe("14.000"));

    await applyCustom(user, "band", "300");

    await waitFor(() => expect(lcd(container)).toBe("300.000"));
    expect(screen.getByText("300.000 MHz")).toBeTruthy();
  });

  it("lets a custom measurement band leave a deck's FR-seeded dial range", async () => {
    const user = userEvent.setup();
    const { container } = mountDesignSession({ examples: [DECK] });
    await waitFor(() => expect(lcd(container)).toBe("146.000"));
    expect(dial()).toEqual([144, 148]);

    await applyCustom(user, "measurement band", "300");

    await waitFor(() => expect(lcd(container)).toBe("300.000"));
    const [lo, hi] = dial();
    expect(lo).toBeCloseTo(240);
    expect(hi).toBeCloseTo(375);
  });
});
