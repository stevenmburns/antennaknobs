// Pins the conditional-rendering matrix of the ground panel
// (src/components/session/GroundPanel.tsx, issue #673): checkbox gating of
// the ground-type sub-panel, the finite/PEC/terrain radio set (terrain only
// once presets exist), the finite-method radiogroup (finite only), and the
// terrain preset/knob/media-note rendering driven by the server-supplied
// TerrainPresetSchema — including the server-rename fallback to the first
// preset. Every visibility assertion is paired with an absence assertion —
// a presence-only test still passes if the conditional is deleted.
//
// The no-ground branches ("ground plane ignored for <backend>", the disabled
// checkbox) live in GroundPanel.noGround.test.tsx, driven by a roster fixture
// with supports_ground: false (issue #628). Every backend the server actually
// registers supports ground, so this file uses a real served entry.
import type { ComponentProps } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GroundPanel } from "../components/session/GroundPanel";
import type {
  TerrainFieldSchema,
  TerrainParams,
  TerrainPresetSchema,
} from "../lib/ground";
import { entry } from "./backendFixtures";

// --- fixtures --------------------------------------------------------------
// TerrainPresetSchema is server-supplied (GET /capabilities); there is no
// exported default to import, so these are modeled directly on the type
// (src/lib/ground.ts lines 35-50).

function terrainField(over: Partial<TerrainFieldSchema> = {}): TerrainFieldSchema {
  return {
    key: "height",
    label: "crest height",
    unit: "m",
    default: 5,
    min: 0,
    max: 20,
    step: 0.5,
    ...over,
  };
}

function terrainPreset(over: Partial<TerrainPresetSchema> = {}): TerrainPresetSchema {
  return {
    name: "levee",
    label: "Levee crest",
    tooltip: "Levee tooltip text",
    media_note: "Levee media note",
    fields: [terrainField()],
    ...over,
  };
}

// Callbacks are supplied by the harness (and returned as spies) rather than
// overridable, so an assertion can never target a spy the component never got.
type GroundOverrides = Partial<
  Omit<
    ComponentProps<typeof GroundPanel>,
    | "setGroundEnabled"
    | "setGroundType"
    | "setFiniteGroundMethod"
    | "setTerrainPreset"
    | "setTerrainParams"
  >
>;

