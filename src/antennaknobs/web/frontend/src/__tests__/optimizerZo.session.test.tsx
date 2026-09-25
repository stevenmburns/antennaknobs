// AK#1735 — the optimizer gear menu's Zo field, end to end through a real
// <DesignSession>. AC6LA asked where to set a Zo other than 50 for a built-in
// design with two knobs marked. The design's own reference arrives on the
// /geometry preview (`design_z0_ohms`: a `.ssn` Generator's Zo, or
// ui_params["target_z0"]); the field starts there, an edit becomes the
// session's reference — the SWR readout's label follows it at once, and the
// request carries it as `z0_ohms` — text that is not a Zo is refused where it
// was typed, and the override persists per design across a reload.
//
// The live solve rides the /ws socket, which setup.ts's InertWebSocket keeps
// silent (the harness's documented non-goal), so the request leg is read off
// the /geometry preview the PAUSED branch sends: the same buildRequest() body
// the socket and /optimize get.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { mountDesignSession, HARNESS_EXAMPLE } from "./designSessionHarness";
import { ZO_STORAGE_KEY } from "../lib/zoOverride";

const DESIGN_ZO = 75;

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

// The preview a 75 ohm file design answers with, recording every body.
function geometryRoute(bodies: Record<string, unknown>[]) {
  return {
    "/geometry": (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
      bodies.push(body);
      return jsonResponse({
        geometry: HARNESS_EXAMPLE.name,
        wires: [],
        z0_ohms: typeof body.z0_ohms === "number" ? body.z0_ohms : DESIGN_ZO,
        design_z0_ohms: DESIGN_ZO,
      });
    },
  };
}

const swrLabel = (ohms: number) => screen.findByText(`SWR (${ohms} Ω)`);
const zoInput = () =>
  screen.getByLabelText("Reference impedance Zo, ohms") as HTMLInputElement;
const openGear = () => fireEvent.click(screen.getByLabelText("Optimisation method"));
const stored = () => localStorage.getItem(ZO_STORAGE_KEY);

function typeZo(text: string) {
  fireEvent.change(zoInput(), { target: { value: text } });
  fireEvent.keyDown(zoInput(), { key: "Enter" });
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("the optimizer's Zo field (AK#1735)", () => {
  it("starts at the design's own Zo from the preview, and the readout says so", async () => {
    mountDesignSession({ routes: geometryRoute([]) });
    await swrLabel(DESIGN_ZO);
    openGear();
    expect(zoInput().value).toBe("75");
    expect(screen.getByText(/the design's own/)).toBeTruthy();
    expect(stored()).toBeNull();
  });

  it("an edit becomes the reference: readout label, request body, storage", async () => {
    const bodies: Record<string, unknown>[] = [];
    mountDesignSession({ routes: geometryRoute(bodies) });
    await swrLabel(DESIGN_ZO);
    // Before any edit the request carries no override at all: the same bytes
    // a session sent before the field existed.
    expect(bodies.length).toBeGreaterThan(0);
    for (const b of bodies) expect("z0_ohms" in b).toBe(false);

    openGear();
    typeZo("100");
    await swrLabel(100);
    expect(screen.getByText(/design: 75 Ω/)).toBeTruthy();
    expect(JSON.parse(stored() ?? "null")).toEqual({ [HARNESS_EXAMPLE.name]: 100 });

    // Pause: the paused branch re-previews with the current request.
    const before = bodies.length;
    fireEvent.click(screen.getByRole("button", { name: /Live/ }));
    await waitFor(() => expect(bodies.length).toBeGreaterThan(before));
    expect(bodies[bodies.length - 1].z0_ohms).toBe(100);
  });

  it.each(["abc", "0", "-50", "", "75 ohm", "Infinity"])(
    "refuses %j visibly and keeps the reference",
    async (bad) => {
      mountDesignSession({ routes: geometryRoute([]) });
      await swrLabel(DESIGN_ZO);
      openGear();
      typeZo("100");
      await swrLabel(100);
      typeZo(bad);
      const alert = await screen.findByRole("alert");
      expect(alert.textContent).toMatch(/Zo must be a number of ohms greater than 0/);
      expect(zoInput().getAttribute("aria-invalid")).toBe("true");
      // Nothing moved: not 50, not the design's 75, still the last good one.
      expect(screen.getByText("SWR (100 Ω)")).toBeTruthy();
      expect(JSON.parse(stored() ?? "null")).toEqual({ [HARNESS_EXAMPLE.name]: 100 });
    },
  );

  it("persists per design across a reload", async () => {
    mountDesignSession({
      routes: geometryRoute([]),
      storage: { [ZO_STORAGE_KEY]: JSON.stringify({ [HARNESS_EXAMPLE.name]: 50 }) },
    });
    await swrLabel(50);
    openGear();
    expect(zoInput().value).toBe("50");
    // Once the preview has said what the design's own is, the field says the
    // 50 is an override of it — and the readout stays on the override.
    await screen.findByText(/design: 75 Ω/);
    expect(screen.getByText("SWR (50 Ω)")).toBeTruthy();
  });

  it("an override stored for ANOTHER design does not apply here", async () => {
    mountDesignSession({
      routes: geometryRoute([]),
      storage: { [ZO_STORAGE_KEY]: JSON.stringify({ "dipoles.other": 300 }) },
    });
    await swrLabel(DESIGN_ZO);
  });

  it("reset, or typing the design's own value, clears the override", async () => {
    mountDesignSession({ routes: geometryRoute([]) });
    await swrLabel(DESIGN_ZO);
    openGear();
    typeZo("100");
    await swrLabel(100);
    fireEvent.click(screen.getByRole("button", { name: "reset" }));
    await swrLabel(DESIGN_ZO);
    expect(stored()).toBeNull();
    expect(zoInput().value).toBe("75");

    typeZo("100");
    await swrLabel(100);
    typeZo("75");
    await swrLabel(DESIGN_ZO);
    expect(stored()).toBeNull();
  });
});
