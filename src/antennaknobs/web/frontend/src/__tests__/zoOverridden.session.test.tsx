// AK#2116 — a gear-menu Zo override says so wherever the reference is shown.
// The override persists per design with no expiry (lib/zoOverride.ts), so a
// design whose file later names another Zo kept measuring against the old
// override with nothing on screen saying the reference was not its own. The
// marker is "Overridden", shown while the session's Zo differs from the
// design's (`zo.value !== zo.design`, ZoField's test), and it leads to the
// gear menu's field, which has the reset.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen, fireEvent, render, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { mountReady, HARNESS_EXAMPLE } from "./designSessionHarness";
import { ZO_STORAGE_KEY } from "../lib/zoOverride";
import { SmithChart } from "../components/charts/SmithChart";
import { SolveReadout } from "../components/results/SolveReadout";
import { ZoOpenContext, ZoOverriddenContext } from "../components/session/zoOpen";
import type { SolveResponse } from "../lib/api";

const DESIGN_ZO = 75;
const TITLE = "Design's own: 75 Ω. Click to change or reset.";

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

const routes = {
  "/geometry": (_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
    return jsonResponse({
      geometry: HARNESS_EXAMPLE.name,
      wires: [],
      z0_ohms: typeof body.z0_ohms === "number" ? body.z0_ohms : DESIGN_ZO,
      design_z0_ohms: DESIGN_ZO,
    });
  },
};

const zoInput = () =>
  screen.getByLabelText("Reference impedance Zo, ohms") as HTMLInputElement;
const openGear = () => fireEvent.click(screen.getByLabelText("Tools menu"));
function typeZo(text: string) {
  fireEvent.change(zoInput(), { target: { value: text } });
  fireEvent.keyDown(zoInput(), { key: "Enter" });
}
const markers = () => screen.queryAllByText(/Overridden/);

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("the readout marks an overridden Zo (AK#2116)", () => {
  it("shows Overridden while the Zo differs, and clears on reset with no solve", async () => {
    await mountReady({ routes });
    expect(markers()).toHaveLength(0);
    openGear();
    typeZo("200");
    const label = screen.getByRole("button", { name: "SWR (200 Ω, Overridden)" });
    expect(label.getAttribute("title")).toBe(TITLE);
    fireEvent.click(screen.getByRole("button", { name: "reset" }));
    expect(screen.queryByRole("button", { name: /Overridden/ })).toBeNull();
    expect(markers()).toHaveLength(0);
    expect(screen.getByText(`SWR (${DESIGN_ZO} Ω)`)).toBeTruthy();
  });

  it("never appears when the design's own value is typed", async () => {
    await mountReady({ routes });
    openGear();
    typeZo("75");
    expect(markers()).toHaveLength(0);
    typeZo("75.0");
    expect(markers()).toHaveLength(0);
    expect(localStorage.getItem(ZO_STORAGE_KEY)).toBeNull();
  });

  it("a stored override is marked from the first paint after a reload", async () => {
    await mountReady({
      routes,
      storage: { [ZO_STORAGE_KEY]: JSON.stringify({ [HARNESS_EXAMPLE.name]: 200 }) },
    });
    expect(screen.getByRole("button", { name: "SWR (200 Ω, Overridden)" })).toBeTruthy();
  });

  it("clicking the marker opens the gear menu at the Z₀ field, focused", async () => {
    await mountReady({
      routes,
      storage: { [ZO_STORAGE_KEY]: JSON.stringify({ [HARNESS_EXAMPLE.name]: 200 }) },
    });
    expect(screen.queryByLabelText("Reference impedance Zo, ohms")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "SWR (200 Ω, Overridden)" }));
    expect(zoInput().value).toBe("200");
    // Focus is only readable off the document.
    // eslint-disable-next-line testing-library/no-node-access
    expect(document.activeElement).toBe(zoInput());
    expect(screen.getByRole("button", { name: "reset" })).toBeTruthy();
  });

  it("the optimizer's menu marks it, and the marker leads to the field", async () => {
    await mountReady({
      routes,
      storage: { [ZO_STORAGE_KEY]: JSON.stringify({ [HARNESS_EXAMPLE.name]: 200 }) },
    });
    fireEvent.click(screen.getByLabelText("Optimisation method"));
    const line = screen.getByText(/SWR and Match Z₀ are against 200 Ω/);
    const marker = within(line).getByRole("button", { name: "Overridden" });
    expect(marker.getAttribute("title")).toBe(TITLE);
    fireEvent.click(marker);
    // eslint-disable-next-line testing-library/no-node-access
    expect(document.activeElement).toBe(zoInput());
  });

  it("the stage's Smith chart marks it beside its Z₀ corner", async () => {
    const { container } = await mountReady({
      routes,
      layout: "grid",
      pinned: ["smith", "vswr", "antenna"],
      storage: { [ZO_STORAGE_KEY]: JSON.stringify({ [HARNESS_EXAMPLE.name]: 200 }) },
    });
    // eslint-disable-next-line testing-library/no-node-access
    const chart = container.querySelector<HTMLElement>(".grid-cell .smith-chart")!;
    const marker = within(chart).getByRole("button", { name: "Overridden" });
    expect(marker.getAttribute("title")).toBe(TITLE);
    fireEvent.click(marker);
    // eslint-disable-next-line testing-library/no-node-access
    expect(document.activeElement).toBe(zoInput());
  });
});

// The components on their own: the marker follows the context, and only it.
const smithBase: ComponentProps<typeof SmithChart> = {
  r: 70,
  x: 20,
  z0: 200,
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

describe("the Overridden marker, component by component (AK#2116)", () => {
  it("the Smith chart marks only a Zo that is not the design's", () => {
    const open = vi.fn();
    const { rerender } = render(
      <ZoOpenContext.Provider value={open}>
        <ZoOverriddenContext.Provider value={75}>
          <SmithChart {...smithBase} />
        </ZoOverriddenContext.Provider>
      </ZoOpenContext.Provider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Overridden" }));
    expect(open).toHaveBeenCalledTimes(1);
    rerender(
      <ZoOpenContext.Provider value={open}>
        <ZoOverriddenContext.Provider value={null}>
          <SmithChart {...smithBase} z0={75} />
        </ZoOverriddenContext.Provider>
      </ZoOpenContext.Provider>,
    );
    expect(screen.queryByText("Overridden")).toBeNull();
    // No session: nothing to compare against, nothing marked.
    rerender(<SmithChart {...smithBase} />);
    expect(screen.queryByText("Overridden")).toBeNull();
  });

  it("the collapsed readout pill carries the marker too", () => {
    const result = {
      z_in_re: 50,
      z_in_im: 0,
      z0_ohms: 200,
      wires: [],
      feed_wire_index: 0,
    } as unknown as SolveResponse;
    render(
      <ZoOverriddenContext.Provider value={75}>
        <SolveReadout
          result={result}
          rttMs={null}
          currentExample={undefined}
          effectiveMultiFeed={false}
          normCheck={null}
          normCheckEnabled={false}
          z0={200}
          collapsed
          onCollapsedChange={() => {}}
        />
      </ZoOverriddenContext.Provider>,
    );
    const pill = screen.getByRole("button", { name: /Show the full solve readout/ });
    const marker = within(pill).getByText(/Overridden/);
    expect(marker.textContent).toBe(" (200 Ω, Overridden)");
    expect(marker.getAttribute("title")).toBe(TITLE);
  });
});