function renderGroundPanel(overrides: GroundOverrides = {}) {
  const spies = {
    setGroundEnabled: vi.fn(),
    setGroundType: vi.fn(),
    setFiniteGroundMethod: vi.fn(),
    setTerrainPreset: vi.fn(),
    setTerrainParams: vi.fn(),
  };
  const view = render(
    <GroundPanel
      backend={entry("bspline")}
      groundEnabled={false}
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

// NumberField's <label> wraps only the caption/value spans, not the input, so
// there is no label→control association for getByLabelText to follow: locate
// the field by its caption text and step out to the sibling input.
function numberField(label: string): HTMLInputElement {
  const field = screen.getByText(label).closest(".field");
  if (!field) throw new Error(`no .field wrapper for "${label}"`);
  return within(field as HTMLElement).getByRole("spinbutton") as HTMLInputElement;
}

describe("GroundPanel — ground-plane checkbox", () => {
  it("reflects groundEnabled", () => {
    const off = renderGroundPanel({ groundEnabled: false });
    expect(screen.getByRole("checkbox", { name: /ground plane/ })).toHaveProperty(
      "checked",
      false,
    );
    off.unmount();

    renderGroundPanel({ groundEnabled: true });
    expect(screen.getByRole("checkbox", { name: /ground plane/ })).toHaveProperty(
      "checked",
      true,
    );
  });

  it("fires setGroundEnabled(true) when checked from off", async () => {
    const { user, setGroundEnabled } = renderGroundPanel({ groundEnabled: false });
    await user.click(screen.getByRole("checkbox", { name: /ground plane/ }));
    expect(setGroundEnabled).toHaveBeenCalledWith(true);
    expect(setGroundEnabled).toHaveBeenCalledTimes(1);
  });

  it("fires setGroundEnabled(false) when unchecked from on", async () => {
    const { user, setGroundEnabled } = renderGroundPanel({ groundEnabled: true });
    await user.click(screen.getByRole("checkbox", { name: /ground plane/ }));
    expect(setGroundEnabled).toHaveBeenCalledWith(false);
    expect(setGroundEnabled).toHaveBeenCalledTimes(1);
  });
});

describe("GroundPanel — sub-panel gating", () => {
  it("hides the ground-type radiogroup while ground is disabled", () => {
    renderGroundPanel({ groundEnabled: false });
    expect(screen.queryByRole("radiogroup", { name: "Ground type" })).toBeNull();
  });

  it("shows the ground-type radiogroup once ground is enabled", () => {
    renderGroundPanel({ groundEnabled: true });
    expect(screen.queryByRole("radiogroup", { name: "Ground type" })).not.toBeNull();
  });
});

describe("GroundPanel — ground-type radios", () => {
  it("always offers finite and PEC", () => {
    renderGroundPanel({ groundEnabled: true, terrainPresets: [] });
    expect(screen.getByRole("radio", { name: /^finite/ })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "PEC" })).toBeTruthy();
  });

  it("hides the terrain radio when there are no presets", () => {
    renderGroundPanel({ groundEnabled: true, terrainPresets: [] });
    expect(screen.queryByRole("radio", { name: "terrain" })).toBeNull();
  });

  it("offers the terrain radio when presets exist", () => {
    renderGroundPanel({ groundEnabled: true, terrainPresets: [terrainPreset()] });
    expect(screen.queryByRole("radio", { name: "terrain" })).not.toBeNull();
  });

  // Each case starts from a groundType OTHER than the one clicked: a radio
  // that is already checked does not re-fire onChange, and the harness spy
  // never writes state back into the checked prop.
  it.each([
    ["finite", "pec", /^finite/],
    ["pec", "finite", "PEC"],
    ["terrain", "finite", "terrain"],
  ] as const)("fires setGroundType(%s) when that radio is clicked", async (
    clicked,
    startingFrom,
    name,
  ) => {
    const { user, setGroundType } = renderGroundPanel({
      groundEnabled: true,
      groundType: startingFrom,
      terrainPresets: [terrainPreset()],
    });
    await user.click(screen.getByRole("radio", { name }));
    expect(setGroundType).toHaveBeenCalledWith(clicked);
    expect(setGroundType).toHaveBeenCalledTimes(1);
  });

  it("checks the radio matching groundType", () => {
    renderGroundPanel({
      groundEnabled: true,
      groundType: "pec",
      terrainPresets: [terrainPreset()],
    });
    expect(screen.getByRole("radio", { name: /^finite/ })).toHaveProperty("checked", false);
    expect(screen.getByRole("radio", { name: "PEC" })).toHaveProperty("checked", true);
    expect(screen.getByRole("radio", { name: "terrain" })).toHaveProperty("checked", false);
  });
});

describe("GroundPanel — finite-ground method sub-radiogroup", () => {
  it("shows the method radiogroup only for groundType finite", () => {
    const finite = renderGroundPanel({ groundEnabled: true, groundType: "finite" });
    expect(
      screen.queryByRole("radiogroup", { name: "Finite-ground solve method" }),
    ).not.toBeNull();
    finite.unmount();

    const pec = renderGroundPanel({ groundEnabled: true, groundType: "pec" });
    expect(
      screen.queryByRole("radiogroup", { name: "Finite-ground solve method" }),
    ).toBeNull();
    pec.unmount();

    renderGroundPanel({
      groundEnabled: true,
      groundType: "terrain",
      terrainPresets: [terrainPreset()],
    });
    expect(
      screen.queryByRole("radiogroup", { name: "Finite-ground solve method" }),
    ).toBeNull();
  });

  // Same already-checked-radio caveat as the ground-type clicks above: start
  // each case from the OTHER method so the click is a real state change.
  it("fires setFiniteGroundMethod(sommerfeld) when Sommerfeld is clicked", async () => {
    const { user, setFiniteGroundMethod } = renderGroundPanel({
      groundEnabled: true,
      groundType: "finite",
      finiteGroundMethod: "fast",
    });
    await user.click(screen.getByRole("radio", { name: "Sommerfeld" }));
    expect(setFiniteGroundMethod).toHaveBeenCalledWith("sommerfeld");
    expect(setFiniteGroundMethod).toHaveBeenCalledTimes(1);
  });

  it("fires setFiniteGroundMethod(fast) when refl-coef is clicked", async () => {
    const { user, setFiniteGroundMethod } = renderGroundPanel({
      groundEnabled: true,
      groundType: "finite",
      finiteGroundMethod: "sommerfeld",
    });
    await user.click(screen.getByRole("radio", { name: /^refl-coef/ }));
    expect(setFiniteGroundMethod).toHaveBeenCalledWith("fast");
    expect(setFiniteGroundMethod).toHaveBeenCalledTimes(1);
  });

  it("checks the radio matching finiteGroundMethod", () => {
    renderGroundPanel({
      groundEnabled: true,
      groundType: "finite",
      finiteGroundMethod: "sommerfeld",
    });
    expect(screen.getByRole("radio", { name: /^refl-coef/ })).toHaveProperty(
      "checked",
      false,
    );
    expect(screen.getByRole("radio", { name: "Sommerfeld" })).toHaveProperty(
      "checked",
      true,
    );
  });
});

