// Pins GroundPanel's no-ground-support branches (issue #673 follow-up):
// the "ground plane ignored for <backend>" note, the disabled checkbox, and
// the withheld ground-type sub-panel. Every current Backend supports ground,
// so these branches are unreachable with real predicates — but issue #628
// moves `supports_ground` into the server-supplied backend roster, where a
// future solver can genuinely carry `false`. This file mocks the predicate
// (rather than casting a fake Backend string, which would render an
// undefined label) to pin the UI contract that server data will exercise.
//
// A separate file from GroundPanel.test.tsx because vi.mock is file-scoped
// and hoisted: the main matrix must keep testing the real predicates.
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GroundPanel } from "../components/session/GroundPanel";
import { BACKEND_LABEL, type Backend } from "../lib/backends";

// Pretend PyNEC is the ground-less solver. Both predicates are mocked in
// step: the real backendSupportsTerrain calls backendSupportsGround through
// a module-internal reference the mock cannot intercept, so overriding only
// one would leave the pair inconsistent.
vi.mock("../lib/backends", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/backends")>();
  const supports = (b: Backend) => b !== "pynec";
  return {
    ...actual,
    backendSupportsGround: supports,
    backendSupportsTerrain: supports,
  };
});

// Callbacks are supplied by the harness (and returned as spies) rather than
// overridable, so an assertion can never target a spy the component never got.
function renderGroundPanel(overrides: Partial<{
  backend: Backend;
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
      backend="pynec"
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

const IGNORED_NOTE = `ground plane ignored for ${BACKEND_LABEL.pynec}`;

describe("GroundPanel — backend without ground support (mocked predicate)", () => {
  it("shows the ignored note only while ground is enabled", () => {
    const on = renderGroundPanel({ groundEnabled: true });
    expect(screen.queryByText(IGNORED_NOTE)).not.toBeNull();
    on.unmount();

    renderGroundPanel({ groundEnabled: false });
    expect(screen.queryByText(IGNORED_NOTE)).toBeNull();
  });

  it("shows no note for a backend that supports ground", () => {
    renderGroundPanel({ backend: "bspline", groundEnabled: true });
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
    renderGroundPanel({ backend: "bspline", groundEnabled: true });
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
