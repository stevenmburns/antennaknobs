/**
 * "Custom…" in the band picker (#1487): a band for a frequency the design's
 * band table does not cover.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BandDropdown } from "../components/params/BandDropdown";
import type { BandSpec } from "../lib/params";

const BANDS: BandSpec[] = [
  { key: "2m", label: "2m", freq_mhz: 146, min_mhz: 144, max_mhz: 148 },
  { key: "70cm", label: "70cm", freq_mhz: 435, min_mhz: 420, max_mhz: 450 },
];

function input(name: string) {
  return screen.getByRole("spinbutton", { name }) as HTMLInputElement;
}

describe("BandDropdown custom band (#1487)", () => {
  it("offers no Custom… entry without onCustom", async () => {
    const user = userEvent.setup();
    render(
      <BandDropdown bands={BANDS} value="2m" onSelect={() => {}} ariaLabel="band" />,
    );
    await user.click(screen.getByRole("button", { name: "band" }));
    expect(screen.getAllByRole("option")).toHaveLength(2);
    expect(screen.queryByRole("option", { name: "Custom…" })).toBeNull();
  });

  it("prefills the current frequency and applies a centre with the default ±1.5 % span", async () => {
    const user = userEvent.setup();
    const onCustom = vi.fn();
    const onSelect = vi.fn();
    render(
      <BandDropdown
        bands={BANDS}
        value="2m"
        onSelect={onSelect}
        onCustom={onCustom}
        customSeedMhz={146}
        ariaLabel="band"
      />,
    );
    await user.click(screen.getByRole("button", { name: "band" }));
    await user.click(screen.getByRole("option", { name: "Custom…" }));
    expect(input("centre (MHz)").value).toBe("146");
    expect(input("span (MHz)").value).toBe("4.38");

    await user.clear(input("centre (MHz)"));
    await user.type(input("centre (MHz)"), "300");
    // An untouched span follows the centre.
    expect(input("span (MHz)").value).toBe("9");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(onCustom).toHaveBeenCalledWith(300, 9);
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.queryByRole("form", { name: "band custom" })).toBeNull();
  });

  it("keeps a typed span, submits on Enter, and refuses an empty centre by name", async () => {
    const user = userEvent.setup();
    const onCustom = vi.fn();
    render(
      <BandDropdown
        bands={BANDS}
        value="70cm"
        onSelect={() => {}}
        onCustom={onCustom}
        customSeedMhz={435}
        ariaLabel="measurement band"
      />,
    );
    await user.click(screen.getByRole("button", { name: "measurement band" }));
    await user.click(screen.getByRole("option", { name: "Custom…" }));

    await user.clear(input("span (MHz)"));
    await user.type(input("span (MHz)"), "20");
    await user.clear(input("centre (MHz)"));
    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByRole("alert").textContent).toBe(
      "centre must be a positive frequency",
    );
    expect(onCustom).not.toHaveBeenCalled();

    await user.type(input("centre (MHz)"), "900");
    expect(input("span (MHz)").value).toBe("20");
    await user.type(input("centre (MHz)"), "{Enter}");
    expect(onCustom).toHaveBeenCalledWith(900, 20);
  });

  it("refuses a span wider than twice the centre, and Escape closes the form", async () => {
    const user = userEvent.setup();
    const onCustom = vi.fn();
    render(
      <BandDropdown
        bands={BANDS}
        value="2m"
        onSelect={() => {}}
        onCustom={onCustom}
        customSeedMhz={10}
        ariaLabel="band"
      />,
    );
    await user.click(screen.getByRole("button", { name: "band" }));
    await user.click(screen.getByRole("option", { name: "Custom…" }));
    await user.clear(input("span (MHz)"));
    await user.type(input("span (MHz)"), "25");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByRole("alert").textContent).toBe(
      "span must be less than twice the centre",
    );
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("form", { name: "band custom" })).toBeNull();
    expect(onCustom).not.toHaveBeenCalled();
  });
});