describe("GroundPanel — terrain sub-panel", () => {
  const levee = terrainPreset({
    name: "levee",
    label: "Levee crest",
    tooltip: "Levee tooltip text",
    media_note: "Levee media note",
    fields: [
      terrainField({
        key: "height",
        label: "crest height",
        unit: "m",
        default: 5,
      }),
      terrainField({
        key: "setback",
        label: "setback",
        unit: null,
        default: 3,
      }),
    ],
  });
  const cliff = terrainPreset({
    name: "cliff",
    label: "Cliff edge",
    tooltip: "Cliff tooltip text",
    media_note: "Cliff media note",
    fields: [
      terrainField({
        key: "drop",
        label: "drop height",
        unit: "m",
        default: 8,
      }),
    ],
  });
  const presets = [levee, cliff];

  it("renders one radio per preset, labelled and titled from the schema", () => {
    renderGroundPanel({
      groundEnabled: true,
      groundType: "terrain",
      terrainPresets: presets,
      terrainPreset: "levee",
    });
    const leveeRadio = screen.getByRole("radio", { name: "Levee crest" });
    expect(leveeRadio.closest("label")?.getAttribute("title")).toBe(
      "Levee tooltip text",
    );
    const cliffRadio = screen.getByRole("radio", { name: "Cliff edge" });
    expect(cliffRadio.closest("label")?.getAttribute("title")).toBe(
      "Cliff tooltip text",
    );
  });

  it("fires setTerrainPreset with the clicked preset's name", async () => {
    const { user, setTerrainPreset } = renderGroundPanel({
      groundEnabled: true,
      groundType: "terrain",
      terrainPresets: presets,
      terrainPreset: "levee",
    });
    await user.click(screen.getByRole("radio", { name: "Cliff edge" }));
    expect(setTerrainPreset).toHaveBeenCalledWith("cliff");
    expect(setTerrainPreset).toHaveBeenCalledTimes(1);
  });

  it("checks the radio and shows the fields of the preset named by terrainPreset", () => {
    renderGroundPanel({
      groundEnabled: true,
      groundType: "terrain",
      terrainPresets: presets,
      terrainPreset: "cliff",
    });
    expect(screen.getByRole("radio", { name: "Levee crest" })).toHaveProperty(
      "checked",
      false,
    );
    expect(screen.getByRole("radio", { name: "Cliff edge" })).toHaveProperty(
      "checked",
      true,
    );
    expect(numberField("drop height (m)")).toBeTruthy();
    expect(screen.queryByText("crest height (m)")).toBeNull();
  });

  it("falls back to the first preset when terrainPreset names one absent from the list", () => {
    renderGroundPanel({
      groundEnabled: true,
      groundType: "terrain",
      terrainPresets: presets,
      terrainPreset: "renamed-on-server",
    });
    expect(screen.getByRole("radio", { name: "Levee crest" })).toHaveProperty(
      "checked",
      true,
    );
    expect(screen.getByRole("radio", { name: "Cliff edge" })).toHaveProperty(
      "checked",
      false,
    );
    expect(numberField("crest height (m)")).toBeTruthy();
    expect(screen.queryByText("drop height (m)")).toBeNull();
  });

  it("labels a knob with the unit when set, bare when not", () => {
    renderGroundPanel({
      groundEnabled: true,
      groundType: "terrain",
      terrainPresets: presets,
      terrainPreset: "levee",
    });
    expect(numberField("crest height (m)")).toBeTruthy(); // unit set
    expect(numberField("setback")).toBeTruthy(); // unit null -> bare label
  });

  it("uses terrainParams[key] when present, else the field default", () => {
    renderGroundPanel({
      groundEnabled: true,
      groundType: "terrain",
      terrainPresets: presets,
      terrainPreset: "levee",
      terrainParams: { height: 12 },
    });
    expect(numberField("crest height (m)").value).toBe("12"); // overridden
    expect(numberField("setback").value).toBe("3"); // falls back to default
  });

  it("commits an edit through setTerrainParams as an updater over the previous params", async () => {
    const { user, setTerrainParams } = renderGroundPanel({
      groundEnabled: true,
      groundType: "terrain",
      terrainPresets: presets,
      terrainPreset: "levee",
      terrainParams: { height: 5 },
    });
    await user.type(numberField("setback"), "9"); // "3" -> "39"
    expect(setTerrainParams).toHaveBeenCalledTimes(1);
    const updater = setTerrainParams.mock.calls[0][0] as (
      p: TerrainParams,
    ) => TerrainParams;
    const sample = { height: 5, other: 1 };
    expect(updater(sample)).toEqual({ ...sample, setback: 39 });
  });

  it("renders the active preset's media_note", () => {
    const first = renderGroundPanel({
      groundEnabled: true,
      groundType: "terrain",
      terrainPresets: presets,
      terrainPreset: "levee",
    });
    expect(screen.queryByText("Levee media note")).not.toBeNull();
    expect(screen.queryByText("Cliff media note")).toBeNull();
    first.unmount();

    renderGroundPanel({
      groundEnabled: true,
      groundType: "terrain",
      terrainPresets: presets,
      terrainPreset: "cliff",
    });
    expect(screen.queryByText("Cliff media note")).not.toBeNull();
    expect(screen.queryByText("Levee media note")).toBeNull();
  });
});

