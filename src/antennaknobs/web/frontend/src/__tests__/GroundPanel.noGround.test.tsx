// Pins GroundPanel's no-ground-support branches (issue #673 follow-up): the
// "ground plane ignored for <backend>" note, the disabled checkbox, and the
// withheld ground-type sub-panel.
//
// These branches used to be unreachable — every backend supports ground, so
// PR #683 reached them by vi.mock-ing the predicate. Issue #628 moved
// `supports_ground` into the server-supplied roster, so a fixture entry
// carrying `false` exercises them with real data: the mock is gone and the
// assertions below are unchanged from the mocked version.
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GroundPanel } from "../components/session/GroundPanel";
import type { BackendEntry } from "../lib/backends";
import { backendEntry, entry } from "./backendFixtures";

// A solver that models no ground — the capability a future momwire backend
// could genuinely report.
const GROUNDLESS: BackendEntry = backendEntry({
  name: "future-solver",
  label: "Future solver",
  supports_ground: false,
});

// Callbacks are supplied by the harness (and returned as spies) rather than
// overridable, so an assertion can never target a spy the component never got.
function renderGroundPanel(overrides: Partial<{
  backend: BackendEntry;
  groundEnabled: boolean;
}> = {}) {
  const spies = {
    setGroundEnabled: vi.fn(),
    setGroundType: vi.fn(),
    setFiniteGroundMethod: vi.fn(),
    setTerrainPreset: vi.fn(),
    setTerrainParams: vi.fn(),
  };
  const view = render(
    <GroundPanel
      backend={GROUNDLESS}
      groundEnabled={true}
      groundType="finite"
      finiteGroundMethod="fast"
      terrainPresets={[]}
      terrainPreset=""
      terrainParams={{}}
      {...overrides}
      {...spies}
    />,
  );
  return { ...view, ...spies, user: userEvent.setup() };
}

const IGNORED_NOTE = `ground plane ignored for ${GROUNDLESS.label}`;

describe("GroundPanel — backend without ground support (served supports_ground: false)", () => {
  it("shows the ignored note only while ground is enabled", () => {
    const on = renderGroundPanel({ groundEnabled: true });
    expect(screen.queryByText(IGNORED_NOTE)).not.toBeNull();
    on.unmount();

    renderGroundPanel({ groundEnabled: false });
    expect(screen.queryByText(IGNORED_NOTE)).toBeNull();
  });

  it("shows no note for a backend that supports ground", () => {
    renderGroundPanel({ backend: entry("bspline"), groundEnabled: true });
    expect(screen.queryByText(/ground plane ignored/)).toBeNull();
  });

  it("disables the checkbox, and clicking it fires nothing", async () => {
    const { user, setGroundEnabled } = renderGroundPanel({ groundEnabled: true });
    const box = screen.getByRole("checkbox", { name: /ground plane/ });
    expect(box).toHaveProperty("disabled", true);
    await user.click(box);
    expect(setGroundEnabled).not.toHaveBeenCalled();
  });

  it("keeps the checkbox enabled for a supporting backend", () => {
    renderGroundPanel({ backend: entry("bspline"), groundEnabled: true });
    expect(screen.getByRole("checkbox", { name: /ground plane/ })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("withholds the ground-type sub-panel even though groundEnabled is true", () => {
    renderGroundPanel({ groundEnabled: true });
    expect(screen.queryByRole("radiogroup", { name: "Ground type" })).toBeNull();
  });
});
