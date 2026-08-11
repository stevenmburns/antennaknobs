// The user-design reload button, end to end through a real <DesignSession>
// (issue #867). The unit pins live in CatalogPanel.test.tsx (visibility
// gating + click wiring) and params.test.ts (mergeSeededDefaults); what those
// cannot show is the reload actually reloading: a click re-fetches /examples
// (the server re-registers user designs on every GET — that fetch IS the
// reload) and re-runs the /geometry preview for the SAME selected design, and
// a param the edited file just grew shows up seeded without touching the
// selection. The solve leg past the preview rides the previewReady release
// (the design-switch path) and lives on the /ws socket, which setup.ts's
// InertWebSocket keeps silent — same non-goal as the harness documents.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mountDesignSession, HARNESS_EXAMPLE } from "./designSessionHarness";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";

const GAP_PARAM: SchemaParamSpec = {
  name: "gap",
  label: "Gap",
  default: 0.25,
  kind: "float",
  min: 0,
  max: 1,
  step: 0.05,
  precision: 2,
  unit: null,
  visible_when: null,
};

// The same design served twice: as first loaded, and as re-served after an
// "edit" added the Gap param. Which one /examples returns is the test's knob.
const USER_EXAMPLE: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  name: "user.probe",
  label: "Probe (user file)",
};
const USER_EXAMPLE_EDITED: ExampleDescriptor = {
  ...USER_EXAMPLE,
  param_schema: [GAP_PARAM],
};

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("user-design reload (issue #867)", () => {
  it("re-fetches /examples, re-previews the same design, and seeds a new param", async () => {
    let examplesCalls = 0;
    let geometryCalls = 0;
    mountDesignSession({
      examples: [USER_EXAMPLE],
      routes: {
        "/examples": () => {
          examplesCalls += 1;
          // First serve: the design as first loaded. Every later serve: the
          // edited file, one param richer.
          return jsonResponse({
            examples: [examplesCalls === 1 ? USER_EXAMPLE : USER_EXAMPLE_EDITED],
            errors: [],
          });
        },
        "/geometry": () => {
          geometryCalls += 1;
          return jsonResponse({ wires: [] });
        },
      },
    });

    // Catalog resolved, the user design auto-selected, the button gated in.
    const reload = await screen.findByRole("button", {
      name: "reload design file",
    });
    expect(examplesCalls).toBe(1);
    // The design-switch preview for the auto-selected design.
    await waitFor(() => expect(geometryCalls).toBe(1));
    expect(screen.queryByText("Gap")).toBeNull();

    await userEvent.setup().click(reload);

    // The reload re-fetched the catalog and re-ran the preview effect for the
    // same (still-selected) geometry.
    await waitFor(() => expect(examplesCalls).toBe(2));
    await waitFor(() => expect(geometryCalls).toBe(2));

    // The param the edit added rendered, seeded from its schema default —
    // merge-seed, not the old skip-if-seen (which would leave the bag without
    // a `gap` entry).
    const gapLabel = await screen.findByText("Gap");
    expect(gapLabel).toBeTruthy();
    const slider = screen.getByRole("slider", { name: "Gap" });
    expect(slider.getAttribute("aria-valuenow")).toBe("0.25");
  });
});