describe("GroundPanel — PEC excludes finite-method and terrain content", () => {
  it("renders neither the finite-method radiogroup nor terrain content for PEC", () => {
    renderGroundPanel({
      groundEnabled: true,
      groundType: "pec",
      terrainPresets: [terrainPreset({ name: "levee", label: "Levee crest" })],
    });
    expect(
      screen.queryByRole("radiogroup", { name: "Finite-ground solve method" }),
    ).toBeNull();
    expect(screen.queryByRole("radiogroup", { name: "Terrain preset" })).toBeNull();
    expect(screen.queryByRole("radio", { name: "Levee crest" })).toBeNull();
  });
});

describe("GroundPanel — ground-requirement notice", () => {
  const NOTICE = "buried design — Sommerfeld ground selected automatically";

  it("renders the notice when the design declares sommerfeld", () => {
    renderGroundPanel({ groundEnabled: true, groundRequirement: "sommerfeld" });
    expect(screen.queryByText(NOTICE)).not.toBeNull();
  });

  it("renders no notice without a requirement (absent or null)", () => {
    const absent = renderGroundPanel({ groundEnabled: true });
    expect(screen.queryByText(NOTICE)).toBeNull();
    absent.unmount();

    renderGroundPanel({ groundEnabled: true, groundRequirement: null });
    expect(screen.queryByText(NOTICE)).toBeNull();
  });

  it("shows the notice even while ground is toggled off — the requirement text explains why it will come back", () => {
    // The notice is keyed on the DESIGN, not on the current selection state:
    // a user who unchecks the ground plane should still see why the panel
    // seeded itself (the by-name solver refusal remains the enforcement).
    renderGroundPanel({ groundEnabled: false, groundRequirement: "sommerfeld" });
    expect(screen.queryByText(NOTICE)).not.toBeNull();
  });
});
